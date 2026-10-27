# CubeSandbox 资料分类与导航

[返回 Materials](../../README.md) · [返回 AI Sandbox](../README.md)

本页统一索引 CubeSandbox 的架构、适配、测试、调优与故障资料。根目录文档按主题列在后半部分，既有专题目录和仓库顶层实验包保留原路径。

新增或修订材料前先读 [仓库规范](../../AGENTS.md) 和 [CubeSandbox 专项规则](AGENTS.md)，按材料类型选择目录并同步维护对应索引。

## 按任务查找

| 任务 | 首选入口 | 阅读范围 |
| --- | --- | --- |
| 了解架构与版本变化 | [架构图](architecture/cubesandbox-minimal-v2.png)、[v0.5.1 → v0.7.1 演进](version-evolution/cubesandbox-v0.5.1-to-v0.7.1-evolution.zh-CN.md) | 架构概览与指定版本间的变化 |
| 核对对比测试版本与补丁 | [二进制与内核清单](comparison-inventory-20261027/README.md) | 2026-10-27 公开报告：源码/组件SHA、生效条件、内核补丁和性能边界；原始证据未公开 |
| 分析创建时延 | [perf 索引](perf/README.md) | 各轮报告、阶段定义、计时口径、时间轴与工具状态 |
| 比较机器配置 | [machine_config 快照与对比指南](machine_config/README.md) | 2026-10-20 `.90` 全模块 JSON / Markdown；已只读采集并校验，可离线对比 |
| 复现 c100n100 优化 | [调优指南](c100n100-perf-tuning/README.zh-CN.md)、[测试指南](c100n100-perf-tuning/TESTING-GUIDE.zh-CN.md) | 配置、补丁、验证与回退方法；环境前提以正文为准 |
| 选择 workload / 构建 benchmark 镜像 | [benchmark 索引](benchmark/README.md) | 镜像来源、上游 workload、runner、参数与报告 |
| 测试回放密度 | [SWE 回放入口](benchmark/swe-replay-density/README.md)、[密度指南](benchmark/swe-replay-density/docs/CUBESANDBOX_DENSITY_GUIDE.md) | 镜像、模板、回放方法及独立运行证据 |
| 分析内存占用 | [内存测量指南](benchmark/analysis/cubesandbox-memory-density-measurement-guide.md)、[CoW 记账模型](benchmark/analysis/cubesandbox-cow-memory-accounting-model.md) | 内存测量口径、分析报告与勘误 |
| 理解快照与生命周期 | [Snapshot](snapshot-deep-dive.md)、[Runtime Snapshot](snapshot-runtime-deep-dive.md)、[模板与快照内容](CUBESANDBOX_TEMPLATE_AND_SNAPSHOT_CONTENT_ANALYSIS.md) | 概念、运行机制与数据内容 |
| 排查 ARM64 恢复故障 | [适配问题汇总](arm64-adaptation-issues-summary-zh.md)、[2026-08-06 调试包](debug/arm64-vgic-ap1r-nmi-active-20260806/README.md) | 历史调查、复现、修复与证据边界 |
| 构建 guest / 内核 | [openEuler Guest 构建](CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md)、[SP1 irqbypass 补丁指南](openeuler-24.03-sp1-irqbypass-xarray-v2-build-guide.md) | 镜像、内核与补丁的具体构建流程 |
| 理解测试用例 | [testcases_analysis](testcases_analysis/README.md) | 测试矩阵、数据流、时序和源码证据 |

## 专题目录的边界

