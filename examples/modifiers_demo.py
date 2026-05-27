"""Demonstrate graph modifiers with a simplified VM testing scenario.

Three modifier types are shown:

1. EdgeGuard — configure_hugepages blocks start_vm when hugepages
   are disabled, forcing the runner to find an alternative path.

2. TransientHook — set_memtune injects a libvirtd restart before
   the next memtune-related operation.

3. TransitionObserver — attach_mem_device registers an audit log
   check that runs after every attach/detach operation.
"""
from testweaver import (
    action, check, cleanup, provides, requires, clears, excludes,
    EdgeGuard, TransientHook, TransitionObserver,
)


# --- Setup operations ---

@action
@provides('vm.config')
@excludes('vm.config')
def define_vm(params, env):
    print(f"  virsh define {params.get('guest_name', 'testvm')}.xml")


@action
@requires('vm.config')
@excludes('vm.active')
@provides('vm.active')
def start_vm(params, env):
    print(f"  virsh start {params.get('guest_name', 'testvm')}")


@action
@requires('vm.config')
@excludes('vm.active')
@provides('vm.active')
def start_vm_alt(params, env):
    """Alternative start path (without hugepage dependency)."""
    print(f"  virsh start {params.get('guest_name', 'testvm')} --skip-hugepages")


# --- EdgeGuard demo ---

@action
@requires('vm.config')
@excludes('hugepage_config')
@provides('hugepage_config')
def configure_hugepages(params, env):
    """Configure hugepages on the host.

    When hugetlbfs_mount is empty, hugepages are disabled and
    start_vm will fail. Returns an EdgeGuard to block it.
    """
    mount = params.get('hugetlbfs_mount', '/dev/hugepages')
    print(f"  Setting hugetlbfs_mount = '{mount}'")
    if mount == '':
        return EdgeGuard(
            blocked_op='start_vm',
            reason='hugepages disabled by empty mount path',
        )


# --- TransientHook demo ---

@action
@requires('vm.active')
@excludes('vm.active.memtune')
@provides('vm.active.memtune')
def set_memtune(params, env):
    """Set memory tuning parameters.

    When restart_libvirtd param is set, injects a libvirtd restart
    before the next check_memtune operation.
    """
    limit = params.get('hard_limit', 1048576)
    print(f"  virsh memtune {params.get('guest_name', 'testvm')} --hard-limit {limit}")
    if params.get('restart_libvirtd'):
        def restart_libvirtd(p):
            print("  systemctl restart libvirtd")

        return TransientHook(
            before_op='check_memtune',
            action=restart_libvirtd,
            name='restart_libvirtd',
            reason='libvirtd restart required after memtune',
        )


# --- TransitionObserver demo ---

@action
@requires('vm.active')
@excludes('vm.active.memdevice')
@provides('vm.active.memdevice')
def attach_mem_device(params, env):
    """Hot-attach a memory device and register audit observer."""
    print(f"  virsh attach-device {params.get('guest_name', 'testvm')} mem.xml")

    def check_audit(p):
        print(f"  ausearch -m VIRT_RESOURCE -ts recent | grep memory")

    return TransitionObserver(
        watch_ops=['attach_mem_device', 'detach_mem_device'],
        verify=check_audit,
        name='audit_log_check',
        reason='verify audit trail after memory device changes',
    )


# --- Check operations ---

@check
@requires('vm.active')
def check_vm_running(params, env):
    print(f"  virsh domstate {params.get('guest_name', 'testvm')}")


@check
@requires('vm.active.memtune')
def check_memtune(params, env):
    print(f"  virsh memtune {params.get('guest_name', 'testvm')}")


@check
@requires('vm.active.memdevice')
def check_mem_device(params, env):
    print(f"  virsh dommemstat {params.get('guest_name', 'testvm')}")


# --- Cleanup operations ---

@cleanup
@requires('vm.active')
@clears('vm.active')
def destroy_vm(params, env):
    print(f"  virsh destroy {params.get('guest_name', 'testvm')}")


@cleanup
@requires('vm.config')
@excludes('vm.active')
@clears('vm.config')
def undefine_vm(params, env):
    print(f"  virsh undefine {params.get('guest_name', 'testvm')}")
