# Lifecycle Hooks

Lifecycle hooks run at fixed points in the test execution, outside the dependency graph. They're ideal for environment provisioning, log collection, state snapshots, and cleanup tasks that don't participate in case generation.

## Suite-Level Hooks

`@suite_setup` runs once before any test case. `@suite_teardown` runs once after all cases finish, even if suite setup or cases fail.

```python
from testweaver import suite_setup, suite_teardown

@suite_setup
def provision_vms(context):
    """Start the test VM pool."""
    print(f"Provisioning VMs for suite: {context['_suite_name']}")
    print(f"Will run {context['_case_count']} test cases")

@suite_teardown
def collect_logs(context):
    """Gather all VM logs — runs even if suite setup failed."""
    if context.get('_suite_setup_failed'):
        print("Suite setup failed, collecting diagnostic logs")
    else:
        print("Collecting final test logs")
```

Suite hooks receive a context dict containing all suite-level params plus:

| Key | Type | Description |
|-----|------|-------------|
| `_suite_name` | `str` | Name of the test suite |
| `_case_count` | `int` | Number of cases to run |
| `_suite_setup_failed` | `bool` | (teardown only) Whether suite setup failed |

## Case-Level Hooks

`@case_setup` runs before each test case. `@case_teardown` runs after each case, even on failure.

```python
from testweaver import case_setup, case_teardown

@case_setup
def snapshot_vm(context):
    """Take a VM snapshot before each test case."""
    case_id = context['_case_id']
    print(f"Creating snapshot for case: {case_id}")

@case_teardown
def restore_and_log(context):
    """Restore VM state and collect logs after each case."""
    status = context.get('_status', 'unknown')
    case_id = context['_case_id']
    print(f"Case {case_id} finished with status: {status}")
    if status != "pass":
        print(f"Collecting failure logs for {case_id}")
```

Case hooks receive a context dict containing case-level params plus:

| Key | Type | Description |
|-----|------|-------------|
| `_case` | `TestCase` | The test case object |
| `_case_id` | `str` | Case identifier |
| `_status` | `str` | (teardown only) Case status before teardown |

## Multiple Hooks

You can define multiple hooks of the same type. They run in definition order, and a failure in one does not prevent others from running:

```python
@case_teardown
def save_vm_logs(context):
    print("Saving VM logs...")

@case_teardown
def save_network_logs(context):
    print("Saving network logs...")

@case_teardown
def reset_firewall(context):
    print("Resetting firewall rules...")
```

## Error Semantics

| Scenario | Behavior |
|----------|----------|
| Suite setup fails | All cases skipped (status=error); suite teardown still runs |
| Case setup fails | Main steps skipped; cleanup and case teardown still run |
| Teardown fails | Recorded in results but doesn't change case/suite status |
| One hook of N fails | Remaining hooks still run |

## Programmatic API

```python
from testweaver.engine import run_all, run_case
from testweaver.schema import LifecycleHooks

# Hooks can be set programmatically
hooks = LifecycleHooks(
    suite_setup=[my_setup_fn],
    suite_teardown=[my_teardown_fn],
    case_setup=[my_case_setup],
    case_teardown=[my_case_teardown],
)
definition.hooks = hooks

# run_all returns (case_results, suite_hook_results)
results, suite_hooks = run_all(cases, definition, workers=4)

# Suite hook results
for hr in suite_hooks:
    print(f"Suite hook: {hr.hook_name} ({hr.hook_type}): {hr.status}")

# Case hook results are per-case
for r in results:
    for hr in r.hook_results:
        print(f"  {hr.hook_type}: {hr.hook_name} -> {hr.status}")
        if hr.error:
            print(f"    Error: {hr.error}")
```

## HookResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `hook_name` | `str` | Function name |
| `hook_type` | `str` | One of `suite_setup`, `suite_teardown`, `case_setup`, `case_teardown` |
| `status` | `str` | `"pass"` or `"error"` |
| `error` | `str \| None` | Error message on failure |
| `duration_ms` | `float` | Execution time in milliseconds |
