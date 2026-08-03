# ARM64 vGIC AP1R NMI-active 故障：实验设计与分析链全记录

- 日期：2026-07-31
- 结论报告：`CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md`（仓库根目录）
- 修复产物：`fixes/arm64-vgic-apr-nmi-active-20260731/`
- 本目录：`scripts/` 关键实验脚本；`key-data/` 关键数据摘录与决定性原始数据

本文档不按时间流水账组织，而按**假设驱动的实验链**组织：每一步说明「当前假设空间 → 实验设计（观测点/对照/判定标准）→ 关键数据 → 推理结论 → 新的问题」。所有数据文件路径均可在 `key-data/` 或 `remote-results/` 中复核。

---

## 第 0 阶段：起点与假设空间

**已知**（来自 07-25 前的 codex session 与更早实验）：2-vCPU 模板 restore 后 CPU1 WFI 风暴（~20 万次/秒 WFI trap）；IRQ27（虚拟 timer）以 HW-backed PENDING 停在 ICH_LR 不被消费；另有 3 个 Group-1 pending LR（SGI1、LPI 0x2015/0x201a）同样不被消费；WFI PC 推进正常；`maxcpus=1` 完全规避；换 openEuler guest kernel 后串行/高并发均不复现；约 8 秒后 Cubelet 报 `reset guest time failed`。

**假设空间**：
- H1：guest 侧 IRQ 接收路径停滞（CPU1 从不解屏蔽 / cpu interface 未使能 / PMR 异常）
- H2：hyp/vgic 注入路径断裂（LR 未真正写入硬件、HCR.IMO 被清、ICH_HCR.En=0）
- H3：snapshot 恢复的状态与 guest 初始化时序交互（restore 顺序、timer CVAL 过去值）
- H4：本地对 CubeShim 等组件的修改引入（用户假设）
- H5：定制 host 内核（sbench-irqbypass-xarray）引入
- H6：通用 KVM/EL2 bug（旧文档 §11.4 的结论，已被前序 session 质疑）

**前序遗留方法论问题**：所有观测都是 host 影子状态；guest 内部行为（PSTATE.I 轨迹、idle 循环活性）与 EL2 真值均无数据。

---

## 第 1 阶段：纯社区基线复现（排除 H4，锁定复现载体）

**设计意图**：用户怀疑故障与本地修改的 CubeShim 等组件有关。在继续深挖前，必须先把栈恢复到哈希可验证的社区状态，否则后续所有观测都无法归因。

**设计**：
- 组件恢复不是"装个社区版"而是**哈希对齐**：cubelet `88e5e224`（07-25 源码干净重建）、shim `4702fde1`（社区 CI 构建，非本地重编——本地重编哈希 `762c3a3a` 不一致，特意排除）、cubemaster `0b78e83c`；其余 6 个二进制逐一核对与社区指纹一致（`scripts/restore_community_stack_for_reset_time_repro.sh`，含回滚 trap）。
- 复现载体选择历史最强：07-27 数据中社区 TencentOS guest image 复现率 35/40，远高于旧内核模板。guest image 切到保留的社区副本，新建模板 `tpl-42e1ad04f7354b1295e05b78`。
- 观测：串行 create + 逐次抓 cubelet/shim/VMM 日志增量 + 条件触发 eBPF（复用 07-25 的 `trace_arm64_wfi_vgic.bt`）。

**关键数据**：4 次串行 3 fail / 1 pass；3 次 fail 全部采到与 07-25 逐位一致的签名（WFI PC 恒定、LR0=IRQ27 HW PENDING、VMCR=0xf04c000a）。两种表面错误（`reset guest time failed` 8s 与 `PortBindingFailed` 30s 探针超时）同根。

**结论**：H4 排除——**纯社区全栈稳定复现**。同时得到一个此前未明说的结论：`reset guest time failed` 与 `PortBindingFailed` 是同一底层事件的两个超时竞速结果。

---

## 第 2 阶段：kvm_entry 全量 PSTATE 采样（切开 H1 的两种子假设）

