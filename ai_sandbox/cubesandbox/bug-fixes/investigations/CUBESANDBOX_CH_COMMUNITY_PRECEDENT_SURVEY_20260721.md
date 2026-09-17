# CubeSandbox ARM64 多 vCPU 恢复故障 — Cloud Hypervisor 社区先例检索报告

> 整理日期：2026-07-21  
> 检索范围：cloud-hypervisor/cloud-hypervisor GitHub issues / PRs / commits  
> 关联文档：[问题说明](CUBESANDBOX_ARM64_MULTIVCPU_RESTORE_ISSUE_BRIEF_20260721.md)

---

## 1. 一分钟结论

CubeSandbox 在 ARM64/openEuler 6.6 上 2 vCPU snapshot/restore 间歇性卡死的故障，在 Cloud Hypervisor 社区有**大量近亲先例**，核心集中在三件事：

1. **aarch64 多 vCPU snapshot/restore 的正确性本身长期脆弱**，近一年仍在持续修 bug；
2. **counter / vtimer 的恢复语义是版本敏感的**（PR #8343），CubeSandbox 已经试过 #8343 风格但只能到 99/100；
3. **社区尚未覆盖"timer PPI vs vGIC 恢复时序"** —— 这正是 CubeSandbox 残留的 1%。

**关键判断**：CubeSandbox 落在上游已修（counter 数值）与未修（timer 使能 / vGIC 重排序时序）的交界处。社区证据强力支持文档当前的排查方向，但**没有现成 patch 能直接达到 100/100**。

---

## 2. 速览矩阵

| 社区条目 | 类型 | 与 CubeSandbox 吻合度 | 状态 / 日期 | 链接 |
| --- | --- | --- | --- | --- |
| **PR #8343** arm64 guest clock across snapshot/restore & migration | PR | **极高**（文档"PR #8343 风格"来源；v2 明确处理 aarch64 多 vCPU 正确性） | merged 2026-06-19 | [#8343](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343) |
| **Issue #6001** live migration 后 vCPU 100% on aarch64 | Issue | **行为级双胞胎**（对应"残留 100% CPU 的 CubeShim"） | closed，未根因 | [#6001](https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6001) |
| **Issue #6966** ARM snapshot restore 失败 | Issue | **环境级双胞胎**（同 Kunpeng-920 + 6.6.0-x + boot=2） | closed，根因 Rust UB | [#6966](https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6966) |
| **Issue #4239 / PR #4244** vCPU 必须按数值顺序恢复 | Issue/PR | **结构性**（证明 aarch64 恢复对顺序极敏感） | fixed v25.0 | [#4239](https://github.com/cloud-hypervisor/cloud-hypervisor/issues/4239) / [#4244](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/4244) |
| **PR #8268** 正确保存/恢复 SVE 寄存器 | PR | **结构性**（近期 aarch64 寄存器恢复修复，旧 fork 可能缺失） | merged 2026-05-22 | [#8268](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8268) |
| **PR #4960** Move Gic to the new restore path | PR | **结构性**（vGIC 恢复时机重构） | closed | [#4960](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/4960) |
| **Issue #6970** test_snapshot_restore_with_fd fails on aarch64 | Issue | 参考性（aarch64 snapshot restore CI 至今仍 flaky） | **open** | [#6970](https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6970) |

---

## 3. Tier 1 — 最贴近的先例

### 3.1 PR #8343 — arm64: correct the guest clock across snapshot/restore and migration

- **链接**：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343 （[改动文件 diff](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343/files)）
- **合并时间**：2026-06-19
- **背景**：x86 上 snapshot restore / migration 后 guest 用 kvmclock 路径把 CLOCK_REALTIME 追回；ARM64 没有这个 helper，原先只是 round-trip `CNTVCT_EL0`，导致 cold-restore 或迁移接收端 guest 的时间落后整个 downtime。
- **做法**：snapshot 时记录 guest counter + host 墙钟 + counter 频率；restore / migration 接收端，在 vCPU 运行前用 `KVM_REG_ARM_TIMER_CNT` ONE_REG 把 `CNTVCT` 推进 downtime 时长。
- **🔥 关键（v2 changelog 原文）**：

  > *"aarch64 multi-vCPU correctness: gate the counter write on KVM_CAP_COUNTER_OFFSET — Linux ≥6.4 tracks the vtimer offset VM-wide (one boot-vCPU write), older kernels per-vCPU (write all). v1 wrote vcpu0 only."*

