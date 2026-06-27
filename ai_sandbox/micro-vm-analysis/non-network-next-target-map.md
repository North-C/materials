# 非网络下一批真实样本目标图

本文承接：

- [非网络横线样本资产矩阵](./non-network-sample-asset-matrix.md)
- [存储、rootfs 与共享文件系统跨项目专题分析](./storage-rootfs-sharefs-cross-project.md)
- [Virtio 传输与设备数据路径跨项目专题分析](./virtio-data-path-cross-project.md)
- [中断与事件通知跨项目专题分析](./interrupt-event-notification-cross-project.md)

前面的文档已经回答了：

1. 现在哪些 non-network 主题已经有分析结构
2. 哪些 seed 已经具备完整的采证包
3. 哪些项目当前最缺真实运行证据

本文继续往前压一层。

它不再讨论“哪条横线更重要”这种泛化问题。

它只回答：

下一批最值得变成 `real` 的，具体是哪几个场景。

源码基线：当前工作树。

## 1. 核心结论

当前四个项目里，下一批最值得推进的 non-network `real`，建议按下面顺序收敛：

1. CubeSandbox：guest-visible restore/update failure `real`
2. Kata Containers：storage convergence `real`
3. Firecracker：rootfs/backing/restore `real`
4. Cloud Hypervisor：backend/notifier/restore failure `real`

这个排序不是在比较项目本身的重要性。

它只反映一个问题：

哪一份 seed 现在最接近“只差一包新证据”就能被安全升级。

## 2. 目标一：CubeSandbox guest-visible failure `real`

CubeSandbox 当前已经同时拥有：

1. 一份成功基线 `real`
2. 两份控制面失败 `real`
3. 一份最完整的 guest-visible failure seed

缺的正是第三类：

控制面成功，但 worker/backend 已推进，最终 guest-visible state 未收敛。

对应 seed：

- [cubesandbox-guest-visible-restore-checklist-seed-20260622](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md)

最小成功标准：

1. 同一 attempt 里能证明 `VmRestore` / `VmResumeFromSnapshot` / `VmSetFs` / `VmAddDevice` 至少一条成功
2. 同一 attempt 里能证明 worker/backend 至少推进一段
3. 同一 attempt 里能证明 guest-visible convergence 最终失败

为什么它排第一：

因为这份 seed 现在最完整，且一旦升成 `real`，CubeSandbox 的三类问题域就能完整拆开：

1. success baseline
2. control-plane failure
3. guest-visible failure

ARM64 下这一目标最值得优先抓的，不是泛泛的“失败日志”，而是这四层按同一 attempt 对齐：

1. `VmRestore` / `VmResumeFromSnapshot` / `VmSetFs` / `VmAddDevice`
2. `VsockServerReady` / `VmShutdown` / probe fallback
3. `FsEvent` / `back_state` / `deserialize_and_apply_data` / TAP/tap fd 重绑
4. guest `wait a pci` / `get_virtio_blk_pci_device_name` / mount / net / ready 结果

换句话说，CubeSandbox ARM64 最值的不是多抓一点日志，而是抓对这四层的同 attempt 对照。

## 3. 目标二：Kata storage convergence `real`

Kata 当前已经有：

1. codepath-derived translation 证据
2. request-shaped `CreateContainerRequest.storages` 样本
3. guest-side `add_storages()` / `mount_from()` 的函数链

但还没有一组同 attempt 的真实 guest-side 运行证据。

对应 seed：

- [kata-storage-convergence-checklist-seed-20260622](./samples/kata-storage-convergence-checklist-seed-20260622/SUMMARY.md)

最小成功标准：

1. 一次真实 translation / request propagation 记录
2. 一段真实 guest `add_storages()` / `mount_storage()` / `mount_from()` 记录
3. 一次最终 rootfs / volume 可用性或失败结果

为什么它排第二：

因为它已经明显高于“纯代码路径”，但仍停在 request-side。只要再拿到 guest 运行证据，就能真正推进。

ARM64 下这一目标最值得优先抓的证据，不是再证明 `CreateContainerRequest.storages` 有哪些字段，而是：

1. guest `add_storages()`
2. guest `mount_storage()`
3. guest `mount_from()`
4. 最终 rootfs / volume 是否真正可用

这条线在 ARM64 上尤其要避免误判成 hypervisor 层失败，因为 host 侧 request 已经有较强样本，真正缺的是 guest-side 收敛。

## 4. 目标三：Firecracker rootfs/backing `real`

Firecracker 当前已经有：

1. root expression 锚点
2. backing/restore 边界
3. request-shaped sample/template

但没有任何真实 restore + guest-visible 设备 / rootfs 结果。

对应 seed：

- [fc-rootfs-backing-restore-checklist-seed-20260622](./samples/fc-rootfs-backing-restore-checklist-seed-20260622/SUMMARY.md)

最小成功标准：

