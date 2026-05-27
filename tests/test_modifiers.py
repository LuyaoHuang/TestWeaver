"""Tests for graph modifiers: EdgeGuard, TransientHook, TransitionObserver."""

from testweaver.graph import build_graph, generate_cases
from testweaver.engine import run_step, run_case, run_all
from testweaver.modifiers import EdgeGuard, TransientHook, TransitionObserver
from testweaver.schema import (
    Operation, TestSuite as Suite, TestDefinition as Defn, TestCase,
)


def _make_definition(operations, targets, **kwargs):
    return Defn(
        operations=operations,
        suite=Suite(name="test", targets=targets, **kwargs),
    )


# ---------------------------------------------------------------------------
# Modifier dataclass construction
# ---------------------------------------------------------------------------

def test_edge_guard_creation():
    g = EdgeGuard(blocked_op="start_vm", reason="hugepages disabled")
    assert g.blocked_op == "start_vm"
    assert g.reason == "hugepages disabled"


def test_edge_guard_defaults():
    g = EdgeGuard(blocked_op="x")
    assert g.reason == ""


def test_transient_hook_creation():
    called = []
    h = TransientHook(
        before_op="step2",
        action=lambda p: called.append(1),
        name="restart",
        reason="need restart",
    )
    assert h.before_op == "step2"
    assert h.name == "restart"
    h.action({})
    assert called == [1]


def test_transition_observer_creation():
    called = []
    o = TransitionObserver(
        watch_ops=["attach", "detach"],
        verify=lambda p: called.append(1),
        name="audit",
    )
    assert o.watch_ops == ["attach", "detach"]
    o.verify({})
    assert called == [1]


# ---------------------------------------------------------------------------
# run_step returns modifiers
# ---------------------------------------------------------------------------

def test_run_step_shell_returns_no_modifier():
    from testweaver.env import Env
    op = Operation(name="echo", type="action", provides=["x"], run="echo ok")
    result, modifier = run_step(op, {}, Env())
    assert result.status == "pass"
    assert modifier is None


def test_run_step_callable_no_return():
    from testweaver.env import Env
    op = Operation(name="noop", type="action", provides=["x"],
                   callable=lambda *a: None)
    result, modifier = run_step(op, {}, Env())
    assert result.status == "pass"
    assert modifier is None


def test_run_step_callable_returns_edge_guard():
    from testweaver.env import Env
    def my_op(params, env):
        return EdgeGuard(blocked_op="bad_step", reason="blocked")

    op = Operation(name="setup", type="action", provides=["x"], callable=my_op)
    result, modifier = run_step(op, {}, Env())
    assert result.status == "pass"
    assert isinstance(modifier, EdgeGuard)
    assert modifier.blocked_op == "bad_step"
    assert result.modifier_type == "edge_guard"


def test_run_step_callable_returns_transient_hook():
    from testweaver.env import Env
    def my_op(params, env):
        return TransientHook(before_op="next", action=lambda p: None, name="hook1")

    op = Operation(name="setup", type="action", provides=["x"], callable=my_op)
    result, modifier = run_step(op, {}, Env())
    assert isinstance(modifier, TransientHook)
    assert result.modifier_type == "transient_hook"


def test_run_step_callable_returns_observer():
    from testweaver.env import Env
    def my_op(params, env):
        return TransitionObserver(watch_ops=["a"], verify=lambda p: None, name="obs1")

    op = Operation(name="setup", type="action", provides=["x"], callable=my_op)
    result, modifier = run_step(op, {}, Env())
    assert isinstance(modifier, TransitionObserver)
    assert result.modifier_type == "transition_observer"


def test_run_step_callable_non_modifier_return_ignored():
    from testweaver.env import Env
    op = Operation(name="setup", type="action", provides=["x"],
                   callable=lambda *a: "some string")
    result, modifier = run_step(op, {}, Env())
    assert result.status == "pass"
    assert modifier is None


def test_run_step_callable_failure_no_modifier():
    from testweaver.env import Env
    def fail_op(params, env):
        raise RuntimeError("boom")

    op = Operation(name="fail", type="action", provides=["x"], callable=fail_op)
    result, modifier = run_step(op, {}, Env())
    assert result.status == "fail"
    assert modifier is None


