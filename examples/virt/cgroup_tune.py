from testweaver import action, check, cleanup, provides, requires, excludes, cut


# =============================================================================
# BLKIOTUNE
# =============================================================================

@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkiotune.weight')
@provides('vm.blkiotune.weight')
def set_io_weight(params):
    """Set blkiotune I/O weight."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('io_weight', 500)
    print(f"virsh blkiotune {guest} --weight={value}")


@check
@requires('vm.blkiotune.weight')
def check_io_weight(params):
    """Check blkiotune I/O weight."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkiotune {guest} | grep weight")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkiotune.device_read_iops_sec')
@provides('vm.blkiotune.device_read_iops_sec')
def set_device_read_iops_sec(params):
    """Set device read IOPS per second."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('device_read_iops_sec', 1000)
    print(f"virsh blkiotune {guest} --device-read-iops-sec={value}")


@check
@requires('vm.blkiotune.device_read_iops_sec')
def check_device_read_iops_sec(params):
    """Check device read IOPS per second."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkiotune {guest} | grep device-read-iops-sec")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkiotune.device_write_iops_sec')
@provides('vm.blkiotune.device_write_iops_sec')
def set_device_write_iops_sec(params):
    """Set device write IOPS per second."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('device_write_iops_sec', 1000)
    print(f"virsh blkiotune {guest} --device-write-iops-sec={value}")


@check
@requires('vm.blkiotune.device_write_iops_sec')
def check_device_write_iops_sec(params):
    """Check device write IOPS per second."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkiotune {guest} | grep device-write-iops-sec")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkiotune.device_read_bytes_sec')
@provides('vm.blkiotune.device_read_bytes_sec')
def set_device_read_bytes_sec(params):
    """Set device read bytes per second."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('device_read_bytes_sec', 1048576)
    print(f"virsh blkiotune {guest} --device-read-bytes-sec={value}")


@check
@requires('vm.blkiotune.device_read_bytes_sec')
def check_device_read_bytes_sec(params):
    """Check device read bytes per second."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkiotune {guest} | grep device-read-bytes-sec")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkiotune.device_write_bytes_sec')
@provides('vm.blkiotune.device_write_bytes_sec')
def set_device_write_bytes_sec(params):
    """Set device write bytes per second."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('device_write_bytes_sec', 1048576)
    print(f"virsh blkiotune {guest} --device-write-bytes-sec={value}")


@check
@requires('vm.blkiotune.device_write_bytes_sec')
def check_device_write_bytes_sec(params):
    """Check device write bytes per second."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkiotune {guest} | grep device-write-bytes-sec")


@cleanup
@requires('vm.blkiotune')
@cut('vm.blkiotune')
def clear_blkiotune(params):
    """Clear blkiotune settings by restarting guest."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh destroy {guest}")
    print(f"virsh start {guest}")


# =============================================================================
# MEMTUNE
# =============================================================================

@action
@requires('vm.active', 'vm.config')
@excludes('vm.memtune.hard_limit')
@provides('vm.memtune.hard_limit')
def set_hard_limit(params):
    """Set memory hard limit."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('hard_limit', 1048576)
    print(f"virsh memtune {guest} --hard-limit={value}")


@check
@requires('vm.memtune.hard_limit')
def check_hard_limit(params):
    """Check memory hard limit."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh memtune {guest} | grep hard_limit")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.memtune.soft_limit')
@provides('vm.memtune.soft_limit')
def set_soft_limit(params):
    """Set memory soft limit."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('soft_limit', 524288)
    print(f"virsh memtune {guest} --soft-limit={value}")


@check
@requires('vm.memtune.soft_limit')
def check_soft_limit(params):
    """Check memory soft limit."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh memtune {guest} | grep soft_limit")


@action
@requires('vm.active', 'vm.config', 'vm.memtune.hard_limit')
@excludes('vm.memtune.swap_hard_limit')
@provides('vm.memtune.swap_hard_limit')
def set_swap_hard_limit(params):
    """Set swap hard limit (requires hard_limit set first)."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('swap_hard_limit', 2097152)
    print(f"virsh memtune {guest} --swap-hard-limit={value}")


