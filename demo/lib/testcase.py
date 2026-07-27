from typing import cast

from xbot.framework import testcase

from .testbed import TestBed


class TestCase(testcase.TestCase):
    """
    TestCase for Docker demo.
    """

    @property
    def testbed(self) -> TestBed:
        """
        TestBed instance.

        :return: Docker TestBed instance.
        """
        return cast(TestBed, super().testbed)
