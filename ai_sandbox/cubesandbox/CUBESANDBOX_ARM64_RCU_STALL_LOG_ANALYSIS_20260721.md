# CubeSandbox ARM64 RCU Stall 与 Stack Dump 日志说明

> 整理日期：2026-07-21  
> 日志日期：2026-07-20  
> 分析对象：2 vCPU Template 恢复后的 guest RCU stall、清理超时与残留 CubeShim

## 1. 结论摘要

日志表明，相关 Sandbox 的 guest 内核中，CPU1 长时间失去前进能力。CPU0 检测到 CPU1 未完成 RCU quiescent state，并在需要全 CPU 同步时持续等待 CPU1 响应。

RCU stall 是强故障证据，但更接近后果和定位线索，不是最终根因。现有日志不能单独区分 timer interrupt 丢失、vGIC/PPI 状态异常、跨 CPU 中断异常或 CPU1 卡在其他不可抢占路径。

结合 CubeSandbox 恢复代码和 Linux 6.6 KVM/ARM64 实现，当前最高优先级方向是：Snapshot 没有形成 timer 与 vGIC 的同一时刻状态，恢复后各 vCPU 的首次 `KVM_RUN` 又缺少完成确认，CPU1 可能在 timer IRQ 与 VGIC pending/active 状态重算时失去中断前进能力。

这是有代码依据的根因推断，尚不是最终定论。确认仍需要取得 CPU1 timer PPI line、pending、active，以及首次 `KVM_RUN` 前后的直接证据。

两个目标实例最初都已完成 Snapshot 恢复、agent 连接和 Sandbox 创建。问题在后续运行与清理阶段暴露。

因此，本批次不只是“创建接口直接失败”，还存在“创建成功但 guest 随后失去推进能力”的情况。

两个实例在清理前均残留 CubeShim，进程 CPU 占用约 103%。这与 vCPU 忙转、guest RPC 失联和 VM 无法正常退出的现象一致。

## 2. 日志范围与批次背景

日志来自测试批次 `create-c10-n200`。下表数据可直接核对[批次汇总 JSON](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/create-c10-n200.case-summary.json)：

| 项目 | 值 |
| --- | ---: |
| Template | `tpl-80e1fa6aefa14f80854a23d0` |
| VM 规格 | `2C2000M` |
| 并发数 | 10 |
| 总请求数 | 200 |
| 创建成功 | 190 |
| 创建失败 | 10 |
| 创建成功率 | 95% |
| 恢复清理回收的 Shim | 10 |
| 最终清理状态 | Sandbox、Shim、task 均为 0 |

[失败证据摘要](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/summary.txt)还统计到 40 条 ttrpc timeout 和 107 条 VMM task timeout。

这些是错误签名次数，不应直接等同于失败实例数。

本文重点分析两个具有完整 RCU stack dump 的实例：

- `3563f1ab6bce4f61997a32a74527840b`
- `5991840072c74ff7870f6139ec55bb4b`

原始日志是并发汇总日志，夹杂了 `8640...`、`5d53...`、`bee4...` 等其他实例。分析时必须按 `InstanceId` 分组，不能把相邻行直接串成一个 Sandbox 的时间线。

## 3. 两个实例的时间线

### 3.1 实例 `3563...`

| 时间 | 事件 | 判断 | 原始证据 |
| --- | --- | --- | --- |
| `06:27:31.447` | `create req start`，开始从 Snapshot 恢复 | 创建开始 | [L37-L42](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L37-L42) |
| `06:27:31.459` | `agent is ready` | guest agent 已可连接 | [L43](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L43) |
| `06:27:31.469` | `create req finish` | 创建接口已成功完成 | [L49](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L49) |
| `06:28:01.439` | 发起 kill | 创建约 30 秒后开始停止 | [L237-L238](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L237-L238) |
| `06:28:11.439` | 发起 delete | kill 未正常结束 | [L257-L258](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L257-L258) |
| `06:28:21.641` | `destroy sandbox` ttrpc timeout | guest RPC 已无法响应 | [L319](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L319) |
| `06:28:22.450` | guest 报告 CPU1 RCU stall | stall watchdog 输出证据 | [L374-L377](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L374-L377) |
| `06:28:22.641` | VM shutdown event 超时 | VM 未正常退出 | [L386](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L386) |
| `06:28:32.525` | RCU kthread starvation 与完整 stack dump | 故障持续存在 | [L422-L469](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L422-L469) |

### 3.2 实例 `5991...`

| 时间 | 事件 | 判断 | 原始证据 |
| --- | --- | --- | --- |
| `06:27:31.725` | `create req start` | 创建开始 | [L97-L102](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L97-L102) |
| `06:27:31.741` | `agent is ready` | guest agent 已可连接 | [L103](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L103) |
| `06:27:31.752` | `create req finish` | 创建接口已成功完成 | [L109](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L109) |
| `06:28:01.660` | 发起 kill | 创建约 30 秒后开始停止 | [L243-L244](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L243-L244) |
| `06:28:11.659` | 发起 delete | kill 未正常结束 | [L266-L267](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L266-L267) |
| `06:28:21.863` | `destroy sandbox` ttrpc timeout | guest RPC 已无法响应 | [L333-L334](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L333-L334) |
| `06:28:22.679` | guest 报告 CPU1 RCU stall | 与 `3563...` 基本相同 | [L390-L393](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L390-L393) |
| `06:28:22.863` | VM shutdown event 超时 | VM 未正常退出 | [L398](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L398) |
| `06:28:32.753` | RCU kthread starvation 与完整 stack dump | 故障持续存在 | [L474-L521](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L474-L521) |

两个实例的顺序和间隔高度相似，说明这不是单条孤立日志，而是同一 Template、同一并发批次下可重复出现的 guest 多 CPU 前进性故障。

RCU watchdog 需要等待阈值后才打印 stall。guest 时间约 56 秒时出现告警，不代表故障在第 56 秒才开始；CPU1 停止正常推进可能发生得更早。

## 4. RCU Stall 字段说明

