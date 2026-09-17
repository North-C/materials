# CubeSandbox ARM64 Template 静止窗口与 KVM 机制分析

## 1. 文档信息

- 日期：2026-07-20
- 最后更新：2026-07-22，重组 KVM、Generic Timer 与 GICv3 机制主线并补充图示
- 适用版本：CubeSandbox v0.5.1
- 社区源码基线：`a164417f497234a0d787cb328b0ae96480b1569b`
- 分析对象：ARM64，2 vCPU Template
- 关联主报告：`CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md`
- 关联细化文档：`CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md`
  （Pause/Resume/Restore 函数级细节、本文 §4.2-4.3 的两处小修正、插桩点设计）
- 关联概念文档：`CUBESANDBOX_ARM_GIC_BASICS_AND_CPU1_TICK_CHAIN_20260721.md`
  （GIC 基础概念、CPU1 第一个 tick 的全链路图与逐环节失效模式）
- 关联链路文档：`CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ANALYSIS_20260721.md`
  （跨进程调用链、真实函数代码和 Restore 三个时序窗口）
- 主要源码目录：`source_code/CubeSandbox-v0.5.1-arm64-timer-history`
- Arm 架构基线：Arm ARM DDI 0487 M.c、Generic Timer 102379 v1.4、GIC IHI 0069 H.b、PSCI DEN 0022 F.b
- Linux 接口基线：Linux KVM API 与 VGICv3 文档，检索日期 2026-07-20

本文用于解释实验中所称的“静止窗口（quiescence window）假设”，并展开 CubeSandbox
构建和恢复 Template 时，从 CubeMaster、Cubelet、CubeShim、Cloud Hypervisor 到 Linux
KVM/ARM Generic Timer/vGIC 的完整机制。

具体实验版本、执行过程、结果、当前状态和证据索引统一记录在关联主报告中。本文只保留
理解实验所需的机制、架构约束和诊断原则。

## 2. 术语校正

实验中讨论的是“静止窗口”，不是通常意义上的“静态窗口”。

静止窗口表示：

> `VmPause` 已向调用方返回，但是否所有 vCPU 线程都已经到达不会再改变可快照状态的
> 稳定点，仍需要进一步确认。在 `VmPause` 与 `VmSnapshot` 之间增加固定等待，用于判断
> 快照是否过早开始。

这里必须区分三个状态：

| 状态 | 含义 | 当前实现是否明确确认 |
| --- | --- | --- |
| VM 逻辑状态为 `Paused` | VMM 状态机已完成 Pause 流程 | 是 |
| vCPU 的 `KVM_RUN` 已被中断 | vCPU 已从 guest 返回 userspace，并完成必要的 immediate-exit 运行 | 是，使用 `vcpu_run_interrupted` |
| vCPU userspace 线程已进入 `park()` | 线程已经实际睡眠，不再执行 pause 分支代码 | 否 |

`VmPause` 返回时可以确认前两项，但社区 v0.5.1 没有一个严格表示第三项的同步原语。

## 3. Template 构建的完整链路

### 3.1 控制面和制品阶段

从 OCI 镜像创建 Template 时，控制面大致执行：

```text
cubemastercli / CubeAPI
  -> CubeMaster 创建异步 Template Job
  -> 拉取并解析 OCI 镜像
  -> 生成固定大小的 ext4 rootfs 制品
  -> Cubelet 创建 Template 构建 Sandbox
  -> guest 启动应用和 agent
  -> CubeShim 对运行中的 VM 执行 app snapshot
  -> 保存 VM 状态、内存卷和 Template 元数据
  -> Template 状态变为 READY
```

OCI rootfs 制品和 VM Snapshot 不是同一对象：

- rootfs 制品由镜像内容和 writable layer 规格生成。
- VM Snapshot 包含特定 CPU/内存规格下的 vCPU、内存、vGIC 和虚拟设备状态。
- 同一 rootfs 制品可以被多个 Template 引用，但每次实验仍需从日志确认 VM Snapshot
  是否由当前实验 Shim 新建。

### 3.2 CubeShim 的两条 Snapshot 路径

`CubeShim/shim/src/snapshot/mod.rs` 中存在两条不同路径。

非 app snapshot 路径：

```text
Snapshot::handle
  -> do_snapshot
  -> launch_vmm
  -> boot_vm
  -> wait_vm_ready
  -> create_snapshot
       -> ApiRequest::VmPause
       -> ApiRequest::VmSnapshot
  -> store_metadata
```

app snapshot 路径：

```text
Snapshot::handle
  -> do_app_snapshot
       -> api_pause_vm().await
       -> api_snapshot_vm().await
       -> store_metadata()
       -> api_resume_vm().await
```

Template 构建时，Cubelet 启动独立 `cube-runtime snapshot --app-snapshot` 子进程。
该 CLI 执行 `do_app_snapshot`，再通过目标 Sandbox 的 `chapi` Unix socket，把三个 HTTP
请求交给 `containerd-shim-cube-rs` 中的 VMM 线程。

VMM 观察到的调用顺序为：

```text
API request event: VmPause
API request event: VmSnapshot(...)
API request event: VmResume
```

因此，添加在同步 `create_snapshot()` 中的等待或插桩不会影响 Template 的 app snapshot
流程。任何静止窗口验证都必须命中实际调用链，并从 VMM 事件确认 Pause 与 Snapshot
之间的真实间隔。

## 4. Cloud Hypervisor 的 Pause 机制

### 4.1 VM 层 Pause

VMM 收到 `VmPause` 后调用 `Vm::pause()`，主要顺序为：

```text
校验 Running -> Paused 状态迁移
  -> 激活尚未完成激活的 virtio 设备
  -> CpuManager::pause()
  -> DeviceManager::pause()
  -> VM state = Paused
  -> 返回成功
```

这里的 `VmState::Paused` 是 VMM 状态机结果。它依赖各组件 `pause()` 返回，但并不直接
检查每个宿主 vCPU 线程已经进入 Linux 的休眠状态。

### 4.2 CpuManager Pause

社区 v0.5.1 的 `CpuManager::pause()` 主要执行：

```text
vcpus_pause_signalled = true
  -> 对每个 vCPU 线程发送 SIGRTMIN
  -> 等待该 vCPU 的 vcpu_run_interrupted = true
  -> 依次调用 Vcpu::pause()
  -> 返回
```

`Vcpu::pause()` 使用 `Pausable` trait 的默认空实现，因此真正的暂停动作发生在 vCPU
运行线程的循环中。

