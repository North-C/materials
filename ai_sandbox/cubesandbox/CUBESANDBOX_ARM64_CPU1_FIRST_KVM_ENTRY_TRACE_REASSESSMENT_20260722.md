# CubeSandbox ARM64 CPU1 restore 后首次 KVM 运行边界重新分析与 trace 方案

> 整理日期：2026-07-22
> 状态：机制分析、插桩、完整构建、诊断内核切换及 kernel-only 远端实测已完成
> 目标：找到 CPU1 从 snapshot 状态变为“真实进入 guest 并消费首个中断”过程中最早出现分歧的位置
> 结论等级：故障点已收敛，最终根因尚未闭环

> 2026-07-23 更新：trace 设计、操作、字段、构建部署、实测结果和 GHES 硬件中断边界，统一见 `CUBESANDBOX_ARM64_FIRST_ENTRY_TRACE_GUIDE_20260723.md`。本文第 8、9 节保留初稿时点，不再作为当前执行状态。

## 1. 总体判断

当前最可靠的判断不是“timer 值本身错误”，也不是“某个已知 KVM commit 缺失”，而是：

> ARM64 2-vCPU restore 的主要故障点位于 CPU1 resume 后第一次或最初几次真实 `KVM_RUN` 边界。VMM 已写入的软件 timer/vGIC 状态，在 KVM `vcpu_load -> timer restore -> vgic flush -> hyp restore -> guest entry` 的激活过程中，没有稳定地变成 guest 可消费的中断；随后 CPU1 进入 WFx 高频退出，guest timer softirq 停止，最终触发 RCU stall、agent/ttrpc 失联及销毁超时。

现有证据足以把“首次运行边界的中断投递/消费失败”定为直接故障点，但还不足以在下面三类机制中唯一选定最终根因：

1. VMM restore 状态在 load/entry 激活时存在时序或状态一致性问题，且对恢复后 `GET_ONE_REG`/日志时序高度敏感。
2. timer PPI 27 的软件 pending/active、物理 IRQ active 与实际 ICH LR 状态不一致，导致 pending 在进入 guest 前被抑制或未被 CPU interface 呈现。
3. vCPU load 的宿主 CPU 迁移或 per-CPU timer/GIC 硬件状态切换，使 CPU1 首次 entry 使用了错误或陈旧的物理 active/LR 状态。

优先级判断为 `P0 > P1 > P2`。其中 P0 不是指普通的 SET/GET API 失败，而是指“恢复状态何时被 KVM 物化为可运行硬件状态”的问题。

## 2. 已确认的现象链

一次故障实例可以整理为以下顺序：

```text
snapshot restore 完成
  -> CPU1 状态、timer 状态和 VGIC 状态均已由 VMM 写入 KVM
  -> VCPU 线程先以 paused/immediate_exit 状态启动
  -> resume 解除 pause
  -> CPU1 首次或早期 KVM_RUN
  -> 应当可投递的 timer/其他中断未被 guest 消费
  -> CPU1 出现持续 WFx 退出或 polling
  -> guest CPU1 timer softirq/调度进展停止
  -> RCU stall
  -> guest agent/ttrpc 超时
  -> shutdown/delete 超时并可能留下高 CPU shim
```

关键限定：paused 阶段的 `KVM_RUN` 可能因为 `immediate_exit` 只发生 `vcpu_load`，并未真实进入 guest。因此必须区分：

- 第一次 `vcpu_load`；
- 第一次 `immediate_exit == 0` 的真实 entry；
- 第一次真实 entry 后的 exit；
- timer IRQ handler 在 entry 前后发生的时点。

过去只看“restore 后第一次 KVM_RUN”会把这几个边界混在一起。

## 3. 实验 A/B/C 与后续对照的重新归纳

### 3.1 实验 B：cmdline 不是充分根因

实验 B 固定 restore/build 版本并交叉组合 cmdline，四个单元均复现：

