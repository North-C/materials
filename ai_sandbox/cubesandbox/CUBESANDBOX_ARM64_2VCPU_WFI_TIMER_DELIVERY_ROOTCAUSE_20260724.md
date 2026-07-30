# CubeSandbox ARM64 2-vCPU restore 失败根因链与 tracepoint 证据对照

> 日期：2026-07-24
> 节点：`192.168.25.90`，stock 内核 `6.6.0-132.0.0.111.oe2403sp3.aarch64`（**含** vtimer fix `387b558fec9f`）
> 测试对象：坏 2-vCPU Template `tpl-d531debb219747ae8d69e947`，community shim `4702fde1…`，无 VMM 插桩
> 采集方式：stock 内核既有 tracepoint（`kvm_entry/kvm_exit/kvm_timer_*/vgic_update_irq_pending`），独立 tracefs instance，64MB/CPU buffer，无 reboot、无 shim 改动
> 数据目录：`.90:/home/lyq/arm64-v26-tracepoint-capture-20260724/`（`trace.txt` 343MB、`ev_timer_update_irq.txt`、`ev_vgic_irq_pending.txt`、`kallsyms_full.txt` 97348 符号、`FINDINGS.md`、`sdk/results.jsonl`）
> 性质：根因**方向**已由 tracepoint 证据闭合到「timer IRQ27 投递断裂」；精确投递层（ICH_LR）仍待插桩内核确认。

---

## 1. 结论（一段话）

ARM64 2-vCPU snapshot/restore 后，**次级 vCPU（CPU1）卡在 `cpu_do_idle` 的 WFI 循环**（99.94% 的退出是 WFx），处于 idle 等中断状态；而它的虚拟定时器中断 **IRQ27（PPI）在 KVM 软件层已被置 pending**（`kvm_timer_update_irq` 把 level 置 1 共 115 次），**却始终没有被投递给 guest CPU1**——CPU1 在同一时段收到了 267 个其它中断，但从不消费 IRQ27（timer line 从未被 deassert，level0=0）。WFI 因此永远不被打断 → CPU1 不推进 timer softirq/调度 → guest CPU1 RCU stall → 宿主 `reset_guest_date_time` ttrpc 在 8s 内无响应 → `reset guest time failed: ttrpc err: Receive packet timeout`。**vtimer-active fix 已在该内核，故不是 active-stuck；这是另一处 timer/vGIC 投递断裂。** 「投递断裂发生在 ICH_LR 层」是该链唯一尚未被 tracepoint 直接证实的一环（tracepoint 看不到实际 ICH_LR），需 first-entry-trace 插桩内核确认。

---

## 2. 因果链（每环 → 对应证据）

| # | 链环 | 机制 | 证据（见 §3） |
|---:|---|---|---|
| 1 | restore 写入 CPU1 + timer + vGIC 状态 | VMM 把 snapshot 的 CPU1 状态、过期 timer、vGIC 写入 KVM；CPU1 线程 paused 启动后 resume 释放 | VMM restore 链（既有报告）；本 Template 的 snapshot timer 已过期（既有坏模板分析：负 deadline） |
| 2 | CPU1 timer 过期 → KVM 软件 IRQ27 pending | restore/load 后过期 timer 触发，`kvm_timer_update_irq` 把 CPU1 的 IRQ27 line 置 1 | `ev_timer_update_irq.txt`：vcpu1-50975 `VCPU:1 IRQ27 level1` 共 115 次 |
| 3 | vGIC 软件层也把 IRQ27 置 pending | `vgic_update_irq_pending` 对 CPU1 IRQ27 level=1 | `ev_vgic_irq_pending.txt`：与 timer_update_irq 数量同级（~16K 条，IRQ27 为主） |
| 4 | **但 IRQ27 没有投递给 guest CPU1** | guest CPU1 始终不消费 IRQ27（timer line 从未 deassert）；而同一时段 CPU1 收到 267 个其它中断（说明通用投递通路可用） | vcpu1-50975：`level0=0`（从不 deassert）；`kvm_exit: IRQ` 267 次；pass/CPU0 对照均能消费 IRQ27 |
| 5 | CPU1 进入 `cpu_do_idle` WFI 空转 | 无有效中断唤醒，CPU1 反复 WFI（WFI 应被 pending 中断打破，但 IRQ27 未真正投递） | 全量 HSR_EC：vcpu1-50975 1,418,816/1,419,732 = **99.94% WFx**；主导 PC `cpu_do_idle+0x4(wfi)` 199304/200000 |
| 6 | CPU1 不推进 → RCU stall | CPU1 不进 quiescent state、不跑 timer softirq | 故障签名 `reset guest time failed` + 既有 RCU stall 日志（下游） |
| 7 | 宿主 ttrpc 超时 | guest 半挂（CPU1 stall），agent 的 `set_guest_date_time` 跨 CPU/RCU 操作阻塞 | 11/12 失败全是 `reset guest time failed: ttrpc err: Receive packet timeout` @ ~8s |

**关键**：第 4 环是根因核心（IRQ27 投递断裂）；第 5–7 环是其下游必然结果。

---

## 3. 证据对照（逐条数据 + 出处）

### 3.1 失败规模与签名
- 12 次 restore：**11 失败 / 1 成功**（`sdk/results.jsonl`）。
- 11 次失败全部：`SandboxException('500: ... Create sandbox failed:reset guest time failed:ttrpc err: Receive packet timeout Elapsed(())')`，`elapsed_s≈8.0`。
- 1 次成功（attempt 5，sandbox `3f264049…`）：`create_ok/command_ok/delete_ok=true`，`elapsed_s=0.6421`，`command_stdout="ready vcpus=2"`。

