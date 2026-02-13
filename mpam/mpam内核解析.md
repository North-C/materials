# MPAM 深入分析

## 硬件特性介绍

参考：
- [Armv8 MPAM硬件特性介绍](https://zhuanlan.zhihu.com/p/10583420555)

内存系统资源分区和监控（MPAM）的出现，是为了处理确定性服务质量（QoS）的需求。在现代云计算基础设施中，硬件资源的共享是提高利用率的关键，但也带来了性能隔离的挑战，这导致关键业务（如高频交易或实时数据库）的尾延迟（Tail Latency）极易受到同一 SoC 上运行的批处理作业（如视频转码或大数据分析）的干扰。

Intel 通过资源导向技术（RDT）引入了缓存分配技术（CAT）和内存带宽分配（MBA），并在 Linux 内核中建立了 resctrl 子系统来管理这些功能 。为了在 ARM 生态系统中提供对等甚至更高级的功能，Arm 引入了 MPAM 扩展,**MPAM 不仅仅是一个外设控制器，它是一个横跨处理器流水线、互连总线（Interconnect）、系统级缓存（SLC）和内存控制器的系统级架构协议。**

### MPAM 的硬件架构

MPAM 架构放弃了集中式控制器的概念，转而在整个内存系统的互连结构中传递元数据。

1. 请求者（Requester）与执行者（Completer）的分离设计
2. 资源实例选择（RIS）的引入

#### Information Bundle

**在 MPAM 系统中，每一个内存事务（读、写、原子操作）都携带一个边带信号，称为“MPAM 信息包”。**

信息包在硬件链路上透明传递，由以下核心字段组成：


|字段	|全称	|位宽	|功能描述与 Linux 映射|
| - | - | - | - |
| PARTID	| Partition ID	| 最多 16 位	| **控制标签**。用于索引资源分配表。在 Linux 中，它直接映射到 resctrl 的 CLOSID（Class of Service ID）。PARTID 决定了该请求可以使用多少缓存路数或带宽配额 。|
| PMG	|Performance Monitoring Group	|最多 8 位	| **监控标签**。用于细分监控组。在 Linux 中映射到 RMID（Resource Monitoring ID）。这允许在同一个 PARTID 分区内区分不同线程或容器的资源消耗情况 。|
| MPAM_NS	|Non-Secure Bit	|1 位	| **安全状态指示位**。Linux 内核主要管理非安全（Non-Secure）世界的资源。该位确保了普通世界的操作系统无法篡改安全世界（如 TrustZone）的资源配额 。|

这种设计意味着 CPU 核心（PE）本身并不执行资源限制，它只负责“打标签”。真正的限制逻辑发生在下游的**内存系统组件（MSC）**中。

#### 内存系统组件 MSC

**MSC 是实现 MPAM 接口的任何硬件块，包括 L3 缓存、DDR 控制器或片上网络（NoC）节点。**根据 Arm 规范，每个 MSC 可以独立支持不同的功能子集 ：   

- CPOR (Cache Portion Partitioning): 缓存路数位图控制。类似于 Intel 的 CAT。
- CCAP (Cache Capacity Partitioning): 缓存容量计数限制。这是 MPAM 特有的，允许通过计数器设置硬性或软性容量上限。
- MBW (Memory Bandwidth Partitioning): 内存带宽控制。支持三种模式：

    - Minimum/Maximum: 限制绝对带宽值。

    - Proportional: 按比例（权重）分配带宽。

    - Portion: 使用时间切片位图来分配带宽窗口 。   

这些不同硬件组件是异构的，如何处理这些异构性，则需要驱动程序进行操作。

#### 资源实例选择 RIS 机制

在复杂的服务器 SoC 中，一个 MSC 可能管理多个物理资源实例。例如，一个大型的系统级缓存（SLC）可能由 4 个独立的切片（Slice）组成，或者一个内存控制器可能管理 8 个独立的通道。为了节省寄存器地址空间，MPAM 引入了 资源实例选择（RIS） 机制 。

在不支持 RIS 的简单实现中，寄存器直接映射到配置。但在支持 RIS 的实现中，**访问逻辑变为间接寻址**：

1. 驱动程序将目标资源索引（如 Slice 0）写入选择器寄存器 `MPAMCFG_PART_SEL` 的 RIS 字段。

2. 驱动程序读/写配置寄存器（如 `MPAMCFG_CPBM`）。

3. MSC 硬件根据选择器的值，将配置应用到具体的物理资源片上。

**对软件的深远影响： 这种“选择-访问”模式破坏了原子性**。如果不加锁，两个 CPU 同时操作同一个 MSC，可能会发生以下竞态：CPU A 设置了 `RIS=0`，准备写数据；此时 CPU B 中断执行，设置 `RIS=1`；CPU A 恢复执行，将配置错误地写入了 `RIS 1`。因此，James Morse 的补丁集在驱动层引入了极其严格的锁机制（`mpam_list_lock` 和组件级的互斥锁），以确保配置序列的原子性。

## ACPI 与固件接口设计：拓扑发现与抽象

与 x86 平台通过 CPUID 指令枚举 RDT 功能不同，ARM 平台的 MPAM 组件分布在非 CPU 区域，必须通过系统固件（ACPI 或 Device Tree）进行描述。

