from testweaver import action, check, cleanup, provides, requires, excludes, cut


# BYTES SETTINGS

@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkdeviotune.bytes_sec.total_bytes_sec')
@provides('vm.blkdeviotune.bytes_sec.total_bytes_sec')
@excludes('vm.blkdeviotune.bytes_sec.read_bytes_sec',
          'vm.blkdeviotune.bytes_sec.write_bytes_sec')
def set_total_bytes_sec(params):
    """Set total_bytes_sec."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('total_bytes_sec', 1048576)
    print(f"virsh blkdeviotune {guest} vda --total-bytes-sec {value}")


@check
@requires('vm.blkdeviotune.bytes_sec.total_bytes_sec')
def check_total_bytes_sec(params):
    """Check total_bytes_sec."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep total_bytes_sec")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkdeviotune.bytes_sec.read_bytes_sec')
@provides('vm.blkdeviotune.bytes_sec.read_bytes_sec')
@excludes('vm.blkdeviotune.bytes_sec.total_bytes_sec',
          'vm.blkdeviotune.bytes_sec.write_bytes_sec')
def set_read_bytes_sec(params):
    """Set read_bytes_sec."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('read_bytes_sec', 524288)
    print(f"virsh blkdeviotune {guest} vda --read-bytes-sec {value}")


@check
@requires('vm.blkdeviotune.bytes_sec.read_bytes_sec')
def check_read_bytes_sec(params):
    """Check read_bytes_sec."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep read_bytes_sec")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkdeviotune.bytes_sec.write_bytes_sec')
@provides('vm.blkdeviotune.bytes_sec.write_bytes_sec')
@excludes('vm.blkdeviotune.bytes_sec.total_bytes_sec',
          'vm.blkdeviotune.bytes_sec.read_bytes_sec')
def set_write_bytes_sec(params):
    """Set write_bytes_sec."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('write_bytes_sec', 524288)
    print(f"virsh blkdeviotune {guest} vda --write-bytes-sec {value}")


@check
@requires('vm.blkdeviotune.bytes_sec.write_bytes_sec')
def check_write_bytes_sec(params):
    """Check write_bytes_sec."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep write_bytes_sec")


# IOPS SETTINGS

@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkdeviotune.iops_sec.total_iops_sec')
@provides('vm.blkdeviotune.iops_sec.total_iops_sec')
@excludes('vm.blkdeviotune.iops_sec.read_iops_sec',
          'vm.blkdeviotune.iops_sec.write_iops_sec')
def set_total_iops_sec(params):
    """Set total_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('total_iops_sec', 1000)
    print(f"virsh blkdeviotune {guest} vda --total-iops-sec {value}")


@check
@requires('vm.blkdeviotune.iops_sec.total_iops_sec')
def check_total_iops_sec(params):
    """Check total_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep total_iops_sec")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkdeviotune.iops_sec.read_iops_sec')
@provides('vm.blkdeviotune.iops_sec.read_iops_sec')
@excludes('vm.blkdeviotune.iops_sec.total_iops_sec',
          'vm.blkdeviotune.iops_sec.write_iops_sec')
def set_read_iops_sec(params):
    """Set read_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('read_iops_sec', 500)
    print(f"virsh blkdeviotune {guest} vda --read-iops-sec {value}")


@check
@requires('vm.blkdeviotune.iops_sec.read_iops_sec')
def check_read_iops_sec(params):
    """Check read_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep read_iops_sec")


@action
@requires('vm.active', 'vm.config')
@excludes('vm.blkdeviotune.iops_sec.write_iops_sec')
@provides('vm.blkdeviotune.iops_sec.write_iops_sec')
@excludes('vm.blkdeviotune.iops_sec.total_iops_sec',
          'vm.blkdeviotune.iops_sec.read_iops_sec')
def set_write_iops_sec(params):
    """Set write_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('write_iops_sec', 500)
    print(f"virsh blkdeviotune {guest} vda --write-iops-sec {value}")


@check
@requires('vm.blkdeviotune.iops_sec.write_iops_sec')
def check_write_iops_sec(params):
    """Check write_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep write_iops_sec")


