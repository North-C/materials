---
status: in-progress
scope: Agent benchmark、CPU/sandbox workload 研究、无模型任务工具链与版本/证据导航
last_verified: 2026-08-27
source_revision: f036fd2 (navigation baseline only)
canonical: true
evidence_manifest: incomplete
---

# Research：Agent Benchmark 与 CPU/Sandbox 负载

本目录保存围绕 AlphaEval、Agent benchmark、Terminal-Bench/SWE-bench 筛选、无模型 workload 和沙箱执行的研究材料。当前 README 是 research 项目入口；导航已核对，但各实验结论仍以文内时间、环境和 source revision 为准。

## Scope

包含：

- 论文/benchmark 版图与 CPU 负载筛选结论；
- 面向 runc、Kata、Cloud Hypervisor、E2B 等沙箱的测试条件和 PoC；
- Agent CPU Sandbox Toolkit、Terminal-Bench task fixture 和汇总工具；
- 研究过程、版本快照、trajectory、raw/derived result 与第三方输入。

不包含：

- 大模型服务质量或模型能力本身的全面评测；
- 未入库主检出区成果的正文复制；
- 大型版本 tar、profile 或第三方归档的直接提交决策。

## 快速导航

| 目标 | 推荐入口 | 内容角色 |
|---|---|---|
| 理解 AlphaEval 的核心观点 | [AlphaEval 核心总结](alphaeval_core_summary.md) | durable research summary |
| 查看 Agent benchmark 版图 | [Agent benchmark catalog](agent_benchmark_catalog.md) | reference/explanation |
| 选择 CPU 侧 benchmark | [CPU Agent benchmark 筛选报告](cpu_agent_benchmark_report.md) | explanation/decision input |
| 降低大模型侧变量 | [CPU-focused benchmark filter](cpu_focused_benchmark_filter.md) | reference/selection rule |
| 设计沙箱测试条件 | [Sandbox benchmark test conditions](sandbox_benchmark_test_conditions.md) | reference |
| 查看无模型 Terminal-Bench PoC | [Real Terminal-Bench no-LLM PoC](real_terminal_bench_no_llm_poc.md) | experiment report |
| 查看工具链 | [Agent CPU Sandbox Toolkit](agent_cpu_sandbox_toolkit/README.md) | project-local source/how-to |
| 查看 v0 冻结说明 | [Toolkit v0](versions/v0/README.md) | historical/version reference |
| 判断 canonical 与 dirty 输入边界 | [Research 内容收敛图](CONTENT_CONVERGENCE.md), [Dirty Input Manifest](DIRTY_INPUT_MANIFEST.md) | governance/protection |

## Durable research conclusions

### 基础与筛选

- [AlphaEval 核心总结](alphaeval_core_summary.md)：论文核心观点与生产型 Agent 评估背景。
- [Agent benchmark catalog](agent_benchmark_catalog.md)：论文涉及的 benchmark 分类和用途。
- [CPU Agent benchmark 筛选报告](cpu_agent_benchmark_report.md)：面向 CPU 负载与性能优化的候选集。
- [CPU-focused benchmark filter](cpu_focused_benchmark_filter.md)：降低模型侧影响后的保留/降级/剔除规则。
- [Sandbox benchmark test conditions](sandbox_benchmark_test_conditions.md)：Kata/E2B/Firecracker/Docker 的测试条件与执行模式。

### Terminal-Bench 路线

- [ARM sandbox Terminal-Bench PoC](arm_sandbox_terminal_bench_poc.md)：ARM 服务器上的无模型 workload 试跑。
- [Real Terminal-Bench no-LLM PoC](real_terminal_bench_no_llm_poc.md)：Replay Trajectory / Fixed Output 方法。
- [Terminal-Bench task filter v0](terminal_bench_task_filter_v0.md)：初始任务筛选和分层。
- [Long-task candidates](terminal_bench_long_task_candidates.md)：十秒/分钟级 CPU 负载候选。
- [Long-task addition](terminal_bench_long_task_addition.md)：长任务加入 toolkit 的变更与验证记录。
- [Kata Terminal-Bench run flow](kata_terminal_bench_run_flow.md)：Kata 中的 rootfs、runner、ctr 和输出结构。

### SWE-bench 路线

- [SWE-bench task filter v0](swe_bench_task_filter_v0.md)：无模型请求测试用例候选。
- [SWE CPU benchmark tool design](swe_cpu_benchmark_tool_design.md)：fixed patch/replay runner 的需求和构建流程。

### Agent/AI 趋势研究

