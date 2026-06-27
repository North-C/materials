# ARM64 网络准样本覆盖矩阵

本文承接 [ARM64 网络文档索引](./arm64-network-document-index.md)、[ARM64 网络样本成熟度矩阵](./arm64-network-evidence-maturity-matrix.md) 和 [ARM64 网络样本采集 Runbook](./arm64-network-sample-collection-runbook.md)。

前面几篇已经回答了三个问题：

1. 有哪些文档
2. 哪些项目样本成熟度更高
3. 下一批真实样本该怎么采

本文继续回答第四个更实际的问题：

现在四个项目里，哪些失败层已经有“可直接套用的准样本”，哪些还只有失败原型，哪些已经有真实样本。

源码基线：当前工作树。

## 1. 核心结论

当前 ARM64 网络研究线已经不再是“只有边界和原型”。

至少在 Firecracker、Cloud Hypervisor、Kata 这三家里，已经分别落下了两类准样本。

但它们覆盖的层次并不一样。

可以先用一句话概括：

1. Firecracker 强在 host backend 和伪失败判别
2. Cloud Hypervisor 强在 host/guest 枚举和 interrupt visibility
3. Kata 强在 machine/IOMMU 早失败和 guest discovery
4. CubeSandbox 强在真实平台样本和具体故障案例

这意味着后续补真实样本时，不应该平均发力。

而应该优先补“当前矩阵里还空着的层”。

## 2. 覆盖维度定义

为了避免把“样本”说得太笼统，本文把覆盖面拆成六类：

1. host backend / machine 早失败
2. guest 设备发现或基本枚举
3. ARM64 interrupt visibility
4. pseudo-failure / 误判高发层
5. restore / rollback / arch-state 相关层
6. 真实样本或真实案例

这六类不是互斥关系。

同一个项目可以同时覆盖多类。

## 3. 总体覆盖矩阵

| 项目 | host backend / machine 早失败 | guest 发现 / 枚举 | ARM64 interrupt visibility | pseudo-failure | restore / rollback | 真实样本 / 案例 |
|---|---|---|---|---|---|---|
| Firecracker | 有准样本 | 有准样本 | 有准样本 | 有准样本 | 有准样本 | 无 |
| Cloud Hypervisor | 部分覆盖 | 有准样本 | 有准样本 | 有准样本 | 有准样本 | 无 |
| Kata Containers | 有准样本 | 有准样本 | 无独立准样本 | 有准样本 | 无准样本 | 无 |
| CubeSandbox | 有真实案例侧证 | 有真实样本侧证 | 无独立准样本 | 有真实案例 | 有平台级真实样本 | 有 |

这里的“无准样本”不等于没有文档。

它只表示：

当前还没有一篇可直接套用成真实样本记录的准样本。

## 4. Firecracker：覆盖特点

Firecracker 当前已有四份准样本：

1. [TAP / vnet header 早失败](../firecracker/analysis/arm64-network-sample-tap-backend.md)
2. [MMDS / Rate Limiter 伪失败](../firecracker/analysis/arm64-network-sample-mmds-throttle.md)
3. [Restore 后网络异常](../firecracker/analysis/arm64-network-sample-restore-regression.md)
4. [Guest Visibility / Interrupt Visibility](../firecracker/analysis/arm64-network-sample-guest-visibility.md)

这两份把它的优势和短板都暴露得很清楚。

优势是：

最容易误判的两层已经被固定下来了。

也就是：

1. 纯 host backend 初始化错误
2. 共享数据面里的伪失败

但它仍缺的已经不再是准样本分类。

它现在更缺的是：

1. 一份真实 ARM64 guest visibility / interrupt visibility 日志包
2. 一份真实 ARM64 restore 网络失败日志包

这也是为什么 Firecracker 真实样本的采集成本仍然更高。

## 5. Cloud Hypervisor：覆盖特点

Cloud Hypervisor 当前已有四份准样本：

