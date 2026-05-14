# Getting Started

This tutorial walks you through building your first TestWeaver test suite, step by step.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## Step 1: Your First Operation

Create a file called `my_ops.py`:

```python
from testweaver import action, check, cleanup, provides, requires, clears

@action
@provides('file.exists')
def create_file(params):
    """Create a test file"""
    import subprocess
    subprocess.run('echo "hello world" > /tmp/test.txt', shell=True, check=True)

@check
@requires('file.exists')
def check_file(params):
    """Verify the file exists"""
    import subprocess
    subprocess.run('test -f /tmp/test.txt', shell=True, check=True)

@cleanup
@requires('file.exists')
@clears('file.exists')
def remove_file(params):
    """Remove the test file"""
    import subprocess
    subprocess.run('rm -f /tmp/test.txt', shell=True, check=True)
```

What's happening here:
- `@action` + `@provides('file.exists')` — `create_file` is an action that creates the state `file.exists`
- `@check` + `@requires('file.exists')` — `check_file` is a verification target that needs `file.exists` to be active
- `@cleanup` + `@requires('file.exists')` + `@clears('file.exists')` — `remove_file` tears down the state

Run it directly:

```bash
testweaver run my_ops.py --format text
```

TestWeaver automatically builds a dependency graph, finds the path from empty state to `check_file`, and generates a test case: `create_file -> check_file -> remove_file`.

## Step 2: Multiple Paths

Add a second way to create the file:

```python
@action
@provides('file.exists')
def create_file_alt(params):
    """Create the file using Python"""
    with open('/tmp/test.txt', 'w') as f:
        f.write('hello world')
```

Now run `testweaver generate my_ops.py --format text` — you'll see **two** test cases: one through `create_file` and one through `create_file_alt`. TestWeaver automatically discovered both paths to reach `check_file`.

## Step 3: Add Verification

Attach a verify callback to `create_file` so the content is checked immediately after creation:

```python
from testweaver import verify_for

@verify_for('create_file')
def check_content(params):
    """Runs automatically after create_file succeeds"""
    import subprocess
    subprocess.run('grep -q "hello world" /tmp/test.txt', shell=True, check=True)
```

The verify function runs right after `create_file` — no graph node needed, no extra test case generated. It just validates the operation did its job.

## Step 4: Use a YAML Definition

Instead of running the Python file directly, create a YAML file to configure the suite:

```yaml
# my_test.yaml
modules:
  - my_ops.py

suite:
  name: "File Operations"
  targets: [check_file]
  cleanup: true
  params:
    filename: /tmp/test.txt
```

```bash
testweaver validate my_test.yaml    # Check for errors
testweaver generate my_test.yaml    # Preview test cases (JSON)
testweaver run my_test.yaml --format text  # Run with human-readable output
```

## Step 5: YAML-Only Mode

For simple shell-command tests, skip Python entirely:

```yaml
# simple_test.yaml
operations:
  - name: create_file
    type: action
    provides: [file.exists]
    run: echo "hello world" > /tmp/test.txt
    verify: grep -q "hello world" /tmp/test.txt

  - name: check_file
    type: check
    requires: [file.exists]
    run: test -f /tmp/test.txt

  - name: remove_file
    type: cleanup
    requires: [file.exists]
    clears: [file.exists]
    run: rm -f /tmp/test.txt

suite:
  name: "Simple File Test"
  targets: [check_file]
  cleanup: true
```

```bash
testweaver run simple_test.yaml --format text
```

## Step 6: Add Parameters

Make the filename configurable:

```yaml
suite:
  name: "File Operations"
  targets: [check_file]
  cleanup: true
  params:
    filename: /tmp/test.txt

operations:
  - name: create_file
    type: action
    provides: [file.exists]
    run: echo "hello world" > $filename

  - name: check_file
    type: check
    requires: [file.exists]
    run: test -f $filename

  - name: remove_file
    type: cleanup
    requires: [file.exists]
    clears: [file.exists]
    run: rm -f $filename
```

Override from the command line:

```bash
testweaver run simple_test.yaml -p filename=/tmp/other.txt --format text
```

## Step 7: Visualize the Graph

See the dependency graph to understand what TestWeaver built:

```bash
testweaver graph my_test.yaml --format text     # Text summary
testweaver graph my_test.yaml --format mermaid  # Mermaid diagram
testweaver graph my_test.yaml --format dot | dot -Tpng -o graph.png  # Image
```

## What's Next

- [Core Concepts](concepts.md) — operations, states, the dependency graph, and how TestWeaver generates test cases
- [CLI Reference](cli-reference.md) — all commands and flags
- [Examples](examples/) — detailed examples for every feature:
  - [Parameters](examples/parameters.md) — parameter graph and matrix
  - [Multi-Instance](examples/multi-instance.md) — multiple devices with independent states
  - [Graph Modifiers](examples/graph-modifiers.md) — runtime execution control
  - [Filtering](examples/filtering.md) — run specific subsets of cases
  - [Reporting](examples/reporting.md) — JUnit XML, TAP, HTML output
