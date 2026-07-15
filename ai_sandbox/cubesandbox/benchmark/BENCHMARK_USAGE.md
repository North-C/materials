# Cube Benchmark Suite 使用文档

本文说明如何使用 `cube-bench-suite` 镜像在两种场景下测试：

- **Image 模式**：直接用 Docker 运行镜像，适合验证 benchmark 本体、快速取数和离线复现。
- **Template 模式**：将镜像制作成 CubeSandbox template，适合验证模板构建、Sandbox 启动探活，以及在 Sandbox 生命周期中运行 benchmark。

## 1. 镜像与产物

已准备两个架构版本，benchmark 来源版本保持一致：

| 架构 | 镜像 tag | 本地 tar 包 |
|---|---|---|
| arm64 | `cube-bench-suite:upstream-arm64` | `cube-bench-suite_upstream-arm64.tar.gz` |
| x86_64 / amd64 | `cube-bench-suite:upstream-amd64` | `cube-bench-suite_upstream-amd64.tar.gz` |

tar 包校验：

| 文件 | SHA256 |
|---|---|
| `cube-bench-suite_upstream-arm64.tar.gz` | `f4eb197165ff337253de19735907ff946b5b80e8059112aa6ecc426ac52fa792` |
| `cube-bench-suite_upstream-amd64.tar.gz` | `e7f975b775d5a9a7d2184a0c51a50a23f0170107b5a4af22f325350489c7fcb2` |

导入镜像：

```bash
docker load -i cube-bench-suite_upstream-amd64.tar.gz
docker load -i cube-bench-suite_upstream-arm64.tar.gz
```

注意：template 使用的镜像架构必须与 CubeSandbox 节点架构一致。x86 节点使用 `upstream-amd64`，arm64 节点使用 `upstream-arm64`。

## 2. 镜像内 benchmark

统一入口：

```bash
run-benchmark <case>
```

支持的 case：

| case | benchmark 来源 | 说明 |
|---|---|---|
| `versions` | wrapper | 打印运行时版本、benchmark 来源 commit/checksum |
| `sysbench-memory` | `akopytov/sysbench` | 可配置内存顺序/随机读写测试 |
| `sysbench-memory-all` | `akopytov/sysbench` | 依次运行顺序读、顺序写、随机读、随机写 |
| `sysbench-prime` | `akopytov/sysbench` | CPU prime workload，即常用最大素数测试 |
| `sysbench-prime-matrix` | `akopytov/sysbench` | 按素数上限矩阵运行 CPU prime |
| `go-benchmark` | `golang.org/x/benchmarks` | `build/http/json/garbage` 并输出各子项 average |
| `php-benchmark` | `pantheon-systems/php-bench` | PHPBench CPU suite |
| `python-benchmark` | `python/pyperformance` | 默认运行一组短 pyperformance benchmark |
| `node-octane` | `dai-shi/benchmark-octane` | Octane benchmark |
| `java-scimark` | `mork-optimization/scimark` | SciMark 2.2 large |
| `all` | wrapper | 短 smoke run，覆盖所有组 |
| `formal` | wrapper | 正式测试套件，使用固定参数矩阵 |

默认启动行为：

- amd64 镜像 `cube-bench-suite:upstream-amd64` 已基于 `ghcr.io/tencentcloud/cubesandbox-base:2026.16` 重建。
- arm64 镜像 `cube-bench-suite:upstream-arm64` 已基于本地构建的 arm64 `cubesandbox-base:2026.16-arm64-local` 重建；该 base 使用 CubeSandbox 官方 `docker/Dockerfile.cube-base` 同等逻辑，envd ref 为 `2026.16`。
- 不传命令时，base entrypoint 会先启动 envd，再启动 benchmark HTTP health server。
- envd 监听端口：`49983`，`GET /health` 返回 204。CubeSandbox SDK 的 `sandbox.commands.run(...)` 和 `sandbox.files.read(...)` 依赖该端口。
- benchmark health server 监听端口：`49999`，`GET /health` 返回 200，`GET /benchmarks` 返回可用 benchmark case 列表。
- 两个架构的当前 tar 包都可用于 Template + SDK 命令执行；如果后续换成其它自定义镜像，仍需确认镜像启动时有 envd 监听 `49983`。

