# Dry-Run Mode

Use `--dry-run` to preview test execution without running any commands or callables. This is especially useful for large test suites where you want to verify the generated cases and parameter substitution before committing to a long run.

## Basic Dry-Run

```bash
testweaver run my_test.yaml --dry-run
```

Output:

```
Dry-run: 3 test case(s) would be executed

--- check-1 ---
Target: check_file_exists
Params: {'filename': '/tmp/test.txt'}
Steps:
  1. create_file                         run: echo "hello" > $filename  ->  echo "hello" > /tmp/test.txt
  2. check_file_exists                   run: test -f $filename  ->  test -f /tmp/test.txt
Cleanup:
  1. remove_file                         run: rm -f $filename  ->  rm -f /tmp/test.txt
```

## Dry-Run with Filters

All filtering options work with `--dry-run`, so you can preview exactly which subset of cases would run:

```bash
# Preview only fault-injection cases
testweaver run my_test.yaml --dry-run --fault-only

# Preview cases targeting a specific operation
testweaver run my_test.yaml --dry-run -t verify_tpm

# Preview with parameter overrides
testweaver run my_test.yaml --dry-run -p guest_name=prodvm -p timeout=600
```

## Saving Dry-Run Output

Use `-o` to save the preview to a file for review or sharing:

```bash
testweaver run my_test.yaml --dry-run -o execution_plan.txt
```

## Step Display Format

Each step shows the operation name and its action:

| Step Type | Display |
|-----------|---------|
| Shell command (no params) | `run: echo hello` |
| Shell command (with params) | `run: ssh $host cmd  ->  ssh 192.168.1.1 cmd` |
| Python callable | `[callable: my_module.my_function]` |
| Empty/no-op | `[no-op]` |
| Unknown operation | `[unknown operation]` |
