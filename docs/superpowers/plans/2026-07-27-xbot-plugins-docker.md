# xbot.plugins.docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `xbot.plugins.docker` as an SSH-shaped library for executing commands and transferring files through a remote TCP/TLS Docker daemon.

**Architecture:** A single `DockerConnection` owns one Docker client and one target container. Its public command-result, expectation, directory-context, path, transfer, logging, packaging, test, demo, and README conventions mirror `xbot.plugins.ssh`, while command execution and archive transfer use Docker SDK APIs.

**Tech Stack:** Python 3.10+, Docker SDK for Python, xbot.framework, unittest, doctest, setuptools/PEP 621, mypy, build, twine.

## Global Constraints

- Work only in `/Users/zhaowcheng/Code/xbot/xbot.plugins.docker`.
- Keep `/Users/zhaowcheng/Code/xbot/xbot.plugins.ssh` and `/Users/zhaowcheng/Code/xflow/xflow.framework` read-only references.
- Python support is exactly `>=3.10`.
- Runtime dependencies are `xbot.framework>=0.5.1` and `docker`.
- `xbot.plugins.docker.version.__version__` is the only version source; initial version is `0.1.0`.
- Public imports use `xbot.plugins.docker`; do not depend on `xbot.plugins.ssh` or `xflow.framework`.
- Support only remote Docker TCP/TLS. Do not add Unix socket or SSH-context support.
- `container` and `image` are mutually exclusive and exactly one is required.
- Existing containers must already be running and must never be started, stopped, or removed.
- Image connections create a container in `connect()` and remove it with `force=True` in `disconnect()`.
- Do not check whether an image-created container remains running.
- Do not automatically pull images.
- Execute string commands through `['/bin/sh', '-c', command]`.
- Keep `expect`, `timeout`, and `shenvs`; do not implement `prompts`, `sudo()`, or `open()`.
- Keep one `DockerConnection` for both command and file operations.
- Every test, including unit tests, doctests, and real Docker tests, is run by `tests/run.py`.
- README files contain only Introduction, Installation, Get Started, and Demo sections.
- Python docstrings use multi-line triple-quoted form and document parameters and returns with `:param` and `:return`.
- Use single quotes for Python strings by default.
- Put all imports at file scope.
- Split a function signature to one parameter per line when the full signature exceeds 80 characters.
- Run commands below from `/Users/zhaowcheng/Code/xbot/xbot.plugins.docker`.
- Before executing the test steps, set `DOCKER_TEST_HOST`, `DOCKER_TEST_PORT`, and `DOCKER_TEST_IMAGE` to a reachable remote daemon and an image already present there. Set `DOCKER_TEST_CACERT`, `DOCKER_TEST_CLIENTCERT`, and `DOCKER_TEST_CLIENTKEY` when TLS certificates are required.

## File Map

- `.gitignore`: ignore Python, editor, build, virtual-environment, test-project, and macOS generated files.
- `LICENSE`: BSD-2-Clause license aligned with the SSH project.
- `README.md`: English four-section user guide.
- `README.zh.md`: Chinese four-section user guide matching `README.md`.
- `pyproject.toml`: PEP 621 metadata, dependencies, dynamic version, package discovery, and `py.typed`.
- `setup.py`: README build hook aligned with the SSH project.
- `xbot/plugins/docker/__init__.py`: namespace package marker only.
- `xbot/plugins/docker/version.py`: authoritative `__version__`.
- `xbot/plugins/docker/errors.py`: `DockerConnectError` and `DockerCommandError`.
- `xbot/plugins/docker/utils.py`: ANSI and unprintable-character cleanup.
- `xbot/plugins/docker/docker.py`: `DockerCommandResult` and the unified `DockerConnection`.
- `xbot/plugins/docker/py.typed`: PEP 561 marker.
- `tests/__init__.py`: test package marker.
- `tests/run.py`: the only test runner; parses Docker endpoint arguments, configures integration tests, discovers every test, and returns a truthful exit status.
- `tests/test_utils.py`: utility doctest registration.
- `tests/test_docker.py`: result, lifecycle, command, transfer, mocked, doctest, and real Docker tests.
- `demo/README.md`: demo execution instructions matching the SSH demo layout.
- `demo/lib/__init__.py`: demo package marker.
- `demo/lib/testbed.py`: cached Docker connections for xbot.framework.
- `demo/lib/testcase.py`: typed demo TestCase base.
- `demo/testbeds/mytestbed.yml`: remote Docker and target configuration.
- `demo/testcases/__init__.py`: demo testcase package marker.
- `demo/testcases/tc_docker.py`: command and transfer demonstration.
- `demo/testsets/mytestset.yml`: demo testcase paths and tags.
- `docs/.gitkeep`: retain the documentation directory.

---

### Task 1: Package Foundation, Test Runner, Utilities, and Command Result

**Files:**
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `README.zh.md`
- Create: `pyproject.toml`
- Create: `setup.py`
- Create: `xbot/plugins/docker/__init__.py`
- Create: `xbot/plugins/docker/version.py`
- Create: `xbot/plugins/docker/errors.py`
- Create: `xbot/plugins/docker/utils.py`
- Create: `xbot/plugins/docker/docker.py`
- Create: `xbot/plugins/docker/py.typed`
- Create: `tests/__init__.py`
- Create: `tests/run.py`
- Create: `tests/test_utils.py`
- Create: `tests/test_docker.py`