## 3. Image 模式测试

### 3.1 健康检查

amd64：

```bash
docker run -d --name cube-bench-probe-amd64 \
  -p 50083:49983 \
  -p 50099:49999 \
  cube-bench-suite:upstream-amd64

curl -si http://127.0.0.1:50083/health | head
curl -fsS http://127.0.0.1:50099/health
docker rm -f cube-bench-probe-amd64
```

arm64：

```bash
docker run -d --name cube-bench-probe-arm64 \
  -p 50083:49983 \
  -p 50099:49999 \
  cube-bench-suite:upstream-arm64

curl -si http://127.0.0.1:50083/health | head
curl -fsS http://127.0.0.1:50099/health
docker rm -f cube-bench-probe-arm64
```

### 3.2 查看版本和来源

```bash
docker run --rm cube-bench-suite:upstream-amd64 run-benchmark versions
```

输出中会包含 Go/PHP/Python/Node/Java/sysbench 版本，以及 `/opt/cube-bench/SOURCES.md` 中记录的 commit/checksum。

### 3.3 运行单项 benchmark

```bash
# sysbench memory 四象限：顺序读、顺序写、随机读、随机写
docker run --rm \
  -e SYSBENCH_MEMORY_TIME=30 \
  -e SYSBENCH_MEMORY_TOTAL_SIZE=100G \
  -e SYSBENCH_MEMORY_BLOCK_SIZE=1G \
  -e SYSBENCH_MEMORY_THREADS=2 \
  cube-bench-suite:upstream-amd64 \
  run-benchmark sysbench-memory-all

# sysbench memory 单项：随机读
docker run --rm \
  -e SYSBENCH_MEMORY_TIME=30 \
  -e SYSBENCH_MEMORY_TOTAL_SIZE=100G \
  -e SYSBENCH_MEMORY_BLOCK_SIZE=1K \
  -e SYSBENCH_MEMORY_THREADS=4 \
  -e SYSBENCH_MEMORY_OPER=read \
  -e SYSBENCH_MEMORY_ACCESS_MODE=rnd \
  cube-bench-suite:upstream-amd64 \
  run-benchmark sysbench-memory

# sysbench 最大素数 CPU 测试
docker run --rm \
  -e SYSBENCH_TIME=30 \
  -e SYSBENCH_MAX_PRIME=20000 \
  -e SYSBENCH_THREADS=2 \
  cube-bench-suite:upstream-amd64 \
  run-benchmark sysbench-prime

# sysbench 最大素数矩阵：1000 到 100000
docker run --rm \
  -e SYSBENCH_TIME=30 \
  -e SYSBENCH_THREADS=2 \
  -e SYSBENCH_PRIME_MAX_LIST=1000,2000,3000,5000,10000,20000,30000,50000,100000 \
  cube-bench-suite:upstream-amd64 \
  run-benchmark sysbench-prime-matrix

# Go build/http/json/garbage 各子项 average
docker run --rm \
  -e GO_BENCH_REPEATS=3 \
  cube-bench-suite:upstream-amd64 \
  run-benchmark go-benchmark

# PHPBench
docker run --rm \
  -e PHPBENCH_ITERATIONS=2000000 \
  cube-bench-suite:upstream-amd64 \
  run-benchmark php-benchmark

# Python pyperformance，正式模式
docker run --rm \
  -e PYPERFORMANCE_MODE=rigorous \
  cube-bench-suite:upstream-amd64 \
  run-benchmark python-benchmark

# 一次运行镜像内正式套件
docker run --rm cube-bench-suite:upstream-amd64 run-benchmark formal

# Node Octane
docker run --rm cube-bench-suite:upstream-amd64 run-benchmark node-octane

# Java SciMark
docker run --rm cube-bench-suite:upstream-amd64 run-benchmark java-scimark
```

