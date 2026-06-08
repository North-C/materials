# Agent Benchmark CPU 负载研究资料

本目录保存围绕 AlphaEval 论文和 Agent benchmark 的整理材料。

## 文档列表

- `alphaeval_core_summary.md`：AlphaEval 论文核心总结。
- `agent_benchmark_catalog.md`：论文中提到的 Agent / AI benchmark 分类摘录与用途解读。
- `cpu_agent_benchmark_report.md`：面向 CPU 负载与性能优化的 Agent benchmark 筛选报告。
- `cpu_focused_benchmark_filter.md`：在降低大模型侧影响的前提下，对 benchmark 做保留、降级和剔除筛选。
- `sandbox_benchmark_test_conditions.md`：面向 Kata/E2B/Firecracker/Docker 沙箱，收敛 benchmark 测试条件、执行模式和环境要求。
- `arm_sandbox_terminal_bench_poc.md`：在 ARM 服务器上用 runc/Kata/cloud-hypervisor smoke 构建无大模型 Terminal-bench 风格 workload 的 PoC 记录。
- `real_terminal_bench_no_llm_poc.md`：引入真实 Terminal-Bench 任务包，在 runc/Kata 中用 Replay Trajectory / Fixed Output 无模型运行的 PoC。
- `terminal_bench_task_filter_v0.md`：基于当前 Terminal-Bench 任务全集的 v0 筛选结果、任务分层和选择依据。
- `terminal_bench_long_task_candidates.md`：在 v0-ready 任务偏短的前提下，筛选适合构成长时 CPU 负载的 Terminal-Bench 任务、执行模式和扩展条件。
- `terminal_bench_long_task_addition.md`：四组长负载任务加入 toolkit 后的变更、远端 rootfs 环境和验证结果。
- `kata_terminal_bench_run_flow.md`：Kata 中运行 Terminal-Bench 任务的端到端流程说明，包括 rootfs、runner、ctr 启动、执行模式和输出结构。
- `swe_bench_task_filter_v0.md`：面向无模型请求测试用例构建的 SWE-bench v0 筛选结果、任务分层和选择依据。
- `swe_cpu_benchmark_tool_design.md`：把 SWE-bench 任务负载转成 CPU 性能基准工具的需求、输入输出、负载分层和构建流程。
- `versions/v0/README.md`：当前进展的初始 v0 版本说明，含工具链快照路径。

## 推荐阅读顺序

1. 先读 `alphaeval_core_summary.md`，理解 AlphaEval 为什么强调生产型 Agent 评估。
2. 再读 `agent_benchmark_catalog.md`，了解论文涉及的 benchmark 版图。
3. 最后读 `cpu_agent_benchmark_report.md`，用于后续设计 CPU 侧评估负载矩阵。
4. 如果测试目标是隔离 CPU 负载，读 `cpu_focused_benchmark_filter.md`，按其中的主评估集和可选扩展集执行。
5. 如果需要在 AI 沙箱中实际落地测试，读 `sandbox_benchmark_test_conditions.md`，按 V1/V2/V3 测试集推进。
6. 如果需要查看真实 ARM 服务器试跑结果，读 `arm_sandbox_terminal_bench_poc.md`。
7. 如果需要真实 Terminal-Bench 任务的无模型落地方式，读 `real_terminal_bench_no_llm_poc.md`。
8. 如果需要查看 v0 任务筛选和版本冻结结果，读 `terminal_bench_task_filter_v0.md` 与 `versions/v0/README.md`。
9. 如果需要把测试时长扩展到十秒/分钟级，读 `terminal_bench_long_task_candidates.md`。
10. 如果需要直接运行已加入的长任务，读 `terminal_bench_long_task_addition.md`。
11. 如果需要向他人介绍 Kata 运行 Terminal-Bench 的流程，读 `kata_terminal_bench_run_flow.md`。
12. 如果需要把同样的方法迁移到 SWE-bench，先读 `swe_bench_task_filter_v0.md`，再读 `swe_cpu_benchmark_tool_design.md` 确定 fixed patch / replay runner 的需求和构建流程。
