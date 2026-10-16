# CubeSandbox 启动分析报告

并发 100；正式计划请求 100；正式进程内置预热 0。 独立预热计划 3 次，成功 3 次，状态 complete。 数据范围受限（limited）：客户端计时可用，组件阶段仅覆盖有可靠实例 ID 的样本；缺失归属时无法生成按实例的阶段统计。

## 整轮耗时

| 口径 | 耗时 | 数据来源 | 覆盖范围 |
| --- | --- | --- | --- |
| 正式测试整轮耗时 | 482.8875 ms | raw.summary.total_time_s | Runner's measured formal workload, excluding warmup under the cube-bench contract. Includes scheduling and result collection; create-delete mode also includes deletion. Generic producers must use this same scope. |
| 外部命令窗口 | 未提供（missing） | 无 |  |
| 采集窗口 | 22064.187988 ms | manifest.started_at/ended_at | Collector's entire wall-clock capture window, including surrounding log/metrics collection. Not the formal benchmark duration. |
| 独立预热命令耗时 | 196.25793 ms | prewarmup.duration_ms | 正式采集之前的独立进程；不计入正式测试整轮耗时 |

整轮耗时是正式测试从开始到结束的经过时间，不是单次延迟的总和或最大值。外部命令可能包含预热、初始化、清理；采集窗口还可能包含 metrics 和日志收尾。整轮计时缺失时不使用后两者代替。

## 单次启动时延

| 指标 | 值 |
| --- | --- |
| 有效样本数 | 100 |
| 平均值 (ms) | 344.72428 |
| P50 (ms) | 366.321 |
| P95 (ms) | 480.239 |
| 最大值 (ms) | 481.805 |

| 请求统计 | 值 |
| --- | --- |
| observed | 100 |
| successful | 100 |
| errors | 0 |
| valid_latency | 100 |

## warmup 与样本口径

warmup 是正式测量前的预热操作，用于让连接、缓存和资源池预先被使用。官方 cube-bench 串行执行预热，然后开始正式测试；create-only 每次创建，create-delete 每次还包含删除；预热不进入其正式 raw 样本和 summary.total_time_s。自定义 runner 必须明确自己的计时和样本范围。预热不保证消除所有冷启动开销。

本次采用独立进程预热：计划 3 次，成功 3 次，状态 complete，进程退出码 0。正式 cube-bench 使用 -w 0。预热进程耗时单独列出，不加入正式整轮耗时；它与原内置 warmup 不同，正式进程不复用预热进程的 HTTP 连接。预热在正式日志采集窗口之前执行；实例归属依赖预热后的 CLI 基线和正式请求后的清单差集。metrics 是全局指标，仍可能包含背景活动或延迟上报。

组件分组状态：declared。unknown_phase 可能混有预热；declared 仅表示用户声明。阶段样本集合与客户端样本集合不一定相同，父子与并行阶段不能相加。 实例 ID 来源包含 cubemastercli 前后清单：候选 100 个，在用户声明模板独占且正式进程内置预热为 0 的前提下，使用正式命令前后清单差集推定 formal 集合；这是集合级归属，不是逐请求关联。此方式不提供客户端 seq 到实例的映射，CLI 的节点遍历计数不证明每个节点查询成功。

## 已观测阶段

| 分组 | 归属实例数 | 有观测的阶段数 | 统计口径 |
| --- | --- | --- | --- |
| formal | 100 | 20 | 正式集合；归属证据及限制见下文 |
| warmup | 0 | 0 | 预热集合 |
| unknown_phase | 0 | 0 | 实例已归属本轮，但正式/预热阶段未确认；保留观测，不用于正式分布 |

共展示 20 个分组阶段的观测统计；unknown_phase 中有观测的阶段同样展示，不会因为分组未知而隐藏。未观测阶段与全部覆盖缺口见阶段 CSV 和 analysis.json。

