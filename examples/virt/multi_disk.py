from testweaver import (
    action, check, cleanup, provides, requires, excludes, clears,
    verify_for,
)


@action
@requires('vm.active')
@excludes('vm.active.DISK:{disk_id}.attached')
@provides('vm.active.DISK:{disk_id}.attached')
def attach_disk(params):
    """Hot-plug a virtual disk to a running guest."""
    guest_name = params.get('guest_name', 'testvm')
    disk_id = params['disk_id']
    disk_path = f"/var/lib/libvirt/images/{disk_id}.qcow2"
    print(f"qemu-img create -f qcow2 {disk_path} 1G")
    print(f"virsh attach-disk {guest_name} {disk_path} {disk_id} --live")


@verify_for('attach_disk')
def verify_disk_attached(params):
    """Verify disk is visible inside guest after attach."""
    disk_id = params['disk_id']
    print(f"ssh guest 'lsblk | grep {disk_id}'")


@action
@requires('vm.active.DISK:{disk_id}.attached')
@excludes('vm.active.DISK:{disk_id}.formatted')
@provides('vm.active.DISK:{disk_id}.formatted')
def format_disk(params):
    """Format the attached disk with ext4."""
    disk_id = params['disk_id']
    print(f"ssh guest 'mkfs.ext4 /dev/{disk_id}'")


@action
@requires('vm.active.DISK:{disk_id}.formatted')
@excludes('vm.active.DISK:{disk_id}.mounted')
@provides('vm.active.DISK:{disk_id}.mounted')
def mount_disk(params):
    """Mount the formatted disk."""
    disk_id = params['disk_id']
    print(f"ssh guest 'mkdir -p /mnt/{disk_id} && mount /dev/{disk_id} /mnt/{disk_id}'")


@action
@requires('vm.active.DISK:{disk_id}.mounted')
@clears('vm.active.DISK:{disk_id}.mounted')
def unmount_disk(params):
    """Unmount the disk."""
    disk_id = params['disk_id']
    print(f"ssh guest 'umount /mnt/{disk_id}'")


@cleanup
@requires('vm.active.DISK:{disk_id}.attached')
@clears('vm.active.DISK:{disk_id}.attached')
def detach_disk(params):
    """Hot-unplug a virtual disk from a running guest."""
    guest_name = params.get('guest_name', 'testvm')
    disk_id = params['disk_id']
    print(f"virsh detach-disk {guest_name} {disk_id} --live")


@check
@requires('vm.active.DISK:vd*.attached')
def check_any_disk_attached(params):
    """Verify at least one disk is attached — uses wildcard."""
    print("ssh guest 'lsblk --output NAME,SIZE,TYPE | grep disk'")


@check
@requires('vm.active.DISK:vd*.mounted')
def check_any_disk_mounted(params):
    """Verify at least one disk is mounted — uses wildcard."""
    print("ssh guest 'mount | grep /mnt/vd'")