# BYTES MAX SETTINGS

@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.bytes_sec.total_bytes_sec')
@excludes('vm.blkdeviotune.bytes_sec_max.total_bytes_sec_max')
@provides('vm.blkdeviotune.bytes_sec_max.total_bytes_sec_max')
@excludes('vm.blkdeviotune.bytes_sec_max.read_bytes_sec_max',
          'vm.blkdeviotune.bytes_sec_max.write_bytes_sec_max')
def set_total_bytes_sec_max(params):
    """Set total_bytes_sec_max."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('total_bytes_sec_max', 2097152)
    print(f"virsh blkdeviotune {guest} vda --total-bytes-sec-max {value}")


@check
@requires('vm.blkdeviotune.bytes_sec_max.total_bytes_sec_max')
def check_total_bytes_sec_max(params):
    """Check total_bytes_sec_max."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep total_bytes_sec_max")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.bytes_sec.read_bytes_sec')
@excludes('vm.blkdeviotune.bytes_sec_max.read_bytes_sec_max')
@provides('vm.blkdeviotune.bytes_sec_max.read_bytes_sec_max')
@excludes('vm.blkdeviotune.bytes_sec_max.total_bytes_sec_max',
          'vm.blkdeviotune.bytes_sec_max.write_bytes_sec_max')
def set_read_bytes_sec_max(params):
    """Set read_bytes_sec_max."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('read_bytes_sec_max', 1048576)
    print(f"virsh blkdeviotune {guest} vda --read-bytes-sec-max {value}")


@check
@requires('vm.blkdeviotune.bytes_sec_max.read_bytes_sec_max')
def check_read_bytes_sec_max(params):
    """Check read_bytes_sec_max."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep read_bytes_sec_max")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.bytes_sec.write_bytes_sec')
@excludes('vm.blkdeviotune.bytes_sec_max.write_bytes_sec_max')
@provides('vm.blkdeviotune.bytes_sec_max.write_bytes_sec_max')
@excludes('vm.blkdeviotune.bytes_sec_max.total_bytes_sec_max',
          'vm.blkdeviotune.bytes_sec_max.read_bytes_sec_max')
def set_write_bytes_sec_max(params):
    """Set write_bytes_sec_max."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('write_bytes_sec_max', 1048576)
    print(f"virsh blkdeviotune {guest} vda --write-bytes-sec-max {value}")


@check
@requires('vm.blkdeviotune.bytes_sec_max.write_bytes_sec_max')
def check_write_bytes_sec_max(params):
    """Check write_bytes_sec_max."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep write_bytes_sec_max")


# IOPS MAX SETTINGS

@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.iops_sec.total_iops_sec')
@excludes('vm.blkdeviotune.iops_sec_max.total_iops_sec_max')
@provides('vm.blkdeviotune.iops_sec_max.total_iops_sec_max')
@excludes('vm.blkdeviotune.iops_sec_max.read_iops_sec_max',
          'vm.blkdeviotune.iops_sec_max.write_iops_sec_max')
def set_total_iops_sec_max(params):
    """Set total_iops_sec_max."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('total_iops_sec_max', 2000)
    print(f"virsh blkdeviotune {guest} vda --total-iops-sec-max {value}")


@check
@requires('vm.blkdeviotune.iops_sec_max.total_iops_sec_max')
def check_total_iops_sec_max(params):
    """Check total_iops_sec_max."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep total_iops_sec_max")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.iops_sec.read_iops_sec')
@excludes('vm.blkdeviotune.iops_sec_max.read_iops_sec_max')
@provides('vm.blkdeviotune.iops_sec_max.read_iops_sec_max')
@excludes('vm.blkdeviotune.iops_sec_max.total_iops_sec_max',
          'vm.blkdeviotune.iops_sec_max.write_iops_sec_max')
