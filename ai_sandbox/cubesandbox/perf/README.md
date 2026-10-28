# CubeSandbox 性能分析报告与工具索引

本目录在 materials 主分支 **`main`** 保留 v0.7.1 Template c100n100 的历史脚本、历次报告及证据归档，既有内容继续可查阅。

**后续通用工具维护迁至 [GitCode 私有仓库 cubesandbox-startup-profiler](https://gitcode.com/yuncongyue/cubesandbox-startup-profiler)**，访问需要相应成员权限。新仓库仅包含通用分析与参数化采集代码、阶段文档和合成样例，不携带本目录中的测试机信息、实测报告或运行证据。本目录脚本作为历史版本保留，不再同步工具功能更新。

## 对比测试身份与补丁清单

- [二进制 × 生效补丁 × 内核 × 性能，以及内核基线/附加补丁清单（2026-10-27）](../comparison-inventory-20261027/README.md)：独立专题保留两份公开报告、来源哈希与未公开证据说明。区分 original/kit/stack/hotset/自动学习 prewrite、旧K2与V2，不跨条件聚合；本次仅资料发布，没有新增测试。

## v0.7.1 · 90机器 · Template c100n100

测试模板基于 sandbox-code，规格为 **2 vCPU / 2048 MiB / 1G 可写层**。下表收录历次分析报告，另附阶段定义、审计和工具文档；各次模板、版本和预热方法以报告为准。

| 文档 | 内容与状态 |
| --- | --- |
| [独立 PR4＋guest warn／Cubelet 不绑 NUMA（2026-10-19）](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/REPORT.md) | 三正式轮中位189.823 ms、300/300成功；另抓取轮198.052 ms、100/100成功，report.html、脱敏日志、配置/folio探针及历史对比齐全 |
| [agentwarn 模板 / 同进程 w3 最新复测（2026-10-17）](reports/v071-c100n100-agentwarn-w3-20261017/REPORT.md) | 1 pilot + 5 正式轮，中位数159.490 ms、500/500成功；完整脱敏数据包、6轮日志和清理证据，组件每轮103个含预热 |
| [原版 c100n100 实测报告](reports/v071-c100n100-20261012/REPORT.md) | 正式100次成功；主阶段时延、同实例残差、局部时间轴、metrics与覆盖缺口 |
| [更细阶段时延分析报告](reports/v071-c100n100-fine-20261012/REPORT.md) | 旧日志网络微秒级补解析；Cubelet/Shim精细观测方案与构建验证。观测版重测仍待独占窗口，尚无该版本压测结果 |
| [优化版＋NUMA0 实测与更细拆解报告（第三份，2026-10-14）](reports/v071-c100n100-optimized-20261014/REPORT.md) | 正式 API 100 次成功，均值260.965 ms、P95 360.840 ms；组件统计103个含预热，版本漂移的确认轮排除。不是perftrace观测版 |
| [旧 scripts_v2 准确性审计](scripts_v071/AUDIT_V2.md) | 检查日志、metrics、时钟、阶段边界与样本归属的可靠性 |
| [v0.7.1 源码阶段定义](scripts_v071/STAGES.md) | 整体阶段关系示意、同步/并行/异步与计时包含关系、源码计时点、阶段含义及不能直接相加的边界 |
| [新版工具与复现步骤](scripts_v071/README.md) | 采集、正式/预热分类、网络细分、精细span解析、独立时钟时间轴 |

最新报告入口：[PR4/warn 复测与瓶颈分析](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/REPORT.md) · [report.html](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/results/bottleneck-c100/capture/inner-round/runs/20261019T041508Z-ca010a49/analysis/report.html) · [脱敏数据包](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/result.tar.gz) · [发布说明](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/PUBLICATION.md)。

2026-10-17 报告入口：[agentwarn/w3 复测](reports/v071-c100n100-agentwarn-w3-20261017/REPORT.md) · [完整分析](reports/v071-c100n100-agentwarn-w3-20261017/RESULT_REPORT.md) · [完整脱敏数据包](reports/v071-c100n100-agentwarn-w3-20261017/result.tar.gz) · [发布说明](reports/v071-c100n100-agentwarn-w3-20261017/PUBLICATION.md)。

### 数据与时间轴

- 2026-10-19 950（.90）与AMD 9654：[分级对比CSV](reports/c100n100-950-amd9654-stage-comparison-20261019/stage-latencies-950-vs-amd9654-review.csv)、[来源与口径说明](reports/c100n100-950-amd9654-stage-comparison-20261019/README.md)。按启动顺序和九级包含关系排列，五项指标相邻对照；AMD正式100、950组件含3次预热，不作为同条件硬件结论。

- 2026-10-19 独立 PR4/warn：[逐轮CSV](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/round-summary.csv)、[历史整轮对比](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/historical-comparison.csv)、[历史阶段对比](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/stage-comparison.csv)、[folio采样摘要](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/folio-sample-summary.csv)、[时间轴HTML](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/analysis/timeline.html)、[公开文件SHA256](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/SHA256SUMS)、[数据包SHA256](reports/v071-c100n100-pr4-agentwarn-unbound-20261019/result.tar.gz.sha256)。比较表注明各期模板、版本、CPU/NUMA和缓存差异，不能作为单因素补丁收益。

- 2026-10-17 agentwarn/w3：[逐轮CSV](reports/v071-c100n100-agentwarn-w3-20261017/round-summary.csv)、[阶段对比CSV](reports/v071-c100n100-agentwarn-w3-20261017/stage-comparison.csv)、[每轮报告与原始数据入口](reports/v071-c100n100-agentwarn-w3-20261017/RESULT_REPORT.md#证据完整性与交付)、[数据包SHA256](reports/v071-c100n100-agentwarn-w3-20261017/result.tar.gz.sha256)。

- 优化版：[对照CSV](reports/v071-c100n100-optimized-20261014/comparison.csv)、[组件阶段CSV](reports/v071-c100n100-optimized-20261014/capture/stage-latency.csv)、[时间轴HTML](reports/v071-c100n100-optimized-20261014/capture/timeline.html)。组件覆盖与阶段归属限制见报告。
- 原版：[阶段CSV](reports/v071-c100n100-20261012/stage-latency.csv)、[分析JSON](reports/v071-c100n100-20261012/analysis.json)、[时间轴HTML](reports/v071-c100n100-20261012/timeline.html)。HTML下载后可离线打开。
- 网络细分：[CSV](reports/v071-c100n100-fine-20261012/network-details.csv)、[逐实例JSON](reports/v071-c100n100-fine-20261012/network-details.json)。部分样本统计需连同覆盖率读取。
- 观测版：[源码补丁](scripts_v071/observation.patch)、[验证摘要](reports/v071-c100n100-fine-20261012/validation.json)、[部署状态](reports/v071-c100n100-fine-20261012/deployment-status.json)。构建与单测通过不等于压测完成。

早期报告主要提供派生结果和证据摘要，原始日志保留在其采集目录。2026-10-17 agentwarn/w3 按用户要求另发布完整数据包：保留全部记录，仅替换模板下载令牌，具体范围与原始/公开哈希边界见[发布说明](reports/v071-c100n100-agentwarn-w3-20261017/PUBLICATION.md)。

## v0.7.1 · AMD 9654 · Template c100n100

| 文档 | 内容与状态 |
| --- | --- |
| [profiler 五轮启动阶段剖析（2026-10-27）](reports/v071-c100n100-amd9654-profiler-20261027/REPORT.md) | 实测报告：v0.7.1-amd64 单节点，五轮各 100/100 成功、归属已采用、精确清理；r1–r4 客户端 avg 109.8–129.2 ms，进入 Master 前估算约 42 ms 为最大段，r5 RestoreVm 尖峰原因未查明；附同日 bash 基线五轮。只发布派生数据和 profiler 分析输出，原始日志未公开 |
| [社区 v0.7.1 vs BoostKit 2babb6f7 cube-perf-bench 全矩阵（2026-10-27/28）](reports/v071-amd9654-community-vs-boostkit-20261027/REPORT.md) | 实测报告，部分完成：nvme1 全新部署，BoostKit 33/33 项、社区 27/33 项，均为单次调用，只作描述；pause c1/c5/c10 低 56–70%，resume 无明确改善，dirty d100 及以上工作量无效。c100 五轮：BoostKit 119.8 ms（无外部 VM）、社区 125.2 ms（外部 VM 在场），条件不同，**未判定**。附逐项原始输出与脚本，地址、主机名、路径已替换 |
| [模板对照、profiler 瓶颈与 cube-perf-bench 全项（2026-10-28）](reports/v071-amd9654-template-compare-suite-20261028/REPORT.md) | 实测 + 诊断，完成：同一套 BoostKit 2babb6f7 组件下，另一用户的模板 c100n100 中位约 932 ms，重建原模板 127.4 ms（各五轮，区间不重叠）；profiler 定位为恢复后约 750 ms 的 guest 侧停顿（ResetVm / CreateContainer 双峰），缺就绪探针只是推测。重建原模板 snapshot c10 中位 93.6 ms、c50n500 中位 657.7 ms；[全项统一报告](reports/v071-amd9654-template-compare-suite-20261028/SUITE-REPORT.md) 中其余项为单次调用，只作描述；vmm.log 核对显示本次 pause 全部走 PR #32 dirty-log 路径；resume c10 约 0.9 s 来自就绪探针 500 ms 周期的长尾，常态约 400 ms 主要是 resume 重建 VM 后 guest 变慢且随并发线性增长（诊断，原因待验证）。共享主机，无同条件对照组，不判定优化效果 |

## 早期工具与专题资料

- [scripts_v2 原工具目录](scripts_v2/)
- [阶段时延分析（2026-08-03）](CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md)
- [2u2g 核心性能分析（2026-08-03）](CUBESANDBOX_CORE_PERF_2U2G_20260803.md)
- [日志与metrics来源映射](CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md)
- [RunContainer与probe调用链](CUBESANDBOX_RUNCONTAINER_PROBE_CALL_CHAIN.md)
- [Template启动与NUMA balancing分析](CUBESANDBOX_TEMPLATE_STARTUP_NUMA_BALANCING_ANALYSIS.md)
- [Template并发创建优化指南](TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md)
- [社区性能分析指南](CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md)
- [cube-bench 计时分析：TUI 计时偏差、-no-tui 时间轴与 v0.5.1→v0.7.1 版本核对（2026-10-16）](CUBESANDBOX_CUBE_BENCH_TIMING_ANALYSIS_20261016.md)

历史资料的版本、环境和口径以各自文档为准，不与本轮v0.7.1结果混用。
