import subprocess

from testweaver import action, check, cleanup, provides, requires, clears, verify_for


@action
@provides('file.exists')
def create_file(params):
    """Create a hello world file"""
    subprocess.run(
        'echo "hello world" > /tmp/testweaver_hello.txt',
        shell=True, check=True,
    )


@verify_for('create_file')
def check_content(params):
    """Verify file contains hello world"""
    subprocess.run(
        'grep -q "hello world" /tmp/testweaver_hello.txt',
        shell=True, check=True,
    )


@check
@requires('file.exists')
def check_file_exists(params):
    """Verify the file exists"""
    subprocess.run(
        'test -f /tmp/testweaver_hello.txt',
        shell=True, check=True,
    )


@cleanup
@requires('file.exists')
@clears('file.exists')
def remove_file(params):
    """Remove the hello world file"""
    subprocess.run('rm -f /tmp/testweaver_hello.txt', shell=True, check=True)
