import xml.etree.ElementTree as ET

import pytest

from testweaver.reporters import to_html, to_junit_xml, to_tap
from testweaver.schema import CaseResult, RunSummary, StepResult


def _step(op, status="pass", duration_ms=10.0, stdout="", stderr="", error=None):
    return StepResult(
        operation=op, status=status, duration_ms=duration_ms,
        stdout=stdout, stderr=stderr, error=error,
    )


RESULTS = [
    CaseResult(
        case_id="case_pass_1",
        status="pass",
        duration_ms=150.0,
        steps=[_step("setup"), _step("action"), _step("check")],
    ),
    CaseResult(
        case_id="case_fail_1",
        status="fail",
        duration_ms=200.0,
        steps=[
            _step("setup"),
            _step("action", status="fail", stderr="exit code 1", error="action failed"),
        ],
    ),
    CaseResult(
        case_id="case_error_1",
        status="error",
        duration_ms=50.0,
        steps=[
            _step("setup", status="error", stderr="timeout", error="timed out after 300s"),
        ],
    ),
    CaseResult(
        case_id="case_fault_1",
        status="fail",
        duration_ms=100.0,
        is_fault=True,
        steps=[
            _step("setup"),
            _step("fault_action", status="fail", error="injected fault"),
        ],
    ),
]

SUMMARY = RunSummary(
    total=4, passed=1, failed=2, errors=1, duration_ms=500.0,
)


class TestJUnitXML:
    def test_parses_as_valid_xml(self):
        xml_str = to_junit_xml(RESULTS, SUMMARY)
        root = ET.fromstring(xml_str)
        assert root.tag == "testsuites"

    def test_testsuite_attributes(self):
        root = ET.fromstring(to_junit_xml(RESULTS, SUMMARY))
        suite = root.find("testsuite")
        assert suite.get("name") == "TestWeaver"
        assert suite.get("tests") == "4"
        assert suite.get("failures") == "2"
        assert suite.get("errors") == "1"
        assert suite.get("time") == "0.500"
        assert suite.get("timestamp") is not None
        assert suite.get("hostname") is not None

    def test_custom_suite_name(self):
        root = ET.fromstring(to_junit_xml(RESULTS, SUMMARY, suite_name="MySuite"))
        suite = root.find("testsuite")
        assert suite.get("name") == "MySuite"
        for tc in suite.findall("testcase"):
            assert tc.get("classname") == "MySuite"

    def test_testcase_count(self):
        root = ET.fromstring(to_junit_xml(RESULTS, SUMMARY))
        cases = root.findall(".//testcase")
        assert len(cases) == 4

    def test_passing_case_has_no_failure_or_error(self):
        root = ET.fromstring(to_junit_xml(RESULTS, SUMMARY))
        tc = root.find(".//testcase[@name='case_pass_1']")
        assert tc.find("failure") is None
        assert tc.find("error") is None

    def test_failing_case_has_failure_element(self):
        root = ET.fromstring(to_junit_xml(RESULTS, SUMMARY))
        tc = root.find(".//testcase[@name='case_fail_1']")
        failure = tc.find("failure")
        assert failure is not None
        assert failure.get("type") == "TestFailure"
        assert "action failed" in failure.get("message")
        assert "exit code 1" in failure.text

    def test_error_case_has_error_element(self):
        root = ET.fromstring(to_junit_xml(RESULTS, SUMMARY))
        tc = root.find(".//testcase[@name='case_error_1']")
        error = tc.find("error")
        assert error is not None
        assert error.get("type") == "TestError"
        assert "timed out" in error.get("message")

    def test_system_out_and_err(self):
        results = [
            CaseResult(
                case_id="with_output",
                status="pass",
                duration_ms=10.0,
                steps=[_step("op", stdout="hello stdout", stderr="hello stderr")],
            ),
        ]
        summary = RunSummary(total=1, passed=1, duration_ms=10.0)
        root = ET.fromstring(to_junit_xml(results, summary))
        tc = root.find(".//testcase[@name='with_output']")
        assert tc.find("system-out").text == "hello stdout"
        assert tc.find("system-err").text == "hello stderr"

    def test_time_in_seconds(self):
        root = ET.fromstring(to_junit_xml(RESULTS, SUMMARY))
        tc = root.find(".//testcase[@name='case_pass_1']")
        assert tc.get("time") == "0.150"

    def test_xml_declaration(self):
        xml_str = to_junit_xml(RESULTS, SUMMARY)
        assert xml_str.startswith("<?xml")

    def test_empty_results(self):
        summary = RunSummary(total=0, passed=0, duration_ms=0.0)
        root = ET.fromstring(to_junit_xml([], summary))
        assert root.find("testsuite").get("tests") == "0"
        assert len(root.findall(".//testcase")) == 0


