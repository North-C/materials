# Arm GIC 基础概念与 CubeSandbox 中 CPU1 第一个 Tick 的全链路分析

## 1. 文档信息

- 日期：2026-07-21
- 适用版本：CubeSandbox v0.5.1（cloud-hypervisor v28.0 fork），ARM64 / GICv3 / KVM
- 关联文档：
  - `CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_20260720.md`（规范语义，§9 为 GIC 部分）
  - `CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md`（恢复窗口 W1/W2/W3 与插桩点 B1-B11）
- 本文分四部分：
  - 第一部分（§2-§7）：GIC 基础概念原理讲解（SGI/PPI/SPI/LPI、IRQ/FIQ、硬件与 OS 处理流程）；
  - 第二部分（§8-§10）：把上述概念映射到 CubeSandbox 恢复路径，给出"CPU1 第一个
    timer tick 如何到达"的逐环节全链路图，标注每环节对应的寄存器、代码位置和失效模式；
  - 第三部分（§12-§16）：KVM vGIC 深入——它与 GIC 硬件的交互（直通/trap/LR 注入/
    maintenance/timer 硬件路径），以及它与上层 VMM 的交互（设备创建、注入、
    保存/恢复 ABI、CubeSandbox 代码落点）；
  - 第四部分（§17-§19）：Generic Timer 深入——架构总纲解读（System Counter 与
    comparator）、CVAL/TVAL 两种编程方式在 Linux 中的应用、KVM 的 timer 虚拟化机制。

---

# 第一部分：Arm GIC 中断体系原理

## 2. GIC 在系统中的位置

现代 Arm SoC 中，外设和核间事件不直接连到 CPU，而是汇聚到 GIC（Generic Interrupt
Controller），由 GIC 决定"哪个中断、送哪个核、什么时候送"：

```text
外设 / 定时器 / 核间事件
      │ (中断线 / 消息)
      ▼
   GIC: Distributor（全局管理，SPI）
        Redistributor（每核一份，SGI/PPI）
        ITS（消息中断翻译，LPI）
      │ (每核一组 IRQ/FIQ 信号)
      ▼
   CPU interface（ICC_*_EL1 系统寄存器）
      │
      ▼
   PE（异常级 EL0-EL2，PSTATE.I/F 屏蔽）
```

GIC 做三件事：**仲裁**（多个中断谁优先）、**路由**（送到哪个核/哪个异常级/IRQ 还是
FIQ）、**状态跟踪**（每个中断处于什么状态）。

## 3. 四类中断源：SGI / PPI / SPI / LPI

GIC 用 INTID（中断号）区分来源，ID 空间直接编码类别：

| 类型 | INTID 范围 | 作用范围 | 产生方式 | 典型使用者 |
| --- | --- | --- | --- | --- |
| **SGI**（Software Generated） | 0–15 | 核→核 | 软件写 `ICC_SGI1R_EL1` 显式触发 | OS 核间调用（IPI）：调度器唤醒、TLB shootdown、CPU hotplug |
| **PPI**（Private Peripheral） | 16–31 | 每核私有 | 该核专属的外设中断线 | 每核自己的 Generic Timer（EL1 virtual timer 为 PPI 27）、PMU 中断 |
| **SPI**（Shared Peripheral） | 32–1019 | 全局共享，可路由到任意核 | 普通外设中断线 | 磁盘、网卡、UART、virtio 设备 |
| **LPI**（Locality-specific） | ≥8192 | 消息式中断 | 设备写消息到 ITS 翻译器地址（MSI 风格） | PCIe MSI/MSI-X、大规模虚拟设备 |

理解区别的关键在于"**状态存在哪里、谁看得见**"：

- **SGI/PPI 是 per-PE 的**。每个核的 Redistributor 里各有一份独立的
  enable/pending/active 状态。CPU0 的 timer（PPI 27）和 CPU1 的 timer（PPI 27）
  INTID 相同，但**是两条物理上独立的中断线、两份独立的 GIC 状态**——这正是
  "CPU0 正常、CPU1 timer 不 tick"能在同一 INTID 上发生的原因。SGI 类似，只是
  触发源是软件。
- **SPI 是全局的**。Distributor 里只有一份状态，通过 `IROUTER` 配置送往哪个核
  （或一组核）。OS 用它做中断亲和性（irq affinity）。
- **LPI 没有物理中断线**。设备往 `GITS_TRANSLATER` 地址写一个 EventID，ITS 查表
  翻译成"INTID + 目标核"，再经 Redistributor 投递。用于支持 PCIe MSI-X 的海量
  向量和虚拟化直投场景。

## 4. IRQ 与 FIQ

IRQ/FIQ **不是中断源，而是 GIC 发给 PE 的两条物理异常信号**——四类中断中的任何
一个，最终都以 IRQ 或 FIQ 的形式捅到核上：

| | IRQ | FIQ |
| --- | --- | --- |
| 优先级 | 普通 | 高 |
| 屏蔽位 | `PSTATE.I` | `PSTATE.F` |
| GIC 映射 | 通常 Group 1（非安全） | 通常 Group 0（安全） |
| 设计意图 | 通用中断 | 安全/高实时性事件 |
| Linux 实际使用 | 全部中断 | 基本不用（仅 perf pseudo-NMI） |

在安全世界设计里，Group 0 中断配置为 FIQ 并路由到 EL3，即使非安全 OS 屏蔽 IRQ，
安全世界仍能抢进去。KVM 虚拟化场景下 guest 看到的 IRQ/FIQ 都是 vGIC 虚拟的。

**关键架构语义**（与 WFI 问题直接相关）：IRQ/FIQ 信号到达 PE 后能否真正进入异常
处理，要过三关：

```text
GIC 认为可投递（enable + group enable + 优先级 > ICC_PMR_EL1 掩码）
  AND 目标异常级路由允许
  AND PSTATE.I/F 未屏蔽 → IRQ/FIQ taken（进入向量）
```

**WFI 唤醒不要求 IRQ taken**。被 `PSTATE.I` 屏蔽的中断足以把核从 WFI 唤醒，却不
进入 handler。"CPU1 离开 WFI" ≠ "timer handler 执行了"，两者之间隔着整条判定链。

## 5. 硬件处理流程：一个中断的生命周期

GIC 为每个中断维护四态状态机：

```text
Inactive → Pending → Active → Inactive
              ↘ Active and Pending ↗
```

以 CPU1 的 virtual timer（PPI 27，电平触发）为例：

1. **触发**：comparator 条件满足（`CNTVCT ≥ CVAL` 且 `CTL.ENABLE=1`、`IMASK=0`），
   timer 输出线拉高。电平触发时 GIC 见线为高就把 `GICR_ISPENDR0` 对应位置 1
   （pending）。
2. **仲裁**：Redistributor 检查 enable（`GICR_ISENABLER0`）、group
   （`IGROUPR`+`IGRPMODR`）、优先级（`IPRIORITYR`）；CPU interface 检查 group
   enable（`ICC_IGRPEN1_EL1`）和优先级掩码（`ICC_PMR_EL1`）。只有优先级高于掩码
   的最高优先级 pending 中断才发 IRQ 信号给 PE。
3. **Acknowledge**：PE 进入 IRQ 异常，handler 读 `ICC_IAR1_EL1`，返回 INTID 并把
   中断翻转为 **active**（硬件自动清 pending latch——但对电平中断，源线仍高时会
   立刻重新 pending）。
4. **处理**：timer handler 必须**撤销源电平**（写新 CVAL、清 ENABLE 或置 IMASK），
   否则下一步之后 GIC 重新 pending，形成中断风暴。
5. **EOI 与 deactivate**：写 `ICC_EOIR1_EL1`（priority drop）；分离 EOImode 还需
   写 `ICC_DIR_EL1` deactivate，中断回到 inactive。

电平 vs 边缘的差别是两类相反故障的根源：

- **丢线**：恢复后 timer 电平与 GIC pending latch 不一致 → CPU1 永远等不到 tick
  → RCU stall；
- **粘线**：active 恢复错误或源电平一直为高 → 重复 IRQ → vCPU/进程 100% 空转
  （对应社区 Issue #6001）。

## 6. OS（Linux）一侧的处理

