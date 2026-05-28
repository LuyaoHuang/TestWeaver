# Fluent Assertions

## Basic Assertions

```python
from testweaver import action, check, assert_that

@action
@provides('data.ready')
def prepare_data(params, env):
    result = {"status": "ok", "count": 5}
    assert_that(result["status"]).equals("ok")
    assert_that(result["count"]).greater_than(0)

@check
@requires('data.ready')
def verify_data(params, env):
    items = ["a", "b", "c"]
    assert_that(items).has_length(3).contains("b").not_contains("z")
```

## Chaining

Assertions return `self`, so you can chain multiple checks. Execution stops at the first failure:

```python
assert_that(result).is_not_none().has_length(3).contains("key")
```

## Describing Assertions

Use `described_as()` or the second argument to `assert_that` to add context:

```python
# Via constructor argument
assert_that(vm_ip, "VM IP address").matches(r'^\d+\.\d+\.\d+\.\d+$')

# Via .described_as()
assert_that(response.code).described_as("HTTP status").equals(200)
```

## Type and Regex Checks

```python
assert_that(value).is_instance_of(str)
assert_that("abc123").matches(r"^\w+\d+$")
assert_that(error_msg).matches(re.compile(r"error \d+", re.IGNORECASE))
```

## assert_raises

Use `assert_raises` as a context manager to verify that expected exceptions are raised:

```python
from testweaver import assert_raises

# Passes: ValueError is raised
with assert_raises(ValueError):
    raise ValueError("bad input")

# Passes: message substring matches
with assert_raises(ValueError, message="bad"):
    raise ValueError("something bad happened")

# Passes: regex message match
with assert_raises(ValueError, message=re.compile(r"code \d+")):
    raise ValueError("error code 42")

# Fails: no exception raised
with assert_raises(ValueError):
    pass  # AssertionError: expected ValueError but no exception was raised

# Fails: wrong exception type
with assert_raises(ValueError):
    raise TypeError("wrong")  # AssertionError: expected ValueError, got TypeError
```

## Failure Output

When an assertion fails, the engine captures a diff showing expected vs actual:

```
VM IP address
  expected: matches /\d+\.\d+\.\d+\.\d+/
    actual: 'not-an-ip'
```

This appears in `StepResult.error` and is included in JSON, JUnit, TAP, and HTML reports.

## Full Reference

| Method | Passes when |
|--------|-------------|
| `.equals(expected)` | `actual == expected` |
| `.not_equals(expected)` | `actual != expected` |
| `.is_true()` | `bool(actual)` is True |
| `.is_false()` | `bool(actual)` is False |
| `.is_none()` | `actual is None` |
| `.is_not_none()` | `actual is not None` |
| `.greater_than(n)` | `actual > n` (numeric) |
| `.greater_than_or_equal_to(n)` | `actual >= n` (numeric) |
| `.less_than(n)` | `actual < n` (numeric) |
| `.less_than_or_equal_to(n)` | `actual <= n` (numeric) |
| `.contains(item)` | `item in actual` |
| `.not_contains(item)` | `item not in actual` |
| `.has_length(n)` | `len(actual) == n` |
| `.is_instance_of(cls)` | `isinstance(actual, cls)` |
| `.matches(pattern)` | `pattern.search(actual)` succeeds (string actual) |
| `.described_as(label)` | Attach a label for clearer failure messages |
| `assert_raises(Exc, message=None)` | Context manager — Exc is raised, optionally matching message |
