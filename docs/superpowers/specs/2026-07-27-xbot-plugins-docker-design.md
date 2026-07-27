# xbot.plugins.docker 设计

## 目标

`xbot.plugins.docker` 是为 `xbot.framework` 提供 Docker 容器命令执行和
文件传输能力的插件。

项目的目录结构、公开接口、命令结果、异常、日志、测试、示例、README
和打包方式尽量与 `xbot.plugins.ssh` 对齐。Docker 命令执行与文件传输的
底层机制参考 `xflow.framework.container.py`，但本项目不依赖
`xbot.plugins.ssh` 或 `xflow.framework`。

首版只实现核心功能：

- 连接远程 TCP/TLS Docker daemon；
- 连接已有的运行中容器；
- 从镜像创建临时容器；
- 在容器内执行命令；
- 上传和下载文件及目录；
- 管理连接创建的临时容器。

首版不支持本机 Unix socket、SSH Docker context、交互式命令、
`sudo()`、远程文件流 `open()`、自动拉取镜像、自动启动已有容器、
连接重试或自动恢复。

## 项目结构

```text
xbot.plugins.docker/
├── README.md
├── README.zh.md
├── LICENSE
├── pyproject.toml
├── setup.py
├── xbot/plugins/docker/
│   ├── __init__.py
│   ├── docker.py
│   ├── errors.py
│   ├── utils.py
│   ├── version.py
│   └── py.typed
├── tests/
│   ├── run.py
│   ├── test_docker.py
│   └── test_utils.py
├── demo/
└── docs/
```

`docker.py` 中的单一 `DockerConnection` 同时提供命令执行和文件传输。
两类操作共享同一个 Docker client 和容器，避免镜像模式因两个连接而
创建两个不同的临时容器。

`DockerCommandResult` 与 `DockerConnection` 位于 `docker.py`。
`errors.py` 定义项目异常，`utils.py` 提供输出清理函数，
`version.py` 是运行时和打包版本的唯一来源。

## 连接接口

`DockerConnection` 的构造函数只接收并保存连接级默认 `shenvs`。实现时
使用 `None` 作为可变参数默认值，避免不同实例共享字典。

`connect()` 的公开形式为：

```python
connect(
    host,
    container=None,
    image=None,
    port=2375,
    user=None,
    runargs=None,
    timeout=5,
    cacert=None,
    clientcert=None,
    clientkey=None,
)
```

参数语义：

- `host` 和 `port` 指定远程 Docker daemon；
- `container` 是已有容器的名称或 ID；
- `image` 是用于创建临时容器的镜像名称或 ID；
- `container` 与 `image` 必须且只能指定一个；
- `user` 是容器内执行命令的用户，不是 Docker daemon 用户；
- `runargs` 原样传给 `DockerClient.containers.run()`；
- `timeout` 是 Docker client API 请求超时；
- `cacert`、`clientcert` 和 `clientkey` 用于 TLS；
- `clientcert` 与 `clientkey` 必须成对指定。

`container`/`image` 互斥关系或客户端证书配对不合法属于调用参数错误，
抛出 `ValueError`。只有与 daemon 通信、查找目标或创建容器时的失败才
转换为 `DockerConnectError`。

连接远程 daemon 时创建
`DockerClient(base_url='tcp://<host>:<port>', tls=..., timeout=...)`。

已有容器模式调用 `containers.get(container)`。如果容器状态不是
`running`，则关闭 Docker client 并抛出 `DockerConnectError`。库不启动
已有容器，也不改变其生命周期。

镜像模式调用
`containers.run(image, detach=True, **runargs)`。库不检查创建后的容器
是否仍在运行，也不覆盖镜像的 `ENTRYPOINT` 或 `CMD`。需要常驻进程时，
调用者通过 `runargs['command']` 指定。

同一连接已建立时，重复调用 `connect()` 直接返回。

## 断开接口与所有权

`disconnect()` 根据容器来源处理资源：

- 镜像模式创建的临时容器执行 `remove(force=True)`；
- 已有容器不停止、不删除；
- 无论容器清理是否成功，最终都关闭 Docker client；
- 临时容器删除失败时，在关闭 client 后将原始删除异常交给调用者；
- 未连接或已经断开的连接再次调用 `disconnect()` 时直接返回。

