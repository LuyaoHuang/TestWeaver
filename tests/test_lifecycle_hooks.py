"""Tests for lifecycle hooks (suite_setup/teardown, case_setup/teardown)."""
from __future__ import annotations

from testweaver.decorators import (
    action,
    case_setup,
    case_teardown,
    check,
    cleanup,
    clears,
    provides,
    requires,
    suite_setup,
    suite_teardown,
)
from testweaver.engine import run_all, run_case
from testweaver.graph import generate_cases
from testweaver.loader import extract_hooks, extract_operations
from testweaver.schema import (
    CaseResult,
    HookResult,
    LifecycleHooks,
    Operation,
    TestCase,
    TestDefinition,
    TestSuite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_definition(ops, targets, hooks=None, cleanup_flag=True, params=None):
    return TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="hook_test",
            targets=targets,
            cleanup=cleanup_flag,
            params=params or {},
        ),
        hooks=hooks or LifecycleHooks(),
    )


def _simple_ops():
    return [
        Operation(name="do_setup", type="setup", provides=["ready"],
                  callable=lambda p: None),
        Operation(name="do_check", type="check", requires=["ready"],
                  callable=lambda p: None),
        Operation(name="do_cleanup", type="cleanup", requires=["ready"],
                  clears=["ready"], callable=lambda p: None),
    ]


# ---------------------------------------------------------------------------
# Decorator tests
# ---------------------------------------------------------------------------

class TestDecorators:
    def test_suite_setup_sets_hook_meta(self):
        @suite_setup
        def my_hook(ctx):
            pass
        assert my_hook._tw_meta['hook'] == 'suite_setup'

    def test_suite_teardown_sets_hook_meta(self):
        @suite_teardown
        def my_hook(ctx):
            pass
        assert my_hook._tw_meta['hook'] == 'suite_teardown'

    def test_case_setup_sets_hook_meta(self):
        @case_setup
        def my_hook(ctx):
            pass
        assert my_hook._tw_meta['hook'] == 'case_setup'

    def test_case_teardown_sets_hook_meta(self):
        @case_teardown
        def my_hook(ctx):
            pass
        assert my_hook._tw_meta['hook'] == 'case_teardown'


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------

class TestExtractHooks:
    def test_hooks_not_extracted_as_operations(self):
        import types
        mod = types.ModuleType("test_mod")

        @suite_setup
        def my_setup(ctx):
            pass

        @action
        @provides('ready')
        def do_thing(params):
            pass

        mod.my_setup = my_setup
        mod.do_thing = do_thing

        ops = extract_operations(mod)
        op_names = [op.name for op, _ in ops]
        assert 'my_setup' not in op_names
        assert 'do_thing' in op_names

    def test_extract_hooks_finds_all_types(self):
        import types
        mod = types.ModuleType("test_mod")

        @suite_setup
        def ss(ctx): pass
        @suite_teardown
        def st(ctx): pass
        @case_setup
        def cs(ctx): pass
        @case_teardown
        def ct(ctx): pass

        mod.ss = ss
        mod.st = st
        mod.cs = cs
        mod.ct = ct

        hooks = extract_hooks(mod)
        assert len(hooks['suite_setup']) == 1
        assert len(hooks['suite_teardown']) == 1
        assert len(hooks['case_setup']) == 1
        assert len(hooks['case_teardown']) == 1


# ---------------------------------------------------------------------------
# Case-level hook tests
# ---------------------------------------------------------------------------

