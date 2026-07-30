# CubeSandbox ARM64 2/3/4 vCPU 新模板对照报告

日期：2026-07-23  
测试节点：`192.168.25.90`  
测试对象：CubeSandbox v0.5.1 ARM64 Template snapshot/restore

## 1. 结论

综合历史 patched 矩阵和本次社区 v0.5.1 全栈矩阵，结论更新为：

1. 本次社区矩阵对 vCPU 数量边界给出了很强的复现证据：两份全新 2 vCPU Template 在两种清理协议下合计 `5/40`，两份 3 vCPU 和两份 4 vCPU Template 分别为 `40/40`。
2. 9 个宿主二进制和 2 个服务镜像已经替换为社区 v0.5.1、commit `a164417f497234a0d787cb328b0ae96480b1569b` 的构建产物；社区仓库内的 VMM/hypervisor 与 cubecow 模块也被静态链接进对应二进制。2 vCPU 仍高概率失败，说明问题不能由 v0.3/v0.5 cmdline 对齐或 CubeSandbox 宿主组件替换单独修复。
3. 本次两份 2 vCPU Template 都高失败，而 3/4 vCPU 全成功，支持“2 vCPU 显著提高该故障概率”；但历史 patched 矩阵仍存在 2 vCPU `20/20` 和 3 vCPU `0/20` 的反例，因此 CPU 数不是跨所有故障模式都成立的充分条件。
4. 本次 2 vCPU A/B Template 的序列化 GICv3/ITS 状态完全相同；二者保存的 virtual timer 状态方向相反，却都高失败。一次 `state.json` 中的 GIC/ITS 寄存器或 timer deadline 不能单独解释结果。
5. 按组连续测试时，2 vCPU 失败留下 18 个 shim；组末清理后服务恢复为 sandbox/shim/task `0/0/0`。隔离清理协议仍为 `3/20`，因此 CubeSandbox 服务残留不是首个故障的必要前提，但失败后的资源回收异常会污染后续测试。
6. guest kernel、guest rootfs、envd 和 host kernel 不是本次从 CubeSandbox 社区 commit 重建的产物。社区宿主栈仍失败后，排查重心应上移到 guest timer/RCU、host KVM/vtimer 调度以及 snapshot pause/首次 vCPU entry 的交互。
7. 第一项 P0 时间线实验表明，2/3/4 vCPU 的恢复线程都会在正式 `vm_resume_begin` 前执行一次 `immediate_exit` pause-drain `KVM_RUN`；该调用会让每个 vCPU 的 virtual timer IRQ 27 置 pending，但此时均没有真正的 `kvm_entry`。这一顺序是成功 2/3/4 vCPU control 的共同路径，不是 2 vCPU 独有异常。
8. v23 生成的两份全新 2 vCPU Template 均为 `20/20`。其中 trace-off Template 在恢复纯社区 shim 后仍为 `20/20`，所以结果不支持“v23 恢复侧代码已修复问题”；更强的信号来自 Template 构建/快照时序或产物差异，但当前只有两份 v23-built Template，仍不能排除偶然构建到 good Template。
9. v23 主矩阵的 2/3/4 vCPU restore 和 guest `nproc` 均为 `20/20`。4 vCPU 的完整生命周期仅 `7/20` 是因为 12 次 HTTP 408 和 1 次 CubeMaster delete deadline，不能计为 13 次 restore 失败。

因此，当前最准确的判断是：**社区 v0.5.1 宿主栈和已对齐 cmdline 都没有修复问题；2 vCPU 是干净社区矩阵中的强概率条件，但 CPU 数、静态 GIC/ITS/timer 值以及 pause-drain 阶段提前置 pending 的 IRQ 27 都不是已证实的充分根因。第一项 P0 的交叉对照把下一步重点进一步收敛到 Template 构建/暂停/发布阶段，但尚需随机化多 Template A/B 才能建立因果关系。**

## 2. 测试控制

每组测试均满足以下条件：

- 测试前 CubeSandbox API 健康。
- 测试前沙箱、shim、task 为 `0/0/0`。
- 不沿用 baseline Template 的 snapshot；baseline Template 只用于读取相同的容器/rootfs 请求规格。
- 每个测试项重新创建独立 Template。
- 内存固定为 `2000 MiB`，仅改变 CPU 为 `2000m`、`3000m`、`4000m`。
- Template 必须进入 `READY`，并再次读取 `create_request` 校验 CPU 值。
- restore 后通过 guest 内 `nproc` 校验实际 CPU 数，再删除 Sandbox。
- VMM 日志同时校验 `boot_vcpus`、逐个 `Restoring VCPU` 和 `Starting vCPUs`。
- 每个 CPU case 结束后检查并恢复到 `0/0/0`，避免前一组残留污染后一组。

测试脚本修正了 direct TAP envd 探测：除连接配置外，还同步更新 SDK Commands 实例实际使用的 `_envd_api_url`。修正前的 TLS 证书错误只属于测试探测链路，不计为 VM restore 失败。

## 3. 组件组合

### 3.1 实验前 trace-v22 组合