### 3.2 卡死 CPU1（vcpu1-50975）的退出结构
```
total kvm_exit      : 1,419,732
HSR_EC 0x0001 (WFx) : 1,418,816   (99.94%)   ← cpu_do_idle/WFI
HSR_EC 0x0001 之外的 IRQ 退出 : 267          ← 收到了 267 个其它中断
HSR_EC 0x0024 (DABT_LOW) : 451              ← 开机/console(pl011 MMIO)阶段
HSR_EC 0x0020 (IABT_LOW) : 198              ← 开机阶段
HSR_EC 0x0000 (UNKNOWN) : 267              ← 与 IRQ 退出对应（IRQ 取走时 ESR_EC=0 正常）
```
- 主导故障 PC：`0xffffae7ac7660730`，20 万样本命中 **199,304** 次；符号化 → **`cpu_do_idle +0x4`（即 `wfi`）**（`kallsyms_full.txt` 经 `/proc/kallsyms` 解析）。
- 次热 PC `0xffffae7ac7227898/785c` → `pl011_write/pl011_read`，仅 47/45 次，属**开机 console 阶段**，不是卡死循环。

### 3.3 IRQ27（timer）在 CPU1 上 software-pending 但从不被消费
`ev_timer_update_irq.txt` 按 vcpu1-PID 统计 `VCPU:1 IRQ27` 的 level1(assert)/level0(deassert)：

| vcpu1 PID | level1(assert) | level0(deassert=消费) | kvm_exit 总数 | 结果 |
|---|---:|---:|---:|---|
| 50975 | 115 | **0** | 1,419,732 | 失败 |
| 51839 | 98 | **0** | 980,866 | 失败 |
| 51240 | 93 | **0** | 282,740 | 失败 |
| 52242 | 4 | 0 | 1,398,124 | 失败 |
| 51940 | 1 | 0 | 4,831,485 | 失败 |
| …（其余失败 PID 同样 level0=0） | | | | |
| **51538（成功）** | **302** | **1587** | 8,416 | **成功** |

- 失败：IRQ27 被 KVM 反复 assert（level1=N），**从不 deassert（level0=0）** → guest CPU1 从未 EOI/消费 timer。
- 成功：IRQ27 正常 assert/deassert 循环（302/1587）→ timer 被正常消费、guest 推进。

### 3.4 同一 restore 内 CPU0 健康、CPU1 卡死（最锐利对照）
vcpu0-50974 与 vcpu1-50975 是**同一次 restore** 的两个 vCPU 线程（PID 连续）：
```
CPU0 (vcpu0-50974)：kvm_exit 3,856  | WFx 134 | IRQ27 level1=89 level0=12（已消费）
CPU1 (vcpu1-50975)：kvm_exit 1,419,732 | WFx 1,418,816 (99.94%) | IRQ27 level1=115 level0=0（未消费）
```
同一 restore、同一 VMM、同一 snapshot：CPU0 正常跑、正常消费自己的 timer；CPU1 卡死、不消费自己的 timer。→ 故障是 **CPU1（次级 vCPU）专属**，且是 **CPU1 自己的 timer IRQ27 不被投递**（不是全局、不是 CPU0）。

### 3.5 CPU1 收到其它中断、唯独不收 IRQ27
- vcpu1-50975 有 **267 次 `kvm_exit: IRQ`**（HSR_EC=0x0000，IRQ 被取走时的正常 EC），样本 PC 落在 `0xffffae7ac71ff924` / `0xffffae7ac6aadd04`（非 cpu_do_idle）。
- 说明 guest CPU1 的**通用中断投递通路是通的**（能取走 267 个中断），但**唯独 timer IRQ27 没被取走/消费**（level0=0）。
- 又因同一 guest（同 Template）在成功 attempt 里能正常消费 IRQ27（302/1587）→ guest 侧 timer handler 没问题 → 失败时 IRQ27 **根本没投递到 guest**。

### 3.6 vtimer-active fix 已在场（排除 active-stuck）
- `387b558fec9f`（“Deactivate the spurious vtimer interrupt”）是 `openEuler-24.03-LTS-SP3` HEAD 与 `6.6.0-132.0.0` tag 的祖先；.90 运行的 `6.6.0-132.0.0.111.oe2403sp3`（2025-12-29 构建）在该 lineage 内 → **fix 已在运行的内核**（见 [[cubesandbox-kvm-vtimer-active-rootcause]] 证伪记录）。
- 故 §2 第 4 环的投递断裂**不是** `387b558fec9f` 所修的 spurious-vtimer active-stuck，而是另一处 timer/vGIC 投递问题。

---

## 4. 已确认 / 推断 / 未决（诚实边界）

**已由 tracepoint 直接证实：**
- CPU1 卡在 `cpu_do_idle`/WFI（99.94% WFx，主导 PC=cpu_do_idle）。
- CPU1 的 timer IRQ27 在 KVM 软件层被 assert（level1=115）、从不 deassert（level0=0）。
- 同一 restore 内 CPU0 正常、CPU1 卡死；成功 attempt 的 CPU1 正常消费 IRQ27。
- CPU1 能收到 267 个其它中断，唯独不收 timer IRQ27。

**强推断（未直接成像，但由上唯一自洽）：**
- timer IRQ27 **没有被投递给 guest CPU1**（软件 pending 但未进 guest）。依据：guest 能消费 IRQ27（pass 证）、CPU1 通用中断通路可用（267 IRQ 证）、却唯独不消费 IRQ27 → 只能是没投递。

