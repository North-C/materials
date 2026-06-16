# OpenAI 与 Anthropic Agentic AI 业务布局与演进报告

> 研究日期：2026-06-16  
> 研究对象：OpenAI、Anthropic  
> 研究范围：当前业务布局、当前开展业务、用户价值、未来业务演进、未来 Agent 用途  
> 资料口径：以厂商官方发布、官方文档和可信第三方研究为主；涉及未来判断处均为基于公开资料的分析推断。

## 摘要

OpenAI 与 Anthropic 都在把大模型从“回答问题的聊天框”推进为“能够理解上下文、调用工具、执行任务的 Agent 系统”。但两家公司的路径明显不同。

OpenAI 的核心路径是“以 ChatGPT 为统一入口，把 Agent 能力产品化、平台化和生态化”。ChatGPT agent 整合了 Operator 的网页操作能力、Deep Research 的深度研究能力和 ChatGPT 的对话能力；Codex 则面向软件工程任务；Responses API、Agents SDK 与 Apps SDK 面向开发者和第三方应用生态。

Anthropic 的核心路径是“以 Claude 为企业与开发者工作流底座，用 MCP、Claude Code、Skills、Connectors 和垂直产品嵌入企业场景”。Claude Code 是其当前最清晰的 Agent 商业化抓手；MCP 则承担连接企业数据、工具和 Agent 的协议层角色。

总体判断：OpenAI 更像在构建“面向全体用户的 Agent 超级入口和应用分发平台”；Anthropic 更像在构建“面向企业和开发者的 Agent 工作流基础设施”。未来 Agent 的主要用途将从信息问答扩展到任务执行、跨应用操作、软件工程自动化、企业流程自动化、个人助理和高价值垂直行业代理。

## 一、OpenAI

### 1. 当前业务布局

OpenAI 的 Agentic AI 布局可以分为四层。

| 层次 | 代表产品/能力 | 业务含义 |
|---|---|---|
| 用户入口层 | ChatGPT agent、Operator、Deep Research | 把 ChatGPT 从对话产品升级为任务执行入口。 |
| 专业任务层 | Codex、Deep Research | 面向软件工程、研究分析等高价值知识工作。 |
| 开发者平台层 | Responses API、Agents SDK、工具调用、MCP 连接能力 | 让开发者构建自己的 Agent 应用和工作流。 |
| 应用生态层 | Apps SDK、ChatGPT 内应用 | 让第三方服务在 ChatGPT 内被调用、展示和交易。 |

ChatGPT agent 是 OpenAI Agent 战略的核心产品形态。OpenAI 官方称其整合了 Operator、Deep Research 和 ChatGPT 的能力，可使用视觉浏览器、文本浏览器、终端和连接器，在用户授权下完成跨网页、跨工具的任务。

Codex 则是 OpenAI 在软件工程场景中的 Agent 产品。它可以在云端沙箱中读取代码、修改文件、运行测试、解释代码、修复 bug，并把结果返回给用户审阅。

开发者侧，OpenAI 将 Responses API 与 Agents SDK 作为构建 Agent 应用的基础组件。Responses API 面向状态化、多模态、工具调用型交互；Agents SDK 面向更复杂的多 Agent 编排、工具交接、状态追踪和可观测性。

### 2. 当前开展的业务

OpenAI 当前 Agent 业务主要包括以下几类。

| 业务方向 | 当前形态 | 典型任务 |
|---|---|---|
| 通用任务 Agent | ChatGPT agent | 日程简报、网页操作、购物比较、旅行规划、表格更新、报告生成。 |
| 网页操作 Agent | Operator / ChatGPT agent | 点击网页、填表、搜索、下单、预约、跨站点执行任务。 |
| 深度研究 Agent | Deep Research | 多轮搜索、读取网页/PDF/图片、综合资料、生成带引用研究报告。 |
| 软件工程 Agent | Codex | 写功能、修 bug、跑测试、解释代码、生成 PR。 |
| API 与工具平台 | Responses API、Agents SDK | 构建企业内部 Agent、客服 Agent、数据分析 Agent、工作流 Agent。 |
| 应用生态 | Apps SDK | 让第三方应用接入 ChatGPT，提供可交互界面和工具能力。 |

从业务性质看，OpenAI 当前的重点不是单一 Agent 产品，而是把 Agent 能力嵌入 ChatGPT 入口、开发者 API 和第三方应用生态，形成“用户入口 + 专业 Agent + 开发平台 + 应用生态”的组合。

### 3. 用户价值

OpenAI 给用户带来的价值主要体现在三方面。

第一，降低任务完成成本。用户不再只是向模型提问，而是可以把任务委托给 Agent。对个人用户而言，这意味着搜索、整理、订票、购物、规划等任务被压缩到一次自然语言委托。对知识工作者而言，资料收集、表格处理、报告生成、PPT 初稿等工作可以由 Agent 先完成。