- **对 CubeSandbox 的意义**：
  - 宿主内核 `6.6.0-132`（≥6.4）、`KVM_CAP_COUNTER_OFFSET=1` → 落在 **VM-wide 单次写**路径上。
  - ⚠️ **措辞澄清（2026-07-21 订正）**：上游 v1 "只写 vcpu0" **仅对旧内核是 bug**；在 ≥6.4 的 VM-wide 路径上，**只写 boot vCPU 才是正确行为**，写所有 vCPU 反而多余。
  - ✅ **CubeSandbox 已正确实现并穷尽测试（基于 COMPLETE_EXPERIMENT_REPORT §8.1/§9.1/§9.3/§9.4）**：
    - v1/v3/v7 = boot-vCPU-only（正确的 ≥6.4 路径）
    - v4 = 向所有 vCPU 写 ONE_REG（旧内核回退路径）
    - v5/v6 = VM 级 `KVM_ARM_SET_COUNTER_OFFSET` ioctl（#8343 讨论过的替代方案）
    - 三种策略最佳均为 99/100，ONE_REG 与 VM ioctl 两路径均未达 100/100。
  - **结论：counter 写入 gating 这条线已被彻底排除，不是残留缺陷。** 残留 1% 不在 counter write，而在 `CNTV_CTL` 使能时机 / timer PPI vs vGIC 恢复时序（报告 P0 假设、v17 CTL-last 实验所指）。
  - **#8343 只修 `CNTVCT`（counter 数值），不碰 `CNTV_CTL`（timer 使能）与 vGIC 重排序** → 这正是 CubeSandbox 残留 1% 的所在。**社区也还没修这部分。**

### 3.2 Issue #6001 — After live migration vcpu of vm is up 100% on aarch64

- **链接**：https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6001
- **症状**：aarch64 上 live migration（**走的就是 restore 路径**）后目标端 vCPU **100% 空转**，源端正常退出。与 CubeSandbox"残留持续 100% CPU 的 CubeShim"一字不差。
- **环境**：FT-2000+/Kunpeng 系（与 CubeSandbox 的 Kunpeng 950 同族），RHEL 9 内核 5.15。
- **社区结论**：维护者 **怀疑宿主内核太旧，建议升级内核**；最终因复现版本过时被关闭，**未给出确定根因**。
- **意义**：与 CubeSandbox 当前处境一致 —— 社区也没把"恢复后 vCPU 空转 / 中断丢失"坐实。

### 3.3 Issue #6966 — Failed to restore snapshot in ARM architecture

- **链接**：https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6966
- **根因 commit**：https://github.com/cloud-hypervisor/cloud-hypervisor/commit/02f146fef81c4aa4a7ef3555c176d3b533158d7a
- **环境（与 CubeSandbox 几乎完全相同）**：Kunpeng-920、内核 `6.6.0-25`、openEuler 系、`--cpus boot=2`、snapshot → restore。
- **报错**：`RestoreGic(SetDeviceAttribute(Invalid argument))` —— **vGIC 恢复失败**。
- **最终根因（出乎意料）**：**Rust 编译器 UB**（commit `02f146f` 修复）导致 `gic-v3-its` 快照数据被优化掉：
  - debug 版 snapshot：`gic-v3-its.snapshot_data` 长度 **2339**
  - release 版 snapshot：长度 **1698**
  - 恢复时数据不全 → 失败。维护者明确：*"only use the compiler it was tested with."*
- **对 CubeSandbox 的警示**：
  - 文档 4.2 节用"相同 builder 重建 v12 = 99/100"排除了构建器差异，但 #6966 证明 **vGIC/ITS 快照完整性与编译器/Rust 版本强相关**。
  - 建议补廉价对照：用社区验证过的 Rust 版本重编，**diff 坏 Template 与好 Template 的 `gic-v3-its.snapshot_data` 长度**。这正好覆盖 CubeSandbox 怀疑的 W2（vGIC 恢复窗口）。
- **✅ 对照结论（2026-07-21）**：CubeSandbox 源码逐字存在该 UB 模式（未回移 `02f146f`），但构建 pinned 在 Rust 1.77.2（< 1.80.0），显现条件不成立，当前二进制不含该类缺陷，且故障模式与 #6966 不符；属潜在风险（工具链升级即复现），建议回移。详见 `CUBESANDBOX_CH_ISSUE6966_UB_COMPARISON_20260721.md`。