| 目录 | 归类 | 放置内容 |
| --- | --- | --- |
| [architecture/](architecture/) | 架构图 | 图稿与生成说明 |
| [version-evolution/](version-evolution/) | 版本研究 | 指定版本之间的演进分析 |
| [benchmark/](benchmark/README.md) | 基准与功能测试 | `docker/` 构建上下文、`scripts/` runner、`docs/` 方法、`reports/` 报告、`analysis/` 内存专题、`swe-replay-density/` 回放专项 |
| [perf/](perf/README.md) | 启动性能分析 | 阶段耗时、计时边界、观测脚本和逐轮报告；通用工具的后续维护地址见该索引 |
| [c100n100-perf-tuning/](c100n100-perf-tuning/README.zh-CN.md) | 调优复现 | 指南、补丁、配置样例、辅助脚本与状态快照 |
| [comparison-inventory-20261027/](comparison-inventory-20261027/README.md) | 对比测试身份清单 | 二进制与内核两份报告、补丁生效与性能对应、来源缺口和发布校验；不重复发布原始实验包 |
| [machine_config/](machine_config/README.md) | 机器配置基线 | 带采集时间的单机 JSON、可读表格、校验值与离线对比方法；不重复存放性能测试证据 |
| [bug-fixes/](bug-fixes/) | 根因与修复归档 | 修复报告、分析及对应关键数据 |
| [debug/](debug/) | 调查过程与复现包 | 按问题和日期组织的现场、实验及修复验证材料 |
| [testcases_analysis/](testcases_analysis/README.md) | 测试源码解读 | 用例行为、时序、存储及源码证据 |
| [articles/](articles/) | 工程文章 | 从专项工作整理的叙事文章；查数值与结论仍回到对应报告 |

`benchmark` 侧重“测什么、怎么测和测试结果”，`perf` 侧重“耗时在哪里、怎样观测”，`c100n100-perf-tuning` 侧重“怎样配置、修改和复测”。同一实验可以跨目录引用，不复制证据包。

## 仓库顶层的相关实验包

| 入口 | 主题 | 配套材料 |
| --- | --- | --- |
| [cube-bench 对比](../../cube-bench对比/README.md) | 2026-10-16 v0.7.1 / v0.5.1 对比 | 汇总报告、逐轮数据、版本证据与发布清单 |
| [Go / NUMA 实验](../../cube-bench-go-numa-20261016/README.md) | 2026-10-16 Go 参数与 NUMA 三状态实验 | 配置快照、生效矩阵、逐轮结果和配置/恢复脚本 |
| [机器配置](../../machine-configs/) | 实验环境快照 | 按机器和日期保存的 Markdown / CSV 报告 |

这些目录属于本专题的外部入口，原有数据包路径与内部相对引用保持不变。

## 根目录文档分类

下面索引本目录根部既有的专题文档（不含导航与 Agent 规则）。保留原题名与历史日期；按主题归类不代表重新验证正文结论。尤其是多轮故障调查，应结合后续复盘和修复报告阅读。

### 架构、快照与生命周期机制

- [CubeSandbox Pause / Resume / Restore 阶段细化与低扰动插桩设计](CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md)
- [CubeSandbox ARM64 Pause / Snapshot / Resume / Restore 关联链路分析](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ANALYSIS_20260721.md)
- [CubeSandbox ARM64 Template 静止窗口与 KVM 机制分析](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_20260720.md)
- [Arm GIC 基础概念与 CubeSandbox 中 CPU1 第一个 Tick 的全链路分析](CUBESANDBOX_ARM_GIC_BASICS_AND_CPU1_TICK_CHAIN_20260721.md)
- [CubeSandbox 模板与快照内容分析](CUBESANDBOX_TEMPLATE_AND_SNAPSHOT_CONTENT_ANALYSIS.md)
- [CubeSandbox Snapshot 深入分析](snapshot-deep-dive.md)
- [CubeSandbox Runtime Snapshot 运行机制深入分析](snapshot-runtime-deep-dive.md)

### ARM64 适配与早期版本对比

- [CubeSandbox ARM64 v0.3.0 适配版与 v0.5.0 问题侧 Template 测试对比](CUBESANDBOX_ARM64_V030_V050_TEMPLATE_COMPARISON_REPORT_20260721.md)
- [CubeSandbox ARM64 v0.3 与 v0.5 Template 链路源码差异分析](CUBESANDBOX_ARM64_V030_V050_TEMPLATE_SOURCE_DIFF_ANALYSIS_20260722.md)
- [CubeSandbox ARM64 v0.3 / v0.5.1 内核参数对齐复测报告](CUBESANDBOX_ARM64_V030_V051_CMDLINE_ALIGNMENT_RERUN_REPORT_20260723.md)
- [CubeSandbox v16 与社区 v0.5.1 修改差异分析](CUBESANDBOX_V16_VS_COMMUNITY_V051_CHANGE_ANALYSIS_20260722.md)
- [CubeSandbox ARM64 适配问题汇总](arm64-adaptation-issues-summary-zh.md)
- [CubeSandbox ARM64 Adaptation Issues Summary](arm64-adaptation-issues-summary.md)

