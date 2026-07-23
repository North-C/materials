# CubeSandbox ARM64 v0.3 与 v0.5 Template 链路源码差异分析

> 分析日期：2026-07-22  
> 分析范围：Template 构建、Sandbox 从 Template 启动、ARM64 KVM/vCPU/vGIC 状态恢复、内存快照及销毁链路  
> 结论性质：源码差异评估、根因候选排序及已完成的实验 A/B/C；尚未形成唯一根因证明  
> 内嵌证据：保留原始链接；代码块只摘录关键语句，必要时折叠锁、参数和错误处理，并用注释或上下文明确省略部分

## 1. 结论摘要

源码中确实存在与 ARM64 Template 构建直接相关的不一致。最明确的一项是：v0.3 ARM64 适配版主动屏蔽了 x86 时钟参数，v0.5.0/v0.5.1 又在 ARM64 路径中无条件加入 `highres=off` 和 `clocksource=kvm-clock`。

该差异不是静态代码上的推测。v0.5.1 故障环境的 guest 启动日志确认实际命令行包含这些参数；同一日志又显示 ARM64 guest 最终回退到 `arch_sys_counter`，说明 `kvm-clock` 没有成为有效时钟源，但 `highres=off` 仍可能改变 guest timer 行为。

2026-07-22 已完成单变量实验 A：在 v0.5.1 中恢复上述 ARM64 保护，重新构建 Template 后执行 1020 次压力矩阵和 100 次 guest 生命周期门禁。结果仍为 `982/1020` 和 `97/100`，并复现 4 次同型 RCU stall。

因此，该命令行不一致仍应作为 ARM64 正确性问题修复，但已不能解释为当前故障的充分主触发条件。它可能轻微调制故障率；单批次约千次的自然波动不足以证明或排除这种小幅效应。

第二项实质变化是 Template 内存产物。v0.3 把 `memory-ranges` 写入本地快照目录并执行 `sync_all()`；v0.5 把内存写入外部 cubecow 对象，不显式同步，随后销毁临时 Sandbox、停用对象并发布快照目录。

实验 B 已完成构建端/恢复端 2 x 2 交叉。四格分别通过 `97/100`、`95/100`、`95/100`、`93/100`，没有稳定跟随 Template 或恢复侧二进制，否定了任一侧单独决定故障的强假设。

实验 C 发现 Cubelet 虽请求 Full snapshot，`dirty_log=true` 却使 VMM 在类型分派前进入 dirty-log 快路径。修正插桩后，2,097,152,000 字节对象的 49 个写入区间、139 个抽样页全部回读一致。

加入 `sync_all()` 的 C Template 串行生命周期为 `100/100`，但并发创建仍为 `1004/1020`，并复现 1 次 RCU stall 和 17 次销毁/关机超时。因此，缺少显式 flush 不是当前故障的充分根因。

另一方面，vCPU 状态、ARM64 KVM one-reg、vGIC 以及中断恢复主体在 v0.3 适配版与 v0.5.0 中相同。它们仍可能存在共同的时序敏感性，但不是本次版本差异中的新增回归点，验证优先级应低于内存产物和构建/恢复交叉链路。

当前最合理的判断是：命令行和显式 flush 均已排除“充分修复”，2 x 2 也未显示故障跟随单侧。后续优先级应转向两个版本共有的 ARM64 多 vCPU restore/timer/vGIC 时序及其与并发度、宿主 KVM 的交互。

需要特别区分两个现象：Template 构建报错与从 Template 创建 Sandbox 报错都存在，但不必然是同一个失败点。本文 RCU stall 证据来自 Sandbox 恢复后失去 guest 前进性，不能直接代表每一次 Template 构建失败的根因。

## 2. 版本与证据边界

| 对象 | 本文采用的源码基线 | 说明 |
| --- | --- | --- |
| v0.3 ARM64 | `feature/arm64-adaptation@28fe3900ba4c827e17618e49fbbe8eb568b3634f` | 2026-05-26，包含完整 ARM64 适配提交；与 2026-06-05 的测试机二进制时间最接近 |
| v0.3 后续合入版 | `v0.3.1-arm64-rc1@e552b1ba46b7a7a9a05ebec4f47abf03abc386c8` | 2026-06-11，晚于测试机二进制；仅作合入结果旁证 |
| v0.5.0 | `v0.5.0@30b4e25ab16891187c775e002816274427f541f1` | 官方 tag，工作树源码干净 |
| 故障量化批次 | `v0.5.1@a164417f497234a0d787cb328b0ae96480b1569b` | 实际 41/1020 失败批次使用的版本 |

v0.3 测试机二进制没有内嵌 Git commit。Cubelet 只显示 `(devel)`，组件只能用 SHA256 锁定。

证据：[构建元数据](/home/lyq/Projects/Verification/cubesandbox/remote-results/v0.3.0-arm64-template-compare-20260721-2145/preflight/version-build-metadata.txt:1)

证据：[组件 SHA256](/home/lyq/Projects/Verification/cubesandbox/remote-results/v0.3.0-arm64-template-compare-20260721-2145/preflight/component-sha256.txt:1)

内嵌关键内容：

```text
path  github.com/tencentcloud/CubeSandbox/Cubelet/cmd/cubelet
mod   github.com/tencentcloud/CubeSandbox/Cubelet  (devel)

2026-06-05 15:29:12  Cubelet/bin/cubelet
2026-06-05 15:29:04  cube-shim/bin/containerd-shim-cube-rs

594ec50a...beea42  Cubelet/bin/cubelet
491ffe56...d43d012 cube-shim/bin/containerd-shim-cube-rs
```

因此，本文可以证明“保存的 v0.3 ARM64 适配源码与 v0.5 源码存在什么差异”，但不能声称远端 v0.3 二进制逐字节来自 `28fe3900`。后续结论按证据强度标记，不跨越这一边界。

`CubeSandbox-sandbox-clone` 当前工作树包含多项未提交实验修改，尤其涉及 hypervisor。本文没有把这些未提交内容当作 v0.3 基线，只使用其不可变 tag 信息作旁证。

v0.5.1 相对 v0.5.0 的三个关键 Shim 文件哈希完全一致：`config.rs`、`sb.rs`、`snapshot/mod.rs`。因此，本文指出的 ARM64 命令行不一致也精确存在于实际故障批次中。

可在 v0.5.1 仓库中复核：

```bash
git diff --name-status \
  30b4e25ab16891187c775e002816274427f541f1 \
  a164417f497234a0d787cb328b0ae96480b1569b -- \
  CubeShim/shim/src/hypervisor/config.rs \
  CubeShim/shim/src/sandbox/sb.rs \
  CubeShim/shim/src/snapshot/mod.rs
```

该命令无输出，表示三个文件没有变化。

内嵌哈希结果，左右版本值相同：

```text
config.rs       2726fecb2ae913257a4ee849dc00a9c1b1d602c87146c2c77548901e76e7de9e
sb.rs           3629b8d3ea3de5bc336029b609407ea2f707dc4b5dbbfb0b6156076f4199e03a
snapshot/mod.rs 707f907ecc57f067170ab5ecaf29eb87bf717d3ff88ff9424c19ca4a182937fc
```

## 3. 测试结果与故障落点