**设计意图**：H1 有两个本质不同的子假设：H1a「guest 从不解屏蔽 IRQ」（问题在 guest 上下文/恢复的 DAIF 状态）；H1b「guest 解屏蔽了但注入不生效」（问题在 hyp/vgic）。区分它们能决定调查方向朝向 guest 还是朝向 hyp。

**观测点选择的关键推理**：vIRQ 的投递在 guest 将 PSTATE.I 清零时由硬件完成，**不经过 hyp**——所以 hyp 侧 exit 路径永远看不到"投递瞬间"。但每次 guest entry 时恢复的 PSTATE 就是该次运行窗口的屏蔽状态（内核源码确认：`__sysreg_restore_el2_return_state` 原样恢复 `ctxt.regs.pstate`，DAIF 位透传，`to_hw_pstate` 只改 mode 位）。因此 `__kvm_vcpu_run` 入口采样 `vcpu->arch.ctxt.regs.pstate` 的 bit7 是语义正确的观测点。

**采样设计**（`scripts/trace_arm64_irq27_entry_pstate.bt`）：
- **条件触发**：同一 KVM 线程 vCPU1 累计 10000 次 WFI 才 arm——这是风暴的确定性签名，避免在健康 VM 的常态 WFI 上浪费窗口；
- arm 后对 vCPU1 的**每一次** guest entry 聚合 I 位（`@i0`/`@i1` 计数），I=0 的 entry 额外记录 PC/PSTATE/LR0 直方图；
- 窗口 50000 次 entry（约 100ms）自动收尾。聚合在内核侧完成，用户态输出只有几行——这是高频率事件（47.5 万/秒）观测的必要设计。
- **对照**：PASS 健康沙箱跑同一探针 5 秒（`trace_arm64_irq27_entry_pstate_pass.bt`）。没有对照，分布本身无法解释。

**关键数据**（`key-data/entry-pstate-fail-ordered.log`、v2 有序版）：
- fail：50000 次 entry，**i0=3 / i1=49997**；3 次 I=0 的 entry 落在 seq 11416/15643/21130（风暴中段，非窗口起点残留），PC 解码（减去 KASLR delta 0x33baf4a00000 对照 System.map）为 **`cpuidle_idle_call+0xb8` 与 `do_idle+0x70`——正常 idle 路径**；且这 3 次 entry 时 LR0 仍 PENDING、vIRQ 仍没被 take。
- pass 对照（`key-data/pass-control-entry-pstate.log`）：i0=1529 / i1=1463，PC 分布丰富（用户态/内核态各类指令）。

**推理**：
- H1a（guest 从不解屏蔽）**被否定**：guest 确实会进入解屏蔽区段；idle 循环是活的。
- H1b 的形态被进一步收窄：即使 I=0 且 LR pending，中断也不投递。同时注意一个更深的矛盾——**WFI 以 47.5 万次/秒持续 trap 本身证明 PE 侧没有 wake event**（WFI 在有 pending 中断信号时不会挂起、也就不会 trap），即虚拟接口根本没有向 PE 断言 vIRQ；而 `kvm_vcpu_block` 立即返回又说明 host 软件模型认为有 pending。
- 新问题：断点在「vgic 软件模型判 pending」与「接口向 PE 呈现」之间。需要把所有接口门控的状态一次采全。

---

## 第 3 阶段：接口态全量采样（枚举门控，证伪逐个分支）

**设计意图**：把"接口呈现"的所有架构门控一次采全：HCR.IMO、ICH_HCR.En、VMCR（VENG1/VPMR）、LR 影子、irq27 的 vgic_irq 模型态、timer 子系统状态。每个都对应 H2 的一个子分支。设计原则：**一次实验排除一整层假设**，而不是一个一个试。

**关键技术点**：
- `vcpu->arch.hcr_el2` 可直接 eBPF 读（`kvm_vcpu_arch` 偏移 2208，pahole 验证）——这是「下次 entry 将写入 HCR_EL2 的值」，不需要 EL2 访问；
- VMCR/LR 影子在 WFI 路径会被 `kvm_vgic_vmcr_sync`/`__vgic_v3_save_state` 从硬件同步回写——即**影子值就是硬件真值**（这个论证后来变得非常重要：它意味着"影子正常"等于"硬件正常"，排除了影子-硬件脱节的大部分可能）；
- 采样频率 1/4096，控制数据量（`scripts/trace_arm64_irq27_interface_state.bt`）。

