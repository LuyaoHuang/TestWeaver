# Logging

TestWeaver uses Python's standard `logging` module throughout the engine, graph builder, definition loader, CLI, and now all supporting modules (filtering, sorting, reporting, analysis, etc.). By default, logging is silent (WARNING level). Use CLI flags to enable execution tracing.

## Quick Debugging

The fastest way to enable debug logging is the `TESTWEAVER_LOG` environment variable:

```bash
# Show everything without changing CLI arguments
TESTWEAVER_LOG=DEBUG testweaver run my_test.yaml

# Works with all subcommands
TESTWEAVER_LOG=INFO testweaver graph my_test.yaml
```

## Basic Usage

```bash
# Show case and step lifecycle events
testweaver run my_test.yaml -v

# Show everything: commands, return codes, modifiers, env state
testweaver run my_test.yaml --debug

# Show very detailed state transitions and decorator applications
testweaver run my_test.yaml --trace

# Write logs to a file while also printing to stderr
testweaver run my_test.yaml -v --log-file execution.log

# Debug graph building and case generation
testweaver generate my_test.yaml -v
testweaver graph my_test.yaml --debug
```

## Log Levels

| Level | Typical output |
|-------|---------------|
| WARNING (default) | Only timeouts and unexpected errors |
| INFO (`-v`) | `Case started: check-1`, `Step finished: setup status=pass (12ms)`, `Graph built: 5 nodes, 8 edges`, `Generated 3 test case(s)`, `Filtered: 2/5 case(s) matched`, `Sorted 3 case(s)`, `Debug suggestion: cause=Command timeout` |
| DEBUG (`--debug`) | `Executing command: echo hello (timeout=300s)`, `Command exit code: 0`, `Operation 'start_vm' is blocked by edge guard`, `Filtering 5 case(s): ids=...`, `Matrix expanded: 4/8 combinations (excluded 4)`, `Generating JUnit XML report` |
| TRACE (`--trace`) | `Env.set('vm.active')`, `Env.graft(src='vm.config', tgt='vm.saved')`, `Env.clear('vm.temp')` — every state mutation, plus all DEBUG output |

## Environment Variable

Set `TESTWEAVER_LOG` to any standard Python level name or the custom `TRACE` level:

```bash
TESTWEAVER_LOG=INFO testweaver run my_test.yaml
TESTWEAVER_LOG=DEBUG testweaver generate my_test.yaml
TESTWEAVER_LOG=TRACE testweaver run my_test.yaml --workers 2
```

The env var takes precedence over CLI flags, so you can force TRACE level even on commands that don't expose `--trace`.

## Parallel Execution Logs

When running with multiple workers (`-w N`), log lines include the thread name so you can trace which worker is executing each case:

```bash
testweaver run my_test.yaml -v -w 4
```

```
2026-05-14 10:30:00,123 INFO  [testweaver.engine] [Thread-1] Case started: check-1 (target=check, steps=3)
2026-05-14 10:30:00,124 INFO  [testweaver.engine] [Thread-2] Case started: check-2 (target=check, steps=3)
2026-05-14 10:30:00,200 INFO  [testweaver.engine] [Thread-1] Step finished: setup status=pass (75ms)
```

## Programmatic Configuration

For programmatic use, configure the `testweaver` logger directly:

```python
from testweaver import get_logger, TRACE
from testweaver.engine import run_all
from testweaver.graph import build_graph, generate_cases
from testweaver.log import configure

# Quick setup: enable DEBUG-level logging
configure(level="DEBUG")

# Or use TRACE for state-level detail
configure(level=TRACE)

# All modules now emit logs
graph = build_graph(definition.operations)
cases = generate_cases(definition, graph)
results, suite_hooks = run_all(cases, definition, graph=graph)

# For fine-grained control, configure per-module loggers
import logging
logging.getLogger("testweaver.engine").setLevel(logging.DEBUG)
logging.getLogger("testweaver.graph").setLevel(logging.WARNING)

# Use TestWeaver's get_logger helper with .trace() method
logger = get_logger(__name__)
logger.trace("Detailed state info: %s", data)
```

## Module Coverage

All TestWeaver modules now emit logs at appropriate levels:

| Module | Logs emitted |
|--------|-------------|
| `engine` | Step/case lifecycle, commands, hooks, edge guards, retries |
| `graph` | Graph build stats, node limits, case generation counts |
| `schema` | Definition loading, module discovery |
| `loader` | Module loading, operation extraction |
| `filtering` | Filter criteria, matched/total counts |
| `sorting` | Strategy selection, top-3 case order |
| `matrix` | Axis expansion, excluded combinations, skip-ops |
| `reporters` | Report generation (JUnit, TAP, HTML) |
| `analyzer` | Summarization, failure detection, debug suggestions |
| `env` | State mutations at TRACE level (set, unset, clear, graft) |
| `decorators` | Logger available for downstream use |
