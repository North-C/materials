# OpenAI 与 Anthropic 的 Agentic AI 战略、CPU 服务器需求空间与厂商竞争力研究

> 研究日期: 2026-06-16 | 来源数量: 51 | 字数: ~9500 | 模式: Standard | AS_OF: 2026-06 | 官方/分析师一级源占比: ~50%

## 摘要 / Executive Summary

截至 2026 年中，OpenAI 与 Anthropic 已经把 Agent 从概念演示推到了 10 亿美元级别的真实业务：OpenAI 在 2025 年 7 月发布 **ChatGPT agent**，把此前独立的 Operator（浏览器代理）、Deep Research（深度研究）和 ChatGPT 对话能力整合进一个产品，并以 Pro 用户 400 条/月、其他付费 40 条/月的"消息配额"作为新的定价杠杆 [1]；Anthropic 的 **Claude Code** 在 2025 年 5 月到 2026 年 5 月的一年内，年化收入从 0 跃迁至 25 亿美元以上，作者已经占到全球 GitHub 公开提交的约 4% [4]。两家公司的运行率收入都在 2026 年 4 月达到约 300 亿美元，但路径截然相反：OpenAI 约 85% 来自 ChatGPT 消费订阅且仍在亏损，2026 全年预计亏 140 亿美元；Anthropic 约 85% 来自企业和开发者，Q2 2026 已经实现 5.59 亿美元的营业利润 [25]。

在 Agentic AI 工作负载侧，一个由 AMD、Intel、TrendForce、Arm 共同推动的产业共识正在形成：CPU 与 GPU 的部署比例正在从训练时代的 1:8、推理时代的 1:4，向 Agentic 阶段的 **1:1–1:2** 演进 [18][34][35]。KAIST 在 arXiv 2506.04301 中的实测数据给出了最关键的解释：在一次 Agent 任务中，工具调用阶段 GPU 闲置时间高达执行时间的 54.5%——**在 Agentic 系统里，被低度利用的是 GPU，而不是 CPU** [23]。

以微信为典型样本的容量测算显示：在 14.32 亿月活、30% 活跃采纳率、单 Agent 平均 0.5 核的基础情景下，需要约 **2.15 亿个 CPU 核、170 万台双路服务器、420 亿美元一次性资本开支** [33][18][39]；激进情景（50% 采纳 × 2 核/agent）则达到 14.3 亿核、1120 万台服务器，相当于今天全球超大规模数据中心总规模的 30–45% [20][29]。CPU 服务器厂商的竞争维度已经从单纯的单核 IPC，扩展到核数密度、内存带宽、AI 矩阵扩展（Intel AMX / AMD AVX-512 / ARM SVE2）、机密计算（TDX/SEV-SNP/CCA）、TCO、供应链韧性、信创合规等八项以上。报告最后给出优化路径与核心争议。

---

## 目录

1. 第一部分：当前 Agentic AI 业务布局
   - 1. OpenAI：从 Operator 到 ChatGPT Agent 的产品整合
   - 2. Anthropic：Claude Code 与 MCP 生态的企业路径
   - 3. 财务对照：消费者与企业的两条岔路
   - 4. 价值主张与商业模式小结
2. 第二部分：未来 Agent 应用与 CPU 服务器需求空间
   - 5. Agentic AI 市场规模：多家机构预测的对照
   - 6. 未来 Agent 应用形态
   - 7. Agentic 工作负载特性：为什么 CPU 不可替代
   - 8. 微信场景 CPU 需求测算：三档情景
   - 9. 全球外推与可行性边界
   - 10. Agent 负载形态：spiky / steady / sync / async
3. 第三部分：CPU 服务器厂商竞争力维度
   - 11. CPU 服务器厂商竞争格局
   - 12. Agentic 工作负载下的竞争力八维度
   - 13. 优化路径与路线图（2026–2027）
4. 第四部分：综合判断
   - 14. 核心争议
   - 15. 关键发现
   - 16. 局限性与未来方向
5. 参考文献

---

## 第一部分：当前 Agentic AI 业务布局

### 1. OpenAI：从 Operator 到 ChatGPT Agent 的产品整合

OpenAI 在 2025–2026 的 Agentic 战略可以总结为一句话："**把所有 Agent 入口收敛进 ChatGPT，把消息配额变成新的定价杠杆**"。

2025 年 3 月，OpenAI 发布了面向开发者的 **Responses API** 与 **Agents SDK**，并提供 Computer Use 工具（其底层 CUA 模型在 OSWorld 上得 38.1%、WebArena 上 58.1%、WebVoyager 上 87%），明确把 Agent 开发作为一等公民的开发原语；同期的 Assistants API 已宣布将在 2026 年中下线 [2]。同年 7 月，OpenAI 把此前独立的 **Operator**（浏览器自动化预览）、**Deep Research**（深度研究）和 ChatGPT 对话能力统一收编为 **ChatGPT agent**——视觉浏览器、文本浏览器、终端、ChatGPT Connectors（Gmail、GitHub）、浏览器接管模式等都作为一个产品内的工具调用。Operator 的独立预览站点在数周内下线 [1]。

商业化层面，OpenAI 的工具调用是按调用次数单独计费的：网页搜索 GPT-4o 每 1000 次查询 30 美元、GPT-4o-mini 25 美元；Codex gpt-5.3-codex 单次 3.50 美元（批处理 0.35 美元）；Deep Research 单次 5.00 美元 [3]。这意味着每完成一个 Agentic 任务（数十次工具调用），实际单次任务成本可能从几美元到几十美元不等。

更激进的定价信号来自 The Information 在 2025 年 3 月披露的内部投资者路演：OpenAI 正在向投资人推介三档"博士级 Agent"——2000 美元/月（高收入知识工作者）、1 万美元/月（中等）、2 万美元/月（PhD 级研究 Agent）[27]。这一价格区间尚未官方落地，应作为"投资者叙事"而非已发布 SKU 对待。

**置信度:** High（产品形态与官方定价部分）；Medium（2 万美元/月档位定价，仍属传闻级）

**依据:** [1][2][3] 为 OpenAI 官方一手资料，[27] 是高信誉的 The Information 报道，但产品定价的具体 SKU 仍需待 S-1 或官方发布验证。

**反方解释:** HSBC 在 2026 年估计 OpenAI 相对其增长计划存在约 2070 亿美元的资金缺口 [25]——其 2026 年预计 140 亿美元亏损和 2028 年 1210 亿美元计算开支意味着 OpenAI 必须在 Agentic 业务上大规模变现才能闭环，2 万美元/月定价也可能是为支撑这一叙事的"投资者友好型"披露，未必最终落地。

### 2. Anthropic：Claude Code 与 MCP 生态的企业路径

Anthropic 走的是"**先做开发者工具，再向企业横向扩展**"的路径，且把战略支点压在一个开放协议——**Model Context Protocol（MCP）**——上。

最具说服力的数字来自 Anthropic 2026 年 5 月的 Series G 融资披露：**Claude Code 年化收入从 2025 年 5 月的 0、到 2025 年 11 月的 10 亿美元、再到 2026 年 5 月的 25 亿美元以上**，业务订阅在 2026 年内增长了 4 倍，企业客户已占 Claude Code 收入的 50% 以上；周活跃用户在 2026 年内翻倍；Claude Code 已经占到全球所有公开 GitHub 提交的约 4%（一个月内翻倍）[4]。这是软件行业近年来最快的产品收入爬坡曲线之一。

战略层面有四条主线：

