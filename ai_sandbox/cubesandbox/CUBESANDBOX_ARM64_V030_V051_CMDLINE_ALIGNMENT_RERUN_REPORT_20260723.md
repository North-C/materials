# CubeSandbox ARM64 v0.3 / v0.5.1 内核参数对齐复测报告

日期：2026-07-23  
测试节点：`192.168.25.90`（`aarch64`）  
宿主机内核：`6.6.0-132.0.0.111.oe2403sp3.aarch64`

## 1. 结论

本轮从源码对比、修改、ARM64 编译、组件替换、模板重建、guest 参数核验、服务恢复后复测到环境还原全部重新执行。

结论分为三层：

1. **代码修改正确生效。** v0.5.1 ARM64 guest 中已不再注入 `earlyprintk=ttyS0`、`mitigations=off`、`highres=off`、`clocksource=kvm-clock`、`clocksource=tsc`、`tsc=reliable`；`console=ttyAMA0,115200` 和 `earlycon=pl011` 仍保留。
2. **初始 patched 高失败批次确实受到服务过载污染。** 当时虽然 systemd 单元均为 active，但现场已有 18 个沙箱、65 个 shim、18 个 task，多个 shim 长时间占用 100% 以上 CPU。因此该批次不作为正式 A/B 结论。
3. **参数对齐仍未修复问题。** 全量重启 CubeSandbox 控制面和计算面、连续确认 `0/0/0`、重新创建两个全新 patched 模板后：生命周期预检为 `0/5`，正式串行创建为 `4/20` 成功、`16/20` 失败；失败 guest 中分别记录到 18 次 RCU stall、18 次 RCU kthread starved 和 18 次 timer handling issue。

因此，本轮验证结果为：

> v0.3 内核参数对齐已正确落地，但只能改变部分失败表现，不能消除 ARM64 VM 恢复后的 timer/RCU/ttrpc 故障，不能判定为修复成功。

机器可读总汇总见 [comparison-summary.json](remote-results/cmdline-rerun-ab-20260723-103303/comparison-summary.json)。

## 2. 源码重新对比

### 2.1 固定比较点

| 对象 | 固定版本 |
|---|---|
| v0.3 ARM64 适配参考 | `a8710be646abdfb2f6b561861ef808d07266ee54` |
| v0.3 参考仓库当前固定点 | `28fe3900ba4c827e17618e49fbbe8eb568b3634f` |
| v0.5.1 baseline | tag `v0.5.1`，`a164417f497234a0d787cb328b0ae96480b1569b` |
| v0.5.1 patched worktree | 基于上述 v0.5.1，分支 `experiment/arm64-v03-cmdline-rerun-20260723` |

参考提交和原始补丁分别归档在：

- [v0.3-adaptation-commit.txt](remote-results/cmdline-rerun-ab-20260723-103303/source-comparison/v0.3-adaptation-commit.txt)
- [v0.3-cmdline-reference.patch](remote-results/cmdline-rerun-ab-20260723-103303/source-comparison/v0.3-cmdline-reference.patch)
- [本轮 v0.5.1 patch](remote-results/cmdline-rerun-ab-20260723-103303/source-comparison/v0.5.1-arm64-v03-cmdline-alignment.patch)

### 2.2 重新确认的参数差异

| 参数 | v0.3 ARM64 | v0.5.1 baseline ARM64 | 本轮 patched ARM64 |
|---|---:|---:|---:|
| `earlyprintk=ttyS0` | 不注入 | 注入 | 不注入 |
| `mitigations=off` | 不注入 | 注入 | 不注入 |
| `highres=off` | 不注入 | normal/TAP 注入 | 不注入 |
| `clocksource=kvm-clock` | 不注入 | normal/TAP 注入 | 不注入 |
| `clocksource=tsc` | 不注入 | non-TAP snapshot 注入 | 不注入 |
| `tsc=reliable` | 不注入 | non-TAP snapshot 注入 | 不注入 |

v0.5.1 中 `no_timer_check`、`noreplace-smp` 和 x86 console 已有架构条件，本轮没有重复修改。

### 2.3 实施内容

