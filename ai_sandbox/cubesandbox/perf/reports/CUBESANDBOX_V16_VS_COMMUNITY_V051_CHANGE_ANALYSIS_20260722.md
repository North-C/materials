# CubeSandbox v16 与社区 v0.5.1 修改差异分析

> 分析时间：2026-07-22
>
> 对照范围：社区 `v0.5.1@a164417f497234a0d787cb328b0ae96480b1569b` 与诊断版 `v16@12d301b15c27df976b1a84a6a38ca70ba097c63a`
>
> 完整补丁：[v16-vs-community.patch](./evidence/v16-vs-community-v0.5.1-20260722/v16-vs-community.patch)

## 1. 结论

v16 相比社区 v0.5.1 只有 4 个线性提交，修改 3 个文件，合计 `+168/-2`。没有合入新的 Cloud Hypervisor 上游修复，也没有修改依赖版本。

这些修改可分为三类：Template pause/snapshot/resume 日志、vCPU timer 状态日志，以及恢复时新增的 3 次 KVM timer `GET_ONE_REG` readback。

其中，唯一改变 KVM ioctl 序列的是 timer readback：每个 ARM64 vCPU 完成全部系统寄存器写回后，依次读取 CNT、CTL、CVAL，再设置 MP state。

v16 没有修改寄存器保存值、写回顺序、vGIC 恢复、restored-vCPU 启动、`reset guest time`、重试或错误处理。因此它不是一项已经证明语义正确的正式修复。

现有实验只能证明：v16 的额外 KVM readback 或关键窗口内的日志时序，足以让本批故障窗口不再出现。当前还不能区分 KVM GET 的状态副作用与纯时序观察效应。

“v16 没有问题”应严格表述为：在 stock 宿主内核的本批测试中，v16 得到串行 `100/100`、并发 `1020/1020`，目标签名为 0；不能外推为所有负载下永久无故障。

## 2. 对照对象

### 2.1 社区基线

社区版身份如下。

部署版本见 [deployed-version.txt](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/deploy/deployed-version.txt)。

二进制摘要见 [sha256-after-install.txt](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/deploy/sha256-after-install.txt)。

```text
source commit = a164417f497234a0d787cb328b0ae96480b1569b
Shim version  = containerd-shim-cube-rs v0.5.1
Shim sha256   = c3d9bd094a8fc9d86b4b06a684ee574f8f8e023479c1f4088b8597c2a6c03d46
build time    = 2026-07-11T08:08:24Z
```

### 2.2 v16

v16 构建环境见 [build-metadata.txt](./remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/deploy/build-metadata.txt)。

产物版本见 [built-version.txt](./remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/deploy/built-version.txt)。

二进制摘要见 [built-sha256.txt](./remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/deploy/built-sha256.txt)。

```text
source commit = 12d301b15c27df976b1a84a6a38ca70ba097c63a
branch        = experiment/arm64-timer-readback-v16
Shim version  = v0.5.1-arm64-timer-readback-v16
Shim sha256   = e7e9433b0789fef6f56343da10cfbc8ff5b7a59380e494ac2799055802dd5bbb
build time    = 2026-07-20T13:56:38Z
builder       = ghcr.io/tencentcloud/cubesandbox-builder:ubuntu2004-arm64
build mode    = cargo --release --locked --offline
```

构建过程同时生成 Shim 和 `cube-runtime`，但实际 v16 测试只部署了 Shim/VMM 二进制。运行中的 Runtime 始终保持社区版 SHA `d1e2db00...a7a9`。

两处归档的 v16 二进制 SHA 均为 `e7e9433b...d5bbb`，ELF Build ID 均为 `7ab5344c...`，证明后续 stock 测试使用的是同一构建产物。

## 3. 完整差异范围

Git merge-base 正是社区提交 `a164417f...`，两者之间没有合并提交，只有以下 4 个本地诊断提交。完整记录见 [commit-series.txt](./evidence/v16-vs-community-v0.5.1-20260722/commit-series.txt)。

| 顺序 | commit | 内容 | 性质 |
| --- | --- | --- | --- |
| 1 | `fe914da4` | 记录 Template 和 vCPU timer snapshot/restore 状态 | 诊断日志 |
| 2 | `45c498f6` | 修正 KVM timer 寄存器标签 | 日志语义修正 |
| 3 | `e6a4b326` | 恢复后读取 CNT、CTL、CVAL | 新增 KVM GET ioctl |
| 4 | `12d301b1` | 导入 `log::info` 宏 | 编译修正 |

