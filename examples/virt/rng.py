from testweaver import (
    action, check, cleanup, provides, requires, clears, excludes, cut,
    when_param, unless_param,
)


@action
@when_param('rng_backend_model', 'egd')
@when_param('rng_source_mode', 'server')
@excludes('vm.active.rng', 'rng_source')
@provides('rng_source')
def create_rng_source_server(params):
    """Create a server as RNG source for EGD backend."""
    print("cat /dev/urandom | nc -k -l 1234 &")


@action
@when_param('rng_backend_model', 'egd')
@when_param('rng_source_mode', 'client')
@requires('vm.active.rng')
@excludes('rng_source')
@provides('rng_source')
def create_rng_source_client(params):
    """Create a client as RNG source for EGD backend (bind mode)."""
    host = params.get('rng_host', '127.0.0.1')
    port = params.get('rng_port', '1234')
    print(f"cat /dev/urandom | nc {host} {port} &")


@action
@requires('rng_source')
@excludes('vm.active.rng')
@clears('rng_source')
def destroy_rng_source(params):
    """Destroy RNG source processes."""
    print("pkill -9 socat")
    print("pkill -9 nc")
    print("pkill -9 cat")


@action
@requires('vm.config')
@excludes('vm.config.rng')
@provides('vm.config.rng')
def add_rng_in_inactive_vmxml(params):
    """Add RNG device to inactive guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    rng_model = params.get('rng_model', 'virtio')
    print(f"# Adding RNG model={rng_model} to {guest_name} XML")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <rng model='virtio'><backend model='random'>/dev/urandom</backend></rng>")
    print(f"virsh define /tmp/vm.xml")


@action
@requires('vm.config')
@requires('vm.config.rng')
@clears('vm.config.rng')
def rm_rng_in_inactive_vmxml(params):
    """Remove RNG device from inactive guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"# Removing RNG from {guest_name} XML")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Remove <rng> element from XML")
    print(f"virsh define /tmp/vm.xml")


@action
@requires('vm.active')
@excludes('vm.active.rng')
@provides('vm.active.rng')
def live_attach_rng_device(params):
    """Hot-plug RNG device to running guest."""
    guest_name = params.get('guest_name', 'testvm')
    rng_model = params.get('rng_model', 'virtio')
    print(f"# Preparing RNG device XML with model={rng_model}")
    print(f"virsh attach-device {guest_name} /tmp/rng.xml --live")


@action
@requires('vm.active.rng')
@clears('vm.active.rng')
def live_detach_rng_device(params):
    """Hot-unplug RNG device from running guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh detach-device {guest_name} /tmp/rng.xml --live")


@action
@requires('vm.config')
@excludes('vm.config.rng')
@provides('vm.config.rng')
def cold_attach_rng_device(params):
    """Cold-plug RNG device to inactive guest."""
    guest_name = params.get('guest_name', 'testvm')
    rng_model = params.get('rng_model', 'virtio')
    print(f"# Preparing RNG device XML with model={rng_model}")
    print(f"virsh attach-device {guest_name} /tmp/rng.xml --config")


@action
@requires('vm.config.rng')
@clears('vm.config.rng')
def cold_detach_rng_device(params):
    """Cold-unplug RNG device from inactive guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh detach-device {guest_name} /tmp/rng.xml --config")


@check
@requires('vm.active.rng')
def verify_rng_in_vm(params):
    """Verify RNG device is functional inside guest."""
    print("ssh guest 'dd if=/dev/hwrng of=/dev/null count=100'")


@check
@requires('vm.active')
@excludes('vm.active.rng')
def verify_no_rng_in_vm(params):
    """Verify no RNG device exists inside guest."""
    print("ssh guest 'dd if=/dev/hwrng of=/dev/null count=1'")
    print("# Expected: No such device")


@cleanup
@requires('rng_source')
@excludes('vm.active', 'vm.config')
@cut('rng_source')
def cleanup_rng_source(params):
    """Clean up RNG source processes."""
    print("pkill -9 socat")
    print("pkill -9 nc")
    print("pkill -9 cat")