修改集中在三个文件：

- `CubeShim/shim/src/hypervisor/config.rs`
- `CubeShim/shim/src/sandbox/sb.rs`
- `CubeShim/shim/src/snapshot/mod.rs`

实现方式：

- 为 `earlyprintk=ttyS0`、`mitigations=off` 增加非 ARM64 条件。
- 新增 `add_sandbox_clock_cmdlines()`，统一 normal sandbox 的时钟参数。
- 新增 `add_snapshot_clock_cmdlines(tap)`，统一 TAP/non-TAP snapshot 参数。
- 调整既有测试期望，并新增 `clock_cmdlines_match_architecture`，在 ARM64 上断言六项参数均不存在，同时保持非 ARM64 行为不变。

补丁统计为 3 个文件、87 行新增、9 行删除；`git diff --check` 通过。

## 3. ARM64 编译与产物

使用 ARM64 builder `ghcr.io/tencentcloud/cubesandbox-builder:ubuntu2004-arm64`，baseline 和 patched 均从干净 v0.5.1 worktree 重新 release 编译。

| 产物 | SHA256 |
|---|---|
| baseline shim | `7385896cccfe2c7969c2373dd78d04ab59ea0b9c42c7e0a5de2618fbad9e4ae8` |
| baseline runtime | `c6c9d04496de9a3eb7dc43d2f10688e72f30a6f64743208f6562986d4627b049` |
| patched shim | `74f129a7407006f9d1d5384e6a9219daa1cd827e7ec0aa4d55029d8e9718b55c` |
| patched runtime | `9d279ed065c19b4f17179e51d4a3890e7eb0cafaa8c1e360ab4cae727f926a25` |

四个产物均验证为 AArch64 ELF，见 [artifacts.file.txt](remote-results/cmdline-rerun-ab-20260723-103303/build/artifacts.file.txt) 和 [artifacts.sha256](remote-results/cmdline-rerun-ab-20260723-103303/build/artifacts.sha256)。

新增 ARM64 单测通过：

```text
test hypervisor::config::tests::clock_cmdlines_match_architecture ... ok
test result: ok. 1 passed; 0 failed
```

完整输出见 [patched-arm64-unit-test.log](remote-results/cmdline-rerun-ab-20260723-103303/build/patched-arm64-unit-test.log)。

A/B 部署时两阶段共同使用 baseline runtime `c6c9d0...926a25`，patched 阶段只切换 shim；patched runtime 仅编译和校验，没有作为运行变量部署。

## 4. 参数生效验证

### 4.1 baseline 新模板

baseline 模板 `tpl-6a05df9aba3b0dcc345786d0` 为本轮新建，实际 guest cmdline 包含：

```text
earlyprintk=ttyS0 mitigations=off quiet highres=off clocksource=kvm-clock
```

原始记录见 [baseline/kernel-cmdline.jsonl](remote-results/cmdline-rerun-ab-20260723-103303/baseline/kernel-cmdline.jsonl)。

### 4.2 服务恢复后的 patched 全新模板

用户要求不沿用 baseline 模板后，正式结果只使用服务恢复后新建的模板：

| 用途 | 新模板 |
|---|---|
| 5 次生命周期预检 | `tpl-b351e2db738b2b6e94505969` |
| 正式串行 20 次 | `tpl-04e4dd0f14d59a6ff7a29521` |

正式模板实际 cmdline 为：

```text
root=/dev/pmem0 rootflags=dax,errors=remount-ro ro rootfstype=ext4
panic=1 printk.devkmsg=on console=ttyAMA0,115200 net.ifnames=0 audit=0
LANG=C raid=noautodetect agent.debug_console agent.debug_console_vport=1026
quiet earlycon=pl011,mmio,0x09000000
```

六个目标参数均为 false，ARM64 console/earlycon 均保留。结构化断言见：

- [预检模板 cmdline](remote-results/cmdline-rerun-ab-20260723-103303/patched/retest-clean-service-new-template/template/kernel-cmdline-verification.json)
- [正式模板 cmdline](remote-results/cmdline-rerun-ab-20260723-103303/patched/formal-clean-retest/template/kernel-cmdline-verification.json)

