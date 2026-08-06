# CubeSandbox ARM64 模板恢复失败问题说明

- 文档日期：2026-08-06
- 问题范围：ARM64 多 vCPU 模板 snapshot restore 后沙箱创建失败
- 主要错误：`reset guest time failed`、`reset reseed random dev failed`、guest RCU stall
- 当前修复：`aprmask` 内核 + 修复版 `cube-runtime`

## 1. 测试环境

问题定位和修复验证分为两个阶段。

### 1.1 根因定位环境

| 项目 | 配置 |
|---|---|
| 节点 | `192.168.25.90` |
| 架构 | Kunpeng ARM64，384 pCPU |
| 中断控制器 | GICv3，支持 FEAT_GICv3_NMI |
| 虚拟化 | KVM + CubeSandbox cloud-hypervisor fork |
| 主要场景 | 多 vCPU 模板 snapshot restore 后创建沙箱 |
| 主要对照 | 未修复、仅 VMM 修复、仅内核修复、双修复 |

该阶段使用历史高复现模板和社区栈进行串行、并发及 eBPF/EL2 插桩实验，目的是确定故障发生在 guest、VMM 还是 KVM/vGIC 层。

### 1.2 修复后正式验证环境

| 项目 | 配置 |
|---|---|
| 节点 | `192.168.25.65`，主机名 `master` |
| 内核 | `6.6.0-sbench-irqbypass-xarray-v2-aprmask` |
| cube-runtime SHA256 | `a68d64cd29c84d544b2c8a4e1f9d6ab2d60d7d451f9ecd1ffccb811d4749ea9f` |
| 镜像 | `192.168.25.65:2900/bench/sandbox-code:latest` |
| 模板配置 | 1U/2G、2U/2G、3U/2G、4U/2G、5U/2G |
| 模板数量 | 每档 5 个，共 25 个，严格串行构建 |
| 每模板压力 | 6 轮，每轮并发创建 50 个，共 300 次 |
| 总创建次数 | 7,500 次 |
| TAP 配置 | `tap_init_num=1000`；稳定基线为 links=1000、pool=984 |
| 测试时段 | 2026-08-05 20:12:07 至 20:39:50（UTC+8） |

每轮结束后删除本轮沙箱、清理本轮残留 shim，并等待 TAP 连续 3 次恢复至稳定基线且 `abnormal=0、quarantined=0`，才开始下一轮。

## 2. 问题现象

### 2.1 用户可见现象

模板恢复创建沙箱时出现概率性失败，通常约 8 秒后返回 HTTP 500。CubeShim 的关键日志如下：

```text
Create sandbox failed:reset guest time failed:ttrpc err: Receive packet timeout Elapsed(())
```

Cubelet 会将其包装为创建 shim task 失败：

```text
run container failed.failed to create shim task: Others("Other: Create sandbox failed:reset guest time failed:ttrpc err: Receive packet timeout Elapsed(())")
```

部分失败首先表现为：

```text
Create sandbox failed:reset reseed random dev failed: ...
```

更上层还可能表现为探针或端口绑定超时。上述字符串是外部症状，并不是根因本身。

### 2.2 guest 内部现象

失败 VM 的非启动 vCPU 无法继续接收虚拟中断，进入高频 WFI trap 循环；随后 guest 报告 timer/RCU 异常：

```text
[   70.806549][    C0] rcu: Possible timer handling issue on cpu=1 timer-softirq=34
[   70.807408][    C0] rcu: rcu_sched kthread starved for 15002 jiffies! ... ->cpu=1
```

历史测量中 WFI trap 可达到约 20 万至 47.5 万次/秒。`maxcpus=1` 能规避历史多 vCPU 故障，是问题与 vCPU1 状态强相关的重要线索。

### 2.3 vGIC 关键异常

失败实例中，vCPU1 的 AP1R0 高位出现固定污染：

```text
put,197704674786700,791171,vcpu=1 cpu=313 ap1r0=8000000000000000 ap1r1=0
load,197704675074110,791171,vcpu=1 cpu=342 ap1r0=8000000000000000 (shadow already dirty)
```

`0x8000000000000000` 即 `ICH_AP1R0_EL2` bit63。失败样本中该位持续存在并在 vCPU put/load 时跨 pCPU 传播；通过样本中该位为 0。

## 3. 问题原因与推断过程

### 3.1 已确认的直接原因

`ICH_AP1R0_EL2` bit63 在支持 GICv3 NMI 的主机上代表 NMI active-priority 状态。该位被错误置 1 后，会以高于普通 Group-1 虚拟中断的优先级阻止 timer、SGI、LPI 等虚拟中断向 guest 呈现。

