import time
from unittest.mock import patch

from testweaver.engine import run_all, run_case
from testweaver.schema import (
    CaseResult,
    Operation,
    TestCase,
    TestDefinition,
    TestSuite,
)
from testweaver.graph import build_graph, generate_cases


def _simple_definition():
    ops = [
        Operation(name="setup", type="setup", provides=["ready"], run="true"),
        Operation(name="work", type="action", requires=["ready"], provides=["done"], run="true"),
        Operation(name="check", type="check", requires=["done"], run="true"),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready", "done"], run="true"),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="parallel_test", targets=["check"]),
    )


def _slow_definition(delay: float = 0.1):
    ops = [
        Operation(name="setup", type="setup", provides=["ready"], run=f"sleep {delay}"),
        Operation(name="check", type="check", requires=["ready"], run="true"),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"], run="true"),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="slow_test", targets=["check"]),
    )


def test_workers_1_matches_sequential():
    defn = _simple_definition()
    cases = generate_cases(defn)
    assert len(cases) >= 1

    sequential, _ = run_all(cases, defn, timeout=10, workers=1)
    parallel, _ = run_all(cases, defn, timeout=10, workers=2)

    assert len(sequential) == len(parallel)
    for s, p in zip(sequential, parallel):
        assert s.case_id == p.case_id
        assert s.status == p.status


def test_parallel_workers_2():
    defn = _simple_definition()
    cases = generate_cases(defn)
    results, _ = run_all(cases, defn, timeout=10, workers=2)
    assert all(r.status == "pass" for r in results)


def test_workers_0_auto_detects():
    defn = _simple_definition()
    cases = generate_cases(defn)
    results, _ = run_all(cases, defn, timeout=10, workers=0)
    assert len(results) == len(cases)
    assert all(r.status == "pass" for r in results)


def test_parallel_preserves_order():
    defn = _simple_definition()
    cases = generate_cases(defn)
    results, _ = run_all(cases, defn, timeout=10, workers=2)
    for case, result in zip(cases, results):
        assert case.case_id == result.case_id


def test_parallel_faster_than_sequential():
    defn = _slow_definition(delay=0.15)
    cases = generate_cases(defn)
    if len(cases) < 2:
        cases = cases * 4

    start = time.monotonic()
    run_all(cases, defn, timeout=10, workers=1)  # noqa: result unused
    sequential_time = time.monotonic() - start

    start = time.monotonic()
    run_all(cases, defn, timeout=10, workers=4)  # noqa: result unused
    parallel_time = time.monotonic() - start

    assert parallel_time < sequential_time


def test_parallel_with_callables():
    def do_setup(params, env):
        pass

    def do_check(params, env):
        pass

    def do_teardown(params, env):
        pass

    ops = [
        Operation(name="setup", type="setup", provides=["ready"], callable=do_setup),
        Operation(name="check", type="check", requires=["ready"], callable=do_check),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"], callable=do_teardown),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="callable_test", targets=["check"]),
    )
    cases = generate_cases(defn)
    results, _ = run_all(cases, defn, timeout=10, workers=2)
    assert all(r.status == "pass" for r in results)


def test_parallel_with_graph_replan():
    defn = _simple_definition()
    graph = build_graph(defn.operations)
    cases = generate_cases(defn, graph)
    results, _ = run_all(cases, defn, timeout=10, graph=graph, workers=2)
    assert len(results) == len(cases)
    assert all(r.status == "pass" for r in results)
