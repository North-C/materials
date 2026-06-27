# Kata ARM64 Backend Diff QEMU 样本种子

本目录用于单独承接：

`QEMU backend`

上的 ARM64 网络 attach 失败。

关联总种子：[kata-arm64-network-backend-diff-seed-20260618](../kata-arm64-network-backend-diff-seed-20260618/)。

## 1. 场景

- 日期：`2026-06-18`
- 节点架构：`arm64`
- backend：`qemu`
- 目标签名：`QMP not initialized`

## 2. 当前状态

这不是失败回放。

它是把 QEMU 路径单独拆成一个可落真实样本的子目录。

## 3. 预期归类

- backend-specific hotplug readiness
- 不是 machine / vIOMMU 更早失败
- 不是 guest discovery 更后失败
