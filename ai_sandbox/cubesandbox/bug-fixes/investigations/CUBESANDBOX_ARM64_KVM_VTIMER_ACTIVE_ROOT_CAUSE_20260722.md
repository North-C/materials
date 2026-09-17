# CubeSandbox ARM64 多 vCPU 恢复故障 — KVM 内核层根因闭环报告

> 整理日期：2026-07-22  
> 性质：根因最终闭环到 KVM 内核层（vtimer 物理 IRQ active 卡死），含可执行修复  
> 上游链路：[完整实验报告](CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md)（§14.4-14.7 完整因果链、§10.8 VMM 修复尝试被否定）

---

## 1. 一分钟结论

CubeSandbox ARM64 2-vCPU snapshot/restore 间歇性卡死（CPU1 timer/RCU stall → `reset guest time` 8s 超时）的根因是：

> **运行的 `sbench-irqbypass` 定制内核（commit `8394b32f`，2025-06-20）缺失 openEuler/Huawei 的修复 commit `387b558fec9f`（2025-11-18）“KVM: arm64: Deactivate the spurious vtimer interrupt”。** 该 fix 已在内核树 HEAD（`1cefaec0de`，2026-01-04），但在另一分支；运行内核分支早于该 fix。

**机制**：vtimer 中断带 `IRQD_FORWARDED_TO_VCPU` 且 EOImode=1。恢复过期 timer（tpl-3394：CTL=5、CNT≥CVAL）时，`kvm_arch_timer_handler` 存在 ISTATUS 暂态=0 的竞态窗口；缺 fix 时 handler 既不注入也不 deactivate → 物理 IRQ 卡在 **active 态** → 阻塞后续中断投递给 vcpu1 → CPU1 stall。

**修复**：把 `387b558fec9f` cherry-pick 到 sbench-irqbypass 内核分支，重建、重装、重启、A/B。该 fix 在 handler 里对 `should_fire=false` 的 spurious vtimer IRQ 调用 `set_timer_irq_phys_active(ctx, false)`，解除 active 阻塞。

---

## 2. 证据收敛路径（VMM 排除 → KVM 内核）

### 2.1 VMM 层全部排除（详见上游报告 §10.8、§14.4-14.7）

| 维度 | 结论 | 手段 |
| --- | --- | --- |
| counter offset / #8343 | 排除 | v1-v9（三路径均 99/100） |
| timer CTL 写入顺序 | 证伪 | v17（CTL-last，4/5 同模式失败） |
| 软件 vgic 状态（redistributor pending、ap_list 可投递、LR 已装、ICC、PSTATE.I、host 迁移） | **全部正确** | ftrace + kprobe + v18 ICC/PSTATE dump |
| VMM 层机制修复（bulk 延迟 / 重 arm / defer timer） | **最多 ~25% 概率平移 race，无确定性修复** | v19/v20/v21 |

关键判定：vcpu1 上 vgic 软件链路全通（pending→ap_list→LR→ICC 使能→PSTATE.I=0），但中断仍不被 guest 取走 → 残留硬件层；且 VMM 层无法干净修复 → 转向 KVM 内核。

### 2.2 KVM 源码定位（内核树 `/home/lyq/Projects/Micro-VM/kernel`，openEuler 6.6）

逐层读 KVM arm64 源码（`arch/arm64/kvm/{arch_timer.c, vgic/*, arm.c, hyp/vgic-v3-sr.c}`）：

1. `kvm_arch_vcpu_runnable`（arm.c:869）**移除了 `kvm_vcpu_has_pending_timer`**，且 `kvm_cpu_has_pending_timer`（arch_timer.c:521）被改成 **WFIT-only**（上游应是 `should_fire(vtimer)||should_fire(ptimer)`）。这是为 `CONFIG_VIRT_VTIMER_IRQ_BYPASS`（vtimer 走物理 GIC HW 直通）做的定制。
2. 本内核是 `sbench-irqbypass` 定制内核：`CONFIG_VIRT_VTIMER_IRQ_BYPASS=y`，但 **`/proc/cmdline` 无 `kvm-arm.vtimer_irqbypass=1`**，dmesg 无 “vtimer-irqbypass enabled” → irqbypass 运行时**关闭**，走标准 vtimer 路径。
3. `kvm_timer_vcpu_load_gic`（arch_timer.c:799）：`phys_active = kvm_vgic_map_is_active() | ctx->irq.level` → `set_timer_irq_phys_active`。vtimer 是 **forwarded（`IRQD_FORWARDED_TO_VCPU`）+ EOImode=1**。
4. **决定性**：`git log` 找到 commit `387b558fec9f "KVM: arm64: Deactivate the spurious vtimer interrupt"`，其 commit message **逐字描述了本症状**，并已带 `Fixes:` 标签。

