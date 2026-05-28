"""Tests for the @params_require decorator and operation filtering."""

import textwrap

import pytest

from testweaver.decorators import params_require
from testweaver.schema import TestDefinition, TestSuite, _operation_meets_params_require


def _write_module(tmp_path, name, source):
    mod = tmp_path / name
    mod.write_text(textwrap.dedent(source))
    return mod


class TestParamsRequireDecorator:
    def test_sets_params_require_meta(self):
        @params_require('arch')
        def my_func(params, env):
            pass

        assert my_func._tw_meta['params_require'] == [('arch', None, None)]

    def test_sets_exact_value_meta(self):
        @params_require(('cgroup_version', '=', 2))
        def my_func(params, env):
            pass

        assert my_func._tw_meta['params_require'] == [('cgroup_version', '=', 2)]

    def test_sets_multiple_conditions(self):
        @params_require('arch', ('os', '=', 'linux'), 'kvm_available')
        def my_func(params, env):
            pass

        assert my_func._tw_meta['params_require'] == [
            ('arch', None, None),
            ('os', '=', 'linux'),
            ('kvm_available', None, None),
        ]

    def test_rejects_invalid_argument(self):
        with pytest.raises(TypeError, match="params_require expects"):
            @params_require(123)  # type: ignore
            def my_func(params, env):
                pass

    def test_rejects_bad_tuple_length(self):
        with pytest.raises(TypeError, match="params_require expects"):
            @params_require(('key', '='))  # type: ignore
            def my_func(params, env):
                pass

    def test_preserves_existing_meta(self):
        @params_require('arch')
        @params_require(('os', '=', 'linux'))
        def my_func(params, env):
            pass

        assert my_func._tw_meta['params_require'] == [
            ('os', '=', 'linux'),
            ('arch', None, None),
        ]


class TestOperationMeetsParamsRequire:
    def test_passes_with_no_requirements(self):
        from testweaver.schema import Operation
        op = Operation(name="test", type="action")
        assert _operation_meets_params_require(op, {})

    def test_passes_when_key_exists(self):
        from testweaver.schema import Operation
        op = Operation(
            name="test", type="action",
            params_require=[['arch', None, None]],
        )
        assert _operation_meets_params_require(op, {'arch': 'x86_64'})

    def test_fails_when_key_missing(self):
        from testweaver.schema import Operation
        op = Operation(
            name="test", type="action",
            params_require=[['arch', None, None]],
        )
        assert not _operation_meets_params_require(op, {})

    def test_passes_when_value_equals(self):
        from testweaver.schema import Operation
        op = Operation(
            name="test", type="action",
            params_require=[['cgroup_version', '=', 2]],
        )
        assert _operation_meets_params_require(op, {'cgroup_version': 2})

    def test_fails_when_value_not_equal(self):
        from testweaver.schema import Operation
        op = Operation(
            name="test", type="action",
            params_require=[['cgroup_version', '=', 2]],
        )
        assert not _operation_meets_params_require(op, {'cgroup_version': 1})

    def test_passes_when_value_not_equals_operator(self):
        from testweaver.schema import Operation
        op = Operation(
            name="test", type="action",
            params_require=[['arch', '!=', 'arm64']],
        )
        assert _operation_meets_params_require(op, {'arch': 'x86_64'})

    def test_fails_when_value_not_equals_operator_fails(self):
        from testweaver.schema import Operation
        op = Operation(
            name="test", type="action",
            params_require=[['arch', '!=', 'arm64']],
        )
        assert not _operation_meets_params_require(op, {'arch': 'arm64'})

    def test_all_conditions_must_pass(self):
        from testweaver.schema import Operation
        op = Operation(
            name="test", type="action",
            params_require=[
                ['arch', None, None],
                ['cgroup_version', '=', 2],
            ],
        )
        assert not _operation_meets_params_require(op, {'arch': 'x86_64'})


