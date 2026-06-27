# CubeSandbox `/dev/shm` 容量不足样本记录

本目录是一个已填真实样本包。

它对应的不是 ARM64 网络数据面失败，也不是 guest-visible 收敛失败。

更准确地说，它是一份：

`storage / snapshot benchmark precondition` 失败类 `real` 样本。

## 1. 场景

- 日期：`2026-06-13`
- 节点架构：`arm64`
- 场景类型：dirty-page snapshot benchmark
- 目标签名：`No space left on device` on `/dev/shm`

## 2. 结论

这个失败点不在 snapshot 子系统本身，也不在中断或 virtio 数据面。

它发生在：

`benchmark template / runtime /dev/shm capacity precondition`

更具体地说，模板运行时容器的 `/dev/shm` 只有 64MiB，导致 dirty-page benchmark
在 100MiB 及以上用例无法先把目标脏页写进去。

## 3. 归类

- 首个失败点：benchmark precondition / tmpfs capacity
- 对应签名：`dd: error writing '/dev/shm/dirty': No space left on device`
- 归类层级：storage / snapshot benchmark precondition
- 回看文档：
  - [存储、rootfs 与共享文件系统跨项目专题分析](../../storage-rootfs-sharefs-cross-project.md)
  - [非网络当前证据缺口总表](../../non-network-evidence-gaps.md)

## 4. 与已有样本的关系

它和：

- `cubesandbox-rollback-sandbox-not-running-real-20260622`
- `cubesandbox-no-more-resource-real-20260613`

同属非网络失败样本，但问题域不同。

前两者都是控制面失败。

这份则是：

- benchmark / storage precondition failure

它同样不应被误归为 guest-visible failure 样本。
