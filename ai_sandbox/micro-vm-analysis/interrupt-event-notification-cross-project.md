# 中断与事件通知跨项目专题分析

本文从源码比较当前四个重点项目的中断与事件通知路径：Firecracker、Cloud Hypervisor、Kata Containers、CubeSandbox。核心问题是：guest 如何通知 host 有新队列工作，host 设备完成后又如何把中断送回 guest。

这条路径连接 virtqueue、eventfd、ioeventfd、irqfd、MSI/MSI-X、IOAPIC/APIC、GIC/ITS 和 vCPU run loop。它决定设备延迟、vhost 后端接入、热迁移状态和架构差异。

> 项目级中断**状态恢复**专题（MsixConfig snapshot → VirtioPciDevice restore → GIC/IOAPIC route re-enable）见 [CubeSandbox 中断状态恢复链路](../CubeSandbox-sandbox-clone/analysis/interrupt-state-restore-chain.md)。

## 1. 通用模型

```mermaid
flowchart LR
    GuestDrv["guest virtio driver"] --> Notify["queue notify write"]
    Notify --> Ioeventfd["ioeventfd / queue EventFd"]
    Ioeventfd --> Worker["VMM or backend worker"]
    Worker --> Used["used ring update"]
    Used --> Interrupt["VirtioInterrupt / Interrupt group"]
    Interrupt --> Irqfd["irqfd EventFd"]
    Irqfd --> Route["KVM GSI routing"]
    Route --> Ctrl["IOAPIC/APIC or GIC/ITS"]
    Ctrl --> Vcpu["vCPU observes interrupt"]
```

通知链有两个方向。guest 到 host 通常是写通知寄存器，VMM 用 ioeventfd 或 queue eventfd 唤醒设备。host 到 guest 通常是设备写 irqfd，再由 KVM 根据 GSI/MSI 路由注入。

PCI/MSI-X 路径还多一层向量表。设备先看队列或配置对应的 vector，再检查 mask/PBA，然后写该 vector 的 eventfd。MMIO 路径通常只有共享 IRQ status 和单个中断事件。

## 2. 横向对照

| 项目 | host 通知入口 | guest 中断出口 | 控制器模型 | 架构差异核心 |
|---|---|---|---|---|
| Firecracker | MMIO/PCI queue eventfd，vhost-user 可拿 notifier | MMIO `IrqTrigger` 或 PCI `VirtioInterruptMsix` 写 eventfd | 直接维护 KVM GSI 路由和 irqfd | x86_64 用 IOAPIC/MSI；aarch64 用 GICv3/v2 和 FDT |
| Cloud Hypervisor | `VirtioTransport::ioeventfds` 注册到 VM | `InterruptManager` 创建 MSI group，Virtio PCI trigger vector | x86_64 IOAPIC；aarch64 GIC；riscv64 AIA | aarch64 GIC 支持 snapshot restore；x86_64 IOAPIC 作为 MMIO 设备 |
| Kata Containers | 不直接处理 queue event | 不直接注入 IRQ，交给 QEMU/CH/Firecracker 等 hypervisor | runtime 配置外部 hypervisor 的 IRQ 模式 | amd64 QEMU IOMMU 影响 kernel_irqchip；arm64 virt 不走 Intel IOMMU |
| CubeSandbox | Cloud Hypervisor 派生的 ioeventfd 注册 | `VirtioInterruptMsix` 通过 interrupt group 触发 | x86_64 IOAPIC；aarch64 GICv3 ITS | PVM/平台能力叠加在 CH-like VMM 上，ARM64 需关注 GIC/ITS 与 MSI 保留区 |

crosvm 当前暂停继续扩展，本文不作为主线对照对象，只在必要处保留历史背景。

## 3. Firecracker：抽象最薄，直接维护 GSI/irqfd

**设计取向**：设备不理解 APIC/GIC，只触发传输层给的 `VirtioInterrupt` 对象；VMM 直接维护 KVM GSI 路由与 irqfd。路径短、开销低，适合固定设备集。

### 3.1 guest→host notify（两条入口）