class TestCaseHooks:
    def test_case_setup_runs_before_steps(self):
        log = []

        def case_setup_fn(ctx):
            log.append('case_setup')

        def do_action(params):
            log.append('action')

        ops = [
            Operation(name="act", type="action", provides=["done"],
                      callable=do_action),
            Operation(name="chk", type="check", requires=["done"],
                      callable=lambda p: log.append('check')),
            Operation(name="clr", type="cleanup", requires=["done"],
                      clears=["done"], callable=lambda p: None),
        ]
        hooks = LifecycleHooks(case_setup=[case_setup_fn])
        defn = _make_definition(ops, ["chk"], hooks=hooks)
        cases = generate_cases(defn)
        result = run_case(cases[0], defn)

        assert result.status == "pass"
        assert log[0] == 'case_setup'
        assert 'action' in log
        assert result.hook_results[0].hook_type == "case_setup"
        assert result.hook_results[0].status == "pass"

    def test_case_teardown_runs_after_steps(self):
        log = []

        def case_teardown_fn(ctx):
            log.append('case_teardown')

        ops = [
            Operation(name="act", type="action", provides=["done"],
                      callable=lambda p: log.append('action')),
            Operation(name="chk", type="check", requires=["done"],
                      callable=lambda p: log.append('check')),
            Operation(name="clr", type="cleanup", requires=["done"],
                      clears=["done"], callable=lambda p: log.append('cleanup')),
        ]
        hooks = LifecycleHooks(case_teardown=[case_teardown_fn])
        defn = _make_definition(ops, ["chk"], hooks=hooks)
        cases = generate_cases(defn)
        result = run_case(cases[0], defn)

        assert result.status == "pass"
        assert log[-1] == 'case_teardown'
        assert result.hook_results[0].hook_type == "case_teardown"

    def test_case_teardown_runs_on_failure(self):
        teardown_ran = []

        def case_teardown_fn(ctx):
            teardown_ran.append(ctx.get('_status'))

        ops = [
            Operation(name="fail_op", type="action", provides=["done"],
                      callable=lambda p: (_ for _ in ()).throw(RuntimeError("boom"))),
            Operation(name="chk", type="check", requires=["done"],
                      callable=lambda p: None),
        ]
        hooks = LifecycleHooks(case_teardown=[case_teardown_fn])
        defn = _make_definition(ops, ["chk"], hooks=hooks, cleanup_flag=False)
        cases = generate_cases(defn)
        result = run_case(cases[0], defn)

        assert result.status == "fail"
        assert len(teardown_ran) == 1
        assert teardown_ran[0] == "fail"

    def test_case_setup_failure_skips_main_steps(self):
        log = []

        def failing_setup(ctx):
            raise RuntimeError("setup boom")

        ops = [
            Operation(name="act", type="action", provides=["done"],
                      callable=lambda p: log.append('action')),
            Operation(name="chk", type="check", requires=["done"],
                      callable=lambda p: log.append('check')),
            Operation(name="clr", type="cleanup", requires=["done"],
                      clears=["done"], callable=lambda p: log.append('cleanup')),
        ]
        hooks = LifecycleHooks(case_setup=[failing_setup])
        defn = _make_definition(ops, ["chk"], hooks=hooks)
        cases = generate_cases(defn)
        result = run_case(cases[0], defn)

        assert result.status == "error"
        assert 'action' not in log
        assert any(r.status == "error" for r in result.hook_results)

    def test_case_setup_failure_still_runs_teardown(self):
        teardown_ran = []

        def failing_setup(ctx):
            raise RuntimeError("setup boom")

        def td(ctx):
            teardown_ran.append(True)

        ops = _simple_ops()
        hooks = LifecycleHooks(case_setup=[failing_setup], case_teardown=[td])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        run_case(cases[0], defn)

        assert len(teardown_ran) == 1

    def test_case_context_has_expected_keys(self):
        received = {}

        def capture_setup(ctx):
            received.update(ctx)

        ops = _simple_ops()
        hooks = LifecycleHooks(case_setup=[capture_setup])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        run_case(cases[0], defn)

        assert '_case' in received
        assert '_case_id' in received
        assert received['_case_id'] == cases[0].case_id

    def test_case_teardown_context_has_status(self):
        received = {}

        def capture_td(ctx):
            received.update(ctx)

        ops = _simple_ops()
        hooks = LifecycleHooks(case_teardown=[capture_td])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        run_case(cases[0], defn)

        assert received['_status'] == "pass"

    def test_multiple_case_hooks_all_run(self):
        log = []

        def hook_a(ctx):
            log.append('a')

        def hook_b(ctx):
            log.append('b')

        ops = _simple_ops()
        hooks = LifecycleHooks(case_setup=[hook_a, hook_b])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        run_case(cases[0], defn)

        assert log == ['a', 'b']

    def test_failing_hook_doesnt_prevent_other_hooks(self):
        log = []

        def hook_fail(ctx):
            log.append('fail')
            raise RuntimeError("boom")

        def hook_ok(ctx):
            log.append('ok')

        ops = _simple_ops()
        hooks = LifecycleHooks(case_setup=[hook_fail, hook_ok])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        result = run_case(cases[0], defn)

        assert log == ['fail', 'ok']
        assert result.status == "error"


