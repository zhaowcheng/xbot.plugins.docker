from xbot.framework import testbed
from xbot.plugins.docker.docker import DockerConnection


class TestBed(testbed.TestBed):
    """
    TestBed for Docker demo.
    """

    def __init__(self, filepath: str) -> None:
        """
        Initialize the Docker TestBed.

        :param filepath: TestBed filepath.
        :return: None.
        """
        super().__init__(filepath)
        self._conns: dict[str, DockerConnection] = {}

    def get_conn(self, role: str) -> DockerConnection:
        """
        Get the connection for a target role.

        :param role: Target role.
        :return: Cached Docker connection.
        """
        if role in self._conns:
            return self._conns[role]
        targets = self.get('targets')
        for target in targets:
            if target['role'] == role:
                conn = DockerConnection()
                conn.connect(
                    self.get('docker.host'),
                    port=self.get('docker.port'),
                    container=target.get('container'),
                    image=target.get('image'),
                    user=target.get('user'),
                    runargs=target.get('runargs'),
                    cacert=self.get('docker.cacert'),
                    clientcert=self.get('docker.clientcert'),
                    clientkey=self.get('docker.clientkey'),
                )
                self._conns[role] = conn
                return conn
        raise ValueError(f'No such Docker target: role={role}')

    def disconnect(self) -> None:
        """
        Disconnect all cached connections.

        :return: None.
        """
        first_error: Exception | None = None
        try:
            for conn in self._conns.values():
                try:
                    conn.disconnect()
                except Exception as error:
                    if first_error is None:
                        first_error = error
        finally:
            self._conns.clear()
        if first_error is not None:
            raise first_error
