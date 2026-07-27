"""
Docker module.
"""

import io
import os
import posixpath
import shlex
import tarfile
import threading
import time
from contextlib import contextmanager
from select import select
from typing import Generator, cast

from docker import DockerClient
from docker.errors import DockerException
from docker.models.containers import Container
from docker.tls import TLSConfig

from xbot.framework.logger import ExtraAdapter, getlogger
from xbot.plugins.docker.errors import DockerCommandError, DockerConnectError
from xbot.plugins.docker.utils import (
    remove_ansi_escape_chars,
    remove_unprintable_chars,
)


logger = getlogger(__name__)


class DockerCommandResult(str):
    """
    Result of a Docker command.
    """

    __rc: int
    __cmd: str

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

    def exec(
        self,
        cmd: str,
        expect: int | str | None = 0,
        timeout: int | float = 15,
        shenvs: dict[str, str] | None = None,
    ) -> DockerCommandResult:
        """
        Execute a command in the connected container.

        :param cmd: Command to execute.
        :param expect: Expected return code, output text, or None to skip
            checks.
        :param timeout: Command timeout in seconds.
        :param shenvs: Per-command shell environment variables.
        :return: Command output and metadata.
        :raises DockerCommandError: If the command result does not match expect.
        :raises TimeoutError: If the command does not finish before timeout.
        """
        effective_cmd = cmd
        if self._cwd:
            effective_cmd = f'cd {shlex.quote(self._cwd)} && {cmd}'
        extra: dict[str, dict[str, DockerCommandResult]] = {'hook': {}}
        self._logger.info(
            f"Command: '{effective_cmd}', Expect: '{expect}'",
            extra=extra,
        )
        environment = {
            'LANG': 'C.UTF-8',
            'LANGUAGE': 'en_US.UTF-8',
        }
        environment.update(self._shenvs)
        environment.update(shenvs or {})
        exec_info = self._client().api.exec_create(
            self._container_resource().id,
            ['/bin/sh', '-c', effective_cmd],
            stdout=True,
            stderr=True,
            stdin=False,
            tty=True,
            environment=environment,
            user=self._user,
        )
        exec_id = exec_info['Id']
        socket = self._client().api.exec_start(
            exec_id,
            tty=True,
            socket=True,
        )
        encoding = environment['LANG'].rpartition('.')[2] or 'utf-8'
        output = ''
        started = time.monotonic()
        try:
            while time.monotonic() - started <= timeout:
                readable, _, _ = select([socket], [], [], 0.1)
                if socket not in readable:
                    continue
                if hasattr(socket, 'recv'):
                    data = socket.recv(1024)
                else:
                    data = socket.read(1024)
                if not data:
                    break
                output += data.decode(encoding=encoding, errors='ignore')
            else:
                result = DockerCommandResult(
                    output,
                    rc=-1,
                    cmd=effective_cmd,
                )
                extra['hook']['more'] = result
                raise TimeoutError(
                    f"Command '{effective_cmd}' timedout({timeout}s):\n{result}"
                )
        finally:
            socket.close()

        result = DockerCommandResult(
            output,
            rc=self._client().api.exec_inspect(exec_id)['ExitCode'],
            cmd=effective_cmd,
        )
        extra['hook']['more'] = result
        if expect is None:
            return result
        if isinstance(expect, int) and expect == result.rc:
            return result
        if isinstance(expect, str) and expect in result:
            return result
        raise DockerCommandError(
            'Expectations not met:\n'
            f'Command: {effective_cmd}\n'
            f'Expect: {expect}\n'
            f'ReturnCode: {result.rc}\n'
            f'Output:\n{result}'
        )

    def join(self, *paths: str) -> str:
        """
        Join container paths using POSIX semantics.

        :param paths: Path components.
        :return: Joined container path.
        """
        return posixpath.join(*paths)

    def normpath(self, path: str) -> str:
        """
        Normalize a container path using POSIX semantics.

        :param path: Container path.
        :return: Normalized container path.
        """
        return posixpath.normpath(path)

    def basename(self, path: str) -> str:
        """
        Return the final component of a container path.

        :param path: Container path.
        :return: Final path component.
        """
        return posixpath.basename(path)

    def exists(self, path: str) -> bool:
        """
        Check whether a container path exists.

        :param path: Container path.
        :return: True when the path exists.
        """
        result = self.exec(
            f'test -e {shlex.quote(path)}',
            expect=None,
        )
        return result.rc == 0

    def makedirs(self, path: str) -> None:
        """
        Create a container directory and its parents.

        :param path: Container directory path.
        :return: None.
        """
        self.exec(f'mkdir -p -- {shlex.quote(path)}')

    def _get_owner(self) -> tuple[int, int]:
        """
        Return the connected container user and group IDs.

        :return: Container user and group IDs.
        """
        if self._uid is None or self._gid is None:
            self._uid = int(self.exec('id -u'))
            self._gid = int(self.exec('id -g'))
        return self._uid, self._gid

    def getfile(
        self,
        rfile: str,
        ldir: str,
        filename: str | None = None,
    ) -> None:
        """
        Download a container file into an existing local directory.

        :param rfile: Container file path.
        :param ldir: Existing local destination directory.
        :param filename: Optional local destination filename.
        :return: None.
        """
        container = self._container_resource()
        if not os.path.exists(ldir):
            raise FileNotFoundError(ldir)
        if not os.path.isdir(ldir):
            raise NotADirectoryError(ldir)
        stream, _ = container.get_archive(rfile)
        archive_data = io.BytesIO()
        for chunk in stream:
            archive_data.write(chunk)
        archive_data.seek(0)
        with tarfile.open(fileobj=archive_data, mode='r') as archive:
            member = archive.getmembers()[0]
            archive.extract(member, ldir)
        if filename is not None:
            os.replace(
                os.path.join(ldir, member.name),
                os.path.join(ldir, filename),
            )

    def getdir(self, rdir: str, ldir: str) -> None:
        """
        Download a container directory into an existing local directory.

        :param rdir: Container directory path.
        :param ldir: Existing local destination directory.
        :return: None.
        """
        container = self._container_resource()
        if not os.path.exists(ldir):
            raise FileNotFoundError(ldir)
        if not os.path.isdir(ldir):
            raise NotADirectoryError(ldir)
        stream, _ = container.get_archive(rdir)
        archive_data = io.BytesIO()
        for chunk in stream:
            archive_data.write(chunk)
        archive_data.seek(0)
        with tarfile.open(fileobj=archive_data, mode='r') as archive:
            archive.extractall(ldir)

    def putfile(
        self,
        lfile: str,
        rdir: str,
        filename: str | None = None,
    ) -> None:
        """
        Upload a local file into a container directory.

        :param lfile: Local file path.
        :param rdir: Container destination directory.
        :param filename: Optional destination filename.
        :return: None.
        """
        container = self._container_resource()
        uid, gid = self._get_owner()

        def set_owner(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
            """
            Set archive ownership.

            :param tarinfo: Archive member metadata.
            :return: Updated archive member metadata.
            """
            tarinfo.uid = uid
            tarinfo.gid = gid
            return tarinfo

        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            archive.add(
                lfile,
                arcname=filename or os.path.basename(lfile),
                filter=set_owner,
            )
        if not self.exists(rdir):
            self.makedirs(rdir)
        stream.seek(0)
        container.put_archive(rdir, stream)

    def putdir(self, ldir: str, rdir: str) -> None:
        """
        Upload a local directory into a container directory.

        :param ldir: Local directory path.
        :param rdir: Container destination directory.
        :return: None.
        """
        container = self._container_resource()
        uid, gid = self._get_owner()

        def set_owner(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
            """
            Set archive ownership.

            :param tarinfo: Archive member metadata.
            :return: Updated archive member metadata.
            """
            tarinfo.uid = uid
            tarinfo.gid = gid
            return tarinfo

        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            archive.add(
                ldir,
                arcname=os.path.basename(os.path.normpath(ldir)),
                filter=set_owner,
            )
        if not self.exists(rdir):
            self.makedirs(rdir)
        stream.seek(0)
        container.put_archive(rdir, stream)

    @contextmanager
    def cd(self, path: str) -> Generator[None, None, None]:
        """
        Change the working directory for commands in the context.

        :param path: Container working directory.
        :return: Context manager iterator.
        """
        self._cdlock.acquire()
        try:
            self._cwd = path
            yield
        finally:
            self._cwd = ''
            self._cdlock.release()
