"""Tests for runtime data passing between operations via Env node values."""
from __future__ import annotations

from testweaver.decorators import state_data
from testweaver.engine import run_case, run_step
from testweaver.env import Env
from testweaver.graph import apply_operation, generate_cases
from testweaver.schema import (
    Operation,
    StateData,
    TestCase,
    TestDefinition,
    TestSuite,
)


def _make_definition(operations, targets, **kwargs):
    return TestDefinition(
        operations=operations,
        suite=TestSuite(name="test", targets=targets, **kwargs),
    )


# ---------------------------------------------------------------------------
# Env value field
# ---------------------------------------------------------------------------

def test_env_value_not_in_hash():
    """Two envs with same boolean structure but different values are equal."""
    e1 = Env()
    e1.set('vm.active')
    e1.set_value('vm.active', {'uuid': 'abc'})

    e2 = Env()
    e2.set('vm.active')
    e2.set_value('vm.active', {'uuid': 'xyz'})

    assert e1 == e2
    assert hash(e1) == hash(e2)
    assert e1._get_node('vm.active').value == {'uuid': 'abc'}
    assert e2._get_node('vm.active').value == {'uuid': 'xyz'}


def test_env_value_survives_copy():
    """Deep copy preserves values."""
    e = Env()
    e.set('vm.active')
    e.set_value('vm.active', {'uuid': 'abc'})
    e2 = e.copy()
    assert e2._get_node('vm.active').value == {'uuid': 'abc'}


def test_env_clear_resets_value():
    """Clearing a node resets its value and children."""
    e = Env()
    e.set('vm.active')
    e.set_value('vm.active', {'uuid': 'abc'})
    e.clear('vm.active')
    node = e._get_node('vm.active')
    assert node is not None
    assert node.value is None
    assert node.children == {}
    assert node.data is False


def test_env_graft_copies_value():
    """Graft copies the source node's value to the target."""
    e = Env()
    e.set('vm.config.cpu')
    e.set_value('vm.config.cpu', {'cores': 4})
    e.graft('vm.config', 'vm.active')
    assert e._get_node('vm.active.cpu').value == {'cores': 4}


def test_env_set_value_creates_intermediate_nodes():
    """set_value creates intermediate nodes as needed."""
    e = Env()
    e.set_value('a.b.c', {'key': 'val'})
    node = e._get_node('a.b.c')
    assert node is not None
    assert node.value == {'key': 'val'}


def test_env_value_isolation_multi_instance():
    """Values on different instance paths are independent."""
    e = Env()
    e.set('vm.active.TPM:tpm0.init')
    e.set('vm.active.TPM:tpm1.init')
    e.set_value('vm.active.TPM:tpm0.init', {'uuid': 'uuid0'})
    e.set_value('vm.active.TPM:tpm1.init', {'uuid': 'uuid1'})

    assert e._get_node('vm.active.TPM:tpm0.init').value == {'uuid': 'uuid0'}
    assert e._get_node('vm.active.TPM:tpm1.init').value == {'uuid': 'uuid1'}


# ---------------------------------------------------------------------------
# StateData model
# ---------------------------------------------------------------------------

def test_state_data_construction():
    sd = StateData(values={'vm.active': {'uuid': 'abc'}})
    assert sd.values['vm.active']['uuid'] == 'abc'


def test_state_data_empty():
    sd = StateData()
    assert sd.values == {}


# ---------------------------------------------------------------------------
# run_step: env.set_value() (side-effect pattern)
# ---------------------------------------------------------------------------

