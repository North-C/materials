# CubeSandbox ARM64 多 vCPU Template 恢复故障综合复盘与根因再判断

> 结论版本：2026-07-22
>
> 证据截止：2026-07-22 16:18 +08:00
>
> 覆盖范围：v0.3/v0.5 对照、历史 v1-v21、实验 A/B/C、stock 宿主内核复测、guest RCU 日志、宿主 KVM trace、源码调用链、`.65`/`.90` 远端环境
>
> 本文是独立的综合判断。既有报告和原始结果保持不变；如既有报告中的机制表述与本文冲突，以本文对证据边界的重新审查为准。

## 1. 执行结论

### 1.1 当前总体判断

当前证据最支持以下因果链：

```text
ARM64 多 vCPU Template restore
  -> 恢复 CPU/system register、virtual timer 与 vGIC 状态
  -> restored vCPU 线程启动后立即 resume
  -> CPU1 在首次或最初若干次 KVM_RUN 边界没有消费本应可投递的中断
  -> CPU1 反复 WFI/WFE 退出，timer softirq 不再推进
  -> guest CPU1 RCU stall，CPU0 等待跨 CPU 同步
  -> guest agent/reset/reseed/delete 失去响应
  -> API HTTP 408、ttrpc/shutdown timeout、残留高 CPU Shim
```

其中：

- **直接故障点为高置信度**：CPU1 的中断投递或消费在 restore 后首次 KVM 运行边界失效。
- **根因机制类别为中高置信度**：这是 ARM64 多 vCPU 恢复中 timer、vGIC、vCPU 状态跨组件不一致或激活竞态，而不是普通业务 API、网络或清理逻辑故障。
- **精确责任组件尚未确认**：现有证据不能区分“VMM 恢复了瞬态或不一致的状态组合”与“宿主 KVM 在 vGIC/timer load、put 或首次 entry 中没有正确激活该组合”。
- **实验 A/B 已否定命令行差异是决定性根因**。
- **实验 C 已否定缺少 `sync_all()` 是充分根因**，但没有完成对 dirty bitmap 遗漏页的全量排除。
- **`.90` 切回 stock 宿主内核后，v16 曾通过 `100/100 + 1020/1020`，但这不是 stock 内核的单变量证明**。
- **同一 stock 内核、同一 v16 Template 只替换为社区 v0.5.1 Shim 后，结果降为 `96/100 + 998/1020`，并复现 RCU/timer/ttrpc 链**。
- **社区 v0.5.1 自己构建的新 Template 也在串行中得到 `99/100`，排除了“仅为 v16 构建产物与社区恢复侧不兼容”**。
- **irqpass 定制内核不再是首要候选**；v16 的 KVM timer readback/插桩产生观察效应，VMM/KVM restore 激活窗口重新成为首要方向。

因此，当前最准确的根因表述是：

> **CubeSandbox 当前 ARM64 多 vCPU Template 恢复故障点仍位于 VMM 恢复状态与宿主 KVM 首次 vCPU entry 的边界。社区版在 stock 内核上复现，而 v16 readback/插桩版未复现，说明该边界对恢复后的 KVM GET 或额外时序扰动高度敏感。现有证据仍不足以归到某个具体代码行。**

### 1.2 社区 v0.5.1 复测对旧结论的修正

同一 stock 内核、同一 Template、同一 Runtime 和服务栈下，只把 Shim 从 v16 换回社区 v0.5.1，即从全通过变为串行 4 次、并发 22 次失败。

```text
v16:              serial 100/100, concurrent 1020/1020, signatures 0
official v0.5.1:  serial  96/100, concurrent  998/1020, RCU/timer/ttrpc reproduced
```

完整证据见[社区 v0.5.1 Shim/VMM 替换复测](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md)。

本轮没有出现字面 `reset guest time failed`，但出现 10 组 RCU stall/starved、4 条 timer handling issue、34 条 receive timeout 和 30 条 shutdown timeout。因此，该字符串不能作为故障是否消失的唯一判据。

### 1.3 不能再写成最终根因的说法

| 说法 | 当前判断 |
| --- | --- |
| ARM64 启动参数中残留 x86 参数导致故障 | 实验 A/B 直接反证，不是决定性根因 |
| cubecow memory volume 没有 flush，restore 读到旧数据 | 实验 C 反证为“不充分”；仍有 bitmap 完整性边界，但不是简单 flush 问题 |
| `CNTVCT_EL0`/counter offset 单点错误 | v1-v7 等多轮修复仍复现，已显著降级 |
| `CNTV_CTL/CVAL` 固定写入顺序就是根因 | v9、v17、v19-v21 不支持，简单顺序或延时模型已否定 |
| 软件 LR 已经进入硬件 ICH LR，因此一定是 EL2/KVM 硬件投递 bug | 现有 kprobe 只能证明软件路径和可运行判定，不能直接证明进入 guest 前的硬件寄存器最终状态 |
| trace 证明 vCPU 没有发生宿主 CPU 迁移 | 原始时间线在 pause/immediate-exit 到恢复 entry 之间出现迁移，该排除项应撤回 |
| 并发是故障必要条件 | 实验 B 的串行生命周期也失败；并发或负载最多是概率调制因素 |
| v0.5 的 ARM64 KVM restore 主体代码回归 | v0.3/v0.5 主恢复代码相同，且跨环境对照有混杂，证据不足 |
| stock 宿主内核已经消除故障 | 该结论来自 v16 单批结果；社区 Shim 在同一 stock 内核上同型复现 |
| 没有 `reset guest time failed` 就表示问题消失 | 社区 Shim 本轮该字符串为 0，但 RCU/timer/ttrpc 与 HTTP 408 明确复现 |