arm64 只需要将镜像 tag 改成 `cube-bench-suite:upstream-arm64`。

### 3.4 常用环境变量

| 变量 | 默认值 | 适用 case |
|---|---|---|
| `SYSBENCH_MEMORY_TIME` | `30` | `sysbench-memory`, `sysbench-memory-all` |
| `SYSBENCH_MEMORY_TOTAL_SIZE` | `100G` | `sysbench-memory`, `sysbench-memory-all` |
| `SYSBENCH_MEMORY_BLOCK_SIZE` | `1K` | `sysbench-memory`, `sysbench-memory-all` |
| `SYSBENCH_MEMORY_THREADS` | `SYSBENCH_THREADS` 或 `nproc` | `sysbench-memory`, `sysbench-memory-all` |
| `SYSBENCH_MEMORY_OPER` | `write` | `sysbench-memory`，可选 `read`/`write` |
| `SYSBENCH_MEMORY_ACCESS_MODE` | `seq` | `sysbench-memory`，可选 `seq`/`rnd` |
| `SYSBENCH_MEMORY_SCOPE` | `global` | `sysbench-memory`, `sysbench-memory-all` |
| `SYSBENCH_TIME` | `30` | `sysbench-prime` |
| `SYSBENCH_MAX_PRIME` | `20000` | `sysbench-prime` |
| `SYSBENCH_PRIME_MAX_LIST` | `1000,2000,3000,5000,10000,20000,30000,50000,100000` | `sysbench-prime-matrix` |
| `SYSBENCH_THREADS` | `nproc` | `sysbench-prime`, `sysbench-prime-matrix` |
| `GO_BENCH_REPEATS` | `1` | `go-benchmark` |
| `PHPBENCH_ITERATIONS` | `2000000` | `php-benchmark` |
| `PYPERFORMANCE_BENCHMARKS` | `python_startup,json_dumps,json_loads,richards,scimark` | `python-benchmark` |
| `PYPERFORMANCE_MODE` | `fast` | `python-benchmark` |
| `PYPERFORMANCE_RIGOROUS` | `0` | `python-benchmark` |
| `CUBE_BENCH_OUT_DIR` | `/tmp/cube-bench-results` | wrapper 输出目录 |

内存 benchmark 参数说明：

| case | 可设置参数 | 作用 | 设置建议 |
|---|---|---|---|
| `sysbench-memory` | `SYSBENCH_MEMORY_OPER` | 单项内存操作类型，`read` 或 `write`。 | 顺序读写/随机读写单独取数时设置。 |
| `sysbench-memory` | `SYSBENCH_MEMORY_ACCESS_MODE` | 单项访问模式，`seq` 或 `rnd`。 | `seq` 表示顺序访问，`rnd` 表示随机访问。 |
| `sysbench-memory`, `sysbench-memory-all` | `SYSBENCH_MEMORY_THREADS` | 并发线程数。 | 建议等于 Sandbox CPU 核数。 |
| `sysbench-memory`, `sysbench-memory-all` | `SYSBENCH_MEMORY_TIME` | 每个内存子项运行秒数。 | smoke 用 `5`；正式取数建议 `30` 或更高。 |
| `sysbench-memory`, `sysbench-memory-all` | `SYSBENCH_MEMORY_TOTAL_SIZE` | 每个子项总传输量上限。 | 正式统一使用 `100G`。 |
| `sysbench-memory`, `sysbench-memory-all` | `SYSBENCH_MEMORY_BLOCK_SIZE` | 单次内存操作块大小。 | 正式统一使用 `1G`；跨机器对比必须固定。 |
| `sysbench-memory`, `sysbench-memory-all` | `SYSBENCH_MEMORY_SCOPE` | memory buffer 作用域，`global` 或 `local`。 | 默认 `global`；不建议混合比较 `global` 和 `local`。 |

