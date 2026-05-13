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

## Multi-Instance Namespaces

TestWeaver supports modeling multiple devices of the same type with independent states. This uses the `:` namespace separator and additive parameter choices.

### Basic Multi-Instance Setup

```python
# multi_tpm_ops.py
from testweaver import action, check, cleanup, provides, requires, clears

@action
@provides('vm.active.TPM:{tpm_id}.init')
def attach_tpm(params):
    """Attach a TPM device to the VM"""
    print(f"virsh attach-device {params.get('guest_name')} tpm-{params['tpm_id']}.xml")

@action
@requires('vm.active.TPM:{tpm_id}.init')
@provides('vm.active.TPM:{tpm_id}.ready')
def configure_tpm(params):
    """Configure the TPM device"""
    print(f"tpm2_startup -c on {params['tpm_id']}")

@check
@requires('vm.active.TPM:tpm*.ready')
def check_any_tpm_ready(params):
    """Verify at least one TPM is ready — uses wildcard to match any instance"""
    print("Checking TPM status in guest")

@cleanup
@requires('vm.active.TPM:{tpm_id}.init')
@clears('vm.active.TPM:{tpm_id}.init')
def detach_tpm(params):
    """Detach a TPM device"""
    print(f"virsh detach-device tpm-{params['tpm_id']}.xml")
```

```yaml
# multi_tpm_test.yaml
modules:
  - multi_tpm_ops.py

suite:
  name: "Multi-TPM Verification"
  targets: [check_any_tpm_ready]
  param_choices:
    - name: tpm_id
      values: [tpm0, tpm1]
      mode: additive
  cleanup: true
```

The `mode: additive` setting expands each templated operation into per-instance concrete operations (`attach_tpm[tpm_id=tpm0]`, `attach_tpm[tpm_id=tpm1]`). Unlike `exclusive` mode (the default), all instances coexist in the same graph — the engine explores paths where tpm0 and tpm1 are attached in different orders.

### Wildcard Queries

Use `*` in `requires` or `excludes` to query across instances:

```python
# Match ANY instance
@requires('vm.active.TPM:tpm*.ready')    # True if tpm0 OR tpm1 is ready

# Match a specific instance (no wildcard)
@requires('vm.active.TPM:tpm0.ready')    # True only if tpm0 is ready
```

Wildcards match per path segment using `fnmatch` — `TPM:tpm*` matches `TPM:tpm0`, `TPM:tpm1`, etc. The `*` does not cross `.` boundaries.

Wildcards are only allowed in read paths (`requires`, `excludes`). Write paths (`provides`, `clears`, `cuts`, `grafts`) must be deterministic — use `{param}` templates instead.

### Multiple Device Types

You can have multiple independent instance dimensions:

```python
@action
@provides('TPM:{tpm_id}.on')
def attach_tpm(params):
    pass

@action
@provides('DISK:{disk_id}.on')
def attach_disk(params):
    pass

@check
@requires('TPM:tpm*.on', 'DISK:disk*.on')
def check_devices(params):
    """Requires at least one TPM and one disk to be attached"""
    pass
```

```yaml
suite:
  name: "Multi-Device"
  targets: [check_devices]
  param_choices:
    - name: tpm_id
      values: [tpm0, tpm1]
      mode: additive
    - name: disk_id
      values: [disk0, disk1]
      mode: additive
```

### Generation Strategies

Multi-instance expansion can produce many test cases. Use `generation_strategy` to control this:

```yaml
suite:
  name: "Multi-Device Test"
  targets: [check_devices]
  generation_strategy: pairwise
  param_choices:
    - name: tpm_id
      values: [tpm0, tpm1]
      mode: additive
    - name: disk_id
      values: [disk0, disk1]
      mode: additive
```

| Strategy | Behavior | Best For |
|----------|----------|----------|
| `exhaustive` | (Default) All valid test paths | Small instance counts, critical path testing |
| `pairwise` | Minimum subset covering all pairs of instance operations | Multiple device types, compatibility verification |
| `representative` | One case per unique step-sequence shape | Verifying system behavior where the specific device ID is irrelevant |

### Mixing Additive and Exclusive Choices

You can combine additive instances with exclusive parameter choices:

```yaml
suite:
  name: "TPM with Backend Variants"
  targets: [verify_tpm]
  param_choices:
    - name: tpm_backend
      values: [emulator, passthrough]
      mode: exclusive
    - name: tpm_id
      values: [tpm0, tpm1]
      mode: additive
```

This generates separate test paths for each backend (emulator vs passthrough), with both TPM instances available in each path.

## Operation Verification

Attach verify callbacks to operations so that verification runs automatically after each successful step. This is cleaner than making verifications separate graph nodes — verify functions don't change state, so they shouldn't participate in path-finding.

### Python: `@verify_for`

```python
from testweaver import action, cleanup, provides, requires, clears, verify_for

@action
@provides('rng.present')
def add_rng(params):
    """Attach RNG device to VM"""
    print(f"virsh attach-device {params.get('guest_name')} rng.xml")

@verify_for('add_rng')
def verify_rng_in_vm(params):
    """Verify RNG device is visible inside the VM"""
    print(f"ssh {params.get('guest_name')} ls /dev/hwrng")

@action
@requires('rng.present')
@clears('rng.present')
def remove_rng(params):
    """Detach RNG device from VM"""
    print(f"virsh detach-device {params.get('guest_name')} rng.xml")

@verify_for('remove_rng')
def verify_no_rng_in_vm(params):
    """Verify RNG device is no longer visible inside the VM"""
    import subprocess
    result = subprocess.run(
        f"ssh {params.get('guest_name')} test ! -e /dev/hwrng",
        shell=True,
    )
    if result.returncode != 0:
        raise AssertionError("RNG device still present after removal")
```

When `add_rng` runs and passes, `verify_rng_in_vm` runs automatically. When `remove_rng` runs and passes, `verify_no_rng_in_vm` runs automatically. No multi-target chaining needed.

### YAML: `verify` field

```yaml
operations:
  - name: add_rng
    type: action
    provides: [rng.present]
    run: virsh attach-device $guest_name rng.xml
    verify: ssh $guest_name ls /dev/hwrng

  - name: remove_rng
    type: action
    requires: [rng.present]
    clears: [rng.present]
    run: virsh detach-device $guest_name rng.xml
    verify: ssh $guest_name test ! -e /dev/hwrng
```

### Verify vs Check vs TransitionObserver

| Mechanism | When it runs | Graph impact | Lifetime |
|-----------|-------------|--------------|----------|
| `verify` / `@verify_for` | After its attached operation | None | Per operation |
| `@check` target | End of test case (as a target) | Target node | Once per case |
| `TransitionObserver` | After any watched operation | None | Rest of case |

Use `verify` when you want to validate that a specific operation did its job. Use `@check` when you want a standalone verification target. Use `TransitionObserver` when you need ongoing monitoring across multiple operations.

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
| `multi_disk.py` | 8 | Multi-disk hot-plug with additive namespaces and wildcard queries |
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

# Multi-instance: additive disk namespaces with wildcard queries
testweaver generate examples/virt/multi_disk_test.yaml --format text
testweaver run examples/virt/multi_disk_test.yaml --format text
```