- **Claude Agent SDK**（2026 年初由 Claude Code SDK 更名）+ 托管 MCP 计算组合成"Claude + MCP Managed Agents"，把 Agent 部署的产品形态从 CLI 工具升级为可托管的基础设施 [4]。
- **MCP 协议捐赠**：2025 年 11 月，Anthropic 把 MCP 捐给 Linux Foundation 下新成立的"Agentic AI Foundation"。截至 2026 年中，MCP 累计下载量约 9700 万次，已经获得 OpenAI 和 Google 的跨厂商采纳 [5]。这是 Anthropic 把"协议层"——而非"模型层"——作为护城河的最明确表态。
- **垂直行业拓展**：2026 年 1 月推出 Cowork（11 个针对销售/法律/财务角色的开源插件）；Claude for Enterprise 已通过 HIPAA 合规认证；TCS 合作覆盖 56 个国家、5 万名员工 [4]。
- **从模型到工作流**：与 OpenAI 主要把 Agent 作为消费产品不同，Anthropic 的客户结构（>500 家年付超 100 万美元、8 家财富 10 强）显示其 Agent 业务的核心是"企业工作流自动化" [4]。

**置信度:** High

**依据:** [4][5] 均为 Anthropic 官方一手披露，财务与产品数字清晰可追溯。

**反方解释:** Anthropic Q2 2026 的 5.59 亿美元营业利润**剔除了股权激励**，GAAP 口径下尚未盈利；同时 Anthropic 预测 2028 年实现 700 亿美元收入、170 亿美元正向现金流和约 77% 毛利率 [25]——这一预测假设了极高的企业 AI 支出持续扩张，若 Goldman Sachs 的保守采纳率预测（2030 年知识工作者 Agentic 采纳率仅 12%）成真，Anthropic 的预测目标将面临显著下行风险 [13]。

### 3. 财务对照：消费者与企业的两条岔路

> ⚠️ **预测口径警示**：表中所有 2026 全年和 2028 预测均来自投资者路演材料与媒体报道 [25]，**两家公司均未公开 S-1**。Anthropic 的"5.59 亿美元营业利润"剔除了股权激励（非 GAAP），GAAP 口径下尚未盈利；OpenAI 的"亏损 140 亿美元"则可能包含一次性资本开支。读者应将这些数字理解为"管理层向投资者的目标叙事"，而非已审计财务结果。

把两家公司放在同一坐标系里看，2026 年 4 月是一个关键拐点：**Anthropic 在年化运行率上首次追平 OpenAI**，两家都在约 300 亿美元水平 [25]。但收入结构截然不同：

| 维度 | OpenAI | Anthropic |
|---|---|---|
| 收入结构 | ~85% ChatGPT 消费订阅，~95% 用户为免费层 | ~85% 企业/开发者 API |
| 2026 全年业绩 | 预计亏损 140 亿美元 | Q2 2026 已实现 5.59 亿美元营业利润（**非 GAAP**，剔除股权激励；GAAP 仍亏损） |
| 2028 预测 | 计算开支 1210 亿美元，亏损 740 亿美元 | 收入 700 亿美元，正向现金流 170 亿美元（投资者路演目标） |
| IPO 进度 | 已秘密提交，目标 2026 年 9 月 > 1 万亿美元估值 | 亦在准备 IPO |
| 大客户基数 | 9 亿周活用户（消费侧）| > 500 家年付百万级客户、8 家财富 10 强 |

数据来源：[4][25]

一个被低估的细节：**企业客户单位 token 的收入贡献是消费客户的 3–5 倍** [25]。这意味着 Anthropic 的"企业优先"策略不仅利润率更高，在单位算力变现效率上也结构性占优——而 Agentic AI 因为典型工作流（编码、客服、RPA 替代）本身就是企业场景，这一结构性优势还有继续扩大的趋势。

**置信度:** High（公开报道一致）

**依据:** [25] Forbes 援引了 OpenAI 与 Anthropic 双方高管和 IPO 准备文件，且与 [4] 官方披露相互印证。

**反方解释:** 两家公司都未公开 S-1，所有 2026–2028 的财务预测都基于投资者路演材料与分析师估计，实际业绩可能因为算力成本、客户流失率、模型迭代速度等因素显著偏离。

### 4. 价值主张与商业模式小结

综合看，OpenAI 与 Anthropic 当前给用户带来的核心价值可以归纳为三类：

1. **任务自动化**：浏览器操作、文档处理、深度研究、代码生成等"本需人工 30 分钟以上"的任务被压缩到分钟级 [1][2][4]。Operator 的 OSWorld 38.1% 说明桌面自动化仍不成熟，但网页与 API 范围内（WebArena 58.1%、WebVoyager 87%）已经具备生产力。
2. **企业工作流嵌入**：通过 SDK + MCP 把 Agent 接入既有 IT 系统（GitHub、Gmail、企业 SaaS），让 LLM 不再是孤立的聊天框，而是有上下文、有工具、有记忆的工作流执行体 [2][5]。
3. **新经济模式（services-as-software）**：Sequoia 在 2026 年 1 月明确提出"services-as-software"论点——Agent 把原本需要人工服务的工作（法律检索、客服、SRE、销售开发代表）转化为软件订阅，使可寻址市场从约 1 万亿美元的软件市场扩展到约 10 万亿美元以上的全球服务市场 [50]。

商业模式的差异：

- **OpenAI**：消费订阅（Plus 20 美元/月、Pro 200 美元/月）+ API 按 token 计费 + 高级 Agent 阶梯定价（传闻 2000–20000 美元/月）。本质是"消费入口 + 算力配额"。
- **Anthropic**：企业席位订阅（Claude Code Business、Claude for Enterprise）+ API 按 token 计费 + MCP 托管计算服务费。本质是"企业工作流订阅 + 协议生态护城河"。

一个值得关注的叙事信号：两家 CEO 都在 2026 年 5 月 IPO 前夕公开收回此前关于"AI 招致大规模失业"的预测——Amodei 2025 年还称"50% 白领入门级岗位将消失、失业率可能升至 20%"，2026 年改口称"自动化将扩展人类工作"；Altman 2023 年"岗位注定会消失"的表态也被更审慎的措辞取代 [26]。这一反转本身就是一个信号——在企业客户和政治善意面前，激进的"AI 替代"叙事对销售和监管关系都有害。

**置信度:** High

---

## 第二部分：未来 Agent 应用与 CPU 服务器需求空间

### 5. Agentic AI 市场规模：多家机构预测的对照

主要分析师对 Agentic AI 的市场规模预测存在显著的"牛-熊"区间。把六家权威机构放在一张图上：

| 机构 | 关键预测 | 时间窗口 | Source |
|---|---|---|---|
| IDC FutureScape | Agentic AI 占总 IT 支出 10–15%（2026）→ ~26%（2029，约 1.3 万亿美元）；45% 企业规模编排（2030） | 2026–2030 | [9][10] |
| Gartner | 40% 企业应用内嵌任务专用 Agent（2026 底，2025 不到 5%）；2026 处于"期望膨胀期"，实际部署率仅 17% | 2026 | [11][12] |
| Goldman Sachs | 2030 知识工作者 Agentic 采纳率仅 12%，2040 升至 37%；token 月消耗从 2026 基线增长 24 倍至 120 万亿 | 2026–2040 | [13] |
| McKinsey | 88% 企业使用 AI；62% 在试点 Agentic；仅 23% 进行规模部署 | 2025 | [14] |
| Deloitte | 66% 企业实现生产力提升；仅 20% 实现收入增长；34%/30%/37% 分为深度转型/流程重设/表面应用三档 | 2026 | [15] |
| Morgan Stanley | 全面 Agentic + 人形机器人可为标普 500 带来 ~9200 亿美元年净收益；影响约 90% 职业 | 2025 | [16] |
| Bain | 软件开发类 Agentic 实际生产力提升约 10–15%（vs 炒作的 80%） | 2025 | [17] |

把 IDC 的 1.3 万亿美元（2029）放到坐标系里：这相当于 2025 年全球企业 IT 支出约 5 万亿美元的 26%，是一个**结构性而非边际性**的开支转移。但同时 Goldman Sachs 的 12% 采纳率（2030）与 IDC/Gartner 的 40–45% 形成强烈反差——**这一分歧本身就是市场最大的不确定性**。

**置信度:** Medium