| 组件 | SHA256 |
|---|---|
| shim `v0.5.1-arm64-first-entry-trace-v22` | `c57d617f4fe017ac0ce068565d07dddfed0792ba0e124f9f1a913f90a1675c37` |
| runtime `v0.5.1` | `d1e2db0097d258f12cfd5727f92b074ff4a5520cbee5ee05e59144c05962a7a9` |

### 3.2 v0.3 cmdline 对齐 patched 组合

| 组件 | SHA256 |
|---|---|
| patched shim | `74f129a7407006f9d1d5384e6a9219daa1cd827e7ec0aa4d55029d8e9718b55c` |
| baseline runtime | `c6c9d04496de9a3eb7dc43d2f10688e72f30a6f64743208f6562986d4627b049` |

patched 组实际 VMM cmdline 为：

```text
root=/dev/pmem0 rootflags=dax,errors=remount-ro ro rootfstype=ext4
panic=1 printk.devkmsg=on console=ttyAMA0,115200 net.ifnames=0 audit=0
LANG=C raid=noautodetect agent.debug_console agent.debug_console_vport=1026 quiet
```

其中不存在 `highres=off`、`clocksource=kvm-clock`、`earlyprintk=ttyS0` 和 `mitigations=off`，说明此前的 ARM64 参数对齐确实落地。

## 4. trace-v22 初始矩阵

三个 Template 均为本轮新建，最终使用修正后的 `nproc` 探测各执行 10 次。

| CPU | Template | create | `nproc` | delete | 完整生命周期 |
|---:|---|---:|---:|---:|---:|
| 2 | `tpl-6032c0b05d7f49269006d29a` | 10/10 | 10/10 | 10/10 | 10/10 |
| 3 | `tpl-5c2f60f6312c4c30a0e7d2e7` | 10/10 | 10/10 | 10/10 | 10/10 |
| 4 | `tpl-c4fb24a2fa604c5088045ec2` | 10/10 | 10/10 | 10/10 | 10/10 |

三组 VMM 日志分别确认：

- 2 vCPU：20 个首轮配置记录均为 `boot_vcpus: 2`，每次恢复 CPU0-1。
- 3 vCPU：20 个首轮配置记录均为 `boot_vcpus: 3`，每次恢复 CPU0-2。
- 4 vCPU：20 个首轮配置记录均为 `boot_vcpus: 4`，每次恢复 CPU0-3。

本组合累计 91 次 restore（包括初始矩阵、HTTP health 补测、`nproc` smoke 和最终 `nproc` 矩阵），没有发现 RCU stall、RCU kthread starvation、timer handling issue、soft/hard lockup 或 panic。

证据：[validated-summary.json](remote-results/arm64-vcpu-count-matrix-20260723-152244/results/validated-summary.json)。

该结果不能外推为产品问题已修复，因为 trace-v22 插桩会改变首次 vCPU 运行时序，而且它不是此前参数对齐失败实验所使用的组件。

## 5. patched 新模板矩阵

### 5.1 按 Template 展开的结果

| CPU | Template | 观察次数 | create | `nproc` | 完整生命周期 | 主要表现 |
|---:|---|---:|---:|---:|---:|---|
| 2 | `tpl-5da2494d80424d10a93d18bd` | 20 | 20/20 | 20/20 | 20/20 | 稳定成功 |
| 2 | `tpl-92f253df57e7477883163cf7` | 16 | 1/16 | 1/16 | 1/16 | 15 次 timer/RCU/ttrpc 同型失败；为避免服务过载提前停止 |
| 3 | `tpl-23d1abfcd0f5418c935a64c5` | 20 | 0/20 | 0/20 | 0/20 | restore/resume 后立即 `Recv len invalid:0` |
| 3 | `tpl-c3facd60eed34fd9833d4dd8` | 20 | 20/20 | 20/20 | 20/20 | 同规格重建后稳定成功 |
| 4 | `tpl-fe4b0d9deb3c4268a395989e` | 20 | 20/20 | 20/20 | 20/20 | 稳定成功 |
| 4 | `tpl-a9baf838c44f45509cabb810` | 20 | 20/20 | 20/20 | 20/20 | 服务恢复后独立重建仍稳定成功 |

证据：[comparison-summary.json](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/comparison-summary.json)。

### 5.2 坏 2 vCPU Template

第二份 2 vCPU Template 的 16 个观察样本中，1 次完整成功，15 次失败。15 个失败实例全部同时出现：

- `reset guest time failed: ... Receive packet timeout`
- `rcu_preempt detected stalls`
- `rcu_preempt kthread starved`
- `Possible timer handling issue on cpu=1`
- `destroy sandbox failed: ... Receive packet timeout`

各签名覆盖的独立失败实例都是 `15/15`，不是把一个实例的重复日志误计为多个失败。

证据：[signature-counts.json](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/cpu2-replicate/signature-counts.json)、[results.jsonl](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/cpu2-replicate/results/results.jsonl) 和 [cube-shim-failures.log](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/cpu2-replicate/cube-shim-failures.log)。

这重新确认了原始 2 vCPU timer/RCU 故障仍然存在，但第一份 2 vCPU Template 的 `20/20` 又说明“2 vCPU 必然失败”不成立。

### 5.3 坏 3 vCPU Template

第一份 3 vCPU Template 为确定性的 `0/20`。VMM 每次都完成：