**关键数据**（`key-data/iface-state-fail-storm-attempt001.log`，50000 次 entry 逐位恒定）：
```
hcr=0x2403c807d263f imo=1 twi=1 vi=0 ich_hcr=1 vmcr=f04c000a ulrs=5
lr0=70a0001b0000001b(IRQ27 HW PENDING) lr1=...2015 lr2=...0 lr3=...201a lr4=...1(SGI1)
irq27: line=0 pend=0 act=0 en=1 hw=1 ... timer_loaded=1 timer_level=1
```
- HCR 解码：IMO=1；E2H=1 一度可疑，查源码确认是该 openEuler hVHE 内核 `vcpu_reset_hcr` 的正常行为（**一次差点误入歧途的假线索，靠源码核对排除**）。
- **irq27 的 vgic_irq 模型态：line=0、pending_latch=0、active=0——软件模型里它根本不是 pending**，但它的 LR 影子恒为 PENDING。
- 物理计数器对照：整个 ~8 秒风暴期间 KVM vtimer 物理 PPI（irq 11）只在风暴 pCPU 上触发了 **2 次**（`key-data/interrupts-{before,after-fail-1}.txt` 逐 CPU diff）。

**推理**（结合内核源码逻辑）：
- LR 冻结 50000 次不变 ⟺ `kvm_vgic_flush_hwstate` 早退 ⟺ **ap_list 为空**（`vgic_flush_lr_state` 若运行必然重算或清空 LR0——irq27 模型态非 pending 会被 populate 成非 pending 或被 nuke）。**LR 全是残留，这是"果"不是"因"**。
- ap_list 空 → `kvm_vgic_vcpu_pending_irq`=false（VI=0 也排除）→ `kvm_vcpu_block` 不睡的唯一来源是 **`kvm_cpu_has_pending_timer`（timer_level=1）**——风暴引擎定位。
-  wedge 自锁形态浮现：LR 不被消费 → populate 吃掉 line_level → ap_list 空 → 模型里 irq27 消失；timer level 锁存在 1 → 永不 block → 风暴；guest 收不到 tick → 无法重编程 CVAL → 物理 timer 不再触发（2 次）→ 永久死锁。
- **但核心矛盾仍未解**：硬件回读真值显示 LR pending + 全部门控打开，PE 却看不到 vIRQ——架构上不可能。剩下的未知只在 EL2 运行时。

---

## 第 4 阶段：v22 插桩内核留存数据复核（决定性突破）

**设计意图**：EL2 真值（ICH 寄存器在 entry/exit 的实际值）host 侧 eBPF 读不到。但 07-22 曾用 first-entry-trace-v22 插桩内核做过实验（EL2 捕获 ICH_HCR/VMCR/MISR/EISR/ELRSR/AP1R0/LR 写回 ftrace）。**在重启换内核（高成本）之前，先复核留存数据是否已含答案（零成本）**——这是本次调查性价比最高的一步。

**关键动作**：此前的分析结论是「fail/pass 前 64 次 entry 完全相同」。复核时**逐字段**比对完整 hw tuple，而不是只看当初列出的字段子集。

**关键数据**（`key-data/v22-el2-first-entry-trace-full.txt`，3 fail + 1 pass，1193 条 `kvm_arm64_first_entry`；关键行摘录 `v22-el2-key-lines.txt`）：
- 3 个 fail 的 vcpu1，全部 64 帧：`hw_entry` 的 **AP1R0 字段 = `0x8000000000000000`（bit63 置位）**；
- pass 与 07-22 数据集的 25 个 PASS run：AP1R0 只有 `0x0` 或 `0x100000`（IRQ27 被正常消费时的 active 位），**从无 bit63**；
- 其余字段（HCR=1 En、VMCR、ELRSR、LR 内容、MISR/EISR=0）fail/pass 完全一致——**「前 64 次完全相同」的旧结论只在字段子集上成立，AP1R0 被漏掉了**。