语言运行时 benchmark 参数说明：

| case | 可设置参数 | 作用 | 设置建议 |
|---|---|---|---|
| `go-benchmark` | `GO_BENCH_REPEATS` | 每个 Go benchmark 子项重复次数。子项固定为 `build/http/json/garbage`，wrapper 会分别输出每个子项的 average，并额外输出全局 average。 | smoke 用 `1`；正式取数使用 `3` 或以上并固定 CPU 资源。 |
| `php-benchmark` | `PHPBENCH_ITERATIONS` | 传给 PHPBench 的 `iterations`。 | smoke 用 `10000`；正式取数可使用默认 `2000000` 或按耗时调高/调低。 |
| `python-benchmark` | `PYPERFORMANCE_BENCHMARKS` | pyperformance benchmark 名称列表，逗号分隔。 | smoke 用 `python_startup,json_dumps`；正式取数可用默认列表或指定完整目标项。 |
| `python-benchmark` | `PYPERFORMANCE_MODE` | `fast` 或 `rigorous`。 | smoke 用 `fast`；正式取数用 `rigorous`。 |
| `python-benchmark` | `PYPERFORMANCE_RIGOROUS` | 设为 `1` 时强制使用 pyperformance `--rigorous`。 | 与 `PYPERFORMANCE_MODE=rigorous` 等价，二选一即可。 |
| `node-octane` | 无 wrapper 参数 | 直接运行上游 Octane `node run.js`。 | 通过容器/Sandbox 资源限制、重复运行次数控制对比条件。 |
| `java-scimark` | 无 wrapper 参数 | 固定运行 SciMark 2.2 `-large`。 | 通过容器/Sandbox 资源限制、重复运行次数控制对比条件。 |

完整 Python 模式：

```bash
docker run --rm \
  -e PYPERFORMANCE_RIGOROUS=1 \
  -e PYPERFORMANCE_BENCHMARKS=python_startup,json_dumps \
  cube-bench-suite:upstream-amd64 \
  run-benchmark python-benchmark
```

## 4. Template 模式测试

Template 模式分两类：

1. **默认 template**：用于验证 image 能被 CubeSandbox 制作为 template，Sandbox 能成功启动并通过 `/health` 探活。
2. **benchmark 启动 template**：通过 `--cmd/--arg/--env` 覆写启动命令，让 Sandbox 启动后自动运行某个 benchmark，再启动 health server。

### 4.1 准备 registry 镜像

`cubemastercli tpl create-from-image` 需要 CubeSandbox 节点可拉取的 OCI image reference。离线环境通常先把 tar 包导入到集群节点或私有 registry，再重新打 tag：

```bash
docker load -i cube-bench-suite_upstream-amd64.tar.gz

docker tag cube-bench-suite:upstream-amd64 \
  <registry>/cube-bench-suite:upstream-amd64

docker push <registry>/cube-bench-suite:upstream-amd64
```

arm64 集群使用：

```bash
docker load -i cube-bench-suite_upstream-arm64.tar.gz

docker tag cube-bench-suite:upstream-arm64 \
  <registry>/cube-bench-suite:upstream-arm64

docker push <registry>/cube-bench-suite:upstream-arm64
```

### 4.2 创建默认 benchmark template

默认 template 保留镜像 ENTRYPOINT：先启动 `49983` envd，再启动 `49999` benchmark health server。需要通过 SDK 执行 benchmark 时，readiness probe 建议指向 `49983/health`，这样可以验证命令执行通道所需的 envd 已经就绪。

```bash
cubemastercli --address <cubemaster-ip> --port 8089 tpl create-from-image \
  --image <registry>/cube-bench-suite:upstream-amd64 \
  --writable-layer-size 2G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health
```

如果命令返回 job id，可继续观察：

