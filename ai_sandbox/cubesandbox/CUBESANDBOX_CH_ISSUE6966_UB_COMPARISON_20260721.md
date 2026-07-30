# Issue #6966（get_device_attr UB）与 CubeSandbox 的对照分析

## 1. 文档信息

- 日期：2026-07-21
- 关联文档：
  - `CUBESANDBOX_CH_COMMUNITY_PRECEDENT_SURVEY_20260721.md`（§3.3 Issue #6966）
  - `CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md`
- 社区条目：cloud-hypervisor Issue #6966，根因修复 commit `02f146fef81c4aa4a7ef3555c176d3b533158d7a`
  （Alyssa Ross，2024-08-12，"hypervisor: kvm: aarch64: fix get_device_attr() UB"）
- 分析源码树：`source_code/CubeSandbox`（v0.5.1，社区基线 `a164417f4`）

## 2. 结论

> **CubeSandbox 源码中完整存在 #6966 的 UB 代码模式（未回移 `02f146f`），但当前构建
>  pinned 在 Rust 1.77.2（< 1.80.0），UB 的显现条件不成立，因此该类问题在当前
>  二进制中不存在、也不构成当前 timer/vGIC 故障的根因。它是一个潜在风险：
>  一旦工具链升级到 ≥ 1.80，会立刻复现 #6966 式的 vGIC 快照截断。**

判定依据分三层：UB 模式逐处比对（§3）、显现条件比对（§4）、故障模式反向验证（§5）。

## 3. UB 模式逐处比对：`02f146f` 修复前代码在 CubeSandbox 中逐字存在

#6966 的根因：`DeviceFd::get_device_attr` 通过 `kvm_device_attr.addr` 向该地址**写入**，
而旧代码传入的是**不可变局部变量**的 `*const` 指针——按 Rust 规则这是 UB。Rust 1.80.0
的优化变更（rust-lang/rust `d2d24e3`）使 release 构建中这些写入被优化掉，
`get_icc_regs` 读到的 `ICC_CTLR_EL1` 恒为 0，`num_priority_bits` 被算成 1，
AP 寄存器被跳过，`gic-v3-its` 快照数据从 2339 项截断为 1698 项。

`02f146f` 的修复方式是把每个 `_attr_access(fd, ..., val: &u32, set: bool)` 拆成
`_attr_set`（传 `&val as *const`，只写）和 `_attr_get`（传 `&mut val as *mut`，只读）。

CubeSandbox fork（基于 cloud-hypervisor v28.0，早于 2024-08 的修复）四个文件全部是
修复前形态：

| 文件 | 旧函数 | 行号 | get 路径调用点 | 绑定可变性 |
| --- | --- | --- | --- | --- |
| `hypervisor/hypervisor/src/kvm/aarch64/gic/dist_regs.rs` | `dist_attr_access` `:80-90`，`addr: val as *const u32 as u64` | `:84` | `read_ctlr` `:100-103`、`get_interrupts_num` `:111-123`、`get_dist_regs` `:177-181` | **不可变**（`let val: u32 = 0`） |
| `hypervisor/hypervisor/src/kvm/aarch64/gic/icc_regs.rs` | `icc_attr_access` `:82-96` | `:86` | `get_icc_regs` `:110-148`（#6966 中实际被优化掉的正是这段） | **不可变**（`let val = 0`） |
| `hypervisor/hypervisor/src/kvm/aarch64/gic/redist_regs.rs` | `redist_attr_access` `:99-109` | `:103` | `access_redists_aux` `:131-140` | `mut` 绑定但取 `&val` 共享引用转 `*const`，同一 UB 形态 |
| `hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs` | `gicv3_its_attr_access` `:30-50` | `:40` | ITS 状态读取 `:327-381`（`its_baser_state/its_ctlr_state/...`） | **不可变** |

即：上游修复涉及的 4 个文件、所有调用点，CubeSandbox 与修复前代码一致，**未回移
`02f146f`**。同时也未包含配套上游修复 rust-vmm/kvm-ioctls#273（把
`get_device_attr` 标记为 `unsafe`）。

## 4. 显现条件比对：当前工具链不会让 UB 显现

#6966 的关键事实是该 UB **直到 Rust 1.80.0 才在 release 模式下显现**（上游原话：
"an optimisation change in Rust 1.80.0 caused the test to start failing when built in
release mode"）。

CubeSandbox 的实际构建工具链：

- `CubeShim/rust-toolchain.toml`：`channel = "1.77.2"`。
- `docker/Dockerfile.builder:11-14`：`RUST_TOOLCHAIN_HYPERVISOR=1.77.2`（builder 镜像
  同时装 1.77.2/1.85/1.89，默认 1.89，但 rustup 按目录的 `rust-toolchain.toml` 解析）。
- v15 实际构建命令（`remote-results/arm64-vcpu-sync-v10-20260720/v15-timer-state-trace/deploy/build-offline-cached.log`）：

  ```text
  cd /workspace/CubeShim && cargo build --release --locked --offline
  ```

  工作目录在 `CubeShim` 内，rustup 解析到 `CubeShim/rust-toolchain.toml` → **1.77.2**。

1.77.2 < 1.80.0，旧优化器不利用该 UB，写入按源码语义发生，vGIC 快照数据完整。
因此**当前部署的二进制（官方 v0.5.1 及 v1-v16 实验构建）不携带 #6966 类缺陷**。

## 5. 故障模式反向验证：CubeSandbox 的故障形态与 #6966 不符

若 UB 显现，预期表现与 CubeSandbox 实际观测矛盾：

