from __future__ import annotations

from itertools import product as cartesian_product
from typing import Any

from .schema import Operation, ParamConstraint, ParamMatrix


def _constraint_matches(
    constraint: ParamConstraint,
    combination: dict[str, Any],
) -> bool:
    """Check whether a constraint's when-clause matches a parameter combination."""
    for key, expected in constraint.when.items():
        actual = combination.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        else:
            if actual != expected:
                return False
    return True


def expand_matrix(matrix: ParamMatrix) -> list[dict[str, Any]]:
    """Expand a parameter matrix into all valid combinations.

    Computes the Cartesian product of all axes, then removes any
    combinations excluded by constraints.

    Args:
        matrix: Parameter matrix with axes and optional constraints.

    Returns:
        List of parameter dicts, one per valid combination.
    """
    if not matrix.axes:
        return [{}]

    names = [axis.name for axis in matrix.axes]
    value_lists = [axis.values for axis in matrix.axes]

    result = []
    for values in cartesian_product(*value_lists):
        combo = dict(zip(names, values))
        excluded = any(
            c.exclude and _constraint_matches(c, combo)
            for c in matrix.constraints
        )
        if not excluded:
            result.append(combo)

    return result


def get_skip_ops(
    combination: dict[str, Any],
    constraints: list[ParamConstraint],
    operations: list[Operation] | None = None,
) -> set[str]:
    """Determine which operations to skip for a given parameter combination.

    Args:
        combination: Current parameter values.
        constraints: Matrix-level constraints with ``skip_ops``.
        operations: Operations with per-operation ``skip_when`` rules.

    Returns:
        Set of operation names to skip.
    """
    skip: set[str] = set()
    for c in constraints:
        if _constraint_matches(c, combination):
            skip.update(c.skip_ops)
    if operations:
        for op in operations:
            for cond in op.skip_when:
                if all(combination.get(k) == v for k, v in cond.items()):
                    skip.add(op.name)
    return skip
