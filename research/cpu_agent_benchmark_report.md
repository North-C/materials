# CPU 上 Agent 评估 Benchmark 负载分析报告

## 目标

本报告面向在 CPU 上进行主要 Agent 评估测试的场景，筛选适合用于 CPU 负载、性能瓶颈、任务调度和系统优化分析的 benchmark 类型。重点不放在模型分数本身，而放在 benchmark 是否能产生真实 Agent 运行负载：代码执行、文件 IO、浏览器/GUI 自动化、容器沙箱、工具调用、数据处理、日志采集和评测脚本执行。

## 一、推荐优先级

| 优先级 | Benchmark 类别 | 代表 Benchmark | 适合度 |
|---|---|---|---|
| P0 | 生产型综合 Agent | AlphaEval, TheAgentCompany, xbench | 最贴近真实业务 Agent |
| P0 | 软件工程/CLI | SWE-bench, Terminal-bench, ProjDevBench, LongCLI-Bench | CPU/IO/测试负载明显 |
| P1 | OS/GUI/Web 操作 | OSWorld, WebArena, AppWorld, OfficeQA, OdysseyBench | 浏览器、GUI、截图、状态验证负载丰富 |
| P1 | 数据科学/ML 工程 | MLE-bench, DSBench, DAComp | 数据处理、训练脚本、评测耗时明显 |
| P2 | 工具调用/MCP | MCP-Universe, BFCL, Tool Decathlon, tau-bench | 适合分析 tool runtime 和 orchestration |
| P2 | 科研 Agent | PaperBench, CORE-Bench, EXP-Bench, ResearchGym | 长链路、复现实验、依赖安装复杂 |
| P3 | 知识/数学/推理 | MMLU, GPQA, FrontierMath, ARC-AGI-2 | 更偏模型能力，CPU 侧负载较弱 |

## 二、P0：生产型综合 Agent Benchmark

代表：AlphaEval、TheAgentCompany、xbench。

这类 benchmark 最接近真实企业使用 Agent 的方式。AlphaEval 覆盖 HR、金融投资、采购运营、软件工程、医疗生命科学、技术研究 6 个职业领域，输入包括 PDF、Excel、Markdown、代码/YAML，并通过 Docker 沙箱、CLI Agent、rubric.py、LLM Judge、UI 测试等组合完成评估。

CPU 侧价值：

| 负载来源 | 说明 |
|---|---|
| 容器沙箱 | 每个任务可能涉及 Docker 启动、文件挂载、隔离执行 |
| 多格式解析 | PDF、Excel、CSV、图片、代码文件处理 |
| Agent orchestration | 多轮工具调用、文件读写、轨迹记录 |
| 评测脚本 | rubric、数值校验、结构校验、UI 自动化 |
| 长任务运行 | AlphaEval 报告中平均每任务约 14 分钟、46 轮交互 |

建议用途：作为 CPU Agent benchmark 总控框架，观察完整生产任务下的端到端 wall time、CPU time、IO wait、上下文切换、容器开销和评测阶段耗时。

## 三、P0：软件工程与 CLI Benchmark

代表：SWE-bench、Terminal-bench、ProjDevBench、LongCLI-Bench。

这类任务要求 Agent 在代码仓库或命令行环境中修改文件、运行测试、安装依赖、阅读日志、修复错误。它们非常适合 CPU 性能评估，因为本地执行占比较高，不只是 API 调用。

典型负载：

| 阶段 | CPU/系统压力 |
|---|---|
| repo 初始化 | git checkout、依赖解析、文件扫描 |
| 代码理解 | rg、cat、sed、语言服务器或静态分析 |
| 代码修改 | 文件写入、格式化、lint |
| 测试执行 | pytest、npm test、编译、单元测试 |
| 失败重试 | 多轮测试-修复循环，产生长时间 CPU 占用 |

建议用途：用于测试 CPU 在多 Agent 并发代码任务下的吞吐能力。重点指标包括测试阶段 CPU 占比、依赖安装耗时、文件系统热点、并发任务间资源争用。

## 四、P1：OS/GUI/Web 操作 Benchmark

代表：OSWorld、WebArena、AppWorld、OfficeQA、OdysseyBench。

这类 benchmark 让 Agent 在真实或模拟桌面、浏览器、办公软件、网页应用中完成任务。OSWorld 强调真实 OS 环境和多模态桌面任务；WebArena 强调网页环境中的高层自然语言指令到具体网页交互。

典型负载：

| 负载来源 | 说明 |
|---|---|
| 浏览器进程 | Chromium/Playwright/Selenium 占用 CPU 和内存 |
| GUI 自动化 | 鼠标键盘事件、窗口状态、截图 |
| OCR/视觉处理 | 截图理解、图像编码、页面状态解析 |
| 环境状态验证 | 文件、DOM、应用状态检查 |
| 多应用切换 | Office、浏览器、文件系统、终端混合操作 |

建议用途：用于评估 CPU 在 GUI Agent 中的实际瓶颈，尤其是浏览器实例数量、截图频率、页面渲染、自动化测试与 Agent 推理之间的资源竞争。

## 五、P1：数据科学与 ML 工程 Benchmark

代表：MLE-bench、DSBench、DAComp。

MLE-bench 以真实 Kaggle 风格 ML 工程任务为核心，DSBench 面向数据科学 Agent，DAComp 覆盖数据智能生命周期。这类 benchmark 的特点是数据文件大、Python 执行重、实验循环长。

典型负载：

