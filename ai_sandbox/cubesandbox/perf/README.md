# CubeSandbox 性能分析报告与工具索引

本目录在 materials 主分支 **`main`** 保留 v0.7.1 Template c100n100 的历史脚本、历次报告及证据归档，既有内容继续可查阅。

**后续通用工具维护迁至 [GitCode 私有仓库 cubesandbox-startup-profiler](https://gitcode.com/yuncongyue/cubesandbox-startup-profiler)**，访问需要相应成员权限。新仓库仅包含通用分析与参数化采集代码、阶段文档和合成样例，不携带本目录中的测试机信息、实测报告或运行证据。本目录脚本作为历史版本保留，不再同步工具功能更新。

## v0.7.1 · 90机器 · Template c100n100

测试模板基于 sandbox-code，规格为 **2 vCPU / 2048 MiB / 1G 可写层**。下表收录历次分析报告，另附阶段定义、审计和工具文档；各次模板、版本和预热方法以报告为准。

| 文档 | 内容与状态 |
| --- | --- |
| [agentwarn 模板 / 同进程 w3 最新复测（2026-10-17）](reports/v071-c100n100-agentwarn-w3-20261017/REPORT.md) | 1 pilot + 5 正式轮，中位数159.490 ms、500/500成功；完整脱敏数据包、6轮日志和清理证据，组件每轮103个含预热 |
| [原版 c100n100 实测报告](reports/v071-c100n100-20261012/REPORT.md) | 正式100次成功；主阶段时延、同实例残差、局部时间轴、metrics与覆盖缺口 |
| [更细阶段时延分析报告](reports/v071-c100n100-fine-20261012/REPORT.md) | 旧日志网络微秒级补解析；Cubelet/Shim精细观测方案与构建验证。观测版重测仍待独占窗口，尚无该版本压测结果 |
| [优化版＋NUMA0 实测与更细拆解报告（第三份，2026-10-14）](reports/v071-c100n100-optimized-20261014/REPORT.md) | 正式 API 100 次成功，均值260.965 ms、P95 360.840 ms；组件统计103个含预热，版本漂移的确认轮排除。不是perftrace观测版 |
| [旧 scripts_v2 准确性审计](scripts_v071/AUDIT_V2.md) | 检查日志、metrics、时钟、阶段边界与样本归属的可靠性 |
| [v0.7.1 源码阶段定义](scripts_v071/STAGES.md) | 整体阶段关系示意、同步/并行/异步与计时包含关系、源码计时点、阶段含义及不能直接相加的边界 |
| [新版工具与复现步骤](scripts_v071/README.md) | 采集、正式/预热分类、网络细分、精细span解析、独立时钟时间轴 |

最新报告入口：[agentwarn/w3 复测](reports/v071-c100n100-agentwarn-w3-20261017/REPORT.md) · [完整分析](reports/v071-c100n100-agentwarn-w3-20261017/RESULT_REPORT.md) · [完整脱敏数据包](reports/v071-c100n100-agentwarn-w3-20261017/result.tar.gz) · [发布说明](reports/v071-c100n100-agentwarn-w3-20261017/PUBLICATION.md)。

### 数据与时间轴

- 2026-10-17 agentwarn/w3：[逐轮CSV](reports/v071-c100n100-agentwarn-w3-20261017/round-summary.csv)、[阶段对比CSV](reports/v071-c100n100-agentwarn-w3-20261017/stage-comparison.csv)、[每轮报告与原始数据入口](reports/v071-c100n100-agentwarn-w3-20261017/RESULT_REPORT.md#证据完整性与交付)、[数据包SHA256](reports/v071-c100n100-agentwarn-w3-20261017/result.tar.gz.sha256)。

- 优化版：[对照CSV](reports/v071-c100n100-optimized-20261014/comparison.csv)、[组件阶段CSV](reports/v071-c100n100-optimized-20261014/capture/stage-latency.csv)、[时间轴HTML](reports/v071-c100n100-optimized-20261014/capture/timeline.html)。组件覆盖与阶段归属限制见报告。
- 原版：[阶段CSV](reports/v071-c100n100-20261012/stage-latency.csv)、[分析JSON](reports/v071-c100n100-20261012/analysis.json)、[时间轴HTML](reports/v071-c100n100-20261012/timeline.html)。HTML下载后可离线打开。
- 网络细分：[CSV](reports/v071-c100n100-fine-20261012/network-details.csv)、[逐实例JSON](reports/v071-c100n100-fine-20261012/network-details.json)。部分样本统计需连同覆盖率读取。
- 观测版：[源码补丁](scripts_v071/observation.patch)、[验证摘要](reports/v071-c100n100-fine-20261012/validation.json)、[部署状态](reports/v071-c100n100-fine-20261012/deployment-status.json)。构建与单测通过不等于压测完成。

早期报告主要提供派生结果和证据摘要，原始日志保留在其采集目录。2026-10-17 agentwarn/w3 按用户要求另发布完整数据包：保留全部记录，仅替换模板下载令牌，具体范围与原始/公开哈希边界见[发布说明](reports/v071-c100n100-agentwarn-w3-20261017/PUBLICATION.md)。

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
