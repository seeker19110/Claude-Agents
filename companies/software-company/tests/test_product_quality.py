"""Offline tests: fixture receipts are synthetic, not product certifications."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from company.product_quality import (
    CATALOG,
    MAX_ARTIFACT_BYTES,
    DesignBrief,
    Evidence,
    ProjectProfile,
    Receipt,
    TrustedIssuer,
    assess,
    compile_contract,
    main,
    required_checks,
    sign_evidence,
)

NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)
SHA = "a" * 40
CONTEXT = "b" * 64
# Deterministic NONSECRET keys only for isolated test fixtures.
RUNNER_KEY = hashlib.sha256(b"public unit-test runner fixture").digest()
REVIEWER_KEY = hashlib.sha256(b"public unit-test reviewer fixture").digest()
DESIGN = {
    "research_basis": "Repository evidence plus explicit hypotheses; no user study claimed.",
    "research_status": "hypothesis", "primary_tasks": "Find and complete the next lesson.",
    "layout_rationale": "Task-first hierarchy, not an administrative dashboard.",
    "visual_direction": "Calm, legible and consistent with the actual project brand.",
    "information_density": "Progressive disclosure for learners; denser review for teachers.",
    "content_tone": "Clear and respectful.", "component_system": "Reuse accessible components and semantic tokens.",
    "interaction_states": "Loading, empty, error, success, disabled and permission denied.",
    "accessibility_plan": "WCAG 2.2 AA mapping, keyboard, focus, zoom and reading-order checks.",
    "validation_plan": "Device and task-based review with real content; label simulated findings.",
    "devices": ["phone", "desktop"], "locales": ["vi-VN"],
}


def profile_data(**changes):
    return {
        "schema_version": 1, "project_id": "example", "run_id": "run-example",
        "goal": "Deliver a sustainable high-quality product with evidence.",
        "domains": ["general"], "surfaces": ["api"], "audiences": ["operators"],
        "critical_journeys": ["Create and retrieve a valid resource."],
        "acceptance_criteria": [{"id": "AC-1", "outcome": "Resource round trip preserves valid fields.",
                                  "verification": "Integration test checks stored and returned values."}],
        "quality_targets": [{"id": "latency-p95", "unit": "ms", "operator": "lte", "value": 500.0,
                             "conditions": "Representative fixture workload; illustrative, not a universal SLO."}],
        "non_goals": ["Do not rewrite unrelated systems."],
        "constraints": ["No weakening security or acceptance criteria."],
        "technology_rationale": "Prefer supported compatible technology with a documented upgrade path.",
        "scale_and_slo": "Validate the declared project workload and recovery objectives.",
        "data_classification": "public", "persists_data": False, "operates_service": False,
        "serves_children": False, "uses_ai": False, "completion_target": "verified",
        "design": None, **changes,
    }


def make_profile(**changes):
    return ProjectProfile.model_validate(profile_data(**changes))


@pytest.fixture
def bundle(tmp_path):
    profile = make_profile()
    contract = compile_contract(profile)["contract_hash"]
    issuers = {
        "ci": TrustedIssuer("runtime-ci", "runner", frozenset(k for k, c in CATALOG.items() if c.mode == "runner"), RUNNER_KEY),
        "qa": TrustedIssuer("independent-qa", "reviewer", frozenset(k for k, c in CATALOG.items() if c.mode == "reviewer"), REVIEWER_KEY),
    }
    receipts = []
    for check in required_checks(profile):
        artifact = tmp_path / f"{check.id}.txt"
        artifact.write_text(f"Synthetic fixture for {check.id}\n", encoding="utf-8")
        issuer_id = "ci" if check.mode == "runner" else "qa"
        evidence = Evidence(schema_version=1, check_id=check.id, run_id=profile.run_id,
                            candidate_sha=SHA, context_hash=CONTEXT, contract_hash=contract,
                            issuer=issuer_id, status="pass", created_at=NOW - timedelta(minutes=1),
                            expires_at=NOW + timedelta(hours=1), artifact_path=artifact.name,
                            artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                            details="Synthetic unit-test evidence; not a real product test.",
                            covered_acceptance=["AC-1"] if check.id == "testing.acceptance" else [],
                            measurements={"latency-p95": 100.0} if check.id == "performance.budget" else {})
        receipts.append(sign_evidence(evidence, issuers[issuer_id].key))
    kwargs = {"expected_contract_hash": contract, "candidate_sha": SHA, "context_hash": CONTEXT,
              "author_principals": frozenset({"implementation-worker"}), "trusted_issuers": issuers,
              "evidence_root": tmp_path, "now": NOW}
    return profile, receipts, kwargs


def rewrite(receipt, key, **changes):
    data = receipt.evidence.model_dump()
    data.update(changes)
    return sign_evidence(Evidence.model_validate(data), key)


def test_valid_bundle_and_idempotent_submit(bundle):
    profile, receipts, kwargs = bundle
    result = assess(profile, receipts, **kwargs)
    assert result.quality_pass and len(result.passed) == len(required_checks(profile))
    assert assess(profile, receipts + receipts, **kwargs) == result


def test_missing_evidence_is_not_success(bundle):
    profile, _, kwargs = bundle
    result = assess(profile, [], **kwargs)
    assert not result.quality_pass
    assert all(reason.endswith(":missing") for reason in result.blockers)


@pytest.mark.parametrize("status", ["fail", "blocked", "unknown"])
def test_nonpassing_status_cannot_be_averaged_away(bundle, status):
    profile, receipts, kwargs = bundle
    issuer = kwargs["trusted_issuers"][receipts[0].evidence.issuer]
    receipts[0] = rewrite(receipts[0], issuer.key, status=status)
    result = assess(profile, receipts, **kwargs)
    assert not result.quality_pass
    assert result.blockers == (f"{receipts[0].evidence.check_id}:status_{status}",)


@pytest.mark.parametrize("field,value,reason", [
    ("run_id", "another-run", "wrong_run_or_contract"),
    ("contract_hash", "c" * 64, "wrong_run_or_contract"),
    ("candidate_sha", "d" * 40, "stale_candidate_or_context"),
    ("context_hash", "e" * 64, "stale_candidate_or_context"),
    ("issuer", "forged-reviewer", "unauthorized_issuer"),
])
def test_stale_or_untrusted_receipts(bundle, field, value, reason):
    profile, receipts, kwargs = bundle
    key = kwargs["trusted_issuers"][receipts[0].evidence.issuer].key
    receipts[0] = rewrite(receipts[0], key, **{field: value})
    assert any(item.endswith(reason) for item in assess(profile, receipts, **kwargs).blockers)


def test_signature_tampering(bundle):
    profile, receipts, kwargs = bundle
    raw = receipts[0].model_dump()
    raw["evidence"]["details"] = "tampered"
    receipts[0] = Receipt.model_validate(raw)
    assert any(item.endswith("invalid_signature") for item in assess(profile, receipts, **kwargs).blockers)


@pytest.mark.parametrize("created,expires", [
    (NOW - timedelta(hours=2), NOW),
    (NOW + timedelta(minutes=1), NOW + timedelta(hours=1)),
    (NOW - timedelta(hours=25), NOW + timedelta(hours=1)),
])
def test_time_window(bundle, created, expires):
    profile, receipts, kwargs = bundle
    key = kwargs["trusted_issuers"][receipts[0].evidence.issuer].key
    receipts[0] = rewrite(receipts[0], key, created_at=created, expires_at=expires)
    assert any(item.endswith("expired_or_future_evidence") for item in assess(profile, receipts, **kwargs).blockers)


def test_bad_expiry_and_naive_clock(bundle):
    profile, receipts, kwargs = bundle
    with pytest.raises(ValidationError):
        rewrite(receipts[0], REVIEWER_KEY, expires_at=receipts[0].evidence.created_at)
    with pytest.raises(ValueError, match="timezone-aware"):
        assess(profile, receipts, **{**kwargs, "now": datetime(2026, 9, 24)})


def test_author_cannot_review_with_alias(bundle):
    profile, receipts, kwargs = bundle
    kwargs["trusted_issuers"]["qa"] = replace(kwargs["trusted_issuers"]["qa"], principal_id="implementation-worker")
    result = assess(profile, receipts, **kwargs)
    assert not result.quality_pass and any(item.endswith("self_approval") for item in result.blockers)


def test_unknown_author_set_blocks(bundle):
    profile, receipts, kwargs = bundle
    for authors in (frozenset(), frozenset({" "})):
        result = assess(profile, receipts, **{**kwargs, "author_principals": authors})
        assert "identity:missing_author_set" in result.blockers


def test_shared_signing_key_blocks(bundle):
    profile, receipts, kwargs = bundle
    kwargs["trusted_issuers"]["ci"] = replace(kwargs["trusted_issuers"]["ci"], key=REVIEWER_KEY)
    result = assess(profile, receipts, **kwargs)
    assert "identity:shared_key_across_principals" in result.blockers


def test_issuer_wrong_mode_or_scope(bundle):
    profile, receipts, kwargs = bundle
    old = kwargs["trusted_issuers"]["qa"]
    for issuer in (replace(old, mode="runner"), replace(old, allowed_checks=frozenset({"design.visual"}))):
        kwargs["trusted_issuers"]["qa"] = issuer
        assert any(item.endswith("unauthorized_issuer") for item in assess(profile, receipts, **kwargs).blockers)


@pytest.mark.parametrize("path", ["../escape.log", "/etc/passwd", "C:\\escape.log", "sub\\..\\escape.log", "missing.log"])
def test_unsafe_or_missing_artifact(bundle, path):
    profile, receipts, kwargs = bundle
    key = kwargs["trusted_issuers"][receipts[0].evidence.issuer].key
    receipts[0] = rewrite(receipts[0], key, artifact_path=path)
    assert any(item.endswith("missing_changed_or_unsafe_artifact") for item in assess(profile, receipts, **kwargs).blockers)


@pytest.mark.parametrize("content", [b"tampered", b""])
def test_changed_or_empty_artifact(bundle, content):
    profile, receipts, kwargs = bundle
    (kwargs["evidence_root"] / receipts[0].evidence.artifact_path).write_bytes(content)
    assert not assess(profile, receipts, **kwargs).quality_pass


def test_oversized_artifact(bundle):
    profile, receipts, kwargs = bundle
    path = kwargs["evidence_root"] / receipts[0].evidence.artifact_path
    with path.open("wb") as stream:
        stream.truncate(MAX_ARTIFACT_BYTES + 1)
    assert not assess(profile, receipts, **kwargs).quality_pass


def test_symlink_escape(bundle, tmp_path):
    profile, receipts, kwargs = bundle
    external = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    external.write_text("outside", encoding="utf-8")
    link = tmp_path / "escape-link"
    try:
        link.symlink_to(external)
    except OSError:
        pytest.skip("symlink privilege unavailable")
    key = kwargs["trusted_issuers"][receipts[0].evidence.issuer].key
    receipts[0] = rewrite(receipts[0], key, artifact_path=link.name)
    assert not assess(profile, receipts, **kwargs).quality_pass


def test_conflicting_receipts_need_reconciliation(bundle):
    profile, receipts, kwargs = bundle
    key = kwargs["trusted_issuers"][receipts[0].evidence.issuer].key
    receipts.append(rewrite(receipts[0], key, status="fail"))
    assert any(item.endswith("conflicting_receipts") for item in assess(profile, receipts, **kwargs).blockers)


def test_unexpected_evidence_cannot_hide_failure(bundle):
    profile, receipts, kwargs = bundle
    receipts.append(rewrite(receipts[0], REVIEWER_KEY, check_id="hidden.failed.check", status="fail"))
    assert "hidden.failed.check:unexpected_check" in assess(profile, receipts, **kwargs).blockers


def test_contract_changes_invalidate_pin(bundle):
    profile, receipts, kwargs = bundle
    changed = make_profile(goal=profile.goal + " Changed scope.")
    assert "contract:changed_or_unpinned" in assess(changed, receipts, **kwargs).blockers
    assert compile_contract(profile) == compile_contract(make_profile())


@pytest.mark.parametrize("surface", ["web", "mobile", "desktop"])
def test_ui_requires_project_design(surface):
    with pytest.raises(ValidationError):
        make_profile(surfaces=[surface])
    ids = {check.id for check in required_checks(make_profile(surfaces=[surface], design=DESIGN))}
    assert {"design.visual", "usability.journeys", "accessibility.interaction"} <= ids


@pytest.mark.parametrize("surface", ["api", "cli", "library"])
def test_nonvisual_product_does_not_get_visual_theatre(surface):
    assert not any(check.id == "design.visual" for check in required_checks(make_profile(surfaces=[surface])))


@pytest.mark.parametrize("domain", ["general", "education", "healthcare", "finance", "commerce", "enterprise", "industrial", "content"])
def test_industry_applicability(domain):
    ids = {check.id for check in required_checks(make_profile(domains=[domain]))}
    assert "domain.fitness" in ids
    assert ("domain.obligations" in ids) == (domain in {"healthcare", "finance", "industrial"})


@pytest.mark.parametrize("changes,expected", [
    ({"persists_data": True}, {"data.restore", "data.integrity"}),
    ({"operates_service": True}, {"operations.observability", "operations.recovery"}),
    ({"data_classification": "sensitive"}, {"privacy.lifecycle"}),
    ({"serves_children": True}, {"children.safeguards", "privacy.lifecycle"}),
    ({"uses_ai": True}, {"ai.evaluation"}),
    ({"completion_target": "merged"}, {"integration.candidate"}),
    ({"completion_target": "staging", "operates_service": True}, {"integration.candidate", "release.receipt"}),
    ({"completion_target": "production", "operates_service": True}, {"integration.candidate", "release.receipt"}),
])
def test_risk_and_delivery_checks(changes, expected):
    assert expected <= {check.id for check in required_checks(make_profile(**changes))}


@pytest.mark.parametrize("changes", [
    {"domains": []}, {"domains": ["unrecognized"]}, {"domains": ["education", "education"]},
    {"surfaces": ["web", "web"], "design": DESIGN}, {"goal": " "}, {"audiences": []},
    {"critical_journeys": []}, {"non_goals": []}, {"persists_data": "false"},
    {"schema_version": 2}, {"completion_target": "production"}, {"skip_security": True},
])
def test_invalid_profile_cannot_reduce_quality(changes):
    with pytest.raises(ValidationError):
        make_profile(**changes)


def test_worker_verified_flag_is_rejected(bundle):
    _, receipts, _ = bundle
    data = receipts[0].model_dump()
    data["verified"] = True
    with pytest.raises(ValidationError):
        Receipt.model_validate(data)
    with pytest.raises(ValidationError):
        DesignBrief.model_validate({**DESIGN, "research_status": "certified"})


def test_bad_keys_and_trust():
    for principal, mode, scope, key in [
        ("", "runner", frozenset({"testing.unit"}), RUNNER_KEY),
        ("qa", "worker", frozenset({"testing.unit"}), RUNNER_KEY),
        ("qa", "runner", frozenset(), RUNNER_KEY),
        ("qa", "runner", frozenset({"*"}), RUNNER_KEY),
        ("qa", "runner", frozenset({"testing.unit"}), b"short"),
    ]:
        with pytest.raises(ValueError):
            TrustedIssuer(principal, mode, scope, key)


def test_short_signing_key(bundle):
    with pytest.raises(ValueError):
        sign_evidence(bundle[1][0].evidence, b"short")


def test_schema_and_plan_cli(tmp_path, capsys):
    assert main(["schema"]) == 0
    assert "goal" in json.loads(capsys.readouterr().out)["properties"]
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile_data()), encoding="utf-8")
    assert main(["plan", str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["contract_hash"] == compile_contract(make_profile())["contract_hash"]
    assert main(["plan", str(tmp_path / "absent")]) == 2
    assert "no approval issued" in capsys.readouterr().err


def test_verify_cli(tmp_path, bundle, capsys):
    profile, receipts, kwargs = bundle
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")
    receipt_path = tmp_path / "receipts.json"
    # CLI uses the actual current time, not the fixture clock.
    current = datetime.now(UTC)
    receipts = [rewrite(r, kwargs["trusted_issuers"][r.evidence.issuer].key,
                        created_at=current - timedelta(minutes=1), expires_at=current + timedelta(hours=1)) for r in receipts]
    receipt_path.write_text(json.dumps([r.model_dump(mode="json") for r in receipts]), encoding="utf-8")
    registry = {}
    for issuer_id, issuer in kwargs["trusted_issuers"].items():
        key_file = tmp_path / f"{issuer_id}.fixture-key"
        key_file.write_bytes(issuer.key)
        registry[issuer_id] = {"principal_id": issuer.principal_id, "mode": issuer.mode,
                               "allowed_checks": sorted(issuer.allowed_checks), "key_file": key_file.name}
    trust_path = tmp_path / "trust.json"
    trust_path.write_text(json.dumps(registry), encoding="utf-8")
    args = ["verify", str(profile_path), str(receipt_path), "--contract-hash", kwargs["expected_contract_hash"],
            "--candidate-sha", SHA, "--context-hash", CONTEXT, "--author", "implementation-worker",
            "--evidence-root", str(tmp_path), "--trust-registry", str(trust_path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["quality_pass"]
    receipt_path.write_text("[]", encoding="utf-8")
    assert main(args) == 1
    capsys.readouterr()
    for invalid in ({}, "bad-json"):
        receipt_path.write_text(json.dumps(invalid) if isinstance(invalid, dict) else invalid, encoding="utf-8")
        assert main(args) == 2
        capsys.readouterr()
    receipt_path.write_text("[]", encoding="utf-8")
    for invalid_registry in ([], {"ci": {}}, {"ci": {**registry["ci"], "allowed_checks": "*"}}):
        trust_path.write_text(json.dumps(invalid_registry), encoding="utf-8")
        assert main(args) == 2
        capsys.readouterr()


def test_schema_example_roundtrip():
    example = Path(__file__).parents[1] / "examples" / "product-quality-profile.json"
    profile = ProjectProfile.model_validate_json(example.read_text(encoding="utf-8"))
    assert profile.design is not None
    assert "design.visual" in {check.id for check in required_checks(profile)}


@pytest.mark.parametrize("coverage", [[], ["AC-other"], ["AC-1", "AC-extra"]])
def test_acceptance_coverage_is_enforced(bundle, coverage):
    profile, receipts, kwargs = bundle
    index = next(i for i, r in enumerate(receipts) if r.evidence.check_id == "testing.acceptance")
    receipts[index] = rewrite(receipts[index], RUNNER_KEY, covered_acceptance=coverage)
    assert "testing.acceptance:incomplete_acceptance_coverage" in assess(profile, receipts, **kwargs).blockers


@pytest.mark.parametrize("measurements", [{}, {"latency-p95": 501.0}])
def test_quality_target_enforced_even_when_driver_claims_pass(bundle, measurements):
    profile, receipts, kwargs = bundle
    index = next(i for i, r in enumerate(receipts) if r.evidence.check_id == "performance.budget")
    receipts[index] = rewrite(receipts[index], RUNNER_KEY, measurements=measurements)
    assert "performance.budget:missing_or_unmet_quality_target" in assess(profile, receipts, **kwargs).blockers


def test_lower_bound_target(bundle):
    profile, receipts, kwargs = bundle
    raw = profile.model_dump()
    raw["quality_targets"][0].update(operator="gte", value=100.0)
    profile = ProjectProfile.model_validate(raw)
    contract = compile_contract(profile)["contract_hash"]
    receipts = [rewrite(r, kwargs["trusted_issuers"][r.evidence.issuer].key, contract_hash=contract) for r in receipts]
    kwargs["expected_contract_hash"] = contract
    assert assess(profile, receipts, **kwargs).quality_pass
    index = next(i for i, r in enumerate(receipts) if r.evidence.check_id == "performance.budget")
    receipts[index] = rewrite(receipts[index], RUNNER_KEY, measurements={"latency-p95": 99.0})
    assert not assess(profile, receipts, **kwargs).quality_pass


@pytest.mark.parametrize("field", ["acceptance_criteria", "quality_targets"])
def test_duplicate_acceptance_or_target_ids_rejected(field):
    raw = profile_data()
    raw[field].append(raw[field][0])
    with pytest.raises(ValidationError):
        ProjectProfile.model_validate(raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_measurement_rejected(bundle, value):
    with pytest.raises(ValidationError):
        rewrite(bundle[1][0], REVIEWER_KEY, measurements={"latency-p95": value})



def test_trust_registry_absolute_key_path(tmp_path):
    from company.product_quality import _read_trust

    key = tmp_path / "fixture.key"
    key.write_bytes(RUNNER_KEY)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"ci": {"principal_id": "runtime-ci", "mode": "runner",
                        "allowed_checks": ["testing.unit"], "key_file": str(key.resolve())}}), encoding="utf-8")
    assert _read_trust(registry)["ci"].key == RUNNER_KEY


def test_product_quality_module_entrypoint(monkeypatch, capsys):
    import runpy
    import warnings

    monkeypatch.setattr("sys.argv", ["product_quality", "schema"])
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*found in sys.modules.*", category=RuntimeWarning)
        with pytest.raises(SystemExit) as stopped:
            runpy.run_module("company.product_quality", run_name="__main__", alter_sys=True)
    assert stopped.value.code == 0
    assert "properties" in json.loads(capsys.readouterr().out)
