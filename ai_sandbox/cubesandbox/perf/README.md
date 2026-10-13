# CubeSandbox 性能分析报告与工具索引

本次 v0.7.1 Template c100n100 分析统一保存在 materials 主分支 **`main`**。查阅时从本页进入，无需在不同提交链接之间切换；后续本任务的报告直接更新主分支，不再新建分支。

## v0.7.1 · 90机器 · Template c100n100

测试模板基于 sandbox-code，规格为 **2 vCPU / 2048 MiB / 1G 可写层**。

| 文档 | 内容与状态 |
| --- | --- |
| [原版 c100n100 实测报告](reports/v071-c100n100-20261012/REPORT.md) | 正式100次成功；主阶段时延、同实例残差、局部时间轴、metrics与覆盖缺口 |
| [更细阶段时延分析报告](reports/v071-c100n100-fine-20261012/REPORT.md) | 旧日志网络微秒级补解析；Cubelet/Shim精细观测方案与构建验证。观测版重测仍待独占窗口，尚无该版本压测结果 |
| [旧 scripts_v2 准确性审计](scripts_v071/AUDIT_V2.md) | 检查日志、metrics、时钟、阶段边界与样本归属的可靠性 |
| [v0.7.1 源码阶段定义](scripts_v071/STAGES.md) | 源码计时点、阶段含义、包含关系及不能直接相加的边界 |
| [新版工具与复现步骤](scripts_v071/README.md) | 采集、正式/预热分类、网络细分、精细span解析、独立时钟时间轴 |

### 数据与时间轴

- 原版：[阶段CSV](reports/v071-c100n100-20261012/stage-latency.csv)、[分析JSON](reports/v071-c100n100-20261012/analysis.json)、[时间轴HTML](reports/v071-c100n100-20261012/timeline.html)。HTML下载后可离线打开。
- 网络细分：[CSV](reports/v071-c100n100-fine-20261012/network-details.csv)、[逐实例JSON](reports/v071-c100n100-fine-20261012/network-details.json)。部分样本统计需连同覆盖率读取。
- 观测版：[源码补丁](scripts_v071/observation.patch)、[验证摘要](reports/v071-c100n100-fine-20261012/validation.json)、[部署状态](reports/v071-c100n100-fine-20261012/deployment-status.json)。构建与单测通过不等于压测完成。

原始请求日志可能含凭据和环境，完整日志保留在报告所列采集目录；仓库提供派生结果和证据摘要。

## 早期工具与专题资料

- [scripts_v2 原工具目录](scripts_v2/)
- [阶段时延分析（2026-08-03）](CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md)
- [2u2g 核心性能分析（2026-08-03）](CUBESANDBOX_CORE_PERF_2U2G_20260803.md)
- [日志与metrics来源映射](CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md)
- [RunContainer与probe调用链](CUBESANDBOX_RUNCONTAINER_PROBE_CALL_CHAIN.md)
- [Template启动与NUMA balancing分析](CUBESANDBOX_TEMPLATE_STARTUP_NUMA_BALANCING_ANALYSIS.md)
- [Template并发创建优化指南](TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md)
- [社区性能分析指南](CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md)

历史资料的版本、环境和口径以各自文档为准，不与本轮v0.7.1结果混用。
