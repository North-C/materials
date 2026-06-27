# Firecracker ARM64 Guest Visibility 样本种子

本目录是一个准实样示范包。

它不是基于真实失败日志。

它把 Firecracker ARM64 `guest visibility / interrupt visibility` 准样本，直接落成一个可复用的样本目录。

关联准样本：[Firecracker ARM64 网络准样本：Guest Visibility / Interrupt Visibility](../../../firecracker/analysis/arm64-network-sample-guest-visibility.md)。

## 1. 场景

- 日期：`2026-06-18`
- 节点架构：`arm64`
- 场景类型：guest visibility / interrupt visibility
- 目标：证明问题晚于 `TapOpen` / `TapSetVnetHdrSize`，也晚于 MMDS / limiter 伪失败

## 2. 当前状态

这不是失败回放。

它是一个把准样本结构落成目录的种子包。

后续只要拿到 guest 侧“不具备网络可用性”的真实证据，就可以直接在这个目录上升级成真实样本。

## 3. 预期归类

- host backend 正常
- queue / MMDS 层没有更近解释
- 最终归到 guest visibility / interrupt visibility