第二，提高知识工作的交付速度。Deep Research 和 ChatGPT agent 能够进行多步检索、阅读、分析和组织，适用于金融研究、政策分析、学术背景调研、竞品分析等场景。其价值不只是“回答”，而是“带出处、带结构、可追溯地生成研究结果”。

第三，提高软件工程效率。Codex 将 Agent 引入代码库上下文，可以并行处理多个开发任务，适合修复简单 bug、补测试、解释模块、重构局部代码、生成 PR 草稿。对工程团队来说，它的价值在于把大量零散、重复、上下文依赖强的工程任务后台化。

从商业价值看，OpenAI 正在把 ChatGPT 的消费入口优势转化为任务执行入口优势。Agent 任务天然消耗更多推理、工具调用和沙箱资源，因此也为更高阶订阅、企业版和 API 用量创造了付费空间。

### 4. 未来业务的演进

OpenAI 的未来演进大概率沿四条路径展开。

第一，ChatGPT 从“聊天入口”演进为“任务入口”。ChatGPT agent 会逐渐成为高级用户和企业用户的默认工作模式，用户将越来越多地用自然语言发起任务，而不是直接打开多个网站或软件。

第二，Agent 能力从单点工具走向统一平台。Operator、Deep Research、Codex 等能力会继续被整合到 ChatGPT 和 API 平台中，形成统一的模型、工具、状态、权限和审计体系。

第三，ChatGPT 可能成为应用分发和服务交易入口。Apps SDK 使第三方应用能够在 ChatGPT 中提供界面和工具能力。若这一生态成熟，ChatGPT 将不只是 AI 助手，而可能成为用户调用服务、完成交易和管理工作的入口。

第四，Codex 会从“代码助手”演进为“软件工程 Agent”。未来它可能承担更多长任务，例如持续修复 CI、自动补测试、迁移框架、升级依赖、进行安全修复、生成审查意见和维护文档。

### 5. 未来 Agent 的用途

OpenAI 体系下的未来 Agent 用途可以分为六类。

| 用途 | 说明 |
|---|---|
| 个人事务代理 | 管理邮件、日程、旅行、购物、订阅、提醒和网页操作。 |
| 研究分析代理 | 自动完成资料检索、证据整理、报告生成和结论追踪。 |
| 办公自动化代理 | 生成文档、表格、幻灯片、会议纪要、项目更新和经营分析。 |
| 软件工程代理 | 写代码、跑测试、修 bug、提交 PR、迁移代码、做代码审查。 |
| 企业流程代理 | 连接 CRM、ERP、知识库、工单系统和审批系统，完成跨系统任务。 |
| 应用与交易代理 | 在 ChatGPT 内调用第三方应用，完成订购、预订、支付前确认等任务。 |

OpenAI 的战略重点可以概括为：让 ChatGPT 代表用户完成跨网站、跨应用、跨工具的任务，并把这种能力开放给开发者和第三方服务商。

## 二、Anthropic

### 1. 当前业务布局

Anthropic 的 Agentic AI 布局更偏企业、开发者和工作流基础设施。

| 层次 | 代表产品/能力 | 业务含义 |
|---|---|---|
| 模型能力层 | Claude 3.5/4 系列、computer use、extended thinking | 强化代码、推理、工具使用和长任务执行能力。 |
| 协议与连接层 | Model Context Protocol, MCP | 用统一协议连接企业数据源、工具和 Agent。 |
| 开发者产品层 | Claude Code、Claude Agent SDK | 把 Claude 嵌入终端、IDE、代码库和工程流程。 |
| 企业工作流层 | Claude Cowork、Claude for Slack、Claude for Microsoft 365、Claude for Chrome | 将 Agent 嵌入办公、浏览器和协作工具。 |
| 垂直场景层 | Claude Security、Skills、Connectors、Plugins | 面向安全、合规、企业知识和角色化任务。 |

Anthropic 最重要的差异化资产是 MCP。MCP 的作用是让 Agent 用标准方式连接外部系统，避免每个模型或每个应用都为每个数据源单独开发连接器。这使 Anthropic 不只是模型供应商，也在争夺 Agent 生态的协议层位置。

Claude Code 是 Anthropic 当前最成熟的 Agent 产品。它嵌入终端、IDE、Web、桌面和 Slack，能够理解代码库、修改文件、运行命令、执行测试、生成提交或 PR。

Claude Cowork、Claude for Chrome、Claude for Microsoft 365 和 Claude for Slack 则说明 Anthropic 正把 Agent 从开发者场景扩展到更广泛的企业知识工作场景。

### 2. 当前开展的业务