## 5. baseline 结果

### 5.1 创建压力测试

每个 case 前后都要求沙箱/shim/task 为 `0/0/0`，失败遗留 shim 由脚本记录并回收。

| case | 成功 | 失败 | 成功率 | 回收 shim |
|---|---:|---:|---:|---:|
| `c=1, n=20` | 1 | 19 | 5.0% | 21 |
| `c=10, n=200` | 12 | 188 | 6.0% | 191 |
| `c=20, n=300` | 21 | 279 | 7.0% | 282 |
| `c=50, n=500` | 28 | 472 | 5.6% | 472 |
| **合计** | **62** | **958** | **6.08%** | **966** |

完整聚合见 [baseline pressure aggregate](remote-results/cmdline-rerun-ab-20260723-103303/baseline/pressure/results/aggregate.json)。

`c=50` 清理后 Cubelet 前两次启动发生 workflow 依赖插件注册失败，systemd 第三次重试恢复；该过程没有从结果中删除，日志见 [cubelet restart journal](remote-results/cmdline-rerun-ab-20260723-103303/baseline/pressure/results/create-c50-n500-post.cubelet-restart-journal.txt)。

### 5.2 串行完整生命周期

100 次 `create -> guest /health -> delete`：

| 指标 | 结果 |
|---|---:|
| create | 6/100 |
| guest `/health` | 6/100 |
| delete | 6/100 |
| 完整生命周期 | 6/100 |
| 最终 API 沙箱 | 0 |

失败分布为 `reset guest time` 73 次、`reset reseed random` 18 次、API 408 3 次。汇总见 [baseline lifecycle summary](remote-results/cmdline-rerun-ab-20260723-103303/baseline/lifecycle/results/summary.json) 和 [signature-counts.json](remote-results/cmdline-rerun-ab-20260723-103303/baseline/logs/signature-counts.json)。

## 6. 服务异常判断与恢复

patched 初始压力批次中，systemd 和模板状态仍显示 active/READY，但现场为：

```text
sandboxes=18
shims=65
tasks=18
```

多个 shim 持续占用 100% 至 170% CPU；仅看 `/health` 或 systemd active 不足以认定服务可测试。现场见 [invalid-run-diagnostics](remote-results/cmdline-rerun-ab-20260723-103303/patched/pressure/invalid-run-diagnostics/invalid-state-summary.txt)。该批次被标记为无效，不进入正式 A/B。

恢复动作：

1. 停止测试进程，保留进程、接口、日志和资源现场。
2. 通过 API 删除可见沙箱。
3. 停止 Cubelet，按精确 PID 回收 Cube shim。
4. 按依赖顺序重启 network-agent、CubeMaster、Cubelet、Cube API、lifecycle-manager、proxy。
5. 在 `t0` 和约 30 秒后重复验证所有服务 active、API/compute 健康、沙箱/shim/task 为 `0/0/0`。
6. 在此稳定窗口之后新建 patched 模板。

两次预检证据见 [preflight](remote-results/cmdline-rerun-ab-20260723-103303/patched/retest-clean-service-new-template/preflight)。

## 7. 服务恢复后 patched 有效复测

### 7.1 全新模板生命周期预检

模板 `tpl-b351e2db738b2b6e94505969` 的 5 次结果：

| 指标 | 结果 |
|---|---:|
| create | 0/5 |
| guest `/health` | 0/5 |
| delete | 0/5 |
| 完整生命周期 | 0/5 |

失败为 `reset guest time` 3 次、`reset reseed random` 1 次、`create container` ttrpc timeout 1 次。见 [smoke summary](remote-results/cmdline-rerun-ab-20260723-103303/patched/retest-clean-service-new-template/smoke/results/summary.json) 和 [smoke signature counts](remote-results/cmdline-rerun-ab-20260723-103303/patched/retest-clean-service-new-template/smoke/signature-counts.json)。

### 7.2 第二次恢复后的正式串行对照