这个状态并非由真实 guest NMI 产生，因此不存在对应的 LR，也无法通过 guest EOI 清除。KVM 在 vCPU put/load 时又会在硬件 APR 和 vCPU 影子状态间保存、恢复该位，最终形成持续到 VM 销毁的中断饥饿状态。

因果链如下：

1. snapshot restore 期间，AP1R0 bit63 被错误注入 vCPU 状态；
2. NMI-active 优先级阻断所有普通 Group-1 虚拟中断；
3. guest vCPU 收不到 timer tick 和其他唤醒中断；
4. vCPU 进入 WFI trap 风暴，pending LR 长期无法消费；
5. guest agent 不再响应 reset time/reseed RPC；
6. CubeShim 等待约 8 秒后返回 `Receive packet timeout`；
7. 持续运行的 guest 随后出现 timer handling issue 和 RCU stall。

### 3.2 bit63 的两个独立注入向量

本问题不是单一位置的错误，而是存在两个相互独立的污染入口。

#### 向量 A：cube-runtime 的 32/64 位访问宽度错误

cloud-hypervisor fork 的 `icc_regs.rs` 使用 `u32` 缓冲区访问 `KVM_DEV_ARM_VGIC_GRP_CPU_SYSREGS`，但内核 `kvm_sys_reg_get/set_user` 按 `u64` 指针读写 8 字节。

结果是：

- GET 时，内核写入 8 字节，越过 4 字节槽位并污染相邻内存；
- SET/restore 时，内核读取 8 字节，高 32 位来自下一槽位或 Vec 边界外堆内存；
- 最后一个 vCPU 的最后一个 ICC 寄存器正好是 `ICC_AP1R0_EL1`，越界值的最高位可映射为 AP1R0 bit63。

健康 vCPU0 曾观测到 `ap1r0=0x700000000`，其中高 32 位的 `7` 正好对应下一快照槽位的 SRE 值，构成了宽度错位的字节级证据。

#### 向量 B：内核保存了 APR 高 32 位硬件读回垃圾

在当前支持 FEAT_GICv3_NMI 的 GIC 上，AP 寄存器高 32 位可能读回瞬时无效值，实测形态包括 `0x80000000`、`0xffffffff` 等。

原内核的 `__vgic_v3_save_aprs()` 未屏蔽高位，直接将硬件读回值保存到 vCPU 影子状态；下一次 `__vgic_v3_restore_aprs()` 又将其写回硬件。这样原本不应被使用的读回垃圾会被持久化，并可能成为真实的 NMI-active 状态。

### 3.3 推断和确认过程

定位过程不是从超时字符串直接推断，而是逐层缩小范围：

1. 在纯社区栈中仍能复现，排除本地 Cubelet/CubeMaster 功能改动；
2. `maxcpus=1` 可规避，失败集中于 vCPU1，确定问题与多 vCPU restore 状态有关；
3. 观测到 WFI 风暴、timer pending、LR 不消费，确认 guest 不是普通启动慢，而是虚拟中断未投递；
4. HCR.IMO、ICH_HCR.En、VMCR.VENG1、PMR 等接口门控均正常，排除常规中断开关错误；
5. EL2 插桩和 eBPF 对照发现 fail/pass 唯一稳定差异为 AP1R0 bit63：失败样本恒为 1，通过样本为 0；
6. put/load 追踪证明污染在 restore 窗口进入影子状态并持续传播；
7. 解析模板 ICC 快照布局并审计代码，确认 `u32`/`u64` 宽度不匹配；
8. 硬件读回实验同时确认内核侧存在独立的高位污染入口；
9. 单独修复任一入口仍只有 5/20 通过，双修复达到 20/20，且 bit63 消失，完成因果验证。

此前考虑过 guest 时钟追赶、坏 pCPU、HCR/PMR 配置、物理 timer、定制内核差异等方向，均被 A/B 对照或寄存器实测排除。

### 3.4 适用边界

`reset guest time failed` 是阶段性错误字符串，不具备根因唯一性。只有同时出现 AP1R0 bit63、虚拟中断不投递、WFI 风暴或后续 RCU stall 等特征时，才能归入本文所述 vGIC 故障。

历史上还发现过模板在 guest 内部 probe teardown 中间态被截取形成“坏快照”的独立问题，它也可能返回相同超时字符串，但不存在 AP1R0 bit63/WFI 风暴。两类问题应通过寄存器探针和 guest console 区分，不能仅凭 API 文案归因。

## 4. 当前使用的修复方法

当前采用“双修复”：`aprmask` 内核与修复版 `cube-runtime` 同时部署。

### 4.1 aprmask 内核

内核补丁修改 `arch/arm64/kvm/hyp/vgic-v3-sr.c::__vgic_v3_save_aprs()`，保存 AP0R/AP1R 时统一执行：

```c
value & 0xffffffffULL
```

选择该处理的理由：

