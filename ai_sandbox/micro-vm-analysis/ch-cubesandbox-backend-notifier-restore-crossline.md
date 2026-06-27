# Cloud Hypervisor 与 CubeSandbox：Backend / Notifier / Restore 交叉线

本文聚焦一个容易在三条横线里重复出现、但又最容易说散的问题：

Cloud Hypervisor 与 CubeSandbox 在外部 backend、notifier 复用、restore 重建、guest-visible state 收敛上，到底是同一类问题，还是两类问题。

源码基线：当前工作树。

关联横线：

- [Virtio 传输与设备数据路径跨项目专题分析](./virtio-data-path-cross-project.md)
- [中断与事件通知跨项目专题分析](./interrupt-event-notification-cross-project.md)
- [存储、rootfs 与共享文件系统跨项目专题分析](./storage-rootfs-sharefs-cross-project.md)

## 1. 核心结论

Cloud Hypervisor 与 CubeSandbox 在底层 VMM 机制上确实是同一谱系。

它们都把：

1. queue notify
2. queue eventfd
3. virtio interrupt notifier
4. MSI-X / irqfd / controller route

收敛成一套由 transport 和 interrupt manager 持有的机制。

但两者在 restore 和 guest-visible state 的问题边界上并不完全相同。

Cloud Hypervisor 更偏：

VMM 设备拓扑、transport state、backend 重连是否成立

CubeSandbox 更偏：

平台控制面、当前节点后端资源、worker 唤醒、guest agent ready 和 mount/网络收敛是否重新闭环

这意味着同样一个“restore 成功但 guest 不可用”的症状，在两边的第一怀疑点并不相同。

## 2. 统一底座：backend 复用 VMM notifier，不接管中断拓扑

Cloud Hypervisor 的 vhost-user/vDPA 路径已经给出最清楚的证据。

vhost-user common controller 配置 vring 时，会从 `virtio_interrupt.notifier(Queue(index))` 取 eventfd，再传给 backend 的 `set_vring_call()`。

同一函数还把 queue eventfd 传给 `set_vring_kick()`。

证据：

- [cloud-hypervisor/virtio-devices/src/vhost_user/vu_common_ctrl.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/virtio-devices/src/vhost_user/vu_common_ctrl.rs:272)

vDPA 路径也是同一模式：`set_vring_call()`、`set_vring_kick()`、`set_config_call()` 都来自 transport/interrupt 侧已经准备好的 eventfd。

证据：

- [cloud-hypervisor/virtio-devices/src/vdpa.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/virtio-devices/src/vdpa.rs:282)

这说明一个重要边界：

外部 backend 接手的是 vring 实际消费，不是中断拓扑主权。

换句话说，backend 不自己发明 queue interrupt route。真正的 route、mask、MSI-X、GIC/IOAPIC 仍由 VMM 的 transport 和 interrupt manager 负责。

CubeSandbox 底层沿用同一模式。它同样由 `VirtioPciDevice`、interrupt source group 和 irqfd/controller 负责中断注入，平台层不直接改 queue 或 irq 路由。

证据：

- [CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/transport/pci_device.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/transport/pci_device.rs:795)
- [CubeSandbox-sandbox-clone/hypervisor/vmm/src/interrupt.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/vmm/src/interrupt.rs:28)

## 3. Cloud Hypervisor：更像设备拓扑与 backend 重连问题

Cloud Hypervisor 的 restore 重点是把 transport、device tree 和 controller state 重建回来。

`VirtioPciDevice::snapshot()` 会保存：

1. `VirtioPciDeviceState`
2. PCI configuration
3. virtio common config
4. MSI-X state

证据：

- [cloud-hypervisor/virtio-devices/src/transport/pci_device.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/virtio-devices/src/transport/pci_device.rs:1305)

中断控制器也单独 snapshot/restore：

- aarch64 GIC：保存 VGIC state，restore 时调用 `restore_vgic()`
- x86_64 IOAPIC：保存 redirection entries，restore 时重建 routing

证据：

- [cloud-hypervisor/devices/src/gic.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/devices/src/gic.rs:158)
- [cloud-hypervisor/vmm/src/device_manager.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/vmm/src/device_manager.rs:1728)
- [cloud-hypervisor/devices/src/ioapic.rs](/home/lyq/Projects/Micro-VM/cloud-hypervisor/devices/src/ioapic.rs:445)

这意味着对 Cloud Hypervisor 来说，如果出现：

restore 成功，backend 看起来也在线，但 guest 设备或中断异常

更应该先查：

