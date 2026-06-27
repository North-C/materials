# ARM64 网络文档索引

本文是 ARM64 网络研究线的目录入口。

目标不是新增分析结论。

目标是把当前已经产出的文档，按用途重新分组，避免后续在多个目录里来回翻找。

源码基线：当前工作树。

## 1. 如何使用这份索引

如果你要理解项目边界，先看“能力边界矩阵”。

如果你要排查问题，先看“观测指南”。

如果你已经拿到错误文本，先看“失败原型”。

如果你准备做一次实测或补样本，先看“命令总表”“样本成熟度”“优先级”和“runbook”。

CubeSandbox 额外有一组更接近真实环境的样本与日志补齐文档，放在单独一节。

## 2. 横向总表

| 类型 | 文档 |
|---|---|
| 验证/观测总表 | [ARM64 网络验证与观测总表](./arm64-network-validation-observation-matrix.md) |
| 失败签名总表 | [ARM64 网络失败签名总表](./arm64-network-failure-signature-matrix.md) |
| 命令总表 | [ARM64 网络测试与取证命令总表](./arm64-network-test-observation-command-matrix.md) |
| 样本成熟度 | [ARM64 网络样本成熟度矩阵](./arm64-network-evidence-maturity-matrix.md) |
| 准样本覆盖 | [ARM64 网络准样本覆盖矩阵](./arm64-network-sample-coverage-matrix.md) |
| 样本优先级 | [ARM64 网络下一批样本优先级](./arm64-network-next-sample-priority.md) |
| 目标图 | [ARM64 网络下一批真实样本目标图](./arm64-network-next-target-map.md) |
| 采集手册 | [ARM64 网络样本采集 Runbook](./arm64-network-sample-collection-runbook.md) |
| 样本模板 | [ARM64 网络样本模板目录](./samples/README.md) |

## 3. Firecracker

| 类型 | 文档 |
|---|---|
| 能力边界 | [Firecracker ARM64 网络能力边界矩阵](../firecracker/analysis/arm64-network-capability-matrix.md) |
| 观测指南 | [Firecracker ARM64 网络观测指南](../firecracker/analysis/arm64-network-observation-guide.md) |
| 失败原型 | [Firecracker ARM64 网络失败原型](../firecracker/analysis/arm64-network-failure-prototypes.md) |
| 准样本 | [Firecracker ARM64 网络准样本：TAP / vnet header 早失败](../firecracker/analysis/arm64-network-sample-tap-backend.md) |
| 准样本 | [Firecracker ARM64 网络准样本：MMDS / Rate Limiter 伪失败](../firecracker/analysis/arm64-network-sample-mmds-throttle.md) |
| 准样本 | [Firecracker ARM64 网络准样本：Restore 后网络异常](../firecracker/analysis/arm64-network-sample-restore-regression.md) |
| 准样本 | [Firecracker ARM64 网络准样本：Guest Visibility / Interrupt Visibility](../firecracker/analysis/arm64-network-sample-guest-visibility.md) |
| 相关主链 | [Firecracker Virtio Net 数据面链路](../firecracker/analysis/virtio-net-data-path-chain.md) |

## 4. Cloud Hypervisor

| 类型 | 文档 |
|---|---|
| 能力边界 | [Cloud Hypervisor ARM64 网络能力边界矩阵](../cloud-hypervisor/analysis/arm64-network-capability-matrix.md) |
| 观测指南 | [Cloud Hypervisor ARM64 网络观测指南](../cloud-hypervisor/analysis/arm64-network-observation-guide.md) |
| 失败原型 | [Cloud Hypervisor ARM64 网络失败原型](../cloud-hypervisor/analysis/arm64-network-failure-prototypes.md) |
| 准样本 | [Cloud Hypervisor ARM64 网络准样本：多网卡](../cloud-hypervisor/analysis/arm64-network-sample-multi-if.md) |
| 准样本 | [Cloud Hypervisor ARM64 网络准样本：PCI MSI](../cloud-hypervisor/analysis/arm64-network-sample-pci-msi.md) |
| 准样本 | [Cloud Hypervisor ARM64 网络准样本：Runtime `add-net` / Hotplug 失败](../cloud-hypervisor/analysis/arm64-network-sample-hotplug-failure.md) |
| 准样本 | [Cloud Hypervisor ARM64 网络准样本：Restore 后网络异常](../cloud-hypervisor/analysis/arm64-network-sample-restore-regression.md) |
| 相关主链 | [Cloud Hypervisor I/O 设备数据面链路](../cloud-hypervisor/analysis/io-device-data-path-chain.md) |

