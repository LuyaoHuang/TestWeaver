# Graph Modifiers

In real test environments, a step's execution can change what future steps are valid. For example, disabling hugepages makes VM start impossible, or setting memory tuning requires a libvirtd restart before the next operation. The static dependency graph can't model these runtime decisions.

Graph modifiers let callable operations return objects that influence execution flow. The runner processes them during case execution — no changes to the graph engine or case generation are needed.

## EdgeGuard

Blocks a future operation, forcing the runner to find an alternative path through the dependency graph (replanning). Use when a step discovers that a later step is now invalid.

```python
from testweaver import action, provides, excludes, EdgeGuard

@action
@provides('hugepage_config')
@excludes('hugepage_config')
def configure_hugepages(params):
    mount = params.get('hugetlbfs_mount', '/dev/hugepages')
    if mount == '':
        return EdgeGuard(
            blocked_op='start_vm',
            reason='hugepages disabled by empty mount path',
        )
```

When the runner encounters a blocked operation in the remaining steps, it queries the dependency graph for an alternative path that avoids the blocked operation. If no alternative exists, the case ends with an error. The `CaseResult` includes `replanned=True` and `replan_reason` when replanning occurs.

Replanning requires the graph to be passed to `run_case` / `run_all`:

```python
from testweaver.graph import build_graph, generate_cases
from testweaver.engine import run_all

graph = build_graph(definition.operations)
cases = generate_cases(definition, graph)
results, suite_hooks = run_all(cases, definition, graph=graph)
```

## TransientHook

Injects a one-shot step before a future operation. The hook fires once and is automatically removed. Use for temporary obligations like "restart a service before the next matching operation".

```python
from testweaver import action, provides, requires, TransientHook

@action
@requires('vm.active')
@provides('vm.active.memtune')
def set_memtune(params):
    limit = params.get('hard_limit', 1048576)
    print(f"virsh memtune --hard-limit {limit}")

    if params.get('restart_libvirtd'):
        def restart(p):
            print("systemctl restart libvirtd")

        return TransientHook(
            before_op='check_memtune',
            action=restart,
            name='restart_libvirtd',
            reason='libvirtd restart required after memtune',
        )
```

The injected step appears in `CaseResult.steps` with `injected=True`.

## TransitionObserver

Registers a persistent verification callback that runs after every execution of a watched operation, for the remainder of the case. Does not affect graph validity or case generation.

```python
from testweaver import action, provides, requires, TransitionObserver

@action
@requires('vm.active')
@provides('vm.active.memdevice')
def attach_mem_device(params):
    print("virsh attach-device mem.xml")

    def check_audit(p):
        print("ausearch -m VIRT_RESOURCE -ts recent")

    return TransitionObserver(
        watch_ops=['attach_mem_device', 'detach_mem_device'],
        verify=check_audit,
        name='audit_log_check',
        reason='verify audit trail after memory device changes',
    )
```

Observer results are attached to the corresponding `StepResult.observer_results` list. If the verify callable raises an exception, the case is marked as failed.

## Modifier Summary

| Modifier | Purpose | Lifetime | Affects graph? |
|----------|---------|----------|----------------|
| `EdgeGuard` | Block a future operation, trigger replan | Rest of case | Yes (replan) |
| `TransientHook` | Inject a step before a future operation | One-shot | No |
| `TransitionObserver` | Verify after matching operations | Rest of case | No |

## Full Example

See `examples/modifiers_demo.py` and `examples/modifiers_demo.yaml` for a complete working example that demonstrates all three modifier types in a VM testing scenario.

```bash
# Normal run — all 60 cases pass
testweaver run examples/modifiers_demo.yaml --format text

# With hugepages disabled — EdgeGuard triggers replanning
testweaver run examples/modifiers_demo.yaml -p hugetlbfs_mount= --format text
```