| transport | notify 注册 | 锚点 |
|---|---|---|
| MMIO | `register_mmio_virtio()` 把每个 queue eventfd 注册到 `NOTIFY_REG_OFFSET` | `device_manager/mmio.rs:175` |
| PCI | `VirtioPciDevice::register_notification_ioevent()` 把每个 queue eventfd 注册到 notification BAR | `transport/pci/device.rs:595` |

### 3.2 host→guest 中断（两条路径）

| 路径 | 机制 | 锚点 |
|---|---|---|
| MMIO | `IrqTrigger` 持 `irq_status` + `irq_evt`；`trigger_irq` 先设 config/vring bit，再 `irq_evt.write(1)` | `transport/mmio.rs:404-478` |
| PCI | `VirtioInterruptMsix` 绑 `MsixConfig` + config vector + queue vector + `MsixVectorGroup` | `transport/pci/device.rs:357-387` |

PCI 触发流程：按 `Config`/`Queue(index)` 找 vector → 未配置则返回 → 全局或 entry mask 则设 PBA → 否则 `vectors.trigger(vector)`。

### 3.3 GSI 路由与 irqfd

| 项 | 机制 | 锚点 |
|---|---|---|
| MSI 路由 | `Vm::register_msi` 写 `KVM_IRQ_ROUTING_MSI`；`set_gsi_routes` 把未 mask entry 提交 KVM | `vstate/vm.rs:428-487` |
| 顺序 | 先注册 route → `KVM_SET_GSI_ROUTING` → 启用 irqfd（注释：避免旧内核路由缺失时触发异常） | — |
| vector enable/disable | `MsixVectorGroup::trigger` 写 vector EventFd；`MsixVector::enable/disable` 调 `register_irqfd`/`unregister_irqfd` | `vstate/interrupts.rs:65-130` |

### 3.4 架构分流

| 架构 | 机制 | 锚点 |
|---|---|---|
| aarch64 GIC | 先 GICv3，fallback GICv2 | `arch/aarch64/gic/mod.rs:172-188` |
| `Vm::register_irq()` | 同为 `KVM_IRQ_ROUTING_IRQCHIP`；x86_64 设 `KVM_IRQCHIP_IOAPIC`，aarch64 设 `0`（交给 GIC） | `vstate/vm.rs` |

**能力边界**：路径短、适合低开销固定设备集；代价是没有通用中断管理层，扩展复杂设备需直接面对 GSI/MSI 细节。

## 4. Cloud Hypervisor：三层抽象（hypervisor trait / interrupt manager / transport）

**设计取向**：把中断拆成三层——KVM wrapper 提供 primitive、VMM `InterruptManager` 管 route/group、设备 transport 只用抽象。分层清楚，代价是调用链更长。

### 4.1 InterruptManager / InterruptSourceGroup

| 项 | 机制 | 锚点 |
|---|---|---|
| 抽象 | `InterruptManager` + `InterruptSourceGroup`：设备只需 create group、update route、trigger index、拿 notifier | `vm-device/src/interrupt/mod.rs:96-185` |
| route | `InterruptRoute` 分配 GSI + eventfd；`enable` 注册 irqfd，`trigger` 写 eventfd，`notifier` 返回克隆 eventfd | `vmm/src/interrupt.rs:28-87` |
| MSI group | `trigger(index)` 找 route 写 eventfd；`update` 由 group 调 `vm.make_routing_entry` 建 KVM route | `vmm/src/interrupt.rs:159-210` |

### 4.2 DeviceManager 依赖顺序

`DeviceManager` 先构造 MSI interrupt manager，再构造 IOAPIC 或 GIC——**依赖顺序**：IOAPIC/GIC 自身也需要 MSI manager（`vmm/src/device_manager.rs:1248-1258`）。

### 4.3 VirtioPciDevice 与 vhost-user

| 项 | 机制 | 锚点 |
|---|---|---|
| 创建 | 按队列数+1 分配 MSI-X vector，创建 `VirtioPciDevice`，遍历 `ioeventfds` 注册到 VM | `device_manager.rs:4215-4321` |
| 触发 | interrupt manager 生成 MSI group + `MsixConfig`；触发时解析 vector、检查 mask/PBA、调 `interrupt_source_group.trigger` | — |
| vhost-user 复用 notifier | `set_vring_call` 取 virtio interrupt notifier，`set_vring_kick` 取 queue eventfd | `vu_common_ctrl.rs:272-282` |