```bash
cubemastercli --address <cubemaster-ip> --port 8089 tpl watch --job-id <job_id>
cubemastercli --address <cubemaster-ip> --port 8089 tpl list
```

验证重点：

- template 构建任务完成。
- template 在目标节点上状态正常。
- 用该 template 创建 Sandbox 后，Cube 的 readiness probe 能访问 `49983/health`。
- 如需额外验证 benchmark health server，可在 Sandbox 内或端口转发后访问 `49999/health`。

### 4.3 通过 SDK 在 template 内运行 benchmark

当前 amd64/arm64 镜像都已经内置并默认启动 envd，可直接用 E2B SDK 创建 Sandbox 后执行 `run-benchmark`。如果使用其它自定义镜像，必须确认镜像基于 `cubesandbox-base` 或已经自行注入并启动 envd，且 template 暴露 `49983`。

```bash
export E2B_API_URL=http://<cubeapi-host>:3000
export E2B_API_KEY=e2b_000000
export CUBE_TEMPLATE_ID=<template-id>
export CUBE_BENCH_HOST_OUT=./cube-bench-results
# 使用 Cube 内置 mkcert 证书时需要；该路径必须存在于运行 SDK 脚本的宿主机
export SSL_CERT_FILE=/path/to/cube-rootCA.pem
```

```bash
python3 - <<'PY'
import json
import os
import shlex
from pathlib import Path

# 如果外部使用 CUBE_SSL_CERT_FILE 保存 Cube CA，这里转换为 E2B SDK 识别的 SSL_CERT_FILE。
if "CUBE_SSL_CERT_FILE" in os.environ and "SSL_CERT_FILE" not in os.environ:
    os.environ["SSL_CERT_FILE"] = os.environ["CUBE_SSL_CERT_FILE"]

from e2b_code_interpreter import Sandbox

template = os.environ["CUBE_TEMPLATE_ID"]
host_out = Path(os.environ.get("CUBE_BENCH_HOST_OUT", "./cube-bench-results"))
host_out.mkdir(parents=True, exist_ok=True)
manifest = host_out / "manifest.jsonl"
manifest.unlink(missing_ok=True)

benchmarks = [
    {
        "name": "versions",
        "cmd": "run-benchmark versions",
        "timeout": 120,
    },
    {
        "name": "sysbench-memory-all-formal",
        "cmd": "SYSBENCH_MEMORY_TIME=30 SYSBENCH_MEMORY_TOTAL_SIZE=100G SYSBENCH_MEMORY_BLOCK_SIZE=1G SYSBENCH_MEMORY_THREADS=2 run-benchmark sysbench-memory-all",
        "timeout": 300,
    },
    {
        "name": "go-benchmark-formal",
        "cmd": "GO_BENCH_REPEATS=3 run-benchmark go-benchmark",
        "timeout": 1800,
    },
    {
        "name": "php-benchmark-formal",
        "cmd": "PHPBENCH_ITERATIONS=2000000 run-benchmark php-benchmark",
        "timeout": 1200,
    },
    {
        "name": "python-benchmark-formal",
        "cmd": "PYPERFORMANCE_MODE=rigorous run-benchmark python-benchmark",
        "timeout": 3600,
    },
    {
        "name": "node-octane",
        "cmd": "run-benchmark node-octane",
        "timeout": 1200,
    },
    {
        "name": "java-scimark",
        "cmd": "run-benchmark java-scimark",
        "timeout": 600,
    },
]

for max_prime in [1000, 2000, 3000, 5000, 10000, 20000, 30000, 50000, 100000]:
    benchmarks.append({
        "name": f"sysbench-prime-{max_prime}",
        "cmd": f"SYSBENCH_TIME=30 SYSBENCH_THREADS=2 SYSBENCH_MAX_PRIME={max_prime} run-benchmark sysbench-prime",
        "timeout": 120,
    })

with Sandbox.create(template=template) as sandbox:
    sandbox.commands.run("mkdir -p /tmp/cube-bench-sdk", timeout=60)

    for item in benchmarks:
        name = item["name"]
        raw_cmd = item["cmd"]
        timeout = item["timeout"]
        sandbox_log = f"/tmp/cube-bench-sdk/{name}.log"

        # tee 会在 Sandbox 内保存完整合并输出；SDK 再把该文件读回宿主机。
        wrapped = f"set -o pipefail; {raw_cmd} 2>&1 | tee {shlex.quote(sandbox_log)}"
        sdk_cmd = f"/bin/bash -lc {shlex.quote(wrapped)}"

        print(f"$ {raw_cmd}")
        result = sandbox.commands.run(sdk_cmd, timeout=timeout)

        # 保存 SDK 直接返回的输出，便于排查 SDK/streaming 层问题。
        (host_out / f"{name}.stdout.log").write_text(result.stdout or "", encoding="utf-8")
        (host_out / f"{name}.stderr.log").write_text(result.stderr or "", encoding="utf-8")

        # 从 Sandbox 文件系统拷贝 benchmark 完整日志到宿主机。
        content = sandbox.files.read(sandbox_log)
        if isinstance(content, bytes):
            (host_out / f"{name}.log").write_bytes(content)
        else:
            (host_out / f"{name}.log").write_text(content, encoding="utf-8")

        meta = {
            "name": name,
            "command": raw_cmd,
            "sandbox_log": sandbox_log,
            "host_log": str(host_out / f"{name}.log"),
            "exit_code": result.exit_code,
        }
        with manifest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")

        if result.exit_code != 0:
            raise RuntimeError(f"{name} failed with exit_code={result.exit_code}")
PY
```

