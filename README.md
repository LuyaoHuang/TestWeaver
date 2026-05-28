# TestWeaver

AI-native test case generation framework using dependency graphs.

TestWeaver is a modern rework of [depend-test-framework](https://github.com/LuyaoHuang/depend-test-framework), redesigned to be AI-native and agent-friendly. Define test operations with decorators in Python (or declaratively in YAML), and TestWeaver builds a dependency graph to automatically discover all valid test paths.

## Features

**Core**
- Decorator-based definitions — `@provides`, `@requires`, `@clears`, `@excludes`, `@graft`, `@cut`
- Hierarchical state model — states are trees (`vm.config.tpm`)
- Automatic case generation — dependency graph finds all valid paths to each target
- Runtime data flow — operations pass dynamic data (UUIDs, IPs) through `env` node values
- Operation verification — `@verify_for` / `verify` YAML field
- Graph modifiers — `EdgeGuard`, `TransientHook`, `TransitionObserver` for runtime decisions

**Parameterization**
- Parameter graph (`param_choices`) — parameters affect which operations are available
- Parameter matrix (`param_matrix`) — Cartesian product with constraint filtering
- Multi-instance namespaces — `TPM:tpm0`, `TPM:tpm1` with wildcard queries and generation strategies

**Execution**
- Parallel execution — `--workers N` for concurrent test cases
- Retry / flaky handling — `--retries` with automatic flaky detection
- Per-step timeout — `@timeout(seconds)` per operation
- Lifecycle hooks — `@suite_setup`, `@suite_teardown`, `@case_setup`, `@case_teardown`
- Dry-run mode — `--dry-run` to preview without executing

**Output & Analysis**
- Structured reporting — JSON, JUnit XML, TAP, HTML
- Graph visualization — DOT (Graphviz) and Mermaid export
- Case filtering — `-k`, `--target`, `--has-step`, `--fault-only`
- Case prioritization — `--sort shortest|longest|target|total|fault-first|random`
- Progress reporting — live progress bar with `--progress`
- Logging — `--verbose`, `--debug`, `--log-file`

**Assertions**
- Fluent assertion API — `assert_that(value).equals(expected).greater_than(0)`
- Chained assertions with rich expected-vs-actual diffs
- `assert_raises` context manager for exception testing

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

### Python Module

```python
# my_ops.py
from testweaver import action, check, cleanup, provides, requires, clears, verify_for

@action
@provides('file.exists')
def create_file(params, env):
    import subprocess
    subprocess.run('echo "hello world" > /tmp/test.txt', shell=True, check=True)

@verify_for('create_file')
def check_content(params, env):
    import subprocess
    subprocess.run('grep -q "hello world" /tmp/test.txt', shell=True, check=True)

@check
@requires('file.exists')
def check_file_exists(params, env):
    import subprocess
    subprocess.run('test -f /tmp/test.txt', shell=True, check=True)

@cleanup
@requires('file.exists')
@clears('file.exists')
def remove_file(params, env):
    import subprocess
    subprocess.run('rm -f /tmp/test.txt', shell=True, check=True)
```

```bash
testweaver run my_ops.py --format text
```

### YAML-Only Mode

```yaml
operations:
  - name: create_file
    type: action
    provides: [file.exists]
    run: echo "hello world" > /tmp/hello.txt
    verify: grep -q "hello world" /tmp/hello.txt

  - name: check_file_exists
    type: check
    requires: [file.exists]
    run: test -f /tmp/hello.txt

  - name: remove_file
    type: cleanup
    requires: [file.exists]
    clears: [file.exists]
    run: rm -f /tmp/hello.txt

suite:
  name: "Hello World"
  targets: [check_file_exists]
  cleanup: true
```

### Running

```bash
testweaver validate my_test.yaml          # Check for errors
testweaver generate my_test.yaml          # Generate test cases
testweaver run my_test.yaml               # Run tests (JSON output)
testweaver run my_test.yaml --format text # Human-readable output
testweaver graph my_test.yaml --format dot | dot -Tpng -o graph.png  # Visualize
```

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Tutorial: build your first test suite step by step |
| [Core Concepts](docs/concepts.md) | Operations, states, dependency graph, modifiers, parameters |
| [CLI Reference](docs/cli-reference.md) | All commands and flags |

### Examples

| Topic | Description |
|-------|-------------|
| [Parameters](docs/examples/parameters.md) | Parameter graph and matrix |
| [Multi-Instance](docs/examples/multi-instance.md) | Multiple devices with independent states |
| [Verification](docs/examples/verification.md) | Operation verification callbacks |
| [Graph Modifiers](docs/examples/graph-modifiers.md) | EdgeGuard, TransientHook, TransitionObserver |
| [Graph Visualization](docs/examples/graph-visualization.md) | DOT and Mermaid export |
| [Filtering](docs/examples/filtering.md) | Select test case subsets |
| [Prioritization](docs/examples/prioritization.md) | Sort cases by strategy |
| [Dry-Run](docs/examples/dry-run.md) | Preview without executing |
| [Scalability](docs/examples/scalability.md) | Graph size and path depth controls |
| [Reporting](docs/examples/reporting.md) | JUnit XML, TAP, HTML output |
| [Retry](docs/examples/retry.md) | Retry and flaky test handling |
| [Logging](docs/examples/logging.md) | Logging configuration |
| [Progress](docs/examples/progress.md) | Progress bar and callbacks |
| [Lifecycle Hooks](docs/examples/lifecycle-hooks.md) | Suite and case setup/teardown |
| [Data Flow](docs/examples/data-flow.md) | Passing runtime data between operations |
| [Assertions](docs/examples/assertions.md) | Fluent assertion API with chaining and diffs |
| [Virtualization](docs/examples/virtualization.md) | libvirt/QEMU example modules |

## Virtualization Examples

The `examples/virt/` directory contains mock implementations of libvirt/QEMU test operations (VM lifecycle, vTPM, save/restore, disk management, and more). See [Virtualization Examples](docs/examples/virtualization.md).

```bash
testweaver generate examples/virt/vtpm_test.yaml --format text
testweaver run examples/virt/backing_chain_test.yaml --format text
```

## For AI Agents

TestWeaver is designed to be used by AI agents:

1. **Get the schema**: `testweaver schema --type definition` returns the JSON Schema
2. **Generate a definition**: Write a YAML file matching the schema
3. **Validate**: `testweaver validate <file>` checks for errors
4. **Run**: `testweaver run <file> --output results.json` returns structured results
5. **Debug**: `testweaver analyze results.json -d <file>` provides failure details

All commands output JSON by default.

## License

MIT
