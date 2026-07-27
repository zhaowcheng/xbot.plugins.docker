"""
Test Docker utility doctests.
"""

import doctest
import unittest

from xbot.plugins.docker import utils


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    ignore: str | None,
) -> unittest.TestSuite:
    """
    Add utility module doctests.

    :param loader: Unittest loader.
    :param tests: Discovered test suite.
    :param ignore: Unused discovery pattern.
    :return: Test suite with doctests.
    """
    tests.addTests(doctest.DocTestSuite(utils))
    return tests
