from __future__ import annotations

import subprocess
import time
from string import Template
from typing import Any

import networkx as nx

from .env import Env
from .graph import apply_operation
from .modifiers import EdgeGuard, GraphModifier, TransientHook, TransitionObserver
from .schema import (
    CaseResult,
    ObserverResult,
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


def _run_callable(
    func: Any,
    params: dict[str, Any],
) -> tuple[bool, str, str, Any]:
    try:
        ret = func(params)
        return True, "", "", ret
    except Exception as e:
        return False, "", str(e), None


def _extract_modifier(value: Any) -> GraphModifier | None:
    if isinstance(value, (EdgeGuard, TransientHook, TransitionObserver)):
        return value
    return None


def run_step(
    operation: Operation,
    params: dict[str, Any],
    timeout: int = 300,
) -> tuple[StepResult, GraphModifier | None]:
    if operation.callable is not None:
        start = time.monotonic()
        ok, stdout, stderr, ret = _run_callable(operation.callable, params)
        duration = (time.monotonic() - start) * 1000
        modifier = _extract_modifier(ret) if ok else None
        result = StepResult(
            operation=operation.name,
            status="pass" if ok else "fail",
            duration_ms=round(duration, 2),
            stdout=stdout,
            stderr=stderr,
            error=None if ok else stderr,
        )
        if modifier is not None:
            _record_modifier(result, modifier)
        return result, modifier

    command = _substitute_params(operation.run, params)
    if not command.strip():
        return StepResult(operation=operation.name, status="skip"), None

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
    ), None


def _record_modifier(result: StepResult, modifier: GraphModifier) -> None:
    if isinstance(modifier, EdgeGuard):
        result.modifier_type = "edge_guard"
        result.modifier_detail = f"Blocked '{modifier.blocked_op}': {modifier.reason}"
    elif isinstance(modifier, TransientHook):
        result.modifier_type = "transient_hook"
        result.modifier_detail = f"Hook before '{modifier.before_op}': {modifier.reason}"
    elif isinstance(modifier, TransitionObserver):
        result.modifier_type = "transition_observer"
        result.modifier_detail = f"Watching {modifier.watch_ops}: {modifier.reason}"


def _run_hook(hook: TransientHook, params: dict[str, Any]) -> StepResult:
    name = hook.name or f"hook_before_{hook.before_op}"
    start = time.monotonic()
    try:
        hook.action(params)
        duration = (time.monotonic() - start) * 1000
        return StepResult(
            operation=name,
            status="pass",
            duration_ms=round(duration, 2),
            injected=True,
            modifier_detail=hook.reason,
        )
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        return StepResult(
            operation=name,
            status="fail",
            duration_ms=round(duration, 2),
            stderr=str(e),
            error=str(e),
            injected=True,
        )


def _run_observer(obs: TransitionObserver, params: dict[str, Any]) -> ObserverResult:
    start = time.monotonic()
    try:
        obs.verify(params)
        duration = (time.monotonic() - start) * 1000
        return ObserverResult(
            observer_name=obs.name or "observer",
            status="pass",
            duration_ms=round(duration, 2),
        )
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        return ObserverResult(
            observer_name=obs.name or "observer",
            status="fail",
            error=str(e),
            duration_ms=round(duration, 2),
        )


def _replan_remaining(
    current_env: Env,
    target_op: Operation,
    graph: nx.MultiDiGraph,
    blocked_ops: set[str],
) -> list[str] | None:
    def edge_ok(u: Any, v: Any, key: Any) -> bool:
        return graph.edges[u, v, key]["operation"] not in blocked_ops

    filtered = nx.subgraph_view(graph, filter_edge=edge_ok)

    target_nodes = []
    for node in filtered.nodes:
        if not all(node.is_active(r) for r in target_op.requires):
            continue
        if any(node.is_active(s) for s in target_op.excludes):
            continue
        target_nodes.append(node)

    if current_env not in filtered:
        return None

    best_path = None
    for target in target_nodes:
        try:
            path = nx.shortest_path(filtered, current_env, target)
            if best_path is None or len(path) < len(best_path):
                best_path = path
        except nx.NetworkXNoPath:
            continue

    if best_path is None:
        return None

    result = []
    for i in range(len(best_path) - 1):
        u, v = best_path[i], best_path[i + 1]
        for _, data in filtered[u][v].items():
            if data["operation"] not in blocked_ops:
                result.append(data["operation"])
                break
    return result