## 2. 问题现象重新整理

### 2.1 必要条件与非必要条件

目前观测到的核心条件是 **ARM64、多 vCPU、从 Template/Snapshot 恢复**：

- 1 vCPU 对照稳定，2 vCPU 开始出现间歇故障。
- 2 GiB、4 GiB、8 GiB 均出现过问题，内存容量不是决定因素。
- 关闭 PMU、固定 NUMA、去除 TAP/network-agent、停 Kubernetes、换探针端口均不能消除问题。
- 全新 Template 仍可能失败，Template 年龄不是必要条件。
- 实验 B 在每格 100 次串行完整生命周期中复现，说明高并发不是必要条件。
- 实验 C 的不同压力档失败率没有随并发单调增加，说明“并发越高必然越坏”也不成立。

既有排除实验详见[完整实验报告第 18 节](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md:1276)。

### 2.2 用户可见现象

失败并不只有一种 API 表面：

1. Sandbox 创建请求等待约 30 秒后返回 HTTP 408。
2. 部分流程先表现为 restore/create 已返回，随后 guest `/health`、reset/reseed 或 delete 超时。
3. CubeShim/VMM 出现 ttrpc receive timeout、等待 shutdown event 超时。
4. 失败实例可能留下高 CPU Shim，需要测试工具回收。

实验 B 进一步说明：本批次中失败首先落在 create/API 408；只要 create 成功，后续 guest `/health` 和 delete 均成功。因而 delete/ttrpc 错误不是独立根因，而是同一 guest 卡死在不同超时窗口中的下游表现。

### 2.3 guest 内部现象

代表性失败中：

- CPU1 报 RCU stall，落后多个 grace period。
- CPU1 的 timer softirq 计数停止推进，并出现 `Possible timer handling issue`。
- CPU0 在 `smp_call_function_many`、freezer 等跨 CPU 等待路径中阻塞。
- `detected by 0` 表示 CPU0 检测到 CPU1 长时间没有 quiescent state，不表示 CPU0 是故障源。

完整字段和调用栈解释见[RCU Stall 日志分析](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md:84)。

### 2.4 现象层结论

RCU、freezer、ttrpc、HTTP 408 和残留 Shim 是同一故障链的不同下游层次。最早可重复识别的技术异常不是清理失败，而是 **CPU1 恢复后没有正常推进中断驱动的 guest 时间与调度活动**。

## 3. 从系统层次重新看问题

这个问题实际跨越两条不同链路，必须分别验证。

### 3.1 Template 产物链路

```text
Cubelet AppSnapshot
  -> 创建空的 cubecow memory volume
  -> 请求 SnapshotType::Full
  -> Template VM 从启动时启用 dirty_log
  -> MemoryManager::send 先命中 dirty_log 快路径
  -> KVM dirty bitmap OR VMM bitmap
  -> 只把 bitmap 标出的 range 写入外部 memory volume
  -> Cubelet 停止临时 Sandbox、deactivate 并发布 Template
```

这里存在一个容易误判的语义差异：Cubelet 请求 `Full`，不等于 VMM 实际执行 `SnapshotType::Full` 分支。

- Cubelet 明确说明新 Template 没有可 overlay 的 base memory blob，所以请求 Full：[appsnapshot.go](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:283)。
- `CreateMemoryVolume` 创建的是空对象，和 clone 既有 memory 的 `CommitTemplateMemory` 不同：[cubecow_volume_manager.go](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/storage/cubecow_volume_manager.go:196)。
- Template VM 启动时将 memory dirty log 打开：[snapshot/mod.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeShim/shim/src/snapshot/mod.rs:256) 和 [sb.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/CubeShim/shim/src/sandbox/sb.rs:727)。
- `MemoryManager::send()` 在匹配 `snapshot_type` 前先执行 dirty-log 分支并 `return`：[memory_manager.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/memory_manager.rs:3030)。真正的 Full 分支在同文件的 3109 行之后。

这形成一个需要单独验证的不变量：

> 对一个空的外部 memory volume，dirty bitmap 必须覆盖暂停时所有非零且 restore 必需的 guest memory 页；没有被写入的稀疏区必须确实等价于全零页。

KVM dirty logging 与 VMM bitmap 的并集是为了满足这个不变量。相关初始化和 KVM slot 逻辑见 [memory_manager.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/memory_manager.rs:2317) 与 [kvm/mod.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/hypervisor/src/kvm/mod.rs:620)。但实验 C 只检查了 bitmap 已选中的区间，没有检查被遗漏区间是否含非零数据。

### 3.2 Restore 与首次运行链路

