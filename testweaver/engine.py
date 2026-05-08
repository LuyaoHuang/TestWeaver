from __future__ import annotations

import subprocess
import time
from string import Template
from typing import Any

from .schema import (
    CaseResult,
    Operation,
    StepResult,
    TestCase,
    TestDefinition,
)


def _substitute_params(command: str, params: dict[str, Any]) -> str:
    str_params = {k: str(v) for k, v in params.items()}
    return Template(command).safe_substitute(str_params)


def _run_command(command: str, timeout: int = 300) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def run_step(
    operation: Operation,
    params: dict[str, Any],
    timeout: int = 300,
) -> StepResult:
    command = _substitute_params(operation.run, params)
    if not command.strip():
        return StepResult(
            operation=operation.name,
            status="skip",
        )

    start = time.monotonic()
    returncode, stdout, stderr = _run_command(command, timeout)
    duration = (time.monotonic() - start) * 1000

    if returncode == 0:
        status = "pass"
        error = None
    else:
        status = "fail"
        error = f"Exit code {returncode}"

    return StepResult(
        operation=operation.name,
        status=status,
        duration_ms=round(duration, 2),
        stdout=stdout,
        stderr=stderr,
        error=error,
    )


def run_case(
    case: TestCase,
    definition: TestDefinition,
    timeout: int = 300,
) -> CaseResult:
    ops_by_name = {op.name: op for op in definition.operations}
    params = dict(definition.suite.params)
    step_results: list[StepResult] = []
    case_status = "pass"
    start = time.monotonic()

    all_steps = list(case.steps)
    if case.cleanup_steps:
        all_steps.extend(case.cleanup_steps)

    cleanup_start_idx = len(case.steps)

    for i, step_name in enumerate(all_steps):
        op = ops_by_name.get(step_name)
        if op is None:
            step_results.append(StepResult(
                operation=step_name,
                status="error",
                error=f"Unknown operation '{step_name}'",
            ))
            if i < cleanup_start_idx:
                case_status = "error"
                break
            continue

        result = run_step(op, params, timeout)
        step_results.append(result)

        if result.status in ("fail", "error") and i < cleanup_start_idx:
            case_status = result.status
            for remaining in all_steps[cleanup_start_idx:]:
                cleanup_op = ops_by_name.get(remaining)
                if cleanup_op:
                    step_results.append(run_step(cleanup_op, params, timeout))
            break

    duration = (time.monotonic() - start) * 1000

    return CaseResult(
        case_id=case.case_id,
        steps=step_results,
        status=case_status,
        duration_ms=round(duration, 2),
    )


def run_all(
    cases: list[TestCase],
    definition: TestDefinition,
    timeout: int = 300,
) -> list[CaseResult]:
    return [run_case(case, definition, timeout) for case in cases]
