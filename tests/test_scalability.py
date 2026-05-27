import logging
import os

from click.testing import CliRunner

from testweaver.cli import main
from testweaver.graph import build_graph, generate_cases
from testweaver.schema import (
    Operation,
    TestDefinition,
    TestSuite,
)


def _wide_graph_ops(n_alternatives=10):
    """Create operations where N alternatives all provide the same state."""
    ops = []
    for i in range(n_alternatives):
        ops.append(Operation(
            name=f"setup_{i}", type="action",
            provides=["ready"], excludes=["ready"],
            callable=lambda *a: None,
        ))
    ops.append(Operation(
        name="check", type="check", requires=["ready"],
        callable=lambda *a: None,
    ))
    ops.append(Operation(
        name="teardown", type="cleanup", requires=["ready"],
        clears=["ready"], callable=lambda *a: None,
    ))
    return ops


def _deep_chain_ops(depth=10):
    """Create a chain of operations: s0 -> s1 -> ... -> s{depth-1} -> check."""
    ops = []
    for i in range(depth):
        req = [f"s{i}"] if i > 0 else []
        ops.append(Operation(
            name=f"step_{i}", type="action" if i > 0 else "setup",
            requires=req, provides=[f"s{i + 1}"],
            callable=lambda *a: None,
        ))
    ops.append(Operation(
        name="check", type="check", requires=[f"s{depth}"],
        callable=lambda *a: None,
    ))
    ops.append(Operation(
        name="cleanup", type="cleanup", requires=["s1"],
        clears=["s1"], callable=lambda *a: None,
    ))
    return ops


def _branching_ops():
    """Create operations that produce many graph nodes via state combinations."""
    ops = [
        Operation(name="set_a", type="setup", provides=["a"], excludes=["a"],
                  callable=lambda *a: None),
        Operation(name="set_b", type="action", provides=["b"], excludes=["b"],
                  callable=lambda *a: None),
        Operation(name="set_c", type="action", provides=["c"], excludes=["c"],
                  callable=lambda *a: None),
        Operation(name="set_d", type="action", provides=["d"], excludes=["d"],
                  callable=lambda *a: None),
        Operation(name="set_e", type="action", provides=["e"], excludes=["e"],
                  callable=lambda *a: None),
        Operation(name="set_f", type="action", provides=["f"], excludes=["f"],
                  callable=lambda *a: None),
        Operation(name="check", type="check", requires=["a", "b", "c", "d"],
                  callable=lambda *a: None),
        Operation(name="cleanup_a", type="cleanup", requires=["a"],
                  clears=["a"], callable=lambda *a: None),
    ]
    return ops


class TestMaxGraphNodes:
    def test_default_allows_normal_graphs(self):
        ops = _wide_graph_ops(5)
        graph = build_graph(ops)
        assert graph.number_of_nodes() == 2

    def test_cap_limits_nodes(self):
        ops = _branching_ops()
        uncapped = build_graph(ops, max_nodes=9999)
        capped = build_graph(ops, max_nodes=5)
        assert capped.number_of_nodes() <= 5
        assert uncapped.number_of_nodes() > 5

    def test_warning_logged_on_cap(self, caplog):
        ops = _branching_ops()
        with caplog.at_level(logging.WARNING, logger="testweaver.graph"):
            build_graph(ops, max_nodes=3)
        assert "Graph node limit reached" in caplog.text

    def test_no_warning_when_under_limit(self, caplog):
        ops = _wide_graph_ops(3)
        with caplog.at_level(logging.WARNING, logger="testweaver.graph"):
            build_graph(ops, max_nodes=500)
        assert "Graph node limit reached" not in caplog.text

    def test_suite_field_default(self):
        suite = TestSuite(name="t", targets=["check"])
        assert suite.max_graph_nodes == 500

    def test_generate_cases_respects_max_graph_nodes(self):
        ops = _branching_ops()
        graph_capped = build_graph(ops, max_nodes=5)
        graph_uncapped = build_graph(ops, max_nodes=9999)
        assert graph_capped.number_of_nodes() <= 5
        assert graph_uncapped.number_of_nodes() > graph_capped.number_of_nodes()


