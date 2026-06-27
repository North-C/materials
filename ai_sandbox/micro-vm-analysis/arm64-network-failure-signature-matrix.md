# ARM64 网络失败签名总表

本文承接 [ARM64 网络验证与观测总表](./arm64-network-validation-observation-matrix.md)。

前一篇回答“各项目该先验证哪一层、先看哪类信号”。

本文继续把这些材料压成更直接的“失败签名矩阵”。

目标不是解释所有原理。

目标是让看到一条错误文本时，能立刻知道它更可能属于哪一层，应优先回看哪篇项目文档。

源码基线：当前工作树。

## 1. 核心结论

四个项目当前已经能归纳出三类 ARM64 网络失败签名：

1. host backend 层：
   TAP、vhost、fd、tc/eBPF attach、IOMMU segment 组合失败。
2. guest 枚举层：
   FDT/GIC/PCI host bridge、guest PCI/sysfs 路径发现失败。
3. guest/config 收敛层：
   agent `UpdateInterface/Routes`、平台 `config net`、restore 首包唤醒失败。

这三类失败不能混看。

同样是“guest 没网”，在 Firecracker 里更可能是 TAP/FDT/GIC；

在 Cloud Hypervisor 里更可能是 `add_net` 之后的 guest 枚举；

在 Kata 里更可能是 guest agent PCI 路径与 hotplug；

在 CubeSandbox 里更可能还要加上 eBPF/TC 和平台配网收敛。

## 2. 总体矩阵

| 项目 | 最典型失败签名 | 所属层级 | 首选回看文档 |
|---|---|---|---|
| Firecracker | `TapOpen` / `TapSetVnetHdrSize` / `undo_pop` 相关 net 异常 | host backend / queue | [virtio-net-data-path-chain](../firecracker/analysis/virtio-net-data-path-chain.md) |
| Cloud Hypervisor | `Error when adding new network device to the VM` / `InvalidIommuHotplug` / `TapEnable` | host config / backend | [arm64-network-observation-guide](../cloud-hypervisor/analysis/arm64-network-observation-guide.md) |
| Kata | `unrecognised machinetype` / `Arm64 architecture does not support vIOMMU` / `update interface request failed` / `interface not available` | machine / agent path | [arm64-network-observation-guide](../kata-containers/analysis/arm64-network-observation-guide.md) |
| CubeSandbox | `can't load mvmtap` / `tcnl.Filter.Replace failed` / `wait a pci` / `create sandbox!, config net` 失败 | eBPF/TC / guest config | [arm64-network-observation-guide](../CubeSandbox-sandbox-clone/analysis/arm64-network-observation-guide.md) |

## 3. Firecracker：失败签名

Firecracker 的 net 设备构造一开始就会在 `Net::new()` 中打开 TAP。

典型失败签名包括：

1. `TapOpen`
2. `TapSetVnetHdrSize`

