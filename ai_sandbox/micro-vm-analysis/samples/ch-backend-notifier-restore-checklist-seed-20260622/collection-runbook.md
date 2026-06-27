# Collection Runbook

目标：
为
`ch-backend-notifier-restore-checklist-seed-20260622`
补齐一组可以升级成 `real` 的最小证据集合。

这份 runbook 不新增架构结论。

它只回答：

1. 下一轮应该抓哪些证据
2. 抓取顺序是什么
3. 抓到什么程度才值得升级 `real`

## 1. 最小目标

同一轮证据里，至少同时覆盖：

1. restore 成功
2. notifier / kick / call / config 重建
3. controller restore 证据
4. guest 设备可见或不可见的最终结果

如果缺任何一段，都不要升 `real`。

## 2. 推荐采集顺序

### A. Restore success

至少保留一组：

- restore 请求
- 返回值
- `event == "restored"` 或等价成功信号

建议记录：

```bash
# restore commands / API requests
# event monitor output
```

### B. Transport / notifier

至少保留一组：

- `set_vring_call`
- `set_vring_kick`
- `set_config_call`

建议 grep：

```bash
rg -n "set_vring_call|set_vring_kick|set_config_call" <vmm-or-backend-logs>
```

### C. Controller restore

至少保留一组：

- `restore_vgic`
- or GIC state restore evidence
- or IOAPIC snapshot/restore evidence
- or MSI-X / route / mask / PBA related state evidence

建议 grep：

```bash
rg -n "restore_vgic|ioapic|msix|mask|PBA|InterruptSourceGroup|route" <vmm-logs-or-state-dump>
```

### D. Guest result

至少保留一组：

- guest sees expected device
  或
- guest still cannot see/use expected device

建议记录：

```bash
lsblk
mount
ip link
ls /dev
```

根据故障对象选择 disk/fs/net/pmem 检查。

## 3. 最小目录回填顺序

拿到证据后，按下面顺序回填当前 seed：

1. `api.txt`
   写 restore 请求、返回值、source_url、destination_url
2. `host.txt`
   写 restore success、notifier/backend、controller 观察
3. `logs.txt`
   写 event/VMM/backend/controller 实际日志路径
4. `guest.txt`
   写 guest 设备可见性与最终可用性
5. `classification.md`
   收敛 `final_bucket` 与 `confidence`

## 4. 升级门槛

满足下面条件后，才把这份 seed 升成 `real`：

1. 同一批证据里能证明 restore 已成功
2. 同一批证据里能证明 transport/notifier 已重建
3. 同一批证据里能证明 controller restore 已完成或明确异常
4. 同一批证据里能证明 guest 是否真正看到/用到设备

如果只有：

- restore success + `restored` 事件
  仍然只能算 `seed`

如果只有：

- guest 侧失败，但缺 transport/controller 证据
  不能安全分类为 CH backend/notifier/restore `real`

## 5. 最常见误判

### 误判一

`event == "restored"`
=
guest-visible state 已恢复

这是错误的。

它只能证明 restore 流程成功结束，不证明 backend/notifier/controller/guest 收敛已经成立。

### 误判二

backend 在线
=
中断和 guest 设备可见性已经恢复

这也是错误的。

route / GIC / IOAPIC / MSI-X state 仍然可能没闭合。

## 6. 与现有资产的关系

这份 seed 的源码型对照材料是：

- [Cloud Hypervisor 与 CubeSandbox：Backend / Notifier / Restore 交叉线](../../ch-cubesandbox-backend-notifier-restore-crossline.md)
- [Cloud Hypervisor 与 CubeSandbox：Restore 后 Guest 不可用验证清单](../../ch-cubesandbox-restore-guest-unavailability-checklist.md)
- [中断与事件通知跨项目专题分析](../../interrupt-event-notification-cross-project.md)
