from testweaver import action, check, provides, requires, excludes, cut


@action
@requires('vm.active', 'vm.config')
@excludes('vm.with_snapshots')
@provides('vm.with_snapshots')
def create_snapshot(params):
    """Create a disk snapshot."""
    guest_name = params.get('guest_name', 'testvm')
    snap_name = params.get('snapshot_name', 'snap1')
    print(f"virsh snapshot-create-as {guest_name} {snap_name} --disk-only")


@check
@requires('vm.with_snapshots')
@excludes('vm.with_snapshots.block_pulled', 'vm.with_snapshots.block_committed')
def check_snapshots(params):
    """Verify snapshots exist in the backing chain."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh snapshot-list {guest_name}")
    print(f"virsh domblkinfo {guest_name} vda")


@action
@requires('vm.active', 'vm.config', 'vm.with_snapshots')
@excludes('vm.with_snapshots.block_pulled', 'vm.with_snapshots.block_committed')
@provides('vm.with_snapshots.block_pulled')
def block_pull_snapshots(params):
    """Block-pull to flatten the backing chain."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh blockpull {guest_name} vda --wait")


@action
@requires('vm.active', 'vm.config', 'vm.with_snapshots')
@excludes('vm.with_snapshots.block_pulled', 'vm.with_snapshots.block_committed')
@provides('vm.with_snapshots.block_committed')
def block_commit_snapshots(params):
    """Block-commit to merge snapshot layers."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh blockcommit {guest_name} vda --active --wait --pivot")


@action
@requires('vm.active', 'vm.config', 'vm.with_snapshots')
@cut('vm.with_snapshots')
def delete_snapshots(params):
    """Delete all snapshots and restore original disk."""
    guest_name = params.get('guest_name', 'testvm')
    print(f"virsh snapshot-list {guest_name} --name | xargs -I {{}} virsh snapshot-delete {guest_name} {{}} --metadata")
    print(f"# Recreate guest with original disk")
    print(f"virsh destroy {guest_name}")
    print(f"virsh undefine {guest_name}")
    print(f"virsh define /tmp/guest.xml")
    print(f"virsh start {guest_name}")
