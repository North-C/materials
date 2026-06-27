# ARM64 网络样本成熟度矩阵

本文承接 [ARM64 网络验证与观测总表](./arm64-network-validation-observation-matrix.md)、[ARM64 网络失败签名总表](./arm64-network-failure-signature-matrix.md) 和 [ARM64 网络测试与取证命令总表](./arm64-network-test-observation-command-matrix.md)。

前面三篇已经把：

1. 验证层级
2. 失败签名
3. 可直接执行的命令

都梳理清楚了。

本文继续回答最后一个很实际的问题：

这四个项目里，哪个已经有“真实 ARM64 网络样本”，哪个还只有源码原型，后续应优先在哪补实样。

源码基线：当前工作树。

## 1. 核心结论

当前四个项目在 ARM64 网络这条线上，样本成熟度并不一样。

可以粗分为三档：

第一档：已有平台级成功样本，且仓库里留有故障线索。

目前只有 CubeSandbox 达到这一档。

第二档：已有清晰的测试命令、失败原型，且部分项目已经进入“准样本”阶段，但缺少成套 ARM64 真实失败样本。

Firecracker、Cloud Hypervisor、Kata Containers 都属于这一档。

第三档：只有源码边界，没有现成命令或样本。

当前四个项目在网络线上已经没有落在这一档的。

这意味着后续工作的优先级已经很清楚：

不要再扩抽象框架。

应该把第二档的项目补成带真实日志的失败样本，把第一档的项目补成更完整的中间层证据样本。

## 2. 总体矩阵

| 项目 | 能力边界文档 | 观测指南 | 失败原型 | 现成命令/测试锚点 | 准样本状态 | 真实 ARM64 样本成熟度 |
|---|---|---|---|---|---|---|
| Firecracker | 有 | 有 | 有 | 有基础命令与源码锚点 | 有 | 低 |
| Cloud Hypervisor | 有 | 有 | 有 | 有 guest `/proc/interrupts` 与 tap 命令锚点 | 有 | 低 |
| Kata Containers | 有 | 有 | 有 | 有 runtime/agent/backend 错误锚点 | 有 | 低 |
| CubeSandbox | 有 | 有 | 有 | 有 `quickcheck`/`cube-diag`/`collect-logs` | 有真实样本/模板 | 中 |

## 3. Firecracker：成熟度判断

Firecracker 现在已经有三层文档：

1. [ARM64 网络能力边界矩阵](../firecracker/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../firecracker/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../firecracker/analysis/arm64-network-failure-prototypes.md)

同时也有比较明确的源码锚点：

1. `TapOpen`
2. `TapSetVnetHdrSize`
3. `undo_pop()`
4. MMDS 分流

源码依据：[arm64-network-failure-prototypes.md](../firecracker/analysis/arm64-network-failure-prototypes.md)。

但它缺少两样东西：

1. 一份真实 ARM64 失败日志样本
2. 一组项目内现成保存下来的 ARM64 网络故障记录

不过它也已经不再只是失败原型层。

当前还多了两份准样本：

1. [Firecracker ARM64 网络准样本：TAP / vnet header 早失败](../firecracker/analysis/arm64-network-sample-tap-backend.md)
2. [Firecracker ARM64 网络准样本：MMDS / Rate Limiter 伪失败](../firecracker/analysis/arm64-network-sample-mmds-throttle.md)

因此 Firecracker 现在属于：

`源码原型成熟，但真实样本成熟度低`

## 4. Cloud Hypervisor：成熟度判断

Cloud Hypervisor 也已经有三层文档：

1. [ARM64 网络能力边界矩阵](../cloud-hypervisor/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../cloud-hypervisor/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../cloud-hypervisor/analysis/arm64-network-failure-prototypes.md)

它的优势是测试锚点比 Firecracker 更直接。

例如仓库里已有：

1. guest `/proc/interrupts` 的 GICv3 相关命令
2. host `ip link` / tap 数量检查
3. `virtio-device activated` 事件锚点

源码依据：[arm64-network-observation-guide.md](../cloud-hypervisor/analysis/arm64-network-observation-guide.md)。

但它同样缺少：

1. 现成保存下来的 ARM64 失败日志目录
2. 一篇基于真实失败输出整理的样本记录

不过它已经不再只是“命令和原型”。

当前还多了两份准样本：