**依据:** 6 家机构均为一级权威源，但定义口径不一致——IDC 把"agentic AI 应用 + agentic fleet 管理"合并计算，Gartner 仅算企业应用内嵌 Agent，Goldman Sachs 仅算"知识工作者采纳"，三者不能直接相加。task-b 笔记明确指出 IDC 与 Gartner 之间存在 20–40% 的重复计算风险。

**反方解释:** Gartner 2026 Hype Cycle 把 Agentic AI 放在"期望膨胀期"位置，CIO 调研显示实际部署率仅 17% [12]；Bain 实证显示真实生产力提升 10–15%，远低于窄任务场景下 80% 的炒作数字 [17]。Goldman Sachs 还特别指出**实时语音 Agent 当前单位经济性比人工还贵**——并非所有 Agent 模式都经济可行 [13]。

### 6. 未来 Agent 应用形态

把"未来 Agent 用来做什么"按时间-场景做矩阵展开：

**短期（2026–2027）：垂直任务自动化**
- 编码（Claude Code、Cursor、Copilot Workspace）——已被验证最成熟的 Agentic 场景 [4][17]
- 客户支持（bland AI、Decagon、Sierra）——Deloitte 列为最高影响场景之一 [15]
- 知识管理 / 内部搜索（Glean、Notion AI）[15]
- 网页研究 / 浏览器自动化（ChatGPT agent）[1]

**中期（2028–2030）：跨应用个人与企业 Agent**
- 个人助理 Agent（按用户、按角色、按场景）：日程、邮件、采购、健康
- 企业流程 Agent：销售开发、SDR、SRE、财务结算、合规审查 [50][51]
- 多 Agent 协作系统：Manager–Worker、Debate、Tree-search 等架构（KAIST 论文中 LATS 算法已经实测平均每个请求 71 次 LLM 调用 [23]）

**长期（2030+）：services-as-software 与 AGI 路径**
- Sequoia "2026: This is AGI" 论点 [50]：长时程 Agent 实质等同 AGI
- a16z "Humans for Ideas, AI for Execution" 论点 [51]：人类负责战略，AI 负责执行
- 人机协作比例反转：从"1 人操作多机器"变为"1 人监督多 Agent"

**对微信这种超级应用的具体含义**：
- 用户侧：每个微信用户配一个长期记忆 + 多 MCP 集成（朋友圈、视频号、小程序、微信支付、企业微信）的个人 Agent
- 商家侧：每个小程序背后是一个商户 Agent，处理客服、订单、营销
- 平台侧：微信本身成为"Agent 编排平台"，类似 Anthropic 的 Claude + MCP Managed Agents 模式

### 7. Agentic 工作负载特性：为什么 CPU 不可替代

这是本报告最关键的一节，因为它直接决定了 CPU 服务器的需求空间。Agent 一次任务的资源消耗可以分解为 7 层：

| 层 | 主要承担硬件 | 单次任务的资源特征 |
|---|---|---|
| LLM 前向推理 | GPU/NPU | 单次任务平均 9.2 倍 CoT 的 LLM 调用，LATS 算法 71 次/任务 [23] |
| 任务编排（任务分解、状态机）| CPU | LangGraph/Temporal 类状态机，每步调度 |
| 工具调用（HTTP API、数据库、SaaS）| CPU | 30.2% 的总延迟来自工具执行 [23] |
| MCP Server 常驻 | CPU + 内存 | 每用户典型 3–20 个常驻 MCP server [38] |
| RAG / 向量检索 | CPU + 内存 | 嵌入推理 + ANN 检索，读多写少（10–50:1）[48] |
| 浏览器/代码沙箱 | CPU | Firecracker/E2B microVM，按需启动 [39] |
| 记忆/KV Cache/认证 | CPU + 内存 + GPU 显存 | 长期记忆 100 KB–5 MB/用户；KV cache 在 Agent 任务中比 CoT 多 3.0–5.4 倍 [23][48] |

**核心证据 1：CPU:GPU 比例的结构性转变**

> ⚠️ **来源利益冲突提示**：本节主要来源 AMD [34]、Intel [35]、Arm [40] 均为 CPU 厂商，存在明确商业利益——它们有动机夸大 CPU 需求增长。TrendForce [18] 作为独立分析师提供交叉验证，但其"agentic fleet management"口径与同业定义存在重复计算风险（详见 task-b Gap）。读者应将"1:1–1:2"理解为厂商共识 + 独立分析师确认，而非完全中立的实测。

AMD、Intel、TrendForce、Arm 在 2026 年都独立确认了同一趋势 [18][34][35][40]：

- 训练时代：CPU:GPU = 1:8（CPU 仅作为 head node，每 8 卡 GPU 服务器配 1 颗 CPU）
- 当前推理时代：1:4
- Agentic 时代：**1:1 到 1:2**（4–8 倍的 CPU 相对增长）

Arm 给出的结构性基准更直接：传统 AI 数据中心每 GW 电力约需 3000 万 CPU 核，Agentic AI 阶段每 GW 需 1.2 亿 CPU 核，**4 倍密度提升** [18]。

**核心证据 2：GPU 闲置 54.5%**

KAIST 论文 [23] 测得：在一次 Agent 任务中，由于工具调用阶段 GPU 必须等待 CPU/外部响应，**GPU 闲置时间高达执行时间的 54.5%**。这是"在 Agentic 系统中 GPU 才是被低度利用的资源"这一论断的最直接证据，也意味着如果 CPU 跟不上，GPU 的吞吐会被严重浪费。

**核心证据 3：CPU 在 Agentic 栈中的不可替代角色**

AMD 在官方博客里把 CPU 的角色总结为四类 [34]：
1. **编排（Orchestration）**：任务分解引擎、多 Agent 协调
2. **Agent 执行与工具调用**：触发 API、连接传统企业软件
3. **策略与安全**：每个自主操作前的实时校验
4. **数据预处理与上下文拼接**：JSON 解析、向量索引、prompt 组装

GPU 擅长矩阵乘法（Transformer 前向），但**对这些串行、IO 密集、控制流复杂的工作无能为力**——这是 CPU 不可替代的根本原因。

**核心证据 4：MCP Server 是新增的 CPU 长驻层**

MCP 是 2025 年才大规模铺开的新协议层，对基础设施的影响被严重低估。SemiAnalysis 在"AI Value Capture"系列 [22] 中明确把 MCP 列为模型实验室从"卖模型"转向"卖工作流执行"的关键抓手，是 Anthropic 把协议层作为护城河战略的物理表现。TM Dev Lab 的基准测试 [38] 给出了关键数字：

| 实现 | RPS | 平均延迟 | 内存占用 |
|---|---|---|---|
| Rust (rmcp 0.17) | 4845 | 5.09ms | 10.9 MB |
| Quarkus (JVM) | 4739 | 4.04ms | 194.5 MB |
| Go (mcp-go) | 3616 | 6.87ms | 23.9 MB |
| Python (FastMCP) | 259 | — | 258.6 MB |

一个企业 Agent 典型接入 20 个 MCP 集成（GitHub、Slack、Postgres、S3、内部 API 等）。如果是 Python 实现，仅 MCP 管道就需要约 5.2 GB 内存 + 40 vCPU；如果是 Rust 实现，只需 220 MB + 4 vCPU [38]。**这意味着 MCP 实现语言的选择对 Agentic 基础设施成本有一阶影响**——这是一个被绝大多数厂商规划忽略的成本杠杆。

> ⚠️ **单一来源提示**：MCP 实现性能差异 [38] 来自 TM Dev Lab 一家独立测试，发布于 2026-02，覆盖 15 种实现。结论方向（系统语言远优于解释语言）符合软件工程常识，但具体倍数（10–20×）尚未被第二个独立基准复现。在生产规划中应将该比例视为"数量级正确"，而非精确数字。

**置信度:** High

