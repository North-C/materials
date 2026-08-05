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

### 3.1 如何理解 `direct_timings_ms`

`direct_timings_ms` 中的“direct”表示数据来自已有计时器，或者来自同一时钟上的两个直接时间戳。它不表示各行互斥，也不表示各行可以相加。

以下面一轮 3U2G `c50n500` 数据为例，各边界的关系是：

```text
T0  create req start
 |
 |  sandbox 创建窗口                         Avg  75.250ms
 |  `-- VM start -> agent ready              Avg  46.878ms
 |
Ts  sandbox finish
 |
 |  container 创建窗口                       Avg  35.581ms
 |  `-- Shim CreateContainer                 Avg  35.026ms
 |      `-- Guest receive -> restore branch  Avg   0.713ms（498/503）
 |
Tc  container finish                         累计 Avg 110.831ms
 |
 |  request 收尾                             Avg   0.546ms
 |
Tf  create req finish                        总计 Avg 111.377ms
```

平均值可以按外层互斥窗口闭合：

```text
sandbox 创建窗口 + container 创建窗口
= 75.250497 + 35.580517
= 110.831014ms（container finish cumulative）

container finish cumulative + request 收尾
= 110.831014 + 0.545539
= 111.376553ms（create request total）
```

| 字段 | Count | 计时边界 | 示例 Avg | 如何解读 |
|---|---:|---|---:|---|
| `shim_create_container` | 503 | Shim `CreateContainer` 的 StatDefer | 35.026ms | 从请求参数准备开始，覆盖 agent client lock、完整 CreateContainer RPC、Guest 处理、RPC 返回和 Shim 状态更新 |
| `create_request_total` | 503 | `create req start -> create req finish` | 111.377ms | 整个 Shim create request 的最外层窗口，包含 sandbox 创建、container 创建及少量收尾 |
| `vm_start_to_agent_ready` | 503 | `start vm start -> agent is ready` | 46.878ms | sandbox 创建窗口内的重叠子窗口，覆盖 VMM 启动、restore、等待 vsock 和连接 agent |
| `sandbox_finish_cumulative` | 503 | `T0 -> sandbox finish` | 75.250ms | 从 request 起点累计到 sandbox 完成，是累计位置，不是可与其他行相加的独立阶段 |
| `container_finish_cumulative` | 503 | `T0 -> container finish` | 110.831ms | 从 request 起点累计到 container 完成，同样是累计位置 |
| `sandbox_to_container_finish` | 503 | 对每个实例计算 `Tc - Ts` | 35.581ms | sandbox 完成后的 container 创建窗口；与 Shim `CreateContainer` 近似同窗 |
| `guest_receive_to_restore_branch` | 498 | Guest 内两个高精度时间戳之差 | 0.713ms | Guest 收到 RPC 后进行 OCI 转换、读取 annotation 并选择 restore 分支的时间；本轮只有 498 个完整标记对 |

本轮各外层窗口占 `create_request_total` 的比例为：

| 外层窗口 | Avg | 占 request total | 判断 |
|---|---:|---:|---|
| request start 到 sandbox finish | 75.250ms | 67.6% | 当前最大的外层窗口 |
| VM start 到 agent ready | 46.878ms | 42.1% | sandbox 窗口中的主要已知组成，但不能与其父窗口相加 |
| sandbox finish 到 container finish | 35.581ms | 31.9% | container 创建窗口 |
| Shim `CreateContainer` | 35.026ms | 31.4% | 基本覆盖 container 创建窗口 |
| container finish 到 request finish | 0.546ms | 0.5% | request 收尾，可忽略 |

因此，本轮的主要耗时不再是 `CreateContainer`。最大的外层窗口是 sandbox 创建，其中 `VM start -> agent ready` 是当前首要已知子窗口；`CreateContainer` 已降到约 35ms，但仍是第二个较大的阶段。只有在测试环境、Template 和代码配置一致时，才能将它与旧轮次对比并判断为热点迁移。

`sandbox_to_container_finish` 与 `shim_create_container` 的 Avg 分别为 35.581ms 和 35.026ms，差约 0.555ms。二者数值接近，说明 CreateContainer 基本覆盖了 sandbox 完成到 container 完成的窗口；但它们是近似同窗的两套边界，不能相加。

`guest_receive_to_restore_branch` 不包含 Shim 到 Guest 的 RPC 传输，也不包含 restore 分支之后的 sandbox lock、PID 查找、`start_exec_process`、RPC 返回。它很短，只能说明 Guest 收到请求后的分支判断不是热点。

本轮 `guest_receive_to_restore_branch.count=498`，而 `shim_create_container.count=503`，所以不能直接用两个整体 Avg 相减计算正式残差。应读取 `diagnostic_residual_ms.restore_path_unresolved`；分析器只对具有完整 Guest 标记的同一 InstanceId 做差。还应同时检查 `path_counts`、`marker_coverage.guest_create_receive_ms` 和 `marker_coverage.guest_restore_branch_ms`，判断缺少的 5 条是日志转发缺失还是路径不同。

阅读 `direct_timings_ms` 时必须遵守以下规则：

1. `sandbox_finish_cumulative` 和 `container_finish_cumulative` 都从 T0 起算；只有两者逐实例相减才得到 container 窗口，不能把两行相加。
2. `shim_create_container` 被 `create_request_total` 包含，`guest_receive_to_restore_branch` 又被 `shim_create_container` 包含，嵌套行不能相加。
3. `vm_start_to_agent_ready` 是跨多个 Shim 子阶段的重叠窗口，不能再与 `LaunchVmm`、`RestoreVm`、`ResetVm` 直接求和。
4. Avg 在 503 个样本一一对应时可以用于检查均值闭合；P50/P95/Max 必须先按 InstanceId 计算差值，再对差值求统计量，不能直接使用汇总行相减。例如本轮 `sandbox cumulative P50 65ms + container window P50 29ms = 94ms`，并不等于 `container cumulative P50 104ms`。
5. `count` 必须先一致。Guest 阶段本轮只有 498 条，不能与 503 条 Shim 阶段直接做整体 Avg 差；API 正式请求通常为 500 条，而组件分段为 503 条（包含 3 个 warmup），也不能直接逐样本比较。
6. 当前粘贴数据未给出 `sandbox_finish_cumulative.p95`。这不影响 Avg 闭合，但在判断 sandbox 窗口长尾前应先确认是粘贴遗漏还是原始 JSON 缺失。

如需查看顺序和包含关系，应同时打开 `stage-latency.csv`：`parent_stage_id`/`hierarchy_path` 表示包含链，`sequence_group`/`sequence_index` 表示执行顺序，`additivity=do_not_sum` 表示禁止直接相加。

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