v0.3 ARM64 适配版在 2 vCPU/2000 MiB 下完成 1020/1020，在 2 vCPU/4096 MiB 下也完成 1020/1020；两组各自又通过 100/100 次 guest HTTP 生命周期门禁。[测试汇总](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_V030_V050_TEMPLATE_COMPARISON_REPORT_20260721.md:115)

内嵌关键结果：

| 测试对象 | 创建结果 | guest 生命周期门禁 |
| --- | ---: | ---: |
| v0.3，2C2000M | 1020/1020 | 100/100 |
| v0.3，2C4096M | 1020/1020 | 100/100 |
| v0.5.1 问题批次，2C2000M | 979/1020 | 未作为该批次判定项 |

问题侧相同四档合计 979/1020，失败 41 次。[原始 aggregate](/home/lyq/Projects/Verification/cubesandbox/remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/aggregate.json:87)

```json
{
  "total_requests": 1020,
  "total_successful": 979,
  "total_errors": 41
}
```

41 个失败实例中，统计到 40 次 Shim destroy ttrpc timeout 和 107 次 VMM task timeout。

证据：[失败摘要](/home/lyq/Projects/Verification/cubesandbox/remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/summary.txt:1)

```text
failed_ids=41
shim_destroy_ttrpc_timeouts=40
vmm_task_timeouts=107
reset_guest_time_errors=0
```

代表实例 `3563...` 和 `5991...` 都是先完成创建并报告 agent ready，约 30 秒后停止流程失去响应，随后出现 CPU1 RCU stall、ttrpc timeout 和 VM shutdown timeout。[实例时间线](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md:50)

内嵌代表实例 `3563...` 的关键日志：

```text
[56.296944] rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
[56.297961] rcu: 1-...!: (7 GPs behind) ... softirq=1162/1162
[56.298993] rcu: (detected by 0, t=5253 jiffies, g=301, q=8 ncpus=2)
[56.299742] Sending NMI from CPU 0 to CPUs 1:

[66.372270] rcu: rcu_preempt kthread starved for 5253 jiffies!
[66.373592] rcu: Unless rcu_preempt kthread gets sufficient CPU time,
             OOM is now expected behavior.
```

这说明 RCU 日志不是“创建 API 当场失败”的首个错误。它证明的是：从 Template 恢复出的 VM 起初能够运行，之后 CPU1 未完成 RCU 所需的推进，CPU0 仍能运行并检测到异常。

`softirq=1162/1162` 支持 timer/softirq/调度推进停止，但不能单凭该字段证明最初丢失的一定是 timer interrupt。[字段解释](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md:101)

## 4. 两条相关代码链路

### 4.1 Template 构建链路

v0.3 的主要路径是：Cubelet `AppSnapshot` 创建临时 Cubebox，取得快照规格，调用 `cube-runtime snapshot` 写入临时目录，重命名目录，最后销毁临时 Cubebox。

证据与操作顺序位于 v0.3 [appsnapshot.go](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/Cubelet/services/cubebox/appsnapshot.go:214)：快照目录计算在 214-235 行，执行快照在 242-251 行，目录发布在 253-266 行，销毁在 274-307 行。

内嵌主干代码，省略错误分支：

```go
tmpSnapshotPath := snapshotPath + ".tmp"
s.executeCubeRuntimeSnapshot(ctx, sandboxID, spec, tmpSnapshotPath)

os.Rename(tmpSnapshotPath, snapshotPath)
s.Destroy(destroyCtx, annotatedDestroyReq)
```

v0.5 增加了 CubeMaster Template 定义、节点副本和状态持久化。入口在 [CreateTemplate](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeMaster/pkg/templatecenter/store.go:399)，并经 445 行进入副本创建，最终在 601 行调用 Cubelet `AppSnapshot`。

```go
replicas, persistErr := createTemplateReplicasOnNodes(
    ctx, templateID, createReq, nodes, replicaRunOptions{},
)

rsp, err := cubelet.AppSnapshot(
    ctx,
    cubelet.GetCubeletAddr(target.HostIP()),
    &cubeboxv1.AppSnapshotRequest{
    CreateRequest: cubeletReq,
    SnapshotDir:   req.SnapshotDir,
    },
)
```

v0.5 Cubelet 要求 cubecow 后端，随后创建外部内存对象并请求全量快照。实验 C 证明，VMM 的实际内存写入分支还受 `dirty_log` 优先判断控制，不能仅根据请求类型判断。

证据：[cubecow 前置检查](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:84)

证据：[内存对象与 Full snapshot](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:252)

```go
if !storage.IsCowBackend() {
    rsp.Ret.RetMsg = "AppSnapshot requires storage_backend=cubecow"
    return rsp, nil
}

memoryObject, err = storage.CreateTemplateMemoryVolume(
    ctx, templateID, memorySizeBytes,
)

s.executeCubeRuntimeSnapshot(
    ctx, sandboxID, spec, tmpSnapshotPath,
    memoryObject.DevPath, snapshotTypeFull,
)
```

执行成功后，v0.5 依次写 `memory.dev`、创建 rootfs 快照、销毁临时 Cubebox、停用 cubecow 对象，再发布目录。[后处理顺序](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:299)

```go
writeMemoryDevFile(tmpSnapshotPath, memoryObject.DevPath)
storage.CreateTemplateRootfsFromBuild(ctx, templateID)

s.Destroy(destroyCtx, destroyReq)
deactivateCowSnapshotObjects(ctx, stepLog, memoryObject, rootfsObject)

os.Rename(tmpSnapshotPath, snapshotPath)
```

因此，v0.5 的 Template 构建错误可能出现在临时 Sandbox 启动、VMM snapshot、cubecow 内存对象、rootfs 快照、临时 Sandbox 销毁、对象停用或元数据持久化等不同阶段。必须用 job phase 和首个错误区分，不能统一归为 KVM restore 错误。

### 4.2 Sandbox 从 Template 恢复链路

两个版本的 Shim 都是 `launch_vmm -> restore_vm -> 等待 vsock ready`。

v0.3 入口：[start_vm](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/CubeShim/shim/src/sandbox/sb.rs:744)

v0.5 入口：[start_vm](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeShim/shim/src/sandbox/sb.rs:781)

两个版本共有的主干：

```rust
ch.launch_vmm().await?;

if self.by_snapshot() {
    // 这里只展示 restore 成功主干；原代码还包含失败回退分支。
    self.restore_vm().await?;
    snapshot = true;
}
if !snapshot {
    self.boot_vm().await?;
}

let ev = ch.wait_notify(Duration::from_secs(10)).await?;
if CH::NotifyEvent::VsockServerReady != ev {
    return Err("unexpected ready event".to_string());
}
```

关键差异是内存来源。v0.3 只传本地快照目录，v0.5 额外传入 `memory_vol_url`。

v0.3 证据：[RestoreConfig](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/CubeShim/shim/src/sandbox/sb.rs:838)

```rust
// v0.3：内存文件由 source_url 指向的本地快照目录提供。
let config = RestoreConfig {
    source_url: PathBuf::from(snapshot),
    fs: Some(fss),
    net: Some(nets),
    disks: Some(disks),
    pmem: Some(pmems),
    vsock: Some(vsock),
    ..Default::default()
};
```

v0.5 证据：[RestoreConfig](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeShim/shim/src/sandbox/sb.rs:864)

