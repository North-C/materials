# ARM64 网络下一批样本优先级

本文承接 [ARM64 网络样本成熟度矩阵](./arm64-network-evidence-maturity-matrix.md)。

成熟度矩阵已经回答了：

1. 哪些项目已有平台级样本
2. 哪些项目还停留在原型/命令层

本文继续把它收敛成更直接的执行优先级。

目标不是扩展新的分析框架。

目标是明确：

如果下一轮只补一到两份真实样本，先补哪一份最值。

源码基线：当前工作树。

## 1. 核心结论

当前四个项目的 ARM64 网络样本优先级，建议这样排：

1. Kata Containers ARM64 网络失败样本
2. Cloud Hypervisor ARM64 网络失败样本
3. Firecracker ARM64 网络失败样本
4. CubeSandbox ARM64 中间层日志样本

这个排序不是在比较项目重要性。

它只反映一个问题：

哪一条线现在最缺“真实日志去验证已经写好的边界/观测/失败原型”。

## 2. 为什么 Kata 排第一

Kata 当前已经有：

1. [ARM64 网络能力边界矩阵](../kata-containers/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../kata-containers/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../kata-containers/analysis/arm64-network-failure-prototypes.md)

但它还没有：

一份真实 ARM64 网络失败样本，来证明 machine、endpoint、guest agent、backend 四层划分是否真的足够好用。

Kata 的失败层数最多，而且最依赖“先归层再看日志”。

它现在虽然已经有两份准样本：

1. [Kata ARM64 网络准样本：Machine / vIOMMU 早失败](../kata-containers/analysis/arm64-network-sample-machine-iommu.md)
2. [Kata ARM64 网络准样本：Guest Agent 设备发现失败](../kata-containers/analysis/arm64-network-sample-agent-discovery.md)

因此它最值得先补样本。

一旦有了第一份真实失败样本，前面三篇文档的实用价值会明显提升。

## 3. 为什么 Cloud Hypervisor 排第二

Cloud Hypervisor 当前也已经有：

1. [ARM64 网络能力边界矩阵](../cloud-hypervisor/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../cloud-hypervisor/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../cloud-hypervisor/analysis/arm64-network-failure-prototypes.md)

它的优点是观测命令和测试锚点已经比较成熟。

另外它也已经有两份准样本：

1. [Cloud Hypervisor ARM64 网络准样本：多网卡](../cloud-hypervisor/analysis/arm64-network-sample-multi-if.md)
2. [Cloud Hypervisor ARM64 网络准样本：PCI MSI](../cloud-hypervisor/analysis/arm64-network-sample-pci-msi.md)

例如：

1. guest `/proc/interrupts`
2. host `ip link`
3. `virtio-device activated`

因此只要拿到一份真实失败样本，落地成本会比较低。

它排在 Kata 后面，只是因为：

Kata 的多层失败分流比 Cloud Hypervisor 更依赖真实样本来验证。

## 4. 为什么 Firecracker 排第三

Firecracker 也已经有完整三层文档：

1. [ARM64 网络能力边界矩阵](../firecracker/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../firecracker/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../firecracker/analysis/arm64-network-failure-prototypes.md)

它现在也已经有两份准样本：

1. [Firecracker ARM64 网络准样本：TAP / vnet header 早失败](../firecracker/analysis/arm64-network-sample-tap-backend.md)
2. [Firecracker ARM64 网络准样本：MMDS / Rate Limiter 伪失败](../firecracker/analysis/arm64-network-sample-mmds-throttle.md)

但它相对前两者更缺少现成的项目内 ARM64 测试锚点和 guest 观测脚本。

它的失败更偏：

1. TAP/backend
2. queue/rate limiter
3. MMDS 分流
4. FDT/GIC/restore

这些层都很清晰，但要做成“真实样本记录”，比 Cloud Hypervisor 更依赖拿到 VMM 侧具体日志。

所以它排在第三。

## 5. 为什么 CubeSandbox 反而排第四

CubeSandbox 不是因为不重要才排第四。

恰恰相反，它现在已经有最多的样本基础：

1. [ARM64 网络实测样本记录](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-sample.md)
2. [ARM64 日志采集缺口与补齐路径](../CubeSandbox-sandbox-clone/analysis/arm64-log-collection-gap.md)
3. [ARM64 日志源映射](../CubeSandbox-sandbox-clone/analysis/arm64-log-source-map.md)
4. [ARM64 网络失败原型](../CubeSandbox-sandbox-clone/analysis/arm64-network-failure-prototypes.md)

而且仓库里已经有真实的：

`tap fd unavailable`

故障记录。

它现在最缺的不是“有没有样本”。

而是缺一份带 `collect-logs.sh` 产物的中间层日志样本。

这条工作当然重要，但相较于前面三家“完全没真实失败样本”，紧迫度没那么高。

## 6. 最小行动建议

如果下一轮只能做一件事，建议优先做：

`Kata ARM64 网络失败样本记录`

如果下一轮能做两件事，建议加上：

`Cloud Hypervisor ARM64 网络失败样本记录`

如果能做三件事，再加上：

`Firecracker ARM64 网络失败样本记录`

CubeSandbox 的下一步则更偏“补中间层日志”，而不是“从零开始做样本”。

## 7. 样本选择标准

不管先做哪家，样本都建议满足这三个条件：

1. 有明确错误文本
2. 能映射到已有的失败原型
3. 有最小可复核的上下文

所谓上下文，最少应包括：

1. 触发配置
2. 关键日志
3. 所属层级
4. 回看的项目级文档

没有这四项的“日志截图”，价值远低于一个稍短但结构完整的样本记录。

## 8. 结论

现在这条 ARM64 网络研究线已经从“缺框架”进入“缺实样”的阶段。

而下一批最值得优先补的样本，顺序已经足够明确：

Kata，Cloud Hypervisor，Firecracker，最后是 CubeSandbox 的中间层日志补齐。
