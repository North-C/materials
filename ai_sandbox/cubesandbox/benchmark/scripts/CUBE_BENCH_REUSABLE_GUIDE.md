# `cube_bench_reusable.py` 使用指南

`cube_bench_reusable.py` 直接调用 CubeAPI 的 REST 接口创建、查询和删除 Sandbox，并通过 Sandbox 内网 IP 的 envd `49983` 端口运行 `cube-bench-suite`。脚本只使用 Python 标准库，不依赖 E2B SDK，适合复制到 CubeSandbox 控制节点、计算节点或能同时访问 CubeAPI 与 Sandbox 内网的运维机上运行。

脚本默认运行 `formal` 套件。使用 Template 新建 Sandbox 运行正式套件时，默认每个 case 使用一个新的 Sandbox。

## 1. 运行前提

开始前必须满足以下条件：

- 运行机为 Linux，安装了 Python 3.10 或更高版本。
- 运行机能访问 CubeAPI，默认地址为 `http://127.0.0.1:3000`。
- 运行机能直接访问 Sandbox 内网 IP 的 TCP `49983` 和 `49999` 端口。
- CubeSandbox 服务正常，已有 `READY` 状态的 benchmark Template，或者已有从该 Template 启动的 Sandbox。
- Template 来自 `cube-bench-suite` 镜像，包含 `/opt/cube-bench` 和 `run-benchmark`。
- Template 已启动并暴露 envd `49983`；建议同时暴露 benchmark health server `49999`。
- 自动解析 Sandbox IP 时，`cubemastercli` 必须在 `PATH` 中。只有复用单个 Sandbox 且显式传入 `--sandbox-ip` 时才可省略它。
- 正式逐 case 隔离模式必须安装 `cubemastercli`，因为每个新 Sandbox 都需要单独解析 IP。

该脚本不能通过公网 CubeProxy 转发 envd 命令。若运行机无法直达 Sandbox 内网，应使用 `cube_bench_sdk.py`。

## 2. 安装依赖

### 2.1 安装 Python

Ubuntu/Debian：

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv ca-certificates
```

RHEL/CentOS Stream/Rocky/AlmaLinux：

```bash
sudo dnf install -y python3 ca-certificates
```

确认版本：

```bash
python3 --version
```

脚本不需要执行 `pip install`。它使用的 `argparse`、`urllib`、`ssl`、`subprocess`、`tarfile` 等模块都随 Python 标准库提供。若 Python 版本低于 3.10，请先从操作系统软件源安装 Python 3.10 或更高版本。

可用以下命令验证脚本所需标准库：

```bash
python3 -c 'import argparse, base64, json, ssl, struct, subprocess, tarfile, urllib.request; print("stdlib ok")'
```

### 2.2 安装或获取 `cubemastercli`

CubeSandbox 的一键部署会将 `cubemastercli` 链接到 `/usr/local/bin`。先检查：

```bash
command -v cubemastercli
cubemastercli --help
```

如果 CubeSandbox 已部署但命令不在 `PATH`，找到部署目录中的二进制并安装到系统路径：

```bash
sudo install -m 0755 /path/to/cubemastercli /usr/local/bin/cubemastercli
```

如果只有本仓库源代码，也可以用与 `source_code/CubeSandbox/CubeMaster/go.mod` 匹配的 Go 工具链构建：

```bash
cd source_code/CubeSandbox/CubeMaster
go build -o /tmp/cubemastercli ./cmd/cubemastercli
sudo install -m 0755 /tmp/cubemastercli /usr/local/bin/cubemastercli
cd -
```

构建前先执行 `go version`，并确保版本满足该 `go.mod` 中的 `go` 指令。若不希望安装 `cubemastercli`，只能使用已有 Sandbox，并同时传入 `--sandbox-id`、`--sandbox-ip` 和 `--single-sandbox`。

### 2.3 准备 benchmark Template

如果已有可用 Template，可跳过本节。示例创建命令：

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

ARM64 节点使用 `upstream-arm64` 镜像。记录命令返回的 `job_id` 和 `template_id`，等待 Template 就绪：

```bash
cubemastercli tpl watch --job-id <job_id>
cubemastercli tpl info --template-id <template_id>
```

正式 benchmark 的资源规格必须在各次对比中保持一致。镜像导入和 registry 推送步骤见项目根目录的 `BENCHMARK_REUSE.md`。

## 3. 网络和服务检查

默认 CubeAPI 可通过环境变量覆盖：

```bash
export CUBE_API='http://127.0.0.1:3000'
```

已有 Sandbox 时先获取或确认内网 IP：

```bash
cubemastercli cubebox info --sandboxid <sandbox_id>
```

脚本从输出中以 `SANDBOX_IP` 开头的行读取 IP。确认运行机能访问健康端点：

```bash
python3 -c 'import urllib.request; print(urllib.request.urlopen("http://<sandbox_ip>:49983/health", timeout=5).status)'
python3 -c 'import urllib.request; print(urllib.request.urlopen("http://<sandbox_ip>:49999/health", timeout=5).status)'
```

`49983` 是执行命令的必要端口。`49999` 只用于记录 benchmark health 状态；它失败时脚本会把错误写入 `health.txt`，但仍会尝试运行 case。

## 4. 运行前检查

```bash
python3 scripts/cube_bench_reusable.py --help
python3 scripts/cube_bench_reusable.py --suite smoke --list-cases
python3 scripts/cube_bench_reusable.py --suite formal --list-cases
```

`--list-cases` 不访问 CubeAPI、不创建 Sandbox，也不要求提供 Template 或 Sandbox 参数。

## 5. 常用运行方式

### 5.1 首次运行 smoke 套件

建议先用一个 Sandbox 验证控制面、IP 解析和 envd 通道：

```bash
python3 scripts/cube_bench_reusable.py \
  --cube-api http://127.0.0.1:3000 \
  --template-id <template_id> \
  --suite smoke \
  --single-sandbox \
  --results-dir ./results/reusable-smoke \
  --delete
