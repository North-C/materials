# CubeSandbox ARM64 多 vCPU Template 恢复故障分析

分析日期：2026-07-17  
测试节点：`root@192.168.25.90`  
当前分析版本：CubeSandbox v0.5.1，提交 `a164417f497234a0d787cb328b0ae96480b1569b`  
关联历史版本：CubeSandbox v0.5.0  
结论状态：**根因已形成高置信度判断，修复尚待多 vCPU 回归验证**

## 1. 摘要

当前故障发生在 ARM64 环境中基于 Template 的 Sandbox 启动阶段。使用 2 vCPU
Template 从预制 VM Snapshot 恢复时，guest 内的辅助服务无法及时响应，CubeShim
随后在 `reset guest time` 或 `reset reseed random dev` 调用处发生 ttrpc 超时。失败 VM
中同时观察到 Linux 内核 `rcu_preempt detected stalls`，且卡顿集中在次级 vCPU。

将其他条件保持不变，仅把 Template 从 2 vCPU 改为 1 vCPU 后，连续 10 次
create-delete 全部成功，单次创建约 45～51 ms，未再观察到 RCU stall。这一对照结果
表明故障与 ARM64 多 vCPU Snapshot 恢复强相关，而不是 benchmark 镜像、Template
探针、XFS 数据盘或单纯的网络资源池问题。

结合 Cloud Hypervisor 上游已合并的 PR #8343，当前高置信度根因是：

> CubeSandbox 当前内置的 Cloud Hypervisor 在 ARM64 Snapshot 恢复时直接回放
> `CNTVCT_EL0` 状态，没有正确处理停机期间经过的时间及 Linux 6.4 以后 VM 级
> vtimer offset 的多 vCPU 一致性，导致次级 vCPU 的虚拟定时器或时间推进异常。

时间异常会使 guest 内核调度、RCU grace period、定时器和 ttrpc 服务处理停滞；
`reset guest time failed` 是故障暴露点，不是根因本身。

## 2. 影响范围

已确认或高度相关的影响包括：

- ARM64、KVM、2 个及以上 vCPU 的 Template/Snapshot 恢复。
- 基于 Template 创建 Sandbox 的成功率和创建延迟。
- Snapshot、Rollback、Clone、Pause/Resume 等依赖 VM 状态恢复的测试。
- 失败后的 CubeShim 回收，可能留下管理面不可见的 shim 或运行态资源。
- 依赖稳定多核环境的正式 benchmark，当前结果不能作为性能验收数据。

当前未发现证据表明 x86_64 存在同一问题。上游修复也明确将该问题限定在
ARM64/KVM 路径，x86_64 继续使用已有的 kvmclock 恢复机制。

## 3. 故障现象

### 3.1 管理面和 CubeShim

典型错误包括：

```text
reset guest time failed: ... ttrpc ... timeout
reset reseed random dev failed: ... ttrpc ... timeout
context deadline exceeded
```

调用顺序上，CubeShim 已经恢复 VM，随后通过 guest agent 执行时间重置和随机设备
reseed。由于 guest 调度或定时器已异常，ttrpc 请求无法在超时前完成。

### 3.2 Guest 内核

失败 VM 中观察到类似日志：

```text
rcu: rcu_preempt detected stalls on CPUs/tasks
```

卡顿主要出现在 CPU1。该现象与“单 vCPU 正常、多 vCPU 失败”的对照一致：
CPU0 能继续推进并不足以保证共享 guest clock、各 vCPU 虚拟定时器和 RCU 状态一致。

### 3.3 后续影响

当 guest agent 不响应时，CubeShim 对 VM 内 task 的 kill、delete 和状态查询也可能
超时，进而留下残余 shim。TAP 池耗尽和探针失败会放大后续错误，但它们是连锁影响，
不是本轮对照实验指向的首要根因。

## 4. 证据链