- **INTID → Linux IRQ 号**：GIC 驱动（`irq-gic-v3.c` + `irq-gic-v3-its.c`）注册
  irq_domain，SPI/PPI/LPI 映射到 Linux 虚拟 IRQ 号。device tree 中 timer 节点声明
  `interrupts = <GIC_PPI 11 IRQ_TYPE_LEVEL_HIGH>`（11+16=PPI 27），arch_timer 驱动
  据此注册 per-CPU clockevent。
- **执行上下文**：IRQ taken → `el1_irq` → hardirq 上下文（关中断、只做必要工作）
  → 重活交给 softirq/tasklet/workqueue。日志中的 `timer-softirq=110` 是 RCU stall
  检测器发现 timer 软中断长期未跑——它是"tick 丢失"的下游症状，不是第一现场。
- **per-CPU 中断的特殊性**：PPI/SGI 是 percpu irq，不能跨核迁移；每个核独立
  `enable_percpu_irq()`。CPU hotplug（PSCI CPU_OFF/ON）时，per-CPU 的 timer 和
  GIC CPU interface（`ICC_*`）都要逐个重新初始化。
- **FIQ**：Linux 基本只留给 perf pseudo-NMI，普通驱动不使用。

## 7. 虚拟化视角（KVM vGIC）

- **CPU interface 硬件直通**：EL2 的 `ICH_LR*_EL2`（List Register）装入虚拟中断，
  guest 读 `ICC_IAR1_EL1` 由硬件直接响应，ack/EOI 大多不 trap。
- **Distributor/Redistributor 由 KVM 软件模拟**：guest 对 GICD/GICR MMIO 的访问
  trap 到 KVM；快照/恢复时 VMM 通过 `KVM_GET/SET_DEVICE_ATTR` 读写的正是这份软件
  状态（CubeSandbox 快照中 dist=568 + rdist=48 + icc=18 共 634 项，见
  `CUBESANDBOX_CH_ISSUE6966_UB_COMPARISON_20260721.md` §7.2）。
- **timer 中断由 KVM 内核产生**：KVM 按 guest 的 CVAL/CTL 模拟 comparator。vCPU
  在 PE 上运行时，guest 的 timer 上下文直接装载到硬件 timer，到期即硬件 vtimer
  IRQ；vCPU 被阻塞（WFI trap 到 KVM）时，KVM 用后台软件 timer 在到期时把 PPI 的
  **line level** 置位并唤醒 vCPU。因此 **line level 由 KVM timer 子系统计算，
  pending/active latch 由 vGIC 子系统管理**——两个子系统恢复顺序不一致时，line 与
  latch 就会错位（CubeSandbox W2 窗口的本质）。
- **line level 与 pending latch 的 ABI 分离**：`GICR_ISPENDR0` device attr 读写的
  是软件 latch；真实输入电平要走 `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO`。guest 可见
  pending ≈ latch OR line。只恢复快照中的 latch 无法重建完整电平状态。
- **WFI trap**：guest 执行 WFI 通常 trap 到 KVM，宿主线程阻塞在 `KVM_RUN` 内，
  有可投递虚拟中断时才返回 guest。"虚拟中断形成"与"vCPU 线程被唤醒"之间隔着
  KVM 调度。

---

# 第二部分：CubeSandbox 恢复后 CPU1 第一个 Tick 的全链路

## 8. 全链路图

以下按时间顺序展开从 `VmRestore` API 进入到 guest CPU1 执行第一个 timer handler
的完整链条。标注约定：`[W1]/[W2]/[W3]` 为
`CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md` §6.4 定义
的时序窗口；`(Bx)` 为该文档 §7.4 的插桩点；文件行号基于 `source_code/CubeSandbox`。

```text
阶段 A: vCPU 状态恢复（vmm 线程，vm.rs:2762-2771）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  create_vcpu (cpu.rs:795-829)
    → vcpu.init(&vm)                         :807-808
    → vcpu.restore(snapshot) → set_state()   :810
        kvm/mod.rs:2176-2192:
          set_regs(core regs: X0-X30/SP/PC/PSTATE)   :2179
          for reg in sys_regs: KVM_SET_ONE_REG        :2181-2187
            ├─ idx 8: KVM_REG_ARM_TIMER_CTL  ← [W1 起点]
            │    CTL=5 (ENABLE+ISTATUS) 写入后，
            │    KVM timer 子系统即认为 timer 已启用，
            │    但此时 CNT/CVAL 还是新建 vCPU 的 UNKNOWN 值
            ├─ idx 9: KVM_REG_ARM_TIMER_CNT
            └─ idx 10: KVM_REG_ARM_TIMER_CVAL ← [W1 终点]
          set_mp_state(RUNNABLE)                      :2189
  (Bx: B2 快照数据记录/B3 timer 写入顺序/B4 可选读回)

阶段 B: vGIC 创建与恢复（vmm 线程，vm.rs:2773-2774）[W2]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  restore_vgic_and_enable_interrupt (vm.rs:2286-2359)
    → create_vgic(vcpu_count=2)              :2300-2308
    → init_pmu(PPI+16)                       :2311-2315
    → set_gicr_typers(saved_states)          :2318-2325
    → gic set_state (gic/mod.rs:398-462):
        gicd_ctlr → dist(568 项)             :401-403
                 → redist(每 CPU 24 项)       :405   ← CPU1 的 PPI27
                 │    enable/pending latch/group/priority 落在这里
                 → icc(每 CPU 9 项)           :407   ← CPU1 的
                 │    SRE/CTLR/IGRPEN0/IGRPEN1/PMR/BPR/AP
                 → ITS ...                    :410-461
    → enable() 开启 irq 路由                  :2343-2357
  [W2 终点：此前 timer line 已形成，但 CPU1 的 PPI 状态才刚写好]
  (Bx: B5 vgic_restore 各阶段)

阶段 C: vCPU 线程启动并保持 paused（vm.rs:2787-2794）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  start_restored_vcpus (cpu.rs:1178-1185)
    → activate_vcpus(n, false, Some(true))   (cpu.rs:1107-1144)
        vcpus_pause_signalled.store(true)    :1121-1123
        start_vcpu 逐线程 spawn               :1134-1137 (线程名 vcpu{id}, :916)
        新线程第一圈即命中 pause 分支 (cpu.rs:968-999)
          → immediate-exit KVM_RUN → park()
  Vm::restore 末尾 state=Paused (vm.rs:2808)
  随后 vm.resume() (lib.rs:727 → cpu.rs:2080-2096)
        vcpus_pause_signalled.store(false)   :2086
        unpark_thread() 逐 vCPU               :2092-2094
  [W3 起点：CPU1 线程离开 park 循环 (cpu.rs:995-998)]
  (Bx: B6 线程启动/B7 unpark 时间戳)

阶段 D: CPU1 首次 KVM_RUN（vCPU 线程，cpu.rs:1012-1014）[W3 核心]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  vcpu.lock().run() → ioctl KVM_RUN
    KVM 在 vCPU load 时把 guest timer 上下文（CVAL/CTL）装载到硬件 PE，
    按 VirtualCount = PhysicalCount - CNTVOFF_EL2 评估 comparator：
    ├─ 若 CVAL 在未来：装载硬件 timer，guest 直接运行，
    │   到期时硬件产生 vtimer IRQ（不经过 KVM 软件路径）
    └─ 若 CVAL 已过期 / vCPU 即将阻塞（WFI trap）：
        KVM 后台 swtimer 到期 → 置 PPI27 line level → 唤醒 vCPU
  (Bx: B8 首次 KVM_RUN enter/exit reason)

阶段 E: vGIC 仲裁与投递（KVM 内核）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CPU1 的 PPI27 可投递条件（全部来自阶段 B 恢复的状态）：
    line level (KVM timer 子系统, 阶段 D)
      OR GICR_ISPENDR0 latch (redist 恢复)
    AND GICR_ISENABLER0.enable=1      (redist 恢复)
    AND group/IGRPMODR 正确            (redist 恢复)
    AND ICC_IGRPEN1_EL1=1              (icc 恢复, 实测 =0x1)
    AND priority > ICC_PMR_EL1         (icc 恢复, 实测 =0xf0)
    → 写入 ICH_LR_EL2，guest 侧 IRQ 信号成立

阶段 F: guest 侧异常进入与处理（guest Linux）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  PSTATE.I=0（CPU1 完成 percpu 初始化并开中断后）
    → IRQ taken → el1_irq → arch_timer handler
    → handler 写新 CVAL（撤销源电平）→ EOI (ICC_EOIR1_EL1)
    → scheduler tick 推进 → timer softirq 运转 → RCU 正常
  若 PSTATE.I=1 且 CPU1 停在 WFI：IRQ 信号只能唤醒 WFI，不能进入 handler
  [W3 终点：第一个 tick 完成]
  (Bx: B10 reset_guest 成功=链路 F 已通的间接证据)
```