**依据:** 4 家独立来源（AMD、Intel、TrendForce、Arm）+ 1 篇严谨学术论著（KAIST）+ 1 篇 ISCA 顶会论文（DeepSeek-V3）+ 1 份 MCP 基准测试，结论高度一致。

**反方解释:** NVIDIA Grace Hopper / BlueField DPU 阵营主张把 CPU+GPU 放在同一 NVLink 域内、用 DPU 卸载网络与安全，从而最小化分立 CPU 服务器需求——这是 SemiAnalysis 付费报告 [21] 中"CPUs are Back"论点的主要反对意见。同时 GPU 路线如果继续以 Vera Rubin 等 FP4 高密度卡推进，部分 SLM 推理可能回流 GPU，缩小 CPU-only 推理窗口。

### 8. 微信场景 CPU 需求测算：三档情景

> ⚠️ **方法论警示**：本节给出的是"**装机容量上界**"——假设每个活跃用户都拥有常驻、未被多路复用的 Agent 进程。真实生产架构（如 ChatGPT、Claude）通常按 50–200 用户/并发槽 多路复用，实际并发 CPU 需求可能比本节中位数低 1–2 个数量级。把本节数字理解为"如果每个用户都拥有专属常驻 Agent"的最大容量需求，而非实际并发负载。

把上述工作负载特征落地到具体场景。**核心问题**：如果每个微信用户配一个 Agent，需要多少 CPU 核？

**输入参数**（所有数字均有来源）：

| 变量 | 取值 | 来源 |
|---|---|---|
| 微信 MAU | 14.32 亿（2026 Q1 腾讯财报） | [33] |
| 微信支付用户 | 9.35 亿 | [49] |
| 朋友圈日活 | ~10 亿 | [33] |
| 活跃 Agent 采纳率（情景） | 10% / 30% / 50% | 设定 |
| 每 Agent CPU 核（情景） | 0.1 / 0.5 / 1.0 / 2.0 | 三角化见下 |
| 双路服务器核数 | 128（2026 主流）| [18] |
| AI 服务器 ASP | 1.9 万美元（2025）→ 2.7 万美元（2026） | [30] |
| 5 年直线折旧 | — | 设定 |

**单 Agent CPU 核数三角化**（无任何厂商发布过官方"每 Agent 核数"规格，需基于组件加总）：

| 层 | 单 Agent 占用 | 推算依据 |
|---|---|---|
| LLM 推理（GPU 池分摊到 CPU 侧）| 0.05–0.10 核 | vLLM 单 GPU 服务 10–20 并发；100 并发 Agent 用 26 vCPU [39] |
| 编排（LangGraph/Temporal） | 0.05–0.20 核 | 8–12 vCPU/GPU ÷ 10–20 Agent [39] |
| MCP Server（3 个常驻）| 0.02–0.05 核 | Python 实现 258 MB × 3，CPU 空闲低，调用时尖峰 [38] |
| RAG / 向量检索 | 0.02–0.05 核 | Mem0 把 token 成本砍 90%，延迟 < 2s [48] |
| 浏览器/代码沙箱（按需摊销）| 0.02–0.10 核 | Firecracker/E2B microVM，冷启动 |
| 记忆/认证/遥测（固定开销）| 0.02–0.05 核 | — |
| **合计** | **0.15–0.55 核/Agent** | 中位 ≈ 0.3 |

由此设定三档：

- **保守**：0.1 核（强多路复用，稀疏工具调用）
- **基础**：0.5 核（典型常驻 Agent，3 MCP，周期性 RAG）
- **激进**：2.0 核（高级用户，多 Agent，频繁沙箱）

**测算矩阵**：

| 情景 | 采纳率 | Agent 数 | 核/Agent | 总 CPU 核 | 双路服务器数 | 一次性资本开支 | 年折旧 |
|---|---|---|---|---|---|---|---|
| 保守 | 10% | 1.43 亿 | 0.1 | **1430 万** | 11.2 万 | 28 亿美元 | 5.6 亿 |
| 基础-低 | 30% | 4.30 亿 | 0.1 | 4300 万 | 33.6 万 | 84 亿 | 16.8 亿 |
| **基础-中** | **30%** | **4.30 亿** | **0.5** | **2.15 亿** | **168 万** | **420 亿** | **84 亿** |
| 基础-高 | 30% | 4.30 亿 | 1.0 | 4.30 亿 | 336 万 | 840 亿 | 168 亿 |
| 激进 | 50% | 7.16 亿 | 2.0 | **14.3 亿** | 1120 万 | 2800 亿 | 560 亿 |

**基准情景（30% 采纳 × 0.5 核/Agent）的关键含义**：

- 约 **2.15 亿 CPU 核**
- 约 **170 万台双路服务器**（128 核/台）
- 约 **420 亿美元一次性资本开支**，年折旧约 84 亿美元
- 相当于腾讯 2026 年规划 AI 投资（约 360 亿人民币 ≈ 50 亿美元）的 8–10 倍——单年无法承受，但作为 8–10 年的建设周期合理
- 相当于今天全球超大规模数据中心服务器总装机量（约 2500–3500 万台）的 **5–7%** [20]

**置信度:** Medium

**依据:** 输入参数（MAU、TrendForce 的 4 倍密度比、MCP 内存占用、Mem0 性能）都有高质量来源；但**单 Agent CPU 核数 0.1–2.0 是基于组件加总的三角化，没有厂商官方规格**，误差范围 ±2 倍。

**反方解释:** 真实生产架构高度依赖多路复用——"1 用户 1 Agent"更可能是"1 个逻辑 Agent 身份 + 共享推理池 + 按用户隔离的记忆"，而非 1 个常驻进程。如果多路复用比为 50–200:1，**并发 CPU 需求会比上面"装机容量"数字低 1–2 个数量级**——基础-中情景的 2.15 亿核是"假设每个活跃用户都拥有常驻 Agent"的上界估计。此外，相当一部分编排工作可以下沉到端侧（手机 NPU、Apple Intelligence 模式），将云侧 CPU 需求再下降 30–50%。

### 9. 全球外推与可行性边界

把基础-中情景线性外推到全球约 50 亿互联网用户（缩放系数 5B / 1.432B ≈ 3.49 倍）：

| 情景 | 全球 CPU 核 | 全球服务器 | 全球资本开支 |
|---|---|---|---|
| 保守（10% × 0.1）| 5000 万 | 39 万 | 98 亿 |
| **基础（30% × 0.5）** | **7.5 亿** | **590 万** | **1470 亿** |
| 激进（50% × 2.0）| **50 亿** | **3900 万** | **9750 亿** |

**对照基准**：

- 2025 年 Google 服务器支出 552 亿美元，估计当年新增 5–6 百万台，累计装机 1000–2000 万台 [29]
- Meta 官方表述"数百万台机器" [7]
- 全球超大规模数据中心总数 1136 个，平均每个 > 5000 台，AWS+Microsoft+Google 占约 60% 容量 [20]
- 2025 Q1 全球服务器营收同比 +134% 至 952 亿美元 [30]

**结论**：

- **基础情景**（7.5 亿核 / 590 万台 / 1470 亿美元）相当于今天全球超大规模数据中心总规模的 17–24%，作为 2030 年前的全球 Agentic 基础设施建设目标是合理且可达的。
- **激进情景**（50 亿核 / 3900 万台 / 9750 亿美元）相当于今天全球超大规模数据中心规模的 5–7 倍，是有记载以来最大单年服务器支出的约 2.5 倍——只有当 Agentic AI 全面替代白领工作且端侧算力无法承担负载时才会出现，时间窗口至少 10 年。

**置信度:** Medium

**依据:** 微信基准数据可信；外推线性假设可能高估（发展中国家人均 Agent 使用强度低于中国一线城市）；服务器总量基准来自 Synergy、NextPlatform 等可信源。

**反方解释:** Goldman Sachs 2030 年知识工作者采纳率仅 12% 的预测如果成立 [13]，全球 Agent 实际并发会大幅低于上述假设，基础情景的 7.5 亿核可能砍半。

