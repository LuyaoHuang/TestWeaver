from __future__ import annotations

import html
import platform
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.dom import minidom

from .schema import CaseResult, RunSummary


def to_junit_xml(
    results: list[CaseResult],
    summary: RunSummary,
    suite_name: str = "TestWeaver",
) -> str:
    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(testsuites, "testsuite")
    testsuite.set("name", suite_name)
    testsuite.set("tests", str(summary.total))
    testsuite.set("failures", str(summary.failed))
    testsuite.set("errors", str(summary.errors))
    testsuite.set("time", f"{summary.duration_ms / 1000:.3f}")
    testsuite.set("timestamp", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    testsuite.set("hostname", platform.node() or "localhost")

    for r in results:
        tc = ET.SubElement(testsuite, "testcase")
        tc.set("name", r.case_id)
        tc.set("classname", suite_name)
        tc.set("time", f"{r.duration_ms / 1000:.3f}")

        if r.status == "fail":
            first_fail = next(
                (s for s in r.steps if s.status == "fail"), None,
            )
            msg = ""
            body = ""
            if first_fail:
                msg = first_fail.error or f"{first_fail.operation} failed"
                body = first_fail.stderr or first_fail.error or ""
            failure = ET.SubElement(tc, "failure")
            failure.set("type", "TestFailure")
            failure.set("message", msg)
            failure.text = body

        elif r.status == "error":
            first_err = next(
                (s for s in r.steps if s.status == "error"), None,
            )
            msg = ""
            body = ""
            if first_err:
                msg = first_err.error or f"{first_err.operation} error"
                body = first_err.stderr or first_err.error or ""
            error = ET.SubElement(tc, "error")
            error.set("type", "TestError")
            error.set("message", msg)
            error.text = body

        stdout_parts = [s.stdout for s in r.steps if s.stdout]
        stderr_parts = [s.stderr for s in r.steps if s.stderr]
        if stdout_parts:
            so = ET.SubElement(tc, "system-out")
            so.text = "\n".join(stdout_parts)
        if stderr_parts:
            se = ET.SubElement(tc, "system-err")
            se.text = "\n".join(stderr_parts)

    rough = ET.tostring(testsuites, encoding="unicode", xml_declaration=False)
    dom = minidom.parseString(rough)
    return dom.toprettyxml(indent="  ", encoding=None)


def to_tap(results: list[CaseResult], summary: RunSummary) -> str:
    lines: list[str] = [
        "TAP version 13",
        f"1..{summary.total}",
    ]

    for i, r in enumerate(results, 1):
        status = "ok" if r.status == "pass" else "not ok"
        fault_tag = " # FAULT" if r.is_fault else ""
        lines.append(f"{status} {i} - {r.case_id} ({r.duration_ms:.0f}ms){fault_tag}")

        if r.status != "pass":
            first_bad = next(
                (s for s in r.steps if s.status in ("fail", "error")), None,
            )
            if first_bad:
                lines.append("  ---")
                lines.append(f"  message: '{first_bad.error or first_bad.operation + ' failed'}'")
                lines.append(f"  severity: {r.status}")
                lines.append(f"  at:")
                lines.append(f"    step: '{first_bad.operation}'")
                if first_bad.stderr:
                    stderr_escaped = first_bad.stderr.replace("'", "''")
                    lines.append(f"  stderr: '{stderr_escaped}'")
                lines.append("  ...")

    lines.append(f"# total: {summary.total}")
    lines.append(f"# passed: {summary.passed}")
    lines.append(f"# failed: {summary.failed + summary.errors}")
    lines.append("")
    return "\n".join(lines)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TestWeaver Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f5f5f5; color: #333; padding: 2rem; }}
  .summary {{ background: #fff; border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;
              box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .summary h1 {{ font-size: 1.4rem; margin-bottom: 1rem; }}
  .stats {{ display: flex; gap: 1.5rem; flex-wrap: wrap; }}
  .stat {{ text-align: center; }}
  .stat .value {{ font-size: 2rem; font-weight: bold; }}
  .stat .label {{ font-size: 0.85rem; color: #666; }}
  .stat.pass .value {{ color: #22863a; }}
  .stat.fail .value {{ color: #cb2431; }}
  .stat.error .value {{ color: #e36209; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
           overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  th {{ background: #24292e; color: #fff; text-align: left; padding: 0.75rem 1rem;
       font-weight: 600; font-size: 0.9rem; }}
  td {{ padding: 0.75rem 1rem; border-top: 1px solid #e1e4e8; font-size: 0.9rem; }}
  tr:hover {{ background: #f6f8fa; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
            font-size: 0.8rem; font-weight: 600; }}
  .badge.pass {{ background: #dcffe4; color: #22863a; }}
  .badge.fail {{ background: #ffdce0; color: #cb2431; }}
  .badge.error {{ background: #fff5b1; color: #e36209; }}
  .badge.fault {{ background: #f1e05a; color: #735c0f; margin-left: 0.5rem; }}
  details {{ margin-top: 0.25rem; }}
  details summary {{ cursor: pointer; color: #0366d6; font-size: 0.85rem; }}
  .step-list {{ margin: 0.5rem 0 0.5rem 1rem; font-size: 0.85rem; }}
  .step-list li {{ margin-bottom: 0.25rem; list-style: none; }}
  .step-list li::before {{ content: ""; display: inline-block; width: 8px; height: 8px;
                           border-radius: 50%; margin-right: 0.5rem; }}
  .step-list li.s-pass::before {{ background: #22863a; }}
  .step-list li.s-fail::before {{ background: #cb2431; }}
  .step-list li.s-error::before {{ background: #e36209; }}
  .step-list li.s-skip::before {{ background: #959da5; }}
  pre.output {{ background: #f6f8fa; padding: 0.5rem; border-radius: 4px; margin-top: 0.25rem;
                font-size: 0.8rem; overflow-x: auto; white-space: pre-wrap; word-break: break-all; }}
</style>
</head>
<body>
<div class="summary">
  <h1>TestWeaver Report</h1>
  <div class="stats">
    <div class="stat"><div class="value">{total}</div><div class="label">Total</div></div>
    <div class="stat pass"><div class="value">{passed}</div><div class="label">Passed</div></div>
    <div class="stat fail"><div class="value">{failed}</div><div class="label">Failed</div></div>
    <div class="stat error"><div class="value">{errors}</div><div class="label">Errors</div></div>
    <div class="stat"><div class="value">{duration}</div><div class="label">Duration</div></div>
  </div>
</div>
<table>
<thead><tr><th>Case</th><th>Status</th><th>Duration</th><th>Steps</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>
"""


def _format_duration(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.2f}s"


def _build_step_html(r: CaseResult) -> str:
    if not r.steps:
        return ""
    parts = ['<details><summary>Show steps</summary><ul class="step-list">']
    for s in r.steps:
        cls = f"s-{s.status}"
        label = html.escape(s.operation)
        dur = _format_duration(s.duration_ms)
        parts.append(f'<li class="{cls}">{label} ({dur})')
        if s.stderr:
            parts.append(f'<pre class="output">{html.escape(s.stderr)}</pre>')
        elif s.error:
            parts.append(f'<pre class="output">{html.escape(s.error)}</pre>')
        parts.append("</li>")
    parts.append("</ul></details>")
    return "\n".join(parts)


def to_html(results: list[CaseResult], summary: RunSummary) -> str:
    rows: list[str] = []
    for r in results:
        fault_badge = '<span class="badge fault">FAULT</span>' if r.is_fault else ""
        status_badge = f'<span class="badge {r.status}">{r.status.upper()}</span>{fault_badge}'
        step_detail = _build_step_html(r)
        rows.append(
            f"<tr>"
            f"<td>{html.escape(r.case_id)}</td>"
            f"<td>{status_badge}</td>"
            f"<td>{_format_duration(r.duration_ms)}</td>"
            f"<td>{step_detail}</td>"
            f"</tr>"
        )

    return _HTML_TEMPLATE.format(
        total=summary.total,
        passed=summary.passed,
        failed=summary.failed,
        errors=summary.errors,
        duration=_format_duration(summary.duration_ms),
        rows="\n".join(rows),
    )
