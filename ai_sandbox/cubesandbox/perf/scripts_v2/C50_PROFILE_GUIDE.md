# c50 profiling 采样与汇总工具

## 1. 工具组成

| 文件 | 用途 |
|---|---|
| `run_c50_profile.sh` | 运行 c50 压测、截取各组件增量日志、采集 host/BPF 数据，并生成 CreateContainer 精简事件流 |
| `analyze_c50_profile.mjs` | 按 InstanceId 关联 API、CubeMaster、Cubelet、Shim 及 CreateContainer 事件，输出汇总和逐实例明细 |
| `sample_c50_host.sh` | 周期采集 CPU、调度、进程和 shim 数量 |
| `run_cubesandbox_openeuler_template_perf.sh` | 执行 warmup、并发创建和清理门禁 |

采样节点需要 Bash、`jq`、`rg`、`curl` 和 `bpftrace`。采样脚本默认读取 `/data/log`，因此应在 CubeSandbox 计算节点上以有权读取日志和运行 bpftrace 的用户执行。汇总机需要 Node.js；可以把完整 profile 复制到开发机后再运行分析器，采样节点本身不要求安装 Node.js。

## 2. 运行新测试

```bash
BASE_DIR=/home/lyq/cubesandbox-profile-tools-v2 \
OUT_DIR=/home/lyq/results/profile-c50-n500 \
CASE_NAME=community-baseline-3u2g-c50-n500 \
TEMPLATE_ID=<template-id> \
  bash /home/lyq/cubesandbox-profile-tools-v2/run_c50_profile.sh
```

runner 和 host sampler 默认从 `run_c50_profile.sh` 所在目录读取；只有拆分部署时才需要通过 `RUNNER`、`HOST_SAMPLER` 覆盖路径。`BASE_DIR` 只用于默认结果目录，显式设置 `OUT_DIR` 后不参与工具定位。

`run_c50_profile.sh` 当前固定向 runner 传入 `CASE_MATRIX="$CASE_NAME 50 500"`，即最大并发 50、正式请求 500；runner 另执行 3 个 warmup。它不会重试失败的正式请求。

采样完成后新增：

```text
evidence/create-container-events.jsonl
evidence/create-container-sampling.txt
```

前者只保留带 InstanceId 的 CreateContainer 相关事件。后者记录 schema 版本、来源和事件条数。完整 `shim_req-delta.log` 仍保留用于审计。

## 3. 汇总

```bash
node ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs <profile-dir> \
  --details-out <profile-dir>/create-container-details-v2.jsonl \
  --csv-out <profile-dir>/stage-latency.csv \
  > <profile-dir>/analysis-v2.json
```

分析器优先读取 `evidence/create-container-events.jsonl`；旧数据没有该文件时自动回退到 `evidence/shim_req-delta.log`，因此旧 profile 仍可直接重放。

`--csv-out` 可省略；默认生成 `<profile-dir>/stage-latency.csv`。CSV 将阶段统计、执行顺序和包含关系放在同一行，适合直接用表格软件筛选和排序：

| CSV 列 | 含义 |
|---|---|
| `flow_order` / `depth` | 按创建流程阅读的排序值和层级缩进 |
| `stage_id` / `parent_stage_id` | 稳定阶段标识及直接父阶段；据此可还原包含树 |
| `hierarchy_path` | 已展开的完整包含链，可直接阅读而不必递归查找父行 |
| `containment_relation` | `inside` 表示直接包含；`equivalent_window` 表示近似同窗；`propagated_copy` 表示传播副本；`derived_from` 表示派生量 |
| `sequence_group` / `sequence_index` | 同组阶段的实际执行顺序；空值表示当前证据不能确认顺序 |
| `previous_stage_id` | 同组中直接前序阶段 |
| `related_stage_ids` | 重叠窗口、传播来源或聚合成员，不代表父子关系 |
| `timing_kind` | 直接外层、直接内层、累计边界、传播指标、派生残差等计时类型 |
| `additivity` | 是否属于可解释的顺序子段；`do_not_sum` 的行不得直接相加 |
| `count` 至 `max_ms` | 样本数和阶段时延统计 |

推荐先按 `flow_order` 升序阅读主流程，再用 `parent_stage_id` 查看包含关系。即使两个阶段 Avg 数值接近，只要关系为 `inside` 或 `equivalent_window`，就不能把它们相加。

`analysis-v2.json` 的 `create_container_detail` 包含：

| 字段 | 含义 |
|---|---|
| `event_source` / `raw_event_count` | 实际读取的数据源和 JSONL 事件数 |
| `path_counts` | restore、normal-create 或 unknown 路径的实例数 |
| `marker_coverage` | 每个边界成功关联到多少实例 |
| `direct_timings_ms` | 只使用同一时钟或已有 StatDefer 的直接计时 |
| `normal_path_agent_timings_ms` | 社区 normal-create 汇总日志中的五个 agent 子阶段；restore 路径为 `null` |
| `diagnostic_residual_ms` | 用于缩小排查范围的差值，不能当成单函数直接计时 |

所有统计均输出 `count/avg/min/p50/p95/max`，单位为 ms。RFC3339 日志的小数秒会被保留；分位数使用 nearest-rank：将样本升序排列后取 `ceil(p*N)` 对应值。

逐实例 JSONL 每行对应一个 InstanceId。分析长尾时先按 `shim_create_container_ms` 排序，再检查 marker 是否完整和 `path` 是否一致，不要只看整批平均值。

## 4. CreateContainer 计时边界

| 字段 | 计算方式 | 是否可直接解释 |
|---|---|---|
| `shim_create_container_ms` | Shim `CreateContainer` StatDefer | 是 |
| `sandbox_to_container_finish_ms` | Shim 同一累计计时器的 container finish 减 sandbox finish | 是 |
| `guest_receive_to_restore_branch_ms` | Guest 内嵌时间戳相减 | 是，只表示分发和分支选择 |
| `restore_path_unresolved_ms` | Shim CreateContainer 减 Guest 分支选择 | 否；包含请求准备、RPC 和 `start_exec_process` |

Guest stdout/stderr 经过 wrapper 异步转发，外层 `Timestamp` 可能发生乱序。分析器只用 `LogContent` 中的 guest `ts` 做 guest 内部差值，不使用 wrapper 到达时间计算阶段。

要直接拆开 restore 路径的锁等待、子进程 spawn 和 wait，仍需在社区 `start_exec_process` 内增加结构化计时点；现有社区 metrics 没有这些 RPC latency histogram。

## 5. `.90` 集成验证

2026-08-05 已在 `192.168.25.90` 使用社区原版 openEuler 3U2G Template 完成真实 `c50n500`：500/500 成功，runner/watcher 均退出 0，测试后 0 sandbox、0 shim、0 task。采集得到 503 个关联实例和 5,531 条 CreateContainer 精简事件，本地汇总生成 26 个阶段、22 列关系 CSV。