1. 读取 `boot_vcpus: 3, max_vcpus: 3`。
2. 恢复并创建 CPU0、CPU1、CPU2。
3. 记录 `vm has been restored` 和 `vm has been resumed`。
4. 约 3 ms 后 Shim 收到 `Create sandbox failed:Recv len invalid:0`，随后关闭 VMM。

20 个失败实例都没有 RCU stall 或 timer handling issue。这是与坏 2 vCPU Template 不同的失败模式，更接近 restore 后 guest/Shim 通信流或被快照化的 agent/probe 状态异常。

重新创建第二份 3 vCPU Template 后，相同测试立即变为 `20/20`，guest 内均返回 `ready vcpus=3`。因此该故障跟随第一份 Template 产物，不跟随 3 vCPU 规格本身。

证据：[3 vCPU signature counts](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/cpu3/signature-counts.json)、[坏模板结果](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/cpu3/results/results.jsonl) 和 [重建模板结果](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/cpu3-replicate/results/results.jsonl)。

## 6. 对 CPU 数假设的判断

| 假设 | 本轮判断 | 依据 |
|---|---|---|
| 2 vCPU 才会失败 | 不成立 | 两份 2 vCPU Template 分别为 20/20 和 1/16 |
| 3 vCPU 不会失败 | 不成立 | 第一份 3 vCPU Template 为 0/20，第二份为 20/20 |
| 4 vCPU 当前更稳定 | 暂时支持 | 两份独立 4 vCPU Template 共 40/40，但 Template 数仍少 |
| 增加 CPU 数已修复 timer/RCU | 证据不足 | 4 vCPU 未复现不等于消除竞态；3 vCPU 还暴露了另一种坏快照表现 |
| 参数对齐可以修复 | 不成立 | cmdline 已对齐，坏 2 vCPU Template 仍完整复现原故障链 |
| Template 构建时状态是关键变量 | 明显增强 | 同规格重建可从 0%/6.25% 变为 100% |

CPU 数仍可能调制竞态概率。尤其 4 vCPU 增加了 vCPU、virtual timer、GIC redistributor/SGI/PPI 状态数量，也会改变 snapshot pause 与首次 `KVM_RUN` 的调度顺序。但当前数据要求把分析单位从“每次 restore”提升为“每次 Template 构建 + 该 Template 的多次 restore”。只对一份 Template 重复 100 次，无法区分 CPU 影响和坏 Template 固化效应。

## 7. good/bad Template 日志与快照结构化对比

本节不是对 JSON 文本做行级 diff，而是先解析 `state.json` 内嵌的 VMM snapshot JSON，再分别比较 vCPU KVM state、GICv3/ITS、virtio/vsock 设备状态。Template ID、请求 UUID、创建时间、TAP/IP/MAC 等分配值先归一化，避免把必然变化误判为根因。

分析器：[analyze_template_snapshot_pairs.py](scripts/analyze_template_snapshot_pairs.py)  
完整结果：[snapshot-log-structural-comparison.json](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/snapshot-log-structural-comparison.json)

### 7.1 静态输入与版本

2 vCPU good/bad、3 vCPU bad/good、4 vCPU good/good 三组中，以下文件归一化后均一致：

- `template-request.json`
- snapshot `config.json`
- snapshot `metadata.json`
- snapshot `catalog.json`

`template-info.json` 只剩 `compat_checked_unix` 的检查时间不同。2 vCPU good/bad 的 kernel digest、rootfs/image、VMM `ch_version=1.0.3`、CPU/内存、cmdline 和设备配置没有发现语义差异。

因此，现有证据不支持“坏模板收到不同请求”或“坏模板使用了不同 kernel/image/VMM 配置”。

### 7.2 GICv3/ITS

2 vCPU good/bad Template 的 VMM 序列化 GIC 状态逐值完全一致：

| 状态 | 结果 |
|---|---|
| distributor `dist` | 568/568 项，0 项不同 |
| redistributor `rdist` | 48/48 项，0 项不同 |
| per-vCPU `icc` | 18/18 项，0 项不同 |
| `GICD_CTLR` | 相同，均为 82 |
| `ITS_CTLR` / `ITS_IIDR` | 相同 |
| `ITS_CBASER` | 相同 |
| `ITS_CWRITER` / `ITS_CREADR` | 相同，均为 2080 |
| 8 个 `ITS_BASER` | 逐项相同 |

3 vCPU bad/good 只有 `rdist` 的 72 项中 2 项不同；两份都成功的 4 vCPU good/good 对照也存在 `dist` 2 项、`icc` 1 项不同。因此，少量 GIC 寄存器差异本身属于 snapshot 时刻状态变化，不能单独解释失败。

源码中的 `Gicv3ItsState` 只序列化上述寄存器数组与 ITS 标量；ITS device/collection/interrupt translation tables 通过 `KVM_DEV_ARM_ITS_SAVE_TABLES` 写入 guest RAM。当前归档只有 `state/config/metadata/catalog.json`，没有 catalog 指向的 memory volume payload，因此本节能确认“序列化的 GIC/ITS 寄存器一致”，但还不能确认“guest RAM 内 ITS tables 逐字节一致”。

### 7.3 vCPU core/system/timer state

