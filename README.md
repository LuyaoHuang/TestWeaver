# TestWeaver

AI-native test case generation framework using dependency graphs.

TestWeaver is a modern rework of [depend-test-framework](https://github.com/LuyaoHuang/depend-test-framework), redesigned to be AI-native and agent-friendly. Define test operations with decorators in Python (or declaratively in YAML), and TestWeaver builds a dependency graph to automatically discover all valid test paths.

## Features

- **Decorator-based definitions** — define operations in Python with `@provides`, `@requires`, `@clears`, `@excludes`, `@graft`, `@cut`
- **Hierarchical state model** — states are trees (`vm.config.tpm`), matching the original framework's `Env` design
- **Automatic case generation** — dependency graph finds all valid paths to reach each test target
- **Operation verification** — attach verify callbacks to operations with `@verify_for` or the `verify` YAML field; runs automatically after each successful step
- **Parameter support** — two approaches for parameterized testing: parameter graph and parameter matrix
- **Multi-instance namespaces** — model multiple devices of the same type (`TPM:tpm0`, `TPM:tpm1`) with independent states in a single graph, wildcard queries (`TPM:tpm*.ready`), and generation strategies to control state-space explosion
- **Graph modifiers** — runtime modifiers (`EdgeGuard`, `TransientHook`, `TransitionObserver`) let operations influence future execution when the graph can't be fully static
- **Structured reporting** — output results as JSON, JUnit XML (CI integration), TAP (streaming), or HTML (visual reports)
- **Structured JSON output** — every command outputs machine-readable JSON
- **Graph visualization** — export dependency graphs as DOT (Graphviz) or Mermaid for visual exploration
- **Parallel test execution** — run independent test cases concurrently with `--workers`
- **Test case filtering** — select cases by ID pattern, target, step, or fault status with `-k`, `--target`, `--has-step`, `--fault-only`, `--no-fault`
- **Dry-run mode** — preview test cases without executing them with `--dry-run`; shows resolved commands, callables, and cleanup steps
- **Scalability controls** — prevent combinatorial explosion with `max_graph_nodes`, `max_path_depth`, and `max_state_depth` limits on graph building and case generation
- **Retry / flaky test handling** — automatic retries for failed cases with `--retries` and `--retry-delay`; flaky detection when a case fails then passes on retry
- **Lifecycle hooks** — `@suite_setup` / `@suite_teardown` run once before/after all cases; `@case_setup` / `@case_teardown` run before/after each case; teardown hooks always fire, even on failure
- **Case prioritization** — sort generated cases by strategy (`shortest`, `longest`, `target`, `total`, `fault-first`, `fault-last`, `random`) with `--sort`; assign operation priorities with `@priority(level)`
- **Progress reporting** — real-time progress bar during test execution with `--progress`; auto-detects TTY; shows pass/fail status per case
- **Logging infrastructure** — structured logging with `--verbose`, `--debug`, and `--log-file` flags; thread-aware output for parallel execution
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
from testweaver import action, check, cleanup, provides, requires, clears, verify_for

@action
@provides('file.exists')
def create_file(params):
    """Create a hello world file"""
    import subprocess
    subprocess.run('echo "hello world" > /tmp/test.txt', shell=True, check=True)

@verify_for('create_file')
def check_content(params):
    """Verify file contains hello world — runs automatically after create_file"""
    import subprocess
    subprocess.run('grep -q "hello world" /tmp/test.txt', shell=True, check=True)

@check
@requires('file.exists')
def check_file_exists(params):
    """Verify the file exists"""
    import subprocess
    subprocess.run('test -f /tmp/test.txt', shell=True, check=True)

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
  targets: [check_file_exists]
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
testweaver validate my_test.yaml     # Check for errors
testweaver generate my_test.yaml     # Generate test cases
testweaver run my_test.yaml          # Run tests (JSON output)
testweaver run my_test.yaml --format junit -o results.xml  # JUnit XML for CI
testweaver run my_test.yaml --format html -o report.html   # HTML report
testweaver run my_test.yaml -w 4     # Run tests with 4 parallel workers
testweaver run my_test.yaml --retries 3  # Retry failed cases up to 3 times
testweaver run my_test.yaml --dry-run     # Preview what would run without executing
testweaver run my_test.yaml -k "check-*"  # Run only cases matching a pattern
testweaver run my_test.yaml --sort shortest    # Run shortest cases first
testweaver generate my_test.yaml --sort target # Sort by operation priority
testweaver run my_test.yaml --progress     # Force progress bar on
testweaver run my_test.yaml -v       # Show execution logs on stderr
testweaver run my_test.yaml --debug --log-file run.log  # Debug logs to file
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
| `priority` | Integer priority level for case sorting (default: 0, higher = more important) |
| `run` | Shell command to execute (YAML-only mode) |
| `verify` | Shell command to verify the operation succeeded (runs after `run`) |

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
| `@verify_for(op_name)` | Attach as verify callback for the named operation |
| `@when_param(name, value)` | Require a specific parameter value (param graph) |
| `@unless_param(name, value)` | Exclude when a parameter value is set (param graph) |
| `@skip_when(**conditions)` | Skip operation when conditions match (param matrix) |
| `@suite_setup` | Run once before all test cases (lifecycle hook) |
| `@suite_teardown` | Run once after all test cases (lifecycle hook) |
| `@case_setup` | Run before each test case (lifecycle hook) |
| `@case_teardown` | Run after each test case (lifecycle hook) |
| `@timeout(seconds)` | Set per-operation timeout, overriding the global `--timeout` |
| `@priority(level)` | Set operation priority for case sorting (higher = more important) |

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

### Graph Visualization

Export the dependency graph as DOT (Graphviz) or Mermaid for visual exploration:

```bash
testweaver graph my_test.yaml --format dot          # DOT output to stdout
testweaver graph my_test.yaml --format dot -o g.dot # Save to file
testweaver graph my_test.yaml --format mermaid      # Mermaid output
```

Nodes are styled by role: initial state (circle/blue), dead-end states (octagon/salmon), and normal states (box/yellow). Edges are colored by operation type: actions (blue), setup (green), cleanup (red), and faults (orange).

Pipe DOT output to Graphviz to render an image:

```bash
testweaver graph my_test.yaml --format dot | dot -Tpng -o graph.png
```

Paste Mermaid output into any Mermaid-compatible renderer (GitHub markdown, Mermaid Live Editor, etc.).

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

## Operation Verification

Operations can have a verify callback that runs automatically after the operation succeeds. This keeps the dependency graph clean — verifications aren't state transitions, so they shouldn't be graph nodes.

### Python Module

Use `@verify_for` to attach a verify function to an operation:

```python
from testweaver import action, provides, verify_for

@action
@provides('rng.present')
def add_rng(params):
    print(f"virsh attach-device {params.get('guest_name')} rng.xml")

@verify_for('add_rng')
def verify_rng_in_vm(params):
    """Runs automatically after add_rng succeeds"""
    print(f"ssh {params.get('guest_name')} ls /dev/hwrng")
```

### YAML

Use the `verify` field for a shell command that runs after the operation:

```yaml
operations:
  - name: add_rng
    type: action
    provides: [rng.present]
    run: virsh attach-device $guest_name rng.xml
    verify: ssh $guest_name ls /dev/hwrng
```

### Behavior

- Verify runs only when the operation passes — skipped on step failure
- If verify fails, the case is marked as failed and cleanup runs
- Verify results appear in `StepResult.verify_result`
- Parameters are substituted in YAML verify commands just like `run`

See [docs/examples.md](docs/examples.md#operation-verification) for more examples.

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

## Lifecycle Hooks

Lifecycle hooks run at fixed points in the test execution, outside the dependency graph. Unlike `@setup` / `@cleanup` (which are graph nodes participating in pathfinding), lifecycle hooks always fire at their designated position.

| Hook | When it runs | Scope |
|------|-------------|-------|
| `@suite_setup` | Once before the first test case | Suite |
| `@suite_teardown` | Once after the last test case | Suite |
| `@case_setup` | Before each test case | Per-case |
| `@case_teardown` | After each test case | Per-case |

```python
from testweaver import (
    action, check, cleanup, provides, requires, clears,
    suite_setup, suite_teardown, case_setup, case_teardown,
)

@suite_setup
def start_test_environment(context):
    """Provision the test VM pool — runs once before any cases."""
    print(f"Starting environment for suite: {context['_suite_name']}")

@suite_teardown
def collect_suite_logs(context):
    """Gather logs after all cases complete — always runs, even on failure."""
    print("Collecting suite-level logs...")

@case_setup
def snapshot_state(context):
    """Take a state snapshot before each test case."""
    print(f"Snapshot before case: {context['_case_id']}")

@case_teardown
def collect_case_logs(context):
    """Collect per-case logs regardless of outcome."""
    print(f"Collecting logs for case {context['_case_id']} (status: {context.get('_status')})")

@action
@provides('ready')
def setup_service(params):
    pass

@check
@requires('ready')
def verify_service(params):
    pass

@cleanup
@requires('ready')
@clears('ready')
def teardown_service(params):
    pass
```

### Hook Context

All hooks receive a single `context` dict. Suite hooks get suite-level params plus `_suite_name` and `_case_count`. Case hooks get case-level params plus `_case` (the `TestCase` object) and `_case_id`. Teardown hooks additionally get `_status` (case status) or `_suite_setup_failed` (bool).

### Error Semantics

- **Suite setup failure** skips all test cases (marked as `error`); suite teardown still runs
- **Case setup failure** skips the case's main steps; cleanup and case teardown still run
- **Teardown failures** are recorded but don't change the case/suite status
- A failing hook does not prevent other hooks of the same type from running

### Parallel Execution

Suite hooks run in the main thread, outside the `ThreadPoolExecutor`. Case hooks run inside each case's thread. Each case gets its own `context` dict — no shared mutable state.

### Programmatic API

```python
from testweaver.engine import run_all

# run_all returns (case_results, suite_hook_results)
results, suite_hooks = run_all(cases, definition, workers=4)

for r in results:
    for hr in r.hook_results:
        print(f"  {hr.hook_type}: {hr.status} ({hr.duration_ms:.0f}ms)")
```

See [docs/examples.md](docs/examples.md#lifecycle-hooks) for more examples.

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

## Multi-Instance Namespaces

When testing systems with multiple devices of the same type (e.g., multiple TPMs, disks, or NICs), use the namespace separator `:` with additive parameter choices to model independent device instances in a single graph.

### Defining Instance Operations

Use `{param}` templates in state paths. The `:` separates the collection name from the instance ID:

```python
from testweaver import action, check, provides, requires

@action
@provides('vm.active.TPM:{tpm_id}.init')
def attach_tpm(params):
    print(f"Attaching TPM {params['tpm_id']}")

@action
@requires('vm.active.TPM:{tpm_id}.init')
@provides('vm.active.TPM:{tpm_id}.ready')
def configure_tpm(params):
    print(f"Configuring TPM {params['tpm_id']}")

@check
@requires('vm.active.TPM:tpm*.ready')  # wildcard: ANY instance ready
def check_any_tpm_ready(params):
    print("At least one TPM is ready")
```

### Declaring Instances

Use `mode: additive` on `param_choices` to expand templates into concrete operations that coexist in the same graph:

```yaml
suite:
  name: "Multi-TPM Verification"
  targets: [check_any_tpm_ready]
  param_choices:
    - name: tpm_id
      values: [tpm0, tpm1]
      mode: additive
```

This expands `attach_tpm` into `attach_tpm[tpm_id=tpm0]` and `attach_tpm[tpm_id=tpm1]`, each with independent state paths. The graph explores all orderings of device operations.

### Read-Write Separation

- **Write paths** (`provides`, `clears`, `cuts`, `grafts`): must be deterministic — use `{param}` templates, never `*`
- **Read paths** (`requires`, `excludes`): can use `*` wildcards for cross-instance queries

### Generation Strategies

Multi-instance graphs can produce many test cases. Control this with `generation_strategy`:

```yaml
suite:
  name: "Multi-Device Test"
  targets: [check_all_ready]
  generation_strategy: pairwise  # or: exhaustive, representative
```

| Strategy | Description |
|----------|-------------|
| `exhaustive` | (Default) All valid test paths |
| `pairwise` | Minimum subset covering all pairs of instance operations |
| `representative` | One test case per unique step-sequence shape |

See [docs/examples.md](docs/examples.md#multi-instance-namespaces) for full examples.

## CLI Reference

```bash
testweaver validate <file> [-v] [--debug]           # Validate definition
testweaver generate <file> [--format json|text] [-p key=value] [-s strategy] [-v]  # Generate cases
testweaver run <file> [-o file] [--timeout 300] [-w 4] [-p key=value]  # Run tests
               [-s shortest|longest|target|total|fault-first|fault-last|random]
               [--sort-seed N]                   # Sort cases by strategy
               [--retries N] [--retry-delay S]       # Retry failed cases
               [--format json|text|junit|tap|html]
               [--dry-run]                           # Preview without executing
               [--progress | --no-progress]              # Progress bar (default: auto-detect TTY)
               [--max-graph-nodes N] [--max-path-depth N] [--max-state-depth N]
               [-v] [--debug] [--log-file path]     # Logging options
testweaver analyze <results.json> [-d file]         # Analyze results
testweaver graph <file> [--format json|text|dot|mermaid] [-o file] [-v]  # Show/export graph
testweaver matrix <file> [--format json|text]       # Preview parameter combos
testweaver schema [--type definition|results|summary|test_case]  # Export JSON Schema
```

### Filtering Options

Both `generate` and `run` accept filtering options to select a subset of generated cases:

```bash
testweaver generate <file> -k "check-*"             # Cases with IDs matching a glob pattern
testweaver generate <file> -k "check-*" -k "fault-*"  # Multiple patterns (OR)
testweaver run <file> -t verify_tpm                  # Only cases targeting verify_tpm
testweaver run <file> --has-step install_swtpm       # Cases containing a specific step
testweaver run <file> --fault-only                   # Only fault-injection cases
testweaver run <file> --no-fault                     # Exclude fault-injection cases
testweaver run <file> -k "check-*" --no-fault        # Combine filters (AND)
```

| Option | Short | Description |
|--------|-------|-------------|
| `--filter` | `-k` | fnmatch glob pattern on case ID (repeatable, OR) |
| `--target` | `-t` | Keep cases targeting this operation (repeatable, OR) |
| `--has-step` | | Keep cases containing this step (repeatable, OR) |
| `--fault-only` | | Keep only fault-injection cases |
| `--no-fault` | | Exclude fault-injection cases |

All filter types are AND-combined: a case must match every specified criterion. Within each repeatable option, matching is OR (match any).

## Case Prioritization

By default, test cases run in generation order. Use `--sort` / `-s` to reorder them by strategy. Available on both `generate` and `run`.

```bash
testweaver run my_test.yaml --sort shortest          # Shortest cases first (smoke tests)
testweaver run my_test.yaml --sort longest            # Longest cases first (integration)
testweaver run my_test.yaml --sort target             # By target operation priority
testweaver run my_test.yaml --sort total              # By sum of all step priorities
testweaver run my_test.yaml --sort fault-first        # Fault cases before normal
testweaver run my_test.yaml --sort fault-last         # Normal cases before fault
testweaver run my_test.yaml --sort random             # Randomize order
testweaver run my_test.yaml --sort random --sort-seed 42  # Reproducible random
```

| Strategy | Description |
|----------|-------------|
| `shortest` | Fewer steps first — run quick smoke tests before longer paths |
| `longest` | More steps first — thorough integration tests first |
| `target` | Sort by target operation's `priority` value (descending) |
| `total` | Sort by sum of all step priorities (descending) |
| `fault-first` | Fault-injection cases before normal cases |
| `fault-last` | Normal cases before fault-injection cases |
| `random` | Shuffle order (use `--sort-seed` for reproducibility) |

### Operation Priority

Assign priority levels to operations with `@priority`. Higher values mean more important. The `target` and `total` sort strategies use these values.

```python
from testweaver import action, check, provides, requires, priority

@action
@priority(1)
@provides('config')
def basic_setup(params):
    pass

@action
@priority(5)
@provides('config.advanced')
@requires('config')
def advanced_setup(params):
    pass

@check
@priority(10)
@requires('config')
def critical_check(params):
    pass
```

In YAML:

```yaml
operations:
  - name: basic_setup
    type: action
    provides: [config]
    priority: 1

  - name: critical_check
    type: check
    requires: [config]
    priority: 10
```

With `--sort target`, cases targeting `critical_check` (priority 10) run before cases targeting lower-priority operations.

### Pipeline

Sorting applies after filtering: generate -> filter -> sort -> run. This means you can combine `--sort` with all filter options:

```bash
testweaver run my_test.yaml --no-fault --sort shortest -k "check-*"
```

### Programmatic API

```python
from testweaver.sorting import sort_cases
from testweaver.graph import generate_cases

cases = generate_cases(definition)
sorted_cases = sort_cases(cases, "target", operations=definition.operations)
sorted_cases = sort_cases(cases, "random", seed=42)
```

See [docs/examples.md](docs/examples.md#case-prioritization) for more examples.

## Parallel Execution

By default, test cases run sequentially. Use `--workers` / `-w` to run independent cases concurrently:

```bash
testweaver run my_test.yaml -w 4      # 4 parallel workers
testweaver run my_test.yaml -w 0      # Auto-detect from CPU count
```

Each test case runs in its own thread with independent state — no shared mutable data between cases. The underlying shell commands (`subprocess.run`) release the GIL, so threads achieve near-full parallelism for command-based operations.

| Workers | Behavior |
|---------|----------|
| `1` | (Default) Sequential execution |
| `N > 1` | Run up to N cases concurrently |
| `0` | Auto-detect based on CPU count |

Results are always returned in the same order as the generated cases, regardless of execution order.

**Note:** Use caution with parallel execution when test cases share external resources (VMs, files, network ports). Sequential execution (`-w 1`) is safer when cases may interfere with each other.

### Programmatic API

```python
from testweaver.engine import run_all
from testweaver.filtering import filter_cases
from testweaver.sorting import sort_cases
from testweaver.graph import build_graph, generate_cases

graph = build_graph(definition.operations)
cases = generate_cases(definition, graph)
cases = filter_cases(cases, ids=["check-*"], no_fault=True)
cases = sort_cases(cases, "shortest")  # optional: reorder before execution
results, suite_hooks = run_all(cases, definition, graph=graph, workers=4)
```

## Dry-Run Mode

Preview what test cases would be executed without actually running anything. Useful for verifying case generation, checking parameter substitution, and reviewing execution plans before committing to a long-running test suite.

```bash
testweaver run my_test.yaml --dry-run
testweaver run my_test.yaml --dry-run -p host=10.0.0.1   # With param overrides
testweaver run my_test.yaml --dry-run -k "check-*"       # With filters
testweaver run my_test.yaml --dry-run -o preview.txt     # Save to file
```

The output shows each case with its target, parameters, steps (with resolved shell commands), and cleanup steps:

```
Dry-run: 2 test case(s) would be executed

--- check-1 ---
Target: check_vm
Params: {'host': '192.168.1.1', 'vm_name': 'testvm'}
Steps:
  1. setup_host                          run: ssh $host echo ready  ->  ssh 192.168.1.1 echo ready
  2. start_vm                            run: virsh start $vm_name  ->  virsh start testvm
  3. check_vm                            run: virsh domstate $vm_name  ->  virsh domstate testvm
Cleanup:
  1. stop_vm                             run: virsh destroy $vm_name  ->  virsh destroy testvm
  2. teardown_host                       run: ssh $host shutdown  ->  ssh 192.168.1.1 shutdown

--- fault-bad_start-1 [FAULT] ---
...
```

For Python callable operations, the output shows the function's qualified name instead of a shell command:

```
  2. start_vm                            [callable: my_ops.start_vm]
```

All filtering options (`-k`, `--target`, `--has-step`, `--fault-only`, `--no-fault`) work with `--dry-run`. The `--format` flag is ignored since there are no execution results to format.

## Scalability Controls

TestWeaver's graph-based case generation can produce a combinatorial explosion on large definitions — many operations with overlapping state transitions create exponentially many graph nodes and test paths. Three controls prevent this:

| Control | YAML Field | CLI Flag | Default | What it limits |
|---------|-----------|----------|---------|----------------|
| Graph size | `max_graph_nodes` | `--max-graph-nodes` | 500 | Max nodes discovered during BFS graph building |
| Path depth | `max_path_depth` | `--max-path-depth` | 20 | Max steps in any test case path |
| State complexity | `max_state_depth` | `--max-state-depth` | 0 (off) | Skip states with more than N active entries |

```bash
testweaver run my_test.yaml --max-graph-nodes 100    # Smaller graph
testweaver run my_test.yaml --max-path-depth 10      # Shorter test cases
testweaver run my_test.yaml --max-state-depth 5      # Skip complex states
```

### YAML Configuration

```yaml
suite:
  name: large_test
  targets: [check_vm]
  max_graph_nodes: 200
  max_path_depth: 15
  max_state_depth: 8
```

CLI flags override YAML values. When a limit is hit during graph building, a warning is logged (visible with `-v` or `--debug`).

### When to Tune

- **`max_graph_nodes`** — lower this when graph building is slow or consuming too much memory. The graph has many nodes when operations create many independent states (e.g., multi-instance namespaces with several devices).
- **`max_path_depth`** — lower this when generated cases have too many steps. The default of 20 allows paths up to 20 edges long; most practical tests are much shorter.
- **`max_state_depth`** — set this when states accumulate many entries (e.g., multiple devices each with several sub-states). A value of 0 means no limit.

See [docs/examples.md](docs/examples.md#scalability-controls) for more examples.

## Per-Step Timeout

By default, every operation uses the global `--timeout` value (300s). You can override this per-operation when different steps have very different expected durations — e.g., a VM boot may need 600s while a `virsh` command should complete in 30s.

### Python Decorator

```python
from testweaver import action, provides, timeout

@action
@provides('vm.active')
@timeout(600)
def boot_vm(params):
    """Boot a VM — may take up to 10 minutes."""
    subprocess.run(['virsh', 'start', params['vm_name']], check=True)

@action
@provides('vm.config')
@timeout(30)
def define_vm(params):
    """Define a VM — should be fast."""
    subprocess.run(['virsh', 'define', params['xml_path']], check=True)
```

### YAML

```yaml
operations:
  - name: boot_vm
    type: action
    provides: [vm.active]
    requires: [vm.config]
    timeout: 600
    run: virsh start $vm_name

  - name: check_vm
    type: check
    requires: [vm.active]
    timeout: 30
    run: virsh domstate $vm_name | grep running
```

### Behavior

- Operations without `timeout` use the global `--timeout` CLI value (default 300s).
- Per-step timeout applies to both shell commands and Python callables.
- Callable timeout enforcement uses `signal.SIGALRM` (Linux) and is only available in the main thread. When using `--workers` > 1, callable timeout is not enforced in worker threads; shell commands always have subprocess-level timeout protection regardless.
- Dry-run mode (`--dry-run`) shows `[timeout=Xs]` for operations with per-step timeouts.

## Retry / Flaky Test Handling

Infrastructure tests are notoriously flaky — network timeouts, VM boot delays, transient service errors. TestWeaver can automatically retry failed test cases and detect flaky tests.

```bash
testweaver run my_test.yaml --retries 3                # Retry failed cases up to 3 times
testweaver run my_test.yaml --retries 2 --retry-delay 5  # Wait 5s between retries
testweaver run my_test.yaml --retries 2 -w 4           # Works with parallel execution
```

When a case fails and `--retries` is set, TestWeaver re-runs the entire case (including cleanup) up to N additional times. If the case passes on a retry, it is marked as **flaky** — the final status is "pass", but the `flaky` flag signals unreliable behavior.

| Option | Default | Description |
|--------|---------|-------------|
| `--retries` | `0` | Maximum number of retry attempts after the first run |
| `--retry-delay` | `0.0` | Seconds to wait between retry attempts |

### Output

The text format shows retry information inline:

```
Total: 5  Passed: 4  Failed: 1  Errors: 0
Retried: 2
Flaky: 1
Duration: 3200ms
  [PASS] check-1 (150ms)
  [PASS] check-2 [FLAKY] (retried 1x) (450ms)
  [FAIL] check-3 (retried 2x) (900ms)
  [PASS] check-4 (120ms)
  [PASS] check-5 (100ms)
```

All structured formats (JSON, JUnit XML, TAP, HTML) include retry metadata. JUnit XML uses `<flakyFailure>` elements (supported by Jenkins) and `<properties>` for retry counts. TAP adds `# FLAKY` directives. HTML reports show a collapsible "Retry attempts" section with per-attempt step details.

### Retry Behavior

- **Case-level retry** — the entire case (all steps + cleanup) runs again from scratch
- **Cleanup between attempts** — each failed attempt runs cleanup before the next attempt starts
- **Parallel-safe** — retries happen within each worker thread, no shared state
- **Final result wins** — `CaseResult.steps` and `status` reflect the last attempt
- **All attempts recorded** — `CaseResult.attempts` stores every attempt's steps and status
- **Flaky detection** — `CaseResult.flaky` is `True` when the case ultimately passed but failed on at least one earlier attempt

### Programmatic API

```python
from testweaver.engine import run_all, run_case_with_retries

# Via run_all (recommended)
results, suite_hooks = run_all(cases, definition, retries=3, retry_delay=2.0)

# Per-case (advanced)
result = run_case_with_retries(case, definition, retries=2, retry_delay=1.0)

# Inspect retry details
for r in results:
    if r.flaky:
        print(f"{r.case_id} is flaky (retried {r.retry_count}x)")
    if r.retry_count > 0 and r.status != "pass":
        print(f"{r.case_id} failed after {r.retry_count + 1} attempts")
```

See [docs/examples.md](docs/examples.md#retry--flaky-test-handling) for more examples.

## Logging

By default, TestWeaver produces no log output — only structured results on stdout and a brief progress message on stderr. Use logging flags to get execution visibility:

```bash
testweaver run my_test.yaml -v                    # INFO: case/step start/end, timing, graph stats
testweaver run my_test.yaml --debug               # DEBUG: commands, return codes, modifiers, env state
testweaver run my_test.yaml -v --log-file run.log  # Also write logs to a file
```

| Flag | Level | What it shows |
|------|-------|---------------|
| (default) | WARNING | Silent — only timeouts and errors |
| `--verbose` / `-v` | INFO | Case/step lifecycle, graph build stats, definition loading |
| `--debug` | DEBUG | Shell commands, return codes, callable names, edge guards, replanning, hooks, observers, cleanup |
| `--log-file <path>` | — | Write logs to a file (in addition to stderr) |

Logs go to **stderr** so they don't interfere with structured result output on stdout. When running with `--workers > 1`, log lines include the thread name for tracing parallel execution:

```
2026-05-14 10:30:00,123 INFO  [testweaver.engine] [Thread-1] Case started: check-1 (target=check, steps=3)
2026-05-14 10:30:00,124 INFO  [testweaver.engine] [Thread-2] Case started: check-2 (target=check, steps=3)
```

The `--verbose` and `--debug` flags are also available on `validate`, `generate`, and `graph` commands.

### Programmatic Logging

Each module uses Python's standard `logging` with loggers under the `testweaver` namespace. Configure them directly for programmatic use:

```python
import logging

logging.getLogger("testweaver").setLevel(logging.INFO)
logging.getLogger("testweaver").addHandler(logging.StreamHandler())

# Now engine, graph, schema, and loader all emit logs
results, suite_hooks = run_all(cases, definition)
```

## Progress Reporting

By default, TestWeaver auto-detects whether stderr is a TTY and shows a live progress bar during `testweaver run`. The progress bar displays overall completion, elapsed time, ETA, and the pass/fail status of each completed case.

```bash
testweaver run my_test.yaml                    # Auto-detect TTY
testweaver run my_test.yaml --progress         # Force progress bar on
testweaver run my_test.yaml --no-progress      # Force progress bar off
```

Example output:

```
Running 5 case(s)  [################----]  3/5  [PASS] check-3
```

### Behavior

- **Auto-detect** (default) — progress bar appears when stderr is a TTY; suppressed when piped
- **`--verbose` / `--debug`** — progress bar is auto-disabled to avoid interleaved output; logging provides superset information
- **`--format json/junit/tap/html`** — progress bar on stderr does not interfere with structured output on stdout
- **Parallel execution** — progress bar updates are thread-safe; cases appear as they complete (may be out-of-order)
- **Empty case list** — no progress bar shown

### Programmatic API

The `run_all()` function accepts an optional `on_progress` callback that fires after each case completes:

```python
from testweaver.engine import run_all
from testweaver.schema import ProgressEvent

def my_callback(event: ProgressEvent):
    print(f"[{event.index + 1}/{event.total}] {event.case_id}: {event.status}")

results, suite_hooks = run_all(cases, definition, on_progress=my_callback)
```

The `ProgressEvent` includes `case_id`, `status`, `duration_ms`, `index`, `total`, `is_fault`, `flaky`, and `retry_count`. The callback is invoked from worker threads in parallel mode — ensure your callback is thread-safe.

## Structured Reporting

The `run` command supports multiple output formats via `--format`:

| Format | Flag | Use Case |
|--------|------|----------|
| `json` | `--format json` | (Default) Machine-readable structured output |
| `text` | `--format text` | Human-readable summary |
| `junit` | `--format junit` | JUnit XML for CI integration (Jenkins, GitHub Actions, GitLab CI) |
| `tap` | `--format tap` | TAP version 13 streaming output |
| `html` | `--format html` | Self-contained HTML report with visual styling |

```bash
# JUnit XML for CI pipelines
testweaver run my_test.yaml --format junit -o results.xml

# TAP output for streaming consumers
testweaver run my_test.yaml --format tap

# HTML report for visual review
testweaver run my_test.yaml --format html -o report.html
```

All formats include fault-injection case tagging and can be combined with `--output` / `-o` to save to a file.

### Programmatic API

```python
from testweaver.reporters import to_junit_xml, to_tap, to_html
from testweaver.analyzer import summarize_run

summary = summarize_run(results)
junit_xml = to_junit_xml(results, summary, suite_name="My Suite")
tap_output = to_tap(results, summary)
html_report = to_html(results, summary)
```

See [docs/examples.md](docs/examples.md#structured-reporting) for format details and CI configuration examples.

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
