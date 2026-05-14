# Logging

TestWeaver uses Python's standard `logging` module throughout the engine, graph builder, definition loader, and CLI. By default, logging is silent (WARNING level). Use CLI flags to enable execution tracing.

## Basic Usage

```bash
# Show case and step lifecycle events
testweaver run my_test.yaml -v

# Show everything: commands, return codes, modifiers, env state
testweaver run my_test.yaml --debug

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
| INFO (`-v`) | `Case started: check-1`, `Step finished: setup status=pass (12ms)`, `Graph built: 5 nodes, 8 edges`, `Generated 3 test case(s)` |
| DEBUG (`--debug`) | `Executing command: echo hello (timeout=300s)`, `Command exit code: 0`, `Operation 'start_vm' is blocked by edge guard`, `Replanned around 'start_vm': new path [...]`, `Firing transient hook before 'check_memtune'` |

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
import logging
from testweaver.engine import run_all
from testweaver.graph import build_graph, generate_cases

# Enable INFO-level logging to stderr
tw_logger = logging.getLogger("testweaver")
tw_logger.setLevel(logging.INFO)
tw_logger.addHandler(logging.StreamHandler())

# All modules (engine, graph, schema, loader) now emit logs
graph = build_graph(definition.operations)
cases = generate_cases(definition, graph)
results, suite_hooks = run_all(cases, definition, graph=graph)

# For fine-grained control, configure per-module loggers
logging.getLogger("testweaver.engine").setLevel(logging.DEBUG)
logging.getLogger("testweaver.graph").setLevel(logging.WARNING)
```
