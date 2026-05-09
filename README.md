# TestWeaver

AI-native test case generation framework using dependency graphs.

TestWeaver is a modern rework of [depend-test-framework](https://github.com/LuyaoHuang/depend-test-framework), redesigned to be AI-native and agent-friendly. Define test operations with decorators in Python (or declaratively in YAML), and TestWeaver builds a dependency graph to automatically discover all valid test paths.

## Features

- **Decorator-based definitions** — define operations in Python with `@provides`, `@requires`, `@clears`, `@excludes`, `@graft`, `@cut`
- **Hierarchical state model** — states are trees (`vm.config.tpm`), matching the original framework's `Env` design
- **Automatic case generation** — dependency graph finds all valid paths to reach each test target
- **Parameter support** — two approaches for parameterized testing: parameter graph and parameter matrix
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

## Parameter Support

TestWeaver offers two approaches for parameterized testing.

### Approach 1: Parameter Graph (`param_choices`)

Parameter values become states in the dependency graph. The graph engine naturally discovers all valid paths for each parameter combination. Use this when parameters change *which operations are available*.

```python
# vtpm_ops.py
from testweaver import action, check, provides, requires, excludes, when_param

@action
@when_param('tpm_backend', 'emulator')
@provides('swtpm_installed')
@excludes('swtpm_installed')
def install_swtpm(params):
    """Only runs when tpm_backend=emulator"""
    print("yum install swtpm swtpm-tools -y")

@action
@requires('vm.config')
@provides('vm.config.tpm')
def add_tpm(params):
    print(f"Adding TPM to {params.get('guest_name')}")

@check
@requires('vm.active.tpm')
def verify_tpm(params):
    print("Checking /dev/tpm0 inside guest")
```

```yaml
modules:
  - vtpm_ops.py

suite:
  name: vtpm
  targets: [verify_tpm]
  param_choices:
    - name: tpm_backend
      values: [emulator, passthrough]
```

The graph generates different test paths: emulator paths go through `install_swtpm`, passthrough paths skip it.

### Approach 2: Parameter Matrix (`param_matrix`)

Defines parameter axes and constraint rules. Generates the Cartesian product of values, filters invalid combinations, and runs each valid combination through the graph. Use this when parameters are *data values* that don't change graph structure.

```yaml
modules:
  - schedinfo_ops.py

suite:
  name: schedinfo
  targets: [check_cpu_shares]
  params:
    guest_name: testvm
  param_matrix:
    axes:
      - name: cpu_shares
        values: [512, 1024, 2048]
      - name: vcpu_count
        values: [1, 2, 4]
    constraints:
      - when: {cpu_shares: 2048, vcpu_count: 1}
        exclude: true
        reason: "Invalid combo: high shares with single vCPU"
```

You can also use the `@skip_when` decorator on operations:

```python
@action
@skip_when(vcpu_count=1)
@requires('vm.active')
@provides('vm.schedinfo.numa_balanced')
def enable_numa_balancing(params):
    """Skip for single-vCPU guests"""
    pass
```

### CLI Parameter Override

Override or add parameters from the command line:

```bash
testweaver run my_test.yaml -p guest_name=testvm -p timeout=60
testweaver matrix my_test.yaml --format text   # Preview parameter combinations
```

## Virtualization Examples

The `examples/virt/` directory contains mock implementations of libvirt/QEMU test operations, ported from depend-test-framework:

| Module | Operations | Description |
|--------|-----------|-------------|
| `vm_basic.py` | 4 | Guest lifecycle: define, start, destroy, undefine |
| `vtpm.py` | 11 | vTPM device management with param_choices (emulator vs passthrough) |
| `save_restore.py` | 8 | Save/restore using graft+cut migrate pattern |
| `vdisk.py` | 2 | Virtual disk attach and verify |
| `backing_chain.py` | 6 | Snapshot management with block pull/commit |
| `schedinfo.py` | 7 | CPU scheduling parameters |
| `numa.py` | 1 | NUMA topology configuration |
| `mem_device.py` | 4 | Memory hotplug |

Try them:

```bash
testweaver generate examples/virt/vdisk_test.yaml --format text
testweaver run examples/virt/backing_chain_test.yaml --format text
testweaver graph examples/virt/save_restore_test.yaml --format text

# Parameter graph: emulator vs passthrough generate different test paths
testweaver generate examples/virt/vtpm_test.yaml --format text

# Parameter matrix: test cpu_shares with 3 values
testweaver generate examples/virt/schedinfo_test.yaml --format text
testweaver matrix examples/virt/schedinfo_test.yaml --format text
```

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
