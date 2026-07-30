# CubeSandbox ARM64 首次 KVM entry trace 设计、操作与实测说明

> 文档日期：2026-07-23  
> 证据截止：2026-07-22 21:01 +08:00  
> 适用问题：ARM64 2-vCPU Template restore 后 CPU1 中断不前进、RCU stall、agent/ttrpc 超时  
> 状态：KVM 与 VMM 插桩、构建、内核切换及 kernel-only 实测已完成；故障态 metadata/readback 对照受远端硬件高温中断

## 1. 结论摘要

本轮已经直接修改 KVM/arm64、重新编译完整 openEuler 内核，并在 `.90` 上两次切换到诊断内核。

当前看到 stock 内核，不代表没有切换。诊断内核采用一次性 GRUB 启动，重启后自动回落 stock。

新增 trace 不是单点 `printk`。它同时覆盖 VMM restore 输入、KVM vCPU load、timer 状态、vGIC 软件 IRQ27、真实 ICH LR、guest entry/exit 和 timer handler 前后状态。

第一轮诊断内核上完成 5 次和 20 次串行生命周期采集，结果均全通过。共得到 445,819 条 trace event，per-CPU 统计中 `overrun=0`、`commit overrun=0`。

扩展到 50 次时写出 49 个成功结果，随后宿主发生 kdump。vmcore 明确显示根因为 Mellanox 网卡高温导致 PCIe root-port GHES fatal，不是 KVM、RCU 或 guest timer panic。

第二次切入诊断内核时，网卡温度快速达到 108-110°C。为避免再次把硬件崩溃混入 KVM 实验，未运行 workload，仅生成自定义 trace metadata 后主动重启回 stock。

因此，当前已有可信的成功边界样本，但尚未捕获问题本身的失败边界。不能用本轮 25/25 成功声称问题已修复，也不能把被 GHES 截断的第 50 次记为 KVM 失败。

## 2. 为什么必须修改 KVM

用户态 VMM 只能看到写给 KVM 的 snapshot 状态和 ioctl 结果。过去的日志最多证明“软件认为 IRQ pending”，无法证明进入 guest 前实际硬件 ICH LR 中存在什么。

本问题的关键边界位于：

```text
VMM restore input
  -> KVM_SET_ONE_REG / VGIC device restore
  -> vcpu_load
  -> timer load/restore
  -> kvm_vgic_flush_hwstate
  -> ICH_LR<n>_EL2 写入
  -> __kvm_vcpu_run
  -> kvm_vgic_sync_hwstate
  -> timer sync/handler
```

只有 KVM EL1 与 hyp/EL2 代码能在同一 entry generation 中取得实际 `ICH_HCR_EL2`、`ICH_VMCR_EL2`、`ICH_ELRSR_EL2`、`ICH_AP1R0_EL2` 和 `ICH_LR<n>_EL2`。

因此，本轮不是只改 VMM。已在 openEuler KVM 源码加入 tracepoint，完整编译 `Image + modules`，安装 initramfs 和 GRUB 条目，并实际启动该内核测试。

没有直接加入“修复性”状态重写，是因为 v16 的额外 GET/log 已显示观察效应。若一开始改变 pending、active 或 timer 顺序，可能只是掩盖竞态，无法确定原始分歧发生在哪一层。

## 3. 插桩总体设计

插桩分为三个扰动等级：

| 等级 | KVM trace | VMM metadata | 额外 KVM GET | 用途 |
| --- | --- | --- | --- | --- |
| L0 | 开 | 关 | 无 | 先验证真实 entry、ICH LR 与采集链 |
| L1 | 开 | 开 | 无 | 关联 VMM 输入与 KVM 激活，不重复 v16 readback |
| L2 | 开 | 开 | 有 | 对照 GET readback 是否改变故障概率 |

默认状态下，两个 KVM event 和两个 VMM 门控文件均关闭。未启动采集时，VMM restore 语义不变，KVM 不执行新增的 ICH/timer 状态读取。

