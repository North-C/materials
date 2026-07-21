# CubeSandbox ARM64 多 vCPU Template 恢复故障问题说明

> 整理日期：2026-07-21  
> 证据周期：2026-07-16 至 2026-07-21  
> 当前状态：问题未解决，正式 benchmark 前置门禁不通过

## 1. 一分钟结论

CubeSandbox 在指定 ARM64/openEuler 6.6 节点上，从 2 vCPU Template 创建 Sandbox 时会间歇性卡死。问题发生在 VM Snapshot 恢复和 guest 初始化阶段，早于 benchmark 命令执行。

失败时，guest 的 CPU1 出现 timer softirq/RCU stall，随后 guest agent 不再响应。外部首先看到 `reset guest time` 或 `reseed random dev` 超时。

销毁请求也会超时，并可能残留一个持续占用约 100% CPU 的 CubeShim。

1 vCPU 连续 10/10 成功；2 vCPU 在 2、4、8 GiB 下均出现过失败。社区原版重建控制组为 99/100，已有时钟、counter offset、PMU、同步及等待类实验均未达到 100/100 验收门槛。

当前最强证据指向 ARM virtual timer、timer PPI 与 vGIC 恢复顺序附近的时序竞态。但 timer PPI 和首次 `KVM_RUN` 的直接状态尚未采集，因此这仍是高优先级假设，不是最终根因。

当前部署的 v16 含详细诊断日志。它会改变故障结果，属于有观察效应的诊断版本，不能作为正式修复。

## 2. 影响与判定

| 项目 | 说明 |
| --- | --- |
| 影响平台 | ARM64，多 vCPU Template/Snapshot 恢复 |
| 主要场景 | 从 2 vCPU Template 创建 Sandbox |
| 用户可见结果 | 创建返回 HTTP 500/408，约 8 秒或 30 秒超时 |
| 系统后果 | guest agent 失联，正常销毁失败，可能残留高 CPU CubeShim |
| 不受影响的对照 | 1 vCPU Template 在已测样本中稳定 |
| 当前判定 | 基础服务健康，但 2 vCPU 恢复可靠性不达标 |

验收标准是全新 2 vCPU / 4 GiB Template 连续 100 次完成创建、命令和删除，且无 RCU/timer 错误、无残留 Shim、Sandbox 最终为 0。现有无插桩方案均未通过。

## 3. 测试环境