Anthropic 当前 Agent 业务主要包括以下几类。

| 业务方向 | 当前形态 | 典型任务 |
|---|---|---|
| 软件工程 Agent | Claude Code | 读代码、改多文件、跑命令、写测试、开 PR、解释系统。 |
| 浏览器/电脑操作 Agent | Computer use、Claude for Chrome | 浏览网页、点击、输入、抓取信息、完成网页任务。 |
| 企业知识工作 Agent | Claude Cowork | 整理文件、生成报告、准备周报、分析资料、处理跨工具上下文。 |
| 协作工具 Agent | Claude for Slack、Microsoft 365 | 在消息、文档、表格、邮件和幻灯片中辅助工作。 |
| 安全 Agent | Claude Security | 扫描代码库、验证漏洞、提出修复建议、辅助安全团队。 |
| 企业能力封装 | Skills、Connectors、Plugins | 将企业流程、格式、知识和脚本封装为可复用能力。 |
| 开发者生态 | MCP、Claude Agent SDK | 帮助开发者构建连接企业工具和数据的 Agent。 |

Anthropic 当前业务的关键特点是“嵌入现有工作现场”。它不是只让用户打开一个聊天框，而是把 Claude 放进终端、IDE、浏览器、Slack、Microsoft 365 和企业系统中。

### 3. 用户价值

Anthropic 给用户带来的价值主要体现在四方面。

第一，提升开发者生产力。Claude Code 可以直接工作在真实代码库中，理解上下文并执行命令。对开发者来说，它降低了理解陌生代码、修改多文件、补测试和定位 bug 的成本。

第二，降低企业工具集成成本。MCP 为 Agent 连接数据源和工具提供统一协议，使企业可以用更标准化的方式接入 GitHub、Slack、数据库、文件系统、浏览器和内部系统。其价值类似 Agent 时代的“USB-C 接口”：统一连接方式，降低生态碎片化。

第三，沉淀组织知识和流程。Skills、Plugins 和 Connectors 可以把企业内部的格式、流程、脚本和专业知识封装起来，让 Agent 输出更稳定、更符合组织规范。

第四，提高高价值垂直任务效率。Claude Security 表明 Anthropic 正在把 Agent 用于安全漏洞分析、验证和修复建议。类似能力也可扩展到法律、金融、医疗、合规、审计等专业场景。

从商业价值看，Anthropic 的优势在于企业和开发者场景的高付费意愿。相比个人助手，企业软件工程、安全、合规和办公自动化更容易形成高客单价、可度量 ROI 和长期合同。

### 4. 未来业务的演进

Anthropic 的未来演进大概率沿五条路径展开。

第一，MCP 会继续成为其生态抓手。随着越来越多工具、数据库和 SaaS 服务支持 MCP，Claude 将更容易成为企业 Agent 的默认执行层之一。

第二，Claude Code 会从个人开发助手演进为工程团队 Agent。未来它可能承担代码迁移、测试生成、CI 修复、安全补丁、依赖升级和多 Agent 协同开发任务。

第三，Skills 和 Plugins 会使 Claude 更角色化。企业可以把销售、财务、法务、安全、运营等岗位流程封装为专用 Skill，使 Claude 从通用助手演进为岗位专家。

第四，Claude Cowork、Chrome、Slack 和 Microsoft 365 会把 Agent 扩展到企业日常工作。Anthropic 的重点不是另造一个工作入口，而是嵌入用户已经使用的工具。

第五，Claude Security 代表其垂直行业路径。安全场景对上下文理解、权限控制、审计、人类审批和可追溯性要求高，适合 Anthropic 强调安全、可靠和企业治理的品牌定位。

### 5. 未来 Agent 的用途

Anthropic 体系下的未来 Agent 用途可以分为七类。

| 用途 | 说明 |
|---|---|
| 软件工程代理 | 长时间理解代码库、执行开发任务、管理测试和 PR。 |
| 企业知识代理 | 查询、整理、生成和更新组织内部知识资产。 |
| 办公协作代理 | 在 Slack、邮件、文档、表格和会议中处理信息流。 |
| 浏览器任务代理 | 通过网页执行检索、录入、数据收集和后台任务。 |
| 安全代理 | 发现漏洞、验证风险、生成补丁、辅助安全运营。 |
| 角色化岗位代理 | 面向销售、财务、法务、客服、运营等岗位执行标准流程。 |
| 企业系统代理 | 通过 MCP 接入数据库、代码库、工单、CRM、ERP 和内部工具。 |

Anthropic 的战略重点可以概括为：让 Claude 成为企业工具链中的可信执行者，并用 MCP、Skills 和企业集成降低 Agent 落地成本。

## 三、OpenAI 与 Anthropic 对比