源码依据：[virtio-net device.rs](../firecracker/src/vmm/src/devices/virtio/net/device.rs#L328)。

运行时另一个值得区分的信号是：

`tx_queue.undo_pop()`

它出现在 rate limiter token 不足时。

源码依据：[virtio-net device.rs](../firecracker/src/vmm/src/devices/virtio/net/device.rs#L716)。

这类信号不是“设备创建失败”。

它更像数据面被限速阻塞，因此不能误判成 guest 枚举问题。

Firecracker 还有一类项目独有签名是 MMDS 相关。

例如帧被 MMDS 消费、MMDS 数据存储未初始化等。

源码依据：[virtio-net device.rs](../firecracker/src/vmm/src/devices/virtio/net/device.rs#L497)。

所以对 Firecracker，先要区分：

1. TAP/backend 创建失败
2. 队列被限速回退
3. MMDS 分流导致的特殊行为

## 4. Cloud Hypervisor：失败签名

Cloud Hypervisor 的第一类失败签名来自 `vm_add_net()`。

它会直接记录：

`Error when adding new network device to the VM: ...`

源码依据：[vmm/src/lib.rs](../cloud-hypervisor/vmm/src/lib.rs#L2365)。

第二类高价值签名是：

`InvalidIommuHotplug`

它说明问题还在设备模型组合层，没有进入 guest 枚举。

源码依据：[vmm/src/device_manager.rs](../cloud-hypervisor/vmm/src/device_manager.rs#L5019)。

第三类失败来自 tap/backend：

1. `TapOpen`
2. `TapEnable`
3. `MultiQueueNoTapSupport`
4. `MultiQueueNoDeviceSupport`

源码依据：[open_tap.rs](../cloud-hypervisor/net_util/src/open_tap.rs#L14)。

对 Cloud Hypervisor 而言，看到这些错误时，不该先去看 guest。

只有 host 这层过了，才值得继续看 FDT/GIC/guest `virtio-device activated`。

## 5. Kata Containers：失败签名

Kata ARM64 的最早失败签名几乎都很直白。

第一类是 machine 选择：

`unrecognised machinetype: ...`

源码依据：[qemu_arm64.go](../kata-containers/src/runtime/virtcontainers/qemu_arm64.go#L52)。

第二类是 IOMMU：

`Arm64 architecture does not support vIOMMU`

源码依据：[qemu_arm64.go](../kata-containers/src/runtime/virtcontainers/qemu_arm64.go#L117)。

第三类是 endpoint/hotplug 阶段。

典型信号包括：

1. `waiting for network interfaces in namespace`
2. `no network interfaces found after timeout`
3. `configuring hotplugged network in guest`

源码依据：[sandbox.go](../kata-containers/src/runtime/virtcontainers/sandbox.go#L353)。

第四类是 agent 收敛失败：

1. `update interface request failed`
2. `update routes request failed`
3. `interface not available: ...`

源码依据：[kata_agent.go](../kata-containers/src/runtime/virtcontainers/kata_agent.go#L621)，[agent rpc.rs](../kata-containers/src/agent/src/rpc.rs#L1122)。

第五类来自 backend 差异：

1. `QMP not initialized`
2. `open named tuntap`
3. `insert network device`

源码依据：[qemu/inner.rs](../kata-containers/src/runtime-rs/crates/hypervisor/src/qemu/inner.rs#L837)，[ch/inner_device.rs](../kata-containers/src/runtime-rs/crates/hypervisor/src/ch/inner_device.rs#L387)。

另见：[dragonball/inner_device.rs](../kata-containers/src/runtime-rs/crates/hypervisor/src/dragonball/inner_device.rs#L280)。

Kata 的特点是：

同样一句“guest 没网”，可能分别对应 machine、endpoint、agent、backend 四层。

## 6. CubeSandbox：失败签名

CubeSandbox 的失败签名层次最多。

第一类来自 ARM64 eBPF loader：

1. `can't load localgw`
2. `can't load mvmtap`
3. `can't load nodenic`

源码依据：[bpf_arm64.go](../CubeSandbox-sandbox-clone/CubeNet/cubevs/bpf_arm64.go#L16)。

第二类来自 TC attach：

1. `tc.Open failed`
2. `tcnl.Qdisc.Add failed`
3. `tcnl.Filter.Replace failed`

源码依据：[tc.go](../CubeSandbox-sandbox-clone/CubeNet/cubevs/tc.go#L16)。

第三类来自 host 网络资源：

`network-agent newTap attach filter failed`

源码依据：[netdevice.go](../CubeSandbox-sandbox-clone/network-agent/internal/service/netdevice.go#L394)。

第四类来自 guest 侧收敛：

1. `wait a pci`
2. `Failed to update interface/routes`
3. `create sandbox!, config net`

这些签名本身已经在项目级文档中分层解释过。

因此 CubeSandbox 的典型误判，是把平台级 one-click/E2E PASS 当成这些中间层也已经完全有证据。

## 7. 失败签名按层级重排

如果不按项目，而按失败层级重排，可以得到这张表。

| 层级 | Firecracker | Cloud Hypervisor | Kata | CubeSandbox |
|---|---|---|---|---|
| host backend | `TapOpen` | `TapOpen` / `TapEnable` | `open named tuntap` | `tc.Open` / `Filter.Replace` / `newTap attach filter failed` |
| machine/device model | FDT/GIC 描述异常 | `InvalidIommuHotplug` | `unrecognised machinetype` / `does not support vIOMMU` | FDT/GIC + eBPF/TC 组合异常 |
| guest 枚举 | guest 不见 virtio-net | guest 无 `virtio-device activated` | `interface not available` | `wait a pci` 失败 |
| guest 配网收敛 | 不适用固定 agent | 不适用固定 agent | `update interface request failed` / `update routes request failed` | `config net` 失败 |
| restore/唤醒 | net state/MMDS/queue 恢复异常 | GIC state / guest 枚举恢复异常 | 取决于 runtime + backend | `gic-v3-its` / 首包不醒 |

这张表的用途，是帮后续失败样本归档时少走弯路。

看到一条错误，先归层，再回项目。

比直接在四个项目里盲搜更快。

## 8. 推荐的签名归档方式

后续如果继续补失败样本，建议每个样本至少记录：

1. 原始错误文本
2. 触发阶段
3. 所属层级
4. 回看的项目级文档
5. 最终归因

这五项比只截一段日志更有价值。

因为它能直接和现有矩阵、观测指南、验证总表互相引用。

## 9. 结论

现在四个项目的 ARM64 网络材料，已经不只是“能力矩阵”和“观测顺序”。

再加上这张失败签名总表，后续碰到真实日志时，已经可以直接做结构化归档。

下一步最值得做的，不再是扩展抽象框架。

而是按这张表去补真实失败样本，让每个项目至少有一到两个能和这些签名对上的案例。