**未决（tracepoint 看不到，需插桩内核）：**
- 投递断裂的**精确层**：IRQ27 在失败 CPU1 的 entry 时**是否在实际 ICH_LR**？matrix §9.1 的成功样本里 CPU1 PRE_ENTRY 时 IRQ27 已物化进 ICH_LR27（`used_lrs=1, hw_entry_irq27_lr=...`）。假设：失败时 IRQ27 **没进 ICH_LR27**（或仅 active 无 pending、或 phys_active 卡、或优先级/门控问题）。这一环只能由 first-entry-trace 插桩内核的 `kvm_arm64_first_entry`(PRE_ENTRY) 实测 ICH_LR/VMCR/ELRSR/AP1R0 来定。
- **为何 2-vCPU 高发、3/4-vCPU 稳定**：本数据只覆盖 2-vCPU；需在插桩内核上同口径采 2-vCPU 失败 vs 3-vCPU 成功的 CPU1 首次 entry，看 ICH_LR 在哪层分叉。

---

## 5. 排除项（已证伪/降级的方向）

| 方向 | 判断 | 依据 |
|---|---|---|
| vtimer-active / `387b558fec9f` 缺失 | 排除 | fix 已在 stock 内核，故障仍复现（§3.6） |
| 「DABT/内存异常风暴 / pl011」 | 排除（自我修正） | DABT/IABT 仅占 0.04%（开机/console），主导是 WFx（§3.2）。先前结论源于「前 20-30K exit 采样 + awk 正则漏 WFx 小写 x」两个偏差 |
| cmd line / 启动参数 | 非充分 | 既有实验 A/B（[reassessment](CUBESANDBOX_ARM64_MULTIVCPU_ROOT_CAUSE_REASSESSMENT_20260722.md)） |
| memory volume flush / 缺页 | 非充分 | 既有实验 C；且本 trace 显示 CPU1 是 WFI 空转而非访存缺页 |
| guest 侧 timer handler bug | 排除 | 同 guest 在 pass 里正常消费 IRQ27 |
| VMM restore 侧代码（v16/v23 等） | 非修复 | [[cubesandbox-trace-stripped-v26]]：重建 v23（含/不含插桩）都坏；cf25ae12 的 20/20 不可复现 |

---

## 6. 下一步（插桩内核数据采集，待 .90 硬件稳定）

1. 解决 .90 的 `0000:61:00.*` 网卡高温（idle ~119°C > crit 105°C，曾致 GHES fatal @368s，[[cubesandbox-90-nic-thermal-blocker]]）。
2. 一次性启动 first-entry-trace 插桩内核 `…first-entry-trace-v22`（已在 .90 `/boot`，自定义 event `kvm:kvm_arm64_first_entry`(LOAD/PRE_ENTRY/POST_EXIT) + `kvm:kvm_arm64_timer_handler`，读实际 `ICH_HCR/VMCR/MISR/EISR/ELRSR/AP1R0` 与 IRQ27 LR）。
3. 在坏 Template 上 L0→L1（metadata-only，避免 readback 观察效应）采**失败 restore** 的 CPU1 四层 trace：VMM 输入 / KVM LOAD+PRE_ENTRY timer+IRQ27 软件 / **实际 ICH_LR+VMCR+phys_active** / POST_EXIT 消费。
4. 判据（[trace guide §9.2](CUBESANDBOX_ARM64_FIRST_ENTRY_TRACE_GUIDE_20260723.md)）：失败 CPU1 的 PRE_ENTRY 是否「IRQ27 软件pending 但实际 ICH_LR 无 IRQ27 / 仅 active / phys_active 持续」→ 定投递断裂的精确层。
5. 同口径采 3-vCPU 成功对照，回答「为何 2-vCPU 而 3/4-vCPU 不」。

---

## 7. 方法与可复现

- **tracepoint 采集**：`collect` 用独立 tracefs instance（`/sys/kernel/tracing/instances/v26fail`，64MB/CPU，mono 时钟），启用 `kvm_entry/kvm_exit/kvm_timer_emulate/kvm_timer_hrtimer_expire/kvm_timer_update_irq/kvm_timer_save_state/kvm_timer_restore_state/vgic_update_irq_pending`；workload 为 `cube_template_create_rate.py --template-id tpl-d531debb --attempts 12`（community shim，无 VMM 插桩）。
- **PC 符号化**：guest 为 monolithic 内核（无可加载模块），地址是 KASLR'd 内核 text（base≈`0xffffae7ac6a00000`）；用 e2b SDK 建一个健康 sandbox，`/bin/bash -lc "grep -E '^ffffae7ac(6|7)' /proc/kallsyms"` 取 97348 个运行时符号，离线 bisect 解析 PC（kptr_restrict=1，root 可见地址）。
- **教训**：trace 统计必须**全量流式**（非 `head` 截断前若干行，否则只看到开机阶段）；HSR_EC reason 正则要**大小写不敏感**（`WFx` 含小写 x）。

## 附录 A：自我修正记录

- 初版据「前 20-30K exit 的 top-PC + HSR_EC（awk `[A-Z_]+` 漏 `WFx`）」误判为「CPU1 DABT/pl011 内存异常风暴、非 WFI、插桩内核是错工具」。
- 全量流式统计 + 大小写不敏感正则后纠正：99.94% WFx，主导 PC `cpu_do_idle`。详见 `.90:…/FINDINGS.md` 末尾「CORRECTION」段与本仓库 memory `cubesandbox-stock-kernel-dabt-storm`。

---

## 8. 插桩内核 ICH_LR 实测（2026-07-24，对 §4「未决」的证伪）