```rust
// v0.5：状态文件仍来自 source_url，内存改由外部 volume 提供。
let config = RestoreConfig {
    source_url: PathBuf::from(snapshot),
    fs: Some(fss),
    net: Some(nets),
    disks: Some(disks),
    pmem: Some(pmems),
    vsock: Some(vsock),
    memory_vol_url: restore_memory_vol_url,
    ..Default::default()
};
```

VMM 内部仍执行相同主序列：读取 config/state，`new_from_snapshot`，恢复 VM 状态，然后 `resume`。

v0.3 证据：[vm_restore](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/hypervisor/vmm/src/lib.rs:647)

v0.5 证据：[vm_restore](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/lib.rs:653)

内嵌 v0.5 VMM 主恢复序列：

```rust
let mut vm = Vm::new_from_snapshot(
    &snapshot,
    vm_config.clone(),
    // 省略未变化的参数
    restore_cfg.memory_vol_url.as_deref(),
)?;

vm.restore(snapshot).map_err(VmError::Restore)?;
vm.resume().map_err(VmError::Resume)?;
```

v0.5 仅在 `new_from_snapshot` 增加外部内存 URL，[具体参数](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/lib.rs:708)。这把差异进一步收敛到“恢复使用的内存产物及其生命周期”，而不是顶层恢复状态机。

## 5. 差异一：ARM64 时钟参数适配被回退

### 5.1 v0.3 的明确适配

v0.3 在默认参数中通过 `#[cfg(not(target_arch = "aarch64"))]` 排除 `no_timer_check`、`noreplace-smp`、`earlyprintk=ttyS0` 和 `mitigations=off`。

证据：[v0.3 config.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/CubeShim/shim/src/hypervisor/config.rs:73)

```rust
let params = vec![
    // ...
    #[cfg(not(target_arch = "aarch64"))]
    "no_timer_check".to_string(),
    #[cfg(not(target_arch = "aarch64"))]
    "noreplace-smp".to_string(),
    // ...
    #[cfg(not(target_arch = "aarch64"))]
    "earlyprintk=ttyS0".to_string(),
    // ...
    #[cfg(not(target_arch = "aarch64"))]
    "mitigations=off".to_string(),
];
```

v0.3 又把 Sandbox 和 snapshot 时钟参数封装为架构感知函数。在 ARM64 构建中，不加入 `highres=off`、`clocksource=kvm-clock`、`clocksource=tsc` 或 `tsc=reliable`。[架构判断](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/CubeShim/shim/src/hypervisor/config.rs:179)

```rust
pub fn add_sandbox_clock_cmdlines(&mut self) -> &mut Self {
    #[cfg(not(target_arch = "aarch64"))]
    {
        self.add_cmdline("highres=off".to_string());
        self.add_cmdline("clocksource=kvm-clock".to_string());
    }
    self
}

pub fn add_snapshot_clock_cmdlines(&mut self, tap: bool) -> &mut Self {
    #[cfg(not(target_arch = "aarch64"))]
    {
        if tap {
            self.add_cmdline("highres=off".to_string());
            self.add_cmdline("clocksource=kvm-clock".to_string());
        } else {
            self.add_cmdline("clocksource=tsc".to_string());
            self.add_cmdline("tsc=reliable".to_string());
        }
    }
    self
}
```

普通 Sandbox 准备 VM 配置时调用该函数，snapshot VM 配置也调用架构感知函数。

普通 Sandbox：[调用位置](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/CubeShim/shim/src/sandbox/sb.rs:695)

snapshot VM：[调用位置](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/CubeShim/shim/src/snapshot/mod.rs:230)

这不是偶然代码形态。提交 `a8710be646abdfb2f6b561861ef808d07266ee54` 的说明明确写明：为 ARM64 避免 x86-only guest cmdline 参数，并为此增加了 ARM64 单元测试。

### 5.2 v0.5 的不一致

v0.5 已正确区分 ARM64 console，但又无条件加入 `earlyprintk=ttyS0` 和 `mitigations=off`。[v0.5 默认参数](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeShim/shim/src/hypervisor/config.rs:73)

```rust
#[cfg(target_arch = "aarch64")]
params.push("console=ttyAMA0,115200".to_string());

// 下列参数没有 ARM64 条件保护。
params.extend([
    // ...
    "earlyprintk=ttyS0".to_string(),
    // ...
    "mitigations=off".to_string(),
]);
```

更关键的是，普通 Sandbox 配置无条件加入 `highres=off` 和 `clocksource=kvm-clock`。[v0.5 sb.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeShim/shim/src/sandbox/sb.rs:731)

```rust
if self.debug {
    vc.add_cmdline("agent.log=debug".to_string());
} else {
    vc.add_cmdline("quiet".to_string());
}
vc.add_cmdline("highres=off".to_string());
vc.add_cmdline("clocksource=kvm-clock".to_string());
```

snapshot VM 在 TAP 模式加入同一组参数，在非 TAP 模式加入 `clocksource=tsc` 和 `tsc=reliable`。[v0.5 snapshot/mod.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeShim/shim/src/snapshot/mod.rs:256)

```rust
if self.tap {
    // ...
    vm_config.add_cmdline("highres=off".to_string());
    vm_config.add_cmdline("clocksource=kvm-clock".to_string());
} else {
    vm_config.add_cmdline("clocksource=tsc".to_string());
    vm_config.add_cmdline("tsc=reliable".to_string());
}
```

这构成确定的 ARM64 适配不一致：v0.3 有意加上的架构保护，在 v0.5 相关链路中不存在。

### 5.3 运行日志确认

v0.5.1 故障环境的 guest 明确打印：

```text
... earlyprintk=ttyS0 ... mitigations=off quiet highres=off clocksource=kvm-clock ...
```

原始位置见[guest Kernel command line](/home/lyq/Projects/Verification/cubesandbox/remote-results/reinstall-v0.5.1-new-kernel-20260720/hello-failure-evidence/cube-shim-req-after-official-c1.log:44)。

同一日志显示 `earlyprintk=ttyS0` 被列为未知参数，`mitigations=off` 则被 ARM64 内核实际应用。

证据：[未知参数](/home/lyq/Projects/Verification/cubesandbox/remote-results/reinstall-v0.5.1-new-kernel-20260720/hello-failure-evidence/cube-shim-req-after-official-c1.log:46)

证据：[mitigations 应用记录](/home/lyq/Projects/Verification/cubesandbox/remote-results/reinstall-v0.5.1-new-kernel-20260720/hello-failure-evidence/cube-shim-req-after-official-c1.log:41)

```text
CPU features: kernel page table isolation forced OFF by mitigations=off
Unknown kernel command line parameters
"LANG=C raid=noautodetect earlyprintk=ttyS0"
```

`clocksource=kvm-clock` 最终没有生效。guest 发现 ARM 架构计数器，并切换到 `arch_sys_counter`。

证据：[计数器发现](/home/lyq/Projects/Verification/cubesandbox/remote-results/reinstall-v0.5.1-new-kernel-20260720/hello-failure-evidence/cube-shim-req-after-official-c1.log:82)

证据：[最终切换](/home/lyq/Projects/Verification/cubesandbox/remote-results/reinstall-v0.5.1-new-kernel-20260720/hello-failure-evidence/cube-shim-req-after-official-c1.log:193)

```text
clocksource: arch_sys_counter: mask: 0x1ffffffffffffff ...
clocksource: Switched to clocksource arch_sys_counter
```

