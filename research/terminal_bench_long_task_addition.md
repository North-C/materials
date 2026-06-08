# Terminal-Bench Long Workload Addition

## Scope

已将四组长负载任务加入 `/root/agent-cpu-sandbox-toolkit`，用于在无大模型 API 的情况下构造更长的 Agent terminal workload：

1. `jsonl-aggregator`
2. `large-scale-text-editing`
3. `deterministic-tarball`
4. `sqlite-with-gcov`

本地 toolkit 同步目录：

```text
/home/lyq/Projects/materials/research/agent_cpu_sandbox_toolkit
```

远端 ARM 服务器目录：

```text
/root/agent-cpu-sandbox-toolkit
```

## Toolkit Changes

新增或更新：

| Path | Purpose |
|---|---|
| `agent_cpu_sandbox_toolkit/terminal-bench-tasks/jsonl-aggregator` | 已有任务，作为可 repeat 的 JSONL 长负载 |
| `agent_cpu_sandbox_toolkit/terminal-bench-tasks/large-scale-text-editing` | 1M 行 CSV + Vim 宏长负载 |
| `agent_cpu_sandbox_toolkit/terminal-bench-tasks/deterministic-tarball` | deterministic tar/zstd 归档负载 |
| `agent_cpu_sandbox_toolkit/terminal-bench-tasks/sqlite-with-gcov` | SQLite gcov 编译负载 |
| `agent_cpu_sandbox_toolkit/tools/run_terminal_bench_task.py` | 增加 long-task profile、`--rootfs`、`--workload-repeat`、`--force-prepare`、`/tests` 挂载和 symlink 保留 |
| `agent_cpu_sandbox_toolkit/images/tbench-long/Dockerfile` | 长任务镜像定义 |
| `agent_cpu_sandbox_toolkit/LONG_TASKS.md` | 运行说明和验证记录 |

## Runtime Environment

Docker build 当前受服务器 Docker/containerd 兼容问题阻塞：

```text
type with url containerd.linux.runc.CreateOptions: not found
```

已改用 containerd `--rootfs` 路径：

```text
/root/tbench-long-rootfs
```

该 rootfs 基于 `docker.io/library/golang:1.25.0` 展开，并安装了：

```text
vim zstd zstdcat file sqlite3 rustc bc jimsh tclsh gcc make python3
```

Kata rootfs smoke 已通过。

## Validated Runs

| Task | Runtime | Mode | Repeat | Wall Time | Status |
|---|---|---|---:|---:|---|
| `jsonl-aggregator` | runc | replay | 3 | 10.014705s | pass |
| `large-scale-text-editing` | runc | replay | 1 | 120.127073s | pass |
| `large-scale-text-editing` | runc | fixed | 1 | 120.324130s | pass |
| `deterministic-tarball` | runc | fixed | 5 | 14.338949s | pass |
| `deterministic-tarball` | kata | fixed | 2 | 23.052157s | pass |
| `sqlite-with-gcov` | runc | replay | 1 | 18.091837s | pass |

## Example Commands

```bash
cd /root/agent-cpu-sandbox-toolkit
```

JSONL repeat replay:

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id jsonl-aggregator \
  --runtime runc \
  --mode replay_trajectory \
  --workload-repeat 10
```

Large text editing fixed output:

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id large-scale-text-editing \
  --runtime runc \
  --mode fixed_output \
  --rootfs /root/tbench-long-rootfs
```

Deterministic tarball fixed output:

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id deterministic-tarball \
  --runtime kata \
  --mode fixed_output \
  --rootfs /root/tbench-long-rootfs \
  --workload-repeat 5
```

SQLite gcov replay:

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id sqlite-with-gcov \
  --runtime runc \
  --mode replay_trajectory \
  --rootfs /root/tbench-long-rootfs
```

## Notes

- `large-scale-text-editing` 是当前最长且最稳定的 fixed-output 长负载，单次约 120s。
- `deterministic-tarball` 默认较短，建议通过 `--workload-repeat` 放大。
- `sqlite-with-gcov` 适合作 replay-only 长负载；fixed-output 会绕过主要编译负载。
- `jsonl-aggregator` 可通过 `--workload-repeat` 从 10s 放大到 30s/分钟级。