| 观测点 | #6966（UB 显现） | CubeSandbox 实际 |
| --- | --- | --- |
| 失败确定性 | release 二进制每次 restore 必失败 | 间歇性（最佳 99/100）；同一坏 Template 才确定性失败 |
| 首个错误 | `RestoreGic(SetDeviceAttribute(Invalid argument))`，VMM 恢复直接报错 | VMM restore 成功，失败点在 restore 之后的 `reset guest time` ttrpc 超时 |
| 快照数据 | `gic-v3-its.snapshot_data` 截断（2339→1698） | v15 记录的快照状态完整可读（`sys_regs=259`，timer 五元组值合理） |
| 恢复后状态 | vGIC 状态全错，guest 立即不可用 | vsock/agent 一度 ready，CPU1 timer tick 数秒后才 stall |
| 新 Template | 同一 release 二进制做的新 Template 同样必坏 | v12/v15 新 Template 99-100/100 |

此外 v16 读回实验证明 KVM 接受了保存的 timer 状态且未被静默修改；若 vGIC 快照在
构建期已被截断，恢复会在 `restore_vgic_and_enable_interrupt`（`vm.rs:2286-2359`）
阶段即报错，不可能走到 guest agent 阶段。

## 6. 残留风险与建议

1. **潜在风险（中优先级）**：同一 builder 镜像内默认工具链是 1.89。以下任一变化都会
   让 UB 立刻显现并复现 #6966：
   - 在 `CubeShim` 目录之外驱动构建（rust-toolchain.toml 不生效，解析到默认 1.89）；
   - 升级 `CubeShim/rust-toolchain.toml` 的 channel 到 ≥ 1.80；
   - 上游 `kvm-ioctls` 升级后按 #273 将 `get_device_attr` 标记 `unsafe`，旧调用点
     会直接编译失败（这反而是好事，编译期兜底）。
2. **建议回移 `02f146f`**：该修复是机械式拆分（`_access` → `_set`/`_get`），无语义
   变化、无行为变化，可一次性消除潜在风险。改动范围即 §3 表中 4 个文件。
3. **廉价收尾验证（远端执行，可彻底关闭这条线）**：
   - builder 容器内 `cd /workspace/CubeShim && rustc -V`，确认输出 1.77.2；
   - diff 坏 Template（`tpl-3394...`）与好 Template（`tpl-687c...`/`tpl-7c04...`）
     的 `gic-v3-its.snapshot_data` 条目数，预期一致（1.77.2 下不会截断）。

## 7. 远端验证结果（2026-07-21，root@192.168.25.90）

### 7.1 工具链确认 ✅

```text
$ docker run --rm -v <远端工作树>:/workspace -w /workspace/CubeShim \
    ghcr.io/tencentcloud/cubesandbox-builder:ubuntu2004-arm64 bash -lc "rustc -V"
rustc 1.77.2 (25ef9e3d8 2024-04-9)
1.77.2-aarch64-unknown-linux-gnu (overridden by '/workspace/CubeShim/rust-toolchain.toml')
```

构建目录内的工具链解析确实落在 1.77.2，UB 显现条件（≥ 1.80.0）不成立。

### 7.2 GIC 快照数据完整性比对 ✅

解析各 Template `2C2000M/snapshot/state.json` 中
`snapshots["gic-v3-its"]["snapshot_data"]["gic-v3-its-section"]["snapshot"]`
（内嵌 JSON 字符串），逐项计数：

| Template | dist | rdist | icc | total | json_len | 已知结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `tpl-3394a026...`（v10，确定性失败） | 568 | 48 | 18 | 634 | 2342 | 坏 |
| `tpl-5f25f261...`（v11，0/5） | 568 | 48 | 18 | 634 | 2342 | 坏 |
| `tpl-80e1fa6a...`（社区旧，4/5） | 568 | 48 | 18 | 634 | 2342 | 基本好 |
| `tpl-7c04ce72...`（v12，99/100） | 568 | 48 | 18 | 634 | 2342 | 好 |
| `tpl-687c8890...`（v15，100/100） | 568 | 48 | 18 | 634 | 2342 | 好 |

坏/好 Template 的 GIC 快照结构完全一致，无任何截断（#6966 显现时为 2339→1698）。

### 7.3 UB 显现的关键签名不存在 ✅

#6966 中 UB 的直接签名是 `ICC_CTLR_EL1` 读回 0 → `num_priority_bits=1` → AP 寄存器被
跳过。实际快照数据：

```text
tpl-3394（坏）: vcpu0/vcpu1 均 SRE=0x7 CTLR=0x8400 (priority_bits=5) IGRPEN1=0x1 PMR=0xf0
tpl-687c（好）: 数值完全相同
```

`CTLR=0x8400` 非零、`priority_bits=5`（Kunpeng GIC 实现 5 级优先级，9 个 ICC 寄存器/
vCPU 与之一致），证明 `get_icc_regs` 的读路径真实返回了 KVM 数据，未被优化掉。

### 7.4 结论更新

**#6966 类问题在 CubeSandbox 当前部署与实验二进制中不存在，该线索正式关闭。**
源码中的 UB 模式（未回移 `02f146f`）仍建议按 §6.2 修复，以消除工具链升级风险。
4. **对当前故障排查的意义**：#6966 这条线可以排除，不占用 W2（vGIC 恢复窗口）的
   实验预算；P0 假设（timer CTL 早于 CNT/CVAL 与 vGIC 恢复顺序）不受影响，v17
   CTL-last 实验仍按主报告 §20 推进。