```text
加载 snapshot/外部 memory volume
  -> DeviceManager restore
  -> CpuManager restore
  -> ARM64 vGIC restore + enable interrupt
  -> device restore
  -> start_restored_vcpus
  -> VM 状态设为 Paused
  -> 同一个 VmRestore 请求内立即 vm.resume()
  -> 各 vCPU 首次 KVM_RUN
```

源码顺序是明确的：

- `Vm::restore()` 先恢复 CPU，随后 ARM64 vGIC，再启动 restored vCPU：[vm.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/vm.rs:2762)。
- `vm.restore(snapshot)` 返回后紧接 `vm.resume()`，两者之间没有额外的所有 vCPU first-entry ready 门禁：[lib.rs](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/lib.rs:725)。

完整调用链见[Pause/Resume/Restore 分析](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ANALYSIS_20260721.md:726)。

### 3.3 两条链路不能混为一个假设

Template 产物可能错误，restore 激活也可能错误。实验 C 只削弱了第一条链路中的“写入可见性”子假设；guest/KVM trace 则把实际挂死位置定位在第二条链路。二者可以独立存在，不能因为 restore trace 指向 timer/vGIC 就宣称 memory artifact 已全量正确，也不能因为产物有潜在风险就忽略已观察到的首个运行边界异常。

## 4. 证据与实验过程总览

### 4.1 环境和证据完整性

主要节点：

| 节点 | 当前/实验内核 | 作用 |
| --- | --- | --- |
| `192.168.25.90` | 历史：`6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-8394b32f`；当前：stock `6.6.0-132.0.0.111.oe2403sp3.aarch64` | v0.5 问题复现、v1-v21、A/B/C、stock 内核复测 |
| `192.168.25.65` | `6.6.0-132.0.0.111.oe2403sp3.aarch64` | 历史 v0.3 稳定对照 |

实验 B/C 归档包含 215 个 checksum 条目；本次已执行 `sha256sum --quiet -c SHA256SUMS`，全部通过。归档入口为 [EXPERIMENT_B_C_SUMMARY.md](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/EXPERIMENT_B_C_SUMMARY.md:1)，校验清单为 [SHA256SUMS](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/SHA256SUMS:1)。

必须保留的环境混杂是：v0.3 稳定结果和 v0.5 问题结果并非同一宿主、同一内核和同一完整软件栈。该对照证明“ARM64/Kunpeng/2 vCPU 天生不稳定”不成立，但不能单独证明“v0.5 用户态代码回归”。

### 4.2 v0.3 与 v0.5 问题基线

| 组别 | 创建压力 | guest 完整生命周期 | 解释 |
| --- | ---: | ---: | --- |
| v0.3 ARM64，2C/2000MiB，`.65` | 1020/1020 | 100/100 | 稳定，但跨宿主/内核 |
| v0.3 ARM64，2C/4096MiB，`.65` | 1020/1020 | 100/100 | 内存扩展仍稳定 |
| v0.5.1 问题基线，2C/2000MiB，`.90` | 979/1020 | 未作为该批门禁 | 41 次失败 |
| v0.5.1 同环境复测，`.90` | 980/1020 | 未作为该批门禁 | 40 次失败，显示自然波动 |
| v0.5.1 stock + v16，`.90` | 1020/1020 | 100/100 | 全新 Template，目标故障签名为 0 |
| v0.5.1 stock + 社区 Shim，同一 v16 Template | 998/1020 | 96/100 | 10 组 RCU stall，4 条 timer issue |
| v0.5.1 stock + 社区 Shim，社区新 Template | c1 20/20；c10 197/200 | 99/100 | c20/c50 因宿主硬件 panic 停止 |

原始对照和口径见[v0.3/v0.5 Template 比较报告](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_V030_V050_TEMPLATE_COMPARISON_REPORT_20260721.md:115)。社区 Shim 的同机复测见[替换复测报告](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md)。

源码比较还显示，v0.3 与 v0.5 的 ARM64 KVM/vCPU/vGIC 主 restore 代码基本相同，差异更多位于上层启动参数、Template 产物与环境：[源码差异分析](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_V030_V050_TEMPLATE_SOURCE_DIFF_ANALYSIS_20260722.md:569)。

### 4.3 v1-v21 实验重新归类

这些版本更适合用于否定具体机制，不适合用单次 `98/100`、`99/100` 证明修复。

| 实验类别 | 代表版本与结果 | 可得结论 |
| --- | --- | --- |
| counter/CNTVCT 修正 | v1 98/100、v2 98/100、v3 99/100、v6 98/100 | PR #8343 风格修正、catch-up 和 VM offset 均不充分 |
| per-vCPU one-reg 策略 | v4 4/5 | 扩大 timer one-reg 写入没有消除故障 |
| PMU 与通用配置 | v8 98/100 | PMU 不是主要根因 |
| 重写 timer 值/顺序 | v9 1/5、v17 1/5 | 强行改 CTL/CVAL 或 CTL-last 反而可能恶化，简单寄存器顺序模型不成立 |
| vCPU pause/restore ACK | v10/v11 产生可重复坏 Template | 能改变窗口和样本，但没有形成修复 |
| 未修改上游重建 | v12 99/100 且同型 CPU1 RCU | builder/toolchain 不是根因，原始代码自身可复现 |
| 路径插桩 | v13/v14 未命中部署路径 | 无法用于判断假设真伪 |
| 观察效应 | v15 新 Template 100/100；v16 readback 使坏样本转好；加 ftrace 又转坏 | 故障窗口对时序扰动高度敏感，日志本身不是修复 |
| 延时、二次 restore、defer timer | v19-v21 多组仍失败且无单调剂量关系 | 固定延时和局部重排不是充分修复 |