2 vCPU good/bad 的每个 vCPU 都包含相同的 259 个 KVM one-reg ID，MP state 也相同。CPU0 有 8 个、CPU1 有 10 个 system register 值不同，其余分别为 251 和 249 个相同。非 timer 差异主要是 `TTBR0_EL1`、`ESR_EL1`、`FAR_EL1`、`VBAR_EL1`、`TPIDR_EL1/EL0`，与不同启动地址、当前任务和异常现场相符。

坏 2 vCPU Template 最显眼的 timer 瞬时值在 CPU1：

| Template | `CNTV_CTL_EL0` | `CNTV_CVAL-CNTVCT` |
|---|---:|---:|
| good 2 vCPU | 5 | +91357 |
| bad 2 vCPU | 1 | -160775 |

但这个模式不是失败的充分条件：成功的第二份 3 vCPU Template 三个 vCPU 分别出现 `-73440`、`-52707`、`-33649` 且 `CNTV_CTL_EL0=1`；成功的第二份 4 vCPU Template 也出现 `-162441` 且 `CNTV_CTL_EL0=1`。两份都成功的 4 vCPU control 之间，部分 vCPU 的 `CNTV_CTL_EL0` 同样会在 1 和 5 之间变化。

所以 timer state 仍是高优先级相关变量，但不能根据一次 state.json 中的负 deadline 或 CTL 值直接判定快照损坏。更可能需要结合 pause 后的 register 保存顺序、memory publish 时刻，以及首次 `KVM_RUN` 后内核 timer 注入顺序分析。

### 7.4 virtio/vsock 状态

三组独立 Template 的可变 device sections 都不会逐字节相同。主要差异是：

- virtio queue 的 `desc_table`、`avail_ring`、`used_ring` guest 地址；
- vsock `connections` 中的 local port 顺序/数量；
- vsock backend 的 `local_port_set` 顺序/数量。

3 vCPU bad/good 的 vsock connection 数为 2 对 3，但两份都成功的 4 vCPU control 也为 3 对 2。2 vCPU good/bad 的连接数相同，只是 local port 排列不同。因此，当前看不到仅出现在 bad Template 的静态 vsock 形状。

源码定位确认 3 vCPU 的 `Recv len invalid:0` 不是 guest agent 返回空 ttrpc message：Shim 在 `AsyncUtils::connect_agent` 中连接 host 侧 `/run/vc/vm/<sandbox-id>/cube.sock`，发送 vsock mux 握手 `CONNECT 1024\n`，随后第一次 `UnixStream::read_buf` 直接得到 EOF（0 字节）。该错误发生在 `agent is ready` 之前，因此应优先检查 VMM vsock backend/muxer 恢复、host Unix socket 生命周期和 guest vsock 1024 监听就绪时序。

仅比较 snapshot 中 `connections`/`local_port_set` 仍不足以判定根因：两份成功 4 vCPU control 也存在 2/3 个连接的差异。新矩阵需要同时记录 cube.sock 创建/accept/close、CONNECT request/response 和 guest 1024 listener 首次就绪时间。

### 7.5 日志时序与根因边界

| Template | 中位生命周期 | 结果/首个错误 |
|---|---:|---|
| good 2 vCPU | 0.6409 s | 20/20 |
| bad 2 vCPU | 8.0444 s | 15/16 为 guest-time ttrpc timeout，随后 RCU/timer stall |
| bad 3 vCPU | 0.02795 s | 0/20，`Recv len invalid:0` |
| good 3 vCPU | 0.63375 s | 20/20 |

坏 2 vCPU Template 在第 1-11 次失败后，第 12 次完整成功，随后第 13-16 次再次失败。相同 state/memory snapshot 能在失败之间成功一次，说明它不是“静态内容必然不可恢复”；宿主调度、首次 vCPU entry、timer 注入或 restore 后通信时序仍是必要变量。VMM 日志中没有 GIC/ITS restore error，15 个失败 restore 只有 2 条 ttrpc Task/State timeout error；hypervisor 本身均完成 restore/resume。

坏 3 vCPU Template 则是另一条故障链：VMM 同样完成 restore/resume，但 Shim 到 VMM vsock mux 的 `CONNECT 1024` 握手立即读到 EOF；它尚未创建 agent ttrpc client，更未调用 `set_guest_date_time`。坏 2 vCPU 则已完成 mux 握手并记录 `agent is ready`，随后在 agent `set_guest_date_time` ttrpc 上超时。两者不能合并统计为同一根因。

现阶段优先级判断更新为：

1. Template 构建/pause/publish 与首次 restore 的跨组件时序；
2. vCPU virtual timer 保存/恢复和首次注入，但必须用成功 control 校验；
3. memory volume 中未归档的 guest RAM 与 ITS tables；
4. envd/shim/vsock 通信状态，尤其是 3 vCPU 短帧；
5. 静态 cmdline、GIC/ITS 寄存器和 CPU 数本身，目前证据不支持其为充分条件。

## 8. 社区 v0.5.1 全栈重新部署与复测

### 8.1 社区组件边界

本轮使用社区 release `v0.5.1`、commit `a164417f497234a0d787cb328b0ae96480b1569b` 重新构建并独立部署了 11 个组件：