每个 vCPU 只跟踪前 64 次 guest exit。该限制用于覆盖首次 entry 窗口，同时避免 WFx storm 或长期运行把最初状态挤出 ring buffer。

## 4. KVM/arm64 新增 trace

### 4.1 工作树与改动范围

- 工作树：`source_code/openEuler-kvm-first-entry-trace-v22`
- 分支：`experiment/kvm-arm64-first-entry-trace-v22`
- 源码基线：openEuler 24.03 LTS-SP3，`1cefaec0de17...`
- 改动：8 个文件，新增约 549 行，删除 3 行

主要文件：

| 文件 | 作用 |
| --- | --- |
| `arch/arm64/kvm/arm.c` | LOAD、PRE_ENTRY、POST_EXIT 边界和 load generation |
| `arch/arm64/kvm/arch_timer.c` | 软件/live timer 与 handler 前后状态 |
| `arch/arm64/kvm/vgic/vgic.c` | PPI 27 软件 IRQ 状态与 trace capture 门禁 |
| `arch/arm64/kvm/hyp/vgic-v3-sr.c` | 真实 ICH 寄存器和 LR 的 entry/exit 快照 |
| `arch/arm64/kvm/hyp/nvhe/hyp-main.c` | nVHE hyp 状态回传 host vCPU |
| `arch/arm64/kvm/trace_arm.h` | 两个 trace event 的字段与打印格式 |
| `include/kvm/arm_arch_timer.h` | timer trace state 结构 |
| `include/kvm/arm_vgic.h` | IRQ、ICH 和 generation trace state 结构 |

### 4.2 `kvm_arm64_first_entry`

新增 event：

```text
kvm:kvm_arm64_first_entry
```

它包含三个 phase：

| 数值 | 名称 | 采集位置 | 含义 |
| ---: | --- | --- | --- |
| 0 | LOAD | `kvm_arch_vcpu_load()` 后 | 包含 paused/immediate-exit load |
| 1 | PRE_ENTRY | vGIC flush 后、真实 hyp entry 前 | 即将交给 guest 的最终状态 |
| 2 | POST_EXIT | hyp 返回、vGIC sync 后 | 判断 entry 后状态变化 |

`LOAD` 和真实 entry 必须分开。恢复线程启动时可能先因 `immediate_exit=1` 只做 load/put，没有真正运行 guest。

`load_gen` 每次 vCPU load 递增。`prev_cpu` 记录上一 generation 的宿主 CPU，用来识别 restore 窗口内的 host CPU 迁移。

### 4.3 timer 字段

主要字段：

| 字段 | 含义 |
| --- | --- |
| `timer_sw_ctl/cval` | KVM 软件保存的 CNTV_CTL/CVAL |
| `timer_live_ctl/cval` | 当前宿主 CPU 上的 live timer 状态 |
| `timer_cnt` | 当前 virtual counter |
| `timer_delta` | `CVAL - counter`，小于等于 0 表示已到期 |
| `timer_host_irq` | 对应宿主物理 timer IRQ |
| `timer_flags` | loaded、line、should_fire、phys_active、valid 位图 |

`timer_flags` 位定义：

| bit | 含义 |
| ---: | --- |
| 0 | timer context 已 load |
| 1 | KVM timer IRQ line level |
| 2 | `kvm_timer_should_fire()` 为真 |
| 3 | 宿主物理 timer IRQ active |
| 4 | phys_active 读取有效 |

### 4.4 IRQ27 软件状态

`irq27_flags` 位定义：

| bit | 含义 |
| ---: | --- |
| 0 | 状态有效 |
| 1 | line level |
| 2 | pending latch |
| 3 | 聚合 pending |
| 4 | active |
| 5 | enabled |
| 6 | hardware-backed IRQ |

同时记录 priority、group、config、host IRQ，以及软件生成的 IRQ27 LR 和第一个 pending LR。

### 4.5 实际 ICH 状态

hyp 在 entry 写入和 exit 读回 ICH 状态时采集：

