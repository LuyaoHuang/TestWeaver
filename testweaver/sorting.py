"""Sort generated test cases by configurable strategies."""
from __future__ import annotations

import random as _random

from .log import get_logger
from .schema import Operation, TestCase

logger = get_logger(__name__)

SORT_STRATEGIES = (
    "shortest",
    "longest",
    "target",
    "total",
    "fault-first",
    "fault-last",
    "random",
)


def _build_ops_map(operations: list[Operation]) -> dict[str, Operation]:
    return {op.name: op for op in operations}


def _require_operations(
    operations: list[Operation] | None,
    strategy: str,
) -> dict[str, Operation]:
    if operations is None:
        raise ValueError(
            f"'operations' is required for strategy '{strategy}'"
        )
    return _build_ops_map(operations)


def sort_cases(
    cases: list[TestCase],
    strategy: str,
    *,
    operations: list[Operation] | None = None,
    seed: int | None = None,
) -> list[TestCase]:
    """Sort test cases according to the given strategy.

    Returns a new list; the original is not modified.  Each returned
    case has its ``priority`` field set to the computed score (except
    for the ``random`` strategy, which leaves it at 0.0).

    Args:
        cases: Test cases to sort.
        strategy: One of :data:`SORT_STRATEGIES`.
        operations: Operation definitions (required for ``target``
            and ``total`` strategies).
        seed: Random seed for the ``random`` strategy.

    Raises:
        ValueError: If *strategy* is unknown or *operations* is
            missing when required.
    """
    if strategy not in SORT_STRATEGIES:
        raise ValueError(
            f"Unknown sort strategy '{strategy}'. "
            f"Available: {', '.join(SORT_STRATEGIES)}"
        )

    logger.debug("Sorting %d case(s) by strategy=%s (seed=%s)", len(cases), strategy, seed)

    if strategy == "shortest":
        scored = [(len(c.steps), c) for c in cases]
        scored.sort(key=lambda t: t[0])
    elif strategy == "longest":
        scored = [(len(c.steps), c) for c in cases]
        scored.sort(key=lambda t: t[0], reverse=True)
    elif strategy == "target":
        ops_map = _require_operations(operations, strategy)
        scored = [
            (ops_map[c.target].priority if c.target in ops_map else 0, c)
            for c in cases
        ]
        scored.sort(key=lambda t: t[0], reverse=True)
    elif strategy == "total":
        ops_map = _require_operations(operations, strategy)
        scored = [
            (
                sum(ops_map[s].priority for s in c.steps if s in ops_map),
                c,
            )
            for c in cases
        ]
        scored.sort(key=lambda t: t[0], reverse=True)
    elif strategy == "fault-first":
        scored = [(0 if c.is_fault else 1, c) for c in cases]
        scored.sort(key=lambda t: t[0])
    elif strategy == "fault-last":
        scored = [(1 if c.is_fault else 0, c) for c in cases]
        scored.sort(key=lambda t: t[0])
    else:
        result = list(cases)
        rng = _random.Random(seed)
        rng.shuffle(result)
        return result

    result = []
    for score, case in scored:
        copy = case.model_copy(update={"priority": float(score)})
        result.append(copy)
    logger.info("Sorted %d case(s): %s", len(result), [c.case_id for c in result[:3]])
    return result
