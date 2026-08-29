# CubeSandbox

状态：`indexed`。本页建立主题地图，不修改现有技术结论，也不把日期最新的文件自动视为 canonical。

## 快速入口

| 读者目标 | 当前入口 | 内容角色 |
|---|---|---|
| 浏览项目总入口 | [CubeSandbox 材料导航](../../ai_sandbox/cubesandbox/README.md) | project canonical index |
| 审阅内容收敛关系 | [CubeSandbox 内容收敛图](../../ai_sandbox/cubesandbox/CONTENT_CONVERGENCE.md) | canonical/supersede/evidence map |
| 查看外部证据可达性 | [Evidence availability](../../ai_sandbox/cubesandbox/EVIDENCE_AVAILABILITY.md) | local verification archive map |
| 了解 benchmark 构建与测试 | [CubeSandbox benchmark README](../../ai_sandbox/cubesandbox/benchmark/README.md) | project-local how-to/reference |
| 理解 Template、Snapshot、Clone、Pause/Resume | [测试用例与数据流分析](../../ai_sandbox/cubesandbox/testcases_analysis/README.md) | explanation/reference |
| 阅读面向社区的 irqbypass 工程故事 | [ARM64 irqbypass engineering story](../../ai_sandbox/cubesandbox/articles/cubesandbox-arm64-irqbypass-engineering-story.md) | durable knowledge/publication |
| 查看 AP1R 调试证据包 | [AP1R debug bundle](../../ai_sandbox/cubesandbox/debug/arm64-vgic-ap1r-nmi-active-20260806/README.md) | evidence + fix + report |
| 查看 AP1R evidence manifest | [AP1R manifest](../../ai_sandbox/cubesandbox/debug/arm64-vgic-ap1r-nmi-active-20260806/MANIFEST.md) | evidence lineage |
| 复用性能采集方法 | [perf 目录](../../ai_sandbox/cubesandbox/perf/) | scripts/how-to/reports |
| 审阅 perf lineage | [Perf manifest](../../ai_sandbox/cubesandbox/perf/MANIFEST.md) | profiling lineage |
| 查 benchmark 报告与 CSV | [benchmark reports](../../ai_sandbox/cubesandbox/benchmark/reports/) | report + derived evidence |
| 审阅 benchmark reports lineage | [Benchmark reports manifest](../../ai_sandbox/cubesandbox/benchmark/reports/README.md) | derived evidence lineage |

## 内容分类

### 架构与生命周期

- Template/Snapshot 内容、数据流与生命周期分析。
- Pause/Resume/Restore 调用链与状态语义。
- Cloud Hypervisor、KVM、vGIC/timer 等底层机制。

### 性能与 benchmark

- benchmark 镜像、参数、SDK/envd runner 和报告。
- Template create、并发、NUMA、profiling 和 metric source mapping。
- raw/derived/report 必须分层；成功样本 latency 与整轮吞吐不能混用。

### 问题、修复与验证

- ARM64 multi-vCPU restore、AP1R/NMI、RCU stall、readiness 等问题链。
- `bug-fixes/` 与 `debug/` 中的 patch、验证脚本、环境和证据。
- instrumentation 成功不自动等于生产修复；最终结论需指向辨别性证据。

### 操作与构建

- guest image、openEuler kernel、Template、benchmark image 与部署指南。
- 操作指南必须标明版本、架构、前置条件和是否已验证。

### 公开文章

- 面向社区的文章是独立 publication，可以重述必要上下文，但技术结论应指向 canonical 分析和脱敏证据 manifest。

## 当前收敛结论

- AP1R/NMI restore failure 当前以 `bug-fixes/...ROOTCAUSE_AND_FIX_20260731.md` 作为结论候选，以 `debug/arm64-vgic-ap1r-nmi-active-20260806/README.md` 作为证据候选。
- `CUBESANDBOX_ARM64_2VCPU_WFI_TIMER_DELIVERY_ROOTCAUSE_20260724.md` 已被 2026-07-31 根因报告明示修正并终结，应作为 historical investigation chain 保留。
- `testcases_analysis/README.md` 是 Snapshot/lifecycle 当前实现和源码证据入口；两份 `snapshot-*-deep-dive.md` 继续作为 explanation candidates。
- benchmark/perf 已有第一版 report/profiling manifest，但 raw input、generator、host、template/image 和脚本调用方映射仍不完整，不能直接按日期报告选最终结论。
- 2026-08-29 对本地 `/home/lyq/Projects/Verification/cubesandbox` 做只读检查后，CubeSandbox 文档中抽取出的 327 个 `remote-results/`、`source_code/` 和绝对 Verification 路径全部可达；这解决的是本地 provenance 可达性，不解决公开网页便携性。
- `perf/` 与 `perf/scripts_v2/` 的脚本重复只形成收敛候选，尚不删除。

详细映射见 [CubeSandbox 内容收敛图](../../ai_sandbox/cubesandbox/CONTENT_CONVERGENCE.md)。

## 当前治理缺口

- 同一问题同时存在顶层日期报告、analysis、debug、perf、公开文章和中英文总结，尚未逐主题确认 canonical。
- 一部分报告引用仓库外 `remote-results/`、`source_code/` 或绝对本地路径，网页端无法独立解析。
- `perf/` 与 `perf/scripts_v2/` 至少有两组完全相同脚本，仍需检查调用者与历史意义。
- benchmark reports 混合解释文档和 CSV，缺目录级 manifest 说明原始输入与生成命令。

## 下一 Workspace（MAT-02）

1. 补齐 benchmark reports manifest 中的 raw input、generator、template/image、host 和 failure denominator。
2. 补齐 perf manifest 中的 raw profile/log、分析命令、host 和 workload。
3. 从 AP1R debug bundle 目录运行 checksum 验证，并对齐 component revisions。
4. 对重复脚本检查调用方和 README 引用，形成保留/收敛提案。
5. 网页 Wiki 已推迟；完成内容治理后再决定未来全文渲染 allowlist。

相关主题：[大文件与生成物](large-files.md) · [信息架构](../meta/INFORMATION_ARCHITECTURE.md)
