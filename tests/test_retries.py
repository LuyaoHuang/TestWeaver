import time
import xml.etree.ElementTree as ET

from testweaver.engine import run_all, run_case_with_retries
from testweaver.analyzer import summarize_run
from testweaver.reporters import to_html, to_junit_xml, to_tap
from testweaver.schema import (
    AttemptResult,
    CaseResult,
    Operation,
    RunSummary,
    StepResult,
    TestCase,
    TestDefinition,
    TestSuite,
)
from testweaver.graph import build_graph, generate_cases


def _flaky_definition(fail_count=1):
    """Build a definition with a callable that fails `fail_count` times then passes."""
    call_counter = [0]

    def flaky_action(params):
        call_counter[0] += 1
        if call_counter[0] <= fail_count:
            raise RuntimeError("transient failure")

    ops = [
        Operation(name="setup", type="setup", provides=["ready"], callable=lambda p: None),
        Operation(name="action", type="action", requires=["ready"], provides=["done"],
                  callable=flaky_action),
        Operation(name="check", type="check", requires=["done"], callable=lambda p: None),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready", "done"], callable=lambda p: None),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="retry_test", targets=["check"]),
    ), call_counter


def _always_fail_definition():
    """Build a definition where the action always fails."""
    def failing_action(params):
        raise RuntimeError("permanent failure")

    ops = [
        Operation(name="setup", type="setup", provides=["ready"], callable=lambda p: None),
        Operation(name="action", type="action", requires=["ready"], provides=["done"],
                  callable=failing_action),
        Operation(name="check", type="check", requires=["done"], callable=lambda p: None),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready", "done"], callable=lambda p: None),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="fail_test", targets=["check"]),
    )


def _passing_definition():
    """Build a definition that always passes."""
    ops = [
        Operation(name="setup", type="setup", provides=["ready"], callable=lambda p: None),
        Operation(name="check", type="check", requires=["ready"], callable=lambda p: None),
        Operation(name="teardown", type="cleanup", requires=["ready"],
                  clears=["ready"], callable=lambda p: None),
    ]
    return TestDefinition(
        operations=ops,
        suite=TestSuite(name="pass_test", targets=["check"]),
    )


# --- Engine tests ---


class TestRunCaseWithRetries:
    def test_no_retries_behaves_like_run_case(self):
        defn = _passing_definition()
        cases = generate_cases(defn)
        result = run_case_with_retries(cases[0], defn, timeout=10, retries=0)
        assert result.status == "pass"
        assert result.retry_count == 0
        assert result.flaky is False
        assert result.attempts == []

    def test_flaky_detection(self):
        defn, counter = _flaky_definition(fail_count=1)
        cases = generate_cases(defn)
        result = run_case_with_retries(cases[0], defn, timeout=10, retries=2)
        assert result.status == "pass"
        assert result.flaky is True
        assert result.retry_count == 1
        assert len(result.attempts) == 2
        assert result.attempts[0].status in ("fail", "error")
        assert result.attempts[1].status == "pass"

    def test_all_retries_exhausted(self):
        defn = _always_fail_definition()
        cases = generate_cases(defn)
        result = run_case_with_retries(cases[0], defn, timeout=10, retries=2)
        assert result.status in ("fail", "error")
        assert result.retry_count == 2
        assert result.flaky is False
        assert len(result.attempts) == 3
        assert all(a.status in ("fail", "error") for a in result.attempts)

    def test_no_retry_on_pass(self):
        defn = _passing_definition()
        cases = generate_cases(defn)
        result = run_case_with_retries(cases[0], defn, timeout=10, retries=3)
        assert result.status == "pass"
        assert result.retry_count == 0
        assert result.flaky is False
        assert result.attempts == []

    def test_retry_delay(self):
        defn, _ = _flaky_definition(fail_count=1)
        cases = generate_cases(defn)
        start = time.monotonic()
        result = run_case_with_retries(
            cases[0], defn, timeout=10, retries=1, retry_delay=0.3,
        )
        elapsed = time.monotonic() - start
        assert result.status == "pass"
        assert elapsed >= 0.3

    def test_attempt_numbers_are_sequential(self):
        defn, _ = _flaky_definition(fail_count=2)
        cases = generate_cases(defn)
        result = run_case_with_retries(cases[0], defn, timeout=10, retries=3)
        assert result.status == "pass"
        assert [a.attempt for a in result.attempts] == [1, 2, 3]

    def test_duration_covers_all_attempts(self):
        defn, _ = _flaky_definition(fail_count=1)
        cases = generate_cases(defn)
        result = run_case_with_retries(
            cases[0], defn, timeout=10, retries=1, retry_delay=0.2,
        )
        assert result.duration_ms >= 200

    def test_final_steps_from_last_attempt(self):
        defn, _ = _flaky_definition(fail_count=1)
        cases = generate_cases(defn)
        result = run_case_with_retries(cases[0], defn, timeout=10, retries=1)
        assert result.status == "pass"
        assert all(s.status in ("pass", "skip") for s in result.steps)