- `ICH_HCR_EL2`
- `ICH_VMCR_EL2`
- `ICH_MISR_EL2`
- `ICH_EISR_EL2`
- `ICH_ELRSR_EL2`
- `ICH_AP1R0_EL2`
- IRQ27 对应 LR 的 index/raw value
- 第一个 pending LR 的 index/raw value

trace 文本中的 `hw_entry` 和 `hw_exit` 是压缩 tuple：

```text
valid,hcr,vmcr,misr,eisr,elrsr,ap1r0,irq27_index:irq27_lr,pending_index:pending_lr
```

这部分解决了旧 trace 的核心缺口：软件 vGIC pending 不再被等同于“已经写入实际 ICH LR”。

### 4.6 `kvm_arm64_timer_handler`

新增 event：

```text
kvm:kvm_arm64_timer_handler
```

它在物理 timer handler 内同时记录 before/after：CTL、CVAL、counter、delta、line、phys_active 和 `should_fire`。

目标是验证下列转换是否完成：

```text
should_fire=1
  -> kvm_timer_update_irq(level=1)

should_fire=0
  -> set_timer_irq_phys_active(false)
```

本轮成功样本中该 event 为 0，不代表插桩失效。恢复时 timer 已过期，IRQ27 在 entry flush 中直接进入 LR，没有等待新的物理 timer handler。

## 5. VMM 新增日志

### 5.1 工作树与改动范围

- 工作树：`source_code/CubeSandbox-v0.5.1-arm64-first-entry-trace-v22`
- 分支：`experiment/arm64-first-entry-trace-v22`
- 基线：CubeSandbox v0.5.1，`a164417f...`
- 改动：6 个文件，新增约 572 行，删除 3 行

主要文件：

| 文件 | 作用 |
| --- | --- |
| `hypervisor/hypervisor/src/kvm/mod.rs` | CPU/timer SET 输入、阶段耗时和可选 GET readback |
| `hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs` | VGIC restore 前后状态和可选 readback |
| `gic/redist_regs.rs` | 解码 GICR PPI 27 |
| `gic/icc_regs.rs` | 解码 ICC PMR/BPR/IGRPEN/AP 状态 |
| `hypervisor/vmm/src/cpu.rs` | snapshot 输入、vCPU thread ready、resume release |
| `hypervisor/vmm/src/vm.rs` | VM restore/resume 总阶段时间线 |

所有日志统一使用：

```text
ARM64_FIRST_ENTRY event=<name> ...
```

### 5.2 门控文件

| 文件 | 行为 |
| --- | --- |
| `/tmp/cube_arm64_first_entry_trace_enable` | 只输出已有 snapshot/阶段 metadata |
| `/tmp/cube_arm64_first_entry_readback_enable` | metadata 加诊断 GET readback |

metadata 模式不新增 `GET_ONE_REG`。readback 模式会读取 timer 和 VGIC 状态，专门用于验证 v16 型观察效应。

### 5.3 主要事件

| 事件 | 说明 |
| --- | --- |
| `vmm_restore_input` | CPU snapshot 的 PC、PSTATE、MP state、timer 输入 |
| `kvm_set_state_begin` | KVM SET 前的最终输入 |
| `kvm_sysregs_set_complete` | system register SET 完成 |
| `kvm_timer_readback` | 仅 readback 模式出现 |
| `kvm_set_state_complete` | 单 vCPU state restore 完成 |
| `vgic_state` | snapshot 或 KVM readback 的 PPI27/ICC 解码 |
| `vgic_restore_complete` | VGIC restore 总耗时和 readback 标志 |
| `vcpu_threads_ready` | restored vCPU 线程已创建但仍 paused |
| `vcpu_resume_release_begin/complete` | resume 释放边界 |
| `cpu_manager_restore_begin/complete` | CPU manager restore 总边界 |

## 6. 采集脚本

脚本：`scripts/collect_arm64_first_entry_trace.sh`

### 6.1 安全门禁

