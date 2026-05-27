"""Tests for the data_flow_demo.py example.

Verifies that the runtime data flow feature works correctly:
- Operations can write data to env nodes via env.set_value()
- Downstream operations can read data from env nodes via env._get_node()
- The full dependency graph generates and executes correctly
- Data is isolated to the correct state paths
"""
from __future__ import annotations

from pathlib import Path

from testweaver.env import Env
from testweaver.engine import run_case, run_step
from testweaver.graph import apply_operation, build_graph, generate_cases
from testweaver.loader import extract_hooks, extract_operations, load_module
from testweaver.schema import Operation, TestDefinition, TestSuite


EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
DEMO_PATH = EXAMPLES_DIR / "data_flow_demo.py"


def _load_demo_ops():
    """Load the demo module and return (operations_dict, definition)."""
    module = load_module(DEMO_PATH)
    pairs = extract_operations(module)
    ops = []
    for op, func in pairs:
        op.callable = func
        ops.append(op)
    hooks = extract_hooks(module)
    targets = [op.name for op in ops if op.type == "check"]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="data_flow_demo", targets=targets, cleanup=True),
        hooks=hooks,
    )
    return {op.name: op for op in ops}, defn


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

def test_can_load_demo_module():
    """The demo module loads and extracts operations without error."""
    ops_by_name, defn = _load_demo_ops()
    assert len(ops_by_name) == 4
    assert "provision_vm" in ops_by_name
    assert "configure_vm" in ops_by_name
    assert "verify_vm" in ops_by_name
    assert "deprovision_vm" in ops_by_name


def test_operation_types():
    """Each operation has the correct type."""
    ops_by_name, _ = _load_demo_ops()
    assert ops_by_name["provision_vm"].type == "action"
    assert ops_by_name["configure_vm"].type == "action"
    assert ops_by_name["verify_vm"].type == "check"
    assert ops_by_name["deprovision_vm"].type == "cleanup"


def test_state_dependencies():
    """Operations declare the correct provides/requires/clears."""
    ops_by_name, _ = _load_demo_ops()
    assert "vm.active" in ops_by_name["provision_vm"].provides
    assert "vm.active" in ops_by_name["configure_vm"].requires
    assert "vm.configured" in ops_by_name["configure_vm"].provides
    assert "vm.configured" in ops_by_name["verify_vm"].requires
    assert "vm.active" in ops_by_name["deprovision_vm"].clears
    assert "vm.configured" in ops_by_name["deprovision_vm"].clears


def test_callables_accept_params_and_env():
    """Callables have the two-argument signature (params, env)."""
    ops_by_name, _ = _load_demo_ops()
    import inspect
    for op_name, op in ops_by_name.items():
        sig = inspect.signature(op.callable)
        params = list(sig.parameters.keys())
        assert params == ["params", "env"], (
            f"{op_name} expected ['params', 'env'], got {params}"
        )


# ---------------------------------------------------------------------------
# Step-by-step data flow
# ---------------------------------------------------------------------------

def test_provision_vm_writes_data_to_env():
    """provision_vm writes runtime data (uuid, ip) to vm.active node."""
    ops_by_name, _ = _load_demo_ops()
    env = Env()
    result, modifier = run_step(ops_by_name["provision_vm"], {}, env)
    assert result.status == "pass"
    assert modifier is None

    node = env._get_node("vm.active")
    assert node is not None
    assert node.value is not None
    assert node.value["name"] == "test-vm-01"
    assert node.value["uuid"].startswith("test-vm-01-")
    assert node.value["ip"].startswith("10.0.0.")


def test_configure_vm_reads_data_written_by_provision():
    """configure_vm can read what provision_vm wrote on vm.active."""
    ops_by_name, _ = _load_demo_ops()

    env = Env()
    run_step(ops_by_name["provision_vm"], {}, env)
    env.set("vm.active")  # simulate state activation from apply_operation

    result, modifier = run_step(ops_by_name["configure_vm"], {}, env)
    assert result.status == "pass"

    node = env._get_node("vm.configured")
    assert node is not None
    assert node.value is not None
    assert len(node.value["config_hash"]) == 12


def test_verify_vm_reads_data_from_both_steps():
    """verify_vm can read data from both vm.active and vm.configured."""
    ops_by_name, _ = _load_demo_ops()

    env = Env()
    run_step(ops_by_name["provision_vm"], {}, env)
    env.set("vm.active")
    run_step(ops_by_name["configure_vm"], {}, env)
    env.set("vm.configured")

    result, modifier = run_step(ops_by_name["verify_vm"], {}, env)
    assert result.status == "pass"


def test_deprovision_vm_reads_uuid_from_env():
    """deprovision_vm reads the UUID from env to clean up the right VM."""
    ops_by_name, _ = _load_demo_ops()

    env = Env()
    run_step(ops_by_name["provision_vm"], {}, env)
    env.set("vm.active")

    result, modifier = run_step(ops_by_name["deprovision_vm"], {}, env)
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_configure_vm_fails_without_provision_data():
    """configure_vm raises if vm.active has no runtime data."""
    ops_by_name, _ = _load_demo_ops()

    env = Env()
    env.set("vm.active")  # state is active but no value was set

    result, _ = run_step(ops_by_name["configure_vm"], {}, env)
    assert result.status == "fail"
    assert "no runtime data" in result.error.lower()