差异统计见 [diff-summary.txt](./evidence/v16-vs-community-v0.5.1-20260722/diff-summary.txt)，关键内容为：

```text
CubeShim/shim/src/sandbox/sb.rs      |  25 ++++++++-
hypervisor/hypervisor/src/kvm/mod.rs |  41 ++++++++++++++
hypervisor/vmm/src/cpu.rs            | 104 ++++++++++++++++++++++++++++++++++-
3 files changed, 168 insertions(+), 2 deletions(-)
```

没有 `Cargo.toml`、`Cargo.lock`、vGIC、memory manager、device manager、seccomp、guest agent 或 Runtime 业务代码差异。

## 4. 修改一：Template 构建阶段日志

补丁位置：[v16-vs-community.patch 第 1 行](./evidence/v16-vs-community-v0.5.1-20260722/v16-vs-community.patch#L1)。

社区版直接执行 `pause -> snapshot -> resume`。v16 在相同操作前后增加 `Instant` 和 4 条日志：

```rust
let trace_started = Instant::now();
infof!(self.log, "ARM64_TIMER_TRACE event=template_snapshot_begin ...");

let ch = self.ch.as_ref().unwrap().lock().await;
ch.pause_vm().await?;
infof!(self.log, "ARM64_TIMER_TRACE event=template_snapshot_paused ...");

ch.snapshot_vm(...).await?;
infof!(self.log, "ARM64_TIMER_TRACE event=template_snapshot_saved ...");

let result = ch.resume_vm().await;
infof!(self.log, "ARM64_TIMER_TRACE event=template_snapshot_resumed ...");
result
```

这部分不修改 snapshot 参数、内存内容或 pause/resume 调用顺序，但会延长各阶段间隔并产生同步日志开销。

它可能改变新 Template 的保存时刻，却不能解释同一 Template 的恢复差异。`tpl-592...` 保持不变、只切换恢复侧 Shim 后，社区版仍从全通过降为串行 `96/100`、并发 `998/1020`。

因此，Template 构建日志不是 v16 在同 Template 强对照中成功的充分原因。

## 5. 修改二：保存状态和阶段日志

补丁位置：[timer trace helper](./evidence/v16-vs-community-v0.5.1-20260722/v16-vs-community.patch#L323) 和 [restore 调用点](./evidence/v16-vs-community-v0.5.1-20260722/v16-vs-community.patch#L400)。

v16 新增 `trace_arm64_timer_state()`。它扫描已经位于内存中的 `CpuState.sys_regs`，提取 PC、CNTKCTL、timer CNT/CTL/CVAL 等字段并打印。

```rust
let find_reg = |encoding: u16| {
    inner.sys_regs.iter().enumerate()
        .find(|(_, reg)| reg.id as u16 == encoding)
        .map(|(index, reg)| (index, reg.addr))
};

let vtimer_cval = find_reg(KVM_REG_ARM_TIMER_CVAL);
let vtimer_ctl = find_reg(KVM_REG_ARM_TIMER_CTL);
let vtimer_cnt = find_reg(KVM_REG_ARM_TIMER_CNT);

info!("ARM64_TIMER_TRACE event={} vcpu={} ...", event, vcpu_id);
```

调用点有两个：Template snapshot 获得 `saved_state` 后，以及 Sandbox restore 从快照反序列化 `saved_state` 后、调用 KVM `set_state()` 之前。

```rust
let saved_state: CpuState = snapshot.to_state(VCPU_SNAPSHOT_ID)?;
trace_arm64_timer_state("vcpu_restore_saved_state", self.id, &saved_state);
self.vcpu.set_state(&saved_state)?;
```

这部分没有调用 KVM，也没有修改 `saved_state`。但日志位于每个 vCPU 的状态写回之前，会改变 CPU0、CPU1 顺序恢复之间的主机调度和时间间隔。

v16 还在 `CpuManager::pause/resume/snapshot/restore` 前后增加阶段日志和耗时统计。它们不改变控制流，但同样位于敏感窗口中。

## 6. 修改三：恢复后的 KVM timer readback

这是 v16 唯一新增 KVM ioctl 的修改，也是当前最值得拆分验证的差异。

完整前后代码见 [社区版](./evidence/v16-vs-community-v0.5.1-20260722/community-set-state.txt) 和 [v16](./evidence/v16-vs-community-v0.5.1-20260722/v16-set-state.txt)。

### 6.1 社区版

社区版 ARM64 `set_state()` 写 core registers，按快照向量顺序写全部 system registers，然后直接设置 MP state。

```rust
fn set_state(&self, state: &CpuState) -> cpu::Result<()> {
    let state: VcpuKvmState = state.clone().into();
    self.set_regs(&state.core_regs)?;

    for reg in &state.sys_regs {
        self.fd.lock().unwrap()
            .set_one_reg(reg.id, &reg.addr.to_le_bytes())?;
    }

    self.set_mp_state(state.mp_state.into())?;
    Ok(())
}
```

### 6.2 v16

v16 保留全部原有写回代码，并在 system-register 循环之后、`set_mp_state()` 之前加入 3 次 `get_one_reg()`。

补丁精确位置：[v16-vs-community.patch 第 229 行](./evidence/v16-vs-community-v0.5.1-20260722/v16-vs-community.patch#L229)。

```rust
const KVM_REG_ARM_TIMER_CVAL: u16 = 0xdf02;
const KVM_REG_ARM_TIMER_CTL: u16 = 0xdf19;
const KVM_REG_ARM_TIMER_CNT: u16 = 0xdf1a;

let read_back = |encoding: u16| -> cpu::Result<Option<(usize, u64, u64)>> {
    let Some((index, saved)) = state.sys_regs.iter().enumerate()
        .find(|(_, reg)| reg.id as u16 == encoding)
    else {
        return Ok(None);
    };

    let mut bytes = [0_u8; 8];
    self.fd.lock().unwrap().get_one_reg(saved.id, &mut bytes)?;
    Ok(Some((index, saved.addr, u64::from_le_bytes(bytes))))
};

let vtimer_cnt = read_back(KVM_REG_ARM_TIMER_CNT)?;
let vtimer_ctl = read_back(KVM_REG_ARM_TIMER_CTL)?;
let vtimer_cval = read_back(KVM_REG_ARM_TIMER_CVAL)?;
info!("ARM64_TIMER_TRACE event=kvm_timer_restore_readback ...");

self.set_mp_state(state.mp_state.into())?;
```

实际 ioctl 序列由社区版的：

```text
SET core -> SET all sys_regs -> SET MP state
```

变为：

```text
SET core -> SET all sys_regs
         -> GET timer CNT -> GET timer CTL -> GET timer CVAL
         -> format/write info log -> SET MP state
```

v16 还给 `KvmVcpu` 增加 `id: u8`，只用于在 readback 日志中区分 vCPU，不参与状态计算。

## 7. readback 在恢复链中的准确位置

完整摘录见 [restore-call-chain-v16.txt](./evidence/v16-vs-community-v0.5.1-20260722/restore-call-chain-v16.txt)。关键顺序为：

```text
Vm::restore
  -> CpuManager::restore
     -> 逐 vCPU create_vcpu(snapshot)
        -> Vcpu::restore
           -> saved-state info log
           -> KvmVcpu::set_state
              -> SET core/sys_regs
              -> GET CNT/CTL/CVAL       [v16 新增]
              -> readback info log      [v16 新增]
              -> SET MP state
  -> restore_vgic_and_enable_interrupt
  -> restore_devices
  -> start_restored_vcpus(paused=true)
  -> 返回 VMM
VMM::restore_vm
  -> vm.resume()
  -> unpark vCPU
  -> 正常 KVM_RUN
```

因此 readback 位于每个 vCPU 状态写回期间，早于 vGIC restore，也早于 restored-vCPU 线程启动和首次正常 `KVM_RUN`。

`start_restored_vcpus()` 本身没有变化，仍以 `paused=true` 启动线程。VMM 在 `vm.restore()` 返回后立即调用 `vm.resume()`，也没有新增全体 vCPU parked/first-entry ACK。

## 8. 实际 readback 结果

原始记录见 [timer-trace.log](./remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/v10-template-smoke-1/timer-trace.log)。关键值直接展开如下：

```text
vcpu0 saved:    CNT=483864240 CTL=5 CVAL=483762171 delta=-102069
vcpu0 readback: CNT=483874528 CTL=5 CVAL=483762171 delta=-112357

vcpu1 saved:    CNT=483887497 CTL=5 CVAL=483762171 delta=-125326
vcpu1 readback: CNT=483897583 CTL=5 CVAL=483762171 delta=-135412

CpuManager restore elapsed = 459 us
```

CTL 和 CVAL 的读回值与保存值一致；CNT 在 ioctl 和日志期间继续前进约 10k tick，因此 deadline 在 readback 时已经过期得更久。

这些值证明 KVM 接受并能读出 timer tuple，但没有观测 timer PPI line、VGIC pending/active、LR 或首次 `KVM_RUN` 后的状态。

所以不能据此证明 readback 修复了 timer IRQ，只能证明额外 GET 和日志发生后，本次 Sandbox 成功启动。

## 9. 明确没有修改的链路

### 9.1 `reset guest time`

社区版与 v16 的代码位置和内容完全相同，均位于 `CubeShim/shim/src/sandbox/sb.rs:420`：

```rust
let req = agent::SetGuestDateTimeRequest {
    Sec: tm.timestamp(),
    Usec: tm.timestamp_subsec_micros() as i64,
    ..Default::default()
};

client
    .set_guest_date_time(self.ctx.clone(), &req)
    .await
    .map_err(|e| format!("reset guest time failed:{}", e))?;
```

因此 v16 不出现该字符串，不是因为删除、跳过或重试了 `set_guest_date_time()`，而是 guest 在本批测试中没有在这一 RPC 点失去响应。

### 9.2 vGIC 与首次 vCPU entry

v16 没有修改 `restore_vgic_and_enable_interrupt()`、VGIC snapshot、IRQ line、`start_restored_vcpus()`、pause flag、barrier 或 `vm.resume()`。

### 9.3 Timer 写回语义

v16 没有重排 timer CTL/CNT/CVAL 的 `SET_ONE_REG` 顺序，没有屏蔽 timer，没有重新计算 CVAL，也没有把 timer 写回延迟到 vGIC restore 之后。

### 9.4 其他组件

CubeAPI、CubeMaster、Cubelet、guest kernel、agent、Template 格式、memory volume、rootfs、network 和已部署 Runtime 都没有因 v16 改变。

## 10. 实验对照如何约束解释

### 10.1 同宿主、同 Template、只换 Shim

最强证据来自 stock 内核和同一个 `tpl-592...`。

v16 结果见 [stock 复测报告](./remote-results/v0.5.1-stock-host-kernel-template-retest-20260722-1508/TEST_SUMMARY.md)。

社区回转见 [社区替换复测](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md)。

```text
v16      serial lifecycle = 100/100
v16      concurrent       = 1020/1020
v16      target signatures= 0

community serial lifecycle = 96/100
community concurrent       = 998/1020
community RCU stall        = 10
community timer issue      = 4
community receive timeout  = 34
```

该对照保持宿主内核、Template、Runtime、镜像和服务栈不变，直接证明恢复侧 v16 差异会显著改变结果。

它不能单独指出是 3 次 GET、哪一条日志、代码布局还是这些因素的组合，因为 v16 同时改变了 ioctl 序列和执行时序。

### 10.2 确定性坏 Template 的 A/B

同一个历史坏 Template 在诊断插桩下可成功，而切回社区版后 `0/1`。社区失败原文见 [run.log](./remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/ab-control/official-v10-template-smoke-1/run.log)。

```text
community create_ok=false
error=reset reseed random dev failed: ttrpc Receive packet timeout
elapsed=8.0878s
```

这一结果支持“关键窗口对轻微扰动敏感”，但样本量很小，只能作为机制佐证，不能替代大样本同 Template 对照。

## 11. 对 v16 成功原因的分级判断

### 11.1 高可能：关键窗口内的观察效应

每个 vCPU 在 `set_state()` 前打印 saved state，写回后进入 3 次 KVM ioctl，再格式化打印 readback。两颗 vCPU 串行恢复，额外开销会改变 CPU0/CPU1、timer、vGIC restore 与首次 entry 的相对时刻。

现有日志显示整个 `CpuManager::restore` 约 459 us。对于需要在首次 vCPU load 时组合 timer 和 VGIC 状态的链路，这一量级足以移动竞态窗口。

### 11.2 中等可能：`GET_ONE_REG` 触发 KVM 内部状态物化

GET 并非普通内存读取，而是额外进入 KVM 的 vCPU one-reg ioctl 路径。它可能促使内核读取或同步当前 timer context，使后续首次 vCPU load 看到不同的中间状态。

当前没有内核侧 before/after 证据证明 GET 改写了 IRQ line、pending 或 active，所以这里只能列为可能机制，不能写成已证实副作用。

### 11.3 较低可能：Template 构建日志本身

v16 构建新 Template 时确实改变了 pause/snapshot/resume 间隔。但社区恢复同一个 v16 Template 仍失败，说明它至多影响概率或产物时刻，不是恢复成功的充分条件。

### 11.4 不能接受的结论

不能把 v16 描述为“修复了 `reset guest time`”。该函数未改，而且社区版本轮 `reset guest time=0` 时仍复现 RCU/timer/ttrpc 故障链。

也不能把 v16 描述为已经合入 Cloud Hypervisor 或 Linux KVM 的正式 timer 修复。Git 差异中不存在相关语义补丁。

## 12. 最小拆分实验建议

后续应基于同一个 `a164417f` 和同一个 Template，随机交错运行以下版本。宿主 GHES/PCIe 高温问题排除前，不应执行 c20/c50 高压档位。

| 版本 | saved-state 日志 | KVM GET | readback 日志 | 目的 |
| --- | --- | --- | --- | --- |
| V0 | 无 | 无 | 无 | 社区基线 |
| V1 | 有 | 无 | 有阶段日志 | 量化纯日志/时序影响 |
| V2 | 无 | CNT/CTL/CVAL | 延后输出 | 分离 GET 的影响 |
| V3 | 无 | 无 | 等量延迟 | 分离 GET 与耗时 |
| V4 | 有 | CNT/CTL/CVAL | 有 | 精确复现 v16 |

如果 V2 稳定而 V1/V3 失败，证据才开始指向 GET 的 KVM 侧作用。如果 V1 或 V3 同样稳定，则主要是时序窗口被移动。

随后可把 GET 拆成 CNT-only、CTL-only、CVAL-only，并分别移动到 `set_mp_state` 后、vGIC restore 后和 vCPU start 前，确定真正敏感点。

每个版本至少记录 create、guest health、delete、RCU/timer/ttrpc 和残留 Shim；版本顺序必须随机化，避免 Template 年龄、宿主温度和固定执行顺序成为混杂变量。

## 13. 最终判断

v16 的有效差异不是一个已知正式修复，而是一组位于 ARM64 restore 关键窗口中的诊断操作。

从源码看，优先级最高的是 `SET all sys_regs -> GET CNT/CTL/CVAL -> log -> SET MP state` 这一新增序列；其次是每个 vCPU set_state 前后的同步日志。

从实验看，这些操作足以在当前批次中把故障率降到 0，但尚未证明它们建立了正确且可长期依赖的 timer/VGIC 不变量。

因此，v16 适合作为定位基准和临时对照，不应直接作为生产修复发布。正式修复需要通过拆分实验确定 GET 的状态作用或具体竞态，再以无诊断副作用的最小语义改动实现。

## 14. 证据索引

- [完整 Git 补丁](./evidence/v16-vs-community-v0.5.1-20260722/v16-vs-community.patch)
- [4 个提交的完整身份](./evidence/v16-vs-community-v0.5.1-20260722/commit-series.txt)
- [文件与行数统计](./evidence/v16-vs-community-v0.5.1-20260722/diff-summary.txt)
- [社区 ARM64 set_state 摘录](./evidence/v16-vs-community-v0.5.1-20260722/community-set-state.txt)
- [v16 ARM64 set_state 摘录](./evidence/v16-vs-community-v0.5.1-20260722/v16-set-state.txt)
- [v16 restore 调用链摘录](./evidence/v16-vs-community-v0.5.1-20260722/restore-call-chain-v16.txt)
- [证据校验和](./evidence/v16-vs-community-v0.5.1-20260722/SHA256SUMS)
- [v16 stock 内核成功批次](./remote-results/v0.5.1-stock-host-kernel-template-retest-20260722-1508/TEST_SUMMARY.md)
- [社区版同机同 Template 回转](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md)