| 类型 | 社区构建并部署的组件 |
|---|---|
| 宿主二进制 | `cubemaster`、`cubemastercli`、`cubelet`、`cubecli`、`network-agent`、`cubevsmapdump`、`cube-api`、`containerd-shim-cube-rs`、`cube-runtime` |
| 服务镜像 | `cube-lifecycle-manager`、`cube-proxy` |
| 静态链接模块 | 社区仓库 `hypervisor/*` 编译进 `containerd-shim-cube-rs`；cubecow 编译进 `cubelet` |

这里不存在单独运行的外部 Cloud Hypervisor 二进制。snapshot metadata 中的 `1.0.3` 是快照格式版本，不是外部 VMM 版本。原始来源记录保留不变以维持结果目录 SHA256 清单；边界修正记录单独保存为 [component-provenance-reviewed.json](remote-results/community-stack-vcpu-matrix-20260723-161000/evidence/component-provenance-reviewed.json)。完整二进制/镜像哈希见 [component-provenance.json](remote-results/community-stack-vcpu-matrix-20260723-161000/evidence/component-provenance.json)。

以下运行资产未从该 CubeSandbox commit 重建，仍属于外部或预置依赖：guest kernel `6.6.119-49.6`、guest rootfs、envd `0.5.24`、host kernel、MySQL、Redis、CoreDNS 和 openresty。因而“社区版全栈”在本报告中严格指 CubeSandbox 仓库拥有的宿主服务、runtime/shim、VMM 模块和服务镜像，不代表 guest/host 内核及基础镜像全部重建。

### 8.2 新模板测试矩阵

六个测试项都重新创建了 Template，没有复用 baseline snapshot。A 组是变更测试协议前已经完成的逐次隔离清理；B 组采用最新要求：每组连续创建 20 次，只在该 CPU 组完成后统一清理。

| 协议 | CPU | 新 Template | 成功 | 失败 | 主要失败签名 |
|---|---:|---|---:|---:|---|
| A：逐次隔离 | 2 | `tpl-52c8fddf838e4c10b19f3061` | 3/20 | 17/20 | 9 次 guest time ttrpc timeout、2 次 reseed timeout、6 次 HTTP 408 |
| A：逐次隔离 | 3 | `tpl-8401824f925c4f95ac21df43` | 20/20 | 0/20 | 无 |
| A：逐次隔离 | 4 | `tpl-9d0725461c4e4e31b5be5112` | 20/20 | 0/20 | 无 |
| B：组末清理 | 2 | `tpl-e3d8337f3b544adb9a460f0e` | 2/20 | 18/20 | 18 次 guest time ttrpc timeout |
| B：组末清理 | 3 | `tpl-92e2ea49246c4948bc6bd3c2` | 20/20 | 0/20 | 无 |
| B：组末清理 | 4 | `tpl-376b2c61aa324143a7a84ccb` | 20/20 | 0/20 | 无 |

所有成功实例都通过 guest `nproc` 和 delete 校验。主矩阵共 6 个 case、每个 20 次，完整性字段为 `complete=true`。变更协议过程中被中断的补充尝试已移到 `matrix/supplemental-isolated-b`，不计入主汇总。

证据：[comparison-summary.json](remote-results/community-stack-vcpu-matrix-20260723-161000/comparison-summary.json)。

### 8.3 失败、服务状态与组末清理

A 组 2 vCPU 的原始 shim 日志中，按独立实例统计有 5 个实例出现 RCU stall、4 个出现 RCU kthread/timer starvation、4 个出现 `Possible timer handling issue`。B 组的 18 次失败统一收敛为 `reset guest time` ttrpc timeout，没有出现此前坏 3 vCPU Template 的 `Recv len invalid:0`。

B 组 2 vCPU 结束、清理前的状态为：API sandboxes `0`、containerd tasks `0`、shim `18`。统一清理后恢复为 `0/0/0`，API health 正常；3/4 vCPU 组也均在组末完成清理。由此可以区分两件事：

1. A 组每次尝试前都执行 `0/0/0` 隔离门禁，但 2 vCPU 仍失败 17 次，所以服务残留不是初始触发条件。
2. B 组证明失败路径没有可靠回收 shim；继续无清理地压测会积累污染，因此每组结束清理是必要的测试控制，同时资源回收本身需要单独修复。

### 8.4 社区 A/B Template 快照对比

新矩阵的结构化分析结果见 [snapshot-log-structural-comparison.json](remote-results/community-stack-vcpu-matrix-20260723-161000/snapshot-log-structural-comparison.json)。每个 CPU 的 A/B Template 归一化后，`template-request`、snapshot `config`、`metadata` 和 `catalog` 都相同；`template-info` 只剩兼容性检查时间不同。

2 vCPU A/B 的序列化 GICv3/ITS 状态再次逐值完全一致：`dist` 568 项、`rdist` 48 项、`icc` 18 项、8 个 `ITS_BASER` 以及全部 ITS 标量均无差异。两份 Template 的 timer 瞬时状态却相反：

| 2 vCPU Template | vCPU0 `CNTV_CTL` / `CVAL-VCT` | vCPU1 `CNTV_CTL` / `CVAL-VCT` | 结果 |
|---|---:|---:|---:|
| A | `1` / `-46633` | `1` / `-24624` | 3/20 |
| B | `5` / `+95205` | `5` / `+115334` | 2/20 |