代表性日志：

```text
rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
rcu: 1-...!: (7 GPs behind) idle=3c48/0/0x0
     softirq=1162/1162 fqs=0 (false positive?)
rcu: (detected by 0, t=5253 jiffies, g=301, q=8 ncpus=2)
Sending NMI from CPU 0 to CPUs 1:
```

原始位置：

- [实例 `3563...` L374-L377](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L374-L377)
- [实例 `5991...` L390-L393](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L390-L393)

### 4.1 `1-...!`

开头的 `1` 指向 CPU1。该 CPU 没有在预期时间内完成 RCU 所需的 quiescent state，因此被 RCU stall detector 标记。

这与其他实验中故障集中在 CPU1 的现象一致。它不能单独证明 CPU1 完全停止执行，但可以确认 CPU1 没有完成 RCU 所需的正常推进。

### 4.2 `7 GPs behind`

`GP` 是 RCU grace period。`7 GPs behind` 表示 CPU1 已落后多个 grace period，RCU 无法确认旧读者已经退出，因此后续回收和回调不能正常完成。

实例 `5991...` 显示 `6 GPs behind`，含义相同。

### 4.3 `softirq=1162/1162`

RCU 检测记录中的两个 softirq 计数相同。结合持续 stall，可判断检测窗口内没有观察到预期的 RCU softirq 推进。

它支持“CPU1 的 timer/softirq/调度推进异常”，但不能独立证明最初丢失的是 timer interrupt。

### 4.4 `detected by 0`

该字段表示 CPU0 仍能执行 RCU 检测逻辑，并由 CPU0 发现 CPU1 未推进。故障并不是两个 vCPU 同时完全停止。

### 4.5 `t=5253 jiffies`

`t` 表示 RCU 观察到 stall 已持续的内核 tick 数。换算成秒依赖 guest 的 `CONFIG_HZ`，不应只凭该字段做固定时间换算。

该值说明故障已持续较长时间，而不是瞬时调度抖动。

### 4.6 `(false positive?)`

这是 Linux RCU stall 日志中的通用提示，提醒管理员某些长时间关中断、严重过载或调试环境也可能触发告警。

本批次中两个独立实例出现同类 CPU1 stall，同时伴随 ttrpc timeout、VM shutdown timeout 和高 CPU Shim，因此不能据此把本次事件判定为误报。

### 4.7 `Sending NMI from CPU 0 to CPUs 1`

内核尝试向 CPU1 发送诊断性 NMI/backtrace 请求，以获取 CPU1 当前栈。提供的片段中没有 CPU1 返回的有效调用栈。

这与 CPU1 无响应相符，但也可能是诊断中断实现或日志采集不完整所致，不能仅凭“缺少 CPU1 栈”下最终结论。

## 5. 第一段调用栈：RCU Grace-Period 线程

```text
task:rcu_preempt state:R pid:17
Call trace:
  __switch_to
  __schedule
  schedule
  schedule_timeout
  rcu_gp_fqs_loop
  rcu_gp_kthread
  kthread
ret_from_fork
```

原始位置：

- [实例 `3563...` L422-L434](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L422-L434)
- [实例 `5991...` L474-L486](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L474-L486)

这段栈属于 RCU grace-period 内核线程。`rcu_gp_fqs_loop` 表示它正在等待 CPU 报告 quiescent state，并尝试推进当前 grace period。

该栈说明 RCU grace period 无法完成，但没有显示 `rcu_gp_kthread` 自身发生代码死锁。真正缺失的是其他 CPU，当前日志明确指向 CPU1，所需的进度或响应。

日志中的：

```text
rcu_preempt kthread starved for 5253 jiffies
Unless rcu_preempt kthread gets sufficient CPU time,
OOM is now expected behavior.
```

表示如果 RCU 长期不能推进，回调和待回收对象会持续积压，最终可能引发 OOM。它是风险预警，不表示打印该行时已经发生 OOM。

## 6. 第二段调用栈：CPU0 等待全 CPU 同步

关键栈如下：

```text
CPU: 0 PID: 62 Comm: tokio-runtime-w
pc: __cmpwait_case_32
lr: smp_call_function_many_cond

__cmpwait_case_32
  -> smp_call_function_many
  -> smp_call_function
  -> kick_all_cpus_sync
  -> arch_jump_label_transform_apply
  -> __jump_label_update
  -> jump_label_update
  -> static_key_slow_inc_cpuslocked
  -> freezer_apply_state
  -> freezer_write
  -> cgroup_file_write
  -> kernfs_fop_write_iter
  -> vfs_write
  -> ksys_write
  -> __arm64_sys_write
```

原始位置：

- [实例 `3563...` L435-L469](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L435-L469)
- [实例 `5991...` L487-L521](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L487-L521)

该栈表示 guest 内名为 `tokio-runtime-w` 的用户态线程正在通过 `write()` 修改 cgroup freezer 状态。

`freezer_apply_state` 更新 static key 时，需要通过 `kick_all_cpus_sync` 让所有在线 CPU 完成同步。guest 只有两个 CPU，CPU0 此时卡在 `smp_call_function_many` 的等待路径。

结合 RCU 已明确报告 CPU1 stall，最合理的解释是 CPU0 正等待 CPU1 完成跨 CPU 同步，但 CPU1 没有及时处理或确认请求。

这段栈直接证明了多 CPU 前进性被破坏：不仅 RCU 无法等待到 CPU1，普通内核的全 CPU 同步操作也因 CPU1 无响应而停住。

## 7. `freezer_write` 是否是根因

当前证据不能证明 cgroup freezer 是根因。

`freezer_write` 是 CPU0 当时执行的操作。该操作需要所有 CPU 响应，因此它更像一个故障暴露点：CPU1 已经异常，freezer 的全 CPU 同步使问题变得可见并阻塞 CPU0。

如果要证明 freezer 是触发原因，需要在 CPU1 正常的对照组中，仅改变 freezer 操作，并证明故障在该操作后首次出现。现有日志没有提供这种因果对照。

