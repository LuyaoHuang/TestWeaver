import textwrap
import tempfile
from pathlib import Path

from testweaver.decorators import (
    action, check, cleanup, setup, provides, requires, clears,
    excludes, graft, cut, priority,
)
from testweaver.env import Env
from testweaver.loader import load_module, extract_operations, load_operations_from_modules
from testweaver.schema import GraftDef, Operation, TestDefinition, TestSuite, load_definition
from testweaver.graph import build_graph, generate_cases


# --- Decorator metadata tests ---

def test_action_decorator():
    @action
    def my_op(params):
        pass
    assert my_op._tw_meta['type'] == 'action'


def test_check_decorator():
    @check
    def my_op(params):
        pass
    assert my_op._tw_meta['type'] == 'check'


def test_cleanup_decorator():
    @cleanup
    def my_op(params):
        pass
    assert my_op._tw_meta['type'] == 'cleanup'


def test_setup_decorator():
    @setup
    def my_op(params):
        pass
    assert my_op._tw_meta['type'] == 'setup'


def test_provides_decorator():
    @provides('a', 'b')
    def my_op(params):
        pass
    assert my_op._tw_meta['provides'] == ['a', 'b']


def test_requires_decorator():
    @requires('x')
    def my_op(params):
        pass
    assert my_op._tw_meta['requires'] == ['x']


def test_clears_decorator():
    @clears('x', 'y')
    def my_op(params):
        pass
    assert my_op._tw_meta['clears'] == ['x', 'y']


def test_stacked_decorators():
    @action
    @provides('file.exists')
    @requires('dir.exists')
    def create_file(params):
        """Create a file"""
        pass

    meta = create_file._tw_meta
    assert meta['type'] == 'action'
    assert meta['provides'] == ['file.exists']
    assert meta['requires'] == ['dir.exists']
    assert create_file.__doc__ == "Create a file"


# --- Module loading tests ---

def _write_module(tmp_path, filename, code):
    p = tmp_path / filename
    p.write_text(textwrap.dedent(code))
    return p


def test_load_module_and_extract(tmp_path):
    mod_file = _write_module(tmp_path, "ops.py", """\
        from testweaver import action, check, cleanup, provides, requires, clears

        @action
        @provides('ready')
        def do_setup(params):
            "Set things up"
            pass

        @check
        @requires('ready')
        def verify(params):
            "Check things"
            pass

        @cleanup
        @requires('ready')
        @clears('ready')
        def teardown(params):
            "Clean up"
            pass

        def helper():
            "Not decorated, should be skipped"
            pass
    """)
    module = load_module(mod_file)
    op_pairs = extract_operations(module)
    assert len(op_pairs) == 3

    ops = {op.name: (op, func) for op, func in op_pairs}
    assert 'do_setup' in ops
    assert 'verify' in ops
    assert 'teardown' in ops
    assert 'helper' not in ops

    setup_op, _ = ops['do_setup']
    assert setup_op.type == 'action'
    assert setup_op.provides == ['ready']
    assert setup_op.requires == []

    verify_op, _ = ops['verify']
    assert verify_op.type == 'check'
    assert verify_op.requires == ['ready']

    teardown_op, _ = ops['teardown']
    assert teardown_op.type == 'cleanup'
    assert teardown_op.clears == ['ready']


# --- End-to-end: modules -> graph -> cases ---

def test_module_based_case_generation(tmp_path):
    mod_file = _write_module(tmp_path, "ops.py", """\
        from testweaver import action, check, cleanup, provides, requires, clears

        @action
        @provides('ready')
        def setup_a(params):
            pass

        @action
        @provides('ready')
        def setup_b(params):
            pass

        @check
        @requires('ready')
        def verify(params):
            pass

        @cleanup
        @requires('ready')
        @clears('ready')
        def teardown(params):
            pass
    """)

    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(textwrap.dedent(f"""\
        modules:
          - ops.py

        suite:
          name: "test"
          targets: [verify]
          cleanup: true
    """))

    defn = load_definition(yaml_file)
    assert len(defn.operations) == 4

    graph = build_graph(defn.operations)
    cases = generate_cases(defn, graph)
    assert len(cases) == 2

    step_sets = {tuple(c.steps) for c in cases}
    assert ('setup_a', 'verify') in step_sets
    assert ('setup_b', 'verify') in step_sets

    for case in cases:
        assert case.cleanup_steps == ['teardown']