| 恢复侧/构建侧组合 | 100 次生命周期结果 |
| --- | ---: |
| 组合 1 | 97/100 |
| 组合 2 | 95/100 |
| 组合 3 | 95/100 |
| 组合 4 | 93/100 |

这说明 cmdline 或启动参数可以调制窗口，但不能解释问题的有无。它不应继续作为主根因方向。

### 3.2 实验 C：普通 flush/文件可见性不是充分根因

实验 C 在 `sync_all()` 后确认：

- memory volume 长度正确；
- 49 个实际写入区间中的 139 个抽样页回读一致；
- 使用该产物做并发矩阵仍为 `1004/1020`，失败 16 次；
- 同型 CPU1 RCU stall 仍然出现。

因此可以否定“仅缺少普通 fsync/flush”这一充分根因。它仍不能严格证明 snapshot 每一页和所有设备状态完全一致，但后续若继续查产物，应使用同暂停点的全量分块哈希或双份 snapshot diff，而不是继续增加 reopen/fsync。

### 3.3 stock host kernel + v16：成功结果存在明显观察效应

同一 `.90` 节点、stock host kernel、v16 Shim 的结果为：

- 串行生命周期 `100/100`；
- 并发创建 `1020/1020`；
- 目标签名 0。

但把恢复侧 Shim 单变量切为社区 v0.5.1，同一 stock kernel、同一个由 v16 构建的 Template 立即变为：

- 串行 `96/100`；
- 并发 `998/1020`；
- 10 次 RCU stall、4 次 timer handling 异常、34 次 receive timeout。

这组对照同时说明：

1. stock kernel 不是充分修复；
2. Template 由 v16 构建不是充分解释；
3. v16 恢复侧增加的少量 timer `GET_ONE_REG` 和日志时序显著改变故障概率；
4. v16 的成功更像观察效应，不能当成语义修复。

因此，本轮新插桩必须把“只记录已有输入状态”和“额外执行 KVM GET readback”拆成两个独立模式。

### 3.4 native Cloud Hypervisor control 的含义

native snapshot/restore 对照在相同 host 上也出现低概率 restore 故障，支持问题位于 VMM/KVM restore 激活边界，而不是 CubeAPI、CubeMaster 或 SDK 独有逻辑。但它不能单独区分 VMM 状态模型与 KVM/GIC 硬件状态问题。

## 4. 对旧“物理 vtimer active 卡死”结论的修正

`CUBESANDBOX_ARM64_KVM_VTIMER_ACTIVE_ROOT_CAUSE_20260722.md` 把缺失 commit `387b558f` 写成最终根因，这个结论目前证据不足，不能继续作为已闭环事实：

1. 当前用于诊断的 openEuler `openEuler-24.03-LTS-SP3` 源码 `1cefaec0de17` 已包含 handler 的 `should_fire == false -> set_timer_irq_phys_active(false)` 行为。
2. stock kernel + 社区 Shim 仍可复现，说明“仅升级到含该分支修复的 stock kernel”并未消除故障。
3. 过去的 ftrace/kprobe 没有在同一 vCPU、同一 entry generation 上同时捕获软件 IRQ、物理 active 和实际 ICH LR，因而没有直接证明 active-stuck。

更准确的表述应为：

> 物理 timer IRQ active 与 vGIC/LR 状态错配仍是高优先级机制假设，但不是已证明的最终根因。新 trace 将直接验证它。

## 5. 正向机制：restore 状态如何变为 guest 可见中断

### 5.1 VMM restore 状态阶段

正常路径必须完成以下状态转换：

```text
snapshot CPU state
  -> SET_ONE_REG: core/system/timer registers
  -> SET_MP_STATE
snapshot VGIC distributor/redistributor/CPU-interface state
  -> KVM device attr restore
device restore
  -> VCPU threads ready but paused
resume
  -> VCPU threads released
```

这里需要验证的不是 ioctl 是否返回 0，而是 CPU1 输入状态之间是否自洽：

