from testweaver import action, check, provides, requires, excludes


@action
@requires('vm.config')
@excludes('vm.config.vdisk')
@provides('vm.config.vdisk')
def add_disk(params):
    """Add a virtual disk to inactive guest."""
    guest_name = params.get('guest_name', 'testvm')
    disk_path = params.get('disk_path', '/var/lib/libvirt/images/test.qcow2')
    print(f"qemu-img create -f qcow2 {disk_path} 1G")
    print(f"virsh attach-disk {guest_name} {disk_path} vdb --config")


@check
@requires('vm.active.vdisk')
def check_disk(params):
    """Verify virtual disk is visible inside guest."""
    print("ssh guest 'lsblk | grep vdb'")
