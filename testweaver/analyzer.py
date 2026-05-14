from __future__ import annotations

from collections import Counter

from .schema import (
    CaseResult,
    DebugSuggestion,
    FailureDetail,
    HookResult,
    Operation,
    RunSummary,
)


def summarize_run(
    results: list[CaseResult],
    suite_hook_results: list[HookResult] | None = None,
) -> RunSummary:
    """Compute summary statistics from a list of case results.

    Args:
        results: Completed case results from a test run.

    Returns:
        Aggregated counts, timing, failure patterns, and slowest steps.
    """
    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    errors = sum(1 for r in results if r.status == "error")
    duration = sum(r.duration_ms for r in results)

    failure_ops: Counter[str] = Counter()
    for r in results:
        if r.status in ("fail", "error"):
            for step in r.steps:
                if step.status in ("fail", "error"):
                    failure_ops[step.operation] += 1

    failure_patterns = [
        f"{op} failed {count} time(s)" for op, count in failure_ops.most_common(5)
    ]

    all_steps = []
    for r in results:
        for step in r.steps:
            if step.status == "pass":
                all_steps.append({"operation": step.operation, "duration_ms": step.duration_ms})
    all_steps.sort(key=lambda s: s["duration_ms"], reverse=True)

    flaky = sum(1 for r in results if r.flaky)
    retried = sum(1 for r in results if r.retry_count > 0)

    return RunSummary(
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        duration_ms=round(duration, 2),
        failure_patterns=failure_patterns,
        slowest_steps=all_steps[:5],
        flaky=flaky,
        retried=retried,
        suite_hook_results=suite_hook_results or [],
    )


def find_failures(
    results: list[CaseResult],
    operations: list[Operation] | None = None,
) -> list[FailureDetail]:
    """Extract failure details from case results.

    Args:
        results: Completed case results.
        operations: If provided, enriches failures with state info.

    Returns:
        One FailureDetail per failed case (first failing step only).
    """
    ops_by_name = {op.name: op for op in operations} if operations else {}
    failures = []

    for r in results:
        if r.status == "pass":
            continue
        for i, step in enumerate(r.steps):
            if step.status in ("fail", "error"):
                op = ops_by_name.get(step.operation)
                failures.append(FailureDetail(
                    case_id=r.case_id,
                    failed_step=step.operation,
                    step_index=i,
                    stderr=step.stderr,
                    error=step.error,
                    required_states=op.requires if op else [],
                    active_states=op.provides if op else [],
                ))
                break

    return failures


def suggest_debug(
    failure: FailureDetail,
    operations: list[Operation],
) -> DebugSuggestion:
    """Generate a debugging suggestion for a single failure.

    Args:
        failure: The failure to diagnose.
        operations: All operations in the test definition.

    Returns:
        A suggestion with likely cause and relevant provider operations.
    """
    ops_by_name = {op.name: op for op in operations}
    failed_op = ops_by_name.get(failure.failed_step)

    if not failed_op:
        return DebugSuggestion(
            failure=failure,
            likely_cause=f"Unknown operation '{failure.failed_step}'",
            message="The failed operation is not defined in the test definition.",
        )

    providers = []
    for req in failed_op.requires:
        for op in operations:
            if req in op.provides and op.name != failed_op.name:
                providers.append(op.name)

    likely_cause = ""
    message = ""

    if failure.error and "timed out" in failure.error.lower():
        likely_cause = "Command timeout"
        message = (
            f"Operation '{failed_op.name}' timed out. "
            f"Consider increasing the timeout with @timeout(seconds) decorator "
            f"or the 'timeout' field in YAML."
        )
    elif failure.stderr:
        likely_cause = "Command execution error"
        message = (
            f"Operation '{failed_op.name}' failed with stderr output. "
            f"Review the command: {failed_op.run.strip()[:200]}"
        )
    elif failed_op.requires:
        likely_cause = "Possible missing prerequisite state"
        message = (
            f"Operation '{failed_op.name}' requires states {failed_op.requires}. "
            f"Verify that operations {providers} completed successfully."
        )
    else:
        likely_cause = "Unknown failure"
        message = f"Operation '{failed_op.name}' failed without clear error output."

    return DebugSuggestion(
        failure=failure,
        likely_cause=likely_cause,
        suggested_operations=providers,
        message=message,
    )