一次性启动 first-entry-trace-v22 内核（含 vtimer fix + 自定义 `kvm:kvm_arm64_first_entry`(LOAD/PRE_ENTRY/POST_EXIT，读实际 `ICH_LR/VMCR/ELRSR/AP1R0`)），在坏 Template `tpl-d531debb` 上 L0（kernel-only，community shim，无 VMM marker）采 4 次 restore（3 失败 1 成功），采到 1193 条 `kvm_arm64_first_entry`、其中 256 条 phase=1（PRE_ENTRY）vcpu=1（每 attempt 64 条，受「每 vCPU 前 64 次 exit」限流）。

### 8.1 关键结果：IRQ27 确实在实际 ICH_LR 里（fail 与 pass 首帧完全相同）

4 个 vcpu1-PID（3 fail + 1 pass）在**首次 PRE_ENTRY 完全一致**：

| 字段 | 值（4 个 PID 全相同） |
|---|---|
| pstate | `0x814010c5` → **PSTATE.I=1（中断屏蔽）** |
| timer_flags | `0x1f` → should_fire=1、phys_active=1、loaded、line、valid 全置 |
| irq27_flags | `0x61` → valid+enabled+hw-backed（pending 已转 LR） |
| used_lrs | `1` |
| **hw_entry irq27_lr** | **`0:0x70a0001b0000001b`**（IRQ27 在 ICH_LR0，pending） |
| hw_entry pending_lr | `0:0x70a0001b0000001b` |
| PC | `0xffffae7ac722789c`（pl011_write 区——早期 console 阶段） |

`0x70a0001b0000001b` 低 32 位 `0x1b`=27（vINTID=IRQ27），与 matrix §9.1 **成功**样本的 `hw_entry_irq27_lr` 逐位相同。

seq 0–63（限流窗口内）fail 与 pass 也完全相同：`hw_entry irq27_lr` 与 `hw_exit irq27_lr` 都是 `0:0x70a0001b0000001b`（IRQ27 一直 pending 在 LR，未被消费/EOI），PSTATE.I 一直=1。

### 8.2 对 §4「未决」的证伪与再收敛

- **证伪**：§4 假设「失败时 IRQ27 没进 ICH_LR」。实测：失败 CPU1 的 ICH_LR **正确装入了 IRQ27（pending、可投递）**，与成功一致。**vGIC/ICH_LR 投递层不是断裂点。**
- **再收敛**：断裂点在 ICH_LR **下游**——guest **没有消费（take/EOI）这个已正确投递的 IRQ27**。结合 §3.3 的未限流 stock tracepoint：失败 IRQ27 `level0=0`（从不 deassert=从不 EOI）、CPU1 WFx 风暴（cpu_do_idle）；成功 `level0=1587`（消费）。即「投递对了，消费没发生」。
- **限流盲区**：自定义 event 限「每 vCPU 前 64 次 exit」，而前 64 次是 pl011 console 早期阶段（PC=pl011_write，PSTATE.I=1）；真正的 cpu_do_idle/WFI 风暴在 64 次之后，未被自定义 event 捕获。故「guest 为何不消费」的精确机制（PSTATE.I 是否在风暴中持续=1？WFI 是否未被 pending LR 打破？guest resume 路径？）**仍超出现有插桩可见范围**。

### 8.3 修订后的根因边界

| 层 | 状态 |
|---|---|
| VMM restore 输入（timer/vGIC snapshot） | 正确（既有分析） |
| KVM 软件 timer/vGIC（IRQ27 software-pending） | 正确（§3.3） |
| **实际 ICH_LR 投递（IRQ27 进硬件 LR）** | **正确（§8.1，IRQ27 在 ICH_LR0 pending）** |
| guest 消费（take/EOI IRQ27） | **失败：不消费（WFI 风暴、level0=0）；成功：消费** |
| 下游 RCU stall / ttrpc 超时 | 后果 |

**当前最准表述**：故障点不在 KVM/vGIC 的 ICH_LR 投递层（IRQ27 已正确装入硬件 LR），而在 **guest 侧未能消费该已投递中断**——CPU1 卡在 cpu_do_idle/WFI，不 take/EOI IRQ27。精确的 guest 侧机制（PSTATE.I 持续屏蔽 / WFI 未被打破 / guest resume 路径）需把插桩限流从 64 提到更大（或对 WFI 退出路径加无界 kprobe 读 PSTATE/ICH_LR）才能定位。2-vCPU vs 3/4-vCPU 的差异仍待在该层对照。

### 8.4 数据资产
本地：`/tmp/ichlr_trace.txt`（3.6MB）、`/tmp/ichlr_format.txt`、`/tmp/ichlr_results.jsonl`、`/tmp/parse_ichlr*.py`。远端：`.90:/home/lyq/arm64-v26-ichlr-cap-20260724/`（trace.txt + format-* + sdk/results.jsonl + workload.log）。.90 已恢复 stock 内核 + community shim（default=stock，无 crash-loop）。

### 8.5 注：插桩内核在 .90 上因 61:00.* 网卡高温反复 GHES crash（曾 crash-loop）；本次是在 crash 间隙的窗口内完成采集并 scp 出 trace。后续若要采 64-exit 之后的 WFI 风暴态，需先稳定硬件 + 提高限流。

---

## 9. 下一步观测目的：WFI 风暴期的 PSTATE.I（kprobe/eBPF）