# --- run_all integration tests ---


class TestRunAllWithRetries:
    def test_retries_default_zero(self):
        defn = _passing_definition()
        cases = generate_cases(defn)
        results, _ = run_all(cases, defn, timeout=10, workers=1)
        assert all(r.retry_count == 0 for r in results)
        assert all(r.flaky is False for r in results)

    def test_parallel_with_retries(self):
        defn, _ = _flaky_definition(fail_count=1)
        cases = generate_cases(defn)
        results, _ = run_all(cases, defn, timeout=10, workers=2, retries=2)
        for r in results:
            assert r.status == "pass"

    def test_preserves_order_with_retries(self):
        defn = _passing_definition()
        cases = generate_cases(defn)
        results, _ = run_all(cases, defn, timeout=10, workers=1, retries=1)
        for case, result in zip(cases, results):
            assert case.case_id == result.case_id


# --- Schema tests ---


class TestSchemaBackwardCompat:
    def test_case_result_without_new_fields(self):
        cr = CaseResult(case_id="x", status="pass")
        assert cr.retry_count == 0
        assert cr.flaky is False
        assert cr.attempts == []

    def test_case_result_model_validate(self):
        data = {"case_id": "x", "status": "pass", "duration_ms": 10.0}
        cr = CaseResult.model_validate(data)
        assert cr.retry_count == 0
        assert cr.flaky is False

    def test_case_result_json_roundtrip(self):
        cr = CaseResult(
            case_id="x",
            status="pass",
            flaky=True,
            retry_count=1,
            attempts=[AttemptResult(attempt=1, status="fail", duration_ms=5.0)],
        )
        data = cr.model_dump()
        restored = CaseResult.model_validate(data)
        assert restored.flaky is True
        assert restored.retry_count == 1
        assert len(restored.attempts) == 1

    def test_run_summary_new_fields(self):
        s = RunSummary(total=5, passed=3, failed=1, errors=1, flaky=2, retried=3)
        assert s.flaky == 2
        assert s.retried == 3

    def test_run_summary_defaults(self):
        s = RunSummary(total=1, passed=1)
        assert s.flaky == 0
        assert s.retried == 0


# --- Analyzer tests ---


class TestAnalyzerRetries:
    def test_summarize_counts_flaky_and_retried(self):
        results = [
            CaseResult(case_id="a", status="pass", flaky=True, retry_count=1),
            CaseResult(case_id="b", status="fail", retry_count=2),
            CaseResult(case_id="c", status="pass"),
        ]
        s = summarize_run(results)
        assert s.flaky == 1
        assert s.retried == 2

    def test_summarize_no_retries(self):
        results = [CaseResult(case_id="a", status="pass")]
        s = summarize_run(results)
        assert s.flaky == 0
        assert s.retried == 0


# --- Reporter tests ---


def _step(op, status="pass", duration_ms=10.0, stdout="", stderr="", error=None):
    return StepResult(
        operation=op, status=status, duration_ms=duration_ms,
        stdout=stdout, stderr=stderr, error=error,
    )


def _make_flaky_result():
    return CaseResult(
        case_id="flaky_case",
        status="pass",
        duration_ms=300.0,
        flaky=True,
        retry_count=1,
        steps=[_step("setup"), _step("action"), _step("check")],
        attempts=[
            AttemptResult(
                attempt=1,
                status="fail",
                duration_ms=100.0,
                steps=[_step("setup"), _step("action", status="fail", error="transient")],
            ),
            AttemptResult(
                attempt=2,
                status="pass",
                duration_ms=150.0,
                steps=[_step("setup"), _step("action"), _step("check")],
            ),
        ],
    )