def set_read_iops_sec_max(params):
    """Set read_iops_sec_max."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('read_iops_sec_max', 1000)
    print(f"virsh blkdeviotune {guest} vda --read-iops-sec-max {value}")


@check
@requires('vm.blkdeviotune.iops_sec_max.read_iops_sec_max')
def check_read_iops_sec_max(params):
    """Check read_iops_sec_max."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep read_iops_sec_max")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.iops_sec.write_iops_sec')
@excludes('vm.blkdeviotune.iops_sec_max.write_iops_sec_max')
@provides('vm.blkdeviotune.iops_sec_max.write_iops_sec_max')
@excludes('vm.blkdeviotune.iops_sec_max.total_iops_sec_max',
          'vm.blkdeviotune.iops_sec_max.read_iops_sec_max')
def set_write_iops_sec_max(params):
    """Set write_iops_sec_max."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('write_iops_sec_max', 1000)
    print(f"virsh blkdeviotune {guest} vda --write-iops-sec-max {value}")


@check
@requires('vm.blkdeviotune.iops_sec_max.write_iops_sec_max')
def check_write_iops_sec_max(params):
    """Check write_iops_sec_max."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep write_iops_sec_max")


# IOPS SIZE SETTINGS

@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.iops_sec')
@excludes('vm.blkdeviotune.iops_sec.size_iops_sec')
@provides('vm.blkdeviotune.iops_sec.size_iops_sec')
def set_size_iops_sec(params):
    """Set size_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('size_iops_sec', 512)
    print(f"virsh blkdeviotune {guest} vda --size-iops-sec {value}")


@check
@requires('vm.blkdeviotune.iops_sec.size_iops_sec')
def check_size_iops_sec(params):
    """Check size_iops_sec."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep size_iops_sec")


# GROUP NAME SETTINGS

@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune')
@excludes('vm.blkdeviotune.group_name')
@provides('vm.blkdeviotune.group_name')
def set_group_name(params):
    """Set group_name."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('group_name', 'default-group')
    print(f"virsh blkdeviotune {guest} vda --group-name {value}")


@check
@requires('vm.blkdeviotune.group_name')
def check_group_name(params):
    """Check group_name."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep group_name")


# BYTES MAX LENGTH SETTINGS

@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.bytes_sec_max.total_bytes_sec_max')
@excludes('vm.blkdeviotune.bytes_sec_max_length.total_bytes_sec_max_length')
@provides('vm.blkdeviotune.bytes_sec_max_length.total_bytes_sec_max_length')
@excludes('vm.blkdeviotune.bytes_sec_max_length.read_bytes_sec_max_length',
          'vm.blkdeviotune.bytes_sec_max_length.write_bytes_sec_max_length')
def set_total_bytes_sec_max_length(params):
    """Set total_bytes_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('total_bytes_sec_max_length', 10)
    print(f"virsh blkdeviotune {guest} vda --total-bytes-sec-max-length {value}")


@check
@requires('vm.blkdeviotune.bytes_sec_max_length.total_bytes_sec_max_length')
def check_total_bytes_sec_max_length(params):
    """Check total_bytes_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep total_bytes_sec_max_length")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.bytes_sec_max.read_bytes_sec_max')
@excludes('vm.blkdeviotune.bytes_sec_max_length.read_bytes_sec_max_length')
@provides('vm.blkdeviotune.bytes_sec_max_length.read_bytes_sec_max_length')
@excludes('vm.blkdeviotune.bytes_sec_max_length.total_bytes_sec_max_length',
          'vm.blkdeviotune.bytes_sec_max_length.write_bytes_sec_max_length')
def set_read_bytes_sec_max_length(params):
    """Set read_bytes_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('read_bytes_sec_max_length', 10)
    print(f"virsh blkdeviotune {guest} vda --read-bytes-sec-max-length {value}")


@check
@requires('vm.blkdeviotune.bytes_sec_max_length.read_bytes_sec_max_length')
def check_read_bytes_sec_max_length(params):
    """Check read_bytes_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep read_bytes_sec_max_length")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.bytes_sec_max.write_bytes_sec_max')