1. [多网卡](../cloud-hypervisor/analysis/arm64-network-sample-multi-if.md)
2. [PCI MSI](../cloud-hypervisor/analysis/arm64-network-sample-pci-msi.md)
3. [Runtime `add-net` / Hotplug 失败](../cloud-hypervisor/analysis/arm64-network-sample-hotplug-failure.md)
4. [Restore 后网络异常](../cloud-hypervisor/analysis/arm64-network-sample-restore-regression.md)

它的覆盖非常适合做“中层校验”。

因为这两份样本刚好卡在：

1. host tap + guest 接口枚举
2. guest `/proc/interrupts` 的 MSI 可见性

所以 Cloud Hypervisor 当前最不缺的是：

1. 基本枚举样本
2. ARM64 interrupt visibility 样本

它目前更缺的是：

1. 真实失败日志
2. 更细的 host backend 伪失败样本
3. 更细的 guest 中断回归样本

## 6. Kata Containers：覆盖特点

Kata 当前已有三份准样本：

1. [Machine / vIOMMU 早失败](../kata-containers/analysis/arm64-network-sample-machine-iommu.md)
2. [Guest Agent 设备发现失败](../kata-containers/analysis/arm64-network-sample-agent-discovery.md)
3. [Backend 差异失败](../kata-containers/analysis/arm64-network-sample-backend-diff.md)

这三份几乎正好对应 Kata 最关键的三层：

1. host runtime 入口边界
2. backend-specific attach 边界
3. guest discovery 中层边界

所以 Kata 当前最不缺的是：

1. 早失败归层
2. guest device discovery 归层

它更缺的是：

1. interrupt visibility 层的直接样本
2. 一份真正把 backend 差异落地的真实日志样本
3. route convergence 或 restore 相关样本

这也解释了为什么 Kata 仍是第一优先级。

不是因为文档少。

而是因为它最需要真实样本来验证“多层归类”本身是否好用。

## 7. CubeSandbox：覆盖特点

CubeSandbox 的位置和前三家完全不同。

它不是先有大量准样本，再等真实样本。

它反而是已经有：

1. [ARM64 网络实测样本记录](../CubeSandbox-sandbox-clone/analysis/arm64-network-evidence-sample.md)
2. [tap fd unavailable 故障案例](../CubeSandbox-sandbox-clone/analysis/tap-fd-unavailable-case-study.md)

也就是说，它在“真实样本 / 真实案例”这一列已经领先。

但它的弱点也很明确：

缺少把中间层日志单独压成准样本或真实样本的记录。

所以 CubeSandbox 当前不是“没有样本”。

而是：

真实平台样本已有，中间层日志覆盖仍薄。

## 8. 下一步最值的补位点

如果按“当前覆盖空洞最大”来排，下一步最值的补位点是：

1. Kata 的 backend 差异真实样本
2. Cloud Hypervisor 的真实失败样本
3. Firecracker 的真实 guest visibility / interrupt visibility 样本
4. CubeSandbox 的中间层日志样本

更具体地说：

Kata 需要一份能把 machine / endpoint / guest discovery / backend 真正串起来的真实日志。

Cloud Hypervisor 需要一份能把准样本升级成真实失败记录的日志包。

Firecracker 需要一份把“共享数据面已知”继续推进到“guest 侧可见或 restore 异常”的样本。

CubeSandbox 则需要一份真正包含 `collect-logs.sh` 中间层产物的案例。

## 9. 这张矩阵应该怎么用

后续如果继续补样本，建议先看这张矩阵，再决定做哪家。

使用顺序建议如下：

1. 先看某项目在哪一列是空的
2. 再回到对应项目的准样本或失败原型
3. 最后按 [ARM64 网络样本采集 Runbook](./arm64-network-sample-collection-runbook.md) 去采

这样做的好处是：

不会再重复补已经有覆盖的层。

## 10. 结论

现在 ARM64 网络研究线已经从“项目级文档堆积”进入“样本覆盖管理”阶段。

这张矩阵的价值，就是把四家的样本覆盖缺口摆平。

后续的工作重点不该再是补新的抽象分类。

而是沿这张矩阵，把还空着的层逐个补成真实样本。
