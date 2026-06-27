# CubeSandbox ARM64 中间层日志样本模板

本目录用于记录：

`CubeSandbox ARM64 collect-logs 中间层日志样本`

目标文档：[ARM64 网络下一批真实样本目标图](../../arm64-network-next-target-map.md)。

关联案例：[CubeSandbox ARM64 `tap fd unavailable` 故障案例分析](../../../CubeSandbox-sandbox-clone/analysis/tap-fd-unavailable-case-study.md)。

## 1. 场景

- 日期：
- 节点架构：
- 触发类型：并发创建 / restore / 其他
- 目标签名：`tap fd unavailable` / 其他

## 2. 预期目标

不是再证明平台层功能。

而是补齐：

`network-agent` / `cubeshim` / `cubevmm` / `runtime` / `dmesg`

的中间层日志。

## 3. 最终结论

- 是否拿到 `collect-logs.sh` 产物：
- 是否命中目标签名：
- 首个失败点：
- 回看的故障案例：
