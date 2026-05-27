# Runtime Data Flow

TestWeaver passes the `env` tree as the second argument to every operation callable. It lets you share dynamic runtime data between operations — UUIDs, IP addresses, config checksums — without polluting the global `params` namespace.

## The Problem

TestWeaver's `Env` tree is purely boolean during graph building — it tracks which states exist, not what values they hold. But real tests need to pass runtime data:

- A `provision_vm` operation gets back a dynamic UUID and IP
- A `configure_vm` operation needs that IP to SSH in
- A `verify_vm` operation needs the UUID to check status
- A `deprovision_vm` operation needs the UUID to tear down

Without env node values, you'd have to write data to `params`, which pollutes the global namespace and breaks multi-instance tests.

## How It Works

### Writing Data

Return a `StateData` from your callable.  The engine applies the values to
``Env`` nodes and records them on ``StepResult.env_data`` for tracking:

```python
from testweaver import state_data

@action
@provides('vm.active')
@excludes('vm.active')
def provision_vm(params, env):
    vm_uuid = allocate_vm(params.get('vm_name'))
    return state_data({'vm.active': {
        'uuid': vm_uuid,
        'ip': '10.0.0.42',
    }})
```

You can also write side-effect-style via ``env.set_value(path, data)``.
The two patterns coexist — prefer ``StateData`` returns when the framework
should track what data was bound to which state path.

### Reading Data

Call `env._get_node(path).value` in any operation that `requires` that state:

```python
@action
@requires('vm.active')
def configure_vm(params, env):
    node = env._get_node('vm.active')
    vm_ip = node.value['ip']
    ssh(vm_ip, 'install-package.sh')
```

### Why Scoped to State Nodes?

Data is attached to state paths, not a flat dict. This gives you natural isolation for multi-instance tests:

```python
@action
@provides('vm.active.TPM:tpm0.init')
def attach_tpm0(params, env):
    return state_data({'vm.active.TPM:tpm0.init': {'uuid': 'uuid-0'}})

@action
@provides('vm.active.TPM:tpm1.init')
@requires('vm.active.TPM:tpm0.init')
def attach_tpm1(params, env):
    return state_data({'vm.active.TPM:tpm1.init': {'uuid': 'uuid-1'}})

@check
@requires('vm.active.TPM:tpm0.init', 'vm.active.TPM:tpm1.init')
def verify_both(params, env):
    n0 = env._get_node('vm.active.TPM:tpm0.init')
    n1 = env._get_node('vm.active.TPM:tpm1.init')
    assert n0.value['uuid'] != n1.value['uuid']
```

## Complete Example

`examples/data_flow_demo.py` demonstrates a full VM provisioning pipeline:

```bash
testweaver run examples/data_flow_demo.py --format text
```

Output:

```
[provision] test-vm-01: uuid=test-vm-01-fb1d3404 ip=10.0.0.96
[configure] test-vm-01 @ 10.0.0.96: config_hash=82037cd56ba2
[verify] vm_uuid=test-vm-01-fb1d3404 config_hash=82037cd56ba2
[deprovision] test-vm-01: deleting uuid=test-vm-01-fb1d3404
```

The UUID and IP flow from provision → configure → verify → deprovision without touching `params`.

## Important Notes

- **Graph-safe**: Values don't affect `__hash__` or `__eq__` — two envs with the same boolean structure are equal regardless of values. The dependency graph is unchanged.
- **Persistent across transitions**: Values survive `apply_operation()` and `env.copy()` (deep copy).
- **Cleared on clear()**: `env.clear('path')` resets the value to `None`.
- **Copied by graft**: `env.graft(src, tgt)` copies the source node's value to the target.
- **Lifecycle hooks don't receive env**: `@suite_setup`, `@case_setup`, etc. receive a `context` dict, not `(params, env)`.

## API Reference

| Method | Description |
|--------|-------------|
| `env.set_value(path, value)` | Attach data to the node at `path`. Creates intermediate nodes as needed. |
| `env._get_node(path)` | Get the `Env` node at `path`. Returns `None` if the path doesn't exist. |
| `node.value` | The data attached to a node (default `None`). |

## See Also

- [Core Concepts](../concepts.md#runtime-data-flow) — runtime data flow overview
- [Getting Started](../getting-started.md#step-7-pass-runtime-data-between-operations) — tutorial with data flow
- [examples/data_flow_demo.py](../../examples/data_flow_demo.py) — complete example source
- [tests/test_example_data_flow.py](../../tests/test_example_data_flow.py) — tests for the example