### 4.4 ARM64 restore 三个边界

| 边界 | 机制 | 锚点 |
|---|---|---|
| 创建即拉起 | `Gic::new()` 建 vGIC 并先建 legacy interrupt source group + `enable()` | `devices/src/gic.rs` |
| restore | `Gic::restore_vgic()` 先用恢复的 vCPU state 调 `set_gicr_typers()`，再写回 vGIC state | — |
| 编排 | aarch64 `add_interrupt_controller()` restore 场景下，controller 创建后立刻取 `saved_vcpu_states` 调 `restore_vgic(...)` | `device_manager.rs:1712-1757` |

x86_64 下 IOAPIC 插入 MMIO bus 与 device tree（`device_manager.rs:1801-1838`）。

**机制结论**：CH 在 ARM64 下不是"先有设备中断后补 GIC"的松散模式，而是明确依赖 `saved_vcpu_states → GICR_TYPER → vGIC state restore` 顺序。

## 5. Kata Containers：runtime 不注入 IRQ，只选模式

**设计取向**：不在 runtime 层实现 IRQ 注入，委托给 QEMU/CH/FC/Dragonball plugin，配置层选可用模式。边界是 runtime 语义——要知道何时需 split irqchip/IOMMU/VFIO/热插拔，但不复制 irqfd/MSI 路由逻辑。

### 5.1 Go runtime QEMU irqchip

| 项 | 机制 |
|---|---|
| amd64 | `splitIrqChipMachineOptions` = `accel=kvm,kernel_irqchip=split` |
| IOMMU 影响 | 普通 IOMMU 场景影响 kernel irqchip 选择 |

### 5.2 runtime-rs QEMU generator

| 项 | 机制 |
|---|---|
| irqchip | 保留 `kernel_irqchip` 字段 |
| IOMMU | `add_iommu` 设 `kernel_irqchip=split` |
| arm64 特例 | virt machine 不支持 Intel IOMMU，`add_iommu` 对 virt 只补 guest kernel 参数后返回（平台能力选择，非 IRQ 注入实现） |

### 5.3 Cloud Hypervisor plugin

`ch/inner_device.rs:651-652` 暴露 `use_generic_irq`/`use_shared_irq` 这类设备 IRQ 参数，**实际注入仍由 CH 执行**。

**能力边界**：要知道何时需 split irqchip/IOMMU/VFIO/热插拔，但不应把 QEMU/CH 的 irqfd/MSI 路由复制到 runtime。

## 6. CubeSandbox：CH 派生 + 平台语义 + ARM64 显式 GIC/ITS restore

**设计取向**：VMM 中断链路接近 CH，上层保证 snapshot/rollback、CubeVS、network-agent、CubeCoW 状态不破坏设备通知。ARM64 restore 比 CH 更显式，GIC/ITS snapshot 是硬前提。

### 6.1 KVM wrapper 与 DeviceManager

| 项 | 机制 | 锚点 |
|---|---|---|
| primitive | `create_irq_chip`/`register_irqfd`/`unregister_irqfd`；aarch64 `create_vgic` | `hypervisor/src/kvm/mod.rs` |
| split irq | x86_64 `enable_split_irq`：split irqchip 下只有 local APIC 在内核，PIC/IOAPIC 不在 | `kvm/mod.rs:677-690` |
| 依赖顺序 | `DeviceManager` 先 `add_interrupt_controller` 再构造 legacy interrupt manager；aarch64= `gic::Gic`，x86_64 = IOAPIC MMIO 设备 | — |

### 6.2 VirtioPciDevice（CH 风格）

| 项 | 机制 | 锚点 |
|---|---|---|
| 创建 | 按队列数+1 算 MSI-X vector，创建 `VirtioPciDevice`，注册每个 queue eventfd 为 ioeventfd | `device_manager.rs:3615-3714` |
| MSI group | interrupt manager 创建 MSI group + `MsixConfig` + `VirtioInterruptMsix` | `transport/pci_device.rs:419-503` |
| 触发 | queue/config → vector，mask/PBA 检查，`interrupt_source_group.trigger`；notifier 同 group | `transport/pci_device.rs:795-834` |

