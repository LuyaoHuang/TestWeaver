from testweaver import action, check, provides, requires, excludes


@action
@requires('vm.config.numa')
@excludes('vm.config.maxmemory')
@provides('vm.config.maxmemory')
def set_maxmemory(params):
    """Set maxMemory in guest XML for memory hotplug."""
    guest_name = params.get('guest_name', 'testvm')
    max_mem = params.get('max_memory', 4194304)
    print(f"# Setting maxMemory={max_mem} for {guest_name}")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <maxMemory slots='16'> element")
    print(f"virsh define /tmp/vm.xml")


@action
@requires('vm.config.maxmemory')
@excludes('vm.config.memdevice')
@provides('vm.config.memdevice')
def set_memory_device(params):
    """Add memory device to inactive guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    mem_size = params.get('mem_device_size', 524288)
    print(f"# Adding memory device size={mem_size} to {guest_name}")
    print(f"virsh attach-device {guest_name} /tmp/mem_device.xml --config")


@action
@requires('vm.active.maxmemory')
@excludes('vm.active.memdevice')
@provides('vm.active.memdevice')
def attach_mem_device(params):
    """Live-attach a memory device to running guest."""
    guest_name = params.get('guest_name', 'testvm')
    mem_size = params.get('mem_device_size', 524288)
    print(f"# Live-attaching memory device size={mem_size} to {guest_name}")
    print(f"virsh attach-device {guest_name} /tmp/mem_device.xml --live")


@check
@requires('vm.active.memdevice')
def check_mem_device_audit(params):
    """Verify memory device hotplug via audit log."""
    print("ausearch -m VIRT_RESOURCE | grep memory")
    print("ssh guest 'lsmem'")
