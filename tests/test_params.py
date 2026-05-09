import textwrap
from pathlib import Path

from testweaver.decorators import (
    action, check, cleanup, provides, requires, clears,
    excludes, when_param, unless_param, skip_when,
)
from testweaver.schema import (
    Operation, TestCase, TestDefinition, TestSuite,
    ParamChoice, ParamAxis, ParamConstraint, ParamMatrix,
    GraftDef,
)
from testweaver.graph import (
    build_graph, generate_cases, _expand_param_choices,
)
from testweaver.matrix import expand_matrix, get_skip_ops


# --- Decorator tests ---

def test_when_param_decorator():
    @when_param('backend', 'emulator')
    def my_op(params):
        pass
    assert 'params.backend.emulator' in my_op._tw_meta['requires']


def test_unless_param_decorator():
    @unless_param('mode', 'passthrough')
    def my_op(params):
        pass
    assert 'params.mode.passthrough' in my_op._tw_meta['excludes']


def test_skip_when_decorator():
    @skip_when(backend='passthrough')
    def my_op(params):
        pass
    assert my_op._tw_meta['skip_when'] == [{'backend': 'passthrough'}]


def test_skip_when_multiple():
    @skip_when(backend='passthrough')
    @skip_when(mode='legacy')
    def my_op(params):
        pass
    assert len(my_op._tw_meta['skip_when']) == 2


# --- ParamChoice / expand tests ---

def test_expand_param_choices_single():
    choices = [ParamChoice(name='color', values=['red', 'blue'])]
    ops = _expand_param_choices(choices)
    assert len(ops) == 2
    assert ops[0].name == '__set_param_color_red'
    assert ops[0].provides == ['params.color.red']
    assert 'params.color.blue' in ops[0].excludes
    assert 'params.color.red' in ops[0].excludes


def test_expand_param_choices_mutual_exclusion():
    choices = [ParamChoice(name='x', values=['a', 'b', 'c'])]
    ops = _expand_param_choices(choices)
    assert len(ops) == 3
    for op in ops:
        provided = op.provides[0]
        for other_op in ops:
            if other_op is not op:
                assert provided in other_op.excludes


# --- Approach 1: Parameter Graph ---

def test_param_graph_generates_variants():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="teardown", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[ParamChoice(name="mode", values=["fast", "slow"])],
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) == 2
    modes = {c.params.get('mode') for c in cases}
    assert modes == {'fast', 'slow'}
    for case in cases:
        assert case.steps == ['setup', 'check']
        assert not any(s.startswith('__set_param_') for s in case.steps)


def test_param_graph_gates_operations():
    ops = [
        Operation(name="common_setup", type="action", provides=["base"]),
        Operation(
            name="special_setup", type="action",
            requires=["base", "params.mode.special"],
            provides=["extra"],
        ),
        Operation(name="check_base", type="check", requires=["base"]),
        Operation(name="check_extra", type="check", requires=["extra"]),
        Operation(name="cleanup", type="cleanup", requires=["base"], clears=["base"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check_extra"],
            param_choices=[ParamChoice(name="mode", values=["normal", "special"])],
            cleanup=False,
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) >= 1
    for case in cases:
        assert case.params['mode'] == 'special'
        assert 'special_setup' in case.steps


def test_param_graph_case_ids_include_params():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="cleanup", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[ParamChoice(name="color", values=["red", "blue"])],
        ),
    )
    cases = generate_cases(defn)
    case_ids = {c.case_id for c in cases}
    assert any('color=red' in cid for cid in case_ids)
    assert any('color=blue' in cid for cid in case_ids)


def test_param_graph_two_axes():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="cleanup", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="x", values=["a", "b"]),
                ParamChoice(name="y", values=["1", "2"]),
            ],
        ),
    )
    cases = generate_cases(defn)
    combos = {(c.params['x'], c.params['y']) for c in cases}
    assert ('a', '1') in combos
    assert ('a', '2') in combos
    assert ('b', '1') in combos
    assert ('b', '2') in combos


# --- Approach 2: Parameter Matrix ---

def test_expand_matrix_simple():
    matrix = ParamMatrix(
        axes=[
            ParamAxis(name="x", values=[1, 2]),
            ParamAxis(name="y", values=["a", "b"]),
        ],
    )
    combos = expand_matrix(matrix)
    assert len(combos) == 4
    assert {"x": 1, "y": "a"} in combos
    assert {"x": 2, "y": "b"} in combos


def test_expand_matrix_with_exclude():
    matrix = ParamMatrix(
        axes=[
            ParamAxis(name="x", values=[1, 2, 3]),
        ],
        constraints=[
            ParamConstraint(when={"x": 2}, exclude=True, reason="skip x=2"),
        ],
    )
    combos = expand_matrix(matrix)
    assert len(combos) == 2
    assert {"x": 1} in combos
    assert {"x": 3} in combos


def test_get_skip_ops_from_constraints():
    constraints = [
        ParamConstraint(
            when={"backend": "passthrough"},
            skip_ops=["install_pkg", "uninstall_pkg"],
        ),
    ]
    skip = get_skip_ops({"backend": "passthrough"}, constraints)
    assert skip == {"install_pkg", "uninstall_pkg"}

    skip2 = get_skip_ops({"backend": "emulator"}, constraints)
    assert skip2 == set()