因此，正确表述是：

> cgroup freezer 写操作卡在跨 CPU 同步，证明 CPU1 当时未正常响应；但该栈不足以证明 freezer 导致了 CPU1 异常。

## 8. 清理错误的含义

代表性错误：

```text
destroy sandbox failed:
ttrpc err: Receive packet timeout Elapsed(()), but nothing to do

wait vm shutdown event failed:
Receive event timeout after 1000ms, but nothing to do
```

原始位置：

- [实例 `3563...` ttrpc L319](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L319)
- [实例 `3563...` shutdown L386](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L386)
- [实例 `5991...` ttrpc L333](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L333)
- [实例 `5991...` shutdown L398](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L398)

`destroy sandbox` ttrpc timeout 表示 Shim 无法通过 guest RPC 完成销毁流程。它与 guest 内核已失去正常调度和中断推进的状态一致。

`wait vm shutdown event` 超时表示 Shim 在一秒内没有收到预期的 VMM shutdown event。该错误说明正常 VM 退出链路未完成，不等于 VM 已经安全退出。

`Kill container failed: Not Found` 和 `delete container failed: Not Found` 出现在重复清理或部分 task 状态已移除后，属于次生状态不一致。它们不是本批次最早或最关键的故障点。

错误文本中的 `but nothing to do` 是错误包装信息，不应解释为销毁成功。

## 9. 从 KVM/ARM64 原理推导根因

### 9.1 分析边界

本节把三类证据串联起来：本批次 RCU 日志、CubeSandbox 当前源码、Linux v6.6 上游 KVM/ARM64 实现。

stack dump 中的 `6.6.119-cube.bm.guest.001` 是 guest 内核，见[原始日志 L436](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L436)。