## 9. 逐环节寄存器/代码/失效模式对照表

| 环节 | 关键寄存器/状态 | 代码位置 | 失效模式 | 对应观测 |
| --- | --- | --- | --- | --- |
| A. timer 寄存器恢复 | `CTL`/`CNT`/`CVAL`（one-reg idx 8/9/10） | `kvm/mod.rs:2181-2189` | CTL 先写使过期 timer 提前 enable；值被静默忽略（VM offset 启用后 CNT 写入被忽略且无错误返回） | B3/B4；v16 已证值未被丢弃 |
| A. MP state | `KVM_SET_MP_STATE`（RUNNABLE/STOPPED） | `kvm/mod.rs:2189` | CPU1 恢复为 STOPPED → 永不执行 guest | B2（快照 MP state） |
| A. PSTATE | `PSTATE.I`（core regs） | `kvm/mod.rs:2179` | 必须与 PC 所处启动阶段匹配；单独看不能定罪 | B2 |
| B. redist per-CPU 状态 | `GICR_ISENABLER0/ISPENDR0/IGROUPR/IPRIORITYR` | `gic/redist_regs.rs`；恢复于 `gic/mod.rs:405` | latch 恢复与 line level 错位；恢复到错误的 Redistributor（typer 关联错） | B5；快照 rdist=24 项/CPU |
| B. icc per-CPU 状态 | `ICC_SRE/IGRPEN1/PMR/...` | `gic/icc_regs.rs`；恢复于 `gic/mod.rs:407` | PMR/IGRPEN 错误 → pending 存在但不投递 | 快照实测 `IGRPEN1=1, PMR=0xf0` |
| B. 顺序 | dist→redist→icc→enable | `gic/mod.rs:398-462`、`vm.rs:2328-2357` | timer line 在 redist/icc 写好前已形成（W2） | B5 时间戳与 B3 对齐 |
| C/D. unpark→首跑 | `vcpus_pause_signalled`、线程 park 状态 | `cpu.rs:2086-2094`、`:995-998`、`:1012` | unpark 与 vGIC ready 竞态；首次 KVM_RUN 前后 line 被重算 | B7/B8 |
| D. KVM timer 评估 | `VirtualCount=PhysicalCount-CNTVOFF_EL2`、comparator | KVM 内核（宿主机 6.6） | VM-wide offset 与 per-vCPU CVAL 基准不一致 → 立即过期或远期不到期 | B3/B8；guest cntvct 样本 |
| E. 投递判定 | line/latch/enable/group/priority/PMR/IGRPEN1 | KVM vGIC | 任一条件不满足 → pending 存在但 IRQ 不 taken | §10 采集清单 |
| F. guest 处理 | `PSTATE.I`、clockevent 注册、WFI | guest Linux | WFI 唤醒≠IRQ taken；handler 未清源 → 中断风暴 | guest 侧 arch_timer IRQ 计数 |

## 10. 与该链路对应的观测清单（落地版）

结合插桩设计文档 §7.4 的 B 系列点位，验证"第一个 tick 是否按链路到齐"需要采集：

1. **阶段 A 结束时（每 vCPU）**：`CTL/CNT/CVAL` 写入值与返回码（B3，TraceBuf 内存
   记录）、快照中的 PC/PSTATE.I/MP state（B2）。
2. **阶段 B 各子阶段时间戳**（B5）：确认 redist/icc 恢复晚于 timer 写入（W2 宽度），
   并从快照数据核对 CPU1 的 `GICR_ISENABLER0`（PPI27 enable）、`ISPENDR0` latch、
   `IPRIORITYR[27]`。
3. **阶段 D 首次 KVM_RUN**（B8，once flag）：enter 时刻、exit reason（是否 WFI
   wakeup）、随后第一个 timer IRQ 的注入（guest 侧 arch_timer IRQ 计数从 0 变 1）。
4. **line level 直读**：对 CPU1 的 PPI27 用 `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO`
   读取真实电平，与 latch（`GICR_ISPENDR0`）、按公式
   `expired && !imask` 计算的 `expected_line` 三方对比——三者不一致处即第一
   分歧点。
5. **guest 侧对齐**：诊断内核记录 CPU1 首次 arch_timer IRQ、首次 scheduler tick、
   WFI enter/exit 各一次。

## 11. 一页速记

| 问题 | 一句话答案 |
| --- | --- |
| SGI 是什么 | 软件写 `ICC_SGI1R_EL1` 触发的核间中断（IPI），ID 0–15 |
| PPI 是什么 | 每核私有外设中断，ID 16–31；**每个核的 timer 各是一条独立 PPI（27）** |
| SPI 是什么 | 全局共享外设中断，ID 32–1019，可路由到任意核 |
| LPI 是什么 | 消息式中断（MSI 风格），设备写 ITS 翻译器产生，ID ≥8192 |
| IRQ vs FIQ | GIC 到 PE 的两条异常信号；FIQ 优先级更高、走 `PSTATE.F`，Linux 几乎只用 IRQ |
| 谁决定 IRQ 能否 taken | GIC enable/group/priority + PMR + PSTATE.I，全部通过才行 |
| WFI 唤醒 = IRQ taken 吗 | 不等于；被屏蔽的 IRQ 也能唤醒 WFI |
| 电平中断为什么要清源 | 不撤源电平，EOI 后 GIC 立刻重新 pending → 中断风暴 |
| CubeSandbox 故障落在哪 | 阶段 D/E：KVM timer line 与 vGIC latch 在 W2/W3 窗口内的恢复时序错位 |

---

# 第三部分：KVM vGIC 深入

## 12. 三层视图总览

```text
┌─────────────────────────────────────────────────────────────┐
│ guest EL1/EL0                                                │
│   ICC_IAR1/EOIR/PMR/IGRPEN 读写 ── 硬件直通（不 trap）        │
│   GICD/GICR/GITS MMIO 访问     ── stage-2 fault，trap 到 KVM  │
│   CNTV_CVAL/CTL 读写           ── 硬件直通（不 trap）         │
└──────────────┬──────────────────────────────┬────────────────┘
               │ 硬件虚拟接口                  │ trap
               ▼                              ▼
┌──────────────────────────┐   ┌───────────────────────────────┐
│ GIC 硬件虚拟化扩展        │   │ KVM vGIC 软件状态（EL2）        │
│  virtual CPU interface   │◄─►│  vgic_irq 位图（spi/ppi 数组）  │
│  ICH_LR*_EL2（列表寄存器）│   │  dist/redist/icc/its 软件副本   │
│  ICH_VMCR/HCR/MISR_EL2   │   │  timer line level（arch_timer） │
│  物理 GICD/GICR/CPU 接口  │   │                               │
└──────────────────────────┘   └──────────────┬────────────────┘
                                              │ ioctl / device attr
                                              ▼
                               ┌───────────────────────────────┐
                               │ VMM（containerd-shim 内 vmm 线程）│
                               │  创建/注入/保存/恢复             │
                               └───────────────────────────────┘
```

核心设计原则：**高频操作走硬件，低频/配置类操作走软件**。ack/EOI/优先级掩码这类每次
中断都要做的动作由硬件虚拟 CPU 接口直接完成，零 trap；distributor/redistributor
配置和虚拟中断的来源管理由 KVM 软件维护；VMM 只在创建、注入外部中断和迁移/快照时
介入。

## 13. vGIC 与 GIC 硬件的交互

### 13.1 GICv3 的硬件虚拟化组件