| 项目 | 值 |
| --- | --- |
| 实验节点 | `root@192.168.25.90` |
| 宿主架构 | `aarch64` |
| CPU | Kunpeng 950 7592C，2 Socket，384 逻辑 CPU |
| NUMA / 内存 | 4 个 NUMA 节点，约 2.2 TiB |
| 宿主内核 | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray` |
| KVM | API 12，`KVM_CAP_COUNTER_OFFSET=1` |
| CubeSandbox 基线 | v0.5.1，commit `a164417f497234a0d787cb328b0ae96480b1569b` |
| 起始部署 | v0.5.0 one-click standalone，后续以 v0.5.1 诊断 |
| 数据盘 | `/dev/nvme3n1`，XFS 挂载到 `/data/cubelet` |
| 网络 | 500 个持久 TAP，`one_queue vnet_hdr persist` |

主要复现覆盖 2 vCPU / 2、4、8 GiB Template。正式 benchmark 使用固定 ARM64 镜像，image ID、registry digest 和本地归档 SHA256 均已固化。

实验期间 kubelet 已停止并禁用；Cube API、Cubelet、CubeMaster、CubeProxy 和 network-agent 保持运行。测试前确认无 Sandbox、无 Shim、TAP 数量为 500、无 failed systemd unit。

## 4. 测试操作

### 4.1 基本复现

1. 确认 CubeSandbox 基础服务健康，清空 Sandbox 和残留 CubeShim。
2. 选择 2 vCPU Template，串行创建 Sandbox。
3. 创建成功后执行简单命令，确认 CPU 数、内存和 envd 可用。
4. 删除 Sandbox，并检查 Sandbox、Shim 和 TAP 是否恢复到测试前状态。
5. 重复 5 次冒烟或 100 次门禁，关联采集 CubeMaster、Cubelet、CubeShim/VMM 和 guest console 日志。

实际异常具有概率性。少量 5/5 成功不能判定稳定，已有版本在冒烟通过后仍在 100 次门禁中失败。

### 4.2 对照与收敛实验

| 对照项 | 操作 | 结果 |
| --- | --- | --- |
| vCPU 数 | 1 vCPU 与 2 vCPU 对比 | 1 vCPU 10/10；2 vCPU 可失败 |
| 内存 | 2、4、8 GiB | 三种规格均出现过 2 vCPU 失败 |
| NUMA | 将 Cubelet 线程绑定 NUMA0 | 首次测试仍失败 |
| 网络 | 核对 TAP 分配、注册和 `LOWER_UP` | 网络先成功，随后 guest reset 超时 |
| Kubernetes | 停止并禁用 kubelet | 问题仍复现 |
| PMU | v8 关闭 guest PMU | 98/100，仍有 CPU1 timer stall |
| Template 年龄 | 使用全新 Template | 最佳 99/100，未消除问题 |
| 构建环境 | 相同 builder 重建社区原版 v12 | 99/100，排除构建器差异 |

## 5. 测试结果

### 5.1 代表性结果

| 测试 | 结果 | 说明 |
| --- | ---: | --- |
| SDK benchmark 套件 | 19/19 | 只说明成功创建的 Sandbox 可运行 benchmark |
| 初始 Template 创建测试 | 95.0%-97.5% | 创建路径已有间歇性失败 |
| Snapshot/Rollback/Clone/Pause-Resume 矩阵 | 0/25 | 在创建或恢复准备阶段失败 |
| 1 vCPU 连续 create-delete | 10/10 | 稳定对照 |
| 社区原版重建控制组 v12 | 99/100 | 失败后 CPU1 RCU/timer stall，残留 1 个 Shim |
| PR #8343 风格与 v1-v9 最佳有效结果 | 99/100 | 时钟相关修复有改善，但不完整 |
| v9 重写 CVAL/CTL | 1/5 | 显著恶化，已回滚 |
| 纯插桩 v15 | 100/100 | 存在观察效应，不能作为修复 |

### 5.2 最强 A/B 结果

固定使用历史确定性坏 Template `tpl-3394a026ea014a34a3002eb0`，保持主机和测试时段相邻，仅切换 CubeShim 二进制：

| 二进制 | 结果 | 关键现象 |
| --- | --- | --- |
| v15 纯日志插桩 | 5/5 成功 | 无残留 Sandbox/CubeShim |
| v16 SET 后读回插桩 | 单次成功 | KVM 读回的 CTL/CVAL 与保存值一致 |
| 社区原版 v0.5.1 | 0/1，8.0878 秒失败 | CPU1 RCU stall、timer handling issue、残留 Shim |

社区原版失败后 Shim 在 8 秒和 86 秒时都约占用 100% CPU。相同 Template 在插桩版本成功、切回原版立即失败，证明诊断日志自身改变了竞态窗口。

## 6. 错误日志与故障顺序

### 6.1 用户可见错误

```text
500: CubeMaster returned error code -1: failed to run container
Create sandbox failed:reset guest time failed:
ttrpc err: Receive packet timeout Elapsed(())
```

同一问题也可能首先表现为：

```text
Create sandbox failed:reset reseed random dev failed:
ttrpc err: Receive packet timeout Elapsed(())
```

`reset guest time` 和 `reseed random dev` 是恢复后最早的 guest RPC，错误表示 guest 此时已失去响应，不代表这两个 RPC 本身就是根因。

### 6.2 guest 与销毁错误

```text
rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
rcu: Possible timer handling issue on cpu=1 timer-softirq=122

method handle /containerd.task.v2.Task/State got error timed out
method handle /containerd.task.v2.Task/Kill got error timed out

destroy sandbox failed:ttrpc err:
Receive packet timeout Elapsed(()), but nothing to do
```

### 6.3 已确认的故障顺序

```text
恢复 Template Snapshot
  -> network-agent 完成 TAP 配置，接口进入 LOWER_UP
  -> CPU1 的 timer/RCU 不再正常推进
  -> guest agent 无法处理 reset 或 task RPC
  -> CubeShim ttrpc 超时
  -> CubeMaster 返回 500/408
  -> kill/delete/destroy 继续超时
  -> 管理面移除记录，但高 CPU CubeShim 可能残留
