# Progress Reporting

Real-time progress bar during `testweaver run`, showing completion, ETA, and per-case pass/fail status.

## Basic Usage

```bash
testweaver run my_test.yaml                    # Auto-detect TTY (default)
testweaver run my_test.yaml --progress         # Force progress bar on
testweaver run my_test.yaml --no-progress      # Force progress bar off
```

When enabled, stderr shows a live-updating progress bar:

```
Running 10 case(s)  [################----]  8/10  00:00:12  [PASS] check-8
```

## Interaction with Other Flags

- `--verbose` / `--debug` — auto-disables progress bar to avoid interleaved output on stderr
- `--format json/junit/tap/html` — progress bar goes to stderr, structured output to stdout; no interference
- `--dry-run` — no progress bar (nothing to execute)
- `--workers N` — progress bar is thread-safe; updates arrive as cases complete

## Programmatic API

Pass an `on_progress` callback to `run_all()` for custom progress handling:

```python
from testweaver.engine import run_all
from testweaver.schema import ProgressEvent

events = []

def track_progress(event: ProgressEvent):
    events.append(event)
    pct = (event.index + 1) / event.total * 100
    print(f"  [{pct:.0f}%] {event.case_id}: {event.status} ({event.duration_ms:.0f}ms)")

results, suite_hooks = run_all(cases, definition, on_progress=track_progress)
print(f"Collected {len(events)} progress events")
```

With parallel workers, the callback is invoked from worker threads — ensure thread safety:

```python
import threading
from testweaver.engine import run_all
from testweaver.schema import ProgressEvent

lock = threading.Lock()
completed = 0

def threadsafe_progress(event: ProgressEvent):
    global completed
    with lock:
        completed += 1
        print(f"  [{completed}/{event.total}] {event.case_id}: {event.status}")

results, suite_hooks = run_all(
    cases, definition, workers=4, on_progress=threadsafe_progress,
)
```

## ProgressEvent Fields

| Field | Type | Description |
|-------|------|-------------|
| `case_id` | `str` | Test case identifier |
| `status` | `"pass" \| "fail" \| "error"` | Final case status |
| `duration_ms` | `float` | Total execution time in milliseconds |
| `index` | `int` | 0-based position in the original case list |
| `total` | `int` | Total number of cases in the run |
| `is_fault` | `bool` | Whether this is a fault-injection case |
| `flaky` | `bool` | Whether the case was flaky (failed then passed on retry) |
| `retry_count` | `int` | Number of retry attempts |
