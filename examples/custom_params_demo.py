"""
Environment-Aware Test Parameters
==================================

Demonstrates the ``@custom_params`` decorator for detecting the runtime
environment and adjusting test parameters before case generation.

Use cases:
  - Detect OS / kernel / cgroup versions at runtime
  - Check available hardware or drivers
  - Adjust parameters based on host configuration

The decorated function runs once during definition loading, after module
import but before the dependency graph is built.  CLI ``--param`` overrides
still take precedence.

Scenario:
  1. Detect available hypervisor (KVM vs no-KVM)
  2. Detect host architecture
  3. Combine into params that downstream operations can reference
"""
from __future__ import annotations

import platform
import subprocess
from testweaver import action, check, custom_params, provides, requires


# ---------------------------------------------------------------------------
# Custom params: detect environment at load time
# ---------------------------------------------------------------------------


@custom_params
def detect_environment(params):
    """Detect host capabilities and set baseline params."""
    # Detect virtualization support
    try:
        subprocess.run(
            ['test', '-e', '/dev/kvm'],
            check=True, capture_output=True,
        )
        params['hypervisor'] = 'kvm'
        params['vm_count'] = 4
    except subprocess.CalledProcessError:
        params['hypervisor'] = 'none'
        params['vm_count'] = 0

    # Detect architecture
    params['arch'] = platform.machine()

    # Detect OS family
    params['os'] = platform.system().lower()

    return params


# ---------------------------------------------------------------------------
# Operations that use the detected params
# ---------------------------------------------------------------------------


@action
@provides('vms.running')
def start_vms(params, env):
    """Start VMs based on the detected hypervisor capability."""
    hv = params.get('hypervisor', 'none')
    count = params.get('vm_count', 0)
    arch = params.get('arch', 'unknown')

    if hv == 'none':
        print(f"[SKIP] No hypervisor available on {arch}, skipping VM start")
        return

    print(f"Starting {count} VM(s) on {hv} ({arch})")
    for i in range(count):
        print(f"  VM {i}: started")


@check
@requires('vms.running')
def verify_vms(params, env):
    """Verify VMs are running — only generated when hypervisor is available."""
    count = params.get('vm_count', 0)
    print(f"Verifying {count} VM(s) are healthy")


@action
@requires('vms.running')
def stop_vms(params, env):
    """Stop all running VMs."""
    print(f"Stopping VMs (hypervisor={params.get('hypervisor')})")