# ---------------------------------------------------------------------------
# Suite-level hook tests
# ---------------------------------------------------------------------------

class TestSuiteHooks:
    def test_suite_setup_runs_before_cases(self):
        log = []

        def ss(ctx):
            log.append('suite_setup')

        ops = [
            Operation(name="act", type="action", provides=["done"],
                      callable=lambda p: log.append('action')),
            Operation(name="chk", type="check", requires=["done"],
                      callable=lambda p: None),
            Operation(name="clr", type="cleanup", requires=["done"],
                      clears=["done"], callable=lambda p: None),
        ]
        hooks = LifecycleHooks(suite_setup=[ss])
        defn = _make_definition(ops, ["chk"], hooks=hooks)
        cases = generate_cases(defn)
        results, suite_hooks = run_all(cases, defn, timeout=10)

        assert log[0] == 'suite_setup'
        assert all(r.status == "pass" for r in results)
        assert len(suite_hooks) == 1
        assert suite_hooks[0].hook_type == "suite_setup"
        assert suite_hooks[0].status == "pass"

    def test_suite_teardown_runs_after_cases(self):
        log = []

        def st(ctx):
            log.append('suite_teardown')

        ops = [
            Operation(name="act", type="action", provides=["done"],
                      callable=lambda p: log.append('action')),
            Operation(name="chk", type="check", requires=["done"],
                      callable=lambda p: None),
            Operation(name="clr", type="cleanup", requires=["done"],
                      clears=["done"], callable=lambda p: None),
        ]
        hooks = LifecycleHooks(suite_teardown=[st])
        defn = _make_definition(ops, ["chk"], hooks=hooks)
        cases = generate_cases(defn)
        results, suite_hooks = run_all(cases, defn, timeout=10)

        assert log[-1] == 'suite_teardown'
        assert suite_hooks[0].hook_type == "suite_teardown"

    def test_suite_setup_failure_skips_all_cases(self):
        def failing_ss(ctx):
            raise RuntimeError("suite boom")

        ops = _simple_ops()
        hooks = LifecycleHooks(suite_setup=[failing_ss])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        results, suite_hooks = run_all(cases, defn, timeout=10)

        assert all(r.status == "error" for r in results)
        assert any(h.status == "error" for h in suite_hooks)

    def test_suite_teardown_runs_even_on_setup_failure(self):
        teardown_ran = []

        def failing_ss(ctx):
            raise RuntimeError("suite boom")

        def st(ctx):
            teardown_ran.append(True)

        ops = _simple_ops()
        hooks = LifecycleHooks(suite_setup=[failing_ss], suite_teardown=[st])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        run_all(cases, defn, timeout=10)

        assert len(teardown_ran) == 1

    def test_suite_context_has_expected_keys(self):
        received = {}

        def capture_ss(ctx):
            received.update(ctx)

        ops = _simple_ops()
        hooks = LifecycleHooks(suite_setup=[capture_ss])
        defn = _make_definition(ops, ["do_check"], hooks=hooks,
                                params={"host": "localhost"})
        cases = generate_cases(defn)
        run_all(cases, defn, timeout=10)

        assert received['_suite_name'] == "hook_test"
        assert received['_case_count'] == len(cases)
        assert received['host'] == "localhost"

    def test_suite_teardown_context_has_setup_status(self):
        received = {}

        def failing_ss(ctx):
            raise RuntimeError("boom")

        def capture_st(ctx):
            received.update(ctx)

        ops = _simple_ops()
        hooks = LifecycleHooks(suite_setup=[failing_ss], suite_teardown=[capture_st])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        run_all(cases, defn, timeout=10)

        assert received['_suite_setup_failed'] is True

    def test_suite_hooks_in_run_summary(self):
        def ss(ctx):
            pass

        ops = _simple_ops()
        hooks = LifecycleHooks(suite_setup=[ss])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        results, suite_hooks = run_all(cases, defn, timeout=10)

        from testweaver.analyzer import summarize_run
        summary = summarize_run(results, suite_hook_results=suite_hooks)
        assert len(summary.suite_hook_results) == 1
        assert summary.suite_hook_results[0].status == "pass"


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------