### 4.3 signal_thread 的 ACK 含义

`VcpuState::signal_thread()` 反复执行：

```text
pthread_kill(vcpu_thread, SIGRTMIN)
  -> 检查 vcpu_run_interrupted
  -> 未置位则等待 1 ms 后重试
```

收到信号后，阻塞在 `KVM_RUN` 中的 vCPU 线程返回 userspace。该 ACK 的语义是
“vCPU 运行循环已经到达中断点”，不是“线程已完成 park”。

### 4.4 immediate_exit 的作用

vCPU pause 分支没有直接在第一次 `KVM_RUN` 返回后保存状态，而是：

```text
set_immediate_exit(true)
  -> 再执行一次 KVM_RUN
  -> 预期得到 VmExit::Ignore
  -> set_immediate_exit(false)
  -> vcpu_run_interrupted = true
  -> while pause flag { thread::park() }
```

再次进入 `KVM_RUN` 很重要。KVM 文档要求某些 MMIO/PIO 等退出只有在 userspace
重新进入 `KVM_RUN` 后才算完成；否则 userspace看到的 vCPU 状态可能没有包含未完成操作。
`immediate_exit` 使 KVM 完成待处理操作后立即退出，不允许 guest 继续执行一段不受控指令。

### 4.5 静止窗口出现在哪里

当前顺序为：

```text
vCPU thread                         VMM/CpuManager thread
-----------                         ---------------------
complete immediate_exit KVM_RUN
vcpu_run_interrupted = true  -----> signal_thread returns
                                    CpuManager::pause returns
                                    VmState = Paused
                                    VmPause response returns
load pause flag
thread::park()                      VmSnapshot may start
```

`vcpu_run_interrupted=true` 与 `thread::park()` 之间存在指令和调度间隔，这构成静止窗口
假设所关注的时序边界。

但这仍不是根因证明，原因包括：

1. `vcpu_run_interrupted` 置位前已经完成 immediate-exit `KVM_RUN`。
2. vCPU 状态读取会取得 vCPU mutex，与 vCPU 线程中的 KVM 操作串行化。
3. pause flag 已经为 true，vCPU 线程通常不会再次进入正常 guest `KVM_RUN`。
4. 即使线程尚未实际睡眠，可快照 KVM 状态仍可能已经稳定。

所以固定等待只能判断时序敏感性，不能代替寄存器和事件级证据。

## 5. VM Snapshot 保存了什么

`Vm::snapshot()` 首先确认逻辑状态为 `Paused`，然后按以下主要顺序保存：

```text
VM metadata
  -> CpuManager snapshot
  -> MemoryManager snapshot
  -> ARM64 vGIC snapshot
  -> DeviceManager snapshot
```

### 5.1 ARM64 vCPU 状态

KVM ARM64 `Vcpu::state()` 执行：

1. `KVM_GET_MP_STATE` 获取 vCPU 电源/运行状态。
2. 获取 ARM core registers，例如通用寄存器、PC 和 PSTATE。
3. 通过 `KVM_GET_REG_LIST` 获取该内核暴露给 guest 的寄存器 ID 列表。
4. 过滤出 system registers。
5. 对每个 ID 执行 `KVM_GET_ONE_REG`。
6. 将寄存器 ID 和值写入 `VcpuKvmState.sys_regs`。

当前代码为寄存器列表分配约 500 项。ARM Generic Timer 的 per-vCPU 状态也由 KVM
one-reg 接口暴露，因此 timer 状态是否完整、一致以及恢复顺序均属于重点检查对象。

### 5.2 内存

Template 构建 VM 启用了 dirty log。MemoryManager 保存 guest memory，并可将内存数据
放入独立 `memory_vol_url` 指向的卷中。运行时恢复会把同一内存快照映射到新 VM。

内存快照正确并不意味着 CPU timer 状态正确。guest 可以恢复足够多的内存和设备状态，
使 vsock/agent 一度显示 ready，但随后仍因 timer 或中断状态不一致而停止正常推进。

### 5.3 vGIC

ARM64 Snapshot 还会：

1. 从保存的 vCPU 状态计算/设置 GIC redistributor typer。
2. 保存 vGIC distributor、redistributor、ITS 及中断相关状态。

ARM Generic Timer 的中断通常通过 per-CPU PPI 注入 GIC。即使 timer 的 CVAL/CTL
寄存器正确，如果 vGIC redistributor、PPI pending/active 状态或恢复启用顺序不一致，
CPU1 仍可能收不到预期的 timer interrupt。

## 6. Template 恢复链路

运行时从 Template 创建 Sandbox 时，CubeShim 的主要路径为：

```text
SandBox::start_vm
  -> by_snapshot()
  -> restore_vm()
       -> 校验 SnapshotInfo 与当前 CPU/内存/镜像/内核/磁盘匹配
       -> 生成 RestoreConfig
       -> VMM VmRestore
       -> app_snapshot_restore 分支直接返回，跳过 VsockServerReady 等待
  -> 连接 guest agent
  -> reset guest time / reseed random / 创建 Sandbox
```

VMM 内部恢复大致为：

```text
接收 VM config 和 Snapshot
  -> 恢复内存映射
  -> 恢复 DeviceManager 基础状态
  -> CpuManager::restore，逐个创建并 set_state vCPU
  -> 恢复 vGIC 并启用中断路由
  -> 恢复 virtio 等设备
  -> 启动 restored vCPU threads，初始保持 paused
  -> 同一个 VmRestore 请求内立即 resume：清除 pause flag 并 unpark vCPU
```

因此，app snapshot restore 的 API 成功边界已经包含 resume，但 Shim 不额外等待
`VsockServerReady`。后续单次 `connect_agent` 和 `reset_guest` 紧邻首次正常 `KVM_RUN`，
这也是第 11 节 W3 窗口在用户态最早暴露的地方。

### 6.1 ARM64 set_state 顺序

每个 vCPU 的 KVM 状态恢复顺序为：

```text
set core registers
  -> 对保存的每个 system register 执行 KVM_SET_ONE_REG
  -> set MP state
```

这意味着需要重点核对：

- CPU0 和 CPU1 保存的 timer register 集合是否相同。
- CPU1 的 CVAL/CTL 等值是否在 snapshot 时已经异常。
- VM 级 counter offset 与 per-vCPU timer 状态是否属于同一时间基准。
- vGIC 恢复是否发生在 timer 状态恢复之后，并正确保留对应 PPI。
- vCPU resume 后，CPU1 第一次进入 `KVM_RUN` 前后状态是否发生异常变化。

