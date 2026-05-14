# Structured Reporting

TestWeaver can output test results in multiple formats for different consumers.

## JUnit XML

JUnit XML is the standard format for CI/CD test result integration. Jenkins, GitHub Actions, and GitLab CI all parse it natively.

```bash
testweaver run my_test.yaml --format junit -o results.xml
```

Output structure:

```xml
<?xml version="1.0" ?>
<testsuites>
  <testsuite name="Hello World" tests="3" failures="1" errors="0"
             time="1.234" timestamp="2026-05-14T10:30:00+00:00" hostname="ci-node">
    <testcase name="check_file_exists-1" classname="Hello World" time="0.150"/>
    <testcase name="check_file_exists-2" classname="Hello World" time="0.200">
      <failure type="TestFailure" message="create_file failed">
        /tmp/hello.txt: Permission denied
      </failure>
      <system-err>/tmp/hello.txt: Permission denied</system-err>
    </testcase>
    <testcase name="check_file_exists-3" classname="Hello World" time="0.010">
      <system-out>hello world</system-out>
    </testcase>
  </testsuite>
</testsuites>
```

Key attributes for CI tools:
- `classname` — required by GitLab CI for proper grouping
- `time` — duration in seconds (converted from TestWeaver's milliseconds)
- `<failure>` vs `<error>` — assertion failures vs unexpected errors
- `<system-out>` / `<system-err>` — captured step output

### GitHub Actions Integration

```yaml
# .github/workflows/test.yml
- name: Run tests
  run: testweaver run my_test.yaml --format junit -o results.xml

- name: Publish test results
  uses: dorny/test-reporter@v1
  if: always()
  with:
    name: TestWeaver Results
    path: results.xml
    reporter: java-junit
```

### GitLab CI Integration

```yaml
# .gitlab-ci.yml
test:
  script:
    - testweaver run my_test.yaml --format junit -o results.xml
  artifacts:
    reports:
      junit: results.xml
```

## TAP (Test Anything Protocol)

TAP version 13 is a text-based streaming format. Each test result is printed as it completes, making it ideal for live monitoring.

```bash
testweaver run my_test.yaml --format tap
```

Output:

```
TAP version 13
1..3
ok 1 - check_file_exists-1 (150ms)
not ok 2 - check_file_exists-2 (200ms)
  ---
  message: 'create_file failed'
  severity: fail
  at:
    step: 'create_file'
  stderr: '/tmp/hello.txt: Permission denied'
  ...
ok 3 - check_file_exists-3 (10ms)
# total: 3
# passed: 2
# failed: 1
```

Fault-injection cases are tagged with a `# FAULT` directive:

```
not ok 4 - fault-create_file-1 (50ms) # FAULT
```

## HTML

A self-contained HTML page with inline CSS — no external dependencies, viewable in any browser.

```bash
testweaver run my_test.yaml --format html -o report.html
```

The report includes:
- Summary header with pass/fail/error counts and total duration
- Color-coded status badges (green/red/orange)
- Fault-injection badges for fault cases
- Expandable step-by-step details per case with stdout/stderr output

## Programmatic API

All formatters accept `list[CaseResult]` and `RunSummary`:

```python
from testweaver.engine import run_all
from testweaver.analyzer import summarize_run
from testweaver.reporters import to_junit_xml, to_tap, to_html

results, suite_hooks = run_all(cases, definition)
summary = summarize_run(results, suite_hook_results=suite_hooks)

# Generate reports
junit_xml = to_junit_xml(results, summary, suite_name="My Suite")
tap_output = to_tap(results, summary)
html_report = to_html(results, summary)

# Write to files
Path("results.xml").write_text(junit_xml)
Path("report.html").write_text(html_report)
```
