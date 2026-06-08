# AlphaEval 核心总结

论文：AlphaEval: Evaluating Agents in Production
链接：https://arxiv.org/abs/2604.12162

## 核心观点

AlphaEval 提出一个面向真实生产场景的 Agent 评估框架。它的核心判断是：现有 Agent benchmark 多来自整理好的代码 issue、网页任务或标准答案任务，无法充分反映企业真实使用 Agent 时遇到的模糊需求、多模态输入、隐含约束、长交付链路和专家主观验收标准。

AlphaEval 关注的不是裸模型能力，而是完整 Agent 产品能力，例如 Claude Code、Codex、GitHub Copilot、Cursor 等商业 Agent scaffold 与模型组合后的实际表现。

## 主要贡献

1. 生产需求到 benchmark 的构造流程

   AlphaEval 给出四阶段方法：合作伙伴接入、需求访谈、任务形式化、迭代验证。任务被标准化为 `query.md`、`task.yaml`、`files/`、`.eval/rubric.py` 等结构，便于复现和扩展。

2. 94 个真实生产任务

   任务来自 7 家公司，覆盖 6 个 O*NET 职业领域：人力资源、金融投资、采购运营、软件工程、医疗生命科学、技术研究。输入包括 PDF、Excel/CSV、Markdown/Text、代码/YAML 等，其中 PDF 约 42%。

3. 评估完整 Agent 产品

   论文评估 Claude Code、Codex、GitHub Copilot、Cursor 等 Agent scaffold 与不同模型组合，共 14 个配置。结论是 scaffold 影响非常大，同一个模型通过不同 Agent 产品运行，分数可相差 11 到 15 分。

4. 多范式自动评估框架

   AlphaEval 组合使用 LLM-as-a-Judge、参考答案校验、约束验证、形式化/数值验证、rubric 评分、自动 UI 测试等方法。所有 Agent 通过 CLI 在 Docker 沙箱中运行，并记录工具调用、文件读写、输出轨迹和评分 JSON。

## 关键实验结论

最佳配置是 Claude Code + Claude Opus 4.6，平均分 64.41/100，说明前沿 Agent 在真实生产任务上仍有明显缺口。

同一模型换 scaffold 后差异很大：Opus 4.6 在 Claude Code 上为 64.41，在 Codex 上为 53.45。这说明评估 CPU 负载时不能只看模型调用，要把 Agent 框架、工具调用策略、文件 IO、浏览器/UI 测试、Docker 环境等一起纳入。

领域差异也很大：Technology Research 平均约 62.0，Human Resources 平均约 30.0。单一总分不足以判断生产可用性，应按业务领域拆解评估。

## 生产特有失败模式

论文总结了 6 类生产特有失败模式：

1. 级联依赖失败
2. 主观判断崩塌
3. 信息检索失败
4. 长文档逻辑不一致
5. 约束误解
6. 格式合规失败

## 对 CPU 负载与性能优化的启示

AlphaEval 本身不是 CPU benchmark，但它非常适合作为 Agent 评估负载建模的参考。论文报告平均每任务约 14 分钟、46 轮交互，并包含 Docker、CLI Agent、文件处理、PDF/表格解析、搜索、代码生成、UI 自动化测试、LLM Judge 等多类负载。

后续如果研究 CPU 性能，应围绕这些阶段采集指标：

- 进程 CPU 时间
- wall time
- 上下文切换
- IO wait
- 容器启动与隔离开销
- 浏览器/UI 测试开销
- 并发任务吞吐
- 工具调用轨迹与评分阶段耗时