### 6.3 ARM64 GICv3 ITS

| 项 | 机制 | 锚点 |
|---|---|---|
| ITS device | 创建 ITS device | `gic/mod.rs:154-184` |
| 兼容字符串 | 暴露 `arm,gic-v3` + `arm,gic-v3-its` | `gic/mod.rs:272-283` |

### 6.4 ARM64 restore（比 CH 更显式）

CubeSandbox 不在 `DeviceManager` 里补一次 `restore_vgic()`，而是在 `vmm/src/vm.rs` 走专门的 `restore_vgic_and_enable_interrupt()`：

1. 从 `cpu_manager` 取恢复后的 vCPU states；
2. 显式 `create_vgic(...)`；
3. `init_pmu(...)`；
4. `set_gicr_typers(&saved_vcpu_states)`；
5. **要求存在 `GicV3Its snapshot`**，调用 `restore(...)` 写回 GIC/ITS 状态。

缺少 `GicV3Its snapshot` 时直接报错返回——**GIC/ITS snapshot 不是"最好有"，而是 restore 成立的硬前提**。完整链路见 [中断状态恢复专题](../CubeSandbox-sandbox-clone/analysis/interrupt-state-restore-chain.md)。

### 6.5 virtio-iommu MSI 保留区

`virtio-devices/src/iommu.rs:52-57` 注释说明必须提供 MSI 保留区，否则 guest driver 会定义 ARM 相关默认区并与 x86 冲突。

**能力边界**：差异不在单个 IRQ primitive，而在平台语义——VMM 中断链路接近 CH，上层保证 snapshot/rollback、CubeVS、network-agent、CubeCoW 不破坏设备通知。

## 7. ARM64 与 x86_64 差异

x86_64 主要对象：local APIC、IOAPIC、MSI/MSI-X、可选 split irqchip；CH/CubeSandbox 把 IOAPIC 建成 MMIO bus 设备。

ARM64 主要对象：GIC、GICv3 ITS、FDT 描述、MSI frame/ITS 路由；CH/CubeSandbox 都把 GIC 作为 aarch64 interrupt controller 并考虑 restore。

Firecracker 在 ARM64 创建 GICv3 失败后可 fallback GICv2；x86_64 围绕 IOAPIC 与 PCI/MSI-X。

**CH 与 CubeSandbox 在 ARM64 restore 上并不完全一样：**

| 项目 | ARM64 restore 模式 | 排查重点 |
|---|---|---|
| Cloud Hypervisor | `interrupt controller creation → restore_vgic(saved_vcpu_states, vgic_state)`，对齐 MSI/group/legacy routing 与 vGIC state | interrupt manager / route / vGIC state |
| CubeSandbox | `VM-level restore orchestration → create_vgic → init_pmu → set_gicr_typers → require GICv3 ITS snapshot → restore`，把 GIC/ITS restore 纳入 VM 恢复强约束 | VM restore 编排是否把 GIC/ITS restore 全部走完 |

这解释了为什么同样是 ARM64 "guest 无中断"，两边不该用同一套排查优先级。

Kata 差异更偏配置：amd64 QEMU 在 IOMMU 场景切 split irqchip；runtime-rs arm64 virt 直接避开 Intel IOMMU 路径。

## 8. 源码阅读顺序

按同一条因果链读四个项目，最有效：

1. transport 如何为 queue notify 建立 `ioeventfd` 或等价入口；
2. device activate 边界，确认 queue/eventfd/interrupt 在哪一起交给 worker；
3. worker 如何从 queue 取 descriptor 并落到 host backend；
4. used ring 更新后由谁决定 `prepare_kick` 或 `signal_used_queue`；
5. 外部 backend、snapshot/restore、ARM64/x86_64 差异是否改变这条主链。

