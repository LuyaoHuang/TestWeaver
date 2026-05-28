"""Decorator-based operation definitions for TestWeaver.

Define test operations in Python with decorators instead of YAML:

    from testweaver import action, provides, requires, clears, verify_for

    @action
    @provides('file.exists')
    def create_file(params, env):
        subprocess.run('echo hello > /tmp/test.txt', shell=True, check=True)

    @verify_for('create_file')
    def check_content(params, env):
        subprocess.run('grep -q hello /tmp/test.txt', shell=True, check=True)

    @check
    @requires('file.exists')
    def verify_file(params, env):
        subprocess.run('test -f /tmp/test.txt', shell=True, check=True)
"""
from __future__ import annotations

from typing import Any, Callable

from .log import get_logger

logger = get_logger(__name__)


def _ensure_meta(func: Callable) -> dict[str, Any]:
    """Get or create the ``_tw_meta`` metadata dict on a function."""
    if not hasattr(func, '_tw_meta'):
        func._tw_meta = {}
    return func._tw_meta


def provides(*states: str) -> Callable:
    """Mark states that this operation activates on success."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('provides', []).extend(states)
        return func
    return decorator


def requires(*states: str) -> Callable:
    """Mark states that must be active before this operation runs."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('requires', []).extend(states)
        return func
    return decorator


def clears(*states: str) -> Callable:
    """Mark states that this operation deactivates."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('clears', []).extend(states)
        return func
    return decorator


def excludes(*states: str) -> Callable:
    """Mark states that must not be active for this operation to run."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('excludes', []).extend(states)
        return func
    return decorator


def graft(src: str, tgt: str) -> Callable:
    """Copy state subtree from *src* to *tgt* after execution."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('grafts', []).append({'src': src, 'tgt': tgt})
        return func
    return decorator


def cut(*paths: str) -> Callable:
    """Remove state subtrees at the given paths after execution."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('cuts', []).extend(paths)
        return func
    return decorator


def timeout(seconds: int) -> Callable:
    """Set a per-operation timeout in seconds, overriding the global default."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta['timeout'] = seconds
        return func
    return decorator


def priority(level: int) -> Callable:
    """Set a priority level for this operation. Higher values = more important."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta['priority'] = level
        return func
    return decorator


def _type_decorator(op_type: str) -> Callable:
    """Create a decorator that sets the operation type."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta['type'] = op_type
        return func
    return decorator


def action(func: Callable) -> Callable:
    """Mark a function as an action operation."""
    return _type_decorator('action')(func)


def check(func: Callable) -> Callable:
    """Mark a function as a check (target) operation."""
    return _type_decorator('check')(func)


def setup(func: Callable) -> Callable:
    """Mark a function as a setup operation."""
    return _type_decorator('setup')(func)


def cleanup(func: Callable) -> Callable:
    """Mark a function as a cleanup operation."""
    return _type_decorator('cleanup')(func)


def _safe_val(value: Any) -> str:
    return str(value).replace('.', '_')


def when_param(param_name: str, value: Any) -> Callable:
    """Require a specific parameter value (Approach 1: params as state)."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        state = f"params.{param_name}.{_safe_val(value)}"
        meta.setdefault('requires', []).append(state)
        return func
    return decorator


def unless_param(param_name: str, value: Any) -> Callable:
    """Exclude when a specific parameter value is set (Approach 1: params as state)."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        state = f"params.{param_name}.{_safe_val(value)}"
        meta.setdefault('excludes', []).append(state)
        return func
    return decorator


def verify_for(operation_name: str) -> Callable:
    """Attach this function as a verify callback for the named operation."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta['verify_for'] = operation_name
        return func
    return decorator


def skip_when(**conditions: Any) -> Callable:
    """Skip this operation when parameter conditions match (Approach 2: matrix)."""
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('skip_when', []).append(conditions)
        return func
    return decorator


