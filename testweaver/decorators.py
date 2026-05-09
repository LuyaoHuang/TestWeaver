"""Decorator-based operation definitions for TestWeaver.

Define test operations in Python with decorators instead of YAML:

    from testweaver import action, provides, requires, clears

    @action
    @provides('file.exists')
    def create_file(params):
        subprocess.run('echo hello > /tmp/test.txt', shell=True, check=True)

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