GICv3 为虚拟化提供一组 EL2 专用资源（不是 guest 可见的 GICD/GICR MMIO，而是 CPU
上的系统寄存器和硬件状态）：

| 组件 | 作用 |
| --- | --- |
| virtual CPU interface | 硬件为每个 PE 实现的"虚拟 CPU 接口"，guest 的 `ICC_*_EL1` 访问被硬件重定向到这里 |
| `ICH_LR0..n_EL2`（List Registers，常见 4-16 个） | hypervisor 预填的待投递虚拟中断队列；guest ack 时硬件从 LR 供给 INTID |
| `ICH_VMCR_EL2` | 虚拟接口的 VM 控制镜像（VPMR 虚拟优先级掩码、VENG0/1 组使能等） |
| `ICH_HCR_EL2` | 总开关（`En`）与 maintenance 中断使能位（UIEn/LRENPie/NPIE/EOI 计数等） |
| `ICH_MISR_EL2` / `ICH_EISR_EL2` / `ICH_ELRSR_EL2` | maintenance 状态：LR 下溢、哪些 LR 被 EOI、哪些 LR 空闲 |
| vGIC maintenance interrupt | 物理 PPI（INTID 25），LR 不足或需要 EL2 介入时在宿主触发 |

### 13.2 guest 直通访问：不 trap 的路径

`ICH_HCR_EL2.En=1` 后，guest 对 `ICC_*_EL1` 系统寄存器的访问**由硬件直接服务**：

- 读 `ICC_IAR1_EL1`（ack）：硬件从最高优先级有效 LR 返回 INTID，并把该 LR 状态
  从 pending 翻为 active；
- 写 `ICC_EOIR1_EL1`：硬件做 priority drop，更新 LR 状态（EOImode=1 时 deactivate
  由 `ICC_DIR_EL1` 完成，同样硬件处理）；
- `ICC_PMR_EL1`、`ICC_IGRPEN0/1_EL1`：直接读写虚拟接口状态（`ICH_VMCR_EL2` 的
  guest 侧镜像）。

因此 guest 的中断热路径（ack/handler/EOI）**不经过 KVM**。KVM 通过事后读 LR 状态
得知 guest 处理进度（见 13.4）。

### 13.3 trap 路径：GICD/GICR/GITS MMIO

Distributor、Redistributor、ITS 没有硬件虚拟化——它们在 stage-2 页表中根本
不映射，guest 每次访问都产生 stage-2 fault，进入 KVM 的 MMIO 模拟
（内核 `vgic-mmio-v3.c`、`vgic-its.c`）：

- guest 写 `GICD_ISENABLER`/`GICD_IPRIORITYR`/`GICD_IROUTER` → KVM 更新 SPI 的
  软件状态（`vgic_irq` 数组）；
- guest 写 `GICR_ISENABLER0`/`GICR_ISPENDR0`/`GICR_IPRIORITYR` → KVM 更新该 vCPU
  对应 redistributor 的 SGI/PPI 软件状态；
- guest 对 ITS 的命令队列操作 → KVM 解析 LPI 翻译表（保存在 guest 内存中）。

KVM 据此维护每个虚拟中断的完整软件状态：`enabled/pending(latch)/active/
line_level/priority/group/target_vcpu/config(level|edge)`。这份状态就是
§14.3 保存/恢复 ABI 读写的对象，也是 CubeSandbox 快照里那 634 项的来源。

### 13.4 vCPU load/put：List Register 的填充与回收

KVM 在每次进入/退出 guest 时同步硬件 LR 与软件状态：

```text
vCPU load（KVM_RUN 进入 guest 前）
  kvm_vgic_flush_hwstate:
    1. 用该 vCPU 当前虚拟 PMR/group enable 写 ICH_VMCR_EL2
    2. 从软件状态挑出 (pending|active) && enabled && 优先级最高的虚拟中断，
       填入空闲的 ICH_LR*_EL2（每个 LR 记录 INTID、优先级、状态、
       是否携带硬件 deactivate 映射）
    3. ICH_HCR_EL2.En=1，配置 maintenance 使能
  → 进入 guest；guest ack 时由硬件从 LR 供给

guest 运行中
  若待投递中断多于 LR 容量，或出现需要 EL2 处理的条件（EOI、group enable 变化），
  硬件触发 vGIC maintenance interrupt（PPI 25，宿主 EL2 处理），
  KVM 在中断处理里 refill LR、回收已 EOI 的 LR

vCPU put（退出 guest 后）
  kvm_vgic_sync_hwstate:
    1. 读 ICH_ELRSR_EL2/各 LR，回收 guest 已 ack/EOI 的状态变化，
       更新软件 active/pending
    2. 电平中断：若 EOI 时 line level 仍为高 → 重新 pending（与 §5 物理语义一致）
    3. 把新产生的 pending 中断留待下次 load 时注入
```

要点：**guest 看到的"GIC"大部分是 LR 和虚拟接口的硬件行为；KVM 只在 load/put
边界批量对账**。这也是为什么 vGIC 的软件状态在 vCPU 运行期间是"旧账"——
保存/恢复 ABI 要求 vCPU 停下来才能读到一致状态（对应 `EBUSY` 约束，§14.3）。

### 13.5 virtual timer 的硬件路径（与本故障最相关）

ARM 架构没有把 timer comparator 虚拟化给 guest——guest 直接读写硬件
`CNTV_CVAL_EL0/CNTV_CTL_EL0`，而 `CNTVOFF_EL2` 由 KVM 按 VM 设置
（`VirtualCount = PhysicalCount - CNTVOFF_EL2`）。中断的产生分两种情形：

```text
情形 1：vCPU 正在运行
  KVM 在 vCPU load 时把 guest 的 CVAL/CTL 装载到 PE 的硬件 timer
  → 到期产生物理 vtimer PPI（INTID 27），因 HCR_EL2.IMO=1 被路由到 EL2
  → 宿主 handler 不做 guest 可见动作之外的事：
    把该 vCPU 的虚拟 PPI27 的 line_level 置 1（KVM timer 子系统 ↔ vGIC 的接口）
  → 重新进入 guest，vGIC 按仲裁规则投递虚拟 IRQ

情形 2：vCPU 因 WFI 被阻塞（宿主线程睡在 KVM_RUN 里）
  KVM 用宿主软件 timer（hrtimer）在 CVAL 到期点到期
  → 同样置 line_level=1
  → kvm_vcpu_kick() 唤醒阻塞的 vCPU 线程（必要时向目标物理 CPU 发 IPI）
  → vCPU 恢复运行，load 时经 LR 注入
```

关键结构性事实：**虚拟 PPI27 的 line_level 由 KVM 的 arch_timer 子系统计算和持有，
pending latch/active/enable 由 vGIC 子系统持有**。两者通过内部接口同步，但 VMM 从
userspace 看到的读取通道是不同的（one-reg vs device attr，见 §14.3/§14.4）——
恢复时两套状态的写入顺序就是 W2 窗口的物理本质。

### 13.6 LPI/ITS：GICv3 下的软件翻译

GICv3 硬件不支持 LPI 直接注入（那是 GICv4.1 的 vLPI/vPE 特性）。GICv3 下：

- guest 设备写 `GITS_TRANSLATER` → trap → KVM 查 guest 内存中的 ITS 翻译表
  （device table / collection table / LPI config table），得到
  `INTID + 目标 redistributor`，然后按普通虚拟中断注入；
- MSI 经 irqfd 到达时（`KVM_SET_GSI_ROUTING` 路由表匹配），KVM 同样走软件翻译；
- 快照/恢复时 ITS 的表内容在 guest 内存里，KVM 提供
  `KVM_DEV_ARM_ITS_SAVE_TABLES/RESTORE_TABLES` 让 VMM 触发表的内核侧解析与落盘
  （CubeSandbox 在 `gic/mod.rs:453` 使用）。

## 14. vGIC 与上层 VMM 的交互

VMM（本项目中即 shim 进程内的 vmm 线程）通过四类接口与 vGIC 交互。

### 14.1 创建与初始化