详细版本、补丁身份和原始结果见[完整实验报告第 9 至 10 节](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md:394)。

该矩阵支持的是“恢复窗口具有竞争性和观察效应”，但不能据此直接断言竞态发生在某一行代码。v19-v21 只否定已测试的延时与重排，不否定所有可能的 VMM 协议修复。

## 5. 实验 A：ARM64 命令行保护

### 5.1 设计

实验 A 在 v0.5.1 中仅恢复 v0.3 的 ARM64 条件保护，使 x86 专用的 `clocksource=kvm-clock` 等参数不再写入 ARM64 guest cmdline；使用同一 `.90` 节点、同一 custom kernel、同一镜像和 2C/2000MiB 规格构建新 Template。

### 5.2 结果

- 创建压力：`982/1020`，38 次错误。
- 历史同环境两批：`979/1020` 和 `980/1020`。
- 同批复现 4 次 CPU1 同型 RCU stall。
- 完整 guest 生命周期：`97/100`。

原始摘要见[实验 A 总结](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/EXPERIMENT_SUMMARY.md:1)。

### 5.3 判断

命令行保护是合理的 ARM64 正确性修复，应该保留；但其失败量级与基线相同，且故障签名相同。它不是本问题的充分根因，也没有证据显示它显著改变失败概率。

## 6. 实验 B：构建侧与恢复侧交叉

### 6.1 实际设计边界

实验 B 不是完整的“v0.3 对 v0.5”2x2，而是：

- 构建侧：v0.5.1 原版 Template 与实验 A 命令行修正版 Template。
- 恢复侧：v0.5.1 原版 v12 重建二进制与实验 A 修正版二进制。
- 四格各执行 100 次串行“create、guest `/health`、delete”完整生命周期。
- 全程使用 `.90` 的同一个 custom kernel。

二进制身份：

| 恢复侧 | Shim SHA256 | Runtime SHA256 |
| --- | --- | --- |
| 原版 v12 | `10f2925...` | `d1e2db...` |
| 命令行修正版 | `070da9...` | `e28ad4...` |

### 6.2 结果

| 恢复侧 | 构建侧 | 生命周期成功 | RCU stall | ttrpc/shutdown timeout |
| --- | --- | ---: | ---: | ---: |
| 原版 | 原版 | 97/100 | 2 | 3/3 |
| 原版 | 命令行修正版 | 95/100 | 1 | 5/5 |
| 命令行修正版 | 原版 | 95/100 | 2 | 4/4 |
| 命令行修正版 | 命令行修正版 | 93/100 | 0 | 6/6 |

矩阵原始汇总见 [matrix-summary.json](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-b/matrix-summary.json:1)，归一化签名见 [matrix-summary-normalized.tsv](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-b/matrix-summary-normalized.tsv:1)。

### 6.3 能得出的结论

1. 四格都失败，故障不只跟随某个构建侧 Template，也不只跟随某个恢复侧二进制。
2. 没有出现“只有不兼容组合失败”的象限，因此未发现命令行差异造成的构建/恢复格式兼容问题。
3. 串行也出现失败，并发不是必要条件。
4. RCU dump 不是完备计数器。最后一格有超时但没有 RCU dump，不能把 `RCU=0` 解释成不同故障。

### 6.4 不能从 B 得出的结论

四格按固定顺序执行，没有随机交错；每个构建侧只有一个 Template，原版和修正版 Template 的创建时间、年龄与实例身份不同；恢复二进制还与执行时间段绑定。因此：

- 不能把 `97%` 对 `93%` 解释为修正版更差。
- 不能用 pooled `192/200` 对 `188/200` 量化构建侧或恢复侧效应。
- B 足以否定“命令行修正决定成败”的强假设，但不足以检测几个百分点的概率变化。

## 7. 实验 C：memory volume flush/readback

### 7.1 C0 发现实际分支

C0 只给 `SnapshotType::Full` 分支加入 flush/readback，但日志没有出现验证标记。原因不是补丁失效，而是请求虽然为 Full，`self.dirty_log=true` 让代码先进入 dirty-log 分支并直接返回。

这次实验修正了此前分析中的关键前提：**AppSnapshot 的 Full 是请求语义，实际产物算法是 dirty bitmap 写入语义。**

### 7.2 C1 设计和直接证明

C1 同时覆盖 dirty-log 和 Full 两条实际写入路径：

1. 完成 range 写入。
2. 调用 `sync_all()`。
3. drop 写句柄。
4. 以只读方式重新打开外部 memory volume。
5. 校验逻辑长度。
6. 对每个实际写入区间抽查首、中、尾最多 4 KiB，与暂停 guest memory 逐字节比较。

C1 Template `tpl-a2591c59834c4899ba75eaab` 的结果：

