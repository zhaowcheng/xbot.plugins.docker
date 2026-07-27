"""
Test Docker module helpers.
"""

import doctest
import importlib.util
import io
import shutil
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from docker import DockerClient
from docker.errors import DockerException, NotFound
from docker.models.containers import Container
from docker.tls import TLSConfig

from demo.lib.testbed import TestBed as DemoTestBed
from xbot.plugins.docker import docker
from xbot.plugins.docker.docker import DockerCommandResult, DockerConnection
from xbot.plugins.docker.errors import DockerCommandError, DockerConnectError


HOST = ''
PORT = 2375
IMAGE = ''
CACERT = ''
CLIENTCERT = ''
CLIENTKEY = ''


def load_runner_module() -> ModuleType:
    """
    Load the test runner without executing its command-line entry point.

    :return: Loaded test runner module.
    """
    runner_path = Path(__file__).with_name('run.py')
    spec = importlib.util.spec_from_file_location(
        'xbot_plugins_docker_test_runner',
        runner_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Cannot load test runner: {runner_path}')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def create_docker_client() -> DockerClient:
    """
    Create a real client using the configured Docker endpoint.

    :return: Docker client.
    """
    tls: TLSConfig | bool = False
    if CACERT or CLIENTCERT:
        tls = TLSConfig(
            ca_cert=CACERT,
            verify=bool(CACERT),
            client_cert=(
                (CLIENTCERT, CLIENTKEY)
                if CLIENTCERT and CLIENTKEY
                else None
            ),
        )
    return DockerClient(
        base_url=f'tcp://{HOST}:{PORT}',
        tls=tls,
        timeout=5,
    )


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


class TestDockerConnection(unittest.TestCase):
    """
    Test Docker connection lifecycle.
    """

    def setUp(self) -> None:
        """
        Create a mocked Docker client and containers.

        :return: None.
        """
        self.client_patch = patch('xbot.plugins.docker.docker.DockerClient')
        self.client_class = self.client_patch.start()
        self.client = self.client_class.return_value
        self.select_patch = patch('xbot.plugins.docker.docker.select')
        self.select = self.select_patch.start()
        existing = self.client.containers.get.return_value
        existing.status = 'running'
        existing.name = 'existing'
        existing.id = 'existing-id'
        self.container = existing
        created = self.client.containers.create.return_value
        created.status = 'running'
        created.name = 'created-container'
        created.id = 'created-id'
        self.conn = DockerConnection()

    def tearDown(self) -> None:
        """
        Stop the Docker client patch.

        :return: None.
        """
        self.client_patch.stop()
        self.select_patch.stop()

    def create_connected_connection(
        self,
        shenvs: dict[str, str] | None = None,
        user: str | None = None,
    ) -> DockerConnection:
        """
        Create a connection backed by the mocked existing container.

        :param shenvs: Default shell environment variables.
        :param user: Container command user.
        :return: Connected Docker connection.
        """
        connection = DockerConnection(shenvs=shenvs)
        connection.connect('127.0.0.1', container='existing', user=user)
        return connection

    def configure_exec(
        self,
        output: bytes,
        rc: int,
    ) -> MagicMock:
        """
        Configure the Docker API responses for one command execution.

        :param output: Command output received from the socket.
        :param rc: Command return code.
        :return: Mocked Docker socket.
        """
        socket = MagicMock()
        socket.recv.side_effect = [output, b'']
        self.client.api.exec_create.return_value = {'Id': 'exec-id'}
        self.client.api.exec_start.return_value = socket
        self.client.api.exec_inspect.return_value = {'ExitCode': rc}
        self.select.return_value = ([socket], [], [])
        return socket

    def test_connect_requires_exactly_one_target(self) -> None:
        """
        Test connection requires one target source.

        :return: None.
        """
        conn = DockerConnection()
        with self.assertRaisesRegex(ValueError, 'only one'):
            conn.connect('127.0.0.1')
        with self.assertRaisesRegex(ValueError, 'only one'):
            conn.connect(
                '127.0.0.1',
                container='existing',
                image='alpine:latest',
            )
        self.client_class.assert_not_called()

    def test_client_certificate_and_key_must_be_paired(self) -> None:
        """
        Test client certificate paths must be paired.

        :return: None.
        """
        conn = DockerConnection()
        with self.assertRaisesRegex(ValueError, 'clientcert'):
            conn.connect(
                '127.0.0.1',
                container='existing',
                clientcert='cert.pem',
            )
        self.client_class.assert_not_called()

    def test_existing_stopped_container_is_rejected(self) -> None:
        """
        Test stopped caller-owned containers cannot be connected.

        :return: None.
        """
        container = self.client.containers.get.return_value
        container.status = 'exited'

        with self.assertRaises(DockerConnectError):
            self.conn.connect('127.0.0.1', container='existing')

        container.start.assert_not_called()
        self.client.close.assert_called_once_with()

    def test_disconnect_removes_only_image_container(self) -> None:
        """
        Test disconnect removes a container created from an image.

        :return: None.
        """
        self.conn.connect(
            '127.0.0.1',
            image='alpine:latest',
            runargs={'command': 'sleep 60'},
        )
        created = self.client.containers.create.return_value

        self.conn.disconnect()

        created.start.assert_called_once_with()
        created.remove.assert_called_once_with(force=True)
        self.client.close.assert_called_once_with()

    def test_second_connect_does_not_call_docker_api(self) -> None:
        """
        Test a connected instance does not connect again.

        :return: None.
        """
        self.conn.connect('127.0.0.1', container='existing')
        self.conn.connect('other-host', image='alpine:latest')

        self.client_class.assert_called_once()
        self.client.containers.get.assert_called_once_with('existing')
        self.client.containers.create.assert_not_called()

    def test_unopened_accessors_raise_connect_error(self) -> None:
        """
        Test connection resources cannot be used before connect.

        :return: None.
        """
        with self.assertRaisesRegex(
            DockerConnectError,
            'Docker connection is not open.',
        ):
            self.conn._client()
        with self.assertRaisesRegex(
            DockerConnectError,
            'Docker connection is not open.',
        ):
            self.conn._container_resource()

    def test_second_disconnect_does_not_call_docker_api(self) -> None:
        """
        Test a disconnected instance does not close twice.

        :return: None.
        """
        self.conn.connect('127.0.0.1', container='existing')
        self.conn.disconnect()
        self.conn.disconnect()

        self.client.close.assert_called_once_with()

    def test_exec_uses_shell_user_and_merged_environment(self) -> None:
        """
        Test command execution uses the configured shell environment and user.

        :return: None.
        """
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
            self.client.containers.get.return_value.id,
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
        """
        Test all supported expectation modes.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.configure_exec(output=b'not found\n', rc=2)
        self.conn.exec('ls /missing', expect=2)
        self.configure_exec(output=b'hello\n', rc=7)
        self.conn.exec('echo hello', expect='hello')
        self.configure_exec(output=b'failed\n', rc=9)
        self.conn.exec('false', expect=None)

    def test_expect_mismatch_raises_command_error(self) -> None:
        """
        Test a mismatched expectation raises a command error.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.configure_exec(output=b'hello\n', rc=1)

        with self.assertRaises(DockerCommandError) as context:
            self.conn.exec('echo hello')

        self.assertIn('Command: echo hello', str(context.exception))
        self.assertIn('Expect: 0', str(context.exception))
        self.assertIn('ReturnCode: 1', str(context.exception))

    def test_cd_prefixes_command_and_restores_directory(self) -> None:
        """
        Test directory contexts prefix a command and restore the directory.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.configure_exec(output=b'/tmp\n', rc=0)

        with self.conn.cd('/tmp'):
            result = self.conn.exec('pwd')

        self.assertEqual(result.cmd, 'cd /tmp && pwd')
        self.assertEqual(self.conn._cwd, '')

    @staticmethod
    def create_archive(members: dict[str, bytes]) -> bytes:
        """
        Create a tar archive for download tests.

        :param members: Archive member contents by name.
        :return: Uncompressed tar archive data.
        """
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            for name, content in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))
        return stream.getvalue()

    def test_posix_path_helpers(self) -> None:
        """
        Test container path helpers use POSIX semantics.

        :return: None.
        """
        self.assertEqual(self.conn.join('/tmp', 'a', 'file'), '/tmp/a/file')
        self.assertEqual(self.conn.normpath('/tmp/a/../b/'), '/tmp/b')
        self.assertEqual(self.conn.basename('/tmp/b/file'), 'file')

    def test_exists_returns_command_status(self) -> None:
        """
        Test exists returns whether the command reports a path.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.configure_exec(output=b'', rc=1)

        self.assertFalse(self.conn.exists('/tmp/missing'))

    def test_makedirs_uses_quoted_recursive_command(self) -> None:
        """
        Test makedirs creates a container directory recursively.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.configure_exec(output=b'', rc=0)

        self.conn.makedirs('/tmp/a path')

        self.client.api.exec_create.assert_called_once_with(
            self.container.id,
            ['/bin/sh', '-c', "mkdir -p -- '/tmp/a path'"],
            stdout=True,
            stderr=True,
            stdin=False,
            tty=True,
            environment={
                'LANG': 'C.UTF-8',
                'LANGUAGE': 'en_US.UTF-8',
            },
            user=None,
        )

    def test_get_owner_caches_container_identity(self) -> None:
        """
        Test container owner IDs are looked up once per connection.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        with patch.object(
            self.conn,
            'exec',
            side_effect=[DockerCommandResult('1000'), DockerCommandResult('1001')],
        ) as execute:
            self.assertEqual(self.conn._get_owner(), (1000, 1001))
            self.assertEqual(self.conn._get_owner(), (1000, 1001))

        self.assertEqual(execute.call_count, 2)
        execute.assert_has_calls([unittest.mock.call('id -u'), unittest.mock.call('id -g')])

    def test_getfile_extracts_remote_basename(self) -> None:
        """
        Test getfile extracts a downloaded file using its remote basename.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.container.get_archive.return_value = (
            iter([self.create_archive({'source': b'content'})]),
            {},
        )
        with tempfile.TemporaryDirectory() as directory:
            self.conn.getfile('/tmp/source', directory)

            self.assertEqual(
                Path(directory, 'source').read_bytes(),
                b'content',
            )

    def test_getfile_renames_download(self) -> None:
        """
        Test getfile renames a downloaded file when requested.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.container.get_archive.return_value = (
            iter([self.create_archive({'source': b'content'})]),
            {},
        )
        with tempfile.TemporaryDirectory() as directory:
            self.conn.getfile('/tmp/source', directory, filename='renamed')

            self.assertEqual(
                Path(directory, 'renamed').read_bytes(),
                b'content',
            )

    def test_getdir_keeps_top_level_directory(self) -> None:
        """
        Test getdir preserves the remote directory basename locally.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.container.get_archive.return_value = (
            iter([self.create_archive({'tree/nested/file.txt': b'content'})]),
            {},
        )
        with tempfile.TemporaryDirectory() as directory:
            self.conn.getdir('/tmp/tree', directory)

            self.assertEqual(
                Path(directory, 'tree', 'nested', 'file.txt').read_bytes(),
                b'content',
            )

    def test_getfile_propagates_unopened_connection_error(self) -> None:
        """
        Test getfile preserves the public unopened connection error.

        :return: None.
        """
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(
                DockerConnectError,
                r'^Docker connection is not open\.$',
            ):
                self.conn.getfile('/tmp/source', directory)

    def test_transfer_helpers_propagate_unopened_connection_error(
        self,
    ) -> None:
        """
        Test transfer and path helpers preserve the public connection error.

        :return: None.
        """
        calls = (
            (self.conn.getdir, ('/tmp/tree', '/tmp')),
            (self.conn.putfile, ('/tmp/source', '/tmp')),
            (self.conn.putdir, ('/tmp/tree', '/tmp')),
            (self.conn.exists, ('/tmp/source',)),
            (self.conn.makedirs, ('/tmp/tree',)),
        )

        for method, args in calls:
            with self.subTest(method=method.__name__):
                with self.assertRaisesRegex(
                    DockerConnectError,
                    r'^Docker connection is not open\.$',
                ):
                    method(*args)

    def test_getfile_requires_existing_local_destination(self) -> None:
        """
        Test getfile does not create a missing local destination directory.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.container.get_archive.return_value = (
            iter([self.create_archive({'source': b'content'})]),
            {},
        )
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory, 'missing')
            with self.assertRaises(FileNotFoundError):
                self.conn.getfile('/tmp/source', str(missing))

        self.assertFalse(missing.exists())

    def test_getdir_requires_existing_local_destination(self) -> None:
        """
        Test getdir does not create a missing local destination directory.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.container.get_archive.return_value = (
            iter([self.create_archive({'tree/file.txt': b'content'})]),
            {},
        )
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory, 'missing')
            with self.assertRaises(FileNotFoundError):
                self.conn.getdir('/tmp/tree', str(missing))

        self.assertFalse(missing.exists())

    def test_getfile_propagates_docker_error(self) -> None:
        """
        Test getfile does not wrap Docker archive errors.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        error = DockerException('download failed')
        self.container.get_archive.side_effect = error
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(DockerException) as caught:
                self.conn.getfile('/tmp/source', directory)

        self.assertIs(caught.exception, error)

    def test_putfile_archives_local_basename_with_owner(self) -> None:
        """
        Test putfile archives a file at its basename with container ownership.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.conn._uid = 1000
        self.conn._gid = 1000
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'source.txt')
            source.write_bytes(b'content')
            with patch.object(self.conn, 'exists', return_value=True):
                self.conn.putfile(str(source), '/tmp')

        stream = self.container.put_archive.call_args.args[1]
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r') as archive:
            members = archive.getmembers()
        self.assertEqual(members[0].name, 'source.txt')
        self.assertTrue(all(member.uid == 1000 for member in members))
        self.assertTrue(all(member.gid == 1000 for member in members))
        self.assertEqual(self.container.put_archive.call_args.args[0], '/tmp')

    def test_putfile_uses_requested_archive_name(self) -> None:
        """
        Test putfile uses a requested archive name.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.conn._uid = 1000
        self.conn._gid = 1000
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'source.txt')
            source.write_bytes(b'content')
            with patch.object(self.conn, 'exists', return_value=True):
                self.conn.putfile(str(source), '/tmp', filename='renamed')

        stream = self.container.put_archive.call_args.args[1]
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r') as archive:
            self.assertEqual(archive.getmembers()[0].name, 'renamed')

    def test_putdir_archives_top_level_directory_with_owner(self) -> None:
        """
        Test putdir keeps the local directory basename in the archive.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.conn._uid = 1000
        self.conn._gid = 1000
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'tree')
            source.mkdir()
            Path(source, 'child.txt').write_bytes(b'content')
            with patch.object(self.conn, 'exists', return_value=True):
                self.conn.putdir(str(source), '/tmp')

        stream = self.container.put_archive.call_args.args[1]
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r') as archive:
            members = archive.getmembers()
        self.assertEqual(members[0].name, 'tree')
        self.assertIn('tree/child.txt', [member.name for member in members])
        self.assertTrue(all(member.uid == 1000 for member in members))
        self.assertTrue(all(member.gid == 1000 for member in members))

    def test_putfile_creates_missing_remote_destination(self) -> None:
        """
        Test putfile creates the destination before uploading.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.conn._uid = 1000
        self.conn._gid = 1000
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'source.txt')
            source.write_bytes(b'content')
            with (
                patch.object(self.conn, 'exists', return_value=False),
                patch.object(self.conn, 'makedirs') as makedirs,
            ):
                self.conn.putfile(str(source), '/missing')

        makedirs.assert_called_once_with('/missing')
        self.assertEqual(self.container.put_archive.call_args.args[0], '/missing')

    def test_putfile_propagates_docker_error(self) -> None:
        """
        Test putfile does not wrap Docker archive errors.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        self.conn._uid = 1000
        self.conn._gid = 1000
        error = DockerException('upload failed')
        self.container.put_archive.side_effect = error
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory, 'source.txt')
            source.write_bytes(b'content')
            with patch.object(self.conn, 'exists', return_value=True):
                with self.assertRaises(DockerException) as caught:
                    self.conn.putfile(str(source), '/tmp')

        self.assertIs(caught.exception, error)

    def test_exec_timeout_closes_socket_and_reports_partial_output(
        self,
    ) -> None:
        """
        Test a command timeout closes its socket and reports partial output.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        socket = MagicMock()
        self.client.api.exec_create.return_value = {'Id': 'exec-id'}
        self.client.api.exec_start.return_value = socket

        with (
            patch(
                'xbot.plugins.docker.docker.select',
                return_value=([], [], []),
            ),
            patch(
                'xbot.plugins.docker.docker.time.monotonic',
                side_effect=(0.0, 0.0, 1.0),
            ),
            self.assertRaisesRegex(TimeoutError, "Command 'sleep 1' timedout"),
        ):
            self.conn.exec('sleep 1', timeout=0.5)

        socket.close.assert_called_once_with()

    def test_exec_reads_socket_io_objects(self) -> None:
        """
        Test command execution reads socket-like objects without recv.

        :return: None.
        """
        self.conn = self.create_connected_connection()
        socket = MagicMock(spec=['read', 'close'])
        socket.read.side_effect = [b'hello\n', b'']
        self.client.api.exec_create.return_value = {'Id': 'exec-id'}
        self.client.api.exec_start.return_value = socket
        self.client.api.exec_inspect.return_value = {'ExitCode': 0}
        self.select.return_value = ([socket], [], [])

        result = self.conn.exec('echo hello')

        self.assertEqual(result, 'hello')
        socket.read.assert_called()

    def test_image_connection_creates_without_pull_or_status_check(
        self,
    ) -> None:
        """
        Test image target creates a temporary container directly.

        :return: None.
        """
        runargs: dict[str, object] = {'command': 'sleep 60'}

        self.conn.connect('127.0.0.1', image='alpine:latest', runargs=runargs)

        self.client.containers.create.assert_called_once_with(
            'alpine:latest',
            detach=True,
            command='sleep 60',
        )
        created = self.client.containers.create.return_value
        created.start.assert_called_once_with()
        self.client.images.pull.assert_not_called()
        self.client.containers.get.assert_not_called()
        self.assertEqual(runargs, {'command': 'sleep 60'})

    def test_existing_container_disconnect_does_not_mutate_lifecycle(
        self,
    ) -> None:
        """
        Test caller-owned container lifecycle remains unchanged.

        :return: None.
        """
        self.conn.connect('127.0.0.1', container='existing')
        existing = self.client.containers.get.return_value

        self.conn.disconnect()

        existing.remove.assert_not_called()
        existing.stop.assert_not_called()
        existing.start.assert_not_called()

    def test_lookup_error_becomes_connect_error_and_closes_client(self) -> None:
        """
        Test Docker lookup failures are converted after cleanup.

        :return: None.
        """
        self.client.containers.get.side_effect = DockerException('lookup failed')

        with self.assertRaisesRegex(DockerConnectError, 'lookup failed'):
            self.conn.connect('127.0.0.1', container='missing')

        self.client.close.assert_called_once_with()

    def test_create_error_becomes_connect_error_and_closes_client(self) -> None:
        """
        Test Docker create failures are converted after cleanup.

        :return: None.
        """
        self.client.containers.create.side_effect = DockerException(
            'create failed'
        )

        with self.assertRaisesRegex(DockerConnectError, 'create failed'):
            self.conn.connect('127.0.0.1', image='alpine:latest')

        self.client.close.assert_called_once_with()

    def test_missing_image_is_reported_without_pull(self) -> None:
        """
        Test a missing image is reported without an implicit image pull.

        :return: None.
        """
        self.client.containers.create.side_effect = NotFound('image missing')

        with self.assertRaisesRegex(DockerConnectError, 'image missing'):
            self.conn.connect('127.0.0.1', image='missing:latest')

        self.client.images.pull.assert_not_called()
        self.client.close.assert_called_once_with()

    def test_start_error_removes_created_container(self) -> None:
        """
        Test a start failure removes the already-created container.

        :return: None.
        """
        created = self.client.containers.create.return_value
        created.start.side_effect = DockerException('start failed')
        created.remove.side_effect = DockerException('remove failed')

        with self.assertRaisesRegex(DockerConnectError, 'start failed'):
            self.conn.connect('127.0.0.1', image='alpine:latest')

        created.remove.assert_called_once_with(force=True)
        self.client.close.assert_called_once_with()

    def test_removal_error_is_reraised_after_client_close(self) -> None:
        """
        Test removal failure is retained after Docker client cleanup.

        :return: None.
        """
        self.conn.connect('127.0.0.1', image='alpine:latest')
        created = self.client.containers.create.return_value
        removal_error = DockerException('remove failed')
        created.remove.side_effect = removal_error

        with self.assertRaises(DockerException) as caught:
            self.conn.disconnect()

        self.assertIs(caught.exception, removal_error)
        self.client.close.assert_called_once_with()

    def test_logger_prefixes_identify_target_and_owner(self) -> None:
        """
        Test prefixes distinguish existing and temporary targets.

        :return: None.
        """
        self.conn.connect('127.0.0.1', container='existing', user='root')

        self.assertEqual(
            self.conn._logger.extra['prefix'],
            'docker://root@127.0.0.1:2375/existing',
        )
        self.conn.disconnect()
        self.conn.connect('127.0.0.1', image='alpine:latest', user='root')

        self.assertEqual(
            self.conn._logger.extra['prefix'],
            'docker://root@127.0.0.1:2375/alpine:latest->created-container',
        )


