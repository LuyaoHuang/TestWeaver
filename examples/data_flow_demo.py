"""
VM Provisioning with Runtime Data Flow
======================================

Demonstrates two patterns for passing runtime data between operations:

1. **StateData return** — return ``state_data(...)`` from callables.
   The engine applies values to ``Env`` nodes and records them on
   ``StepResult.env_data`` for framework-level tracking.

2. **Direct env access** — call ``env.set_value()`` / ``env._get_node()``
   directly on the env tree for side-effect-style data flow.

Scenario:
  1. Provision a VM → gets back a dynamic UUID and IP address
  2. Configure the VM via SSH → reads the IP, writes a config checksum
  3. Verify the VM → reads both UUID and config state
  4. Deprovision → reads UUID to tear down
"""
from __future__ import annotations

import hashlib
from testweaver import (
    action, check, cleanup, provides, requires, clears, excludes, state_data,
)


# ---------------------------------------------------------------------------
# Action: provision a VM (StateData return pattern)
# ---------------------------------------------------------------------------

@action
@provides('vm.active')
@excludes('vm.active')
def provision_vm(params, env):
    """Provision a VM and return its UUID/IP via StateData.

    Returning ``state_data(...)`` lets the framework track what data was
    bound to which state node — visible in the JSON output.
    """
    vm_name = params.get('vm_name', 'test-vm-01')
    vm_uuid = f"{vm_name}-{hashlib.md5(vm_name.encode()).hexdigest()[:8]}"
    vm_ip = f"10.0.0.{hash(vm_name) % 254 + 1}"

    print(f"[provision] {vm_name}: uuid={vm_uuid} ip={vm_ip}")
    return state_data({
        'vm.active': {
            'name': vm_name,
            'uuid': vm_uuid,
            'ip': vm_ip,
        },
    })


# ---------------------------------------------------------------------------
# Action: configure the VM (reads from env, returns StateData)
# ---------------------------------------------------------------------------

@action
@requires('vm.active')
@provides('vm.configured')
def configure_vm(params, env):
    """Configure the VM by reading its IP from the env node.

    Reads data written by *provision_vm* via ``env._get_node()``, then
    returns a config checksum via ``StateData``.
    """
    node = env._get_node('vm.active')
    if node is None or node.value is None:
        raise RuntimeError("vm.active has no runtime data — did provision_vm run?")

    vm_data = node.value
    vm_ip = vm_data['ip']
    vm_name = vm_data['name']

    config_content = f"{vm_name}-configured-v2"
    config_hash = hashlib.sha256(config_content.encode()).hexdigest()[:12]
    print(f"[configure] {vm_name} @ {vm_ip}: config_hash={config_hash}")

    return state_data({'vm.configured': {'config_hash': config_hash}})


# ---------------------------------------------------------------------------
# Check: verify the VM is running with correct config
# ---------------------------------------------------------------------------

@check
@requires('vm.configured')
def verify_vm(params, env):
    """Verify the VM — reads data from both provision and configure steps."""
    active_node = env._get_node('vm.active')
    configured_node = env._get_node('vm.configured')

    vm_uuid = active_node.value['uuid']
    config_hash = configured_node.value['config_hash']

    print(f"[verify] vm_uuid={vm_uuid} config_hash={config_hash}")
    assert vm_uuid.startswith('test-vm-'), f"Unexpected UUID: {vm_uuid}"
    assert len(config_hash) == 12, f"Unexpected hash length: {config_hash}"


# ---------------------------------------------------------------------------
# Cleanup: deprovision the VM (keyword-style auto-map)
# ---------------------------------------------------------------------------

@cleanup
@requires('vm.active')
@clears('vm.active')
@clears('vm.configured')
def deprovision_vm(params, env):
    """Deprovision the VM — reads UUID from the env node."""
    node = env._get_node('vm.active')
    if node is None or node.value is None:
        print("[deprovision] nothing to clean up")
        return

    vm_data = node.value
    vm_name = vm_data['name']
    vm_uuid = vm_data['uuid']
    print(f"[deprovision] {vm_name}: deleting uuid={vm_uuid}")
