# Agent / AI Benchmark 分类摘录与用途解读

本文件根据 AlphaEval 论文 Table 1 中列出的 benchmark 进行整理，并按用途分类解读。重点服务于后续 CPU 上 Agent 评估负载研究。

## 1. 软件工程与编码类

| Benchmark | 主要用途 |
|---|---|
| SWE-bench | 评估 Agent 修复真实 GitHub issue 的能力 |
| SWE-bench Multimodal | 加入视觉/截图等多模态软件问题 |
| Multi-SWE-bench | 多语言真实 issue 修复 |
| SWE-Lancer | 面向真实自由职业软件任务和经济价值评估 |
| SWT-Bench | 评估真实 bug fix 的测试与验证能力 |
| Terminal-bench | 长任务 CLI 环境中的 Agent 操作能力 |
| FeatBench | 功能级代码生成，更贴近实际开发需求 |
| DevBench | 覆盖完整软件开发生命周期 |
| LongCLI-Bench | 长周期命令行编程任务 |
| ProjDevBench | 端到端项目开发型编码 Agent 评估 |

这类最适合做 CPU 侧代码 Agent 工作负载：编译、测试、文件读写、包安装、CLI 调用、静态分析都会产生明显本地 CPU/IO 压力。

## 2. 数据科学与 ML 工程类

| Benchmark | 主要用途 |
|---|---|
| DSBench | 数据科学 Agent 能否完成数据分析任务 |
| MLE-bench | 机器学习工程任务，如 Kaggle 风格建模 |
| KernelBench | 评估模型写高性能 GPU kernel 的能力 |
| DAComp | 数据智能全生命周期任务，含清洗、分析、建模 |

这类适合评估 Python 执行、数据处理、表格计算、模型训练脚本等负载。CPU 关注点是 pandas/numpy 计算、数据 IO、任务并发和脚本运行时间。

## 3. 代码竞赛与安全类

| Benchmark | 主要用途 |
|---|---|
| LiveCodeBench | 污染较低的代码题评估 |
| CodeElo | 竞赛级代码生成，用 Elo 方式衡量 |
| Aider Polyglot | 多语言代码编辑/修复能力 |
| CyBench | 网络安全能力与风险评估 |
| BountyBench | 攻防 Agent 在真实安全系统中的价值评估 |
| VimGolf-Gym | Vim/编辑器操作任务 |
| DPAI Arena | JetBrains 相关开发 Agent 竞技/评测 |
| Spring AI Bench | Spring AI 生态相关开发能力 |
| AGENTS.md Eval | 评估仓库级上下文文件对 coding agent 的帮助 |

安全与代码竞赛类更强调正确性和约束执行。CPU 负载通常来自测试执行、沙箱、编译器、解释器和安全环境模拟。

## 4. 工具使用与网页交互类

| Benchmark | 主要用途 |
|---|---|
| WebArena | 网页环境中的自主操作任务 |
| AgentBench | 通用 LLM Agent 能力评估 |
| AgentBoard | 多轮 Agent 分析评估面板 |
| tau-bench | 工具-Agent-用户交互任务 |
| tau2-Bench | 双控制环境中的对话 Agent |
| TheAgentCompany | 办公/企业真实任务 Agent 评估 |
| Tool Decathlon | 多工具、长周期任务执行 |
| ACEBench | 工具使用能力对比 |
| MCP-Universe | 基于真实 MCP server 的工具调用评估 |
| BFCL | 函数调用/工具调用基准 |
| Context-Bench | Agent 上下文工程能力 |
| Letta Evals | 评估具备记忆/学习能力的 Agent |
| EcomBench | 电商场景 Agent 评估 |
| DeliveryBench | 真实配送/收益型 Agent 任务 |
| WorFBench | Agentic workflow 生成能力 |
| BrowseComp | 浏览器搜索 Agent 的困难检索任务 |
| AgencyBench | 大上下文真实任务中的自主 Agent |
| HammerBench | 移动设备函数调用/工具调用评估 |

这是最贴近 Agent 产品负载的类别：浏览器、HTTP 请求、工具调用、状态维护、长轨迹日志、JSON 解析都会参与。CPU 分析应重点拆分 tool runtime、browser runtime、agent orchestration 和 evaluator runtime。

## 5. 操作系统与 GUI 类

| Benchmark | 主要用途 |
|---|---|
| GAIA | 通用 AI assistant 复杂任务 |
| OSWorld | 真实电脑环境中的多模态操作任务 |
| AppWorld | 可控 app 世界中的交互式任务 |
| WebSuite | 系统分析 Web Agent 失败原因 |
| OSUniverse | 多模态 GUI 导航 Agent |
| OdysseyBench | 长周期 Office 应用工作流 |
| OfficeQA | 企业办公端到端 grounded reasoning |