def _make_retried_fail_result():
    return CaseResult(
        case_id="retried_fail",
        status="fail",
        duration_ms=400.0,
        retry_count=2,
        steps=[_step("setup"), _step("action", status="fail", error="permanent")],
        attempts=[
            AttemptResult(attempt=1, status="fail", duration_ms=100.0,
                          steps=[_step("setup"), _step("action", status="fail", error="permanent")]),
            AttemptResult(attempt=2, status="fail", duration_ms=100.0,
                          steps=[_step("setup"), _step("action", status="fail", error="permanent")]),
            AttemptResult(attempt=3, status="fail", duration_ms=100.0,
                          steps=[_step("setup"), _step("action", status="fail", error="permanent")]),
        ],
    )


class TestJUnitXMLRetries:
    def test_flaky_case_has_flaky_failure_element(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        root = ET.fromstring(to_junit_xml(results, summary))
        tc = root.find(".//testcase[@name='flaky_case']")
        flaky_fail = tc.find("flakyFailure")
        assert flaky_fail is not None
        assert "transient" in flaky_fail.get("message")

    def test_retried_case_has_properties(self):
        results = [_make_retried_fail_result()]
        summary = RunSummary(total=1, failed=1, retried=1, duration_ms=400.0)
        root = ET.fromstring(to_junit_xml(results, summary))
        tc = root.find(".//testcase[@name='retried_fail']")
        props = tc.find("properties")
        assert props is not None
        retry_prop = props.find("property[@name='retry_count']")
        assert retry_prop is not None
        assert retry_prop.get("value") == "2"

    def test_flaky_property_set(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        root = ET.fromstring(to_junit_xml(results, summary))
        tc = root.find(".//testcase[@name='flaky_case']")
        props = tc.find("properties")
        flaky_prop = props.find("property[@name='flaky']")
        assert flaky_prop is not None
        assert flaky_prop.get("value") == "true"

    def test_no_retry_no_properties(self):
        results = [CaseResult(case_id="clean", status="pass", duration_ms=10.0,
                              steps=[_step("op")])]
        summary = RunSummary(total=1, passed=1, duration_ms=10.0)
        root = ET.fromstring(to_junit_xml(results, summary))
        tc = root.find(".//testcase[@name='clean']")
        assert tc.find("properties") is None
        assert tc.find("flakyFailure") is None


class TestTAPRetries:
    def test_flaky_directive(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        output = to_tap(results, summary)
        assert "# FLAKY" in output

    def test_retry_count_in_diagnostic(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        output = to_tap(results, summary)
        assert "retry_count: 1" in output
        assert "flaky: true" in output

    def test_retried_summary_comments(self):
        results = [_make_flaky_result(), _make_retried_fail_result()]
        summary = RunSummary(total=2, passed=1, failed=1, flaky=1, retried=2, duration_ms=700.0)
        output = to_tap(results, summary)
        assert "# retried: 2" in output
        assert "# flaky: 1" in output

    def test_no_retry_no_extra_comments(self):
        results = [CaseResult(case_id="clean", status="pass", duration_ms=10.0,
                              steps=[_step("op")])]
        summary = RunSummary(total=1, passed=1, duration_ms=10.0)
        output = to_tap(results, summary)
        assert "retried" not in output
        assert "flaky" not in output


class TestHTMLRetries:
    def test_flaky_badge(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        output = to_html(results, summary)
        assert "FLAKY" in output
        assert 'class="badge flaky"' in output

    def test_retry_count_shown(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        output = to_html(results, summary)
        assert "retried 1x" in output

    def test_retry_attempts_section(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        output = to_html(results, summary)
        assert "Show retry attempts" in output
        assert "Attempt 1:" in output
        assert "Attempt 2:" in output

    def test_flaky_summary_stat(self):
        results = [_make_flaky_result()]
        summary = RunSummary(total=1, passed=1, flaky=1, retried=1, duration_ms=300.0)
        output = to_html(results, summary)
        assert "Flaky" in output

    def test_no_retry_no_attempt_section(self):
        results = [CaseResult(case_id="clean", status="pass", duration_ms=10.0,
                              steps=[_step("op")])]
        summary = RunSummary(total=1, passed=1, duration_ms=10.0)
        output = to_html(results, summary)
        assert "Show retry attempts" not in output
        assert "FLAKY" not in output
