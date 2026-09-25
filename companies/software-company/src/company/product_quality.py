"""Compile project-specific quality contracts and verify authenticated evidence.

This is an additive, fail-closed assessment layer (root ADR-0018), NOT a test runner,
identity provider, deploy authorizer, or automatic replacement for HumanGate.
The coordinator must pin the contract, candidate, context and author identities.
Signer keys and the evidence store must be inaccessible to implementation workers.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StringConstraints,
    model_serializer,
    model_validator,
)

from .delivery_contract import DeliveryContract, DeliveryReport, adopted_source, delivery_gaps

POLICY_VERSION = "product-excellence/2"
POLICY_VERSION_V3 = "product-excellence/3"
MAX_EVIDENCE_AGE = timedelta(hours=24)
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
DEFAULT_CHECK_ID = "performance.budget"
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Revision = Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
Domain = Literal["general", "education", "healthcare", "finance", "commerce", "enterprise", "industrial", "content"]
Surface = Literal["web", "mobile_app", "desktop", "api", "cli", "library"]
Mode = Literal["runner", "independent_review"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, revalidate_instances="always")


class DesignBrief(StrictModel):
    """Project-specific rationale, never a universal aesthetic or template."""
    research_basis: Text
    research_status: Literal["observed", "hypothesis", "mixed"]
    primary_tasks: Text
    layout_rationale: Text
    visual_direction: Text
    information_density: Text
    content_tone: Text
    component_system: Text
    interaction_states: Text
    accessibility_plan: Text
    validation_plan: Text
    devices: list[Text] = Field(min_length=1)
    locales: list[Text] = Field(min_length=1)


class AcceptanceCriterion(StrictModel):
    id: Text
    outcome: Text
    verification: Text


class QualityTarget(StrictModel):
    id: Text
    unit: Text
    operator: Literal["lte", "gte"]
    value: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    conditions: Text
    check_id: str = DEFAULT_CHECK_ID

    @model_serializer(mode="wrap")
    def serialize_target(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.check_id == DEFAULT_CHECK_ID:
            document.pop("check_id", None)  # Preserve pre-adoption v2 contract bytes.
        return document


class EvidencePolicy(StrictModel):
    max_age_seconds: int = Field(ge=3600, le=604800)
    max_artifact_bytes: int = Field(ge=1, le=268435456)


class ProjectProfile(StrictModel):
    schema_version: Literal[1]
    project_id: Text
    run_id: Text
    goal: Text
    domains: list[Domain] = Field(min_length=1)
    surfaces: list[Surface] = Field(min_length=1)
    audiences: list[Text] = Field(min_length=1)
    critical_journeys: list[Text] = Field(min_length=1)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    quality_targets: list[QualityTarget] = Field(min_length=1)
    non_goals: list[Text] = Field(min_length=1)
    constraints: list[Text] = Field(min_length=1)
    technology_rationale: Text
    scale_and_slo: Text
    data_classification: Literal["public", "internal", "sensitive"]
    persists_data: bool
    operates_service: bool
    serves_children: bool
    uses_ai: bool
    completion_target: Literal["verified", "merged", "staging", "production"]
    design: DesignBrief | None = None
    delivery: DeliveryContract | None = None
    evidence_policy: EvidencePolicy | None = None

    @model_serializer(mode="wrap")
    def serialize_profile(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.delivery is None:
            document.pop("delivery", None)  # Preserve pre-adoption v2 contract bytes.
        if self.evidence_policy is None:
            document.pop("evidence_policy", None)  # Preserve pre-adoption v2 contract bytes.
        return document

    @model_validator(mode="after")
    def coherent(self) -> ProjectProfile:
        for values in (self.domains, self.surfaces):
            if len(values) != len(set(values)):
                raise ValueError("domain and surface entries must be unique")
        for items in (self.acceptance_criteria, self.quality_targets):
            identifiers = [item.id for item in items]
            if len(identifiers) != len(set(identifiers)):
                raise ValueError("acceptance and target identifiers must be unique")
        if set(self.surfaces) & {"web", "mobile_app", "desktop"} and self.design is None:
            raise ValueError("a graphical product requires a project-specific design brief")
        if self.completion_target in {"staging", "production"} and not self.operates_service:
            raise ValueError("deployment target requires operates_service=true")
        if self.delivery is not None:
            self.delivery.validate_acceptance({a.id for a in self.acceptance_criteria})
        allowed_check_ids = {check.id for check in required_checks(self)}
        for target in self.quality_targets:
            if target.check_id not in allowed_check_ids:
                raise ValueError(f"quality target check_id must reference a required check: {target.check_id}")
        return self


@dataclass(frozen=True)
class Check:
    id: str
    dimension: str
    mode: Mode
    criterion: str


def _checks(rows: list[tuple[str, str, Mode, str]]) -> tuple[Check, ...]:
    return tuple(Check(*row) for row in rows)


BASE_CHECKS = _checks([
    ("goal.traceability", "product_fitness", "independent_review", "Every mandatory outcome has acceptance evidence; no stubs or scope drift."),
    ("architecture.fitness", "architecture", "independent_review", "ADR explains boundaries, alternatives, evolution and minimal necessary complexity."),
    ("technology.support", "technology", "independent_review", "Supported versions, licenses, dependencies, upgrade path and operating fit are verified."),
    ("engineering.static", "engineering", "runner", "Applicable build/lint/type checks run on the candidate; omissions require contract justification."),
    ("testing.unit", "correctness", "runner", "Relevant unit and regression tests pass without weakened assertions or hidden failures."),
    ("testing.integration", "compatibility", "runner", "Component/API contracts and failure paths work with representative dependencies."),
    ("testing.acceptance", "product_fitness", "runner", "Critical journeys complete against real outcomes, not just success messages."),
    ("security.threat_model", "application_security", "independent_review", "Threat model and versioned applicable security requirements cover the actual attack surface."),
    ("security.verification", "application_security", "runner", "Applicable authorization, input, secrets and dependency checks have no unresolved blocking findings."),
    ("supply_chain.inventory", "supply_chain", "runner", "Dependency inventory, provenance and license evidence are traceable to the build."),
    ("maintainability.review", "maintainability", "independent_review", "Independent review checks cohesion, duplication, complexity, tests and extension seams."),
    ("performance.budget", "performance", "runner", "Representative load/device/data measurements meet the declared budgets."),
    ("reliability.failure_paths", "reliability", "runner", "Timeouts, retries, partial failure and recovery preserve stated invariants."),
    ("documentation.handover", "operability", "independent_review", "Setup, configuration, troubleshooting and maintenance instructions match the candidate."),
    ("domain.fitness", "domain", "independent_review", "Workflows, terminology and assumptions fit these users and industries, not a generic template."),
])
UI_CHECKS = _checks([
    ("design.rationale", "ux", "independent_review", "Research status, task model, layout and visual direction are coherent for this project."),
    ("design.system", "ui", "independent_review", "Tokens, typography, hierarchy, components and content are consistent with the design brief."),
    ("design.visual", "ui", "independent_review", "Rendered screens with realistic content meet the project rubric; no universal aesthetic score."),
    ("design.responsive_states", "ux", "runner", "Target devices, locales, loading/empty/error/success/permission states are exercised."),
    ("accessibility.automated", "accessibility", "runner", "Automated checks cover applicable accessibility rules on critical journeys."),
    ("accessibility.interaction", "accessibility", "independent_review", "Keyboard, focus, zoom, reading order and assistive interaction are checked; automated scans alone are insufficient."),
    ("usability.journeys", "ux", "independent_review", "Task-based usability evaluation records evidence and separates simulated findings from real-user research."),
])
DATA_CHECKS = _checks([
    ("data.integrity", "data_integrity", "runner", "Migration, constraints, concurrent updates and retry/idempotency preserve data invariants."),
    ("data.restore", "reliability", "runner", "A representative backup is actually restored and checked against stated recovery objectives."),
])
SERVICE_CHECKS = _checks([
    ("operations.observability", "operability", "runner", "Health, logs, metrics and actionable alerts work without leaking sensitive data."),
    ("operations.runbook", "operability", "independent_review", "Deployment, incident response, ownership, rollback and lifecycle costs are explicit."),
    ("operations.recovery", "reliability", "runner", "Rollback or roll-forward recovery is rehearsed in an authorized environment."),
])
EXTRA_CHECKS = _checks([
    ("privacy.lifecycle", "privacy", "independent_review", "Minimization, retention, deletion, access and sensitive telemetry follow the project obligations."),
    ("domain.obligations", "domain", "independent_review", "Jurisdiction, harm scenarios and applicable obligations are mapped; required external expertise is not fabricated."),
    ("children.safeguards", "safety", "independent_review", "Age-appropriate flows, privacy and misuse risks are explicitly assessed."),
    ("ai.evaluation", "ai", "runner", "Task-specific evals cover factuality, unsafe input, injection, privacy, fallback, latency and cost."),
    ("integration.candidate", "delivery", "runner", "Required CI passes on the exact integrated candidate; old-branch green is not reused blindly."),
    ("release.receipt", "delivery", "runner", "Authorized deployment receipt and post-deploy health/smoke checks match the candidate and target."),
])
DELIVERY_CHECK = Check("delivery.definition", "delivery", "runner",
                       "Pinned Ready/Done/Complete contract is met; every applicable gate actually ran; no false-green no-op.")
CATALOG = {check.id: check for check in (*BASE_CHECKS, *UI_CHECKS, *DATA_CHECKS, *SERVICE_CHECKS, *EXTRA_CHECKS, DELIVERY_CHECK)}


def required_checks(profile: ProjectProfile) -> tuple[Check, ...]:
    """Checks may be added by applicability, never removed by a worker verdict."""
    selected = list(BASE_CHECKS)
    if set(profile.surfaces) & {"web", "mobile_app", "desktop"}:
        selected.extend(UI_CHECKS)
    if profile.persists_data:
        selected.extend(DATA_CHECKS)
    if profile.operates_service:
        selected.extend(SERVICE_CHECKS)
    extra: list[str] = []
    if profile.data_classification == "sensitive" or profile.serves_children:
        extra.append("privacy.lifecycle")
    if set(profile.domains) & {"healthcare", "finance", "industrial"}:
        extra.append("domain.obligations")
    if profile.serves_children:
        extra.append("children.safeguards")
    if profile.uses_ai:
        extra.append("ai.evaluation")
    if profile.completion_target != "verified":
        extra.append("integration.candidate")
    if profile.completion_target in {"staging", "production"}:
        extra.append("release.receipt")
    if profile.delivery is not None:
        extra.append(DELIVERY_CHECK.id)
    selected.extend(CATALOG[name] for name in extra)
    return tuple(sorted(selected, key=lambda check: check.id))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _uses_v3_policy(profile: ProjectProfile) -> bool:
    if profile.evidence_policy is not None:
        return True
    return any(target.check_id != DEFAULT_CHECK_ID for target in profile.quality_targets)


def compile_contract(profile: ProjectProfile) -> dict[str, Any]:
    profile = ProjectProfile.model_validate(profile)
    policy = profile.evidence_policy
    max_age_seconds = policy.max_age_seconds if policy is not None else MAX_EVIDENCE_AGE.total_seconds()
    max_artifact_bytes = policy.max_artifact_bytes if policy is not None else MAX_ARTIFACT_BYTES
    body = {"policy_version": POLICY_VERSION_V3 if _uses_v3_policy(profile) else POLICY_VERSION,
            "evidence_policy": {"max_age_seconds": max_age_seconds,
                                "max_artifact_bytes": max_artifact_bytes, "signature": "HMAC-SHA256"},
            "profile": profile.model_dump(mode="json"),
            "checks": [asdict(check) for check in required_checks(profile)]}
    if profile.delivery is not None:
        body["template_source"] = adopted_source()
    return {**body, "contract_hash": hashlib.sha256(_canonical(body)).hexdigest()}


class Evidence(StrictModel):
    schema_version: Literal[1]
    check_id: Text
    run_id: Text
    candidate_sha: Revision
    context_hash: Digest
    contract_hash: Digest
    issuer: Text
    status: Literal["pass", "fail", "blocked", "unknown"]
    created_at: AwareDatetime
    expires_at: AwareDatetime
    artifact_path: Text
    artifact_sha256: Digest
    details: Text
    covered_acceptance: list[Text] = Field(default_factory=list)
    measurements: dict[str, Annotated[float, Field(allow_inf_nan=False)]] = Field(default_factory=dict)

    delivery_report: DeliveryReport | None = None

    @model_serializer(mode="wrap")
    def serialize_evidence(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        document: dict[str, Any] = handler(self)
        if self.delivery_report is None:
            document.pop("delivery_report", None)  # Preserve signatures and lost-ACK fingerprints for old runs.
        return document

    @model_validator(mode="after")
    def valid_window(self) -> Evidence:
        if self.expires_at <= self.created_at:
            raise ValueError("evidence expiry must follow creation")
        return self


class Receipt(StrictModel):
    evidence: Evidence
    signature: Digest


@dataclass(frozen=True)
class TrustedIssuer:
    """Provisioned out-of-band, not accepted from worker receipts or prompts."""
    principal_id: str
    mode: Mode
    allowed_checks: frozenset[str]
    key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not self.principal_id.strip() or self.mode not in {"runner", "independent_review"} or len(self.key) < 32:
            raise ValueError("invalid trust configuration")
        if not self.allowed_checks or not self.allowed_checks <= CATALOG.keys():
            raise ValueError("issuer must be scoped to known checks")


def sign_evidence(evidence: Evidence, key: bytes) -> Receipt:
    """For a trusted driver AFTER checking the real outcome, not for workers."""
    if len(key) < 32:
        raise ValueError("signing key requires at least 32 bytes")
    signature = hmac.new(key, _canonical(evidence.model_dump(mode="json")), hashlib.sha256).hexdigest()
    return Receipt(evidence=evidence, signature=signature)


@dataclass(frozen=True)
class Assessment:
    quality_pass: bool
    contract_hash: str
    candidate_sha: str
    completion_target: str
    required: tuple[str, ...]
    passed: tuple[str, ...]
    blockers: tuple[str, ...]


def _artifact_valid(root: Path, evidence: Evidence, max_artifact_bytes: int = MAX_ARTIFACT_BYTES) -> bool:
    path = PurePosixPath(evidence.artifact_path)
    if path.is_absolute() or ".." in path.parts or "\\" in evidence.artifact_path or ":" in evidence.artifact_path:
        return False
    try:
        base = root.resolve(strict=True)
        artifact = (base / str(path)).resolve(strict=True)
        if not artifact.is_relative_to(base) or not artifact.is_file():
            return False
        size = artifact.stat().st_size
        if size <= 0 or size > max_artifact_bytes:
            return False
        digest = hashlib.sha256()
        with artifact.open("rb") as stream:
            for chunk in iter(lambda: stream.read(65536), b""):
                digest.update(chunk)
        return hmac.compare_digest(digest.hexdigest(), evidence.artifact_sha256)
    except (OSError, ValueError, RuntimeError):
        return False


def _effective_policy(profile: ProjectProfile) -> tuple[timedelta, int]:
    policy = profile.evidence_policy
    if policy is None:
        return MAX_EVIDENCE_AGE, MAX_ARTIFACT_BYTES
    return timedelta(seconds=policy.max_age_seconds), policy.max_artifact_bytes


def _targets_met(profile: ProjectProfile, evidence: Evidence, check_id: str) -> bool:
    for target in profile.quality_targets:
        if target.check_id != check_id:
            continue
        value = evidence.measurements.get(target.id)
        if value is None:
            return False
        if target.operator == "lte" and value > target.value:
            return False
        if target.operator == "gte" and value < target.value:
            return False
    return True


def assess(
    profile: ProjectProfile,
    receipts: list[Receipt],
    *,
    expected_contract_hash: str,
    candidate_sha: str,
    context_hash: str,
    author_principals: frozenset[str],
    trusted_issuers: dict[str, TrustedIssuer],
    evidence_root: Path,
    now: datetime | None = None,
) -> Assessment:
    """Fail closed. PASS is evidence eligibility, never deploy authority or certification.

    Expected inputs and the COMPLETE author set come from the trusted coordinator.
    Exact duplicate receipts are idempotent; conflicting receipts require reconciliation.
    A signature authenticates the driver, not the correctness of its test methodology.
    """
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    contract_hash = str(compile_contract(profile)["contract_hash"])
    checks = {check.id: check for check in required_checks(profile)}
    max_evidence_age, max_artifact_bytes = _effective_policy(profile)
    targeted_check_ids = {target.check_id for target in profile.quality_targets}
    blockers: list[str] = []
    passed: list[str] = []
    if not hmac.compare_digest(contract_hash, expected_contract_hash):
        blockers.append("contract:changed_or_unpinned")
    if not author_principals or any(not principal.strip() for principal in author_principals):
        blockers.append("identity:missing_author_set")
    seen_keys: dict[bytes, str] = {}
    for trusted in trusted_issuers.values():
        if trusted.key in seen_keys and seen_keys[trusted.key] != trusted.principal_id:
            blockers.append("identity:shared_key_across_principals")
        seen_keys[trusted.key] = trusted.principal_id
    by_check: dict[str, list[Receipt]] = defaultdict(list)
    seen_receipts: set[bytes] = set()
    for receipt in receipts:
        fingerprint = _canonical(receipt.model_dump(mode="json"))
        if fingerprint in seen_receipts:
            continue
        seen_receipts.add(fingerprint)
        by_check[receipt.evidence.check_id].append(receipt)
    for unknown in sorted(by_check.keys() - checks.keys()):
        blockers.append(f"{unknown}:unexpected_check")
    for check_id, check in checks.items():
        candidates = by_check.get(check_id, [])
        if len(candidates) != 1:
            blockers.append(f"{check_id}:{'missing' if not candidates else 'conflicting_receipts'}")
            continue
        receipt = candidates[0]
        evidence = receipt.evidence
        issuer = trusted_issuers.get(evidence.issuer)
        reason = ""
        if issuer is None or issuer.mode != check.mode or check_id not in issuer.allowed_checks:
            reason = "unauthorized_issuer"
        elif not hmac.compare_digest(receipt.signature, sign_evidence(evidence, issuer.key).signature):
            reason = "invalid_signature"
        elif evidence.run_id != profile.run_id or evidence.contract_hash != contract_hash:
            reason = "wrong_run_or_contract"
        elif evidence.candidate_sha != candidate_sha or evidence.context_hash != context_hash:
            reason = "stale_candidate_or_context"
        elif not (evidence.created_at <= current < evidence.expires_at) or current - evidence.created_at > max_evidence_age:
            reason = "expired_or_future_evidence"
        elif check.mode == "independent_review" and issuer.principal_id in author_principals:
            reason = "self_approval"
        elif evidence.status != "pass":
            reason = f"status_{evidence.status}"
        elif check_id == "testing.acceptance" and set(evidence.covered_acceptance) != {c.id for c in profile.acceptance_criteria}:
            reason = "incomplete_acceptance_coverage"
        elif check_id in targeted_check_ids and not _targets_met(profile, evidence, check_id):
            reason = "missing_or_unmet_quality_target"
        elif check_id == DELIVERY_CHECK.id and profile.delivery is not None and (
            gaps := delivery_gaps(profile.delivery, evidence.delivery_report, profile.completion_target)
        ):
            reason = "delivery_unmet:" + ";".join(gaps)
        elif not _artifact_valid(evidence_root, evidence, max_artifact_bytes):
            reason = "missing_changed_or_unsafe_artifact"
        if reason:
            blockers.append(f"{check_id}:{reason}")
        else:
            passed.append(check_id)
    return Assessment(not blockers, contract_hash, candidate_sha, profile.completion_target,
                      tuple(checks), tuple(passed), tuple(blockers))


def _read_trust(path: Path) -> dict[str, TrustedIssuer]:
    """Registry and key files are coordinator-owned, outside worker sandboxes."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, TrustedIssuer] = {}
    if not isinstance(raw, dict):
        raise ValueError("trust registry must be an object")
    for issuer_id, config in raw.items():
        if not isinstance(config, dict) or set(config) != {"principal_id", "mode", "allowed_checks", "key_file"}:
            raise ValueError("invalid trust registry entry")
        if not isinstance(config["allowed_checks"], list):
            raise ValueError("allowed_checks must be a list")
        key_path = Path(config["key_file"])
        if not key_path.is_absolute():
            key_path = path.parent / key_path
        result[issuer_id] = TrustedIssuer(config["principal_id"], config["mode"],
                                         frozenset(config["allowed_checks"]), key_path.read_bytes())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project-specific, quality-first contract and evidence assessment")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("schema")
    plan = sub.add_parser("plan")
    plan.add_argument("profile", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("profile", type=Path)
    verify.add_argument("receipts", type=Path)
    for name in ("candidate-sha", "context-hash", "contract-hash"):
        verify.add_argument(f"--{name}", required=True)
    verify.add_argument("--author", action="append", required=True)
    verify.add_argument("--trust-registry", type=Path, required=True)
    verify.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "schema":
            output = ProjectProfile.model_json_schema()
            code = 0
        else:
            profile = ProjectProfile.model_validate_json(args.profile.read_text(encoding="utf-8"))
            if args.command == "plan":
                output = compile_contract(profile)
                code = 0
            else:
                raw = json.loads(args.receipts.read_text(encoding="utf-8"))
                if not isinstance(raw, list):
                    raise ValueError("receipts must be an array")
                receipts = [Receipt.model_validate_json(json.dumps(item)) for item in raw]
                result = assess(profile, receipts, expected_contract_hash=args.contract_hash,
                                candidate_sha=args.candidate_sha, context_hash=args.context_hash,
                                author_principals=frozenset(args.author), trusted_issuers=_read_trust(args.trust_registry),
                                evidence_root=args.evidence_root)
                output = asdict(result)
                code = 0 if result.quality_pass else 1
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return code
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        # Do not echo malformed inputs: a registry may contain credential material.
        print(f"Invalid quality input ({type(error).__name__}); no approval issued.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
