import textwrap
from itertools import combinations
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


# --- Instance expansion (additive mode) ---

from testweaver.graph import (
    _render_state_paths, _has_instance_templates, _expand_instance_choices,
)


def test_render_state_paths_basic():
    op = Operation(
        name="attach", type="action",
        provides=["vm.TPM:{tpm_id}.init"],
        requires=["vm.active"],
    )
    rendered = _render_state_paths(op, {"tpm_id": "tpm0"})
    assert rendered.provides == ["vm.TPM:tpm0.init"]
    assert rendered.requires == ["vm.active"]
    assert rendered.name == "attach"


def test_render_state_paths_no_templates():
    op = Operation(
        name="setup", type="action",
        provides=["vm.active"],
    )
    rendered = _render_state_paths(op, {"tpm_id": "tpm0"})
    assert rendered is op


def test_render_state_paths_sanitizes_dots():
    op = Operation(
        name="attach", type="action",
        provides=["dev.{dev_id}.ready"],
    )
    rendered = _render_state_paths(op, {"dev_id": "disk.0"})
    assert rendered.provides == ["dev.disk_0.ready"]


def test_has_instance_templates():
    op = Operation(
        name="attach", type="action",
        provides=["vm.TPM:{tpm_id}.init"],
    )
    assert _has_instance_templates(op, {"tpm_id"})
    assert not _has_instance_templates(op, {"disk_id"})


def test_expand_instance_choices_basic():
    ops = [
        Operation(
            name="attach", type="action",
            provides=["vm.TPM:{tpm_id}.init"],
        ),
        Operation(
            name="start", type="action",
            provides=["vm.active"],
        ),
    ]
    choices = [ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive")]
    expanded = _expand_instance_choices(ops, choices)

    assert len(expanded) == 3
    names = {op.name for op in expanded}
    assert "attach[tpm_id=tpm0]" in names
    assert "attach[tpm_id=tpm1]" in names
    assert "start" in names

    tpm0_op = next(op for op in expanded if op.name == "attach[tpm_id=tpm0]")
    assert tpm0_op.provides == ["vm.TPM:tpm0.init"]
    assert tpm0_op.instance_params == {"tpm_id": "tpm0"}


def test_instance_graph_multiple_devices():
    ops = [
        Operation(name="attach", type="action", provides=["TPM:{tpm_id}.init"]),
        Operation(
            name="configure", type="action",
            requires=["TPM:{tpm_id}.init"],
            provides=["TPM:{tpm_id}.ready"],
        ),
        Operation(name="check", type="check", requires=["TPM:{tpm_id}.ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="multi-tpm",
            targets=["check"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
            ],
            cleanup=False,
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) >= 2
    all_steps = set()
    for case in cases:
        all_steps.update(case.steps)
    assert "attach[tpm_id=tpm0]" in all_steps
    assert "attach[tpm_id=tpm1]" in all_steps


def test_instance_cases_contain_all_instances():
    ops = [
        Operation(name="init", type="action", provides=["dev:{dev_id}.on"]),
        Operation(
            name="verify", type="check",
            requires=["dev:{dev_id}.on"],
        ),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="device-test",
            targets=["verify"],
            param_choices=[
                ParamChoice(name="dev_id", values=["d0", "d1"], mode="additive"),
            ],
            cleanup=False,
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) >= 2
    targets = set()
    for case in cases:
        check_steps = [s for s in case.steps if s.startswith("verify")]
        targets.update(check_steps)
    assert "verify[dev_id=d0]" in targets
    assert "verify[dev_id=d1]" in targets


def test_instance_params_in_case():
    ops = [
        Operation(name="attach", type="action", provides=["TPM:{tpm_id}.init"]),
        Operation(name="check", type="check", requires=["TPM:{tpm_id}.init"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0"], mode="additive"),
            ],
            cleanup=False,
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) == 1
    assert cases[0].params.get("tpm_id") == "tpm0"


def test_additive_and_exclusive_coexist():
    ops = [
        Operation(name="setup", type="action", provides=["ready"]),
        Operation(name="attach", type="action",
                  requires=["ready"], provides=["TPM:{tpm_id}.init"]),
        Operation(name="check", type="check",
                  requires=["TPM:{tpm_id}.init"]),
        Operation(name="teardown", type="cleanup",
                  requires=["ready"], clears=["ready"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="mode", values=["fast", "slow"], mode="exclusive"),
                ParamChoice(name="tpm_id", values=["tpm0"], mode="additive"),
            ],
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) >= 2
    modes = {c.params.get("mode") for c in cases}
    assert modes == {"fast", "slow"}
    for case in cases:
        assert case.params.get("tpm_id") == "tpm0"


def test_no_expansion_without_templates():
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
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
            ],
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) >= 1
    for case in cases:
        for step in case.steps:
            assert '[' not in step


# --- Wildcard matching ---

from testweaver.env import Env


def test_env_wildcard_basic():
    env = Env()
    env.set('TPM:tpm0.ready')
    assert env.is_active('TPM:tpm*.ready')


def test_env_wildcard_no_match():
    env = Env()
    env.set('TPM:tpm0.init')
    assert not env.is_active('TPM:tpm*.ready')


def test_env_wildcard_multiple_instances():
    env = Env()
    env.set('TPM:tpm0.init')
    env.set('TPM:tpm1.ready')
    assert env.is_active('TPM:tpm*.ready')
    assert not env.is_active('TPM:tpm*.configured')


def test_env_wildcard_nested():
    env = Env()
    env.set('vm.active.TPM:tpm0.ready')
    env.set('vm.active.TPM:tpm1.init')
    assert env.is_active('vm.active.TPM:tpm*.ready')
    assert env.is_active('vm.active.TPM:tpm*.init')
    assert not env.is_active('vm.active.DISK:disk*.ready')


def test_env_no_wildcard_unchanged():
    env = Env()
    env.set('a.b.c')
    assert env.is_active('a.b.c')
    assert env.is_active('a.b')
    assert env.is_active('a')
    assert not env.is_active('a.b.d')
    assert not env.is_active('x.y')


def test_wildcard_requires_in_graph():
    ops = [
        Operation(name="attach", type="action", provides=["TPM:{tpm_id}.init"]),
        Operation(
            name="configure", type="action",
            requires=["TPM:{tpm_id}.init"],
            provides=["TPM:{tpm_id}.ready"],
        ),
        Operation(
            name="check_any_ready", type="check",
            requires=["TPM:tpm*.ready"],
        ),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="wildcard-test",
            targets=["check_any_ready"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
            ],
            cleanup=False,
        ),
    )
    cases = generate_cases(defn)
    assert len(cases) >= 1
    for case in cases:
        assert "check_any_ready" in case.steps
        has_configure = any(s.startswith("configure[") for s in case.steps)
        assert has_configure


def test_wildcard_excludes_in_graph():
    env = Env()
    env.set('TPM:tpm0.error')
    assert env.is_active('TPM:tpm*.error')

    env2 = Env()
    env2.set('TPM:tpm0.ready')
    assert not env2.is_active('TPM:tpm*.error')


# --- Read-write separation (Problem 5) ---


def test_wildcard_in_provides_rejected():
    import pytest
    with pytest.raises(ValueError, match="wildcard.*not allowed.*write"):
        TestDefinition(
            operations=[
                Operation(name="bad", type="action", provides=["TPM:tpm*.init"]),
                Operation(name="c", type="check", requires=["TPM:tpm*.init"]),
            ],
            suite=TestSuite(name="test", targets=["c"]),
        )


def test_wildcard_in_clears_rejected():
    import pytest
    with pytest.raises(ValueError, match="wildcard.*not allowed.*write"):
        TestDefinition(
            operations=[
                Operation(name="setup", type="action", provides=["ready"]),
                Operation(name="bad", type="cleanup", requires=["ready"],
                          clears=["TPM:tpm*.init"]),
                Operation(name="c", type="check", requires=["ready"]),
            ],
            suite=TestSuite(name="test", targets=["c"]),
        )


def test_wildcard_in_requires_allowed():
    defn = TestDefinition(
        operations=[
            Operation(name="setup", type="action", provides=["TPM:tpm0.ready"]),
            Operation(name="check", type="check", requires=["TPM:tpm*.ready"]),
            Operation(name="cleanup", type="cleanup",
                      requires=["TPM:tpm0.ready"], clears=["TPM:tpm0.ready"]),
        ],
        suite=TestSuite(name="test", targets=["check"]),
    )
    assert defn is not None


# --- Generation strategies (Problem 4) ---


def test_generation_strategy_exhaustive_default():
    ops = [
        Operation(name="attach", type="action", provides=["TPM:{tpm_id}.init"]),
        Operation(name="check", type="check", requires=["TPM:{tpm_id}.init"]),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
            ],
            cleanup=False,
        ),
    )
    cases = generate_cases(defn)
    exhaustive_count = len(cases)
    assert exhaustive_count >= 2


