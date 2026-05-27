import os
import tempfile

from click.testing import CliRunner

from testweaver.cli import main
from testweaver.graph import generate_cases
from testweaver.schema import (
    Operation,
    TestCase,
    TestDefinition,
    TestSuite,
)


def _write_yaml(tmp_dir: str, content: str) -> str:
    """Write a YAML definition file and return its path."""
    path = os.path.join(tmp_dir, "def.yaml")
    with open(path, "w") as f:
        f.write(content)
    return path


BASIC_YAML = """\
operations:
  - name: setup_host
    type: setup
    provides: [host.ready]
    run: "ssh $host echo ready"
  - name: start_vm
    type: action
    requires: [host.ready]
    provides: [vm.running]
    run: "virsh start $vm_name"
  - name: check_vm
    type: check
    requires: [vm.running]
    run: "virsh domstate $vm_name"
  - name: stop_vm
    type: cleanup
    requires: [vm.running]
    clears: [vm.running]
    run: "virsh destroy $vm_name"
  - name: teardown_host
    type: cleanup
    requires: [host.ready]
    clears: [host.ready]
    run: "ssh $host shutdown"
suite:
  name: vm_test
  params:
    host: 192.168.1.1
    vm_name: testvm
  targets: [check_vm]
"""


class TestDryRunCLI:
    def test_dry_run_flag_accepted(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert result.exit_code == 0

    def test_dry_run_header(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert "Dry-run:" in result.output
            assert "test case(s) would be executed" in result.output

    def test_dry_run_shows_case_id_and_target(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert "Target: check_vm" in result.output

    def test_dry_run_shows_params(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert "192.168.1.1" in result.output
            assert "testvm" in result.output

    def test_dry_run_shows_resolved_commands(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert "virsh start $vm_name" in result.output
            assert "virsh start testvm" in result.output

    def test_dry_run_shows_steps_section(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert "Steps:" in result.output

    def test_dry_run_shows_cleanup(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert "Cleanup:" in result.output

    def test_dry_run_no_execution(self):
        """Verify no commands are actually executed during dry-run."""
        yaml_content = """\
operations:
  - name: boom
    type: setup
    provides: [ready]
    run: "exit 1"
  - name: check
    type: check
    requires: [ready]
    run: "exit 1"
  - name: cleanup
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "exit 1"
suite:
  name: no_exec_test
  targets: [check]
"""
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(yaml_content)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert result.exit_code == 0
            assert "Dry-run:" in result.output

    def test_dry_run_with_output_file(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "-o", "out.txt", "def.yaml"])
            assert result.exit_code == 0
            assert os.path.exists("out.txt")
            content = open("out.txt").read()
            assert "Dry-run:" in content
            assert "check_vm" in content

    def test_dry_run_with_filter(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, [
                "run", "--dry-run", "-k", "nonexistent_pattern", "def.yaml",
            ])
            assert result.exit_code == 0
            assert "0 test case(s) would be executed" in result.output

    def test_dry_run_with_param_override(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(BASIC_YAML)
            result = runner.invoke(main, [
                "run", "--dry-run", "-p", "host=10.0.0.1", "def.yaml",
            ])
            assert result.exit_code == 0
            assert "10.0.0.1" in result.output


FAULT_YAML = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "echo setup"
  - name: action
    type: action
    requires: [ready]
    provides: [done]
    run: "echo action"
  - name: check
    type: check
    requires: [done]
    run: "echo check"
  - name: bad_action
    type: fault
    fault_for: action
    requires: [ready]
    run: "echo fault"
  - name: teardown
    type: cleanup
    requires: [ready]
    clears: [ready, done]
    run: "echo teardown"
suite:
  name: fault_test
  targets: [check]
  faults: true
"""


class TestDryRunFaults:
    def test_fault_cases_tagged(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(FAULT_YAML)
            result = runner.invoke(main, ["run", "--dry-run", "def.yaml"])
            assert result.exit_code == 0
            assert "[FAULT]" in result.output

    def test_fault_only_filter_with_dry_run(self):
        runner = CliRunner()
        with runner.isolated_filesystem():
            with open("def.yaml", "w") as f:
                f.write(FAULT_YAML)
            result = runner.invoke(main, [
                "run", "--dry-run", "--fault-only", "def.yaml",
            ])
            assert result.exit_code == 0
            for line in result.output.split("\n"):
                if line.startswith("--- "):
                    assert "[FAULT]" in line


class TestDryRunCallable:
    def test_callable_shown(self):
        ops = [
            Operation(name="setup", type="setup", provides=["ready"],
                      callable=lambda *a: None),
            Operation(name="check", type="check", requires=["ready"],
                      callable=lambda *a: None),
            Operation(name="teardown", type="cleanup", requires=["ready"],
                      clears=["ready"], callable=lambda *a: None),
        ]
        defn = TestDefinition(
            operations=ops,
            suite=TestSuite(name="callable_test", targets=["check"]),
        )
        cases = generate_cases(defn)
        assert len(cases) > 0

        from testweaver.cli import _format_step_line
        line = _format_step_line(1, "setup", ops[0], {})
        assert "[callable:" in line

    def test_no_op_shown(self):
        from testweaver.cli import _format_step_line
        op = Operation(name="noop", type="action", provides=["x"], run="")
        line = _format_step_line(1, "noop", op, {})
        assert "[no-op]" in line

    def test_unknown_operation_shown(self):
        from testweaver.cli import _format_step_line
        line = _format_step_line(1, "missing", None, {})
        assert "[unknown operation]" in line