脚本要求 root，并检查两个新增 KVM event 必须存在。若当前 `tracing_on != 0`，脚本拒绝运行，避免覆盖其他人的 active trace 会话。

开始前保存所有 event 状态、`tracing_on` 和 VMM 门控文件。无论 workload 成功、失败或收到信号，trap 都会恢复原状态。

输出目录必须为空。该限制避免把不同批次的 trace、dmesg 和服务日志混在一起。

### 6.2 自动启用的 event

必选：

```text
kvm/kvm_arm64_first_entry
kvm/kvm_arm64_timer_handler
```

若内核提供，则同时启用：

```text
kvm/kvm_timer_update_irq
kvm/kvm_timer_restore_state
kvm/vgic_update_irq_pending
```

没有启用无界的 `kvm_wfx_arm64`。故障时 WFx 可能形成 storm，持续写 ring buffer 会覆盖真正需要保留的首次 entry。

### 6.3 自动收集内容

| 文件/目录 | 内容 |
| --- | --- |
| `environment.txt` | 内核、cmdline、trace clock、buffer 和 workload |
| `enabled-events.txt` | 本次实际启用的 event |
| `formats/` | event format，保证字段可离线解析 |
| `kernel-trace.txt` | 完整 trace 文本 |
| `per_cpu/*.stats` | entries、overrun、commit overrun、bytes |
| `dmesg.before/after.txt` | workload 前后内核日志 |
| `logs/` | VMM、Shim、Cubelet 日志增量 |
| `workload.log` | SDK 串行测试输出 |
| `result.txt` | 返回码、时间和采集时长 |

服务日志使用 inode 和 byte offset 截取增量。若发生 rotate 或 truncate，则复制新文件并标记 `rotated_or_truncated`。

trace 起止通过 `trace_marker` 写入 wall-clock 纳秒和 workload 返回码，便于和 VMM 文本日志对齐。

## 7. 构建、安装与内核切换

### 7.1 构建产物

诊断内核 release：

```text
6.6.0-132.0.0.111.oe2403sp3.aarch64-first-entry-trace-v22
```

内核 Build ID：

```text
570a0c165dc58b289b6e8f5e007e85a8b27c7ca0
```

核心制品 SHA256：

| 制品 | SHA256 |
| --- | --- |
| `vmlinuz-*` | `e8c000a22e6b1caf...` |
| `System.map-*` | `39dad1d782841b96...` |
| `config-*` | `7abb6854ad728b12...` |
| `modules-*.tar.zst` | `e9d95b93acdcd032...` |

VMM Shim：

```text
containerd-shim-cube-rs v0.5.1-arm64-first-entry-trace-v22
SHA256 c57d617f4fe017ac0ce068565d07dddfed0792ba0e124f9f1a913f90a1675c37
```

完整 host config 的 `Image + modules`、nVHE `kvm_nvhe.o` 和 VMM ARM64 release 构建均成功。内核包在远端安装前逐项通过 SHA256 校验。

### 7.2 安装动作

远端安装包含：

```text
/lib/modules/<release>
/boot/vmlinuz-<release>
/boot/System.map-<release>
/boot/config-<release>
/boot/initramfs-<release>.img
```

随后使用 `grubby --add-kernel` 添加条目。每次都重新执行 `grubby --set-default <stock-vmlinuz>`，确保 stock 是持久默认。

### 7.3 为什么使用一次性启动

诊断内核通过：

```bash
grub2-reboot 0
systemctl reboot
```

只安排下一次启动进入条目 0。`saved_entry` 始终是 stock，`next_entry` 在成功启动后清空。

这样即使诊断内核、trace 或无关硬件故障触发 kdump，下一次自动启动也会回到 stock。第一次 GHES fatal 后正是按此策略回退。

## 8. 标准操作流程

### 8.1 前置检查

```bash
uname -r
systemctl is-active cube-sandbox-cubelet.service
systemctl is-active cube-sandbox-cubemaster.service
curl -fsS http://127.0.0.1:3000/sandboxes
ps -eo pid,args | grep -E '[c]ontainerd-shim-cube|[c]ube-vmm'
cat /sys/kernel/tracing/current_tracer
cat /sys/kernel/tracing/tracing_on
wc -l /sys/kernel/tracing/set_event
grubby --default-kernel
grub2-editenv list
```

