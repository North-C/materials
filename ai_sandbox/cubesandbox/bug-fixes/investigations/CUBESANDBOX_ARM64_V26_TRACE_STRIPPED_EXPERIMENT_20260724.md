# CubeSandbox ARM64 v26 trace-stripped 实验：判定 v23 20/20 是否来自插桩副作用

日期：2026-07-24
测试节点：`root@192.168.25.90`（stock 内核 `6.6.0-132.0.0.111.oe2403sp3.aarch64`）
源码基线：社区 `v0.5.1`，commit `a164417f497234a0d787cb328b0ae96480b1569b`
实验分支：`experiment/arm64-trace-stripped-v26`（worktree `source_code/CubeSandbox-v0.5.1-arm64-trace-stripped-v26`）

## 1. 目标

回答 [handoff §10.5/§10.6](CUBESANDBOX_ARM64_MULTIVCPU_HANDOFF_PLAN_20260724.md) 遗留的观察者效应问题：

> v23 timeline-trace shim 构建的 2-vCPU Template 即使 trace-off、甚至恢复侧换回纯社区 shim 仍为 `20/20`；而社区构建的 Template 只有 `2–3/20`。这到底是
> (A) v23 插桩被编译进二进制后改变了 Template 构建/pause/snapshot 阶段的二进制布局/时序（副作用），还是
> (B) 只是连续抽到两份 good Template（抽样波动）？

v23 插桩原本由运行时文件门禁（`/tmp/cube_arm64_first_entry_trace_enable`）控制；trace-off 时插桩函数早返回，但插桩代码仍编译进二进制、且每个调用点仍做一次 `stat` 系统调用——即“v23 trace-off 实验中的 trace 开销”。

## 2. 方法：编译期剥除插桩

新增 Cargo feature `arm64-first-entry-trace`（默认 off），沿 `containerd-shim-cube-rs → cube-hypervisor → vmm → hypervisor` 转发（仿既有 `lib_support`）。把 v23 全部插桩门控在该 feature 后：

- `hypervisor/vmm/src/cpu.rs`（25 处）、`vm.rs`（29 处）：`#[cfg(all(target_arch="aarch64", feature="kvm"))]` 全为 v23 新增，整文件替换为追加 `feature="arm64-first-entry-trace"`。
- `hypervisor/hypervisor/src/kvm/mod.rs`：定向门控 v23 新增的 6 const + 2 helper fn + `KvmVcpu.id` 字段/初始化 + `set_state` 内 8 段插桩（社区已有 28 处同谓词不动）。
- `hypervisor/hypervisor/src/kvm/aarch64/gic/{mod,icc_regs,redist_regs}.rs`：门控 `trace_gic_state`、`decode_icc_states`/`decode_ppi_state` 及其测试、相关 import 与 `set_state` 插桩段。

两个提交：`e44a751`（导入 v23 patch 作基线）、`cd93f70`（加门控）。本地 aarch64 `cargo check`（vmm crate，feature on/off）均通过。

## 3. 构建产物与校验（builder `ghcr.io/tencentcloud/cubesandbox-builder:ubuntu2004-arm64`，rustc 1.89.0）

固定 `CUBE_VERSION=v0.5.1 CUBE_COMMIT=a164417f… CUBE_BUILD_TIME=2026-07-23T08:10:00Z`，使两个产物仅 feature 不同。

| 产物 | `ARM64_FIRST_ENTRY` 串 | flag-path 串 | SHA256 |
|---|---:|---:|---|
| bin-stripped（feature off） | **0** | **0** | `29b91ce77a96bad7…` |
| bin-instrumented（feature on） | 4 | 1 | `a5f51ee425ae4254…` |
| 干净社区 a164417f（对照） | 0 | 0 | `4702fde1390fc8ec…`（== 官方） |

- 干净社区构建**逐字节复现**官方社区哈希 `4702fde1…`，证明 builder 工具链与 CI 一致、构建可复现。
- stripped 零插桩（零字符串、零插桩符号、零门禁系统调用）→ 功能等价社区。
- stripped 与干净社区有 ~24 字节代码 + ~4 KB 页对齐 padding 残留（源于加了 Cargo feature；24 字节落在两个 `KvmGicV3Its` gic 方法内）。非插桩开销，不影响实验结论。

## 4. Template A/B 实验（trace off，每组建 1 份全新 2-vCPU Template + restore 20 次）

| 组 | 部署的 shim（构建+恢复同 shim） | 新 Template | 通过 |
|---|---|---|---:|
| v1-stripped | stripped（零插桩） | `tpl-d531debb219747ae8d69e947` | **5/20** |
| v2-instrumented | instrumented（v23 插桩，本次重建 `a5f51ee4`） | `tpl-55fd01fc795545a8ad008310` | **3/20** |

对照口径（[matrix 报告 §10](CUBESANDBOX_ARM64_VCPU_COUNT_TEMPLATE_MATRIX_REPORT_20260723.md)）：原 v23 `cf25ae12` 同口径 `20/20`；社区 `2–3/20`。

## 5. 结论

**重建 v23 源码——无论是否带插桩——都不复现 v23 的 20/20。**

- stripped（零插桩）= 5/20，instrumented（v23 插桩重建）= 3/20，二者同处于“坏”区间，与社区基线一致，远低于原 v23 的 20/20。
- 二者唯一差异是 feature（插桩在场与否），结果同坏 → **插桩的“在场”并非 v23 20/20 的决定因素**。
- 因此 handoff §10.5/§10.6 的假设 (A)（插桩二进制布局副作用）被否定；倾向 (B)：原 v23 两份 good Template 是抽样/构建偶然，绑定 `cf25ae12` 那次具体构建（含其特定 `CUBE_BUILD_TIME`/版本串导致的布局），不可由重建复现。

工程含义：**v23 不是可复现的修复**，与既有综合结论一致——用户态无确定性修复，根因位于 KVM/内核 timer/vGIC 首次 entry 边界（见 [KVM vtimer-active 根因](CUBESANDBOX_ARM64_KVM_VTIMER_ACTIVE_ROOT_CAUSE_20260722.md)）。不应把 v23 或任何“加日志/插桩后变好”的版本当作修复发布。

## 6. 后续

- 若要彻底区分“`cf25ae12` 具体布局副作用”与“纯抽样波动”：用 `cf25ae12` 的精确构建 env（`CUBE_VERSION=0.0.0-dev`/`CUBE_COMMIT=unknown`/`CUBE_BUILD_TIME=2026-07-23T11:36:15Z`）重建 instrumented 再测。无论哪种，结论“v23 非修复”不变。
- 若要 stripped 真字节等价社区：改用 `RUSTFLAGS=--cfg arm64_first_entry_trace`（零 Cargo.toml 改动）替代 Cargo feature，可消掉 24 字节残留。
- 仍建议多份 Template 重复以缩窄概率区间；但 3/20、5/20 对 20/20 的对比已具决定性。

## 7. 远端状态与资产

实验结束已恢复纯社区 shim（live SHA256 `4702fde1…`），六服务 active，sandbox/shim/task `0/0/0`。
结果目录：`.90:/home/lyq/arm64-v26-trace-stripped-exp-20260724/groups/{v1-stripped,v2-instrumented}/`。
构建产物：`.90:/home/lyq/CubeSandbox-v0.5.1-arm64-trace-stripped-v26/_output/{bin-stripped,bin-instrumented}/`。
