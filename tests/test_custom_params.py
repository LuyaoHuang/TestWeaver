"""Tests for the @custom_params decorator and integration."""

import textwrap

import pytest

from testweaver.decorators import custom_params
from testweaver.loader import extract_custom_params, load_module
from testweaver.schema import TestDefinition, TestSuite, load_definition


def _write_module(tmp_path, filename, code):
    p = tmp_path / filename
    p.write_text(textwrap.dedent(code))
    return p


class TestCustomParamsDecorator:
    def test_sets_custom_params_meta(self):
        @custom_params
        def my_func(params):
            return params

        assert my_func._tw_meta == {'custom_params': True}

    def test_does_not_affect_other_meta(self):
        @custom_params
        def my_func(params):
            return params

        assert 'type' not in my_func._tw_meta
        assert 'provides' not in my_func._tw_meta

    def test_preserves_function_identity(self):
        @custom_params
        def my_func(params):
            return params

        assert my_func.__name__ == 'my_func'


class TestExtractCustomParams:
    def test_finds_single_function(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import custom_params

            @custom_params
            def detect_env(params):
                params['arch'] = 'x86_64'
                return params
        """)
        module = load_module(mod_file)
        funcs = extract_custom_params(module)
        assert len(funcs) == 1
        assert funcs[0].__name__ == 'detect_env'

    def test_finds_multiple_functions(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import custom_params

            @custom_params
            def detect_arch(params):
                params['arch'] = 'x86_64'
                return params

            @custom_params
            def detect_cgroup(params):
                params['cgroup'] = 2
                return params
        """)
        module = load_module(mod_file)
        funcs = extract_custom_params(module)
        assert len(funcs) == 2
        names = {f.__name__ for f in funcs}
        assert names == {'detect_arch', 'detect_cgroup'}

    def test_ignores_non_decorated_functions(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import custom_params

            @custom_params
            def detect_env(params):
                return params

            def plain_func():
                pass
        """)
        module = load_module(mod_file)
        funcs = extract_custom_params(module)
        assert len(funcs) == 1

    def test_ignores_other_decorated_functions(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import action, custom_params, provides

            @custom_params
            def detect_env(params):
                return params

            @action
            @provides('ready')
            def do_work(params, env):
                pass
        """)
        module = load_module(mod_file)
        funcs = extract_custom_params(module)
        assert len(funcs) == 1
        assert funcs[0].__name__ == 'detect_env'

    def test_returns_empty_list_with_no_custom_params(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import action, provides

            @action
            @provides('ready')
            def do_work(params, env):
                pass
        """)
        module = load_module(mod_file)
        funcs = extract_custom_params(module)
        assert funcs == []


class TestApplyCustomParams:
    def test_applies_single_function(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import action, check, custom_params, provides, requires

            @custom_params
            def detect_env(params):
                params['arch'] = 'arm64'
                return params

            @action
            @provides('ready')
            def do_setup(params, env):
                pass

            @check
            @requires('ready')
            def verify(params, env):
                pass
        """)
        defn = load_definition(mod_file)
        assert len(defn.custom_params_funcs) == 1
        defn.apply_custom_params()
        assert defn.suite.params == {'arch': 'arm64'}

    def test_applies_multiple_functions_in_order(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import action, check, custom_params, provides, requires

            @custom_params
            def step1_base(params):
                params['os'] = 'linux'
                params['version'] = '1.0'
                return params

            @custom_params
            def step2_override(params):
                params['version'] = '2.0'
                return params

            @action
            @provides('ready')
            def do_setup(params, env):
                pass

            @check
            @requires('ready')
            def verify(params, env):
                pass
        """)
        defn = load_definition(mod_file)
        defn.apply_custom_params()
        assert defn.suite.params['os'] == 'linux'
        assert defn.suite.params['version'] == '2.0'

    def test_raises_on_none_return(self):
        @custom_params
        def bad_func(params):
            return None

        defn = TestDefinition(
            operations=[],
            suite=TestSuite(name="test", targets=[]),
            custom_params_funcs=[bad_func],
        )
        with pytest.raises(ValueError, match="returned None"):
            defn.apply_custom_params()

    def test_noop_with_empty_funcs(self):
        defn = TestDefinition(
            operations=[],
            suite=TestSuite(name="test", targets=[]),
        )
        defn.apply_custom_params()


class TestEndToEnd:
    def test_params_flow_into_generated_cases(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import action, check, custom_params, provides, requires

            @custom_params
            def detect_env(params):
                params['cgroup_version'] = 2
                return params

            @action
            @provides('ready')
            def do_setup(params, env):
                pass

            @check
            @requires('ready')
            def verify(params, env):
                pass
        """)
        from testweaver.graph import build_graph, generate_cases

        defn = load_definition(mod_file)
        defn.apply_custom_params()
        graph = build_graph(defn.operations)
        cases = generate_cases(defn, graph)
        assert len(cases) == 1
        assert cases[0].params.get('cgroup_version') == 2

    def test_cli_param_overrides_custom_params(self, tmp_path):
        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import action, check, custom_params, provides, requires

            @custom_params
            def detect_env(params):
                params['arch'] = 'x86_64'
                return params

            @action
            @provides('ready')
            def do_setup(params, env):
                pass

            @check
            @requires('ready')
            def verify(params, env):
                pass
        """)
        from testweaver.cli import main
        from click.testing import CliRunner

        runner = CliRunner()
        with runner.isolated_filesystem():
            import shutil
            shutil.copy(mod_file, "m.py")
            result = runner.invoke(main, ['generate', 'm.py', '-p', 'arch=arm64'])
            assert result.exit_code == 0
            assert '"arch": "arm64"' in result.output

    def test_yaml_with_modules_loads_custom_params(self, tmp_path):
        mod_file = _write_module(tmp_path, "ops.py", """\
            from testweaver import action, check, custom_params, provides, requires

            @custom_params
            def detect_env(params):
                params['env'] = 'staging'
                return params

            @action
            @provides('ready')
            def do_setup(params, env):
                pass

            @check
            @requires('ready')
            def verify(params, env):
                pass
        """)
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(textwrap.dedent("""\
            modules:
              - ops.py
            suite:
              name: "test"
              targets: [verify]
        """))
        defn = load_definition(yaml_file)
        assert len(defn.custom_params_funcs) == 1
        defn.apply_custom_params()
        assert defn.suite.params['env'] == 'staging'