必须确认 sandbox 为空、无 Shim/VMM、tracefs 无使用者、stock 仍是持久默认。

硬件门禁不能只看 ACPI thermal zone。必须同时读取 `/sys/class/hwmon/hwmon*/temp*_input`，因为本次 Mellanox 105-110°C 没有体现在 65-72°C 的普通 thermal zone 中。

### 8.2 将 tracefs 置为采集可用状态

只有在 `current_tracer=nop`、`set_event` 为空、无 trace reader 时，才执行：

```bash
printf '0\n' >/sys/kernel/tracing/tracing_on
```

采集器会拒绝 `tracing_on=1`。这是保护现有 trace 会话的设计，不应通过修改脚本绕过。

### 8.3 L0 kernel-only

```bash
collect_arm64_first_entry_trace.sh OUTPUT_DIR -- \
  /home/lyq/cube-bench-sdk-venv/bin/python \
  cube_template_create_rate.py \
  --api-url http://127.0.0.1:3000 \
  --template-id tpl-592352ea663648e486962db3 \
  --attempts 20 \
  --sandbox-timeout 300 \
  --command-timeout 30 \
  --cubemaster-cli /usr/local/services/cubetoolbox/CubeMaster/bin/cubemastercli \
  --cubemaster-port 8089 \
  --guest-probe-port 49999 \
  --guest-probe-path /health \
  --results-dir OUTPUT_DIR/sdk
```

### 8.4 L1 metadata-only

在 L0 基础上增加：

```bash
--vmm-metadata
```

采集器会创建 `/tmp/cube_arm64_first_entry_trace_enable`，结束后删除。该模式不创建 readback 门控文件。

### 8.5 L2 readback

使用：

```bash
--vmm-readback
```

采集器会同时创建 metadata 和 readback 门控文件。该组必须在相同 Template、样本数和宿主健康条件下与 L1 对照。

## 9. 字段判读方法

### 9.1 正常边界

成功样本中，CPU1 通常先出现一次 paused/immediate-exit LOAD，再出现真实运行 generation：

```text
LOAD gen=1
  -> LOAD gen=2
  -> PRE_ENTRY gen=2
  -> POST_EXIT gen=2
```

本轮代表性 CPU1 在 PRE_ENTRY 时：

```text
timer_delta < 0
timer_flags = 0x1f
irq27_flags = 0x61
used_lrs = 1
hw_entry_irq27_lr = 0x70a0001b0000001b
```

这说明 timer 已过期，KVM 软件 IRQ 已在 flush 中物化为真实 ICH LR27。`irq27_flags=0x61` 本身不表示丢失，因为 pending 已从软件队列转移到 LR。

CPU0 的成功样本常有两个 LR：一个是 IRQ8，另一个是 IRQ27。CPU1 通常只有 IRQ27。

### 9.2 高优先级异常组合

| 组合 | 初步落点 |
| --- | --- |
| snapshot timer 与 LOAD live timer 不同 | VMM SET 或 KVM load 激活 |
| `should_fire=1` 且 PRE_ENTRY 无软件 pending、无 LR27 | timer 到 vGIC 链断裂 |
| 软件 IRQ27 pending，但实际 ICH 无 LR27 | vGIC flush/LR 生成 |
| LR27 仅 active、phys_active 持续，pending 被抑制 | active-stuck 假设增强 |
| LR27 pending、ICC gate 正常，但多次 POST_EXIT 无进展 | guest mask/exception/消费路径 |
| 只在 `prev_cpu != cpu` 后异常 | per-CPU timer/GIC load-put 路径 |

单条 PRE_ENTRY 不能证明 guest 已消费中断。必须结合连续 POST_EXIT、LR state、AP1R0、PC/PSTATE 和最终 guest health 判断。