| 项目 | notify 注册 | activate/worker | backend 与完成返回 | 边界重点 |
|---|---|---|---|---|
| Firecracker | `mmio.rs::register_mmio_virtio`；`pci/device.rs::ioeventfds` | `virtio/device.rs`、`queue.rs`、block/net 事件处理 | block `process_queue`、net TX/RX、`prepare_kick`、`interrupt_trigger()` | 内置 backend 为主；运行期更新窄；ARM64 主要变在 MMIO/FDT/GIC |
| Cloud Hypervisor | `VirtioPciDevice::ioeventfds()`；`DeviceManager::register_ioevent` | `ActivationContext`；block/net `activate()`；`spawn_virtio_thread()` | `signal_used_queue()`、`VirtioInterruptMsix`、`vu_common_ctrl.rs`、`vdpa.rs` | VMM 内 worker 与外部 vhost-user/vDPA 共存；迁移状态更重 |
| Kata | 不先找 queue；先看 `add_device()`/`HotplugAddDevice()` | hypervisor plugin 分发到 QEMU/CH/FC/Dragonball | guest agent 等待设备出现并做网络/存储配置 | Kata 只表达设备语义，不实现 virtqueue/irqfd |
| CubeSandbox | `pci_device.rs::ioeventfds()`；`device_manager.rs` 注册 | net/fs activate、`NetEpollHandler`/`FsEpollHandler` | `signal_used_queue()`、`VirtioInterruptMsix`、`VmSetFs` pending message | 既有 CH-like VMM 主链，又有 CubeShim/Cubelet 平台包装 |

**三个常见误读需排除：**

1. 别把"设备可 hotplug"误读成"自己实现了完整 virtqueue 数据路径"。Kata 是最典型反例——能 hotplug device，但 queue/interrupt 由下层 VMM 负责。
2. 别把"支持 vhost-user 或 vDPA"误读成"VMM 不再拥有数据路径主权"。CH 和 CubeSandbox 仍负责 queue/kick/call/notifier 绑定与恢复时设备拓扑/interrupt 重建。
3. 别把"activate 已发生"和"guest 已可见"混成一个判断。activate 只证明 queue/eventfd/interrupt 已移入 worker；guest 是否收敛还要看 backend、used ring、中断与 guest agent/driver 配置。

对 Kata 还要再收紧：`HotplugAddDevice succeeded` ≠ `guest-visible convergence completed`。

## 9. 判错与取证顺序

中断专题真正有价值的是把故障分层。一条 virtio I/O 完成链失效通常只卡在三处：

1. guest notify 没有正确进入 host；
2. host worker 已处理 descriptor，但没把完成写回 used ring；
3. used ring 已更新，但 interrupt 没被正确注入 guest。

| 层 | 先看什么 | 典型证据 |
|---|---|---|
| notify 入口 | `ioeventfd` 是否注册，queue eventfd 是否进 worker epoll | FC `register_mmio_virtio`/PCI `ioeventfds`；CH `VirtioTransport::ioeventfds()`；Cube `device_manager.rs` 注册 |
| worker 执行 | eventfd 是否被消费，descriptor 是否被 pop，backend 是否执行 | FC block `process_queue`；CH `BlockEpollHandler`/`NetEpollHandler`；Cube `NetEpollHandler`/`FsEpollHandler` |
| 中断注入 | `prepare_kick`/`signal_used_queue` 后是否进 `VirtioInterrupt`，MSI-X mask/PBA/route 是否挡住 | FC `IrqTrigger`/`VirtioInterruptMsix`；CH `InterruptSourceGroup`；Cube `VirtioInterruptMsix` |
| guest 可见性 | guest 是否真收到中断并看到设备状态变化 | Kata/Cube 还要看 guest agent 等待与配置路径，避免把 guest 内配置误判成 IRQ 丢失 |

**实用判读**：block/net/pmem worker 已 `add_used(...)` 且 `prepare_kick()` 返回 true，但 guest 仍无进展 → 优先看 `VirtioInterrupt → irqfd/MSI-X route`；连 `prepare_kick()` 都没走到 → 不要先怀疑 GIC 或 MSI-X。

**ARM64 额外伪失败**：queue、notifier、backend 都正常，但 `saved_vcpu_states / GICR_TYPER / GICv3 ITS snapshot` 这条 restore 顺序没闭合，导致设备完成无法稳定送达 guest。

**Kata 最易误判**：很多"中断没到 guest"其实已越过 VMM interrupt 层，卡在 guest 内设备发现、agent 等待、route/interface 配置。

## 10. 横向验证重点

最值得补三类跨项目验证点：