# ---------------------------------------------------------------------------
# Multi-instance isolation
# ---------------------------------------------------------------------------

def test_two_vms_have_independent_values():
    """Two instances of the same operation produce independent values."""
    ops_by_name, _ = _load_demo_ops()

    env = Env()
    # Provision vm-a
    result_a, _ = run_step(ops_by_name["provision_vm"], {"vm_name": "vm-a"}, env)
    assert result_a.status == "pass"
    vm_a_data = env._get_node("vm.active").value
    assert vm_a_data["name"] == "vm-a"

    # The value for vm-a should be on vm.active
    # (In a multi-instance scenario you'd have vm.active.vm-a and vm.active.vm-b
    # with instance-param-rendered state paths; here we just verify two sequential
    # provisions with different params produce different data.)
    env_a = env.copy()
    env_a.clear("vm.active")

    env2 = Env()
    result_b, _ = run_step(ops_by_name["provision_vm"], {"vm_name": "vm-b"}, env2)
    assert result_b.status == "pass"
    vm_b_data = env2._get_node("vm.active").value
    assert vm_b_data["name"] == "vm-b"

    # The UUIDs should differ because vm_name differs
    assert vm_a_data["uuid"] != vm_b_data["uuid"]


# ---------------------------------------------------------------------------
# apply_operation preserves env values
# ---------------------------------------------------------------------------

def test_apply_operation_preserves_env_values():
    """apply_operation keeps values on copied nodes."""
    ops_by_name, _ = _load_demo_ops()

    env = Env()
    run_step(ops_by_name["provision_vm"], {}, env)

    new_env = apply_operation(env, ops_by_name["provision_vm"])
    assert new_env is not None
    node = new_env._get_node("vm.active")
    assert node.value is not None
    assert "uuid" in node.value


# ---------------------------------------------------------------------------
# Full graph test
# ---------------------------------------------------------------------------

def test_full_graph_generation_and_execution():
    """The framework generates and executes test cases with working data flow."""
    ops_by_name, defn = _load_demo_ops()

    graph = build_graph(defn.operations)
    assert graph.number_of_nodes() > 0

    cases = generate_cases(defn, graph)
    assert len(cases) >= 1

    # Every case should pass
    for case in cases:
        result = run_case(case, defn, graph=graph)
        assert result.status == "pass", (
            f"Case {case.case_id} failed: "
            + "; ".join(
                s.error for s in result.steps if s.status in ("fail", "error")
            )
        )


def test_case_steps_are_in_dependency_order():
    """The generated case runs provision → configure → verify in order."""
    ops_by_name, defn = _load_demo_ops()

    graph = build_graph(defn.operations)
    cases = generate_cases(defn, graph)

    provision_idx = None
    configure_idx = None
    verify_idx = None
    deprovision_idx = None

    result = run_case(cases[0], defn, graph=graph)
    for i, step in enumerate(result.steps):
        if step.operation == "provision_vm":
            provision_idx = i
        elif step.operation == "configure_vm":
            configure_idx = i
        elif step.operation == "verify_vm":
            verify_idx = i
        elif step.operation == "deprovision_vm":
            deprovision_idx = i

    assert provision_idx is not None
    assert configure_idx is not None
    assert verify_idx is not None
    assert deprovision_idx is not None
    assert provision_idx < configure_idx < verify_idx < deprovision_idx


# ---------------------------------------------------------------------------
# Value does NOT affect graph identity
# ---------------------------------------------------------------------------

def test_env_values_dont_affect_graph_equality():
    """Two envs with same structure but different values are equal in graph."""
    ops_by_name, _ = _load_demo_ops()

    env1 = Env()
    run_step(ops_by_name["provision_vm"], {"vm_name": "vm-a"}, env1)

    env2 = Env()
    run_step(ops_by_name["provision_vm"], {"vm_name": "vm-b"}, env2)

    # Both have vm.active in the boolean structure
    env1.set("vm.active")
    env2.set("vm.active")

    assert env1 == env2
    assert hash(env1) == hash(env2)
    # But values differ
    assert env1._get_node("vm.active").value["name"] == "vm-a"
    assert env2._get_node("vm.active").value["name"] == "vm-b"


# ---------------------------------------------------------------------------
# Params are not polluted
# ---------------------------------------------------------------------------

def test_params_are_not_polluted_by_env_data():
    """The params dict stays clean — env data lives on env nodes, not in params."""
    ops_by_name, _ = _load_demo_ops()

    captured_params = {}

    def check_params(params, env):
        captured_params["keys"] = set(params.keys())
        captured_params["has_vm_data"] = "uuid" in params or "ip" in params

    op = Operation(
        name="check_params", type="check",
        requires=["vm.active", "vm.configured"],
        callable=check_params,
    )

    env = Env()
    env.set("vm.active")
    env.set_value("vm.active", {"uuid": "abc", "ip": "10.0.0.1"})
    env.set("vm.configured")
    env.set_value("vm.configured", {"config_hash": "deadbeef"})

    result, _ = run_step(op, {"vm_name": "test-vm-01"}, env)
    assert result.status == "pass"
    assert captured_params["has_vm_data"] is False, (
        "Env data leaked into params dict"
    )
    assert captured_params["keys"] == {"vm_name"}
