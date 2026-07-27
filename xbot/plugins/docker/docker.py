"""
Docker module.
"""

import threading
from typing import cast

from docker import DockerClient
from docker.errors import DockerException
from docker.models.containers import Container
from docker.tls import TLSConfig

from xbot.framework.logger import ExtraAdapter, getlogger
from xbot.plugins.docker.errors import DockerConnectError
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


class DockerConnection:
    """
    Docker connection.
    """

    def __init__(self, shenvs: dict[str, str] | None = None) -> None:
        """
        Create a Docker connection.

        :param shenvs: Default shell environment variables.
        :return: None.
        """
        self._logger = ExtraAdapter(logger, {})
        self._shenvs = (shenvs or {}).copy()
        self._dockerclient: DockerClient | None = None
        self._container: Container | None = None
        self._target_source: str | None = None
        self._temporary = False
        self._user: str | None = None
        self._cwd = ''
        self._uid: int | None = None
        self._gid: int | None = None
        self._cdlock = threading.Lock()

    def _client(self) -> DockerClient:
        """
        Return the connected Docker client.

        :return: Docker client.
        :raises DockerConnectError: If the connection is not open.
        """
        if self._dockerclient is None:
            raise DockerConnectError('Docker connection is not open.')
        return self._dockerclient

    def _container_resource(self) -> Container:
        """
        Return the connected Docker container.

        :return: Docker container.
        :raises DockerConnectError: If the connection is not open.
        """
        if self._container is None:
            raise DockerConnectError('Docker connection is not open.')
        return self._container

    def connect(
        self,
        host: str,
        container: str | None = None,
        image: str | None = None,
        port: int = 2375,
        user: str | None = None,
        runargs: dict[str, object] | None = None,
        timeout: int = 5,
        cacert: str | None = None,
        clientcert: str | None = None,
        clientkey: str | None = None,
    ) -> None:
        """
        Open the Docker connection.

        :param host: Docker daemon host.
        :param container: Existing running container name or ID.
        :param image: Image used to create a temporary container.
        :param port: Docker daemon port.
        :param user: Container command user.
        :param runargs: Arguments passed to container creation.
        :param timeout: Docker API timeout in seconds.
        :param cacert: CA certificate path.
        :param clientcert: Client certificate path.
        :param clientkey: Client private-key path.
        :return: None.
        :raises ValueError: If target or client certificate arguments are invalid.
        :raises DockerConnectError: If the Docker connection cannot be opened.
        """
        if self._dockerclient is not None:
            return
        if bool(container) == bool(image):
            raise ValueError('Specify only one container or image target.')
        if bool(clientcert) != bool(clientkey):
            raise ValueError('clientcert and clientkey must be specified together.')

        dockerclient: DockerClient | None = None
        try:
            tls = _create_tls_config(cacert, clientcert, clientkey)
            dockerclient = DockerClient(
                base_url=f'tcp://{host}:{port}',
                tls=tls,
                timeout=timeout,
            )
            if container:
                dockercontainer = dockerclient.containers.get(container)
                if dockercontainer.status != 'running':
                    raise DockerConnectError(
                        f'Docker container {container} is not running.'
                    )
                temporary = False
                target_source = 'container'
                prefix_target = container
            else:
                dockercontainer = dockerclient.containers.run(
                    cast(str, image),
                    detach=True,
                    **(runargs or {}),
                )
                temporary = True
                target_source = 'image'
                prefix_target = f'{image}->{dockercontainer.name}'
        except DockerException as error:
            if dockerclient is not None:
                dockerclient.close()
            raise DockerConnectError(str(error)) from None
        except DockerConnectError:
            if dockerclient is not None:
                dockerclient.close()
            raise

        self._dockerclient = dockerclient
        self._container = dockercontainer
        self._target_source = target_source
        self._temporary = temporary
        self._user = user
        self._logger.extra['prefix'] = (
            f'docker://{user}@{host}:{port}/{prefix_target}'
        )
        self._logger.info('Connecting...')

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
            self._target_source = None
            self._temporary = False
            self._user = None
            self._uid = None
            self._gid = None
        if removal_error is not None:
            raise removal_error
