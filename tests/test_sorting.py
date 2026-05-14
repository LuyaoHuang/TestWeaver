import pytest

from testweaver.schema import Operation, TestCase
from testweaver.sorting import SORT_STRATEGIES, sort_cases


def _case(case_id, target="check", steps=None, is_fault=False):
    return TestCase(
        case_id=case_id,
        target=target,
        steps=steps or [target],
        is_fault=is_fault,
    )


def _ops():
    return [
        Operation(name="setup_a", type="action", provides=["a"], priority=1),
        Operation(name="setup_b", type="action", provides=["b"], priority=5),
        Operation(name="check", type="check", requires=["a", "b"], priority=3),
        Operation(
            name="boom", type="fault", fault_for="check",
            requires=["a"], priority=0,
        ),
        Operation(
            name="teardown", type="cleanup", requires=["a"],
            clears=["a"], priority=2,
        ),
    ]


CASES = [
    _case("c1", steps=["setup_a", "setup_b", "check"]),            # 3 steps
    _case("c2", steps=["setup_a", "check"]),                       # 2 steps
    _case("c3", steps=["setup_a", "setup_b", "setup_a", "check"]), # 4 steps
    _case("f1", target="boom", steps=["setup_a", "boom"], is_fault=True),  # 2 steps, fault
]


def test_shortest():
    result = sort_cases(CASES, "shortest")
    assert [c.case_id for c in result] == ["c2", "f1", "c1", "c3"]


def test_longest():
    result = sort_cases(CASES, "longest")
    assert [c.case_id for c in result] == ["c3", "c1", "c2", "f1"]


def test_target_strategy():
    ops = _ops()
    result = sort_cases(CASES, "target", operations=ops)
    ids = [c.case_id for c in result]
    assert ids[0] == "c1" or ids[0] == "c2" or ids[0] == "c3"
    assert result[-1].case_id == "f1"
    for c in result:
        if c.target == "check":
            assert c.priority == 3.0
        elif c.target == "boom":
            assert c.priority == 0.0


def test_total_strategy():
    ops = _ops()
    result = sort_cases(CASES, "total", operations=ops)
    scores = {c.case_id: c.priority for c in result}
    assert scores["c1"] == 1 + 5 + 3  # setup_a(1) + setup_b(5) + check(3)
    assert scores["c2"] == 1 + 3      # setup_a(1) + check(3)
    assert scores["c3"] == 1 + 5 + 1 + 3  # setup_a + setup_b + setup_a + check
    assert scores["f1"] == 1 + 0      # setup_a(1) + boom(0)
    assert [c.case_id for c in result] == ["c3", "c1", "c2", "f1"]


def test_fault_first():
    result = sort_cases(CASES, "fault-first")
    assert result[0].case_id == "f1"
    assert all(not c.is_fault for c in result[1:])


def test_fault_last():
    result = sort_cases(CASES, "fault-last")
    assert result[-1].case_id == "f1"
    assert all(not c.is_fault for c in result[:-1])


def test_random_with_seed():
    r1 = sort_cases(CASES, "random", seed=42)
    r2 = sort_cases(CASES, "random", seed=42)
    assert [c.case_id for c in r1] == [c.case_id for c in r2]


def test_random_different_seeds():
    r1 = sort_cases(CASES, "random", seed=1)
    r2 = sort_cases(CASES, "random", seed=999)
    ids1 = [c.case_id for c in r1]
    ids2 = [c.case_id for c in r2]
    assert set(ids1) == set(ids2)


def test_does_not_mutate_input():
    original_ids = [c.case_id for c in CASES]
    sort_cases(CASES, "longest")
    assert [c.case_id for c in CASES] == original_ids


def test_empty_list():
    assert sort_cases([], "shortest") == []


def test_single_case():
    single = [_case("only")]
    result = sort_cases(single, "shortest")
    assert len(result) == 1
    assert result[0].case_id == "only"


def test_invalid_strategy_raises():
    with pytest.raises(ValueError, match="Unknown sort strategy"):
        sort_cases(CASES, "nonexistent")


def test_target_requires_operations():
    with pytest.raises(ValueError, match="'operations' is required"):
        sort_cases(CASES, "target")


def test_total_requires_operations():
    with pytest.raises(ValueError, match="'operations' is required"):
        sort_cases(CASES, "total")


def test_shortest_without_operations():
    result = sort_cases(CASES, "shortest")
    assert len(result) == len(CASES)


def test_fault_first_without_operations():
    result = sort_cases(CASES, "fault-first")
    assert result[0].is_fault


def test_priority_field_set_after_sort():
    ops = _ops()
    result = sort_cases(CASES, "target", operations=ops)
    for c in result:
        assert isinstance(c.priority, float)
        if c.target == "check":
            assert c.priority == 3.0


def test_all_strategies_valid():
    for strategy in SORT_STRATEGIES:
        if strategy in ("target", "total"):
            result = sort_cases(CASES, strategy, operations=_ops())
        else:
            result = sort_cases(CASES, strategy, seed=0)
        assert len(result) == len(CASES)