```text
KVM_CREATE_DEVICE(KVM_DEV_TYPE_ARM_VGIC_V3)     → 得到 gic device fd
KVM_SET_DEVICE_ATTR:
  GROUP=KVM_DEV_ARM_VGIC_GRP_ADDR, ATTR=KVM_VGIC_V3_ADDR_TYPE_DIST   → GICD 基址
  GROUP=KVM_DEV_ARM_VGIC_GRP_ADDR, ATTR=KVM_VGIC_V3_ADDR_TYPE_REDIST → redist 区域
  GROUP=KVM_DEV_ARM_VGIC_GRP_NR_IRQS                                 → SPI 数量
  GROUP=KVM_DEV_ARM_VGIC_GRP_CTRL, ATTR=KVM_DEV_ARM_VGIC_CTRL_INIT   → 完成初始化
```

约束：vCPU 必须先于 redist 区域创建（KVM 需要 vCPU↔redistributor 关联）；INIT 之后
vCPU 才能运行；保存/恢复要求关联顺序一致（机制文档 §9.5）。

CubeSandbox 落点：`vm.rs:2300-2308` `create_vgic`（restore 路径）、
`hypervisor/src/kvm/aarch64/gic/mod.rs` 中 `create_device`/地址设置；
`set_gicr_typers`（`vm.rs:2318-2325`）按快照 vCPU 状态回填每个 redistributor 的
`GICR_TYPER`（含 MPIDR 关联与 last 标记）。

### 14.2 中断注入

| 路径 | ioctl | 用途 | CubeSandbox 落点 |
| --- | --- | --- | --- |
| 连线中断 | `KVM_IRQ_LINE`（电平 0/1） | UART、virtio-mmio 等 | 本 fork 未直接使用 |
| eventfd 注入 | `KVM_IRQFD`（可带 resample） | virtio 设备的 legacy 中断：驱动 kick eventfd → KVM 注入 | `devices/src/gic.rs:92`、`vmm/src/interrupt.rs:44/:60`、`kvm/mod.rs:423-433` |
| MSI 路由 | `KVM_SET_GSI_ROUTING` | MSI 向量 → INTID 翻译表 | `vmm/src/interrupt.rs:109`、`kvm/mod.rs:561-585`；seccomp 白名单 `seccomp_filters.rs:133/138` |

### 14.3 保存/恢复 ABI（`KVM_GET/SET_DEVICE_ATTR`）

| group | 内容 | CubeSandbox 落点 |
| --- | --- | --- |
| `KVM_DEV_ARM_VGIC_GRP_DIST_REGS` | GICD_CTLR/STATUSR/IGROUPR/ISENABLER/ISPENDR/ISACTIVER/IPRIORITYR/ICFGR/IROUTER（快照 568 项） | `gic/dist_regs.rs` |
| `KVM_DEV_ARM_VGIC_GRP_REDIST_REGS` | 每 redistributor 的 TYPER/STATUSR/WAKER/IGROUPR0/ISENABLER0/ISPENDR0/ISACTIVER0/ICFGR/IPRIORITYR（快照 24 项/vCPU） | `gic/redist_regs.rs` |
| `KVM_DEV_ARM_VGIC_GRP_CPU_SYSREGS` | ICC_SRE/CTLR/IGRPEN0/IGRPEN1/PMR/BPR0/BPR1/AP0R0/AP1R0（快照 9 项/vCPU，attr 内嵌 MPIDR 选目标 vCPU） | `gic/icc_regs.rs` |
| `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO` | **每个电平中断的真实输入线电平**（与 ISPENDR latch 是不同状态域） | **当前未使用**——观测缺口 |
| `KVM_DEV_ARM_VGIC_GRP_ITS_REGS` + `KVM_DEV_ARM_ITS_SAVE_TABLES/RESTORE_TABLES` | ITS 寄存器与表 | `gic/mod.rs:410-461` |

ABI 约束：

- attr 编码内嵌 redistributor 索引/MPIDR 与寄存器偏移，逐寄存器访问；
- **vCPU 运行中访问可返回 `EBUSY`**——保存必须在 pause 之后（CubeSandbox 在
  `Vm::snapshot` 前已完成 `CpuManager::pause`，见机制文档 §11.3）；
- 恢复有顺序要求：vCPU 创建顺序、redist 区域创建顺序、以及恢复写入顺序要一致，
  否则 vCPU↔redistributor 关联错位（PPI 状态落到错误的核上）。

### 14.4 timer 的 VMM 接口（one-reg，与 device attr 完全不同的通道）

```text
KVM_GET_ONE_REG / KVM_SET_ONE_REG:
  KVM_REG_ARM_TIMER_CTL  (idx 8)   ←→ KVM arch_timer 模拟状态 cntv_ctl
  KVM_REG_ARM_TIMER_CNT  (idx 9)   ←→ 当前 virtual count 视图
  KVM_REG_ARM_TIMER_CVAL (idx 10)  ←→ cntv_cval

VM 级（需 KVM_CAP_COUNTER_OFFSET=227，本机 =1）：
  KVM_ARM_SET_COUNTER_OFFSET（VM fd，ioctl 号 0x4030aea5）
    对 physical+virtual counter 视图施加 VM-wide offset，覆盖所有已建/未建 vCPU；
    调用后 KVM 静默忽略 one-reg 对 CNT/CNTPCT 的写入（无错误返回）
```

CubeSandbox 落点：`kvm/mod.rs:2176-2192`（set_state 内按内核 REG_LIST 顺序
CTL→CNT→CVAL 写入）；seccomp 缺口见
`CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md` §6.5。

### 14.5 与故障相关的接口边界小结

恢复一个 vCPU 的 timer 中断涉及 **三个不同 ABI 通道、两个 KVM 子系统**：

```text
one-reg (KVM_SET_ONE_REG)      → arch_timer 子系统：CTL/CNT/CVAL、line 的计算输入
device attr (REDIST_REGS)      → vGIC 子系统：CPU1 PPI27 的 enable/latch/group/priority
device attr (CPU_SYSREGS)      → vGIC 子系统：CPU1 的 PMR/IGRPEN1/APR
（缺失的第四条：LEVEL_INFO 读回 line level，可作观测点）
```

三个通道没有事务原子性（机制文档 §11.2）。写入顺序 CTL→CNT→CVAL→（vGIC 恢复）→
首次 KVM_RUN 之间，line_level 的计算输入（CVAL/CTL/offset）与 vGIC 的仲裁输入
（enable/latch/PMR）在不同时间点就绪——这正是 W2/W3 窗口里"timer PPI 与 vGIC
恢复顺序时序敏感交互"的全部物理内容。

## 15. 串回 CubeSandbox 故障场景

把 §8 全链路图的阶段 D/E 用本节机制重新表述：

1. `set_state` 写 CTL（idx 8）后，arch_timer 子系统已具备"timer 启用"的输入，
   但 CNT/CVAL 尚未写入——若此刻 KVM 评估 comparator，输入是新建 vCPU 的 UNKNOWN
   值（W1）；
2. CNT/CVAL 写完后到 vGIC redist/icc 恢复前，line_level 的计算输入已齐，但 CPU1
   的 PPI27 enable/latch/PMR 还是新建 vGIC 的默认值（W2）；
3. vGIC 恢复完成后、首次 KVM_RUN 的 vCPU load 时，KVM 做第一次完整对账：
   line_level（由恢复后的 CVAL/CTL/offset 重算）与 latch（快照恢复值）合并，
   填充 LR。这次对账的结果取决于 W1/W2 期间各状态到达的先后顺序（W3）；
4. 观测上，唯一能区分"line 没形成"和"line 形成但被仲裁挡下"的 userspace 手段，
   就是 §14.3 的 `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO`（line level）与
   `GICR_ISPENDR0`（latch）、按 CTL/CVAL/CNT 计算的 `expected_line` 三方对比
   （见 §10 观测清单第 4 条）。

## 16. 一页速记（KVM vGIC 部分）