1. `VirtioPciDevice` transport state 是否重建正确
2. MSI-X mask/PBA/vector 是否一致
3. `InterruptSourceGroup` route 是否恢复正确
4. GIC / IOAPIC restore 顺序与 state 是否完整
5. 外部 backend socket / protocol feature / vring base 是否与原状态一致

而不是先怀疑 guest agent，因为 CH 本身没有固定 guest agent 路径。

## 4. CubeSandbox：更像平台闭环与当前节点资源重绑问题

CubeSandbox 在 VMM 内部有同样的 transport/notifier/irqfd 机制，但平台层额外插入了更多状态。

例如 `VmSetFs` 并不直接改 queue。

它通过 CubeShim 发送 `ApiRequest::VmSetFs`，VMM 再把 `FsEvent` 放入 pending message 并唤醒 fs worker。

证据：

- [CubeSandbox-sandbox-clone/CubeShim/shim/src/hypervisor/cube_hypervisor.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/CubeShim/shim/src/hypervisor/cube_hypervisor.rs:185)
- [CubeSandbox-sandbox-clone/hypervisor/vmm/src/device_manager.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/vmm/src/device_manager.rs:1173)

virtio-net 的 host TAP 也不是简单固定资源。

普通 restore / 启动路径下，当前节点要重新提供 TAP 或 tap fd；`NetEpollHandler` 消费的是当前节点重新绑定出来的 queue eventfd 和 TAP fd。

证据：

- [CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/net.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/net.rs:694)
- [CubeSandbox-sandbox-clone/analysis/network-data-plane-interrupt-wakeup-chain.md](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/analysis/network-data-plane-interrupt-wakeup-chain.md:4)

native virtio-fs restore 比 net 更进一步。它不仅恢复 transport，还会尝试把 backend server 的 `back_state` 反序列化并重新应用到当前 server。

证据：

- [CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/fs.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/fs.rs:916)
- [CubeSandbox-sandbox-clone/analysis/virtio-net-fs-restore-chain.md](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/analysis/virtio-net-fs-restore-chain.md:1)

所以在 CubeSandbox 里，同样一个“restore 成功但 guest 不可用”的症状，更常见的优先怀疑点是：

1. 当前节点后端资源有没有重新绑定成功
2. `VmSetFs` / `VmAddDevice` 是否真的唤醒了 worker
3. guest agent 是否真的看见了设备并完成 mount / 网络配置
4. ready/notify 语义是否已经重新闭环

## 5. 三条横线里的落点差异

同一个交叉线，在三条横线里关注点不一样。

| 横线 | Cloud Hypervisor | CubeSandbox |
|---|---|---|
| 存储 | 更偏 device tree、backend socket、transport state 是否恢复 | 更偏 `StorageInfo -> VmSetFs -> agent mount -> ready` 是否重收敛 |
| I/O 虚拟化 | 更偏 `kick/call/notifier` 是否仍绑定同一 vring 语义 | 更偏控制面更新是否真的传导到 worker 与 guest-visible state |
| 中断虚拟化 | 更偏 route/mask/controller restore | 更偏 irqfd/notifier 正常但平台闭环没完成时的伪故障 |

这也是为什么不能把两边的故障都简单称成“backend 问题”。

在 CH 里，“backend 问题”往往真的是 transport/notifier/backend 重连问题。

在 CubeSandbox 里，“backend 问题”常常只是表象，真正断的可能是平台层状态传播和 guest 可见性闭环。

## 6. 推荐验证顺序

如果后续继续补真实样本或验证清单，推荐按下面顺序推进。

### Cloud Hypervisor

1. 先验证 `set_vring_call()` / `set_vring_kick()` / `set_config_call()` 的 eventfd 是否来自同一 notifier 模型
2. 再验证 `VirtioPciDevice::snapshot()` 和 controller snapshot 是否把 transport / MSI-X / route 保存完整
3. 最后验证 restore 后 guest 是否真的重新收到 interrupt 或重新看到设备

### CubeSandbox

1. 先验证控制面请求是否真的触发 `VmSetFs` / `VmAddDevice`
2. 再验证 worker 是否被唤醒、当前节点资源是否已重绑
3. 最后验证 guest agent 是否真的看到设备并完成 mount / 网络配置 / ready 收敛

## 7. 后续入口

这条交叉线后续如果继续扩，最自然的下一步有两条：

1. 拆一份更偏验证清单的专题，把 CH 与 CubeSandbox 各自的 `restore 后 guest 不可用` 证据链列成 checklist
2. 基于现有样本体系，分别为：
   - `Cloud Hypervisor backend/notifier/restore`
   - `CubeSandbox guest-visible state after restore/update`
   
   建两份样本模板或 seed
