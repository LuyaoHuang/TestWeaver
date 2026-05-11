from testweaver import action, check, provides, requires, excludes


@action
@excludes('hugepage_config')
@provides('hugepage_config')
def host_hugepage_config(params):
    """Configure hugepages on host."""
    pagesize = params.get('pagesize', '2048')
    print(f"echo {pagesize} > /proc/sys/vm/nr_hugepages")
    print(f"mount -t hugetlbfs hugetlbfs /dev/hugepages")


@action
@requires('vm.config', 'hugepage_config')
@excludes('vm.config.hugepage')
@provides('vm.config.hugepage')
def guest_hugepage_settings(params):
    """Set hugepage XML element in guest config."""
    guest_name = params.get('guest_name', 'testvm')
    pagesize = params.get('pagesize', '2048')
    print(f"# Setting hugepage pagesize={pagesize} for {guest_name}")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <memoryBacking><hugepages/></memoryBacking>")
    print(f"virsh define /tmp/vm.xml")


@check
@requires('hugepage_config', 'vm.active.hugepage')
def check_hugepage_cmdline(params):
    """Check hugepage in QEMU command line."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"ps aux | grep {guest_name} | grep hugepage")


@action
@requires('vm.config')
@excludes('vm.config.mlock')
@provides('vm.config.mlock')
def set_mem_lock_xml(params):
    """Set memory lock in guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"# Setting <memoryBacking><locked/></memoryBacking> for {guest_name}")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <locked/> element")
    print(f"virsh define /tmp/vm.xml")


@check
@requires('vm.active.mlock')
def verify_mem_lock(params):
    """Verify memory lock is active."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"ps aux | grep {guest_name} | grep mlock")
    print("cat /proc/$(pidof qemu-kvm)/status | grep VmLck")


@action
@requires('vm.config')
@excludes('vm.config.nosharepage')
@provides('vm.config.nosharepage')
def set_nosharepage_xml(params):
    """Set nosharepage in guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"# Setting <memoryBacking><nosharepages/></memoryBacking> for {guest_name}")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <nosharepages/> element")
    print(f"virsh define /tmp/vm.xml")


@check
@requires('vm.active.nosharepage')
def verify_nosharepage(params):
    """Verify nosharepage is active."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"ps aux | grep {guest_name} | grep nosharepage")


@action
@requires('vm.active')
@excludes('vm.active.memtune')
@provides('vm.active.memtune')
def virsh_memtune(params):
    """Set memtune on running guest."""
    guest_name = params.get('guest_name', 'testvm')
    memtune = params.get('memtune', '1048576')
    print(f"virsh memtune {guest_name} --hard-limit {memtune}")


@action
@requires('vm.config')
@excludes('vm.config.memtune')
@provides('vm.config.memtune')
def virsh_memtune_conf(params):
    """Set memtune on inactive guest config."""
    guest_name = params.get('guest_name', 'testvm')
    memtune = params.get('memtune', '1048576')
    print(f"virsh memtune {guest_name} --hard-limit {memtune} --config")


@check
@requires('vm.active.memtune')
def verify_memtune_cgroup(params):
    """Verify memtune setting in cgroup."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"# Check cgroup memory limit for {guest_name}")
    print("cat /sys/fs/cgroup/machine.slice/*/memory.max")


@check
@requires('vm.active.memtune')
def verify_memtune_xml(params):
    """Verify memtune setting in guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh memtune {guest_name}")


@action
@requires('vm.config')
@excludes('vm.config.memballoon')
@provides('vm.config.memballoon')
def set_memballoon_xml(params):
    """Set memballoon model in guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    memballoon = params.get('memballoon', 'virtio')
    print(f"# Setting memballoon model={memballoon} for {guest_name}")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print(f"# Insert <memballoon model='{memballoon}'/>")
    print(f"virsh define /tmp/vm.xml")


@action
@requires('vm.active')
@excludes('vm.active.curmem')
@provides('vm.active.curmem')
def hot_set_guest_mem(params):
    """Hot-set guest current memory."""
    guest_name = params.get('guest_name', 'testvm')
    curmem = params.get('curmem', '524288')
    print(f"virsh setmem {guest_name} {curmem} --live")


@action
@requires('vm.config')
@excludes('vm.config.curmem')
@provides('vm.config.curmem')
def cold_set_guest_mem(params):
    """Cold-set guest current memory."""
    guest_name = params.get('guest_name', 'testvm')
    curmem = params.get('curmem', '524288')
    print(f"virsh setmem {guest_name} {curmem} --config")


@check
@requires('vm.active.curmem')
def verify_setmem_in_guest(params):
    """Verify memory size inside guest."""
    print("ssh guest 'free -m'")
    print("ssh guest 'cat /proc/meminfo | grep MemTotal'")


@action
@requires('vm.config')
@excludes('vm.config.mem_period')
@provides('vm.config.mem_period')
def virsh_set_period_conf(params):
    """Set memory stats period on inactive guest."""
    guest_name = params.get('guest_name', 'testvm')
    mem_period = params.get('mem_period', '10')
    print(f"virsh dommemstat {guest_name} --period {mem_period} --config")


@action
@requires('vm.active')
@excludes('vm.active.mem_period')
@provides('vm.active.mem_period')
def virsh_set_period(params):
    """Set memory stats period on running guest."""
    guest_name = params.get('guest_name', 'testvm')
    mem_period = params.get('mem_period', '10')
    print(f"virsh dommemstat {guest_name} --period {mem_period} --live")


@check
@requires('vm.active')
def virsh_dommemstat(params):
    """Check guest memory statistics."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh dommemstat {guest_name}")


@check
@requires('vm.active.mem_period')
def check_period_in_xml(params):
    """Verify memory period in guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh dumpxml {guest_name} | grep period")