### 9.1 为何需要这一帧
§8 已证：ICH_LR 投递层正确（IRQ27 在硬件 LR pending）。断裂在下游「guest 不消费已投递的 IRQ27」。但自定义 event 限流在前 64 次 exit（全是 pl011 console 早期阶段，fail/pass 逐帧相同），真正的 `cpu_do_idle`/WFI 风暴（~1.4M exit）在 64 次之后，**PSTATE.I 在风暴里是 1 还是 0 没有成像**——而这是区分两种根因的决定性量。

### 9.2 二选一判定
在 WFI 退出路径上**无界**读取每次 WFI 的 guest PSTATE.I（及 IRQ27 是否仍在 ICH_LR）：

- **(A) 风暴里 PSTATE.I=1（中断屏蔽）**：WFI 虽被 pending 的 IRQ27 唤醒，但因 PSTATE.I=1 **不 take**该中断 → 不 EOI → 不消费 → 回 idle 再 WFI，死循环。
  → 根因方向 **guest 侧**：snapshot 把 CPU1 恢复成 PSTATE.I=1，guest resume 路径没能 unmask 即 idle 卡死。
- **(B) 风暴里 PSTATE.I=0（中断开）但 WFI 仍不被 pending 的 IRQ27 打破 / 仍不 take**：IRQ27 明明 pending 在 ICH_LR、中断也开，却既不唤醒 WFI 也不被取走。
  → 根因方向 **KVM/EL2 硬件一致性**：pending 的 ICH_LR 没有正确向 WFI / 向 guest CPU interface 呈现。

两者修复方式完全不同（guest resume 路径 vs KVM/EL2 呈现），而现有数据无法区分。读出风暴期 PSTATE.I 即可定性。

### 9.3 实现选择
- 自定义 event 已能读 PSTATE+ICH_LR，只是被「前 64 次 exit」限流。**最干净**是重建插桩内核把限流提到 ~4096（复用已验证的读取逻辑）。
- **不想重建内核时**的替代：用 eBPF/kprobe 在 stock 内核上挂 WFI 退出路径（如 `kvm_handle_wfx`），每次 WFI 读 guest PSTATE（`vcpu->arch.ctxt...pstate`）+ vcpu_id，过滤 vcpu_id==1，统计风暴期 PSTATE.I。优点：无需插桩内核、可在稳定的 stock 内核上跑（避开 61:00.* 高温对插桩内核的 crash-loop）。局限：ICH_LR 属 EL2 寄存器，EL1 kprobe 不能直接读实际硬件 LR（只能读 KVM 软件 vgic pending 作代理）；但判定 A/B 只需 PSTATE.I，ICH_LR 已由 §8 证在前 64 帧正确。

---

## 10. eBPF kprobe 实测：WFI 风暴期 PSTATE.I 全程=1（定性根因）

### 10.1 方法
stock 内核上用 bpftrace kprobe 挂 `kvm_handle_wfx`（WFI/WFE trap handler，arg0=`struct kvm_vcpu*`），按 vcpu_id 聚合每次 WFI 的 guest PSTATE.I（`vcpu->arch.ctxt.regs.pstate` 的 bit7）。在坏 Template `tpl-d531debb` 上跑 4 次 restore（3 fail 1 pass）期间采集。

```
kprobe:kvm_handle_wfx {
  $v=(struct kvm_vcpu*)arg0;
  @wfi_I[$v->vcpu_id, ($v->arch.ctxt.regs.pstate >> 7) & 1] = count();
}
```

### 10.2 结果
```
@wfi_I[0, 1]: 594              # CPU0 WFI 且 PSTATE.I=1（masked）—— 仅 594 次，CPU0 多数在跑
@wfi_I[1, 1]: 18,898,156       # CPU1 WFI 且 PSTATE.I=1（masked）—— 1890 万次，全部
@vcpu1_pstate_sample: 0x614010c5   # bit7=1 → PSTATE.I=1
（无 @wfi_I[1, 0] 项 → CPU1 从未在 PSTATE.I=0 下 WFI）
```

### 10.3 定性：根因是 (A) guest 侧中断屏蔽，不是 (B) KVM/EL2 投递
CPU1 的整个 WFI 风暴（1890 万次）**全程 PSTATE.I=1（中断屏蔽）**。即 guest CPU1 在 `cpu_do_idle` 里 WFI 时**中断是关的**。IRQ27 虽已正确投递进 ICH_LR（§8.1）、pending 可投递，但 guest 因 PSTATE.I=1 **无法 take 该中断** → WFI 虽被 pending 唤醒却不进入 IRQ 异常 → 不 EOI → 不消费 → 回 idle 再 WFI，死循环。

⇒ **§9.2 的 (B)「PSTATE.I=0 但 WFI 不被打破 / KVM/EL2 呈现断裂」被证伪。** KVM/EL2 投递与呈现均正确；断裂在 **guest 侧：CPU1 带着中断屏蔽（PSTATE.I=1）进入 idle/WFI**，无法消费已投递的 timer IRQ27。

### 10.4 根因再收敛（最终）
故障点不在 KVM/vGIC/ICH_LR 任何一层（投递全对），而在 **guest CPU1 的 PSTATE.I=1（中断屏蔽）+ 进入 cpu_do_idle/WFI**：
- snapshot 把 CPU1 恢复成 PSTATE.I=1（§8.1 首帧 pstate=0x814010c5，I=1）。
- restore 后 CPU1 resume 进 `cpu_do_idle`/WFI 时**没重新开中断**（PSTATE.I 保持 1）→ masked-idle 死循环 → 取不到 pending 的 IRQ27 → timer 不推进 → RCU stall → `reset guest time` 超时。
- 成功 attempt：CPU1 没陷入 masked-idle（重新开了中断 / 有工作可做 / 取到了 IRQ27），故正常。

