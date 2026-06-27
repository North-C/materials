# Firecracker 与 Kata：Rootfs / Backing / Guest-Visible Storage 交叉线

本文聚焦一个和 `Cloud Hypervisor + CubeSandbox` 很不同、但同样容易被混掉的问题：

Firecracker 与 Kata 虽然都会让 guest 看到 block 或共享目录相关对象，但两者在“rootfs 语义到底由谁成立”这件事上，处在完全不同的层级。

源码基线：当前工作树。

关联专题：

- [存储、rootfs 与共享文件系统跨项目专题分析](./storage-rootfs-sharefs-cross-project.md)
- [Firecracker 存储 / rootfs / share-fs 边界链路](../firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md)
- [Share-fs / Rootfs / Volume 到 Agent 链路](../kata-containers/analysis/sharefs-rootfs-volume-agent-chain.md)

## 1. 核心结论

Firecracker 解决的是：

如何把 root block / pmem 设备暴露给 guest，并通过 kernel cmdline 指定哪一个是 root。

Kata 解决的是：

如何把 host rootfs / volume 翻译成 guest agent 能落地的 `Storage`、mount 和 OCI 语义。

两者都可能出现“guest 看起来没有 rootfs/volume”的症状，但第一怀疑点完全不同。

Firecracker 更像：

root 表达、backing file 一致性、restore 后设备是否仍然可见

Kata 更像：

translation、request propagation、agent storage 落地、guest mount convergence

## 2. Firecracker：rootfs 语义由设备表达和 cmdline 决定

Firecracker 的 rootfs 语义是 VMM 级。

`build_microvm_for_boot()` 在 attach block / pmem 阶段直接把 root 写进 kernel cmdline：

- `root=/dev/vda`
- `root=PARTUUID=...`
- `root=/dev/pmem{i}`

证据：

- [firecracker/src/vmm/src/builder.rs](/home/lyq/Projects/Micro-VM/firecracker/src/vmm/src/builder.rs:672)

这意味着 Firecracker 的 rootfs 成立条件是：

1. 设备被正确 attach
2. cmdline 指向正确的 root device
3. backing file / pmem file 在 restore 后仍语义一致

它没有 Kata 那样的 guest agent `Storage` 翻译层。

## 3. Kata：rootfs 语义由 translation + agent 落地决定

Kata 的 rootfs 语义是 runtime + guest agent 级。

host 侧先做：

1. `handler_rootfs()`
2. `handler_volumes()`
3. 生成 `CreateContainerRequest.storages`

证据：

- [kata-containers/src/runtime-rs/crates/resource/src/rootfs/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/resource/src/rootfs/mod.rs:66)
- [kata-containers/src/runtime-rs/crates/resource/src/volume/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/resource/src/volume/mod.rs:52)
- [kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/container_manager/container.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/container_manager/container.rs:260)

guest 侧再做：

1. `add_storages()`
2. `mount_storage()`
3. `mount_from()`

证据：

- [kata-containers/src/agent/src/storage/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/agent/src/storage/mod.rs:253)
- [kata-containers/src/agent/rustjail/src/mount.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/agent/rustjail/src/mount.rs:755)

所以 Kata 的 rootfs 成立条件是：

1. host 侧 translation 正确
2. `CreateContainerRequest.storages` 正确构造并传入 guest
3. guest agent 真的执行 storage handler
4. mount 最终成功

## 4. 相同症状，不同怀疑点

同样看到“guest rootfs / volume 不可用”，两边应该先怀疑的位置不同。

| 项目 | 第一怀疑点 | 第二怀疑点 | 第三怀疑点 |
|---|---|---|---|
| Firecracker | root device 表达是否正确 | backing file 是否仍语义一致 | guest 是否重新看到 block / pmem |
| Kata | `handler_rootfs()` / `handler_volumes()` 是否生成正确 storage | `CreateContainerRequest.storages` 是否成功传到 guest | `add_storages()` / `mount_from()` 是否真正落地 |

这也是为什么不能把两者都粗暴归为“存储 restore 失败”。

对 Firecracker 来说，更像：

设备表达或 backing file 问题

对 Kata 来说，更像：

storage convergence 问题

## 5. 样本资产如何对应

这条交叉线已经各自落到对应 checklist seed：

- [Firecracker rootfs/backing/restore checklist seed](./samples/fc-rootfs-backing-restore-checklist-seed-20260622/SUMMARY.md)
- [Kata storage convergence checklist seed](./samples/kata-storage-convergence-checklist-seed-20260622/SUMMARY.md)

前者更适合承接：

- root 表达
- backing file 依赖
- restore 后设备可见性

后者更适合承接：

- translation
- request propagation
- guest storage landing
- mount convergence

## 6. 推荐使用顺序

如果后续要继续把这条线往真实样本推进，建议顺序是：

1. 先用 Firecracker seed 固定 rootfs / backing / restore 的最小回填方法
2. 再用 Kata seed 固定 `CreateContainerRequest.storages -> add_storages() -> mount_from()` 的回填方法

原因很直接：

Firecracker 变量更少，更容易先把“设备表达型 rootfs 语义”跑通。

Kata 的价值则在于把“guest-visible storage convergence”方法建立起来。
