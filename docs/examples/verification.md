# Operation Verification

Attach verify callbacks to operations so that verification runs automatically after each successful step. This is cleaner than making verifications separate graph nodes — verify functions don't change state, so they shouldn't participate in path-finding.

## Python: `@verify_for`

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

## YAML: `verify` field

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

## Verify vs Check vs TransitionObserver

| Mechanism | When it runs | Graph impact | Lifetime |
|-----------|-------------|--------------|----------|
| `verify` / `@verify_for` | After its attached operation | None | Per operation |
| `@check` target | End of test case (as a target) | Target node | Once per case |
| `TransitionObserver` | After any watched operation | None | Rest of case |

Use `verify` when you want to validate that a specific operation did its job. Use `@check` when you want a standalone verification target. Use `TransitionObserver` when you need ongoing monitoring across multiple operations.