- `CNTV_CTL.ENABLE/MASK/ISTATUS`；
- `CNTV_CVAL - CNTVCT` 的符号和数量级；
- `CNTKCTL_EL1`；
- GICR PPI 27 的 enable/pending/active/group/priority/config；
- ICC PMR/BPR/IGRPEN 与 active-priority 状态。

### 5.2 KVM load 与 timer restore

`kvm_arch_vcpu_load()` 之后，timer 代码要把虚拟 timer 上下文切到当前宿主 CPU，并恢复必要的物理 timer/GIC 状态。必须成立：

- 该 load 属于本次 restore 的正确 generation；
- vCPU 没有在未完成 put/save 的情况下跨宿主 CPU 复用硬件状态；
- `live CNTV_CTL/CVAL` 与 KVM 软件 context 一致；
- `should_fire`、软件 line level 和物理 IRQ active 的组合合法。

特别需要区分以下合法/异常组合：

| timer 状态 | 正常含义 |
| --- | --- |
| `ENABLE=0` | 不应产生 timer 中断 |
| `ENABLE=1, MASK=1` | 可过期但不应投递 |
| `ENABLE=1, MASK=0, delta>0` | 尚未到期，等待硬件 timer |
| `ENABLE=1, MASK=0, delta<=0` | `should_fire=1`，PPI 27 应进入可投递状态 |
| `should_fire=0, phys_active=1` 持续存在 | 高度可疑，需看 handler 是否及时 deactivate |

### 5.3 vGIC flush 与 LR 生成

KVM 进入 guest 前，vGIC 要从软件 IRQ 状态生成 ICH list register。对 level PPI 27，下面状态必须关联观察：

- 软件 `pending/active/line_level/enabled`；
- 是否在 `ap_list`；
- KVM 软件保存的 LR；
- 写入硬件后的实际 `ICH_LR<n>_EL2`；
- `ICH_HCR_EL2/VMCR_EL2/ELRSR_EL2/AP1R0_EL2`。

若 IRQ 已 active，`vgic_v3_populate_lr()` 可能抑制 pending。只有同时读取软件 IRQ 和实际硬件 LR，才能判断问题发生在：

1. timer 没有把 IRQ 置 pending；
2. 软件 IRQ 已 pending，但 LR 未生成；
3. LR 已生成，但只有 active、没有 pending；
4. LR 正确，CPU interface gate 阻止投递；
5. LR 和 gate 均正确，但 guest 没有取走，问题进一步进入 guest PSTATE/handler。

### 5.4 guest entry/exit 与消费判定

“投递成功”不能只由 pending 判断，至少还要看到一个消费信号：

- pre-entry 时 LR 为 pending 或 pending+active；
- post-exit 时对应 LR、ELRSR、active-priority 或软件 pending 发生合理变化；
- guest PC/PSTATE 从 WFx 附近前进，或随后不再形成无进展 WFx storm；
- timer handler/软中断继续推进，不发生 CPU1 RCU stall。

## 6. 新增插桩

### 6.1 VMM 插桩分支

工作树：`source_code/CubeSandbox-v0.5.1-arm64-first-entry-trace-v22`  
分支：`experiment/arm64-first-entry-trace-v22`

所有日志统一使用 `ARM64_FIRST_ENTRY` 前缀，覆盖：

- VM restore/resume 各阶段；
- CPU manager、VCPU thread ready、resume release；
- CPU1 timer snapshot 输入值及各 SET 阶段；
- VGIC snapshot 中 PPI 27 和 ICC gate 的解码值；
- 可选的 KVM timer/VGIC readback。

门控文件：

| 文件 | 行为 |
| --- | --- |
| `/tmp/cube_arm64_first_entry_trace_enable` | 只输出 metadata，不新增 timer GET readback |
| `/tmp/cube_arm64_first_entry_readback_enable` | 在 metadata 基础上执行诊断 GET readback |

默认两者都关闭，原始 restore 语义不变。metadata-only 是首轮复现模式；readback 仅作为匹配对照，防止重复 v16 的观察效应误判。

### 6.2 KVM/arm64 插桩分支

