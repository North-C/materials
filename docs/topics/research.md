# Research

状态：`indexed`。本页只整理已提交基线和主检出区只读状态；不覆盖两处 modified Dockerfile，不吸收或重打包未跟踪成果。

## 快速入口

| 读者目标 | 当前入口 | 内容角色 |
|---|---|---|
| 理解 Agent benchmark CPU 研究脉络 | [research README](../../research/README.md) | durable knowledge index |
| 判断 canonical/历史/证据边界 | [Research 内容收敛图](../../research/CONTENT_CONVERGENCE.md) | convergence map |
| 查看主检出区 dirty 输入保护清单 | [Dirty Input Manifest](../../research/DIRTY_INPUT_MANIFEST.md) | protection manifest |
| 查看 benchmark toolkit | [agent_cpu_sandbox_toolkit README](../../research/agent_cpu_sandbox_toolkit/README.md) | project-local source/how-to |
| 查看 v0 冻结说明 | [versions/v0 README](../../research/versions/v0/README.md) | historical/version reference |
| 查看 AI 趋势研究 | [agent_ai_trend](../../research/agent_ai_trend/) | research reports/notes |

## 内容分类

### Durable research conclusions

- AlphaEval、Agent benchmark catalog、CPU workload 筛选与测试条件。
- 长任务候选、Terminal-Bench/Kata 执行流和 SWE-bench 迁移方法。
- 每份结论应标明论文/数据集版本、检索时间与 last verified。

### Toolkit source

- runner、workload、summary 工具、Dockerfile、测试和执行脚本。
- README 负责输入输出、支持平台、依赖、版本和复现入口。

### Task fixtures

- 每个 Terminal-Bench task 的 Dockerfile、compose、tests、solution 和 self-contained 依赖。
- task 内重复 `mini_pytest.py` 可能是离线自包含边界，不能仅凭 hash 合并。

### Evidence and derived results

- trajectory JSONL、benchmark result、profile、日志与版本快照。
- summary/report 属于 derived evidence，必须能追到 raw input 和生成脚本。

### Vendor inputs and versions

- 第三方源码归档记录上游 URL、版本、许可证和 hash。
- `versions/v0` 应说明冻结范围与 source revision；大型版本 tar 不直接进入普通 Git。

## 当前 dirty 边界

2026-08-27 只读复核仍为：

- modified：`Dockerfile.e2b`、`Dockerfile.e2b-perf`；
- research 下存在大量未跟踪 task、tool、trajectory、vendor archive 和版本 tar；
- 当前 Workspace 不读取 diff、不覆盖、不暂存、不提交这些路径。

## 当前 Workspace（MAT-03 phase 1）

已新增 research 收敛图和 dirty input manifest，先保护主检出区成果并明确 clean checkout 缺口。仍未复制、移动或提交主检出区 dirty/untracked 文件。

## 下一阶段（MAT-03 phase 2）

1. 以主检出区 dirty 状态为输入建立保护清单。
2. 区分研究结论、toolkit source、task fixture、raw/derived evidence、vendor input。
3. 为 `versions/v0` 建立 provenance 和生成说明，大型 tar 使用 MAT-01 的存储决策。
4. 确认两处 modified Dockerfile 的 canonical 与合并方式。
5. 更新 research README；网页 Wiki 已推迟，未来另行决定全文 allowlist。

相关主题：[大文件与生成物](large-files.md) · [迁移计划](../meta/MIGRATION_PLAN.md)
