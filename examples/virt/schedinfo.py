from testweaver import action, check, cleanup, provides, requires, excludes, cut


@action
@requires('vm.active')
@excludes('vm.schedinfo.cpu_shares')
@provides('vm.schedinfo.cpu_shares')
def set_cpu_shares(params, env):
    """Set CPU shares via schedinfo."""
    guest_name = params.get('guest_name', 'testvm')
    value = params.get('cpu_shares', 1024)
    print(f"virsh schedinfo {guest_name} --set cpu_shares={value}")


@check
@requires('vm.schedinfo.cpu_shares')
def check_cpu_shares(params, env):
    """Verify CPU shares setting."""
    guest_name = params.get('guest_name', 'testvm')
    value = params.get('cpu_shares', 1024)
    print(f"virsh schedinfo {guest_name} | grep cpu_shares")
    print(f"# Expected: cpu_shares = {value}")


@action
@requires('vm.active')
@excludes('vm.schedinfo.vcpu_period')
@provides('vm.schedinfo.vcpu_period')
def set_vcpu_period(params, env):
    """Set vCPU period via schedinfo."""
    guest_name = params.get('guest_name', 'testvm')
    value = params.get('vcpu_period', 100000)
    print(f"virsh schedinfo {guest_name} --set vcpu_period={value}")


@check
@requires('vm.schedinfo.vcpu_period')
def check_vcpu_period(params, env):
    """Verify vCPU period setting."""
    guest_name = params.get('guest_name', 'testvm')
    value = params.get('vcpu_period', 100000)
    print(f"virsh schedinfo {guest_name} | grep vcpu_period")
    print(f"# Expected: vcpu_period = {value}")


@action
@requires('vm.active')
@excludes('vm.schedinfo.vcpu_quota')
@provides('vm.schedinfo.vcpu_quota')
def set_vcpu_quota(params, env):
    """Set vCPU quota via schedinfo."""
    guest_name = params.get('guest_name', 'testvm')
    value = params.get('vcpu_quota', -1)
    print(f"virsh schedinfo {guest_name} --set vcpu_quota={value}")


@check
@requires('vm.schedinfo.vcpu_quota')
def check_vcpu_quota(params, env):
    """Verify vCPU quota setting."""
    guest_name = params.get('guest_name', 'testvm')
    value = params.get('vcpu_quota', -1)
    print(f"virsh schedinfo {guest_name} | grep vcpu_quota")
    print(f"# Expected: vcpu_quota = {value}")


@cleanup
@requires('vm.schedinfo')
@cut('vm.schedinfo')
def clear_schedinfo(params, env):
    """Clear all schedinfo settings by restarting guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh destroy {guest_name}")
    print(f"virsh start {guest_name}")
