from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial
from string import Template
from typing import Any, Callable

import networkx as nx

from .log import get_logger

logger = get_logger(__name__)

from .env import Env
from .graph import _render_state_paths, apply_operation
from .modifiers import EdgeGuard, GraphModifier, TransientHook, TransitionObserver
from .schema import (
    AttemptResult,
    CaseResult,
    HookResult,
    ObserverResult,
    Operation,
    ProgressEvent,
    StateData,
    StepResult,
    TestCase,
    TestDefinition,
)


def _substitute_params(command: str, params: dict[str, Any]) -> str:
    """Substitute parameter placeholders in a shell command string."""
    str_params = {k: str(v) for k, v in params.items()}
    return Template(command).safe_substitute(str_params)


def _run_command(command: str, timeout: int = 300) -> tuple[int, str, str]:
    """Execute a shell command and return exit code, stdout, and stderr."""
    logger.debug("Executing command: %s (timeout=%ds)", command, timeout)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        logger.debug("Command exit code: %d", result.returncode)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", timeout, command)
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        logger.debug("Command failed with exception: %s", e)
        return -1, "", str(e)


def _run_callable(
    func: Callable[..., Any],
    params: dict[str, Any],
    env: Env,
    timeout: int = 300,
) -> tuple[bool, str, str, Any, bool]:
    """Call a Python callable with params and env, capture success/output/return.

    Returns:
        ``(ok, stdout, stderr, return_value, is_assertion_failure)``
    """
    logger.debug("Calling %s (timeout=%ds)", getattr(func, "__qualname__", func), timeout)

    use_alarm = threading.current_thread() is threading.main_thread()

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"Callable timed out after {timeout}s")

    if use_alarm:
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
    try:
        ret = func(params, env)
        if use_alarm:
            signal.alarm(0)
        logger.debug("Callable succeeded")
        return True, "", "", ret, False
    except TimeoutError as e:
        logger.warning("Callable timed out after %ds", timeout)
        return False, "", str(e), None, False
    except Exception as e:
        if use_alarm:
            signal.alarm(0)
        from .assertions import AssertionError as _AssertionError
        is_assert = isinstance(e, _AssertionError)
        logger.debug("Callable raised %s: %s", type(e).__name__, e)
        return False, "", str(e), None, is_assert
    finally:
        if use_alarm:
            signal.signal(signal.SIGALRM, old_handler)


def _apply_state_data(
    sd: StateData, operation: Operation, env: Env,
) -> dict[str, Any]:
    """Apply StateData values to env nodes and return the resolved mapping.

    Auto-maps keyword-style data to the operation's single ``provides``
    path when no explicit paths are present in the values dict.
    """
    values = dict(sd.values)
    if values and operation.provides and len(operation.provides) == 1:
        has_path_keys = any('.' in k for k in values)
        if not has_path_keys:
            values = {operation.provides[0]: values}
    for path, data in values.items():
        env.set_value(path, data)
    return values


def _extract_modifier(value: Any) -> GraphModifier | None:
    """Extract a GraphModifier from a callable's return value, if present."""
    if isinstance(value, (EdgeGuard, TransientHook, TransitionObserver)):
        return value
    return None


def _parse_instance_params(step_name: str) -> tuple[str, dict[str, Any]]:
    """Parse instance parameters from a step name like ``'op[k=v]'``."""
    if '[' not in step_name:
        return step_name, {}
    base, rest = step_name.split('[', 1)
    param_str = rest.rstrip(']')
    instance_params: dict[str, Any] = {}
    for pair in param_str.split(','):
        k, v = pair.strip().split('=', 1)
        instance_params[k] = v
    return base, instance_params


def _run_lifecycle_hook(
    func: Callable[..., Any],
    hook_type: str,
    context: dict[str, Any],
) -> HookResult:
    """Execute a single lifecycle hook and return its result."""
    name = getattr(func, '__qualname__', getattr(func, '__name__', hook_type))
    logger.info("Running %s hook: %s", hook_type, name)
    start = time.monotonic()
    try:
        func(context)
        duration = (time.monotonic() - start) * 1000
        logger.info("Hook %s passed (%.0fms)", name, duration)
        return HookResult(
            hook_name=name,
            hook_type=hook_type,
            status="pass",
            duration_ms=round(duration, 2),
        )
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        logger.error("Hook %s failed: %s (%.0fms)", name, e, duration)
        return HookResult(
            hook_name=name,
            hook_type=hook_type,
            status="error",
            error=str(e),
            duration_ms=round(duration, 2),
        )