```text
expected_bytes=2097152000
observed_bytes=2097152000
written_ranges=49
samples=139
fnv64=0xbb9a8c7b6d0dffa2
```

日志见 [CubeVmm.log](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/template/c1/CubeVmm.log:135)，提取结果见 [sync-readback-verification.txt](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/template/c1/sync-readback-verification.txt:1)。

它直接证明：

- reopen 后对象长度是 2,097,152,000 字节。
- 49 个已写 range 的 139 个抽样页全部可见并与 guest memory 一致。
- 被抽查区域没有短读或 mismatch。

### 7.3 C1 恢复结果

串行完整生命周期：`100/100`，该批未出现 RCU、ttrpc 或 shutdown timeout。

随后对同一个 C1 Template 执行创建压力：

| 并发/请求数 | 成功 | HTTP 408 创建失败 | 回收 Shim |
| ---: | ---: | ---: | ---: |
| 1/20 | 20 | 0 | 0 |
| 10/200 | 197 | 3 | 4 |
| 20/300 | 293 | 7 | 7 |
| 50/500 | 494 | 6 | 6 |
| 合计 | 1004/1020 | 16 | 17 |

压力批出现 1 次同型 CPU1 RCU stall，CPU1 落后 7 个 grace period，timer softirq 停在 `1394/1394`，由 CPU0 检测；同时有 17 次 ttrpc/shutdown timeout。汇总见 [aggregate.json](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/validation/official-create-pressure/results/aggregate.json:5) 和 [signature-counts.txt](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/experiment-c/validation/official-create-pressure/signature-counts.txt:1)。

### 7.4 C 对 flush 假设的判断

`100/100` 与 `1004/1020` 不矛盾，前者只是没有命中低概率故障。C1 在显式 sync、关闭和重新打开后仍复现相同故障链，因此：

> **缺少 `sync_all()` 或普通 write visibility 不是当前故障的充分根因。**

不能反向宣称 flush 使失败从约 4% 降到 1.6%。C 没有同期、随机化、同 Template 状态的无 flush 控制组；Template 身份、构建时间和插桩时序都变化了。v15/v16 已证明观察行为本身能够改变窗口。

四个压力档失败率分别约为 `0%`、`1.5%`、`2.33%`、`1.2%`，没有单调并发剂量关系。此外，每档 create-only 测试会在档内累积已成功 Sandbox，所以名义并发度与活动 VM/资源占用并未完全分离。并发和负载可能放大触发概率，但现有数据不能给出单调模型。

### 7.5 C 没有关闭的产物假设

C1 的 FNV64 是 139 个抽样页的累计摘要，不是 2 GiB 逻辑镜像的全量 hash；更重要的是，它只遍历 **dirty bitmap 已经选中的 written ranges**。

C1 的 reopen/readback 还发生在 VMM snapshot 写入函数内部，早于 Cubelet 随后停止临时 Sandbox、deactivate memory object 并发布 Template。因而它证明了写句柄关闭后同一路径重新打开的可见性，但没有验证完整 deactivate/publish 生命周期之后的全量逻辑内容。

如果某个 restore 必需的非零页既没有进入 KVM dirty bitmap，也没有进入 VMM bitmap，那么：

- 该页不会被写入空 cubecow volume；
- 该页不会出现在 `written_ranges`；
- C1 也不会抽查它；
- 长度正确仍无法发现该页以 sparse zero 形式存在。

这并不表示已经发现 dirty bitmap false-negative。dirty logging 从 Template VM 创建期启用，理论上 guest 写页和 VMM 写页的并集应覆盖有效非零内存，因此该候选低于 timer/vGIC 首次 entry 假设。准确结论是：

> “缺少 flush”已明显降级；“空基卷上的 Full 请求实际由 dirty-only 算法实现，其 bitmap 是否完整”仍是一个尚未被 C 关闭的中低优先级产物假设。

## 8. 宿主 trace 的证明边界

### 8.1 已观察到的失败行为

对可重复坏 Template 的 500 ms 原始失败 trace：

| 指标 | vCPU0 | vCPU1 |
| --- | ---: | ---: |
| KVM exits | 1,259 | 约 120,954 |
| WFx exits | 52 | 约 120,220 |
| timer IRQ27 level=1 | 242 | 4 |

更深的 kprobe 中，CPU1 的 `kvm_vgic_vcpu_pending_irq` 和 `kvm_arch_vcpu_runnable` 反复返回 1，`vgic_v3_populate_lr` 路径被大量调用。v18 还读回 CPU1 的 `ICC_IGRPEN1=1`、`ICC_PMR=0xf0`、`PSTATE.I=0`。

这些证据共同支持：CPU1 已启动并进入 idle WFI；KVM 软件状态认为存在可投递中断且 vCPU runnable，但 guest 没有取得使 timer/softirq 向前推进的中断。

### 8.2 旧结论中需要收回的两处过度推断

第一，`kvm_vgic_vcpu_pending_irq=1` 证明软件 vGIC 的 ap_list 中有满足 pending、enabled、inactive 和优先级条件的中断，但探针没有返回 INTID，不能证明每次都是 IRQ27。