KVM timer/VGIC 代码运行在宿主内核。测试记录中的宿主版本是 `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray`，见[问题说明 L34-L44](CUBESANDBOX_ARM64_MULTIVCPU_RESTORE_ISSUE_BRIEF_20260721.md#L34-L44)。

上游 v6.6 代码用于解释机制。最终结论必须在上述 openEuler 宿主内核的实际源码或 trace 上复核，不能用 guest 版本代替宿主 KVM 版本。

下文严格区分：

- **事实**：日志或当前源码可以直接证明。
- **机制依据**：Linux v6.6 KVM 代码明确规定的行为。
- **推断**：事实与机制能够解释，但还没有直接状态证据。

### 9.2 一个 ARM virtual timer 实际跨越两套状态

从 KVM 的角度，virtual timer 不是只靠 `CNTV_CTL/CNTV_CVAL` 两个寄存器就能完整迁移。

第一部分是 vCPU timer 状态：

- `CNT` 或 VM-wide counter offset：决定 guest 当前时间。
- `CVAL`：绝对到期时间。
- `CTL.ENABLE`、`CTL.IMASK`：决定 timer 是否允许产生中断。
- `ISTATUS`：KVM 根据当前 counter 与 `CVAL` 推导的只读状态。

机制位置：

- [Linux v6.6 `kvm_timer_should_fire()` L381-L420](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L381-L420)
- [`read_timer_ctl()` L1094-L1107](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1094-L1107)

第二部分是中断控制器状态：

- timer PPI 当前输入线电平 `line level`。
- GICR pending latch。
- pending、active、enable、group、priority。
- CPU1 对应的 Redistributor 和 ICC CPU interface 状态。

机制位置：

- [VGIC pending latch 与 line level L131-L157](https://github.com/torvalds/linux/blob/v6.6/Documentation/virt/kvm/devices/arm-vgic-v3.rst#L131-L157)
- [`LEVEL_INFO_LINE_LEVEL` L249-L278](https://github.com/torvalds/linux/blob/v6.6/Documentation/virt/kvm/devices/arm-vgic-v3.rst#L249-L278)

迁移正确性要求两部分来自同一个逻辑时刻，并在 vCPU 再次运行前形成一致组合。只保证 one-reg 写入成功，不能证明 timer IRQ 已被正确投递。

### 9.3 Snapshot 保存顺序存在跨组件时间窗口

`Vm::snapshot()` 只允许在 VM 逻辑状态为 `Paused` 时执行，但保存顺序固定为 CPU、内存、vGIC、设备。源码位置：[vm.rs L2678-L2730](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2678-L2730)。

```rust
// hypervisor/vmm/src/vm.rs:2678-2730
if current_state != VmState::Paused {
    return Err(...);
}

vm_snapshot.add_snapshot(self.cpu_manager.lock().unwrap().snapshot()?);
vm_snapshot.add_snapshot(self.memory_manager.lock().unwrap().snapshot()?);
self.add_vgic_snapshot_section(&mut vm_snapshot)?;
vm_snapshot.add_snapshot(self.device_manager.lock().unwrap().snapshot()?);
```

`CpuManager::snapshot()` 又按 `self.vcpus` 顺序逐个读取 vCPU。源码位置：[cpu.rs L2104-L2113](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L2104-L2113)。

```rust
// hypervisor/vmm/src/cpu.rs:2104-2111
for vcpu in &self.vcpus {
    let cpu_snapshot = vcpu.lock().unwrap().snapshot()?;
    cpu_manager_snapshot.add_snapshot(cpu_snapshot);
}
```

因此，实际保存时间线不是一个原子切面，而是：

```text
CPU0 state(t0)
  -> CPU1 state(t1)
  -> memory state(t2...t3)
  -> vGIC state(t4)
  -> devices state(t5)
```

vCPU 不执行 guest 指令，不等于 ARM system counter 停止。KVM 未加载 timer 时用 `now = physical_counter - offset` 判断 `CVAL <= now`，见[`kvm_timer_should_fire()` L414-L420](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L414-L420)。

具体内核路径还可能通过 background timer 更新 IRQ：

- [`kvm_bg_timer_expire()` L331-L352](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L331-L352)
- [`kvm_hrtimer_expire()` L355-L378](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L355-L378)

如果 CPU1 timer 在 `t1` 到 `t4` 之间跨过 deadline，保存的 timer tuple 与后保存的 vGIC pending/active 状态就可能代表不同时间点。

这构成第一个高优先级候选：**Snapshot 缺少 timer 与 vGIC 的一致性边界**。

### 9.4 当前 vGIC Snapshot 没有单独保存 IRQ line level

当前 `Gicv3ItsState` 保存 distributor、redistributor、ICC、GICD_CTLR 和 ITS 状态。源码位置：[gic/mod.rs L109-L122](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs#L109-L122)。

```rust
// hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs:109-122
pub struct Gicv3ItsState {
    dist: Vec<u32>,
    rdist: Vec<u32>,
    icc: Vec<u32>,
    gicd_ctlr: u32,
    its_ctlr: u64,
    // 其他 ITS 字段省略
}
```

该结构没有保存 `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO` 提供的 IRQ input line bitmap。

Linux KVM VGIC 文档明确区分两类状态：`GICR_ISPENDR0` device attribute 读写的是 pending latch；对 level-triggered IRQ，guest 看到的 pending 是 latch 与 input line level 的逻辑或。

依据：[VGIC 文档 L131-L151](https://github.com/torvalds/linux/blob/v6.6/Documentation/virt/kvm/devices/arm-vgic-v3.rst#L131-L151)

文档还明确说明，完整 GIC 内部状态由 line level 与 latch 共同构成，不能从其中一个推导另一个。[原文位置 L153-L157](https://github.com/torvalds/linux/blob/v6.6/Documentation/virt/kvm/devices/arm-vgic-v3.rst#L153-L157)

PPI 的 line level 可通过 `VGIC_LEVEL_INFO_LINE_LEVEL` 按 vCPU 获取。[接口位置 L249-L278](https://github.com/torvalds/linux/blob/v6.6/Documentation/virt/kvm/devices/arm-vgic-v3.rst#L249-L278)

因此，现有 `rdist` 中即使包含 `ISPENDR0`，也不能据此证明 timer PPI 的 line level 已独立保存。这是一个具体的状态覆盖与可观测性缺口。

这不自动等于实现错误。对 architected timer PPI，输入 line 属于 timer source 状态，最终还会由 KVM timer 模型重算。应先用 `LEVEL_INFO` 做一致性校验，再决定由 timer 侧重建还是显式恢复。

### 9.5 Restore 的用户态代码顺序

`Vm::restore()` 的关键顺序如下。源码位置：[vm.rs L2751-L2794](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2751-L2794)。

```rust
// hypervisor/vmm/src/vm.rs:2751-2794
device_manager.restore(...)?;          // 设备骨架
cpu_manager.restore(...)?;             // 创建并 set_state 所有 vCPU
self.restore_vgic_and_enable_interrupt(&snapshot)?;
device_manager.restore_devices(...)?;
self.cpu_manager.lock().unwrap().start_restored_vcpus()?;
```

ARM64 vCPU 恢复先写 core registers，再按快照向量顺序逐个执行 `KVM_SET_ONE_REG`，最后写 MP state。源码位置：[kvm/mod.rs L2176-L2191](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/mod.rs#L2176-L2191)。

```rust
// hypervisor/hypervisor/src/kvm/mod.rs:2176-2191
self.set_regs(&state.core_regs)?;
for reg in &state.sys_regs {
    self.fd.lock().unwrap()
        .set_one_reg(reg.id, &reg.addr.to_le_bytes())?;
}
self.set_mp_state(state.mp_state.into())?;
```

vGIC 在所有 vCPU `set_state()` 之后创建。代码根据已保存的 vCPU 状态构造 `GICR_TYPER`，再恢复 vGIC 并启用中断路由。[源码位置 vm.rs L2286-L2357](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2286-L2357)

`Gicv3ItsState::set_state()` 当前先写 `GICD_CTLR`，之后才写 distributor、redistributor 和 ICC。源码位置：[gic/mod.rs L398-L407](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs#L398-L407)。

```rust
// hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs:398-407
write_ctlr(&self.device, state.gicd_ctlr)?;
set_dist_regs(&self.device, &state.dist)?;
set_redist_regs(&self.device, &gicr_typers, &state.rdist)?;
set_icc_regs(&self.device, &gicr_typers, &state.icc)?;
```

vCPU 尚未正常执行，使“先写 GICD_CTLR”不一定立即出错。但从恢复不变量看，更稳妥的顺序应是在 dist/rdist/ICC 完成后最后恢复使能状态。

### 9.6 restored vCPU 启动与立即 resume 之间缺少完成确认

`start_restored_vcpus()` 以 `paused=true` 启动所有线程。源码位置：[cpu.rs L1178-L1184](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L1178-L1184)。

```rust
// hypervisor/vmm/src/cpu.rs:1178-1184
pub fn start_restored_vcpus(&mut self) -> Result<()> {
    self.activate_vcpus(self.vcpus.len() as u8, false, Some(true))?;
    Ok(())
}
```

`activate_vcpus()` 的 barrier 只等待所有 vCPU 线程创建并到达启动点。源码位置：[cpu.rs L1106-L1143](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L1106-L1143)。

```rust
// hypervisor/vmm/src/cpu.rs:1117-1143
self.vcpus_pause_signalled.store(true, Ordering::SeqCst);
// 逐个 spawn vCPU 线程
vcpu_thread_barrier.wait();
Ok(())
```

线程通过 barrier 后，如果仍观察到 pause 标志，会先执行一次 `immediate_exit` 的 `KVM_RUN`，再设置 ACK 并 park。源码位置：[cpu.rs L951-L999](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L951-L999)。

```rust
// hypervisor/vmm/src/cpu.rs:968-998
if vcpu_pause_signalled.load(Ordering::SeqCst) {
    vcpu.lock().as_ref().unwrap().vcpu.set_immediate_exit(true);
    if !matches!(vcpu.lock().unwrap().run(), Ok(VmExit::Ignore)) {
        break;
    }
    vcpu.lock().as_ref().unwrap().vcpu.set_immediate_exit(false);

    vcpu_run_interrupted.store(true, Ordering::SeqCst);
    while vcpu_pause_signalled.load(Ordering::SeqCst) {
        thread::park();
    }
}
```

但是 `start_restored_vcpus()` 没有等待每个 `vcpu_run_interrupted=true`。父线程通过 barrier 后即可返回。

外层 `vm_restore()` 随后立即调用 `vm.resume()`。源码位置：[vmm/src/lib.rs L725-L727](source_code/CubeSandbox/hypervisor/vmm/src/lib.rs#L725-L727)。

```rust
// hypervisor/vmm/src/lib.rs:725-727
vm.restore(snapshot)?;
vm.resume()?;
```

`Vm::resume()` 立即进入 `CpuManager::resume()`，后者清除全局 pause 标志并 unpark vCPU。

源码位置：[vm.rs L2618-L2639](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2618-L2639)、[cpu.rs L2080-L2095](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L2080-L2095)。

由此存在以下时序差异：

```text
CPU0: barrier -> 看到 paused=true -> immediate-exit KVM_RUN -> park
CPU1: barrier -> 尚未读取 paused
VMM : restore 返回 -> resume，paused=false
CPU1: 直接进入正常 KVM_RUN
```

也可能出现 CPU0/CPU1 相反的顺序。当前 barrier 不保证两个 vCPU 都完成首次 KVM vCPU-load，也不保证二者都已进入 park 状态。

这一候选与三项现象高度吻合：问题依赖多 vCPU；故障集中在 secondary CPU；少量日志或 readback 能改变确定性坏 Template 的结果。

观察效应的直接 A/B：

- v15 插桩下同一坏 Template 5/5 成功：[summary.json L3-L16](remote-results/arm64-vcpu-sync-v10-20260720/v15-timer-state-trace/deterministic-bad-v10-template/gate-5/summary.json#L3-L16)
- 切回社区原版后 0/1：[run.log L1-L17](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/ab-control/official-v10-template-smoke-1/run.log#L1-L17)

因此，**restored vCPU 首次进入缺少全体 ACK** 应与 timer/vGIC 非原子快照并列为 P0。

限定条件是：如果 timer 与 VGIC 状态完全一致，resume 后直接进入正常 `KVM_RUN` 本应合法。缺少 ACK 目前只是高价值竞态入口，不是已确认缺陷；E1 需要验证它是否改变失败率。

### 9.7 `CTL=5` 的准确含义与一项重要勘误

Linux v6.6 的 timer register list 顺序确实是 CTL、CNT、CVAL，见[guest.c L593-L600](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/guest.c#L593-L600)：

```c
KVM_REG_ARM_TIMER_CTL,
KVM_REG_ARM_TIMER_CNT,
KVM_REG_ARM_TIMER_CVAL,
```

CubeSandbox 保存 `KVM_GET_REG_LIST` 的返回顺序，见[kvm/mod.rs L2047-L2082](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/mod.rs#L2047-L2082)。

恢复时按该向量顺序写回，见[kvm/mod.rs L2176-L2189](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/mod.rs#L2176-L2189)。

但 `KVM_SET_ONE_REG` 写 `CTL` 时，KVM 会明确去掉只读 `ISTATUS`。机制位置：[arch_timer.c L1195-L1210](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1195-L1210)。

```c
// Linux v6.6 arch/arm64/kvm/arch_timer.c:1205-1207
case TIMER_REG_CTL:
    timer_set_ctl(timer, val & ~ARCH_TIMER_CTRL_IT_STAT);
    break;
```

`kvm_arm_timer_set_reg()` 本身只更新 timer context，没有在 CTL/CNT/CVAL 每次写入后调用 `kvm_timer_update_irq()`。[函数位置 L1051-L1091](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1051-L1091)

所以，快照中的 `CTL=5` 表示读取时观察到 `ENABLE + ISTATUS`，但恢复时不能表述为“写入 CTL=5 立即恢复 ISTATUS 并注入 PPI”。

本地 v16 证据显示 CPU0/CPU1 的保存值和 readback 均为 `CTL=5`，且 CVAL 已过期，见[timer-trace.log L2-L5](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/v10-template-smoke-1/timer-trace.log#L2-L5)。它证明值被接受，但没有观测 IRQ line。

按上游 v6.6 机制，单纯把 CTL 改为最后写可以改善寄存器恢复语义，但不一定修复剩余问题。真正关键的是首次 vCPU load 时的 timer IRQ 重算。

如果实际 openEuler 内核对此路径有补丁，CTL 写入行为需要按实际内核重新确认。

### 9.8 第一次 `KVM_RUN` 是 timer 与 VGIC 的状态收敛点

Linux KVM 在 vCPU load 时执行 `kvm_timer_vcpu_load()`。对于 in-kernel VGIC，它先计算 timer 是否应触发，再更新 VGIC line。机制位置：[arch_timer.c L656-L674](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L656-L674)。

```c
// Linux v6.6 arch/arm64/kvm/arch_timer.c:656-674
kvm_timer_update_irq(vcpu, kvm_timer_should_fire(ctx), ctx);

if (irqchip_in_kernel(vcpu->kvm))
    phys_active = kvm_vgic_map_is_active(vcpu, timer_irq(ctx));

phys_active |= ctx->irq.level;
set_timer_irq_phys_active(ctx, phys_active);
```

未加载时，`kvm_timer_should_fire()` 的核心判断是：timer 已启用、未屏蔽，且 `CVAL <= physical_counter - offset`。[函数位置 L381-L420](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L381-L420)

`kvm_timer_update_irq()` 会记录 `ctx->irq.level`，并通过 `kvm_vgic_inject_irq()` 把该电平反映到 in-kernel VGIC。[函数位置 L446-L461](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L446-L461)

这说明第一次 `KVM_RUN` 不是被动进入 guest，而是会把 timer tuple、counter offset、VGIC active 状态和 IRQ line 重新组合。

若 timer 状态来自 `t1`、VGIC latch/active 来自 `t4`，恢复时 KVM 会把两个不同时刻的状态合并。可能结果包括丢失、重复、持续 asserted，或 active/line 不一致。

现有证据尚不能区分具体是哪一种。v16 readback 只证明寄存器值可读回，不能证明首次 `KVM_RUN` 后的 PPI line、pending 和 active 正确。

### 9.9 为什么还要怀疑 CPU1 的整体中断投递

如果只是漏掉一次 timer tick，CPU1 理论上仍可能响应 SGI/IPI。当前栈显示 CPU0 卡在以下路径。

原始位置：

- [实例 `3563...` L440-L462](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L440-L462)
- [实例 `5991...` L492-L514](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L492-L514)

```text
smp_call_function_many
  -> kick_all_cpus_sync
  -> static_key/jump_label
  -> freezer_apply_state
```

这表示 CPU1 连跨 CPU function call 的确认都没有完成。诊断 NMI/backtrace 也没有取得 CPU1 有效栈。

因此，剩余根因可能不只是一条 timer PPI 丢失，还可能是：

- CPU1 GIC Redistributor/ICC 状态错误，PPI 和 SGI 均受影响。
- CPU1 长时间处于 IRQ masked 或不可抢占状态。
- restored CPU1 的 MP/PSTATE 与 VGIC affinity/GICR_TYPER 组合不一致。
- KVM timer IRQ active 映射异常，使 CPU1 无法获得正常中断推进。

RCU 日志把问题从“timer 值是否正确”提升为“CPU1 的整体 interrupt/forward-progress 是否正确”。

### 9.10 根因候选排序

| 优先级 | 候选 | 代码或实验依据 | 仍缺少的证据 |
| --- | --- | --- | --- |
| P0-A | restored vCPU 首次 `KVM_RUN` 缺少全体 ACK | [start barrier](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L1106-L1143) 后[立即 resume](source_code/CubeSandbox/hypervisor/vmm/src/lib.rs#L725-L727)，不等待 ACK | 每个 vCPU 首次进入与 pause flag 时间戳 |
| P0-B | timer 与 vGIC Snapshot 不是同一时刻 | [保存顺序](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2723-L2730)为 vCPU、memory、vGIC；[counter 继续推进](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L414-L420) | 保存窗口两端的 timer/PPI 状态 |
| P0-C | CPU1 VGIC line/latch/active 组合不一致 | [state 无 line bitmap](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs#L109-L122)；[CPU0 等 CPU1](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L440-L462) | CPU1 PPI/SGI line、pending、active |
| P1-A | VM-wide counter offset 与每 vCPU timer 不一致 | [CNT SET 受 VM offset 标志控制](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1060-L1065)；既有修复未达 100% | 实际 KVM capability 与 offset ioctl trace |
| P1-B | vGIC 恢复顺序不稳妥 | [先写 GICD_CTLR，再写 dist/rdist/ICC](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs#L398-L407) | GICD_CTLR-last 的无日志 A/B |
| P2 | CTL 先于 CNT/CVAL 直接注入 PPI | [SET 路径不重算 IRQ](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1051-L1091)，并[清除 ISTATUS](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1195-L1210) | 实际 vendor kernel 是否偏离上游 |
| 后果 | RCU/freezer/ttrpc/shutdown timeout | [RCU/freezer 栈](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L422-L469)和[ttrpc timeout](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L319)均在失去推进后暴露 | 不应作为初始根因修复 |

### 9.11 当前最完整的因果链

```text
Template Snapshot
  vCPU0/1 timer state 逐个保存
      -> memory 保存期间 counter/deadline 关系继续变化
      -> 较晚保存 vGIC latch/active，且未单列 line level

Template Restore
  vCPU timer/core/MP state 恢复
      -> vGIC dist/rdist/ICC 恢复
      -> restored vCPU 线程以 paused=true 启动
      -> barrier 只确认线程到达，不确认首次 KVM_RUN 完成
      -> VMM 立即 resume

首次 KVM vCPU-load
  KVM 重新计算 should_fire
      -> 注入或撤销 timer PPI line
      -> 与已恢复的 VGIC active/latch 合并
      -> CPU1 进入异常中断或不可推进状态

故障扩散
  CPU1 timer/softirq/RCU 不推进
      -> CPU0 等待 CPU1 的 smp_call_function
      -> freezer 阻塞
      -> guest agent/ttrpc 失联
      -> VM shutdown timeout 与高 CPU CubeShim 残留
```

这条链可以同时解释日志、代码顺序、2 vCPU 依赖和插桩观察效应，但最后两个箭头仍需要直接 trace 证实。

## 10. 已证明、推断与未证明

### 10.1 已证明或高置信度事实

| 事实 | 直接证据 |
| --- | --- |
| 两个目标 Sandbox 的创建接口最初成功完成 | [`3563...` create finish L49](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L49)、[`5991...` L109](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L109) |
| 两个 guest 随后均出现 CPU1 RCU stall | [`3563...` L374-L377](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L374-L377)、[`5991...` L390-L393](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L390-L393) |
| CPU0 的全 CPU 同步因 CPU1 未正常响应而阻塞 | [`3563...` L440-L462](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L440-L462)、[`5991...` L492-L514](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L492-L514) |
| guest RPC 和 VM shutdown 无法完成 | [`3563...` ttrpc L319](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L319)、[shutdown L386](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L386) |
| 两个 CubeShim 残留且各占用约 103% CPU | [进程快照 L4、L6](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/create-c10-n200.processes-before-cleanup.txt#L4-L6) |
| Snapshot 顺序是 CPU、memory、vGIC、devices | [vm.rs L2723-L2730](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2723-L2730) |
| Restore 后启动 paused vCPU，并立即 resume | [vm.rs L2751-L2794](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2751-L2794)、[vmm/src/lib.rs L725-L727](source_code/CubeSandbox/hypervisor/vmm/src/lib.rs#L725-L727) |
| vGIC snapshot state 没有独立 IRQ line-level 字段 | [gic/mod.rs L109-L122](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs#L109-L122) |
| Linux v6.6 首次 vCPU load 重算 timer IRQ 并合并 VGIC active | [arch_timer.c L656-L674](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L656-L674) |
| 诊断插桩能改变确定性坏 Template 的结果 | [v15 5/5 L3-L16](remote-results/arm64-vcpu-sync-v10-20260720/v15-timer-state-trace/deterministic-bad-v10-template/gate-5/summary.json#L3-L16)、[社区原版 0/1 L1-L17](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/ab-control/official-v10-template-smoke-1/run.log#L1-L17) |

### 10.2 高可信度推断

| 推断 | 就地依据 |
| --- | --- |
| 故障位于 timer、VGIC 与首次 `KVM_RUN` 的时序交互附近 | [首次 load 重算 IRQ](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L656-L674)；[窗口内插桩改变结果](remote-results/arm64-vcpu-sync-v10-20260720/v15-timer-state-trace/deterministic-bad-v10-template/gate-5/summary.json#L3-L16) |
| `start_restored_vcpus()` 到 `resume()` 缺少全体 vCPU ACK | [启动 barrier](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L1106-L1143)；[立即 resume](source_code/CubeSandbox/hypervisor/vmm/src/lib.rs#L725-L727) |
| CPU1 异常可能覆盖 timer PPI 和 SGI/IPI | [CPU0 卡在 `smp_call_function_many`](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log#L440-L462) |
| counter offset 可能放大 deadline 差异，但不是唯一解释 | [CNT SET 的 VM-wide offset 分支](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1060-L1065)；[实验结论 L225-L241](CUBESANDBOX_ARM64_MULTIVCPU_RESTORE_ISSUE_BRIEF_20260721.md#L225-L241) |

### 10.3 尚未证明

1. CPU1 第一个错误状态究竟是 timer line、pending、active、ICC、PSTATE 还是 MP state。
2. line-level 未保存是否就是本批次唯一根因。
3. CPU0/CPU1 首次 `KVM_RUN` 的实际先后与 immediate-exit 路径。
4. 当前 openEuler KVM 是否与上游 v6.6 timer/VGIC 路径完全一致。
5. cgroup freezer 或 RCU 本身存在实现缺陷。
6. 固定 sleep、详细日志或 readback 可以作为正式修复。

## 11. 根因验证实验

### 11.1 实验原则

所有实验都使用同一确定性坏 Template 与同一社区基线做 A/B，并保留成功实例作为对照。

默认使用内存 ring buffer 或 tracepoint，结束后一次性导出。窗口内不得格式化打印、同步写盘或额外 GET ioctl，避免重复 v15/v16 的观察效应。

每个时序改动都设置“等量延迟但不改变顺序”的对照组，用于区分真正的顺序修复与延迟掩盖。

### 11.2 E1：验证 restored vCPU 首次进入 ACK

实施位置：[vCPU pause 分支 cpu.rs L951-L999](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L951-L999)、[`start_restored_vcpus()` L1178-L1184](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L1178-L1184)。

在 vCPU 线程记录以下单调时间戳：通过 barrier、读取 pause flag、进入/退出首次 `KVM_RUN`、设置 `vcpu_run_interrupted`、park、resume 后首次正常 `KVM_RUN`。

增加实验组：`start_restored_vcpus()` 必须等到所有 vCPU 的 `vcpu_run_interrupted=true`，再允许 `Vm::restore()` 返回和 `vm.resume()`。

| 结果 | 解释 |
| --- | --- |
| 当前实现失败，ACK barrier 组稳定 | 强支持 P0-A |
| 失败随 CPU0/CPU1 首次进入顺序变化 | 支持多 vCPU first-run 竞态 |
| 两组同样失败 | 转向 P0-B/P0-C，但仍保留状态 trace |

### 11.3 E2：验证 Snapshot 是否为一致切面

实施位置：[VM Snapshot 顺序 vm.rs L2723-L2730](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs#L2723-L2730)、[vGIC state gic/mod.rs L316-L395](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs#L316-L395)。

在 CPU1 state 保存时、memory 保存后、vGIC 保存前后，各采样：

- virtual timer `CTL/CNT/CVAL` 和无符号 `CVAL-CNT`。
- 实际 vtimer PPI 的 `VGIC_LEVEL_INFO_LINE_LEVEL`。
- `GICR_ISPENDR0/ISACTIVER0/ISENABLER0`。
- CPU1 ICC、MP state、PC/PSTATE。

如果 timer 在 CPU snapshot 后跨过 deadline，或 line/latch/active 在 vGIC snapshot 前发生变化，即可直接证明保存侧状态不一致。

可增加一个最小 A/B：把 vGIC snapshot 移到 CPU snapshot 之后并缩短中间窗口。该实验只用于定位，不能替代完整一致性设计。

### 11.4 E3：定位首次 `KVM_RUN` 的 timer/VGIC 重算

实施位置：

- [vCPU set_state L2176-L2191](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/mod.rs#L2176-L2191)
- [vGIC restore L398-L407](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs#L398-L407)
- [KVM timer load L656-L674](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L656-L674)

在恢复后的四个边界读取或 trace 同一组状态：

1. vCPU `set_state()` 完成。
2. vGIC `set_state()` 完成。
3. 每个 vCPU 第一次 `KVM_RUN` 之前。
4. 每个 vCPU 第一次 `KVM_RUN` 返回之后。

宿主侧优先采集 `kvm_timer_should_fire` 的输入结果、`kvm_timer_update_irq`、`kvm_vgic_inject_irq`、IRQ level 和 VGIC active 映射。实际 tracepoint 名称以 vendor kernel 为准。

第一次出现成功组与失败组差异的边界，就是下一步修复位置。

### 11.5 E4：timer-disabled first-entry 对照

实施位置：[ARM64 one-reg restore loop L2176-L2189](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/mod.rs#L2176-L2189)与[restored vCPU start L1178-L1184](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs#L1178-L1184)之间增加受控阶段。

恢复时先保存最终 CTL，但临时以 `ENABLE=0` 写入。完成 vGIC 恢复并让所有 vCPU 做一次受控 immediate-exit `KVM_RUN` 后，再写最终 CTL，再统一 resume。

该实验把“vCPU/GIC 初始装载”和“timer 启用”拆成两个阶段。如果故障消失，说明首次 timer IRQ 重算是关键触发点。

仅把 CTL 调整到 CNT/CVAL 之后写不是同等强度的实验，因为上游 v6.6 的 SET 路径不会在每次 one-reg 写入后立即注入 IRQ。

### 11.6 E5：区分 timer PPI 与整体 CPU1 中断故障

恢复后在依赖 timer 的 workload 前执行最小 guest 自检：CPU0 向 CPU1 发送 SGI/IPI，CPU1 递增共享计数器并应答。

| SGI/IPI | timer PPI | 判断 |
| --- | --- | --- |
| 正常 | 异常 | 优先定位 virtual timer/PPI line |
| 异常 | 异常 | 优先定位 CPU1 GICR/ICC/PSTATE/MP state |
| 均正常，后续才失败 | 采集首次状态变化点与 guest 关中断路径 |

### 11.7 E6：counter offset 与内核版本 A/B

机制位置：[Linux v6.6 `kvm_arm_timer_set_reg()` L1051-L1091](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1051-L1091)、[Cloud Hypervisor PR #8343](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343)。

记录实际 `KVM_CAP_COUNTER_OFFSET`、VM counter offset 设置接口、每个 vCPU 的 CNT/CVAL 与最终读值。

Linux 6.6 中，当 `KVM_ARCH_FLAG_VM_COUNTER_OFFSET` 已设置时，`KVM_REG_ARM_TIMER_CNT` 的 per-vCPU SET 不再更新 offset。恢复逻辑必须按实际 capability 选择 VM-wide 或 per-vCPU 方案。

在同一用户态二进制下，增加上游近似 6.6 与当前 openEuler `6.6.0-132...` 的宿主 A/B。若故障只在 vendor kernel 出现，再比较 `arch_timer.c` 与 VGIC 补丁集。

### 11.8 判定标准

候选修复必须移除详细日志和 readback，并满足：

1. 全新 2 vCPU Template 创建与恢复达到目标样本 100/100。
2. 历史确定性坏 Template 不再复现。
3. CPU1 SGI/IPI 与 timer PPI 自检均正常。
4. 无 RCU/timer stall、ttrpc shutdown timeout 和残留高 CPU Shim。
5. 对照延迟组仍失败或无同等改善，证明修复来自顺序或状态完整性。

## 12. 代码与证据入口

### 12.1 CubeSandbox 代码

- [VM Snapshot/Restore 顺序](source_code/CubeSandbox/hypervisor/vmm/src/vm.rs)
- [vCPU pause、启动、snapshot/restore](source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs)
- [ARM64 vCPU one-reg state](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/mod.rs)
- [ARM64 vGIC state](source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs)
- [完整 Pause/Snapshot/Restore 调用链](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ANALYSIS_20260721.md)
- [低扰动插桩设计](CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md)

### 12.2 Linux/KVM 一手依据

- [timer 到期条件 `kvm_timer_should_fire`](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L381-L420)
- [timer IRQ 注入 `kvm_timer_update_irq`](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L446-L461)
- [首次 vCPU load 与 VGIC active 合并](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L656-L674)
- [timer one-reg SET 行为](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1051-L1091)
- [CTL 写入清除只读 ISTATUS](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/arch_timer.c#L1195-L1210)
- [Linux v6.6 ARM timer one-reg 列表](https://github.com/torvalds/linux/blob/v6.6/arch/arm64/kvm/guest.c#L593-L600)
- [VGIC pending latch 与 line level 语义](https://github.com/torvalds/linux/blob/v6.6/Documentation/virt/kvm/devices/arm-vgic-v3.rst#L131-L157)
- [VGIC `LEVEL_INFO_LINE_LEVEL` 接口](https://github.com/torvalds/linux/blob/v6.6/Documentation/virt/kvm/devices/arm-vgic-v3.rst#L249-L278)
- [Cloud Hypervisor ARM64 guest clock 修复 PR #8343](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343)

### 12.3 本地实验与日志

- [完整多 vCPU 实验报告](CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md)
- [问题说明](CUBESANDBOX_ARM64_MULTIVCPU_RESTORE_ISSUE_BRIEF_20260721.md)
- [批次汇总](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/create-c10-n200.case-summary.json)
- [批次详细结果](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/create-c10-n200.json)
- [失败证据摘要](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/summary.txt)
- [v16 timer SET/readback](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/v10-template-smoke-1/timer-trace.log)
- [社区原版同 Template A/B 失败](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/ab-control/official-v10-template-smoke-1/run.log)
- [CubeShim 与 guest console 日志](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeShim-failed.log)
- [VMM task timeout 日志](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/CubeVmm-failed.log)
- [清理前 Shim 列表](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/create-c10-n200.shims-before-cleanup.txt)
- [清理前进程快照](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/create-c10-n200.processes-before-cleanup.txt)

## 13. 限制

当前没有 CPU1 timer PPI line/pending/active、SGI 应答和首次 `KVM_RUN` 的直接 trace。P0 候选均不能写成已经确认的最终根因。

所有现有实验主要来自同一 ARM64 主机和宿主内核，尚未完成第二主机、上游近似内核和新版 Cloud Hypervisor 的完整 A/B。

本文对 KVM 内部行为的代码依据来自上游 Linux v6.6。测试宿主使用定制 openEuler `6.6.0-132...` 内核，需取得其实际源码或符号 trace，确认具体实现没有偏离。

日志中的 `6.6.119-cube.bm.guest.001` 只标识 guest 内核，不用于推断宿主 KVM 实现。

本文关于 CTL/ISTATUS 的结论修正了早期文档中“CTL=5 写入即恢复 ISTATUS 并立即形成 PPI”的过强表述。后续结论以本节的 KVM 源码分析为准。
