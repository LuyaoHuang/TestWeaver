"""Tests for fault-injection testing: @fault_for decorator and fault case generation."""

import pytest

from testweaver.decorators import fault_for, requires, excludes, provides, action, check, cleanup, clears, cut
from testweaver.graph import build_graph, generate_cases, explain_graph
from testweaver.engine import run_case, run_all
from testweaver.schema import (
    Operation, TestSuite as Suite, TestDefinition as Defn, TestCase,
)


def _make_definition(operations, targets, **kwargs):
    return Defn(
        operations=operations,
        suite=Suite(name="test", targets=targets, **kwargs),
    )


# ---------------------------------------------------------------------------
# Decorator tests
# ---------------------------------------------------------------------------

def test_fault_for_sets_metadata():
    @fault_for('start_vm')
    def my_fault(params, env):
        pass

    meta = my_fault._tw_meta
    assert meta['fault_for'] == 'start_vm'
    assert meta['type'] == 'fault'
    assert meta['terminal'] is True


def test_fault_for_terminal_false():
    @fault_for('start_vm', terminal=False)
    def my_fault(params, env):
        pass

    assert my_fault._tw_meta['terminal'] is False


def test_fault_for_with_extra_requires():
    @fault_for('start_vm')
    @requires('vm.config.hugepage')
    def my_fault(params, env):
        pass

    meta = my_fault._tw_meta
    assert meta['fault_for'] == 'start_vm'
    assert 'vm.config.hugepage' in meta['requires']


def test_fault_for_with_extra_excludes():
    @fault_for('start_vm')
    @excludes('vm.config.memballoon')
    def my_fault(params, env):
        pass

    meta = my_fault._tw_meta
    assert 'vm.config.memballoon' in meta['excludes']


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------

def test_fault_op_rejects_provides():
    with pytest.raises(ValueError, match="must not declare 'provides'"):
        Operation(
            name="bad", type="fault", fault_for="target",
            provides=["something"],
        )


def test_fault_op_rejects_clears():
    with pytest.raises(ValueError, match="must not declare 'clears'"):
        Operation(
            name="bad", type="fault", fault_for="target",
            clears=["something"],
        )


def test_fault_op_rejects_cuts():
    with pytest.raises(ValueError, match="must not declare 'cuts'"):
        Operation(
            name="bad", type="fault", fault_for="target",
            cuts=["something"],
        )


def test_fault_op_rejects_grafts():
    from testweaver.schema import GraftDef
    with pytest.raises(ValueError, match="must not declare 'grafts'"):
        Operation(
            name="bad", type="fault", fault_for="target",
            grafts=[GraftDef(src="a", tgt="b")],
        )


def test_fault_op_requires_fault_for():
    with pytest.raises(ValueError, match="must specify 'fault_for'"):
        Operation(name="bad", type="fault")


def test_fault_op_valid():
    op = Operation(
        name="my_fault", type="fault", fault_for="start",
        requires=["extra_state"],
    )
    assert op.fault_for == "start"
    assert op.terminal is True
    assert op.requires == ["extra_state"]


def test_fault_target_must_exist():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(
            name="my_fault", type="fault", fault_for="nonexistent",
            requires=["ready"],
        ),
    ]
    with pytest.raises(ValueError, match="references target 'nonexistent'"):
        _make_definition(ops, ["check"])


# ---------------------------------------------------------------------------
# Graph construction tests
# ---------------------------------------------------------------------------

def test_fault_not_in_graph():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="enhance", type="action",
                  requires=["ready"], provides=["enhanced"]),
        Operation(name="start", type="action",
                  requires=["ready"], provides=["active"]),
        Operation(name="check", type="check", requires=["active"]),
        Operation(
            name="fault_start", type="fault", fault_for="start",
            requires=["enhanced"],
            callable=lambda *a: None,
        ),
        Operation(name="teardown", type="cleanup",
                  requires=["active"], clears=["active"]),
        Operation(name="clean_enhanced", type="cleanup",
                  requires=["enhanced"], clears=["enhanced"]),
        Operation(name="clean_ready", type="cleanup",
                  requires=["ready"], excludes=["active", "enhanced"],
                  clears=["ready"]),
    ]
    graph = build_graph(ops)
    edge_ops = set()
    for u, v, data in graph.edges(data=True):
        edge_ops.add(data['operation'])
    assert 'fault_start' not in edge_ops


