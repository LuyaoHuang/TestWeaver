from testweaver import action, check, provides, requires, clears, excludes


@action
@requires('vm.config')
@excludes('vm.config.ivshmem')
@provides('vm.config.ivshmem')
def set_ivshmem_device(params, env):
    """Add ivshmem device to inactive guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    ivshmem_size = params.get('ivshmem_size', '4M')
    print(f"# Adding ivshmem device size={ivshmem_size} to {guest_name}")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <shmem name='my_shmem'> element")
    print(f"virsh define /tmp/vm.xml")


@check
@requires('vm.active.ivshmem')
def check_ivshmem_in_guest(params, env):
    """Verify ivshmem device is visible inside guest."""
    print("ssh guest 'ls /dev/shm'")
    print("ssh guest 'lspci | grep shared'")


@check
@requires('vm.active.ivshmem')
def check_ivshmem_cmdline(params, env):
    """Verify ivshmem in QEMU command line."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"ps aux | grep {guest_name} | grep ivshmem")


@check
@requires('vm.config.ivshmem')
def check_ivshmem_audit(params, env):
    """Verify ivshmem configuration in audit log."""
    print("ausearch -m VIRT_RESOURCE | grep shmem")


@action
@requires('vm.active')
@excludes('vm.active.ivshmem')
@provides('vm.active.ivshmem')
def hot_plug_ivshmem(params, env):
    """Hot-plug ivshmem device to running guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh attach-device {guest_name} /tmp/ivshmem.xml --live")


@action
@requires('vm.active', 'vm.active.ivshmem')
@clears('vm.active.ivshmem')
def hot_unplug_ivshmem(params, env):
    """Hot-unplug ivshmem device from running guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh detach-device {guest_name} /tmp/ivshmem.xml --live")