这类对 CPU 评估很有价值，因为会拉起浏览器、桌面应用、GUI 自动化、截图解析、OCR/视觉处理和环境状态校验。

## 6. 科研 Agent 类

| Benchmark | 主要用途 |
|---|---|
| EXP-Bench | AI 是否能执行科研实验 |
| PaperBench | AI 复现实验/论文结果能力 |
| CORE-Bench | 计算可复现性 Agent 评估 |
| Auto-Bench | 自动科学发现能力 |
| ResearchCodeBench | 实现新 ML 研究代码 |
| AstaBench | 科学研究套件中的严谨 Agent 评估 |
| AInsteinBench | 科学代码仓库上的 coding agent |
| ResearchGym | 真实 AI 研究任务 Agent 评估 |

科研类任务通常长链路、依赖多、运行重。适合构造 CPU 压力测试：文献检索、代码复现、实验脚本、数据处理、结果验证。

## 7. 数学、知识与推理类

| Benchmark | 主要用途 |
|---|---|
| MMLU | 大规模多任务知识理解 |
| GPQA Diamond | 研究生级高难问答 |
| MMMU | 多学科多模态理解推理 |
| MathVista | 视觉数学推理 |
| FrontierMath | 前沿高难数学推理 |
| AIME / HMMT / USAMO | 数学竞赛与证明能力 |
| MMMLU | 多语言 MMLU |
| Video-MME | 视频多模态理解 |
| OpenAI-MRCR | 多轮指代消解 |
| HLE | Humanity's Last Exam，广泛高难知识 |
| ARC-AGI-2 | 抽象推理能力 |
| OODBench | 视觉语言模型分布外泛化 |

这类更偏模型能力，不一定产生重 CPU 本地负载，除非配合 verifier、符号计算、视频处理或批量评测。

## 8. Agent 产品评估类

| Benchmark | 主要用途 |
|---|---|
| xbench | 按职业对齐的真实任务，追踪 Agent 生产率扩展 |
| AgentIF-OneDay | 日常场景下通用 Agent 指令遵循 |

这类和 AlphaEval 方向最接近：评估完整 Agent 产品而非裸模型，更适合作为 CPU 负载分析的上层任务集。

## 9. 2026 新兴 Benchmark

| Benchmark | 主要用途 |
|---|---|
| Persona2Web | 个性化 Web Agent，结合用户历史 |
| AmbiBench | 移动 GUI Agent 的模糊/真实指令 |
| PAHF | 从人类反馈学习个性化 Agent |
| AgenticShop | 个性化网页购物 Agent |
| GAP Benchmark | 工具调用安全迁移差距 |
| AgentLAB | 长周期攻击下的 Agent 安全 |
| STING | 多轮多语言非法协助风险 |
| GT-HarmBench | 博弈论视角安全风险 |
| ForesightSafety | 前沿风险与治理安全评估 |
| APST | 重复推理下的安全压力测试 |
| MemoryArena | 多 session 任务中的 Agent 记忆 |
| WebWorld-Bench | Web Agent 训练/评估的大规模网页世界 |
| Gaia2 | 动态、异步环境中的 Agent |
| SkillsBench | Agent skills 跨任务有效性 |
| MATEO | 多模态时间推理与规划 |
| SciAgentGym | 多步科学工具使用 |
| Drug Scouting | 药物资产搜索、投资、BD、竞品情报 |
| AD-Bench | 广告分析 Agent |
| GUI-GENESIS | 自动合成 GUI 环境与可验证奖励 |
| BookingArena | 订票/预订类 Web Agent |
| BrowseComp-V3 | 浏览搜索 Agent 新版本 |
| Collective Behavior | 大量 LLM Agent 集体行为 |
| Unsafer | 多轮工具使用 Agent 安全风险 |
| Proxy State Eval | 多轮工具调用的代理状态可验证评估 |

## 对 CPU 评估研究的筛选建议

优先关注四类：

1. Software / CLI
2. Tool / Web
3. OS / GUI
4. Production / Agent Product

它们最容易产生真实 CPU 负载：容器启动、文件系统操作、浏览器自动化、测试执行、数据解析、长轨迹日志和 evaluator 执行。

AlphaEval 的价值在于把这些能力组合成生产任务包，而不是孤立测模型能力。若目标是 CPU 负载与性能优化，可以从 AlphaEval + Terminal-bench + OSWorld/WebArena + MLE/DSBench 组合出一套覆盖代码、网页、GUI、数据处理的 Agent 评估负载矩阵。
