# TestWeaver

AI-native test case generation framework using dependency graphs.

TestWeaver is a modern rework of [depend-test-framework](https://github.com/LuyaoHuang/depend-test-framework), redesigned to be AI-native and agent-friendly. Define test operations with decorators in Python (or declaratively in YAML), and TestWeaver builds a dependency graph to automatically discover all valid test paths.

## Features

- **Decorator-based definitions** — define operations in Python with `@provides`, `@requires`, `@clears`, `@excludes`, `@graft`, `@cut`
- **Hierarchical state model** — states are trees (`vm.config.tpm`), matching the original framework's `Env` design
- **Automatic case generation** — dependency graph finds all valid paths to reach each test target
- **Parameter support** — two approaches for parameterized testing: parameter graph and parameter matrix
- **Graph modifiers** — runtime modifiers (`EdgeGuard`, `TransientHook`, `TransitionObserver`) let operations influence future execution when the graph can't be fully static
- **Structured JSON output** — every command outputs machine-readable JSON
- **Built-in analysis** — failure detection, debug suggestions, and performance summaries

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

### Python Modules (Recommended)

Define operations in Python with decorators:

```python
# my_ops.py
from testweaver import action, check, cleanup, provides, requires, clears

@action
@provides('file.exists')
def create_file(params):
    """Create a hello world file"""
    import subprocess
    subprocess.run('echo "hello world" > /tmp/test.txt', shell=True, check=True)

@check
@requires('file.exists')
def check_content(params):
    """Verify file contains hello world"""
    import subprocess
    subprocess.run('grep -q "hello world" /tmp/test.txt', shell=True, check=True)

@cleanup
@requires('file.exists')
@clears('file.exists')
def remove_file(params):
    """Remove the hello world file"""
    import subprocess
    subprocess.run('rm -f /tmp/test.txt', shell=True, check=True)
```

Reference the module from YAML:

```yaml
modules:
  - my_ops.py

suite:
  name: "Hello World"
  targets: [check_content]
  cleanup: true
```

Or run the Python file directly:

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

  - name: check_content
    type: check
    requires: [file.exists]
    run: grep -q "hello world" /tmp/hello.txt

  - name: remove_file
    type: cleanup
    requires: [file.exists]
    clears: [file.exists]
    run: rm -f /tmp/hello.txt

suite:
  name: "Hello World"
  targets: [check_content]
  cleanup: true
```

### Running

```bash
testweaver validate my_test.yaml     # Check for errors
testweaver generate my_test.yaml     # Generate test cases
testweaver run my_test.yaml          # Run tests
testweaver graph my_test.yaml        # Show dependency graph
```

## Concepts

### Operations

An operation is a single test step with dependency declarations:

| Field | Description |
|-------|-------------|
| `name` | Unique identifier (function name when using modules) |
| `type` | `action`, `check`, `setup`, or `cleanup` |
| `provides` | States this operation creates |
| `requires` | States that must be active before this operation can run |
| `clears` | States this operation removes (single node) |
| `excludes` | States that must NOT be active (prevents duplicates) |
| `grafts` | Copy a subtree (`src` -> `tgt`) |
| `cuts` | Remove an entire subtree |
| `run` | Shell command to execute (YAML-only mode) |

### Decorators

| Decorator | Description |
|-----------|-------------|
| `@action` | Marks operation as action type |
| `@check` | Marks operation as check type |
| `@setup` | Marks operation as setup type |
| `@cleanup` | Marks operation as cleanup type |
| `@provides(*states)` | Declares states this operation creates |
| `@requires(*states)` | Declares states this operation needs |
| `@clears(*states)` | Declares states this operation removes (single node) |
| `@excludes(*states)` | Declares states that must NOT be active |
| `@graft(src, tgt)` | Copy subtree from src to tgt |
| `@cut(*paths)` | Remove entire subtree |
| `@when_param(name, value)` | Require a specific parameter value (param graph) |
| `@unless_param(name, value)` | Exclude when a parameter value is set (param graph) |
| `@skip_when(**conditions)` | Skip operation when conditions match (param matrix) |

### Hierarchical State

States are dot-separated paths forming a tree. Setting `vm.config.tpm` makes `vm.config` and `vm` active (hierarchically). This models real system structure:

```
vm
├── config
│   ├── tpm
│   ├── disk
│   └── numa
└── active
    ├── tpm    (via graft from vm.config)
    └── disk
```

### Graft and Cut

**Graft** copies a subtree to a new location — used when starting a VM copies config to active state:

```python
@action
@requires('vm.config')
@excludes('vm.active')
@graft('vm.config', 'vm.active')
def start_guest(params):
    print(f"virsh start {params.get('guest_name')}")
```

**Cut** removes an entire subtree — used for cleanup:

```python
@action
@requires('vm.active')
@cut('vm.active')
def destroy_guest(params):
    print(f"virsh destroy {params.get('guest_name')}")
```

### Dependency Graph

TestWeaver builds a directed graph where:
- **Nodes** = hierarchical state trees (`Env` objects)
- **Edges** = operations that transition between states

The graph engine finds all valid paths from the initial empty state to states where each target's `requires` are satisfied.

### Multiple Paths = Multiple Test Cases

When multiple operations provide the same state, TestWeaver generates a test case for each path:

```python
@action
@provides('ready')
def setup_a(params):
    pass

@action
@provides('ready')
def setup_b(params):
    pass

@check
@requires('ready')
def verify(params):
    pass
```

This generates 2 test cases: one via `setup_a` and one via `setup_b`.

## Graph Modifiers

In real test environments, a step's execution can change what future steps are valid. Graph modifiers let callable operations return objects that influence execution flow at runtime.

| Modifier | Purpose | Example |
|----------|---------|---------|
| `EdgeGuard` | Block a future operation, trigger replanning | Hugepages disabled — block VM start |
| `TransientHook` | Inject a one-shot step before a future op | Restart libvirtd before next memtune |
| `TransitionObserver` | Run verification after matching operations | Check audit logs after device attach/detach |

```python
from testweaver import action, provides, EdgeGuard

@action
@provides('hugepage_config')
def configure_hugepages(params):
    if params.get('hugetlbfs_mount') == '':
        return EdgeGuard(blocked_op='start_vm', reason='hugepages disabled')
```

When the runner hits a blocked step, it queries the graph for an alternative path. The `CaseResult` includes `replanned=True` when this happens.

See [docs/examples.md](docs/examples.md#graph-modifiers) for full documentation and examples of all three modifier types.

## Parameter Support

TestWeaver supports two approaches for parameterized testing:

- **Parameter Graph** (`param_choices`) — parameter values become states in the graph; use when parameters change which operations are available
- **Parameter Matrix** (`param_matrix`) — Cartesian product of axes with constraint filtering; use when parameters are data values

```bash
testweaver run my_test.yaml -p guest_name=testvm     # CLI override
testweaver matrix my_test.yaml --format text          # Preview combinations
```

See [docs/examples.md](docs/examples.md#parameter-support) for full examples of both approaches.

## Virtualization Examples

The `examples/virt/` directory contains mock implementations of libvirt/QEMU test operations ported from depend-test-framework (VM lifecycle, vTPM, save/restore, snapshots, memory hotplug, CPU scheduling, and more).

```bash
testweaver generate examples/virt/vtpm_test.yaml --format text
testweaver run examples/virt/backing_chain_test.yaml --format text
```

See [docs/examples.md](docs/examples.md#virtualization-examples) for the full list.

## CLI Reference

```bash
testweaver validate <file>                          # Validate definition
testweaver generate <file> [--format json|text] [-p key=value]  # Generate cases
testweaver run <file> [-o results.json] [--timeout 300] [-p key=value]  # Run tests
testweaver analyze <results.json> [-d file]         # Analyze results
testweaver graph <file> [--format json|text]        # Show dependency graph
testweaver matrix <file> [--format json|text]       # Preview parameter combos
testweaver schema [--type definition|results|summary|test_case]  # Export JSON Schema
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