1. 一次真实 snapshot / restore 请求
2. 一次 root expression 与设备的对应关系
3. 一次 backing consistency 证据
4. 一次 guest 设备可见性
5. 一次 rootfs 最终可用性结果

为什么它排第三：

因为这条线当前仍完全受限于没有新的 runtime/guest transcript，不像 Kata 已经有 request-shaped 样本那样更靠前。

ARM64 下这一目标最值得优先抓的证据，是同一 attempt 里的三层对应关系：

1. restore 请求成功
2. `root=/dev/vda` / `root=PARTUUID=...` / `root=/dev/pmem{i}` 之一到底是什么
3. guest `/dev/vd*` / `/dev/pmem*` 是否出现，以及 `/` 是否真正可用

Firecracker 在这里最容易被误判成“restore 成功就算过关”，但对 ARM64 来说，真正值钱的是 guest-visible 结果而不是 API 成功。

## 5. 目标四：Cloud Hypervisor failure `real`

Cloud Hypervisor 当前已经有：

1. documented request-shaped sample
2. `event == "restored"` baseline
3. success baseline `real`

但仍没有一份 failure-side runtime/guest bundle。

对应 seed：

- [ch-backend-notifier-restore-checklist-seed-20260622](./samples/ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md)

最小成功标准：

1. 一次真实 restore success
2. transport/notifier 重建证据
3. controller restore 证据
4. guest-visible failure 或成功结果

为什么它排第四：

因为当前已经有 success baseline `real`，但 failure-side 证据仍然完全空白；同时它比 CubeSandbox/Kata 更依赖拿到成套的 runtime 证据。

ARM64 下这一目标最值得优先抓的，是：

1. `event == "restored"`
2. `set_vring_call` / `set_vring_kick` / `set_config_call`
3. `restore_vgic` / controller state
4. guest 是否真的重新看到设备

也就是说，CH 在 ARM64 上最容易卡的不是“有没有 restore 命令”，而是 transport/notifier/controller 这一整段有没有和 guest-visible 结果对上。

## 6. 四个目标的最小对照表

| 优先级 | 项目 | 目标场景 | 目标样本名模板 | 最小成功标准 |
|---|---|---|---|---|
| 1 | CubeSandbox | guest-visible restore/update failure | `cubesandbox-guest-visible-failure-<date>` | 控制面成功 + worker推进 + guest-visible失败 |
| 2 | Kata Containers | storage convergence | `kata-storage-convergence-<date>` | request + guest storage landing + final usability |
| 3 | Firecracker | rootfs/backing/restore | `fc-rootfs-backing-restore-<date>` | restore + root expression + backing + guest visibility + rootfs usability |
| 4 | Cloud Hypervisor | backend/notifier/restore failure | `ch-backend-notifier-restore-failure-<date>` | restore + transport/notifier + controller + guest result |

对应的推荐 bundle 目录名也可以直接固定为：

| 项目 | 推荐 bundle 目录名 |
|---|---|
| CubeSandbox | `cubesandbox-guest-visible-attempt-<YYYYMMDD>-<id>/` |
| Kata Containers | `kata-storage-attempt-<YYYYMMDD>-<id>/` |
| Firecracker | `fc-rootfs-restore-attempt-<YYYYMMDD>-<id>/` |
| Cloud Hypervisor | `ch-backend-restore-attempt-<YYYYMMDD>-<id>/` |

## 7. 这张目标图应该怎么用

后续如果继续推进，不建议再从“哪条横线还值得补”重新讨论。

更建议直接按下面顺序：

1. 先看这张目标图，选一个最值得升级的 seed
2. 再进对应 seed 目录
3. 按该 seed 的：
   - `fill-guide`
   - `evidence-targets`
   - `collection-runbook`
   - `minimum-log-bundle`
   - `decision-table`
   - `bundle-template`
   - `bundle-skeleton`
   来接一包新的证据
4. 如果是一包全新的证据，先用：
   - [非网络证据包记录模板](./non-network-evidence-bundle-template.md)
   把事实落账，再回填到具体 seed

如果目标本身是 ARM64 主机上的问题，再多做一步：

在开始回填前，先把同一 attempt 里最关键的 ARM64 特征写清楚，例如：

- `GIC / ITS`
- `virt` machine / `gic-version=host`
- `/dev/pmem*` / `/dev/vd*`
- `VsockServerReady` / probe fallback

这样后面在 `decision-table` 分桶时，不会把纯 guest convergence 和纯架构控制器问题混在一起。

这样可以避免继续在“规则还差不差”这个问题上打转。

## 8. 结论

non-network 三条横线现在已经不再缺“分析框架”。

它缺的是：

把下一批真正有价值的 `real` 做出来。

这张目标图的作用，就是把“下一步”收敛成四个明确场景。

如果当前没有新的运行时证据进入工作树，最合理的动作通常不是继续扩展分析结构，
而是停在这里，等待新的 host/runtime/guest 证据包进入后，再按既有 seed 和 runbook 推进。