### 多 vCPU 恢复故障、实验与追踪

- [Cloud Hypervisor ARM64 原生 Snapshot/Restore 对照实验报告](CLOUD_HYPERVISOR_ARM64_NATIVE_SNAPSHOT_RESTORE_CONTROL_20260722.md)
- [CubeSandbox ARM64 2-vCPU restore 失败根因链与 tracepoint 证据对照](CUBESANDBOX_ARM64_2VCPU_WFI_TIMER_DELIVERY_ROOTCAUSE_20260724.md)
- [CubeSandbox ARM64 CPU1 restore 后首次 KVM 运行边界重新分析与 trace 方案](CUBESANDBOX_ARM64_CPU1_FIRST_KVM_ENTRY_TRACE_REASSESSMENT_20260722.md)
- [CubeSandbox ARM64 首次 KVM entry trace 设计、操作与实测说明](CUBESANDBOX_ARM64_FIRST_ENTRY_TRACE_GUIDE_20260723.md)
- [CubeSandbox ARM64 多 vCPU 恢复故障 — KVM 内核层根因闭环报告](CUBESANDBOX_ARM64_KVM_VTIMER_ACTIVE_ROOT_CAUSE_20260722.md)
- [CubeSandbox ARM64 多 vCPU Template 恢复故障完整实验分析报告](CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md)
- [CubeSandbox ARM64 多 vCPU Template 故障交接与后续执行计划](CUBESANDBOX_ARM64_MULTIVCPU_HANDOFF_PLAN_20260724.md)
- [CubeSandbox ARM64 多 vCPU Template 恢复故障问题说明](CUBESANDBOX_ARM64_MULTIVCPU_RESTORE_ISSUE_BRIEF_20260721.md)
- [CubeSandbox ARM64 多 vCPU Template 恢复故障综合复盘与根因再判断](CUBESANDBOX_ARM64_MULTIVCPU_ROOT_CAUSE_REASSESSMENT_20260722.md)
- [CubeSandbox ARM64 多 vCPU Template 恢复故障分析](CUBESANDBOX_ARM64_MULTIVCPU_SNAPSHOT_RESTORE_ANALYSIS_20260717.md)
- [CubeSandbox ARM64 RCU Stall 与 Stack Dump 日志说明](CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md)
- [CubeSandbox ARM64 v26 trace-stripped 实验：判定 v23 20/20 是否来自插桩副作用](CUBESANDBOX_ARM64_V26_TRACE_STRIPPED_EXPERIMENT_20260724.md)
- [CubeSandbox ARM64 2/3/4 vCPU 新模板对照报告](CUBESANDBOX_ARM64_VCPU_COUNT_TEMPLATE_MATRIX_REPORT_20260723.md)
- [CubeSandbox ARM64 多 vCPU 恢复故障 — Cloud Hypervisor 社区先例检索报告](CUBESANDBOX_CH_COMMUNITY_PRECEDENT_SURVEY_20260721.md)
- [Issue #6966（get_device_attr UB）与 CubeSandbox 的对照分析](CUBESANDBOX_CH_ISSUE6966_UB_COMPARISON_20260721.md)

### Guest 镜像与内核构建

- [CubeSandbox Guest image、OCI 镜像与 vmlinux 的关系](CUBESANDBOX_GUEST_IMAGE_OCI_VMLINUX_RELATIONSHIP.md)
- [CubeSandbox guest 镜像替换手册](CUBESANDBOX_GUEST_IMAGE_REPLACEMENT.md)
- [CubeSandbox ARM64 openEuler Guest image 构建指南](CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md)
- [CubeSandbox openEuler ARM64 `vmlinux-bm` 构建手册](CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md)

### 内核优化与 Shim 迁移

- [CubeShim 优化版本迁移文档](CUBESHIM_OPTIMIZED_MIGRATION_GUIDE_20260729.md)
- [KVM irqbypass XArray 锁竞争优化 用户指南](kvm-irqbypass-xarray-optimize-user-guide.md)
- [openEuler 24.03 LTS-SP1 合并 irqbypass XArray 补丁指南](openeuler-24.03-sp1-irqbypass-xarray-v2-build-guide.md)

### 创建性能、压力测试与就绪分析

- [CubeSandbox 2U2G Template c50n500 优化报告](CUBESANDBOX_C50_OPTIMIZATION_REPORT_20260727.md)
- [CubeSandbox 社区 guest image 切换、回退与 2U2G 复测](CUBESANDBOX_COMMUNITY_GUEST_IMAGE_ROLLBACK_RETEST_20260727.md)
- [CubeSandbox ARM64 v3 OCI 核心性能测试报告](CUBESANDBOX_CORE_PERF_V3_REPORT_20260728.md)
- [CubeSandbox 完整 openEuler Guest Kernel Template 并发性能复测](CUBESANDBOX_FULL_OPENEULER_KERNEL_TEMPLATE_PERF_20260727.md)
- [CubeSandbox guest 镜像 A/B 测试报告](CUBESANDBOX_GUEST_IMAGE_AB_20260725.md)
- [CubeSandbox 历史镜像创建压力测试报告](CUBESANDBOX_HISTORICAL_IMAGE_PRESSURE_20260727.md)
- [CubeSandbox 历史镜像严格 TAP 隔离压力复验](CUBESANDBOX_HISTORICAL_IMAGE_PRESSURE_ISOLATED_TAPS_20260727.md)
- [PASS WITH CAVEATS：MMDS-prime 2U2G + opt235 三轮 c50n500 稳定性报告](CUBESANDBOX_MMDS_PRIME_2U2G_OPT235_C50N500_3ROUNDS_20260821.md)
- [CubeSandbox openEuler Guest 新内核 Template 核心性能测试](CUBESANDBOX_OPENEULER_NEW_KERNEL_TEMPLATE_PERF_20260727.md)
- [CubeSandbox openEuler 1U2G Template 并发性能复测](CUBESANDBOX_OPENEULER_TEMPLATE_PERF_1U2G_20260727.md)
- [CubeSandbox openEuler 2U2G Template 并发性能基线](CUBESANDBOX_OPENEULER_TEMPLATE_PERF_2U2G_BASELINE_20260727.md)
- [CubeSandbox openEuler 3U2G / 4U2G Template 并发性能测试](CUBESANDBOX_OPENEULER_TEMPLATE_PERF_3U4U_20260727.md)
- [CubeSandbox Template 并发创建就绪阶段初步原因分析](CUBESANDBOX_READINESS_INITIAL_ROOT_CAUSE_ANALYSIS_20260728.md)
- [CubeSandbox Template c50n500 吞吐优化报告](CUBESANDBOX_TEMPLATE_400QPS_OPTIMIZATION_20260729.md)
- [并发启动优化](并发启动优化.md)

### 生命周期与综合测试报告

- [CubeSandbox v0.5.0 ARM64 正式测试报告](CUBESANDBOX_FORMAL_TEST_REPORT_ARM64_20260716.md)
- [CubeSandbox Benchmark 前置健康检查报告](CUBESANDBOX_PRE_BENCHMARK_HEALTH_20260718.md)
- [CubeSandbox Runtime Snapshot / Pause / Resume / Clone 基线报告](CUBESANDBOX_SNAPSHOT_PAUSE_RESUME_CLONE_COMMUNITY_BASELINE_20260824.md)
- [CubeSandbox ARM64 性能测试报告](kunpeng-arm64-benchmark-report-zh.md)

## 证据与维护约定

- 先读报告中的版本、机器、工具、负载、预热、计时范围和样本数，再比较数据。create-only、生命周期测试、guest 执行与密度测试分别判断。
- 区分原始记录、派生统计、报告和发布副本；以各数据包的 evidence manifest、publication manifest 或校验文件为准。
- `debug` 中的调查假设、历史根因判断及尚待执行的计划，按各自记录时点理解；不能仅凭标题认定当前版本仍有同一问题。
- 后续新增资料优先进入上面的专题目录，使用主题或日期明确的文件名，并更新对应索引；历史根目录文件保留可追溯路径。
- 本地 `questions/`、`perf/temp.md`、适配草稿及缓存等未跟踪资料，待内容确认后再归档；本索引不把它们列为已发布报告。
