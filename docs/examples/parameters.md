# Parameter Support

TestWeaver offers two approaches for parameterized testing.

## Approach 1: Parameter Graph (`param_choices`)

Parameter values become states in the dependency graph. The graph engine naturally discovers all valid paths for each parameter combination. Use this when parameters change *which operations are available*.

```python
# vtpm_ops.py
from testweaver import action, check, provides, requires, excludes, when_param

@action
@when_param('tpm_backend', 'emulator')
@provides('swtpm_installed')
@excludes('swtpm_installed')
def install_swtpm(params):
    """Only runs when tpm_backend=emulator"""
    print("yum install swtpm swtpm-tools -y")

@action
@requires('vm.config')
@provides('vm.config.tpm')
def add_tpm(params):
    print(f"Adding TPM to {params.get('guest_name')}")

@check
@requires('vm.active.tpm')
def verify_tpm(params):
    print("Checking /dev/tpm0 inside guest")
```

```yaml
modules:
  - vtpm_ops.py

suite:
  name: vtpm
  targets: [verify_tpm]
  param_choices:
    - name: tpm_backend
      values: [emulator, passthrough]
```

The graph generates different test paths: emulator paths go through `install_swtpm`, passthrough paths skip it.

## Approach 2: Parameter Matrix (`param_matrix`)

Defines parameter axes and constraint rules. Generates the Cartesian product of values, filters invalid combinations, and runs each valid combination through the graph. Use this when parameters are *data values* that don't change graph structure.

```yaml
modules:
  - schedinfo_ops.py

suite:
  name: schedinfo
  targets: [check_cpu_shares]
  params:
    guest_name: testvm
  param_matrix:
    axes:
      - name: cpu_shares
        values: [512, 1024, 2048]
      - name: vcpu_count
        values: [1, 2, 4]
    constraints:
      - when: {cpu_shares: 2048, vcpu_count: 1}
        exclude: true
        reason: "Invalid combo: high shares with single vCPU"
```

You can also use the `@skip_when` decorator on operations:

```python
@action
@skip_when(vcpu_count=1)
@requires('vm.active')
@provides('vm.schedinfo.numa_balanced')
def enable_numa_balancing(params):
    """Skip for single-vCPU guests"""
    pass
```

## CLI Parameter Override

Override or add parameters from the command line:

```bash
testweaver run my_test.yaml -p guest_name=testvm -p timeout=60
testweaver matrix my_test.yaml --format text   # Preview parameter combinations
```

## Approach 3: Runtime Param Filtering (`@params_require`)

When params are detected at runtime via `@custom_params`, use `@params_require` to filter operations before the graph is built. This is the recommended companion to `@custom_params`:

```python
from testweaver import action, check, custom_params, params_require, provides, requires

@custom_params
def detect_env(params):
    import os
    params['has_kvm'] = os.path.exists('/dev/kvm')
    return params

@action
@provides('vm.active')
@params_require('has_kvm')
def start_kvm_vm(params, env):
    """Only included when /dev/kvm exists."""
    ...

@check
@requires('vm.active')
@params_require(('hypervisor', '=', 'kvm'))
def verify_kvm(params, env):
    """Only included when hypervisor is exactly 'kvm'."""
    ...
```

- **String argument** — operation is included only if the key exists in params
- **3-tuple argument** `(key, operator, value)` — operation is included only if `params[key]` matches (supports `=` and `!=`)
- Filtering happens after `@custom_params` and CLI `--param` overrides, but before graph building
- Operations without `@params_require` are always included (no filtering)

