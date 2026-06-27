# ARM64 网络验证与观测总表

本文把当前四个项目范围内已经产出的 ARM64 网络材料横向对齐：

1. Firecracker
2. Cloud Hypervisor
3. Kata Containers
4. CubeSandbox

目标不是重复项目级结论。

目标是回答一个更实用的问题：

在 `arm64/aarch64` 上研究或验证网络时，四个项目分别要验证哪一层，最先该看哪类信号，又在哪一层最容易误判。

源码基线：当前工作树。

## 1. 核心结论

四个项目都谈“ARM64 网络”，但验证重点并不相同。

Firecracker 的重点是：

TAP、virtio-net、MMDS、FDT/GIC 与 snapshot state。

Cloud Hypervisor 的重点是：

`NetConfig`、virtio-pci、FDT/PCI host bridge、GICv3/ITS 与 guest 枚举。

Kata Containers 的重点是：

host endpoint、QEMU `virt` machine、guest agent PCI 路径发现，以及 runtime/backend capability。

CubeSandbox 的重点最重：

guest kernel、CubeVS/eBPF/TC、VMM FDT/GIC、guest `cube-agent` 配网、snapshot/restore 首包唤醒。

所以横向比较时，不能把“网络成功”的定义统一成同一句话。

VMM 项目主要关心设备与中断。

runtime/platform 项目还必须关心 guest 内接口状态，甚至 host 平台策略状态。

## 2. 总体对照

| 项目 | 网络真实层级 | ARM64 首要风险 | 最先应看的信号 | 最易误判点 |
|---|---|---|---|---|
| Firecracker | TAP + virtio-net + MMDS | FDT/GIC 描述与 transport | TAP 打开、virtio-net worker、FDT/GIC | 把 host TAP 成功当成 guest 网络 ready |
| Cloud Hypervisor | `NetConfig` + virtio-pci + guest 枚举 | FDT/GICv3/ITS 与 PCI host bridge | `vm_add_net`、tap/backend、`virtio-device activated` | 只看 `vm_add_net()` success |
| Kata Containers | host endpoint + VMM device + kata-agent | `virt` machine、vIOMMU 拒绝、guest PCI 路径 | machine/IOMMU、endpoint discovery、agent `updateInterface` | 只看 endpoint attach，不看 guest agent |
| CubeSandbox | guest kernel + CubeVS + VMM + guest agent + restore | eBPF/TC attach、FDT/GIC、`cube-agent` 配网 | `network-agent newTap`、`VsockServerReady`、`config net` | 只看 one-click/平台成功，不看中间层日志 |

## 3. Firecracker：验证与观测重点

Firecracker 的 virtio-net 数据面在 VMM 内部完成。

`Tap::open_named()` 打开 `/dev/net/tun`，`Net::new()` 把 TAP 交给 virtio-net 设备。

源码依据：[virtio-net-data-path-chain.md](../firecracker/analysis/virtio-net-data-path-chain.md)。

ARM64 风险不在 queue worker 逻辑本身，而在：

1. FDT 对设备和 GIC 的描述
2. guest 是否能发现并驱动设备
3. snapshot/restore 后的中断和网络状态是否还能闭环

Firecracker 的一个独特点是 MMDS。

普通网络帧与 MMDS 帧会在设备内部分流。

因此 Firecracker ARM64 网络最先应该区分：

1. TAP/virtqueue/TX/RX 是否正常
2. MMDS 分流是否影响行为判断

最易误判点是：

把 TAP 能打开、甚至 host 有帧流动，误当成 guest 内网络已经可用。

## 4. Cloud Hypervisor：验证与观测重点

Cloud Hypervisor 的 host 配置入口很统一。

`vm_add_net()`、`DeviceManager::add_net()`、`NetConfig` 在 ARM64 与 x86_64 上看起来几乎一样。

源码依据：[arm64-network-capability-matrix.md](../cloud-hypervisor/analysis/arm64-network-capability-matrix.md)。

但 ARM64 真正的边界在后面：

1. FDT 是否正确描述 devices/GIC/PCI host bridge
2. GICv3/ITS 是否承担 MSI 路径
3. guest 是否真正看到并激活了 virtio-net

Cloud Hypervisor ARM64 最先应看的信号是：

1. `vm_add_net()` 是否通过配置校验
2. TAP/backend 是否能打开并 enable
3. `virtio-device activated`

最易误判点是：

把 `vm_add_net()` 返回成功当成网络 ready，而没有继续确认 guest 枚举与中断返回。

## 5. Kata Containers：验证与观测重点

Kata 的控制面网络逻辑在两种架构上大体共享。

`LinuxNetwork.AddEndpoints()`、`Sandbox.AddInterface()`、agent `UpdateInterface/UpdateRoutes` 都不专为 ARM64 分叉。

源码依据：[network-endpoint-agent-chain.md](../kata-containers/analysis/network-endpoint-agent-chain.md)。

ARM64 风险主要在：

1. QEMU machine 被收敛为 `virt`
2. `appendIOMMU()` 明确拒绝 vIOMMU
3. guest agent 的 PCI/sysfs 根路径不是 x86 标准 root bus
4. runtime-rs backend 差异会把失败点推到不同位置

Kata ARM64 最先应看的信号是：

1. `unrecognised machinetype`
2. `Arm64 architecture does not support vIOMMU`
3. `waiting for network interfaces in namespace`
4. `update interface request failed`
5. guest `interface not available`

最易误判点是：