一个 `DockerConnection` 同时只管理一个 Docker client 和一个容器。
命令或文件方法不提供自动连接能力；调用者必须先显式调用 `connect()`。

## 命令执行

`exec()` 的公开形式为：

```python
exec(
    cmd,
    expect=0,
    timeout=15,
    shenvs=None,
)
```

连接级环境变量默认包含：

```text
LANG=en_US.UTF-8
LANGUAGE=en_US.UTF-8
```

命令级 `shenvs` 覆盖同名连接级环境变量。

命令通过 `['/bin/sh', '-c', cmd]` 执行。首版要求容器提供 `/bin/sh`；
不含该程序的镜像由 Docker 返回执行错误。

`cd(path)` 是上下文管理器。进入上下文后，`exec()` 将实际命令构造为
`cd <path> && <cmd>`；退出时恢复空工作目录。`cd()` 使用锁，保持与
`SSHConnection.cd()` 相同的单连接上下文隔离方式。

执行使用 Docker exec socket 合并读取 stdout 和 stderr，以支持命令
超时。超时后抛出 `TimeoutError` 并断开 exec 数据流；首版不额外终止
容器内仍在运行的进程。

首版不支持 `prompts` 参数或交互式 stdin。

## 命令结果与期望判断

`DockerCommandResult` 是 `str` 子类，行为与 `SSHCommandResult` 对齐：

- 字符串值是清理 ANSI 转义字符和不可打印字符后的合并输出；
- `rc` 保存命令返回码；
- `cmd` 保存实际执行命令；
- `getfield()` 按关键字或行号读取指定字段；
- `getcol()` 读取指定列。

`expect` 支持：

- 整数：实际返回码必须等于该值；
- 字符串：清理后的输出必须包含该字符串；
- `None`：不检查返回码或输出。

期望不满足时抛出 `DockerCommandError`，错误信息包含实际命令、期望值、
返回码和输出。

## 文件与目录

文件接口与 `SFTPConnection` 的命名和目标路径语义对齐：

- `getfile(rfile, ldir, filename=None)`；
- `putfile(lfile, rdir, filename=None)`；
- `getdir(rdir, ldir)`；
- `putdir(ldir, rdir)`；
- `exists(path)`；
- `makedirs(path)`；
- `join(*paths)`；
- `normpath(path)`；
- `basename(path)`。

`getfile()` 和 `getdir()` 使用容器的 `get_archive()` 获取 tar 数据并解包
到本地目标目录。`filename` 用于下载时重命名。`getdir(rdir, ldir)` 的
结果是 `ldir/basename(rdir)`，保留远端顶层目录名。

`putfile()` 和 `putdir()` 在内存中创建 tar 数据，再使用
`put_archive()` 上传。上传目标目录不存在时先调用 `makedirs()`。
`filename` 用于上传时重命名。`putdir(ldir, rdir)` 的结果是
`rdir/basename(ldir)`，保留本地顶层目录名。

上传 tar 条目的 UID/GID 设置为 `user` 在容器中的 UID/GID；未指定
`user` 时使用 Docker exec 的默认用户。UID/GID 通过容器命令获取并在
连接生命周期内缓存。

`exists()` 和 `makedirs()` 使用 `/bin/sh` 命令实现。所有容器路径使用
POSIX 语义，路径辅助方法不依赖宿主系统路径格式。

首版不实现 `open()`。Docker 没有与 SFTP 远程文件流等价的接口，模拟
关闭时回传会扩大首版范围并引入不同语义。

## 异常

项目定义两个异常：

- `DockerConnectError`：daemon 连接、TLS 配置、目标查找、已有容器
  状态或临时容器创建失败；
- `DockerCommandError`：命令结果不符合 `expect`。

命令超时使用内置 `TimeoutError`。文件传输中的本地文件错误和 Docker
API 错误不额外包装，以保留原始错误信息。

## 日志

使用 `xbot.framework.logger.getlogger()` 和 `ExtraAdapter`，与 SSH 插件
保持一致。日志前缀形式为：