因此不能把故障简单表述为“ARM64 使用了 kvm-clock”。更准确的判断是：v0.5 向 ARM64 传入了错误的 x86 时钟选择，同时还用通用参数 `highres=off` 改变了高精度 timer 模式；前者已回退，后者仍是直接的 timer 行为变量。

### 5.4 与 Template/RCU 的因果联系

Template 构建先启动一个 fresh Sandbox，再暂停并保存其内存、vCPU 和 vGIC 状态。`highres=off` 在 guest 启动阶段生效，因此影响发生在快照之前，并会被所有从该 Template 创建的 Sandbox 共同继承。

RCU 日志显示 CPU1 的 timer/softirq/调度推进异常，而 `highres=off` 直接改变 Linux timer 子系统工作模式，因此最初具有机制相关性。

实验 A 已恢复 v0.3 的 ARM64 `cfg` 保护并重新构建 Template。实际命令行确认参数消失，但 1020 次压力仍有 38 次失败并出现 4 次同型 RCU stall。因此该差异降级为正确性修复和可能的概率调制项，而非当前故障的充分主因。

该实验必须重建 Template，不能只替换运行期 Shim 后复用旧 Template，因为旧 Template 已在原参数下启动并保存。完整过程和反证见第 11.1 节。

## 6. 差异二：Template 内存产物与发布语义改变

### 6.1 v0.3：本地文件并显式同步

v0.3 从快照目录创建 `memory-ranges` 文件。dirty 和 full 路径在返回成功前都调用 `sync_all()`。

证据：[文件创建](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/hypervisor/vmm/src/memory_manager.rs:2557)

证据：[dirty 同步](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/hypervisor/vmm/src/memory_manager.rs:2637)

证据：[full 同步](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/hypervisor/vmm/src/memory_manager.rs:2646)

```rust
let mut memory_file_path = url_to_path(destination_url)?;
memory_file_path.push(String::from(SNAPSHOT_FILENAME));

let memory_file = OpenOptions::new()
    .create_new(true)
    .open(memory_file_path)?;

for range in self.snapshot_memory_ranges.regions() {
    self.save_range_to_file(&memory_file, range, 0)?;
}

memory_file.sync_all()?;
```

Cubelet 在 `cube-runtime snapshot` 成功后，通过同一文件系统中的目录重命名发布快照，[v0.3 发布](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/Cubelet/services/cubebox/appsnapshot.go:242)。

### 6.2 v0.5：外部 cubecow 对象、dirty-log 快路径且不显式同步

v0.5 先创建 Template memory volume，把设备路径以 `--memory-vol file://...` 传给 `cube-runtime`。[参数构造](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:595)

VMM 根据 `memory_vol_url` 打开外部目标。源码先判断 `self.dirty_log`，该条件成立时按 KVM/VMM dirty bitmap 写入并直接返回；只有条件不成立时才匹配 `SnapshotType::Full`。

证据：[目标选择](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/memory_manager.rs:3014)

证据：[v0.5.1 dirty-log 写入](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox-v0.5.1-cntvct-fix/hypervisor/vmm/src/memory_manager.rs:3049)

```rust
let memory_file_target = MemorySnapshotFile::from_snapshot_url(
    destination_url,
    config.memory_vol_url.as_deref(),
)?;

if self.dirty_log {
    let memory_file = memory_file_target.open_for_fresh_write()?;

    let sub_table = MemoryRangeTable::from_bitmap(
        dirty_bitmap, range.gpa, host_page_size(),
    );
    for r in sub_table.regions() {
        self.save_range_to_file(
            &memory_file, r, r.gpa - range.gpa + offset,
        )?;
    }
    return Ok(());
}

match config.snapshot_type {
    SnapshotType::Full => { /* 仅 dirty_log=false 时到达 */ }
}
```

两条写入路径原版都没有 `sync_all()`。更重要的是，实验 C0 的运行日志直接证明 Template 构建走的是前一条 dirty-log 路径，而不是字面上的 Full 分支。

[C0 路径证据](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/template/CubeVmm.log:135)

```text
VmSnapshot(... snapshot_type: Full, memory_vol_url: Some(...))
Saving dirty guest memory to snapshot image file.
VmResume
```

之后 Cubelet 先销毁临时 Sandbox，再停用 memory/rootfs 对象。[v0.5 后处理](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:323)

停用操作在 Go 层直接调用 cubecow engine，没有额外可见的 flush。

证据：[DeactivateByKind](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/storage/cubecow_volume_manager.go:402)

证据：[CGO 调用](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/pkg/cubecow/cubecow.go:319)

```go
func (m *CowVolumeManager) DeactivateByKind(
    ctx context.Context, name, kind string,
) error {
    return m.engine.DeactivateVolume(name)
}

func (e *Engine) DeactivateVolume(name string) error {
    ptr, err := e.openHandle()
    if err != nil {
        return err
    }
    rc := C.cubecow_deactivate_volume(
        C.CubecowEngineHandle(ptr), cName,
    )
    if rc != 0 {
        return makeError(rc)
    }
    return nil
}
```

`sync_all()` 是提交 `42423d743f505f825b0f75577704be4b853aa1a4` 有意删除的。提交说明认为快照位于本地文件系统并通过 page cache 消费，fsync 不必要且显著拖慢快照。

内嵌提交说明：

```text
hypervisor/vmm: drop sync_all() from all snapshot write paths

Snapshot files live on local fs and are consumed via the page cache.
Remove it from pagemap-anon / soft-dirty / dirty-log / full paths since
fsync is unnecessary and was dominating snap wall time.
```

### 6.3 风险判断

同机 page cache 通常可保证关闭后重新读取能看到已写数据，因此“没有 `sync_all()`”不能直接等同于快照损坏。现有日志也没有给出短读、校验失败或 JSON state 损坏证据。

但 v0.5 同时引入外部 cubecow 对象、对象停用和 reflink/快照发布，完成契约已经不同于 v0.3 的单目录本地文件。是否在 `DeactivateVolume` 前需要 flush，取决于 cubecow 的具体实现和底层文件/映射生命周期。

实验 C1 已在实际 dirty-log 路径和普通 Full 路径增加 `sync_all()`、关闭后重开、长度检查和写入区间抽样比对。C1 对象长度正确，49 个写入区间的 139 个抽样页均一致。

但 C1 Template 的并发创建仍有 `16/1020` 失败，并复现同型 RCU stall。因此，无显式 flush 不是当前问题的充分根因，应从高优先级候选降级。

该实验不是全量 2GiB 哈希，只能证明抽样位置和长度正确。若仍怀疑产物内容，应做同一暂停点的全量分块哈希或双份 snapshot diff，而不是继续只增加 fsync。

## 7. 未发现版本回归的 ARM64 KVM 主体

以下文件在 v0.3 `28fe3900` 与 v0.5.0 `30b4e25a` 间逐字节相同：

| 模块 | SHA256/比较结果 | 源码位置 |
| --- | --- | --- |
| vCPU 保存、恢复与运行 | `1be16367...`，相同 | [cpu.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs:419) |
| vGIC 设备封装 | `cefb5b4d...`，相同 | [gic.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/devices/src/gic.rs:1) |
| 中断管理 | `4d8229f1...`，相同 | [interrupt.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/interrupt.rs:1) |
| virtio PCI 中断传输 | `27a09666...`，相同 | [pci_device.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/virtio-devices/src/transport/pci_device.rs:1) |
| `kvm/aarch64` 整目录 | `diff -qr` 无输出 | [KVM ARM64 目录](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/aarch64/mod.rs:1) |
| `arch/aarch64` 整目录 | `diff -qr` 无输出 | [ARM64 arch 目录](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/arch/src/aarch64/mod.rs:1) |