修复方向（待验证）：restore 时强制 CPU1 PSTATE.I=0（VMM/KVM 侧清中断屏蔽位），或在 guest resume 路径保证 idle 前开中断。注意这是 **guest 状态/恢复路径**问题，不是 KVM 内核 bug —— 解释了为何 vtimer fix、cmdline、flush、VMM 重排等都不解决（它们都在错误层）。

### 10.5 仍未定
- 为何 2-vCPU 高发、3/4-vCPU 稳定：需在 3/4-vCPU 上同口径跑 bpftrace，看次级 vCPU 是否也 PSTATE.I=1 masked-idle、或其 resume 路径不同。
- snapshot 为何捕获 CPU1 PSTATE.I=1：是 Template 构建时 CPU1 恰处于 masked 区（idle 前/临界区），还是 guest idle 路径本身在 restore 后未开中断。
- 「成功 attempt 不陷入」的精确差异（开中断的时点）。

### 10.6 资产
bpftrace 脚本 `/tmp/wfi_pstate.bt`、捕获结果 `.90:/home/lyq/arm64-v26-wfi-kprobe-20260724/`（bpftrace.out + sdk/results.jsonl + workload.log）。bpftrace v0.19.1（dnf 安装），BTF 来自 stock 内核 `/sys/kernel/btf/vmlinux`。

---

## 11. 进展总结（2026-07-25 更新）

### 11.1 完整调查链路

```
现象: 2-vCPU snapshot/restore 后 ~75% 失败
  → "reset guest time failed: ttrpc err: Receive packet timeout"
  → guest CPU1 RCU stall + timer softirq 停滞

stock 内核 tracepoint (§3):
  → CPU1 99.94% WFx 退出（cpu_do_idle/WFI 风暴）
  → IRQ27 (timer PPI) 软件 pending（level1=115, level0=0 从不消费）
  → CPU0 健康（同 restore, IRQ27 正常消费）

插桩内核 ICH_LR 实测 (§8):
  → IRQ27 正确在 ICH_LR0 (PENDING, HW-backed, vINTID=27)
  → PMR=0xf0（允许 IRQ27@0xa0）
  → 与成功样本逐位相同 → ICH_LR 投递正确

eBPF kprobe (§10):
  → WFI PSTATE.I=1（正常 cpuidle 行为）

代码分析（§9 修正后的完整链路）:
  → do_idle: local_irq_disable() → cpuidle_idle_call() → WFI
  → exit_idle (idle.c:233): if(irqs_disabled()) local_irq_enable()
  → guest 在 WFI 唤醒后确实重开 IRQ（PSTATE.I=0）
  → 但 IRQ27 仍未被取走 → 根因在 KVM/EL2 GIC 虚拟化投递
```

### 11.2 Guest 侧修复实验

| # | 修复方案 | 验证加载 | 结果 | 判定 |
|---|---|---|---|---|
| 1 | `cpu_do_idle` 内 `raw_local_irq_enable()` | ❌ .vm 被 create-from-image 覆盖 | 无效测试 | ❌ 代码分析: `exit_idle` 已重开 IRQ, 修复多余 + 破坏 boot |
| 2 | `cpu_do_idle` 内 IRQ enable + timer re-arm | ❌ 同上 | 无效测试 | ❌ timer re-arm 破坏 boot (过于激进) |
| 3 | `nohlt` cmdline（Cubelet 修改） | ✅ /proc/cmdline 验证 | 18/20 失败 (90%) | ❌ IRQ27 不投递与 idle 模式无关 |
| 4 | **`maxcpus=1` cmdline（Cubelet 修改）** | ✅ /proc/cmdline + nproc=1 | **20/20 通过 (100%)** | ✅ **修复确认** |

### 11.3 `maxcpus=1` 修复

**机制**: `maxcpus=1` 使 guest 内核只上 CPU0。CPU1 永不 online → 无 timer tick → 不需要 IRQ27 → 绕过 KVM/EL2 投递 bug → 无 RCU stall → agent 正常响应。

**实现**: 修改 Cubelet `cube_container_create.go`，在 `cube.vm.kernel.cmdline.append` 注解中添加 `maxcpus=1`。

**验证**:
- `/proc/cmdline` 包含 `maxcpus=1` ✓
- `nproc` = 1 ✓
- 20 次 restore 全部通过 (`lifecycle_success_rate_pct: 100.0`) ✓
- Template `tpl-aadc79f9b2184f579b948d13` (READY) ✓

**提交**: `baf0f3b0b` (CubeSandbox v25 worktree on .90)

**代价**: guest 只用 1 个 vCPU（牺牲 50% 计算能力）。这是**规避方案（workaround）**，不是根因修复。适合作为 KVM 侧修复前的临时措施。

### 11.4 根因最终边界

| 层 | 状态 | 证据 |
|---|---|---|
| VMM restore 输入 | 正确 | snapshot 分析 |
| KVM 软件 vgic（IRQ27 pending） | 正确 | §3.3 timer_update_irq level1=115 |
| **实际 ICH_LR 投递（IRQ27 进硬件 LR）** | **正确** | §8.1 hw_entry irq27_lr=PENDING |
| **vgic_flush/sync 循环** | **正确** | §9 代码分析: flush 填入 → sync 读出 PENDING → fold 保留 → IRQ27 持续在 LR 中 |
| guest 消费（take/EOI IRQ27） | **失败** | level0=0 从不消费；maxcpus=1（CPU1 offline）后 20/20 通过 |
| 下游 RCU stall / ttrpc 超时 | 后果 | 因 CPU1 timer tick 不运行导致 |