| 分组 | 阶段 | 实例覆盖 | 样本数 | 平均 ms | P50 ms | P95 ms | 最大 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| formal | Cubelet.cgroup | 67/100 | 67 | 80.085119 | 79.218 | 154.006 | 214.302 |
| formal | Cubelet.create-sandbox-metadata | 62/100 | 62 | 22.558016 | 22.846 | 43.767 | 51.049 |
| formal | Cubelet.cubebox | 100/100 | 100 | 214.44561 | 227.862 | 283.507 | 299.421 |
| formal | Cubelet.cubebox-service | 100/100 | 100 | 287.91642 | 295.288 | 409.821 | 411.756 |
| formal | Cubelet.cubebox-service-inner | 100/100 | 100 | 254.10194 | 253.272 | 394.12 | 397.48 |
| formal | Cubelet.gen-spec-sandbox | 37/100 | 37 | 16.418 | 15.059 | 34.046 | 38.121 |
| formal | Cubelet.network | 21/100 | 21 | 8.229095 | 7.554 | 12.207 | 14.519 |
| formal | Cubelet.sandbox-create | 100/100 | 100 | 148.02059 | 155.902 | 200.787 | 224.529 |
| formal | Cubelet.sandbox-probe | 100/100 | 100 | 33.74342 | 32.97 | 60.09 | 72.594 |
| formal | Cubelet.sandbox-start | 100/100 | 100 | 157.89619 | 163.052 | 225.262 | 250.759 |
| formal | Cubelet.storage | 87/100 | 87 | 20.500747 | 23.064 | 61.23 | 67.86 |
| formal | Shim.CreateContainer | 100/100 | 100 | 16.61 | 13 | 30 | 64 |
| formal | Shim.CreatePodSandbox | 100/100 | 100 | 65.49 | 64 | 89 | 111 |
| formal | Shim.CreateSandbox | 100/100 | 100 | 1.55 | 1 | 7 | 11 |
| formal | Shim.LaunchVmm | 100/100 | 100 | 1.14 | 1 | 2 | 2 |
| formal | Shim.ResetVm | 100/100 | 100 | 13.7 | 13 | 27 | 33 |
| formal | Shim.RestoreVm | 100/100 | 100 | 19.08 | 13 | 41 | 52 |
| formal | Master response.cube-e2e | 100/100 | 100 | 294.82 | 304 | 419 | 422 |
| formal | Master response.sandbox-probe | 100/100 | 100 | 33.25 | 32 | 60 | 72 |
| formal | Master response.all-probe | 100/100 | 100 | 33.25 | 32 | 60 | 72 |

查看 [阶段 CSV](stage-latency.csv)、[完整分析 JSON](analysis.json) 和 [runner 原始结果与校验记录](benchmark-inputs/)。

## 数据文件

- [完整汇总 JSON](run-summary.json)
- [完整分析 JSON](analysis.json)
- [阶段 CSV](stage-latency.csv)
- [实例时间轴](timeline.html)
- [客户端样本（脱敏副本）](benchmark-inputs/)
- [发布文件校验清单](../../../../../publication-evidence-verification.json)
- [实例归属（脱敏结果）](phase-classification.json)

benchmark-inputs 是脱敏副本；数值保留，文件字节不同于原件。发布清单仅校验发布副本。

## 数据限制

- Command/capture timestamps use collector wall time and can be affected by clock adjustments; they are not monotonic runner timing.
- CLI inventory: operator_asserted_template_exclusivity
- CLI inventory: healthy_nodes_inventory_only
- CLI inventory: node_query_failures_may_be_omitted_despite_complete_reported_scan
- CLI inventory: ownership_inferred_not_independently_verified
- CLI inventory: client_samples_not_mapped_to_instances
- CLI inventory: formal_only_requires_validated_warmup_zero_benchmark
- cubemastercli_instance_ids_collected: 100 formal run IDs available under declared template exclusivity and validated cube-bench warmup=0
- client_sample_id_mapping_unavailable: CLI inventory does not map client seq to server IDs
- 正式窗口 CLI 差集提供实例集合，仍无客户端 seq 到实例 ID 的逐条映射；正式分组基于模板独占声明。
- 脱敏发布副本：时延样本、顺序、统计及时间戳保留；实例使用本实验一致别名。私有配置、完整环境、原始组件日志、Docker inspect及CLI清单未公开，不能从副本重放原始日志解析。
- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- Whole-run duration measures concurrent workload completion, not a sum or maximum of individual request latencies.
- Timing fields and generic clock declarations are producer-supplied evidence; they do not independently certify workload execution or success.
- Request counts describe supplied raw rows; missing raw input remains unknown even when a summary reports totals.
- create_latency_ms is the existing profile.benchmark.create distribution of valid successful samples, not whole-run timing.
