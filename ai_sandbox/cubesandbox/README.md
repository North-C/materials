---
status: in-progress
scope: CubeSandbox 架构、生命周期、ARM64 适配、性能、问题修复、操作材料与证据导航
last_verified: 2026-08-27
source_revision: f036fd2 (navigation baseline only; technical revisions are per document)
canonical: true
evidence_manifest: mixed; see evidence section
---

# CubeSandbox 材料导航

本目录保存 CubeSandbox 的源码解读、实验结论、性能方法、操作指南、公开文章、脚本和证据。当前 README 是项目级导航入口，不替代各文档中的版本、环境和证据说明。

导航链接已在 `f036fd2` 基线核对；技术结论没有在 2026-08-27 统一重跑。带日期的报告通常表示一次历史实验，不自动代表当前版本或 canonical 结论。

## Scope

包含：

- Template、Snapshot、Rollback、Clone、Pause/Resume 等生命周期机制；
- CubeMaster、Cubelet、CubeShim、VMM、KVM/vGIC/timer 等执行链；
- ARM64 适配、guest image、kernel、benchmark 与性能分析；
- 问题根因、修复补丁、验证脚本和原始/派生证据；
- 面向社区的文章和用户指南。

不包含：

- CubeSandbox 源码本体；源码 revision 由具体文档记录；
- 未入库的远端 `remote-results/` 或其他工作区源码；
- 大型镜像、完整原始日志和未审计敏感数据。

## 按目标进入

| 目标 | 推荐入口 | 状态说明 |
|---|---|---|
| 理解 Snapshot 是什么 | [Snapshot 深入分析](snapshot-deep-dive.md) | explanation candidate；需按文内源码语境使用 |
| 理解 create/rollback/clone/resume 差异 | [Runtime Snapshot 运行机制](snapshot-runtime-deep-dive.md) | explanation candidate；与上篇配套 |
| 查看生命周期数据流和当前源码锚点 | [测试用例与数据流分析](testcases_analysis/README.md) | 明确记录源码 commit 的项目内分析入口 |
| 审阅 canonical/supersede/evidence 关系 | [CubeSandbox 内容收敛图](CONTENT_CONVERGENCE.md) | MAT-02 收敛索引；不移动原文 |
| 查看外部证据/source 可达性 | [Evidence availability](EVIDENCE_AVAILABILITY.md) | 本地 Verification archive 映射；不可直接发布 |
| 构建和运行 benchmark | [Benchmark README](benchmark/README.md) | benchmark 子域入口；不保存大型镜像 tar |
| 审阅 benchmark 报告/CSV lineage | [Benchmark reports manifest](benchmark/reports/README.md) | derived evidence manifest；仍缺 raw input 映射 |
| 理解 profiling 指标来源 | [指标与社区源码对照](perf/CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md) | reference；基于社区 `v0.5.1` 指定 commit |
| 审阅 profiling lineage 与脚本重复 | [Perf manifest](perf/MANIFEST.md) | profiling manifest；脚本 canonical 待确认 |
| 采集社区版创建链路 profiling | [社区版 Profiling 指南](perf/CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md) | how-to；适用 `v0.5.0` 指定 commit |
| 查看 AP1R/NMI 根因与修复 | [根因与修复报告](bug-fixes/CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md) | conclusion candidate；与证据包配套 |
| 审阅 AP1R 修复验证证据 | [2026-08-06 证据包](debug/arm64-vgic-ap1r-nmi-active-20260806/README.md) / [manifest](debug/arm64-vgic-ap1r-nmi-active-20260806/MANIFEST.md) | evidence 入口；含 SHA256SUMS、环境、结果和补丁 |
| 阅读面向社区的 irqbypass 总结 | [ARM64 irqbypass 工程故事](articles/cubesandbox-arm64-irqbypass-engineering-story.md) | publication；不替代原始分析和 evidence |

## 内容分区

### 架构与生命周期

- [Snapshot 深入分析](snapshot-deep-dive.md)：Snapshot 组成、存储与上层能力。
- [Runtime Snapshot 运行机制](snapshot-runtime-deep-dive.md)：create、rollback、clone、resume 的边界。
- [Template 与 Snapshot 内容分析](CUBESANDBOX_TEMPLATE_AND_SNAPSHOT_CONTENT_ANALYSIS.md)：内容构成专题。
- [测试用例与数据流分析](testcases_analysis/README.md)：benchmark 矩阵、数据流、时序和源码证据。

该组目前有多个互补入口，不强行指定一个文档覆盖全部生命周期语义。后续 MAT-02 应明确“概念入口”“当前实现参考”“历史实验报告”的关系。

### Benchmark 与性能

- [Benchmark 子目录](benchmark/README.md)：镜像构建、runner、参数、报告和 checksum。
- [Perf 子目录](perf/)：社区 profiling、指标来源、创建链路和并发/NUMA 分析。
- [创建链路分段时延分析](perf/CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md)：历史 profiling 结果。
- [Template 并发创建优化指南](perf/TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md)：操作与优化边界。

性能文档必须保留 workload、版本、资源、readiness、成功/失败样本口径和原始数据关系。日期较新的报告不自动取代基线或方法文档。

### ARM64 适配、镜像与 Kernel

- [ARM64 适配问题汇总（中文）](arm64-adaptation-issues-summary-zh.md)
- [ARM64 adaptation issues summary（English）](arm64-adaptation-issues-summary.md)
- [openEuler guest image 构建指南](CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md)
- [Guest image 替换](CUBESANDBOX_GUEST_IMAGE_REPLACEMENT.md)
- [Guest image、OCI 与 vmlinux 关系](CUBESANDBOX_GUEST_IMAGE_OCI_VMLINUX_RELATIONSHIP.md)