第二，调用 `vgic_v3_populate_lr` 表示 KVM 正在从软件 vGIC 状态填充软件 LR 数组。函数命中次数不能证明在紧邻 guest entry 时，EL2 的实际 `ICH_LR/ICH_HCR/ICH_VMCR` 已具有预期值。因此，旧报告中的“LR 已装入硬件，唯一只剩 ICH 硬件缺陷”超出了现有证据。

v18 的 ICC/PSTATE 读回也只排除了保存值中的静态 mask 异常，不能证明第一次实际 entry 的 live hardware state。

### 8.3 host CPU 迁移修正

旧报告根据恢复后稳定运行区间的 CPU 列写成“无 host CPU 迁移”。重新对齐原始 trace 后，original 失败样本的 CPU1 在线程 pause/immediate-exit 到恢复 entry 之间从 host CPU 76 迁移到 92。

但迁移也出现在 v16 加 ftrace 后的失败样本中，且单凭失败样本不能证明迁移必然触发故障。正确状态是：

- “无迁移”排除项无效，应撤回。
- host vCPU migration/load-put 是值得控制的触发候选。
- 它目前不是已证明根因，需 affinity A/B 和成功/失败对齐。

### 8.4 trace 能支持的最窄结论

当前 trace 最窄且可靠的落点是：

> **软件 KVM/vGIC 认为 CPU1 有可投递中断并持续 runnable，但在首次恢复运行后的实际 guest 执行中，这个状态没有产生被 guest 消费的 IRQ。**

该落点跨越了 VMM 最终输入、KVM vgic software state、per-host-CPU load/put 和 EL2 entry 四个边界。没有 first-entry live state，就不能把责任进一步压到其中某一层。

## 9. 根因候选重新排序

根因候选必须按层次排序，不能把“故障点”和“责任组件”放进同一置信度。

### 9.1 故障点和机制类别

| 层次 | 判断 | 置信度 | 依据 |
| --- | --- | --- | --- |
| 直接故障点 | CPU1 restore 后未消费可投递中断，形成 WFx 风暴和 timer/RCU stall | 高 | guest RCU、KVM exit、pending/runnable、v18 状态共同支持 |
| 机制类别 | timer、vGIC、vCPU 状态在首次 KVM_RUN 前后未形成一致、可激活组合 | 中高 | 多种 timer 单点修补无效，时序插桩有观察效应，故障集中在 first-entry |
| 下游后果 | ttrpc、shutdown、HTTP 408、残留 Shim | 高 | 时间顺序和 B/C 失败链一致 |

### 9.2 责任组件候选

| 排名 | 候选 | 支持证据 | 反证/缺口 | 当前评级 |
| ---: | --- | --- | --- | --- |
| 1 | VMM/KVM restore 激活窗口中的 timer/vGIC/vCPU 状态一致性或时序竞态 | 社区版在 stock 上复现；v16 readback/插桩在同内核、同 Template 上全过；first-entry 落点 | readback 到底改变 KVM 状态还是仅改变时序尚未分离；无 first-entry 最终状态 | 中高 |
| 2 | 空 memory volume 的 dirty-only Full 语义遗漏 restore 必需页 | v0.5 产物语义与 v0.3 不同；C 未扫描 omitted pages | 同一个 v16 Template 只换社区恢复侧即失败；社区新 Template 也失败，说明不是唯一解释 | 中低 |
| 3 | irqpass 定制宿主内核或其交互 | custom 内核下历史多批复现 | 社区 Shim 在 stock 内核同型复现，stock 本身不是充分修复 | 低到中，可能调制概率 |
| 4 | 单纯缺少 flush/write visibility | v0.5 外部对象缺少显式同步是工程风险 | C1 sync+reopen 后仍同型失败 | 低，非充分根因 |
| 5 | ARM64 cmdline 回退 | v0.3/v0.5 有明确差异 | A/B 同型失败 | 低，非充分根因 |
| 6 | CNTVCT、PMU、内存、网络、NUMA、builder 等单因素 | 各自曾有理论可能性 | 多轮直接对照仍失败 | 已排除为主要根因 |

`.90` 的 custom kernel 后缀来自 irqbypass 相关补丁，源码差异主要位于通用 irqbypass/eventfd 以及 x86/vfio/vhost 路径，不直接修改 `arch/arm64/kvm`。当时 dmesg 还显示 GICv4 support disabled，因此不能简单推导 direct vtimer bypass 正在工作。

