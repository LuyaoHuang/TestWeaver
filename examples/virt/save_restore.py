from testweaver import action, check, provides, requires, excludes, graft, cut


@action
@requires('vm.active', 'vm.config')
@graft('vm.active', 'vm.managedsaved')
@cut('vm.active')
def managedsave_guest(params):
    """Managed-save a running guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh managedsave {guest_name}")


@action
@requires('vm.managedsaved', 'vm.config')
@excludes('vm.active')
@graft('vm.managedsaved', 'vm.active')
@cut('vm.managedsaved')
@provides('vm.active.restored', 'vm.active.restored.from_managedsaved')
def restore_from_managedsaved(params):
    """Restore a guest from managed save."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh start {guest_name}")


@action
@requires('vm.active')
@graft('vm.active', 'vm.saved')
@cut('vm.active')
def save_guest(params):
    """Save a running guest to file."""
    guest_name = params.get('guest_name', 'testvm')
    save_path = params.get('save_path', '/tmp/guest.save')
    print(f"virsh save {guest_name} {save_path}")


@action
@requires('vm.saved')
@excludes('vm.active')
@graft('vm.saved', 'vm.active')
@cut('vm.saved')
@provides('vm.active.restored', 'vm.active.restored.from_saved')
def restore_from_saved(params):
    """Restore a guest from save file."""
    save_path = params.get('save_path', '/tmp/guest.save')
    print(f"virsh restore {save_path}")


@check
@requires('vm.managedsaved')
def check_managedsaved_guest(params):
    """Check guest is in managed-saved state."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh domstate {guest_name} --reason")
    print("# Expected: shut off (saved)")


@check
@requires('vm.saved')
def check_saved_guest(params):
    """Check guest is in saved state."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh domstate {guest_name} --reason")
    print("# Expected: shut off (saved)")


@check
@requires('vm.active.restored')
def check_restored_guest(params):
    """Check guest is in restored state."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh domstate {guest_name} --reason")
    print("# Expected: running (restored)")


@check
@requires('vm.managedsaved')
def check_managedsaved_file(params):
    """Check managed save file exists."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"test -f /var/lib/libvirt/qemu/save/{guest_name}.save")
