# Multi-Instance Namespaces

TestWeaver supports modeling multiple devices of the same type with independent states. This uses the `:` namespace separator and additive parameter choices.

## Basic Multi-Instance Setup

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

## Wildcard Queries

Use `*` in `requires` or `excludes` to query across instances:

```python
# Match ANY instance
@requires('vm.active.TPM:tpm*.ready')    # True if tpm0 OR tpm1 is ready

# Match a specific instance (no wildcard)
@requires('vm.active.TPM:tpm0.ready')    # True only if tpm0 is ready
```

Wildcards match per path segment using `fnmatch` — `TPM:tpm*` matches `TPM:tpm0`, `TPM:tpm1`, etc. The `*` does not cross `.` boundaries.

Wildcards are only allowed in read paths (`requires`, `excludes`). Write paths (`provides`, `clears`, `cuts`, `grafts`) must be deterministic — use `{param}` templates instead.

## Multiple Device Types

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

## Generation Strategies

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

## Mixing Additive and Exclusive Choices

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