内嵌完整比较指纹：

```text
cpu.rs        1be16367f284ff3ef9158cf149823b70439f0c9dbd32f66bf4c01e19794fba8e
gic.rs        cefb5b4dfb76e5e1e65d54faa17bdca0e6162d978ec1752cfa808ba9da46f9d1
interrupt.rs  4d8229f1dca674a0aedb13020a9385974ea82e35377c55b3d9362cfad3f00832
pci_device.rs 27a09666b838b64d99ce8d0873f1586173c0878612b20c34300b6be0081f635f
kvm/aarch64   diff -qr exit=0
arch/aarch64  diff -qr exit=0
```

两个版本的 VM snapshot 顺序相同：vCPU、memory、ARM64 vGIC、devices。

v0.3 证据：[Vm::snapshot](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/hypervisor/vmm/src/vm.rs:2661)

v0.5 证据：[Vm::snapshot](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/vm.rs:2663)

两个版本共有的关键顺序：

```rust
vm_snapshot.add_snapshot(self.cpu_manager.lock().unwrap().snapshot()?);
vm_snapshot.add_snapshot(self.memory_manager.lock().unwrap().snapshot()?);

#[cfg(target_arch = "aarch64")]
self.add_vgic_snapshot_section(&mut vm_snapshot)?;

vm_snapshot.add_snapshot(self.device_manager.lock().unwrap().snapshot()?);
```

两个版本的 restore 顺序也相同：先 device manager，后 vCPU，再创建并恢复 vGIC，之后恢复设备，最后以 paused 状态启动全部 vCPU 并统一 resume。

v0.3 证据：[Vm::restore](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/hypervisor/vmm/src/vm.rs:2734)

v0.5 证据：[Vm::restore](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/vm.rs:2736)

两个版本共有的关键顺序：

```rust
self.device_manager.lock().unwrap().restore(device_snapshot)?;
self.cpu_manager.lock().unwrap().restore(cpu_snapshot)?;

#[cfg(target_arch = "aarch64")]
self.restore_vgic_and_enable_interrupt(&snapshot)?;

self.device_manager.lock().unwrap().restore_devices(device_snapshot)?;
self.cpu_manager.lock().unwrap().start_restored_vcpus()?;
```

因此，不能再把“v0.5 新改坏了通用 vCPU one-reg/vGIC 顺序”列为首要版本根因。该代码可能有双方共有的潜在缺口，但仅凭源码差异无法解释为什么 v0.3 测试稳定、v0.5 出现 41 次失败。

## 8. v0.5.1 相对 v0.5.0 的 ARM64 改动评估

实际故障批次是 v0.5.1，因此还需检查它是否改变了上述判断。

v0.5.1 的 `cpu.rs` 增加 PMUv3 初始化失败时仅对 `EINVAL` 回退。[PMU 初始化](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox-v0.5.1-cntvct-fix/hypervisor/vmm/src/cpu.rs:411)

```rust
kvi.features[0] |= 1 << kvm_bindings::KVM_ARM_VCPU_PMU_V3;
if let Err(e) = self.vcpu.vcpu_init(&kvi) {
    if !should_retry_without_pmu(&e) {
        return Err(Error::VcpuArmInit(e));
    }
    kvi.features[0] &= !(1 << kvm_bindings::KVM_ARM_VCPU_PMU_V3);
    self.vcpu.vcpu_init(&kvi)?;
}
```

该路径只改变“不支持 PMUv3 时是否重试”。主机能力在同一节点上是确定的，且失败表现为约 5% 的间歇性恢复后 stall，不符合 PMU capability 不支持所产生的确定性初始化失败。因此它不是当前高优先级候选。

v0.5.1 的 `memory_manager.rs` 把 dirty bitmap 的固定 4 KiB 粒度改为宿主页大小。[宿主页大小](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox-v0.5.1-cntvct-fix/hypervisor/vmm/src/memory_manager.rs:195)

```rust
static HOST_PAGE_SIZE: Lazy<u64> = Lazy::new(|| {
    let ret = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
    u64::try_from(ret).expect("invalid host page size")
});

MemoryRangeTable::from_bitmap(dirty_bitmap, range.gpa, host_page_size());
```

AppSnapshot 明确请求 `snapshotTypeFull`，[请求位置](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:283)，但实验 C 证明 `dirty_log=true` 会先进入 dirty bitmap 分支。因此，该修复实际参与 Template 内存写入。

不过，本次宿主页大小为 4096 字节，与旧代码固定的 4096 相同。[环境证据](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/source/host-page-size.txt:1)

```text
getconf PAGESIZE = 4096
architecture     = aarch64
```

因此，该提交纠正了跨页大小平台的语义，但在本机没有改变 bitmap 粒度，不能解释本次 v0.5.1 的间歇性差异。

除上述两类外，v0.5.0 到 v0.5.1 的 `kvm/aarch64`、vGIC、interrupt、`Vm::restore` 和关键 Shim 配置文件均无差异。故障批次没有引入新的 vCPU timer/vGIC 恢复顺序。

## 9. 从 KVM 原理得到的根因推断

### 9.1 KVM 恢复的一致性单位

KVM 只提供 vCPU 和虚拟设备状态接口，用户态 VMM 负责把 guest memory、每个 vCPU 寄存器/系统寄存器、虚拟 timer、vGIC distributor/redistributor 和设备队列组成一个一致快照。

本项目也按这一模型实现：每个 vCPU 调用 `state()` 保存并用 `set_state()` 恢复；恢复 vCPU 后再创建、恢复并 enable vGIC。

证据：[vCPU 状态](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs:419)

```rust
fn snapshot(&mut self) -> Result<Snapshot, MigratableError> {
    let saved_state = self.vcpu.state()?;
    let mut vcpu_snapshot = Snapshot::new(&format!("{:03}", self.id));
    vcpu_snapshot.add_data_section(SnapshotDataSection::new_from_state(
        VCPU_SNAPSHOT_ID,
        &saved_state,
    )?);
    self.saved_state = Some(saved_state);
    Ok(vcpu_snapshot)
}

fn restore(&mut self, snapshot: Snapshot) -> Result<(), MigratableError> {
    let saved_state: CpuState = snapshot.to_state(VCPU_SNAPSHOT_ID)?;
    self.vcpu.set_state(&saved_state)?;
    Ok(())
}
```

证据：[vGIC 恢复](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/vm.rs:2288)

```rust
interrupt_controller.create_vgic(&self.vm, Gic::create_default_config(vcpu_count))?;
self.cpu_manager.lock().unwrap().init_pmu(AARCH64_PMU_IRQ + 16)?;
interrupt_controller.set_gicr_typers(&saved_vcpu_states);
interrupt_controller.restore(gic_snapshot)?;
interrupt_controller.enable()?;
```

只要 memory、CPU timer 状态和 vGIC 的 SGI/PPI 状态不来自同一逻辑时刻，或恢复后的首次 `KVM_RUN` 时序暴露竞态，就可能出现 CPU0 正常、CPU1 不再收到预期 timer/IPI 的现象。

