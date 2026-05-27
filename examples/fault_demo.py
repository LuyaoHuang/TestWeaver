"""Demonstrate fault-injection testing with a VM lifecycle scenario.

Fault operations declare error scenarios where a normal operation should
fail under specific conditions.  The framework auto-generates test cases
that reach those conditions and execute the fault handler instead of
the target operation.

Two fault scenarios are shown:

1. hugepage_start_error — starting a VM with hugepages configured on a
   host that doesn't support them should fail.

2. tpm_start_error — starting a VM with a TPM device when swtpm is not
   installed should fail.

Run the example:

    testweaver generate examples/fault_demo.yaml --format text
    testweaver graph examples/fault_demo.yaml --format text
"""
from testweaver import (
    action, check, cleanup, fault_for,
    provides, requires, clears, excludes,
)


# --- Setup operations ---

@action
@provides('vm.config')
@excludes('vm.config')
def define_vm(params, env):
    """Define a VM from XML."""
    print(f"  virsh define {params.get('guest_name', 'testvm')}.xml")


@action
@requires('vm.config')
@excludes('vm.config.hugepage')
@provides('vm.config.hugepage')
def configure_hugepages(params, env):
    """Add hugepage backing to the VM config."""
    print(f"  virt-xml {params.get('guest_name', 'testvm')} --edit --memorybacking hugepages=on")


@action
@requires('vm.config')
@excludes('vm.config.tpm')
@provides('vm.config.tpm')
def add_tpm_device(params, env):
    """Add a TPM 2.0 device to the VM config."""
    print(f"  virt-xml {params.get('guest_name', 'testvm')} --add-device --tpm model=tpm-crb")


@action
@requires('vm.config')
@excludes('vm.active')
@provides('vm.active')
def start_vm(params, env):
    """Start the VM."""
    print(f"  virsh start {params.get('guest_name', 'testvm')}")


# --- Fault operations ---
# Each fault adds extra @requires on top of the target operation's
# requires — the framework finds all graph states where both the
# target's conditions AND the fault's extra conditions are satisfied,
# then generates cases that end with the fault handler instead.

@fault_for('start_vm')
@requires('vm.config.hugepage')
def hugepage_start_error(params, env):
    """Start should fail when hugepages are configured but unavailable."""
    print(f"  virsh start {params.get('guest_name', 'testvm')}")
    print("  >> error: internal error: hugepages are disabled by administrator")


@fault_for('start_vm')
@requires('vm.config.tpm')
def tpm_start_error(params, env):
    """Start should fail when TPM is configured but swtpm is not installed."""
    print(f"  virsh start {params.get('guest_name', 'testvm')}")
    print("  >> error: swtpm binary not found in PATH")


# --- Check operations ---

@check
@requires('vm.active')
def check_vm_running(params, env):
    """Verify the VM is running."""
    print(f"  virsh domstate {params.get('guest_name', 'testvm')} | grep running")


# --- Cleanup operations ---

@cleanup
@requires('vm.active')
@clears('vm.active')
def destroy_vm(params, env):
    """Stop the VM."""
    print(f"  virsh destroy {params.get('guest_name', 'testvm')}")


@cleanup
@requires('vm.config.hugepage')
@excludes('vm.active')
@clears('vm.config.hugepage')
def remove_hugepages(params, env):
    """Remove hugepage config."""
    print(f"  virt-xml {params.get('guest_name', 'testvm')} --edit --memorybacking hugepages=off")


@cleanup
@requires('vm.config.tpm')
@excludes('vm.active')
@clears('vm.config.tpm')
def remove_tpm(params, env):
    """Remove TPM device."""
    print(f"  virt-xml {params.get('guest_name', 'testvm')} --remove-device --tpm all")


@cleanup
@requires('vm.config')
@excludes('vm.active', 'vm.config.hugepage', 'vm.config.tpm')
@clears('vm.config')
def undefine_vm(params, env):
    """Undefine the VM."""
    print(f"  virsh undefine {params.get('guest_name', 'testvm')}")
