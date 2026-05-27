from testweaver import action, check, provides, requires, clears, excludes


@action
@requires('vm.active')
@excludes('target_host.vm.active')
@provides('target_host.vm.active')
@clears('vm.active')
def migrate(params, env):
    """Live migrate a guest to target host."""
    guest_name = params.get('guest_name', 'testvm')
    target_host = params.get('target_host', 'remote-host')
    print(f"virsh migrate {guest_name} qemu+ssh://{target_host}/system --live")


@check
@requires('target_host.vm.active')
def check_migrated_guest(params, env):
    """Verify guest is running on target host."""
    guest_name = params.get('guest_name', 'testvm')
    target_host = params.get('target_host', 'remote-host')
    print(f"virsh -c qemu+ssh://{target_host}/system domstate {guest_name}")
    print("# Expected: running")