# ---------------------------------------------------------------------------
# run_case backward compat (no modifiers)
# ---------------------------------------------------------------------------

def test_run_case_no_modifiers_works():
    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready"], callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    assert len(cases) == 1

    result = run_case(cases[0], defn)
    assert result.status == "pass"
    assert result.replanned is False
    assert len(result.steps) == 3  # setup + check + teardown


# ---------------------------------------------------------------------------
# EdgeGuard: replanning
# ---------------------------------------------------------------------------

def test_edge_guard_triggers_replan():
    """Step1 provides two paths. config_bad blocks path_a, so replan picks path_b."""
    ops = [
        Operation(name="config_bad", type="action", provides=["configured"],
                  excludes=["configured"],
                  callable=lambda *a: EdgeGuard(blocked_op="path_a", reason="bad config")),
        Operation(name="path_a", type="action", provides=["ready"],
                  requires=["configured"], excludes=["ready"]),
        Operation(name="path_b", type="action", provides=["ready"],
                  requires=["configured"], excludes=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="clean_ready", type="cleanup", requires=["ready"],
                  clears=["ready"]),
        Operation(name="clean_config", type="cleanup", requires=["configured"],
                  clears=["configured"]),
    ]
    defn = _make_definition(ops, ["check"])
    graph = build_graph(ops)
    cases = generate_cases(defn, graph)

    # Find the case that uses path_a
    path_a_case = None
    for c in cases:
        if "path_a" in c.steps:
            path_a_case = c
            break
    assert path_a_case is not None

    result = run_case(path_a_case, defn, graph=graph)
    assert result.replanned is True
    assert result.status == "pass"
    # After replan, path_b should be used instead of path_a
    step_names = [s.operation for s in result.steps if not s.injected]
    assert "path_a" not in step_names
    assert "path_b" in step_names


