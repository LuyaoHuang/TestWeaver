# Retry / Flaky Test Handling

Infrastructure tests frequently fail due to transient issues — network timeouts, VM boot delays, service restarts. TestWeaver retries failed cases automatically and flags flaky tests.

## Basic Usage

```bash
# Retry failed cases up to 3 times
testweaver run my_test.yaml --retries 3

# Add a delay between retries (useful when waiting for resources to recover)
testweaver run my_test.yaml --retries 2 --retry-delay 10

# Combine with parallel execution
testweaver run my_test.yaml --retries 2 --retry-delay 5 -w 4
```

## How Retries Work

When a test case fails (status `"fail"` or `"error"`) and `--retries` is greater than 0:

1. The failed attempt is recorded (including all steps and cleanup)
2. TestWeaver waits `--retry-delay` seconds (if set)
3. The entire case runs again from scratch — fresh setup, steps, and cleanup
4. If the case passes, it's marked as **flaky** and execution continues
5. If it fails again, repeat until retries are exhausted

Each attempt is independent — cleanup runs at the end of every attempt, and the next attempt starts from a clean state. This is critical for infrastructure testing where a failed VM start needs cleanup before retry.

## Flaky Detection

A test case is marked as **flaky** when:
- It ultimately passes (`status == "pass"`)
- But at least one earlier attempt failed

Flaky cases are a signal that the test or the system under test has intermittent issues. The `CaseResult` carries both the final (passing) result and the full history:

```python
result = run_case_with_retries(case, definition, retries=2)

if result.flaky:
    print(f"Case {result.case_id} is flaky!")
    print(f"  Final status: {result.status}")
    print(f"  Retries needed: {result.retry_count}")
    for att in result.attempts:
        print(f"  Attempt {att.attempt}: {att.status} ({att.duration_ms:.0f}ms)")
```

## Report Output with Retries

### Text Format

```
Total: 4  Passed: 3  Failed: 1  Errors: 0
Retried: 2
Flaky: 1
Duration: 5200ms
  [PASS] check-1 (150ms)
  [PASS] check-2 [FLAKY] (retried 1x) (800ms)
  [FAIL] check-3 (retried 2x) (1500ms)
  [PASS] check-4 (100ms)
```

### JUnit XML

Flaky cases include `<flakyFailure>` elements (Jenkins convention) and `<properties>` with retry metadata:

```xml
<testcase name="check-2" classname="MyTest" time="0.800">
  <properties>
    <property name="retry_count" value="1"/>
    <property name="flaky" value="true"/>
  </properties>
  <flakyFailure type="Attempt1" message="network timeout">
    Connection refused: 192.168.1.100:22
  </flakyFailure>
</testcase>
```

### TAP

```
ok 2 - check-2 (800ms) # FLAKY
  ---
  retry_count: 1
  flaky: true
  ...
# retried: 2
# flaky: 1
```

### HTML

The HTML report shows:
- A **FLAKY** badge (yellow) next to the status
- A **Flaky** count in the summary stats
- A collapsible **"Show retry attempts"** section with per-attempt step details and status badges

## Programmatic API

```python
from testweaver.engine import run_all, run_case_with_retries
from testweaver.analyzer import summarize_run

# Run all cases with retries
results, suite_hooks = run_all(cases, definition, retries=3, retry_delay=2.0, workers=4)
summary = summarize_run(results, suite_hook_results=suite_hooks)

print(f"Flaky cases: {summary.flaky}")
print(f"Cases retried: {summary.retried}")

# Filter flaky results
flaky_cases = [r for r in results if r.flaky]
for r in flaky_cases:
    print(f"  {r.case_id}: passed after {r.retry_count} retry(s)")

# Access attempt history
for r in results:
    if r.attempts:
        for att in r.attempts:
            print(f"  Attempt {att.attempt}: {att.status} ({att.duration_ms:.0f}ms)")
            for step in att.steps:
                print(f"    {step.operation}: {step.status}")
```

## CaseResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `retry_count` | `int` | Number of retries performed (0 = ran once, no retries) |
| `flaky` | `bool` | `True` if the case ultimately passed but failed on earlier attempt(s) |
| `attempts` | `list[AttemptResult]` | All attempt results (only populated when `retry_count > 0`) |

Each `AttemptResult` contains:

| Field | Type | Description |
|-------|------|-------------|
| `attempt` | `int` | 1-indexed attempt number |
| `steps` | `list[StepResult]` | Steps executed in this attempt |
| `status` | `str` | `"pass"`, `"fail"`, or `"error"` |
| `duration_ms` | `float` | Duration of this attempt |
