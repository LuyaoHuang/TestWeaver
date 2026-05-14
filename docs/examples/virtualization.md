# Virtualization Examples

The `examples/virt/` directory contains mock implementations of libvirt/QEMU test operations, ported from depend-test-framework:

| Module | Operations | Description |
|--------|-----------|-------------|
| `vm_basic.py` | 4 | Guest lifecycle: define, start, destroy, undefine |
| `vtpm.py` | 11 | vTPM device management with param_choices (emulator vs passthrough) |
| `save_restore.py` | 8 | Save/restore using graft+cut migrate pattern |
| `vdisk.py` | 2 | Virtual disk attach and verify |
| `multi_disk.py` | 8 | Multi-disk hot-plug with additive namespaces and wildcard queries |
| `backing_chain.py` | 5 | Snapshot management with block pull/commit |
| `schedinfo.py` | 7 | CPU scheduling parameters |
| `numa.py` | 1 | NUMA topology configuration |
| `mem_device.py` | 4 | Memory hotplug |

Try them:

```bash
testweaver generate examples/virt/vdisk_test.yaml --format text
testweaver run examples/virt/backing_chain_test.yaml --format text
testweaver graph examples/virt/save_restore_test.yaml --format text
testweaver graph examples/virt/save_restore_test.yaml --format dot -o save_restore.dot

# Parameter graph: emulator vs passthrough generate different test paths
testweaver generate examples/virt/vtpm_test.yaml --format text

# Parameter matrix: test cpu_shares with 3 values
testweaver generate examples/virt/schedinfo_test.yaml --format text
testweaver matrix examples/virt/schedinfo_test.yaml --format text

# Multi-instance: additive disk namespaces with wildcard queries
testweaver generate examples/virt/multi_disk_test.yaml --format text
testweaver run examples/virt/multi_disk_test.yaml --format text
```
