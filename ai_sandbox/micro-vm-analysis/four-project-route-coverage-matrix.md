# 四项目深入路线完成度矩阵

本文承接 [Micro-VM 项目深入路线总览](./four-project-deep-routes.md)。

前面的总览已经把四个项目的研究路线横向对齐。

但随着文档增多，一个新的问题开始变得更重要：

哪些路线已经真正展开到位，哪些路线还只停在入口级别。

本文的目标就是把这一点收清楚。

源码基线：当前工作树。

## 1. 核心结论

当前四个项目的研究线，整体上已经从“缺入口图”进入“缺覆盖盘点”的阶段。

尤其是 Firecracker、Cloud Hypervisor、Kata，这三家的主干路线已经很厚。

继续局部深挖前，先做一张完成度矩阵更有价值。

一句话概括：

1. Firecracker 的 VMM 核心链路已经比较完整
2. Cloud Hypervisor 的 manager / device / migration 主干也已比较完整
3. Kata 的 runtime / agent / hypervisor 主线已成体系
4. CubeSandbox 的平台控制面、存储与网络线最丰富，但还更偏平台整合层

这意味着后续“继续研究”的最佳方向，不再只是补网络。

更值得开始找的是：

四个项目里仍然相对薄的非网络主路线。

## 2. 完成度分级

本文使用三档状态：

| 状态 | 含义 |
|---|---|
| `已展开` | 不只是有入口名，已经有独立链路文档和较清晰结论 |
| `部分展开` | 已有文档或片段，但还没形成足够稳定的独立研究闭环 |
| `待加强` | 当前更多停留在入口、提示或散落结论，后续值得补 |

## 3. 总体矩阵

| 路线 | Firecracker | Cloud Hypervisor | Kata Containers | CubeSandbox |
|---|---|---|---|---|
| 启动 / 控制面 | 已展开 | 已展开 | 已展开 | 已展开 |
| CPU / vCPU / 调度 | 已展开 | 已展开 | 已展开 | 已展开 |
| Memory / snapshot / restore | 已展开 | 已展开 | 已展开 | 已展开 |
| 设备模型 / virtio transport | 已展开 | 已展开 | 已展开 | 已展开 |
| 运行期控制 / hotplug | 已展开 | 已展开 | 已展开 | 已展开 |
| 网络 / ARM64 网络 | 已展开 | 已展开 | 已展开 | 已展开 |
| 存储 / rootfs / share-fs | 已展开 | 已展开 | 已展开 | 已展开 |
| 安全 / 隔离 / sandboxing | 已展开 | 已展开 | 部分展开 | 部分展开 |
| 可观测性 / 诊断 | 部分展开 | 部分展开 | 已展开 | 已展开 |
| 调度 / 元数据 / 平台任务 | 不适用 | 不适用 | 部分展开 | 已展开 |

这里的“不适用”不是缺失。

它表示项目本身不是平台调度器，不存在 CubeMaster 这一层语义。

## 4. Firecracker：完成度判断

Firecracker 当前最完整的，是 VMM 核心主干：

1. API / pre-boot / runtime controller
2. `build_microvm_for_boot`
3. vCPU / `KVM_RUN`
4. DeviceManager / MMIO / PCI transport
5. snapshot / restore
6. ARM64 与 x86_64 差异

这些路线都已经不是“有入口名”。

它们已经被拆成独立文档并形成闭环。

相对还薄一点的是：

1. 可观测性 / 诊断
2. 更贴近验证视角的存储恢复观测

也就是说，Firecracker 继续深挖时，更值的不是再补一条新的网络分支。

而是把 observability / diagnostics 或存储恢复侧的边界再压实。

## 5. Cloud Hypervisor：完成度判断

Cloud Hypervisor 当前最完整的，是：

1. API / VMM thread / `vm_create` / `vm_boot`
2. CpuManager / MemoryManager / DeviceManager
3. DeviceTree / hotplug / restore
4. I/O 设备数据面
5. migration / transport / dirty log
6. ARM64 网络与中断路径

相对仍然更值得补的是：

1. 可观测性 / 诊断的系统化入口
2. host backend 伪失败或中断回归这类更细的运行态证据

换句话说，Cloud Hypervisor 的主干架构线已经很厚。