# ---------------------------------------------------------------------------
# Fault case generation tests
# ---------------------------------------------------------------------------

def _vm_ops():
    """Shared operations for VM-like scenarios."""
    return [
        Operation(name="define", type="action", provides=["vm.config"]),
        Operation(
            name="add_hugepage", type="action",
            requires=["vm.config"], excludes=["vm.config.hugepage"],
            provides=["vm.config.hugepage"],
        ),
        Operation(
            name="start", type="action",
            requires=["vm.config"], excludes=["vm.active"],
            provides=["vm.active"],
        ),
        Operation(name="check_vm", type="check", requires=["vm.active"]),
        Operation(
            name="destroy", type="cleanup",
            requires=["vm.active"], clears=["vm.active"],
        ),
        Operation(
            name="remove_hugepage", type="cleanup",
            requires=["vm.config.hugepage"], excludes=["vm.active"],
            clears=["vm.config.hugepage"],
        ),
        Operation(
            name="undefine", type="cleanup",
            requires=["vm.config"],
            excludes=["vm.active", "vm.config.hugepage"],
            cuts=["vm.config"],
        ),
    ]


def test_fault_cases_generated():
    ops = _vm_ops() + [
        Operation(
            name="hugepage_error", type="fault", fault_for="start",
            requires=["vm.config.hugepage"],
            callable=lambda *a: None,
        ),
    ]
    defn = _make_definition(ops, ["check_vm"])
    cases = generate_cases(defn)

    normal = [c for c in cases if not c.is_fault]
    faults = [c for c in cases if c.is_fault]

    assert len(normal) >= 1
    assert len(faults) >= 1

    for fc in faults:
        assert fc.target == "hugepage_error"
        assert fc.case_id.startswith("fault-")
        assert fc.is_fault is True
        assert "hugepage_error" in fc.steps
        # The fault op should be the last step (the target)
        assert fc.steps[-1] == "hugepage_error"


def test_fault_case_ids_prefixed():
    ops = _vm_ops() + [
        Operation(
            name="hugepage_error", type="fault", fault_for="start",
            requires=["vm.config.hugepage"],
            callable=lambda *a: None,
        ),
    ]
    defn = _make_definition(ops, ["check_vm"])
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]
    for fc in faults:
        assert fc.case_id.startswith("fault-hugepage_error-")


def test_fault_cleanup_from_pre_fault_state():
    ops = _vm_ops() + [
        Operation(
            name="hugepage_error", type="fault", fault_for="start",
            requires=["vm.config.hugepage"],
            callable=lambda *a: None,
        ),
    ]
    defn = _make_definition(ops, ["check_vm"])
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]

    for fc in faults:
        # Pre-fault state has vm.config + vm.config.hugepage, but NOT vm.active
        # Cleanup should NOT include "destroy" (vm.active is not set)
        assert "destroy" not in fc.cleanup_steps
        # Should include cleanup for hugepage and config
        assert "remove_hugepage" in fc.cleanup_steps or "undefine" in fc.cleanup_steps


def test_fault_with_no_extra_requires():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="do_thing", type="action",
                  requires=["ready"], provides=["done"]),
        Operation(name="check", type="check", requires=["done"]),
        Operation(
            name="fault_do_thing", type="fault", fault_for="do_thing",
            callable=lambda *a: None,
        ),
        Operation(name="clean_done", type="cleanup",
                  requires=["done"], clears=["done"]),
        Operation(name="clean_ready", type="cleanup",
                  requires=["ready"], excludes=["done"],
                  clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]
    assert len(faults) >= 1
    for fc in faults:
        assert fc.target == "fault_do_thing"


