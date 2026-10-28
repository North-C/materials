# CubeSandbox 启动分析报告

并发 100；正式计划请求 100；正式进程内置预热 3。 数据范围受限（limited）：客户端计时可用，组件阶段仅覆盖有可靠实例 ID 的样本；缺失归属时无法生成按实例的阶段统计。

## 整轮耗时

| 口径 | 耗时 | 数据来源 | 覆盖范围 |
| --- | --- | --- | --- |
| 正式测试整轮耗时 | 936.160973 ms | raw.summary.total_time_s | Runner's measured formal workload, excluding warmup under the cube-bench contract. Includes scheduling and result collection; create-delete mode also includes deletion. Generic producers must use this same scope. |
| 外部命令窗口 | 3481.729004 ms | manifest.command.started_at/ended_at | Collector's external-command wall-clock window; may include warmup, setup, cleanup and console draining. Not the formal benchmark duration. |
| 采集窗口 | 4515.334961 ms | manifest.started_at/ended_at | Collector's entire wall-clock capture window, including surrounding log/metrics collection. Not the formal benchmark duration. |

整轮耗时是正式测试从开始到结束的经过时间，不是单次延迟的总和或最大值。外部命令可能包含预热、初始化、清理；采集窗口还可能包含 metrics 和日志收尾。整轮计时缺失时不使用后两者代替。

## 单次启动时延

| 指标 | 值 |
| --- | --- |
| 有效样本数 | 100 |
| 平均值 (ms) | 700.29148 |
| P50 (ms) | 836.251 |
| P95 (ms) | 913.7 |
| 最大值 (ms) | 932.289 |

| 请求统计 | 值 |
| --- | --- |
| observed | 100 |
| successful | 100 |
| errors | 0 |
| valid_latency | 100 |

## warmup 与样本口径

warmup 是正式测量前的预热操作，用于让连接、缓存和资源池预先被使用。官方 cube-bench 串行执行预热，然后开始正式测试；create-only 每次创建，create-delete 每次还包含删除；预热不进入其正式 raw 样本和 summary.total_time_s。自定义 runner 必须明确自己的计时和样本范围。预热不保证消除所有冷启动开销。



组件分组状态：unverified。unknown_phase 可能混有预热；declared 仅表示用户声明。阶段样本集合与客户端样本集合不一定相同，父子与并行阶段不能相加。 实例 ID 来源包含 cubemastercli 前后清单：候选 103 个，在用户声明模板独占的前提下推定本轮归属；仅有清单证据的实例归入 unknown_phase（可能为预热与正式混合）。此方式不提供客户端 seq 到实例的映射，CLI 的节点遍历计数不证明每个节点查询成功。

## 已观测阶段

| 分组 | 归属实例数 | 有观测的阶段数 | 统计口径 |
| --- | --- | --- | --- |
| formal | 0 | 0 | 正式集合；归属证据及限制见下文 |
| warmup | 0 | 0 | 预热集合 |
| unknown_phase | 103 | 24 | 实例已归属本轮，但正式/预热阶段未确认；保留观测，不用于正式分布 |

共展示 24 个分组阶段的观测统计；unknown_phase 中有观测的阶段同样展示，不会因为分组未知而隐藏。未观测阶段与全部覆盖缺口见阶段 CSV 和 analysis.json。