1. notify 已进 host，但 worker 还没处理；
2. worker 已处理并写 used ring，但 vector/route/mask 把中断挡住；
3. guest 实际已收到设备更新，但 guest 内配置收敛慢，被误判成 IRQ 故障。

| 项目 | 最该补的验证点 |
|---|---|
| Firecracker | MMIO 与 PCI 两条中断路径在 restore 后是否仍保持一致的 `irqfd`/route 重建结果 |
| Cloud Hypervisor | vhost-user/vDPA 用 notifier 后，route、mask、GIC/IOAPIC restore 是否仍一致 |
| Kata | plugin 之后，guest agent 的等待与设备配置何时会伪装成 IRQ 问题 |
| CubeSandbox | 平台层 `VmAddDevice`/`VmSetFs` 与底层 interrupt/notifier 的实际联动是否完整，是否存在"控制面成功、guest 不可见"的断层 |

**CH + CubeSandbox 交叉线硬结论：**

1. CH 的 vhost-user/vDPA 后端不自己定义中断路由，只复用 `virtio_interrupt.notifier()` 暴露的 eventfd。
2. restore 后"backend 正常、guest 无中断" → 优先怀疑 `VirtioPciDevice` transport state、MSI-X mask/PBA、`InterruptSourceGroup` route 或 GIC/IOAPIC 恢复顺序，而非 backend 本身。
3. ARM64 下 CH 还要看 `saved_vcpu_states → set_gicr_typers → restore_vgic` 是否完整。
4. CubeSandbox 底层沿用同 irqfd/notifier 模式，但额外插入 `ApiRequest`、`NotifyEvent`、`VmSetFs`、TAP fd passing 与 guest ready 判定。
5. ARM64 restore 下 CubeSandbox 要求 `create_vgic → init_pmu → set_gicr_typers → restore GICv3 ITS snapshot` 全部成立；任一步缺失都可能伪装成普通 virtio 中断故障。
6. 叠加 native virtio-fs `back_state` 恢复、普通 net 的 TAP/tap fd 重绑后，CubeSandbox 更易出现"控制面已恢复、数据面或中断可见性尚未闭环"。

**样本资产：**

- [Cloud Hypervisor backend/notifier/restore checklist seed](./samples/ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md)
- [CubeSandbox guest-visible restore checklist seed](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md)
- 现有 `real`/baseline：[CH backend/notifier/restore baseline real](./samples/ch-backend-notifier-restore-baseline-real-20260622/SUMMARY.md)、[CubeSandbox guest-visible restore baseline real](./samples/cubesandbox-guest-visible-restore-baseline-real-20260622/SUMMARY.md)、[CubeSandbox rollback `sandbox is not running` real](./samples/cubesandbox-rollback-sandbox-not-running-real-20260622/SUMMARY.md)

中断线当前已有成功基线，真正缺的是：CH 的失败类 `real`、CubeSandbox 的 guest-visible/ready/worker 闭环失败类 `real`。排查清单见 [CH 与 CubeSandbox：Restore 后 Guest 不可用验证清单](./ch-cubesandbox-restore-guest-unavailability-checklist.md)。

## 11. 下一步深入路线

项目级函数链均已展开：

- [Firecracker 中断与事件通知链路](../firecracker/analysis/interrupt-event-notification-chain.md)
- [Cloud Hypervisor 中断与事件通知链路](../cloud-hypervisor/analysis/interrupt-event-notification-chain.md)
- [Kata Containers 中断与事件通知委托链路](../kata-containers/analysis/interrupt-event-notification-chain.md)
- [CubeSandbox 中断与事件通知链路](../CubeSandbox-sandbox-clone/analysis/interrupt-event-notification-chain.md)
- [CubeSandbox Virtio 中断注入函数级链路](../CubeSandbox-sandbox-clone/analysis/virtio-interrupt-injection-trace.md)
- [CubeSandbox 中断状态恢复链路（MsixConfig snapshot → VirtioPciDevice restore → GIC/IOAPIC route re-enable）](../CubeSandbox-sandbox-clone/analysis/interrupt-state-restore-chain.md)

CubeSandbox 合并路线：[网络数据面与中断唤醒链路](../CubeSandbox-sandbox-clone/analysis/network-data-plane-interrupt-wakeup-chain.md)。
