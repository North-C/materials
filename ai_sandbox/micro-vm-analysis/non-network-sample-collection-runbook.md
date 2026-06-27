# 非网络样本采集 Runbook

本文不是新的分析专题。

它只回答一个执行层问题：

当你拿到一包新的 non-network 证据，应该按什么顺序处理，才能最小化误分桶和重复劳动。

它适用于当前四份重点 seed：

1. `cubesandbox-guest-visible-restore-checklist-seed-20260622`
2. `kata-storage-convergence-checklist-seed-20260622`
3. `fc-rootfs-backing-restore-checklist-seed-20260622`
4. `ch-backend-notifier-restore-checklist-seed-20260622`

承接文档：

- [非网络横线样本资产矩阵](./non-network-sample-asset-matrix.md)
- [非网络下一批真实样本目标图](./non-network-next-target-map.md)
- [非网络证据包记录模板](./non-network-evidence-bundle-template.md)

## 1. 先决定这包证据属于哪条主线

优先用最少判断先归主线：

| 线 | 典型种子 |
|---|---|
| 存储 / rootfs / share-fs | Firecracker rootfs/backing、Kata storage、CubeSandbox guest-visible 中的 mount/rootfs 子问题 |
| I/O 虚拟化 / worker / backend | CH backend/notifier、CubeSandbox guest-visible 中的 worker/backend 子问题 |
| 中断虚拟化 / route / controller | CH backend/notifier、CubeSandbox guest-visible 中的 irqfd / GIC / ITS / route 子问题 |

如果一包证据跨多条线，不要强行拆成多个 bundle。

先把它当成一个 attempt 记录下来，再在对应 seed 内部分桶。

## 2. 第二步：先记账，不要急着分桶

拿到一包新证据后，先用：

- [非网络证据包记录模板](./non-network-evidence-bundle-template.md)

把这些信息写下来：

1. bundle 名称
2. attempt 唯一标识
3. 项目
4. 机器架构
5. 触发动作
6. 当前已有文件

这一步的目的，是避免先入为主地把证据往某个结论里塞。

## 3. 第三步：选 seed

推荐顺序：

1. 先看 [非网络下一批真实样本目标图](./non-network-next-target-map.md)
2. 再选最接近当前证据形态的 seed

通常优先级如下：

1. `CubeSandbox guest-visible`
2. `Kata storage convergence`
3. `Firecracker rootfs/backing`
4. `Cloud Hypervisor backend/notifier/restore`

但真正选择时，以证据形态为准，不要机械套优先级。

## 4. 第四步：进 seed 目录，按固定顺序走

进入 seed 目录后，统一按这个顺序：

1. `fill-guide`
2. `evidence-targets`
3. `collection-runbook`
4. `minimum-log-bundle`
5. `decision-table`
6. `bundle-template`
7. `bundle-skeleton`

如果该目录还有：

- `request-samples.txt`
- `request-sample-*.json/txt`
- `*.template.json`

就按“真实 dump > request-shaped sample > template”的优先级使用。

## 5. 第五步：整理成 attempt bundle

为每次尝试创建单独目录，例如：

- `cubesandbox-guest-visible-attempt-<date>-<id>/`
- `kata-storage-attempt-<date>-<id>/`
- `fc-rootfs-restore-attempt-<date>-<id>/`
- `ch-backend-restore-attempt-<date>-<id>/`

如果不知道目录里至少该有哪些文件，就先看对应 seed 的：

- `bundle-skeleton.txt`

不要把多个 attempt 混在同一个 bundle 里。

## 6. 第六步：判断证据是否够强

先过：

- `minimum-log-bundle.txt`

如果 minimum bundle 都不满足：

- 不要升级
- 先补缺的那一层

再过：

- `decision-table.txt`

只在 `decision-table` 允许升级的那一行上，才考虑升 `real`。

## 7. 第七步：最常见误判

### 误判一

看到 request sample / template
=
已经有真实运行证据

不是。

这只是 request-side 基线。

### 误判二

看到 success baseline `real`
=
已经能推出 failure `real`

不是。

success baseline 只能做对照，不等于 failure-side 证据已经存在。

### 误判三

控制面失败
=
guest-visible failure

也不是。

例如 CubeSandbox 里的 `sandbox is not running` 仍然属于更早的 control-plane failure。

## 8. 第八步：回填目录文件

最小回填顺序建议如下：

1. `api.txt`
2. `host.txt`
3. `logs.txt`
4. `guest.txt`
5. `classification.md`

如果当前还缺关键日志，不要硬写结论，直接把“仍缺哪一层”写清楚即可。

## 9. 升级条件

只有在同一包证据里，已经同时覆盖：

1. control-plane / request
2. 中间层 / worker / backend / controller
3. guest-visible result

才应该考虑把 `seed` 升成新的 `real`。

否则，最合理的动作是：

- 保持 `seed`
- 记录当前最强证据
- 标明还缺什么

## 10. 结论

这份 runbook 的目标，不是替代四个 seed 目录。

它只是把四个目录已经收敛出来的共性动作统一起来：

先记账，再选 seed，再按 bundle 规则回填，再做升级判定。

## 11. 按项目的最小 live 采集动作

如果下一轮已经真的连上环境，不想先翻四个 seed 目录，可以直接按下面最小动作开始：

### Cloud Hypervisor

1. 记录 snapshot / restore 请求
2. 记录 `event == "restored"`
3. 抓 `set_vring_call` / `set_vring_kick` / `set_config_call`
4. 抓 `restore_vgic` / `ioapic` / `msix`
5. guest 内确认 disk/fs/net/pmem 是否可见

### Firecracker

1. 记录 snapshot / restore 请求
2. 记录 root cmdline：`root=/dev/vda` / `root=PARTUUID=...` / `root=/dev/pmem*`
3. 记录 backing file / disk path / pmem path
4. guest 内确认 `/dev/vd*` / `/dev/pmem*`
5. guest 内确认 `/` 是否真正可用

### Kata Containers

1. 记录 `handler_rootfs()` / `handler_volumes()` 分类结果
2. 记录 `CreateContainerRequest.storages`
3. 抓 guest `add_storages` / `mount_storage` / `mount_from`
4. guest 内确认 rootfs / volume 是否真正可用

### CubeSandbox

1. 记录 `VmRestore` / `VmResumeFromSnapshot` / `VmSetFs` / `VmAddDevice`
2. 记录 `VsockServerReady` / `VmShutdown` / probe fallback
3. 抓 `FsEvent` / `back_state` / `deserialize_and_apply_data` / TAP/tap fd 重绑
4. 抓 guest `wait a pci` / `get_virtio_blk_pci_device_name` / mount / net / ready 结果

这四组动作都只是起步动作。

真正升级前，仍要回到对应 seed 的：

- `minimum-log-bundle`
- `decision-table`

做最后判定。