def run_case(
    case: TestCase,
    definition: TestDefinition,
    timeout: int = 300,
    graph: nx.MultiDiGraph | None = None,
) -> CaseResult:
    ops_by_name = {op.name: op for op in definition.operations}
    params = dict(case.params) if case.params else dict(definition.suite.params)
    step_results: list[StepResult] = []
    case_status = "pass"
    replanned = False
    replan_reason = None
    start = time.monotonic()

    blocked_ops: set[str] = set()
    hooks: list[TransientHook] = []
    observers: list[TransitionObserver] = []
    current_env = Env()

    remaining_main = list(case.steps)
    cleanup_steps = list(case.cleanup_steps) if case.cleanup_steps else []
    max_replans = 3
    replan_count = 0

    main_idx = 0
    while main_idx < len(remaining_main):
        step_name = remaining_main[main_idx]
        op = ops_by_name.get(step_name)

        if op is None:
            step_results.append(StepResult(
                operation=step_name,
                status="error",
                error=f"Unknown operation '{step_name}'",
            ))
            case_status = "error"
            break

        # Check edge guards
        if step_name in blocked_ops:
            if graph is None or replan_count >= max_replans:
                msg = "No graph for replan" if graph is None else "Max replans exceeded"
                step_results.append(StepResult(
                    operation=step_name,
                    status="error",
                    error=f"Operation blocked: {msg}",
                ))
                case_status = "error"
                break

            target_op = ops_by_name.get(case.target)
            new_steps = _replan_remaining(current_env, target_op, graph, blocked_ops)
            if new_steps is None:
                step_results.append(StepResult(
                    operation=step_name,
                    status="error",
                    error="Replan failed: no alternative path",
                ))
                case_status = "error"
                break

            remaining_main = new_steps + [case.target]
            main_idx = 0
            replan_count += 1
            replanned = True
            replan_reason = f"Blocked: {step_name}"
            continue

        # Fire transient hooks
        fired = [h for h in hooks if h.before_op == step_name]
        for hook in fired:
            hook_result = _run_hook(hook, params)
            step_results.append(hook_result)
            hooks.remove(hook)
            if hook_result.status in ("fail", "error"):
                case_status = hook_result.status
                break
        if case_status != "pass":
            break

        # Execute the step
        result, modifier = run_step(op, params, timeout)
        step_results.append(result)

        # Update env tracking
        new_env = apply_operation(current_env, op)
        if new_env is not None:
            current_env = new_env

        # Process modifier
        if modifier is not None:
            if isinstance(modifier, EdgeGuard):
                blocked_ops.add(modifier.blocked_op)
            elif isinstance(modifier, TransientHook):
                hooks.append(modifier)
            elif isinstance(modifier, TransitionObserver):
                observers.append(modifier)

        # Run transition observers
        matching = [o for o in observers if step_name in o.watch_ops]
        for obs in matching:
            obs_result = _run_observer(obs, params)
            result.observer_results.append(obs_result)
            if obs_result.status in ("fail", "error"):
                case_status = obs_result.status
                break

        if result.status in ("fail", "error"):
            case_status = result.status

        if case_status != "pass":
            break

        main_idx += 1

    # Cleanup phase — no modifier processing
    if case_status != "pass" or cleanup_steps:
        for cleanup_name in cleanup_steps:
            cleanup_op = ops_by_name.get(cleanup_name)
            if cleanup_op:
                cleanup_result, _ = run_step(cleanup_op, params, timeout)
                step_results.append(cleanup_result)

    duration = (time.monotonic() - start) * 1000

    return CaseResult(
        case_id=case.case_id,
        steps=step_results,
        status=case_status,
        duration_ms=round(duration, 2),
        replanned=replanned,
        replan_reason=replan_reason,
    )


def run_all(
    cases: list[TestCase],
    definition: TestDefinition,
    timeout: int = 300,
    graph: nx.MultiDiGraph | None = None,
) -> list[CaseResult]:
    return [run_case(case, definition, timeout, graph=graph) for case in cases]