def suite_setup(func: Callable) -> Callable:
    """Mark a function to run once before all test cases."""
    meta = _ensure_meta(func)
    meta['hook'] = 'suite_setup'
    return func


def suite_teardown(func: Callable) -> Callable:
    """Mark a function to run once after all test cases."""
    meta = _ensure_meta(func)
    meta['hook'] = 'suite_teardown'
    return func


def case_setup(func: Callable) -> Callable:
    """Mark a function to run before each test case."""
    meta = _ensure_meta(func)
    meta['hook'] = 'case_setup'
    return func


def case_teardown(func: Callable) -> Callable:
    """Mark a function to run after each test case."""
    meta = _ensure_meta(func)
    meta['hook'] = 'case_teardown'
    return func


def fault_for(operation_name: str, *, terminal: bool = True) -> Callable:
    """Declare this function as a fault scenario for the named operation.

    The decorated function runs instead of the target operation when the
    fault's extra conditions (requires/excludes) are met.  The framework
    auto-generates test cases that reach those conditions.
    """
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta['fault_for'] = operation_name
        meta['type'] = 'fault'
        meta['terminal'] = terminal
        return func
    return decorator


def tag(*tags: str) -> Callable:
    """Attach metadata tags to an operation for suite-level filtering.

    Tags are strings like ``"smoke"``, ``"regression"``, ``"slow"``.
    Use ``filter_tags`` / ``exclude_tags`` in the suite definition to
    control which cases run based on their operations' tags.

    Usage::

        @tag("smoke", "fast")
        @check
        @requires('vm.active')
        def verify_vm(params, env): ...
    """
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('tags', []).extend(tags)
        return func
    return decorator


def params_require(*keys: str | tuple) -> Callable:
    """Require specific params keys (and optionally values) for this operation.

    Operations that don't meet their params requirements are filtered out
    before graph generation.  Use together with ``@custom_params`` to
    dynamically detect the environment and constrain the test graph.

    **Key-existence check** (string)::

        @params_require('kvm_available', 'arch')
        @check
        @requires('vm.active')
        def verify_vm(params, env): ...

    **Exact-value check** (3-tuple)::

        @params_require(('cgroup_version', '=', 2))
        @action
        @provides('cgroup.configured')
        def configure_cgroup_v2(params, env): ...

    All conditions must be satisfied for the operation to be included.
    """
    parsed = []
    for key in keys:
        if isinstance(key, str):
            parsed.append((key, None, None))
        elif isinstance(key, tuple) and len(key) == 3:
            parsed.append((key[0], key[1], key[2]))
        else:
            raise TypeError(
                f"params_require expects str or 3-tuple, got {type(key)}"
            )

    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('params_require', []).extend(parsed)
        return func
    return decorator


def custom_params(func: Callable) -> Callable:
    """Mark a function to transform suite params before test case generation.

    The decorated function receives the suite params dict, modifies it
    (typically based on environment detection), and returns it.  It runs
    after module loading but before graph building and case generation.

    Usage::

        @custom_params
        def detect_environment(params):
            params['arch'] = platform.machine()
            return params
    """
    meta = _ensure_meta(func)
    meta['custom_params'] = True
    return func


def state_data(*args: Any, **kwargs: Any) -> Any:
    """Create a :class:`StateData` object to return from an operation callable.

    The engine applies the values to ``Env`` nodes and records them on
    the ``StepResult`` for framework-level tracking.  Two conventions:

    **Explicit path mapping** (single dict)::

        return state_data({'vm.active': {'uuid': 'abc'}})

    **Keyword convenience** — auto-mapped to the operation's single
    ``provides`` path::

        # @provides('vm.active')
        return state_data(uuid='abc', ip='10.0.0.1')
    """
    from .schema import StateData

    if args and isinstance(args[0], dict):
        return StateData(values=args[0])
    if kwargs:
        return StateData(values=kwargs)
    raise TypeError(
        "state_data() requires either a dict argument or keyword arguments"
    )