**机制解读**：本机 GIC 支持 FEAT_GICv3_NMI（eBPF 读 `pfr1_nmi=1`，`scripts/nmi_check.bt`），bit63 是 NMI active-priority 位；KVM 的 vgic `has_nmi=0` 不管理该位。NMI-active 是超级优先级——**阻断所有 Group-1 虚拟中断呈现**。这与全部观测吻合：LR pending 但不呈现、WFI 无 wake event 持续 trap、I=0 也不投递、guest 永不 EOI（没有 NMI LR 可 EOI，wedge 永久）、4 个不同类型 LR 全部不消费（接口级阻断而非单中断问题）。

**新问题**：bit63 从哪来？（时序上它在 seq0——第一条 guest 指令之前——就已存在。）

---

## 第 5 阶段：当前内核免重启验证相关性

**设计意图**：v22 数据来自旧 guest kernel + 插桩内核；在接受该结论前，必须在**当前环境**（sbench 内核 + openEuler guest kernel + 社区镜像模板）上重现「fail⟺bit63」的相关性。方法：eBPF 直读影子 `vcpu->arch.vgic_cpu.vgic_v3.vgic_ap1r[0]`（put 时从硬件回写，等效观测）。

**关键数据**：fail 风暴窗口 ap1r0=`0x8000000000000000` 贯穿 50000 次 entry；3/3 健康沙箱 ap1r0=0（`key-data/` 中 iface/pass 日志）。加上 v22 数据合计 **fail 4/4 带 bit63，pass 0/29**。

**结论**：相关性在当前环境成立。进入污染源定位。

---

## 第 6 阶段：污染源定位（含两次方法论纠偏）

**设计**：在 put/load 边界探针（`trace_arm64_ap1r_pollution.bt`）比较 `vgic_ap1r[0]` 变化并记录 pCPU——若污染来自特定 pCPU 的硬件残留，会表现为 pCPU 聚集。

**关键数据与两次纠偏**：
- 首个 bit63 事件是 restore 窗口内的一次 put 读回（guest 尚未执行任何指令）→ 污染在 host 侧进入。
- 健康 vcpu0 出现 `ap1r0=0x700000000`——后查明这是**向量 A 的字节级指纹**（见第 7 阶段）。
- **纠偏 1（控制手段失效）**：用 systemd `AllowedCPUs` 做 pCPU 绑核 A/B（313 vs 56 均 9/10 fail），一度误读为「与 pCPU 无关」。后查探针日志发现 vCPU 线程根本没被绑住（shim 进程逃出 cubelet 的 cgroup）——**"控制手段已生效"本身必须验证**。不过后续普查（14 个 pCPU 同时有干净/污染读回）独立地得出了同样结论，结论幸存但过程是教训。
- **纠偏 2（混杂变量）**：标准 openEuler 内核 A/B（grub2-reboot 一次性启动）——故障与 bit63 完全同样复现，**排除 sbench 定制内核（H5）**，把嫌疑钉在主线 KVM 代码 + 这颗 GIC 硬件的行为上。
- GHES/SDEI 外部 NMI 事件与 create 失败窗口无日志相关，外部触发假说弱化。

---

## 第 7 阶段：来源代码分析（两条独立注入向量）

**向量 A（userspace）**：复核 VMM GIC 恢复代码时发现 `icc_regs.rs::icc_attr_access` 用 `&u32` 传 `kvm_device_attr.addr`，而内核 `kvm_sys_reg_{get,set}_user` 一律按 `u64 __user *` 访问 8 字节：
- set（restore）：寄存器 N 的恢复值 = `state[N] | (state[N+1] << 32)`；**最后一个 vCPU 的最后一项（恰为 ICC_AP1R0_EL1）读到 Vec 越界堆垃圾**，垃圾 bit31=1 时即 bit63；
- get（snapshot）：8 字节写溢出到下一槽位（逐次覆盖所以大体无害）+ 末次越界写（UB）。