这两份 Template 在负 deadline/CTL=1 和正 deadline/CTL=5 两种相反状态下都高失败。成功的 3 vCPU A Template 也存在 vCPU2 `CNTV_CTL=1`、deadline `-123471`；成功的 4 vCPU A/B Template 同样存在部分负 deadline。由此排除“单次保存的负 timer deadline 或 CTL=1 可以充分判定坏快照”。

3 vCPU A/B 只有一个 `rdist` 项不同，4 vCPU A/B 的序列化 GIC/ITS 完全一致，两组均为 `20/20 + 20/20`。device section 中的 queue guest address 和 vsock connection 差异在成功与失败 Template 中都会出现，仍未发现坏模板独有的静态形状。

六份 memory/rootfs volume 的 SHA256 均不同，这是独立新建 Template 的预期结果。2 GiB memory payload 未复制到本地，但远端路径、文件属性、已分配块数和完整 SHA256 已留证，六份远端 volume 也仍保留，可继续抽取 ITS tables 所在 guest RAM 页进行逐页比较。

### 8.5 当前远端状态与结果完整性

本轮结束后没有恢复 trace-v22，远端继续运行社区构建组件。六个 CubeSandbox systemd 服务均为 `active`，API 返回 `{"status":"ok","sandboxes":0}`，sandbox/shim/task 为 `0/0/0`，最终 live SHA256 与本轮构建产物一致。

六个新 Template 当前均保留为 `READY`，对应 memory/rootfs 路径存在，清单见 [templates-preserved.tsv](remote-results/community-stack-vcpu-matrix-20260723-161000/evidence/final/templates-preserved.tsv)。结果目录共 1032 个原始清单文件通过 `sha256sum -c SHA256SUMS` 校验，没有失败项。

完整结果目录：[community-stack-vcpu-matrix-20260723-161000](remote-results/community-stack-vcpu-matrix-20260723-161000)。

## 9. 后续优先级

| 优先级 | 状态 | 检查项 | 目的/下一步 |
|---|---|---|---|
| P0 | 下一项 | 交替使用纯社区 shim 与 v23 trace-off shim 随机化构建多份 2 vCPU Template，再统一切回同一纯社区 shim restore；每份 Template 5-10 次、每组末清理 | 同模板跨 shim 对照已经排除“恢复侧 v23 修复”。该 A/B 能直接区分 Template 构建时序/二进制布局效应与偶然 good Template |
| P0 | 阶段完成 | 对 2 vCPU 的 snapshot pause、timer state 保存、pause-drain `KVM_RUN`、正式首次 `KVM_RUN`、`kvm_entry` 和 IRQ 27 建立统一时间线，并以 3/4 vCPU 为 control | 成功 control 的共同顺序已经建立；提前 IRQ 27 不具有 2 vCPU 特异性。仍需对一份已证实 bad 的社区 Template 获取同类低扰动 trace |
| P0 | 待执行 | 对 host KVM/vtimer 调度和 guest kernel timer/RCU 路径增加低扰动 trace，同时记录 envd `set_guest_date_time` 到达/返回 | 社区宿主栈已全部替换仍复现，剩余边界集中在 host/guest 内核、envd 与首次 vCPU 调度交互 |
| P1 | 待执行 | 从六份保留的 memory volume 提取 ITS device/collection/interrupt translation table 页，与 `KVM_DEV_ARM_ITS_SAVE_TABLES/RESTORE_TABLES` 前后状态对比 | `state.json` 中 GIC/ITS 寄存器一致不代表 guest RAM 内 ITS tables 一致 |
| P1 | 待执行 | 修复/定位失败路径遗留 shim，并把组末 `0/0/0` 作为后续矩阵硬门禁 | B 组 2 vCPU 18 次失败遗留 18 个 shim，会放大后续测试污染 |
| P1 | 待执行 | 保留此前 3 vCPU `CONNECT 1024` 的 VMM vsock mux accept/close 与 guest listener trace | 该 EOF 故障没有在社区主矩阵复现，应与当前 2 vCPU guest-time timeout 分开分析 |
| P2 | 待执行 | 对 snapshot 构建阶段记录 agent/probe 空闲、VM pause、memory publish、state 发布的严格顺序 | 验证是否捕获未收敛的通信、timer 或内存状态 |

patched 和社区两轮均已归档每份 Template 的 `state.json`、`config.json`、`metadata.json` 和 `catalog.json`。社区轮还记录了 volume 完整哈希并保留远端 payload；下一步已经具备做 ITS table 页和 guest RAM 定点对比的条件。

## 10. P0 snapshot/首次 vCPU entry 统一时间线

### 10.1 组件与插桩边界

本轮从社区 v0.5.1 commit `a164417f497234a0d787cb328b0ae96480b1569b` 构建 trace-v23 shim。插桩覆盖 VMM snapshot pause、逐 vCPU KVM state 保存、restore stages、pause-drain run、正式首次 `KVM_RUN` 调用前后；宿主 stock kernel 同时使用现有 `kvm_timer_*`、`kvm_entry` 和 `vgic_update_irq_pending` tracepoint。v23 shim SHA256 为 `cf25ae1203ea7d14ae6f3594dd6a8e8d9174bad83af3ba0d7141f6312ae8dbc7`，其余社区服务与 runtime 未替换。

