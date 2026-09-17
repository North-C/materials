# CubeSandbox ARM64 多 vCPU Template 恢复故障完整实验分析报告

## 1. 报告信息

- 报告日期：2026-07-18
- 实验节点：`root@192.168.25.90`
- 实验周期：2026-07-16 至 2026-07-18
- CubeSandbox 起始部署版本：v0.5.0 one-click standalone
- 当前诊断源码基线：v0.5.1，commit `a164417f497234a0d787cb328b0ae96480b1569b`
- 当前结论：**基础服务健康，但 ARM64 2 vCPU Template 恢复稳定性未达到正式 benchmark 前置门槛**
- 主证据目录：`/home/lyq/cube-bench-formal-arm64-2c4g-retest-20260717-175203/diagnostics`

本文档取代 2026-07-17 形成的阶段性分析结论。阶段性报告当时判断 Cloud Hypervisor
PR #8343 很可能可以解决问题；后续 v1-v9 实验表明，该 PR 修复的 guest clock 问题
确实存在，但仅回移相关逻辑不能完全消除当前 CubeSandbox fork 上的多 vCPU 恢复卡死。

## 2. 执行摘要

实验得到以下结论：

1. Benchmark 镜像和镜像内 benchmark 套件不是本次 Sandbox 创建故障的根因。2026-07-16
   SDK 正式套件 19/19 完成，镜像归档、远端镜像 ID 和 registry digest 已固定。
2. 故障发生在 benchmark 命令执行之前，即 2 vCPU ARM64 Template 的 VM Snapshot
   恢复和 guest agent 初始化阶段。
3. 1 vCPU Template 连续 10/10 创建、销毁成功；2 vCPU 在 2 GiB、4 GiB 和 8 GiB
   内存规格下均可间歇性失败，变量明确收敛到多 vCPU 恢复路径。
4. 失败时 guest 出现 CPU1 timer softirq/RCU stall，随后 CubeShim 与 guest agent 之间的
   ttrpc `Task/State`、`Task/Kill`、时间重置和销毁操作超时，并留下高 CPU CubeShim。
5. XFS、TAP 池、network-agent、探针端口、内存容量、NUMA 跨节点、Kubernetes 干扰和
   guest PMU 已分别检查，均不能解释或消除故障。
6. 回移 Cloud Hypervisor PR #8343 后，100 次创建仍有 2 次失败。后续加入精确 CNTVCT
   快照、1 秒追赶上限、VM 级 `KVM_ARM_SET_COUNTER_OFFSET` 和 seccomp allowlist 后，
   最佳结果为全新 Template 99/100，仍未达到 100/100 门槛。
7. 在恢复 offset 后额外重写 vtimer CVAL/CTL 的 v9 实验明显恶化为 1/5，已回滚。
8. 当前保留 v7 实验二进制用于后续诊断。静态集群状态干净，但不能据此判定 2 vCPU
   Template 功能正常；正式 benchmark 因可靠性门槛未通过而暂停。

因此，当前高置信度判断是：

> Cloud Hypervisor PR #8343 所修复的 ARM64 guest counter 跨 Snapshot/Restore 连续性问题
> 是故障链的一部分，但 CubeSandbox 当前 Cloud Hypervisor fork、恢复顺序、其他 vtimer/GIC
> 状态或宿主 KVM 兼容路径中仍存在残余问题。单独增加该 PR 不能视为完整修复。

## 3. 实验范围与验收标准

本轮实验关注的是正式 benchmark 的前置条件，而不是 benchmark 分数本身。主要测试动作是：

1. 从指定 Template 创建 Sandbox。
2. 等待 VM Snapshot 恢复、guest agent 就绪和 CubeSandbox 初始化完成。
3. 在可创建的测试中执行简单命令验证 CPU、内存和 envd。
4. 删除 Sandbox。
5. 检查 Cube API、CubeShim、TAP 和错误日志是否回到干净状态。

正式测试的稳定性门槛定义为：

- 全新 2 vCPU / 4 GiB Template 连续创建、执行、销毁 100 次，成功率 100%。
- Cube API 中 Sandbox 数量最终为 0。
- 不存在残留 `containerd-shim-cube-rs`。
- 不出现 `reset guest time failed`、ttrpc timeout、RCU stall 或 timer handling 错误。
- TAP 池数量保持 500，network-agent 无对应分配失败。

