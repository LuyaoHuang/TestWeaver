# Tag Filtering

Tags let you label operations and then filter test cases by those labels in the suite YAML. This is the recommended way to create separate smoke/regression/slow test suites that share the same operation definitions.

## Tagging Operations

Use the `@tag` decorator on any operation:

```python
from testweaver import action, check, tag, provides, requires

@tag("smoke", "fast")
@check
@requires('vm.active')
def verify_vm(params, env):
    """Quick sanity check — runs in every smoke suite."""
    pass

@tag("slow", "e2e")
@action
@provides('vm.active')
def provision_vm(params, env):
    """Full VM provisioning — only in e2e suites."""
    pass

@tag("regression")
@action
@provides('data.ready')
def load_test_data(params, env):
    """Loads test fixtures — regression only."""
    pass
```

Tags can also be set in YAML definitions:

```yaml
operations:
  - name: verify_vm
    type: check
    requires: [vm.active]
    run: "test -f /tmp/vm-ready"
    tags: [smoke, fast]
```

## Suite-Level Filtering

Control which tagged operations run via `filter_tags` and `exclude_tags` in the suite YAML:

```yaml
# smoke.yaml — only fast smoke tests
suite:
  name: smoke
  targets: [verify_vm]
  filter_tags: [smoke]

# regression.yaml — everything except slow/flaky
suite:
  name: regression
  targets: [verify_vm, check_data]
  exclude_tags: [slow, flaky]

# e2e.yaml — only end-to-end tests
suite:
  name: e2e
  targets: [verify_vm, check_data]
  filter_tags: [e2e]
```

## Semantics

- **`filter_tags`** — a case is kept if **any** of its operations (including cleanup steps) has at least one of the listed tags. Multiple tags are OR-ed: `filter_tags: [smoke, regression]` matches cases touching either tag.
- **`exclude_tags`** — a case is dropped if **any** of its operations has **any** of the listed tags.
- Both can be combined: `filter_tags: [smoke]` + `exclude_tags: [slow]` runs smoke tests that don't touch slow operations.

Tags are evaluated against all steps in the case, including cleanup steps.

## Multiple Suite Files

A common pattern is to define operations once in a shared module and create separate suite files for different test profiles:

```
tests/
  ops.py              # all operation definitions with tags
  smoke.yaml          # suite: filter_tags: [smoke]
  regression.yaml     # suite: exclude_tags: [slow, flaky]
  e2e.yaml            # suite: filter_tags: [e2e]
```

Run the appropriate suite:

```bash
testweaver run tests/smoke.yaml        # fast smoke check
testweaver run tests/regression.yaml   # full regression
testweaver run tests/e2e.yaml          # end-to-end only
```

## Programmatic API

```python
from testweaver.filtering import filter_cases

ops_by_name = {op.name: op for op in definition.operations}

# Only cases touching smoke-tagged operations
smoke_cases = filter_cases(
    cases, tags=["smoke"], ops_by_name=ops_by_name,
)

# Regression: exclude slow and flaky
regression_cases = filter_cases(
    cases, exclude_tags=["slow", "flaky"], ops_by_name=ops_by_name,
)

# Combined: smoke but no slow ops
subset = filter_cases(
    cases, tags=["smoke"], exclude_tags=["slow"],
    ops_by_name=ops_by_name,
)
```