def test_module_ops_have_callable(tmp_path):
    mod_file = _write_module(tmp_path, "ops.py", """\
        from testweaver import action, provides

        @action
        @provides('x')
        def my_action(params):
            pass
    """)

    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        modules:
          - ops.py

        suite:
          name: "test"
          targets: [my_action]
          cleanup: false
    """))

    defn = load_definition(yaml_file)
    op = defn.operations[0]
    assert op.callable is not None


def test_mixed_yaml_and_module_ops(tmp_path):
    mod_file = _write_module(tmp_path, "ops.py", """\
        from testweaver import action, provides

        @action
        @provides('ready')
        def from_module(params):
            pass
    """)

    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        modules:
          - ops.py

        operations:
          - name: from_yaml
            type: check
            requires: [ready]
            run: "echo ok"
          - name: cleanup_yaml
            type: cleanup
            requires: [ready]
            clears: [ready]
            run: "echo cleanup"

        suite:
          name: "mixed"
          targets: [from_yaml]
          cleanup: true
    """))

    defn = load_definition(yaml_file)
    names = {op.name for op in defn.operations}
    assert 'from_yaml' in names
    assert 'from_module' in names
    assert 'cleanup_yaml' in names

    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].steps == ['from_module', 'from_yaml']


def test_backward_compat_yaml_only():
    """Pure YAML definitions still work."""
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="test", targets=["check"]),
    )
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].steps == ["setup", "check"]


# --- Env class tests ---

def test_env_set_and_is_active():
    env = Env()
    env.set('vm.config')
    assert env.is_active('vm.config')
    assert env.is_active('vm')  # parent active due to child
    assert not env.is_active('vm.active')


def test_env_hierarchical_active():
    env = Env()
    env.set('vm.config.tpm.vtpm')
    assert env.is_active('vm.config.tpm.vtpm')
    assert env.is_active('vm.config.tpm')
    assert env.is_active('vm.config')
    assert env.is_active('vm')
    assert not env.is_active('vm.active')


def test_env_unset():
    env = Env()
    env.set('a.b')
    env.set('a.b.c')
    env.unset('a.b')
    # a.b.data is now False, but a.b.c is still active,
    # so a.b is still "active" hierarchically (has active children)
    assert env.is_active('a.b')
    assert env.is_active('a.b.c')
    # Unsetting a leaf fully deactivates it
    env.unset('a.b.c')
    assert not env.is_active('a.b.c')
    assert not env.is_active('a.b')


def test_env_clear_removes_subtree():
    env = Env()
    env.set('vm.config.tpm')
    env.set('vm.config.disk')
    env.clear('vm.config')
    assert not env.is_active('vm.config')
    assert not env.is_active('vm.config.tpm')
    assert not env.is_active('vm.config.disk')


def test_env_graft():
    env = Env()
    env.set('vm.config')
    env.set('vm.config.tpm')
    env.graft('vm.config', 'vm.active')
    assert env.is_active('vm.active')
    assert env.is_active('vm.active.tpm')
    assert env.is_active('vm.config')  # source unchanged


def test_env_equality_and_hash():
    env1 = Env()
    env1.set('a')
    env1.set('b')
    env2 = Env()
    env2.set('b')
    env2.set('a')
    assert env1 == env2
    assert hash(env1) == hash(env2)


def test_env_subset():
    small = Env.from_states(['a'])
    big = Env.from_states(['a', 'b'])
    assert small <= big
    assert not big <= small


def test_env_from_states():
    env = Env.from_states(['x.y', 'a.b.c'])
    assert env.is_active('x.y')
    assert env.is_active('a.b.c')
    assert env.is_active('x')
    assert env.is_active('a.b')