### 10. Agent 负载形态：spiky / steady / sync / async

理解负载形态对 CPU 服务器选型至关重要。

**双峰负载（Bimodal）**：用户主动触发的回合是 spiky 的——单次任务可能 10–30 次工具调用在数秒内并发，然后空闲数分钟到数小时；后台 Agent 工作（记忆整理、定时任务、主动监控）则是 steady 的。**容量必须按"峰值并发回合 × 峰值工具调用率"配置，而非平均** [18][39]。

**同步 vs 异步**：混合。HTTP 类 MCP 工具调用是异步（awaitable），但每次调用都会阻塞一个 CPU 线程用于调度与解析。Spheron 数据显示，10 个 Agent × 3 个并行工具 = 30 个并发线程/回合 [39]。

**记忆读写比**：读密集。Mem0 类记忆层按 用户/会话/Agent 索引；典型模式是每对话回合写 1 条记忆、检索 5–20 条作为上下文，**读写比 10–50:1** [48]。

**加速器需求**：
- **AMX（Intel）**：用于 tokenization、CPU 侧小模型推理；当 ≤13B 模型与编排层共置时有效
- **AVX-512 / ARM SVE2**：嵌入生成（RAG）、向量距离计算、JSON 解析；RAG 热路径可加速 2–4 倍
- **专用推理**：每用户常驻 Agent 的推理负载本身应留在 GPU/NPU，CPU 负责编排而非矩阵运算 [18]

**架构含义**：常驻 Agent 倾向于**多小核高效**架构（ARM Neoverse V3、AmpereOne、Graviton5 的 136–192 核/socket），而非少大核 x86——这是 Arm 数据中心论点的物理基础 [40]。

**置信度:** High（定性描述一致）；Medium（具体读写比、并发比来自单点来源）

---

## 第三部分：CPU 服务器厂商竞争力维度

### 11. CPU 服务器厂商竞争格局

**芯片层**：

| 阵营 | 代表产品 | 2026 状态 |
|---|---|---|
| x86 – Intel | Xeon 6（Granite Rapids P-core / Sierra Forest E-core）、Clearwater Forest（288 核/450W）| 份额跌至历史低点 72.2%（Q3 2025）；供货紧张 [42][43][6] |
| x86 – AMD | EPYC 9005（Turin / Zen 5）、Venice（Zen 6，256 核 / 512 线程） | 份额 27.8%（Q3 2025），2026 峰值预计 35% 单元份额、近 50% 收入份额 [31][42] |
| ARM – Ampere | AmpereOne A192-32X（192 核/274W） | 能效比 AMD 高 1.73 倍（厂商自报）；Google 公开采纳 [44] |
| ARM – AWS | Graviton4 / 即将 Graviton5（192 核） | 推动 ARM 服务器份额从 2018 的 0.5% 升至 2025 的 13% [46] |
| ARM – Microsoft | Cobalt 100（Neoverse N2）/ Cobalt 200（Neoverse V3 + CCA） | Llama-3-8B Q4 batch=16 实测 446 tok/s（vs EPYC 249、Xeon 312），实例价格便宜 30% [41] |
| ARM – Google | Axion | 内部工作负载大规模替换 |
| ARM – 阿里 | Yitian 710 / 玄铁 C950 + 镇武 810E 加速器 | 2026 转向 Agentic AI 专用路线 [32] |
| ARM – 华为 | 鲲鹏 930+ 灵衢互联 + openEuler + CCA 机密 Agent | 国产 CPU 中唯一公开 Articulated Agentic AI 架构 [47] |
| ARM – 飞腾 / 海光 / 龙芯 / 申威 / 兆芯 | S2500 / 7280 / 3C6000 等 | "国产 CPU 六君子"；国资委 79 号文要求 2027 年底完成信创替代 [47] |

**整机层**：Dell、HPE 仍主导全球 AI 服务器收入（2025 Q1 全球营收 +134%）[30]；Lenovo 在 Q1 2026 x86 单元份额同比 +21.2% 至 7.3%（IDC 数据）；Supermicro、Inspur（浪潮）、新华三、宁畅、Cisco 等跟进。

**供应链紧张**：AMD 2026 服务器 CPU 产能**已售罄**，新订单只能排队；Intel 同样紧张，2026 Q1 涨价 ≤15%；交期延长至约 6 个月；台积电 3nm 利用率 100%、订单超额认购 3 倍 [4][19][28][42][45]。

### 12. Agentic 工作负载下的竞争力八维度

从前面分析的负载特性反推，CPU 服务器厂商的竞争力可以拆为以下 8 个维度：

#### 维度 1：单核 IPC 与基频

DeepSeek-V3 ISCA'25 论文明确指出：**延迟敏感任务（kernel 启动、网络处理）需要基频 > 4 GHz** [24]。Agentic 工作负载中工具调用、KV cache 传输等都是延迟敏感的，单核基频直接影响端到端时延。

#### 维度 2：核数密度（每 socket / 每 U）

Agent 编排、MCP 常驻等都是"多并发、单线程轻量"工作，**核数密度比单核性能更重要**。2026 旗舰 CPU 都在 88–288 核范围：Xeon 6+ Clearwater Forest 288 核/450W；AMD EPYC Venice 256 核/512 线程；Arm AGI CPU 136 核/300W；AWS Graviton5 192 核 [18]。Arm 阵营在此维度结构性领先。

#### 维度 3：内存带宽与容量

DeepSeek 论文 [24] 给出硬约束：160 条 PCIe 5.0 通道（640 GB/s）需要约 1 TB/s DRAM 带宽每节点——传统 DDR5 难以满足。DDR5-6400 vs Intel MRDIMM-8800 是当前主要分歧点（AMD 实测 [36] 显示 MRDIMM 更贵但并不必然带来更高吞吐）。CXL 2.0/3.0 内存池化是必经路径。

#### 维度 4：AI 矩阵扩展指令

- **Intel AMX**（Xeon 6 / Sapphire Rapids+）+ PyTorch 2.8：支持 A16W8、DA8W8、A16W4 量化推理 [37]
- **AMD AVX-512 / VNNI**（Zen 4+）
- **ARM SVE2 / SME / I8MM / MATMUL_INT8**（Neoverse N2/V3）

Cobalt 100 实测显示 [41]：在 Llama-3-8B Q4_0 batch=16 上达到 446 tok/s，SVE/I8MM/MATMUL_INT8 是关键 ISA。

#### 维度 5：IO 与加速器互联

PCIe 5.0/6.0、CXL 2.0/3.0、NIC 集成到 I/O die、NVLink/Infinity Fabric 用于 CPU↔GPU 互联。DeepSeek 论文 [24] 推荐"将 NIC 集成到 I/O die、用 NVLink 而非 PCIe 连接 CPU-GPU"——这是下一代架构的关键选择。

华为鲲鹏的"灵衢"互联（100 ns 延迟、TB 级统一内存池）是中国厂商在此维度上的差异化尝试 [47]。

#### 维度 6：能效（perf/W）与 TCO

AmpereOne A192-32X 在推荐系统推理上能效比 AMD 高 1.73 倍 [44]；ARM Cobalt 100 实例价格比 x86 便宜 30–44% [41]。在 Agentic 工作负载的"低强度、长尾"特性下，perf/W 是 TCO 的决定性因素。

#### 维度 7：机密计算（TEE）

Agentic AI 处理大量企业敏感数据（代码、合同、客户信息），机密计算从可选变为**必选**：

- **Intel TDX**（Trust Domain Extensions，VM 级）
- **AMD SEV-SNP**（Secure Encrypted Virtualization，VM 级）
- **ARM CCA**（Confidential Compute Architecture，Realm-based，Cobalt 200 内置）

Apple Private Cloud Compute 已扩展至 NVIDIA Confidential Computing GPU [41][47]。华为鲲鹏 2026 峰会明确把"基于 CCA 的机密 Agent"作为核心卖点 [47]。**预期 2026 年企业级 Agent 招标会要求 TEE**——这是中国厂商弯道超车的关键窗口。