class TestFilterOperationsByParams:
    def test_removes_operations_with_unmet_requirements(self):
        from testweaver.schema import Operation
        op1 = Operation(
            name="keep_me", type="action",
            params_require=[['arch', None, None]],
        )
        op2 = Operation(
            name="remove_me", type="action",
            params_require=[['kvm_available', None, None]],
        )
        defn = TestDefinition(
            operations=[op1, op2],
            suite=TestSuite(name="test", targets=["keep_me"]),
        )
        defn.suite.params = {'arch': 'x86_64'}

        removed = defn.filter_operations_by_params()
        assert len(removed) == 1
        assert removed[0].name == "remove_me"
        assert len(defn.operations) == 1
        assert defn.operations[0].name == "keep_me"

    def test_keeps_all_when_no_requirements(self):
        from testweaver.schema import Operation
        op1 = Operation(name="a", type="action")
        op2 = Operation(name="b", type="action")
        defn = TestDefinition(
            operations=[op1, op2],
            suite=TestSuite(name="test", targets=["a", "b"]),
        )
        removed = defn.filter_operations_by_params()
        assert len(removed) == 0
        assert len(defn.operations) == 2

    def test_returns_empty_list_when_nothing_removed(self):
        from testweaver.schema import Operation
        op = Operation(
            name="a", type="action",
            params_require=[['arch', None, None]],
        )
        defn = TestDefinition(
            operations=[op],
            suite=TestSuite(name="test", targets=["a"]),
        )
        defn.suite.params = {'arch': 'x86_64'}
        removed = defn.filter_operations_by_params()
        assert removed == []

    def test_updates_targets_validation(self):
        from testweaver.schema import Operation
        op = Operation(
            name="a", type="action",
            params_require=[['missing_key', None, None]],
        )
        defn = TestDefinition(
            operations=[op],
            suite=TestSuite(name="test", targets=["a"]),
        )
        removed = defn.filter_operations_by_params()
        assert len(removed) == 1
        assert len(defn.operations) == 0


class TestIntegration:
    def test_custom_params_then_filter_then_generate(self, tmp_path):
        from testweaver.schema import load_definition

        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import (
                action, check, custom_params, params_require, provides, requires,
            )

            @custom_params
            def detect_env(params):
                params['hypervisor'] = 'kvm'
                return params

            @action
            @provides('vm.active')
            def start_vm(params, env):
                pass

            @check
            @requires('vm.active')
            @params_require('hypervisor')
            def verify_kvm(params, env):
                pass

            @check
            @requires('vm.active')
            @params_require('missing_key')
            def verify_lxc(params, env):
                pass
        """)
        defn = load_definition(mod_file)
        defn.apply_custom_params()
        assert defn.suite.params['hypervisor'] == 'kvm'

        removed = defn.filter_operations_by_params()
        removed_names = [op.name for op in removed]
        assert 'verify_lxc' in removed_names
        assert 'verify_kvm' not in removed_names
        assert 'start_vm' not in removed_names

    def test_cli_param_override_affects_filtering(self, tmp_path):
        from testweaver.schema import load_definition

        mod_file = _write_module(tmp_path, "m.py", """\
            from testweaver import (
                action, check, custom_params, params_require, provides, requires,
            )

            @custom_params
            def detect_env(params):
                params['hypervisor'] = 'kvm'
                return params

            @action
            @provides('vm.active')
            def start_vm(params, env):
                pass

            @check
            @requires('vm.active')
            @params_require(('hypervisor', '=', 'lxc'))
            def verify_lxc(params, env):
                pass
        """)
        defn = load_definition(mod_file)
        defn.apply_custom_params()

        # Before override: 'hypervisor' is 'kvm', so verify_lxc filtered
        removed = defn.filter_operations_by_params()
        assert len(removed) == 1

        # After CLI override: 'hypervisor' is 'lxc', so verify_lxc kept
        defn2 = load_definition(mod_file)
        defn2.apply_custom_params()
        defn2.suite.params['hypervisor'] = 'lxc'
        removed2 = defn2.filter_operations_by_params()
        assert len(removed2) == 0