@excludes('vm.blkdeviotune.bytes_sec_max_length.write_bytes_sec_max_length')
@provides('vm.blkdeviotune.bytes_sec_max_length.write_bytes_sec_max_length')
@excludes('vm.blkdeviotune.bytes_sec_max_length.total_bytes_sec_max_length',
          'vm.blkdeviotune.bytes_sec_max_length.read_bytes_sec_max_length')
def set_write_bytes_sec_max_length(params):
    """Set write_bytes_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('write_bytes_sec_max_length', 10)
    print(f"virsh blkdeviotune {guest} vda --write-bytes-sec-max-length {value}")


@check
@requires('vm.blkdeviotune.bytes_sec_max_length.write_bytes_sec_max_length')
def check_write_bytes_sec_max_length(params):
    """Check write_bytes_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep write_bytes_sec_max_length")


# IOPS MAX LENGTH SETTINGS

@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.iops_sec_max.total_iops_sec_max')
@excludes('vm.blkdeviotune.iops_sec_max_length.total_iops_sec_max_length')
@provides('vm.blkdeviotune.iops_sec_max_length.total_iops_sec_max_length')
@excludes('vm.blkdeviotune.iops_sec_max_length.read_iops_sec_max_length',
          'vm.blkdeviotune.iops_sec_max_length.write_iops_sec_max_length')
def set_total_iops_sec_max_length(params):
    """Set total_iops_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('total_iops_sec_max_length', 10)
    print(f"virsh blkdeviotune {guest} vda --total-iops-sec-max-length {value}")


@check
@requires('vm.blkdeviotune.iops_sec_max_length.total_iops_sec_max_length')
def check_total_iops_sec_max_length(params):
    """Check total_iops_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep total_iops_sec_max_length")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.iops_sec_max.read_iops_sec_max')
@excludes('vm.blkdeviotune.iops_sec_max_length.read_iops_sec_max_length')
@provides('vm.blkdeviotune.iops_sec_max_length.read_iops_sec_max_length')
@excludes('vm.blkdeviotune.iops_sec_max_length.total_iops_sec_max_length',
          'vm.blkdeviotune.iops_sec_max_length.write_iops_sec_max_length')
def set_read_iops_sec_max_length(params):
    """Set read_iops_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('read_iops_sec_max_length', 10)
    print(f"virsh blkdeviotune {guest} vda --read-iops-sec-max-length {value}")


@check
@requires('vm.blkdeviotune.iops_sec_max_length.read_iops_sec_max_length')
def check_read_iops_sec_max_length(params):
    """Check read_iops_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep read_iops_sec_max_length")


@action
@requires('vm.active', 'vm.config', 'vm.blkdeviotune.iops_sec_max.write_iops_sec_max')
@excludes('vm.blkdeviotune.iops_sec_max_length.write_iops_sec_max_length')
@provides('vm.blkdeviotune.iops_sec_max_length.write_iops_sec_max_length')
@excludes('vm.blkdeviotune.iops_sec_max_length.total_iops_sec_max_length',
          'vm.blkdeviotune.iops_sec_max_length.read_iops_sec_max_length')
def set_write_iops_sec_max_length(params):
    """Set write_iops_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    value = params.get('write_iops_sec_max_length', 10)
    print(f"virsh blkdeviotune {guest} vda --write-iops-sec-max-length {value}")


@check
@requires('vm.blkdeviotune.iops_sec_max_length.write_iops_sec_max_length')
def check_write_iops_sec_max_length(params):
    """Check write_iops_sec_max_length."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh blkdeviotune {guest} vda | grep write_iops_sec_max_length")


# CLEANUP

@cleanup
@requires('vm.blkdeviotune')
@cut('vm.blkdeviotune')
def clear_blkdeviotune(params):
    """Clear all blkdeviotune settings by restarting guest."""
    guest = params.get('guest_name', 'testvm')
    print(f"virsh destroy {guest}")
    print(f"virsh start {guest}")