class TestDemoTestBed(unittest.TestCase):
    """
    Test the demo TestBed lifecycle.
    """

    def test_disconnect_continues_after_connection_error(self) -> None:
        """
        Test disconnect cleans every cached connection after an error.

        :return: None.
        """
        testbed = object.__new__(DemoTestBed)
        first = MagicMock(spec=DockerConnection)
        second = MagicMock(spec=DockerConnection)
        first_error = DockerException('first disconnect failed')
        first.disconnect.side_effect = first_error
        second.disconnect.side_effect = DockerException(
            'second disconnect failed'
        )
        testbed._conns = {
            'first': first,
            'second': second,
        }

        with self.assertRaises(DockerException) as caught:
            testbed.disconnect()

        self.assertIs(caught.exception, first_error)
        first.disconnect.assert_called_once_with()
        second.disconnect.assert_called_once_with()
        self.assertEqual(testbed._conns, {})


class TestDockerRunner(unittest.TestCase):
    """
    Test real-integration runner configuration failures.
    """

    def test_empty_endpoint_values_are_rejected(self) -> None:
        """
        Test present but empty endpoint options fail argument parsing.

        :return: None.
        """
        parser = load_runner_module().create_parser()
        arguments = (
            ('-H', '', '-i', 'rockylinux:9'),
            ('-H', '127.0.0.1', '-i', ''),
        )

        for args in arguments:
            with self.subTest(args=args):
                with (
                    patch('sys.stderr', new=io.StringIO()),
                    self.assertRaises(SystemExit) as caught,
                ):
                    parser.parse_args(args)
                self.assertEqual(caught.exception.code, 2)

    def test_missing_integration_configuration_is_an_error(self) -> None:
        """
        Test a missing endpoint cannot silently skip real integration.

        :return: None.
        """
        with (
            patch(f'{__name__}.HOST', ''),
            patch(f'{__name__}.IMAGE', ''),
            self.assertRaisesRegex(
                RuntimeError,
                r'^Real Docker endpoint is not configured\.$',
            ),
        ):
            TestDockerIntegration.setUpClass()