所有 VMM 标记都受 `/tmp/cube_arm64_first_entry_trace_enable` 门禁控制。内核 trace 使用独立 tracefs instance，不修改 global tracing；`kvm_entry` 在 256 次命中后自动 trace-off，避免高频 trace 持续扰动。源码相对社区 commit 的完整差异见 [timeline-v23-vs-community.patch](remote-results/arm64-vcpu-timeline-v23-20260723-194248/evidence/source/timeline-v23-vs-community.patch)。

最初一次未限流 smoke 产生 `22,025,387` 次 overrun，并使工作负载失败，属于无效样本，已从正式统计排除。限流后的 41 份正式 restore trace 均为 `kernel_trace_overrun=0`。另一次被 delete 阻塞中断的 CPU4 partial group 也不计入主结果，正式 CPU4 数据只取 `matrix-cpu4-rerun`。

### 10.2 新 Template 20 次矩阵

本轮每个 CPU case 都新建 Template，baseline 仅提供请求结构，没有复用其 snapshot；每组执行 20 次 create、guest `nproc`、delete，只在组末清理。

| CPU | 新 Template | restore create | guest `nproc` | delete | 完整生命周期 | 内核 trace |
|---:|---|---:|---:|---:|---:|---:|
| 2 | `tpl-8be0fd3a1ba04feaa4948a0e` | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| 3 | `tpl-9a0e143ed679478c868b2b16` | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |
| 4 | `tpl-9eac06abfc7a4c46a95537c6` | 20/20 | 20/20 | 7/20 | 7/20 | 1/20 |

CPU4 的 13 个 lifecycle failure 全部发生在 guest `nproc=4` 已成功之后：12 次 delete HTTP 408，1 次 CubeMaster `DeadlineExceeded`。所以 restore/guest 可用性仍是 `20/20`，不能把删除阶段问题计为 timer/restore 失败。组末最终清理均恢复为 shim/task `0/0`。

### 10.3 snapshot pause 与 timer 保存

| CPU | VM pause | vCPU state 保存完成 | snapshot 完成 | 保存的 `CNTV_CTL / (CVAL-CNT)` |
|---:|---:|---:|---:|---|
| 2 | 1.392 ms | 0.497 ms | 1.468 ms | CPU0 `5/-93091`，CPU1 `5/-117731` |
| 3 | 2.530 ms | 0.640 ms | 1.623 ms | CPU0-2 均为 `5`，delta `-156247/-178017/-197627` |
| 4 | 3.481 ms | 0.918 ms | 2.044 ms | CPU0-2 为 `5` 且负 delta；CPU3 为 `1/+137950` |

pause 和逐 vCPU state 保存耗时随 CPU 数量增长，没有出现 2 vCPU 独有的长尾。2/3 vCPU 的 timer deadline 全部已经过期但 Template 均为 `20/20`；4 vCPU 同时包含正、负 deadline 也为 guest `20/20`。这再次证明保存瞬间的 CTL/delta 方向不是坏快照的充分判据。

### 10.4 restore、timer IRQ 与真正 guest entry 的顺序

VMM 与 kernel 共同给出的实际顺序为：

1. restore 创建 vCPU thread 时保持 `paused=true`。
2. 每个 vCPU 先执行一次设置 `immediate_exit` 的 pause-drain `KVM_RUN`。
3. 该调用的内核路径对每个 vCPU 执行 IRQ 27 level 1、VGIC pending 和 timer state restore/save；此时尚未执行 `vm_resume_begin`，也没有 `kvm_entry`。
4. VMM 完成 restore 后正式 resume，并释放所有 vCPU。
5. 各 vCPU 进入正式首次 `KVM_RUN`；内核在真正 `kvm_entry` 前再次更新 IRQ 27，然后才进入 guest。

| CPU | 完整 VMM 时间线 | 内核时间线 | 全 vCPU 在 resume 前 IRQ 27 | resume 前 `kvm_entry` | pause-drain 到 resume 中位数 | resume 到正式 run 调用中位数 | run 调用释放偏差中位数 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 20/20 | 20/20 | 20/20 | 0/20 | 375.595 us | 17.600 us | 3.180 us |
| 3 | 20/20 | 20/20 | 20/20 | 0/20 | 382.905 us | 19.695 us | 4.015 us |
| 4 | 20/20 | 1/20 | 1/1 | 0/1 | 395.775 us | 19.015 us | 6.225 us |

正式 trace 共捕获到 66 个可关联的首次 `kvm_entry` vCPU 样本；66/66 都在正式 run 调用开始后、真正 entry 前再次观察到 IRQ 27，调用到 entry 的中位数约为 2/3/4 vCPU 的 `11.420/12.015/11.460 us`。trace-off 上限会漏掉部分 3/4 vCPU 后续 entry，因此只对实际捕获的样本下结论。

