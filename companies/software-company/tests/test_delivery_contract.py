"""Selective template adoption. All records and signed reports here are synthetic."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from xagents_core.execution import ExecutionJournal, RunStatus

from company.delivery_contract import (
    TEMPLATE_REVISION,
    DeliveryContract,
    DeliveryReport,
    adopted_source,
    delivery_gaps,
    ready_gaps,
)
from company.product_quality import Evidence, ProjectProfile, assess, compile_contract, main, sign_evidence_hmac
from company.quality_execution import compile_execution
from test_product_quality import NOW, RUNNER_KEY, profile_data, rewrite
from test_product_quality import bundle as bundle
from test_quality_commit import begin, commit
from test_quality_execution import work_for


def delivery_data(**changes):
    return {
        "source_revision": TEMPLATE_REVISION,
        "adoption": "brownfield", "completion_level": "complete",
        "spec": {"state": "Approved for implementation", "artifact_ref": "fixture:spec",
                 "artifact_sha256": "1" * 64, "approval_record": "fixture:decision-not-real",
                 "approved_by": "director:fixture", "approved_at": NOW.isoformat()},
        "research_refs": ["fixture:repository-survey"],
        "no_change_rationale": "Retain the runtime; add only the missing delivery semantics.",
        "alternatives_and_tradeoffs": "Compare no change, a thin adapter, and copying the full framework.",
        "baseline_ref": "fixture:baseline", "blocking_decisions": [],
        "acceptance_tests": [{"acceptance_id": "AC-1", "test_ref": "fixture:test-roundtrip"}],
        "gates": [
            {"id": "unit", "phase": "done", "mechanism": "command", "applicable": True,
             "command": ["python", "-m", "pytest", "tests/unit"]},
            {"id": "handover", "phase": "complete", "mechanism": "inspection", "applicable": True},
            {"id": "device", "phase": "done", "mechanism": "inspection", "applicable": False,
             "scope_reason": "API-only fixture; no device application is shipped."},
        ], **changes,
    }


def contract(**changes):
    return DeliveryContract.model_validate_json(json.dumps(delivery_data(**changes)))


def report_data(**changes):
    return {
        "level": "complete", "target": "verified", "open_required_items": 0,
        "blocking_findings": 0, "goals_measured": True, "guardrails_met": True,
        "out_of_scope_items": 5,
        "gates": [
            {"id": "unit", "status": "PASS", "checks_executed": 2, "exit_code": 0,
             "command": ["python", "-m", "pytest", "tests/unit"], "evidence_ref": "fixture:unit-results"},
            {"id": "handover", "status": "PASS", "checks_executed": 1, "evidence_ref": "fixture:handover"},
            {"id": "device", "status": "NOT_APPLICABLE", "checks_executed": 0, "evidence_ref": "fixture:scope"},
        ], **changes,
    }


def report(**changes):
    return DeliveryReport.model_validate_json(json.dumps(report_data(**changes)))


def adopted_profile(**changes):
    return ProjectProfile.model_validate_json(json.dumps(profile_data(**{"delivery": delivery_data(), **changes})))


def test_valid_contract_and_complete_report_are_not_a_second_state_machine():
    profile = adopted_profile()
    compiled = compile_contract(profile)
    assert compiled["template_source"] == adopted_source()
    assert compiled["template_source"]["revision"] == TEMPLATE_REVISION
    assert "delivery.definition" in {c["id"] for c in compiled["checks"]}
    spec = compile_execution(profile, work_for(profile))
    assert len(spec.tasks) == len(work_for(profile).tasks) + 1
    assert spec.tasks[0].write_scope == work_for(profile).tasks[0].write_scope
    assert delivery_gaps(profile.delivery, report(), "verified") == ()


@pytest.mark.parametrize("state", ["Draft", "In review", "not Approved for implementation",
                                      "Draft / In review / Approved for implementation"])
def test_template_placeholder_or_mention_is_not_approval(state):
    data = delivery_data()
    data["spec"]["state"] = state
    with pytest.raises(ValidationError):
        DeliveryContract.model_validate_json(json.dumps(data))


def change_at(data, path, value):
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    last = int(parts[-1]) if isinstance(current, list) else parts[-1]
    current[last] = value
    return data


@pytest.mark.parametrize("path,value", [
    ("source_revision", "2" * 40), ("source_revision", "main"),
    ("spec.approved_by", " "), ("spec.approval_record", ""),
    ("spec.approved_at", "2026-09-25T00:00:00"), ("spec.artifact_sha256", "short"),
    ("baseline_ref", None), ("blocking_decisions", ["Unresolved payment retention"]),
    ("research_refs", []), ("no_change_rationale", ""), ("acceptance_tests", []),
    ("gates", []), ("gates.0.command", []), ("gates.2.scope_reason", ""),
    ("gates.0.applicable", "true"), ("gates.0.unknown_field", True),
    ("gates.1.command", ["true"]),
])
def test_readiness_rejects_missing_or_unreviewed_inputs(path, value):
    with pytest.raises(ValidationError):
        DeliveryContract.model_validate_json(json.dumps(change_at(delivery_data(), path, value)))


def test_greenfield_does_not_require_a_brownfield_baseline():
    assert contract(adoption="greenfield", baseline_ref=None).baseline_ref is None
    assert contract(completion_level="done", gates=delivery_data()["gates"][:1]).completion_level == "done"


@pytest.mark.parametrize("kind", ["gate_ids", "acceptance_ids", "no_done", "no_complete"])
def test_readiness_cannot_hide_required_stages_or_duplicate_ids(kind):
    data = delivery_data()
    if kind == "gate_ids":
        data["gates"].append(copy.deepcopy(data["gates"][0]))
    elif kind == "acceptance_ids":
        data["acceptance_tests"] *= 2
    elif kind == "no_done":
        data["gates"][0]["phase"] = "complete"
    else:
        data["gates"][1]["phase"] = "done"
    with pytest.raises(ValidationError):
        DeliveryContract.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("ids", [["OTHER"], ["AC-1", "EXTRA"]])
def test_profile_requires_exact_acceptance_to_test_mapping(ids):
    data = delivery_data(acceptance_tests=[{"acceptance_id": i, "test_ref": "fixture:test"} for i in ids])
    with pytest.raises(ValidationError, match="acceptance"):
        adopted_profile(delivery=data)


def test_ready_preflight_revalidates_unchecked_model_copy():
    invalid = adopted_profile().model_copy(update={"delivery": contract().model_copy(update={"blocking_decisions": ("block",)})})
    with pytest.raises(ValidationError):
        compile_contract(invalid)


@pytest.mark.parametrize("path,value,reason", [
    ("gates.0.status", "NOT_CONFIGURED", "NOT_CONFIGURED"),
    ("gates.0.status", "FAIL", "FAIL"),
    ("gates.0.status", "NOT_APPLICABLE", "NOT_APPLICABLE"),
    ("gates.0.checks_executed", 0, "no_checks"),
    ("gates.0.exit_code", 1, "command_mismatch_or_failure"),
    ("gates.0.exit_code", None, "command_mismatch_or_failure"),
    ("gates.0.command", ["true"], "command_mismatch_or_failure"),
    ("gates.0.command", [], "command_mismatch_or_failure"),
    ("gates.1.command", ["true"], "inspection_must_not_claim_command"),
    ("gates.1.exit_code", 0, "inspection_must_not_claim_command"),
    ("gates.2.status", "PASS", "scope_mismatch"),
    ("level", "done", "incomplete_level_or_target"),
    ("target", "production", "incomplete_level_or_target"),
    ("open_required_items", 1, "required_work_open"),
    ("blocking_findings", 1, "blocking_findings"),
    ("goals_measured", False, "goal_measurement_missing"),
    ("guardrails_met", False, "guardrail_regression"),
])
def test_report_rejects_false_green(path, value, reason):
    observation = DeliveryReport.model_validate_json(json.dumps(change_at(report_data(), path, value)))
    assert any(reason in gap for gap in delivery_gaps(contract(), observation, "verified"))


def test_missing_extra_and_repeated_report_entries():
    assert delivery_gaps(contract(), None, "verified") == ("report_missing",)
    assert "unit:missing" in delivery_gaps(contract(), report(gates=report_data()["gates"][1:]), "verified")
    data = report_data()
    data["gates"].append({**data["gates"][0], "id": "unexpected"})
    assert "unexpected:unexpected_gate" in delivery_gaps(contract(), report(**data), "verified")
    data["gates"].append(data["gates"][0])
    with pytest.raises(ValidationError):
        report(**data)


def test_done_is_task_scope_not_full_project_completion():
    plan = contract(completion_level="done", gates=delivery_data()["gates"][:1])
    observed = report(level="done", goals_measured=False, open_required_items=9, gates=report_data()["gates"][:1])
    assert delivery_gaps(plan, observed, "verified") == ()
    assert delivery_gaps(contract(), report(out_of_scope_items=999), "verified") == ()


@pytest.mark.parametrize("path,value", [("gates.0.checks_executed", True), ("open_required_items", -1),
                                        ("gates.0.status", "SKIP"), ("gates.0.status", "success")])
def test_report_has_no_coerced_counts_or_skip_success_alias(path, value):
    with pytest.raises(ValidationError):
        DeliveryReport.model_validate_json(json.dumps(change_at(report_data(), path, value)))


class FakeApprovalLookupForTest:
    """Deterministic stand-in for a real, out-of-band approval registry."""

    def __init__(self, records: dict[tuple[str, str], str]):
        self._records = records

    def approved(self, record: str, artifact_sha256: str) -> str | None:
        return self._records.get((record, artifact_sha256))


def _real_spec_artifact(tmp_path):
    artifact = tmp_path / "spec.md"
    artifact.write_text("Synthetic fixture spec; not a real approval.\n", encoding="utf-8")
    return artifact.name, hashlib.sha256(artifact.read_bytes()).hexdigest()


AUTHORS = frozenset({"implementation-worker"})


@pytest.fixture
def ready_ok(tmp_path):
    """A contract whose spec is genuinely, verifiably approved before any evidence."""
    artifact_ref, artifact_sha256 = _real_spec_artifact(tmp_path)
    spec = {**delivery_data()["spec"], "artifact_ref": artifact_ref, "artifact_sha256": artifact_sha256,
            "approved_by": "director:fixture", "approval_record": "fixture:decision-1",
            "approved_at": (NOW - timedelta(hours=2)).isoformat()}
    lookup = FakeApprovalLookupForTest({(spec["approval_record"], artifact_sha256): spec["approved_by"]})
    return contract(spec=spec), tmp_path, lookup


def _ready(contract_, root, lookup, **over):
    kwargs = {"authors": AUTHORS, "now": NOW, "earliest_evidence": NOW - timedelta(hours=1),
              "evidence_root": root, "lookup": lookup, **over}
    return ready_gaps(contract_, **kwargs)


def test_ready_gaps_pass_with_verified_lookup(ready_ok):
    contract_, root, lookup = ready_ok
    assert _ready(contract_, root, lookup) == ()


def test_ready_gaps_self_approval(ready_ok):
    contract_, root, lookup = ready_ok
    assert "spec_self_approval" in _ready(contract_, root, lookup, authors=frozenset({contract_.spec.approved_by}))


def test_ready_gaps_approved_in_future(ready_ok):
    contract_, root, lookup = ready_ok
    assert "spec_approved_in_future" in _ready(contract_, root, lookup, now=NOW - timedelta(hours=3))


def test_ready_gaps_approved_after_evidence(ready_ok):
    contract_, root, lookup = ready_ok
    assert "spec_approved_after_evidence" in _ready(contract_, root, lookup, earliest_evidence=NOW - timedelta(hours=3))


def test_ready_gaps_artifact_changed(ready_ok):
    contract_, root, lookup = ready_ok
    (root / contract_.spec.artifact_ref).write_bytes(b"tampered after approval")
    assert "spec_artifact_changed" in _ready(contract_, root, lookup)


def test_ready_gaps_no_lookup_is_unverified(ready_ok):
    contract_, root, _ = ready_ok
    assert "approval_record_unverified" in _ready(contract_, root, None)


def test_ready_gaps_wrong_principal_is_unverified(ready_ok):
    contract_, root, _ = ready_ok

    class WrongLookup:
        def approved(self, record: str, artifact_sha256: str) -> str | None:
            return "someone-else"

    assert "approval_record_unverified" in _ready(contract_, root, WrongLookup())


def _ready_ok_as(tmp_path, *, approved_by: str, approval_record: str = "fixture:decision-1"):
    """Same shape as the `ready_ok` fixture, with a controllable `approved_by`/lookup key."""
    artifact_ref, artifact_sha256 = _real_spec_artifact(tmp_path)
    spec = {**delivery_data()["spec"], "artifact_ref": artifact_ref, "artifact_sha256": artifact_sha256,
            "approved_by": approved_by, "approval_record": approval_record,
            "approved_at": (NOW - timedelta(hours=2)).isoformat()}
    lookup = FakeApprovalLookupForTest({(approval_record, artifact_sha256): approved_by})
    return contract(spec=spec), tmp_path, lookup


def test_ready_gaps_self_approval_case_insensitive(tmp_path):
    contract_, root, lookup = _ready_ok_as(tmp_path, approved_by="alice")
    assert "spec_self_approval" in _ready(contract_, root, lookup, authors=frozenset({"Alice"}))


def test_ready_gaps_self_approval_ignores_surrounding_whitespace(tmp_path):
    contract_, root, lookup = _ready_ok_as(tmp_path, approved_by="alice")
    assert "spec_self_approval" in _ready(contract_, root, lookup, authors=frozenset({" alice "}))


def test_ready_gaps_lookup_principal_normalized_is_verified(tmp_path):
    artifact_ref, artifact_sha256 = _real_spec_artifact(tmp_path)
    spec = {**delivery_data()["spec"], "artifact_ref": artifact_ref, "artifact_sha256": artifact_sha256,
            "approved_by": "alice", "approval_record": "fixture:decision-1",
            "approved_at": (NOW - timedelta(hours=2)).isoformat()}
    lookup = FakeApprovalLookupForTest({(spec["approval_record"], artifact_sha256): "ALICE "})
    contract_ = contract(spec=spec)
    gaps = _ready(contract_, tmp_path, lookup, authors=AUTHORS)
    assert "approval_record_unverified" not in gaps


def test_assess_blocks_delivery_without_approval_lookup(delivery_bundle):
    profile, receipts, kwargs = delivery_bundle
    result = assess(profile, receipts, **{**kwargs, "approval_lookup": None})
    assert not result.quality_pass
    assert any("approval_record_unverified" in b for b in result.blockers)


@pytest.fixture
def delivery_bundle(bundle, tmp_path):
    _, old_receipts, kwargs = bundle
    artifact_ref, artifact_sha256 = _real_spec_artifact(tmp_path)
    spec = {**delivery_data()["spec"], "artifact_ref": artifact_ref, "artifact_sha256": artifact_sha256,
            "approved_at": (NOW - timedelta(hours=2)).isoformat()}
    profile = adopted_profile(delivery=delivery_data(spec=spec))
    digest = compile_contract(profile)["contract_hash"]
    receipts = [rewrite(r, kwargs["trusted_issuers"][r.evidence.issuer].key, contract_hash=digest) for r in old_receipts]
    data = receipts[0].evidence.model_dump()
    data.update(check_id="delivery.definition", issuer="ci", delivery_report=report())
    receipts.append(sign_evidence_hmac(Evidence.model_validate(data), RUNNER_KEY))
    lookup = FakeApprovalLookupForTest({(spec["approval_record"], artifact_sha256): spec["approved_by"]})
    return profile, receipts, {**kwargs, "expected_contract_hash": digest, "approval_lookup": lookup}


def test_assessor_and_atomic_journal_consume_the_template_contract(delivery_bundle, tmp_path):
    profile, receipts, kwargs = delivery_bundle
    assert assess(profile, receipts, **kwargs).quality_pass
    path = tmp_path / "delivery.sqlite"
    with ExecutionJournal(path) as journal:
        count = begin(journal, profile)
        state = commit(journal, profile, receipts, kwargs, count)
        assert state.status is RunStatus.SUCCEEDED
        stored = journal.events(profile.run_id)[-1].payload
        assert stored["receipts"][-1]["evidence"]["delivery_report"]["level"] == "complete"
    with ExecutionJournal(path) as journal:
        assert journal.resume(profile.run_id) == state
        assert commit(journal, profile, receipts, kwargs, count) == state


@pytest.mark.parametrize("field,value", [("checks_executed", 0), ("status", "NOT_CONFIGURED")])
def test_signed_false_green_is_blocked_and_persisted(delivery_bundle, tmp_path, field, value):
    profile, receipts, kwargs = delivery_bundle
    data = report_data()
    data["gates"][0][field] = value
    receipts[-1] = rewrite(receipts[-1], RUNNER_KEY, delivery_report=report(**data))
    assert not assess(profile, receipts, **kwargs).quality_pass
    with ExecutionJournal(tmp_path / "failure.sqlite") as journal:
        count = begin(journal, profile)
        assert commit(journal, profile, receipts, kwargs, count).status is RunStatus.BLOCKED
        assert "delivery.definition" in journal.events(profile.run_id)[-1].payload["reason"]


def test_missing_report_and_tampering_cannot_bypass_the_existing_assessor(delivery_bundle):
    profile, receipts, kwargs = delivery_bundle
    without = rewrite(receipts[-1], RUNNER_KEY, delivery_report=None)
    assert not assess(profile, [*receipts[:-1], without], **kwargs).quality_pass
    raw = receipts[-1].model_dump()
    raw["evidence"]["delivery_report"]["gates"][0]["checks_executed"] = 999
    from company.product_quality import Receipt
    tampered = Receipt.model_validate(raw)
    assert "delivery.definition:invalid_signature" in assess(profile, [*receipts[:-1], tampered], **kwargs).blockers


def test_contract_change_invalidates_prior_receipts(delivery_bundle):
    profile, receipts, kwargs = delivery_bundle
    data = profile.model_dump(mode="json")
    data["delivery"]["spec"]["artifact_sha256"] = "9" * 64
    changed = ProjectProfile.model_validate_json(json.dumps(data))
    assert compile_contract(changed)["contract_hash"] != compile_contract(profile)["contract_hash"]
    assert not assess(changed, receipts, **kwargs).quality_pass


def test_opt_out_preserves_v2_contract_and_signature_bytes(bundle):
    profile, receipts, kwargs = bundle
    compiled = compile_contract(profile)
    assert "delivery" not in profile.model_dump(mode="json")
    assert "template_source" not in compiled
    assert "delivery_report" not in receipts[0].evidence.model_dump(mode="json")
    expected = {k: v for k, v in compiled.items() if k != "contract_hash"}
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                      allow_nan=False).encode()).hexdigest()
    # Captured by executing the unmodified product_quality.py from parent 74bd6de1.
    assert digest == "fb5dd9731ff1d74353d8f602e1e858c8c6749eac171b767f94d539f11d99332b"
    assert digest == kwargs["expected_contract_hash"]
    assert "delivery.definition" not in {x["id"] for x in compiled["checks"]}
    raw = receipts[0].evidence.model_dump(mode="json")
    key = kwargs["trusted_issuers"][raw["issuer"]].key
    signature = hmac.new(key, json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                       allow_nan=False).encode(), hashlib.sha256).hexdigest()
    assert signature == receipts[0].signature
    assert assess(profile, receipts, **kwargs).quality_pass


def test_source_lock_and_example_use_the_same_reviewed_revision(capsys):
    root = Path(__file__).resolve().parents[3]
    lock = json.loads((root / "docs/integrations/projects-template.lock.json").read_text(encoding="utf-8"))
    assert lock == adopted_source()
    example = Path(__file__).resolve().parents[1] / "examples/product-quality-profile.json"
    assert main(["plan", str(example)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["template_source"] == lock
    assert output["profile"]["delivery"]["completion_level"] == "complete"
