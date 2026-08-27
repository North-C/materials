# 三个 AI Sandbox 平台源码对比

本目录收录面向技术管理/架构评审的 AI Sandbox 三平台源码对比，以及可直接用于 3–5 分钟汇报的一页图表。

## 交付物

- [three-platform-source-comparison.md](three-platform-source-comparison.md) — 源码支撑的完整中文对比：结论、版本范围、组件、流程、技术矩阵、版本演化、证据索引和限制。
- [one-slide-content.md](one-slide-content.md) — 可直接搬到 16:9 PPT 的一页内容、90 秒讲稿和页脚版本。
- [sandbox-platform-one-slide.drawio](sandbox-platform-one-slide.drawio) — 可编辑 draw.io 图。
- [sandbox-platform-one-slide.svg](sandbox-platform-one-slide.svg) — standalone SVG，可导入 PowerPoint。

## 版本口径

主对比只使用 2026-08-27 当日核验的 latest stable release：

- CubeSandbox `v0.6.0@8721dd151971ce3c2966482bbd32904ad98f378e`
- AgentENV `v0.1.3@7f4a9b9f198e350fbf1e514b837eabb277ecb2f8`
- E2B-infra `2026.29@557445ffddda8d9a27f6f529a3f4d7732cf81a13`

默认分支 HEAD 的新增能力只放在“版本演化观察”，没有混入主对比。完整 tag、commit、日期与默认分支 HEAD 核验记录见 [three-platform-source-comparison.md](three-platform-source-comparison.md) 的“版本范围”章节。

## 状态与证据

- `status`: verified
- `last_verified`: 2026-08-27
- `evidence`: [three-platform-source-comparison.md](three-platform-source-comparison.md) 中的逐项目源码路径、符号和行号索引
- `source revisions`: CubeSandbox `8721dd151971ce3c2966482bbd32904ad98f378e`；AgentENV `7f4a9b9f198e350fbf1e514b837eabb277ecb2f8`；E2B-infra `557445ffddda8d9a27f6f529a3f4d7732cf81a13`

## 边界

本交付只做源码研究、文档和图表；未修改三个产品源码，未运行远端环境，也不包含性能排名。外部宣传性能数字未作为选型结论。
