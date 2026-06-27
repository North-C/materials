# ARM64 网络测试与取证命令总表

本文承接 [ARM64 网络验证与观测总表](./arm64-network-validation-observation-matrix.md) 和 [ARM64 网络失败签名总表](./arm64-network-failure-signature-matrix.md)。

前两篇已经回答：

1. 四个项目各自该验证哪一层
2. 看到哪类错误文本应先回看哪篇文档

本文继续把它们落到最直接的一层：

真正做 ARM64 网络验证或取证时，可以先跑哪些命令、这些命令能证明到哪一层、又不能证明到哪一层。

源码基线：当前工作树。

## 1. 核心结论

当前四个项目能稳定抽出的 ARM64 网络取证命令，大致分成三类：

1. host backend 命令
   例如 `ip link`、`ethtool`、tap 数量检查、`/readyz`。
2. guest 设备与中断命令
   例如 `ip link`、`ip route`、`/proc/interrupts`、guest 内执行简单命令。
3. 平台级诊断脚本
   例如 `quickcheck.sh`、`cube-diag/check-procs.sh`、`collect-logs.sh`。

这些命令很有用，但它们证明的层级不同。

最容易出错的地方不是“没跑命令”。

而是把本来只证明 host 进程 ready 的命令，误当成 guest 网络或平台网络已经 ready。

## 2. 总体矩阵

| 命令类型 | 典型命令 | 更适合的项目 | 能证明什么 | 不能证明什么 |
|---|---|---|---|---|
| host tap/interface | `ip link` / `ip link show` | Firecracker / Cloud Hypervisor / CubeSandbox | host 接口是否存在、是否 up | guest 是否看见设备 |
| host offload/feature | `ethtool` | Cloud Hypervisor / crosvm 背景 | host backend 是否按预期配置 | guest 路由和 IP 是否正确 |
| guest interface | `ip link` / `ip route` | Kata / CubeSandbox | guest 内接口和路由状态 | host eBPF/TC 是否正确 |
| guest interrupts | `grep ... /proc/interrupts` | Cloud Hypervisor / Firecracker | guest 中断控制器和设备中断是否可见 | 应用层业务是否可用 |
| runtime/platform ready | `/readyz`、healthz、quickcheck | CubeSandbox | 控制面/进程级 ready | 中间层数据面与 guest 配网 |
| structured log collection | `collect-logs.sh` | CubeSandbox | 保存多模块证据 | 不会自动判断哪个层先失败 |

## 3. Firecracker：建议的最小命令组

Firecracker 当前最值得配合项目级文档使用的，不是复杂脚本，而是围绕 TAP、MMDS 和 guest 可见性的最小命令组。

第一组是 host 侧接口命令。

例如：

1. `ip link show <host_dev_name>`
2. `ip link show type tuntap`

它们更适合确认 `Tap::open_named()` 指向的接口是否真实存在。

源码依据：[virtio-net-data-path-chain.md](../firecracker/analysis/virtio-net-data-path-chain.md)。

第二组是 guest 侧设备/中断命令。

例如：

1. guest 内 `ip link`
2. guest 内 `/proc/interrupts`

Firecracker 项目内没有像 Cloud Hypervisor 那样现成的 ARM64 `/proc/interrupts` helper 常量。

但从能力边界上看，这仍是确认 FDT/GIC 路径是否真正闭环的最直接入口。

第三组是 MMDS 相关命令。

如果场景启用了 MMDS，则要把：

1. host 上“没看到帧”
2. guest 里能访问 metadata

这两类现象一起看，避免把 MMDS 分流误判成发包失败。

## 4. Cloud Hypervisor：建议的最小命令组

Cloud Hypervisor 项目里已经给出一部分现成命令锚点。

最直接的是 ARM64 guest `/proc/interrupts` 检查：

1. `grep -c 'GICv3.*uart-pl011' /proc/interrupts || true`
2. `grep -c 'GICv3.*arm-pmu' /proc/interrupts || true`

