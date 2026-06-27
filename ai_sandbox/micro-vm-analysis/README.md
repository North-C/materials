# Analysis 导航入口

本目录是顶层分析入口。

这里不放项目内源码长链本体。

项目级源码链路继续放各仓库自己的 `analysis/` 目录。

顶层 `analysis/` 只放四类内容：

1. 项目路线总览
2. 跨项目专题判断
3. ARM64 网络线索引与样本体系
4. 样本资产入口

## 0. 如果你是第一次想系统学习

如果你目标是“完整理解这些轻量化虚拟机、学会如何构建高性能 VM、建立性能与安全的设计依据”，先从这里开始，再进入下面的四类读法：

- [轻量化虚拟机设计全景与学习路线](./vm-design-landscape-overview.md)：完整面貌 + 四段式学习课程，贯穿已有 chain 文档。
- [性能设计依据跨项目专题分析](./performance-design-basis-cross-project.md)：性能从哪些设计决策来，带实测锚点。
- [安全设计依据跨项目专题分析](./security-design-basis-cross-project.md)：安全怎么推理、怎么取舍，威胁模型与纵深防御原理。
- [分析框架改进意见](./analysis-improvement-recommendations.md)：框架自身的完整性盘点与改进优先级。

这四份是“综合学习层”，建立在下面的机制专题之上。学机制读专题，学取舍读设计依据，两者互补。

## 1. 四类读法

### A. 按项目路线读

如果你要跟着单个项目深入，先从这里开始：

- [四项目深入路线总览](./four-project-deep-routes.md)
- [四项目深入路线完成度矩阵](./four-project-route-coverage-matrix.md)

然后再进入各项目自己的源码链路目录：

- [Firecracker 路线](../firecracker/analysis/deep-routes.md)
- [Cloud Hypervisor 路线](../cloud-hypervisor/analysis/deep-routes.md)
- [Kata Containers 路线](../kata-containers/analysis/deep-routes.md)
- [CubeSandbox 路线](../CubeSandbox-sandbox-clone/analysis/deep-routes.md)

### B. 按跨项目专题读

如果你要横向比较，优先从这些专题开始：

- [启动路径与控制面](./boot-control-plane-cross-project.md)
- [Snapshot / Restore / Clone](./snapshot-restore-cross-project.md)
- [存储、rootfs 与共享文件系统](./storage-rootfs-sharefs-cross-project.md)
- [Virtio 传输与设备数据路径](./virtio-data-path-cross-project.md)
- [中断与事件通知](./interrupt-event-notification-cross-project.md)
- [ARM64 非网络风险图](./arm64-non-network-risk-map.md)
- [Cloud Hypervisor / CubeSandbox：Restore 后 Guest 不可用验证清单](./ch-cubesandbox-restore-guest-unavailability-checklist.md)
- [非网络横线样本资产矩阵](./non-network-sample-asset-matrix.md)
- [非网络下一批真实样本目标图](./non-network-next-target-map.md)
- [非网络证据包记录模板](./non-network-evidence-bundle-template.md)
- [非网络样本采集 Runbook](./non-network-sample-collection-runbook.md)
- [非网络当前证据缺口总表](./non-network-evidence-gaps.md)
- [可观测性与故障诊断](./observability-diagnostics-cross-project.md)
- [Hypervisor / KVM / vCPU 执行边界](./hypervisor-kvm-vcpu-cross-project.md)

### C. 按 ARM64 网络线读

如果你只关心 ARM64 网络，先从这一组入口开始：

- [ARM64 网络文档索引](./arm64-network-document-index.md)
- [ARM64 网络准样本覆盖矩阵](./arm64-network-sample-coverage-matrix.md)
- [ARM64 网络下一批真实样本目标图](./arm64-network-next-target-map.md)
- [ARM64 网络样本采集 Runbook](./arm64-network-sample-collection-runbook.md)

### D. 按样本资产读

如果你准备开始采样、归档或补证据，直接看：

- [样本资产目录](./samples/README.md)
- [样本目录索引](./samples/INDEX.md)

## 2. 目录约定

保持以下约定：

1. 项目级源码链路继续放各 repo 的 `analysis/`
2. 跨项目判断、顶层索引、样本体系只放顶层 `analysis/`

这条约定的目的，是避免把“源码链路”和“跨项目判断”重新混回一层。

## 3. 当前重点

按当前完成度矩阵，前一批轻量薄线已经补过：

1. [CubeSandbox CPU / vCPU 资源边界](../CubeSandbox-sandbox-clone/analysis/cpu-vcpu-resource-boundary-chain.md)
2. [Firecracker 存储 / rootfs / share-fs 边界](../firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md)
3. [Cloud Hypervisor host backend 伪失败更细化样本](../cloud-hypervisor/analysis/arm64-network-sample-host-backend-pseudo-failures.md)

因此下一批优先不要继续扩 ARM64 网络框架。

更值得转去补的是：

1. [存储线继续细化](./storage-rootfs-sharefs-cross-project.md)
2. [I/O 虚拟化横线](./virtio-data-path-cross-project.md)
3. [中断虚拟化横线](./interrupt-event-notification-cross-project.md)
4. [Cloud Hypervisor / CubeSandbox ARM64 restore 联合判错清单](./ch-cubesandbox-restore-guest-unavailability-checklist.md)

如果你接下来要从样本资产角度继续推进，可以直接在：

- [样本目录索引](./samples/INDEX.md)

里按 `template / seed / real / validated` 继续筛选。

## 4. 推荐使用顺序

如果你是第一次进入这个目录，建议按下面顺序读：

1. 先读这份入口
2. 再选“按项目路线”或“按跨项目专题”
3. 如果要做样本，就直接进入 `samples/`