```

## 7. 涉及代码链路

以下链路以社区 v0.5.1 源码和 CodeGraph AST 索引为准。历史报告中把 `SandBox::create_snapshot` 视为入口的结论已作废；该函数在仓库内无调用者。

### 7.1 Template 构建与 Snapshot

```text
Cubelet AppSnapshot
  -> executeCubeRuntimeSnapshot
  == 启动短命 cube-runtime 子进程 ==>
cube-runtime snapshot --app-snapshot
  -> snapshot::cmd::execute
  -> Snapshot::handle
  -> Snapshot::do_app_snapshot
  == HTTP/1.1 over /run/vc/vm/<id>/chapi ==>
containerd-shim-cube-rs 内的 VMM
  -> ApiRequest::VmPause
  -> ApiRequest::VmSnapshot
  -> ApiRequest::VmResume
```

`Vm::pause` 等待每个 vCPU 完成一次 immediate-exit `KVM_RUN` 并置 ACK，但不保证线程已经执行到 `park()`。`Vm::snapshot` 随后按 CPU -> memory -> vGIC -> devices 保存状态。

关键文件：

- `Cubelet/services/cubebox/appsnapshot.go`
- `CubeShim/cube-runtime/src/main.rs`
- `CubeShim/shim/src/snapshot/mod.rs`
- `hypervisor/vmm/src/vm.rs`
- `hypervisor/vmm/src/cpu.rs`

### 7.2 从 Template 创建 Sandbox

```text
SandBox::create_sandbox
  -> start_vm
  -> restore_vm
  -> VMM ApiRequest::VmRestore
     -> Vm::restore
        -> DeviceManager 骨架恢复
        -> CpuManager::restore
           -> 各 vCPU set_state(core -> sys_regs -> MP state)
        -> 创建并恢复 vGIC，启用中断路由
        -> 恢复设备
        -> 以 paused=true 启动 vCPU 线程
     -> Vm::resume，清 pause flag 并 unpark
  -> connect_agent
  -> reset_guest(set time -> reseed random)
  -> agent CreateSandbox