**最窄根因**: 在 `exit_idle` 重开 IRQ（PSTATE.I=0）后，尽管 IRQ27 在 ICH_LR 中 PENDING + PMR 允许 + PSTATE.I=0，**KVM/EL2 GIC 虚拟化硬件未将 pending 的 ICH_LR 呈现给 guest CPU1 的中断信号**。这是 KVM 内核 bug，与 guest 的 idle 模式（WFI vs polling）无关。

### 11.5 .90 当前状态

```text
内核: 6.6.0-132.0.0.111.oe2403sp3.aarch64 (stock)
Cubelet: 已部署 maxcpus=1 修改版 (binary 含 maxcpus)
shim: community 4702fde1
.vm: 原始社区版
API: {"status":"ok","sandboxes":0}
六服务: active
```

### 11.6 关键代码位置（host 内核 /home/lyq/Projects/Micro-VM/kernel）

| 位置 | 作用 |
|---|---|
| `kernel/sched/idle.c:295` | `local_irq_disable()` — WFI 前禁用 IRQ |
| `kernel/sched/idle.c:150-233` | `cpuidle_idle_call()` — WFI + `exit_idle` 重开 IRQ |
| `arch/arm64/kernel/idle.c` | `cpu_do_idle()` — save_irq_context + WFI + restore |
| `arch/arm64/include/asm/cpuidle.h:15-34` | `arm_cpuidle_save/restore_irq_context` — PMR/DAIF 管理 |
| `arch/arm64/kvm/vgic/vgic.c:1020` | `kvm_vgic_flush_hwstate` — 从 ap_list 填入 ICH_LR |
| `arch/arm64/kvm/vgic/vgic.c:965` | `kvm_vgic_sync_hwstate` — 读硬件 ICH_LR → fold → prune |
| `arch/arm64/kvm/vgic/vgic-v3.c:38` | `vgic_v3_fold_lr_state` — LR 状态折叠回软件 irq |
| `arch/arm64/kvm/hyp/vgic-v3-sr.c:204` | `__vgic_v3_save_state` — 读 ICH_LR + 清零硬件 LR + ELRSR 判断 |
| `arch/arm64/kvm/arch_timer.c:615` | `kvm_timer_update_irq` — timer IRQ level 注入 |

### 11.7 Guest 内核源码与实验产物

- Guest 内核源码: `.90:/home/lyq/OpenCloudOS-Kernel-6.6.119` (tag 6.6.119-49.6)
- CubeSandbox 源码: `.90:/home/lyq/CubeSandbox-v0.5.1-arm64-state-log-only-v25` (community a164417f)
- 插桩内核: `.90:/boot/vmlinuz-…first-entry-trace-v22` (自定义 event, 64-exit 限流)
- bpftrace v0.19.1 已安装

### 11.8 下一步方向

1. **KVM 侧根因修复**（推荐）: 提高插桩内核的 64-exit 限流到 ≥4096，在 `exit_idle` 重开 IRQ 后的那个 entry 观察实际 ICH_LR 是否被硬件呈现给 guest。然后修复 `arch/arm64/kvm/vgic/` 或 `hyp/vgic-v3-sr.c` 中的投递呈现 bug。

2. **`isolcpus=1` + `rcu_nocbs=1`** (Guest 侧, 保留 CPU1 online): 尝试不牺牲 CPU 的方案——CPU1 保持 online 但不调度用户任务，可能避免 RCU stall（但 KVM/EL2 投递问题仍可能在 kernel thread 上触发）。

3. **保留 `maxcpus=1` 作为临时方案**: 在 KVM 侧修复完成前，确保 sandbox 可用（牺牲性能换取正确性）。

### 11.9 提交记录

| 仓库 | Commit | 内容 |
|---|---|---|
| CubeSandbox v25 worktree | `baf0703b0b` | **maxcpus=1 修复（确认有效, 20/20 通过）** |
| CubeSandbox v25 worktree | `31a36195f` | nohlt 实验（负面结果, 18/20 失败） |
| OpenCloudOS-Kernel | `e6a58e090` | IRQ-enable 实验（负面结果, 修复位置错误） |
| OpenCloudOS-Kernel | `26d065591` | IRQ enable + timer re-arm 实验（负面结果, 破坏 boot） |

---

## 12. 社区基线 + 条件触发 eBPF 复核（2026-07-25）

> 本节修订 §11.4 的结论强度：现有证据支持「问题在 KVM/guest IRQ 恢复边界」，但**尚不足以确认通用 KVM/EL2 bug**，更不能确认是 timer-only 故障。

### 12.1 基线与样本

- .90 已从 `maxcpus=1` Cubelet 重置为社区提交 `a164417f497234a0d787cb328b0ae96480b1569b` 的干净源码重建版；运行 cmdline 不含 `nohlt`/`maxcpus=1`。
- 其余 8 个 host 二进制哈希和 lifecycle-manager/proxy 镜像 ID 与社区 provenance 一致。
- stock host kernel 保持 `6.6.0-132.0.0.111.oe2403sp3.aarch64`，未改 KVM 源码。
- 三轮共 11 次串行 restore：5 pass、6 fail；6 个 fail 全是 `reset guest time failed`。
- pass 的 CPU1 WFI 总数仅 68/77/89（另两次也未达 10,000）；fail 均超过 10,000 并触发 256-exit 窗口。

完整资产与逐次日志见：
[arm64-ebpf-wfi-lr-community-baseline-20260725-161653](remote-results/arm64-ebpf-wfi-lr-community-baseline-20260725-161653/README.md)。

