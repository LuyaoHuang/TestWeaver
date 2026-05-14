# Test Case Filtering

After generating test cases, use filtering options to run a specific subset. Available on both `generate` and `run`.

## Filter by Case ID

Use `-k` with fnmatch glob patterns to match case IDs:

```bash
# Run only cases whose ID starts with "check-"
testweaver run my_test.yaml -k "check-*"

# Multiple patterns — matches any (OR)
testweaver run my_test.yaml -k "check-1" -k "verify-*"

# Preview which cases match
testweaver generate my_test.yaml -k "fault-*" --format text
```

## Filter by Target Operation

Use `-t` / `--target` to keep only cases for specific targets:

```bash
testweaver run examples/virt/vtpm_test.yaml -t verify_tpm
testweaver generate my_test.yaml -t check_file_exists -t check_permissions
```

## Filter by Step Presence

Use `--has-step` to keep cases that include a specific operation in their step sequence:

```bash
# Only cases that go through install_swtpm
testweaver run examples/virt/vtpm_test.yaml --has-step install_swtpm
```

## Filter Fault Cases

```bash
# Only fault-injection cases
testweaver run my_test.yaml --fault-only

# Exclude fault-injection cases
testweaver run my_test.yaml --no-fault
```

## Combining Filters

All filter types are AND-combined. Within each repeatable option, matching is OR:

```bash
# check-* cases that are NOT faults
testweaver run my_test.yaml -k "check-*" --no-fault

# Cases targeting verify_tpm that contain the install_swtpm step
testweaver run examples/virt/vtpm_test.yaml -t verify_tpm --has-step install_swtpm
```

## Programmatic API

```python
from testweaver.filtering import filter_cases
from testweaver.graph import generate_cases

cases = generate_cases(definition)

# Filter by ID pattern
subset = filter_cases(cases, ids=["check-*"])

# Filter by target and exclude faults
subset = filter_cases(cases, targets=["verify_tpm"], no_fault=True)

# Filter by parameter values
subset = filter_cases(cases, params={"tpm_backend": "emulator"})

# Combine multiple criteria (AND)
subset = filter_cases(
    cases,
    ids=["check-*"],
    steps=["install_swtpm"],
    no_fault=True,
)
```