```

脚本会创建一个 Sandbox，解析其 IP，检查两个健康端口，顺序运行 8 个 smoke case，生成报告和压缩包，最后删除 Sandbox。

### 5.2 正式逐 case 隔离运行

```bash
python3 scripts/cube_bench_reusable.py \
  --cube-api http://127.0.0.1:3000 \
  --template-id <template_id> \
  --suite formal \
  --isolate-cases \
  --results-dir ./results/reusable-formal \
  --delete
```

通过 Template 新建 Sandbox 且选择 `formal` 时，省略 `--isolate-cases` 也会默认逐 case 隔离。正式套件共有 19 个 case，因此该模式会依次创建 19 个 Sandbox；请确认配额，并建议始终传入 `--delete`。

### 5.3 正式套件共用一个 Sandbox

若资源有限或只验证可运行性，可以显式复用一个 Sandbox：

```bash
python3 scripts/cube_bench_reusable.py \
  --template-id <template_id> \
  --suite formal \
  --single-sandbox \
  --delete
```

同一 Sandbox 中前序测试产生的缓存、温度和文件状态可能影响后续结果，因此该模式不适合作为严格隔离的对比基准。

### 5.4 只运行指定 case

```bash
python3 scripts/cube_bench_reusable.py \
  --template-id <template_id> \
  --suite formal \
  --case versions \
  --case sysbench-memory-rnd-read-formal \
  --case sysbench-prime-20000 \
  --isolate-cases \
  --delete
```

`--case` 可重复。case 必须属于 `--suite` 指定的套件，可使用完整名称或去掉最前面的数字前缀。

### 5.5 复用已有 Sandbox，并由 CLI 解析 IP

```bash
python3 scripts/cube_bench_reusable.py \
  --sandbox-id <sandbox_id> \
  --suite smoke \
  --results-dir ./results/reusable-existing
```

### 5.6 没有 `cubemastercli` 时复用已有 Sandbox

```bash
python3 scripts/cube_bench_reusable.py \
  --cube-api http://<cubeapi-host>:3000 \
  --sandbox-id <sandbox_id> \
  --sandbox-ip <sandbox_ip> \
  --suite smoke \
  --single-sandbox \
  --results-dir ./results/reusable-existing
```

这种方式不能使用 `--isolate-cases`，因为脚本无法解析每个新 Sandbox 的 IP。

### 5.7 HTTPS CubeAPI

系统信任 CubeAPI 的 CA 时直接使用 HTTPS 地址：

```bash
export SSL_CERT_FILE='/path/to/rootCA.pem'
python3 scripts/cube_bench_reusable.py \
  --cube-api https://<cubeapi-host>:3000 \
  --template-id <template_id> \
  --suite smoke \
  --single-sandbox \
  --delete
```

仅在临时诊断且无法安装 CA 时使用：

```bash
python3 scripts/cube_bench_reusable.py \
  --cube-api https://<cubeapi-host>:3000 \
  --template-id <template_id> \
  --suite smoke \
  --single-sandbox \
  --insecure \
  --delete