def test_env_to_flat_set():
    env = Env()
    env.set('a')
    env.set('b.c')
    flat = env.to_flat_set()
    assert 'a' in flat
    assert 'b.c' in flat


# --- New decorator tests ---

def test_excludes_decorator():
    @excludes('file.exists')
    def my_op(params):
        pass
    assert my_op._tw_meta['excludes'] == ['file.exists']


def test_graft_decorator():
    @graft('vm.config', 'vm.active')
    def my_op(params):
        pass
    assert my_op._tw_meta['grafts'] == [{'src': 'vm.config', 'tgt': 'vm.active'}]


def test_cut_decorator():
    @cut('vm.active')
    def my_op(params):
        pass
    assert my_op._tw_meta['cuts'] == ['vm.active']


# --- Graph tests with new features ---

def test_excludes_prevents_duplicate():
    """excludes prevents running an op when state already exists."""
    ops = [
        Operation(name="create", type="action", provides=["file"],
                  excludes=["file"]),
        Operation(name="check", type="check", requires=["file"]),
        Operation(name="remove", type="cleanup", requires=["file"],
                  clears=["file"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="test", targets=["check"]),
    )
    graph = build_graph(ops)
    # create can only run once because excludes prevents it when file exists
    assert graph.number_of_nodes() == 2
    assert graph.number_of_edges() == 2  # create and remove


def test_graft_in_graph():
    """Graft copies subtree during state transition."""
    ops = [
        Operation(name="define", type="action", provides=["vm.config"]),
        Operation(
            name="start", type="action",
            requires=["vm.config"], excludes=["vm.active"],
            grafts=[GraftDef(src="vm.config", tgt="vm.active")],
        ),
        Operation(name="check", type="check", requires=["vm.active"]),
        Operation(
            name="destroy", type="cleanup",
            requires=["vm.active"],
            cuts=["vm.active"],
        ),
        Operation(
            name="undefine", type="cleanup",
            requires=["vm.config"], excludes=["vm.active"],
            cuts=["vm.config"],
        ),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="test", targets=["check"]),
    )
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].steps == ["define", "start", "check"]


def test_cut_removes_subtree_in_graph():
    """Cut removes state and all children."""
    ops = [
        Operation(name="setup_a", type="action", provides=["x.a"]),
        Operation(name="setup_b", type="action", provides=["x.b"],
                  requires=["x.a"]),
        Operation(name="check", type="check", requires=["x.b"]),
        Operation(name="cleanup", type="cleanup", requires=["x"],
                  cuts=["x"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="test", targets=["check"]),
    )
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].steps == ["setup_a", "setup_b", "check"]
    assert cases[0].cleanup_steps == ["cleanup"]


def test_hierarchical_requires():
    """Requiring 'a' is satisfied by setting 'a.child'."""
    ops = [
        Operation(name="setup", type="action", provides=["parent.child"]),
        Operation(name="check", type="check", requires=["parent"]),
        Operation(name="cleanup", type="cleanup", requires=["parent"],
                  cuts=["parent"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="test", targets=["check"]),
    )
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].steps == ["setup", "check"]


def test_priority_decorator():
    @priority(5)
    def my_op(params):
        pass
    assert my_op._tw_meta['priority'] == 5


def test_priority_stacked_with_action():
    @action
    @priority(3)
    @provides('x')
    def my_op(params):
        pass
    meta = my_op._tw_meta
    assert meta['type'] == 'action'
    assert meta['priority'] == 3
    assert meta['provides'] == ['x']


def test_priority_extracted_by_loader():
    src = textwrap.dedent("""\
        from testweaver import action, provides, priority

        @action
        @priority(7)
        @provides('state.ready')
        def important_op(params):
            pass
    """)
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write(src)
        f.flush()
        module = load_module(f.name)
        pairs = extract_operations(module)
    assert len(pairs) == 1
    op, _ = pairs[0]
    assert op.priority == 7
