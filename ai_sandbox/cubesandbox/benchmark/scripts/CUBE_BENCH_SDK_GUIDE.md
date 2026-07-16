# `cube_bench_sdk.py` 使用指南

`cube_bench_sdk.py` 通过 CubeSandbox 的 E2B 兼容接口创建或连接 Sandbox，再通过 SDK 的命令执行与文件读取接口运行 `cube-bench-suite`。它适合从开发机、运维机或 CI 节点远程执行测试，不要求运行机能直接访问 Sandbox 的内部 IP。

脚本默认运行 `formal` 套件。使用 Template 新建 Sandbox 运行正式套件时，默认每个 case 使用一个全新的 Sandbox，以减少前一个 case 对后一个 case 的影响。

## 1. 运行前提

开始前必须满足以下条件：

- 运行机为 Linux，安装了 Python 3.10 或更高版本。
- 运行机能访问 CubeAPI，例如 `http://<cubeapi-host>:3000`。
- CubeSandbox 控制面、CubeProxy 和计算节点工作正常。
- 已有由 `cube-bench-suite` 镜像创建且状态为 `READY` 的 Template，或者已有从该 Template 启动且仍在运行的 Sandbox。
- Template 内 `/opt/cube-bench` 存在，`run-benchmark` 已加入 `PATH`。
- Template 已启动 envd，并暴露端口 `49983`；readiness probe 建议使用 `49983/health`。
- 运行正式套件时应准备足够的 CPU、内存、磁盘和可用 Sandbox 配额。默认正式套件有 19 个 case，逐 case 隔离时会创建 19 个 Sandbox。

`49999` 是 benchmark 镜像的辅助健康检查端口，建议暴露，但 SDK 脚本执行测试的必需端口是 `49983`。

## 2. 安装依赖

### 2.1 安装 Python 和基础工具

Ubuntu/Debian：

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip ca-certificates
```

RHEL/CentOS Stream/Rocky/AlmaLinux：

```bash
sudo dnf install -y python3 python3-pip ca-certificates
```

确认 Python 版本：

```bash
python3 --version
```

若版本低于 3.10，请先用操作系统的软件源安装 Python 3.10 或更高版本，并在下文用对应的解释器创建虚拟环境。

### 2.2 创建虚拟环境并安装 SDK

在项目根目录执行：

```bash
python3 -m venv .venv-cube-bench
source .venv-cube-bench/bin/activate
python -m pip install --upgrade pip
python -m pip install 'e2b-code-interpreter>=2.4,<3'
```

这里使用与本仓库 E2B 示例一致的主版本范围，避免未来不兼容的主版本升级影响测试。验证安装：

```bash
python -c 'from importlib.metadata import version; print(version("e2b-code-interpreter"))'
python -c 'from e2b_code_interpreter import Sandbox; print(Sandbox)'
```

每次打开新终端后，先重新激活环境：

```bash
source .venv-cube-bench/bin/activate
```

### 2.3 准备 benchmark Template

如果 Template 已经存在，可跳过本节。否则先将与计算节点架构匹配的镜像推送到节点可访问的 registry，然后创建 Template。示例：

```bash
cubemastercli tpl create-from-image \
  --image <registry>/cube-bench-suite:upstream-amd64 \
  --writable-layer-size 8G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health \
  --cpu 8000 \
  --memory 16000
```

ARM64 节点将镜像 tag 换成 `upstream-arm64`。记录返回的 `job_id` 和 `template_id`，等待构建完成：

```bash
cubemastercli tpl watch --job-id <job_id>
cubemastercli tpl info --template-id <template_id>
```

必须确认 Template 为 `READY`。镜像导入、registry 推送和 Template 资源参数的完整说明见项目根目录的 `BENCHMARK_REUSE.md`。

## 3. 配置连接信息

推荐用环境变量保存常用连接信息：

```bash
export E2B_API_URL='http://<cubeapi-host>:3000'
export E2B_API_KEY='e2b_000000'
export CUBE_TEMPLATE_ID='<template_id>'
```

变量含义：

| 变量 | 是否必需 | 说明 |
|---|---:|---|
| `E2B_API_URL` | 是 | CubeAPI 的 E2B 兼容接口地址，也可用 `--api-url` 传入。 |
| `E2B_API_KEY` | 是 | API key；未启用鉴权的本地部署通常使用任意非空值，脚本默认 `e2b_000000`。 |
| `CUBE_TEMPLATE_ID` | 新建时是 | 用于创建 Sandbox 的 Template ID，也可用 `--template-id` 传入。 |
| `SSL_CERT_FILE` | 视部署而定 | CubeProxy 使用私有或 mkcert CA 时的根证书文件。 |
| `CUBE_SSL_CERT_FILE` | 否 | 脚本专用证书变量；设置后优先于 `SSL_CERT_FILE`。 |

如果 CubeProxy 使用 Cube 的 mkcert CA，证书必须位于运行脚本的宿主机，而不是 Sandbox 内：

```bash
export SSL_CERT_FILE='/path/to/rootCA.pem'
test -r "$SSL_CERT_FILE"
```

也可以不设置变量，在命令中传入 `--ssl-cert-file /path/to/rootCA.pem`。脚本会将该值写入当前进程的 `SSL_CERT_FILE`，供 SDK 的 HTTPS 客户端使用。

## 4. 运行前检查

先确认脚本可解析、SDK 已安装并查看 case：

```bash
python scripts/cube_bench_sdk.py --help
python scripts/cube_bench_sdk.py --suite smoke --list-cases
python scripts/cube_bench_sdk.py --suite formal --list-cases
```

`--list-cases` 只打印 case、超时时间和实际命令，不会创建 Sandbox，也不要求设置 API 地址或 Template ID。

## 5. 常用运行方式

### 5.1 先运行 smoke 套件

建议首次接入先在单个 Sandbox 中运行 smoke：

```bash
python scripts/cube_bench_sdk.py \
  --suite smoke \
  --single-sandbox \
  --results-dir ./results/sdk-smoke \
  --delete