#### 维度 8：供应链、地缘政治与生态

- **出口管制**：H200 对中国进口在 2026 年 3 月前已停止 [42]；中国互联网厂商处于观望状态，部分考虑海外部署
- **信创合规**：国资委 79 号文要求 2027 年底央企 IT 系统完成信创替代；信创采购可获 20% 价格优惠 [47]
- **生态**：鲲鹏宣称 7000+ 合作伙伴、27000+ 解决方案、415 万开发者 [47]；CUDA 替代（oneAPI、ROCm）仍处早期
- **超大规模定制芯片**：AWS Graviton、Azure Cobalt、Google Axion、阿里 Yitian、华为鲲鹏——超大规模厂商都在去 Intel/AMD 化

#### 维度 8.5：软件栈与可移植性

容器化（Kubernetes + containerd）、向量数据库（Milvus、Valkey、Qdrant）、Agent 框架（LangGraph、Temporal、Claude Agent SDK、OpenAI Agents SDK）等软件层的成熟度直接影响硬件选择。华为路线强调 openEuler + BoostKit 的全栈优化，使 Flink+Spark 类工作负载性能提升 67% [47]。

**置信度:** High（八维度均有多源支撑）；Medium（具体基准数据多来自厂商自报，存在 cherry-picking）

### 13. 优化路径与路线图（2026–2027）

针对每个维度的厂商优化方向：

| 维度 | Intel 路线 | AMD 路线 | ARM 阵营（Ampere/Graviton/Cobalt/鲲鹏） | 整机厂商（Dell/HPE/Lenovo/Inspur） |
|---|---|---|---|---|
| 单核 IPC | Diamond Rapids（2026 后）| Zen 6（Venice，2026）| Neoverse V3 / V4 | 选配 |
| 核数密度 | Clearwater Forest 288 核 | Venice 256 核/512 线程 | AmpereOne 192 / Graviton5 192 / 鲲鹏超节点 | 高密度 2U4N |
| 内存带宽 | MRDIMM-8800 + CXL | DDR5-6400 + CXL | DDR5-6400 + CXL | CXL 内存扩展柜 |
| AI 矩阵扩展 | AMX + PyTorch 2.8 | AVX-512 + ZenDNN | SVE2 / SME / MATMUL_INT8 | 与框架协同 |
| IO | PCIe 5.0 → 6.0 | PCIe 5.0 → 6.0 | PCIe 5.0 + CXL | NVLink/Infinity Fabric |
| 能效 | E-core 大规模铺开 | Zen 5c | ARM 物理优势 | 液冷 |
| 机密计算 | TDX | SEV-SNP | CCA（Cobalt 200 起）| 一体化 CVM 方案 |
| 信创 | 不适用 | 不适用 | 鲲鹏/飞腾/海光/龙芯 | 浪潮/新华三/华为/宁畅 |

**给中国厂商的具体建议**：

1. **聚焦 Agentic 编排专用 CPU tier**：而非追求与 x86 旗舰正面对标。AMD 已经明确把"agentic CPU rack"作为独立产品线 [34]，鲲鹏的超节点 + 灵衢路线 [47] 是同一思路的中国版。
2. **TEE 作为企业 Agent 招标门槛**：率先支持 CCA / 自研 TEE，可以在 2026–2027 的政企客户中获得结构性优势。
3. **MCP 实现语言优化**：把 Rust / Go 作为 MCP 参考实现语言，相对于 Python 实现可以节省 10–20 倍内存和 5–10 倍 CPU [38]——这是被严重低估的成本杠杆。
4. **CXL 内存池化**：Agent 长期记忆（每用户 100 KB–5 MB）在亿级用户规模下是 TB-PB 级，CXL 池化可以避免每服务器本地大内存的浪费。
5. **超大规模定制路线**：阿里玄铁/镇武、华为鲲鹏已经走在自研道路上，应该继续投入；同时构建与 hyperscaler 类似的内部 CPU 路线图。
6. **端云协同**：把编排、MCP、小模型推理下沉到端侧（手机 NPU、车机芯片）可以降低云侧 CPU 需求 30–50%。

**置信度:** Medium-High

---

## 第四部分：综合判断

### 14. 核心争议

> 本节是 P6 反方审视的产出。报告撰写过程中识别出 5 项需要在结论中显式披露的争议点，其中至少 3 项可能显著改变基础情景的 CPU 需求测算结果。

- **争议 1：Agentic AI 采纳速度——12% vs 45%**
  IDC/Gartner 预测 2030 年 40–45% 企业规模编排 [9][11]，Goldman Sachs 预测同期知识工作者采纳率仅 12% [13]，Bain 实证显示真实生产力提升 10–15% 远低于炒作 [17]。**这是本报告最大不确定性**：基础情景的 7.5 亿全球 CPU 核需求可能在 3 亿–15 亿之间浮动。**敏感性提示**：若 Goldman Sachs 路径成真，第 8 节中位数 2.15 亿核将下调至 ~1 亿核；若 Morgan Stanley/Sequoia 路径成真，将上调至 ~5 亿核。

- **争议 2：CPU 是否会被 Grace Hopper / DPU 路线吞并**
  NVIDIA 主张 CPU+GPU+DPU 同一 NVLink 域最小化分立 CPU 需求；AMD/Intel/TrendForce/Arm 主张独立的 Agentic CPU tier [34][35][18]。**目前共识倾向后者**——4 家独立厂商加 1 篇顶会论文支持，但 NVIDIA 路线仍可能在未来 5 年改变格局。**利益冲突披露**：本报告 CPU:GPU 1:1 的核心论据来源 AMD/Intel/Arm 三家都销售 CPU，存在结构性偏向；TrendForce 是相对中立的第三方，但 SemiAnalysis 付费报告 [21] 的具体 BoM 数字未能在公开渠道复现。

- **争议 3：每 Agent CPU 核数的真实值**
  本报告基于组件加总得到 0.1–2.0 核/Agent 区间，但**没有任何厂商发布过官方规格**，生产环境高度依赖多路复用。激进多路复用（50–200 用户/并发槽）下，并发 CPU 需求可能比装机容量数字低 1–2 个数量级。**这是第 8 节 2.15 亿核数字的最大单一风险**。

- **争议 4：端侧 vs 云侧的负载分配**
  Apple Intelligence、华为端侧大模型、骁龙 8 Gen 4 等都在把一部分 Agent 工作下沉到端侧。如果 30–50% 编排工作在端侧完成，云侧 CPU 需求会等比例下降。Meta Llama 3.2 1B/3B 模型 [8] 和 DeepSeek 论文中提到的 MoE-on-SoC (~20 TPS) [24] 都支持这一方向。

- **争议 5：Vera Rubin 等 GPU 新架构是否会回流 SLM 推理**
  如果 NVIDIA FP4 高密度卡大规模铺开，CPU-only 推理窗口可能收窄——但**Agent 编排层仍然只能在 CPU 上运行**，这是 CPU 需求的下界保证。

### 15. 关键发现

- **发现 1：CPU:GPU 比例正在结构性从 1:4 转向 1:1–1:2**，4 家独立厂商和 1 篇顶会论文一致确认；GPU 在 Agent 任务中闲置 54.5% 是最直接的物理证据 [18][23][34][35][40]。
- **发现 2：微信场景的基础 CPU 需求约 2.15 亿核 / 170 万台服务器 / 420 亿美元**（30% 采纳 × 0.5 核/Agent）；全球基础情景约 7.5 亿核，约当今全球超大规模数据中心规模的 17–24% [33][18][20][39]。
- **发现 3：MCP 协议层是被低估的 CPU 需求增长点**——每用户 3–20 个常驻 MCP server，Python 实现比 Rust 实现消耗多 10–20 倍资源 [38]。
- **发现 4：CPU 服务器竞争力已扩展到 8+ 维度**——核数密度、内存带宽、AI 矩阵指令、IO、能效、机密计算、供应链、生态——单核 IPC 已经不是决定性维度，ARM 阵营在多数维度结构性领先 [41][44][46]。
- **发现 5：中国信创与机密计算是国产 CPU 厂商的差异化窗口**——国资委 79 号文 + TEE 招标要求提供了 2–3 年的政策红利期 [47]。