| 问题 | 一句话答案 |
| --- | --- |
| guest 的 ICC 访问会 trap 吗 | 不会；硬件虚拟 CPU 接口直接服务 ack/EOI/PMR |
| guest 的 GICD/GICR 访问呢 | 全部 trap（stage-2 fault），KVM 软件模拟 |
| 虚拟中断怎么进 guest | KVM 在 vCPU load 时填 ICH_LR*_EL2，guest ack 由硬件供给 |
| LR 不够怎么办 | vGIC maintenance interrupt（PPI 25）在 EL2 触发 refill |
| KVM 怎么知道 guest EOI 了 | vCPU put 时读回 LR 状态对账；电平未撤销则重新 pending |
| timer 中断谁算 line level | KVM arch_timer 子系统（到期在 EL2 截获或 swtimer），不是 vGIC |
| VMM 怎么注入设备中断 | `KVM_IRQ_LINE` / `KVM_IRQFD`（eventfd）/ MSI 走 `KVM_SET_GSI_ROUTING` |
| 快照保存了 vGIC 什么 | dist/redist/icc 的软件状态；**不含 line level**（需 `LEVEL_INFO` 单独读） |
| 恢复为什么是时序敏感的 | timer line 输入与 vGIC 仲裁输入经三条无原子性的 ABI 通道先后就绪 |

---

# 第四部分：Generic Timer 深入

## 17. 架构总纲解读（Arm Generic Timer Reference 原文）

手册原文：

> Each core has a set of timers. These timers are comparators, which compare against
> the broadcast system count that is provided by the System Counter. Software can
> configure timers to generate interrupts or events in set points in the future.
> Software can also use the system count to add timestamps, because the system count
> gives a common reference point for all cores.

四句各对应一个核心架构事实：

### 17.1 "Each core has a set of timers."

每个 PE **独立拥有一组** timer，不是全系统共享一个。这组指 EL1 physical timer
（`CNTP_*`）、EL1 virtual timer（`CNTV_*`）、EL2 的 `CNTHP_*`/`CNTHV_*`、EL3 的
`CNTPS_*` 等——按异常级分套，每套寄存器都是 per-PE 副本。

关键含义：**CPU0 写自己的 `CNTV_CVAL` 不会也不能影响 CPU1 的 timer**，它们只是
共用同一个时间基准（17.2）。这就是 CubeSandbox 故障中 CPU0 tick 正常而 CPU1
timer 可以独立出问题的原因——两者是两套硬件状态，快照里也是两份 per-vCPU 的
`CTL/CVAL`（one-reg idx 8/9/10 每个 vCPU 各存一份）。

### 17.2 "These timers are comparators, which compare against the broadcast system count"

timer 的物理构造是**比较器（comparator）**，不是"会倒数的东西"。真正的计数全
系统只有一份——SoC 里的 System Counter，持续递增并**广播到所有核**；每个核的
timer 只做一件事：不停拿广播计数值与自己的 `CVAL` 比较，`count ≥ CVAL` 时输出
条件成立信号。

由此推出：

- **timer 没有"运行/暂停"**。清 `CTL.ENABLE` 只关比较器输出，System Counter 照走，
  重新 enable 一个已过期 CVAL 会立即产生输出（机制文档 §7.4 的规则源于此）。
- **所有核看到同一计数轴**，物理计数层面不存在"CPU1 的 counter 比 CPU0 慢"。
  虚拟化差异全部来自 per-VM 的 `CNTVOFF_EL2` 偏移，offset 是 VM 级不变量，
  CPU0/CPU1 必须一致（PR #8343 与 v1-v9 实验围绕的问题）。
- **恢复顺序敏感的结构根源**：CVAL 是静态数值，"是否过期"取决于它与当前广播
  计数的相对关系。恢复时先写 CTL（enable）再写 CVAL，比较器在 CVAL 未写好时就
  已用旧值参与比较——W1 窗口的物理本质。

### 17.3 "Software can configure timers to generate interrupts or events in set points in the future."

软件通过设定未来的比较点让 timer 产生**中断或事件**：

- 写 `CNTV_CVAL`（绝对值）或 `CNTV_TVAL`（相对值，硬件展开为
  `CVAL = CNTVCT + SignExtend(TVAL)`），配合 `ENABLE=1`、`IMASK=0`，到期电平送到
  GIC PPI（virtual timer 为 PPI 27）——Linux clockevent 的全部工作原理；
- "or events" 指 event stream（`WFE` 唤醒等），不走 GIC，日常主要是中断路径；
- "set points in the future" 隐含 **timer 一次性、不自动重装**：到期后电平一直
  为高，handler 必须显式设下一个点（或 mask/disable）撤电平——GIC 电平中断的
  清源义务。

### 17.4 "Software can also use the system count to add timestamps"

广播计数同时充当**全系统统一的时间戳基准**：任何核读 `CNTPCT/CNTVCT` 都是同一
根轴上的值，可跨核比较先后。Linux 用它实现 clocksource（`CLOCK_MONOTONIC`
底层）、`sched_clock()`；RCU stall 检测的 "timer wakeup didn't happen" 判断
底层也是在核对这根公共轴。

实践含义（插桩纪律）：所有观测（VMM/KVM/guest）应换算到同一根轴上对齐，但
guest 读的 `CNTVCT = 物理计数 - CNTVOFF_EL2` 与宿主 `CLOCK_MONOTONIC` 不是同一
根轴——跨层对齐时必须先把 `CNTVOFF` 和 `CNTFRQ` 纳入换算，否则"第一个分歧点"
的定位会被时间轴错位污染。

**一句话总结**：System Counter 是全系统唯一的广播计数轴；每个核的 timer 只是
挂在轴上的比较器，软件靠写未来比较点获得中断，靠直接读轴获得统一时间戳。

## 18. CVAL / TVAL 两种编程方式在 Linux 中的应用

手册说明：配置 timer 有两种方式——写 64 位比较器 `CVAL`（`count ≥ CVAL` 触发），
或写 32 位有符号 `TVAL`（硬件内部取当前计数并展开 `CVAL = TVAL + System Count`）。
两者是**同一 timer 的两种编程视图，不是两个 timer**。Linux 分层使用两者：
时间子系统抽象层面思考 CVAL 模型（绝对时间），落笔动作用 TVAL 模型（相对偏移）。

### 18.1 两层设施的分工

- **clockevents**（每 CPU 一个 `clock_event_device`，`drivers/clocksource/arm_arch_timer.c`）：
  框架与驱动的接口是 `set_next_event(delta_cycles)`——"从现在开始多少 tick 后
  到期"，相对语义，天然映射 TVAL；
- **hrtimer / timer_list**：所有定时任务按**绝对时间**（ktime，纳秒）排序——
  CVAL 模型的思维。

换算在最后一刻完成：hrtimer 到期点减当前时间得 delta（纳秒→cycles，用
clocksource mult/shift），再调 `set_next_event(delta)`。**绝对时间在软件层维护，
相对偏移只在落笔瞬间生成**。

### 18.2 arch_timer 驱动：从 CVAL 写法换成 TVAL 写法

早期内核是 CVAL 写法：`write(cntv_cval, evt + arch_counter_get_cntvct())`；
较新内核（5.x 起）改为 TVAL 写法：`write(cntv_tval, evt)`。原因正是"hardware
reads the count **internally**"：

- 省一次 `CNTVCT` 读取及其 `ISB` 屏障（每个 tick 的热路径开销）；
- 消除 read-then-write 非原子性：CVAL 写法中读数与写比较器之间时间照走，
  deadline 天然偏旧；TVAL 由硬件在写的一瞬间内部取数，语义原子。

手册"The count is approximate"描述的正是这个近似误差。**凡是"基于旧时间样本
计算绝对 deadline"的场景都有此问题**——包括快照恢复：VMM 拿快照时刻保存的
`CNT/CVAL` 做判断，`vtimer_delta` 出现负值（deadline 已过期）就是这个非原子性
的宏观版本。

### 18.3 oneshot 模式：每个 tick 一次全新编程

arch_timer 以 oneshot 注册（`CLOCK_EVT_FEAT_ONESHOT`）。Linux 的周期 tick 不靠
硬件自动重装，而是每次到期后软件再编程：

```text
到期 → EL1 IRQ → arch_timer_handler（每 CPU，PPI 27）
  → clockevents event_handler → tick/hrtimer 处理
  → 算出下一个到期点 → set_next_event(新 delta)   ← 写新 TVAL，同时撤掉旧电平
```

GIC 电平中断的清源义务在 Linux 里的落实就是：handler 一定写新 TVAL。