社区 Shim 在 stock 内核上的复现将 irqpass 分支降级。它仍可能改变故障概率，但已不能解释“有无故障”。相关上游提交为 [Linux 8394b32faecd](https://github.com/torvalds/linux/commit/8394b32faecd9c63b3c436e78e62519e9548e530)。

### 9.3 为什么当前不能给出具体代码行根因

要把根因归到某一行，至少需要下面之一：

1. 同一 paused state 下，VMM 写给 KVM 的最终 timer/vGIC/vCPU 状态已经违反明确不变量。
2. VMM 输入相同且合法，但 stock 与 custom kernel 在 first-entry live state 或结果上稳定分叉。
3. 同一快照产物在全量逻辑内存比较中存在可重复遗漏，且修复遗漏后故障消失。

本轮完成了相同 stock 内核、相同 Template、不同 Shim 的强对照，证明 v16 的额外 readback/插桩会改变结果。但它同时改变了 KVM ioctl 序列和执行时序，仍不能区分状态副作用与纯观察效应。

因此，继续写“确定是某寄存器、某函数或某内核补丁”仍会混淆定位与证明。

## 10. 下一步决胜实验

### 10.1 已完成：同一 stock 内核、同一 Template 的 v16/社区 Shim 对照

2026-07-22 15:09-15:16 +08:00，`.90` 已切换到 stock kernel，并使用固定 v0.5 完整镜像 digest 新建 2C/2000MiB Template。

关键请求和结果在同一位置展开如下，完整证据见 [stock 内核复测报告](/home/lyq/Projects/Verification/cubesandbox/remote-results/v0.5.1-stock-host-kernel-template-retest-20260722-1508/TEST_SUMMARY.md:1)。

```text
host kernel        = 6.6.0-132.0.0.111.oe2403sp3.aarch64
image digest       = sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d
Template           = tpl-592352ea663648e486962db3, READY
serial lifecycle   = 100/100（create + guest HTTP 200 + delete）
concurrent create  = 1020/1020
RCU/timer/ttrpc    = 0/0/0
final resources    = sandboxes/shims/tasks 0/0/0
```

上述结果使用的是 v16，不能单独证明 stock 内核消除了故障。15:37 后保持 stock 内核、Template、Runtime 和测试工具不变，只把 Shim/VMM 换回社区 v0.5.1：

```text
v16 same Template       = serial 100/100, concurrent 1020/1020, signatures 0
official same Template  = serial  96/100, concurrent  998/1020
official fresh Template = serial  99/100, c1 20/20, c10 197/200
official signatures     = RCU stall 10, timer issue 4, receive timeout 34
```

证据见[社区版替换复测](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md)。该结果把 stock/custom 内核回转从 P0 降为概率调制实验，把 v16 readback 的副作用/时序分离升为 P0。

新的 P0 应从 v16 开始逐项剥离：先保留日志、移除 KVM GET readback；再保留 readback、关闭日志；最后将 readback 移到 vCPU 启动前后的不同位置。每个版本使用同一 Template 随机交错运行，避免固定顺序和 Template 年龄混杂。

### 10.2 P0：同一 paused state 的 true Full 与 dirty-on-empty 对照

不要继续只加 fsync。需要一次真正区分算法的实验：

1. pause guest 后只读取一次 KVM/VMM dirty bitmap，保存 bitmap，避免 `get_and_reset` 改变后续输入。
2. 从同一暂停内存和同一状态 metadata 生成两份产物。
3. 产物一严格走现有 dirty-on-empty 路径。
4. 产物二绕过 `self.dirty_log`，强制逐 range 执行真正 `SnapshotType::Full`。
5. deactivate 后重新打开两份对象，对整个逻辑 2 GiB 分块 hash；同时将 guest memory 全量 hash 作为基准。
6. 明确检查 dirty 产物的所有 omitted range 是否在 guest 中全零。
7. 随机交错恢复两种产物，执行 create、guest health、delete 全生命周期。

判定：只要发现一个“guest 非零但 dirty 产物为零”的 omitted page，产物假设成立；若全量一致且两种产物同型失败，该方向可大幅降级。

### 10.3 P1：低扰动 first-entry 状态采集

如果 v16 readback 剥离实验仍指向 KVM，或 true Full 已排除产物问题，应只采首个恢复 entry，而不是打开高频 ftrace：

```text
per-vCPU saved state
  -> VMM KVM_SET 后 readback
  -> host CPU 与 vgic load/put generation
  -> entry 前软件 used_lrs/vgic_lr[]
  -> entry 前实际 ICH_HCR/ICH_VMCR/ICH_LR
  -> timer line、MP state、PSTATE
  -> 首次 KVM exit reason 与实际 INTID/EOI
```

实现应使用单次 tracepoint、固定大小 per-CPU ring buffer 或故障触发后导出，避免每次 WFx 打日志。必须同时采成功和失败，并按同一 vCPU 的单调序号对齐。

### 10.4 P1：vCPU affinity/迁移 A/B

在不改 snapshot 内容的情况下，对每个 restored vCPU 从 load 到首次若干次 entry 固定独立 host CPU，再与允许调度迁移的控制组交错。该实验用于判断迁移/load-put 是否调制窗口，优先级低于同机内核 A/B，因为迁移本身尚未证明是必要条件。

### 10.5 统一验收口径

任何候选修复必须同时满足：

- 2 vCPU 普通新 Template 与历史可重复坏 Template。
- create 成功后必须完成 guest HTTP health 和 delete，不能只统计 API create 返回。
- 至少 100 次串行完整生命周期和 1020 次四档压力。
- 无 CPU1 RCU/timer stall、ttrpc/shutdown timeout、残留 Shim。
- 修复前后使用同一测试顺序或随机交错，并保留二进制、内核、Template、镜像 digest。
- 2 vCPU 通过后扩展到 4/8 vCPU、2/4/8 GiB，以及运行时 pause/resume/commit。

单批 `100/100` 只能说明该批未命中，不足以证明低概率故障消失。

## 11. 当前远端与本地状态

### 11.1 `.90` 当前状态

2026-07-22 16:18 +08:00 复核：

```text
kernel=6.6.0-132.0.0.111.oe2403sp3.aarch64
default_kernel=/boot/vmlinuz-6.6.0-132.0.0.111.oe2403sp3.aarch64
CubeSandbox services=active
shim_sha256=c3d9bd094a8fc9d86b4b06a684ee574f8f8e023479c1f4088b8597c2a6c03d46
runtime_sha256=d1e2db0097d258f12cfd5727f92b074ff4a5520cbee5ee05e59144c05962a7a9
sandboxes/shims/tasks=0/0/0
templates=tpl-592352ea663648e486962db3,tpl-c7cec6dc635547e3b2853d8c READY
```

当前 Shim 和 Runtime 均为社区 v0.5.1。当前状态见[替换复测最终状态](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/postflight/state-after-host-reboot.txt)。

16:10 宿主因 GHES fatal PCIe root-port hardware error 进入 kdump；重启后 CubeSandbox 服务自动恢复。vmcore dmesg 和内嵌关键行见[替换复测第 7 节](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md)。

### 11.2 `.65` 当前状态

2026-07-22 14:22 +08:00 只读复核：

```text
kernel=6.6.0-132.0.0.111.oe2403sp3.aarch64
cubelet=active
active containerd-shim-cube/cube-vmm=0
```

### 11.3 本地源码状态

本地保留原始 v0.5.1、实验 A 命令行分支和实验 C memory verify 分支。实验分支存在未提交的用户实验修改；本次分析只读取，没有清理、覆盖或提交这些工作树。

## 12. 最终判断

综合全部实验后，我的判断不是“线索变多所以无法判断”，而是问题已经分成了一个高置信度故障点和三个仍需决胜实验的责任分支：

```text
高置信度故障点
  CPU1 在 ARM64 multi-vCPU restore 后的首次 KVM 运行边界
  没有实际消费 KVM 软件层认为可投递的中断

责任分支 A（中高）
  VMM/KVM restore 激活窗口中的 timer/vGIC/vCPU 状态一致性或时序竞态

责任分支 B（中低）
  空 external memory volume 上的 dirty-only Full 语义遗漏了 restore 必需页

责任分支 C（低到中）
  irqpass 定制宿主内核、调度或其他环境因素调制故障概率
```

实验 A/B 已把命令行差异从主因中移除；实验 C 已把普通 flush/可见性问题从主因中移除。社区版在 stock 上同型复现，说明 stock 内核不是充分修复，也使 irqpass 不再是“有无故障”的首要解释。

v16 与社区版的强对照说明额外 KVM timer readback 或其时序扰动能关闭本批故障窗口，但还不能称为修复。`reset guest time failed` 本轮为 0，而 timer/RCU/ttrpc 链仍复现，说明该字符串只是故障落点之一。

最合理的推进顺序是：

1. 将 v16 的 KVM GET readback 与日志时序逐项剥离，使用同一 Template 随机交错，区分状态副作用和纯观察效应。
2. 完成同一 paused state 的 true Full/dirty 全量逻辑内存对照，关闭产物分支。
3. 只针对剩余分支采集 first-entry live ICH/timer/INTID 证据。
4. 宿主 PCIe/网卡高温和 GHES fatal error 排除前，不继续高压 c20/c50。

在这三步完成前，工程上可用 1 vCPU 作为规避，但不应把观察效应版本、额外 flush 或某个 `98/100` 版本作为修复发布。

## 13. 主要证据索引

> 2026-07-24 交接更新：v16 的 GET/log/delay 拆分已完成，V25 日志位置拆分已准备。后续执行口径、命令和决策树统一见[交接与后续执行计划](CUBESANDBOX_ARM64_MULTIVCPU_HANDOFF_PLAN_20260724.md)。

- [v0.5.1 stock 宿主内核 Template/Sandbox 复测](/home/lyq/Projects/Verification/cubesandbox/remote-results/v0.5.1-stock-host-kernel-template-retest-20260722-1508/TEST_SUMMARY.md:1)
- [社区 v0.5.1 Shim/VMM 替换复测](./remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/TEST_SUMMARY.md)
- [实验 B/C 结果摘要](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-b-c-arm64-20260722-1157/EXPERIMENT_B_C_SUMMARY.md:1)
- [实验 A 结果摘要](/home/lyq/Projects/Verification/cubesandbox/remote-results/experiment-a-arm64-v03-cmdline-guards-20260722-1110/EXPERIMENT_SUMMARY.md:1)
- [v0.3/v0.5 Template 源码差异与 A/B/C](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_V030_V050_TEMPLATE_SOURCE_DIFF_ANALYSIS_20260722.md:1)
- [v0.3/v0.5 同口径测试比较](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_V030_V050_TEMPLATE_COMPARISON_REPORT_20260721.md:1)
- [v1-v21 完整实验报告](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md:1)
- [Pause/Snapshot/Resume/Restore 调用链](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ANALYSIS_20260721.md:1)
- [RCU stall 与 KVM/timer 分析](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md:1)
- [Template quiescence/KVM 分析](/home/lyq/Projects/Verification/cubesandbox/CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_20260720.md:1)