### 2.3 运行内核缺该 fix（git 考古）

```
运行内核    8394b32f  2025-06-20  “irqbypass: Use xarray to track producers and consumers”
fix commit  387b558f  2025-11-18  “KVM: arm64: Deactivate the spurious vtimer interrupt”
内核树 HEAD 1cefaec0  2026-01-04  （含该 fix）
```

- `git merge-base --is-ancestor 8394b32f HEAD` → **8394b32f 不在 HEAD 历史里**（独立分支）。
- 8394b32f（2025-06）早于 fix（2025-11）5 个月 → **运行的 sbench-irqbypass 内核不含该 fix**。
- 主机 uname：`6.6.0-132...oe2403sp3.aarch64-sbench-irqbypass-8394b32f`（2026-07-20 构建）确认运行的是 8394b32f 基线。

---

## 3. 机制详解（代码级）

### 3.1 fix commit `387b558fec9f` 原文要点

> “when hypervisor receives a vtimer interrupt but ISTATUS is 0, `kvm_timer_update_irq` will not be
> executed to inject this interrupt into the VM. Since EOImode is 1 and the timer interrupt has
> `IRQD_FORWARDED_TO_VCPU` flag, hypervisor will not write `ICC_DIR_EL1` to deactivate the interrupt.
> **This interrupt remains in active state, blocking subsequent interrupt from being process.**”
>
> `Fixes: 9e01dc76be6a ("KVM: arm/arm64: arch_timer: Assign the phys timer on VHE systems")`

fix 的 diff（arch_timer.c）核心：

```c
 static irqreturn_t kvm_arch_timer_handler(int irq, void *dev_id)
 {
     ...
     if (kvm_timer_should_fire(ctx))
         kvm_timer_update_irq(vcpu, true, ctx);
+    else
+        set_timer_irq_phys_active(ctx, false);   // ← 关键：spurious 时 deactivate 物理 IRQ
     ...
 }
```

（同时新增 `set_timer_irq_phys_active()` helper：`irq_set_irqchip_state(host_timer_irq, IRQCHIP_STATE_ACTIVE, active)`。）

### 3.2 在 tpl-3394 恢复时的失效链路

```
tpl-3394 snapshot：vCPU vtimer 过期（CNTV_CTL=5 ENABLE|ISTATUS，CVAL≤CNT）
 └─ VMM cpu set_state 写 CNTV_CTL（SET_ONE_REG）
     └─ kvm_arm_timer_write(CTL)：timer_set_ctl(timer, val & ~ARCH_TIMER_CTRL_IT_STAT)
         ← 把 ISTATUS 位清掉，存为 CTL=1（ISTATUS 由实际 CVAL/CNT 重算）
 └─ vCPU load（kvm_arch_vcpu_load → kvm_timer_vcpu_load → timer_restore_state）
     写物理 CNTV_CVAL/CTL，过期 timer 触发物理 vtimer IRQ（forwarded）
 └─ kvm_arch_timer_handler 处理该物理 IRQ
     竞态窗口：此刻 kvm_timer_should_fire() 返回 false（ISTATUS 暂态 0）
     ├─ 旧代码（运行内核 8394b32f，无 fix）：
     │    不注入（should_fire=false）+ 不 deactivate（forwarded+EOImode=1 无 ICC_DIR_EL1）
     │    → 物理 vtimer IRQ 卡在 ACTIVE
     │    → 对应 vgic irq->active=true
     │    → vgic_v3_populate_lr：if(irq->active) allow_pending=false（level）→ LR 不置 pending 位
     │    → guest 收不到 timer PPI → WFI-poll 死循环 → CPU1 timer/RCU stall
     └─ 打了 fix 的内核：else set_timer_irq_phys_active(ctx,false) → 解除 active → 不阻塞
```