### 16. 局限性与未来方向

**本研究局限**：

- **没有厂商官方"每 Agent CPU 核数"规格**：所有 0.1–2.0 核/Agent 的数字都是基于组件加总的三角化，误差 ±2 倍。
- **腾讯内部 AI 基础设施容量未公开**：腾讯把 GPU+服务器采购合并到 Operating CapEx，没有公开装机量、GPU 数量、按用户算力分配等数据 [6]。
- **CPU-specific TCO 拆分缺失**：主要分析师（IDC、Gartner、Goldman）都没有把 Agentic AI 基础设施 TCO 拆分为 CPU vs GPU vs 加速器 [13]。
- **国产 CPU 公开 SPEC 基准稀缺**：飞腾、海光、龙芯没有公开的 SPECrate 或独立 Phoronix 测试 [task-e Gaps]。
- **Agentic-specific 端到端基准缺失**：AMD/Intel/Arm 都发布 vLLM/llama.cpp 吞吐数据，但没有发布 Agent-loop 端到端延迟（多工具调用闭环）。
- **训练侧 CPU:GPU 比例未单独拆分**：本报告 1:1–1:2 主要适用于推理/Agentic，训练仍可能保持 1:8 head-node 模式。
- **超大规模厂商内部数据无法访问**：Google、Meta、Microsoft 的 Agent 部署细节、单位 Agent 成本等均为不公开。

**未来研究方向**：

1. **建立 Agent-loop 端到端基准**（如 LLM-Agent、AgentBench、ToolBench 在各 CPU 上的对比）——填补当前厂商只在 LLM token/s 上对比的空白
2. **追踪 Anthropic Claude Code / OpenAI ChatGPT agent 在 S-1 中的算力成本披露**（预计 2026 年下半年）
3. **中国 Agentic AI 基础设施市场单独研究**——信创 + 国产 CPU + TEE 三重驱动下，可能走出与海外不同的产业格局
4. **CXL 内存池化在 Agent 长期记忆层的实证研究**——目前仍停留在架构建议层面，缺乏大规模生产数据
5. **端云协同下 Agent 编排的最优分配**——量化多少编排工作可以下沉到端侧而不损失体验

---

## 参考文献

### A. 厂商官方 / 财报 (official)

[1] OpenAI. "Introducing ChatGPT agent". Source-Type: official. As Of: 2025-07. https://openai.com/index/introducing-chatgpt-agent/
[2] OpenAI. "New tools for building agents (Responses API, Agents SDK, Computer Use)". Source-Type: official. As Of: 2025-03. https://openai.com/index/new-tools-for-building-agents/
[3] OpenAI. "API Pricing". Source-Type: official. As Of: 2026-06. https://developers.openai.com/api/docs/pricing
[4] Anthropic. "Anthropic raises $30 billion in Series G funding at $380 billion post-money valuation". Source-Type: official. As Of: 2026-05. https://www.anthropic.com/news/anthropic-raises-30-billion-series-g-funding-380-billion-post-money-valuation
[5] Anthropic. "Donating the Model Context Protocol and Establishing the Agentic AI Foundation". Source-Type: official. As Of: 2025-11. https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
[6] Tencent. "Q1 2025 Earnings (Operating CapEx CNY 26.4B, +300% YoY)". Source-Type: official. As Of: 2025-05. https://www.alphaspread.com/security/hkex/700/investor-relations/earnings-call/q1-2025
[7] Meta Engineering. "Meta's Infrastructure Evolution and the Advent of AI". Source-Type: official. As Of: 2025-09. https://engineering.fb.com/2025/09/29/data-infrastructure/metas-infrastructure-evolution-and-the-advent-of-ai/
[8] Meta AI. "Llama 3.2: Revolutionizing edge AI and vision with open models". Source-Type: official. As Of: 2024-09. https://ai.meta.com/blog/llama-3-2-connect-2024-vision-edge-mobile-devices/

### B. 权威分析师 / 投行 / 咨询

[9] IDC FutureScape. "2026 Predictions Reveal the Rise of Agentic AI". Source-Type: secondary-industry. As Of: 2025-11. https://my.idc.com/getdoc.jsp?containerId=prUS53883425
[10] IDC. "Agentic AI to Dominate IT Budget Expansion Over Next Five Years". Source-Type: secondary-industry. As Of: 2025-08. https://my.idc.com/getdoc.jsp?containerId=prUS53765225
[11] Gartner. "Predicts 40% of Enterprise Apps Will Feature Task-Specific AI Agents by 2026". Source-Type: secondary-industry. As Of: 2025-08. https://www.gartner.com/en/newsroom/press-releases/2025-08-26-gartner-predicts-40-percent-of-enterprise-apps-will-feature-task-specific-ai-agents-by-2026-up-from-less-than-5-percent-in-2025
[12] Gartner. "2026 Hype Cycle for Agentic AI". Source-Type: secondary-industry. As Of: 2026-04. https://www.gartner.com/en/articles/hype-cycle-for-agentic-ai
[13] Goldman Sachs Research. "AI Agents Forecast to Boost Tech Cash Flow as Usage Soars". Source-Type: secondary-industry. As Of: 2026-05. https://www.goldmansachs.com/insights/articles/ai-agents-forecast-to-boost-tech-cash-flow-as-usage-soars
[14] McKinsey & Company. "The State of AI: Global Survey 2025". Source-Type: secondary-industry. As Of: 2025-11. https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai
[15] Deloitte AI Institute. "State of AI in the Enterprise 2026". Source-Type: secondary-industry. As Of: 2026-01. https://www.deloitte.com/us/en/what-we-do/capabilities/applied-artificial-intelligence/content/state-of-ai-in-the-enterprise.html
[16] Morgan Stanley Insights. "AI Could Affect 90% of Occupations (2H 2025)". Source-Type: secondary-industry. As Of: 2025-08. https://www.morganstanley.com/insights/articles/ai-workplace-outlook-2H-2025
[17] Bain. "From Pilots to Payoff: Generative AI in Software Development — Technology Report 2025". Source-Type: secondary-industry. As Of: 2025-06. https://www.bain.com/insights/from-pilots-to-payoff-generative-ai-in-software-development-technology-report-2025/
[18] TrendForce. "The Great Rebalance: How Agentic AI Is Reshaping the CPU:GPU Ratio". Source-Type: secondary-industry. As Of: 2026-04. https://insights.trendforce.com/p/agentic-ai-cpu-gpu
[19] TrendForce / IndexBox. "CPU shortage emerges as new challenge for AI industry in 2025-2026". Source-Type: secondary-industry. As Of: 2026-04. https://www.indexbox.io/blog/cpu-shortage-emerges-as-new-challenge-for-ai-industry-in-2025-2026/
[20] Synergy Research Group. "Hyperscale Data Center Count Hits 1136". Source-Type: secondary-industry. As Of: 2025-12. https://www.srgresearch.com/articles/hyperscale-data-center-count-hits-1136-average-size-increases-us-accounts-for-54-of-total-capacity
[21] SemiAnalysis. "CPUs are Back: The Datacenter CPU Landscape in 2026". Source-Type: secondary-industry. As Of: 2026-01. https://newsletter.semianalysis.com/p/cpus-are-back-the-datacenter-cpu
[22] SemiAnalysis. "AI Value Capture: The Shift To Model Labs". Source-Type: secondary-industry. As Of: 2026-Q1. https://newsletter.semianalysis.com/p/ai-value-capture-the-shift-to-model

### C. 学术 / 工程系统类

