"""Product-quality adapter for the existing execution kernel (root ADR-0018).

No second scheduler, state machine, identity provider or deployment authority.
Only a trusted coordinator may supply pins/identities or append the assessed
result to its journal. This module never writes a task-success event itself.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from xagents_core.execution import (
    Complexity,
    ExecutionJournal,
    ExecutionJournalError,
    RunSpec,
    TaskResult,
    TaskSpec,
    TaskStatus,
)

from .product_quality import ProjectProfile, Receipt, TrustedIssuer, assess, compile_contract, required_checks

QUALITY_TASK_ID = "quality:accept"
CONTRACT_PREFIX = "quality-contract:sha256:"


def compile_execution(profile: ProjectProfile, work: RunSpec) -> RunSpec:
    """Preserve the work DAG and append one aggregate, read-only quality barrier.

    Use the original work spec on repeated calls. Registration of the identical
    compiled spec is idempotent in ExecutionJournal; a changed contract needs a
    new run/revision, not overwriting an already registered execution plan.
    """
    if work.run_id != profile.run_id or work.objective != profile.goal:
        raise ValueError("profile and execution run/goal must match")
    if not work.tasks:
        raise ValueError("a quality run requires a nonempty work DAG")
    if any(task.task_id.startswith("quality:") for task in work.tasks):
        raise ValueError("quality task namespace is reserved; supply the original work spec")
    if any(ref.startswith(CONTRACT_PREFIX) for task in work.tasks for ref in task.context_refs):
        raise ValueError("work spec already has a quality pin; do not mix contract revisions")
    pin = CONTRACT_PREFIX + str(compile_contract(profile)["contract_hash"])
    tasks = tuple(replace(task, context_refs=(*task.context_refs, pin)) for task in work.tasks)
    barrier = TaskSpec(
        task_id=QUALITY_TASK_ID,
        objective="Independently verify the pinned product contract on the selected candidate before completion.",
        dependencies=tuple(task.task_id for task in tasks),
        complexity=Complexity.C3,
        acceptance=tuple(check.id for check in required_checks(profile)),
        context_refs=(pin,),
        # No generic tool/write privileges; the coordinator binds trusted evidence drivers.
    )
    return RunSpec(work.run_id, work.objective, (*tasks, barrier))


def evaluate_result(
    profile: ProjectProfile,
    result: TaskResult,
    receipts: list[Receipt],
    *,
    expected_attempt_id: str,
    expected_base_sha: str,
    expected_diff_hash: str,
    expected_contract_hash: str,
    candidate_sha: str,
    context_hash: str,
    author_principals: frozenset[str],
    trusted_issuers: dict[str, TrustedIssuer],
    evidence_root: Path,
    now: datetime | None = None,
) -> TaskResult:
    """Fail-closed conversion to a native TaskResult, preserving evidence/artifacts.

    Expected identity/revision values must come from the coordinator, not from
    the worker's result. A passing result is NOT authority to append events,
    merge or deploy. Existing core command receipts cannot override domain checks.
    """
    if not expected_attempt_id.strip():
        raise ValueError("an independently pinned attempt is required")
    for value in (expected_base_sha, candidate_sha):
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
            raise ValueError("full base and candidate revisions are required")
    for value in (expected_diff_hash, expected_contract_hash, context_hash):
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("full diff/contract/context digests are required")
    assessment = assess(
        profile, receipts, expected_contract_hash=expected_contract_hash,
        candidate_sha=candidate_sha, context_hash=context_hash,
        author_principals=author_principals, trusted_issuers=trusted_issuers,
        evidence_root=evidence_root, now=now,
    )
    blockers = [*result.findings, *assessment.blockers]
    if result.task_id != QUALITY_TASK_ID or result.attempt_id != expected_attempt_id:
        blockers.append("execution:wrong_task_or_attempt")
    if result.base_sha != expected_base_sha or result.head_sha != candidate_sha or result.diff_hash != expected_diff_hash:
        blockers.append("execution:stale_base_head_or_diff")
    if result.status is not TaskStatus.SUCCEEDED:
        blockers.append("execution:source_not_succeeded")
    if result.unresolved:
        blockers.append("execution:unresolved_decisions")
    if any(not item.passed or item.head_sha != candidate_sha for item in result.evidence):
        blockers.append("execution:failed_or_stale_command_evidence")
    return replace(result, status=TaskStatus.FAILED if blockers else TaskStatus.SUCCEEDED,
                   findings=tuple(dict.fromkeys(blockers)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bind product quality to the native execution kernel")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "register"):
        command = sub.add_parser(name)
        command.add_argument("profile", type=Path)
        command.add_argument("work", type=Path)
        if name == "register":
            command.add_argument("--journal", type=Path, required=True)
    status = sub.add_parser("status")
    status.add_argument("run_id")
    status.add_argument("--journal", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output: dict[str, Any]
        if args.command == "status":
            if not args.journal.is_file():
                raise ValueError("journal does not exist; status must not create an empty run")
            with ExecutionJournal(args.journal) as journal:
                state = journal.resume(args.run_id)
            output = {"run_id": state.run_id, "status": state.status.value,
                      "tasks": {key: value.value for key, value in state.tasks.items()},
                      "attempts": state.attempts, "blocked_reason": state.blocked_reason}
        else:
            profile = ProjectProfile.model_validate_json(args.profile.read_text(encoding="utf-8"))
            work = RunSpec.from_json(args.work.read_text(encoding="utf-8"))
            spec = compile_execution(profile, work)
            if args.command == "register":
                with ExecutionJournal(args.journal) as journal:
                    journal.register(spec)
            output = {"quality_contract": compile_contract(profile), "execution_spec": json.loads(spec.to_json())}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ExecutionJournalError, sqlite3.Error) as error:
        print(f"Invalid execution input ({type(error).__name__}); no task completion issued.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