### 18.4 TVAL 位宽对 NO_HZ 的硬约束

TVAL 低 32 位按有符号解释，单次最大间隔 `2^31-1` tick，驱动上报
`max_delta_ticks = 0x7fffffff`：25 MHz 下约 86 秒，1 GHz 下仅约 2.1 秒。NO_HZ
idle 想睡更久时，超过 max_delta 的部分被截断或交给 tick broadcast。**CPU 睡眠
时长上限被 TVAL 位宽硬性约束**。

这也解释了快照中 `CVAL-CNT`（`vtimer_delta`）通常只有几万到几百万 tick 量级——
Linux 绝大多数时候都在编很近的 deadline，pause 落到哪个点、快照里 timer 是否
过期，概率上非常敏感（v10 坏 Template 两 timer 均过期、v12/v15 好 Template 未
过期，正是这种近 deadline 高频编程的采样结果）。

### 18.5 TVAL 负值语义：测量过期时长

TVAL 到期后继续递减为负值，可读出"多久前触发"。诊断价值：

- `vtimer_delta = CVAL - CNT` 的负值绝对值 = 已过期 tick 数（除以 `CNTFRQ` 得秒）；
- 注意：ENABLE=0 时 TVAL 读值 UNKNOWN；判到期必须用 64 位无符号
  `CVAL ≤ count`，不能用 `Signed64(CNT-CVAL)` 或 32 位 TVAL 近似（回绕误判）。
  插桩规范 `expired = enable && condition_met`（无符号比较）即按此编写。

### 18.6 虚拟化视角：KVM 只见 CVAL 模型

- guest 写 `CNTV_TVAL_EL0` 不 trap，硬件当场展开进 `CNTV_CVAL_EL0`，KVM 看不到
  用的是哪种写法；
- KVM one-reg ABI 与快照格式里**只有 CVAL/CTL/CNT，没有 TVAL**（`sys_regs` idx
  8/9/10），恢复本质是 CVAL 模型；
- 恢复后 guest 无感，Linux 照旧每 tick 写 TVAL。问题集中在"恢复后的第一段
  时间里，旧 CVAL 与新 CNT/offset 的关系"——**一旦第一个 tick 正常完成、Linux
  重新编程，后续自愈**。这解释了故障为何总表现为"恢复后数秒内 CPU1 stall"
  而非运行中期劣化。

### 18.7 对照表

| 模型 | 手册语义 | Linux 里的对应物 |
| --- | --- | --- |
| CVAL（绝对） | 写 64 位比较点，`count ≥ CVAL` 触发 | hrtimer/timer_list 绝对 ktime 排序；KVM 快照/恢复的唯一形式 |
| TVAL（相对） | 写 32 位有符号偏移，硬件原子展开 | clockevents `set_next_event(delta)`，5.x 起 arch_timer 实际写法 |
| TVAL 递减到负 | 读回"已过期多久" | 诊断：`vtimer_delta=CVAL-CNT` 负值同理 |
| 不自动重装 | 电平保持到软件清源 | oneshot：每 tick 一次全新编程 |
| 32 位上限 | `2^31-1` tick | `max_delta_ticks=0x7fffffff`，约束 NO_HZ 睡眠 |

## 19. KVM 的 timer 虚拟化机制

总原则：**guest 直接操作硬件 timer，KVM 不参与每次读写，只在"中断产生"、
"vCPU 换入换出"和"vCPU 阻塞"三个边界上对账**。

### 19.1 guest 直通：读写 timer 寄存器不 trap

KVM 通过 `CNTHCTL_EL2` 允许 guest EL1 直接访问 virtual timer/counter。guest
每个 tick——读 `CNTVCT`、写 `CNTV_TVAL/CVAL/CTL`——全部硬件直接执行，零 trap，
KVM 无感知，也看不到用的是 TVAL 还是 CVAL。物理 counter/timer（`CNTP_*`）是否
trap 取决于 `EL1PCTEN/EL1PCEN`，较新内核默认也不 trap。CubeSandbox guest 使用
virtual timer（日志中只有 `CNTV_*`）。

### 19.2 host 与 guest 的分工：physical 归宿主，virtual 归 guest

每个 PE 的 timer 按时钟域分开：VHE 模式下宿主内核在 EL2 用 physical timer
（`CNTP`/`CNTHP`）做自己的调度 tick；guest 用 virtual timer（`CNTV`），
`VirtualCount = PhysicalCount - CNTVOFF_EL2`，offset 由 KVM 按 VM 维护
（`kvm->arch.counter_offset`，per-VM 一份，所有 vCPU 共享）。两者是同一
System Counter 广播轴上的两个视图，互不干扰。

### 19.3 guest 运行时：到期在 EL2 截获

KVM 运行时 `HCR_EL2.IMO=1`，所有物理 IRQ 先路由到 EL2：

```text
guest 写 CVAL（或 TVAL 展开）→ 硬件 comparator 到期
  → 物理 vtimer PPI（INTID 27）触发，被 IMO=1 截获到 EL2
  → KVM timer IRQ handler：把该 vCPU 虚拟 PPI27 的 line_level 置 1
  → 重新进入 guest，vGIC 经 LR 注入虚拟 IRQ
  → guest 才看到自己的 timer 中断
```

**每个 guest tick 付出一次 world switch**。vCPU load 时 KVM 把 guest 的
CVAL/CTL 装进硬件，让 comparator 在 guest 运行期间由硬件持续工作。

### 19.4 vCPU load/put：timer 上下文换入换出与 line 重算

硬件 `CNTV_CVAL/CTL` 每 PE 一份，多 vCPU 复用同一物理 CPU，KVM 在调度边界切换
上下文（`arch/arm64/kvm/arch_timer.c`）：

```text
vCPU load（KVM_RUN 进入 guest 前）：
  1. 写 CNTVOFF_EL2 = VM 的 counter_offset
  2. 把内存上下文的 cntv_ctl / cntv_cval 写入硬件寄存器
  3. ★ 重新评估 timer 条件：
     enable && !imask && (VirtualCount >= CVAL) → 置/清 line_level
     （arch_timer 子系统状态 → vGIC line 的同步点）

vCPU put（退出 guest 后）：
  把硬件 CNTV_CTL/CVAL 读回内存上下文保存
```

第 3 步是恢复语义的关键：**line_level 不是持久状态，每次 vCPU load 按
"CTL/CVAL/offset 当前组合"重新计算**。

### 19.5 vCPU 阻塞（WFI）：后台软 timer 接管

```text
guest 执行 WFI → trap 到 EL2（HCR_EL2.TWI）
  → KVM 让宿主线程睡眠（kvm_vcpu_block）
  → 睡前把 guest deadline 从 guest 轴换算到宿主轴
    （用 counter_offset 和 CNTFRQ），布防宿主侧后台 timer
  → 后台 timer 到期：置 line_level=1，kvm_vcpu_kick()
    （唤醒睡眠线程；vCPU 在别的物理 CPU 上则发 IPI）
  → vCPU 恢复运行，load 时按 19.4 流程注入
```

vCPU 不跑时，KVM 用宿主的时间系统替 guest"看着表"。

### 19.6 userspace ABI：VMM 看到的是内存上下文

one-reg 读写的是 19.4 的内存模拟上下文（要求 vCPU 不在运行中），不是硬件寄存器：

| one-reg | 语义 | 注意 |
| --- | --- | --- |
| `KVM_REG_ARM_TIMER_CTL`（idx 8） | 上下文 cntv_ctl | SET 只是写入，line 重算推迟到下次 load |
| `KVM_REG_ARM_TIMER_CNT`（idx 9） | 当前 virtual count | **GET 返回动态值**（此刻物理计数-offset） |
| `KVM_REG_ARM_TIMER_CVAL`（idx 10） | 上下文 cntv_cval | 静态值 |

VM 级 `KVM_ARM_SET_COUNTER_OFFSET`（本机 cap 227=1）设置共享 `CNTVOFF`；调用后
KVM **静默忽略** one-reg 对 CNT 的写入（不报错）——"SET 全部成功"不能证明
counter 恢复生效。

### 19.7 快照/恢复视角：什么被保存、什么被重算