## 7. Linux KVM on ARM：状态所有权与 Snapshot ABI

前文已经给出 CubeSandbox 的保存和恢复顺序。本节先回答更基础的问题：这些状态分别
属于谁，以及 KVM 为 userspace 提供了什么接口。只有先划清所有权，后续 Timer 与 GIC
的状态关系才不会被误解成一组彼此独立的寄存器。

![KVM 状态所有权与 Snapshot 状态域](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_ASSETS_20260722/01-kvm-state-ownership.svg)

### 7.1 KVM 不提供单一的“保存整个 VM”事务

KVM 暴露运行虚拟机所需的内核对象，但 Snapshot 格式和调用顺序由 VMM 定义。
CubeSandbox/Cloud Hypervisor 必须组合多个 fd、多个 ioctl 和 userspace 状态，才能形成
一个可恢复的制品。

| 状态域 | KVM/Userspace 对象 | 主要内容 | CubeSandbox 保存入口 |
| --- | --- | --- | --- |
| VM-wide | VM fd | counter 策略、内存槽、VM 级能力 | VMM 与 MemoryManager |
| per-vCPU | 每个 vCPU fd | core registers、system registers、MP state | `Vcpu::state` |
| vGIC | vGIC device fd | Distributor、Redistributor、CPU interface、ITS | vGIC snapshot |
| Userspace device | VMM 对象 | virtio、配置、后端文件与元数据 | DeviceManager |

这些状态域存在依赖关系。per-vCPU timer 必须使用同一个 VM-wide 时间基准；MPIDR 和
vCPU 创建顺序必须与 Redistributor 对应；guest memory 中的 Linux timekeeping 数据也
必须与恢复后的 counter 连续性一致。

### 7.2 per-vCPU 状态：one-reg 与 MP state

ARM64 `Vcpu::state()` 先读取 `KVM_GET_MP_STATE` 和 core registers，再执行
`KVM_GET_REG_LIST`。过滤 system register ID 后，VMM 对每个 ID 单独调用
`KVM_GET_ONE_REG`，把 `{id, value}` 顺序写入 `VcpuKvmState.sys_regs`。

恢复过程与保存向量直接对应：

```text
set core registers
  -> 按 sys_regs 保存顺序逐项 KVM_SET_ONE_REG
  -> KVM_SET_MP_STATE
```

one-reg 的成功只说明某一次寄存器访问成功。它不保证多个寄存器来自同一时刻，也不保证
两个 vCPU 与 vGIC state 自动构成原子快照。寄存器集合还取决于内核版本、vCPU feature
和 finalization 状态。

因此，VMM 必须保存实际 register ID，不能仅凭寄存器名称重建编号。无法读取、无法写入、
被内核忽略或 readback 不一致的条目，都属于 Snapshot 正确性的一部分。

### 7.3 VM-wide 状态：时间策略不是单个 vCPU 的属性

Generic Timer 的 comparator 是 per-vCPU 状态，但 guest 看到的时间轴必须对整台 VM
一致。Linux KVM 可通过 VM 级 counter-offset ABI 定义这条时间轴，随后所有已创建和
后续创建的 vCPU 都应服从同一策略。

这形成一个容易遗漏的依赖：保存 `CNTV_CVAL_EL0`、`CNTV_CTL_EL0` 等 per-vCPU 状态，
并不等于保存了它们所比较的时间基准。第 8 节会从 System Counter 开始展开该关系。

### 7.4 vGIC 状态：device attributes 是另一个状态空间

KVM vGIC 不是 vCPU one-reg 的附属部分。Distributor、Redistributor、CPU interface 和
ITS 通过 device attributes 独立访问；其中 PPI 的 enable、pending、active 等状态属于
目标 PE 的 Redistributor。

完整的 CPU interface 状态还包括 `ICC_PMR_EL1`、`ICC_IGRPEN*` 和 active priority
registers。它们决定 pending interrupt 能否真正送到 PE，不能由 `GICR_ISPENDR0`
单独推导。

KVM VGIC ABI 要求在所有 vCPU 停止运行时访问完整状态。相关访问在 vCPU 运行期间可能
返回 `EBUSY`。这也是 Pause 必须先建立稳定边界、再读取 vGIC 的直接原因。

### 7.5 VMM 的职责是建立跨状态域一致性

| 层 | 该层明确定义什么 | 不替 VMM 定义什么 |
| --- | --- | --- |
| Arm Generic Timer | counter、offset、comparator、输出电平 | VM Snapshot 格式 |
| GICv3 | 中断状态、路由、优先级和电源接口 | Timer 与 GIC 的保存顺序 |
| PSCI | CPU power API 与启动状态 | KVM MP state 序列化 |
| Linux KVM | one-reg、MP state、VGIC attrs、counter offset | 跨 ioctl 原子事务 |
| CubeSandbox/VMM | Pause、Snapshot 制品和恢复顺序 | 不能假设 KVM 自动补全遗漏状态 |

因此，机制分析不能停在“所有 ioctl 都返回成功”。真正的判定标准是：各状态域在
Snapshot 时属于同一逻辑时刻，并在首次 `KVM_RUN` 前恢复为彼此兼容的组合。

## 8. Arm Generic Timer：从公共时间轴到 PPI 电平

Generic Timer 的逻辑链只有一条：公共 System Counter 形成计数视图，per-PE comparator
把计数与 deadline 比较，`CTL` 决定是否输出电平，最后该电平进入同一 PE 的 GIC PPI。

![Generic Timer 从公共计数到 PPI 电平](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_ASSETS_20260722/02-generic-timer-signal-path.svg)

### 8.1 公共时间源与计数视图

System Counter 是固定有效频率、持续递增的系统级时间源，计数被提供给所有 PE。
计数宽度为 56 至 64 位。它表示时间流逝，不表示日期；RTC 和 Linux
`CLOCK_REALTIME` 属于更高层状态。

| 对象 | 架构含义 | 主要寄存器 |
| --- | --- | --- |
| System Counter | SoC 中持续递增的共同时间源 | 平台实现 |
| Physical Count | PE 对 System Counter 的物理视图 | `CNTPCT_EL0`、`CNTPCTSS_EL0` |
| Virtual Count | 物理计数减去虚拟偏移 | `CNTVCT_EL0`、`CNTVCTSS_EL0` |
| Counter Frequency | 软件把 ticks 换算为时间的频率 | `CNTFRQ_EL0` |