def _run_hooks(
    hooks: list[Callable[..., Any]],
    hook_type: str,
    context: dict[str, Any],
) -> list[HookResult]:
    """Run a list of lifecycle hooks in order, collecting results."""
    results = []
    for func in hooks:
        result = _run_lifecycle_hook(func, hook_type, context)
        results.append(result)
    return results


def run_step(
    operation: Operation,
    params: dict[str, Any],
    env: Env,
    timeout: int = 300,
) -> tuple[StepResult, GraphModifier | None]:
    """Execute a single test step and return its result.

    Runs the operation's callable (if set) or shell command, captures
    timing and output, and extracts any returned graph modifier.

    Args:
        operation: The operation to execute.
        params: Parameter dict passed to the callable or substituted
            into the shell command.
        env: Current runtime environment.  Callables receive this as
            their second argument and can read/write node values via
            ``env.get_node(path).value`` or ``env.set_value(path, v)``.
        timeout: Maximum execution time in seconds for shell commands.

    Returns:
        A tuple of ``(StepResult, optional GraphModifier)``.
    """
    logger.info("Step started: %s", operation.name)

    if operation.callable is not None:
        start = time.monotonic()
        ok, stdout, stderr, ret, is_assert = _run_callable(operation.callable, params, env, timeout)
        duration = (time.monotonic() - start) * 1000
        env_data = None
        if ok and isinstance(ret, StateData):
            env_data = _apply_state_data(ret, operation, env)
        modifier = _extract_modifier(ret) if ok else None
        result = StepResult(
            operation=operation.name,
            status="pass" if ok else "fail",
            duration_ms=round(duration, 2),
            stdout=stdout,
            stderr=stderr,
            error=None if ok else stderr,
            env_data=env_data,
            is_assertion_failure=is_assert,
        )
        if modifier is not None:
            _record_modifier(result, modifier)
        logger.info("Step finished: %s status=%s (%.0fms)", operation.name, result.status, duration)
        return result, modifier

    command = _substitute_params(operation.run, params)
    if not command.strip():
        logger.info("Step skipped (empty command): %s", operation.name)
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

    logger.info("Step finished: %s status=%s (%.0fms)", operation.name, status, duration)
    return StepResult(
        operation=operation.name,
        status=status,
        duration_ms=round(duration, 2),
        stdout=stdout,
        stderr=stderr,
        error=error,
    ), None


def _record_modifier(result: StepResult, modifier: GraphModifier) -> None:
    """Record modifier type and detail on a step result."""
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
    """Execute a transient hook and return its step result."""
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
    """Execute a transition observer's verify callback."""
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


def _run_verify(
    operation: Operation,
    params: dict[str, Any],
    env: Env,
    timeout: int = 300,
) -> ObserverResult | None:
    """Run the operation's verify callback or command, if defined."""
    if operation.verify_callable is not None:
        start = time.monotonic()
        ok, _, stderr, _, _ = _run_callable(operation.verify_callable, params, env, timeout)
        duration = (time.monotonic() - start) * 1000
        if ok:
            return ObserverResult(
                observer_name=f"verify_{operation.name}",
                status="pass",
                duration_ms=round(duration, 2),
            )
        return ObserverResult(
            observer_name=f"verify_{operation.name}",
            status="fail",
            error=stderr,
            duration_ms=round(duration, 2),
        )
    if operation.verify:
        command = _substitute_params(operation.verify, params)
        if not command.strip():
            return None
        start = time.monotonic()
        returncode, stdout, stderr = _run_command(command, timeout)
        duration = (time.monotonic() - start) * 1000
        if returncode == 0:
            return ObserverResult(
                observer_name=f"verify_{operation.name}",
                status="pass",
                duration_ms=round(duration, 2),
            )
        return ObserverResult(
            observer_name=f"verify_{operation.name}",
            status="fail",
            error=stderr or f"Exit code {returncode}",
            duration_ms=round(duration, 2),
        )
    return None