1. [Cloud Hypervisor ARM64 网络准样本：多网卡](../cloud-hypervisor/analysis/arm64-network-sample-multi-if.md)
2. [Cloud Hypervisor ARM64 网络准样本：PCI MSI](../cloud-hypervisor/analysis/arm64-network-sample-pci-msi.md)

因此 Cloud Hypervisor 现在属于：

`测试命令和错误锚点清楚，但真实样本成熟度低`

## 5. Kata Containers：成熟度判断

Kata 也已经有三层文档：

1. [ARM64 网络能力边界矩阵](../kata-containers/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../kata-containers/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../kata-containers/analysis/arm64-network-failure-prototypes.md)

Kata 的特点是错误文本很清楚：

1. `unrecognised machinetype`
2. `Arm64 architecture does not support vIOMMU`
3. `interface not available`
4. `QMP not initialized`

源码依据：[arm64-network-failure-prototypes.md](../kata-containers/analysis/arm64-network-failure-prototypes.md)。

但它最缺的是：

一份真实 ARM64 网络失败日志，能把 machine、endpoint、agent、backend 四层中的哪一层先失败真正落地。

不过它现在也已经不只停留在失败原型层。

当前还多了两份准样本：

1. [Kata ARM64 网络准样本：Machine / vIOMMU 早失败](../kata-containers/analysis/arm64-network-sample-machine-iommu.md)
2. [Kata ARM64 网络准样本：Guest Agent 设备发现失败](../kata-containers/analysis/arm64-network-sample-agent-discovery.md)

因此 Kata 现在属于：

`失败原型已经齐，但真实样本成熟度低`

## 6. CubeSandbox：成熟度判断

CubeSandbox 已经不仅有三层文档。

它还有：

1. [ARM64 网络实测取证模板](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-template.md)
2. [ARM64 网络实测样本记录](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-sample.md)
3. [ARM64 日志采集缺口与补齐路径](../CubeSandbox-sandbox-clone/analysis/arm64-log-collection-gap.md)
4. [ARM64 日志源映射](../CubeSandbox-sandbox-clone/analysis/arm64-log-source-map.md)

更重要的是，仓库里已经存在真实 ARM64 记录：

1. one-click E2E 成功样本
2. `tap fd unavailable` 并发故障线索

源码依据：[arm64-network-evidence-sample.md](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-sample.md)，[arm64-network-failure-prototypes.md](../CubeSandbox-sandbox-clone/analysis/arm64-network-failure-prototypes.md)。

它当前真正缺的不是样本，而是：

缺少一份带 `collect-logs.sh` 中间层日志目录的故障样本。

因此 CubeSandbox 现在属于：

`平台级样本成熟度中等，但中间层日志样本仍未成熟`

## 7. 优先级排序

如果按“下一份真实样本最值得先补哪家”排序，我建议这样排：

1. Kata Containers
2. Cloud Hypervisor
3. Firecracker
4. CubeSandbox

原因不是项目重要性，而是证据缺口大小。

Firecracker 现在也已经进入“准样本”阶段。

Cloud Hypervisor 和 Kata 已经进一步进入“准样本”阶段。

其中 Kata 的失败分层最复杂，又还没有一份真实日志去验证这套分层是否好用，所以优先级最高。

CubeSandbox 虽然还缺中间层日志，但至少已经有平台级成功样本和一类真实故障线索，不是最空的一家。

## 8. 推荐下一步

建议后续按下面顺序补样本。

第一步：补 Kata ARM64 网络失败样本。

理由：

machine、IOMMU、endpoint、agent、backend 五层都已有明确原型，但还没有真实日志落点。

第二步：补 Cloud Hypervisor ARM64 网络失败样本。

理由：

它的 guest `/proc/interrupts`、tap 数量和 `virtio-device activated` 已有现成锚点，成样本成本低。

第三步：补 Firecracker ARM64 网络失败样本。

理由：

它的错误更偏 VMM 内部，需要先拿到更贴近设备/队列的日志或测试输出。

第四步：补 CubeSandbox 的中间层日志样本。

理由：

它不是没有样本，而是样本已经偏平台级，缺的是 `collect-logs.sh` 产物与中间层日志目录。

## 9. 结论

现在这条 ARM64 网络研究线，已经从“缺框架”进入“缺样本”的阶段。

这其实是好事。

因为它说明继续扩概念层文档的收益已经明显下降。

后续只要按这篇成熟度矩阵去补样本，研究线就会开始从源码解释转向证据闭环。 