工作树：`source_code/openEuler-kvm-first-entry-trace-v22`  
分支：`experiment/kvm-arm64-first-entry-trace-v22`

新增两个 trace event：

1. `kvm:kvm_arm64_first_entry`
2. `kvm:kvm_arm64_timer_handler`

`kvm_arm64_first_entry` 分为三个 phase：

| phase | 位置 | 目的 |
| --- | --- | --- |
| `LOAD` | vCPU load | 记录 generation、宿主 CPU 和软件状态；包括 immediate-exit load |
| `PRE_ENTRY` | 真实 guest entry 前 | 记录即将进入 guest 的 timer、IRQ27、实际 ICH 状态 |
| `POST_EXIT` | guest exit 后 | 判断 IRQ 是否被消费及硬件状态如何回收 |

采集字段包括：

- VM/VCPU、PID/TID、host CPU、load generation、exit count、phase；
- 软件与 live `CNTV_CTL/CVAL/CNTVCT/delta`；
- timer line、`should_fire`、物理 active；
- IRQ27 `pending/active/line/enabled/hw/mapped/ap_list`；
- 实际 `ICH_HCR/VMCR/MISR/EISR/ELRSR/AP1R0`；
- 实际 LR 中 IRQ27 和第一个 pending IRQ 的 raw value/index/state。

timer handler event 在 handler 前后各记录一次，可直接验证：

```text
handler 前 should_fire/phys_active/line
  -> update_irq 或 deactivate
handler 后 should_fire/phys_active/line
```

trace 默认关闭；只有启用 event 后才增加硬件寄存器读取，并限制每个 vCPU 前 64 次 exit，控制开销和日志量。

### 6.3 采集脚本

脚本：`scripts/collect_arm64_first_entry_trace.sh`

脚本负责：

- 检查诊断内核 trace event 是否存在；
- 拒绝覆盖已有 active tracing 会话；
- 保存并恢复 event、`tracing_on` 和门控文件状态；
- 同时采集 trace 格式、per-CPU 丢事件统计、dmesg、lscpu、lsmod、workload 输出；
- 支持 metadata-only 和 readback 两种 VMM 模式。

示例：

```bash
sudo ./collect_arm64_first_entry_trace.sh /data/trace/run-metadata \
  --vmm-metadata -- <串行生命周期命令>
```

## 7. 远端实验设计与判定矩阵

目标节点优先使用 `.90`，固定 stock 时已复现的 Template `tpl-592352ea663648e486962db3`、2 vCPU/2000 MiB、串行 create-health-delete。先做低压力样本，避免历史 PCIe/NIC 健康问题和并发噪声。

### 7.1 部署门禁

只有同时满足以下条件才部署：

- SSH 管理面稳定；
- 无活动 sandbox/shim/task；
- Cube 服务 active；
- 温度低于停止阈值；
- 当前启动无新增 GHES/PCIe fatal 或 mlx5 health error；
- `/boot` 和根文件系统空间充足；
- stock kernel 保留为永久默认项，诊断内核仅安排一次性启动或明确回滚项；
- 现有 Shim 已按 SHA256 备份。

### 7.2 测试阶段

| 阶段 | VMM 模式 | 建议样本 | 目的 |
| --- | --- | ---: | --- |
| A0 | trace 全关 | 5 | 部署健康冒烟 |
| A1 | metadata-only | 20，未命中再扩至 50 | 捕获原始故障，不引入 GET readback |
| A2 | metadata-only | 对命中实例保留完整日志 | 做 CPU1 entry generation 关联 |
| B1 | readback | 与 A1 相同 | 验证 v16 型 readback 是否再次压低故障概率 |
| C1 | metadata-only，必要时限制 host CPU | 小样本 | 仅在 trace 指向 host migration 时验证 P2 |

禁止直接从并发 c20/c50 开始。串行 20 次在历史约 4% 故障率下已有约 56% 的至少一次命中概率，且能显著减少跨实例 trace 混杂。

### 7.3 结果判定