```

脚本创建一个 Sandbox，顺序运行 8 个 smoke case，生成报告和压缩包，最后关闭 Sandbox。

### 5.2 运行正式套件

```bash
python scripts/cube_bench_sdk.py \
  --suite formal \
  --isolate-cases \
  --results-dir ./results/sdk-formal \
  --delete
```

正式套件使用 Template 新建 Sandbox 时，省略 `--isolate-cases` 也会默认逐 case 隔离。建议显式写出该选项，让运行方式在日志和命令历史中更清楚。

正式测试耗时较长，Python rigorous case 的单 case 超时为 3600 秒。`--sandbox-timeout` 默认 7200 秒，表示 Sandbox 生命周期，不是每个 benchmark 的命令超时。

### 5.3 只运行指定 case

`--case` 可以重复，既可使用完整名称，也可省略数字前缀：

```bash
python scripts/cube_bench_sdk.py \
  --suite formal \
  --case versions \
  --case sysbench-memory-seq-read-formal \
  --case sysbench-prime-10000 \
  --isolate-cases \
  --delete
```

case 必须属于 `--suite` 选择的套件。传入未知名称时脚本会直接报错。

### 5.4 复用已有 Sandbox

```bash
python scripts/cube_bench_sdk.py \
  --sandbox-id <sandbox_id> \
  --suite smoke \
  --results-dir ./results/sdk-existing
```

复用已有 Sandbox 时只能使用单 Sandbox 模式，不能同时指定 `--isolate-cases`。已安装的 SDK 必须提供 `Sandbox.connect`、`from_id` 或 `reconnect` 之一；否则应改用 Template 新建 Sandbox，或使用 `cube_bench_reusable.py` 并传入 Sandbox IP。

`--delete` 对已有 Sandbox 同样生效。若该 Sandbox 仍有其他用途，不要传入 `--delete`。

### 5.5 使用命令行参数代替环境变量

```bash
python scripts/cube_bench_sdk.py \
  --api-url 'http://<cubeapi-host>:3000' \
  --api-key 'e2b_000000' \
  --template-id '<template_id>' \
  --ssl-cert-file '/path/to/rootCA.pem' \
  --suite smoke \
  --single-sandbox \
  --delete
