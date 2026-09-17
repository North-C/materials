# reports (perf)

带日期的模板与性能报告集：版本对比、规格矩阵、优化迭代、压测复验。与同目录层级的脚本、指南和 manifest 分离：

- 指标语义与脚本：[../CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md](../CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md)、[../scripts_v2/](../scripts_v2/)
- 指南类：[../CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md](../CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md)、[../TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md](../TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md)
- 溯源与缺口：[../MANIFEST.md](../MANIFEST.md)

## 内容概览

- v0.3.0 / v0.5.x / v16 / community 对比与 cmdline 对齐复测
- vCPU 数量-模板矩阵
- C50 优化、core perf v3、400QPS 优化
- openEuler kernel/template perf 系列（1U2G/2U2G/3U4U/full kernel/new kernel）
- 历史镜像创建压测与严格 TAP 隔离复验
- readiness 阶段初步定位、cubeshim 迁移指南、irqbypass xarray 优化指南、并发启动优化笔记

报告为 historical evidence：引用结论前先对照 [MANIFEST.md](../MANIFEST.md) 确认 workload、revision 与 raw evidence 状态。

## Provenance

本目录 18 份文档原位于 `ai_sandbox/cubesandbox/` 顶层，2026-09-17 迁入（MAT-02 批次 C2）；纯 Git rename，内容零改动，仓库内入链已全部重写。