再次全量恢复服务、稳定 20 秒、确认 `0/0/0` 后，新建模板 `tpl-04e4dd0f14d59a6ff7a29521`，执行与 baseline 相同的 `c=1, n=20, warmup=3, create-only`：

| 版本 | 成功 | 失败 | 成功率 |
|---|---:|---:|---:|
| baseline | 1/20 | 19/20 | 5% |
| patched | 4/20 | 16/20 | 20% |

patched 样本成功率增加 15 个百分点，但样本仍有 80% 失败，不能视为修复；而且 18 个失败 VM（包含 2 个 warmup 失败）均出现：

- `rcu: INFO: rcu_preempt detected stalls`
- `rcu_preempt kthread starved`
- `timer handling issue`

结构化对比见 [create-c1-n20-comparison.json](remote-results/cmdline-rerun-ab-20260723-103303/patched/formal-clean-retest/create-c1-n20-comparison.json)，原始 Shim 签名见 [cube-shim-key-signatures.log](remote-results/cmdline-rerun-ab-20260723-103303/patched/formal-clean-retest/create-c1-n20/cube-shim-key-signatures.log)。

由于恢复后的 5 次生命周期已经 `0/5`，正式串行仍 `16/20` 失败且重新产生 timer/RCU 故障，本轮没有继续扩大 patched 高并发样本。继续运行只会再次把已确认的 guest 故障放大为控制面过载，不能改变“未修复”的判定。被中止的初始压力数据完整保留，但不与 baseline 做正式数值比较。

## 8. 结果解释

本轮可以排除两种错误解释：

- **不是参数未生效。** 两个服务恢复后新模板的实际 guest cmdline 均通过结构化断言。
- **不是仅由旧模板或未恢复服务造成。** 全量服务恢复、两次稳定窗口和两个新模板之后仍可立即复现。

服务过载会把主要错误从约 8 秒的 ttrpc timeout 放大为 30 秒 HTTP 408，因此初始异常失败数有环境放大因素；但干净环境下仍有 80% 至 100% 的恢复失败，且 timer/RCU 签名保留，说明产品问题本身仍存在。

下一步应继续聚焦 ARM64 snapshot restore 的虚拟定时器/GIC 状态恢复和 vCPU resume 顺序，而不是继续调整这六项 cmdline。建议以本轮正式模板路径为最小复现，围绕以下边界增加状态采集：

1. restore 后首次 vCPU entry 前后的 CNTVCT/CNTVOFF/CNTV_CTL 状态。
2. VGIC restore 与 vCPU resume 的先后顺序。
3. guest 首次 timer interrupt、RCU grace-period kthread 获得运行时间的时间线。
4. ttrpc server 恢复前后的 guest monotonic/boottime 跳变。

## 9. 其他组件与位置的候选优先级

本轮 A/B 共同使用 baseline runtime，patched 阶段只切换 Shim。CubeMaster、Cubelet、cubecow、guest kernel/agent、VMM 主恢复逻辑和宿主 KVM 均未作为独立变量替换。

因此，本轮只能回答“六个 cmdline 参数是否足以修复 v0.5”，不能回答“v0.5 其他组件是否与 v0.3 等价”。剩余候选按当前证据排序如下。

| 优先级 | 组件或边界 | 当前判断 |
|---|---|---|
| P0 | VMM/KVM restore 激活窗口中的 virtual timer、vGIC、vCPU 状态一致性与首次 `KVM_RUN` 时序 | 与 RCU/timer/CPU1 stall 最吻合；v16 readback/插桩曾在同内核、同 Template 上改变结果 |
| P1 | v0.5 Cubelet/cubecow Template memory 产物 | 外部空 memory volume、dirty-log 快路径、deactivate/publish 均不同于 v0.3；抽样读回正确，但 omitted page 和完整逻辑内存尚未全量验证 |
| P1 | Shim 中 cmdline 之外的 restore 输入 | v0.5 额外传入 `memory_vol_url`，并组合 fs/net/disk/pmem/vsock；本轮没有对齐这些输入 |
| P1 | 宿主固件、硬件、IRQ/调度和 NUMA 条件 | stock/custom 内核不能决定故障有无，但平台差异可能调制 first-entry 竞态概率 |
| P2 | guest-agent、ttrpc、CubeMaster/API/Cubelet 控制面 | `reset guest time` 等 timeout 多数发生在 guest timer/RCU 停止推进之后，更像下游表现；服务过载会继续放大为 HTTP 408 |
| P2 | PMU fallback、单纯缺少 flush、六个 cmdline 参数 | 均有代码差异或工程风险，但已有实验否定其为充分根因 |

