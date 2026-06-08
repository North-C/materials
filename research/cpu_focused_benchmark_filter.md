# 面向 CPU 负载评估的 Benchmark 过滤建议

## 过滤目标

本轮筛选目标是评估 CPU 的负载特征和性能表现，同时尽量降低大模型侧的影响。

因此 benchmark 选择应优先满足：

1. 本地执行占比高：测试、编译、数据处理、浏览器/GUI、容器、评测脚本能产生明确 CPU 负载。
2. 评分尽量确定性：优先使用单元测试、规则校验、数值校验、状态校验，减少 LLM-as-a-Judge。
3. 可做 replay 或固定轨迹：允许使用固定 agent 输出、固定 patch、固定命令序列，单独测 harness/evaluator/环境负载。
4. 外部依赖少：减少实时网页搜索、人工主观判断、云端模型调用延迟对结果的干扰。

## 保留优先级

| 等级 | Benchmark | 保留理由 | 使用建议 |
|---|---|---|---|
| 强保留 | Terminal-bench | 终端任务、本地命令、文件系统、容器/沙箱负载明显 | 优先用于 CPU/IO/进程调度测试 |
| 强保留 | SWE-bench | repo checkout、依赖安装、测试执行、patch 验证负载明确 | 建议使用固定 patch 或固定 agent 输出做 replay |
| 强保留 | MLE-bench | 数据读取、特征工程、训练/评测脚本负载高 | 选择 CPU-only 配置，限制 GPU |
| 强保留 | DSBench | 数据分析、Python 执行、表格处理明显 | 适合 pandas/numpy/脚本负载分析 |
| 条件保留 | AlphaEval 子集 | 部分任务有规则评分、文件处理、UI 测试和数值验证 | 只选低 LLM Judge 依赖的领域和任务 |
| 条件保留 | OSWorld | GUI、截图、浏览器/桌面自动化本地负载高 | 建议固定动作轨迹或使用脚本 agent |
| 条件保留 | WebArena | 浏览器渲染、DOM、服务端环境有本地负载 | 建议固定动作轨迹，避免实时模型决策影响 |
| 条件保留 | AppWorld | 可控 app 环境和状态验证 | 适合测环境与 evaluator，不适合纯模型能力评估混入 |
| 条件保留 | OfficeQA / OdysseyBench | Office/办公流任务有 GUI 和文件处理负载 | 需要控制模型调用和外部服务 |

## AlphaEval 的内部过滤建议

AlphaEval 不建议整体直接用于 CPU 负载测试，因为它包含较多 LLM-as-a-Judge、实时研究、主观判断任务。但可以做子集筛选。

| AlphaEval 领域 | 建议 | 原因 |
|---|---|---|
| Procurement & Operations | 保留 | Excel/CSV、约束验证、成本优化、规则评分，本地计算和 evaluator 明确 |
| Software Engineering | 保留 | 代码生成结果可通过自动 UI/E2E 测试验证，本地测试负载明显 |
| Healthcare & Life Sciences | 部分保留 | 数值验证、日期计算、规则校验可用；涉及 LLM Judge 的政策分析任务需剔除 |
| Finance & Investment | 部分保留 | 结构化财务数据抽取可保留；投资报告、pitch critique 等 LLM Judge 任务剔除 |
| Human Resources | 剔除 | 主观判断强，F1 结果依赖模型候选选择质量，不利于隔离 CPU 负载 |
| Technology Research | 剔除 | 强依赖网页搜索、信息检索、大模型综合和 LLM Judge |

推荐 AlphaEval CPU 子集：

1. Procurement & Operations：采购约束验证、BOM/Excel 优化类任务。
2. Software Engineering：可自动执行 UI/E2E 测试的代码任务。
3. Healthcare & Life Sciences：纯数值、日期、规则校验任务。
4. Finance & Investment：结构化数据抽取任务，不包含长报告评分。

## 降级为辅助 benchmark

以下 benchmark 可以作为辅助组，但不建议作为 CPU 主评估集。

| Benchmark | 降级原因 | 可用方式 |
|---|---|---|
| MCP-Universe | 工具调用多，但本地 CPU 负载不一定重，模型决策影响大 | 用于测 orchestration 和 trace 处理 |
| BFCL | 主要评估函数调用准确性，本地执行轻 | 用作轻量 baseline |
| Tool Decathlon | 长链路工具任务，但模型选择路径影响大 | 固定工具调用序列后可测 harness |
| tau-bench / tau2-Bench | 对话和用户交互影响较大 | 只用于调度/状态管理开销 |
| PaperBench | 科研复现任务长，但模型规划和外部依赖强 | 适合作为长时间稳定性压力测试，不作为主集 |
| CORE-Bench | 复现环境有价值，但任务复杂度和依赖差异大 | 可选少量固定任务做系统压力测试 |
| ResearchCodeBench | 科研代码实现受模型质量影响强 | 使用固定实现结果进行 replay |

