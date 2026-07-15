# CubeSandbox Benchmark 复用方法

本文档说明如何在另一台已经部署 CubeSandbox 的机器上复用本次测试方法。

## 前提

- 在目标机器上已经启动 CubeSandbox v0.5.0 相关服务。
- 目标机器架构与镜像匹配：
  - arm64 使用 `cube-bench-suite:upstream-arm64`
  - x86_64 使用 `cube-bench-suite:upstream-amd64`
- 镜像已经导入目标机器 Docker，并推送到 CubeSandbox 节点可拉取的 registry。
- `cubemastercli` 可用，CubeAPI 默认监听 `http://127.0.0.1:3000`。

## 1. 导入并推送镜像

以 arm64 为例：

```bash
docker load -i cube-bench-suite_upstream-arm64.tar.gz
docker tag cube-bench-suite:upstream-arm64 127.0.0.1:5000/cube-bench-suite:upstream-arm64
docker login 127.0.0.1:5000 -u admin -p passw0rd
docker push 127.0.0.1:5000/cube-bench-suite:upstream-arm64
```

## 2. 创建 8C16G Template

本次验证中，`49983` 是 envd 命令执行端口，`49999` 是 benchmark health server。为了确保 Template 创建后可通过 SDK/envd 执行命令，readiness probe 使用 `49983 /health`，同时暴露 `49999` 供 benchmark health server 检查。

```bash
cubemastercli template create-from-image \
  --image 127.0.0.1:5000/cube-bench-suite:upstream-arm64 \
  --registry-username admin \
  --registry-password passw0rd \
  --writable-layer-size 8G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health \
  --cpu 8000 \
  --memory 16000 \
  --instance-type cubebox \
  --network-type tap \
  --allow-internet-access \
  --json
```

记录输出中的 `template_id` 和 `job_id`，等待任务 READY：

```bash
cubemastercli template status --job-id <job_id>
cubemastercli template info --template-id <template_id>
```

## 3. 运行可复用测试脚本

将本仓库中的脚本复制到目标机器，或直接在目标机器的仓库目录运行：

```bash
python3 scripts/run_cube_bench_envd.py \
  --cube-api http://127.0.0.1:3000 \
  --template-id <template_id> \
  --suite formal \
  --results-dir /home/lyq/cube-bench-results-$(date +%Y%m%d-%H%M%S) \
  --delete
```

脚本会执行以下步骤：

1. 通过 CubeAPI `POST /sandboxes` 创建 Sandbox。
2. 通过 `cubemastercli cubebox info` 获取 Sandbox IP。
3. 检查 `49983 /health` 和 `49999 /health`。
4. 通过 envd `http://<sandbox-ip>:49983/process.Process/Start` 执行 benchmark。
5. 保存每个用例的命令、stdout、stderr、返回码、Connect raw stream 和事件 JSON。
6. 生成结果目录的 `.tar.gz` 压缩包。
7. 如果传入 `--delete`，测试结束后删除 Sandbox。

## 4. 正式测试套件

```bash
python3 scripts/run_cube_bench_envd.py \
  --template-id <template_id> \
  --suite formal \
  --delete
```

正式套件包括：

- `sysbench-memory-all-formal`：`SYSBENCH_MEMORY_THREADS=2 SYSBENCH_MEMORY_BLOCK_SIZE=1G SYSBENCH_MEMORY_TOTAL_SIZE=100G`，依次执行顺序读、顺序写、随机读、随机写。
- `sysbench-prime-<N>`：`SYSBENCH_THREADS=2`，`N` 为 `1000, 2000, 3000, 5000, 10000, 20000, 30000, 50000, 100000`。
- `go-benchmark-formal`：`GO_BENCH_REPEATS=3`，输出 `build/http/json/garbage` 各子项 average。
- `php-benchmark-formal`：`PHPBENCH_ITERATIONS=2000000`。
- `python-benchmark-formal`：`PYPERFORMANCE_MODE=rigorous`。
- `node-octane-formal` 和 `java-scimark-formal`：使用镜像内正式默认设置。

## 5. 只跑部分用例

```bash
python3 scripts/run_cube_bench_envd.py \
  --template-id <template_id> \
  --suite formal \
  --case versions \
  --case sysbench-memory-all-formal \
  --case sysbench-prime-10000 \
  --delete
```

可用 case：

- `versions`
- smoke suite：`sysbench-memory-all`, `sysbench-prime`, `go-benchmark`, `php-benchmark`, `python-benchmark`, `node-octane`, `java-scimark`
- formal suite：`sysbench-memory-all-formal`, `sysbench-prime-1000`, `sysbench-prime-2000`, `sysbench-prime-3000`, `sysbench-prime-5000`, `sysbench-prime-10000`, `sysbench-prime-20000`, `sysbench-prime-30000`, `sysbench-prime-50000`, `sysbench-prime-100000`, `go-benchmark-formal`, `php-benchmark-formal`, `python-benchmark-formal`, `node-octane-formal`, `java-scimark-formal`

## 6. 复用已有 Sandbox

如果已经有运行中的 Sandbox：

```bash
python3 scripts/run_cube_bench_envd.py \
  --sandbox-id <sandbox_id> \
  --results-dir /tmp/cube-bench-existing-sandbox
```

如果运行脚本的机器没有 `cubemastercli`，但你已知道 Sandbox IP：

```bash
python3 scripts/run_cube_bench_envd.py \
  --sandbox-id <sandbox_id> \
  --sandbox-ip <sandbox_ip>
```

## 7. 结果文件

每个用例会生成：

- `<case>.cmd`
- `<case>.stdout`
- `<case>.stderr`
- `<case>.rc`
- `<case>.events.json`
- `<case>.raw`

汇总文件：

- `context.json`
- `health.txt`
- `summary.json`
- `<results-dir>.tar.gz`

返回码全部为 `0` 表示 smoke benchmark 可运行。