| 证据 | 结果 | 支持的判断 |
| --- | --- | --- |
| Benchmark 镜像直接运行及 SDK 套件 | 镜像可运行，历史正式套件 19/19 完成 | 排除镜像静态构建或 entrypoint 为主因 |
| 更换 49983/49999 探针 | 故障仍出现 | 排除单一探针端口为主因 |
| XFS 数据盘和 TAP 池修复后重试 | ttrpc 超时仍出现 | XFS 缺失和 TAP 污染不是当前根因 |
| 新建 2 vCPU / 4 GiB / 2G Template | Snapshot 恢复失败，并出现 CPU1 RCU stall | 问题可在干净的多 vCPU Template 上复现 |
| 新建 1 vCPU / 4 GiB / 2G Template | 连续 10/10 create-delete 成功，约 45～51 ms | 将变量收敛到多 vCPU 恢复路径 |
| Cloud Hypervisor PR #8343 | 专门修复 ARM64 guest clock 和多 vCPU 恢复一致性 | 与本地症状、架构和触发条件吻合 |

证据强度判断：

- **已确认**：故障依赖 ARM64 多 vCPU Snapshot 恢复；1 vCPU 是有效临时规避。
- **高置信度推断**：`CNTVCT_EL0`/vtimer offset 恢复不一致导致次级 vCPU 定时器停滞。
- **尚待确认**：移植上游修复后，2 vCPU 及更高规格能否在当前内核和 CubeSandbox
  fork 上完全消除超时及 shim 残留。

## 5. 根因机制

ARM64 guest 通过架构虚拟计数器 `CNTVCT_EL0` 获得时间基准。旧实现会将 Snapshot
中保存的计数器值原样写回。这样会产生两个相关问题：

1. Snapshot 停机期间经过的真实时间没有被补偿，恢复后的 guest clock 落后于真实时间。
2. Linux 6.4 及以后支持 `KVM_CAP_COUNTER_OFFSET`，vtimer offset 按 VM 管理。
   如果恢复逻辑仍按每个 vCPU 逐个写入计数器，每次写入都可能改写共享 offset，
   多 vCPU 最终看到的时间基准可能不一致。

本机内核为 Linux 6.6，处于第二种机制适用范围。若次级 vCPU 的 timer interrupt 或
时间推进异常，guest 内会出现 RCU stall；依赖调度和超时机制的 agent ttrpc 请求也会
停止推进。由此形成以下故障链：

```text
恢复旧 CNTVCT/共享 vtimer offset 处理不正确
  -> 多 vCPU guest clock 或虚拟定时器不一致
  -> 次级 vCPU timer/RCU stall
  -> guest agent 无法及时处理 ttrpc
  -> reset guest time / reseed random dev 超时
  -> Sandbox 创建失败并可能残留 shim
```

## 6. 社区修复方案

Cloud Hypervisor 上游 PR #8343：

- 标题：`arm64: correct the guest clock across snapshot/restore and migration`
- 合并日期：2026-06-19
- Merge commit：`eb1c64e4f01c9dd882e623795b139a129691ccfa`
- 上游验证范围包括 ARM64 Snapshot/Restore、跨宿主机迁移、Pause/Resume 和多 vCPU
  恢复一致性。

上游方案不是简单地跳过计数器恢复，而是：

1. Snapshot 时保存 guest counter、宿主机 wall clock 和 counter frequency。
2. Restore/Migration receive 时计算 VM 停机期间经过的时间。
3. 在 vCPU 运行前，将经过时间换算为 counter ticks 并推进 `CNTVCT`。
4. 根据 `KVM_CAP_COUNTER_OFFSET` 选择写入一次 boot vCPU 或写入所有 vCPU，兼容
   VM 级 offset 和旧内核的 per-vCPU 行为。
5. 对宿主机时间不可读、跨宿主机 counter frequency 不匹配等情况显式失败，避免
   带着错误时钟启动 guest。

这是当前推荐的正式解决方案。应将该 PR 对应提交移植到 CubeSandbox 内置的
Cloud Hypervisor fork，并重新构建 CubeShim/运行时组件。

## 7. 本地实验补丁

为快速验证根因，本地准备了一个仅面向同宿主机恢复的最小实验补丁：