```

`--insecure` 只关闭 CubeAPI HTTPS 证书校验；envd 仍通过 Sandbox 内网的 HTTP `49983` 访问。生产环境不应长期使用该选项。

## 6. 测试套件

### 6.1 Smoke 套件

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

Formal 套件包括：

- 1 个版本记录 case。
- 4 个 sysbench memory case：顺序读、顺序写、随机读、随机写；固定 2 线程、30 秒、1G block、100G total size。
- 9 个 sysbench prime case：最大素数为 `1000,2000,3000,5000,10000,20000,30000,50000,100000`，固定 2 线程、30 秒。
- Go、PHP、Python、Node 和 Java 正式 case；Go 重复 3 次，PHP 使用 2000000 iterations，Python 使用 rigorous 模式。

准确命令和每个 case 的超时时间以 `--list-cases` 输出为准。

## 7. 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--cube-api` | `CUBE_API` 或 `http://127.0.0.1:3000` | CubeAPI REST 地址。 |
| `--template-id` | 无 | 新建 Sandbox 使用的 Template ID。 |
| `--sandbox-id` | 无 | 复用已有 Sandbox。与 `--template-id` 至少提供一个。 |
| `--sandbox-ip` | 无 | 已有 Sandbox 的内网 IP；无 `cubemastercli` 时必需。 |
| `--sandbox-timeout` | `7200` | 新建 Sandbox 生命周期，单位为秒。 |
| `--results-dir` | 带时间戳的 `cube-bench-results-*` | 宿主机结果目录。 |
| `--suite` | `formal` | 选择 `smoke` 或 `formal`。 |
| `--case` | 全套 | 只运行指定 case；可重复。 |
| `--cwd` | `/opt/cube-bench` | Sandbox 内的命令工作目录。 |
| `--delete` | 关闭 | 运行后删除脚本创建或复用的 Sandbox。 |
| `--no-tar` | 关闭 | 不生成结果 `.tar.gz`。 |
| `--no-report` | 关闭 | 不生成 `benchmark-report.md`。 |
| `--insecure` | 关闭 | 禁用 CubeAPI HTTPS 证书校验。 |
| `--list-cases` | 关闭 | 打印 case 后退出。 |
| `--isolate-cases` | 正式新建时默认开启 | 每个 case 新建一个 Sandbox。 |
| `--single-sandbox` | smoke 或已有 Sandbox 时默认 | 所有 case 共用一个 Sandbox。 |

`--delete` 会删除通过 `--sandbox-id` 传入的已有 Sandbox。复用仍有其他任务的 Sandbox 时不要使用该参数。

## 8. 结果与退出码

结果根目录包含：

- `run-context.json`：本次连接参数、case、隔离模式和开始时间。
- `summary.json`：每个 case 的 Sandbox ID、IP、返回码和耗时。
- `benchmark-report.md`：解析后的执行状态及主要指标。
- `sandbox.json`：单 Sandbox 模式下的 CubeAPI Sandbox 信息。
- `health.txt`：`49983` 和 `49999` 健康检查结果。
- `<results-dir>.tar.gz`：结果目录归档，除非使用 `--no-tar`。

单 Sandbox 模式下，case 文件位于结果根目录。隔离模式下，每个 case 使用同名子目录，包含：

- `<case>.cmd`：执行的 benchmark 命令。
- `<case>.stdout`、`<case>.stderr`：envd 返回的标准输出和标准错误。
- `<case>.rc`：命令返回码。
- `<case>.events.json`：解码后的 Connect 事件帧。
- `<case>.raw`：envd 原始响应流，便于协议层排查。
- `sandbox.json`、`health.txt`：该 case 使用的 Sandbox 信息和健康检查。
- `delete-sandbox.txt`：使用 `--delete` 时的 HTTP 删除结果。

全部 case 的 `rc` 为 `0` 时脚本返回 `0`；任一 case 非零时脚本返回 `1`。envd 请求、协议解析或网络异常通常会将 case 记为 `rc=255`。报告只是对已知输出格式的自动解析，正式归档应同时保留 `.stdout`、`.events.json` 和 `.raw`。

## 9. 注意事项与排查

### `cubemastercli is required unless --sandbox-ip is provided`

安装 `cubemastercli` 并加入 `PATH`，或者改为复用已有 Sandbox，同时提供 `--sandbox-id`、`--sandbox-ip` 和 `--single-sandbox`。

### `could not find SANDBOX_IP`

手动运行：

```bash
cubemastercli cubebox info --sandboxid <sandbox_id>
```

确认命令成功且输出含以 `SANDBOX_IP` 开头的行。也可从管理面获取正确 IP 后用 `--sandbox-ip` 显式传入。

### `Connection refused` 或健康检查超时

确认运行机到 Sandbox 网段路由可达、防火墙允许 `49983`，Template 已启动 envd，并且 readiness probe 配置为 `49983/health`。`--sandbox-ip` 必须是 Sandbox 内网 IP，不能填 CubeAPI 或 CubeProxy 地址。

### CubeAPI TLS 证书错误

优先把根证书安装到系统信任库或设置 `SSL_CERT_FILE`。`--insecure` 只用于短期诊断。

### 正式测试残留多个 Sandbox

逐 case 隔离只有在传入 `--delete` 时才自动删除。进程被中断、Sandbox 创建后 IP 解析失败或脚本异常退出时也可能残留，应通过 CubeSandbox 管理命令检查并清理。

### 报告指标为空但 `rc=0`

上游输出格式可能与报告解析器的正则表达式不完全一致。此时以 `<case>.stdout` 为准，并保留 `.events.json` 和 `.raw` 用于核验。
