# 真实 Terminal-Bench 无大模型运行 PoC

## 目标

在 ARM 服务器 `root@192.168.25.61` 的 AI 沙箱环境中，引入真实 Terminal-Bench 任务，用 Fixed Output / Replay Trajectory 方式构建不直接依赖大模型 API 的 Agent benchmark 用例。

本 PoC 与前一版合成 workload 的区别：

- 使用官方 Terminal-Bench 任务包中的真实 `task.yaml`、`solution.sh`、`tests/test_outputs.py` 和输入文件。
- 不调用模型 API。
- 不执行官方 `run-tests.sh` 中的在线 `apt/uv/pip` 安装流程。
- 使用离线 `mini_pytest.py` 直接导入任务自带测试文件并执行 `test_*` 函数。
- 用 oracle `solution.sh` 作为 Replay Trajectory 的第一阶段来源，用已生成产物作为 Fixed Output。

官方依据：

- Terminal-Bench 官方仓库说明：每个任务包含 instruction、test script 和 oracle/reference solution。
- 官方 harness 会连接模型到沙箱终端，并生成 execution logs、task results、terminal panes、sessions、commands 等输出。

## 当前任务子集

已同步到远端：

```text
/root/agent-cpu-sandbox-toolkit/terminal-bench-tasks/
  log-summary/
  constraints-scheduling/
  jsonl-aggregator/
```

选择原因：

| Task | 类型 | 保留原因 |
|---|---|---|
| log-summary | 日志处理 | 轻量、shell/grep/CSV、测试明确，适合 smoke |
| constraints-scheduling | 文件解析/约束满足 | ICS 输入、Python 生成输出、规则验证，接近真实助理任务 |
| jsonl-aggregator | 数据处理 | 约 100 万 JSONL 记录，适合构造数据密集型 CPU 负载 |

暂未选择需要复杂服务、外网、GPU、浏览器、apt 安装、daemon 或主观评测的任务。

## 新增工具

远端目录：

```text
/root/agent-cpu-sandbox-toolkit
```

新增文件：

```text
tools/mini_pytest.py
tools/run_terminal_bench_task.py
tools/summarize_terminal_bench.py
```

### mini_pytest.py

离线测试执行器。它直接导入任务的 `tests/test_outputs.py`，查找并执行所有无参数 `test_*` 函数，输出 JSON：

```json
{
  "status": "pass",
  "passed": 3,
  "failed": 0,
  "skipped": 0
}
```

### run_terminal_bench_task.py

真实 Terminal-Bench 任务运行器，支持：

```text
runtime: runc, kata
mode: replay_trajectory, fixed_output
```

Replay Trajectory：

```text
初始化 /app -> 执行 /app/solution.sh -> 执行 /app/tests/test_outputs.py
```

Fixed Output：

```text
准备 oracle fixed fixture -> 复制 fixed /app -> 只执行 tests/test_outputs.py
```

### summarize_terminal_bench.py

汇总 `runs-terminal-bench/*/run.json` 为 CSV。

## 镜像与运行环境

当前使用：

```text
docker.io/library/golang:1.25.0
```

原因：

- 远端已有该 arm64 镜像。
- 已导入 containerd `default` namespace。
- 镜像内有 `/bin/bash` 和 `python3 3.13.5`。
- 足以运行当前 3 个任务的 oracle solution 和离线测试。

Docker 普通运行在本机仍不可用，错误为：

```text
docker: Error response from daemon: type with url containerd.linux.runc.CreateOptions: not found: unknown.
```

因此当前使用：

```text
runc baseline: ctr -n default run --runtime io.containerd.runc.v2
kata VM:       ctr -n default run --runtime io.containerd.kata.v2
```

## 运行命令

### log-summary

```bash
cd /root/agent-cpu-sandbox-toolkit

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id log-summary \
  --runtime runc \
  --mode replay_trajectory

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id log-summary \
  --runtime kata \
  --mode fixed_output
```

### constraints-scheduling

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id constraints-scheduling \
  --runtime runc \
  --mode replay_trajectory

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id constraints-scheduling \
  --runtime kata \
  --mode fixed_output
```

### jsonl-aggregator

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id jsonl-aggregator \
  --runtime runc \
  --mode replay_trajectory

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id jsonl-aggregator \
  --runtime kata \
  --mode fixed_output
```

### 汇总