**模板快照佐证**（`key-data/template-icc-section-parse.txt`）：icc 段恰为 18 项 = 9 寄存器 × 2 vCPU（5 位抢占级，AP1R1+ 跳过），末项即 vCPU1 的 AP1R0——越界读的布局坐实。CTLR=33792 → pbits=5 与 v22 pass 的 active 位 bit20（0xa0>>3=20）互相印证。
**决定性佐证**：健康 vcpu0 的 `0x700000000` = 它的 AP1R0 高 32 位 = 下一槽位（vCPU1 的 SRE=7）——宽度错配的精确字节形态。
**为什么上游从未发现**：非 NMI GIC 上高 32 位是 RES0、写入被忽略，垃圾无害；只在 NMI 能力 GIC（如本机 Kunpeng）上 bit63 致命。同时解释了镜像敏感性（不同快照→不同 restore 堆布局→不同越界内容）与历史故障率漂移。

**向量 B（硬件读回）**：修复向量 A 后重测，bit63 仍出现（且探针还捕到 `0xffffffff00000000`、`0x4100000000` 等其他高位垃圾形态）——证明 **GIC 硬件的 `ICH_AP1R0_EL2` 高 32 位读回本身不可靠**（疑似物理接口瞬时状态混入/未实现位非零），KVM `__vgic_v3_save_aprs` 原样存入影子、下次 load 写回硬件后坐实为真实 NMI-active。KVM 全程无屏蔽是使能条件。

---

## 第 8 阶段：修复与 2×2 析因验证

**设计**：两个向量独立注入 → 需要 2×2 析因（内核补丁 × VMM 补丁）同时证明「因果」与「修复必要性」。

- 内核补丁：`__vgic_v3_save_aprs` 对 8 个 AP 读回值 `& 0xffffffff`（本机 5 位抢占级，合法状态不受影响）；
- VMM 补丁：`icc_attr_access` 改 8 字节缓冲；get 只存低 32 位（**快照格式不变、旧模板兼容**）；set 高 32 位清零。

**关键数据**（串行 20 次 × 4 象限，`key-data/serial-*.log`）：

| 内核 \ VMM | 原版 | icc 修复 |
|---|---|---|
| 未打补丁 | 5/20 | 5/20 |
| aprmask | 5/20 | **20/20，探针 bit63=0** |

- 单修任一 = 5/20：两条向量各自独立足以致病；
- 双修 = 20/20 且 `key-data/ap1r-after-aprmask-kernel.log` 中 bit63 出现次数为 **0**（仅见健康的 `0x100000` active 位）。

**并发验证**：三模板（A=历史复现模板，B/C=用修复版 VMM 新建的模板，顺带验证修复后的 snapshot 采集路径）cube-bench create-only 矩阵（c10/200、c20/300、c50/500、2×c20/300，共 1600 次创建）：**0 次 `reset guest time failed` / `reset reseed random dev failed`**。
**残余失败甄别**：并发残余失败全为 `Create container failed: ttrpc timeout`（不同阶段不同签名）；用**原版 VMM 对照** c10/200 = 43/200 vs 修复版 49/200——失败率相同，证明这是社区栈 + TencentOS 重镜像的固有并发慢启动问题（validated-optimal 分支的优化对象），与本修复无关。**没有这一步对照，高失败率会被误读为修复无效。**

---

## 方法论要点（可复用）

1. **条件触发 + 内核侧聚合**：高频事件（47.5 万/秒）观测必须先以确定性签名（10k WFI）arm 再开窗，且聚合在内核侧完成，否则数据洪泛淹没目标窗口。
2. **每个实验先写判定标准**：「出现什么结果 → 排除哪个分支」在跑之前明确（如「I=0 entry 存在且 LR pending 未被 take → guest 解屏蔽假设死」）。
3. **对照组与结果同口径**：PASS 对照探针与 FAIL 探针读同样的字段；原版 VMM 对照与修复版跑同样的 bench 参数。
4. **控制手段要验证生效**：绑核 A/B 的教训——cgroup 没约束住目标线程时，"对照实验"产生的是伪数据；用探针确认线程实际落点后才下结论。
5. **留存数据的二次利用**：重启换插桩内核之前先复核旧数据；旧结论「完全相同」只在被检查的字段子集上成立——逐字段全量比对找到了被漏掉的 AP1R0。
6. **观测语义要先核对源码**：`ctxt.regs.pstate` 在 entry 采样是否等于 guest 恢复 PSTATE、VMCR 影子是否即硬件回读真值——这些语义成立与否决定数据可信度，均在对应内核树上核实后再引用。
7. **哈希对齐与证据归档**：组件恢复按 sha256 对齐（本地重编≠社区 CI 构建）；每轮实验自包含 evidence 目录（脚本版本、probe 输出、服务日志、哈希清单）。