class TestTAP:
    def test_version_header(self):
        output = to_tap(RESULTS, SUMMARY)
        assert output.startswith("TAP version 13\n")

    def test_plan_line(self):
        output = to_tap(RESULTS, SUMMARY)
        lines = output.split("\n")
        assert lines[1] == "1..4"

    def test_passing_case(self):
        output = to_tap(RESULTS, SUMMARY)
        assert "ok 1 - case_pass_1 (150ms)" in output

    def test_failing_case(self):
        output = to_tap(RESULTS, SUMMARY)
        assert "not ok 2 - case_fail_1 (200ms)" in output

    def test_error_case(self):
        output = to_tap(RESULTS, SUMMARY)
        assert "not ok 3 - case_error_1 (50ms)" in output

    def test_fault_case_tagged(self):
        output = to_tap(RESULTS, SUMMARY)
        assert "# FAULT" in output
        line = [l for l in output.split("\n") if "case_fault_1" in l][0]
        assert "# FAULT" in line

    def test_yaml_diagnostic_for_failure(self):
        output = to_tap(RESULTS, SUMMARY)
        assert "  ---" in output
        assert "  ..." in output
        assert "severity: fail" in output

    def test_summary_comments(self):
        output = to_tap(RESULTS, SUMMARY)
        assert "# total: 4" in output
        assert "# passed: 1" in output
        assert "# failed: 3" in output

    def test_empty_results(self):
        summary = RunSummary(total=0, passed=0, duration_ms=0.0)
        output = to_tap([], summary)
        assert "1..0" in output

    def test_all_passing(self):
        results = [RESULTS[0]]
        summary = RunSummary(total=1, passed=1, duration_ms=150.0)
        output = to_tap(results, summary)
        assert "not ok" not in output
        assert "ok 1 -" in output


class TestHTML:
    def test_contains_doctype(self):
        output = to_html(RESULTS, SUMMARY)
        assert "<!DOCTYPE html>" in output

    def test_contains_summary_counts(self):
        output = to_html(RESULTS, SUMMARY)
        assert ">4<" in output  # total
        assert ">1<" in output  # passed
        assert ">2<" in output  # failed
        assert ">1<" in output  # errors

    def test_contains_all_case_ids(self):
        output = to_html(RESULTS, SUMMARY)
        for r in RESULTS:
            assert r.case_id in output

    def test_fault_badge(self):
        output = to_html(RESULTS, SUMMARY)
        assert "FAULT" in output

    def test_status_badges(self):
        output = to_html(RESULTS, SUMMARY)
        assert 'class="badge pass"' in output
        assert 'class="badge fail"' in output
        assert 'class="badge error"' in output

    def test_step_details(self):
        output = to_html(RESULTS, SUMMARY)
        assert "Show steps" in output
        assert "setup" in output

    def test_stderr_in_output(self):
        output = to_html(RESULTS, SUMMARY)
        assert "exit code 1" in output

    def test_html_escaping(self):
        results = [
            CaseResult(
                case_id="xss<script>",
                status="pass",
                duration_ms=10.0,
                steps=[_step("op<tag>", stdout="<b>bold</b>")],
            ),
        ]
        summary = RunSummary(total=1, passed=1, duration_ms=10.0)
        output = to_html(results, summary)
        assert "<script>" not in output
        assert "&lt;script&gt;" in output

    def test_empty_results(self):
        summary = RunSummary(total=0, passed=0, duration_ms=0.0)
        output = to_html([], summary)
        assert "<!DOCTYPE html>" in output
        assert ">0<" in output