小规模 5 次冒烟只用于尽早发现明显回归。v7 和 v8 均出现过 5/5 成功、随后 100 次门禁
失败，证明少量成功样本不能作为集群健康依据。

## 4. 环境与输入身份

### 4.1 宿主机

| 项目 | 值 |
| --- | --- |
| 架构 | `aarch64` |
| CPU | Kunpeng 950 7592C，2 Socket，384 逻辑 CPU |
| NUMA | 4 节点，每节点 96 个逻辑 CPU |
| 内存 | 约 2.2 TiB |
| 内核 | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray` |
| KVM API | 12 |
| `KVM_CAP_COUNTER_OFFSET` | `KVM_CHECK_EXTENSION(227)=1` |
| Cubelet 数据盘 | `/dev/nvme3n1` |
| 文件系统 | XFS，挂载于 `/data/cubelet` |
| TAP 池 | 500 个持久 TAP，`one_queue vnet_hdr persist` |

KVM capability 复核证据：

```text
KVM_GET_API_VERSION=12
KVM_CHECK_EXTENSION(227)=1
```

证据文件：`diagnostics/kvm-counter-offset-capability-20260718.txt`。

### 4.2 Benchmark 镜像

| 项目 | 值 |
| --- | --- |
| Tag | `cube-bench-suite:upstream-arm64-20260716-build-noperf` |
| Registry 引用 | `127.0.0.1:5000/cube-bench-suite:upstream-arm64-20260716-build-noperf` |
| Docker image ID | `sha256:be5ca179ddb9de93d296a43d96fd2084de0e5d064b349f0ca0215eb9a03a9905` |
| Registry digest | `sha256:67f24e83e6c0a516c868e7bb90cee246f76ef134e94ec3af3b36b62a122af173` |
| 本地 tar SHA256 | `b23c5640d9348922c85ebcdd9aff3cce537233a587e3dcaeb524b5547289bb26` |
| 架构 | `arm64` |

本地 tar 为
`cube-bench-suite_upstream-arm64-20260716-build-noperf.tar.gz`。远端 Docker image ID 与
registry 引用解析到同一 image ID，避免了可变 tag 指向其他镜像的问题。

### 4.3 当前部署的实验 CubeShim

```text
containerd-shim-cube-rs v0.5.1-arm-clock-vm-offset-cap1s-v7
(a164417f497234a0d787cb328b0ae96480b1569b-clockvmcap1s7)
SHA256=2dd6f1a728e0ba1b78d86be85091bb0bd68f6d5f27617f4e4f37c08c9bec02b8
```

规范路径和兼容链接均解析到：

```text
/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
```

## 5. 第一阶段：正式 benchmark 暴露稳定性问题

2026-07-16 使用 2 vCPU / 4 GiB Template 执行了 SDK 正式套件和 CubeSandbox 核心操作
测试。结果并非“集群完全可用”：

| 测试 | 结果 | 解释 |
| --- | --- | --- |
| SDK benchmark 套件 | 19/19 完成 | 镜像内 benchmark 可以运行 |
| Template 创建，并发 1-50 | 成功率 95.0%-97.5% | 创建路径存在间歇性失败 |
| 单机密度最后一批 | 93.8% | 出现 shim 泄漏及 TAP 压力 |
| Snapshot/Rollback/Clone/Pause-Resume 矩阵 | 0/25 完成目标测量 | 均在创建或恢复准备阶段失败 |

主要错误统计包括 30 次 `context deadline exceeded`、24 次
`reset guest time failed` 和 2 次 `reset reseed random dev failed`。SDK 19/19 只能证明成功创建
的 Sandbox 可以运行 benchmark，不能证明 Template 创建路径可靠。

该阶段原始结果位于：

```text
/home/lyq/cube-bench-formal-arm64-2c4g-20260716-212309
```

对应报告为 `CUBESANDBOX_FORMAL_TEST_REPORT_ARM64_20260716.md`。

## 6. 第二阶段：基线复现与变量收敛

### 6.1 1 vCPU 对照

1 vCPU Template 连续 10 次 create-delete 全部成功：

```text
attempt=1,create=OK,...,elapsed=0.051
attempt=2,create=OK,...,elapsed=0.047
...
attempt=10,create=OK,...,elapsed=0.045
```

创建延迟为 45-51 ms，10 次均能正常销毁。另一次 1 vCPU / 4 GiB 功能门禁结果为：

```json
{"status":"PASS","create_s":0.112,"command_exit":0,
 "stdout":"nproc=1\nmem_kb=4024440\nenvd=ok\n"}