`CNTFRQ_EL0` 不控制硬件计数速度。它由最高实现异常级的软件写入，只向 guest 描述
频率。CPU0 与 CPU1 必须看到相同值，否则 Linux 对同一 tick 数会得到不同时间长度。

普通 `CNTPCT_EL0` 和 `CNTVCT_EL0` 读取可能被推测或重排。需要和前序操作建立边界时
使用 `ISB`；实现 FEAT_ECV 后，可使用 self-synchronized 的 `*CTSS` 视图。

### 8.2 每个 PE 拥有独立 comparator

System Counter 是公共时间源，但 timer comparator 是 per-PE 状态。CPU0 和 CPU1 可以
在同一时间轴上设置不同 deadline，并分别产生自己的 PPI。

| Timer | 寄存器前缀 | 比较的计数 | 常见使用者 |
| --- | --- | --- | --- |
| EL1 physical timer | `CNTP_*_EL0` | physical count | guest EL1/EL0 |
| EL1 virtual timer | `CNTV_*_EL0` | virtual count | 普通虚拟机 guest |
| Non-secure EL2 physical timer | `CNTHP_*_EL2` | physical count | hypervisor |
| Non-secure EL2 virtual timer | `CNTHV_*_EL2` | physical count | VHE host |
| EL3 / Secure timers | `CNTPS_*`、`CNTHPS_*`、`CNTHVS_*` | 对应安全计数视图 | 固件或 Secure EL2 |

本文关注 EL1 virtual timer。它的 `CVAL`、`TVAL` 和 `CTL` 是同一个 comparator 的
不同编程视图，不是三个独立 timer。

### 8.3 `CVAL`、`TVAL` 与到期条件

`CNTV_CVAL_EL0` 保存 64 位绝对 deadline。按 64 位无符号 upcounter 语义，
VirtualCount 到达或超过 `CVAL` 时，TimerConditionMet 成立。

`CNTV_TVAL_EL0` 是 32 位有符号相对视图。写入它等价于：

```text
CNTV_CVAL_EL0 = CNTVCT_EL0 + SignExtend(TVAL[31:0])
```

timer 启用时，读取 `TVAL` 得到 `CVAL - CNTVCT` 的低 32 位。到期后它可表现为负值。
timer 未启用时，Arm ARM 将 `TVAL` 读值定义为 UNKNOWN。

诊断必须优先记录 `CNTVCT`、`CVAL` 和 `CTL`。只有在正常 deadline 范围内，才可把
`Signed32(TVAL) <= 0` 作为近似；不能用 `Signed64(CNTVCT-CVAL)` 替代架构的无符号比较。

### 8.4 `CTL` 把 comparator 条件变成电平信号

`CNTV_CTL_EL0` 的低三位定义 timer 输出：

| 位 | 字段 | 语义 |
| --- | --- | --- |
| bit 0 | `ENABLE` | 1 启用 comparator 输出 |
| bit 1 | `IMASK` | 1 屏蔽中断输出 |
| bit 2 | `ISTATUS` | 启用时表示 TimerConditionMet |

`ISTATUS` 不考虑 `IMASK`。因此 `ISTATUS=1, IMASK=1` 表示 deadline 已到，但输出被
源端屏蔽。`ENABLE=0` 时，`ISTATUS` 的值是 UNKNOWN。

```text
timer_line = ENABLE && !IMASK && TimerConditionMet
```

清除 `ENABLE` 只关闭输出，不冻结计数。timer 也不会自动重装。Linux clockevent handler
必须写入新 `CVAL/TVAL`，或设置 `IMASK`，或清除 `ENABLE`，才能撤销已到期的电平。

### 8.5 EL2 如何给 guest 建立虚拟时间轴

对普通非 VHE guest，virtual timer 使用：

```text
VirtualCount = PhysicalCount - CNTVOFF_EL2
```

`CNTVOFF_EL2` 同时影响 guest 读取 `CNTVCT_EL0` 和 virtual timer 内部比较。寄存器物理上
属于各 PE 的 EL2 context，但 hypervisor 必须让同一 VM 的所有 vCPU 看到一个逻辑时间轴。

`CNTHCTL_EL2` 控制 EL1 对 counter/timer 的直接访问和 trap。字段解释取决于
`HCR_EL2.E2H/TGE` 与 FEAT_ECV，低位 permission 和 ECV trap 字段的极性也不同。
因此不能脱离 feature 集合按固定常量解释 raw value。

FEAT_ECV_POFF 还可通过 `CNTPOFF_EL2` 偏移 EL1 physical count。它不替代
`CNTVOFF_EL2`；前者服务 physical view，后者仍服务 virtual count/timer。

Linux KVM 在支持 `KVM_CAP_COUNTER_OFFSET` 时提供 `KVM_ARM_SET_COUNTER_OFFSET`。
该 VM-wide offset 同时作用于 physical 和 virtual counter，并覆盖所有 vCPU。

调用该 ABI 后，KVM 可以忽略随后通过 one-reg 写入的 `CNTVCT_EL0` 和 `CNTPCT_EL0`，
且不返回错误。因此 `KVM_SET_ONE_REG` 成功不能证明 counter 已按该值恢复。

诊断必须记录 capability、offset 值和设置顺序，再读取恢复后的实际 counter 样本。
目标宿主是否支持该 ABI，要以目标内核实测为准。

### 8.6 Snapshot 必须保持一组时间不变量

Arm 将 `CVAL`、`CTL` 控制位和 `CNTVOFF_EL2` 等 Warm reset 值定义为 UNKNOWN。
新建 vCPU 后保留 reset 状态不能代替恢复。

| 状态 | 范围 | 必须满足的关系 |
| --- | --- | --- |
| counter frequency | VM/平台 | 所有 vCPU 一致，且与 guest 启动值一致 |
| counter offset | 逻辑 VM-wide | 所有 vCPU 使用同一暂停时间策略 |
| `CVAL/CTL` | per-vCPU | 能与恢复后的 VirtualCount 正确比较 |
| timer line | per-vCPU | 等于 `ENABLE && !IMASK && condition` |
| GIC PPI state | per-vCPU | 与 line、pending、active 和投递门控一致 |
| Linux timekeeping | guest memory | 与恢复后的 counter 连续性一致 |

offset 向前跳而 `CVAL` 不变，会让大量 deadline 立即过期；时间轴后跳或 `CVAL` 落在
异常远的未来，会让 CPU 长期等不到 tick。两者都可能最终表现为 RCU stall。