**Interfaces:**
- Consumes: `xbot.framework.logger.getlogger`, `xbot.framework.logger.ExtraAdapter`.
- Produces: `DockerConnectError`, `DockerCommandError`, `remove_ansi_escape_chars(str) -> str`, `remove_unprintable_chars(str) -> str`, and `DockerCommandResult(str)`.
- Produces test configuration fields in `tests.test_docker`: `HOST`, `PORT`, `IMAGE`, `CACERT`, `CLIENTCERT`, and `CLIENTKEY`.

- [ ] **Step 1: Create package metadata and the authoritative version**

Create `xbot/plugins/docker/version.py`:

```python
"""
Package version.
"""

__version__: str = '0.1.0'
```

Create `pyproject.toml` with these exact metadata values:

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "xbot.plugins.docker"
description = "Docker library for xbot.framework"
authors = [
    { name = "zhaowcheng", email = "zhaowcheng@163.com" },
]
license = "BSD-2-Clause"
license-files = ["LICENSE"]
requires-python = ">=3.10"
dependencies = [
    "xbot.framework>=0.5.1",
    "docker",
]
classifiers = [
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dynamic = ["version", "readme"]

[project.urls]
Homepage = "https://github.com/zhaowcheng/xbot.plugins.docker"
Issues = "https://github.com/zhaowcheng/xbot.plugins.docker/issues"

[tool.setuptools.dynamic]
version = { attr = "xbot.plugins.docker.version.__version__" }

[tool.setuptools.packages.find]
include = ["xbot.plugins.docker*", "tests*"]

[tool.setuptools.package-data]
"xbot.plugins.docker" = ["py.typed"]
```

Create `setup.py` with the same README composition behavior as SSH, changing
only the package path and fallback version to `0.1.0`:

```python
"""
Setuptools build hook.
"""

import re

from setuptools import setup


def _build_long_description() -> str:
    """
    Build the bilingual package description.

    :return: Combined Markdown description.
    """
    parts = []
    for readme in ('README.md', 'README.zh.md'):
        with open(readme, encoding='utf8') as readme_file:
            parts.append(''.join(readme_file.readlines()[6:]))
    description = '\n***\n\n'.join(parts)
    with open(
        'xbot/plugins/docker/version.py',
        encoding='utf8',
    ) as version_file:
        match = re.search(
            r"__version__[^'\"\\]+['\"]([^'\"]+)",
            version_file.read(),
        )
        version = match.group(1) if match else '0.1.0'
    return description.replace(
        '/tree/master/',
        f'/tree/v{version}/',
    )


setup(
    long_description=_build_long_description(),
    long_description_content_type='text/markdown',
)
```

Create the two README files immediately with their final language switcher and
four headings. Use a one-paragraph introduction, the final
`pip install xbot.plugins.docker` command, a minimal import example, and the
demo link. Task 6 replaces the minimal import example with the complete API
example without adding headings.

Create `.gitignore` with:

```gitignore
__pycache__/
*.py[cod]
*$py.class
.vscode/*
.idea/*
.worktrees/
build/
*.egg-info/
dist/
venv/
testproj/
.DS_Store
```

Create `LICENSE` with the exact BSD 2-Clause text and copyright line from
`/Users/zhaowcheng/Code/xbot/xbot.plugins.ssh/LICENSE`.

Install the working tree after these files exist:

```bash
python -m pip install -e .
```

- [ ] **Step 2: Write failing utility and result tests**

Create `tests/test_utils.py` with doctest registration for
`xbot.plugins.docker.utils`.

In `tests/test_docker.py`, import
`from xbot.plugins.docker import docker` at file scope and register the module
doctests:

```python
def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    ignore: str | None,
) -> unittest.TestSuite:
    """
    Add Docker module doctests.

    :param loader: Unittest loader.
    :param tests: Discovered test suite.
    :param ignore: Unused discovery pattern.
    :return: Test suite with doctests.
    """
    tests.addTests(doctest.DocTestSuite(docker))
    return tests
```

Create these tests in `tests/test_docker.py`:

```python
import unittest

from xbot.plugins.docker.docker import DockerCommandResult


class TestDockerCommandResult(unittest.TestCase):
    """
    Test Docker command results.
    """

    def test_result_is_clean_string_with_metadata(self) -> None:
        """
        Test output cleanup and metadata.

        :return: None.
        """
        result = DockerCommandResult(
            '\x1b[31mjack 20\x1b[0m\r\n'
            'tom 30\xe9\n',
            rc=7,
            cmd='show users',
        )

        self.assertEqual(str(result), 'jack 20\ntom 30')
        self.assertEqual(result.rc, 7)
        self.assertEqual(result.cmd, 'show users')

    def test_result_field_and_column_helpers(self) -> None:
        """
        Test field and column extraction.

        :return: None.
        """
        result = DockerCommandResult('jack 20\ntom 30')

        self.assertEqual(result.getfield('tom', 2), '30')
        self.assertEqual(result.getfield(1, 1), 'jack')
        self.assertEqual(result.getcol(2), ['20', '30'])
```

- [ ] **Step 3: Create the only test runner and verify the tests fail**

Create `tests/run.py` with file-scope imports, required `--host` and `--image`,
port default `2375`, optional TLS arguments, module-level integration
configuration, unittest discovery, and truthful exit status:

```python
"""
Run all tests.
"""

import argparse
import unittest

from pathlib import Path

import test_docker


def create_parser() -> argparse.ArgumentParser:
    """
    Create the test argument parser.

    :return: Argument parser.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', required=True)
    parser.add_argument('-P', '--port', type=int, default=2375)
    parser.add_argument('-i', '--image', required=True)
    parser.add_argument('--cacert')
    parser.add_argument('--clientcert')
    parser.add_argument('--clientkey')
    return parser


def configure_integration_tests(args: argparse.Namespace) -> None:
    """
    Configure real Docker tests.

    :param args: Parsed command-line arguments.
    :return: None.
    """
    test_docker.HOST = args.host
    test_docker.PORT = args.port
    test_docker.IMAGE = args.image
    test_docker.CACERT = args.cacert
    test_docker.CLIENTCERT = args.clientcert
    test_docker.CLIENTKEY = args.clientkey


def main() -> int:
    """
    Run every unit, doctest, and integration test.

    :return: Process exit status.
    """
    args = create_parser().parse_args()
    configure_integration_tests(args)
    startdir = Path(__file__).parent
    suite = unittest.TestLoader().discover(startdir)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
```

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: FAIL because `DockerCommandResult` and utility functions do not yet
exist.

- [ ] **Step 4: Implement exceptions, utilities, and `DockerCommandResult`**

Create `errors.py` with empty `DockerConnectError(Exception)` and
`DockerCommandError(Exception)` classes using multi-line docstrings.

Implement `utils.py` by porting the two focused SSH functions with type
annotations and doctests:

```python
def remove_ansi_escape_chars(s: str) -> str:
    """
    Remove ANSI escape characters from a string.

    :param s: Input string.
    :return: String without ANSI escapes.
    """
    escapes = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return escapes.sub('', s)


def remove_unprintable_chars(s: str) -> str:
    """
    Remove unprintable characters from a string.

    :param s: Input string.
    :return: Printable string.
    """
    return ''.join(char for char in s if char in string.printable)
```

Implement `DockerCommandResult` as a `str` subclass with private `__rc` and
`__cmd`, read-only properties, and the same one-based `getfield()` and
`getcol()` semantics as `SSHCommandResult`.

- [ ] **Step 5: Run all tests and commit**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: every currently discovered test and doctest passes.

Commit:

```bash
git add .gitignore LICENSE README.md README.zh.md pyproject.toml setup.py \
  xbot tests
git commit -m 'feat: add docker plugin foundation'
```

---

### Task 2: Remote Docker Connection and Container Ownership

**Files:**
- Modify: `xbot/plugins/docker/docker.py`
- Modify: `tests/test_docker.py`

**Interfaces:**
- Consumes: `DockerConnectError`.
- Produces: `DockerConnection(shenvs: dict[str, str] | None = None)`.
- Produces: `DockerConnection.connect(host, container=None, image=None, port=2375, user=None, runargs=None, timeout=5, cacert=None, clientcert=None, clientkey=None) -> None`.
- Produces: `DockerConnection.disconnect() -> None`.

- [ ] **Step 1: Write failing validation and lifecycle tests**

Add mocked tests covering these exact cases:

```python
def test_connect_requires_exactly_one_target(self) -> None:
    conn = DockerConnection()
    with self.assertRaisesRegex(ValueError, 'only one'):
        conn.connect('127.0.0.1')
    with self.assertRaisesRegex(ValueError, 'only one'):
        conn.connect(
            '127.0.0.1',
            container='existing',
            image='alpine:latest',
        )


def test_client_certificate_and_key_must_be_paired(self) -> None:
    conn = DockerConnection()
    with self.assertRaisesRegex(ValueError, 'clientcert'):
        conn.connect(
            '127.0.0.1',
            container='existing',
            clientcert='cert.pem',
        )


def test_existing_stopped_container_is_rejected(self) -> None:
    container = self.client.containers.get.return_value
    container.status = 'exited'

    with self.assertRaises(DockerConnectError):
        self.conn.connect('127.0.0.1', container='existing')

    container.start.assert_not_called()
    self.client.close.assert_called_once_with()


def test_disconnect_removes_only_image_container(self) -> None:
    self.conn.connect(
        '127.0.0.1',
        image='alpine:latest',
        runargs={'command': 'sleep 60'},
    )
    created = self.client.containers.run.return_value

    self.conn.disconnect()

    created.remove.assert_called_once_with(force=True)
    self.client.close.assert_called_once_with()
```

Use `unittest.mock.patch('xbot.plugins.docker.docker.DockerClient')` in
`setUp()` and configure `containers.get()` and `containers.run()` return
objects with explicit `status`, `name`, and `id` values.

Also test:

- command and file methods called before `connect()` raise
  `DockerConnectError('Docker connection is not open.')`;
- a second `connect()` call performs no Docker API call;
- a second `disconnect()` call performs no Docker API call;
- an image connection never calls `images.pull()` or checks container status;
- an existing-container disconnect never calls `remove()`, `stop()`, or
  `start()`;
- a Docker SDK lookup or create failure becomes `DockerConnectError` and
  closes the client;
- a temporary-container removal error is re-raised only after `client.close()`;
- logger prefixes distinguish
  `docker://user@host:port/container` and
  `docker://user@host:port/image->created-container`.

- [ ] **Step 2: Run all tests to verify the new tests fail**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: FAIL because `DockerConnection` does not exist.

- [ ] **Step 3: Implement connection setup**

Add fields for logger, default environment, client, container, target source,
user, working directory, and a `threading.Lock`. Do not use mutable default
arguments.

Implement TLS construction:

```python
def _create_tls_config(
    cacert: str | None,
    clientcert: str | None,
    clientkey: str | None,
) -> TLSConfig | bool:
    """
    Create Docker TLS configuration.

    :param cacert: CA certificate path.
    :param clientcert: Client certificate path.
    :param clientkey: Client private-key path.
    :return: TLS configuration or False.
    """
    if not cacert and not clientcert:
        return False
    return TLSConfig(
        ca_cert=cacert,
        verify=bool(cacert),
        client_cert=(
            (clientcert, clientkey)
            if clientcert and clientkey
            else None
        ),
    )
```

In `connect()`, validate arguments before creating a client. Create
`DockerClient(base_url=f'tcp://{host}:{port}', tls=tls, timeout=timeout)`.
Use truth-value pairing for certificate paths:
`bool(clientcert) != bool(clientkey)`, so the empty strings passed by the
canonical test command behave as omitted values.
Call `containers.get(container)` for existing targets and reject any status
other than `running`. Call
`containers.run(image, detach=True, **(runargs or {}))` for image targets
without checking the resulting status.

Catch Docker SDK connection, lookup, TLS, and create failures, close the
newly created client, and raise `DockerConnectError(str(error)) from None`.
Do not translate caller `ValueError` validation failures.

Add private typed accessors for the client and container. Each accessor raises
`DockerConnectError('Docker connection is not open.')` when its resource is
absent; every command and file method uses these accessors instead of relying
on `None` attribute failures.

- [ ] **Step 4: Implement idempotent disconnect**

Use a saved removal exception so client closure cannot mask it:

```python
def disconnect(self) -> None:
    """
    Close the Docker connection.

    :return: None.
    """
    if self._dockerclient is None:
        return
    removal_error: Exception | None = None
    try:
        if self._temporary and self._container is not None:
            self._container.remove(force=True)
    except DockerException as error:
        removal_error = error
    try:
        self._dockerclient.close()
    finally:
        self._dockerclient = None
        self._container = None
        self._temporary = False
        self._uid = None
        self._gid = None
    if removal_error is not None:
        raise removal_error
```

Import `DockerException` at file scope. Do not catch `BaseException`.

- [ ] **Step 5: Run all tests and commit**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: every current test passes; mocked image connection confirms
`detach=True` and unchanged `runargs`, and mocked existing connection confirms
no lifecycle mutation.

Commit:

```bash
git add xbot/plugins/docker/docker.py tests/test_docker.py
git commit -m 'feat: add docker connection lifecycle'
```

---

### Task 3: Command Execution, Expectations, Timeout, and `cd()`

**Files:**
- Modify: `xbot/plugins/docker/docker.py`
- Modify: `tests/test_docker.py`

**Interfaces:**
- Consumes: connected `DockerClient`, `Container`, `DockerCommandResult`, and `DockerCommandError`.
- Produces: `DockerConnection.exec(cmd, expect=0, timeout=15, shenvs=None) -> DockerCommandResult`.
- Produces: `DockerConnection.cd(path: str) -> Generator[None, None, None]`.

- [ ] **Step 1: Write failing command tests**

Mock the low-level Docker client API and add tests for:

```python
def test_exec_uses_shell_user_and_merged_environment(self) -> None:
    self.conn = self.create_connected_connection(
        shenvs={'LANG': 'C.UTF-8', 'BASE': 'one'},
        user='xbot',
    )
    self.configure_exec(output=b'hello\n', rc=0)

    result = self.conn.exec(
        'echo hello',
        shenvs={'BASE': 'two', 'EXTRA': 'three'},
    )

    self.client.api.exec_create.assert_called_once_with(
        self.container.id,
        ['/bin/sh', '-c', 'echo hello'],
        stdout=True,
        stderr=True,
        stdin=False,
        tty=True,
        environment={
            'LANG': 'C.UTF-8',
            'LANGUAGE': 'en_US.UTF-8',
            'BASE': 'two',
            'EXTRA': 'three',
        },
        user='xbot',
    )
    self.assertEqual(result, 'hello')
    self.assertEqual(result.rc, 0)
    self.assertEqual(result.cmd, 'echo hello')


def test_expect_supports_rc_string_and_none(self) -> None:
    self.configure_exec(output=b'not found\n', rc=2)
    self.conn.exec('ls /missing', expect=2)
    self.configure_exec(output=b'hello\n', rc=7)
    self.conn.exec('echo hello', expect='hello')
    self.configure_exec(output=b'failed\n', rc=9)
    self.conn.exec('false', expect=None)


def test_expect_mismatch_raises_command_error(self) -> None:
    self.configure_exec(output=b'hello\n', rc=1)
    with self.assertRaises(DockerCommandError) as context:
        self.conn.exec('echo hello')
    self.assertIn('Command: echo hello', str(context.exception))
    self.assertIn('Expect: 0', str(context.exception))
    self.assertIn('ReturnCode: 1', str(context.exception))


def test_cd_prefixes_command_and_restores_directory(self) -> None:
    self.configure_exec(output=b'/tmp\n', rc=0)
    with self.conn.cd('/tmp'):
        result = self.conn.exec('pwd')
    self.assertEqual(result.cmd, "cd /tmp && pwd")
    self.assertEqual(self.conn._cwd, '')
```

Add a timeout test using a mocked socket that never becomes readable and
`unittest.mock.patch('xbot.plugins.docker.docker.select', return_value=([], [], []))`.

- [ ] **Step 2: Run all tests to verify failures**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: FAIL because `exec()` and `cd()` are not implemented.

- [ ] **Step 3: Implement Docker exec streaming**

Build the effective command, quoting the `cd()` path with `shlex.quote()`.
Create the exec instance with the exact options asserted above. Start it with
`exec_start(exec_id, tty=True, socket=True)`.

Read in a loop using `time.monotonic()` and `select([socket], [], [], 0.1)`.
Decode with the charset suffix from `LANG`, falling back to UTF-8 when no
suffix exists. Close the socket in all paths. On timeout, create a partial
`DockerCommandResult` with `rc=-1`, attach it to the logger hook, and raise:

```python
raise TimeoutError(
    f"Command '{effective_cmd}' timedout({timeout}s):\n{result}"
)
```

After EOF, read `ExitCode` from `exec_inspect(exec_id)`, build
`DockerCommandResult`, and apply the three `expect` modes exactly as specified.

- [ ] **Step 4: Implement locked directory context**

Implement `cd()` with `@contextmanager`, the connection's lock, and a `finally`
block that resets `_cwd`:

```python
@contextmanager
def cd(self, path: str) -> Generator[None, None, None]:
    """
    Change the working directory for commands in the context.

    :param path: Container working directory.
    :return: Context manager iterator.
    """
    self._cdlock.acquire()
    try:
        self._cwd = path
        yield
    finally:
        self._cwd = ''
        self._cdlock.release()
```

- [ ] **Step 5: Run all tests and commit**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: every test passes, including timeout, cleanup, command metadata, all
expectation modes, environment override, shell selection, and directory reset.

Commit:

```bash
git add xbot/plugins/docker/docker.py tests/test_docker.py
git commit -m 'feat: execute commands in docker containers'
```

---

### Task 4: Archive-Based File and Directory Transfer

**Files:**
- Modify: `xbot/plugins/docker/docker.py`
- Modify: `tests/test_docker.py`

**Interfaces:**
- Consumes: `DockerConnection.exec()` and the connected `Container`.
- Produces: `join()`, `normpath()`, `basename()`, `exists()`, `makedirs()`, `getfile()`, `putfile()`, `getdir()`, and `putdir()`.

- [ ] **Step 1: Write failing path and archive tests**

Add pure path tests:

```python
def test_posix_path_helpers(self) -> None:
    self.assertEqual(self.conn.join('/tmp', 'a', 'file'), '/tmp/a/file')
    self.assertEqual(self.conn.normpath('/tmp/a/../b/'), '/tmp/b')
    self.assertEqual(self.conn.basename('/tmp/b/file'), 'file')
```

Use temporary local directories and mocked `get_archive()`/`put_archive()` to
assert:

- `getfile('/tmp/source', local_dir)` creates `local_dir/source`;
- download rename creates `local_dir/renamed`;
- `getdir('/tmp/tree', local_dir)` creates `local_dir/tree`;
- `putfile(local_file, '/tmp')` archives the file under its basename;
- upload rename uses the requested archive name;
- `putdir(local_tree, '/tmp')` archives the top directory under its basename;
- every uploaded tar member receives the cached container UID and GID;
- `put_archive()` receives an existing destination directory.

Inspect uploaded tar data in tests:

```python
stream = self.container.put_archive.call_args.args[1]
stream.seek(0)
with tarfile.open(fileobj=stream, mode='r') as archive:
    members = archive.getmembers()
self.assertEqual(members[0].name, 'renamed')
self.assertTrue(all(member.uid == 1000 for member in members))
self.assertTrue(all(member.gid == 1000 for member in members))
```

- [ ] **Step 2: Run all tests to verify failures**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: FAIL because file and path methods do not exist.

- [ ] **Step 3: Implement POSIX path and remote filesystem helpers**

Use `posixpath.join`, `posixpath.normpath`, and `posixpath.basename`.

Implement `exists()` without triggering expectation errors:

```python
def exists(self, path: str) -> bool:
    """
    Check whether a container path exists.

    :param path: Container path.
    :return: True when the path exists.
    """
    result = self.exec(
        f'test -e {shlex.quote(path)}',
        expect=None,
    )
    return result.rc == 0
```

Implement `makedirs()` with `mkdir -p --` and `shlex.quote()`.

Implement `_get_owner()` by executing `id -u` and `id -g` once per connection,
converting both results to integers, and caching them in `_uid` and `_gid`.

- [ ] **Step 4: Implement download methods**

For `getfile()`, collect `get_archive()` chunks into `io.BytesIO`, extract the
single top-level member into `ldir`, and rename it when `filename` is supplied.
For `getdir()`, extract the archive into `ldir` without stripping the remote
directory basename.

Ensure the caller-provided local destination directory must already exist,
matching `SFTPConnection.getfile()` behavior. Let `FileNotFoundError` and
Docker API exceptions propagate unchanged.

- [ ] **Step 5: Implement upload methods**

For `putfile()`, create an in-memory uncompressed tar with arcname equal to
`filename` or the local basename. For `putdir()`, add the directory recursively
with its basename as the top-level arcname.

Use a tar filter for every uploaded member:

```python
def set_owner(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    """
    Set archive ownership.

    :param tarinfo: Archive member metadata.
    :return: Updated archive member metadata.
    """
    tarinfo.uid = uid
    tarinfo.gid = gid
    return tarinfo
```

Call `makedirs(rdir)` only when `exists(rdir)` is false, rewind the stream, and
call `container.put_archive(rdir, stream)`.

- [ ] **Step 6: Run all tests and commit**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: every test passes, including filenames, directory basenames, POSIX
normalization, ownership, destination creation, and error propagation.

Commit:

```bash
git add xbot/plugins/docker/docker.py tests/test_docker.py
git commit -m 'feat: transfer docker container files'
```

---

### Task 5: Real Remote Docker Integration and Cleanup Verification

**Files:**
- Modify: `tests/test_docker.py`
- Modify: `tests/run.py`

**Interfaces:**
- Consumes: module-level endpoint configuration from `tests/run.py`.
- Consumes: public `DockerConnection` command, lifecycle, and transfer APIs.
- Produces: one real integration suite that owns and removes every resource it creates.

- [ ] **Step 1: Add the real Docker client fixture**

At file scope import `DockerClient`, `TLSConfig`, `NotFound`, `tempfile`,
`shutil`, `uuid`, and `Path`.

Create a helper using the same endpoint and TLS rules as the plugin. In
`TestDockerIntegration.setUpClass()`, create a unique fixture name:

```python
cls.fixture_name = (
    f'xbot-plugins-docker-test-{uuid.uuid4().hex[:8]}'
)
cls.fixture = cls.client.containers.run(
    IMAGE,
    command=['/bin/sh', '-c', 'while :; do sleep 60; done'],
    detach=True,
    name=cls.fixture_name,
)
cls.local_root = Path(tempfile.mkdtemp(prefix='xbot-docker-test-'))
```

In `tearDownClass()`, remove the fixture with `force=True`, remove the local
temporary directory with
`shutil.rmtree(cls.local_root, ignore_errors=True)`, and close
the raw client in `finally` blocks.

- [ ] **Step 2: Add image lifecycle and command integration tests**

Connect with:

```python
conn.connect(
    HOST,
    port=PORT,
    image=IMAGE,
    runargs={
        'command': ['/bin/sh', '-c', 'while :; do sleep 60; done'],
    },
    cacert=CACERT,
    clientcert=CLIENTCERT,
    clientkey=CLIENTKEY,
)
```

Save the created container ID before disconnect. Test `expect=0`, nonzero
return-code expectation, string expectation, `expect=None`, environment
override, `DockerCommandResult`, `cd('/tmp')`, and:

```python
with self.assertRaises(TimeoutError):
    conn.exec('sleep 2', timeout=1)
```

After `disconnect()`, assert `client.containers.get(saved_id)` raises
`docker.errors.NotFound`.

- [ ] **Step 3: Add existing and stopped container integration tests**

Connect by `container=cls.fixture_name`, run `echo` and file checks, then
disconnect. Reload the raw fixture and assert its status remains `running`.

Create a stopped container with `client.containers.create()`, assert plugin
`connect(container=stopped.name)` raises `DockerConnectError`, and remove the
stopped fixture in `finally`.

- [ ] **Step 4: Add real file and directory transfer tests**

Create a local structure containing one file and a nested directory. Upload
and download with original and renamed filenames. Assert file contents and
directory layout on both sides. Use a unique remote root under `/tmp`, and
remove it in a test-class cleanup registered before the first assertion.

Verify:

```text
putfile: local/file -> remote_root/file
putfile rename: local/file -> remote_root/renamed
putdir: local/tree -> remote_root/tree
getfile rename: remote_root/file -> download/renamed
getdir: remote_root/tree -> download/tree
```

- [ ] **Step 5: Prove the runner fails truthfully**

Temporarily change one integration assertion from the expected content to a
known wrong string. Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: output contains `FAILED` and the shell exit status is nonzero.

Restore the assertion through `apply_patch`, rerun the same command, and
expect `OK` with exit status zero. Do not commit the deliberate failure.

- [ ] **Step 6: Verify cleanup and commit**

After the successful run, query the daemon using the test endpoint and assert:

- no container name starts with `xbot-plugins-docker-test-`;
- no image-created test container ID remains;
- the unique remote `/tmp` test path is absent;
- the local temporary directory is absent.

Commit:

```bash
git add tests/run.py tests/test_docker.py
git commit -m 'test: cover real docker operations'
```

---

### Task 6: SSH-Aligned README and xbot.framework Demo

**Files:**
- Modify: `README.md`
- Modify: `README.zh.md`
- Create: `demo/README.md`
- Create: `demo/lib/__init__.py`
- Create: `demo/lib/testbed.py`
- Create: `demo/lib/testcase.py`
- Create: `demo/testbeds/mytestbed.yml`
- Create: `demo/testcases/__init__.py`
- Create: `demo/testcases/tc_docker.py`
- Create: `demo/testsets/mytestset.yml`
- Create: `docs/.gitkeep`

**Interfaces:**
- Consumes: final `DockerConnection` public API.
- Produces: English and Chinese user guides with exactly four sections and a runnable xbot.framework demo.

- [ ] **Step 1: Write the English README**

Mirror the SSH README language switcher and separators. Use exactly these
headings:

```markdown
## Introduction
## Installation
## Get Started
## Demo
```

The Get Started code must demonstrate two separate connections:

```python
import os
import shutil

from xbot.plugins.docker.docker import DockerConnection

host = '192.168.8.8'

container_conn = DockerConnection()
container_conn.connect(
    host,
    container='existing-container',
    user='root',
)
container_conn.exec('echo hello', expect=0)
container_conn.disconnect()

image_conn = DockerConnection()
image_conn.connect(
    host,
    image='alpine:latest',
    runargs={'command': 'sleep infinity'},
    user='root',
)

image_conn.exec('echo hello', expect=0)
image_conn.exec('/bin/sh -c "exit 2"', expect=2)
image_conn.exec('echo hello', expect='hello')
image_conn.exec('/bin/sh -c "exit 7"', expect=None)

result = image_conn.exec('echo "jack 20"; echo "tom 30"')
assert str(result) == 'jack 20\ntom 30'
assert result.rc == 0
assert result.getfield('tom', 2) == '30'
assert result.getcol(2) == ['20', '30']

with image_conn.cd('/tmp'):
    assert image_conn.exec('pwd') == '/tmp'

local_home = os.environ.get('HOME') or os.environ['HOMEPATH']
local_put_dir = os.path.join(local_home, 'docker-put-dir')
local_get_dir = os.path.join(local_home, 'docker-get-dir')
remote_dir = '/tmp/docker-put-get-dir'
shutil.rmtree(local_put_dir, ignore_errors=True)
shutil.rmtree(local_get_dir, ignore_errors=True)
os.makedirs(os.path.join(local_put_dir, 'tree', 'nested'))
os.makedirs(local_get_dir)
with open(
    os.path.join(local_put_dir, 'file'),
    'w',
    encoding='utf-8',
) as local_file:
    local_file.write('xbot\n')

image_conn.makedirs(remote_dir)
image_conn.putfile(
    os.path.join(local_put_dir, 'file'),
    remote_dir,
)
image_conn.putfile(
    os.path.join(local_put_dir, 'file'),
    remote_dir,
    filename='renamed',
)
image_conn.putdir(
    os.path.join(local_put_dir, 'tree'),
    remote_dir,
)
image_conn.getfile(
    image_conn.join(remote_dir, 'file'),
    local_get_dir,
)
image_conn.getfile(
    image_conn.join(remote_dir, 'file'),
    local_get_dir,
    filename='renamed',
)
image_conn.getdir(
    image_conn.join(remote_dir, 'tree'),
    local_get_dir,
)

image_conn.disconnect()
```

Do not add test, development, build, architecture, or release sections.

- [ ] **Step 2: Write the matching Chinese README**

Use exactly these headings:

```markdown
## 简介
## 安装
## 入门
## 示例项目
```

Keep every code example and behavior synchronized with `README.md`; translate
only prose and comments.

- [ ] **Step 3: Create the demo connection cache**

Implement `demo/lib/testbed.py` so `TestBed.get_conn(role)` reads the selected
Docker server, container/image, runargs, TLS paths, and user from YAML, creates
one `DockerConnection`, caches it by role, and returns the same connection on
subsequent calls.

Implement `disconnect()` on the demo TestBed to close every cached connection,
ensuring image-created containers are removed.

Use this implementation shape:

```python
from xbot.framework import testbed
from xbot.plugins.docker.docker import DockerConnection


class TestBed(testbed.TestBed):
    """
    TestBed for Docker demo.
    """

    def __init__(self, filepath: str) -> None:
        """
        Initialize the Docker TestBed.

        :param filepath: TestBed filepath.
        :return: None.
        """
        super().__init__(filepath)
        self._conns: dict[str, DockerConnection] = {}

    def get_conn(self, role: str) -> DockerConnection:
        """
        Get the connection for a target role.

        :param role: Target role.
        :return: Cached Docker connection.
        """
        if role in self._conns:
            return self._conns[role]
        targets = self.get('targets')
        for target in targets:
            if target['role'] == role:
                conn = DockerConnection()
                conn.connect(
                    self.get('docker.host'),
                    port=self.get('docker.port'),
                    container=target.get('container'),
                    image=target.get('image'),
                    user=target.get('user'),
                    runargs=target.get('runargs'),
                    cacert=self.get('docker.cacert'),
                    clientcert=self.get('docker.clientcert'),
                    clientkey=self.get('docker.clientkey'),
                )
                self._conns[role] = conn
                return conn
        raise ValueError(f'No such Docker target: role={role}')

    def disconnect(self) -> None:
        """
        Disconnect all cached connections.

        :return: None.
        """
        for conn in self._conns.values():
            conn.disconnect()
        self._conns.clear()
```

Create `demo/testbeds/mytestbed.yml` with:

```yaml
docker:
  host: 192.168.8.8
  port: 2375
  cacert:
  clientcert:
  clientkey:
targets:
  - role: test
    user: root
    container:
    image: alpine:latest
    runargs:
      command: sleep infinity
```

- [ ] **Step 4: Create the demo testcase**

Implement `tc_docker` steps for:

- successful command and output expectation;
- nonzero return-code expectation;
- `expect=None`;
- `cd('/tmp')`;
- file upload/download;
- directory upload/download.

Its teardown removes local demo data and disconnects the cached connection.
Use `xbot.framework.utils.assertx` for explicit content and path assertions,
matching the SSH demo style.

Use `setup()` to assign `self.docker = self.testbed.get_conn('test')`, create
one local temporary directory with `tempfile.mkdtemp()`, create a file and a
nested directory under it, and create `/tmp/xbot-docker-demo` through
`makedirs()`. Implement the steps with these exact public calls:

```python
def step1(self) -> None:
    """
    Test successful command execution.

    :return: None.
    """
    self.docker.exec('echo hello', expect='hello')


def step2(self) -> None:
    """
    Test return-code and unchecked expectations.

    :return: None.
    """
    self.docker.exec('/bin/sh -c "exit 2"', expect=2)
    self.docker.exec('/bin/sh -c "exit 7"', expect=None)


def step3(self) -> None:
    """
    Test the directory context.

    :return: None.
    """
    with self.docker.cd('/tmp'):
        assertx(self.docker.exec('pwd'), '==', '/tmp')


def step4(self) -> None:
    """
    Test file transfer.

    :return: None.
    """
    self.docker.putfile(self.local_file, self.remote_dir)
    self.docker.getfile(
        self.docker.join(self.remote_dir, 'file'),
        self.download_dir,
    )


def step5(self) -> None:
    """
    Test directory transfer.

    :return: None.
    """
    self.docker.putdir(self.local_tree, self.remote_dir)
    self.docker.getdir(
        self.docker.join(self.remote_dir, 'tree'),
        self.download_dir,
    )
```

Implement teardown in this order:

```python
def teardown(self) -> None:
    """
    Clean demo resources.

    :return: None.
    """
    try:
        self.docker.exec(
            f'rm -rf -- {self.remote_dir}',
            expect=None,
        )
    finally:
        shutil.rmtree(self.local_root, ignore_errors=True)
        self.testbed.disconnect()
```

- [ ] **Step 5: Validate docs against the public API and commit**

Run:

```bash
rg -n '^## ' README.md README.zh.md
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: each README has exactly four second-level headings and all tests
pass.

Commit:

```bash
git add README.md README.zh.md demo docs/.gitkeep
git commit -m 'docs: add docker plugin usage and demo'
```

---

### Task 7: Type, Build, Artifact, and Final-State Verification

**Files:**
- Modify only if verification exposes a defect: source, tests, metadata, README, or demo file responsible for that defect.

**Interfaces:**
- Consumes: the complete package.
- Produces: a clean, typed, buildable, installable, and verified source tree without publishing.

- [ ] **Step 1: Re-run the only test entrypoint**

Run:

```bash
python tests/run.py \
  -H "$DOCKER_TEST_HOST" \
  -P "$DOCKER_TEST_PORT" \
  -i "$DOCKER_TEST_IMAGE" \
  --cacert "${DOCKER_TEST_CACERT:-}" \
  --clientcert "${DOCKER_TEST_CLIENTCERT:-}" \
  --clientkey "${DOCKER_TEST_CLIENTKEY:-}"
```

Expected: one combined result ending in `OK` and exit status zero.

- [ ] **Step 2: Run syntax and type verification**

Run:

```bash
python -m compileall xbot tests demo
python -m mypy xbot/plugins/docker tests
```

Expected: both commands exit zero. Fix only concrete reported defects, keeping
public signatures and behavior unchanged, then rerun both commands.

- [ ] **Step 3: Build clean artifacts**

Remove only generated package outputs inside this repository:

```bash
rm -rf build dist xbot.plugins.docker.egg-info
python -m build --no-isolation
python -m twine check dist/*
```

Expected: one `0.1.0` wheel and one `0.1.0` sdist, both passing `twine check`.

- [ ] **Step 4: Inspect artifact contents and installed metadata**

List archive members:

```bash
python -m zipfile -l dist/xbot_plugins_docker-0.1.0-py3-none-any.whl
tar -tzf dist/xbot_plugins_docker-0.1.0.tar.gz
```

Verify inclusion of:

```text
README.md
README.zh.md
LICENSE
xbot/plugins/docker/docker.py
xbot/plugins/docker/errors.py
xbot/plugins/docker/utils.py
xbot/plugins/docker/version.py
xbot/plugins/docker/py.typed
tests/run.py
tests/test_docker.py
tests/test_utils.py
```

Verify exclusion of `__pycache__`, `.pyc`, `.DS_Store`, local temporary data,
and credentials.

Install the wheel into a disposable virtual environment:

```bash
rm -rf /tmp/xbot-plugins-docker-verify
python -m venv /tmp/xbot-plugins-docker-verify
/tmp/xbot-plugins-docker-verify/bin/python -m pip install \
  --no-deps dist/xbot_plugins_docker-0.1.0-py3-none-any.whl
```

Run this assertion with the disposable environment:

```python
from importlib.metadata import version
from xbot.plugins.docker.version import __version__

assert version('xbot.plugins.docker') == '0.1.0'
assert __version__ == '0.1.0'
```

Execute it as:

```bash
/tmp/xbot-plugins-docker-verify/bin/python -c \
  "from importlib.metadata import version; from xbot.plugins.docker.version import __version__; assert version('xbot.plugins.docker') == '0.1.0'; assert __version__ == '0.1.0'"
```

- [ ] **Step 5: Recheck remote cleanup and final Git state**

Use the remote test endpoint to confirm no test containers or remote test
paths remain. Run:

```bash
git status --short
git log --oneline --decorate -8
```

Expected: only intentional source changes are present; no generated artifacts
are staged or committed.

- [ ] **Step 6: Commit verification fixes if needed**

If Steps 1–5 required source changes, commit only those files:

```bash
git add README.md README.zh.md pyproject.toml setup.py \
  xbot/plugins/docker tests demo
git commit -m 'fix: complete docker plugin validation'
```

If no source changes were needed, do not create an empty commit.

Do not tag, push, publish to TestPyPI/PyPI, or create a GitHub Release.
