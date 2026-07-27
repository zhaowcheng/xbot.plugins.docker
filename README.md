<p align="center">
  <br>English | <a href="README.zh.md">中文</a>
</p>

***

## Introduction

`xbot.plugins.docker` provides Docker support for [xbot.framework](https://github.com/zhaowcheng/xbot.framework).

## Installation

Install via pip:

```
pip install xbot.plugins.docker
```

## Get Started

```python
import os
import shutil

from xbot.plugins.docker.docker import DockerConnection

host = '192.168.8.8'

container_conn = DockerConnection()
container_conn.connect(
    host,
    container='existing-container',
    user='root',
)
container_conn.exec('echo hello', expect=0)
container_conn.disconnect()

image_conn = DockerConnection()
image_conn.connect(
    host,
    image='alpine:latest',
    runargs={'command': 'sleep infinity'},
    user='root',
)

image_conn.exec('echo hello', expect=0)
image_conn.exec('/bin/sh -c "exit 2"', expect=2)
image_conn.exec('echo hello', expect='hello')
image_conn.exec('/bin/sh -c "exit 7"', expect=None)

result = image_conn.exec('echo "jack 20"; echo "tom 30"')
assert str(result) == 'jack 20\ntom 30'
assert result.rc == 0
assert result.getfield('tom', 2) == '30'
assert result.getcol(2) == ['20', '30']

with image_conn.cd('/tmp'):
    assert image_conn.exec('pwd') == '/tmp'

local_home = os.environ.get('HOME') or os.environ['HOMEPATH']
local_put_dir = os.path.join(local_home, 'docker-put-dir')
local_get_dir = os.path.join(local_home, 'docker-get-dir')
remote_dir = '/tmp/docker-put-get-dir'
shutil.rmtree(local_put_dir, ignore_errors=True)
shutil.rmtree(local_get_dir, ignore_errors=True)
os.makedirs(os.path.join(local_put_dir, 'tree', 'nested'))
os.makedirs(local_get_dir)
with open(
    os.path.join(local_put_dir, 'file'),
    'w',
    encoding='utf-8',
) as local_file:
    local_file.write('xbot\n')

image_conn.makedirs(remote_dir)
image_conn.putfile(
    os.path.join(local_put_dir, 'file'),
    remote_dir,
)
image_conn.putfile(
    os.path.join(local_put_dir, 'file'),
    remote_dir,
    filename='renamed',
)
image_conn.putdir(
    os.path.join(local_put_dir, 'tree'),
    remote_dir,
)
image_conn.getfile(
    image_conn.join(remote_dir, 'file'),
    local_get_dir,
)
image_conn.getfile(
    image_conn.join(remote_dir, 'file'),
    local_get_dir,
    filename='renamed',
)
image_conn.getdir(
    image_conn.join(remote_dir, 'tree'),
    local_get_dir,
)

image_conn.disconnect()
```

## Demo

Here is a [demo](https://github.com/zhaowcheng/xbot.plugins.docker/tree/master/demo) project showing how to use `xbot.plugins.docker` in a test project.
