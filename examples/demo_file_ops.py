"""
Simple File Operations Demo
============================
Shows the basic value proposition of dependency-based test generation.

3 ways to create a file, 1 test to read it, 1 cleanup.
Framework automatically generates 3 complete test cases.
"""
import os

from testweaver import action, check, cleanup, provides, requires, excludes, clears


@action
@provides('file.exists')
@excludes('file.exists')
def create_file_with_echo(params, env):
    """Create file using shell echo."""
    file_path = params.get('file_path', '/tmp/tw_test.txt')
    os.system(f'echo "Created by echo" > {file_path}')


@action
@provides('file.exists')
@excludes('file.exists')
def create_file_with_python(params, env):
    """Create file using Python open()."""
    file_path = params.get('file_path', '/tmp/tw_test.txt')
    with open(file_path, 'w') as f:
        f.write("Created by Python")


@action
@provides('file.exists')
@excludes('file.exists')
def create_file_with_touch(params, env):
    """Create file using touch command."""
    file_path = params.get('file_path', '/tmp/tw_test.txt')
    os.system(f'touch {file_path}')
    with open(file_path, 'w') as f:
        f.write("Created by touch")


@check
@requires('file.exists')
def test_read_file(params, env):
    """Verify we can read the file."""
    file_path = params.get('file_path', '/tmp/tw_test.txt')
    with open(file_path, 'r') as f:
        content = f.read()
    assert content, "File should not be empty"


@cleanup
@requires('file.exists')
@clears('file.exists')
def remove_file(params, env):
    """Remove the test file."""
    file_path = params.get('file_path', '/tmp/tw_test.txt')
    os.remove(file_path)