```

VMM 在同一个 `VmRestore` 请求内立即执行 `Vm::resume`。app snapshot 恢复分支不等待额外的 `RestoreReady` 或 `VsockServerReady`，因此首个 guest RPC 紧邻 vCPU 首次正常运行窗口。

ARM64 `set_state()` 按快照原顺序写 system registers。已观测顺序是 `TIMER_CTL -> TIMER_CNT -> TIMER_CVAL`，随后才恢复 vGIC。

由此形成三个重点窗口：

| 窗口 | 范围 | 风险 |
| --- | --- | --- |
| W1 | 写 CTL 到写完 CNT/CVAL | timer 可能在完整 counter/deadline 写回前启用 |
| W2 | vCPU timer 状态完成到 vGIC 恢复完成 | timer PPI line 与 redistributor 状态可能发生竞态 |
| W3 | unpark 到首次正常 `KVM_RUN` | pending、PSTATE、MP state 组合决定 CPU1 是否收到首个 tick |

关键文件：

- `CubeShim/shim/src/sandbox/sb.rs`
- `CubeShim/shim/src/hypervisor/cube_hypervisor.rs`
- `hypervisor/vmm/src/lib.rs`
- `hypervisor/vmm/src/vm.rs`
- `hypervisor/vmm/src/cpu.rs`
- `hypervisor/hypervisor/src/kvm/mod.rs`
- `hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs`

## 8. 可能原因与证据等级

### 8.1 已确认事实

- 问题依赖 ARM64 多 vCPU Template/Snapshot 恢复，1 vCPU 是当前稳定功能规避。
- 失败集中表现为 CPU1 timer/RCU stall，之后 guest agent 和 ttrpc 失去响应。
- PR #8343 风格的 guest counter 修复和 VM counter offset 均未达到 100%。
- KVM 接受了测试样本的 timer one-reg 写入，未静默改写 CTL/CVAL。
- 诊断日志或读回操作能使确定性坏 Template 成功，存在明显观察效应。

### 8.2 高优先级推测

P0：快照中 timer 为已启用且 deadline 已过期时，恢复代码先写 CTL，再写 CNT/CVAL，可能过早形成 timer PPI。

P0：timer 状态先于 vGIC distributor/redistributor/pending/active 状态恢复，两者合并存在竞态，导致 CPU1 丢失或无法处理首次 timer interrupt。

P1：vCPU unpark、首次 `KVM_RUN`、GIC ready、PSTATE.I 和 MP state 之间仍可能存在顺序问题。

P1：counter offset、每 vCPU timer 状态与当前 openEuler 6.6 KVM/旧 Cloud Hypervisor fork 之间可能存在兼容差异。

### 8.3 已排除为主要根因

Benchmark 镜像、单一探针端口、XFS、TAP 参数、内存不足、跨 NUMA 调度、Kubernetes 干扰、guest PMU、Template 陈旧和构建工具链差异均已通过对照排除。

v13/v14 的 50 ms 等待没有命中真实生效路径：v13 改错函数；v14 虽改到 `do_app_snapshot`，但未部署承载该代码的 `cube-runtime`。两者不能用于评价“静止窗口”假设。

## 9. 实验确认过程摘要

1. 正式 benchmark 暴露创建成功率不足，确认故障发生在命令执行前。
2. 通过 1/2 vCPU、内存、NUMA、TAP、Kubernetes 和 PMU 对照，把变量收敛到多 vCPU Snapshot 恢复。
3. v1-v9 测试 guest clock、精确 CNTVCT、counter offset、seccomp 和 CVAL/CTL，最佳仍为 99/100。
4. v10/v11 的同步改动产生确定性坏 Template；v12 原版重建 99/100，排除 builder 差异。
5. v15/v16 插桩让坏 Template 成功；同一时段切回社区原版立即失败，将范围收敛到 timer/vGIC 时序竞态。
6. v16 读回证明 KVM 没有丢弃 CTL/CVAL 写入，但尚未观测 PPI line、pending/active 和首次 `KVM_RUN`。

## 10. 当前状态与下一步

截至 2026-07-21，远端基础服务静态健康，Sandbox 和 Shim 均已清空，但运行的是诊断用 v16：

```text
version=v0.5.1-arm64-timer-readback-v16
commit=12d301b15c27df976b1a84a6a38ca70ba097c63a
sha256=e7e9433b0789fef6f56343da10cfbc8ff5b7a59380e494ac2799055802dd5bbb
```

下一步应做最小无日志 A/B：先验证 `TIMER_CTL` 最后恢复；再在 vGIC 恢复后重放 CTL，并设置等量延迟对照，区分“顺序修复”和“延迟掩盖”。

同时需要采集 CPU1 timer PPI line/pending/active、GICR/ICC 状态以及首次 `KVM_RUN` 前后事件。只有找到第一处状态分歧，才能确定修复层级。

候选修复必须去掉详细日志，通过全新 2 vCPU Template 100/100、历史坏 Template、无 RCU/timer 错误、无残留 Shim，之后才能恢复正式 benchmark。

## 11. 证据入口

综合实验与结论：

- [完整实验报告](CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md)
- [Pause/Resume/Restore 校正后调用链](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ANALYSIS_20260721.md)
- [阶段细化与路径勘误](CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md)
- [静止窗口与 KVM 机制](CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_20260720.md)

本地原始证据：

- [v15 100 次结果](remote-results/arm64-vcpu-sync-v10-20260720/v15-timer-state-trace/serial-until-failure-100/summary.txt)
- [v15 历史坏 Template 5 次结果](remote-results/arm64-vcpu-sync-v10-20260720/v15-timer-state-trace/deterministic-bad-v10-template/gate-5/summary.json)
- [v16 timer SET/读回日志](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/v10-template-smoke-1/timer-trace.log)
- [社区原版同 Template A/B 失败](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/ab-control/official-v10-template-smoke-1/run.log)
- [社区原版 CPU1 RCU/timer 日志](remote-results/arm64-vcpu-sync-v10-20260720/v16-timer-readback/ab-control/official-v10-template-smoke-1/shim-key-events-through-40s.log)
- [2026-07-18 精简证据归档清单](remote-results/arm64-multivcpu-experiment-20260718/CUBESANDBOX_ARM64_MULTIVCPU_EVIDENCE_FILES_20260718.txt)

## 12. 限制

所有实验均在同一台 ARM64 主机和同一宿主内核上完成，尚未做第二台 ARM64 主机、新版 Cloud Hypervisor 或不同内核的完整 A/B。

当前没有 timer PPI line/pending/active 与首次 `KVM_RUN` 的直接证据，因此不能把 P0 假设写成最终根因，也不能把固定等待或诊断插桩当作修复。
