# Kata ARM64 Route Convergence 样本种子

本目录是一个准实样示范包。

它不是基于真实失败日志。

它把 Kata ARM64 `route convergence 失败` 准样本，直接落成一个可复用目录。

关联准样本：[Kata ARM64 网络准样本：Route Convergence 失败](../../../kata-containers/analysis/arm64-network-sample-route-convergence.md)。

## 1. 场景

- 日期：`2026-06-18`
- 节点架构：`arm64`
- 场景类型：guest route convergence
- 目标：固定 `update routes request failed` 这一层

## 2. 当前状态

这不是失败回放。

它是把 route convergence 准样本结构落成目录的种子包。

后续只要拿到真实日志，就可以直接在这个目录上补成真实样本。

## 3. 预期归类

- guest route convergence
- 不是 machine / vIOMMU 更早失败
- 不是 backend attach 更早失败
- 不是 guest discovery 更早失败
