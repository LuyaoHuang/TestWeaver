import textwrap
import tempfile
from pathlib import Path

from testweaver.decorators import action, check, cleanup, setup, provides, requires, clears
from testweaver.loader import load_module, extract_operations, load_operations_from_modules
from testweaver.schema import Operation, TestDefinition, TestSuite, load_definition
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