中英文适配汇总是 2026-05-06 的语言变体和历史快照，不代表当前 ARM64 支持状态；后续需确认主版本、同步方式和 historical 标记。

### 问题、修复与验证

- `bug-fixes/`：根因结论、分析链、关键数据和修复脚本。
- `debug/`：可审阅问题包、环境、逐请求结果、关键日志、补丁和校验和。
- 顶层 `CUBESANDBOX_ARM64_*` 日期报告：多 vCPU restore、timer、RCU stall、WFI/vGIC 等历史分析链。

AP1R 主题当前推荐把“根因与修复报告”作为结论候选，把 `debug/.../README.md` 作为证据入口；是否 supersede 更早的 timer/WFI 文档仍需逐篇审阅，不能批量删除。

### 操作、构建与用户指南

- [Benchmark 使用与构建](benchmark/README.md)
- [openEuler guest image 构建](CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md)
- [openEuler vmlinux/BM 构建](CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md)
- [CubeShim 优化迁移指南](CUBESHIM_OPTIMIZED_MIGRATION_GUIDE_20260729.md)
- [irqbypass XArray 优化用户指南](kvm-irqbypass-xarray-optimize-user-guide.md)

执行前必须核对文档标明的 release、commit、架构和环境。历史 IP、Template ID、镜像 tag 和路径不能当作当前值复用。

### 公开文章

- [CubeSandbox ARM64 irqbypass 工程故事](articles/cubesandbox-arm64-irqbypass-engineering-story.md)
- [文章资产](articles/assets/)：与文章配套的 SVG。

公开文章可以为可读性重述必要背景，但不应成为原始数据或源码 revision 的唯一记录。

## Canonical 候选与关系

| Scope | 当前入口 | 当前判断 |
|---|---|---|
| CubeSandbox 目录导航 | 本 README | canonical 入口 |
| 内容收敛关系 | `CONTENT_CONVERGENCE.md` | MAT-02 canonical/supersede/evidence map |
| 外部证据可达性 | `EVIDENCE_AVAILABILITY.md` | `remote-results/`、`source_code/`、绝对 Verification 路径的本地可达性索引 |
| benchmark 工作流 | `benchmark/README.md` | 子域 canonical 入口 |
| 生命周期测试用例与源码证据 | `testcases_analysis/README.md` | 子域入口；适用其记录的源码 commit |
| Snapshot 概念与 Runtime Snapshot | 两份 `snapshot-*-deep-dive.md` | 互补 explanation candidates，尚未合并 |
| profiling 指标语义 | `perf/CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md` | `v0.5.1` reference candidate |
| AP1R 根因结论 | `bug-fixes/...ROOTCAUSE_AND_FIX_20260731.md` | conclusion candidate |
| AP1R 验证证据 | `debug/.../README.md` | evidence entry |
| irqbypass 公开叙事 | `articles/...engineering-story.md` | publication canonical；非 evidence canonical |
| ARM64 适配汇总 | 中英文两份 summary | historical language pair；主版本待确认 |

“candidate”表示导航层已找到最可能入口，不表示已经完成逐段比对、当前环境复测或用户最终确认。

## Evidence 与 provenance

成熟例子：

- [AP1R debug bundle](debug/arm64-vgic-ap1r-nmi-active-20260806/README.md) 含环境、结果、关键日志、补丁、脚本和 `SHA256SUMS`。
- `benchmark/checksums/` 只保留大型镜像导出的 checksum，不提交镜像 tar。
- [Benchmark reports manifest](benchmark/reports/README.md)、[Perf manifest](perf/MANIFEST.md) 与 [AP1R debug manifest](debug/arm64-vgic-ap1r-nmi-active-20260806/MANIFEST.md) 已建立第一版 lineage 入口。
- [Evidence availability](EVIDENCE_AVAILABILITY.md) 已确认抽取出的 327 个 Verification 路径在本地归档中全部存在；这些仍是非便携 provenance，不应直接作为公开 Wiki 链接。

待治理：

- `benchmark/reports/` 混合解释报告与派生 CSV；目录级 manifest 已建立，但 raw input 与 generator 映射仍不完整。
- 部分顶层报告引用未入库 `remote-results/`、`source_code/` 或绝对本地路径。
- 虽然本地 Verification archive 可解析这些路径，但仓库内和未来网页端仍不可直接依赖绝对路径；需要按主题转换为 manifest。
- `perf/` 与 `perf/scripts_v2/` 存在完全相同脚本，需先检查调用者和历史用途。

## 状态规则

- 本 README 的 `last_verified` 只表示导航链接和目录关系核对日期。
- 文档技术状态以文内 release/commit、实验日期和 evidence 为准。
- 未标状态的日期报告默认作为 `historical candidate` 审阅，不能仅按日期判定最新结论。
- 未完成逐篇审阅前，不删除 superseded 候选，也不改写历史报告。

## 后续整理

MAT-02 建议按主题小批推进：

1. Snapshot/lifecycle canonical 关系；
2. AP1R 与更早 WFI/timer 分析的 supersede 映射；
3. benchmark reports 的 evidence manifest；
4. perf 脚本重复与版本关系；
5. ARM64 中英文汇总的主版本和 historical 状态。

相关入口：[仓库根 README](../../README.md) · [CubeSandbox 跨项目目录](../../docs/topics/cubesandbox.md) · [迁移计划](../../docs/meta/MIGRATION_PLAN.md)