---

## 4. Tier 2 — 结构性相关（aarch64 恢复正确性）

### 4.1 Issue #4239 / PR #4244 — vCPU 必须按数值顺序恢复

- 链接：[#4239](https://github.com/cloud-hypervisor/cloud-hypervisor/issues/4239) / [PR #4244](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/4244)
- 原文：*"the order is in character order not numeric order... leads to chaos when create vcpus then system crash on aarch64"*。BTree 字典序把 "11" 排在 "2" 前。
- **注意**：对 2 vCPU（id "0"/"1"）这个具体 bug 不触发；但它是"aarch64 恢复对 vCPU 顺序敏感"的权威佐证，与 CubeSandbox"1 vCPU 稳定、2 vCPU 失败、恢复顺序是核心变量"判断同向。

### 4.2 PR #4960 — Move Gic to the new restore path

- 链接：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/4960
- vGIC 恢复时机的重构，与 W2（vGIC 恢复窗口）直接相关。若 CubeSandbox fork 基线老，可能停在旧 GIC 恢复路径上。

### 4.3 PR #8268 — aarch64: Correctly save/restore SVE registers

- 链接：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8268
- 合并于 2026-05-22。说明 aarch64 寄存器 save/restore 近一年仍在持续修 bug，**旧 fork 大概率缺一连串此类修复**。

---

## 5. Tier 3 — 邻接的 resume 时序竞态（可能影响 W1 / W3）

| PR | 链接 | 与 CubeSandbox 的关联 |
| --- | --- | --- |
| #8004 signal activated queue eventfds on resume | [link](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8004) | virtio 设备在 resume 时的事件通知竞态 |
| #7900 Avoid raciness on device activation | [link](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/7900) | virtio 设备激活竞态 |
| #8256 preserve kvmclock realtime and fill if needed | [link](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8256) | "先恢复时钟、再 resume vCPU"上游既定模式 |
| #8383 skip MSR_IA32_TSC restore so masterclock engages on vm.restore | [link](https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8383) | x86 TSC offset 在 restore 被写两次的竞态；#8343 是其 arm64 镜像 |

- CubeSandbox 故障顺序"network-agent 完成 TAP 配置 → 接口 LOWER_UP → CPU1 stall"中，**virtio-net 激活时序**是 W3 的候选变量。
- x86 经验：每个 vCPU 的时钟 offset 在 restore 时会被写两次，存在竞态 —— 与 arm64 的 vtimer offset 行为同构。

---

## 6. 与 CubeSandbox 假设（W1/W2/W3）的映射

文档第 7.2 节定义的三个风险窗口，与社区证据的对应关系：

| 窗口 | 范围 | 社区对应证据 |
| --- | --- | --- |
| **W1** 写 CTL 到写完 CNT/CVAL | timer 可能在完整 counter/deadline 写回前启用 | 主线 timer 寄存器按 `KVM_GET_REG_LIST` 顺序（CTL→CNT→CVAL）恢复，**CTL 在前不是 CubeSandbox 独有偏差**；真正 arming 多在首次 `KVM_RUN`，与 W3 重叠 |
| **W2** vCPU timer 状态完成 → vGIC 恢复完成 | timer PPI line 与 redistributor 状态竞态 | #8343（counter/vtimer 版本敏感）、#6966（vGIC/ITS 数据完整性）、#4960（GIC 恢复路径） |
| **W3** unpark → 首次正常 KVM_RUN | pending/PSTATE/MP state 决定 CPU1 是否收到首个 tick | #6001（恢复后 100% 空转）、#8004/#7900（virtio resume 激活竞态） |

---

## 7. 对 CubeSandbox 的行动建议（按性价比排序）

1. **~~【最廉价·优先】借 #6966 排雷~~ ✅ 已排除（2026-07-21 远端验证）**：builder 实际解析 rustc 1.77.2（< 1.80.0 显现阈值）；坏/好 Template 的 `gic-v3-its.snapshot_data` 结构完全一致（dist=568/rdist=48/icc=18，json_len=2342，无截断）；`ICC_CTLR_EL1=0x8400` 非零、priority_bits=5，UB 签名不存在。详见 `CUBESANDBOX_CH_ISSUE6966_UB_COMPARISON_20260721.md` §7。
2. **~~【复查移植正确性】核对 #8343 v2 的多 vCPU gating~~ ✅ 已通过/证伪（2026-07-21）**：CubeSandbox 已正确实现并穷尽测试 counter 写入的三种策略（boot-vCPU-only = v1/v3/v7；all-vCPU = v4；VM-ioctl = v5/v6），最佳均 99/100。**counter write gating 不是残留缺陷**，无需再复查。残留点在 `CNTV_CTL` 使能时机 / timer PPI vs vGIC 时序（见下方 #4）。
3. **【核对 fork 基线】** 确认 fork 是否含 #8343 / #8268 / #4960 / #8004 / #7900。旧 fork 大概率缺近期 aarch64 寄存器/GIC/virtio 恢复修复。
4. **【按文档第 10 节推进时序实验】** 最小无日志 A/B：`TIMER_CTL` 最后恢复；vGIC 恢复后重放 CTL；设等量延迟对照，区分"顺序修复"和"延迟掩盖"。同时采集 CPU1 timer PPI line/pending/active、GICR/ICC 状态、首次 `KVM_RUN` 前后事件。
5. **【内核变量】** #6001 与 #8343 都把内核/KVM 版本列为强变量。openEuler 6.6 是下游，vtimer VM-wide offset 行为取决于 backport。文档 12 节已把"第二台主机 / 新内核"列为未做项 —— 与社区线索一致，值得优先。

---

## 8. 一句话总结

> CubeSandbox 的故障 = **已知的 aarch64 多 vCPU snapshot/restore 脆弱性（社区 #8343 / #4244 / #6001 / #6966 印证）+ 上游尚未覆盖的"timer PPI vs vGIC 恢复时序"残留空白**。社区先例强力支持文档当前排查方向，但没有现成 patch 可直接达到 100/100。

---

## 附录 A — 全部链接索引

### Tier 1
- PR #8343：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8343
- Issue #6001：https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6001
- Issue #6966：https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6966
- 根因 commit `02f146f`：https://github.com/cloud-hypervisor/cloud-hypervisor/commit/02f146fef81c4aa4a7ef3555c176d3b533158d7a

### Tier 2
- Issue #4239：https://github.com/cloud-hypervisor/cloud-hypervisor/issues/4239
- PR #4244：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/4244
- PR #4960：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/4960
- PR #8268：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8268

### Tier 3
- PR #8004：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8004
- PR #7900：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/7900
- PR #8256：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8256
- PR #8383：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/8383

### 参考性
- Issue #6970（OPEN）：https://github.com/cloud-hypervisor/cloud-hypervisor/issues/6970
- v25.0 release notes：https://www.cloudhypervisor.org/blog/cloud-hypervisor-v25-0-released/

### 历史背景
- Issue #1644 Basic VM snapshot/restore support for AArch64：https://github.com/cloud-hypervisor/cloud-hypervisor/issues/1644
- PR #2811 AArch64: Enable snapshot/restore：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/2811
- PR #3049 vmm: Fix live-migration on AArch64：https://github.com/cloud-hypervisor/cloud-hypervisor/pull/3049

---

## 附录 B — 检索方法与限制

- **方法**：GitHub REST API 搜索 issues/PRs（`api.github.com/search/issues`），关键词组合包括 `aarch64 timer snapshot restore`、`arm64 restore vcpu hang`、`vtimer`、`CNTVCT`、`counter offset`、`migration aarch64 timer`、`softirq`、`stall` 等；对命中的高相关条目拉取正文与评论；对 PR 拉取 commits 与 files。
- **限制**：
  - 仅检索 cloud-hypervisor 主仓 issue/PR 标题与正文（GitHub 搜索不全文索引评论正文，可能漏掉只在评论里讨论 timer/vGIC 顺序的条目）。
  - 未检索 rust-vmm/kvm-ioctls、rust-vmm/vfio 等依赖仓的相关改动。
  - 未覆盖 Cloud Hypervisor 邮件列表（lists.cloudhypervisor.org）与 Slack —— 部分深入讨论可能在邮件列表归档中，建议作为后续补充检索源。
  - 检索时间点 2026-07-21；#8343 系 2026-06 才合并，相关后续讨论可能仍在演进。