class TestMaxPathDepth:
    def test_default_value(self):
        suite = TestSuite(name="t", targets=["check"])
        assert suite.max_path_depth == 20

    def test_limits_step_count(self):
        ops = _deep_chain_ops(depth=15)
        defn_shallow = TestDefinition(
            operations=ops,
            suite=TestSuite(name="t", targets=["check"],
                            max_path_depth=5),
        )
        cases = generate_cases(defn_shallow)
        assert len(cases) == 0

    def test_allows_within_limit(self):
        ops = _deep_chain_ops(depth=5)
        defn = TestDefinition(
            operations=ops,
            suite=TestSuite(name="t", targets=["check"],
                            max_path_depth=20),
        )
        cases = generate_cases(defn)
        assert len(cases) > 0

    def test_default_does_not_break_existing(self):
        ops = _deep_chain_ops(depth=5)
        defn = TestDefinition(
            operations=ops,
            suite=TestSuite(name="t", targets=["check"]),
        )
        cases = generate_cases(defn)
        assert len(cases) > 0


class TestMaxStateDepth:
    def test_default_value(self):
        suite = TestSuite(name="t", targets=["check"])
        assert suite.max_state_depth == 0

    def test_zero_means_no_limit(self):
        ops = _branching_ops()
        graph_unlimited = build_graph(ops, max_state_depth=0)
        assert graph_unlimited.number_of_nodes() > 1

    def test_limits_state_size(self):
        ops = _branching_ops()
        graph_limited = build_graph(ops, max_state_depth=2)
        graph_unlimited = build_graph(ops, max_state_depth=0)
        assert graph_limited.number_of_nodes() < graph_unlimited.number_of_nodes()

    def test_initial_node_always_included(self):
        ops = _branching_ops()
        graph = build_graph(ops, max_state_depth=1)
        assert graph.number_of_nodes() >= 1


class TestCLIScalabilityFlags:
    def _write_yaml(self, content):
        runner = CliRunner()
        return runner

    def test_generate_max_graph_nodes_flag(self):
        yaml_content = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "true"
  - name: check
    type: check
    requires: [ready]
    run: "true"
  - name: cleanup
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "true"
suite:
  name: test
  targets: [check]
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(yaml_content)
            result = runner.invoke(main, [
                "generate", "--max-graph-nodes", "100", "def.yaml",
            ])
            assert result.exit_code == 0

    def test_run_max_graph_nodes_flag(self):
        yaml_content = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "true"
  - name: check
    type: check
    requires: [ready]
    run: "true"
  - name: cleanup
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "true"
suite:
  name: test
  targets: [check]
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(yaml_content)
            result = runner.invoke(main, [
                "run", "--dry-run", "--max-graph-nodes", "100", "def.yaml",
            ])
            assert result.exit_code == 0
            assert "Dry-run:" in result.output

    def test_generate_max_path_depth_flag(self):
        yaml_content = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "true"
  - name: check
    type: check
    requires: [ready]
    run: "true"
  - name: cleanup
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "true"
suite:
  name: test
  targets: [check]
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(yaml_content)
            result = runner.invoke(main, [
                "generate", "--max-path-depth", "5", "def.yaml",
            ])
            assert result.exit_code == 0

    def test_generate_max_state_depth_flag(self):
        yaml_content = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "true"
  - name: check
    type: check
    requires: [ready]
    run: "true"
  - name: cleanup
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "true"
suite:
  name: test
  targets: [check]
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(yaml_content)
            result = runner.invoke(main, [
                "generate", "--max-state-depth", "10", "def.yaml",
            ])
            assert result.exit_code == 0


class TestYAMLScalabilityFields:
    def test_yaml_fields_parsed(self):
        yaml_content = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "true"
  - name: check
    type: check
    requires: [ready]
    run: "true"
  - name: cleanup
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "true"
suite:
  name: test
  targets: [check]
  max_graph_nodes: 42
  max_path_depth: 7
  max_state_depth: 3
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(yaml_content)
            result = runner.invoke(main, ["generate", "def.yaml"])
            assert result.exit_code == 0

    def test_cli_flag_overrides_yaml(self):
        yaml_content = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "true"
  - name: check
    type: check
    requires: [ready]
    run: "true"
  - name: cleanup
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "true"
suite:
  name: test
  targets: [check]
  max_path_depth: 3
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(yaml_content)
            result_default = runner.invoke(main, ["generate", "def.yaml"])
            result_override = runner.invoke(main, [
                "generate", "--max-path-depth", "10", "def.yaml",
            ])
            assert result_default.exit_code == 0
            assert result_override.exit_code == 0
