"""Graph modifiers: runtime objects that alter execution flow.

Three modifier types let callable operations influence future steps:

- EdgeGuard: blocks a state transition, forcing replan
- TransientHook: injects a one-shot step before a matching operation
- TransitionObserver: runs verification after matching state transitions
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EdgeGuard:
    """Block a future operation, forcing the runner to replan.

    Returned by a callable operation when it discovers that a future
    operation is now invalid due to runtime state.
    """
    blocked_op: str
    reason: str = ""


@dataclass
class TransientHook:
    """Inject a one-shot step before a matching future operation.

    Fires once when the runner is about to execute ``before_op``,
    then auto-removes.
    """
    before_op: str
    action: Callable[[dict[str, Any]], None]
    name: str = ""
    reason: str = ""


@dataclass
class TransitionObserver:
    """Persistent verification callback for matching operations.

    Runs ``verify`` after every execution of an operation whose name
    appears in ``watch_ops``, for the remainder of the case.
    """
    watch_ops: list[str]
    verify: Callable[[dict[str, Any]], None]
    name: str = ""
    reason: str = ""


#: Union type for all graph modifier kinds.
GraphModifier = EdgeGuard | TransientHook | TransitionObserver
