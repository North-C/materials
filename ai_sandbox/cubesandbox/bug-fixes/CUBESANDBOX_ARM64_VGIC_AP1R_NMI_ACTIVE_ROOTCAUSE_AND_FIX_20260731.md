# CubeSandbox ARM64 多 vCPU 模板恢复故障（reset guest time failed）根因与修复报告

- 日期：2026-07-31
- 测试节点：`192.168.25.90`（Kunpeng ARM64，384 pCPU，GICv3 + FEAT_GICv3_NMI）
- 关联文档：`CUBESANDBOX_ARM64_2VCPU_WFI_TIMER_DELIVERY_ROOTCAUSE_20260724.md`（前序分析，本报告修正并终结其遗留问题）、`CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md`（v1–v9 clock 修复矩阵）、`CUBESANDBOX_CH_ISSUE6966_UB_COMPARISON_20260721.md`（相邻但不同的另一个 UB）
- 修复产物：`fixes/arm64-vgic-apr-nmi-active-20260731/`

## 1. 问题现象

ARM64 上 2-vCPU 模板 snapshot restore 创建沙箱时间歇失败（历史上 2%–90% 不等，随时间升高），失败签名为 Cubelet 报 `reset guest time failed: ttrpc err: Receive packet timeout`（约 8 秒）或 `reset reseed random dev failed`，或更表层的 `PortBindingFailed` 探针超时（约 30 秒）。失败 VM 内 CPU1 陷入 WFI 风暴（~20–47.5 万次/秒 WFI trap），guest agent 无响应，随后出现 RCU stall / `Possible timer handling issue on cpu=1`。`maxcpus=1` 可完全规避。

## 2. 根因（一句话）

**vCPU 的 `ICH_AP1R0_EL2` bit63（FEAT_GICv3_NMI 的 NMI active-priority 位）被置为 1 并被 KVM 在影子↔硬件之间永久来回传递；该幽灵 NMI-active 状态以超级优先级阻断全部 Group-1 虚拟中断的呈现，vCPU 从此收不到任何虚拟中断（timer/SGI/LPI 全灭），形成不可恢复的中断饥饿 wedge。**

该位被置起有两条相互独立的注入向量，各自都能单独以高概率触发故障：

- **向量 A（VMM/userspace）**：cloud-hypervisor fork 的 `icc_regs.rs` 用 `&u32` 访问 `KVM_DEV_ARM_VGIC_GRP_CPU_SYSREGS`，而内核 `kvm_sys_reg_{get,set}_user` 一律按 `u64 __user *` 读/写 8 字节。restore（set）侧，最后一个 vCPU 的最后一个寄存器（恰为 `ICC_AP1R0_EL1`）的高 32 位读到 **Vec 越界的堆垃圾**；垃圾 bit31 置 1 时即成为寄存器 bit63。
- **向量 B（内核/硬件读回）**：这颗 NMI 能力的 GIC 上，`ICH_AP1R0_EL2` 的高 32 位（架构上未实现/RES0）会读回瞬时垃圾（实测到 `0x80000000`、`0xFFFFFFFF`、`0x41` 等形态）；`__vgic_v3_save_aprs`（vcpu put 时）将其原样存入 vCPU 影子，下次 vcpu load 的 `__vgic_v3_restore_aprs` 再写回硬件——**读回垃圾被写回后坐实为真实的 NMI-active**。

两条向量解释了一切历史观测：故障率随镜像/模板/时间变化（向量 A 的堆内容概率）、随时间推移整体升高、openEuler 镜像几乎不触发而社区（TencentOS）镜像高触发（restore 窗口内堆布局/时序差异）、换 guest kernel 改变触发率（restore 时序变化）、`maxcpus=1` 规避（vCPU0 的高 32 位错位读到的是下一槽位的 SRE=7 等无害值，且 1-vCPU 模板无 CPU1 参与）。

## 3. 完整因果链

1. bit63（NMI-active）进入 vCPU1 的 AP 状态（向量 A 或 B，发生在 restore 窗口内、第一条 guest 指令之前）。
2. NMI-active 是超级优先级 → 虚拟 CPU 接口不再向 PE 呈现任何 Group-1 虚拟中断（HCR.IMO、ICH_HCR.En、VMCR.VENG1/VPMR 全部正常也无济于事）。
3. guest 收不到 timer tick → vCPU1 的 idle 循环永远等不到中断；WFI 无 wake event 而持续 trap（HCR.TWI=1）。
4. 幽灵 active 永远不能被 EOI（不存在对应的 NMI LR）→ wedge 随 VM 终身；每次 put/load 经影子回存/重写，跨 pCPU 迁移也甩不掉。
5. 曾经 populate 进 LR 的 pending 中断（IRQ27 等 5 个）永不消费 → 其 `line_level` 被 populate 吃掉、`ap_list` 清空、flush 早退 → LR 影子冻结为残留（这是此前观测到的"LR pending 不被消费"现象的来源，是**结果而非病因**）。
6. KVM timer 子系统的 `timer_level=1` 使 `kvm_cpu_has_pending_timer()` 恒真 → `kvm_vcpu_block` 永不睡眠 → 47.5 万次/秒的 WFI trap 风暴（vcpu 线程占满 CPU，KVM_RUN 全程持有 `vcpu->mutex`）。
7. CubeShim 的 reset guest time / reseed random dev 流程需要对 vcpu0 做 `KVM_GET_ONE_REG`，阻塞在永不释放的 `vcpu->mutex` 上 → 约 8 秒后 ttrpc 超时 → `reset guest time failed`。（哪个错误先报取决于 reset-time 8 秒与探针 30 秒哪个超时先触发。）