- 当前实现中每个有效 APR 的架构状态位于低 32 位；
- 当前 guest 未虚拟化 NMI，不存在合法的 guest NMI-active 高位状态；
- 屏蔽高 32 位可以阻止硬件读回垃圾进入 KVM vCPU 影子；
- 即使 userspace 或硬件再次提供异常高位，也不会在硬件/影子循环中被持续放大。

该补丁用于切断“硬件读回垃圾 → vCPU 影子 → 写回硬件”的向量 B。

### 4.2 修复版 cube-runtime

VMM 补丁将 `icc_attr_access()` 的缓冲区从 `u32` 改为 `u64`，使其与 KVM CPU sysreg ABI 的 8 字节访问一致：

- GET 使用 8 字节缓冲区，序列化时只保存低 32 位；
- SET 将快照中的 `u32` 显式扩展成高位为 0 的 `u64` 后再传给 KVM；
- 快照中的 ICC 数据仍保持原 32 位格式，避免破坏旧模板兼容性。

该补丁从源头消除越界读写和随机高位注入，即向量 A。

### 4.3 为什么两个修复必须同时使用

两个入口相互独立：

- 只修 cube-runtime，硬件高位读回仍可能经内核进入影子状态；
- 只修内核保存路径，未修复 cube-runtime 仍可能在 restore SET 时直接向 KVM 注入高位；
- 实测未修复、仅 VMM 修复、仅内核修复均只有 5/20 通过；
- 双修复后达到 20/20，且探针不再观测到 bit63。

因此当前选择双修复不是重复防护，而是分别关闭两个已实验证实的注入向量。

## 5. 修复后的测试结果

### 5.1 初始修复矩阵

| 配置 | 串行结果 | 说明 |
|---|---:|---|
| 未修复 | 5/20 | 失败样本均带 AP1R0 bit63 |
| 仅修复 cube-runtime | 5/20 | 内核读回向量仍存在 |
| 仅使用 aprmask 内核 | 5/20 | VMM restore 注入向量仍存在 |
| aprmask + 修复版 cube-runtime | 20/20 | bit63=0 |

双修复后早期多模板并发测试累计 1,600 次创建，未出现目标错误签名。

### 5.2 `.65` 多资源、多模板正式验证

| 配置 | 模板数 | 创建数 | 成功 | 失败 |
|---|---:|---:|---:|---:|
| 1U/2G | 5 | 1,500 | 1,500 | 0 |
| 2U/2G | 5 | 1,500 | 1,500 | 0 |
| 3U/2G | 5 | 1,500 | 1,500 | 0 |
| 4U/2G | 5 | 1,500 | 1,500 | 0 |
| 5U/2G | 5 | 1,500 | 1,500 | 0 |
| **合计** | **25** | **7,500** | **7,500** | **0** |

错误签名统计：

```text
templates_ready                    25/25
template_build_failures             0
restore_pass                     7500/7500
restore_fail                         0
api_reset_guest_time_failed          0
shim_log_reset_guest_time_failed     0
shim_log_vm_boot_failed              0
dmesg_rcu_stall_signatures           0
cleanup_failures                     0
```

资源清理结果：150/150 轮均达到：

```text
sandboxes=0
shims=0
tap links=1000
tap pool=984
tap abnormal=0
tap quarantined=0
```

### 5.3 当前结论

在本次指定环境、1U/2G 至 5U/2G 资源矩阵、25 个新模板和 7,500 次并发恢复样本内，修复前的 vGIC/AP1R0 故障未再复现。双修复同时覆盖了已经确认的 userspace 与内核两个污染入口，测试结果与根因模型一致。

该结论是针对当前测试矩阵的回归结论，不应表述为对任意硬件、任意 guest 镜像和无限运行时间下的绝对证明。后续仍建议保留 AP1R0 bit63、WFI 频率、`reset guest time failed` 和 RCU stall 的监控。

## 6. 证据与实现位置

- 根因报告：`CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md`
- 修复补丁：`fixes/arm64-vgic-apr-nmi-active-20260731/`
- AP1R0 污染日志：`remote-results/arm64-entry-pstate-repro-20260730/ap1r-pollution.log`
- 失败 CubeShim/RCU 日志：`remote-results/cubesandbox-template-perf-2u2g-community-image-openEuler-kernel-20260727-213225/evidence/identity-attempt-1-shim.log`
- 正式验证报告：`remote-results/aprmask-multi-resource-65-20260805/REPORT.zh-CN.md`
- 逐模板汇总：`remote-results/aprmask-multi-resource-65-20260805/validate4/summary.tsv`
- 7,500 次请求明细：`remote-results/aprmask-multi-resource-65-20260805/validate4/results.tsv`
- 测试脚本：`scripts/validate_aprmask_multi_resource_templates_65.sh`
