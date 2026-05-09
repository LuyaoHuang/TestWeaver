from testweaver import action, cleanup, provides, requires, excludes, graft, cut


@action
@provides('vm.config')
@excludes('vm.config')
def define_guest(params):
    """Define a guest from XML."""
    guest_name = params.get('guest_name', 'testvm')
    guest_xml = params.get('guest_xml', '/tmp/guest.xml')
    print(f"virsh define {guest_xml}")


@action
@requires('vm.config')
@excludes('vm.active')
@graft('vm.config', 'vm.active')
def start_guest(params):
    """Start a defined guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh start {guest_name}")


@action
@requires('vm.active')
@cut('vm.active')
def destroy_guest(params):
    """Force stop a running guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh destroy {guest_name}")


@cleanup
@requires('vm.config')
@excludes('vm.active')
@cut('vm.config')
def undefine_guest(params):
    """Undefine a guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh undefine {guest_name}")
