# CubeSandbox Rollback `sandbox is not running` 样本记录

本目录是一个已填真实样本包。

它对应的不是 ARM64 网络数据面失败，而是 snapshot/rollback 并发路径中的平台状态窗口异常。

它也不是 guest-visible 收敛失败。

更准确地说，它是一份：

`control plane / sandbox lifecycle window` 失败类 `real` 样本。

## 1. 场景

- 日期：`2026-06-13`
- 节点架构：`arm64`
- 场景类型：rollback / snapshot concurrency
- 目标签名：`sandbox is not running`

## 2. 结论

这个失败点不在 virtio 数据面，也不在 guest agent mount 收敛。

它发生在：

`CubeMaster / Cubelet 对 sandbox running 状态的判定窗口`

更具体地说，是 rollback case 内创建 snapshot 的阶段，控制面认为目标 sandbox 已不处于 `running`。

## 3. 归类

- 首个失败点：rollback 并发路径中的 sandbox lifecycle state
- 对应签名：`CubeMaster returned error code 130400: sandbox ... is not running`
- 归类层级：control plane / sandbox lifecycle window
- 回看文档：
  - [Rollback / Runtime Update 链路](../../../CubeSandbox-sandbox-clone/analysis/rollback-runtime-update-chain.md)
  - [Snapshot / Restore 网络恢复链路](../../../CubeSandbox-sandbox-clone/analysis/snapshot-restore-network-chain.md)