## 5. Kata Containers

| 类型 | 文档 |
|---|---|
| 能力边界 | [Kata ARM64 网络能力边界矩阵](../kata-containers/analysis/arm64-network-capability-matrix.md) |
| 观测指南 | [Kata ARM64 网络观测指南](../kata-containers/analysis/arm64-network-observation-guide.md) |
| 失败原型 | [Kata ARM64 网络失败原型](../kata-containers/analysis/arm64-network-failure-prototypes.md) |
| 准样本 | [Kata ARM64 网络准样本：Machine / vIOMMU 早失败](../kata-containers/analysis/arm64-network-sample-machine-iommu.md) |
| 准样本 | [Kata ARM64 网络准样本：Guest Agent 设备发现失败](../kata-containers/analysis/arm64-network-sample-agent-discovery.md) |
| 准样本 | [Kata ARM64 网络准样本：Backend 差异失败](../kata-containers/analysis/arm64-network-sample-backend-diff.md) |
| 相关主链 | [Kata 网络 Endpoint 到 Agent 链路](../kata-containers/analysis/network-endpoint-agent-chain.md) |

## 6. CubeSandbox

| 类型 | 文档 |
|---|---|
| 能力边界 | [CubeSandbox ARM64 网络验证矩阵](../CubeSandbox-sandbox-clone/analysis/arm64-network-validation-matrix.md) |
| 观测指南 | [CubeSandbox ARM64 网络观测与取证指南](../CubeSandbox-sandbox-clone/analysis/arm64-network-observation-guide.md) |
| 失败原型 | [CubeSandbox ARM64 网络失败原型](../CubeSandbox-sandbox-clone/analysis/arm64-network-failure-prototypes.md) |
| 取证模板 | [CubeSandbox ARM64 网络实测取证模板](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-template.md) |
| 样本记录 | [CubeSandbox ARM64 网络实测样本记录](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-sample.md) |
| 真实案例 | [CubeSandbox `tap fd unavailable` 故障案例分析](../CubeSandbox-sandbox-clone/analysis/tap-fd-unavailable-case-study.md) |
| 日志缺口 | [CubeSandbox ARM64 日志采集缺口与补齐路径](../CubeSandbox-sandbox-clone/analysis/arm64-log-collection-gap.md) |
| 日志映射 | [CubeSandbox ARM64 日志源映射](../CubeSandbox-sandbox-clone/analysis/arm64-log-source-map.md) |

## 7. 推荐阅读顺序

如果是第一次接触这条线，建议按下面顺序读。

1. 先读 [ARM64 网络验证与观测总表](./arm64-network-validation-observation-matrix.md)
2. 再读你关心项目的“能力边界 + 观测指南”
3. 如果已经有错误日志，再读对应项目的“失败原型”
4. 如果要补样本，再读 [ARM64 网络样本采集 Runbook](./arm64-network-sample-collection-runbook.md)
5. 如果做 CubeSandbox 现场采集，再额外读它的日志缺口与日志映射两篇

## 8. 当前状态

现在这条 ARM64 网络研究线已经基本具备：

1. 项目级能力边界
2. 项目级观测指南
3. 项目级失败原型
4. 横向总表、命令总表、成熟度和采集手册
5. 一个真实案例分析：CubeSandbox `tap fd unavailable`

后续如果继续推进，优先级已经不在“补框架”，而在“补真实失败样本”。
