# Cloud Hypervisor ARM64 Restore 样本种子

本目录是一个准实样示范包。

它不是基于真实失败日志。

它把 Cloud Hypervisor ARM64 `restore 后网络异常` 准样本，直接落成一个可复用目录。

关联准样本：[Cloud Hypervisor ARM64 网络准样本：Restore 后网络异常](../../../cloud-hypervisor/analysis/arm64-network-sample-restore-regression.md)。

## 1. 场景

- 日期：`2026-06-18`
- 节点架构：`arm64`
- 场景类型：snapshot -> restore
- 目标：固定 `pre-restore healthy -> restore complete -> post-restore regression`

## 2. 当前状态

这不是失败回放。

它是一个把 restore / GIC-state 协同问题落成样本目录的种子包。

后续只要拿到真实恢复前后日志，就可以直接在这个目录上补齐。

## 3. 预期归类

- restore / GIC-state coordination
- 不是启动期 `vm_add_net()` / tap/backend 失败
- 不是普通 hotplug 失败
