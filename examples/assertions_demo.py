"""Demonstration of TestWeaver's fluent assertion API.

Run: testweaver run examples/assertions_demo.py --format text
"""

import subprocess
import re

from testweaver import (
    action, check, cleanup,
    provides, requires, clears,
    assert_that, assert_raises,
)


@action
@provides('file.exists')
def create_file(params, env):
    """Create a test file and verify the command succeeded."""
    result = subprocess.run(
        'echo "hello world" > /tmp/test.txt',
        shell=True, capture_output=True, text=True,
    )
    assert_that(result.returncode, "create_file exit code").equals(0)


@check
@requires('file.exists')
def check_content(params, env):
    """Verify file content with chained assertions."""
    result = subprocess.run(
        'cat /tmp/test.txt', shell=True, capture_output=True, text=True,
    )
    assert_that(result.returncode).equals(0)
    content = result.stdout.strip()

    # Chained assertions with description
    assert_that(content, "file content") \
        .is_not_none() \
        .equals("hello world") \
        .matches(r"^hello")


@check
@requires('file.exists')
def check_length(params, env):
    """Verify file length with numeric assertions."""
    result = subprocess.run(
        'wc -c < /tmp/test.txt', shell=True, capture_output=True, text=True,
    )
    byte_count = int(result.stdout.strip())
    assert_that(byte_count) \
        .greater_than(0) \
        .less_than(100)


@check
@requires('file.exists')
def check_list_operations(params, env):
    """Verify list/collection assertions."""
    result = subprocess.run(
        'ls /tmp/test.txt', shell=True, capture_output=True, text=True,
    )
    assert_that(result.stdout.strip()).contains('test.txt')
    assert_that("hello world").not_contains('goodbye')


@action
@provides('regex.checked')
def regex_checks(params, env):
    """Demonstrate regex and type assertions."""
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    assert_that(uuid_str).matches(r'^[0-9a-f-]{36}$')
    assert_that(uuid_str).is_instance_of(str)
    assert_that(42).is_instance_of(int)


@action
@provides('exception.checked')
def exception_checks(params, env):
    """Demonstrate assert_raises context manager."""
    # Passes: correct exception
    with assert_raises(ValueError, message="bad"):
        raise ValueError("something bad happened")

    # Passes: regex message match
    with assert_raises(ValueError, message=re.compile(r"code \d+")):
        raise ValueError("error code 42 occurred")

    # Also check the negative case: wrong type is caught
    try:
        with assert_raises(ValueError):
            raise TypeError("wrong type")
    except AssertionError:
        pass  # expected — wrong exception type correctly detected


@cleanup
@requires('file.exists')
@clears('file.exists')
def remove_file(params, env):
    """Remove the test file."""
    result = subprocess.run(
        'rm -f /tmp/test.txt', shell=True, capture_output=True, text=True,
    )
    assert_that(result.returncode, "remove_file exit code").equals(0)