## 9. Arm GICv3：从中断源到目标 PE

Timer 只负责产生高低电平。GICv3 决定该电平属于哪个 PE、是否成为 pending、能否通过
group 和 priority 门控，以及 guest acknowledge 后如何进入 active/deactivate 生命周期。

### 9.1 先建立组件拓扑

![GICv3 组件与目标 PE 的 Timer PPI 路径](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_ASSETS_20260722/03-gicv3-component-topology.svg)

| 组件 | 主要职责 | 与 Timer PPI 的关系 |
| --- | --- | --- |
| Distributor | 维护 shared SPI 状态与路由 | 不保存每个 PE 的 Timer PPI 私有状态 |
| Redistributor | 维护所属 PE 的 SGI/PPI，收集 LPI | 接收该 PE 的 Timer PPI line |
| CPU interface | group、priority、acknowledge、priority drop、deactivate | 决定 pending PPI 是否呈现给 PE |
| ITS | 把 MSI 翻译为 LPI，并管理设备/collection 表 | 不在 architectural timer PPI 主路径上 |
| PE/vCPU | 执行 guest，读取 ICC system registers | 只处理送达自己的 PPI 实例 |

最关键的结构关系是：CPU1 virtual timer 的 PPI line 直接进入 Redistributor 1 的私有
PPI bank，不先经过 Distributor 做 SPI 路由。CPU0 的同一 INTID 是另一个独立实例，
不能代替 CPU1 的状态。

### 9.2 PPI 身份与 per-PE 状态

GIC 架构规定 INTID 16 至 31 为 PPI。Generic Timer 指南按 SBSA 推荐把 EL1 virtual
timer 分配为 INTID 27，即 PPI 11；具体虚拟平台仍应通过 guest DT/ACPI 验证。

一个 Timer PPI 的有效状态横跨三层：

| 层 | 关键状态 | 作用 |
| --- | --- | --- |
| Timer source | line level | 表示 timer 当前是否持续请求中断 |
| Redistributor | `ISENABLER0`、`ISPENDR0`、`ISACTIVER0`、group、priority | 保存该 PE 的 PPI 私有状态 |
| CPU interface | `ICC_IGRPEN*`、`ICC_PMR_EL1`、active priority | 执行 group 和优先级仲裁 |

因此，“CPU1 PPI pending=1”只是中间状态，不等于 CPU1 会进入 IRQ handler。投递还要
经过 individual enable、group enable、priority mask、CPU interface 和 PSTATE 等门控。

### 9.3 PPI 的完整投递门控

![Timer PPI 从 source line 到目标 PE IRQ signal 的门控](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_ASSETS_20260722/04-gic-ppi-delivery-lifecycle.svg)

有效 pending 由 source line 与 software-latched pending 共同贡献。随后 GIC 依次检查
Redistributor individual enable、interrupt group、`ICC_PMR_EL1` priority 和目标 PE
CPU interface 状态。

这些条件通过后，GIC 才向 PE 呈现 IRQ signal。该 signal 可以唤醒 WFI，但 guest 是否
真正进入 IRQ exception，还取决于 `PSTATE.I` 等 PE 侧条件。第 10 节会单独解释这一步。

门控失败通常不会销毁 pending 请求，而是保留到条件重新打开。因此故障分析应找出
第一个关闭的门，不能把“未进入 handler”直接归因于 Timer 未到期。

### 9.4 四态 interrupt 生命周期

![GIC interrupt 四态生命周期](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_ASSETS_20260722/04b-gic-interrupt-state-machine.svg)

| 状态 | 含义 |
| --- | --- |
| Inactive | 既不 pending，也不 active |
| Pending | 请求已识别，等待目标 PE acknowledge |
| Active | PE 已 acknowledge，当前实例正在处理 |
| Active and pending | 当前实例 active，同时存在后续请求 |

读取 `ICC_IAR1_EL1` 完成 acknowledge，并使 PPI 进入 active。写 `ICC_EOIR1_EL1`
执行 priority drop；是否同时 deactivate 取决于 EOImode。分离模式还需写
`ICC_DIR_EL1`。

Timer PPI 是 level-sensitive。若 handler 在 deactivate 前没有写入新 `CVAL/TVAL`、
设置 `IMASK` 或清除 `ENABLE`，source line 仍为高，PPI 会再次进入 pending。

因此，line/pending 丢失会导致 CPU1 无 tick；而恢复 active 状态后 line 长期为高，
则可能形成重复 IRQ，表现为 guest 或 Shim 高 CPU。这是同一状态机的两种相反失配。

### 9.5 KVM VGIC 必须同时处理 line、latch 与 Redistributor 身份

KVM VGICv3 userspace API 把 level-sensitive PPI 拆成两个可观察部分：

1. `GICR_ISPENDR0` device attribute 表示 software-latched pending。
2. `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO` 表示实际 IRQ input line level。

guest 可见 pending 近似为 `latched_pending OR line_level`。只保存 ISPENDR 无法重建
完整电平状态；只保存 line level 又会丢失软件置 pending。

architectural timer PPI 的 line 通常由 KVM 根据恢复后的 timer 条件重新计算。仍需确认
timer state、VGIC latch/active 和首次 `KVM_RUN` 之间没有短暂的不一致。

KVM VGICv3 ABI 还要求保持 vCPU 创建顺序、Redistributor region 创建顺序及两者交错
关系。恢复后必须确认 CPU1 的 MPIDR 仍映射到 Redistributor 1。

### 9.6 `GICR_WAKER` 描述的是 PE 电源接口状态

每个 Redistributor 都有独立 `GICR_WAKER`。`ProcessorSleep=1` 表示 PE 正进入或已经
进入低功耗；中断保持 pending 并产生 WakeRequest，而不直接进入 CPU interface。

下电前，软件设置 `ProcessorSleep=1` 并等待 `ChildrenAsleep=1`。上电后，软件清除
`ProcessorSleep`，等待 `ChildrenAsleep=0`，再恢复 CPU interface。

虚拟机 Pause 不是物理 CPU powerdown，通常不应照搬该流程。但若 Snapshot 捕获 guest
正在 hotplug 或 suspend CPU1，`GICR_WAKER`、KVM MP state 和 PSCI state 必须一致。

## 10. CPU1 生命周期：把 PSCI、KVM MP state、WFI 与 IRQ 串起来

