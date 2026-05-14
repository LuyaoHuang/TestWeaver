import signal
import textwrap
import time

import pytest

from testweaver.decorators import action, check, cleanup, provides, requires, clears, timeout
from testweaver.engine import _run_callable, run_all, run_step
from testweaver.loader import load_module, extract_operations
from testweaver.schema import (
    Operation,
    StepResult,
    TestCase,
    TestDefinition,
    TestSuite,
    load_definition,
)
from testweaver.graph import build_graph, generate_cases


# --- Decorator metadata tests ---


def test_timeout_decorator():
    @timeout(600)
    def my_op(params):
        pass
    assert my_op._tw_meta['timeout'] == 600


def test_timeout_with_other_decorators():
    @action
    @provides('vm.active')
    @timeout(600)
    def boot_vm(params):
        pass
    meta = boot_vm._tw_meta
    assert meta['type'] == 'action'
    assert meta['provides'] == ['vm.active']
    assert meta['timeout'] == 600


def test_no_timeout_decorator():
    @action
    @provides('ready')
    def my_op(params):
        pass
    assert 'timeout' not in my_op._tw_meta


# --- Loader tests ---


def _write_module(tmp_path, filename, code):
    p = tmp_path / filename
    p.write_text(textwrap.dedent(code))
    return p


def test_loader_extracts_timeout(tmp_path):
    mod_file = _write_module(tmp_path, "ops.py", """\
        from testweaver import action, provides, timeout

        @action
        @provides('ready')
        @timeout(60)
        def fast_op(params):
            pass
    """)
    module = load_module(mod_file)
    op_pairs = extract_operations(module)
    assert len(op_pairs) == 1
    op, _ = op_pairs[0]
    assert op.timeout == 60


def test_loader_no_timeout_is_none(tmp_path):
    mod_file = _write_module(tmp_path, "ops.py", """\
        from testweaver import action, provides

        @action
        @provides('ready')
        def normal_op(params):
            pass
    """)
    module = load_module(mod_file)
    op_pairs = extract_operations(module)
    assert len(op_pairs) == 1
    op, _ = op_pairs[0]
    assert op.timeout is None


# --- YAML timeout field ---


def test_yaml_timeout_field(tmp_path):
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        operations:
          - name: boot_vm
            type: action
            provides: [vm.active]
            timeout: 600
            run: "echo boot"
          - name: check_vm
            type: check
            requires: [vm.active]
            run: "echo ok"
          - name: stop_vm
            type: cleanup
            requires: [vm.active]
            clears: [vm.active]
            run: "echo stop"

        suite:
          name: "timeout_test"
          targets: [check_vm]
          cleanup: true
    """))
    defn = load_definition(yaml_file)
    boot_op = next(op for op in defn.operations if op.name == "boot_vm")
    assert boot_op.timeout == 600
    check_op = next(op for op in defn.operations if op.name == "check_vm")
    assert check_op.timeout is None


# --- Operation model ---


def test_operation_timeout_default():
    op = Operation(name="test", type="action", provides=["x"])
    assert op.timeout is None


def test_operation_timeout_set():
    op = Operation(name="test", type="action", provides=["x"], timeout=120)
    assert op.timeout == 120


# --- Engine: _run_callable timeout ---


def test_run_callable_succeeds_within_timeout():
    def fast_func(params):
        return "ok"
    ok, stdout, stderr, ret = _run_callable(fast_func, {}, timeout=5)
    assert ok is True
    assert ret == "ok"


def test_run_callable_timeout_enforced():
    def slow_func(params):
        time.sleep(10)
    start = time.monotonic()
    ok, stdout, stderr, ret = _run_callable(slow_func, {}, timeout=1)
    elapsed = time.monotonic() - start
    assert ok is False
    assert "timed out" in stderr.lower()
    assert elapsed < 5


def test_run_callable_exception_still_caught():
    def bad_func(params):
        raise ValueError("broken")
    ok, stdout, stderr, ret = _run_callable(bad_func, {}, timeout=5)
    assert ok is False
    assert "broken" in stderr


# --- Engine: per-step timeout resolution ---


def test_per_step_timeout_overrides_global():
    """Operation with timeout=1 should time out even when global is 300."""
    def slow_action(params):
        time.sleep(10)

    ops = [
        Operation(name="setup", type="setup", provides=["ready"],
                  callable=lambda p: None),
        Operation(name="slow", type="action", requires=["ready"],
                  provides=["done"], callable=slow_action, timeout=1),
        Operation(name="check", type="check", requires=["done"],
                  callable=lambda p: None),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready", "done"], callable=lambda p: None),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="timeout_test", targets=["check"]),
    )
    graph = build_graph(defn.operations)
    cases = generate_cases(defn, graph)
    assert len(cases) >= 1

    results, _ = run_all(cases, defn, timeout=300, graph=graph)
    slow_steps = [
        s for r in results for s in r.steps
        if s.operation == "slow"
    ]
    assert len(slow_steps) >= 1
    assert slow_steps[0].status == "fail"
    assert "timed out" in slow_steps[0].error.lower()


def test_global_timeout_used_when_no_per_step():
    """Operation without timeout= uses the global timeout and succeeds."""
    ops = [
        Operation(name="setup", type="setup", provides=["ready"],
                  callable=lambda p: None),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda p: None),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready"], callable=lambda p: None),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="pass_test", targets=["check"]),
    )
    graph = build_graph(defn.operations)
    cases = generate_cases(defn, graph)
    results, _ = run_all(cases, defn, timeout=300, graph=graph)
    assert all(r.status == "pass" for r in results)


# --- Backward compatibility ---


def test_backward_compat_no_timeout_anywhere():
    """Existing definitions without any timeout field work identically."""
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="compat_test", targets=["check"]),
    )
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].steps == ["setup", "check"]