## 4. 关键实验与证据

| # | 实验 | 结果 | 结论 |
|---|---|---|---|
| 1 | 纯社区栈（cubelet `88e5e224`/shim `4702fde1`/cubemaster `0b78e83c`）+ 社区镜像复现 | 4 次串行 3 fail，WFI/LR 签名与历史一致 | 故障与本地组件改动无关 |
| 2 | kvm_entry 全量 PSTATE 采样（fail 窗口 50000 次 entry） | 49997 次 I=1；3 次 I=0（`cpuidle_idle_call+0xb8`/`do_idle+0x70`）且 LR0 pending 仍不投递；PASS 对照 I=0/I=1≈50/50 | guest idle 活着，vIRQ 从不呈现 |
| 3 | 接口态采样 | HCR.IMO=1、ICH_HCR.En=1、VMCR VENG1=1/VPMR=0xf0 全部正常（且为硬件回读真值）；5 个 LR 冻结；ap_list 空；timer_level=1 | 门控正常；LR 是残留；风暴引擎是 timer level |
| 4 | 物理 PPI27 计数 | 整个风暴仅 2 次触发 | 物理 timer 侧已死（wedge 下游） |
| 5 | v22 插桩内核留存 EL2 捕获复核（/tmp/ichlr_trace.txt，3 fail+1 pass） | **fail/pass 唯一 EL2 差异 = `ICH_AP1R0_EL2`：fail 3×64 帧全部 `0x8000000000000000`，pass 全部无 bit63**（25 个历史 PASS run 同）；MISR/EISR 干净 | 锁定 bit63 |
| 6 | 当前内核 eBPF 验证 | fail 风暴窗口 `ap1r0=0x8000000000000000` 恒定；3/3 pass 为 0 | 相关性在非插桩内核成立 |
| 7 | put/load 污染探针 | bit63 在 restore 窗口的 put 读回首次出现并跨 pCPU 传播；健康 vcpu0 出现 `0x700000000`（=下一槽位 SRE=7 错位，向量 A 的字节级佐证） | 双向量各自独立证实 |
| 8 | pCPU 绑核 A/B（313 vs 56，后证实 cgroup 未生效）；14 个 pCPU 同时有干净/污染读回 | 排除坏核假说 | bit63 与 pCPU 无关 |
| 9 | 标准 openEuler 内核 A/B（重启） | 故障与 bit63 同样复现 | 排除 sbench 定制内核 |
| 10 | 模板快照 icc 段解析 | 18 项 = 9 寄存器 × 2 vCPU；末项即 vCPU1 的 AP1R0，set 侧 8 字节读越界 | 向量 A 布局证实 |
| 11 | 修复矩阵（见 §6） | 单修任一向量 5/20；双修 20/20 且 bit63=0；并发 1600 次 0 次目标签名 | 因果闭环 |

## 5. 修复内容

### 5.1 内核补丁（`kernel-vgic-v3-apr-readback-mask.patch`）

`arch/arm64/kvm/hyp/vgic-v3-sr.c::__vgic_v3_save_aprs`：8 个 AP 寄存器的硬件读回值一律 `& 0xffffffff`（每个已实现 AP 寄存器仅低 32 位合法；本机 5 位抢占级）。斩断向量 B 的"读回污染 → 写回坐实"循环。guest 无 NMI LR，NMI-active 永不合法，屏蔽安全。

### 5.2 VMM 补丁（`vmm-icc-regs-u64-access.patch`）

`hypervisor/hypervisor/src/kvm/aarch64/gic/icc_regs.rs::icc_attr_access` 改为 `&mut u64` 缓冲；get 侧仅保存低 32 位（**快照序列化格式不变，旧模板兼容**）；set 侧高 32 位恒 0。消除向量 A 的 OOB 读（set）与 OOB 写（get）。注意该 UB 与 issue #6966 不同（那是 `*const` 可变性 UB，本 fork 因 Rust 1.77.2 未显现），两者都应回移。

### 5.3 产物

- `artifacts/cube-runtime-iccfix-a68d64cd`（CubeShim workspace 构建，含 `snapshot` 子命令；sha256 `a68d64cd…`）
- `artifacts/kernel-6.6.0_sbench_irqbypass_xarray_v2_aprmask-2.aarch64.rpm`（sbench 树 + 内核补丁）
- `artifacts/*-reference`（补丁前后的参考源文件）

