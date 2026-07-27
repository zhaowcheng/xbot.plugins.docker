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
    parser.add_argument('--cacert', default='')
    parser.add_argument('--clientcert', default='')
    parser.add_argument('--clientkey', default='')
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
