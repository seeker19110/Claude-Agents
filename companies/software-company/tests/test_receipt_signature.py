"""ADR-0020 (K2): Ed25519 receipts. Holding only the registry must not yield a valid receipt.

Key pairs are generated at run time; no private key material is committed (ADR-0020 §5).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from company.product_quality import (
    CATALOG,
    MAX_ARTIFACT_BYTES,
    Evidence,
    IssuerKey,
    Receipt,
    TrustedIssuer,
    _read_trust,
    assess,
    compile_contract,
    main,
    required_checks,
    sign_evidence,
    sign_evidence_hmac,
    verify_receipt,
)
from test_product_quality import CONTEXT, NOW, REVIEWER_KEY, RUNNER_KEY, SHA, make_profile

ED25519_POLICY = {"max_age_seconds": 86400, "max_artifact_bytes": MAX_ARTIFACT_BYTES, "allowed_schemes": ["ed25519"]}
NOT_AFTER = NOW + timedelta(days=90)
RUNNER_SCOPE = frozenset(k for k, c in CATALOG.items() if c.mode == "runner")
REVIEWER_SCOPE = frozenset(k for k, c in CATALOG.items() if c.mode == "independent_review")


def pem_of(private: Ed25519PrivateKey) -> str:
    return private.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")


def key_id_of(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()


def registry_key(private: Ed25519PrivateKey, not_after=NOT_AFTER) -> IssuerKey:
    return IssuerKey.from_pem(key_id_of(private), pem_of(private), not_after)


def v4_profile(**changes):
    return make_profile(evidence_policy=ED25519_POLICY, **changes)


def evidence_for(profile, check, artifact, issuer_id, created=NOW - timedelta(minutes=1)):
    return Evidence(schema_version=1, check_id=check.id, run_id=profile.run_id, candidate_sha=SHA,
                    context_hash=CONTEXT, contract_hash=compile_contract(profile)["contract_hash"],
                    issuer=issuer_id, status="pass", created_at=created, expires_at=created + timedelta(hours=2),
                    artifact_path=artifact.name, artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    details="Synthetic unit-test evidence; not a real product test.",
                    covered_acceptance=["AC-1"] if check.id == "testing.acceptance" else [],
                    measurements={"latency-p95": 100.0} if check.id == "performance.budget" else {})


@pytest.fixture
def ed_bundle(tmp_path):
    profile = v4_profile()
    signers = {"ci": Ed25519PrivateKey.generate(), "qa": Ed25519PrivateKey.generate()}
    issuers = {
        "ci": TrustedIssuer("runtime-ci", "runner", RUNNER_SCOPE, public_keys=(registry_key(signers["ci"]),)),
        "qa": TrustedIssuer("independent-qa", "independent_review", REVIEWER_SCOPE,
                            public_keys=(registry_key(signers["qa"]),)),
    }
    receipts = []
    for check in required_checks(profile):
        artifact = tmp_path / f"{check.id}.txt"
        artifact.write_text(f"Synthetic fixture for {check.id}\n", encoding="utf-8")
        issuer_id = "ci" if check.mode == "runner" else "qa"
        evidence = evidence_for(profile, check, artifact, issuer_id)
        receipts.append(sign_evidence(evidence, signers[issuer_id], key_id_of(signers[issuer_id])))
    kwargs = {"expected_contract_hash": compile_contract(profile)["contract_hash"], "candidate_sha": SHA,
              "context_hash": CONTEXT, "author_principals": frozenset({"implementation-worker"}),
              "trusted_issuers": issuers, "evidence_root": tmp_path, "now": NOW}
    return profile, receipts, kwargs, signers


def reviewer_index(receipts):
    return next(i for i, r in enumerate(receipts) if r.evidence.issuer == "qa")


def test_valid_ed25519_bundle_passes(ed_bundle):
    profile, receipts, kwargs, _ = ed_bundle
    result = assess(profile, receipts, **kwargs)
    assert result.blockers == ()
    assert result.quality_pass and len(result.passed) == len(required_checks(profile))
    assert all(r.signature_scheme == "ed25519" and len(r.signature) == 128 for r in receipts)


def _registry_derived_bytes(issuer: TrustedIssuer) -> list[bytes]:
    """Every byte string an attacker holding ONLY the registry could use as key material."""
    material: list[bytes] = []
    for key in issuer.public_keys:
        pem = key.public_key_pem.encode("ascii")
        material += [key.public_key, pem, key.key_id.encode("ascii"), bytes.fromhex(key.key_id),
                     hashlib.sha256(pem).digest(), hashlib.sha256(key.public_key).digest()]
    return material


def test_registry_holder_cannot_forge_a_reviewer_receipt(ed_bundle):
    profile, receipts, kwargs, _ = ed_bundle
    index = reviewer_index(receipts)
    target = receipts[index]
    issuer = kwargs["trusted_issuers"]["qa"]
    real_key_id = issuer.public_keys[0].key_id
    forged: list[Receipt] = []
    for material in _registry_derived_bytes(issuer):
        forged.append(sign_evidence_hmac(target.evidence, material.ljust(32, b"\0")))
        seed = hashlib.sha256(material).digest() if len(material) != 32 else material
        attacker = Ed25519PrivateKey.from_private_bytes(seed)
        # Label the forgery with the REAL registry key id; sign_evidence refuses, so build it by hand.
        signature = attacker.sign(json.dumps(target.evidence.model_dump(mode="json"), sort_keys=True,
                                             separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hex()
        forged.append(Receipt(evidence=target.evidence, signature=signature, signature_scheme="ed25519",
                              key_id=real_key_id))
    assert forged
    check_id = target.evidence.check_id
    for receipt in forged:
        blockers = assess(profile, [*receipts[:index], receipt, *receipts[index + 1:]], **kwargs).blockers
        assert blockers in ((f"{check_id}:invalid_signature",), (f"{check_id}:scheme_not_allowed",))


def test_expired_key_is_rejected(ed_bundle):
    profile, receipts, kwargs, signers = ed_bundle
    issuer = kwargs["trusted_issuers"]["qa"]
    # now > not_after AND the evidence was created after not_after: the key could not sign it.
    expired = registry_key(signers["qa"], not_after=NOW - timedelta(minutes=30))
    kwargs["trusted_issuers"]["qa"] = replace(issuer, public_keys=(expired,))
    result = assess(profile, receipts, **kwargs)
    reviewed = sorted(r.evidence.check_id for r in receipts if r.evidence.issuer == "qa")
    assert sorted(result.blockers) == [f"{check_id}:key_expired" for check_id in reviewed]
    future = replace(expired, not_after=NOW + timedelta(days=1))
    receipt = receipts[reviewer_index(receipts)]
    assert verify_receipt(receipt, replace(issuer, public_keys=(future,)), now=NOW - timedelta(hours=1),
                          allowed_schemes=frozenset({"ed25519"})) == "key_expired"  # created after `now`


def test_rotated_key_still_verifies_receipt_signed_before_not_after(ed_bundle):
    profile, receipts, kwargs, signers = ed_bundle
    issuer = kwargs["trusted_issuers"]["qa"]
    # created_at = NOW - 1 minute < not_after < now: signed while valid, still within the evidence age window.
    retiring = registry_key(signers["qa"], not_after=NOW - timedelta(seconds=30))
    kwargs["trusted_issuers"]["qa"] = replace(issuer, public_keys=(retiring, registry_key(Ed25519PrivateKey.generate())))
    assert assess(profile, receipts, **kwargs).quality_pass


def test_unknown_key_id_is_rejected(ed_bundle):
    profile, receipts, kwargs, _ = ed_bundle
    index = reviewer_index(receipts)
    other = Ed25519PrivateKey.generate()
    receipts[index] = sign_evidence(receipts[index].evidence, other, key_id_of(other))
    assert assess(profile, receipts, **kwargs).blockers == (f"{receipts[index].evidence.check_id}:unknown_key",)


def test_hmac_receipt_on_ed25519_contract_is_scheme_not_allowed(ed_bundle):
    profile, receipts, kwargs, _ = ed_bundle
    kwargs["trusted_issuers"]["qa"] = replace(kwargs["trusted_issuers"]["qa"], key=REVIEWER_KEY)
    index = reviewer_index(receipts)
    receipts[index] = sign_evidence_hmac(receipts[index].evidence, REVIEWER_KEY)
    assert assess(profile, receipts, **kwargs).blockers == (f"{receipts[index].evidence.check_id}:scheme_not_allowed",)


def test_ed25519_receipt_on_legacy_contract_is_scheme_not_allowed(ed_bundle, tmp_path):
    _, _, kwargs, signers = ed_bundle
    legacy = make_profile()
    digest = compile_contract(legacy)["contract_hash"]
    check = next(c for c in required_checks(legacy) if c.mode == "independent_review")
    evidence = evidence_for(legacy, check, tmp_path / f"{check.id}.txt", "qa")
    receipt = sign_evidence(evidence, signers["qa"], key_id_of(signers["qa"]))
    verdict = verify_receipt(receipt, kwargs["trusted_issuers"]["qa"], now=NOW, allowed_schemes=frozenset({"hmac-sha256"}))
    assert verdict == "scheme_not_allowed"
    blockers = assess(legacy, [receipt], **{**kwargs, "expected_contract_hash": digest}).blockers
    assert f"{check.id}:scheme_not_allowed" in blockers


def test_legacy_hmac_receipt_still_passes_on_v2_contract(tmp_path):
    from test_product_quality import _make_bundle

    profile = make_profile()
    receipts, kwargs = _make_bundle(profile, tmp_path)
    assert compile_contract(profile)["policy_version"] == "product-excellence/2"
    dumped = receipts[0].model_dump(mode="json")
    assert set(dumped) == {"evidence", "signature"}  # byte-identical to pre-K2 receipts
    assert receipts[0].signature_scheme == "hmac-sha256" and receipts[0].key_id is None
    assert assess(profile, receipts, **kwargs).quality_pass


def test_legacy_contract_ignores_registry_only_issuer_for_hmac(ed_bundle, tmp_path):
    """An Ed25519-only issuer has no HMAC secret: HMAC over registry bytes is invalid, not accepted."""
    _, _, kwargs, _ = ed_bundle
    issuer = kwargs["trusted_issuers"]["qa"]
    legacy = make_profile()
    check = next(c for c in required_checks(legacy) if c.mode == "independent_review")
    evidence = evidence_for(legacy, check, tmp_path / f"{check.id}.txt", "qa")
    for material in _registry_derived_bytes(issuer):
        receipt = sign_evidence_hmac(evidence, material.ljust(32, b"\0"))
        assert verify_receipt(receipt, issuer, now=NOW, allowed_schemes=frozenset({"hmac-sha256"})) == "invalid_signature"


def test_shared_public_key_across_principals_blocks(ed_bundle):
    profile, receipts, kwargs, signers = ed_bundle
    kwargs["trusted_issuers"]["ci"] = replace(kwargs["trusted_issuers"]["ci"], public_keys=(registry_key(signers["qa"]),))
    assert "identity:shared_key_across_principals" in assess(profile, receipts, **kwargs).blockers


def test_same_public_key_for_one_principal_is_allowed(ed_bundle):
    profile, receipts, kwargs, _ = ed_bundle
    qa = kwargs["trusted_issuers"]["qa"]
    kwargs["trusted_issuers"]["qa-mirror"] = replace(qa, allowed_checks=frozenset({"design.visual"}))
    assert "identity:shared_key_across_principals" not in assess(profile, receipts, **kwargs).blockers


def test_key_entry_rejects_mismatched_id_bad_type_and_naive_expiry():
    private = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="key_id"):
        IssuerKey.from_pem("0" * 64, pem_of(private), NOT_AFTER)
    ec_pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    with pytest.raises(ValueError, match="Ed25519"):
        IssuerKey.from_pem(key_id_of(private), ec_pem, NOT_AFTER)
    with pytest.raises(ValueError, match="timezone"):
        IssuerKey.from_pem(key_id_of(private), pem_of(private), NOT_AFTER.replace(tzinfo=None))
    with pytest.raises(ValueError, match="32 bytes"):
        IssuerKey(key_id_of(private), b"short", NOT_AFTER)


def test_issuer_needs_some_key():
    with pytest.raises(ValueError):
        TrustedIssuer("runtime-ci", "runner", RUNNER_SCOPE)


def test_sign_evidence_refuses_wrong_key_id(ed_bundle):
    _, receipts, _, signers = ed_bundle
    with pytest.raises(ValueError, match="key_id"):
        sign_evidence(receipts[0].evidence, signers["ci"], "0" * 64)


@pytest.mark.parametrize("changes", [
    {"signature_scheme": "ed25519", "key_id": None},
    {"signature_scheme": "ed25519", "key_id": "0" * 64},  # HMAC-length signature under Ed25519
    {"signature_scheme": "hmac-sha256", "key_id": "0" * 64},
    {"signature_scheme": "rsa", "key_id": None},
])
def test_receipt_scheme_shape_is_enforced(ed_bundle, changes):
    _, receipts, _, _ = ed_bundle
    hmac_receipt = sign_evidence_hmac(receipts[0].evidence, RUNNER_KEY)
    assert Receipt.model_validate(hmac_receipt.model_dump()) == hmac_receipt
    with pytest.raises(ValidationError):
        Receipt.model_validate({**hmac_receipt.model_dump(), **changes})


def test_ed25519_signature_must_be_128_hex(ed_bundle):
    _, receipts, _, _ = ed_bundle
    raw = receipts[0].model_dump()
    assert Receipt.model_validate(raw) == receipts[0]  # python-mode round trip, so only the signature differs
    raw["signature"] = raw["signature"][:64]
    with pytest.raises(ValidationError, match="128-hex"):
        Receipt.model_validate(raw)


def test_new_profile_cannot_allow_hmac():
    for schemes in (["hmac-sha256"], ["ed25519", "hmac-sha256"], [], ["ed25519", "ed25519"]):
        with pytest.raises(ValidationError):
            make_profile(evidence_policy={**ED25519_POLICY, "allowed_schemes": schemes})


def test_ed25519_profile_compiles_to_v4():
    contract = compile_contract(v4_profile())
    assert contract["policy_version"] == "product-excellence/4"
    assert contract["evidence_policy"]["signature"] == "Ed25519"
    assert contract["evidence_policy"]["allowed_schemes"] == ["ed25519"]
    v3 = compile_contract(make_profile(evidence_policy={"max_age_seconds": 86400, "max_artifact_bytes": MAX_ARTIFACT_BYTES}))
    assert v3["policy_version"] == "product-excellence/3" and v3["evidence_policy"]["signature"] == "HMAC-SHA256"
    assert "allowed_schemes" not in v3["profile"]["evidence_policy"]


def _registry_document(signers, not_after="2026-12-31T00:00:00Z"):
    return {
        "ci": {"principal_id": "runtime-ci", "mode": "runner", "allowed_checks": sorted(RUNNER_SCOPE),
               "keys": [{"key_id": key_id_of(signers["ci"]), "public_key_pem": pem_of(signers["ci"]), "not_after": not_after}]},
        "qa": {"principal_id": "independent-qa", "mode": "independent_review", "allowed_checks": sorted(REVIEWER_SCOPE),
               "keys": [{"key_id": key_id_of(signers["qa"]), "public_key_pem": pem_of(signers["qa"]), "not_after": not_after}]},
    }


def test_public_key_registry_is_read(ed_bundle, tmp_path):
    _, _, _, signers = ed_bundle
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_registry_document(signers)), encoding="utf-8")
    trust = _read_trust(path)
    assert trust["qa"].key is None
    assert trust["qa"].public_keys[0].key_id == key_id_of(signers["qa"])
    assert trust["qa"].public_keys[0].not_after.utcoffset() == timedelta(0)


def test_transition_registry_entry_may_hold_both_forms(ed_bundle, tmp_path):
    _, _, _, signers = ed_bundle
    (tmp_path / "ci.key").write_bytes(RUNNER_KEY)
    document = _registry_document(signers)
    document["ci"]["key_file"] = "ci.key"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    trust = _read_trust(path)
    assert trust["ci"].key == RUNNER_KEY and len(trust["ci"].public_keys) == 1


@pytest.mark.parametrize("mutate", [
    lambda d: d["qa"].update(keys=[]),
    lambda d: d["qa"].update(keys="not-a-list"),
    lambda d: d["qa"]["keys"][0].update(key_id="0" * 64),
    lambda d: d["qa"]["keys"][0].update(not_after="2026-12-31T00:00:00"),
    lambda d: d["qa"]["keys"][0].update(extra="field"),
    lambda d: d["qa"]["keys"][0].update(public_key_pem="-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n"),
    lambda d: d["qa"].pop("keys"),
    lambda d: d["qa"].update(unexpected=True),
])
def test_invalid_public_key_registry_is_a_config_error(ed_bundle, tmp_path, mutate):
    _, _, _, signers = ed_bundle
    document = _registry_document(signers)
    mutate(document)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        _read_trust(path)


def test_tampered_evidence_field_breaks_signature(ed_bundle):
    """A valid Ed25519 receipt whose evidence is mutated post-signing must not verify.

    Changing `measurements` after signing (contract-hash and everything else untouched,
    signature bytes untouched) has to be caught: the signature covers the whole evidence
    body, so any bit-flip in a signed field must flip the signature check, not just the
    field-level checks further down `assess`.
    """
    profile, receipts, kwargs, _ = ed_bundle
    index = next(i for i, r in enumerate(receipts) if r.evidence.check_id == "performance.budget")
    target = receipts[index]
    tampered_evidence = target.evidence.model_copy(update={"measurements": {"latency-p95": 1.0}})
    tampered = target.model_copy(update={"evidence": tampered_evidence})
    assert tampered.signature == target.signature
    assert tampered_evidence != target.evidence
    blockers = assess(profile, [*receipts[:index], tampered, *receipts[index + 1:]], **kwargs).blockers
    assert blockers == ("performance.budget:invalid_signature",)


def test_tampered_status_field_breaks_signature(ed_bundle):
    """Same attack, but on `status`/`candidate_sha`: a worker cannot flip fail->pass post-hoc."""
    profile, receipts, kwargs, _ = ed_bundle
    index = reviewer_index(receipts)
    target = receipts[index]
    tampered_evidence = target.evidence.model_copy(update={"status": "fail"})
    tampered = target.model_copy(update={"evidence": tampered_evidence})
    assert tampered.signature == target.signature
    blockers = assess(profile, [*receipts[:index], tampered, *receipts[index + 1:]], **kwargs).blockers
    assert blockers == (f"{target.evidence.check_id}:invalid_signature",)


def test_flipped_signature_hex_char_is_rejected(ed_bundle):
    """One hex character flipped in an otherwise well-formed 128-hex Ed25519 signature must not pass."""
    profile, receipts, kwargs, _ = ed_bundle
    index = reviewer_index(receipts)
    target = receipts[index]
    flipped_char = "1" if target.signature[0] != "1" else "2"
    flipped_signature = flipped_char + target.signature[1:]
    assert flipped_signature != target.signature
    tampered = target.model_copy(update={"signature": flipped_signature})
    blockers = assess(profile, [*receipts[:index], tampered, *receipts[index + 1:]], **kwargs).blockers
    assert blockers == (f"{target.evidence.check_id}:invalid_signature",)


def test_expired_key_with_backdated_evidence_blocked_after_max_age(ed_bundle):
    """A key whose `not_after` has passed, with evidence backdated to just before it, is not a
    valid loophole once the evidence itself has aged past `max_age_seconds` (default 24h):
    `assess` must block on `expired_or_future_evidence`, not silently accept a stale receipt.
    """
    profile, receipts, kwargs, signers = ed_bundle
    issuer = kwargs["trusted_issuers"]["qa"]
    index = reviewer_index(receipts)
    target = receipts[index]
    key_not_after = NOW
    created = key_not_after - timedelta(seconds=1)
    resigned_evidence = target.evidence.model_copy(update={"created_at": created, "expires_at": created + timedelta(hours=2)})
    resigned = sign_evidence(resigned_evidence, signers["qa"], key_id_of(signers["qa"]))
    kwargs["trusted_issuers"]["qa"] = replace(issuer, public_keys=(registry_key(signers["qa"], not_after=key_not_after),))
    too_late = key_not_after + timedelta(seconds=ED25519_POLICY["max_age_seconds"] + 1)
    # The key itself still verifies this receipt (created < not_after, created <= now): the
    # block below comes from evidence age, not from the key being past its not_after.
    assert verify_receipt(resigned, kwargs["trusted_issuers"]["qa"], now=too_late,
                          allowed_schemes=frozenset({"ed25519"})) == ""
    result = assess(profile, [*receipts[:index], resigned, *receipts[index + 1:]], **{**kwargs, "now": too_late})
    assert f"{target.evidence.check_id}:expired_or_future_evidence" in result.blockers


def test_expired_key_with_backdated_evidence_passes_within_max_age(ed_bundle):
    """Counter-case, ADR-0020 §4: a receipt signed just before its key's `not_after` still
    verifies when evaluated within the evidence age window, even though the key has since
    passed `not_after` in the registry. This acceptance window is deliberate; immediate
    revocation is done by removing the key from the registry, not by this age check.
    """
    profile, receipts, kwargs, signers = ed_bundle
    issuer = kwargs["trusted_issuers"]["qa"]
    index = reviewer_index(receipts)
    target = receipts[index]
    key_not_after = NOW
    created = key_not_after - timedelta(seconds=1)
    resigned_evidence = target.evidence.model_copy(update={"created_at": created, "expires_at": created + timedelta(hours=2)})
    resigned = sign_evidence(resigned_evidence, signers["qa"], key_id_of(signers["qa"]))
    kwargs["trusted_issuers"]["qa"] = replace(issuer, public_keys=(registry_key(signers["qa"], not_after=key_not_after),))
    within_window = key_not_after + timedelta(hours=1)  # < max_age_seconds (24h) after `created`
    result = assess(profile, [*receipts[:index], resigned, *receipts[index + 1:]], **{**kwargs, "now": within_window})
    assert target.evidence.check_id in result.passed
    assert result.quality_pass


def test_verify_cli_with_public_key_registry(ed_bundle, tmp_path, capsys):
    from datetime import UTC, datetime

    profile, _, kwargs, signers = ed_bundle
    current = datetime.now(UTC)
    receipts = []
    for check in required_checks(profile):
        issuer_id = "ci" if check.mode == "runner" else "qa"
        evidence = evidence_for(profile, check, tmp_path / f"{check.id}.txt", issuer_id,
                                created=current - timedelta(minutes=1))
        receipts.append(sign_evidence(evidence, signers[issuer_id], key_id_of(signers[issuer_id])))
    (tmp_path / "profile.json").write_text(profile.model_dump_json(), encoding="utf-8")
    (tmp_path / "receipts.json").write_text(json.dumps([r.model_dump(mode="json") for r in receipts]), encoding="utf-8")
    not_after = (current + timedelta(days=30)).isoformat()
    (tmp_path / "trust.json").write_text(json.dumps(_registry_document(signers, not_after)), encoding="utf-8")
    args = ["verify", str(tmp_path / "profile.json"), str(tmp_path / "receipts.json"),
            "--contract-hash", kwargs["expected_contract_hash"], "--candidate-sha", SHA, "--context-hash", CONTEXT,
            "--author", "implementation-worker", "--evidence-root", str(tmp_path),
            "--trust-registry", str(tmp_path / "trust.json")]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["quality_pass"]