Timer 和 GIC 状态正确仍不保证 CPU1 执行 handler。还必须确认 CPU1 在固件、KVM 和
guest 架构三个层面的生命周期一致，并区分“被唤醒”和“进入 IRQ exception”。

### 10.1 三种状态属于不同控制层

| 状态层 | 典型状态 | 谁使用 | 回答的问题 |
| --- | --- | --- | --- |
| PSCI | `OFF`、`ON_PENDING`、`ON` | guest 固件与 OS | CPU power 请求处于哪一步 |
| KVM MP state | `RUNNABLE`、`STOPPED`、可选 `SUSPENDED` | VMM 与 KVM | vCPU 是否允许运行 |
| PE 架构状态 | PC、PSTATE、WFI、异常 mask | guest CPU context | 下一条指令及异常是否可 taken |

这些状态相互关联，但不能互相替代。PSCI `ON` 不等于 KVM MP state 必然 `RUNNABLE`；
MP state 可运行也不等于 `PSTATE.I` 已清除，更不等于 GIC 已经投递 Timer PPI。

### 10.2 PSCI 启动把 CPU1 带到 per-CPU 初始化阶段

PSCI 对 secondary CPU 的主状态迁移为：

```text
OFF --CPU_ON--> ON_PENDING --target initialized--> ON
ON  --CPU_OFF succeeds--> OFF
```

`CPU_ON` 提供目标 MPIDR、entry point 和 context ID。目标首次进入返回异常级时，从
entry point 执行，AArch64 的 `X0` 保存 context ID。

启动初期 `SPSR_ELx.{D,A,I,F}` 均为 1。随后固件和 Linux secondary 启动代码依次建立
MMU、GIC CPU interface、per-CPU clockevent，最后才解除需要的异常 mask。

因此 Snapshot 中 `PSTATE.I=1` 不一定错误。必须结合 PC、PSCI 阶段、GIC group enable
和 Linux per-CPU 初始化状态判断。单独看到一个 mask 位不能推出 CPU1 故障。

PSCI 的 CPU_OFF 流程还要求处理 pending interrupt、阻止目标 PE 的 PPI/SGI，并让 CPU
interface 进入 quiescent state。若 Snapshot 正好捕获 hotplug/power transition，恢复必须
同时保持这些状态。

### 10.3 KVM MP state 决定 vCPU 是否有机会运行

`KVM_ARM_VCPU_POWER_OFF` 可使 secondary vCPU 初始保持 power-off。CubeSandbox 恢复
vCPU 时最后写 MP state，然后才恢复 vGIC、启动线程并 resume。

CPU1 若被恢复为 `STOPPED`，即使 Timer/GIC 完全正确也不会执行 guest。若被错误恢复为
`RUNNABLE`，则可能跳过 guest 预期的 `CPU_ON` 初始化阶段。

目标内核支持哪些可设置 MP state 必须通过 ABI 实测。PSCI 状态和 KVM MP state 应被
联合记录，但不能用其中一个推导另一个。

### 10.4 WFI wakeup 与 IRQ taken 是两个事件

![WFI wakeup 与 IRQ exception taken 的分界](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_ASSETS_20260722/05-wfi-wakeup-vs-irq-taken.svg)

`WFI` 是允许实现进入等待状态的 hint，也可以被 KVM trap 和模拟。符合条件的 IRQ 可以
成为 WFI wakeup event，而不考虑对应的 `PSTATE.I/F` mask。

这意味着 PE 可以离开 WFI，但因 `PSTATE.I=1`、group disabled 或 priority 不通过而不
进入 IRQ handler。中断保持 pending，直到门控重新打开。

诊断时应按以下顺序观察：

```text
TimerConditionMet
  -> timer line
  -> GIC effective pending
  -> GIC IRQ signal
  -> KVM/WFI wakeup
  -> PSTATE/group/priority gates
  -> IRQ exception taken
  -> handler rearm timer and deactivate PPI
```

“CPU1 离开 WFI”不能证明 handler 已执行；“PSTATE.I=1”也不能解释完全没有 wakeup。
前者缺少 exception taken 证据，后者之前还存在 Timer、Redistributor 和 CPU interface。

### 10.5 WFI 不是 Snapshot 静止点

Arm ARM 不保证 WFI 排空 pending memory activity。WFI 的低功耗语义也不是 VMM
Snapshot quiescence 的定义。

因此 CPU1 停在 WFI 只说明 guest 当时没有继续执行的工作，不能证明 host vCPU thread、
KVM timer、vGIC 和 guest memory 已构成原子快照。静止边界仍由第 4 节的 Pause 协议建立。

## 11. Snapshot/Restore 是跨状态域的有序事务

到这里可以把机制重新接回 CubeSandbox。Snapshot/Restore 的正确性不由某个寄存器决定，
而取决于 VM-wide 时间、per-vCPU Timer/MP state、vGIC、memory 和 devices 是否按依赖
顺序保存与恢复。

![CubeSandbox ARM64 Snapshot/Restore 状态耦合与时序窗口](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_ASSETS_20260722/06-snapshot-restore-state-coupling.svg)

### 11.1 Snapshot：先建立稳定边界，再逐状态域读取

当前 `Vm::snapshot()` 要求 VM 逻辑状态已经是 `Paused`，然后按以下顺序保存：

```text
per-vCPU core/sys/MP state
  -> guest memory
  -> vGIC Distributor/Redistributor/ICC/ITS
  -> userspace device state
  -> VM metadata and snapshot artifact
```

这个顺序把 vCPU state 放在 vGIC 之前。`add_vgic_snapshot_section` 会使用已保存的 vCPU
状态建立 Redistributor typer，再读取 vGIC state，因此 vCPU identity 是 vGIC 保存的输入。

当前 vGIC state 保存 Distributor、Redistributor、ICC 与 ITS 等 device attributes，
但没有单独保存 `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO`。Timer PPI source line 需要由恢复后的
Timer 条件正确重建。

Pause 的 immediate-exit ACK 保证 vCPU 已完成一致化的 `KVM_RUN`，但不保证 userspace
线程已经执行到 `park()`。vCPU mutex、pause flag 和 VGIC 停机访问约束共同构成当前
实现的一致性边界。

### 11.2 Restore：先重建对象，再恢复状态，最后允许运行

当前恢复顺序为：

```text
创建 VM 并映射 memory
  -> DeviceManager 基础对象
  -> 逐 vCPU set core registers
  -> 按保存顺序 set system registers
  -> set MP state
  -> 创建并恢复 vGIC，启用中断路由
  -> 恢复其余 devices
  -> 启动 restored vCPU threads，保持 paused
  -> Vm::resume 清 pause flag 并 unpark
  -> 首次正常 KVM_RUN
```