@check
@requires('vm.memtune.swap_hard_limit')
def check_swap_hard_limit(params):
    """Check swap hard limit."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh memtune {guest} | grep swap_hard_limit")


@cleanup
@requires('vm.memtune')
@cut('vm.memtune')
def clear_memtune(params):
    """Clear memtune settings by restarting guest."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh destroy {guest}")
    print(f"virsh start {guest}")


# =============================================================================
# SCHEDINFO
# =============================================================================

@action
@requires('vm.active', 'vm.config')
@excludes('vm.cg_schedinfo.cpu_shares')
@provides('vm.cg_schedinfo.cpu_shares')
def set_cg_cpu_shares(params):
    """Set CPU shares via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('cpu_shares', 1024)
    print(f"virsh schedinfo {guest} --set cpu_shares={value}")


@check
@requires('vm.cg_schedinfo.cpu_shares')
def check_cg_cpu_shares(params):
    """Check CPU shares via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh schedinfo {guest} | grep cpu_shares")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.cg_schedinfo.vcpu_period')
@provides('vm.cg_schedinfo.vcpu_period')
def set_cg_vcpu_period(params):
    """Set vCPU period via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('vcpu_period', 100000)
    print(f"virsh schedinfo {guest} --set vcpu_period={value}")


@check
@requires('vm.cg_schedinfo.vcpu_period')
def check_cg_vcpu_period(params):
    """Check vCPU period via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh schedinfo {guest} | grep vcpu_period")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.cg_schedinfo.vcpu_quota')
@provides('vm.cg_schedinfo.vcpu_quota')
def set_cg_vcpu_quota(params):
    """Set vCPU quota via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('vcpu_quota', -1)
    print(f"virsh schedinfo {guest} --set vcpu_quota={value}")


@check
@requires('vm.cg_schedinfo.vcpu_quota')
def check_cg_vcpu_quota(params):
    """Check vCPU quota via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh schedinfo {guest} | grep vcpu_quota")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.cg_schedinfo.emulator_period')
@provides('vm.cg_schedinfo.emulator_period')
def set_cg_emulator_period(params):
    """Set emulator period via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('emulator_period', 100000)
    print(f"virsh schedinfo {guest} --set emulator_period={value}")


@check
@requires('vm.cg_schedinfo.emulator_period')
def check_cg_emulator_period(params):
    """Check emulator period via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh schedinfo {guest} | grep emulator_period")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.cg_schedinfo.emulator_quota')
@provides('vm.cg_schedinfo.emulator_quota')
def set_cg_emulator_quota(params):
    """Set emulator quota via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('emulator_quota', -1)
    print(f"virsh schedinfo {guest} --set emulator_quota={value}")


@check
@requires('vm.cg_schedinfo.emulator_quota')
def check_cg_emulator_quota(params):
    """Check emulator quota via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh schedinfo {guest} | grep emulator_quota")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.cg_schedinfo.global_period')
@provides('vm.cg_schedinfo.global_period')
def set_cg_global_period(params):
    """Set global period via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('global_period', 100000)
    print(f"virsh schedinfo {guest} --set global_period={value}")


@check
@requires('vm.cg_schedinfo.global_period')
def check_cg_global_period(params):
    """Check global period via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh schedinfo {guest} | grep global_period")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.cg_schedinfo.global_quota')
@provides('vm.cg_schedinfo.global_quota')
def set_cg_global_quota(params):
    """Set global quota via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('global_quota', -1)
    print(f"virsh schedinfo {guest} --set global_quota={value}")


@check
@requires('vm.cg_schedinfo.global_quota')
def check_cg_global_quota(params):
    """Check global quota via schedinfo."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh schedinfo {guest} | grep global_quota")


@cleanup
@requires('vm.cg_schedinfo')
@cut('vm.cg_schedinfo')
def clear_cg_schedinfo(params):
    """Clear schedinfo settings by restarting guest."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh destroy {guest}")
    print(f"virsh start {guest}")