`vgic_v3_populate_lr`（vgic-v3.c:110）的 active 阻塞逻辑（与本机制吻合）：

```c
 if (irq->active) {
     val |= ICH_LR_ACTIVE_BIT;
     ...
 }
 ...
 if (irq->config == VGIC_CONFIG_LEVEL) {
     val |= ICH_LR_EOI;
     if (irq->active)
         allow_pending = false;      // ← active 时 pending 位不置，guest 不被通知
 }
 ...
 if (allow_pending && irq_is_pending(irq))
     val |= ICH_LR_PENDING_BIT;
```

---

## 4. 为何解释全部历史证据

| 历史观察 | 本根因如何解释 |
| --- | --- |
| restore 专属（全新 Template ~1/100，tpl-3394 过期 timer 0/100） | ISTATUS 竞态窗口只在恢复**过期** timer 时出现；全新 Template timer 起始 disabled，不触发 |
| per-vcpu1（vcpu0 正常） | 次级 vCPU 的 load/resume 时序更易落入 ISTATUS=0 窗口；vcpu0（BSP）路径与时序不同，能完成 EOI |
| 软件 vgic 状态全正确（pending/ap_list/LR/ICC/PSTATE.I=0/host 无迁移） | 阻塞发生在**物理 IRQ active 态**（forwarded），非软件 vgic 模型；故所有软件层读数正常 |
| v18 ICC dump 两 vcpu 相同且正确 | ICC 无关；问题在物理 IRQ active |
| v17（CTL 顺序）/v19（延迟）/v20（重 arm）/v21（defer）最多 ~25% | VMM 改变的是 ISTATUS 竞态窗口的概率，**无法消除** KVM 内核的 active-stuck；只有内核 fix 能确定性解除 |
| v15/v16（set_state 内逐寄存器穿插日志）100/100 | 大幅时序扰动把 vcpu1 移出 ISTATUS=0 窗口（观察效应），非真实修复 |
| 时序敏感、非单调 | ISTATUS 暂态窗口宽度由调度/时序决定 |
| 1 vCPU 稳定 | 单 vCPU 无次级 vCPU 的 load 竞态 |
| 残留高 CPU CubeShim | vCPU 卡在 WFI-poll 自旋 |

---

## 5. 修复方案

### 5.1 主修复（必需）

把 `387b558fec9f` cherry-pick 到运行的 sbench-irqbypass 内核分支（8394b32f 基线）：

```bash
cd /home/lyq/Projects/Micro-VM/kernel
git checkout <sbench-irqbypass-8394b32f 分支>   # 运行内核基线
git cherry-pick 387b558fec9f8b0d3e0a4d48b5912301c1477bdd
# 解决可能的上下文冲突（fix diff 小且自包含，主要在 arch_timer.c）
# 构建内核（cube 仓 scripts/build-kernel.sh + builder 镜像，或标准 make）
# 安装到 192.168.25.90，重启，A/B
```

预期：tpl-3394 A/B 从 0/X 失败 → 确定性成功。

### 5.2 加固（建议）

审计 `kvm_timer_vcpu_load_gic`（arch_timer.c:799）的 restore-path active 一致性：

```c
phys_active = kvm_vgic_map_is_active(vcpu, timer_irq(ctx));  // 读 vgic 的 active 态
phys_active |= ctx->irq.level;
set_timer_irq_phys_active(ctx, phys_active);
```

确保恢复过期 timer 时不会把陈旧/错配的 active 态设到物理 IRQ。handler fix 覆盖运行时 spurious；restore/load 路径可补一道 active 一致性检查（针对过期 timer 的首帧）。

### 5.3 旁证建议（若 cherry-pick 冲突大）

- 备选 A：直接升级到内核树 HEAD（`1cefaec0de`，2026-01-04，含该 fix 及更多 KVM arm64 修复）构建——但需评估 sbench-irqbypass 特性的兼容。
- 备选 B：对比上游主线 6.6 的 `arch/arm64/kvm/arch_timer.c`，确认本故障路径在主线已修。

