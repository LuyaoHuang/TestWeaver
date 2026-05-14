# Core Concepts

## Operations

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

## Decorators

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
| `@fault_for(op_name)` | Create a fault-injection variant of the named operation |

## Hierarchical State

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

## Graft and Cut

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

## Dependency Graph

TestWeaver builds a directed graph where:
- **Nodes** = hierarchical state trees (`Env` objects)
- **Edges** = operations that transition between states

The graph engine finds all valid paths from the initial empty state to states where each target's `requires` are satisfied.

## Multiple Paths = Multiple Test Cases

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

Operations can have a verify callback that runs automatically after the operation succeeds. Verifications aren't state transitions, so they shouldn't be graph nodes.

Use `@verify_for` in Python or the `verify` field in YAML. See [examples/verification.md](examples/verification.md) for details.

## Graph Modifiers

Runtime modifiers let callable operations influence future execution when the graph can't be fully static:

| Modifier | Purpose |
|----------|---------|
| `EdgeGuard` | Block a future operation, trigger replanning |
| `TransientHook` | Inject a one-shot step before a future operation |
| `TransitionObserver` | Run verification after matching operations |

See [examples/graph-modifiers.md](examples/graph-modifiers.md) for details.

## Graph Visualization

Export the dependency graph as DOT (Graphviz) or Mermaid for visual exploration:

```bash
testweaver graph my_test.yaml --format dot | dot -Tpng -o graph.png
testweaver graph my_test.yaml --format mermaid
```

See [examples/graph-visualization.md](examples/graph-visualization.md) for details.

## Lifecycle Hooks

Hooks run at fixed points in test execution, outside the dependency graph:

| Hook | When it runs |
|------|-------------|
| `@suite_setup` | Once before the first test case |
| `@suite_teardown` | Once after the last test case |
| `@case_setup` | Before each test case |
| `@case_teardown` | After each test case |

Unlike `@setup` / `@cleanup` (graph nodes), lifecycle hooks always fire at their designated position. See [examples/lifecycle-hooks.md](examples/lifecycle-hooks.md) for details.

## Parameter Support

Two approaches for parameterized testing:

- **Parameter Graph** (`param_choices`) — parameter values become states in the graph; use when parameters change which operations are available
- **Parameter Matrix** (`param_matrix`) — Cartesian product of axes with constraint filtering; use when parameters are data values

See [examples/parameters.md](examples/parameters.md) for details.

## Multi-Instance Namespaces

Model multiple devices of the same type (`TPM:tpm0`, `TPM:tpm1`) with independent states using the `:` namespace separator. Supports wildcard queries (`TPM:tpm*.ready`) and generation strategies to control state-space explosion.

See [examples/multi-instance.md](examples/multi-instance.md) for details.
