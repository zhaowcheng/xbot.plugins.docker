import os
import shutil
import tempfile

from xbot.framework.utils import assertx

from . import tc


class tc_docker(tc):
    """
    Test Docker plugin operations.
    """

    def setup(self) -> None:
        """
        Prepare Docker and local demo resources.

        :return: None.
        """
        self.docker = self.testbed.get_conn('test')
        self.local_root = tempfile.mkdtemp()
        self.local_file = os.path.join(self.local_root, 'file')
        self.local_tree = os.path.join(self.local_root, 'tree')
        self.download_dir = os.path.join(self.local_root, 'download')
        self.remote_dir = '/tmp/xbot-docker-demo'
        os.makedirs(os.path.join(self.local_tree, 'nested'))
        os.makedirs(self.download_dir)
        with open(self.local_file, 'w', encoding='utf-8') as local_file:
            local_file.write('xbot\n')
        with open(
            os.path.join(self.local_tree, 'nested', 'file'),
            'w',
            encoding='utf-8',
        ) as nested_file:
            nested_file.write('nested\n')
        self.docker.makedirs(self.remote_dir)

    def step1(self) -> None:
        """
        Test successful command execution.

        :return: None.
        """
        self.docker.exec('echo hello', expect='hello')

    def step2(self) -> None:
        """
        Test return-code and unchecked expectations.

        :return: None.
        """
        self.docker.exec('/bin/sh -c "exit 2"', expect=2)
        self.docker.exec('/bin/sh -c "exit 7"', expect=None)

    def step3(self) -> None:
        """
        Test the directory context.

        :return: None.
        """
        with self.docker.cd('/tmp'):
            assertx(self.docker.exec('pwd'), '==', '/tmp')

    def step4(self) -> None:
        """
        Test file transfer.

        :return: None.
        """
        self.docker.putfile(self.local_file, self.remote_dir)
        self.docker.getfile(
            self.docker.join(self.remote_dir, 'file'),
            self.download_dir,
        )
        downloaded_file = os.path.join(self.download_dir, 'file')
        assertx(os.path.exists(downloaded_file), '==', True)
        with open(downloaded_file, encoding='utf-8') as local_file:
            assertx(local_file.read(), '==', 'xbot\n')

    def step5(self) -> None:
        """
        Test directory transfer.

        :return: None.
        """
        self.docker.putdir(self.local_tree, self.remote_dir)
        self.docker.getdir(
            self.docker.join(self.remote_dir, 'tree'),
            self.download_dir,
        )
        downloaded_nested = os.path.join(
            self.download_dir,
            'tree',
            'nested',
            'file',
        )
        assertx(os.path.exists(downloaded_nested), '==', True)
        with open(downloaded_nested, encoding='utf-8') as nested_file:
            assertx(nested_file.read(), '==', 'nested\n')

    def teardown(self) -> None:
        """
        Clean demo resources.

        :return: None.
        """
        try:
            self.docker.exec(
                f'rm -rf -- {self.remote_dir}',
                expect=None,
            )
        finally:
            shutil.rmtree(self.local_root, ignore_errors=True)
            self.testbed.disconnect()
