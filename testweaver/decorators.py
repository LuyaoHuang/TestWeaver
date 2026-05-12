"""Decorator-based operation definitions for TestWeaver.

Define test operations in Python with decorators instead of YAML:

    from testweaver import action, provides, requires, clears, verify_for

    @action
    @provides('file.exists')
    def create_file(params):
        subprocess.run('echo hello > /tmp/test.txt', shell=True, check=True)

    @verify_for('create_file')
    def check_content(params):
        subprocess.run('grep -q hello /tmp/test.txt', shell=True, check=True)

    @check
    @requires('file.exists')
    def verify_file(params):
        subprocess.run('test -f /tmp/test.txt', shell=True, check=True)
"""
from __future__ import annotations

from typing import Callable


def _ensure_meta(func: Callable) -> dict:
    if not hasattr(func, '_tw_meta'):
        func._tw_meta = {}
    return func._tw_meta


def provides(*states: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('provides', []).extend(states)
        return func
    return decorator


def requires(*states: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('requires', []).extend(states)
        return func
    return decorator


def clears(*states: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('clears', []).extend(states)
        return func
    return decorator


def excludes(*states: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('excludes', []).extend(states)
        return func
    return decorator


def graft(src: str, tgt: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('grafts', []).append({'src': src, 'tgt': tgt})
        return func
    return decorator


def cut(*paths: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta.setdefault('cuts', []).extend(paths)
        return func
    return decorator


def _type_decorator(op_type: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        meta = _ensure_meta(func)
        meta['type'] = op_type
        return func
    return decorator


def action(func: Callable) -> Callable:
    return _type_decorator('action')(func)


def check(func: Callable) -> Callable:
    return _type_decorator('check')(func)


def setup(func: Callable) -> Callable:
    return _type_decorator('setup')(func)


def cleanup(func: Callable) -> Callable:
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
