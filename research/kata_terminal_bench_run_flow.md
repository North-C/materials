# Kata 运行 Terminal-Bench 任务流程说明

## 目标

本文说明当前在 ARM 服务器上通过 Kata 运行真实 Terminal-Bench 任务的流程。该流程不直接调用大模型 API，而是使用 Terminal-Bench 官方任务包、oracle solution replay 或 fixed-output verifier，构造可复用的 Agent terminal workload，用于后续 CPU 负载和性能分析。

## 目录与环境

ARM 服务器：

```bash
ssh root@192.168.25.61
```

Toolkit 目录：

```bash
/root/agent-cpu-sandbox-toolkit
```

Terminal-Bench 任务目录：

```bash
/root/agent-cpu-sandbox-toolkit/terminal-bench-tasks
```

长任务 rootfs：

```bash
/root/tbench-long-rootfs
```

当前使用 rootfs 而不是 Docker image 的原因是，服务器上的 Docker build/run 存在 containerd 兼容问题：

```text
type with url containerd.linux.runc.CreateOptions: not found
```

因此实际运行时使用 containerd 的 `--rootfs` 方式启动 Kata。

## Rootfs 内容

`/root/tbench-long-rootfs` 基于 `docker.io/library/golang:1.25.0` 展开，并安装了长任务所需工具：

```text
python3
gcc
g++
make
vim
zstd
zstdcat
file
sqlite3
rustc
bc
jimsh
tclsh
tar
gzip
sha256sum
```

Kata rootfs smoke 已验证通过。

## 任务包准备

当前已加入的长负载 Terminal-Bench 任务包括：

| Task | 负载类型 | 推荐模式 |
|---|---|---|
| `jsonl-aggregator` | JSONL 生成、扫描、聚合 | replay，可用 `--workload-repeat` 拉长 |
| `large-scale-text-editing` | 100 万行 CSV + Vim 宏处理 | replay / fixed |
| `deterministic-tarball` | 文件树扫描、tar、zstd 压缩 | fixed，可用 `--workload-repeat` 拉长 |
| `sqlite-with-gcov` | SQLite 源码 gcov 编译 | replay only |

任务包位置示例：

```text
/root/agent-cpu-sandbox-toolkit/terminal-bench-tasks/deterministic-tarball
/root/agent-cpu-sandbox-toolkit/terminal-bench-tasks/large-scale-text-editing
```

## Runner 总体流程

入口脚本：

```bash
/root/agent-cpu-sandbox-toolkit/tools/run_terminal_bench_task.py
```

Runner 的主要职责：

1. 读取指定 Terminal-Bench 任务目录。
2. 为每次运行创建独立 run 目录。
3. 将任务内容复制到该 run 目录下的 `app/`。
4. 对部分任务执行额外初始化。
5. 通过 `ctr` 启动 Kata。
6. 在 Kata sandbox 内执行 replay 或 fixed verifier。
7. 保存 `stdout.log`、`stderr.log`、`score.json` 和 `run.json`。

## 任务初始化

Runner 会把任务目录复制成独立的 `/app` 工作目录：

```text
runs-terminal-bench/<run_id>/app
```

不同任务会有不同初始化逻辑：

| Task | 初始化动作 |
|---|---|
| `jsonl-aggregator` | 执行官方 `task-deps/generate_records.py`，生成 5 个 JSONL 文件，总计约 100 万条记录 |
| `large-scale-text-editing` | 执行 `gen_large_csv.py both`，生成 `input.csv` 和 `expected.csv` |
| `deterministic-tarball` | 执行 `setup_source_tree.sh`，生成 `/app/src` 复杂源码树 |
| `sqlite-with-gcov` | 使用 vendored SQLite 源码包，并将 solution 改为离线编译路径，避免运行时 apt |

复制 fixture/run 目录时会保留 symlink，避免影响 `deterministic-tarball` 这类需要验证 symlink 的任务。

## Kata 启动方式

Runner 内部通过 containerd 启动 Kata，核心命令结构如下：

```bash
ctr -n default run --rm \
  --runtime io.containerd.kata.v2 \
  --rootfs /root/tbench-long-rootfs \
  --mount type=bind,src=<run_dir>/app,dst=/app,options=rbind:rw \
  --mount type=bind,src=/root/agent-cpu-sandbox-toolkit,dst=/runner,options=rbind:ro \
  --mount type=bind,src=<run_dir>/app/tests,dst=/tests,options=rbind:ro \
  /root/tbench-long-rootfs \
  <container_id> \
  /bin/bash -lc '<task command>'
```

挂载说明：

| Mount | 作用 |
|---|---|
| `<run_dir>/app -> /app` | 任务工作目录，读写 |
| `/root/agent-cpu-sandbox-toolkit -> /runner` | runner 工具目录，只读 |
| `<run_dir>/app/tests -> /tests` | 兼容 Terminal-Bench 官方测试路径，只读 |

