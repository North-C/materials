# CubeSandbox ARM64 `tap fd unavailable` 样本记录

本目录是一个已填示范样本包。

它对应的不是抽象模板。

它直接落在仓库里已经存在的 ARM64 真实案例上。

关联案例：[CubeSandbox ARM64 `tap fd unavailable` 故障案例分析](../../../CubeSandbox-sandbox-clone/analysis/tap-fd-unavailable-case-study.md)。

## 1. 场景

- 日期：`2026-06-13`
- 节点架构：`arm64`
- 触发类型：并发创建
- 目标签名：`tap fd unavailable`

## 2. 结论

首个失败点不在 guest 内。

它发生在：

`network-agent -> restoreTap -> Cubelet fd pool`

这条 host fd handoff 链上。

对应的真实错误文本已经在现有优化报告中出现。

## 3. 归类

- 首个失败点：`request original tap fd`
- 对应签名：`tap fd unavailable ... Link not found`
- 归类层级：host fd handoff / pooled TAP restore
- 回看文档：
  - [ARM64 网络失败原型](../../../CubeSandbox-sandbox-clone/analysis/arm64-network-failure-prototypes.md)
  - [故障案例分析](../../../CubeSandbox-sandbox-clone/analysis/tap-fd-unavailable-case-study.md)
