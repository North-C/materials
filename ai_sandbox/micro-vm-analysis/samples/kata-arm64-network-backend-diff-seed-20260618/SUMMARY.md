# Kata ARM64 Backend 差异样本种子

本目录是一个准实样示范包。

它不是基于真实失败日志。

它直接把 Kata ARM64 backend 差异准样本，落成一个可复用样本目录。

关联准样本：[Kata ARM64 网络准样本：Backend 差异失败](../../../kata-containers/analysis/arm64-network-sample-backend-diff.md)。

## 1. 场景

- 日期：`2026-06-18`
- 节点架构：`arm64`
- 场景类型：backend-specific network attach failure
- 目标：区分 QEMU / Cloud Hypervisor / Dragonball 三条最早失败路径

## 2. 当前状态

这不是失败回放。

它是一个把已有源码证据转成样本结构的种子包。

后续只要拿到任一 backend 的真实错误文本，就可以直接在这个目录结构上补成真实样本。

## 3. 预期归类

- QEMU：`QMP not initialized`
- Cloud Hypervisor：`open named tuntap`
- Dragonball：`insert network device`