def test_edge_guard_no_graph_errors():
    """EdgeGuard without a graph causes error status."""
    ops = [
        Operation(name="config", type="action", provides=["configured"],
                  callable=lambda *a: EdgeGuard(blocked_op="use_it")),
        Operation(name="use_it", type="action", provides=["ready"],
                  requires=["configured"]),
        Operation(name="check", type="check", requires=["ready"]),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(
        case_id="test-1",
        steps=["config", "use_it", "check"],
        target="check",
    )
    result = run_case(case, defn, graph=None)
    assert result.status == "error"
    blocked_step = [s for s in result.steps if s.operation == "use_it"]
    assert len(blocked_step) == 1
    assert "blocked" in blocked_step[0].error.lower()


def test_edge_guard_no_alternative_path():
    """EdgeGuard blocks the only path; replan fails."""
    ops = [
        Operation(name="config", type="action", provides=["configured"],
                  callable=lambda *a: EdgeGuard(blocked_op="only_path")),
        Operation(name="only_path", type="action", provides=["ready"],
                  requires=["configured"]),
        Operation(name="check", type="check", requires=["ready"]),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    graph = build_graph(ops)
    case = TestCase(
        case_id="test-1",
        steps=["config", "only_path", "check"],
        target="check",
    )
    result = run_case(case, defn, graph=graph)
    assert result.status == "error"
    assert result.replanned is False


# ---------------------------------------------------------------------------
# TransientHook
# ---------------------------------------------------------------------------

def test_transient_hook_fires_before_target():
    """Hook fires before the named operation."""
    hook_log = []

    def step1(params, env):
        return TransientHook(
            before_op="step2",
            action=lambda p: hook_log.append("hook_fired"),
            name="injected_restart",
            reason="restart needed",
        )

    ops = [
        Operation(name="step1", type="action", provides=["a"], callable=step1),
        Operation(name="step2", type="action", provides=["b"], requires=["a"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["b"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["step1", "step2", "check"], target="check")
    result = run_case(case, defn)

    assert result.status == "pass"
    assert hook_log == ["hook_fired"]

    step_names = [s.operation for s in result.steps]
    assert step_names == ["step1", "injected_restart", "step2", "check"]

    injected = result.steps[1]
    assert injected.injected is True
    assert injected.status == "pass"


def test_transient_hook_fires_once():
    """Hook is removed after first match; second match doesn't fire."""
    count = []

    def step1(params, env):
        return TransientHook(
            before_op="repeatable",
            action=lambda p: count.append(1),
            name="one_shot",
        )

    ops = [
        Operation(name="step1", type="action", provides=["a"], callable=step1),
        Operation(name="repeatable", type="action", provides=["b"],
                  requires=["a"], callable=lambda *a: None),
        Operation(name="check", type="check", requires=["b"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["step1", "repeatable", "check"],
                    target="check")
    result = run_case(case, defn)
    assert result.status == "pass"
    assert len(count) == 1


def test_transient_hook_failure_aborts_case():
    """If hook action raises, case fails."""
    def bad_hook(params):
        raise RuntimeError("hook failed")

    def step1(params, env):
        return TransientHook(before_op="step2", action=bad_hook, name="bad_hook")

    ops = [
        Operation(name="step1", type="action", provides=["a"], callable=step1),
        Operation(name="step2", type="action", provides=["b"], requires=["a"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["b"],
                  callable=lambda *a: None),
        Operation(name="cleanup", type="cleanup", requires=["a"], clears=["a"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"])
    case = TestCase(case_id="t1", steps=["step1", "step2", "check"],
                    target="check", cleanup_steps=["cleanup"])
    result = run_case(case, defn)

    assert result.status == "fail"
    hook_step = [s for s in result.steps if s.operation == "bad_hook"]
    assert len(hook_step) == 1
    assert hook_step[0].status == "fail"
    # Cleanup should still run
    cleanup_step = [s for s in result.steps if s.operation == "cleanup"]
    assert len(cleanup_step) == 1


def test_transient_hook_no_match_doesnt_fire():
    """Hook targeting a non-existent step just never fires."""
    count = []

    def step1(params, env):
        return TransientHook(
            before_op="nonexistent",
            action=lambda p: count.append(1),
        )

    ops = [
        Operation(name="step1", type="action", provides=["a"], callable=step1),
        Operation(name="check", type="check", requires=["a"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["step1", "check"], target="check")
    result = run_case(case, defn)
    assert result.status == "pass"
    assert count == []


# ---------------------------------------------------------------------------
# TransitionObserver
# ---------------------------------------------------------------------------

def test_observer_runs_after_watched_ops():
    """Observer verify is called after each watched operation."""
    verify_log = []

    def setup_observer(params, env):
        return TransitionObserver(
            watch_ops=["step2", "step3"],
            verify=lambda p: verify_log.append("verified"),
            name="my_observer",
        )

    ops = [
        Operation(name="step1", type="action", provides=["a"],
                  callable=setup_observer),
        Operation(name="step2", type="action", provides=["b"],
                  requires=["a"], callable=lambda *a: None),
        Operation(name="step3", type="action", provides=["c"],
                  requires=["b"], callable=lambda *a: None),
        Operation(name="check", type="check", requires=["c"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["step1", "step2", "step3", "check"],
                    target="check")
    result = run_case(case, defn)

    assert result.status == "pass"
    assert verify_log == ["verified", "verified"]

    # Observer results attached to step2 and step3
    step2_result = [s for s in result.steps if s.operation == "step2"][0]
    assert len(step2_result.observer_results) == 1
    assert step2_result.observer_results[0].status == "pass"

    step3_result = [s for s in result.steps if s.operation == "step3"][0]
    assert len(step3_result.observer_results) == 1


def test_observer_failure_fails_case():
    """Observer verify raising an exception marks case as failed."""
    def fail_verify(params):
        raise AssertionError("audit check failed")

    def setup_observer(params, env):
        return TransitionObserver(
            watch_ops=["step2"],
            verify=fail_verify,
            name="audit_check",
        )

    ops = [
        Operation(name="step1", type="action", provides=["a"],
                  callable=setup_observer),
        Operation(name="step2", type="action", provides=["b"],
                  requires=["a"], callable=lambda *a: None),
        Operation(name="check", type="check", requires=["b"],
                  callable=lambda *a: None),
        Operation(name="cleanup", type="cleanup", requires=["a"], clears=["a"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"])
    case = TestCase(case_id="t1", steps=["step1", "step2", "check"],
                    target="check", cleanup_steps=["cleanup"])
    result = run_case(case, defn)
    assert result.status == "fail"

    step2_result = [s for s in result.steps if s.operation == "step2"][0]
    assert step2_result.observer_results[0].status == "fail"
    assert "audit check failed" in step2_result.observer_results[0].error


def test_observer_not_triggered_by_unwatched_ops():
    """Observer only fires for ops in watch_ops list."""
    verify_log = []

    def setup_observer(params, env):
        return TransitionObserver(
            watch_ops=["step3"],
            verify=lambda p: verify_log.append("verified"),
            name="selective",
        )

    ops = [
        Operation(name="step1", type="action", provides=["a"],
                  callable=setup_observer),
        Operation(name="step2", type="action", provides=["b"],
                  requires=["a"], callable=lambda *a: None),
        Operation(name="step3", type="action", provides=["c"],
                  requires=["b"], callable=lambda *a: None),
        Operation(name="check", type="check", requires=["c"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(case_id="t1", steps=["step1", "step2", "step3", "check"],
                    target="check")
    result = run_case(case, defn)
    assert verify_log == ["verified"]

    step2_result = [s for s in result.steps if s.operation == "step2"][0]
    assert step2_result.observer_results == []


# ---------------------------------------------------------------------------
# Multiple modifiers in one case
# ---------------------------------------------------------------------------

def test_multiple_modifier_types_together():
    """EdgeGuard, TransientHook, and TransitionObserver all in one case."""
    hook_log = []
    obs_log = []

    def config_step(params, env):
        return EdgeGuard(blocked_op="bad_path", reason="avoid this")

    def memtune_step(params, env):
        return TransientHook(
            before_op="check",
            action=lambda p: hook_log.append("hooked"),
            name="pre_check_hook",
        )

    def attach_step(params, env):
        return TransitionObserver(
            watch_ops=["check"],
            verify=lambda p: obs_log.append("observed"),
            name="watcher",
        )

    ops = [
        Operation(name="config", type="action", provides=["configured"],
                  callable=config_step),
        Operation(name="memtune", type="action", provides=["tuned"],
                  requires=["configured"], callable=memtune_step),
        Operation(name="attach", type="action", provides=["attached"],
                  requires=["tuned"], callable=attach_step),
        Operation(name="check", type="check", requires=["attached"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    case = TestCase(
        case_id="t1",
        steps=["config", "memtune", "attach", "check"],
        target="check",
    )
    result = run_case(case, defn)

    assert result.status == "pass"
    assert hook_log == ["hooked"]
    assert obs_log == ["observed"]

    step_names = [s.operation for s in result.steps]
    assert step_names == ["config", "memtune", "attach", "pre_check_hook", "check"]


# ---------------------------------------------------------------------------
# run_all with graph
# ---------------------------------------------------------------------------

def test_run_all_passes_graph():
    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"], cleanup=False)
    graph = build_graph(ops)
    cases = generate_cases(defn, graph)
    results, _ = run_all(cases, defn, graph=graph)
    assert len(results) == 1
    assert results[0].status == "pass"


# ---------------------------------------------------------------------------
# Cleanup still runs on modifier-induced failures
# ---------------------------------------------------------------------------

def test_cleanup_runs_after_edge_guard_error():
    cleanup_log = []

    ops = [
        Operation(name="config", type="action", provides=["configured"],
                  callable=lambda *a: EdgeGuard(blocked_op="only_way")),
        Operation(name="only_way", type="action", provides=["ready"],
                  requires=["configured"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="clean", type="cleanup", requires=["configured"],
                  clears=["configured"],
                  callable=lambda *a: cleanup_log.append("cleaned")),
    ]
    defn = _make_definition(ops, ["check"])
    case = TestCase(
        case_id="t1",
        steps=["config", "only_way", "check"],
        target="check",
        cleanup_steps=["clean"],
    )
    result = run_case(case, defn, graph=None)
    assert result.status == "error"
    assert cleanup_log == ["cleaned"]