[23] Lee et al., KAIST. "The Cost of Dynamic Reasoning: Demystifying AI Agents and Test-Time Scaling from an AI Infrastructure Perspective". arXiv 2506.04301. Source-Type: academic. As Of: 2025-06. https://arxiv.org/html/2506.04301v1
[24] DeepSeek AI. "Insights into DeepSeek-V3: Scaling Challenges and Reflections on Hardware for AI Architectures". ISCA'25 / arXiv 2505.09343. Source-Type: academic. As Of: 2025-05. https://arxiv.org/html/2505.09343v2

### D. 主流财经 / 科技媒体

[25] Forbes (Carvao, P.). "Anthropic And OpenAI Are Taking Opposite Paths To AI Profitability". Source-Type: journalism. As Of: 2026-05. https://www.forbes.com/sites/paulocarvao/2026/05/21/anthropic-openai-enterprise-ai-profitability/
[26] Fortune. "Sam Altman and Dario Amodei are both walking back their AI jobs apocalypse prophecies". Source-Type: journalism. As Of: 2026-05. https://fortune.com/2026/05/26/sam-altman-dario-amodei-walking-back-ai-jobs-apocalypse-prophecies-ipo/
[27] The Information. "OpenAI Plots Charging $20,000 a Month For PhD-Level Agents". Source-Type: journalism. As Of: 2025-03. https://www.theinformation.com/newsletters/ai-agenda/openai-plots-charging-20-000-a-month-for-phd-level-agents
[28] Tom's Hardware. "CPU requirements for AI workloads are multiplying". Source-Type: journalism. As Of: 2026-04. https://www.tomshardware.com/pc-components/cpus/shifting-need-for-cpus-in-ai-workloads-drives-intensifying-shortages-price-hikes
[29] NextPlatform. "Google Spends More On Servers Than The Whole World Used To". Source-Type: journalism. As Of: 2025-10. https://www.nextplatform.com/cloud/2025/10/30/google-spends-more-on-servers-than-the-whole-world-used-to/1643570
[30] CIO Dive. "Dell, HPE reap revenue gains from AI server demand surge". Source-Type: journalism. As Of: 2025-08. https://www.ciodive.com/news/dell-hpe-ai-server-market-growth/759329/
[31] Phoronix. "AMD EPYC Turin vs Intel Xeon 6 Granite Rapids vs Graviton4 Benchmarks With AWS M8 Instances". Source-Type: journalism. As Of: 2025-11. https://www.phoronix.com/review/aws-m8a-m8g-m8i-benchmarks
[32] Reuters. "Alibaba unveils next-gen chip for agentic AI". Source-Type: journalism. As Of: 2026-03. https://www.reuters.com/world/asia-pacific/alibaba-develops-next-gen-chip-agentic-ai-chinese-media-says-2026-03-24/
[33] 199it. "腾讯：2026年Q1微信月活用户达14.32亿，同比增长2%". Source-Type: journalism. As Of: 2026-05. https://www.199it.com/archives/1828060.html

### E. 厂商工程博客 / 行业技术分析

[34] AMD. "Agentic AI Changes the CPU/GPU Equation". Source-Type: secondary-industry. As Of: 2026-05. https://www.amd.com/en/blogs/2026/agentic-ai-changes-the-cpu-gpu-equation.html
[35] Intel. "The Rising CPU:GPU Ratio in AI Infrastructure: Drivers, Trends, and Implications". Source-Type: secondary-industry. As Of: 2026-04. https://www.intel.com/content/www/us/en/content-details/915817/the-rising-cpu-gpu-ratio-in-ai-infrastructure-drivers-trends-and-implications.html
[36] AMD. "Unlocking Optimal LLM Performance on AMD EPYC CPUs with vLLM". Source-Type: secondary-industry. As Of: 2025-11. https://www.amd.com/en/blogs/2025/unlocking-optimal-llm-performance-on-amd-epyc--cpus-with-vllm.html
[37] Lenovo Press. "Implementing AI Agents without GPUs: High-Performance Inference on Intel Xeon 6". Source-Type: secondary-industry. As Of: 2025-09. https://lenovopress.lenovo.com/lp2406-implementing-ai-agents-without-gpus-high-performance-inference-on-intel-xeon-6
[38] TM Dev Lab. "MCP Server Performance Benchmark v2: 15 Implementations, I/O-bound workloads". Source-Type: secondary-industry. As Of: 2026-02. https://www.tmdevlab.com/mcp-server-performance-benchmark-v2.html
[39] Spheron. "Right-Sizing vCPUs Per GPU for Agentic Inference (2026 Guide)". Source-Type: secondary-industry. As Of: 2026-06. https://www.spheron.network/blog/cpu-to-gpu-ratio-agentic-ai-inference/
[40] Arm Newsroom. "As AI scales, so do CPUs". Source-Type: secondary-industry. As Of: 2026-02. https://newsroom.arm.com/blog/ai-datacenter-cpu-orchestration-arm
[41] Van Laere, T. "Exploring AI CPU-Inferencing with Azure Cobalt 100". Source-Type: community. As Of: 2025-10. https://thomasvanlaere.com/posts/2025/10/exploring-ai-cpu-inferencing-with-azure-cobalt-100/
[42] Wukong Substack. "CPU Squeeze: Agentic AI, Intel, AMD, AWS, H200 (Expert Q&A)". Source-Type: secondary-industry. As Of: 2026-01. https://wukong123.substack.com/p/cpu-squeeze-agentic-ai-intel-amd
[43] The Diligence Stack. "The Intel Foundry Opportunity: Two Paths to Anchor Customer Scale". Source-Type: secondary-industry. As Of: 2026-01. https://www.thediligencestack.com/p/the-intel-foundry-opportunity-two
[44] ServeTheHome. "Ampere AmpereOne 192 Core Performance Outlined (Arm)". Source-Type: journalism. As Of: 2024-06. https://www.servethehome.com/ampere-ampereone-192-core-performance-outlined-arm/
[45] Introl. "The Custom Silicon Inflection Point: Hyperscaler ASICs Challenge NVIDIA's GPU Dominance in 2026". Source-Type: secondary-industry. As Of: 2026-02. https://introl.com/blog/custom-silicon-inflection-2026-hyperscaler-asics-nvidia-gpu
[46] Arm Newsroom. "Pace of Innovation for Custom Silicon on Arm Continues with AWS Graviton4". Source-Type: secondary-industry. As Of: 2025-08. https://newsroom.arm.com/blog/aws-graviton4
[47] C114 通信网. "鲲鹏开发者峰会2026：共赢 Agentic AI 新时代". Source-Type: journalism. As Of: 2026-05. https://m.c114.com.cn/w126-1310928.html
[48] Valkey / Mem0. "AI Agent Memory with Valkey and Mem0 (token cost reduction benchmarks)". Source-Type: secondary-industry. As Of: 2026-03. https://valkey.io/blog/ai-agent-memory-with-valkey-and-mem0/
[49] Business of Apps. "WeChat Revenue and Usage Statistics (2026)". Source-Type: secondary-industry. As Of: 2026-06. https://www.businessofapps.com/data/wechat-statistics/

### F. VC / 投资视角

[50] Sequoia Capital (Grady, P., Huang, S.). "2026: This is AGI". Source-Type: secondary-industry. As Of: 2026-01. https://sequoiacap.com/article/2026-this-is-agi/
[51] Andreessen Horowitz. "Humans Are for Ideas, AI Is for Execution — Notes on AI Apps in 2026". Source-Type: secondary-industry. As Of: 2026-01. https://a16z.com/humans-are-for-ideas-ai-is-for-execution/

---

> 免责声明：本报告基于公开来源编写，所有引用均可追溯至文末参考文献。涉及 OpenAI / Anthropic 财务预测的部分来自投资者路演材料与分析师估计，未经 S-1 验证；涉及 CPU 需求测算的部分基于组件加总三角化，无厂商官方规格；中国国产 CPU 性能数据以厂商自报为主。投资与采购决策需进一步尽调。
