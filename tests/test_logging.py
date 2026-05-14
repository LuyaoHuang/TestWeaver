import logging

from click.testing import CliRunner

from testweaver.cli import main
from testweaver.engine import run_all, run_step
from testweaver.graph import build_graph, generate_cases
from testweaver.schema import (
    Operation,
    TestDefinition,
    TestSuite,
    load_definition,
)


def _simple_definition():
    ops = [
        Operation(name="setup", type="setup", provides=["ready"], run="true"),
        Operation(name="check", type="check", requires=["ready"], run="true"),
        Operation(
            name="teardown", type="cleanup", requires=["ready"],
            clears=["ready"], run="true",
        ),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="log_test", targets=["check"]),
    )


def _reset_testweaver_logger():
    tw = logging.getLogger("testweaver")
    tw.handlers.clear()
    tw.setLevel(logging.WARNING)


def test_engine_logs_at_info(caplog):
    _reset_testweaver_logger()
    defn = _simple_definition()
    cases = generate_cases(defn)

    with caplog.at_level(logging.INFO, logger="testweaver"):
        run_all(cases, defn, timeout=10)  # noqa: result unused

    messages = caplog.text
    assert "Case started:" in messages
    assert "Case finished:" in messages
    assert "Step started:" in messages
    assert "Step finished:" in messages
    assert "Running" in messages


def test_engine_silent_at_warning(caplog):
    _reset_testweaver_logger()
    defn = _simple_definition()
    cases = generate_cases(defn)

    with caplog.at_level(logging.WARNING, logger="testweaver"):
        run_all(cases, defn, timeout=10)  # noqa: result unused

    assert caplog.text == ""


def test_graph_logs_at_info(caplog):
    _reset_testweaver_logger()
    defn = _simple_definition()

    with caplog.at_level(logging.INFO, logger="testweaver"):
        build_graph(defn.operations)

    assert "Graph built:" in caplog.text


def test_generate_cases_logs_count(caplog):
    _reset_testweaver_logger()
    defn = _simple_definition()

    with caplog.at_level(logging.INFO, logger="testweaver"):
        cases = generate_cases(defn)

    assert "Generated" in caplog.text
    assert "test case" in caplog.text


def test_run_step_logs(caplog):
    _reset_testweaver_logger()
    op = Operation(name="my_op", type="action", provides=["x"], run="true")

    with caplog.at_level(logging.INFO, logger="testweaver"):
        result, _ = run_step(op, {}, timeout=10)

    assert result.status == "pass"
    assert "Step started: my_op" in caplog.text
    assert "Step finished: my_op" in caplog.text


def test_debug_shows_command_details(caplog):
    _reset_testweaver_logger()
    op = Operation(name="cmd_op", type="action", provides=["x"], run="echo hello")

    with caplog.at_level(logging.DEBUG, logger="testweaver"):
        run_step(op, {}, timeout=10)

    assert "Executing command:" in caplog.text
    assert "echo hello" in caplog.text


def test_cli_verbose_flag(tmp_path):
    _reset_testweaver_logger()
    defn_file = tmp_path / "test.yaml"
    defn_file.write_text("""\
operations:
  - name: do_thing
    type: action
    provides: [done]
    run: "true"
  - name: check_thing
    type: check
    requires: [done]
    run: "true"
  - name: undo_thing
    type: cleanup
    requires: [done]
    clears: [done]
    run: "true"
suite:
  name: cli_test
  targets: [check_thing]
""")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, ["run", str(defn_file), "-v", "--format", "text"])
    assert result.exit_code == 0
    assert "Case started:" in result.stderr or "Running" in result.stderr


def test_cli_default_no_logs(tmp_path):
    _reset_testweaver_logger()
    defn_file = tmp_path / "test.yaml"
    defn_file.write_text("""\
operations:
  - name: do_thing
    type: action
    provides: [done]
    run: "true"
  - name: check_thing
    type: check
    requires: [done]
    run: "true"
  - name: undo_thing
    type: cleanup
    requires: [done]
    clears: [done]
    run: "true"
suite:
  name: cli_test
  targets: [check_thing]
""")
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, ["run", str(defn_file), "--format", "text"])
    assert result.exit_code == 0
    stderr = result.stderr
    # stderr should only contain the "Running N test case(s)..." line, not logging output
    for line in stderr.strip().splitlines():
        assert "INFO" not in line
        assert "DEBUG" not in line


def test_cli_log_file(tmp_path):
    _reset_testweaver_logger()
    defn_file = tmp_path / "test.yaml"
    defn_file.write_text("""\
operations:
  - name: do_thing
    type: action
    provides: [done]
    run: "true"
  - name: check_thing
    type: check
    requires: [done]
    run: "true"
  - name: undo_thing
    type: cleanup
    requires: [done]
    clears: [done]
    run: "true"
suite:
  name: cli_test
  targets: [check_thing]
""")
    log_path = tmp_path / "test.log"
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, [
        "run", str(defn_file), "-v", "--log-file", str(log_path), "--format", "text",
    ])
    assert result.exit_code == 0
    log_content = log_path.read_text()
    assert "Case started:" in log_content
    assert "Case finished:" in log_content


def test_definition_loading_logs(caplog, tmp_path):
    _reset_testweaver_logger()
    defn_file = tmp_path / "test.yaml"
    defn_file.write_text("""\
operations:
  - name: do_thing
    type: action
    provides: [done]
    run: "true"
  - name: check_thing
    type: check
    requires: [done]
    run: "true"
  - name: undo_thing
    type: cleanup
    requires: [done]
    clears: [done]
    run: "true"
suite:
  name: log_test
  targets: [check_thing]
""")
    with caplog.at_level(logging.INFO, logger="testweaver"):
        load_definition(str(defn_file))

    assert "Loading definition" in caplog.text
    assert "Definition loaded:" in caplog.text
