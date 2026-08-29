---
status: in-progress
scope: research canonical, toolkit, task, evidence and version mapping
last_verified: 2026-08-29
source_revision: f036fd2 (navigation and file-relationship review only)
canonical: true
evidence_manifest: partial
---

# Research 内容收敛图

本文件整理 `research/` 下研究结论、toolkit、Terminal-Bench task、版本快照和证据的关系。它不复制主检出区未跟踪成果，不覆盖 modified Dockerfile，不运行 benchmark。

## 使用规则

- 先从 [README.md](README.md) 进入研究路线，再用本文件判断 canonical、historical、toolkit source、task fixture 和 evidence。
- `canonical` 表示当前推荐入口，不表示所有实验都已复测。
- 主检出区中的 dirty/untracked 文件先见 [DIRTY_INPUT_MANIFEST.md](DIRTY_INPUT_MANIFEST.md)，不要按 clean checkout 的文件状态判断成果是否丢失。
- 同一 task 内重复的 `mini_pytest.py`、Dockerfile、run-tests 等文件可能是自包含任务夹具，不按重复文件自动抽取。

## 主题级 Canonical Map

| Topic | Canonical entry | Supporting inputs | Current decision |
|---|---|---|---|
| Research navigation | [README.md](README.md) | this file, topic page | `README.md` remains the project entry |
| Benchmark landscape | [agent_benchmark_catalog.md](agent_benchmark_catalog.md), [alphaeval_core_summary.md](alphaeval_core_summary.md) | [cpu_agent_benchmark_report.md](cpu_agent_benchmark_report.md) | durable research summaries; need source/date metadata before verified |
| CPU-focused selection | [cpu_focused_benchmark_filter.md](cpu_focused_benchmark_filter.md) | [sandbox_benchmark_test_conditions.md](sandbox_benchmark_test_conditions.md) | selection/reference candidates |
| Terminal-Bench no-LLM route | [real_terminal_bench_no_llm_poc.md](real_terminal_bench_no_llm_poc.md), [terminal_bench_task_filter_v0.md](terminal_bench_task_filter_v0.md) | [arm_sandbox_terminal_bench_poc.md](arm_sandbox_terminal_bench_poc.md) | current research route for no-model workload |
| Long task route | [terminal_bench_long_task_candidates.md](terminal_bench_long_task_candidates.md), [terminal_bench_long_task_addition.md](terminal_bench_long_task_addition.md) | [kata_terminal_bench_run_flow.md](kata_terminal_bench_run_flow.md), toolkit tasks | keep as design/result chain; do not treat clean checkout as complete |
| SWE-bench route | [swe_bench_task_filter_v0.md](swe_bench_task_filter_v0.md), [swe_cpu_benchmark_tool_design.md](swe_cpu_benchmark_tool_design.md) | none in this phase | separate research line; not merged into Terminal-Bench toolkit |
| Agent trend reports | [agent_ai_trend/OpenAI_Anthropic_Agentic_AI_CPU_服务器研究报告.md](agent_ai_trend/OpenAI_Anthropic_Agentic_AI_CPU_服务器研究报告.md), [agent_ai_trend/OpenAI_Anthropic_Agentic_AI_业务布局与演进报告.md](agent_ai_trend/OpenAI_Anthropic_Agentic_AI_业务布局与演进报告.md) | untracked `agent_ai_trend/research-notes/` in main checkout | reports are durable candidates; notes need private/public review before import |
| Toolkit source/how-to | [agent_cpu_sandbox_toolkit/README.md](agent_cpu_sandbox_toolkit/README.md) | untracked `tools/`, `scripts/`, `trajectories/` in main checkout | README describes broader working state than clean checkout; source import still pending |
| Toolkit v0 snapshot | [versions/v0/README.md](versions/v0/README.md) | untracked `versions/v0/agent_cpu_sandbox_toolkit_v0.tar.gz` in main checkout | historical version reference; archive not imported in this Workspace |
| Dirty/untracked inputs | [DIRTY_INPUT_MANIFEST.md](DIRTY_INPUT_MANIFEST.md) | read-only main checkout | protection manifest; not an import list |

## Toolkit Boundary

`agent_cpu_sandbox_toolkit/` 同时包含研究解释、执行工具、task fixture、结果汇总和版本快照。当前按职责区分：

| Layer | Current paths | Governance rule |
|---|---|---|
| Project-local docs | `README.md`, `LONG_TASKS.md`, `E2B_RUNTIME_TASKS.md` | 可作为 toolkit 文档入口，但必须说明 clean checkout 与 dirty inputs 的差异 |
| Runner/tools | `tools/*.py`, `scripts/*.sh` | 先进入 source manifest；后续按功能测试决定是否纳入 Git |
| Task fixtures | `terminal-bench-tasks/*/{Dockerfile,docker-compose.yaml,task.yaml,run-tests.sh,tests/,solution.sh,self-contained/}` | 保持 task 自包含；重复文件先标记为 fixture duplication |
| Raw evidence | `trajectories/*.jsonl`, benchmark logs/profile/results | 不进正文；必须由 evidence manifest 引用 |
| Derived evidence | summaries, CSV/TSV, report markdown | 需要记录生成脚本、输入 hash 和参数 |
| Version snapshot | `versions/v0/` plus external tar | tar 不直接普通 Git；README/manifest 记录 hash、来源和存储决策 |
| Vendor input | task vendor tar and checksums | 用户已要求 vendor tar 不作处理；仅记录边界 |

## 重复与收敛规则

- `self-contained/mini_pytest.py` 在多个 task 中重复出现，当前判定为 task fixture self-contained boundary；不能作为清理对象。
- `tools/mini_pytest.py` 若后续纳入，应说明它与各 task 内 `self-contained/mini_pytest.py` 的关系：共享源、生成源或独立离线副本。
- Dockerfile 变体需按目标 runtime 区分：base/self-contained/E2B/E2B perf/Ubuntu 变体不能按文件名近似合并。
- `large-scale-text-editing` 的两处 modified tracked Dockerfile 必须先由用户确认是否代表最新 canonical；本 Workspace 不吸收 diff。

## 版本与证据决策

- `versions/v0/README.md` 是当前唯一已跟踪 v0 说明；未跟踪 `agent_cpu_sandbox_toolkit_v0.tar.gz` 暂不纳入。
- 版本 tar 需要 sidecar manifest：source revision、生成命令、生成环境、sha256、是否可重建、目标存储位置。
- trajectory/result/profile 属于 raw evidence；summary/report 属于 derived evidence。
- 趋势研究 notes 可能包含调研中间材料，导入前需要确认公开级别、引用来源和是否含账号/内部路径。

## 下一步

1. 用户审阅 [DIRTY_INPUT_MANIFEST.md](DIRTY_INPUT_MANIFEST.md) 后，决定哪些 untracked source/task 进入本仓库。
2. 对 `large-scale-text-editing` 两处 modified Dockerfile 做人工 diff 审阅，选定 canonical。
3. 为 `versions/v0` 增加 manifest，而不是直接提交大型 tar。
4. 为 toolkit raw/derived evidence 建最小 manifest；先记录，不移动原始数据。
5. 若进入提交阶段，按 [Commit and Push Plan](../docs/meta/COMMIT_PUSH_PLAN.md) 分 domain commit。
