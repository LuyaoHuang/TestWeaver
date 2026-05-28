import pytest

from testweaver.filtering import filter_cases
from testweaver.schema import Operation, TestCase


def _case(case_id, target="check", steps=None, is_fault=False, params=None, cleanup_steps=None):
    return TestCase(
        case_id=case_id,
        target=target,
        steps=steps or [target],
        is_fault=is_fault,
        params=params or {},
        cleanup_steps=cleanup_steps or [],
    )


def _ops_by_name(*ops: Operation):
    return {op.name: op for op in ops}


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


# --- Tag filtering tests ---

TAG_OPS = [
    Operation(name="start_vm", type="action", provides=["vm.active"], tags=["slow", "e2e"]),
    Operation(name="verify_vm", type="check", requires=["vm.active"], tags=["smoke", "fast"]),
    Operation(name="quick_setup", type="action", provides=["data.ready"], tags=["fast"]),
    Operation(name="verify_data", type="check", requires=["data.ready"], tags=["smoke", "fast"]),
    Operation(name="teardown", type="cleanup", clears=["vm.active"], tags=["slow"]),
    Operation(name="no_tags_op", type="action", provides=["other.state"], tags=[]),
    Operation(name="bare_check", type="check", requires=["other.state"], tags=[]),
]
TAG_OPS_BY_NAME = _ops_by_name(*TAG_OPS)

TAG_CASES = [
    _case("case-slow", target="verify_vm",
          steps=["start_vm", "verify_vm"], cleanup_steps=["teardown"]),
    _case("case-fast", target="verify_data",
          steps=["quick_setup", "verify_data"]),
    _case("case-mixed", target="verify_vm",
          steps=["start_vm", "quick_setup", "verify_vm", "verify_data"]),
    _case("case-untagged", target="bare_check",
          steps=["no_tags_op", "bare_check"]),
]


def test_tag_filter_single():
    result = filter_cases(TAG_CASES, tags=["smoke"], ops_by_name=TAG_OPS_BY_NAME)
    ids = [c.case_id for c in result]
    assert "case-slow" in ids
    assert "case-fast" in ids
    assert "case-mixed" in ids
    assert "case-untagged" not in ids
    assert len(result) == 3


def test_tag_filter_multiple_or():
    result = filter_cases(TAG_CASES, tags=["slow", "fast"], ops_by_name=TAG_OPS_BY_NAME)
    assert len(result) == 3  # all except case-untagged


def test_tag_filter_no_match():
    result = filter_cases(TAG_CASES, tags=["nonexistent"], ops_by_name=TAG_OPS_BY_NAME)
    assert result == []


def test_exclude_tags():
    result = filter_cases(TAG_CASES, exclude_tags=["slow"], ops_by_name=TAG_OPS_BY_NAME)
    ids = [c.case_id for c in result]
    assert "case-slow" not in ids
    assert "case-fast" in ids
    assert "case-mixed" not in ids  # has start_vm which is slow
    assert "case-untagged" in ids  # verify_data is smoke, not slow


def test_exclude_tags_multiple():
    result = filter_cases(TAG_CASES, exclude_tags=["slow", "fast"], ops_by_name=TAG_OPS_BY_NAME)
    ids = [c.case_id for c in result]
    assert ids == ["case-untagged"]


def test_tag_and_exclude_combined():
    result = filter_cases(
        TAG_CASES, tags=["smoke"], exclude_tags=["slow"],
        ops_by_name=TAG_OPS_BY_NAME,
    )
    ids = [c.case_id for c in result]
    assert "case-fast" in ids  # smoke via verify_data, no slow ops
    assert "case-slow" not in ids  # excluded by slow
    assert "case-mixed" not in ids  # excluded by slow


def test_tag_with_cleanup_steps():
    """Tag filtering includes cleanup steps when collecting tags."""
    result = filter_cases(TAG_CASES, exclude_tags=["slow"], ops_by_name=TAG_OPS_BY_NAME)
    # case-slow has teardown in cleanup_steps, which is tagged slow
    ids = [c.case_id for c in result]
    assert "case-slow" not in ids


def test_tag_filter_no_ops_by_name_raises():
    with pytest.raises(ValueError, match="ops_by_name"):
        filter_cases(TAG_CASES, tags=["smoke"])


def test_tag_filter_combined_with_other_filters():
    result = filter_cases(
        TAG_CASES, ids=["case-*"], tags=["smoke"], exclude_tags=["slow"],
        ops_by_name=TAG_OPS_BY_NAME,
    )
    ids = [c.case_id for c in result]
    assert "case-fast" in ids
    assert len(result) == 1