```bash
python3 tools/summarize_terminal_bench.py runs-terminal-bench \
  | tee runs-terminal-bench/summary.csv
```

## 已验证结果

| Task | Runtime | Mode | Status | Wall Time |
|---|---|---|---|---:|
| log-summary | runc | replay_trajectory | pass | 0.191s |
| log-summary | kata | replay_trajectory | pass | 1.359s |
| log-summary | runc | fixed_output | pass | 0.132s |
| log-summary | kata | fixed_output | pass | 1.331s |
| constraints-scheduling | runc | replay_trajectory | pass | 0.786s |
| constraints-scheduling | kata | replay_trajectory | pass | 1.947s |
| constraints-scheduling | runc | fixed_output | pass | 0.788s |
| constraints-scheduling | kata | fixed_output | pass | 2.053s |
| jsonl-aggregator | runc | replay_trajectory | pass | 3.437s |
| jsonl-aggregator | kata | replay_trajectory | pass | 4.734s |
| jsonl-aggregator | runc | fixed_output | pass | 0.362s |
| jsonl-aggregator | kata | fixed_output | pass | 1.543s |

说明：

- `jsonl-aggregator` 的输入数据是按官方任务的 `task-deps/generate_records.py` 生成，约 100 万条记录。
- 任务初始化阶段已增加 cache，避免每次 replay 前重复生成初始化数据。
- 当前 wall time 是沙箱运行阶段，不包含任务包 scp 和初始 fixture 构建。

## 当前实现与官方 harness 的关系

官方 Terminal-Bench harness 的职责是：

```text
模型/Agent 接入 -> 沙箱终端 -> 任务执行 -> 测试验证 -> 日志与结果输出
```

本 PoC 保留：

```text
真实任务包
真实 oracle solution
真实测试逻辑
真实沙箱运行
真实 pass/fail verifier
```

本 PoC 替换：

```text
模型/Agent 接入 -> oracle solution 或 fixed output
联网 run-tests.sh -> 离线 mini_pytest
Docker harness -> ctr + runc/kata
```

这个取舍符合当前目标：构建不依赖大模型 API 的真实 benchmark 用例，后续用于 CPU 负载分析。

## DeepSeek API 的可选用途

当前不需要 DeepSeek API 即可跑通真实任务，因为 replay 使用官方 oracle solution。

DeepSeek API 后续适合用于两件事：

1. 捕捉真实 Agent 轨迹

   使用 DeepSeek 生成一次解决过程，把实际命令序列保存成：

   ```text
   trajectories/<task-id>/commands.jsonl
   trajectories/<task-id>/files.patch
   trajectories/<task-id>/final_artifacts/
   ```

   后续 CPU 测试只 replay 这些命令，不再调用模型。

2. 生成更多 Fixed Output

   对每个任务保存：

   ```text
   fixed_outputs/<task-id>/app/
   fixed_outputs/<task-id>/score.json
   ```

   后续只执行 verifier，测 evaluator 和沙箱开销。

建议下一步如果接 DeepSeek，不直接纳入 CPU 主测数据，而是只用于“轨迹采集阶段”。采集完成后，CPU 分析仍使用 replay/fixed，不调用模型。

## 下一步建议

1. 扩充任务子集

   优先筛选：

   ```text
   pure shell
   Python stdlib
   local data processing
   no apt/pip/npm/cargo online install
   no browser/GPU/daemon
   deterministic tests
   ```

2. 生成任务清单

   对每个任务标注：

   ```text
   dependencies
   needs_python
   needs_network
   replay_ready
   fixed_output_ready
   expected_runtime_class
   ```

3. 增加 task snapshot

   把 `/app` 初始化快照、fixed output 快照、replay 命令、score 都版本化，便于跨沙箱复用。

4. 适配 cloud-hypervisor

   在同一真实任务集上加入：

   ```bash
   --kata-config /opt/kata/share/defaults/kata-containers/configuration-clh.toml
   ```

5. 后续再做指标采集

   当前阶段先保证真实任务可复用。指标采集可以后置到下一阶段再扩展。

## 参考

- Terminal-Bench GitHub: https://github.com/harbor-framework/terminal-bench
- Terminal-Bench Harness docs: https://www.tbench.ai/docs/harness
- Terminal-Bench Agent interface docs: https://www.tbench.ai/docs/agent-introduction