```text
docker://root@192.168.8.8:2375/existing-container
docker://root@192.168.8.8:2375/alpine:latest->created-container
```

日志记录连接、命令、期望、传输方向和必要输出，不记录证书内容。

## 测试

所有测试只能通过 `tests/run.py` 执行。测试文件使用 `unittest` 组织，
由 `tests/run.py` 统一配置、discover 和运行，并根据
`result.wasSuccessful()` 返回进程退出码。

`tests/run.py` 同时执行：

- 不依赖 daemon 的结果类、工具函数和 mocked Docker 单元测试；
- 依赖远程 daemon 的真实命令、文件传输和生命周期测试；
- 各模块中的 doctest。

正式测试入口需要以下参数：

```text
-H/--host
-P/--port
-i/--image
--cacert
--clientcert
--clientkey
```

远程 daemon 中必须已经存在指定镜像，测试不自动拉取镜像。真实测试
执行以下场景：

1. 使用镜像连接，验证命令、环境变量、三种 `expect`、超时、`cd()`、
   命令结果和文件传输；
2. 断开后从 daemon 检查临时容器已删除；
3. 使用同一镜像创建测试夹具容器，再按已有容器模式连接；
4. 验证已有容器断开后仍存在且仍在运行；
5. 验证停止容器会被拒绝；
6. 删除所有测试容器、容器内测试文件和本地临时目录；
7. 对成功、失败和清理结果给出统一测试汇总和退出码。

远程参数缺失时由参数解析直接报错，不静默跳过真实测试。测试清理放在
可靠的 teardown 路径中，即使断言失败也执行。

类型检查、构建和 `twine check` 属于项目验证，不由 `tests/run.py`
执行，也不描述为测试。

## README 与示例

`README.md` 和 `README.zh.md` 章节严格对齐 SSH 项目：

- Introduction / 简介；
- Installation / 安装；
- Get Started / 入门；
- Demo / 示例项目。

两个 README 内容一一对应。入门示例覆盖：

- 连接已有容器；
- 从镜像创建临时容器；
- `exec()` 的三种 `expect`；
- `DockerCommandResult`；
- `cd()`；
- 文件和目录上传下载；
- `disconnect()`。

README 不增加测试、开发、构建或内部设计章节。

`demo/` 必须先通过 `xbot init -d demo` 初始化标准 xbot 项目，再基于
生成结果添加 Docker TestBed、TestCase、testbed、testset 和 testcase，
不能从空目录手工搭建。删除初始化产生的通用示例，保留标准项目外围文件。
TestBed 缓存 `DockerConnection`，示例展示命令执行和文件传输，并在
teardown 中断开连接和清理本地测试数据。

## 打包

打包布局对齐当前 `xbot.plugins.ssh`：

- PEP 621 `pyproject.toml`；
- 构建后端为 `setuptools.build_meta`；
- Python 要求为 `>=3.10`；
- 依赖为 `xbot.framework>=0.5.1` 和 `docker`；
- 初始版本为 `0.1.0`；
- `xbot.plugins.docker.version.__version__` 是唯一版本源；
- 包含 `py.typed`；
- 使用 BSD-2-Clause；
- 中英文 README 构建钩子与 SSH 项目保持一致；
- 项目 URL 指向 `xbot.plugins.docker` 仓库。

项目验证包括：

- 通过 `tests/run.py` 完成全部测试；
- 类型检查；
- 构建 wheel 和 sdist；
- `twine check`；
- 检查归档中的源码、README、许可证、类型标记和测试入口。

本次范围不包括 TestPyPI、PyPI、git tag 或 GitHub Release。

## 完成标准

项目完成需要同时满足：

1. 公开接口和外围项目结构按本设计与 SSH 插件对齐；
2. 命令与文件传输通过真实远程 Docker daemon 验证；
3. 镜像临时容器在 `disconnect()` 和测试 teardown 后均被删除；
4. 已有容器不被启动、停止或删除；
5. 所有测试均由 `tests/run.py` 执行并返回可信退出码；
6. 本地测试数据和远程测试资源清理完毕；
7. 类型检查和发行包验证通过；
8. README 只包含与 SSH 项目对应的四个章节。