该顺序满足“状态写完后才让 vCPU 正常运行”的基本要求，但内部存在三个跨域窗口：

| 窗口 | 状态边界 | 必须保证 |
| --- | --- | --- |
| W1 | 同一 vCPU 的 Timer system registers 逐项写入 | 启用位不能让半恢复 comparator 产生错误 line |
| W2 | per-vCPU Timer/MP state 已写，vGIC 尚未恢复 | Timer line 与 Redistributor latch/active 不发生错误合并 |
| W3 | resume/unpark 到首次正常 `KVM_RUN` | MP、PSTATE、GIC gates 与 Timer deadline 已互相兼容 |

具体函数与真实代码段见关联链路文档。本文关注三个窗口背后的 KVM/Arm 状态依赖。

### 11.3 为什么单次 ioctl 成功不足以证明恢复正确

| 边界 | 单次成功能证明什么 | 仍不能证明什么 |
| --- | --- | --- |
| `KVM_SET_ONE_REG` | 该 register ID 的调用被 KVM 接受 | counter 写入未被 offset ABI 忽略 |
| `KVM_SET_MP_STATE` | KVM 接受该 vCPU 的 MP state | PSCI 与 guest 启动阶段一致 |
| VGIC device attr | 某个 GIC 字段读写成功 | line、latch、active、ICC 状态整体一致 |
| `Vm::restore` 返回 | VMM 完成预定调用序列 | guest 已获得第一个 Timer IRQ |
| agent/vsock ready | guest 某条通信路径曾经推进 | scheduler tick 和 CPU1 长期推进正常 |

KVM ABI 是逐对象、逐 ioctl 的接口。它不会把所有 vCPU、vGIC 和 memory 自动锁定到一个
逻辑时间点，也不会替 VMM验证跨状态域公式。

### 11.4 当前恢复顺序成立所需的前置条件

1. 所有 vCPU 未正常运行时，才读取或写入完整 vGIC state。
2. counter offset 在正确的 VM 生命周期阶段建立，并对全部 vCPU 使用同一策略。
3. CPU1 Timer one-reg 写入未被忽略，也未被后续初始化覆盖。
4. vCPU 创建顺序、MPIDR 和 Redistributor region 顺序与 Snapshot 一致。
5. Timer line 在首次正常 `KVM_RUN` 前，由完整的 count、CVAL 和 CTL 重新计算。
6. PPI latch、active、enable、group、priority 与 CPU interface 状态共同恢复。
7. MP state、PSCI 阶段、PC/PSTATE 与 guest per-CPU 初始化进度一致。

### 11.5 端到端不变量

可以用一条因果链概括整个机制：

```text
同一 VM-wide 时间轴
  -> CPU1 comparator 在正确 deadline 到期
  -> Timer line 按 CTL 变高
  -> Redistributor 1 形成有效 pending
  -> group/priority/CPU interface 允许投递
  -> KVM 唤醒 CPU1
  -> PSTATE 允许 IRQ exception
  -> handler rearm Timer 并 deactivate PPI
```

故障定位应沿这条链寻找第一个断点。只要上游状态尚未证明正确，就不应直接从下游的
RCU stall、RPC timeout 或高 CPU 反推某个寄存器是根因。

## 12. 沿端到端链路判定 Timer、GIC 与 CPU 状态

第 8 至 11 节建立了从时间轴到 handler 的因果链。诊断时应按表格自上而下寻找第一个
异常状态；越靠后的现象，越可能只是上游错误的结果。

### 12.1 从时间轴到 CPU 执行的状态组合

| 观测组合 | 架构解释 | 优先检查 |
| --- | --- | --- |
| `CNTVCT` 恢复后大幅前跳 | 大量 deadline 立即过期 | offset 计算与恢复策略 |
| `CNTVCT` 后跳或停止推进 | deadline 长期不到期 | counter offset、宿主 KVM timer |
| `CVAL-CNTVCT` 异常大正值 | CPU1 下一事件被推到远期 | CVAL 与 offset 是否同基准 |
| `ENABLE=0` | timer 无输出 | CTL 保存/恢复、guest 是否主动关闭 |
| `ENABLE=1, ISTATUS=1, IMASK=1` | 已到期但源端屏蔽 | CTL 恢复与 guest clockevent 阶段 |
| timer line=1，ISPENDR latch=0 | latch 可为 0，但 effective pending 应由 line 保持 | line-level API、GIC 投递门控 |
| PPI pending=1，IRQ 不 taken | 投递条件未满足 | enable、group、PMR、PSTATE.I、routing |
| PPI active=1，line=1 | deactivate 后会再次 pending | handler 未清源或 active 恢复错误 |
| WFI 被唤醒，handler 不执行 | wakeup 与异常 taken 条件不同 | IRQ mask、group、priority |
| CPU1 MP state=STOPPED | vCPU 不执行 | PSCI/KVM MP state 恢复 |
| `GICR_WAKER.ProcessorSleep=1` | 中断保持 pending，仅请求唤醒 | CPU hotplug/power 状态恢复 |
| CPU1 MPIDR 关联错误 Redistributor | PPI 状态落到错误 CPU | vCPU/region 创建顺序 |

### 12.2 RCU 错误的诊断边界

Linux RCU stall 可能由 CPU 长时间关中断、scheduler-clock interrupt 停止、timer wakeup
未发生、时间突然前跳或 IRQ/exception 路径错误引起。因此它能证明时间推进或调度条件
被破坏，但不能单独证明 Generic Timer 寄存器损坏。

定位时应比较成功和失败在同一阶段的 vCPU、timer、counter offset、PPI 和首次
`KVM_RUN` 状态。第一个不满足 Arm 公式或 KVM ABI 前置条件的阶段才是修复位置；RPC
超时、RCU 日志的打印时刻和 Shim 高 CPU 通常已经是下游表现。

## 13. 工程结论

1. “VM 已 Paused”“vCPU 已退出 KVM_RUN”和“vCPU 线程已 park”不能混为一谈。
2. 固定静止窗口只能用于验证时序敏感性，不能作为正式修复。
3. 当前代码通过 immediate-exit 和 vCPU mutex 提供部分一致性保证，不能仅凭未 park
   就断言快照不一致。
4. 如果确认 Pause 返回过早，应使用明确的同步协议，例如 vCPU 到达稳定点的 ACK，
   而不是固定 sleep。