只看 host endpoint/hotplug 已成功，就断定 guest 网络一定能起。

## 6. CubeSandbox：验证与观测重点

CubeSandbox 是四者里网络边界最重的一个。

它不是只验证 virtio-net。

它至少同时要求：

1. guest ARM64 kernel 配置满足 BPF/TUN/virtio-net/GICv3 ITS
2. CubeVS ARM64 loader 能加载 eBPF object
3. TC filter 能挂到 TAP、node NIC、`cubegw0`
4. VMM 能用 FDT/GICv3/ITS 暴露设备与中断
5. guest `cube-agent` 能完成 `eth0`、route、ARP 配置
6. restore 后首包唤醒不丢

源码依据：[arm64-network-validation-matrix.md](../CubeSandbox-sandbox-clone/analysis/arm64-network-validation-matrix.md)。

CubeSandbox ARM64 最先应看的信号是：

1. `network-agent newTap ...`
2. `register cubevs tap`
3. `vm ready, vsock is listening`
4. `virtio-device activated`
5. guest `wait a pci`
6. `create sandbox!, config net`

最易误判点是：

把 one-click E2E 或平台级 PASS 当成中间层网络链路已经完整证实。

## 7. 四项目的“最小成功信号”对照

| 项目 | 最小成功信号 |
|---|---|
| Firecracker | guest 驱动已看到并驱动 virtio-net，且 TAP/queue path 与 MMDS 分流没有阻断 |
| Cloud Hypervisor | net device 被成功 hotplug，guest 通过 ARM64 FDT/GIC 路径看到并激活设备 |
| Kata Containers | host endpoint 被接入 VM，guest agent 成功执行 `UpdateInterface/UpdateRoutes` |
| CubeSandbox | `network-agent`、CubeVS、VMM、guest `cube-agent` 和 restore 首包唤醒全部闭环 |

这张表最重要的用途，是避免把 VMM 项目的成功信号套到 runtime/platform 项目上。

例如：

Cloud Hypervisor 的“设备激活”并不等于 Kata 的“guest 网络 ready”。

CubeSandbox 的“one-click PASS”也不等于底层网络链日志已经齐全。

## 8. 四项目的“最小失败信号”对照

| 项目 | 最小失败信号 |
|---|---|
| Firecracker | TAP 打开失败、FDT/GIC guest 不可见、restore 后网络状态异常 |
| Cloud Hypervisor | `InvalidIommuHotplug`、tap/backend enable 失败、无 `virtio-device activated` |
| Kata Containers | `unrecognised machinetype`、`does not support vIOMMU`、`update interface request failed` |
| CubeSandbox | `can't load ...`、`tc.Filter.Replace failed`、`wait a pci`/`config net` 失败、restore 后首包不醒 |

这张表也给出了一条通用规则：

越靠近 VMM 的项目，失败信号越偏设备和中断。

越靠近 runtime/platform 的项目，失败信号越偏 guest agent 与平台收敛。

## 9. 推荐的横向验证顺序

如果后续要在四个项目上统一做 ARM64 网络验证，建议顺序如下。

第一步：先确认 guest 设备发现主轴。

也就是区分：

1. Firecracker/Cloud Hypervisor：FDT/GIC/PCI host bridge
2. Kata：QEMU `virt` + guest agent PCI 路径
3. CubeSandbox：FDT/GIC + guest agent + host eBPF/TC

第二步：再确认 host backend。

也就是 tap/fd/vhost-user/vDPA 是否在该项目里真的是主路径。

第三步：再确认 guest 内网络 ready 的定义。

对 VMM 项目看“设备是否被 guest 驱动”。

对 Kata/CubeSandbox 看“接口和路由是否已被 guest agent 应用”。

第四步：最后再确认 restore/rollback 语义。

因为只有 CubeSandbox 和 Kata 在更高层真正暴露 runtime/platform 语义。

## 10. 观测方法总表

| 项目 | 优先文档 |
|---|---|
| Firecracker | [virtio-net-data-path-chain](../firecracker/analysis/virtio-net-data-path-chain.md)、[arch-arm64-x86-chain](../firecracker/analysis/arch-arm64-x86-chain.md) |
| Cloud Hypervisor | [arm64-network-capability-matrix](../cloud-hypervisor/analysis/arm64-network-capability-matrix.md)、[arm64-network-observation-guide](../cloud-hypervisor/analysis/arm64-network-observation-guide.md) |
| Kata Containers | [arm64-network-capability-matrix](../kata-containers/analysis/arm64-network-capability-matrix.md)、[arm64-network-observation-guide](../kata-containers/analysis/arm64-network-observation-guide.md) |
| CubeSandbox | [arm64-network-validation-matrix](../CubeSandbox-sandbox-clone/analysis/arm64-network-validation-matrix.md)、[arm64-network-observation-guide](../CubeSandbox-sandbox-clone/analysis/arm64-network-observation-guide.md)、[arm64-log-source-map](../CubeSandbox-sandbox-clone/analysis/arm64-log-source-map.md) |

## 11. 结论

现在这四个项目在 ARM64 网络上，已经形成了三种不同层级的验证口径：

1. Firecracker/Cloud Hypervisor：VMM 设备与中断口径
2. Kata：runtime + guest agent 口径
3. CubeSandbox：平台 + guest agent + host eBPF/TC 口径

后续再继续深入时，最值得做的不是再写第四套抽象框架。

而是把这些口径逐步补成“失败样本记录”或“实测记录”，让每条路线都既有源码结构，也有落地证据。
