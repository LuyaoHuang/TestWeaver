# Case Prioritization

Sort generated test cases by different strategies to control execution order. Sorting applies after filtering: generate -> filter -> sort -> run.

## Sort by Step Count

Run the shortest (simplest) test cases first — useful for fast smoke-test feedback:

```bash
testweaver run my_test.yaml --sort shortest
```

Or prioritize thorough integration tests:

```bash
testweaver run my_test.yaml --sort longest
```

## Sort by Operation Priority

Assign priority levels to operations with `@priority`. Higher values = more important.

```python
from testweaver import action, check, cleanup, provides, requires, clears, priority

@action
@priority(1)
@provides('vm.defined')
def define_vm(params):
    print(f"virsh define {params.get('vm_name')}")

@action
@priority(3)
@requires('vm.defined')
@provides('vm.active')
def start_vm(params):
    print(f"virsh start {params.get('vm_name')}")

@check
@priority(10)
@requires('vm.active')
def verify_vm_running(params):
    print(f"virsh domstate {params.get('vm_name')}")

@check
@priority(2)
@requires('vm.defined')
def verify_vm_defined(params):
    print(f"virsh dominfo {params.get('vm_name')}")

@cleanup
@requires('vm.defined')
@clears('vm.defined')
def undefine_vm(params):
    print(f"virsh undefine {params.get('vm_name')}")
```

Sort by target operation priority — cases targeting `verify_vm_running` (priority 10) run before `verify_vm_defined` (priority 2):

```bash
testweaver run vm_test.yaml --sort target
```

Sort by total priority (sum of all steps in the case):

```bash
testweaver run vm_test.yaml --sort total
```

## Sort by Fault Status

Run fault-injection cases before (or after) normal cases:

```bash
# Fault cases first — test error handling early
testweaver run my_test.yaml --sort fault-first

# Normal cases first — verify happy path before fault injection
testweaver run my_test.yaml --sort fault-last
```

## Random Order

Randomize case order to discover order-dependent bugs:

```bash
testweaver run my_test.yaml --sort random

# Reproducible random order with a seed
testweaver run my_test.yaml --sort random --sort-seed 42
```

## YAML Priority

Set priorities directly in YAML definitions:

```yaml
operations:
  - name: define_vm
    type: action
    provides: [vm.defined]
    priority: 1
    run: virsh define $vm_name

  - name: verify_vm_running
    type: check
    requires: [vm.active]
    priority: 10
    run: virsh domstate $vm_name | grep running
```

## Combining Sort with Filters

Sorting applies after filtering, so you can combine both:

```bash
# Run non-fault cases, shortest first
testweaver run my_test.yaml --no-fault --sort shortest

# Run only check-* cases, sorted by target priority
testweaver run my_test.yaml -k "check-*" --sort target

# Preview sorted case order without executing
testweaver generate my_test.yaml --sort target --format text
```

## Programmatic API

```python
from testweaver.sorting import sort_cases, SORT_STRATEGIES
from testweaver.graph import generate_cases

cases = generate_cases(definition)

# Sort by step count
short_first = sort_cases(cases, "shortest")

# Sort by target priority (requires operations for priority lookup)
by_priority = sort_cases(cases, "target", operations=definition.operations)

# Sort by total step priority
by_total = sort_cases(cases, "total", operations=definition.operations)

# Reproducible random order
shuffled = sort_cases(cases, "random", seed=42)

# Check available strategies
print(SORT_STRATEGIES)
# ('shortest', 'longest', 'target', 'total', 'fault-first', 'fault-last', 'random')

# Inspect computed priority scores
for case in by_priority:
    print(f"{case.case_id}: priority={case.priority}")
```

## Strategy Reference

| Strategy | Sort Key | Direction | Requires `operations`? |
|----------|----------|-----------|----------------------|
| `shortest` | `len(case.steps)` | Ascending (fewest first) | No |
| `longest` | `len(case.steps)` | Descending (most first) | No |
| `target` | Target operation's `priority` | Descending (highest first) | Yes |
| `total` | Sum of all step priorities | Descending (highest first) | Yes |
| `fault-first` | `is_fault` flag | Faults first | No |
| `fault-last` | `is_fault` flag | Faults last | No |
| `random` | Random shuffle | N/A | No |