## 执行模式

### Replay Trajectory

`replay_trajectory` 模式会先执行官方 oracle solution，再运行确定性测试：

```bash
cd /app
bash /app/solution.sh
python3 /runner/tools/mini_pytest.py /app/tests/test_outputs.py > /app/score.json
```

适合：

- `jsonl-aggregator`
- `large-scale-text-editing`
- `sqlite-with-gcov`

其中 `sqlite-with-gcov` 的主要负载来自 replay 阶段的源码编译。

### Fixed Output

`fixed_output` 模式会复用已准备好的 fixture，只运行 verifier：

```bash
cd /app
python3 /runner/tools/mini_pytest.py /app/tests/test_outputs.py > /app/score.json
```

适合：

- `large-scale-text-editing`
- `deterministic-tarball`

注意：不是所有任务的 fixed-output 都能形成长负载。例如 `sqlite-with-gcov` fixed 后主要只是验证已编译产物，编译负载会消失，因此它更适合作 replay-only。

## Workload Repeat

Runner 支持通过 `--workload-repeat N` 放大负载。

在 replay 模式下：

```bash
for i in $(seq 1 N); do
  bash /app/solution.sh
done
python3 /runner/tools/mini_pytest.py /app/tests/test_outputs.py > /app/score.json
```

在 fixed 模式下：

```bash
for i in $(seq 1 N); do
  python3 /runner/tools/mini_pytest.py /app/tests/test_outputs.py > /app/score.json
done
```

对 `deterministic-tarball`，fixed verifier 内部会反复执行 `/app/build.sh`，所以 repeat 仍然是真实 tar/zstd 负载。

## 示例命令

进入 toolkit 目录：

```bash
cd /root/agent-cpu-sandbox-toolkit
```

### Kata 跑 deterministic-tarball fixed-output

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id deterministic-tarball \
  --runtime kata \
  --mode fixed_output \
  --rootfs /root/tbench-long-rootfs \
  --workload-repeat 5
```

### Kata 跑 large-scale-text-editing fixed-output

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id large-scale-text-editing \
  --runtime kata \
  --mode fixed_output \
  --rootfs /root/tbench-long-rootfs
```

### Kata 跑 jsonl-aggregator replay

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id jsonl-aggregator \
  --runtime kata \
  --mode replay_trajectory \
  --rootfs /root/tbench-long-rootfs \
  --workload-repeat 10
```

## 输出结果

每次运行都会写入：

```text
/root/agent-cpu-sandbox-toolkit/runs-terminal-bench/<run_id>/
```

目录内容：

```text
run.json
stdout.log
stderr.log
app/
  score.json
```

`run.json` 记录：

| 字段 | 含义 |
|---|---|
| `run_id` | 本次运行 ID |
| `task_id` | Terminal-Bench 任务名 |
| `runtime` | `kata` 或 `runc` |
| `mode` | `replay_trajectory` 或 `fixed_output` |
| `rootfs` | 使用的 rootfs 路径 |
| `workload_repeat` | 重复次数 |
| `wall_seconds` | 端到端耗时 |
| `exit_code` | 容器命令退出码 |
| `score.status` | verifier 结果 |
| `resource_usage` | runner 侧基础 resource usage |

汇总命令：

```bash
python3 tools/summarize_terminal_bench.py runs-terminal-bench
```

## 已验证样本

当前已验证 Kata 样本：

| Task | Runtime | Mode | Repeat | Wall Time | Status |
|---|---|---|---:|---:|---|
| `deterministic-tarball` | kata | fixed_output | 2 | 23.052157s | pass |

runc 长任务样本：

| Task | Runtime | Mode | Repeat | Wall Time | Status |
|---|---|---|---:|---:|---|
| `jsonl-aggregator` | runc | replay_trajectory | 3 | 10.014705s | pass |
| `large-scale-text-editing` | runc | replay_trajectory | 1 | 120.127073s | pass |
| `large-scale-text-editing` | runc | fixed_output | 1 | 120.324130s | pass |
| `deterministic-tarball` | runc | fixed_output | 5 | 14.338949s | pass |
| `sqlite-with-gcov` | runc | replay_trajectory | 1 | 18.091837s | pass |

## 流程小结

Kata 运行 Terminal-Bench 任务的核心路径是：

```text
Terminal-Bench task package
  -> runner 初始化 /app
  -> ctr 使用 io.containerd.kata.v2 启动 sandbox
  -> 挂载 /app、/runner、/tests
  -> replay solution 或 fixed verifier
  -> mini_pytest 生成 score.json
  -> runner 保存 run.json/stdout/stderr
```

该流程将模型调用完全移出测试路径，保留真实终端任务执行和 verifier 负载，适合后续分析 Kata 沙箱中的 CPU 负载特征和性能表现。