```

证据：

- `diagnostics/template-1cpu-create10.log`
- `diagnostics/resource-tap-isolation-20260718-112612/pretest-cluster-health/functional-gate-1c4g/result.json`

### 6.2 2 vCPU 与内存规格对照

| Template 规格 | 结果 | 关键观察 |
| --- | --- | --- |
| 1C / 2 GiB | PASS | `nproc=1`，网络正常 |
| 2C / 2 GiB | FAIL | 8.03 秒返回 `reset guest time failed` |
| 2C / 4 GiB | FAIL | 8.03 秒返回同类 ttrpc timeout |
| 2C / 8 GiB 单次 | PASS | 约 62 ms，可正常运行命令 |
| 2C / 8 GiB 重复 | 第 3 次 FAIL | 前两次约 51-52 ms，第 3 次 30 秒 408 |

2C / 2 GiB 的 SDK 原始异常为：

```text
500: CubeMaster returned error code -1: failed to run container
80319aefde6f4021bd765c5c7588e59d: failed to create shim task:
Others("Other: Create sandbox failed:reset guest time failed:
ttrpc err: Receive packet timeout Elapsed(())")
```

2C / 8 GiB 重复结果为：

```json
{"attempt":1,"status":"PASS","create_s":0.0512,"probe_exit":0}
{"attempt":2,"status":"PASS","create_s":0.052,"probe_exit":0}
{"attempt":3,"status":"FAIL","elapsed_s":30.0026,"error":"408: b''"}
```

这组结果排除了“2 GiB 内存不足”作为根因，也说明故障是间歇性的；提高内存只改变复现概率。

### 6.3 NUMA/CPU 亲和性

宿主机有 4 个 NUMA 节点。实验将 Cubelet 的全部 45 个线程从 CPU `0-383` 约束到
NUMA0 的 CPU `0-95`，然后执行 2C / 4 GiB 创建。第 1 次即在 8.09 秒失败：

```text
Create sandbox failed:reset guest time failed:
ttrpc err: Receive packet timeout Elapsed(())
```

因此，跨 NUMA 调度不是该问题的充分解释。

证据：

```text
diagnostics/resource-tap-isolation-20260718-112612/
  affinity-taskset-numa0/c2-m4g-run5/results.jsonl
```

### 6.4 TAP 与 network-agent

对失败实例 `80319aefde6f4021bd765c5c7588e59d` 的关联日志显示，network-agent 在失败之前已
成功完成网络配置：

```text
network-agent EnsureNetwork request:
sandbox_id=80319aefde6f4021bd765c5c7588e59d interfaces=1 routes=1 arps=1 port_mappings=2

network-agent register cubevs tap:
sandbox_id=80319aefde6f4021bd765c5c7588e59d ifindex=12 sandbox_ip=10.100.0.6
```

同一 TAP `z10.100.0.6` 的状态变化为：

```text
before: <NO-CARRIER,BROADCAST,MULTICAST,UP> state DOWN
after:  <BROADCAST,MULTICAST,UP,LOWER_UP> state UP
```

随后 CubeShim 才在 guest 时间重置处超时。测试前后 TAP 始终是持久设备：

```text
z10.100.0.6: tap one_queue vnet_hdr persist
```

所有 100 次门禁结束时 `taps=500`。因此 TAP 成功分配并已与 VM 建链，TAP 参数不是本轮
timer/RCU 卡死的根因。历史 TAP 污染会放大高密度失败，但与此处单实例多 vCPU 故障不同。

### 6.5 Kubernetes、XFS 与静态服务

为排除干扰，远端 kubelet 已停止并禁用：

```text
kubelet_active=inactive
kubelet_enabled=disabled
k8s_processes=0
k8s_ports=0
```

Cube API、Cubelet、CubeMaster、CubeProxy 和 network-agent 保持 active；XFS 数据盘正常，
且静态预检时无 Sandbox、无 CubeShim、500 个 TAP、0 个 failed systemd unit。故障在关闭
Kubernetes 后仍可复现。

## 7. 关键错误证据与故障链

### 7.1 CubeShim 创建与销毁失败

```text
Create sandbox failed:reset guest time failed:
ttrpc err: Receive packet timeout Elapsed(())

destroy sandbox failed:ttrpc err:
Receive packet timeout Elapsed(()), but nothing to do

wait vm shutdown event failed:
Receive event timeout after 1000ms, but nothing to do
```

这说明 VM 已进入 Snapshot 恢复流程，但 guest agent 无法继续处理控制请求，失败后的正常
销毁流程也不可用。

### 7.2 Guest RCU 与 timer softirq

代表性 guest 日志：

```text
rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
rcu: Possible timer handling issue on cpu=1 timer-softirq=110
```

PMU-off 的 v8 仍出现：

```text
[   22.533961] rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
[   32.592968] rcu: Possible timer handling issue on cpu=1 timer-softirq=111
```

v9 回归实验中同样集中在 CPU1：

```text
[   23.516017] rcu: INFO: rcu_preempt detected stalls on CPUs/tasks:
[   33.542425] rcu: Possible timer handling issue on cpu=1 timer-softirq=35
```

### 7.3 VMM ttrpc 超时

```text
method handle /containerd.task.v2.Task/State got error timed out
method handle /containerd.task.v2.Task/Kill got error timed out
```

失败实例通常在约 30.3 秒结束门禁请求，并留下一个 CubeShim。例如 v7 全新 Template
失败轮次 91 的耗时为 30300 ms。

### 7.4 故障链

综合日志顺序，故障链为：

```text
Template Snapshot 恢复
  -> network-agent 成功配置 TAP，VM 侧接口建立 LOWER_UP
  -> guest 次级 vCPU 的 timer/RCU 停止正常推进
  -> guest agent 无法处理时间重置或后续 task 状态请求
  -> CubeShim ttrpc timeout
  -> CubeMaster 创建返回 500/408
  -> 正常 kill/delete/destroy 同样超时
  -> 管理面删除实例，但高 CPU CubeShim 可能残留
```

`reset guest time failed` 是最早稳定出现的用户可见错误点，不等于时间重置 RPC 本身就是
唯一根因；guest 在该调用时已经表现出 timer/RCU 异常。

## 8. 社区修复调查

### 8.1 Cloud Hypervisor PR #8343

上游 PR：`arm64: correct the guest clock across snapshot/restore and migration`

- URL：<https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343>
- 状态：已合并
- 合并时间：2026-06-19T03:47:58Z
- Merge commit：`eb1c64e4f01c9dd882e623795b139a129691ccfa`
- 规模：6 commits，10 个文件，498 additions，48 deletions
- 本地 patch SHA256：`fb3bcb9e2893d134f1d233e32ee6e32c213029ca4457599f786e689a760b7ba3`

PR 解决的问题是 ARM64 没有 x86 kvmclock 同类恢复辅助接口，旧实现仅 round-trip
`CNTVCT_EL0`，导致冷恢复或迁移后 guest 时间落后整个停机时间。其核心方案是：

1. Snapshot 时记录 guest counter、host wall clock 和 counter frequency。
2. Restore 前计算停机时间并推进 CNTVCT。
3. 对 Linux 6.4 以后 VM-wide vtimer offset 使用 boot vCPU 的 ONE_REG 写入，旧内核写所有 vCPU。
4. 在 vCPU 运行前完成恢复，并对时钟读取失败和 CNTFRQ 不匹配显式报错。

需要注意，上游 PR 明确讨论过 `KVM_CAP_COUNTER_OFFSET` VM ioctl，但最终选择 ONE_REG。
当前主机报告 capability 227 可用，而本地 ONE_REG 和 VM ioctl 两种路径均未达到 100/100。

### 8.2 CubeSandbox PMU PR #746

社区 PR：`hypervisor: make arm64 PMU exposure configurable`

- URL：<https://github.com/TencentCloud/CubeSandbox/pull/746>
- 当前状态：open，未合并
- 功能：支持 `cube.vm.pmu=off`，避免请求 `KVM_ARM_VCPU_PMU_V3`

本轮按该思路构建 PMU-off 的 v8，用于验证 PMU 是否触发多 vCPU 恢复卡死。结果仍为
98/100，并有 CPU1 timer handling issue，因此 PMU 不是根因。

## 9. v1-v9 补丁实验矩阵

### 9.1 结果总表

| 版本 | 主要变化 | Template | 样本 | 通过 | 失败 | 残留 shim | 结论 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| v1 | 回移 PR #8343 风格的完整时钟状态；cap 主机写 boot vCPU；完整 elapsed | 旧 2C4G | 100 | 98 | 2 | 2 | 不通过；大量恢复后 RCU 日志 |
| v2 | 保存并恢复精确 snapshot CNTVCT，避免完整 Template age 追赶 | 旧 2C4G | 100 | 98 | 2 | 2 | 不通过；失败仍为 30 秒卡死 |
| v3 | ONE_REG 路径将 elapsed catch-up 限制为 1 秒 | 旧 2C4G | 100 | 99 | 1 | 1 | 不通过；概率下降但未归零 |
| v4 | 完整 elapsed，向所有 vCPU 执行 ONE_REG | 旧 2C4G | 5 | 4 | 1 | 1 | 快速失败；CPU1 timer issue |
| v5 | 改用 VM 级 `KVM_ARM_SET_COUNTER_OFFSET`，完整 elapsed | 旧 2C4G | 100 | 99 | 1 | 1 | **实验无效**；ioctl 被 seccomp 拦截 |
| v6 | v5 + seccomp allowlist，使 VM ioctl 实际执行 | 旧 2C4G | 100 | 98 | 2 | 2 | 不通过；RCU/timer 问题仍在 |
| v7 | v6 + elapsed catch-up 上限 1 秒 | 旧 2C4G | 100 | 97 | 3 | 3 | 不通过 |
| v7 | 同一二进制，新建全新 Template | 新 2C4G | 100 | 99 | 1 | 1 | 当前最佳有效结果，但不通过 |
| v8 | v7 + 强制关闭 guest PMU | 新 2C4G | 100 | 98 | 2 | 2 | PMU 排除 |
| v9 | v7 + offset 后重写 vtimer CVAL/CTL | 新 2C4G | 5 | 1 | 4 | 4 | 明显回归，已回滚 |

100 次门禁失败轮次和耗时：

| 批次 | 失败轮次 | 失败耗时 |
| --- | --- | --- |
| v1 | 47、49 | 30296、30317 ms |
| v2 | 51、93 | 30299、30294 ms |
| v3 | 85 | 30294 ms |
| v5 | 90 | 30298 ms；但功能被 seccomp 阻断，不能评价 ioctl |
| v6 | 31、59 | 30296、30298 ms |
| v7 旧 Template | 15、42、76 | 30296、30295、30297 ms |
| v7 新 Template | 91 | 30300 ms |
| v8 新 Template | 47、99 | 30297、30297 ms |

v4 的第 2 次在约 30 秒失败。v9 的第 1-4 次失败，第 5 次成功。

### 9.2 v1：上游方案直接回移

v1 是验证“仅回移上游时钟修复是否足够”的关键实验。结果为 98/100，并留下 2 个 shim。
日志统计包含 98 条 RCU stall 和 63 条 `Stall ended before state dump start`。这些是日志行数，
并不代表 98 次创建失败；多数创建最终返回成功，但恢复时因完整 Template age 被解释为 elapsed，
guest 经历了可恢复 RCU 报警。

关键失败仍为：

```text
destroy sandbox failed:ttrpc err: Receive packet timeout Elapsed(())
method handle /containerd.task.v2.Task/State got error timed out
method handle /containerd.task.v2.Task/Kill got error timed out
```

结论：PR #8343 对 guest clock 语义有必要，但在当前 fork 上单独回移不够。

### 9.3 v2-v4：CNTVCT 值、elapsed 和 per-vCPU 写入策略

- v2 避免将完整 Template 年龄作为 guest catch-up，成功恢复中的 RCU 噪声明显减少，但仍有
  2 次 30 秒失败。
- v3 将 catch-up 限制为 1 秒，结果改善为 99/100，但仍留下一个卡死 shim。
- v4 尝试向所有 vCPU 写 ONE_REG，5 次中第 2 次失败，并记录：

```text
rcu: Possible timer handling issue on cpu=1 timer-softirq=110
```

结论：只改变 CNTVCT 目标值或写入 vCPU 数量不能完全解决问题。

### 9.4 v5-v7：VM 级 counter offset 与 seccomp

本机 Linux 6.6 支持 `KVM_CAP_COUNTER_OFFSET=227`，因此 v5 改用 VM fd 上的
`KVM_ARM_SET_COUNTER_OFFSET`。但 v5 未把 ioctl `0x4010aeb5` 加入 seccomp allowlist，
每个恢复实例都记录：

```text
Error signal: SIGSYS, possible seccomp violation.
```

所以 v5 的 99/100 不能证明 VM ioctl 有效。v6 加入精确 ioctl allowlist 后才是有效测试。
v6 结果为 98/100，并再次出现：

```text
rcu: Possible timer handling issue on cpu=1 timer-softirq=110
destroy sandbox failed:ttrpc err: Receive packet timeout Elapsed(())
```

v7 在 v6 基础上把 catch-up 限制为 1 秒。旧 Template 97/100；为排除 Template 过旧，
使用同一 v7 二进制新建 `tpl-59ebb6c88f6c41a9ad55da91`，结果为 99/100。全新 Template
降低了失败数量，但没有消除问题。

### 9.5 v8：关闭 PMU

v8 按社区 PR #746 的方向关闭 guest PMU，并新建
`tpl-ca101c482e58406f8348ccbd`。5 次冒烟全部成功，但 100 次门禁在第 47 和 99 次失败，
结果为 98/100。失败 VM 仍有 CPU1 timer softirq 和 RCU stall。

结论：PMU 对该故障不是必要条件。

### 9.6 v9：重写 CVAL/CTL 的反向验证

v9 在 VM offset 恢复后读取并写回每个 vCPU 的 virtual timer CVAL/CTL，尝试强制 KVM
重新评估 timer。全新 Template `tpl-619e16f0e9ad429989fb849c` 的结果为：

```text
attempt=1 rc=1
attempt=2 rc=1
attempt=3 rc=1
attempt=4 rc=1
attempt=5 rc=0
```

4 个失败实例均记录 CPU1 timer handling issue，并留下 4 个 shim。该方案显著恶化故障，
说明 offset 与 pending timer/CVAL/CTL 的关系不能通过简单的寄存器原值重写修复。v9 已撤回，
远端二进制和本地/远端源码均恢复到 v7 逻辑。

## 10. 实验二进制身份

| 版本 | SHA256 |
| --- | --- |
| 官方 v0.5.1 | `c3d9bd094a8fc9d86b4b06a684ee574f8f8e023479c1f4088b8597c2a6c03d46` |
| v1 | `7d03f4ac62e93ba80ef8ee5f506d8056cc508f6e7b5a6aed9b0c93c1d947b541` |
| v2 | `ca86ee7b9dbc6c2cb0dcb19311b50a11a775e3ac44ce4317ac6ab2c0a02108f1` |
| v3 | `af11f9bbc3643909c32391ac50b859ab6031950af8e60521e130783f433d348e` |
| v4 | `72f97717ecfd1c40af58fa0eca1f0ab527236974157161a55fe26f9d8450aeb8` |
| v5 | `ce2a9b745c9fa364420e82cd4a7e613b407972491ad24e5f8780fae279f0b3f8` |
| v6 | `1e1f88ada11064f78d9a3c9cdbe290e965e2cc97b94cf9405fd603edb52f8e5d` |
| v7 | `2dd6f1a728e0ba1b78d86be85091bb0bd68f6d5f27617f4e4f37c08c9bec02b8` |
| v8 | `bca6784b6e0eb01b37698c1257285752d2621276fd411c99fb9376e15413f474` |
| v9 | 未单独保留二进制；执行日志版本为 `v0.5.1-arm-clock-vtimer-refresh-v9` |

远端备份目录：

```text
diagnostics/clockfix-full-deploy/
```

## 11. 已排除项与剩余假设

### 11.1 已通过对照实验排除为主要根因

| 因素 | 证据 | 判断 |
| --- | --- | --- |
| Benchmark 镜像 | SDK 正式套件可运行；镜像 ID/digest 固定 | 不是创建卡死根因 |
| 探针端口 | 49983/49999 均出现过同类失败 | 不是单一端口问题 |
| XFS | `/data/cubelet` 已稳定使用 XFS | 不是当前 timer 卡死原因 |
| TAP 参数 | 失败 VM 的 TAP 已成功注册并 `LOWER_UP` | 不是当前根因 |
| 内存不足 | 2C8G 仍间歇性失败 | 排除 |
| NUMA | 绑定单 NUMA 节点仍失败 | 排除 |
| Kubernetes 干扰 | kubelet inactive/disabled 后仍失败 | 排除 |
| PMU | PMU-off v8 仍 98/100 | 排除 |
| Template 陈旧 | v7 全新 Template 仍 99/100 | 不是唯一原因 |

### 11.2 已确认和高置信度判断

- **已确认**：问题依赖 ARM64 多 vCPU Template/Snapshot 恢复；1 vCPU 是稳定功能规避。
- **已确认**：失败集中表现为 CPU1 timer/RCU stall，随后 guest agent/ttrpc 失去响应。
- **已确认**：PR #8343 风格的 CNTVCT 修复和 VM offset ioctl 均不能在当前 fork 上达到 100%。
- **高置信度**：残余故障仍位于 ARM64 generic timer、多 vCPU snapshot state 和恢复顺序附近。

### 11.3 尚未确认的残余根因

以下方向仍是候选，不应在缺少新对照前写成确定事实：

- CubeSandbox 使用的旧 Cloud Hypervisor fork 缺少 PR #8343 之外的 ARM64 timer/GIC、
  vCPU resume 或 snapshot state 修复。
- CNTVCT offset、每 vCPU CVAL/CTL 和 GIC pending timer interrupt 的恢复顺序不一致。
- 当前 openEuler 6.6 KVM 实现与该旧 VMM 的 VM-wide counter offset 使用方式存在兼容差异。
- vCPU 创建、restore 和 unpark 之间存在低概率竞态，因此主要表现为 1%-3% 间歇失败。

v9 的明显回归支持“timer state 之间存在耦合”，但不能单独区分是 VMM 顺序问题、GIC 状态
问题还是内核 KVM 行为。

## 12. 当前状态

报告形成前最终复核结果：

```text
cubelet=active
api={"status":"ok","sandboxes":0}
network_agent=ok
kubelet=inactive
kubelet_enabled=disabled
cube_shims=0
taps=500
failed_units=0
```

当前状态只能解释为“静态服务干净”。由于有效的最佳 2 vCPU 门禁仍是 99/100，不能标记为
“正式测试可用”。正式 benchmark 未继续运行，以避免把重试成功样本或故障恢复开销混入性能数据。

## 13. 后续建议

建议按以下顺序继续：

1. 不再叠加未经上游验证的单寄存器补丁；保留 v7 作为当前对照基线。
2. 比较 CubeSandbox 当前 Cloud Hypervisor fork 与包含 PR #8343 的完整上游版本，重点审查
   ARM64 vCPU state、generic timer、GIC save/restore、pause/resume 和线程启动顺序的成组变更。
3. 优先尝试升级完整 Cloud Hypervisor 依赖或成组回移相关 ARM64 修复，而不是只 cherry-pick
   PR #8343。
4. 使用更新或不同发行版的 ARM64 KVM 内核做 A/B 对照，区分 VMM 与宿主内核问题。
5. 增加 guest 内每个 vCPU 的 CNTVCT、CVAL、CTL、IRQ pending 和恢复时间点采样；采样必须在
   不改变时序的条件下进行。
6. 每个候选修复先跑 5 次快速门禁，再跑全新 Template 100 次硬门禁；只有 100/100 且无
   shim/RCU/timer 错误才恢复正式 benchmark。
7. 后续还应补充 2、4、8 vCPU，以及 Snapshot/Restore、Pause/Resume、Rollback、Clone 各
   至少 20 次回归。

重试创建或使用 1 vCPU 可以用于 SDK/镜像功能检查，但不应作为正式 2 线程 sysbench 和多核
语言运行时 benchmark 的验收方案。

## 14. 实验限制

- 所有实验在同一台 ARM64 主机和同一宿主内核上完成，尚无第二台 ARM64 主机交叉验证。
- 大多数门禁是串行 create-delete；并发负载只在前期正式测试中覆盖。
- 部分版本使用旧 Template，v7-v9 通过新建 Template 补充了 Template age 对照。
- `fatal_signatures` 和 RCU 统计是日志行数，不等价于失败实例数；通过/失败数以
  `results.csv`、`results.txt` 和 `summary.txt` 为准。
- v5 的 ioctl 被 seccomp 阻断，结果只用于发现 seccomp 依赖，不能用于评价 VM offset 修复。
- 尚未完成完整新版 Cloud Hypervisor 或新内核 A/B 测试，因此残余问题的精确代码位置仍未确定。

## 15. 证据索引

远端根目录：

```text
/home/lyq/cube-bench-formal-arm64-2c4g-retest-20260717-175203/diagnostics
```

关键证据：

| 内容 | 相对路径 |
| --- | --- |
| 1 vCPU 10 次对照 | `template-1cpu-create10.log` |
| 资源、TAP、NUMA、Kubernetes 隔离 | `resource-tap-isolation-20260718-112612/` |
| 2C2G SDK 原始失败 | `resource-tap-isolation-20260718-112612/c2-m2g-run/result.log` |
| TAP 状态前后对照 | `resource-tap-isolation-20260718-112612/c2-m2g-run/links-before.txt`、`links-after-failure.txt` |
| Sandbox/TAP 关联日志 | `resource-tap-isolation-20260718-112612/tap-correlation/` |
| NUMA0 绑定失败 | `resource-tap-isolation-20260718-112612/affinity-taskset-numa0/c2-m4g-run5/` |
| v1 上游方案门禁 | `clockfix-upstream-v1-gate-2c4g-100/` |
| v2 精确 CNTVCT 门禁 | `clockfix-cube-v2-gate-2c4g-100/` |
| v3 1 秒 ONE_REG 门禁 | `clockfix-cube-v3-gate-2c4g-100/` |
| v4 all-vCPU 快速门禁 | `clockfix-all-vcpu-v4-gate-2c4g-5/` |
| v5 seccomp 阻断证据 | `clockfix-vm-offset-v5-gate-2c4g-100/` |
| v6 VM offset 有效门禁 | `clockfix-vm-offset-seccomp-v6-gate-2c4g-100/` |
| v7 旧 Template 门禁 | `clockfix-vm-offset-cap1s-v7-gate-2c4g-100/` |
| v7 全新 Template 门禁 | `clockfix-v7-fresh-template-gate-2c4g-100/` |
| v8 PMU-off 门禁 | `clockfix-v8-nopmu-fresh-gate-2c4g-100/` |
| v9 CVAL/CTL 回归 | `clockfix-v9-vtimer-refresh-gate-2c4g-5/` |
| 各版本二进制备份 | `clockfix-full-deploy/` |
| KVM capability 复核 | `kvm-counter-offset-capability-20260718.txt` |
| Benchmark 前置健康检查 | `CUBESANDBOX_PRE_BENCHMARK_HEALTH_20260718.md` |

本地相关文档：

- `CUBESANDBOX_FORMAL_TEST_REPORT_ARM64_20260716.md`
- `CUBESANDBOX_ARM64_MULTIVCPU_SNAPSHOT_RESTORE_ANALYSIS_20260717.md`，阶段性报告
- `CUBESANDBOX_PRE_BENCHMARK_HEALTH_20260718.md`

精简证据归档位于结果根目录：

```text
CUBESANDBOX_ARM64_MULTIVCPU_EVIDENCE_20260718.tar.gz
CUBESANDBOX_ARM64_MULTIVCPU_EVIDENCE_20260718.tar.gz.sha256
```

归档文件清单位于：

```text
diagnostics/CUBESANDBOX_ARM64_MULTIVCPU_EVIDENCE_FILES_20260718.txt
```

## 16. 最终结论

截至 2026-07-18，CubeSandbox 在该 ARM64/OpenEuler 6.6 主机上的 2 vCPU Template 恢复
故障尚未解决。Cloud Hypervisor PR #8343 修复了一个真实且相关的 guest clock 问题，回移后
也改变了 RCU 表现和失败概率，但有效测试的最佳结果仍为 99/100。TAP、资源规格、NUMA、
Kubernetes、PMU 和旧 Template 已通过对照排除为主要根因。

当前应将状态标记为：

> **基础组件健康；ARM64 多 vCPU Snapshot/Restore 存在低概率但严重的 timer/RCU 卡死；
> PR #8343 单独回移不充分；正式 benchmark 前置门禁不通过。**

在完成完整 Cloud Hypervisor/ARM64 timer-GIC 恢复路径升级或进一步根因修复，并通过全新
2 vCPU Template 100/100 无错误门禁之前，不应继续生成正式性能验收结果。