def test_multiple_faults_for_same_target():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="add_a", type="action",
                  requires=["ready"], provides=["feature_a"]),
        Operation(name="add_b", type="action",
                  requires=["ready"], provides=["feature_b"]),
        Operation(name="do_thing", type="action",
                  requires=["ready"], provides=["done"]),
        Operation(name="check", type="check", requires=["done"]),
        Operation(
            name="fault_a", type="fault", fault_for="do_thing",
            requires=["feature_a"],
            callable=lambda *a: None,
        ),
        Operation(
            name="fault_b", type="fault", fault_for="do_thing",
            requires=["feature_b"],
            callable=lambda *a: None,
        ),
        Operation(name="clean_done", type="cleanup",
                  requires=["done"], clears=["done"]),
        Operation(name="clean_a", type="cleanup",
                  requires=["feature_a"], clears=["feature_a"]),
        Operation(name="clean_b", type="cleanup",
                  requires=["feature_b"], clears=["feature_b"]),
        Operation(name="clean_ready", type="cleanup",
                  requires=["ready"],
                  excludes=["done", "feature_a", "feature_b"],
                  clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]

    fault_targets = {fc.target for fc in faults}
    assert "fault_a" in fault_targets
    assert "fault_b" in fault_targets


def test_no_fault_cases_when_disabled():
    ops = _vm_ops() + [
        Operation(
            name="hugepage_error", type="fault", fault_for="start",
            requires=["vm.config.hugepage"],
            callable=lambda *a: None,
        ),
    ]
    defn = _make_definition(ops, ["check_vm"], faults=False)
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]
    assert len(faults) == 0


def test_no_fault_cases_when_conditions_unmet():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="do_thing", type="action",
                  requires=["ready"], provides=["done"]),
        Operation(name="check", type="check", requires=["done"]),
        Operation(
            name="fault_impossible", type="fault", fault_for="do_thing",
            requires=["never_provided"],
            callable=lambda *a: None,
        ),
        Operation(name="clean", type="cleanup",
                  requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]
    assert len(faults) == 0


# ---------------------------------------------------------------------------
# Execution tests
# ---------------------------------------------------------------------------

def test_run_fault_case_callable():
    called = []

    def fault_fn(params, env):
        called.append("fault_executed")

    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None),
        Operation(name="do_thing", type="action",
                  requires=["ready"], provides=["done"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["done"],
                  callable=lambda *a: None),
        Operation(
            name="fault_do_thing", type="fault", fault_for="do_thing",
            callable=fault_fn,
        ),
        Operation(name="clean_ready", type="cleanup",
                  requires=["ready"], clears=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]
    assert len(faults) >= 1

    result = run_case(faults[0], defn, timeout=10)
    assert result.is_fault is True
    assert result.status == "pass"
    assert "fault_executed" in called


def test_run_fault_case_cleanup_runs():
    cleanup_called = []

    def cleanup_fn(params, env):
        cleanup_called.append("cleaned")

    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None),
        Operation(name="do_thing", type="action",
                  requires=["ready"], provides=["done"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["done"],
                  callable=lambda *a: None),
        Operation(
            name="fault_do_thing", type="fault", fault_for="do_thing",
            callable=lambda *a: None,
        ),
        Operation(name="clean_ready", type="cleanup",
                  requires=["ready"], clears=["ready"],
                  callable=cleanup_fn),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]
    assert len(faults) >= 1

    run_case(faults[0], defn, timeout=10)
    assert "cleaned" in cleanup_called


