from testweaver import (
    action, check, cleanup, provides, requires, excludes, cut,
    when_param, unless_param,
)


@action
@when_param('tpm_backend', 'emulator')
@provides('swtpm_installed')
@excludes('swtpm_installed')
def install_swtpm(params):
    """Install swtpm packages."""
    print("yum install swtpm swtpm-tools -y")


@cleanup
@requires('swtpm_installed')
@excludes('vm.config', 'vm.active')
@cut('swtpm_installed')
def uninstall_swtpm(params):
    """Uninstall swtpm packages."""
    print("yum remove swtpm swtpm-tools -y")


@action
@when_param('tpm_backend', 'emulator')
@provides('tpm_secret')
@excludes('tpm_secret')
def create_tpm_secret(params):
    """Create a TPM secret via virsh secret-define."""
    print("virsh secret-define --file /tmp/tpm_secret.xml")
    print("virsh secret-set-value <uuid> <value>")


@cleanup
@requires('tpm_secret')
@excludes('vm.config.tpm', 'vm.active.tpm')
@cut('tpm_secret')
def undefine_tpm_secret(params):
    """Undefine the TPM secret."""
    print("virsh secret-undefine <uuid>")


@action
@when_param('tpm_backend', 'emulator')
@requires('vm.config', 'swtpm_installed')
@excludes('vm.config.tpm')
@provides('vm.config.tpm')
def add_tpm_emulator(params):
    """Add emulated TPM device to inactive guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    tpm_model = params.get('tpm_model', 'tpm-crb')
    print(f"# Adding emulated TPM model={tpm_model} to {guest_name} XML")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <tpm model='{tpm_model}'><backend type='emulator'/></tpm>")
    print(f"virsh define /tmp/vm.xml")


@action
@when_param('tpm_backend', 'passthrough')
@requires('vm.config')
@excludes('vm.config.tpm')
@provides('vm.config.tpm')
def add_tpm_passthrough(params):
    """Add passthrough TPM device to inactive guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"# Adding passthrough TPM to {guest_name} XML")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Insert <tpm model='tpm-tis'><backend type='passthrough'><device path='/dev/tpm0'/></backend></tpm>")
    print(f"virsh define /tmp/vm.xml")


@action
@requires('vm.config.tpm')
@cut('vm.config.tpm')
def rm_tpm_in_inactive_xml(params):
    """Remove TPM device from inactive guest XML."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"# Removing TPM from {guest_name} XML")
    print(f"virsh dumpxml {guest_name} > /tmp/vm.xml")
    print("# Remove <tpm> element from XML")
    print(f"virsh define /tmp/vm.xml")


@check
@requires('vm.active.tpm')
def verify_tpm_in_vm(params):
    """Verify TPM device is visible inside guest."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"# Checking TPM in {guest_name}")
    print("ssh guest 'ls /dev/tpm0'")
    print("ssh guest 'tpm2_getrandom 8'")
    print("ssh guest 'tpm2_pcrread'")


@action
@requires('vm.active.tpm')
@provides('swtpm_state_file')
@excludes('swtpm_state_file')
def provide_swtpm_state_file(params):
    """Verify swtpm state file exists after guest runs."""
    print("ls /var/lib/libvirt/swtpm/<domuuid>/tpm2/tpm2-00.permall")


@check
@requires('swtpm_state_file')
def verify_swtpm_state_file(params):
    """Verify swtpm state file is present."""
    print("test -f /var/lib/libvirt/swtpm/<domuuid>/tpm2/tpm2-00.permall")


@cleanup
@requires('swtpm_state_file')
@excludes('vm.active', 'vm.config')
@cut('swtpm_state_file')
def rm_swtpm_state_file(params):
    """Remove swtpm state file."""
    print("rm -f /var/lib/libvirt/swtpm/<domuuid>/tpm2/tpm2-00.permall")