这与日志形态一致：CPU0 仍在运行，并在 `smp_call_function_many_cond -> kick_all_cpus_sync -> freezer_write` 路径等待其他 CPU；CPU1 未完成 RCU quiescent state。

证据：[stack dump 解释](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md:173)

内嵌 CPU0 代表性调用栈：

```text
__cmpwait_case_32
smp_call_function_many
smp_call_function
kick_all_cpus_sync
arch_jump_label_transform_apply
__jump_label_update
jump_label_update
static_key_slow_inc_cpuslocked
freezer_apply_state
freezer_write
```

“一致”不等于“版本差异”。由于低层代码相同，更合理的版本推断是：v0.5 改变了被保存的 guest timer 环境、外部内存产物或宿主恢复条件，从而暴露双方共有的低层时序敏感点。

### 9.2 为什么故障会间歇出现

同一 Template 固定了快照时刻的大部分 guest 状态，但每次 restore 的 vCPU 线程调度、首次进入 KVM 的先后顺序、宿主 CPU/NUMA 落点和中断注入时机仍会变化。

如果快照状态恰好处于跨 CPU 同步的敏感窗口，恢复可能大部分成功，少量实例在 CPU1 的 timer/IPI 恢复窗口失配。这与 41/1020、两个实例相似时间线以及故障集中于 CPU1 的现象相容。

该机制也解释了为什么插桩可能改变故障率：日志和同步点会改变 vCPU 首次运行顺序。但“插桩影响现象”只支持竞态，不能定位竞态位于 vCPU、vGIC、memory publish 还是 guest timer 配置。

### 9.3 为什么销毁错误更像后果

Cubelet 的 `destroy.go` 在 v0.3 与 v0.5 中 SHA256 完全相同。

v0.3 证据：[destroy.go](/home/lyq/Projects/Micro-VM/CubeSandbox-arm64-adaptation/Cubelet/services/cubebox/destroy.go:1)

v0.5 证据：[destroy.go](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/destroy.go:1)

内嵌哈希对比：

```text
ef66a68109bda9b57bb67ef1f8b201c1cc3f4e5b02b82e20a9492dd95dc30956  v0.3 destroy.go
ef66a68109bda9b57bb67ef1f8b201c1cc3f4e5b02b82e20a9492dd95dc30956  v0.5 destroy.go
```

日志顺序也是先出现 guest 无法正常停止，之后才有 ttrpc、shutdown timeout 和清理错误。因此 `destroy sandbox failed`、`not found container` 更适合作为 guest stall 后的级联结果，而不是 CPU1 RCU stall 的起因。

## 10. 根因候选排序

| 优先级 | 候选 | 已确认事实 | 因果判断 |
| --- | --- | --- | --- |
| P0 插桩 | 共有的 vCPU timer/vGIC/跨 CPU 同步竞态 | A-C 均不能消除故障；RCU 栈停在 `smp_call_function_many*` | 低层代码虽非版本新增，但最符合剩余机制证据 |
| P1 控制变量 | 宿主 KVM、irq/调度与并发度交互 | C 串行 100/100，并发 1004/1020 | 故障概率随负载暴露，需要重复、随机化同期对照 |
| P1 深验 | memory volume 非抽样位置的数据一致性 | C1 长度与 139 个抽样页正确 | 显式 flush 非充分根因；仅在做全量分块哈希时继续 |
| P2 正确性修复 | ARM64 `highres=off`/x86 时钟参数回归 | 源码差异和运行命令行均确认；实验 A 后仍失败 | 应修复，但不是本环境下消除故障的充分条件 |
| P2 已降级 | 外部 cubecow memory volume 缺少显式 flush | C1 flush/readback 正常，仍失败 16/1020 | 不是充分根因，单次成功率变化不能证明概率改善 |
| P2 已完成 | 构建端与恢复端 2 x 2 交叉 | 四格均失败，97/95/95/93 | 结果未稳定跟随 Template 或恢复侧二进制 |
| P2 | v0.5.1 PMU fallback | 确有代码变化 | 与间歇性 post-restore stall 不符 |
| P2 | v0.5.1 dirty page 粒度 | 实际经过该逻辑，但宿主页为 4096 | 本机与旧固定 4096 等价 |
| P2 | CubeMaster job/副本元数据 | v0.5 链路明显扩展 | 可解释构建 job 失败，不能直接产生 guest CPU1 RCU stall |
| P3 | Cubelet destroy 实现回归 | 两版本文件相同 | 更符合级联后果 |

这里的 P0/P1 表示验证顺序，不表示已经计算出的根因概率。

## 11. 最小验证矩阵

### 11.1 实验 A：只恢复 ARM64 命令行保护

**状态：已完成，结果为负。** 完整实验摘要和原始证据位于 [实验 A 证据目录](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/EXPERIMENT_SUMMARY.md)。

实验以 `v0.5.1@a164417f497234a0d787cb328b0ae96480b1569b` 为基线，只复用 v0.3 的架构保护。完整差异见 [experiment-a.patch](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/source/experiment-a.patch)。

关键改动直接展开如下：

```rust
#[cfg(not(target_arch = "aarch64"))]
"earlyprintk=ttyS0".to_string(),
#[cfg(not(target_arch = "aarch64"))]
"mitigations=off".to_string(),

pub fn add_sandbox_clock_cmdlines(&mut self) -> &mut Self {
    #[cfg(not(target_arch = "aarch64"))]
    {
        self.add_cmdline("highres=off".to_string());
        self.add_cmdline("clocksource=kvm-clock".to_string());
    }
    self
}
```

同一保护也用于 snapshot 的 TAP/non-TAP 分支，使 ARM64 不加入 `clocksource=tsc` 和 `tsc=reliable`。原生 ARM64 builder 单测通过。

[单测日志](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/build/arm64-unit-test.log)

```text
test hypervisor::config::tests::clock_cmdlines_match_architecture ... ok
test result: ok. 1 passed; 0 failed
```

实验二进制身份见 [artifact-identity.txt](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/build/artifact-identity.txt)：

```text
shim    070da9f4f5066a5beb9671b1217c1df3d2ac0acf4c8a4ee451c4de464a30461c
runtime e28ad40427f05d40d64610bfed97c5a2f5d9b50d4a85a66333199d24fa0520ff
version v0.5.1-arm64-v03-cmdline-guards-expA
```

#### 11.1.1 新 Template 和变量确认

实验重新创建了 `tpl-f88bd35625bd48b5865000a8`，而非复用旧 Template。

[创建响应](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/template/create.json)

[READY 结果](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/template/watch.json)

[Template 信息](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/template/info.json)

```text
template_id   tpl-f88bd35625bd48b5865000a8
job_id        16edada1-6d57-46e7-8266-c54e3848becf
status        READY
spec          cpu=2000m,mem=2000Mi
artifact_id   rfs-742a47cd2ccc3e3c037ec444
ext4_sha256   eb64d9c9bbcf25a928bf26be176ba86f2d21fb0b2f09505d5f6a890cd6e4f4dd
image_digest  sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d
```

Template 构建 guest 的实际命令行见完整 Shim 日志和参数计数。

[完整 Shim 日志](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/template/CubeShim-template-build.log)

[参数计数](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/template/cmdline-verification.txt)