## 10. 远端实测结果

### 10.1 第一次诊断启动

节点 `.90` 成功启动：

```text
6.6.0-132.0.0.111.oe2403sp3.aarch64-first-entry-trace-v22
```

两个新增 event 均存在。Cubelet/CubeMaster 正常，tracefs 为 `nop`，无活动 sandbox。

当时 VMM trace-v22 release 构建仍在最终 LTO 链接，因此先使用原 community v0.5.1 Shim 做 L0 kernel-only 验证。

### 10.2 完整采集批次

| 批次 | 生命周期 | first-entry | timer update | timer restore | VGIC pending | overrun |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| smoke-5 | 5/5 | 1,307 | 29,178 | 29,076 | 29,354 | 0 |
| serial-20 | 20/20 | 5,173 | 117,152 | 116,720 | 117,855 | 0 |

smoke-5 共 88,917 条 event、3,140,904 bytes。serial-20 共 356,902 条 event、12,586,028 bytes。

两组 dmesg 前后均没有新增 KVM、RCU stall、watchdog 或 GHES fatal 签名。

25 次全部成功在历史约 4% 失败率下仍有约 36% 的“恰好未命中”概率。因此它只证明插桩和成功路径可工作，不证明问题消失。

### 10.3 50 次批次与 kdump

50 次批次的 `results.jsonl` 完整写到 attempt 49，前 49 次均成功。attempt 50 未形成结果行，collector 也未执行结束落盘。

vmcore-dmesg 的时间线：

| 内核时间 | 事件 |
| ---: | --- |
| 76.799 s | `61:00.0/1` 报高温告警 |
| 267.5 s | mlx5 health 报 High temperature，severity ERROR |
| 367.884 s | GHES 报 PCIe fatal |
| 367.950 s | root port `0000:60:00.0` |
| 368.020 s | `Kernel panic: GHES Fatal hardware error` |
| 368.149 s | 启动 crashdump kernel |

该 panic 栈为 `__ghes_panic -> ghes_proc -> ghes_notify_hed`，没有 KVM、RCU 或 timer 调用链。

因此，该批只能记为“49 次成功后被独立硬件故障截断”，不能记成 49/50，也不能用于计算 KVM 失败率。

### 10.4 vmcore trace 保全

已使用与 vmcore 精确匹配的 vmlinux 和官方 `crash-trace-command` 从 vmcore 导出：

- 384 个 per-CPU `trace_pipe_raw`
- raw ring 总量约 33 MiB
- 带 event metadata 的目录约 51 MiB
- 带 kallsyms 的目录约 56 MiB
- `partial-trace-v22.dat`，约 8.7 MiB

`trace.so` 的 `trace dump -t` 和 `trace show` 在该 384-CPU vmcore 上发生用户态段错误，但 `trace dump -sm` 成功导出 raw ring。原 vmcore 未被修改。

统一 `trace.dat` 的 restore/report 尚未完成。即使恢复成功，该批仍受 PCIe fatal 截断，只能用于确认 panic 前 entry 状态，不能充当目标 KVM 失败样本。

### 10.5 VMM 部署与第二次诊断启动

trace-v22 Shim 构建完成后已上传并校验。原 community Shim 备份 SHA 为：

```text
c3d9bd094a8fc9d86b4b06a684ee574f8f8e023479c1f4088b8597c2a6c03d46
```

trace-v22 Shim 安装 SHA 为：

```text
c57d617f4fe017ac0ce068565d07dddfed0792ba0e124f9f1a913f90a1675c37
```

第二次诊断内核成功启动，但 hwmon 很快显示 Mellanox 108-110°C。系统尚未 panic 时主动停止实验，并 orderly reboot 回 stock。

本次没有执行 L1 metadata 或 L2 readback workload。不能把“VMM 已部署”写成“VMM 插桩已完成远端数据验证”。

## 11. 当前边界与后续实验

### 11.1 必须先处理硬件

在 `.90` 上恢复正式实验前，至少应完成：