P0 位置包括：

- [vCPU state](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/cpu.rs:419)
- [vGIC restore](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/vm.rs:2288)
- [VM restore](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/vm.rs:2736)

v0.3 与 v0.5 的这些低层文件基本相同。因此，更准确的表述是：v0.5 的上层输入、产物或宿主条件可能暴露了共有的 ARM64 多 vCPU 恢复时序缺口。

P1 Template 产物位置包括：

- [AppSnapshot](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go:84)
- [dirty-log memory write](/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/hypervisor/vmm/src/memory_manager.rs:3014)

已有 C1 仅验证 49 个写入区间中的 139 个抽样页。它没有扫描 bitmap 未选择的 page，也没有在 cubecow deactivate/publish 后比较完整 2 GiB 逻辑内容。

## 10. 宿主条件补充核查

2026-07-23 14:30-14:34，对 `.65` 和 `.90` 进行了 SSH 只读采集。没有重启服务，也没有修改 sysctl、IRQ、NUMA、存储或 CubeSandbox 配置。

完整派生记录见 [host-condition-review-20260723.md](remote-results/cmdline-rerun-ab-20260723-103303/host-condition-review-20260723.md)。

该采集晚于正式 A/B，只用于确认稳定配置差异，不能替代测试瞬间的连续 trace。

### 10.1 已确认一致项

| 项目 | `.65` | `.90` | 判断 |
|---|---|---|---|
| CPU 拓扑 | ARM64、384 CPU、2 socket、4 NUMA | 相同 | 不是 CPU 数量/拓扑差异 |
| stock kernel | `6.6.0-132...aarch64` | 相同 | 当前版本一致 |
| vmlinuz SHA256 | `7340ca8f...5107` | 相同 | 内核映像逐字节一致 |
| kernel config SHA256 | `71ce6717...f56` | 相同 | 构建配置一致 |
| kernel cmdline 主体 | 相同 | 相同 | 仅 root LV 名不同 |
| page size / host clocksource | 4096 / `arch_sys_counter` | 相同 | 一致 |
| CPU governor / tuned | `performance` / `throughput-performance` | 相同 | 一致 |
| irqbalance / NUMA balancing | active / `1` | 相同 | 一致 |
| KVM 参数 | `force_wfi_trap=N`、`halt_poll_ns=500000` 等 | 相同 | 常用参数一致 |
| 采集时负载 | load 约 1，CPU 约 100% idle | 相同量级 | 无持续 CPU 压力 |

这些结果将“当前 stock 内核二进制、常用 KVM 参数或 CPU governor 不同”降为低优先级。历史 custom irqbypass 内核仍可能调制概率，但 stock 内核上的既有复现已证明它不是必要条件。

### 10.2 可能关键的差异

| 差异 | `.65`，v0.3 对照 | `.90`，v0.5 问题侧 | 因果判断 |
|---|---|---|---|
| BIOS/平台固件 | Huawei `13.22.00.32` | OEM `10.79` | 可能影响 GIC、timer、PCIe/IRQ；尚无直接因果证据 |
| 物理内存 | 约 690 GiB | 约 2.2 TiB | 内存密度和 NUMA 页分配条件不同 |
| NUMA 内存分布 | 约 192/194/194/128 GiB | 四节点各约 575-581 GiB | `.65` 不对称，`.90` 基本对称 |
| overcommit / HugePages | `1` / 120000 x 2 MiB | `0` / 0 | 可能改变 mmap、页分配和 page cache 行为；不是已证实根因 |
| Swap | 0 | 4 GiB，未使用 | 当前不是压力来源 |
| Template 存储 | legacy storage，root ext4，74% used | cubecow，独立 NVMe XFS reflink，3% used | 直接参与 v0.5 memory/rootfs 对象生命周期 |
| 当前 boot 告警 | 84 条监控 Pod memcg OOM，1 条 hung-task 抑制 | 目标签名 0 | `.65` 更嘈杂但 v0.3 仍全过，削弱一般负载假设 |
| uptime | 约 8 天 | 约 17 小时 | `.90` 为近期重启后的环境 |

