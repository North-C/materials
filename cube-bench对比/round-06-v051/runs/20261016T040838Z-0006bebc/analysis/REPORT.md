# CubeSandbox 启动分析报告

并发 100；正式计划请求 100；正式进程内置预热 0。 独立预热计划 3 次，成功 3 次，状态 complete。 数据范围受限（limited）：客户端计时可用，组件阶段仅覆盖有可靠实例 ID 的样本；缺失归属时无法生成按实例的阶段统计。

## 整轮耗时

| 口径 | 耗时 | 数据来源 | 覆盖范围 |
| --- | --- | --- | --- |
| 正式测试整轮耗时 | 484.97863 ms | raw.summary.total_time_s | Runner's measured formal workload, excluding warmup under the cube-bench contract. Includes scheduling and result collection; create-delete mode also includes deletion. Generic producers must use this same scope. |
| 外部命令窗口 | 19904.884033 ms | manifest.command.started_at/ended_at | Collector's external-command wall-clock window; may include warmup, setup, cleanup and console draining. Not the formal benchmark duration. |
| 采集窗口 | 20951.198975 ms | manifest.started_at/ended_at | Collector's entire wall-clock capture window, including surrounding log/metrics collection. Not the formal benchmark duration. |
| 独立预热命令耗时 | 200.63322 ms | prewarmup.duration_ms | 正式采集之前的独立进程；不计入正式测试整轮耗时 |

整轮耗时是正式测试从开始到结束的经过时间，不是单次延迟的总和或最大值。外部命令可能包含预热、初始化、清理；采集窗口还可能包含 metrics 和日志收尾。整轮计时缺失时不使用后两者代替。

## 单次启动时延

| 指标 | 值 |
| --- | --- |
| 有效样本数 | 100 |
| 平均值 (ms) | 349.45703 |
| P50 (ms) | 349.455 |
| P95 (ms) | 480.958 |
| 最大值 (ms) | 484.192 |

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
| formal | 100 | 22 | 正式集合；归属证据及限制见下文 |
| warmup | 0 | 0 | 预热集合 |
| unknown_phase | 0 | 0 | 实例已归属本轮，但正式/预热阶段未确认；保留观测，不用于正式分布 |

共展示 22 个分组阶段的观测统计；unknown_phase 中有观测的阶段同样展示，不会因为分组未知而隐藏。未观测阶段与全部覆盖缺口见阶段 CSV 和 analysis.json。

| 分组 | 阶段 | 实例覆盖 | 样本数 | 平均 ms | P50 ms | P95 ms | 最大 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| formal | Cubelet.cgroup | 93/100 | 93 | 74.928753 | 82.306 | 120.768 | 180.793 |
| formal | Cubelet.create-sandbox-metadata | 72/100 | 72 | 19.207653 | 15.582 | 40.58 | 60.447 |
| formal | Cubelet.cube-sandbox-store | 16/100 | 16 | 7.632125 | 7.738 | 8.106 | 8.106 |
| formal | Cubelet.cubebox | 100/100 | 100 | 212.90945 | 222.429 | 276.826 | 288.315 |
| formal | Cubelet.cubebox-service | 100/100 | 100 | 300.31254 | 311.589 | 400.24 | 404.328 |
| formal | Cubelet.cubebox-service-inner | 100/100 | 100 | 266.12092 | 259.351 | 382.19 | 388.628 |
| formal | Cubelet.gen-spec-sandbox | 45/100 | 45 | 11.358533 | 9.105 | 22.638 | 32.255 |
| formal | Cubelet.network | 73/100 | 73 | 15.834219 | 14.426 | 31.133 | 86.337 |
| formal | Cubelet.sandbox-create | 100/100 | 100 | 147.00722 | 156.739 | 187.338 | 228.873 |
| formal | Cubelet.sandbox-probe | 100/100 | 100 | 34.12216 | 33.193 | 64.14 | 69.786 |
| formal | Cubelet.sandbox-start | 100/100 | 100 | 157.24709 | 163.599 | 219.425 | 245.346 |
| formal | Cubelet.storage | 86/100 | 86 | 16.756093 | 17.128 | 26.619 | 27.502 |
| formal | Cubelet.workflow | 1/100 | 1 | 5.537 | 5.537 | 5.537 | 5.537 |
| formal | Shim.CreateContainer | 100/100 | 100 | 17.82 | 14 | 31 | 65 |
| formal | Shim.CreatePodSandbox | 100/100 | 100 | 59.52 | 57 | 83 | 95 |
| formal | Shim.CreateSandbox | 100/100 | 100 | 2.1 | 1 | 7 | 24 |
| formal | Shim.LaunchVmm | 100/100 | 100 | 1.22 | 1 | 2 | 2 |
| formal | Shim.ResetVm | 100/100 | 100 | 12.47 | 11 | 23 | 33 |
| formal | Shim.RestoreVm | 100/100 | 100 | 15.41 | 14 | 27 | 40 |
| formal | Master response.cube-e2e | 100/100 | 100 | 304.98 | 316 | 407 | 409 |
| formal | Master response.sandbox-probe | 100/100 | 100 | 33.64 | 33 | 64 | 69 |
| formal | Master response.all-probe | 100/100 | 100 | 33.64 | 33 | 64 | 69 |

查看 [阶段 CSV](stage-latency.csv)、[完整分析 JSON](analysis.json) 和 [runner 原始结果与校验记录](benchmark-inputs/)。

## 数据文件

- [完整汇总 JSON](run-summary.json)
- [完整分析 JSON](analysis.json)
- [阶段 CSV](stage-latency.csv)
- [实例时间轴](timeline.html)
- [客户端样本（脱敏副本）](benchmark-inputs/)
- [发布文件校验清单](../../../..//publication-manifest.json)
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
- 这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。
- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- Whole-run duration measures concurrent workload completion, not a sum or maximum of individual request latencies.
- Timing fields and generic clock declarations are producer-supplied evidence; they do not independently certify workload execution or success.
- Request counts describe supplied raw rows; missing raw input remains unknown even when a summary reports totals.
- create_latency_ms is the existing profile.benchmark.create distribution of valid successful samples, not whole-run timing.
