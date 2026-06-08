# ARM 沙箱 Agent CPU Benchmark PoC

## 目标

在 ARM 服务器 `root@192.168.25.61` 上，基于现有 Kata/containerd 环境，构建一个无大模型支持的可复用 Agent 负载测试工具。第一版选择 `Terminal-bench` 风格的 CLI replay workload，用于验证 Fixed Output / Replay Trajectory 两类执行模式。

本 PoC 的目标不是评估模型能力，而是隔离并测量：

- 沙箱启动与执行开销
- CLI 命令链负载
- 文件生成、扫描、排序、压缩、hash 等本地 CPU/IO 特征
- runc 与 Kata VM 隔离的差异
- Fixed Output 与 Replay Trajectory 的开销差异

## 服务器环境

远端环境：

```text
Host: 192.168.25.61
OS: openEuler 24.03
Kernel: 6.6.0-132.0.0.111.oe2403sp3.aarch64
Arch: aarch64
CPU: Kunpeng 920 7280Z
CPU count: 320
Memory: about 1 TiB
Swap: disabled
NUMA: 4 nodes
```

已确认组件：

```text
kata-runtime: 3.18.0
containerd: installed
ctr: installed
docker: installed but regular docker run failed in this environment
qemu-system-aarch64: installed
/opt/kata/bin/cloud-hypervisor: installed
/opt/kata/bin/firecracker: installed
```

Kata 默认配置：

```text
Runtime: /opt/kata/bin/kata-runtime
Default config: /opt/kata/share/defaults/kata-containers/configuration-qemu.toml
Default hypervisor: QEMU 9.1.2
Guest image: /opt/kata/share/kata-containers/kata-ubuntu-noble.image
```

cloud-hypervisor 配置已 smoke 通过：

```text
KATA_CONF_FILE=/opt/kata/share/defaults/kata-containers/configuration-clh.toml
```

## 工具位置

远端目录：

```text
/root/agent-cpu-sandbox-toolkit
```

本地目录：

```text
agent_cpu_sandbox_toolkit/
```

核心文件：

```text
README.md
tools/run_workload.py
tools/summarize.py
scripts/terminal_cpu_io.sh
trajectories/terminal_cpu_io.jsonl
```

## 四个核心工具

1. `tools/run_workload.py`

   统一运行入口，支持 `runc`、`kata`、`docker` 三种 runtime。当前服务器上 Docker 普通容器运行失败，因此主线使用 `ctr + runc` 和 `ctr + kata`。

2. `scripts/terminal_cpu_io.sh`

   固定 replay workload。执行确定性的文件生成、hash、sort、awk 聚合、grep、tar 压缩和规则校验。

3. `tools/summarize.py`

   汇总 `runs/*/run.json`，输出 CSV。

4. `trajectories/terminal_cpu_io.jsonl`

   人类可读的 replay trajectory 元数据，描述每一步命令及其 CPU/IO 信号。

## 执行模式

### Replay Trajectory

在沙箱内完整执行固定命令链：

```text
generate -> hash_sort -> scan_aggregate -> grep_extract -> archive -> validate
```

适合测：

- shell 命令链
- 进程创建
- hash/sort/tar
- 文件读写
- sandbox end-to-end wall time

### Fixed Output

宿主侧预生成固定产物，沙箱内只执行规则 evaluator：

```text
recompute checksums -> compare fixed outputs -> count files/lines -> score
```

适合测：

- evaluator 本地开销
- 沙箱启动开销
- 文件挂载/读取
- 无模型、无生成路径下的固定评分成本

## 运行命令

Smoke:

```bash
cd /root/agent-cpu-sandbox-toolkit

python3 tools/run_workload.py --runtime runc --runs 1 --files 4 --lines 40 --cpus 1 --memory 512m
python3 tools/run_workload.py --runtime kata --runs 1 --files 4 --lines 40 --cpus 1 --memory 512m
python3 tools/run_workload.py --runtime runc --mode fixed_output --runs 1 --files 4 --lines 40 --cpus 1 --memory 512m
python3 tools/run_workload.py --runtime kata --mode fixed_output --runs 1 --files 4 --lines 40 --cpus 1 --memory 512m
```

中等规模：

```bash
python3 tools/run_workload.py --runtime runc --runs 3 --files 16 --lines 200 --cpus 2 --memory 1g
python3 tools/run_workload.py --runtime kata --runs 3 --files 16 --lines 200 --cpus 2 --memory 1g
python3 tools/run_workload.py --runtime runc --mode fixed_output --runs 3 --files 16 --lines 200 --cpus 2 --memory 1g
python3 tools/run_workload.py --runtime kata --mode fixed_output --runs 3 --files 16 --lines 200 --cpus 2 --memory 1g
```