5. 如果 vCPU 状态在 snapshot 时一致、恢复后才分歧，应把修复放在 KVM ARM timer offset、
   per-vCPU timer 或 vGIC 恢复顺序上。
6. WFI wakeup 与 IRQ taken 是两个阶段；PSTATE.I 被置位不能解释 timer line 是否丢失。
7. Timer PPI 的完整状态还包括正确 Redistributor、source line、pending latch、active、
   enable/group/priority 与 CPU interface，不能只检查一个 pending bit。
8. 必须实测 `KVM_CAP_COUNTER_OFFSET` 路径，不能用 one-reg 调用成功推断 counter 已恢复。

## 14. 关键源码入口

| 模块 | 文件 | 关键函数 |
| --- | --- | --- |
| CubeShim Snapshot 分流 | `CubeShim/shim/src/snapshot/mod.rs` | `Snapshot::handle` |
| app snapshot | 同上 | `do_app_snapshot`、`api_pause_vm`、`api_snapshot_vm`、`api_resume_vm` |
| Sandbox restore | `CubeShim/shim/src/sandbox/sb.rs` | `start_vm`、`restore_vm` |
| VMM API | `hypervisor/vmm/src/lib.rs` | `vm_pause`、`vm_snapshot`、`vm_restore` |
| VM Pause/Snapshot | `hypervisor/vmm/src/vm.rs` | `Vm::pause`、`Vm::snapshot`、`Vm::restore` |
| vCPU 生命周期 | `hypervisor/vmm/src/cpu.rs` | `start_vcpu`、`CpuManager::pause/resume/snapshot/restore` |
| KVM ARM 状态 | `hypervisor/hypervisor/src/kvm/mod.rs` | ARM64 `state`、`set_state` |
| VM 与 vGIC 编排 | `hypervisor/vmm/src/vm.rs` | `add_vgic_snapshot_section`、`restore_vgic_and_enable_interrupt` |
| KVM vGIC state | `hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs` | `KvmGicV3Its::state`、`KvmGicV3Its::set_state` |

## 15. 官方资料与本文保存的规范内容

本节给出可审计来源。第 7 至 12 节已经把分析所需的规范语义写入本文，链接用于
核对版本和原始上下文，不是对正文内容的替代。

### 15.1 Arm Architecture Reference Manual

- 文档：Arm Architecture Reference Manual for A-profile architecture
- 文档编号与版本：DDI 0487 M.c
- 官方入口：<https://developer.arm.com/documentation/ddi0487/latest/>

| 官方章节 | 本文保留的内容 |
| --- | --- |
| D1.7.2 Wait for Interrupt mechanism | WFI hint/trap、wakeup 与 IRQ taken 的区别、mask 不阻止 wakeup |
| D12 Generic Timer in AArch64 state | physical/virtual count、timer comparator 与虚拟化模型 |
| D24.10.1 `CNTFRQ_EL0` | 频率由固件写入，硬件不解释该值 |
| D24.10.2 `CNTHCTL_EL2` | EL1 physical/virtual counter 与 timer 的 access/trap 控制 |
| D24.10.18 `CNTPOFF_EL2` | FEAT_ECV physical offset 的适用范围 |
| D24.10.25-30 | self-synchronized count、`CNTVCT`、`CNTVOFF`、`CTL/CVAL/TVAL` |
| C6.2.504 `WFI` | 指令是可 trap 的低功耗 hint |

### 15.2 Arm Generic Timer 指南

- 文档：Learn the architecture - Generic Timer
- 文档编号与版本：102379_0104_01_en，Version 1.4，2024
- 官方入口：<https://developer.arm.com/documentation/102379/0104/>

本文保留了该指南第 3 至 5 章的核心内容：System Counter 结构、56 至 64 位宽度、频率
与分辨率区别、timer 寄存器族、CVAL/TVAL 编程、CTL 输出条件、level-sensitive 中断、
virtual count 公式、CNTVOFF 以及各 timer 的 SBSA 推荐 INTID。

### 15.3 Arm GICv3/v4 Architecture Specification

- 文档：Arm Generic Interrupt Controller Architecture Specification, GICv3 and GICv4
- 文档编号与版本：IHI 0069 H.b，GICv3.3/GICv4.2，2024
- 官方入口：<https://developer.arm.com/documentation/ihi0069/latest/>

| 官方章节 | 本文保留的内容 |
| --- | --- |
| 1.2.1-1.2.2 | PPI、level-sensitive 语义和四态 interrupt state machine |
| 2.1-2.2 | Distributor/Redistributor 职责、PPI INTID 范围 |
| 4.1 | generate、deliver、activate、priority drop、deactivate 生命周期 |
| 4.7-4.8 | individual/group enable 与 `ICC_PMR_EL1` priority mask |
| 11.6、12.11.42 | power management、`GICR_WAKER` quiescent 协议 |
| 12.11 | `GICR_ISENABLER0/ISPENDR0/ISACTIVER0` 等 per-PE 状态 |

### 15.4 Arm PSCI

- 文档：Arm Power State Coordination Interface
- 文档编号与版本：DEN 0022 F.b，PSCI 1.3，2024
- 官方入口：<https://developer.arm.com/documentation/den0022/latest/>

本文保留了 `CPU_OFF`、`CPU_ON`、`AFFINITY_INFO` 的接口语义，以及第 6.4 节 secondary
CPU 初始状态、第 6.6 节 ON/OFF/ON_PENDING 竞态、第 6.8 节 timer/GIC context 保存和
CPU interface quiescent 要求。

### 15.5 Linux KVM 与 RCU 官方文档

- KVM API：<https://docs.kernel.org/virt/kvm/api.html>
- Arm VGICv3 userspace API：<https://docs.kernel.org/virt/kvm/devices/arm-vgic-v3.html>
- RCU CPU stall detector：<https://docs.kernel.org/RCU/stallwarn.html>

本文保留了 KVM one-reg、MP state、`KVM_ARM_VCPU_POWER_OFF`、
`KVM_ARM_SET_COUNTER_OFFSET` 的关键 ABI，以及 VGIC Redistributor 关联顺序、line-level
与 pending latch 分离、运行中 vCPU 访问限制和 RCU timer-stall 判读方法。

Linux 文档随内核演进。实际修复前应同时保存目标宿主的 `uname -r`、KVM capability
探测结果和对应内核源码版本，不能只依据 docs.kernel.org 当前版本判断旧内核行为。