源码依据：[tests/common/utils.rs](../cloud-hypervisor/cloud-hypervisor/tests/common/utils.rs#L2271)。

虽然这两条不是专门给网络设计的，但它们明确说明了：

Cloud Hypervisor ARM64 的验证思路本来就包含 guest 中断观测。

第二组是 host tap/interface 命令。

测试代码里直接用了：

1. `ip link | grep -c mytap42`
2. `sudo ip link set up dev ...`

源码依据：[tests/integration.rs](../cloud-hypervisor/cloud-hypervisor/tests/integration.rs#L8222)，[tests/common/utils.rs](../cloud-hypervisor/cloud-hypervisor/tests/common/utils.rs#L418)。

第三组是 guest 设备激活后的基础命令。

测试注释多次写到：

`Check the guest virtio-devices, e.g. ... net`

源码依据：[tests/integration.rs](../cloud-hypervisor/cloud-hypervisor/tests/integration.rs#L5861)。

这说明 Cloud Hypervisor 的最小命令组应该是：

1. host 侧 tap/interface
2. guest 侧 `/proc/interrupts`
3. guest 侧 virtio-net 是否出现

而不是只看 `vm_add_net()` 成功。

## 5. Kata Containers：建议的最小命令组

Kata 的 host 侧关键命令，其实大多隐藏在 runtime 日志和 agent 错误文本里。

因此这里比命令更重要的是“最小观测动作”：

1. 确认 machine type 与 IOMMU 组合
2. 确认 endpoint 是否被发现
3. 确认 agent 是否成功 `UpdateInterface` / `UpdateRoutes`

从 guest 侧来说，最直接的命令仍然是：

1. guest 内 `ip link`
2. guest 内 `ip route`

因为 Kata 的网络 ready 边界在 agent 应用 guest 网络状态成功，而不只是 VMM 设备可见。

从源码里看，`updateInterface` 和 `updateRoutes` 是最关键的失败点。

源码依据：[arm64-network-observation-guide.md](../kata-containers/analysis/arm64-network-observation-guide.md)。

因此对 Kata，命令/观测更像：

1. host 日志里找 machine/IOMMU/endpoint/hotplug 错误
2. guest/agent 侧看 interface 与 route 最终状态

## 6. CubeSandbox：建议的最小命令组

CubeSandbox 已经在 one-click 和诊断脚本里给出最完整的现成命令入口。

第一组是 health/ready：

1. `curl -fsS http://127.0.0.1:19090/healthz`
2. `curl -fsS http://127.0.0.1:19090/readyz`

源码依据：[quickcheck.sh](../CubeSandbox-sandbox-clone/deploy/one-click/scripts/one-click/quickcheck.sh#L87)，[arm64-network-evidence-template.md](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-template.md)。

第二组是诊断进程与 socket：

`cube-diag/check-procs.sh`

它会检查 network-agent 端口、`/readyz` 和 socket 是否都存在。

源码依据：[check-procs.sh](../CubeSandbox-sandbox-clone/deploy/one-click/scripts/cube-diag/check-procs.sh#L248)。

第三组是完整日志采集：

`collect-logs.sh`

它能把：

1. `network-agent`
2. `Cubelet`
3. `CubeShim`
4. `CubeVmm`
5. `runtime`
6. `dmesg`
7. `env`

这些证据一次收回来。

源码依据：[collect-logs.sh](../CubeSandbox-sandbox-clone/deploy/one-click/scripts/cube-diag/collect-logs.sh#L1)。

因此 CubeSandbox 的最小命令组是四个项目里最完整的。

但它的局限也一样明确：

`/readyz` 和 `quickcheck` 只能证明控制面和进程级 ready，不能单独证明 CubeVS/TC/FDT/GIC/guest `eth0` 已闭环。

## 7. 命令按层级重排

如果不按项目，而按验证层级重排，可以得到下面这张表。

| 层级 | 优先命令 | 典型项目 |
|---|---|---|
| host backend | `ip link` / `ethtool` / tap 数量检查 | Firecracker / Cloud Hypervisor / CubeSandbox |
| guest 中断 | `grep ... /proc/interrupts` | Cloud Hypervisor / Firecracker |
| guest 网络状态 | `ip link` / `ip route` | Kata / CubeSandbox |
| 进程级 ready | `healthz` / `readyz` / quickcheck | CubeSandbox |
| 全量取证 | `collect-logs.sh` | CubeSandbox |

这张表最重要的用途，是防止命令和问题层级错配。

例如：

1. `ip link` 证明不了 guest agent 配网已成功。
2. `/readyz` 证明不了 virtio-net 中断已闭环。
3. `/proc/interrupts` 证明不了业务流量一定通。

## 8. 推荐的最小组合

如果要做一次尽量轻量、但又不至于过窄的 ARM64 网络验证，建议最小组合如下。

对 VMM 项目：

1. host `ip link`
2. guest `ip link`
3. guest `/proc/interrupts`

对 Kata：

1. host runtime 日志
2. guest `ip link`
3. guest `ip route`

对 CubeSandbox：

1. `quickcheck.sh`
2. `cube-diag/check-procs.sh`
3. `collect-logs.sh`

这样至少可以同时覆盖：

1. host 资源
2. guest 设备
3. 中断或配网状态

## 9. 结论

现在四个项目在 ARM64 网络研究上，已经不缺“从哪里开始”的框架。

更缺的是把这些框架落成一套一致的取证动作。

这份命令总表的作用，就是把前面已经写好的边界矩阵、观测指南和失败签名，压缩成最实用的动作入口。

下一步最有价值的工作，不是再补抽象表格。

而是按这份命令总表去补真实样本，把命令输出和失败签名绑定起来。 
