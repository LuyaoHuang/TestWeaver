from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from .log import get_logger
from .schema import TestCase

logger = get_logger(__name__)


def filter_cases(
    cases: list[TestCase],
    *,
    ids: list[str] | None = None,
    targets: list[str] | None = None,
    steps: list[str] | None = None,
    fault_only: bool = False,
    no_fault: bool = False,
    params: dict[str, str] | None = None,
) -> list[TestCase]:
    """Filter generated test cases by the given criteria.

    All criteria are AND-combined: a case must satisfy every specified
    filter.  Within list-valued filters (*ids*, *targets*, *steps*),
    matching is OR: the case must match at least one entry.

    Args:
        cases: Test cases to filter.
        ids: fnmatch glob patterns matched against ``case_id``.
        targets: Exact target operation names.
        steps: Operation names that must appear in the case's step list.
        fault_only: Keep only fault-injection cases.
        no_fault: Exclude fault-injection cases.
        params: Key/value pairs that must all appear in the case's params.

    Returns:
        The subset of *cases* matching all criteria.

    Raises:
        ValueError: If *fault_only* and *no_fault* are both True.
    """
    if fault_only and no_fault:
        raise ValueError("fault_only and no_fault are mutually exclusive")

    logger.debug(
        "Filtering %d case(s): ids=%s targets=%s steps=%s fault_only=%s no_fault=%s params=%s",
        len(cases), ids, targets, steps, fault_only, no_fault, params,
    )

    result: list[TestCase] = []
    for case in cases:
        if fault_only and not case.is_fault:
            continue
        if no_fault and case.is_fault:
            continue

        if ids and not any(fnmatch(case.case_id, pat) for pat in ids):
            continue

        if targets and case.target not in targets:
            continue

        if steps and not any(s in case.steps for s in steps):
            continue

        if params:
            match = True
            for k, v in params.items():
                if str(case.params.get(k)) != v:
                    match = False
                    break
            if not match:
                continue

        result.append(case)
    logger.debug("Filtered: %d/%d case(s) matched", len(result), len(cases))
    return result
