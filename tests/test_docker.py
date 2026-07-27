"""
Test Docker module helpers.
"""

import doctest
import unittest
from unittest.mock import MagicMock, patch

from docker.errors import DockerException

from xbot.plugins.docker import docker
from xbot.plugins.docker.docker import DockerCommandResult, DockerConnection
from xbot.plugins.docker.errors import DockerCommandError, DockerConnectError


HOST = ''
PORT = 2375
IMAGE = ''
CACERT = ''
CLIENTCERT = ''
CLIENTKEY = ''


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
        created = self.client.containers.run.return_value
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
        created = self.client.containers.run.return_value

        self.conn.disconnect()

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
        self.client.containers.run.assert_not_called()

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
        runargs = {'command': 'sleep 60'}

        self.conn.connect('127.0.0.1', image='alpine:latest', runargs=runargs)

        self.client.containers.run.assert_called_once_with(
            'alpine:latest',
            detach=True,
            command='sleep 60',
        )
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
        self.client.containers.run.side_effect = DockerException('create failed')

        with self.assertRaisesRegex(DockerConnectError, 'create failed'):
            self.conn.connect('127.0.0.1', image='alpine:latest')

        self.client.close.assert_called_once_with()

    def test_removal_error_is_reraised_after_client_close(self) -> None:
        """
        Test removal failure is retained after Docker client cleanup.

        :return: None.
        """
        self.conn.connect('127.0.0.1', image='alpine:latest')
        created = self.client.containers.run.return_value
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