- 检查 ConnectX-6 Dx 散热、风道、风扇和插槽供电
- 检查 `60:00.0 -> 61:00.*` 链路和 PCIe root port
- 检查 mlx5 firmware internal error `ext_synd 0x8a02`
- 确认 NIC hwmon 在空闲和测试期间低于硬件告警阈值
- 连续运行超过历史 368 秒窗口而无 GHES fatal

仅看 CPU/ACPI 温度不足以放行测试。

### 11.2 硬件恢复后的固定顺序

| 顺序 | 模式 | 样本 | 通过条件 |
| ---: | --- | ---: | --- |
| 1 | L0 kernel-only | 5 | event、日志、overrun 和硬件健康正常 |
| 2 | L1 metadata-only | 20 | 无 GET readback；命中失败则立即停 |
| 3 | L1 扩样 | 50 | 仅在硬件持续健康时执行 |
| 4 | L2 readback | 与 L1 相同 | 和 L1 做观察效应对照 |

若 L1 命中失败，应先关联同一 sandbox、VMM PID、vCPU、load generation 和 host CPU，不要继续批量压测覆盖 ring。

### 11.3 最终根因门槛

只有同一失败 CPU1 同时取得以下四层证据，才能闭环：

1. VMM snapshot/SET 输入
2. KVM LOAD 与 PRE_ENTRY timer/IRQ27 软件状态
3. 实际 ICH LR、CPU interface 和 phys_active
4. POST_EXIT、handler 或 guest health 的消费结果

当前判断仍是：故障点位于 CPU1 restore 后首次真实 KVM entry 的中断物化/消费边界。精确责任尚不能在 VMM 状态、KVM timer、vGIC LR 和 host per-CPU 激活之间唯一确定。

## 12. 证据与源码索引

### 12.1 本地结果

- `remote-results/arm64-first-entry-trace-v22-20260722-1927/remote/results/kernel-only-community-smoke-5/`
- `remote-results/arm64-first-entry-trace-v22-20260722-1927/remote/results/kernel-only-community-20/`
- `remote-results/arm64-first-entry-trace-v22-20260722-1927/remote/results/kernel-only-community-50/crash/vmcore-dmesg.txt`

### 12.2 远端结果

```text
/home/lyq/cube-arm64-first-entry-trace-v22-20260722-1927/
  artifacts/
  backup/
  results/
  tools/
```

### 12.3 关键源码位置

- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/arm.c:712`
- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/arm.c:825`
- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/arm.c:1381`
- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/trace_arm.h:16`
- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/trace_arm.h:87`
- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/trace_arm.h:239`
- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/arch_timer.c:348`
- `source_code/openEuler-kvm-first-entry-trace-v22/arch/arm64/kvm/hyp/vgic-v3-sr.c:303`
- `source_code/CubeSandbox-v0.5.1-arm64-first-entry-trace-v22/hypervisor/hypervisor/src/kvm/mod.rs:2204`
- `source_code/CubeSandbox-v0.5.1-arm64-first-entry-trace-v22/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs:27`
- `source_code/CubeSandbox-v0.5.1-arm64-first-entry-trace-v22/hypervisor/vmm/src/cpu.rs:2213`
- `source_code/CubeSandbox-v0.5.1-arm64-first-entry-trace-v22/hypervisor/vmm/src/vm.rs:2643`
- `scripts/collect_arm64_first_entry_trace.sh:85`
- `scripts/collect_arm64_first_entry_trace.sh:103`
- `scripts/collect_arm64_first_entry_trace.sh:247`

## 13. 最终说明

本轮已经完成“修改 KVM、重新编译内核、切换内核、远端运行和抓取成功态日志”。当前缺少的不是 KVM 修改，而是硬件健康条件下的故障态 L1/L2 对照。

下一轮不应继续扩大并发或盲目增加日志。应先修复 `.90` 的 NIC/PCIe 高温，再按 L0、L1、L2 顺序复现，并以同一 entry generation 的 VMM、timer、vGIC 和 ICH 状态作为最终判据。
