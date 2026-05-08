# TestWeaver

AI-native test case generation framework using dependency graphs.

TestWeaver is a modern rework of [depend-test-framework](https://github.com/LuyaoHuang/depend-test-framework), redesigned to be AI-native and agent-friendly. The original framework used Python decorators and LSTM-based scoring; TestWeaver replaces those with declarative YAML definitions, structured JSON output, and JSON Schema exports — making it easy for AI agents to generate, run, and analyze tests.

Define your test operations in YAML with natural language descriptions, and TestWeaver builds a dependency graph to find all valid test paths.

## Features

- **Declarative YAML definitions** — define operations with `provides`, `requires`, and `clears` instead of writing code
- **Automatic case generation** — dependency graph finds all valid paths to reach each test target
- **Structured JSON output** — every command outputs machine-readable JSON, designed for AI agent consumption
- **JSON Schema export** — AI agents can generate valid definitions without examples
- **Built-in analysis** — failure detection, debug suggestions, and performance summaries

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

Create a test definition file (`my_test.yaml`):

```yaml
operations:
  - name: create_file
    description: "Create a hello world file"
    type: action
    provides: [file.exists]
    run: echo "hello world" > /tmp/hello.txt

  - name: check_content
    description: "Verify file contains hello world"
    type: check
    requires: [file.exists]
    run: grep -q "hello world" /tmp/hello.txt

  - name: remove_file
    description: "Remove the hello world file"
    type: cleanup
    requires: [file.exists]
    clears: [file.exists]
    run: rm -f /tmp/hello.txt

suite:
  name: "Hello World"
  description: "Simple file creation and verification test"
  targets: [check_content]
  cleanup: true
```

Run it:

```bash
# Validate the definition
testweaver validate my_test.yaml

# Generate test cases
testweaver generate my_test.yaml

# Run tests and save results
testweaver run my_test.yaml --output results.json

# Analyze results
testweaver analyze results.json -d my_test.yaml
```

## Concepts

### Operations

An operation is a single test step. Each operation declares:

| Field | Description |
|-------|-------------|
| `name` | Unique identifier |
| `description` | Natural language description (for AI agents and humans) |
| `type` | `action`, `check`, `setup`, or `cleanup` |
| `provides` | State keys this operation creates |
| `requires` | State keys that must be active before this operation can run |
| `clears` | State keys this operation removes |
| `run` | Shell command to execute |
| `params` | Parameter definitions with types and defaults |

### Dependency Graph

TestWeaver builds a directed graph where:
- **Nodes** = sets of active states (e.g., `{vm.defined}`, `{vm.defined, vm.running}`)
- **Edges** = operations that transition between states

The graph engine finds all valid paths from the initial empty state `{}` to states where each target's `requires` are satisfied.

### Multiple Paths = Multiple Test Cases

When multiple operations provide the same state, TestWeaver generates a test case for each path:

```yaml
operations:
  - name: create_with_echo
    type: action
    provides: [file.exists]
    run: echo "hello" > /tmp/test.txt

  - name: create_with_touch
    type: action
    provides: [file.exists]
    run: touch /tmp/test.txt

  - name: check_file
    type: check
    requires: [file.exists]
    run: test -f /tmp/test.txt
```

This generates 2 test cases: one using `create_with_echo` and one using `create_with_touch`.

## CLI Reference

```bash
# Validate a test definition
testweaver validate <file.yaml>

# Generate test cases (JSON or text)
testweaver generate <file.yaml> [--format json|text]

# Run tests
testweaver run <file.yaml> [--output results.json] [--timeout 300] [--format json|text]

# Analyze results (with optional definition for debug suggestions)
testweaver analyze <results.json> [-d file.yaml]

# Show dependency graph
testweaver graph <file.yaml> [--format json|text]

# Export JSON Schema (for AI agents to generate valid definitions)
testweaver schema [--type definition|results|summary|test_case]
```

## For AI Agents

TestWeaver is designed to be used by AI agents:

1. **Get the schema**: `testweaver schema --type definition` returns the JSON Schema for test definitions
2. **Generate a definition**: Write a YAML file matching the schema
3. **Validate**: `testweaver validate <file>` checks for errors
4. **Generate & run**: `testweaver run <file> --output results.json` executes and returns structured results
5. **Debug failures**: `testweaver analyze results.json -d <file>` provides failure details and suggestions

All commands output JSON by default — no log parsing required.

## License

MIT