说明：

- amd64 默认 benchmark template 应支持 `sandbox.commands.run(...)`；如果 SDK 命令执行失败，优先检查 template 是否使用了新版 `cube-bench-suite:upstream-amd64`、是否暴露并 probe `49983`、Sandbox 是否仍存活，以及 cube-proxy 到节点网络是否正常。
- 如果 `sandbox.commands.run(...)` 或 `sandbox.files.read(...)` 报 `SSL: CERTIFICATE_VERIFY_FAILED`，说明运行 SDK 的宿主机没有信任 CubeProxy 使用的 mkcert CA。把部署节点上的 `/root/.local/share/mkcert/rootCA.pem` 拷贝到运行脚本的机器，并设置 `SSL_CERT_FILE=/path/to/rootCA.pem` 后重试。
- `node-octane`、`java-scimark`、`go-benchmark` 运行时间更长，建议单独执行并把 timeout 调大。
- 上述示例会在宿主机 `${CUBE_BENCH_HOST_OUT}` 目录保存三类文件：`<case>.log` 是从 Sandbox 内 `/tmp/cube-bench-sdk/<case>.log` 拷贝出的完整 benchmark 输出，`<case>.stdout.log` / `<case>.stderr.log` 是 SDK 命令返回流，`manifest.jsonl` 记录命令、Sandbox 日志路径、宿主机日志路径和退出码。
- 如果命令执行通道不可用，默认 template 仍可用于验证模板构建和 Sandbox 启动，但不能通过 SDK 触发 benchmark 命令。此时使用下一节的启动命令覆写方式。

### 4.4 创建启动即运行 benchmark 的 template

可以用 `create-from-image` 的 `--cmd`、`--arg`、`--env` 覆写容器启动命令。下面示例让 Sandbox 启动时运行一次 sysbench prime，把输出写入日志，然后继续启动 health server，保证 readiness probe 仍可通过。

```bash
cubemastercli --address <cubemaster-ip> --port 8089 tpl create-from-image \
  --image <registry>/cube-bench-suite:upstream-amd64 \
  --writable-layer-size 2G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health \
  --env SYSBENCH_TIME=30 \
  --env SYSBENCH_MAX_PRIME=20000 \
  --env SYSBENCH_THREADS=2 \
  --cmd /bin/sh \
  --cmd -lc \
  --arg 'run-benchmark sysbench-prime | tee /opt/cube-bench/work/sysbench-prime.log; exec python3 /opt/cube-bench/bin/health_server.py'
```