```text
Kernel command line: root=/dev/pmem0 rootflags=dax,errors=remount-ro ro
rootfstype=ext4 panic=1 printk.devkmsg=on console=ttyAMA0,115200
net.ifnames=0 audit=0 LANG=C raid=noautodetect agent.debug_console
agent.debug_console_vport=1026 quiet earlycon=pl011,mmio,0x09000000

highres=off=0
clocksource=kvm-clock=0
clocksource=tsc=0
tsc=reliable=0
earlyprintk=ttyS0=0
mitigations=off=0
```

这组日志证明目标参数已从新 Template 的实际 guest 命令行消失，实验变量生效。

#### 11.1.2 创建压力矩阵结果

实验使用与历史问题批次 SHA256 相同的脚本和 benchmark。

[预检记录](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/create-pressure/preflight.txt)

[aggregate.json](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/create-pressure/template-create-perf/aggregate.json)

```text
runner     55581d9c06a0ee67b47e850b8f02ae294f480feffe55bf2ce61dc9978caf0d4d
cube-bench 8f7402edb027a772f90108db621237146e0756ea65ef729b1552c4822d761eb1
```

| 测试 | 成功/总数 | 错误 | 回收 shim | 清理后 sandbox/shim/task |
| --- | ---: | ---: | ---: | ---: |
| [c1/n20](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/create-pressure/template-create-perf/create-c1-n20.case-summary.json) | 20/20 | 0 | 0 | 0/0/0 |
| [c10/n200](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/create-pressure/template-create-perf/create-c10-n200.case-summary.json) | 191/200 | 9 | 10 | 0/0/0 |
| [c20/n300](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/create-pressure/template-create-perf/create-c20-n300.case-summary.json) | 288/300 | 12 | 12 | 0/0/0 |
| [c50/n500](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/create-pressure/template-create-perf/create-c50-n500.case-summary.json) | 483/500 | 17 | 17 | 0/0/0 |
| 合计 | **982/1020** | **38** | 39 | 每档均清零 |

与问题侧相同脚本的历史结果比较：

| 批次 | 成功/总数 | 错误 | 判断 |
| --- | ---: | ---: | --- |
| 原始问题批次 | 979/1020 | 41 | 基线 |
| 问题侧复测 | 980/1020 | 40 | 基线波动 |
| 实验 A | 982/1020 | 38 | 仍处于约 4% 的同一失败量级 |

实验 A 多 2 至 3 次成功，不能在单批次样本下解释为因果改善。更关键的是，同型 RCU 机制签名没有消失。[签名计数](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/logs/create-pressure-signature-counts.txt)

```text
rcu_stall=4
rcu_kthread_starved=4
shim_destroy_ttrpc_timeout=37
shutdown_event_timeout=37
```

4 个 RCU 实例的完整摘取见 [rcu-instance-key.log](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/create-pressure/rcu-instance-key.log)。代表性实例的关键事件按发生顺序展开：

```text
create req start
agent is ready
create req finish
destroy sandbox failed:ttrpc err: Receive packet timeout
[ 56.159658] rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
[ 56.160684] rcu: 1-...!: (6 GPs behind) ... softirq=1151/1151
[ 56.161818] rcu: (detected by 0, t=5252 jiffies, ... ncpus=2)
[ 66.229024] rcu: rcu_preempt kthread starved for 5252 jiffies!
lr : smp_call_function_many_cond+0x400/0x430
smp_call_function_many+0x20/0x2c
```

这与原问题的 CPU1 stall、约 5250 jiffies、`smp_call_function_many*` 栈一致。目标参数已经不存在而同型错误仍复现，构成实验 A 的直接负证据。

#### 11.1.3 guest 生命周期门禁

100 次门禁不只检查 API 创建。每次创建后通过 CubeMaster 直连 TAP guest 的 `49999/health`，要求 HTTP 200，再删除 Sandbox。

[逐次结果](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/lifecycle-100/results/results.jsonl)

[汇总](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/lifecycle-100/results/summary.json)

[预检记录](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/lifecycle-100/preflight.txt)

```text
lifecycle runner sha256 = 91fca43d5f39dcf43b3ebfce2510baa137adaef2632aa0675d803902b531b0c4
```

```text
create       97/100
guest HTTP   97/100
delete       97/100
lifecycle    97/100
失败序号     34, 50, 93
失败形式     SandboxException("408: b''"), 每次约 30.00 s
```

失败序号、实例和 Shim 事件的关联见 [failed-instances-key.log](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/lifecycle-100/failed-instances-key.log)。

```text
34 -> 165ad6124a904e2bb947890092f1bbcd
50 -> 945bc2c3c3f4462985f589d0ece91dbf
93 -> ce4a86a3d2c540b7baea3eea74e322e8

create req finish
destroy sandbox failed:ttrpc err: Receive packet timeout
wait vm shutdown event failed:Receive event timeout after 1000ms
```

三个失败 shim 在清理前各占约 174% 至 186% CPU。该阶段没有捕获 RCU dump，因此只能确认相同的高 CPU 和清理超时形态，不能把三次失败直接等同为已记录的 RCU stall。

[签名计数](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/logs/lifecycle-100-signature-counts.txt)

#### 11.1.4 边界、恢复与判定

本次宿主内核为 `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-8394b32f`。原始 `979/1020` 和复测 `980/1020` 均来自同一节点、同一内核、同一镜像 digest 和同一 2C/2000MiB 规格。

历史控制组 v12 在该内核上使用未修改的 `a164417f4` 源码和相同 builder 重建新 Template，串行生命周期为 `99/100`，失败实例同样出现 CPU1 RCU/timer stall。[v12 证据](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md:549)

实验后已恢复实验前的 `v16` 诊断 shim 和原始 runtime，服务 active，sandbox/shim/task 为 `0/0/0`。[恢复记录](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/restore/post-restore-state.txt)

```text
shim     e7e9433b...d5bbb  v0.5.1-arm64-timer-readback-v16
runtime  d1e2db00...a7a9  v0.5.1 (a164417f...)
sandboxes=[]  shims=0  tasks=0
template tpl-f88bd35625bd48b5865000a8 READY
```

实验 Template 有意保留，以供实验 B 交叉恢复。完整证据校验表见 [SHA256SUMS](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/SHA256SUMS)。

最终判定：ARM64 命令行保护是必要的正确性修复，但不是本环境下消除该故障的充分条件。实验 A 不支持把 x86 参数视为当前 RCU stall 的主要单一根因，后续应进入实验 B/C。

### 11.2 实验 B：构建端与恢复端交叉

**状态：已完成，四格均复现失败。** 完整摘要位于 [实验 B/C 摘要](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/EXPERIMENT_B_C_SUMMARY.md)。

两种 Template 分别由原版和实验 A 的命令行修正版构建；恢复侧也分别使用两种 Shim/VMM。每格执行 100 次创建、直连 TAP guest `/health`、删除。

[原始矩阵](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-b/matrix-summary.json)

[特征计数](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-b/matrix-summary-normalized.tsv:1)

| 恢复侧 | 构建侧 | 生命周期 | RCU stall | destroy/shutdown timeout |
| --- | --- | ---: | ---: | ---: |
| 原版 | 原版 | 97/100 | 2 | 3/3 |
| 原版 | 命令行修正版 | 95/100 | 1 | 5/5 |
| 命令行修正版 | 原版 | 95/100 | 2 | 4/4 |
| 命令行修正版 | 命令行修正版 | 93/100 | 0 | 6/6 |

关键原始内容：

