# Terminal-Bench Task Filtering v0

## Goal

筛选出适合在 AI 沙箱中运行的真实 Terminal-Bench 任务，用于后续 CPU 负载分析。当前阶段不直接依赖大模型 API，也不把注意力放在详细指标采集上。

## Source Set

当前本地克隆的 Terminal-Bench 仓库状态：

```text
repository: harbor-framework/terminal-bench
commit: 1a6ffa9
task directory: original-tasks/
task directories: 241
task.yaml present: 241
solution.sh present: 233
tests/test_outputs.py present: 238
analyzable tasks with solution + tests: 230
```

说明：用户提到 Terminal-Bench 约 89 个 task，这可能对应某个 Terminal-Bench-Core/leaderboard 子集。当前仓库的 `original-tasks` 中可见任务更多，因此 v0 以本地可见任务为全集做筛选。

## Filtering Criteria

保留任务必须尽量满足：

1. No model API: 不调用 DeepSeek/OpenAI/Claude 等模型 API。
2. Offline runnable: 不依赖运行时联网下载 apt/pip/npm/cargo 依赖。
3. Deterministic verifier: 使用规则测试、文件比较、JSON/CSV 校验、确定性 Python 测试。
4. Replay-friendly: 可以用官方 `solution.sh` 作为 oracle trajectory 来源。
5. Fixed-output-friendly: 可以保存 oracle 生成后的 `/app` 快照，只重放 verifier。
6. Sandbox compatible: 可在 `ctr + runc` / `ctr + kata` 中执行，避免复杂 daemon、GPU、浏览器、systemd、SSH、K8s、QEMU 嵌套等。
7. CPU-relevant: 任务应体现 shell、文件 IO、文本处理、数据处理、约束解析、JSONL 聚合、排序/扫描/解析等本地负载。

降低优先级或剔除：

- 需要在线安装依赖的任务。
- 需要浏览器、GUI、GPU、大型 ML 模型、外部服务的任务。
- 需要长期运行 server/daemon 的任务。
- 测试文件强依赖 pandas/numpy/torch/sklearn/selenium 等未预装第三方包。
- 需要主观评测或 LLM Judge 的任务。

## v0-Ready Tasks

这些任务已经进入远端 `/root/agent-cpu-sandbox-toolkit/terminal-bench-tasks/`，并至少通过一次无模型 replay 验证。

| Task | Category | Why Selected | Current Validation |
|---|---|---|---|
| log-summary | system-administration / logs | 轻量日志扫描，`grep/wc/CSV`，非常适合 smoke 和 fixed-output verifier | runc/kata replay+fixed pass |
| constraints-scheduling | personal-assistant / scheduling | ICS 文件解析、时间窗口约束、规则化 verifier，贴近真实助理类 Agent 任务 | runc/kata replay+fixed pass |
| jsonl-aggregator | file-operations / data processing | 官方生成约 100 万条 JSONL，适合数据密集型 CPU/IO 负载 | runc/kata replay+fixed pass |
| analyze-access-logs | data-science / log analytics | Web access log 统计，`awk/sort/head`，输入输出明确 | runc replay pass |
| bank-trans-filter | data-science / CSV filtering | CSV 解析、模糊匹配、JSON 输出，贴近结构化业务数据处理 | runc replay pass |
| assign-seats | algorithms / CSP | pickle/base64 解码 + 小型约束满足，纯 Python stdlib | runc replay pass |
| schedule-vacation | algorithms / scheduling | 多脚本调度、JSON 中间产物、时间区间求交 | runc replay pass |
| recover-accuracy-log | data-processing / logs | 多日志恢复、JSONL 拆分、准确率计算，贴近多 Agent 日志分析 | runc replay pass |

## v0-Ready Coverage

| Load Pattern | Covered By |
|---|---|
| shell text processing | log-summary, analyze-access-logs |
| CSV/JSON business data | bank-trans-filter |
| JSONL large data aggregation | jsonl-aggregator |
| calendar/time constraints | constraints-scheduling, schedule-vacation |
| encoded/binary input decoding | assign-seats |
| multi-run Agent log recovery | recover-accuracy-log |
| fixed-output verifier path | log-summary, constraints-scheduling, jsonl-aggregator |
| replay trajectory path | all v0-ready tasks |

## v0 Candidate Tasks

这些任务静态看起来适合，但尚未进入 v0-ready，原因通常是需要少量初始化适配、预装工具或镜像扩展。

| Task | Candidate Reason | Blocker / Required Adaptation |
|---|---|---|
| flood-monitoring-basic | CSV 时序插值和 flood event 检测，CPU/文件负载清晰 | 官方 Dockerfile 在 `/data` 生成输入；runner 需要支持额外挂载 `/data` 或初始化复制 |
| regex-log | 正则日志处理，规则化输出 | 需要实际跑通测试，确认输入是否由 Dockerfile 生成 |
| large-scale-text-editing | 100 万行 CSV + Vim 宏，适合大文本编辑负载 | 当前镜像缺少 `vim`；需要预构建离线镜像 |
| tree-directory-parser | 根据 `tree -F` 输出重建目录，文件系统负载好 | 需要 `tree` 命令、locale 和 build-time 数据生成适配 |
| heterogeneous-dates | 日期格式清洗和平均值计算，数据处理清晰 | 官方 solution 运行时 `pip install pandas`；需改为预装 pandas 镜像或使用 stdlib oracle |
| weighted-max-sat-solver | 优化/求解型任务，可能形成 CPU 计算负载 | 需要实际验证是否依赖额外求解器或测试第三方包 |
| predicate-pushdown-bench | 数据查询/优化负载潜力高 | 需要确认依赖和输入初始化 |
| regex-chess | 复杂规则生成/验证，CPU 压力强 | 任务过重且 solution 大；适合作后续高强度组，不进入 v0 |

## Static Screening Summary

静态扫描结果：

```text
analyzable tasks: 230
strict static candidates: 62
v0-ready: 8
v0-candidate: 8
```

静态候选并不等于可运行。Terminal-Bench 很多任务把输入生成逻辑写在 Dockerfile 的 `RUN` 或 `COPY` 中，当前无模型 runner 需要显式复刻这些初始化步骤，才能在 `ctr + runc/kata` 中稳定运行。

## Why Not Use All 89/241 Tasks Directly

不直接批量运行全部任务的原因：

1. 很多任务依赖在线安装，远端服务器无法访问 GitHub/外网。
2. 官方 `run-tests.sh` 默认安装 `uv/pytest`，不适合无网络环境。
3. 多数任务需要官方 base image 或 build-time 数据生成。
4. 部分任务需要服务进程、SSH、Nginx、QEMU、浏览器或 GPU，不适合作为 v0 的离线 CPU 基准。
5. 当前阶段目标是构建可复用 task packages，而不是最大化任务数量。

## Selection Policy for Next Version

v1 扩展建议按以下顺序：

1. 先把 v0-ready 的 8 个任务补齐 runc/kata replay+fixed 全矩阵。
2. 再从 v0-candidate 中补适配，每次只引入 3-5 个任务。
3. 为每个任务增加 `task_profile.json`：

```json
{
  "task_id": "log-summary",
  "offline": true,
  "runtime_dependencies": ["bash", "python3", "grep", "awk"],
  "init_strategy": "copy",
  "replay_ready": true,
  "fixed_output_ready": true,
  "sandbox_ready": ["runc", "kata"],
  "load_type": ["text_processing", "file_io"]
}
```

4. 需要 DeepSeek API 时，只用于捕捉非 oracle 的真实 Agent 命令轨迹；捕捉后仍以 replay/fixed 方式做 CPU 测试。