继续补新的结构图的收益不高。

更值的是补更贴近“怎么判错”的路线。

## 6. Kata Containers：完成度判断

Kata 当前最完整的是：

1. shim v2
2. runtime-rs manager
3. hypervisor plugin
4. agent RPC / guest lifecycle
5. network endpoint -> agent
6. ARM64 网络边界与样本

相对还值得加强的是：

1. route convergence 之后的更细 guest 网络收敛证据
2. 更系统的可观测性 / 诊断入口
3. CPU / 调度层在 Kata 里的具体边界

因为 Kata 更多是 runtime 封装层。

CPU / Memory 很多语义被下沉到 hypervisor plugin，单独成体系的解释还不如网络与 agent 线完整。

## 7. CubeSandbox：完成度判断

CubeSandbox 当前路线最丰富。

尤其是：

1. CubeAPI / CubeMaster / Cubelet / CubeShim 控制面
2. snapshot / restore / rollback / catalog / replica
3. CubeCoW
4. network-agent / CubeVS / TAP fd / ARM64 网络
5. 日志采集与真实案例

它相对仍值得加强的，不是路线数量。

而是把平台层丰富语义继续往底层资源边界压得更实。

例如：

1. CPU / vCPU 资源在平台层如何体现
2. 内存 / snapshot 观测的更稳定实样

## 8. 下一批更值得补的非网络路线

如果后续想避免继续只补网络，建议下一批优先转去三条横线：

1. 存储 / rootfs / share-fs 继续细化
2. I/O 虚拟化横线
3. 中断虚拟化横线

原因很简单。

前一批点名的薄线已经补过。

现在更有价值的，不是继续围绕 ARM64 网络补框架。

而是把已存在的横线专题继续往项目级边界压得更实。

其中如果只看当前四项目里最值得继续复用的一条 ARM64 非网络判错入口，已经可以直接落在：

- [Cloud Hypervisor 与 CubeSandbox：Restore 后 Guest 不可用验证清单](./ch-cubesandbox-restore-guest-unavailability-checklist.md)

原因很直接：

它已经不只是单独讲存储、I/O 或中断，而是把这三条线在 ARM64 restore 下压成了一条联合排查链。

## 9. 这张矩阵怎么用

后续如果继续推进，不建议每次都从零决定“研究什么”。

建议先看这张完成度矩阵。

用法很简单：

1. 先挑一个 `部分展开` 或 `待加强` 的路线
2. 再回到对应项目的 `deep-routes.md`
3. 然后决定是补结构链路，还是补真实样本

这样可以避免只在某一条热门路线过度打磨。

## 10. 结论

当前四个项目的研究已经有明显阶段性成果。

真正缺的，不再是更多入口。

而是对“哪里已经够厚、哪里还值得继续补”保持清楚判断。

这张完成度矩阵的作用，就是把这种判断固定下来。

## 11. 2026-06 更新

本轮按“专题 × 项目”做了完整盘点，并把综合学习层与两个项目级缺口补齐：

1. 新增综合层：[设计全景与学习路线](./vm-design-landscape-overview.md)、[性能设计依据](./performance-design-basis-cross-project.md)、[安全设计依据](./security-design-basis-cross-project.md)。
2. 补 Cloud Hypervisor 安全机制 chain：[isolation-seccomp-landlock-chain](../cloud-hypervisor/analysis/isolation-seccomp-landlock-chain.md)（安全轴 CH 升级为已展开）。
3. 补 Kata 可观测机制 chain：[observability-diagnostics-chain](../kata-containers/analysis/observability-diagnostics-chain.md)（可观测轴 Kata 升级为已展开）。
4. 补 CubeSandbox 可观测聚合 chain：[observability-diagnostics-chain](../CubeSandbox-sandbox-clone/analysis/observability-diagnostics-chain.md)（聚合 arm64-log-* 文档，可观测轴四个活跃项目全部对齐）。
5. 完整盘点与剩余缺口见 [分析框架改进意见](./analysis-improvement-recommendations.md)。

剩余“部分展开”项：Kata/CubeSandbox 的安全聚合 chain、crosvm（暂停）、Firecracker/CH 的可观测虽已展开但仍有细化空间、Kata runtime-rs 与 Go runtime 对称覆盖。