## 建议剔除

以下 benchmark 不适合作为“降低大模型影响的 CPU 负载评估”主集。

| 类别 | Benchmark | 剔除原因 |
|---|---|---|
| 纯知识/问答 | MMLU, GPQA Diamond, HLE, MMMLU | 本地 CPU 负载弱，主要测模型知识 |
| 数学推理 | AIME, HMMT, USAMO, FrontierMath, MathVista | 主要测推理能力，CPU 侧执行少 |
| 抽象推理 | ARC-AGI-2, OODBench | 模型能力主导，系统负载弱 |
| 多模态理解 | Video-MME, MMMU | 若不做本地视频/图像预处理，主要仍是模型侧能力 |
| 浏览搜索能力 | BrowseComp, BrowseComp-V3 | 强依赖实时搜索、模型检索策略和外部网络 |
| 个性化 Web | Persona2Web, AgenticShop | 模型决策和网页状态影响大 |
| 安全/红队 | AgentLAB, STING, GT-HarmBench, ForesightSafety, APST, Unsafer | 目标是安全行为，不是 CPU 负载 |
| 记忆/多 Agent | MemoryArena, Collective Behavior | 模型记忆和多 Agent 交互影响强，变量复杂 |
| 主观职业任务 | Human Resources 类任务 | 主观判断和人工标注权重高，不利于 CPU 隔离 |

## 推荐最终测试矩阵

### A. 主评估集

| 维度 | Benchmark | 主要 CPU 负载 |
|---|---|---|
| 终端/命令行 | Terminal-bench | shell、文件系统、进程调度、容器 |
| 软件工程 | SWE-bench | 依赖安装、测试执行、编译、repo IO |
| 数据科学 | DSBench | pandas/numpy、数据 IO、脚本执行 |
| ML 工程 | MLE-bench | 训练/评测脚本、数据处理、CPU-only 实验 |
| 生产综合子集 | AlphaEval P&O / SE / 数值类任务 | Excel、规则验证、UI/E2E、rubric 执行 |

### B. 可选扩展集

| 维度 | Benchmark | 主要 CPU 负载 |
|---|---|---|
| GUI/桌面 | OSWorld | 浏览器/桌面应用、截图、状态校验 |
| Web 应用 | WebArena | 浏览器渲染、DOM 操作、服务端环境 |
| 办公流 | OfficeQA / OdysseyBench | 文档处理、办公应用、GUI 自动化 |
| 工具编排 | BFCL / MCP-Universe | tool runtime、trace、JSON 解析 |

## 推荐执行方式

为了降低大模型侧影响，建议采用三种运行模式：

### 1. Full Agent 模式

完整运行 Agent，用于观察真实端到端表现。

缺点是模型推理、API 延迟、模型决策质量会显著影响结果。

### 2. Fixed Output 模式

提前固定 Agent 产物，例如 patch、代码文件、CSV 输出、报告文件，然后只运行 benchmark 的本地评测阶段。

适合测：

- 测试执行耗时
- evaluator CPU 开销
- 容器启动成本
- 文件 IO
- 并发吞吐

### 3. Replay Trajectory 模式

记录一次 Agent 工具调用轨迹，后续重复 replay 相同命令、文件操作和测试流程。

适合测：

- Agent harness 开销
- 工具调用 runtime
- 进程调度
- 日志写入
- 端到端系统稳定性

## 最小推荐组合

如果只选一组低模型影响的 CPU benchmark，建议：

1. Terminal-bench：命令行与容器负载。
2. SWE-bench：代码仓库与测试执行负载。
3. DSBench：数据分析脚本负载。
4. MLE-bench：ML 工程 CPU-only 负载。
5. AlphaEval 子集：采购运营、软件工程、数值验证任务。

## 结论

为了评估 CPU 负载特征和性能表现，应过滤掉以模型知识、主观判断、实时搜索、安全行为和复杂多 Agent 交互为核心的 benchmark。

推荐主线是：

`Terminal-bench + SWE-bench + DSBench + MLE-bench + AlphaEval 规则化子集`

这组 benchmark 能覆盖 shell、repo、测试、数据处理、训练脚本、容器、文件 IO、规则 evaluator 和 UI/E2E 测试，同时尽量降低大模型推理质量对 CPU 性能结论的干扰。