### 12.2 eBPF 观测结果

条件：同一 KVM 线程的 vCPU1 达到第 10,000 次 WFI 后，采集后续 256 次 KVM exit。5 个故障窗口均完整，单窗口仅 1.23–1.45 ms（约 17.7–20.8 万 WFI/s）。

每个故障窗口都满足：

- WFI PC=`0xffffae7ac7660730`，PSTATE.I=1；所有 WFI exit 都是 `TRAP/WFx`。
- `used_lrs=4`、`ICH_HCR=0x1`、保存后的 `VMCR=0xf04c000a` 固定不变。
- LR0 固定为 `0x70a0001b0000001b`：IRQ27、pINTID=27、priority=0xa0、Group1、HW-backed、PENDING、非 ACTIVE。
- 不只是 IRQ27：另外 3 个 Group1 pending LR（vINTID=`0x2015`、`0x201a`、`0x1`）也始终不被消费，只是 slot 顺序偶有变化。
- vtimer 始终 `loaded=1, level=1`；IRQ27 为 enabled/HW-mapped（`hwintid=27`, host IRQ 11）。直接硬件映射下 `line_level/pending_latch/active=0` 与 pending HW LR 不矛盾。
- 4 个增强故障样本分别运行在 host CPU 101/302/190/205，窗口内不迁移；不支持「单个坏 pCPU」假设。

### 12.3 WFI PC 推进假设已证伪

第三版探针读取 `vcpu->arch.iflags`：

- 255/255 次 `kvm_handle_wfx` 返回时 `iflags=0x2`，即 `INCREMENT_PC=1`。
- 进入 hyp 后该标志被清除，说明 deferred PC increment 被应用。
- 窗口内实际捕获过一次 PC=`WFI_PC+4`，之后 guest 再回到 WFI PC。

因此普通 `kvm_entry` event 反复打印 WFI PC **不是** KVM 没加 PC；该 event 位于 hyp 应用 deferred increment 之前。后续不得再把这一现象当作 WFI handler bug 证据。

### 12.4 对当前结论的质疑

1. **不是 timer-only。** 四个 Group1 pending LR 都不被消费，更像 CPU1 的整体 IRQ acceptance/resume 状态停滞。
2. **PSTATE.I=1 不是根因证明。** arm64 Linux idle 在 WFI 时屏蔽 IRQ 是正常行为；必须观测 WFI 之后的 unmask 和 IRQ vector，而不是仅采 WFI 点。
3. **fold LR 不是 live EL2 呈现证明。** `vgic_v3_fold_lr_state` 入口能看到刚从硬件保存的 LR，但 stock nVHE eBPF 不能读取 entry 瞬间 live `ICH_MISR/EISR/ELRSR/AP1R0`，也看不到 guest 是否进入 IRQ vector。
4. **`maxcpus=1` 只证明 CPU1 是必要条件。** 它绕过 CPU1 timer/IRQ/RCU 路径，但不能区分 guest snapshot 状态、KVM restore 顺序和 GIC 硬件呈现。
5. **pass/fail 尚未在同一语义起点对齐。** 当前 storm trigger 精确描述终态，却没有捕捉「第一次 IRQ27 拉高到进入风暴」之间的分叉。

所以 §11.4 的「最窄根因是 KVM/EL2 未呈现 ICH_LR」应降级为**待证假设**。当前最窄且可辩护的边界是：

> 2-vCPU snapshot restore 后，CPU1 反复完成 KVM WFI trap/PC 推进，但 guest 不消费任何已 pending 的 Group1 LR；故障位于 snapshot CPU/GIC 状态、KVM/GIC restore 顺序、guest IRQ unmask/vector 三者的交界处。

### 12.5 下一步（按信息增益排序）

1. eBPF trigger 前移到 restore 后第一次 `IRQ27 level=1` 或第一次 flush 出现 pending IRQ27；pass/fail 都采同样长度，并增加 `timer_get_ctl/cval`、`kvm_timer_vcpu_load/put`、`kvm_arch_timer_handler`、`set_timer_irq_phys_active`。
2. guest 侧做可持久化最小 trace：`cpu_do_idle` 返回、DAIF unmask、IRQ vector entry、arch timer handler。先回答 CPU1 是否执行 unmask、是否进入任何 Group1 IRQ vector。
3. 审计 snapshot/restore 的 CPU1 `PSTATE/DAIF`、`ICC_PMR_EL1`、`ICC_IGRPEN1_EL1`、APR、`CNTV_CTL/CVAL`、redistributor 状态及其首次 vCPU entry 前的顺序。
4. 用最小 2-vCPU KVM snapshot selftest 复现；若可复现，再把问题从 CubeSandbox/guest 负载中剥离出来。
5. 只有前述状态仍全部正确时，再加小型 condition-triggered hyp trace 读 live ICH sysreg。这个缺口无法由 stock nVHE eBPF 补齐。

不建议把旧 trace 的 64 限流机械提高到 4096：条件触发 eBPF 已能稳定到达故障窗口，当前缺口是**分叉前状态和 guest/live-EL2 可见性**，不是采样长度。

### 12.6 .90 当前状态（本轮结束）

```text
kernel: 6.6.0-132.0.0.111.oe2403sp3.aarch64 (stock)
Cubelet: community source-clean rebuild, sha256=88e5e224fdfb9b1fca5d4722cfa273c49aa7048dffdb28fb88adbc44ddee4c96
API: {"status":"ok","sandboxes":0}
shim count: 0
task dir count: 0
Cubelet service: active
```