def test_get_skip_ops_from_operation_skip_when():
    ops = [
        Operation(
            name="install", type="action", provides=["pkg"],
            skip_when=[{"backend": "passthrough"}],
        ),
    ]
    skip = get_skip_ops({"backend": "passthrough"}, [], ops)
    assert "install" in skip

    skip2 = get_skip_ops({"backend": "emulator"}, [], ops)
    assert "install" not in skip2


def test_matrix_generates_per_combo_cases():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="cleanup", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_matrix=ParamMatrix(
                axes=[ParamAxis(name="size", values=[10, 20])],
            ),
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) == 2
    sizes = {c.params['size'] for c in cases}
    assert sizes == {10, 20}
    for case in cases:
        assert case.steps == ['setup', 'check']


def test_matrix_skips_ops_per_combo():
    ops = [
        Operation(name="base_setup", type="action", provides=["base"]),
        Operation(name="extra_setup", type="action", requires=["base"], provides=["extra"]),
        Operation(name="check_base", type="check", requires=["base"]),
        Operation(name="check_extra", type="check", requires=["extra"]),
        Operation(name="cleanup_base", type="cleanup", requires=["base"], clears=["base"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check_extra", "check_base"],
            param_matrix=ParamMatrix(
                axes=[ParamAxis(name="mode", values=["full", "minimal"])],
                constraints=[
                    ParamConstraint(
                        when={"mode": "minimal"},
                        skip_ops=["extra_setup", "check_extra"],
                    ),
                ],
            ),
            cleanup=False,
        ),
    )
    cases = generate_cases(defn)
    full_cases = [c for c in cases if c.params['mode'] == 'full']
    minimal_cases = [c for c in cases if c.params['mode'] == 'minimal']

    assert len(full_cases) >= 1
    extra_full = [c for c in full_cases if 'extra_setup' in c.steps]
    assert len(extra_full) >= 1

    for c in minimal_cases:
        assert 'extra_setup' not in c.steps


def test_matrix_case_ids_include_params():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="check", type="check", requires=["ready"]),
        Operation(name="cleanup", type="cleanup", requires=["ready"], clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_matrix=ParamMatrix(
                axes=[ParamAxis(name="x", values=["a", "b"])],
            ),
        ),
    )
    cases = generate_cases(defn)
    assert all('[' in c.case_id for c in cases)
    assert any('x=a' in c.case_id for c in cases)
    assert any('x=b' in c.case_id for c in cases)


# --- Mutual exclusion ---

def test_cannot_use_both_param_modes():
    import pytest
    with pytest.raises(ValueError, match="Cannot use both"):
        TestDefinition(
            operations=[
                Operation(name="s", type="action", provides=["x"]),
                Operation(name="c", type="check", requires=["x"]),
                Operation(name="t", type="cleanup", requires=["x"], clears=["x"]),
            ],
            suite=TestSuite(
                name="test",
                targets=["c"],
                param_choices=[ParamChoice(name="a", values=[1, 2])],
                param_matrix=ParamMatrix(
                    axes=[ParamAxis(name="b", values=[3, 4])],
                ),
            ),
        )


# --- TestCase.params backward compat ---

def test_testcase_params_defaults_empty():
    case = TestCase(case_id="test-1", steps=["a"], target="a")
    assert case.params == {}


# --- YAML loading with param_choices ---

def test_yaml_with_param_choices(tmp_path):
    mod_file = tmp_path / "ops.py"
    mod_file.write_text(textwrap.dedent("""\
        from testweaver import action, check, cleanup, provides, requires, clears, when_param

        @action
        @provides('ready')
        def setup(params):
            pass

        @action
        @when_param('feature', 'advanced')
        @requires('ready')
        @provides('advanced')
        def setup_advanced(params):
            pass

        @check
        @requires('ready')
        def check_basic(params):
            pass

        @cleanup
        @requires('ready')
        @clears('ready')
        def teardown(params):
            pass
    """))
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        modules:
          - ops.py

        suite:
          name: "param_test"
          targets: [check_basic]
          param_choices:
            - name: feature
              values: [basic, advanced]
          cleanup: true
    """))

    from testweaver.schema import load_definition
    defn = load_definition(yaml_file)
    cases = generate_cases(defn)
    assert len(cases) == 3
    features = {c.params['feature'] for c in cases}
    assert features == {'basic', 'advanced'}
    advanced_cases = [c for c in cases if c.params['feature'] == 'advanced']
    assert len(advanced_cases) == 2
    step_sets = {tuple(c.steps) for c in advanced_cases}
    assert ('setup', 'check_basic') in step_sets
    assert ('setup', 'setup_advanced', 'check_basic') in step_sets


# --- YAML loading with param_matrix ---

def test_yaml_with_param_matrix(tmp_path):
    mod_file = tmp_path / "ops.py"
    mod_file.write_text(textwrap.dedent("""\
        from testweaver import action, check, cleanup, provides, requires, clears

        @action
        @provides('ready')
        def setup(params):
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
    """))
    yaml_file = tmp_path / "test.yaml"
    yaml_file.write_text(textwrap.dedent("""\
        modules:
          - ops.py

        suite:
          name: "matrix_test"
          targets: [verify]
          param_matrix:
            axes:
              - name: size
                values: [10, 20, 30]
            constraints:
              - when: {size: 30}
                exclude: true
          cleanup: true
    """))

    from testweaver.schema import load_definition
    defn = load_definition(yaml_file)
    cases = generate_cases(defn)
    assert len(cases) == 2
    sizes = {c.params['size'] for c in cases}
    assert sizes == {10, 20}