## 6. 验证矩阵（.90，社区栈 + 社区 TencentOS 镜像 + 历史复现模板 tpl-42e1ad04）

| 配置 | 测试 | 结果 |
|---|---|---|
| 未修复基线 | 串行 ×20 | **5/20 pass**，fail 均带 bit63 |
| 仅 VMM 修复 | 串行 ×20 | 5/20（向量 B 仍注入） |
| 仅内核修复 | 串行 ×20 | 5/20（向量 A 仍注入） |
| **双修复** | 串行 ×20 | **20/20 pass，探针 bit63=0** |
| **双修复** | 模板 A：c10/200、c20/300、c50/500 | 1000 次创建，**0 次 reset guest time / reseed 签名** |
| **双修复** | 修复版 VMM 新建模板 B/C：各 c20/300 | 600 次创建，**0 次目标签名**（同时验证修复后 snapshot 采集路径） |

并发下残余失败（A ~25%、新模板更高）全部为 `Create container failed: ttrpc Receive packet timeout`——实例已通过 reset-time/reseed 关卡，属不同阶段、不同问题；原版 VMM 对照失败率相同（43/200 vs 49/200），证明其为**社区栈 + TencentOS 重镜像的固有并发慢启动问题**（即 validated-optimal 性能分支的优化对象），与本修复无关。

## 7. 历史上被排除的方向（留档防回潮）

- PR #8343（guest clock CNTVCT 追赶，本地 v1–v9 矩阵）：消除恢复后 RCU 噪声但从未消除故障（最佳 99/100，与无修复对照统计不可区分）。与本根因无关，不建议合入（v7 的 1 秒封顶使 monotonic 落后 wall clock）。
- "通用 KVM/EL2 不呈现 ICH_LR"（旧文档 §11.4）：被 EL2 捕获否定——LR 真实写入硬件且 pending。
- WFI PC 不推进：证伪（deferred increment 观测假象）。
- 单个坏 pCPU、vtimer_irqbypass（未启用）、HCR.IMO/PMR/组使能、sbench 定制内核（标准内核同样复现）：均排除。

## 8. 遗留问题与建议

1. **内核补丁建议补充**：userspace SET 路径（`vgic-sys-reg-v3.c` 的 ICC AP 描述符）同样做屏蔽，纵深防御未修复 VMM/旧快照；该问题可上游（NMI 能力 GIC + `has_nmi=0` 时 AP 读回不屏蔽属主线 6.6 的真实缺陷）。
2. **VMM 补丁可上游 cloud-hypervisor**（非 NMI GIC 上无害故从未暴露）；同时建议回移 #6966 的 `02f146f`。
3. **其他独立 bug**（与本根因无关，建议分别立项）：
   - 并发下 `Create container failed: ttrpc` 慢启动超时（社区栈 + 重镜像）；
   - cloud-hypervisor 并发 TAP `WriteTap(EIO)`（`net_util/src/queue_pair.rs:114`）；
   - pause/resume 失败后 CubeAPI=paused 与 VMM=launched 状态机分裂、shim 对 SIGTERM 无响应只能 SIGKILL；
   - CubeShim reset-time 路径对 `KVM_GET_ONE_REG` 无超时保护（vcpu mutex 可被永久阻塞）——即使未来有别的原因导致 vCPU 不退出 KVM_RUN，此缺陷仍会放大为沙箱创建失败。
4. **运维**：.90 曾因 `/var/crash` 319G vmcore 写满根分区导致 MySQL/CubeMaster 崩溃；已清理（保留 07-30 最新一份，该 panic 发生在标准内核复现窗口，可另行分析）。建议配置 kdump 轮转上限。

## 9. 证据索引

- 修复与补丁：`fixes/arm64-vgic-apr-nmi-active-20260731/`
- 验证数据：`remote-results/arm64-aprmask-validation-20260731/`、`remote-results/arm64-multi-template-concurrent-20260731/`、`remote-results/arm64-community-stack-reset-time-repro-20260730/`、`remote-results/arm64-entry-pstate-repro-20260730/`、`remote-results/arm64-iface-state-repro-20260730/`、`remote-results/arm64-pass-control-20260730/`、`remote-results/arm64-ap1r-repro-20260730/`
- 工具：`scripts/trace_arm64_irq27_entry_pstate{,_v2,_pass}.bt`、`trace_arm64_irq27_interface_state.bt`、`trace_arm64_ap1r_pollution.bt`、`kvm_vcpu_regdump.c`、`serial_create_test.sh`、`multi_template_concurrent_validation.sh`、`deploy_and_test_icc_fix.sh`
- .90 现场：内核构建树 `/home/lyq/kernel-build-irqbypass-v2-20260720/`（含 `vgic-v3-sr.c.pre-aprmask` 备份）、`/home/lyq/arm64-*/` 各实验目录、07-30 vmcore `/var/crash/127.0.0.1-2026-07-30-23:13:18/`