def test_run_step_callable_receives_env():
    """Callable receives env as second argument and can write to it."""
    captured_env = {}

    def producer(params, env):
        captured_env['env'] = env
        env.set_value('vm.active', {'uuid': 'abc'})

    op = Operation(
        name='create', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, modifier = run_step(op, {}, env)
    assert result.status == 'pass'
    assert modifier is None
    assert captured_env['env'] is env
    assert env._get_node('vm.active').value == {'uuid': 'abc'}


def test_run_step_env_writes_data_for_next_step():
    """Data written to env persists for the next step to read."""
    received = {}

    def writer(params, env):
        env.set_value('vm.active', {'uuid': 'test-123'})

    def reader(params, env):
        node = env._get_node('vm.active')
        received['data'] = node.value

    env = Env()
    env.set('vm.active')
    result1, _ = run_step(
        Operation(name='write', type='action', provides=['vm.active'], callable=writer),
        {}, env,
    )
    assert result1.status == 'pass'

    result2, _ = run_step(
        Operation(name='read', type='check', requires=['vm.active'], callable=reader),
        {}, env,
    )
    assert result2.status == 'pass'
    assert received['data'] == {'uuid': 'test-123'}


# ---------------------------------------------------------------------------
# run_step: StateData return value (declarative pattern)
# ---------------------------------------------------------------------------

def test_run_step_state_data_return_applies_to_env():
    """Returning StateData from a callable applies values to env nodes."""
    def producer(params, env):
        return StateData(values={'vm.active': {'uuid': 'abc', 'ip': '10.0.0.1'}})

    op = Operation(
        name='create', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, modifier = run_step(op, {}, env)
    assert result.status == 'pass'
    assert modifier is None
    assert env._get_node('vm.active').value == {'uuid': 'abc', 'ip': '10.0.0.1'}


def test_run_step_state_data_recorded_on_result():
    """StateData values are recorded on StepResult.env_data for tracking."""
    def producer(params, env):
        return state_data({'vm.active': {'uuid': 'tracked-123'}})

    op = Operation(
        name='create', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, _ = run_step(op, {}, env)
    assert result.env_data == {'vm.active': {'uuid': 'tracked-123'}}


def test_run_step_state_data_auto_maps_keyword_style():
    """Keyword-style state_data auto-maps to the single provides path."""
    def producer(params, env):
        return state_data(uuid='abc', ip='10.0.0.1')

    op = Operation(
        name='create', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, _ = run_step(op, {}, env)
    assert env._get_node('vm.active').value == {'uuid': 'abc', 'ip': '10.0.0.1'}
    assert result.env_data == {'vm.active': {'uuid': 'abc', 'ip': '10.0.0.1'}}


def test_run_step_state_data_multi_provides_no_auto_map():
    """With multiple provides, keyword-style data is NOT auto-mapped."""
    def producer(params, env):
        return state_data(uuid='abc')

    op = Operation(
        name='setup', type='action', provides=['vm.active', 'vm.config'],
        callable=producer,
    )
    env = Env()
    result, _ = run_step(op, {}, env)
    assert result.status == 'pass'
    # Keyword-style data without path keys on multi-provides → applied as-is
    # (engine doesn't auto-map because the target is ambiguous)
    assert result.env_data == {'uuid': 'abc'}


def test_run_step_state_data_explicit_paths_bypass_auto_map():
    """Explicit path keys in StateData skip auto-mapping entirely."""
    def producer(params, env):
        return state_data({'vm.active': {'uuid': 'abc'}, 'tpm': {'ver': '2'}})

    op = Operation(
        name='setup', type='action', provides=['vm.active', 'tpm'],
        callable=producer,
    )
    env = Env()
    result, _ = run_step(op, {}, env)
    assert env._get_node('vm.active').value == {'uuid': 'abc'}
    assert env._get_node('tpm').value == {'ver': '2'}
    assert result.env_data == {'vm.active': {'uuid': 'abc'}, 'tpm': {'ver': '2'}}


def test_run_step_state_data_does_not_conflict_with_modifier():
    """StateData and modifier returns are independent — both work."""
    from testweaver.modifiers import EdgeGuard

    # Can't return both at once, but StateData in one step and
    # EdgeGuard in another won't interfere
    def producer(params, env):
        return StateData(values={'vm.active': {'uuid': 'abc'}})

    op = Operation(
        name='create', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, modifier = run_step(op, {}, env)
    assert result.status == 'pass'
    assert modifier is None
    assert result.env_data is not None


def test_run_step_both_set_value_and_state_data():
    """A callable can use env.set_value() AND return StateData — both apply."""
    def producer(params, env):
        env.set_value('vm.active', {'from_set': 1})
        return state_data({'vm.active': {'from_return': 2}})

    op = Operation(
        name='create', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, _ = run_step(op, {}, env)
    assert result.status == 'pass'
    # Last write wins — StateData is applied after env.set_value()
    assert env._get_node('vm.active').value == {'from_return': 2}


def test_run_step_no_state_data_when_not_returned():
    """StepResult.env_data is None when no StateData is returned."""
    def producer(params, env):
        pass

    op = Operation(
        name='noop', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, _ = run_step(op, {}, env)
    assert result.status == 'pass'
    assert result.env_data is None


def test_run_step_callable_failure_ignores_state_data():
    """StateData returned by a failing callable is ignored."""
    def producer(params, env):
        raise RuntimeError("boom")
        return state_data(uuid='abc')

    op = Operation(
        name='fail', type='action', provides=['vm.active'],
        callable=producer,
    )
    env = Env()
    result, _ = run_step(op, {}, env)
    assert result.status == 'fail'
    assert result.env_data is None


# ---------------------------------------------------------------------------
# Full case execution with data flow (StateData pattern)
# ---------------------------------------------------------------------------

def test_full_data_flow():
    """Data produced by setup is available to check via env node values."""
    received = {}

    def setup_fn(params, env):
        return state_data({'vm.active': {'uuid': 'test-vm-abc'}})

    def check_fn(params, env):
        node = env._get_node('vm.active')
        received['uuid'] = node.value['uuid'] if node and node.value else None

    ops = [
        Operation(
            name='create_vm', type='action', provides=['vm.active'],
            callable=setup_fn,
        ),
        Operation(
            name='verify_vm', type='check', requires=['vm.active'],
            callable=check_fn,
        ),
    ]
    defn = _make_definition(ops, ['verify_vm'], cleanup=False)
    cases = generate_cases(defn)
    assert len(cases) == 1

    result = run_case(cases[0], defn)
    assert result.status == 'pass'
    assert received['uuid'] == 'test-vm-abc'


def test_data_flow_multi_step():
    """Data produced in step 1 is available in step 2 and step 3."""
    received_2 = {}
    received_3 = {}

    def setup_fn(params, env):
        return StateData(values={'vm.active': {'uuid': 'abc'}})

    def middle_fn(params, env):
        node = env._get_node('vm.active')
        received_2['uuid'] = node.value['uuid'] if node and node.value else None
        return StateData(values={'vm.active': {'uuid': 'abc', 'state': 'running'}})

    def check_fn(params, env):
        node = env._get_node('vm.active')
        received_3['state'] = node.value['state'] if node and node.value else None

    ops = [
        Operation(
            name='create', type='action', provides=['vm.active'],
            callable=setup_fn,
        ),
        Operation(
            name='start', type='action', provides=['vm.running'],
            requires=['vm.active'],
            callable=middle_fn,
        ),
        Operation(
            name='verify', type='check', requires=['vm.running'],
            callable=check_fn,
        ),
    ]
    defn = _make_definition(ops, ['verify'], cleanup=False)
    cases = generate_cases(defn)
    assert len(cases) >= 1

    result = run_case(cases[0], defn)
    assert result.status == 'pass'
    assert received_2['uuid'] == 'abc'
    assert received_3['state'] == 'running'


def test_data_flow_multi_instance_isolation():
    """Each instance gets its own independent values."""
    tpm0_data = {}
    tpm1_data = {}

    def attach_tpm0(params, env):
        return StateData(values={
            'vm.active.TPM:tpm0.init': {'uuid': 'tpm-uuid-0'},
        })

    def attach_tpm1(params, env):
        return StateData(values={
            'vm.active.TPM:tpm1.init': {'uuid': 'tpm-uuid-1'},
        })

    def check_fn(params, env):
        n0 = env._get_node('vm.active.TPM:tpm0.init')
        n1 = env._get_node('vm.active.TPM:tpm1.init')
        tpm0_data['uuid'] = n0.value['uuid'] if n0 and n0.value else None
        tpm1_data['uuid'] = n1.value['uuid'] if n1 and n1.value else None

    ops = [
        Operation(
            name='attach_tpm0', type='action',
            provides=['vm.active.TPM:tpm0.init'],
            callable=attach_tpm0,
        ),
        Operation(
            name='attach_tpm1', type='action',
            provides=['vm.active.TPM:tpm1.init'],
            requires=['vm.active.TPM:tpm0.init'],
            callable=attach_tpm1,
        ),
        Operation(
            name='verify_both', type='check',
            requires=['vm.active.TPM:tpm0.init', 'vm.active.TPM:tpm1.init'],
            callable=check_fn,
        ),
    ]
    defn = _make_definition(ops, ['verify_both'], cleanup=False)
    cases = generate_cases(defn)
    assert len(cases) == 1

    result = run_case(cases[0], defn)
    assert result.status == 'pass'
    assert tpm0_data['uuid'] == 'tpm-uuid-0'
    assert tpm1_data['uuid'] == 'tpm-uuid-1'


def test_env_value_not_leaked_to_params():
    """Env values are NOT injected into params dict (callables read env directly)."""
    received = {}

    def setup_fn(params, env):
        return state_data({'vm.active': {'uuid': 'secret'}})

    def check_fn(params, env):
        received['has_env_key'] = 'vm.active' in params or '__env' in str(params)

    ops = [
        Operation(
            name='create', type='action', provides=['vm.active'],
            callable=setup_fn,
        ),
        Operation(
            name='verify', type='check', requires=['vm.active'],
            callable=check_fn,
        ),
    ]
    defn = _make_definition(ops, ['verify'], cleanup=False)
    cases = generate_cases(defn)
    result = run_case(cases[0], defn)
    assert result.status == 'pass'
    assert received['has_env_key'] is False


# ---------------------------------------------------------------------------
# state_data helper function
# ---------------------------------------------------------------------------

def test_state_data_helper_with_dict():
    sd = state_data({'vm.active': {'uuid': 'abc'}, 'tpm': {'ver': '2'}})
    assert isinstance(sd, StateData)
    assert sd.values['vm.active'] == {'uuid': 'abc'}
    assert sd.values['tpm'] == {'ver': '2'}


def test_state_data_helper_with_kwargs():
    sd = state_data(uuid='abc', ip='10.0.0.1')
    assert isinstance(sd, StateData)
    assert sd.values == {'uuid': 'abc', 'ip': '10.0.0.1'}


# ---------------------------------------------------------------------------
# Graph: apply_operation preserves existing env values
# ---------------------------------------------------------------------------

def test_apply_operation_preserves_values():
    """Values on the input env survive apply_operation."""
    env = Env()
    env.set('existing.state')
    env.set_value('existing.state', {'key': 'val'})

    op = Operation(name='add', type='action', provides=['new.state'])
    new_env = apply_operation(env, op)

    assert new_env is not None
    assert new_env._get_node('existing.state').value == {'key': 'val'}
    assert new_env._get_node('new.state') is not None


# ---------------------------------------------------------------------------
# env-aware callable reading data from prior steps in full case
# ---------------------------------------------------------------------------

def test_callable_reads_env_value_in_full_case():
    """A callable in a full case run can read env values set by prior steps."""
    received = {}

    def setup_fn(params, env):
        return state_data({'vm.active': {'uuid': 'implicit-vm', 'cores': 4}})

    def check_fn(params, env):
        node = env._get_node('vm.active')
        received['data'] = node.value

    ops = [
        Operation(
            name='create', type='action', provides=['vm.active'],
            callable=setup_fn,
        ),
        Operation(
            name='verify', type='check', requires=['vm.active'],
            callable=check_fn,
        ),
    ]
    defn = _make_definition(ops, ['verify'], cleanup=False)
    cases = generate_cases(defn)
    result = run_case(cases[0], defn)
    assert result.status == 'pass'
    assert received['data'] == {'uuid': 'implicit-vm', 'cores': 4}
