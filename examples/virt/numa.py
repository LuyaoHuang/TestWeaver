from testweaver import action, provides, requires, excludes


@action
@requires('vm.config')
@excludes('vm.config.numa')
@provides('vm.config.numa')
def set_guest_numa(params):
    """Set NUMA topology in guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    numa_nodes = params.get('numa_nodes', 2)
    print(f"# Setting {numa_nodes}-node NUMA topology for {guest_name}")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <numa> element into <cpu> section")
    print(f"virsh define /tmp/vm.xml")