| 维度 | OpenAI | Anthropic |
|---|---|---|
| 战略定位 | 面向全体用户的 Agent 超级入口和开发平台。 | 面向企业和开发者的 Agent 工作流基础设施。 |
| 核心入口 | ChatGPT。 | Claude、Claude Code、企业工具集成。 |
| 成熟场景 | 通用任务、深度研究、网页操作、软件工程。 | 软件工程、企业知识工作、MCP 集成、安全和办公协作。 |
| 生态抓手 | ChatGPT、Apps SDK、Agents SDK、Responses API。 | MCP、Claude Code、Skills、Connectors、Plugins。 |
| 商业化路径 | 消费订阅、企业版、API、第三方应用生态。 | 企业订阅、开发者工具、API、托管 Agent 与垂直行业产品。 |
| 优势 | 用户规模、产品入口强、任务覆盖广、生态分发潜力大。 | 企业场景深入、开发者心智强、协议层布局领先、治理叙事清晰。 |
| 主要挑战 | 安全、隐私、误操作、任务可靠性、成本控制。 | 企业权限治理、集成复杂度、长任务可靠性、生态扩张速度。 |

## 四、综合判断

从当前业务布局看，OpenAI 与 Anthropic 都已经把 Agentic AI 作为下一阶段核心方向，但两者的商业逻辑不同。

OpenAI 的优势是入口和规模。ChatGPT 已经拥有巨大的用户心智，适合把 Agent 能力推向个人用户、知识工作者、中小企业和开发者。它的未来更像一个“AI 原生任务平台”：用户在 ChatGPT 中发起任务，ChatGPT 调用模型、工具、第三方应用和浏览器完成交付。

Anthropic 的优势是企业工作流和开发者场景。Claude Code、MCP、Skills 和企业连接器使其更容易进入真实工作流程。它的未来更像一个“企业 Agent 运行时”：企业把数据、工具、权限和流程连接到 Claude，让 Agent 在可治理的边界内完成任务。

从用户价值看，Agent 的核心变化不是回答更长，而是执行更多。未来高价值 Agent 将具备五个能力：理解长期上下文、调用外部工具、跨系统执行动作、接受人类审批、产生可追溯结果。

从用途看，未来 Agent 会优先在 ROI 清晰、任务重复、上下文丰富、流程可验证的场景中落地。软件工程、研究分析、客服、办公自动化、安全、合规、销售运营和企业内部知识管理会是最早规模化的领域。

因此，可以形成如下判断：

1. Agentic AI 的商业化会先在企业和专业工作中成熟，再向个人生活助手扩散。
2. OpenAI 会继续强化 ChatGPT 的任务入口和应用生态属性。
3. Anthropic 会继续强化 Claude 的企业工作流、开发者工具和协议生态属性。
4. Agent 的长期竞争不只取决于模型能力，也取决于工具生态、权限治理、任务可靠性、可观测性和成本结构。
5. 真正有价值的 Agent 不是“会聊天的模型”，而是“可控、可审计、可集成、能稳定完成任务的执行系统”。

## 参考资料

1. OpenAI, Introducing ChatGPT agent: <https://openai.com/index/introducing-chatgpt-agent/>
2. OpenAI, Introducing Operator: <https://openai.com/index/introducing-operator/>
3. OpenAI, Introducing deep research: <https://openai.com/index/introducing-deep-research/>
4. OpenAI, Introducing Codex: <https://openai.com/index/introducing-codex/>
5. OpenAI Platform Docs, Agents: <https://platform.openai.com/docs/guides/agents>
6. OpenAI Developers, Apps SDK: <https://developers.openai.com/apps-sdk>
7. Anthropic, Claude 3.5 models and computer use: <https://www.anthropic.com/news/3-5-models-and-computer-use>
8. Anthropic, Introducing the Model Context Protocol: <https://www.anthropic.com/news/model-context-protocol>
9. Anthropic, Claude 4: <https://www.anthropic.com/news/claude-4>
10. Claude Docs, Claude Code overview: <https://docs.claude.com/en/docs/claude-code/overview>
11. Claude, Claude Code product page: <https://claude.com/product/claude-code>
12. Claude, Claude Cowork: <https://claude.com/product/cowork>
13. Claude, Claude for Chrome: <https://claude.com/claude-for-chrome>
14. Claude, Claude for Slack: <https://claude.com/claude-for-slack>
15. Claude, Claude for Microsoft 365: <https://claude.com/claude-for-microsoft-365>
16. Claude, Claude Security: <https://claude.com/product/claude-security>
17. Claude, Skills: <https://claude.com/skills>
18. arXiv, MCP ecosystem analysis: <https://arxiv.org/abs/2603.23802>
19. arXiv, Anthropic Economic Index related research: <https://arxiv.org/abs/2511.15080>