```text
restore-original_build-original  97/100  rcu=2  ttrpc=3
restore-original_build-patched   95/100  rcu=1  ttrpc=5
restore-patched_build-original   95/100  rcu=2  ttrpc=4
restore-patched_build-patched    93/100  rcu=0  ttrpc=6
```

结果没有稳定跟随 Template，也没有稳定跟随恢复侧。四格的几个百分点差异可能包含自然波动，不能用于声称某组合更好；但四格均失败足以否定“任一侧单独决定故障”的强假设。

最后一格有 6 次超时但没有 RCU dump，说明 RCU 日志是 stall 的强证据，却不是每次失败都必然输出的完备计数器。

### 11.3 实验 C：内存产物 flush 与读回

**状态：已完成；回读正常，但并发故障仍存在。**

#### 11.3.1 C0：先验证插桩是否命中

C0 只修改普通 Full 分支。Template `tpl-0b98496b4e2945da9e04f5b6` 为 READY，但没有新增标记。

[C0 VMM 日志](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/template/CubeVmm.log:135) 展开的关键顺序为：

```text
VmSnapshot(... snapshot_type: Full, memory_vol_url: Some(...))
Saving dirty guest memory to snapshot image file.
VmResume
```

源码原因是 `self.dirty_log` 判断位于 `match config.snapshot_type` 之前，并在完成 dirty bitmap 写入后直接返回。C0 因此没有验证到实际 Template 内存路径。

#### 11.3.2 C1：覆盖实际 dirty-log 路径

C1 同时覆盖 dirty-log 和普通 Full 路径：写后 `sync_all()`，关闭写句柄，只读重开并检查长度；对每个实际写入区间取首、中、尾最多 4KiB，与暂停 guest memory 逐字节比较。

[C1 补丁](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/source/experiment-c1-dirty-log-and-full.patch:126) 的关键内容：

```rust
memory_file.sync_all()?;
drop(memory_file);

let (observed_len, sample_count, checksum) =
    self.verify_snapshot_ranges_readback(
        &memory_file_target, total_size, &written_ranges,
    )?;
```

新 Template `tpl-a2591c59834c4899ba75eaab` 为 READY。[连续 VMM 日志](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/template/c1/CubeVmm.log:135) 直接给出：

```text
VmSnapshot(... snapshot_type: Full, memory_vol_url: Some(...))
Saving dirty guest memory to snapshot image file.
Experiment C dirty-log snapshot sync/readback verified:
expected_bytes=2097152000, observed_bytes=2097152000,
written_ranges=49, samples=139, fnv64=0xbb9a8c7b6d0dffa2
VmResume
```

因此，本次对象长度正确，49 个写入区间的 139 个抽样页全部匹配，没有短读或 mismatch。[提取证据](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/template/c1/sync-readback-verification.txt:1)

#### 11.3.3 C1 恢复结果

恢复侧切回原始 v0.5.1 v12 控制组，只使用 C1 Template。100 次完整生命周期为 `100/100`，五项异常特征均为 0。

[生命周期汇总](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/validation/lifecycle-100/results/summary.json:15)

[生命周期特征计数](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/validation/lifecycle-100/signature-counts.txt:1)

同一 Template 的 1020 次并发矩阵为：[压力汇总](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/validation/official-create-pressure/results/aggregate.json:5)

| 并发/请求数 | 成功 | 失败 | 回收残留 shim |
| ---: | ---: | ---: | ---: |
| 1/20 | 20 | 0 | 0 |
| 10/200 | 197 | 3 | 4 |
| 20/300 | 293 | 7 | 7 |
| 50/500 | 494 | 6 | 6 |
| 合计 | 1004 | 16 | 17 |

[并发日志特征](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/validation/official-create-pressure/signature-counts.txt:1)

```text
rcu_stall=1
rcu_kthread_starved=1
destroy_ttrpc_timeout=17
shutdown_event_timeout=17
```

串行 `100/100` 与并发 `1004/1020` 不矛盾：前者没有命中低概率故障，后者重新暴露同型错误。单批次成功率高于历史结果不能归因于 flush，因为没有重复、随机化的同期对照。

最终判定：读回异常假设未得到支持；显式 flush 后同型故障仍存在，足以证明“缺少 `sync_all()`”不是充分根因。

C1 是抽样校验而非 2GiB 全量哈希，不能彻底排除其他位置的数据错误。若继续验证产物，应改做全量分块哈希或双份 snapshot diff。

### 11.4 实验 D：同机、同内核、同镜像

当前 v0.3 与问题侧的宿主内核后缀、Template 和 guest image 并非完全一致。[差异边界](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_V030_V050_TEMPLATE_COMPARISON_REPORT_20260721.md:176)

应在同一宿主上固定 KVM、CPU/NUMA、guest kernel、rootfs 和网络，只切换构建/恢复二进制。否则源码差异与宿主差异仍会混杂。

### 11.5 实验 E：最后再做 KVM 状态插桩

若 A-C 均不能收敛，再在 snapshot、restore、每个 vCPU 首次 `KVM_RUN` 前后记录 ARM virtual timer 寄存器、MP state、MPIDR、vGIC redistributor 的 SGI/PPI pending/active 状态，以及 vCPU0/vCPU1 首次进入时间。

该实验成本较高，而且插桩会改变时序。它应放在上层两个确定差异排除之后，而不是作为第一步。

## 12. 最终评估

v0.3 与 v0.5 在 ARM64 Template 链路上存在明确不一致。实验 A 已证明恢复命令行保护后，目标参数从新 Template 消失，但 `982/1020` 和 4 次同型 RCU stall 表明该修正不足以消除当前故障。

实验 B 的四格结果为 `97/100`、`95/100`、`95/100`、`93/100`。故障既不稳定跟随构建侧，也不稳定跟随恢复侧，说明命令行差异不能单独解释问题，且没有发现明确的两侧格式不兼容组合。

实验 C 纠正了“请求 Full 就一定执行 Full 写入分支”的假设。实际 `dirty_log=true` 使 Template 构建先走 dirty bitmap 快路径，这也意味着 v0.5.1 的 dirty page 粒度代码确实参与链路。

C1 已证明 cubecow memory volume 在 `sync_all()` 后长度正确，139 个抽样页与暂停 guest memory 一致。但并发创建仍为 `1004/1020`，并复现 RCU stall 和 17 次清理超时。

因此，无显式 flush 应从高优先级根因降级。它仍是产物持久化契约上的工程风险，但不是当前故障的充分原因；单批次失败数下降也不能在没有同期重复对照时解释为因果改善。

ARM64 KVM/vCPU/vGIC 主恢复代码在 v0.3 与 v0.5.0 间相同。现阶段更准确的根因表述不是“v0.5 改坏了 KVM restore 顺序”，而是“v0.5 的上层输入或产物链路可能暴露了已有 ARM64 多 vCPU 恢复时序敏感性”。

下一步应进入实验 E 的低层观测，而不是继续盲改 flush 或命令行。应在 snapshot、restore 和每个 vCPU 首次 `KVM_RUN` 前后记录 ARM timer、MP state、MPIDR、vGIC redistributor SGI/PPI 状态及 vCPU 首次进入时间。

远端已恢复实验前 v16 shim 和原始 runtime。服务 active，sandboxes/shims/tasks 为 `0/0/0`；C0/C1 两个 Template 均保留为 READY。

[恢复证据](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/final-restore-state.txt:1)