def _replan_remaining(
    current_env: Env,
    target_op: Operation,
    graph: nx.MultiDiGraph,
    blocked_ops: set[str],
) -> list[str] | None:
    """Attempt to find an alternative path when an operation is blocked."""
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
    """Execute all steps of a test case, including cleanup.

    Handles edge guards (replanning), transient hooks, transition
    observers, and verify callbacks during execution.

    Args:
        case: The test case to run.
        definition: Full test definition for operation lookup.
        timeout: Per-step timeout in seconds.
        graph: Pre-built graph for replanning on blocked operations.

    Returns:
        Aggregate result for the case.
    """
    logger.info("Case started: %s (target=%s, steps=%d)", case.case_id, case.target, len(case.steps))
    ops_by_name = {op.name: op for op in definition.operations}
    params = dict(case.params) if case.params else dict(definition.suite.params)
    step_results: list[StepResult] = []
    case_status = "pass"
    replanned = False
    replan_reason = None
    start = time.monotonic()

    blocked_ops: set[str] = set()
    transient_hooks: list[TransientHook] = []
    observers: list[TransitionObserver] = []
    current_env = Env()

    remaining_main = list(case.steps)
    cleanup_steps = list(case.cleanup_steps) if case.cleanup_steps else []
    max_replans = 3
    replan_count = 0

    lc_hook_results: list[HookResult] = []

    case_context = {**params, '_case': case, '_case_id': case.case_id}
    if definition.hooks.case_setup:
        setup_results = _run_hooks(
            definition.hooks.case_setup, "case_setup", case_context,
        )
        lc_hook_results.extend(setup_results)
        if any(r.status != "pass" for r in setup_results):
            case_status = "error"

    try:
        main_idx = 0
        while main_idx < len(remaining_main) and case_status == "pass":
            step_name = remaining_main[main_idx]
            op = ops_by_name.get(step_name)
            instance_params: dict[str, Any] = {}

            if op is None and '[' in step_name:
                base_name, instance_params = _parse_instance_params(step_name)
                op = ops_by_name.get(base_name)
                if op is not None:
                    op = _render_state_paths(op, instance_params)

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
                logger.debug("Operation '%s' is blocked by edge guard", step_name)
                if graph is None or replan_count >= max_replans:
                    msg = "No graph for replan" if graph is None else "Max replans exceeded"
                    logger.debug("Cannot replan: %s", msg)
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
                    logger.debug("Replan failed: no alternative path found")
                    step_results.append(StepResult(
                        operation=step_name,
                        status="error",
                        error="Replan failed: no alternative path",
                    ))
                    case_status = "error"
                    break

                logger.info("Replanned around '%s': new path %s", step_name, new_steps)
                remaining_main = new_steps + [case.target]
                main_idx = 0
                replan_count += 1
                replanned = True
                replan_reason = f"Blocked: {step_name}"
                continue

            # Fire transient hooks
            fired = [h for h in transient_hooks if h.before_op == step_name]
            for hook in fired:
                logger.debug("Firing transient hook before '%s': %s", step_name, hook.reason)
                hook_result = _run_hook(hook, params)
                step_results.append(hook_result)
                transient_hooks.remove(hook)
                if hook_result.status in ("fail", "error"):
                    case_status = hook_result.status
                    break
            if case_status != "pass":
                break

            # Execute the step with per-step params (instance values merged)
            step_params = dict(params)
            if instance_params:
                step_params.update(instance_params)
            step_timeout = op.timeout if op.timeout is not None else timeout
            result, modifier = run_step(op, step_params, current_env, step_timeout)
            step_results.append(result)

            # Run verify if step passed
            if result.status == "pass":
                verify_result = _run_verify(op, step_params, current_env, step_timeout)
                if verify_result is not None:
                    result.verify_result = verify_result
                    if verify_result.status != "pass":
                        case_status = verify_result.status
                        break

            # Update env tracking
            new_env = apply_operation(current_env, op)
            if new_env is not None:
                current_env = new_env

            # Process modifier
            if modifier is not None:
                logger.debug("Modifier returned from '%s': %s", step_name, type(modifier).__name__)
                if isinstance(modifier, EdgeGuard):
                    blocked_ops.add(modifier.blocked_op)
                elif isinstance(modifier, TransientHook):
                    transient_hooks.append(modifier)
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
            logger.debug("Entering cleanup phase (%d steps)", len(cleanup_steps))
            for cleanup_name in cleanup_steps:
                cleanup_op = ops_by_name.get(cleanup_name)
                cleanup_params = dict(params)
                if cleanup_op is None and '[' in cleanup_name:
                    base, inst_params = _parse_instance_params(cleanup_name)
                    cleanup_op = ops_by_name.get(base)
                    if cleanup_op is not None:
                        cleanup_op = _render_state_paths(cleanup_op, inst_params)
                        cleanup_params.update(inst_params)
                if cleanup_op:
                    cleanup_timeout = cleanup_op.timeout if cleanup_op.timeout is not None else timeout
                    cleanup_result, _ = run_step(cleanup_op, cleanup_params, current_env, cleanup_timeout)
                    step_results.append(cleanup_result)
    finally:
        if definition.hooks.case_teardown:
            teardown_results = _run_hooks(
                definition.hooks.case_teardown, "case_teardown",
                {**case_context, '_status': case_status},
            )
            lc_hook_results.extend(teardown_results)

    duration = (time.monotonic() - start) * 1000
    logger.info("Case finished: %s status=%s (%.0fms)", case.case_id, case_status, duration)

    return CaseResult(
        case_id=case.case_id,
        steps=step_results,
        status=case_status,
        duration_ms=round(duration, 2),
        replanned=replanned,
        replan_reason=replan_reason,
        is_fault=case.is_fault,
        hook_results=lc_hook_results,
    )