```

## 6. 测试套件

### 6.1 Smoke 套件

Smoke 套件包含 8 个 case：

| case | 用途 |
|---|---|
| `versions` | 记录镜像、工具链和 benchmark 版本。 |
| `sysbench-memory-all` | 5 秒、2 线程的内存四象限快速检查。 |
| `sysbench-prime` | 5 秒、2 线程、最大素数 5000 的 CPU 快速检查。 |
| `go-benchmark` | Go 子测试各运行 1 次。 |
| `php-benchmark` | 使用 100000 iterations。 |
| `python-benchmark` | fast 模式，只跑 `python_startup,json_dumps`。 |
| `node-octane` | 运行 Node Octane。 |
| `java-scimark` | 运行 Java SciMark。 |

### 6.2 Formal 套件

Formal 套件包含：

- 1 个版本记录 case。
- 4 个 sysbench memory case：顺序读、顺序写、随机读、随机写；固定 2 线程、30 秒、1G block、100G total size。
- 9 个 sysbench prime case：最大素数依次为 `1000,2000,3000,5000,10000,20000,30000,50000,100000`，固定 2 线程、30 秒。
- Go、PHP、Python、Node 和 Java 正式 case；其中 Go 重复 3 次，PHP 使用 2000000 iterations，Python 使用 rigorous 模式。

随脚本版本变化时，以 `--list-cases` 输出为准。

## 7. 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--api-url` | `E2B_API_URL` | CubeAPI 地址，运行测试时必需。 |
| `--api-key` | `E2B_API_KEY` 或 `e2b_000000` | SDK API key。 |
| `--ssl-cert-file` | `CUBE_SSL_CERT_FILE` 或 `SSL_CERT_FILE` | 私有 CA 根证书路径。 |
| `--template-id` | `CUBE_TEMPLATE_ID` | 新建 Sandbox 使用的 Template ID。 |
| `--sandbox-id` | 无 | 连接已有 Sandbox。 |
| `--sandbox-timeout` | `7200` | 新建 Sandbox 的生命周期，单位为秒。 |
| `--results-dir` | 带时间戳的 `cube-bench-sdk-results-*` | 宿主机结果目录。 |
| `--suite` | `formal` | 选择 `smoke` 或 `formal`。 |
| `--case` | 全套 | 只运行指定 case；可重复。 |
| `--cwd` | `/opt/cube-bench` | Sandbox 内执行命令的工作目录。 |
| `--sandbox-out-dir` | `/tmp/cube-bench-sdk` | Sandbox 内保存完整日志的目录。 |
| `--delete` | 关闭 | 测试后 kill/close Sandbox。 |
| `--no-tar` | 关闭 | 不生成结果 `.tar.gz`。 |
| `--no-report` | 关闭 | 不生成 `benchmark-report.md`。 |
| `--list-cases` | 关闭 | 列出所选套件的 case 后退出。 |
| `--isolate-cases` | 正式新建时默认开启 | 每个 case 创建一个 Sandbox。 |
| `--single-sandbox` | smoke 或已有 Sandbox 时默认 | 所有 case 共用一个 Sandbox。 |

## 8. 结果与退出码

结果根目录包含：

- `run-context.json`：本次参数、case、运行方式和开始时间。
- `summary.json`：所有 case 的 Sandbox ID、退出码、耗时和日志大小。
- `benchmark-report.md`：从输出中提取的状态及主要指标。
- `sandbox.json`：单 Sandbox 模式的 Sandbox 信息。
- `<results-dir>.tar.gz`：整个结果目录的归档，除非使用 `--no-tar`。

单 Sandbox 模式下，每个 case 的文件直接位于结果根目录。隔离模式下，每个 case 位于同名子目录，包含：

- `<case>.cmd`：原始 benchmark 命令。
- `<case>.sdk_cmd`：SDK 实际执行的 shell 命令。
- `<case>.log`：从 Sandbox 文件系统读取的完整日志。
- `<case>.stdout.log`、`<case>.stderr.log`：SDK 返回的标准输出和标准错误。
- `<case>.result.json`：SDK 返回值、退出码和异常信息。
- `sandbox.json`：该 case 使用的 Sandbox 信息。
- `delete-sandbox.txt`：使用 `--delete` 时的清理结果。

脚本在所有 case 的退出码均为 `0` 时返回 `0`；任一 case 失败时返回 `1`。SDK 调用或结果读取发生异常时，该 case 通常记录为 `255`。自动生成的报告是便于浏览的解析结果，正式归档仍应保留原始 `.log` 和 `.result.json`。

## 9. 注意事项与排查

### `ModuleNotFoundError: e2b_code_interpreter`

确认已激活虚拟环境并重新安装：

```bash
source .venv-cube-bench/bin/activate
python -m pip install 'e2b-code-interpreter>=2.4,<3'
```

### API 地址缺失或连接失败

确认 `E2B_API_URL` 指向 CubeAPI，不是 CubeProxy，也不是 Sandbox IP：

```bash
printf '%s\n' "$E2B_API_URL"
```

同时检查运行机到 CubeAPI 的路由、防火墙和端口映射。

### TLS 证书错误

确认根证书存在且可读，并通过 `--ssl-cert-file` 或 `SSL_CERT_FILE` 传入。不要用 `--insecure`，SDK 脚本没有该选项。

### 创建成功但命令无法执行

优先检查 Template 是否暴露并启动 `49983` envd，readiness probe 是否为 `49983/health`，以及镜像中是否存在 `/opt/cube-bench` 和 `run-benchmark`。

### 正式运行后残留多个 Sandbox

逐 case 隔离会创建多个 Sandbox，只有传入 `--delete` 才会在各 case 完成后主动清理。发生进程中断或创建阶段异常时仍可能残留 Sandbox，应通过 CubeSandbox 管理命令检查并手动删除。

### 报告中某些指标为空

报告生成器按已知输出格式提取指标。上游 benchmark 输出格式变化时，case 仍可能成功但解析列为空；以 `<case>.log` 和 `<case>.result.json` 为准。
