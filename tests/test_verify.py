"""Tests for operation verify callbacks."""

from testweaver.engine import run_case
from testweaver.graph import generate_cases
from testweaver.schema import (
    Operation, TestSuite as Suite, TestDefinition as Defn, TestCase,
)


def _make_definition(operations, targets, **kwargs):
    return Defn(
        operations=operations,
        suite=Suite(name="test", targets=targets, **kwargs),
    )


# ---------------------------------------------------------------------------
# Callable verify
# ---------------------------------------------------------------------------

def test_verify_callable_passes():
    verify_log = []

    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None,
                  verify_callable=lambda *a: verify_log.append("verified")),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "pass"
    assert verify_log == ["verified"]

    setup_step = result.steps[0]
    assert setup_step.verify_result is not None
    assert setup_step.verify_result.status == "pass"
    assert setup_step.verify_result.observer_name == "verify_setup"


def test_verify_callable_fails():
    def bad_verify(params, env):
        raise AssertionError("verify failed")

    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None,
                  verify_callable=bad_verify),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "fail"

    setup_step = result.steps[0]
    assert setup_step.verify_result is not None
    assert setup_step.verify_result.status == "fail"
    assert "verify failed" in setup_step.verify_result.error


def test_verify_skipped_on_step_failure():
    verify_log = []

    def fail_step(params, env):
        raise RuntimeError("step failed")

    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=fail_step,
                  verify_callable=lambda *a: verify_log.append("should not run")),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "fail"
    assert verify_log == []
    assert result.steps[0].verify_result is None


def test_cleanup_runs_after_verify_failure():
    cleanup_log = []

    def bad_verify(params, env):
        raise AssertionError("verify failed")

    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None,
                  verify_callable=bad_verify),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready"],
                  callable=lambda *a: cleanup_log.append("cleaned")),
    ]
    defn = _make_definition(ops, ["check"])
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check",
                    cleanup_steps=["teardown"])
    result = run_case(case, defn)

    assert result.status == "fail"
    assert cleanup_log == ["cleaned"]


def test_no_verify_result_when_no_verify():
    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "pass"
    assert result.steps[0].verify_result is None


# ---------------------------------------------------------------------------
# Shell command verify
# ---------------------------------------------------------------------------

def test_verify_shell_passes():
    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  run="echo ok", verify="true"),
        Operation(name="check", type="check", requires=["ready"],
                  run="true"),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "pass"
    setup_step = result.steps[0]
    assert setup_step.verify_result is not None
    assert setup_step.verify_result.status == "pass"


def test_verify_shell_fails():
    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  run="echo ok", verify="false"),
        Operation(name="check", type="check", requires=["ready"],
                  run="true"),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "fail"
    setup_step = result.steps[0]
    assert setup_step.verify_result is not None
    assert setup_step.verify_result.status == "fail"


def test_verify_shell_with_param_substitution():
    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  run="echo ok", verify="test $greeting = hello"),
        Operation(name="check", type="check", requires=["ready"],
                  run="true"),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check",
                    params={"greeting": "hello"})
    result = run_case(case, defn)

    assert result.status == "pass"


# ---------------------------------------------------------------------------
# verify_for decorator via loader
# ---------------------------------------------------------------------------

def test_verify_for_decorator_loading():
    from testweaver.decorators import action, provides, verify_for

    @action
    @provides('file.exists')
    def create_file(params):
        pass

    @verify_for('create_file')
    def check_file(params):
        pass

    from testweaver.loader import extract_operations
    import types

    module = types.ModuleType("test_mod")
    module.create_file = create_file
    module.check_file = check_file

    ops = extract_operations(module)
    assert len(ops) == 1

    op, func = ops[0]
    assert op.name == "create_file"
    assert op.verify_callable is check_file
    assert func is create_file


# ---------------------------------------------------------------------------
# Integration: verify with modifiers
# ---------------------------------------------------------------------------

def test_verify_runs_before_modifiers():
    """Verify runs after step but the step still processes normally."""
    verify_log = []
    modifier_log = []

    from testweaver.modifiers import TransitionObserver

    def step_with_observer(params, env):
        modifier_log.append("modifier_returned")
        return TransitionObserver(
            watch_ops=["check"],
            verify=lambda p: None,
            name="obs",
        )

    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=step_with_observer,
                  verify_callable=lambda *a: verify_log.append("verified")),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["setup", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "pass"
    assert verify_log == ["verified"]
    assert modifier_log == ["modifier_returned"]