class TestParallelWithHooks:
    def test_case_hooks_work_with_parallel(self):
        import threading
        threads_seen: set[str] = set()

        def cs(ctx):
            threads_seen.add(threading.current_thread().name)

        ops = _simple_ops()
        hooks = LifecycleHooks(case_setup=[cs])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        if len(cases) < 2:
            cases = cases * 3
        results, _ = run_all(cases, defn, timeout=10, workers=2)
        assert all(r.status == "pass" for r in results)
        assert all(len(r.hook_results) == 1 for r in results)

    def test_suite_hooks_run_outside_pool(self):
        import threading
        suite_thread = []

        def ss(ctx):
            suite_thread.append(threading.current_thread().name)

        ops = _simple_ops()
        hooks = LifecycleHooks(suite_setup=[ss])
        defn = _make_definition(ops, ["do_check"], hooks=hooks)
        cases = generate_cases(defn)
        run_all(cases, defn, timeout=10, workers=2)

        assert len(suite_thread) == 1
        assert 'ThreadPool' not in suite_thread[0]


# ---------------------------------------------------------------------------
# No hooks (backward compatibility)
# ---------------------------------------------------------------------------

class TestNoHooks:
    def test_run_case_without_hooks(self):
        ops = _simple_ops()
        defn = _make_definition(ops, ["do_check"])
        cases = generate_cases(defn)
        result = run_case(cases[0], defn)
        assert result.status == "pass"
        assert result.hook_results == []

    def test_run_all_without_hooks(self):
        ops = _simple_ops()
        defn = _make_definition(ops, ["do_check"])
        cases = generate_cases(defn)
        results, suite_hooks = run_all(cases, defn, timeout=10)
        assert all(r.status == "pass" for r in results)
        assert suite_hooks == []


# ---------------------------------------------------------------------------
# HookResult model
# ---------------------------------------------------------------------------

class TestHookResultModel:
    def test_defaults(self):
        hr = HookResult(hook_name="test", hook_type="case_setup")
        assert hr.status == "pass"
        assert hr.error is None
        assert hr.duration_ms == 0.0

    def test_serialization(self):
        hr = HookResult(
            hook_name="my_hook",
            hook_type="suite_teardown",
            status="error",
            error="boom",
            duration_ms=42.5,
        )
        data = hr.model_dump()
        assert data['hook_name'] == "my_hook"
        assert data['status'] == "error"

    def test_case_result_hook_results_in_json(self):
        cr = CaseResult(
            case_id="test_1",
            status="pass",
            hook_results=[
                HookResult(hook_name="setup", hook_type="case_setup"),
            ],
        )
        data = cr.model_dump()
        assert len(data['hook_results']) == 1