def test_generation_strategy_representative():
    ops = [
        Operation(name="attach", type="action", provides=["TPM:{tpm_id}.init"]),
        Operation(
            name="configure", type="action",
            requires=["TPM:{tpm_id}.init"],
            provides=["TPM:{tpm_id}.ready"],
        ),
        Operation(name="check", type="check", requires=["TPM:{tpm_id}.ready"]),
    ]
    defn_exhaust = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
            ],
            cleanup=False,
            generation_strategy="exhaustive",
        ),
    )
    defn_repr = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
            ],
            cleanup=False,
            generation_strategy="representative",
        ),
    )
    exhaust_cases = generate_cases(defn_exhaust)
    repr_cases = generate_cases(defn_repr)
    assert len(repr_cases) <= len(exhaust_cases)
    assert len(repr_cases) >= 1


def test_generation_strategy_pairwise():
    ops = [
        Operation(name="attach_tpm", type="action", provides=["TPM:{tpm_id}.on"]),
        Operation(name="attach_disk", type="action", provides=["DISK:{disk_id}.on"]),
        Operation(
            name="check", type="check",
            requires=["TPM:tpm*.on", "DISK:disk*.on"],
        ),
    ]
    defn_exhaust = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
                ParamChoice(name="disk_id", values=["disk0", "disk1"], mode="additive"),
            ],
            cleanup=False,
            generation_strategy="exhaustive",
        ),
    )
    defn_pair = TestDefinition(
        operations=ops,
        suite=TestSuite(
            name="test",
            targets=["check"],
            param_choices=[
                ParamChoice(name="tpm_id", values=["tpm0", "tpm1"], mode="additive"),
                ParamChoice(name="disk_id", values=["disk0", "disk1"], mode="additive"),
            ],
            cleanup=False,
            generation_strategy="pairwise",
        ),
    )
    exhaust_cases = generate_cases(defn_exhaust)
    pair_cases = generate_cases(defn_pair)
    assert len(pair_cases) <= len(exhaust_cases)
    assert len(pair_cases) >= 1

    all_tagged = set()
    for case in pair_cases:
        tagged = [s for s in case.steps if '[' in s]
        for a, b in combinations(tagged, 2):
            all_tagged.add((a, b))
    exhaust_pairs = set()
    for case in exhaust_cases:
        tagged = [s for s in case.steps if '[' in s]
        for a, b in combinations(tagged, 2):
            exhaust_pairs.add((a, b))
    assert all_tagged == exhaust_pairs
