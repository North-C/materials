# scripts_v2 审计：用于 CubeSandbox v0.7.1 Template 启动分析的可信边界

审计日期：2026-10-12。

**结论：旧工具能较可靠地定位已观测到的主要耗时窗口，但不能直接给出正式 c100n100 全样本、各阶段互斥且可相加的完整启动时间轴。** 它保留了父子关系、同实例累计计时和 Guest 内嵌时间戳等有价值的证据；主要缺口是请求归属、短阶段日志截断、重复调用配对、采集完整性以及 Prometheus 数据尚未进入分析。

本审计固定以下源码版本，避免 `main` 更新后行号与结论漂移：

- 历史工具：[North-C/materials `c4b243acfaa6d8e41f6524ebe920c49b9cda2c91`](https://github.com/North-C/materials/tree/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2)。审计包含采集器、分析器、host sampler，以及采集器调用的 `run_cubesandbox_openeuler_template_perf.sh`。
- 新版本边界：[CubeSandbox v0.7.1，commit `31d911e430fdf8a8879bd062b8e78066c1a8e89d`](https://github.com/TencentCloud/CubeSandbox/tree/31d911e430fdf8a8879bd062b8e78066c1a8e89d)。本文是在该版本源码上核对计时含义，不表示旧压测当时的部署二进制就是 v0.7.1。

## 1. 哪些计时仍可信

下列结论成立的前提是：实例归属明确、成功/失败路径已区分、单实例 marker 配对唯一、采集没有丢失所需边界。计时窗口可信与样本统计具有代表性是两件事。

| 观测项 | 可以声称的含义 | 不能声称的含义与证据 |
|---|---|---|
| 客户端 `benchmark.create` | cube-bench 报告中的客户端 Create 延迟 | 不是组件时长之和，也不能仅凭 seq 对齐某个 sandbox ID。旧分析器直接读取 benchmark 报告，并按每 50 条 raw 分块；组件集合另外建立。[旧分析器 L519–545][v2-analysis-population] |
| CubeMaster `cube-e2e` | CreateSandbox 服务逻辑开始至返回 defer 中生成响应扩展信息的耗时 | 与客户端边界不同；两个总体 Avg/P95 相减不能当作网络时延。起点见 [sandbox_run.go L116–141][master-start]，成功响应扩展值见 [L701–719][master-probe]。 |
| Cubelet `sandbox-create`、`sandbox-start` | 前者覆盖 `NewTask`，后者覆盖从同一 `taskStart` 到 `Wait`、`Start` 和状态更新结束的累计窗口 | 两者嵌套，不能相加；只有同一实例、同一次调用的差值才近似表示后半段。[cube_container_create.go L1353–1392][cubelet-task] |
| Shim `StatDefer` 阶段 | 单调时钟 `Instant` 的作用域耗时，整数毫秒向下截断 | `0ms` 是小于 1ms 的观测，未必是没有执行；退出异常路径也会写 stat，应检查 RetCode。没有阶段结束时间就只能列 duration。[stat_defer.rs L74–114][shim-stat] |
| Shim sandbox/container cumulative | 从同一 `Instant` 到两个 marker 的累计值；逐实例相减可得到两边界之间的窗口 | 累计值是位置，不是两个独立可加阶段。计时起点位于 `create req start` 日志之后，不能假设与该日志时间戳完全同源同起点。[task_srv.rs L328–398][shim-markers] |
| `VM start → agent ready` | 同一 Shim host 日志时钟上的边界差，覆盖 VM 启动/恢复和 Agent 连接等前置工作 | 不是所有 VM 子阶段的精确分解；不包含后续 `ResetVm`。[sb.rs L472–497][shim-ready] |
| Guest receive → restore branch | 使用 Guest JSON 内嵌 `ts`，衡量接收处理到选择 restore 分支的窗口 | 不含 restore 分支之后的锁等待、passfd/日志流恢复、`start_exec_process`、RPC 返回。源码见 [rpc.rs L156–215][guest-restore]；旧分析器采用内嵌时间而不是转发到达时间的做法正确。[L408–451、L504–512][v2-guest] |

旧工具还正确区分了 `sandbox-probe` 传播副本、`all-probe` 聚合值和 `cubebox-service-inner` 派生残差。v0.7.1 中 Master 只复制 Cubelet 的 Probe 字段并求和，并没有因此再做一次 Probe；`cubebox-service-inner = service - probe - images/volume` 也不是连续独立代码段。[Master L701–719][master-probe]；[Cubelet L446–483][cubelet-residual]。

## 2. 请求归属与统计偏差

旧分析器从日志增量中所有 `Action=Create && Callee=cubebox-service` 记录取得 InstanceId，再筛 Cubelet、Shim 和 Master。它没有用正式压测实例清单建立集合，也没有把 warmup 与正式请求分开。因此常见的 API 500 条、组件 503 条差异是两套样本总体，不能据此做逐项对齐；若同一采集窗口存在其他创建，还可能纳入非本轮实例。[旧分析器 L533–577][v2-analysis-population]。

按阶段分组时只检查 stage 和 CostTime 是否为有限数，没有过滤成功状态、负耗时或同实例重复记录。异常路径和重试会改变该阶段分布；记录条数也不等于独立成功实例数。[旧分析器 L71–83][v2-group]。Shim 本身在异常退出时仍可记录时长，因此分析前必须检查 RetCode。[StatDefer L81–114][shim-stat]。

Cubelet 成功阶段耗时 `<5ms` 时不输出 Trace。旧脚本对剩余记录求 Avg/P50/P95，得到的是“被日志保留下来的阶段记录”的条件分布。尤其是 network、storage、metadata 等短阶段，低覆盖率不意味着其他实例耗时为零，也不能把慢样本平均值称为该阶段的全样本均值。[service.go L497–509][cubelet-trace]。与此不同，`dealCreateInnerMetric` 会把已有 metric 写入 Cubelet 响应 `ExtInfo`；能否采集完整响应应单独核实，不能假设 Master 的成功响应会原样透传所有 Cubelet metric。[service.go L453–455][cubelet-residual]；[Master L709–719][master-probe]。

旧分位数使用 nearest-rank，本身没有算法错误。问题在于分位数所属总体和覆盖率：P95 必须与该行 count、失败数、唯一实例数一起解读；不能把父子阶段 P95 相减，也不能拼接不同实例的分位数形成一个“P95 请求”。[旧分析器 L37–54][v2-stats]。

## 3. 并行、包含和派生量

v0.7.1 默认创建 workflow 是：

```text
[createid, appsnapshot]
    → [images, volume, storage, network, netfile, cube-sandbox-store]
    → [cgroup]
    → [cubebox]
```

方括号内 action 并行，step 之间串行。配置见 [config.toml L177–179][workflow-config]；引擎逐 step 执行见 [engine.go L415–417][workflow-serial]，同 step 使用 errgroup 并发见 [L476–508][workflow-parallel]。这说明不能把 network、storage 等同一步的 duration 相加当作串行关键路径，实际部署的 workflow 配置也需要留证。

旧 CSV 把 network/storage 置于 cubebox 子层级，和上述默认 workflow 不符；它们属于 Cubelet service 中先于 cubebox 的工作。[旧分析器 L170–188][v2-topology]。另外，旧 CSV/说明把 `VM start → agent ready` 与 ResetVm 关联为重叠窗口；v0.7.1 实际先打印 `agent is ready`，之后才执行 `reset_guest`，应纠正这一关联。[旧分析器 L263–267][v2-vm-window]；[sb.rs L482–487][shim-ready]。

`cubebox-inner` 由 cubebox 减去所有 sandbox/container 前缀 metric 得到，内部同时含有嵌套的 sandbox-create/start，因此可能重复扣减。不能把这个残差当成严格测得的“未打点代码时长”。[service.go L464–477][cubelet-residual]。

## 4. 旧输出为何只是部分时间轴

旧 CSV 的 `flow_order`、`parent_stage_id` 和 `sequence_group` 是源码关系元数据，不是每个请求实测的 start/end 时间。Cubelet 在服务退出后异步批量调用 `reportTrace`，日志 Timestamp 是记录输出时刻，不能用 `Timestamp - CostTime` 为每一个 Cubelet action 恢复开始位置。[service.go L312–326][cubelet-batch]；[L497–509][cubelet-trace]。

Shim marker 提供了更可靠的局部边界，但旧实现对普通 marker 取第一次、累计 marker 取最后一次，对 CreateContainer stat 又按 InstanceId 覆盖为最后一条。在同实例多容器、重复调用或重复采集下，可能把不同调用的开始、结束和 duration 拼接在一起。[旧分析器 L381–406][v2-pairing]。它的 difference 也没有拒绝负值，日志乱序或墙钟变化可能产生负差值。[L112–117][v2-difference]。

因此能输出的是“有证据的 Shim 局部时间轴 + 不能定位的其他阶段时长”。应保留以下缺失，而不是推导成精确测量：

- 无起止点的 Cubelet、Master、Shim stat 不能直接画成精确区间。
- Host 墙钟 marker 与单调计时累计值起点不同；二者的偏差同时包含日志开销、起点偏移、整数截断与可能的墙钟调整。
- Guest stdout/stderr 经异步转发，host 包装时间不能作为 Guest 事件真实发生时间。
- `Shim CreateContainer - Guest receive_to_restore_branch` 只能称为诊断残差；v0.7.1 该剩余窗口还包括 passfd 建连/重连、sandbox mutex、reset log readers、exec 及 RPC 等。[rpc.rs L176–215][guest-restore]。

## 5. metrics、采集窗口与日志轮转

旧采集器确实读取压测前后 `/v1/metrics`，但旧分析器没有解析这两个 Prometheus 文件，不能把其结果称为“已经融合 metrics 差分的各阶段延迟”。[采集器 L35、L94][v2-capture]；[旧分析器的最终结果 L627–659][v2-output]。

补充 metrics 时，应按完整 label set 匹配 counter/histogram 的前后值、验证单调性和进程是否重启，再计算有意义的增量。Histogram 的 `Δsum/Δcount` 是该指标总体的平均值，bucket 只能支持分桶估计，不能恢复单实例时间轴；也不能把累计 summary quantile 做差当成本轮 P95。采集窗口包含 warmup、准备、清理或其他请求时，metrics 总体与正式请求日志总体并不自动相同。特别是旧 runner 可能在前后恢复阶段重启 Cubelet，前后计数器可能跨进程生命周期；发生 reset 时不能继续把简单相减解释成一次完整压测。

日志增量采集检查 inode 和 size，但遇到轮转/缩短后会直接复制当前整个文件并写 warning。这既无法追回旧 inode 的未采集尾部，又可能引入当前文件中与本轮无关的记录；仅输出 warning 不足以证明分析完整。[run_c50_profile.sh L96–112][v2-rotation]。按 size 截取也不自动保证行边界完整。旧 JSONL 读取遇到无法解析的行会静默忽略，缺失数量没有进入质量报告。[旧分析器 L57–68][v2-jsonl]。

Host sampler 在检测到 STARTUP_BEGIN 后运行 12 秒，BPF 固定 8 秒；这个触发位于 runner 发起包含 warmup 的 cube-bench 之前。窗口未随正式请求首尾界定，可能含 warmup、漏掉长尾或覆盖后续清理。BPF/host 仅能解释宿主机区间压力，不能直接分配给每个实例的某个阶段。[采集器 L37–76][v2-sampling]；[runner L300–303][v2-run-case]。

## 6. 固定负载与旧 runner 的全局恢复行为

`run_c50_profile.sh` 固定传 `CASE_MATRIX="$case_name 50 500"`。改 CASE_NAME 并不会得到 c100n100；runner 每轮另执行 3 个 warmup。[采集器 L79–87][v2-case]；[runner L302–303][v2-run-case]。分析器还固定每 50 条做分块，CSV 文案硬编码了 500/503，迁移负载后需要同步修正。[分析器 L523–530][v2-analysis-population]；[L133–146][v2-hardcoded]。

旧 runner 的测试前后都执行 `recover_empty_runtime`。其 `cleanup_sandboxes` 枚举 API key 可见的全部 `/sandboxes` 并删除，没有按本轮 run ID、Template 或创建归属过滤；残留 shim/task 时还可能对全部匹配进程发 TERM/KILL，并 stop/start Cubelet。它建立的是一个经过全局恢复的空运行时基线，不是只影响本轮实例的清理流程。[runner L78–158][v2-recovery]；[L295–317][v2-run-case]。

这些行为可能改变 host 缓存、服务生命周期及 metrics counter，必须计入历史实验条件。不能仅因为此次测试改用 c100n100 就沿用这套恢复逻辑；同样，新的仅清理本轮实例流程与历史全局恢复流程条件不同，跨轮性能比较需要披露这一差别。本审计只读取代码，没有执行旧恢复、删除或重启操作。

## 7. 审计后的可接受表述

可以报告：指定版本、Template 与负载下，正式成功请求的客户端延迟；有明确归属、覆盖率和结果状态的阶段统计；唯一 marker 配对得到的 Shim 局部区间；以及标明样本总体和 reset 检查结果的 metrics 增量。

不能报告：把旧 503 条组件记录直接当作 500 条正式请求；把 `<5ms` 未输出阶段补零；把并行/父子/累计/Probe 副本相加；从异步批量 Trace 时间反推每阶段位置；把跨总体 P95 差解释成新阶段；或把 CreateContainer 诊断残差称为实测 `start_exec_process`。

源码不能替代现场验证。实际分析仍需保存部署版本证据、有效 workflow 配置、Template 的 2u2g/1G 参数和构建来源、正式与 warmup 归属证据，以及日志采集缺口与重复 marker 数量。以上审计没有把这些待验证项视为已完成的测试事实。

[v2-analysis-population]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L519-L577
[v2-group]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L71-L83
[v2-stats]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L37-L54
[v2-guest]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L408-L512
[v2-topology]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L170-L188
[v2-vm-window]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L263-L267
[v2-pairing]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L381-L406
[v2-difference]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L112-L117
[v2-jsonl]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L57-L68
[v2-output]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L627-L659
[v2-hardcoded]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/analyze_c50_profile.mjs#L133-L146
[v2-capture]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/run_c50_profile.sh#L35-L94
[v2-rotation]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/run_c50_profile.sh#L96-L112
[v2-sampling]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/run_c50_profile.sh#L37-L76
[v2-case]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/run_c50_profile.sh#L79-L87
[v2-recovery]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/run_cubesandbox_openeuler_template_perf.sh#L78-L158
[v2-run-case]: https://github.com/North-C/materials/blob/c4b243acfaa6d8e41f6524ebe920c49b9cda2c91/ai_sandbox/cubesandbox/perf/scripts_v2/run_cubesandbox_openeuler_template_perf.sh#L289-L323
[master-start]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L116-L141
[master-probe]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L701-L719
[cubelet-task]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/cube_container_create.go#L1353-L1392
[cubelet-residual]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L446-L483
[cubelet-trace]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L497-L509
[cubelet-batch]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L312-L326
[workflow-config]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/config/config.toml#L177-L179
[workflow-serial]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/plugins/workflow/engine.go#L415-L417
[workflow-parallel]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/plugins/workflow/engine.go#L476-L508
[shim-stat]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/log/stat_defer.rs#L74-L114
[shim-markers]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/service/task_srv.rs#L328-L398
[shim-ready]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/sandbox/sb.rs#L472-L497
[guest-restore]: https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/agent/src/rpc.rs#L156-L215