```text
source_code/CubeSandbox-v0.5.1-cntvct-fix/
```

修改文件：

```text
hypervisor/hypervisor/src/kvm/mod.rs
```

补丁识别 `KVM_REG_ARM_TIMER_CNT`，在恢复 ARM64 vCPU system registers 时跳过
Snapshot 中的旧 CNTVCT 值，使 KVM 保留当前 counter/offset。

该补丁的作用是验证“旧 CNTVCT 回放导致故障”这一假设，具有限制：

- 只考虑同宿主机恢复，不保证迁移到不同宿主机时的时钟语义。
- 没有像上游方案一样显式计算停机时间和校验 `CNTFRQ`。
- 没有覆盖上游 PR 的完整 ClockState 抽象和集成测试。
- 当前仅完成源码修改，尚未完成多 vCPU 部署回归，因此不能标记为已修复。

若最小补丁能使 2 vCPU 连续恢复稳定，可进一步证明根因；生产修复仍应优先采用
上游完整方案或等待 CubeSandbox 社区同步对应 Cloud Hypervisor 版本。

## 8. 临时规避措施

在正式修复完成前，可将 ARM64 Template 配置为 1 vCPU。该方案已经通过 10 次
连续 create-delete 冒烟验证，适合验证 SDK、镜像内容和单线程/单核功能。

但 1 vCPU 不适用于本项目的正式 benchmark：正式测试包含 2 线程 sysbench、
多线程语言运行时和多核 Sandbox 场景，改成 1 vCPU 会改变资源竞争关系和性能结果。
因此临时规避只能用于功能检查，不能用来替代正式 2 vCPU 测试结论。

## 9. 修复与验证计划

### 9.1 推荐实施顺序

1. 完成实验补丁的 ARM64 离线构建，记录产物版本和 SHA256。
2. 在维护窗口替换运行时二进制并重启相关服务。
3. 先执行 2 vCPU Template 串行恢复门禁，不立即运行正式 benchmark。
4. 实验补丁验证根因后，移植并构建上游 PR #8343 的完整修复。
5. 完整修复通过回归后，再恢复 Snapshot/Clone/Rollback 和正式 benchmark。

### 9.2 最低验收标准

修复至少应满足：

- 2 vCPU / 4 GiB / 2G Template 连续 create-delete 100 次，成功率 100%。
- 测试期间无 `rcu_preempt detected stalls`。
- 无 `reset guest time failed`、`reset reseed random dev failed` 或 ttrpc timeout。
- CubeMaster Sandbox 数归零后，CubeShim 数也归零，无失联 VM/shim。
- Snapshot/Restore、Pause/Resume、Rollback、Clone 各执行至少 20 次，成功率 100%。
- guest 恢复后的 `CLOCK_REALTIME` 与宿主机时间差处于预设容差内，且时间不倒退。
- 2、4、8 vCPU 分别检查所有 vCPU 的 timer/RCU 稳定性。

正式 benchmark 只能在上述稳定性门禁通过后执行，否则延迟和吞吐数据不可信。

## 10. 当前结论

当前问题可归纳为：**CubeSandbox 所使用的 Cloud Hypervisor 版本缺少 ARM64
Snapshot/Restore guest clock 的完整修复，在 Linux 6.6 多 vCPU 环境中触发虚拟计时器
不一致，进而造成 RCU stall 和 guest agent ttrpc 超时。**

该结论与本地 1 vCPU/2 vCPU 对照实验及上游修复内容一致，置信度较高。当前仍应将
状态标记为“已定位、待修复验证”，而不是“已解决”。

## 11. 参考资料

- [Cloud Hypervisor PR #8343](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343)
- [CubeSandbox ARM64 正式测试报告](./CUBESANDBOX_FORMAL_TEST_REPORT_ARM64_20260716.md)
- [CubeSandbox v0.5.0 ARM64 安装报告](./cubesandbox-install-report-v0.5.0-nvme3n1.md)
- 本地实验补丁：`source_code/CubeSandbox-v0.5.1-cntvct-fix/hypervisor/hypervisor/src/kvm/mod.rs`