| 阶段 | CPU/系统压力 |
|---|---|
| 数据读取 | CSV/Parquet/图片/表格加载 |
| 数据清洗 | pandas/numpy 计算 |
| 特征工程 | 批量转换、聚合、编码 |
| 训练/推理 | CPU 训练、小模型推理、交叉验证 |
| 评分脚本 | leaderboard metric、本地评测 |

建议用途：用于分析 CPU 在数据密集型 Agent 中的吞吐与资源隔离。适合测试多任务并发时的 CPU cache、内存带宽、磁盘 IO、Python 多进程开销。

## 六、P2：工具调用与 MCP Benchmark

代表：MCP-Universe、BFCL、Tool Decathlon、tau-bench、ACEBench。

这类 benchmark 不一定产生很重的计算负载，但非常适合分析 Agent runtime 本身：工具选择、参数生成、函数调用、状态维护、多轮交互、失败恢复。

典型观测点：

| 指标 | 意义 |
|---|---|
| tool call 数量 | 反映 Agent 行为复杂度 |
| 单次 tool latency | 区分模型等待与本地工具耗时 |
| JSON 解析/校验成本 | 工具调用密集时会放大 |
| 重试率 | 影响端到端 CPU 和 wall time |
| trace size | 日志写入和后处理成本 |

建议用途：作为低计算但高 orchestration 的对照组，用来区分 CPU 被业务任务消耗还是 CPU 被 Agent 框架和工具调度消耗。

## 七、P2：科研 Agent Benchmark

代表：PaperBench、CORE-Bench、EXP-Bench、ResearchGym、ResearchCodeBench。

科研类任务通常要求检索论文、复现实验、运行代码、生成报告、比较结果。它们的 CPU 负载不稳定，但非常贴近长周期 Agent 工作流。

适合场景：

| 场景 | 价值 |
|---|---|
| 论文复现 | 依赖安装、脚本运行、实验管理 |
| 科学代码实现 | 类似 coding benchmark，但更偏研究代码 |
| 结果验证 | 需要自定义 evaluator 或 LLM Judge |
| 长链路任务 | 适合观察任务超时、容器残留、磁盘膨胀、日志增长和资源回收 |

建议用途：作为长时间运行稳定性测试，重点观察任务超时、容器残留、磁盘膨胀、日志增长和资源回收。

## 八、不建议作为 CPU 主 Benchmark 的类别

知识、数学、纯问答类 benchmark，例如 MMLU、GPQA、FrontierMath、AIME、ARC-AGI-2，适合评估模型能力，但对 CPU 负载分析价值有限。它们通常缺少复杂本地执行、文件系统操作、浏览器/GUI、数据处理和沙箱环境。

可以作为轻量 baseline，用来测：

| 用途 | 说明 |
|---|---|
| API 调用基线 | 几乎不含本地执行 |
| evaluator 开销 | LLM Judge 或规则评分成本 |
| batch 调度 | 大量短任务吞吐 |

## 九、建议的 CPU 评估组合

建议构建 4 层 benchmark 矩阵：

| 层级 | Benchmark | 目的 |
|---|---|---|
| L1 轻量 Agent 调度 | BFCL / tau-bench | 测工具调用和框架开销 |
| L2 代码执行 | SWE-bench / Terminal-bench | 测编译、测试、文件 IO |
| L3 GUI/Web | OSWorld / WebArena | 测浏览器、截图、GUI 自动化 |
| L4 生产综合 | AlphaEval | 测端到端业务 Agent 负载 |

最小可行组合建议：

1. SWE-bench：代码仓库、测试执行、文件 IO。
2. Terminal-bench：命令行长任务、shell 工具链。
3. OSWorld 或 WebArena：GUI/浏览器操作。
4. MLE-bench 或 DSBench：数据处理和实验脚本。
5. AlphaEval：最终生产综合验证。

## 十、推荐采集指标

| 指标类别 | 具体指标 |
|---|---|
| 时间 | wall time、CPU time、user/sys time、任务排队时间 |
| CPU | 平均利用率、峰值利用率、per-core 分布 |
| 调度 | context switch、run queue、进程/线程数量 |
| IO | read/write bytes、IO wait、文件数、日志大小 |
| 内存 | RSS、page fault、swap、容器内存峰值 |
| 容器 | 启动耗时、镜像大小、挂载成本、清理耗时 |
| Agent | turn 数、tool call 数、失败重试次数、轨迹大小 |
| 评测 | evaluator 耗时、LLM Judge 耗时、rubric 脚本耗时 |

## 结论

如果目标是 CPU 上的 Agent 负载与性能优化，不应只跑模型问答 benchmark。最有价值的是组合型负载：代码执行 + GUI/Web + 数据处理 + 生产综合任务。

AlphaEval 适合作为最终综合评估框架，SWE-bench/Terminal-bench 适合定位本地执行瓶颈，OSWorld/WebArena 适合暴露浏览器和 GUI 自动化成本，MLE-bench/DSBench 适合分析数据密集型 Agent 任务。

## 参考来源

- AlphaEval: https://arxiv.org/abs/2604.12162
- AlphaEval GitHub: https://github.com/GAIR-NLP/AlphaEval
- SWE-bench: https://arxiv.org/abs/2310.06770
- Terminal-bench: https://terminalbench.lol/
- OSWorld: https://os-world.github.io/
- WebArena: https://webarena.dev/og/
- MLE-bench: https://github.com/openai/mle-bench
- DSBench: https://arxiv.org/abs/2409.07703
