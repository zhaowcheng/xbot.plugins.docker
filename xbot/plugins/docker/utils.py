"""
Docker utility functions.
"""

import re
import string


def remove_ansi_escape_chars(s: str) -> str:
    """
    Remove ANSI escape characters from a string.

    :param s: Input string.
    :return: String without ANSI escapes.

    >>> remove_ansi_escape_chars('\x1b[31mhello\x1b[0m')
    'hello'
    """
    escapes = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return escapes.sub('', s)


def remove_unprintable_chars(s: str) -> str:
    """
    Remove unprintable characters from a string.

    :param s: Input string.
    :return: Printable string.

    >>> remove_unprintable_chars('hello\xe9')
    'hello'
    """
    return ''.join(char for char in s if char in string.printable)
