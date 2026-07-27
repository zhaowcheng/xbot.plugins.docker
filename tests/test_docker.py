"""
Test Docker module helpers.
"""

import doctest
import unittest
from unittest.mock import patch

from docker.errors import DockerException

from xbot.plugins.docker import docker
from xbot.plugins.docker.docker import DockerCommandResult, DockerConnection
from xbot.plugins.docker.errors import DockerConnectError


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

    def test_image_connection_creates_without_pull_or_status_check(self) -> None:
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

    def test_existing_container_disconnect_does_not_mutate_lifecycle(self) -> None:
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
