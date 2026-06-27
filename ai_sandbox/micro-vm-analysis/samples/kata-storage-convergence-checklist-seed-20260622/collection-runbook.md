# Collection Runbook

目标：
为
`kata-storage-convergence-checklist-seed-20260622`
补齐一组可以升级成 `real` 的最小证据集合。

这份 runbook 不新增架构结论。

它只回答：

1. 下一轮应该抓哪些证据
2. 抓取顺序是什么
3. 抓到什么程度才值得升级 `real`

## 1. 最小目标

同一轮证据里，至少同时覆盖：

1. host 侧 rootfs/volume translation
2. `CreateContainerRequest.storages`
3. guest `add_storages()` / `mount_from()` 或等价 storage landing
4. rootfs/volume 最终是否真正可用

如果缺任何一段，都不要升 `real`。

## 2. 推荐采集顺序

### A. Host translation

至少保留一组：

- `handler_rootfs()` 分类结果
- `handler_volumes()` 分类结果
- `ShareFsRootfs` / `BlockRootfs` / volume 类型判断

建议 grep：

```bash
rg -n "handler_rootfs|handler_volumes|ShareFsRootfs|BlockRootfs" <runtime-rs-logs-or-instrumented-output>
```

### B. Request propagation

至少保留一组：

- `CreateContainerRequest.storages`
- storage `driver`
- storage `source`
- storage `mount_point`

建议 grep：

```bash
rg -n "CreateContainerRequest|storages|mount_point|driver|source" <host-request-dump-or-runtime-logs>
```

### C. Guest storage landing

至少保留一组：

- `add_storages`
- `mount_storage`
- `mount_from`

建议 grep：

```bash
rg -n "add_storages|mount_storage|mount_from" <guest-agent-logs>
```

### D. Guest-visible result

至少保留一组：

- rootfs/volume 已可用
  或
- mount 未完成 / mount 失败 / device exists but volume unusable

建议记录：

```bash
mount
findmnt
lsblk
```

以及 container create/start 的最终结果。

## 3. 最小目录回填顺序

拿到证据后，按下面顺序回填当前 seed：

1. `api.txt`
   写控制面输入、container create 请求入口、request dump 来源
2. `host.txt`
   写 translation 与 `CreateContainerRequest.storages` 结果
3. `logs.txt`
   写 host/guest 实际日志文件路径
4. `guest.txt`
   写 `add_storages()` / `mount_from()` 与最终可用性
5. `classification.md`
   收敛 `final_bucket` 与 `confidence`

## 4. 升级门槛

满足下面条件后，才把这份 seed 升成 `real`：

1. 同一批证据里能证明 translation 已发生
2. 同一批证据里能证明 `CreateContainerRequest.storages` 已形成并传出
3. 同一批证据里能证明 guest storage landing 已发生
4. 同一批证据里能证明最终 rootfs/volume 是否可用

如果只有：

- translation + request
  仍然只能算 `seed`

如果只有：

- guest 内最终失败，但缺 request / translation
  不能安全分类为 Kata storage convergence `real`

## 5. 最常见误判

### 误判一

`CreateContainerRequest.storages` 已经存在
=
guest mount 已成立

这是错误的。

它只能证明 host -> guest handoff 已准备好。

### 误判二

block/share-fs 设备已加进 VM
=
rootfs/volume 已 guest-visible

这也是错误的。

Kata 还要经过 guest `add_storages()` 和 mount 收敛。

## 6. 与现有资产的关系

这份 seed 的源码型对照材料是：

- [Share-fs / Rootfs / Volume 到 Agent 链路](../../kata-containers/analysis/sharefs-rootfs-volume-agent-chain.md)
- [Firecracker 与 Kata：Rootfs / Backing / Guest-Visible Storage 交叉线](../../fc-kata-storage-semantics-crossline.md)
- [存储、rootfs 与共享文件系统跨项目专题分析](../../storage-rootfs-sharefs-cross-project.md)