其它 benchmark 可替换 `run-benchmark sysbench-prime`：

```bash
run-benchmark sysbench-memory-all
run-benchmark go-benchmark
run-benchmark php-benchmark
run-benchmark python-benchmark
run-benchmark node-octane
run-benchmark java-scimark
```

建议：

- 启动即运行的 benchmark 会影响 Sandbox 就绪时间。长耗时 benchmark 可能让 template/Sandbox readiness 变慢。
- 如果只是验证集群可用，使用默认 template 即可。
- 如果要采集 benchmark 结果，优先使用 Image 模式，或使用支持命令执行通道的 template 通过 SDK 拉取 stdout。

### 4.5 `all` smoke template

如果需要启动后覆盖所有 benchmark 组，可使用 `all`，但耗时明显更长：

```bash
cubemastercli --address <cubemaster-ip> --port 8089 tpl create-from-image \
  --image <registry>/cube-bench-suite:upstream-amd64 \
  --writable-layer-size 2G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health \
  --cmd /bin/sh \
  --cmd -lc \
  --arg 'run-benchmark all | tee /opt/cube-bench/work/all.log; exec python3 /opt/cube-bench/bin/health_server.py'
```

## 5. 推荐测试顺序

1. **先测 image**：

```bash
docker run --rm cube-bench-suite:upstream-amd64 run-benchmark versions
docker run --rm -e SYSBENCH_TIME=3 -e SYSBENCH_THREADS=2 cube-bench-suite:upstream-amd64 run-benchmark sysbench-prime
```

2. **再测 template 构建和探活**：

```bash
cubemastercli --address <cubemaster-ip> --port 8089 tpl create-from-image \
  --image <registry>/cube-bench-suite:upstream-amd64 \
  --writable-layer-size 2G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health
```

3. **最后按需求跑 benchmark**：

- 有命令执行通道：用 SDK 在 Sandbox 内运行 `run-benchmark <case>`。
- 没有命令执行通道：用 `--cmd/--arg` 制作启动即运行 benchmark 的 template。
- 只做性能取数：直接使用 Image 模式，结果更可控。

## 6. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| template 构建成功但探活失败 | `--probe` 端口或 `--probe-path` 错误 | SDK 模式使用 `--probe 49983 --probe-path /health`，并确认 `--expose-port 49983`；只验证 benchmark health server 时可检查 `49999/health` |
| Sandbox 启动很慢 | 启动命令中运行了长耗时 benchmark | 默认 template 只跑 health server；长 benchmark 放到 SDK 命令执行或 Image 模式 |
| `python-benchmark` 下载依赖失败 | pyperformance 创建 venv 时需要 pip 源 | 镜像默认设置腾讯 PyPI 源；离线环境需提前缓存依赖或允许访问内部 PyPI |
| Go benchmark 出现 `perf` 相关 warning | 上游 Go benchmark 会尝试调用 `perf` | 非致命，benchmark 仍会输出结果；如需 perf 数据需额外给容器权限和工具 |
| 结果波动大 | 容器/Sandbox 资源竞争、CPU 频率、调度干扰 | 固定线程数、重复运行、隔离节点负载，Python 可使用 rigorous 模式 |
| `sandbox.commands.run()` 报 `502 bad gateway` / `Code.unavailable` | SDK 通过 cube-proxy 访问 Sandbox 内 `49983`，但 template 未启动 envd、端口未暴露、Sandbox 已暂停/删除，或 cube-proxy 到 compute 节点网络不通 | 先确认 template 使用当前 envd-enabled benchmark 镜像或其它 envd-enabled 镜像，并设置 `--expose-port 49983 --probe 49983`；再检查 DNS/TLS、cube-proxy 日志、Sandbox 是否仍存活 |