| 分组 | 阶段 | 实例覆盖 | 样本数 | 平均 ms | P50 ms | P95 ms | 最大 ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| unknown_phase | Cubelet.cgroup | 4/103 | 4 | 5.4975 | 5.507 | 5.648 | 5.648 |
| unknown_phase | Cubelet.cube-sandbox-store | 3/103 | 3 | 7.144 | 6.53 | 9.232 | 9.232 |
| unknown_phase | Cubelet.cubebox | 103/103 | 103 | 623.733204 | 784.362 | 788.235 | 792.183 |
| unknown_phase | Cubelet.cubebox-service | 103/103 | 103 | 659.315078 | 808.964 | 848.168 | 863.984 |
| unknown_phase | Cubelet.cubebox-service-inner | 103/103 | 103 | 659.242291 | 808.893 | 848.101 | 863.894 |
| unknown_phase | Cubelet.sandbox-create | 103/103 | 103 | 621.248068 | 781.973 | 785.322 | 790.356 |
| unknown_phase | Cubelet.sandbox-start | 103/103 | 103 | 622.383592 | 782.944 | 786.315 | 791.071 |
| unknown_phase | Cubelet.storage | 92/103 | 92 | 37.272272 | 35.053 | 64.258 | 70.554 |
| unknown_phase | Cubelet.workflow | 1/103 | 5 | 5.348 | 5.269 | 5.66 | 5.66 |
| unknown_phase | Shim.CreateContainer | 103/103 | 103 | 174.951456 | 4 | 751 | 752 |
| unknown_phase | Shim.CreatePodSandbox | 103/103 | 103 | 614.68932 | 776 | 778 | 784 |
| unknown_phase | Shim.CreateSandbox | 103/103 | 103 | 0.737864 | 1 | 1 | 2 |
| unknown_phase | Shim.LaunchVmm | 103/103 | 103 | 0.640777 | 1 | 1 | 1 |
| unknown_phase | Shim.ResetVm | 103/103 | 103 | 427.699029 | 761 | 763 | 763 |
| unknown_phase | Shim.RestoreVm | 103/103 | 103 | 7.893204 | 8 | 9 | 10 |
| unknown_phase | Master response.cube-e2e | 103/103 | 103 | 663.019417 | 812 | 853 | 868 |
| unknown_phase | Master response.sandbox-probe | 103/103 | 103 | 0 | 0 | 0 | 0 |
| unknown_phase | Master response.all-probe | 103/103 | 103 | 0 | 0 | 0 | 0 |
| unknown_phase | Master stat.bufferhandle | 103/103 | 103 | 1.028291 | 0.833 | 2.983 | 4.642 |
| unknown_phase | Master stat.cube-e2e | 103/103 | 103 | 663.474 | 812.492 | 853.143 | 868.397 |
| unknown_phase | Master stat.cubemaster-inner | 103/103 | 103 | 3.524689 | 3.227 | 5.91 | 7.424 |
| unknown_phase | Master stat.cubemaster-inner-handle | 103/103 | 103 | 2.202573 | 2.029 | 3.226 | 5.949 |
| unknown_phase | Master stat.cubemaster-post-redis | 103/103 | 103 | 0.28601 | 0.229 | 0.568 | 0.961 |
| unknown_phase | Master stat.cubemaster-post-spec | 103/103 | 103 | 2.170786 | 2.005 | 3.191 | 5.709 |

查看 [阶段 CSV](stage-latency.csv)、[完整分析 JSON](analysis.json) 和 [runner 原始结果与校验记录](benchmark-inputs/)。

## 数据文件

- [完整汇总 JSON](run-summary.json)
- [完整分析 JSON](analysis.json)
- [阶段 CSV](stage-latency.csv)
- [实例时间轴](timeline.html)
- [客户端原始输入（未脱敏）](benchmark-inputs/)
- [输入校验清单](analysis-manifest.json)
- [CLI 实例清单与归属证据（未脱敏）](inventory-evidence/)

benchmark-inputs 保留已提供的客户端结果文件原始字节；没有输入时目录为空。原始输入及报告可能包含敏感信息，分享前需检查。

## 数据限制

- Command/capture timestamps use collector wall time and can be affected by clock adjustments; they are not monotonic runner timing.
- CLI inventory: operator_asserted_template_exclusivity
- CLI inventory: healthy_nodes_inventory_only
- CLI inventory: node_query_failures_may_be_omitted_despite_complete_reported_scan
- CLI inventory: ownership_inferred_not_independently_verified
- CLI inventory: client_samples_not_mapped_to_instances
- CLI inventory: warmup_and_formal_not_separated
- warmup_raw_absent: warmup outcomes and instance IDs are unavailable
- cubemastercli_instance_ids_collected: 103 run IDs available under declared template exclusivity; inventory-only IDs remain unknown_phase (warmup + formal), without raw seq mapping
- client_sample_id_mapping_unavailable: CLI inventory does not map client seq to server IDs
- 实例阶段归属或预热证据不完整；保留客户端计时。CLI 识别的混合集合在 unknown_phase 展示，不能当作正式 100 个实例的分布。
- Formal sandbox IDs are unavailable: component stages cannot be claimed as the formal benchmark population.
- Formal ownership covers 0/100 requested instances; compare coverage with actual benchmark successes.
- unknown_phase is reported separately and may include warmup; it is not a formal-only distribution.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase membership is unverified. Component results remain unknown_phase and are NOT a valid formal-only benchmark distribution.
- Whole-run duration measures concurrent workload completion, not a sum or maximum of individual request latencies.
- Timing fields and generic clock declarations are producer-supplied evidence; they do not independently certify workload execution or success.
- Request counts describe supplied raw rows; missing raw input remains unknown even when a summary reports totals.
- create_latency_ms is the existing profile.benchmark.create distribution of valid successful samples, not whole-run timing.