存储是最贴近产品链路的宿主差异。`.65` 的 `/data/cubelet` 实际位于 root ext4；`.90` 使用独立 `/dev/nvme3n1` XFS，并启用 `storage_backend=cubecow` 和 reflink。

这不仅影响性能，还改变 Template memory/rootfs 对象的创建、deactivate、reflink 和恢复契约。后续应在 publish 后执行完整逻辑内存 hash，并扫描 bitmap omitted pages。

### 10.3 `.90` 硬件风险边界

2026-07-22 16:10，`.90` 曾因 mlx5 高温告警和 GHES PCIe root-port fatal error 进入 kdump。[关键日志](remote-results/v0.5.1-official-shim-stock-kernel-retest-20260722-1536/postflight/host-crash/key-evidence.txt)已归档。

该 panic 与 guest RCU/timer stall 不是同一日志链，不能直接作为 CubeSandbox 根因。不过，它证明 `.90` 不是没有硬件风险的理想控制组。

当前 boot 的 `.90` dmesg 没有 RCU、lockup、OOM、KVM、GIC 或 timer 目标签名，且空闲内存充足。因此，持续宿主资源压力不能解释本轮高失败率。

更可靠的宿主验证应在同一 stock 内核下增加一台无 GHES 历史的同型号节点，并记录 BIOS/BMC/网卡固件、vCPU 线程 CPU/NUMA 落点、IRQ affinity 和首次 `KVM_RUN` 时间线。

## 11. 清理与还原

本轮创建的 4 个测试模板均已删除，DELETE 返回 204，随后 GET 均为 404，见 [template cleanup](remote-results/cmdline-rerun-ab-20260723-103303/restore/template-cleanup/get-status-latest.tsv)。

远端组件已恢复为实验前备份：

| 组件 | 恢复后版本 | SHA256 |
|---|---|---|
| shim | `v0.5.1-arm64-first-entry-trace-v22` | `c57d617f4fe017ac0ce068565d07dddfed0792ba0e124f9f1a913f90a1675c37` |
| runtime | `v0.5.1` | `d1e2db0097d258f12cfd5727f92b074ff4a5520cbee5ee05e59144c05962a7a9` |

最终状态：CubeSandbox 服务 active、API/compute 健康、沙箱/shim/task 为 `0/0/0`，宿主 `kubelet.service` 保持实验前的 inactive。

证据见 [restore summary](remote-results/cmdline-rerun-ab-20260723-103303/restore/components/summary.txt)。

## 12. 证据完整性

远端原始证据共 321 个文件参与 SHA256 清单，已同步到本地并全部通过 `sha256sum -c`：

- [证据目录](remote-results/cmdline-rerun-ab-20260723-103303)
- [SHA256SUMS](remote-results/cmdline-rerun-ab-20260723-103303/SHA256SUMS)
- [源码文件 SHA](remote-results/cmdline-rerun-ab-20260723-103303/source-comparison/source-files.sha256)
- [宿主条件补充核查](remote-results/cmdline-rerun-ab-20260723-103303/host-condition-review-20260723.md)
- [宿主补充核查 SHA256](remote-results/cmdline-rerun-ab-20260723-103303/host-condition-review-20260723.sha256)

宿主条件补充核查是在原始 321 文件清单生成后新增的派生记录，不属于原始 `SHA256SUMS` 覆盖范围。原始 A/B 证据未被改写。

patched 源码保留在 `source_code/CubeSandbox-v0.5.1-cmdline-rerun-20260723`，未提交；baseline 干净 worktree 保留在 `source_code/CubeSandbox-v0.5.1-baseline-rerun-20260723`。