def test_run_all_includes_fault_cases():
    ops = [
        Operation(name="setup", type="action", provides=["ready"],
                  callable=lambda *a: None),
        Operation(name="enhance", type="action",
                  requires=["ready"], provides=["enhanced"],
                  callable=lambda *a: None),
        Operation(name="do_thing", type="action",
                  requires=["ready"], provides=["done"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["done"],
                  callable=lambda *a: None),
        Operation(
            name="fault_do_thing", type="fault", fault_for="do_thing",
            requires=["enhanced"],
            callable=lambda *a: None,
        ),
        Operation(name="clean_done", type="cleanup",
                  requires=["done"], clears=["done"],
                  callable=lambda *a: None),
        Operation(name="clean_enhanced", type="cleanup",
                  requires=["enhanced"], clears=["enhanced"],
                  callable=lambda *a: None),
        Operation(name="clean_ready", type="cleanup",
                  requires=["ready"],
                  excludes=["done", "enhanced"],
                  clears=["ready"],
                  callable=lambda *a: None),
    ]
    defn = _make_definition(ops, ["check"])
    cases = generate_cases(defn)
    results, _ = run_all(cases, defn, timeout=10)

    normal_results = [r for r in results if not r.is_fault]
    fault_results = [r for r in results if r.is_fault]
    assert len(normal_results) >= 1
    assert len(fault_results) >= 1
    for r in fault_results:
        assert r.status == "pass"


# ---------------------------------------------------------------------------
# Loader integration test
# ---------------------------------------------------------------------------

def test_extract_fault_from_module():
    import types
    from testweaver.loader import extract_operations

    mod = types.ModuleType("test_mod")

    @action
    @provides('ready')
    def setup_op(params):
        pass

    @fault_for('setup_op')
    @requires('extra')
    def my_fault(params):
        pass

    mod.setup_op = setup_op
    mod.my_fault = my_fault

    op_pairs = extract_operations(mod)
    ops = {name: op for (op, func) in op_pairs for name in [op.name]}

    assert 'my_fault' in ops
    assert ops['my_fault'].type == 'fault'
    assert ops['my_fault'].fault_for == 'setup_op'
    assert 'extra' in ops['my_fault'].requires


# ---------------------------------------------------------------------------
# explain_graph integration
# ---------------------------------------------------------------------------

def test_explain_graph_includes_fault_ops():
    ops = _vm_ops() + [
        Operation(
            name="hugepage_error", type="fault", fault_for="start",
            requires=["vm.config.hugepage"],
            callable=lambda *a: None,
        ),
    ]
    defn = _make_definition(ops, ["check_vm"])
    info = explain_graph(defn)

    assert "fault_operations" in info
    assert len(info["fault_operations"]) == 1
    f = info["fault_operations"][0]
    assert f["name"] == "hugepage_error"
    assert f["fault_for"] == "start"
    assert f["triggerable_from_n_states"] >= 1
    assert "vm.config.hugepage" in f["extra_requires"]


def test_explain_graph_no_fault_ops():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup",
                  requires=["ready"], clears=["ready"]),
    ]
    defn = _make_definition(ops, ["check"])
    info = explain_graph(defn)
    assert "fault_operations" not in info


# ---------------------------------------------------------------------------
# Generation strategy tests
# ---------------------------------------------------------------------------

def test_fault_cases_respect_strategy_representative():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="path_a", type="action",
                  requires=["ready"], provides=["via_a"]),
        Operation(name="path_b", type="action",
                  requires=["ready"], provides=["via_b"]),
        Operation(name="do_thing", type="action",
                  requires=["ready"], provides=["done"]),
        Operation(name="check", type="check", requires=["done"]),
        Operation(
            name="fault_a", type="fault", fault_for="do_thing",
            requires=["via_a"],
            callable=lambda *a: None,
        ),
        Operation(
            name="fault_b", type="fault", fault_for="do_thing",
            requires=["via_b"],
            callable=lambda *a: None,
        ),
        Operation(name="c_done", type="cleanup",
                  requires=["done"], clears=["done"]),
        Operation(name="c_a", type="cleanup",
                  requires=["via_a"], clears=["via_a"]),
        Operation(name="c_b", type="cleanup",
                  requires=["via_b"], clears=["via_b"]),
        Operation(name="c_ready", type="cleanup",
                  requires=["ready"],
                  excludes=["done", "via_a", "via_b"],
                  clears=["ready"]),
    ]
    defn = _make_definition(
        ops, ["check"], generation_strategy="representative",
    )
    cases = generate_cases(defn)
    faults = [c for c in cases if c.is_fault]
    assert len(faults) >= 1