def run_case_with_retries(
    case: TestCase,
    definition: TestDefinition,
    timeout: int = 300,
    graph: nx.MultiDiGraph | None = None,
    retries: int = 0,
    retry_delay: float = 0.0,
) -> CaseResult:
    """Run a single test case with optional retries on failure.

    Args:
        case: The test case to run.
        definition: Full test definition for operation lookup.
        timeout: Per-step timeout in seconds.
        graph: Pre-built graph for replanning on blocked operations.
        retries: Maximum number of retry attempts after the first run.
        retry_delay: Seconds to wait between retry attempts.

    Returns:
        Final case result with retry metadata populated.
    """
    overall_start = time.monotonic()
    attempts: list[AttemptResult] = []
    result: CaseResult | None = None

    for attempt_num in range(1, retries + 2):
        if attempt_num > 1:
            logger.info(
                "Retrying case '%s' (attempt %d/%d)",
                case.case_id, attempt_num, retries + 1,
            )
            if retry_delay > 0:
                time.sleep(retry_delay)

        result = run_case(case, definition, timeout, graph)

        attempts.append(AttemptResult(
            attempt=attempt_num,
            steps=result.steps,
            status=result.status,
            duration_ms=result.duration_ms,
        ))

        if result.status == "pass":
            break

    assert result is not None
    actual_retries = len(attempts) - 1
    had_failure = any(a.status in ("fail", "error") for a in attempts[:-1])
    is_flaky = result.status == "pass" and had_failure

    overall_duration = (time.monotonic() - overall_start) * 1000

    final = CaseResult(
        case_id=case.case_id,
        steps=result.steps,
        status=result.status,
        duration_ms=round(overall_duration, 2),
        replanned=result.replanned,
        replan_reason=result.replan_reason,
        is_fault=result.is_fault,
        attempts=attempts if actual_retries > 0 else [],
        flaky=is_flaky,
        retry_count=actual_retries,
        hook_results=result.hook_results,
    )

    if is_flaky:
        logger.warning(
            "Case '%s' is flaky: failed %d attempt(s) then passed",
            case.case_id,
            sum(1 for a in attempts if a.status != "pass"),
        )
    elif actual_retries > 0 and result.status != "pass":
        logger.warning(
            "Case '%s' failed after %d attempt(s)",
            case.case_id, len(attempts),
        )

    return final