最关键的排除结论是：**pause-drain 阶段提前置 pending 的 IRQ 27 确实存在，但它同样覆盖 2、3、4 vCPU 成功 control 的每个 vCPU，且三组 pause/resume/release 时间处于同一量级。因此该顺序可能是竞态的必要背景，却不是 2 vCPU 失败的充分条件，也不能单独解释旧社区 Template 的高失败率。**

### 10.5 trace-off 与同 Template 跨 shim 对照

为判断“20/20 是否仅由日志/内核 trace 改变恢复时序”又增加了两组 2 vCPU 对照：

| Template 构建组件 | restore 组件 | VMM/内核 trace | Template | 结果 |
|---|---|---|---|---:|
| v23 | v23 | 开启 | `tpl-8be0fd3a1ba04feaa4948a0e` | 20/20 |
| v23 | v23 | 关闭 | `tpl-63c0898777b24ab99f6d398d` | 20/20 |
| v23 | 纯社区 shim | 关闭 | 同一 `tpl-63c0898777b24ab99f6d398d` | 20/20 |
| 纯社区 | 纯社区 shim | 关闭 | 先前 A/B 两份新 Template | 3/20、2/20 |

同一 v23-built Template 在恢复纯社区 shim 后仍为 `20/20`，直接否定了“必须由 v23 restore 侧代码才能成功”的解释。trace-off 也为 `20/20`，说明主动日志和 kernel trace 不是成功的必要条件。

当前更合理、但尚未被证明的解释是：v23 二进制布局或插桩在 Template 构建/pause/snapshot 阶段改变了时序，因而两次都生成了 good Template；另一种仍然成立的解释只是连续遇到两份 good Template。样本单位应是独立 Template，不应把每份 Template 的 20 次 restore 当成 40 个独立构建样本。

### 10.6 本项 P0 的判断与下一实验

本项 P0 已完成成功 control 的统一时间线，并排除两个假设：

- 不支持“v23 restore 侧修改修复了问题”；同一 Template 回到纯社区 shim 仍成功。
- 不支持“resume 前 IRQ 27 pending 是 2 vCPU 独有根因”；3/4 vCPU control 走相同路径。

本轮没有生成带完整时间线的 bad restore，因此不能比较 good/bad 在首次 entry 后何处分叉。下一项最高价值实验应随机交替构建多份 2 vCPU Template：A 组纯社区构建、B 组 v23 trace-off 构建，然后全部切回同一个纯社区 shim restore。若 B 组坏 Template 率显著下降，才能支持“Template 构建时序/布局效应”；若两组收敛，则本轮两份 v23-built good Template 更可能是抽样波动。对已知 bad 社区 Template 的下一轮 kernel trace 还应同步观察 guest timer/RCU 与 envd `set_guest_date_time`，捕获真正的分叉点。

完整结构化分析见 [timeline-analysis.json](remote-results/arm64-vcpu-timeline-v23-20260723-194248/timeline-analysis.json)，最终环境门禁见 [final-summary.tsv](remote-results/arm64-vcpu-timeline-v23-20260723-194248/evidence/final/final-summary.tsv)，完整结果目录为 [arm64-vcpu-timeline-v23-20260723-194248](remote-results/arm64-vcpu-timeline-v23-20260723-194248)。

### 10.7 最终远端状态

测试结束后已恢复纯社区 shim，live SHA256 为 `4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d`，与测试前社区备份逐字节相同；runtime SHA256 保持 `7630247b17a2092b58cfd8c33ff15c104986facca2981db5f4c1597e4125e072`。六个 CubeSandbox unit 均为 `active`，API sandbox/shim/task 为 `0/0/0`，trace instance 和两个 trace flag 均不存在，global `tracing_on` 保持原值 `1`。本轮 5 份新 Template 均保留为 `READY`。

## 11. patched 历史矩阵的清理状态

> 2026-07-24 交接更新：后续不再沿用本文任一历史 Template。v16 拆分结论、V25 计划、每组 20 次协议和最终恢复门禁见[交接与后续执行计划](CUBESANDBOX_ARM64_MULTIVCPU_HANDOFF_PLAN_20260724.md)。

以下仅描述第 5 节 patched 历史矩阵结束时的状态，不代表当前远端状态：

- shim 已恢复为 trace-v22：`c57d617f...a1675c37`。
- runtime 已恢复为实验前版本：`d1e2db00...962a7a9`。
- CubeSandbox 六个相关服务均为 `active`。
- API 为 `{"status":"ok","sandboxes":0}`。
- 沙箱/shim/task 为 `0/0/0`。
- systemd failed unit 为 `0`。
- 本轮 9 个临时 Template 均已删除，逐个查询返回 `ret_code=130404, template not found`。

证据：[post-restore components](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/post-restore-components.sha256)、[post-restore runtime state](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/post-restore-runtime-state.txt) 和 [template cleanup](remote-results/arm64-vcpu-patched-matrix-20260723-153137/results/template-cleanup-verified.tsv)。

远端结果已完整同步并按逐文件 SHA256 与本地副本比对一致：

- [trace-v22 结果目录](remote-results/arm64-vcpu-count-matrix-20260723-152244)
- [patched 对照结果目录](remote-results/arm64-vcpu-patched-matrix-20260723-153137)
- [社区全栈结果目录](remote-results/community-stack-vcpu-matrix-20260723-161000)
