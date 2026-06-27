# Cloud Hypervisor Backend / Notifier / Restore Checklist Seed

## 1. 目标

把 `Cloud Hypervisor restore 成功但 guest 不可用` 的排查动作，固定为一份可复用 seed。

本目录承接：

- [Cloud Hypervisor 与 CubeSandbox：Restore 后 Guest 不可用验证清单](../../ch-cubesandbox-restore-guest-unavailability-checklist.md)
- [Cloud Hypervisor 与 CubeSandbox：Backend / Notifier / Restore 交叉线](../../ch-cubesandbox-backend-notifier-restore-crossline.md)

## 2. 升级状态

- 当前状态：`seed`
- 目标升级路径：`seed -> real -> validated`

这不是失败回放。

它是一个把 `backend / notifier / restore` 交叉问题落成样本目录的种子包。

后续只要拿到真实 restore 请求、`restored` 事件、backend 重连证据和 guest 侧设备可见性，就可以直接在这个目录上补齐。

当前更准确的状态是：

它已经是一个 **doc/test-derived baseline seed**，不是纯空白占位。

也就是说，它已经吸收了仓库内现成的：

1. 官方 snapshot/restore 文档命令路径
2. `performance-metrics` 中的 restore 事件格式

但还没有真实主机/guest 对照日志，所以不能直接升级为 `real`。

与另外两份非网络存储 seed 一样，本目录现在也包含了更可执行的回填入口：

- [evidence-targets.txt](./evidence-targets.txt)
- [collection-runbook.md](./collection-runbook.md)

它们的作用不是新增结论，而是把 `seed -> real` 的最低证据门槛固定下来。

## 3. 本 seed 关注的问题

1. `VirtioPciDevice` transport state 是否恢复完整
2. vhost-user / vDPA 的 `call/kick/config` eventfd 是否重建
3. MSI-X route / mask / controller restore 是否一致
4. backend 在线但 guest 不可见时，问题是否仍停在 VMM restore 层

## 4. 当前已知证据入口

- transport / PCI / MSI-X snapshot：
  [cloud-hypervisor/virtio-devices/src/transport/pci_device.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/virtio-devices/src/transport/pci_device.rs:1305)
- vhost-user vring setup：
  [cloud-hypervisor/virtio-devices/src/vhost_user/vu_common_ctrl.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/virtio-devices/src/vhost_user/vu_common_ctrl.rs:153)
- vDPA `call/kick/config`：
  [cloud-hypervisor/virtio-devices/src/vdpa.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/virtio-devices/src/vdpa.rs:282)
- GIC restore：
  [cloud-hypervisor/vmm/src/device_manager.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/vmm/src/device_manager.rs:1728)
- IOAPIC snapshot：
  [cloud-hypervisor/devices/src/ioapic.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/devices/src/ioapic.rs:445)

## 5. 当前缺口

1. 缺真实 restore 前后对照日志
2. 缺真实 backend socket / fd 重连证据
3. 缺 guest 侧“看到设备 / 没看到设备”的明确观测

## 6. 已有可直接复用的准真实入口

当前仓库已经有两类可以直接拿来回填 seed 的入口：

1. 官方 snapshot/restore 文档给出了最小命令路径，包括：
   - `pause`
   - `snapshot file://...`
   - `restore source_url=file://...`
   - `resume`

   证据：
   [cloud-hypervisor/docs/snapshot_restore.md](/home/lyq/Projects/Micro-VM/cloud-hypervisor/docs/snapshot_restore.md:1)

2. `performance-metrics` 里已经有 restore 事件监控逻辑，明确以 `event == "restored"` 作为 restore 成功信号。

   证据：
   [cloud-hypervisor/performance-metrics/src/performance_tests.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/performance-metrics/src/performance_tests.rs:532)

## 7. 当前建议的最小回填顺序

1. 先补 restore 请求与 `restored` 成功信号
2. 再补 `set_vring_call` / `set_vring_kick` / `set_config_call` 或等价 transport/backend 证据
3. 再补 GIC / IOAPIC / MSI-X 侧的 route/controller 证据
4. 最后补 guest 侧“是否真正看到设备、是否真正可用”

## 8. 进入真实样本前的最低要求

1. 至少一份 restore 成功记录
2. 至少一份 backend 重连或 vring setup 记录
3. 至少一份 guest 侧设备可见性记录
4. 至少一份 controller restore 或 route/MSI-X/GIC/IOAPIC 证据

具体还缺哪些真实证据，已经单独列为：

- [missing-evidence.txt](./missing-evidence.txt)

## 9. 升级护栏

这份 seed 当前最容易被误判成 `real` 的情况是：

- 只有 `event == "restored"`
- 只有 transport/notifier 证据
- 或只有文档/测试派生的成功基线

这些都还不够。

只有当同一批证据同时覆盖：

1. restore 成功
2. transport/notifier 重建
3. controller restore 状态
4. guest-visible 结果

才应该考虑升级。

如果下一轮已经拿到一包真实日志，建议先对照：

- [minimum-log-bundle.txt](./minimum-log-bundle.txt)
- [decision-table.txt](./decision-table.txt)
- [bundle-template.txt](./bundle-template.txt)
