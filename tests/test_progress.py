"""Tests for progress reporting callback and CLI flag."""
from __future__ import annotations

import json
import threading

from click.testing import CliRunner

from testweaver.cli import main
from testweaver.engine import run_all
from testweaver.graph import generate_cases
from testweaver.schema import (
    CaseResult,
    HookResult,
    LifecycleHooks,
    Operation,
    ProgressEvent,
    TestCase,
    TestDefinition,
    TestSuite,
)


def _simple_definition():
    ops = [
        Operation(name="setup", type="setup", provides=["ready"], run="true"),
        Operation(name="check", type="check", requires=["ready"], run="true"),
        Operation(
            name="teardown", type="cleanup",
            requires=["ready"], clears=["ready"], run="true",
        ),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="progress_test", targets=["check"]),
    )


def _failing_definition():
    ops = [
        Operation(name="setup", type="setup", provides=["ready"], run="true"),
        Operation(name="check", type="check", requires=["ready"], run="false"),
        Operation(
            name="teardown", type="cleanup",
            requires=["ready"], clears=["ready"], run="true",
        ),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="fail_test", targets=["check"]),
    )


# ---------------------------------------------------------------------------
# Engine-level callback tests
# ---------------------------------------------------------------------------

def test_on_progress_called_for_each_case_sequential():
    defn = _simple_definition()
    cases = generate_cases(defn)
    assert len(cases) >= 1

    events: list[ProgressEvent] = []
    results, _ = run_all(cases, defn, timeout=10, workers=1,
                         on_progress=events.append)

    assert len(events) == len(cases)
    for i, event in enumerate(events):
        assert event.index == i
        assert event.total == len(cases)


def test_on_progress_called_for_each_case_parallel():
    defn = _simple_definition()
    cases = generate_cases(defn)
    assert len(cases) >= 1

    events: list[ProgressEvent] = []
    lock = threading.Lock()

    def _safe_append(e: ProgressEvent) -> None:
        with lock:
            events.append(e)

    results, _ = run_all(cases, defn, timeout=10, workers=2,
                         on_progress=_safe_append)

    assert len(events) == len(cases)
    indices = sorted(e.index for e in events)
    assert indices == list(range(len(cases)))


def test_on_progress_receives_correct_status():
    defn = _failing_definition()
    cases = generate_cases(defn)

    events: list[ProgressEvent] = []
    results, _ = run_all(cases, defn, timeout=10, workers=1,
                         on_progress=events.append)

    assert len(events) == len(results)
    for event, result in zip(events, results):
        assert event.status == result.status
        assert event.case_id == result.case_id


def test_on_progress_none_is_noop():
    defn = _simple_definition()
    cases = generate_cases(defn)
    results, _ = run_all(cases, defn, timeout=10, workers=1)
    assert all(r.status == "pass" for r in results)


def test_on_progress_parallel_preserves_result_order():
    defn = _simple_definition()
    cases = generate_cases(defn)

    events: list[ProgressEvent] = []
    lock = threading.Lock()

    def _safe_append(e: ProgressEvent) -> None:
        with lock:
            events.append(e)

    results, _ = run_all(cases, defn, timeout=10, workers=2,
                         on_progress=_safe_append)

    for case, result in zip(cases, results):
        assert case.case_id == result.case_id


def test_on_progress_suite_setup_failure():
    defn = _simple_definition()

    def _failing_hook(ctx):
        raise RuntimeError("setup boom")

    defn.hooks = LifecycleHooks(suite_setup=[_failing_hook])
    cases = generate_cases(defn)

    events: list[ProgressEvent] = []
    results, _ = run_all(cases, defn, timeout=10, workers=1,
                         on_progress=events.append)

    assert len(events) == len(cases)
    assert all(e.status == "error" for e in events)


def test_on_progress_index_values():
    defn = _simple_definition()
    cases = generate_cases(defn)

    events: list[ProgressEvent] = []
    run_all(cases, defn, timeout=10, workers=1,
            on_progress=events.append)

    for i, event in enumerate(events):
        assert event.index == i
        assert event.total == len(cases)


def test_on_progress_receives_retry_info():
    ops = [
        Operation(name="setup", type="setup", provides=["ready"], run="true"),
        Operation(name="check", type="check", requires=["ready"], run="false"),
        Operation(
            name="teardown", type="cleanup",
            requires=["ready"], clears=["ready"], run="true",
        ),
    ]
    defn = TestDefinition(
        operations=ops,
        suite=TestSuite(name="retry_test", targets=["check"]),
    )
    cases = generate_cases(defn)

    events: list[ProgressEvent] = []
    run_all(cases, defn, timeout=10, workers=1, retries=2,
            on_progress=events.append)

    for event in events:
        assert event.retry_count >= 0


# ---------------------------------------------------------------------------
# ProgressEvent model tests
# ---------------------------------------------------------------------------

def test_progress_event_model():
    event = ProgressEvent(
        case_id="test_1",
        status="pass",
        duration_ms=123.4,
        index=0,
        total=5,
        is_fault=True,
        flaky=True,
        retry_count=2,
    )
    assert event.case_id == "test_1"
    assert event.status == "pass"
    assert event.is_fault is True
    data = json.loads(event.model_dump_json())
    assert data["index"] == 0
    assert data["total"] == 5


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

def _write_simple_yaml(tmp_path):
    content = """\
operations:
  - name: setup
    type: setup
    provides: [ready]
    run: "true"
  - name: check
    type: check
    requires: [ready]
    run: "true"
  - name: teardown
    type: cleanup
    requires: [ready]
    clears: [ready]
    run: "true"
suite:
  name: cli_progress_test
  targets: [check]
"""
    path = tmp_path / "test_def.yaml"
    path.write_text(content)
    return str(path)


def test_progress_flag_accepted(tmp_path):
    path = _write_simple_yaml(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["run", path, "--progress", "--format", "json"])
    assert result.exit_code == 0
    result2 = runner.invoke(main, ["run", path, "--no-progress", "--format", "json"])
    assert result2.exit_code == 0


def test_no_progress_shows_running_message(tmp_path):
    path = _write_simple_yaml(tmp_path)
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, ["run", path, "--no-progress", "--format", "json"])
    assert result.exit_code == 0
    assert "Running" in result.stderr
    assert "case(s)" in result.stderr


def test_progress_does_not_affect_stdout(tmp_path):
    path = _write_simple_yaml(tmp_path)
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, ["run", path, "--progress", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "summary" in data
    assert "results" in data
