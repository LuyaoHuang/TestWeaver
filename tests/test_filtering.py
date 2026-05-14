import pytest

from testweaver.filtering import filter_cases
from testweaver.schema import TestCase


def _case(case_id, target="check", steps=None, is_fault=False, params=None):
    return TestCase(
        case_id=case_id,
        target=target,
        steps=steps or [target],
        is_fault=is_fault,
        params=params or {},
    )


CASES = [
    _case("check-1", target="check", steps=["setup", "check"]),
    _case("check-2", target="check", steps=["alt_setup", "check"]),
    _case("verify-1", target="verify", steps=["setup", "verify"]),
    _case("fault-boom-1", target="boom", steps=["setup", "boom"], is_fault=True),
    _case("check-1-mode=fast", target="check", steps=["setup", "check"],
          params={"mode": "fast"}),
]


def test_no_filters_returns_all():
    assert filter_cases(CASES) == CASES


def test_filter_by_id_exact():
    result = filter_cases(CASES, ids=["check-1"])
    assert [c.case_id for c in result] == ["check-1"]


def test_filter_by_id_glob():
    result = filter_cases(CASES, ids=["check-*"])
    assert [c.case_id for c in result] == ["check-1", "check-2", "check-1-mode=fast"]


def test_filter_by_multiple_id_patterns():
    result = filter_cases(CASES, ids=["check-1", "verify-*"])
    assert [c.case_id for c in result] == ["check-1", "verify-1"]


def test_filter_by_target():
    result = filter_cases(CASES, targets=["verify"])
    assert [c.case_id for c in result] == ["verify-1"]


def test_filter_by_multiple_targets():
    result = filter_cases(CASES, targets=["check", "boom"])
    ids = [c.case_id for c in result]
    assert "check-1" in ids
    assert "fault-boom-1" in ids
    assert "verify-1" not in ids


def test_filter_by_step():
    result = filter_cases(CASES, steps=["alt_setup"])
    assert [c.case_id for c in result] == ["check-2"]


def test_filter_by_step_or():
    result = filter_cases(CASES, steps=["alt_setup", "boom"])
    assert len(result) == 2


def test_fault_only():
    result = filter_cases(CASES, fault_only=True)
    assert all(c.is_fault for c in result)
    assert len(result) == 1


def test_no_fault():
    result = filter_cases(CASES, no_fault=True)
    assert not any(c.is_fault for c in result)
    assert len(result) == 4


def test_fault_only_and_no_fault_raises():
    with pytest.raises(ValueError, match="mutually exclusive"):
        filter_cases(CASES, fault_only=True, no_fault=True)


def test_filter_by_params():
    result = filter_cases(CASES, params={"mode": "fast"})
    assert [c.case_id for c in result] == ["check-1-mode=fast"]


def test_combined_filters():
    result = filter_cases(CASES, ids=["check-*"], targets=["check"], no_fault=True)
    ids = [c.case_id for c in result]
    assert "check-1" in ids
    assert "check-2" in ids
    assert "verify-1" not in ids
    assert "fault-boom-1" not in ids


def test_no_matches_returns_empty():
    result = filter_cases(CASES, ids=["nonexistent-*"])
    assert result == []


def test_empty_input():
    assert filter_cases([]) == []
    assert filter_cases([], ids=["*"]) == []
