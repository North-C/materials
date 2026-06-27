# Firecracker ARM64 Guest Visibility 样本模板

本目录用于记录：

`Firecracker ARM64 guest visibility / interrupt visibility 真实失败样本`

目标文档：[ARM64 网络下一批真实样本目标图](../../arm64-network-next-target-map.md)。

关联准样本：[Firecracker ARM64 网络准样本：Guest Visibility / Interrupt Visibility](../../../firecracker/analysis/arm64-network-sample-guest-visibility.md)。

## 1. 场景

- 日期：
- 节点架构：
- host_dev_name：
- 是否涉及 MMDS：
- 启动方式：

## 2. 预期目标

证明：

1. 不是 `TapOpen` / `TapSetVnetHdrSize`
2. 不是 MMDS / limiter 伪失败
3. 而是 guest visibility / interrupt visibility 问题

## 3. 最终结论

- host backend 状态：
- guest 可用性结果：
- 首个失败点：
- 归类层级：