---

## 关键脚本索引（`scripts/`）

| 脚本 | 用途/设计要点 |
|---|---|
| `trace_arm64_wfi_vgic.bt` | 条件触发（10k WFI arm）+ 256 exit 窗口采 WFI PC/PSTATE/LR/VMCR（第 1 阶段，源自 codex session） |
| `trace_arm64_irq27_entry_pstate.bt` / `_v2` | 每次 guest entry 聚合 PSTATE.I；v2 保序输出前 200 条 entry（第 2 阶段） |
| `trace_arm64_irq27_entry_pstate_pass.bt` | PASS 对照版（无 arming，5 秒窗口） |
| `trace_arm64_irq27_interface_state.bt` | 接口门控全量采样：hcr_el2/VMCR/LR 影子/irq27 模型态/timer 态（第 3 阶段） |
| `trace_arm64_ap1r_pollution.bt` | put/load 边界 AP1R0 变化探针，pCPU 普查（第 6 阶段） |
| `nmi_check.bt` | 读 `pfr1_nmi`/`has_nmi` 确认 GIC NMI 能力 |
| `kvm_vcpu_regdump.c` | pidfd_getfd+ptrace 注入的 vCPU 寄存器审计工具；**重要负结果**：KVM_GET_ONE_REG 需 vcpu->mutex，风暴窗口不可读；并实测发现 shim 主线程 D 态卡死在该 ioctl（第 7 环节的直接证据） |
| `restore_community_stack_for_reset_time_repro.sh` | 哈希对齐的社区栈恢复（含回滚 trap）（第 1 阶段） |
| `serial_create_test.sh` / `deploy_and_test_icc_fix.sh` / `multi_template_concurrent_validation.sh` | 串行/并发验证 runner（第 8 阶段） |
| `kernel-vgic-v3-apr-readback-mask.patch` / `vmm-icc-regs-u64-access.patch` | 两个修复补丁（副本，正本在 `fixes/`） |

## 关键数据索引（`key-data/`）

| 文件 | 内容 |
|---|---|
| `v22-el2-first-entry-trace-full.txt` | 插桩内核 EL2 捕获全量（3 fail + 1 pass，1193 条）；`v22-el2-key-lines.txt` 为四个 attempt 的 seq0 行摘录 |
| `entry-pstate-fail-ordered.log` | fail 风暴 50000 次 entry 的 PSTATE 分布 + 前 200 条有序 entry + i0=3 的 seq/PC |
| `pass-control-entry-pstate.log` | PASS 对照（i0/i1≈50/50，PC 分布丰富） |
| `iface-state-fail-storm-attempt001.log` | 接口态全量（hcr/vmcr/LR 冻结/irq27 模型态/timer_level） |
| `interrupts-before.txt` / `interrupts-after-fail-1.txt` | 物理 PPI27 计数（风暴期间仅 +2） |
| `ap1r-pollution-census.log` | put/load 污染普查（bit63 首现位置、vcpu0 的 0x700000000 指纹） |
| `ap1r-after-aprmask-kernel.log` | 修复后探针输出（bit63=0） |
| `serial-*.log` | 2×2 析因四轮串行结果（单元格↔文件映射与 20/20 轮的归档说明见 `key-data/README.md`） |
| `concurrent-bench-summary.jsonl` | 并发矩阵摘要 |
| `template-icc-section-parse.txt` | 模板快照 icc 段布局解析 |

完整全量数据另存于 `remote-results/`（`arm64-community-stack-reset-time-repro-20260730`、`arm64-entry-pstate-repro-20260730`、`arm64-iface-state-repro-20260730`、`arm64-pass-control-20260730`、`arm64-ap1r-repro-20260730`、`arm64-aprmask-validation-20260731`、`arm64-multi-template-concurrent-20260731`）。
