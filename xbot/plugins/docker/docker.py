"""
Docker module.
"""

from typing import cast

from xbot.framework.logger import ExtraAdapter, getlogger
from xbot.plugins.docker.utils import (
    remove_ansi_escape_chars,
    remove_unprintable_chars,
)


logger = getlogger(__name__)


class DockerCommandResult(str):
    """
    Result of a Docker command.
    """

    def __new__(
        cls: type['DockerCommandResult'],
        out: str,
        rc: int = 0,
        cmd: str = '',
    ) -> 'DockerCommandResult':
        """
        Create a cleaned command result.

        :param out: Command output.
        :param rc: Return code.
        :param cmd: Command.
        :return: Command result.
        """
        out = remove_ansi_escape_chars(out)
        out = remove_unprintable_chars(out)
        out = '\n'.join(out.splitlines())
        result = cast(DockerCommandResult, str.__new__(cls, out.strip()))
        result.__rc = rc
        result.__cmd = cmd
        return result

    @property
    def rc(self) -> int:
        """
        Return the command return code.

        :return: Return code.
        """
        return self.__rc

    @property
    def cmd(self) -> str:
        """
        Return the command text.

        :return: Command text.
        """
        return self.__cmd

    def getfield(
        self,
        key: str | int,
        col: int,
        sep: str | None = None,
    ) -> str | None:
        """
        Get a specified field from the output.

        :param key: String to filter a line or one-based line number.
        :param col: One-based column number in the matched line.
        :param sep: Separator used to split the matched line.
        :return: Field value, if a line matched.

        >>> result = DockerCommandResult('jack 20\\ntom 30')
        >>> result.getfield('tom', 2)
        '30'
        """
        matchline = ''
        lines = self.splitlines()
        if isinstance(key, str):
            for line in lines:
                if key in line:
                    matchline = line
        elif isinstance(key, int):
            matchline = lines[key - 1]
        if matchline:
            fields = matchline.split(sep)
            return fields[col - 1].strip()
        return None

    def getcol(
        self,
        col: int,
        sep: str | None = None,
    ) -> list[str]:
        """
        Get a specified column from the output.

        :param col: One-based column number.
        :param sep: Separator used to split each line.
        :return: Column values.

        >>> result = DockerCommandResult('jack 20\\ntom 30')
        >>> result.getcol(2)
        ['20', '30']
        """
        fields = []
        for line in self.splitlines():
            segments = line.split(sep)
            if col <= len(segments):
                fields.append(segments[col - 1])
        return fields