- **被保存的**：每 vCPU `CTL`（静态）、`CVAL`（静态）、`CNT`（GET 时刻的动态
  样本）——one-reg idx 8/9/10；
- **不被保存的**：line_level（load 时重算）、后台软 timer（KVM 内部）、硬件
  寄存器（属于物理 CPU）；
- **vGIC 侧保存的**：PPI27 的 pending latch/enable/priority 与 ICC 状态——与
  line_level 是不同状态域。

恢复正确性可压缩为一句：

> **CPU1 首次 vCPU load 重算 line_level 的那一刻，CVAL、CTL、counter offset 必须
> 已构成一致组合，且 vGIC 仲裁状态（latch/enable/PMR）必须已经恢复。**

CubeSandbox 当前顺序是"全部状态恢复完才 start vCPU、resume 后才首次 KVM_RUN"，
重算发生在 vGIC ready 之后，结构上无明显破绽。残余时序敏感点：

- **W1**：`set_state` 先写 CTL（idx 8）再写 CNT/CVAL。若 KVM 在 SET ONE_REG CTL
  时（而非 load 时）即时评估 timer 条件，评估用的 CVAL 是新建 vCPU 的 UNKNOWN
  值，可能立即形成错误的 line/pending 并被后续流程固化或丢失——v17 CTL-last
  实验验证的正是这一点。
- **W3/观察效应**：首次 load 的重算发生在哪个计数时刻取决于调度。插桩引入的
  数百微秒改变了"offset 设置→首次 load"之间计数轴走过的距离，即改变了重算时
  `VirtualCount >= CVAL` 的判定输入——可解释 v15/v16 日志翻转确定性坏样本
  结果的观察效应。

### 19.8 一页速记（KVM timer 部分）

| 问题 | 答案 |
| --- | --- |
| guest 读写 timer 寄存器 trap 吗 | 不 trap，硬件直通；KVM 看不见每次编程 |
| host/guest 怎么分 timer | host 用 physical timer，guest 用 virtual timer + `CNTVOFF_EL2` |
| guest 运行时 tick 怎么来 | comparator 到期 → 物理 PPI 截获到 EL2 → 置 line_level → LR 注入；每 tick 一次 exit |
| vCPU 阻塞时 tick 怎么来 | 后台 timer（deadline 换算到宿主轴）到期置 line 并 kick vCPU |
| line_level 是持久状态吗 | 不是；每次 vCPU load 按 CTL/CVAL/offset 重算 |
| VMM 看到的 timer 状态 | 内存模拟上下文（one-reg）；CNT 动态样本，CVAL/CTL 静态 |
| VM counter offset 的坑 | 设置后 one-reg CNT 写入被静默忽略 |
| 恢复正确性的核心 | 首次 load 重算时 CVAL/CTL/offset 一致 + vGIC 仲裁状态已恢复 |

### 19.9 展开：WFI 时后台软 timer 为什么必须接管、如何接管

**为什么硬件覆盖不了**：硬件 comparator（`CNTV_CVAL/CTL`）每个物理 PE 只有一份，
任何时刻装的是"当前在该 PE 上运行的 vCPU（或宿主）"的上下文。guest 执行 WFI 后：

```text
guest CPU1: WFI
  → trap 到 EL2（KVM 设 HCR_EL2.TWI=1，故意让 WFI 陷入——否则物理 CPU 直接停在
    WFI 里，宿主调度器失去这个核；trap 后宿主线程挂起，物理 CPU 可去跑别的任务）
  → kvm_vcpu_block → schedule()，宿主线程睡眠
  → CPU1 的 timer 上下文已不在硬件上：该 PE 的 comparator 现在装的是别的东西
```

此时即使 guest CPU1 的 deadline 到了，**没有任何硬件会为它触发**，必须由软件
替它"看着表"。

**接管流程**：

```text
① block 时检查该 vCPU timer：若 CTL.ENABLE=1 且 CVAL 在未来
     delta_ticks = CVAL - (物理计数 - CNTVOFF)
     delta_ns    = delta_ticks / CNTFRQ
   按 delta_ns 在宿主时间系统上布防后台定时器
   （实现上是宿主 clocksource 上的高精度定时器；新版本内核在 guest 不使用
     物理 timer 时也可复用该 PE 空闲的物理 comparator 当后台比较器——
     细节随内核版本而异，语义相同）
② 宿主线程 schedule() 睡死
③ 后台定时器到期（宿主侧中断）：
     置该 vCPU 虚拟 PPI27 的 line_level = 1
     kvm_vcpu_kick()：
       vCPU 线程睡在 KVM_RUN 里 → 直接唤醒
       vCPU 正在别的 pCPU 上跑 guest → 向该 pCPU 发 IPI 强制 exit
④ vCPU 恢复运行，走正常 load 路径：装载 CVAL/CTL、重算 line、填 LR、注入
⑤ 若 vCPU 因其他原因先醒（其他虚拟中断、宿主信号），取消后台定时器
```

**与 WFI 语义的关系**（呼应 wakeup ≠ taken）：第 ③ 步的 kick 只保证 vCPU 重新
运行，不等于 guest handler 会执行：

```text
kick → vCPU load → 虚拟 PPI27 pending（line OR latch）
  → guest 恢复执行到 WFI 时发现 pending wakeup event → WFI 返回（"被唤醒"）
  → PSTATE.I=0 且仲裁通过 → IRQ taken，handler 执行
  → PSTATE.I=1 → 仅 WFI 返回，handler 不执行
```

对 CPU1 调试的投射：恢复后的 CPU1 大概率停在 idle 的 WFI 里，它的第一个 tick
走的就是"后台软 timer → kick → load 注入"路径。line/latch 错位时会出现两种
可区分表现：**kick 发生但 IRQ 不 taken**（WFI 反复唤醒空转）与 **kick 不发生**
（CPU1 长眠不醒）——插桩必须分别记录 wakeup 与 taken。

### 19.10 展开：one-reg ABI 为什么看到的是内存上下文

**为什么没有"可直接读的硬件"**：`CNTV_CVAL_EL0` 这类物理寄存器在物理 PE 上，
此刻里面装的可能是别的 vCPU 的值、宿主的值、或该 vCPU 被调出时残留的陈旧值。
硬件里不存在一个稳定的、属于某个 vCPU 的寄存器副本。因此 KVM 在 vCPU 结构体中
保存一份**软件序列化副本**（内存上下文，如 `cntv_ctl`、`cntv_cval`），one-reg
读写的对象就是它。

**副本与硬件的同步边界**：

```text
vCPU load：内存副本 → 硬件（guest 开始跑）
guest 运行中：guest 直接改硬件，内存副本逐渐变旧   ← 关键区间
vCPU put：硬件 → 内存副本（guest 停下，副本重新变准）
```

推论：**one-reg 读到的值只有在 vCPU 不在运行时才是权威的**。快照要求先 pause
的深层原因即在于此——pause 让所有 vCPU 完成最后一次 put，副本与硬件完成最后
一次对账。

**三个寄存器各自的"非硬件"特性**：

| one-reg | 读写语义 | 要点 |
| --- | --- | --- |
| `CTL`（idx 8） | 读写内存副本 cntv_ctl | SET 只是存值，不动硬件、不武装 comparator；写入时是否即时重算 timer 条件随内核版本而异（W1 待验证点） |
| `CVAL`（idx 10） | 读写内存副本 cntv_cval | SET 存值，硬件等下次 load 才装载 |
| `CNT`（idx 9） | 无"计数寄存器"可读可写 | GET 现场计算 `物理计数 - offset`，每次读都不同；SET 实际是"反推 offset 使读数等于目标值"；VM 级 offset 设置后 CNT 的 SET 被静默忽略 |

**对已有实验结论的意义**：v16 在 `set_state` 后读回 `CNT/CTL/CVAL` 与保存值
一致，**只证明内存副本接受了写入**——不能证明硬件被装载（要等 load），也不能
证明 timer 条件被重新评估（重算发生在首次 load）。因此"KVM 丢弃写入不是直接
原因"的结论成立，但它同时意味着真正的判定时刻被推迟到首次 vCPU load（W3）——
插桩重点应放在首次 `KVM_RUN` 前后，而非 `set_state` 本身。
