# Examples

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

## Graph Modifiers

In real test environments, a step's execution can change what future steps are valid. For example, disabling hugepages makes VM start impossible, or setting memory tuning requires a libvirtd restart before the next operation. The static dependency graph can't model these runtime decisions.

Graph modifiers let callable operations return objects that influence execution flow. The runner processes them during case execution — no changes to the graph engine or case generation are needed.

### EdgeGuard

Blocks a future operation, forcing the runner to find an alternative path through the dependency graph (replanning). Use when a step discovers that a later step is now invalid.

```python
from testweaver import action, provides, excludes, EdgeGuard

@action
@provides('hugepage_config')
@excludes('hugepage_config')
def configure_hugepages(params):
    mount = params.get('hugetlbfs_mount', '/dev/hugepages')
    if mount == '':
        # Hugepages disabled — VM start will fail
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
results = run_all(cases, definition, graph=graph)
```

### TransientHook

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

### TransitionObserver

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

### Modifier Summary

| Modifier | Purpose | Lifetime | Affects graph? |
|----------|---------|----------|----------------|
| `EdgeGuard` | Block a future operation, trigger replan | Rest of case | Yes (replan) |
| `TransientHook` | Inject a step before a future operation | One-shot | No |
| `TransitionObserver` | Verify after matching operations | Rest of case | No |

### Full Example

See `examples/modifiers_demo.py` and `examples/modifiers_demo.yaml` for a complete working example that demonstrates all three modifier types in a VM testing scenario.

```bash
# Normal run — all 60 cases pass
testweaver run examples/modifiers_demo.yaml --format text

# With hugepages disabled — EdgeGuard triggers replanning
testweaver run examples/modifiers_demo.yaml -p hugetlbfs_mount= --format text
```

## Virtualization Examples

The `examples/virt/` directory contains mock implementations of libvirt/QEMU test operations, ported from depend-test-framework:

| Module | Operations | Description |
|--------|-----------|-------------|
| `vm_basic.py` | 4 | Guest lifecycle: define, start, destroy, undefine |
| `vtpm.py` | 11 | vTPM device management with param_choices (emulator vs passthrough) |
| `save_restore.py` | 8 | Save/restore using graft+cut migrate pattern |
| `vdisk.py` | 2 | Virtual disk attach and verify |
| `backing_chain.py` | 5 | Snapshot management with block pull/commit |
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
