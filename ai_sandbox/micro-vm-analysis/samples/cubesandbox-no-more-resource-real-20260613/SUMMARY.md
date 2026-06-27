# CubeSandbox `no more resource` 样本记录

本目录是一个已填真实样本包。

它对应的不是 ARM64 网络数据面失败，也不是 guest-visible 收敛失败。

更准确地说，它是一份：

`control plane / scheduler quota capacity` 失败类 `real` 样本。

## 1. 场景

- 日期：`2026-06-13`
- 节点架构：`arm64`
- 场景类型：create-only / clone concurrency / scheduler capacity
- 目标签名：`no more resource`

## 2. 结论

这个失败点不在 virtio 数据面，不在 guest agent，也不在中断注入。

它发生在：

`CubeMaster scheduler / quota capacity window`

更具体地说，控制面在调度过滤阶段已经找不到满足条件的节点，因此直接返回：

`CubeMaster returned error code 130597: no more resource`

## 3. 归类

- 首个失败点：CubeMaster scheduler quota / capacity
- 对应签名：`ret_code = 130597`, `ret_msg = "no more resource"`
- 归类层级：control plane / scheduler capacity
- 回看文档：
  - [CubeMaster scheduler task chain](../../../CubeSandbox-sandbox-clone/analysis/cubemaster-scheduler-task-chain.md)
  - [非网络当前证据缺口总表](../../non-network-evidence-gaps.md)

## 4. 与已有样本的关系

它和：

- `cubesandbox-rollback-sandbox-not-running-real-20260622`

同属控制面失败类样本，但不是同一问题域。

前者是：

- sandbox lifecycle window

这份则是：

- scheduler quota / capacity exhaustion

它同样不应被误归为 guest-visible 失败样本。