class TestDockerIntegration(unittest.TestCase):
    """
    Test Docker operations against a real remote daemon.
    """

    client: DockerClient
    fixture_name: str
    fixture: Container
    local_root: Path

    @classmethod
    def setUpClass(cls) -> None:
        """
        Create the real Docker client and owned test fixtures.

        :return: None.
        """
        if not HOST or not IMAGE:
            raise RuntimeError('Real Docker endpoint is not configured.')

        cls.client = create_docker_client()
        cls.fixture_name = (
            f'xbot-plugins-docker-test-{uuid.uuid4().hex[:8]}'
        )
        try:
            cls.fixture = cls.client.containers.run(
                IMAGE,
                command=['/bin/sh', '-c', 'while :; do sleep 60; done'],
                detach=True,
                name=cls.fixture_name,
            )
            cls.local_root = Path(
                tempfile.mkdtemp(prefix='xbot-docker-test-')
            )
        except Exception:
            fixture = getattr(cls, 'fixture', None)
            try:
                if fixture is not None:
                    fixture.remove(force=True)
            finally:
                cls.client.close()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Remove every class fixture and close the raw Docker client.

        :return: None.
        """
        try:
            try:
                cls.fixture.remove(force=True)
            except NotFound:
                pass
        finally:
            try:
                shutil.rmtree(cls.local_root, ignore_errors=True)
            finally:
                cls.client.close()

    def remove_remote_root(
        self,
        conn: DockerConnection,
        remote_root: str,
    ) -> None:
        """
        Remove and verify one owned remote test directory.

        :param conn: Open Docker connection.
        :param remote_root: Owned remote test directory.
        :return: None.
        """
        conn.exec(f'rm -rf -- {remote_root}')
        self.assertFalse(conn.exists(remote_root))

    def remove_owned_container(self, container_name: str) -> None:
        """
        Remove an owned test container if the tested cleanup left it behind.

        :param container_name: Unique owned test container name.
        :return: None.
        """
        try:
            container = self.client.containers.get(container_name)
        except NotFound:
            return
        container.remove(force=True)

    def test_image_connection_commands_and_lifecycle(self) -> None:
        """
        Test commands and cleanup for an image-created container.

        :return: None.
        """
        container_name = (
            f'xbot-plugins-docker-test-image-{uuid.uuid4().hex[:8]}'
        )
        conn = DockerConnection()
        self.addCleanup(self.remove_owned_container, container_name)
        conn.connect(
            HOST,
            port=PORT,
            image=IMAGE,
            runargs={
                'command': ['/bin/sh', '-c', 'while :; do sleep 60; done'],
                'name': container_name,
            },
            cacert=CACERT,
            clientcert=CLIENTCERT,
            clientkey=CLIENTKEY,
        )
        try:
            saved_id = self.client.containers.get(container_name).id
            result = conn.exec('printf command-ok')
            self.assertIsInstance(result, DockerCommandResult)
            self.assertEqual(result, 'command-ok')
            self.assertEqual(result.rc, 0)
            self.assertEqual(result.cmd, 'printf command-ok')
            self.assertEqual(conn.exec('exit 7', expect=7).rc, 7)
            self.assertEqual(
                conn.exec('printf string-ok', expect='string-ok'),
                'string-ok',
            )
            self.assertEqual(conn.exec('exit 9', expect=None).rc, 9)
            self.assertEqual(
                conn.exec(
                    'printf "$XBOT_DOCKER_VALUE"',
                    shenvs={'XBOT_DOCKER_VALUE': 'environment-ok'},
                ),
                'environment-ok',
            )
            with conn.cd('/tmp'):
                self.assertEqual(conn.exec('pwd'), '/tmp')
            with self.assertRaises(TimeoutError):
                conn.exec('sleep 2', timeout=1)
        finally:
            conn.disconnect()

        with self.assertRaises(NotFound):
            self.client.containers.get(saved_id)

    def test_existing_container_commands_and_lifecycle(self) -> None:
        """
        Test commands do not change a caller-owned container lifecycle.

        :return: None.
        """
        remote_root = (
            f'/tmp/xbot-plugins-docker-test-existing-'
            f'{uuid.uuid4().hex[:8]}'
        )
        conn = DockerConnection()
        conn.connect(
            HOST,
            port=PORT,
            container=self.fixture_name,
            cacert=CACERT,
            clientcert=CLIENTCERT,
            clientkey=CLIENTKEY,
        )
        try:
            self.assertEqual(conn.exec('echo existing-ok'), 'existing-ok')
            self.assertFalse(conn.exists(remote_root))
            conn.makedirs(remote_root)
            self.assertTrue(conn.exists(remote_root))
        finally:
            try:
                self.remove_remote_root(conn, remote_root)
            finally:
                conn.disconnect()

        fixture = self.client.containers.get(self.fixture_name)
        fixture.reload()
        self.assertEqual(fixture.status, 'running')

    def test_stopped_container_is_rejected(self) -> None:
        """
        Test a real non-running container is rejected and removed.

        :return: None.
        """
        stopped_name = (
            f'xbot-plugins-docker-test-stopped-{uuid.uuid4().hex[:8]}'
        )
        stopped = self.client.containers.create(
            IMAGE,
            command=['/bin/sh', '-c', 'exit 0'],
            name=stopped_name,
        )
        conn = DockerConnection()
        try:
            with self.assertRaises(DockerConnectError):
                conn.connect(
                    HOST,
                    port=PORT,
                    container=stopped.name,
                    cacert=CACERT,
                    clientcert=CLIENTCERT,
                    clientkey=CLIENTKEY,
                )
        finally:
            try:
                conn.disconnect()
            finally:
                stopped.remove(force=True)

    def test_file_and_directory_transfers(self) -> None:
        """
        Test real uploads and downloads with original and renamed paths.

        :return: None.
        """
        case_name = uuid.uuid4().hex[:8]
        local = self.local_root / case_name
        source = local / 'file'
        tree = local / 'tree'
        nested = tree / 'nested'
        download = local / 'download'
        nested.mkdir(parents=True)
        download.mkdir()
        source.write_text('file-content', encoding='utf-8')
        (tree / 'root.txt').write_text('root-content', encoding='utf-8')
        (nested / 'child.txt').write_text(
            'nested-content',
            encoding='utf-8',
        )
        remote_root = f'/tmp/xbot-plugins-docker-test-{case_name}'

        conn = DockerConnection()
        conn.connect(
            HOST,
            port=PORT,
            container=self.fixture_name,
            cacert=CACERT,
            clientcert=CLIENTCERT,
            clientkey=CLIENTKEY,
        )
        self.addCleanup(conn.disconnect)
        self.addCleanup(self.remove_remote_root, conn, remote_root)

        conn.putfile(str(source), remote_root)
        self.assertEqual(
            conn.exec(f'cat {remote_root}/file'),
            'file-content',
        )
        conn.putfile(str(source), remote_root, filename='renamed')
        self.assertEqual(
            conn.exec(f'cat {remote_root}/renamed'),
            'file-content',
        )
        conn.putdir(str(tree), remote_root)
        self.assertEqual(
            conn.exec(f'cat {remote_root}/tree/nested/child.txt'),
            'nested-content',
        )
        conn.getfile(
            f'{remote_root}/file',
            str(download),
            filename='renamed',
        )
        conn.getdir(f'{remote_root}/tree', str(download))

        self.assertEqual(
            (download / 'renamed').read_text(encoding='utf-8'),
            'file-content',
        )
        self.assertEqual(
            (download / 'tree' / 'root.txt').read_text(encoding='utf-8'),
            'root-content',
        )
        self.assertEqual(
            (
                download / 'tree' / 'nested' / 'child.txt'
            ).read_text(encoding='utf-8'),
            'nested-content',
        )
