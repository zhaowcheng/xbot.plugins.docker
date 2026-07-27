"""
Test Docker module helpers.
"""

import doctest
import unittest

from xbot.plugins.docker import docker
from xbot.plugins.docker.docker import DockerCommandResult


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