Kata + cloud-hypervisor:

```bash
python3 tools/run_workload.py \
  --runtime kata \
  --kata-config /opt/kata/share/defaults/kata-containers/configuration-clh.toml \
  --runs 1 \
  --files 4 \
  --lines 40
```

汇总：

```bash
python3 tools/summarize.py runs | tee runs/summary.csv
```

## 初步结果

中等规模参数：

```text
files=16
lines=200
total generated lines=3200
cpus=2
memory=1g
runs=3
```

结果：

| Runtime | Mode | Runs | Avg wall time | Min | Max |
|---|---|---:|---:|---:|---:|
| runc | replay_trajectory | 3 | 3.978s | 3.935s | 4.018s |
| kata/qemu | replay_trajectory | 3 | 16.084s | 15.846s | 16.357s |
| runc | fixed_output | 3 | 0.209s | 0.123s | 0.287s |
| kata/qemu | fixed_output | 3 | 1.299s | 1.277s | 1.328s |

Smoke 结果：

| Runtime | Mode | Scale | Wall time | Status |
|---|---|---|---:|---|
| runc | replay_trajectory | files=4, lines=40 | 0.368s | pass |
| kata/qemu | replay_trajectory | files=4, lines=40 | 2.016s | pass |
| runc | fixed_output | files=4, lines=40 | 0.175s | pass |
| kata/qemu | fixed_output | files=4, lines=40 | 1.282s | pass |
| kata/cloud-hypervisor | replay_trajectory | files=4, lines=40 | 2.010s | pass |

## 观察

1. Kata/QEMU 对短任务的固定开销显著。

   在 Fixed Output 模式下，沙箱内只做 evaluator 校验，runc 平均约 0.21s，Kata/QEMU 平均约 1.30s。这个差异主要体现 VM 沙箱启动、挂载和 shim/runtime 开销。

2. Replay Trajectory 放大了 Kata 与 runc 的差异。

   中等规模 replay 下，runc 平均约 3.98s，Kata/QEMU 平均约 16.08s。该 workload 包含大量 shell/hash/sort/tar 操作，Kata 下 virtio-fs、guest 内进程执行和 VM 隔离路径会放大整体 wall time。

3. Fixed Output 与 Replay Trajectory 能有效拆分负载。

   Fixed Output 更适合测 evaluator 和沙箱启动成本；Replay Trajectory 更适合测 Agent 本地工具链执行成本。

4. Docker 当前不适合作为本机基线。

   本机 `docker run` 失败：

   ```text
   docker: Error response from daemon: type with url containerd.linux.runc.CreateOptions: not found: unknown.
   ```

   因此本 PoC 使用 `ctr + io.containerd.runc.v2` 作为轻量容器基线。

## 当前限制

1. `run.json` 中的 `user_time` / `system_time` 来自 Python `resource.getrusage(RUSAGE_CHILDREN)`，主要反映宿主侧 runner/ctr 进程开销，不代表 guest 内 workload 的完整 CPU time。

2. 当前 workload 是 Terminal-bench 风格的合成 replay，不是官方 Terminal-bench 任务集。它用于先验证沙箱执行和测量框架，后续可替换成官方任务轨迹。

3. `--cpus` 和 `--memory` 对 Docker 参数有效；对当前 `ctr` 路径主要作为 run metadata 记录，尚未强制写入 containerd cgroup spec。后续需要补齐 CPU/memory enforcement。

4. 当前 phase 时间使用秒级时间戳，适合粗略分析，不适合微基准。

## 下一步

1. 增加 guest/container 内部 CPU 采集。

   可选方案：

   - 在 workload 内记录 `/proc/stat` 差分。
   - 在 runc cgroup 和 Kata shim/qemu 进程上采集 cpu.stat。
   - 对 Kata 侧额外跟踪 qemu/cloud-hypervisor 进程 CPU。

2. 增加 cgroup 资源限制。

   对 `ctr` 路径补齐 CPU quota、cpuset、memory limit，使 `--cpus` 和 `--memory` 真实生效。

3. 增加 cloud-hypervisor 正式测试维度。

   当前 cloud-hypervisor smoke 已通过，后续应加入：

   ```text
   kata/qemu
   kata/cloud-hypervisor
   runc
   ```

4. 替换为官方 Terminal-bench 任务轨迹。

   先选无网络、无模型、可规则验证的任务，将一次成功执行记录为 Replay Trajectory。

5. 增加并发测试。

   在 320 vCPU ARM 服务器上测试：

   ```text
   N=1
   N=32
   N=80
   N=160
   N=320
   ```

   分别观察 runc/Kata 的吞吐、启动风暴、virtio-fs 开销和调度行为。