- [Agentic AI CPU 服务器研究报告](agent_ai_trend/OpenAI_Anthropic_Agentic_AI_CPU_服务器研究报告.md)
- [Agentic AI 业务布局与演进报告](agent_ai_trend/OpenAI_Anthropic_Agentic_AI_业务布局与演进报告.md)

趋势报告应记录检索日期和来源；不能因为位于 `research/` 就默认当前有效。

## Toolkit、task 与证据

| 分层 | 当前路径 | 规则 |
|---|---|---|
| toolkit source/how-to | `agent_cpu_sandbox_toolkit/README.md`、`tools/` | README 必须与干净 checkout 实际可用文件一致 |
| workload/task fixture | `agent_cpu_sandbox_toolkit/terminal-bench-tasks/` | 自包含 task 内的重复依赖不自动抽取 |
| toolkit reference | `LONG_TASKS.md`、`E2B_RUNTIME_TASKS.md` | 记录支持矩阵、输入输出和运行前提 |
| raw evidence | trajectory、run logs、profile、task input | 分类前不删除；敏感/大型对象不进入内容目录正文 |
| derived evidence | summary、CSV、报告 | 必须能追到 raw input 和生成工具 |
| version snapshot | `versions/v0/README.md` | 标记 historical、冻结范围和 source revision |
| vendor input | task 内第三方源码/归档 | 记录 URL、版本、许可证和 hash |

## 当前 Git 边界

2026-08-27 只读复核主检出区：HEAD `f036fd2`，2 个 modified、70 个 untracked 文件级条目、0 staged；本地 `main` 相对已知 `origin/main` 落后 3 个提交。两处 modified 均位于 `large-scale-text-editing` 的 Dockerfile。

当前干净基线 `f036fd2` 中，toolkit README 引用的以下核心路径尚未被跟踪，但主检出区存在对应未跟踪成果：

- `tools/run_workload.py`
- `scripts/terminal_cpu_io.sh`
- `tools/summarize.py`
- `trajectories/terminal_cpu_io.jsonl`
- `tools/run_terminal_bench_task.py`
- `tools/summarize_terminal_bench.py`

因此，当前 README 中的 toolkit 命令不能视为“从干净 clone 可复现”。MAT-03 必须先保护并审阅主检出区成果，再决定纳入方式；本 Workspace 不读取 diff、不复制、不暂存这些文件。

## 推荐阅读路线

### 研究 benchmark 版图

1. [AlphaEval 核心总结](alphaeval_core_summary.md)
2. [Agent benchmark catalog](agent_benchmark_catalog.md)
3. [CPU Agent benchmark 筛选报告](cpu_agent_benchmark_report.md)
4. [CPU-focused benchmark filter](cpu_focused_benchmark_filter.md)

### 设计 AI sandbox CPU 测试

1. [Sandbox benchmark test conditions](sandbox_benchmark_test_conditions.md)
2. [ARM sandbox PoC](arm_sandbox_terminal_bench_poc.md)
3. [Real Terminal-Bench no-LLM PoC](real_terminal_bench_no_llm_poc.md)
4. [Toolkit README](agent_cpu_sandbox_toolkit/README.md)

### 扩展任务和版本

1. [Terminal-Bench task filter v0](terminal_bench_task_filter_v0.md)
2. [Long-task candidates](terminal_bench_long_task_candidates.md)
3. [Long-task addition](terminal_bench_long_task_addition.md)
4. [Toolkit v0](versions/v0/README.md)

## Canonical 与状态

- 本 README 是 research 导航 canonical；`last_verified` 只表示路径和 Git 边界核对。
- 每份研究报告的技术结论以文内来源、数据集版本和日期为准。
- `versions/v0` 是 historical snapshot，不是 `latest`。
- 主检出区未跟踪 task/tool/trajectory 在审阅前是成果候选，不是已纳入仓库的 canonical。
- 同一 task 的自包含依赖和全局工具可能有意重复；只有确认职责相同后才能收敛。

## 后续整理

MAT-03 已完成第一阶段保护性整理，新增 [Research 内容收敛图](CONTENT_CONVERGENCE.md) 与 [Dirty Input Manifest](DIRTY_INPUT_MANIFEST.md)。后续建议按以下顺序推进：

1. 保存主检出区 dirty/untracked 输入清单和 hash；
2. 对齐 toolkit README 与实际可纳入的 source/tool/task；
3. 为 `versions/v0` 补 source revision、生成命令、hash 和存储决策；
4. 为 trajectory/raw result/derived summary 建 evidence manifest；
5. 为趋势报告补检索时间、来源和 current/historical 状态。

相关入口：[仓库根 README](../README.md) · [Research 跨项目目录](../docs/topics/research.md) · [迁移计划](../docs/meta/MIGRATION_PLAN.md)