| 观测 | 判断 |
| --- | --- |
| snapshot/input 与 KVM live timer 在 `PRE_ENTRY` 前已分歧 | VMM SET 顺序或 KVM load 激活问题 |
| `should_fire=1`、IRQ27 pending=0 | timer 到 vGIC 更新链断裂 |
| IRQ27 pending=1，但实际 LR 无 IRQ27 | vGIC ap_list/LR 生成或同步问题 |
| LR27 active=1、pending=0，且物理 active 持续 | 支持 active-stuck/active 抑制 pending |
| LR27 pending 正确，ICC gate 正确，但 post-exit 无消费且 WFx storm | 转向 guest exception/IRQ mask/handler 入口 |
| 仅跨 host CPU generation 复现 | 支持 per-CPU timer/GIC save-restore 问题 |
| metadata-only 复现而 readback 不复现 | 确认 readback 观察效应，进一步缩小激活窗口 |
| 两种模式都不复现 | 不能判定修复；扩大串行样本或降低 trace 字段，检查 trace 本身的观察效应 |

## 8. 本地验证状态

截至文档初稿：

- VMM `cargo fmt --all` 完成；
- `hypervisor` 与 `vmm` ARM64 target 的 test/check 均通过；
- 内核改动 `git diff --check` 通过；
- checkpatch 为 0 error、0 warning；
- `arm.o`、`arch_timer.o`、`vgic.o`、VHE `vgic-v3-sr.o` 通过编译；
- 完整 nVHE `kvm_nvhe.o` 已编译并链接；
- full host-config `Image + modules` 与 VMM release 构建进行中。

## 9. 远端实际测试状态

本节将在测试完成后回填。目前没有把本地构建成功等同于远端验证成功。

2026-07-22 约 19:20 的只读预检显示 `.90`：

- 运行 stock `6.6.0-132.0.0.111.oe2403sp3.aarch64`；
- 资源和温度尚可；
- Cube 服务 active，无活动 Cube VMM/shim；
- 当前 tracefs 为 `nop`、空 event/空 buffer；
- 当前启动早期仍出现 mlx5 firmware internal error；上一轮崩溃包含 PCIe/GHES fatal，因此需要保守测试。

随后 `.90` 与 `.65` 均在 SSH banner 前关闭连接，`.90` ICMP 也不可达。管理面未恢复前不执行内核安装、Shim 替换或 reboot。

## 10. 下一步结论门槛

只有捕获到同一 CPU1、同一 load generation 的以下四段状态，才能把最终根因写成闭环：

1. VMM restore 输入；
2. KVM `PRE_ENTRY` 软件 timer/IRQ 状态；
3. 实际 ICH LR/CPU interface 与物理 active；
4. `POST_EXIT` 或 timer handler 后的消费/回收状态。

当前可以对外使用的结论是：

> 直接故障点已收敛到 CPU1 restore 后首次真实 KVM entry 的中断物化与消费边界。首要嫌疑是对 GET/log 时序敏感的 restore 激活一致性，其次是 timer PPI 27 的物理 active、vGIC pending/active 与实际 LR 错配。实验 B 否定 cmdline 充分根因，实验 C 否定普通 flush 充分根因，stock + 社区 Shim 对照否定 stock kernel 充分修复。最终根因必须由新 trace 数据决定，不能继续由单个历史 commit 或单层软件状态推断。

## 11. 证据索引

- `remote-results/experiment-b-c-arm64-20260722-1157/EXPERIMENT_B_C_SUMMARY.md`
- `remote-results/v0.5.1-stock-host-kernel-template-retest-20260722-1508/TEST_SUMMARY.md`
- `remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md`
- `CUBESANDBOX_V16_VS_COMMUNITY_V051_CHANGE_ANALYSIS_20260722.md`
- `CLOUD_HYPERVISOR_ARM64_NATIVE_SNAPSHOT_RESTORE_CONTROL_20260722.md`
- `CUBESANDBOX_ARM64_MULTIVCPU_ROOT_CAUSE_REASSESSMENT_20260722.md`
- `CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md`
- `CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md`