---

## 6. 验证方法

1. **构建修复内核**（不重启前先产出 Image/rpm）。
2. **安装 + 重启** 192.168.25.90（需授权；生产类主机）。
3. **A/B**：tpl-3394 确定性坏 Template × 多次，对比修复前后（预期 0/X → 确定性成功）。
4. **门禁**：全新 2C/4G Template 连续 100 次 create-command-delete，无 RCU/timer 错误、无残留 shim、Sandbox 归零。
5. **回归**：2/4/8 vCPU + Snapshot/Restore、Pause/Resume、Rollback、Clone 各 ≥20 次。
6. **（可选）kprobe 复核**：在修复内核上 kprobe `set_timer_irq_phys_active` 调用，确认 spurious vtimer IRQ 被正确 deactivate（vcpu0 与 vcpu1 一致）。

验收门槛沿用上游报告 §3（全新 2 vCPU/4 GiB 100/100、无 RCU/timer、无残留 Shim、Sandbox=0）。

---

## 7. 关键源码位置（openEuler 6.6，`/home/lyq/Projects/Micro-VM/kernel`）

| 位置 | 含义 |
| --- | --- |
| `arch/arm64/kvm/arch_timer.c:312` | `set_timer_irq_phys_active()`（fix 新增的 helper） |
| `arch/arm64/kvm/arch_timer.c:320` `kvm_arch_timer_handler` | fix 在此加 `else set_timer_irq_phys_active(ctx,false)` |
| `arch/arm64/kvm/arch_timer.c:521` `kvm_cpu_has_pending_timer` | 被定制为 WFIT-only（上游应是 should_fire） |
| `arch/arm64/kvm/arch_timer.c:799` `kvm_timer_vcpu_load_gic` | restore/load 的物理 IRQ active 设置（加固点） |
| `arch/arm64/kvm/arch_timer.c:970` `kvm_timer_vcpu_load` | vCPU load 主入口 |
| `arch/arm64/kvm/arch_timer.c:1446` `kvm_arm_timer_write` | CTL 写清 ISTATUS（`val & ~IT_STAT`） |
| `arch/arm64/kvm/arm.c:869` `kvm_arch_vcpu_runnable` | 移除了 `kvm_vcpu_has_pending_timer` |
| `arch/arm64/kvm/vgic/vgic-v3.c:110` `vgic_v3_populate_lr` | `irq->active → allow_pending=false`（active 阻塞 pending 的 vgic 侧） |

## 8. 相关 commit / 参考

- **缺失的 fix**：`387b558fec9f8b0d3e0a4d48b5912301c1477bdd` “KVM: arm64: Deactivate the spurious vtimer
  interrupt”（Huawei/openEuler，2025-11-18，`Fixes: 9e01dc76be6a`，gitee issue ID7470）。
- 运行内核基线：`8394b32faecd` “irqbypass: Use xarray to track producers and consumers”（2025-06-20）。
- 相关定制：`b57de4ffd7c6` “Simplify kvm_cpu_has_pending_timer()”、`CONFIG_VIRT_VTIMER_IRQ_BYPASS` 系列
  （`747c447574f3`、`d306753c582d`、`b8b70fe6bcf0` 等）、VirtCCA CVM timer 系列（`2df17ca863ac` 等）。
- 社区先例：Cloud Hypervisor Issue #6001（aarch64 恢复后 vCPU 100%，建议换新内核）——与“换含本 fix 的内核”一致。

## 9. 主机当前状态

192.168.25.90 仍运行诊断版 v16（CubeShim，VMM 层），内核未变（`8394b32f`，缺 fix）。tpl-3394 保留 READY。
修复需重建并重启内核（VMM 侧无需再改，v16 可继续诊断或切回社区原版）。

## 10. 结论

> 故障根因最终闭环到 **KVM 内核层**：运行内核（`8394b32f`）缺失 “Deactivate the spurious vtimer
> interrupt” 修复（`387b558fec9f`），导致恢复过期 timer 时 vtimer 物理 IRQ 卡在 active 态、阻塞
> vcpu1 的中断投递。修复 = 应用该 fix（+ restore/load active 一致性加固）并重建内核。VMM 层无需改动。