def run_all(
    cases: list[TestCase],
    definition: TestDefinition,
    timeout: int = 300,
    graph: nx.MultiDiGraph | None = None,
    workers: int = 1,
    retries: int = 0,
    retry_delay: float = 0.0,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> tuple[list[CaseResult], list[HookResult]]:
    """Run test cases and return their results.

    Args:
        cases: Test cases to execute.
        definition: Full test definition for operation lookup.
        timeout: Per-step timeout in seconds.
        graph: Pre-built graph for replanning on blocked operations.
        workers: Number of parallel workers.  ``1`` runs sequentially,
            ``0`` auto-detects based on CPU count, and any value ``>1``
            uses that many threads.
        retries: Maximum number of retry attempts for each failed case.
        retry_delay: Seconds to wait between retry attempts.
        on_progress: Optional callback invoked after each case completes.

    Returns:
        Tuple of (case results in same order as *cases*, suite hook results).
    """
    if workers == 0:
        workers = os.cpu_count() or 1

    if retries > 0:
        logger.info(
            "Running %d case(s) with %d worker(s), max_retries=%d, retry_delay=%.1fs",
            len(cases), workers, retries, retry_delay,
        )
    else:
        logger.info("Running %d case(s) with %d worker(s)", len(cases), workers)
    start = time.monotonic()

    suite_hook_results: list[HookResult] = []
    suite_context: dict[str, Any] = dict(definition.suite.params)
    suite_context['_suite_name'] = definition.suite.name
    suite_context['_case_count'] = len(cases)

    if definition.hooks.suite_setup:
        setup_results = _run_hooks(
            definition.hooks.suite_setup, "suite_setup", suite_context,
        )
        suite_hook_results.extend(setup_results)

    suite_setup_failed = any(r.status != "pass" for r in suite_hook_results)
    results: list[CaseResult] = []

    def _emit(result: CaseResult, index: int) -> None:
        if on_progress is not None:
            on_progress(ProgressEvent(
                case_id=result.case_id,
                status=result.status,
                duration_ms=result.duration_ms,
                index=index,
                total=len(cases),
                is_fault=result.is_fault,
                flaky=result.flaky,
                retry_count=result.retry_count,
            ))

    try:
        if suite_setup_failed:
            logger.error("Suite setup failed; skipping all cases")
            for i, c in enumerate(cases):
                r = CaseResult(
                    case_id=c.case_id,
                    status="error",
                    hook_results=[HookResult(
                        hook_name="suite_setup_failed",
                        hook_type="suite_setup",
                        status="error",
                        error="Skipped due to suite_setup failure",
                    )],
                )
                results.append(r)
                _emit(r, i)
        elif workers == 1:
            for i, case in enumerate(cases):
                result = run_case_with_retries(
                    case, definition, timeout, graph=graph,
                    retries=retries, retry_delay=retry_delay,
                )
                results.append(result)
                _emit(result, i)
        else:
            runner = partial(
                run_case_with_retries, definition=definition, timeout=timeout,
                graph=graph, retries=retries, retry_delay=retry_delay,
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_index = {
                    pool.submit(runner, case): i
                    for i, case in enumerate(cases)
                }
                indexed_results: dict[int, CaseResult] = {}
                for future in as_completed(future_to_index):
                    i = future_to_index[future]
                    result = future.result()
                    indexed_results[i] = result
                    _emit(result, i)
                results = [indexed_results[i] for i in range(len(cases))]
    finally:
        if definition.hooks.suite_teardown:
            teardown_results = _run_hooks(
                definition.hooks.suite_teardown, "suite_teardown",
                {**suite_context, '_suite_setup_failed': suite_setup_failed},
            )
            suite_hook_results.extend(teardown_results)

    duration = (time.monotonic() - start) * 1000
    passed = sum(1 for r in results if r.status == "pass")
    logger.info("Run complete: %d/%d passed (%.0fms)", passed, len(results), duration)
    return results, suite_hook_results
