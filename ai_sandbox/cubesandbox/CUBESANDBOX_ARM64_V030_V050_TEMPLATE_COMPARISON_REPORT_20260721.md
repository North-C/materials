# CubeSandbox ARM64 v0.3.0 适配版与 v0.5.0 问题侧 Template 测试对比

> 测试日期：2026-07-21  
> v0.3.0 测试节点：`root@192.168.25.65`  
> 问题侧证据节点：`root@192.168.25.90`  
> 结论状态：本轮未在 v0.3.0 ARM64 适配版复现同类故障

## 1. 结论摘要

v0.3.0 ARM64 适配版在完全同规格的 2 vCPU/2000 MiB 对照中，四档 `create-only` 共完成 1020/1020，错误为 0。问题侧同档位为 979/1020，错误 41。

两侧汇总可直接核对：

- [v0.3.0 2C2G L87-L89](remote-results/v0.3.0-arm64-template-compare-20260721-2145/exact-2c2000m/template-create-perf/aggregate.json#L87-L89)
- [问题侧 L87-L89](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/aggregate.json#L87-L89)

v0.3.0 2C2G 又完成 100/100 次“创建、guest HTTP 200、删除”门禁，最终 Sandbox 为空。[门禁汇总 L13-L24](remote-results/v0.3.0-arm64-template-compare-20260721-2145/exact-2c2000m/lifecycle-gate-100-guest-http/summary.json#L13-L24)

另外新建了 2 vCPU/4096 MiB Template。构建进入 `READY`，随后四档压力为 1020/1020，100 次 guest 门禁为 100/100。

证据：[构建状态 L7-L20](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-build/first-job-final.json#L7-L20)、[压力汇总 L87-L89](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-create-perf/aggregate.json#L87-L89)。

按本轮实例 ID 提取 Shim、VMM、Cubelet 日志后，未发现 RCU stall、timer handling issue、ttrpc timeout、guest time reset、VM shutdown timeout 或残留 Shim。

因此可以判断：在本节点、本适配版和当前样本量内，没有出现 v0.5.0 问题侧的多 vCPU Template 恢复故障。

该结果不能单独证明差异只来自 CubeSandbox 代码。两侧宿主内核后缀、Template 镜像和部署构建标识并不完全相同。

## 2. 版本口径

| 对象 | 本文口径 | 可验证信息 |
| --- | --- | --- |
| v0.3.0 侧 | 用户提供：基于 v0.3.0 的 ARM64 适配版 | 部署二进制未嵌入 Git commit；以[组件 SHA256](remote-results/v0.3.0-arm64-template-compare-20260721-2145/preflight/component-sha256.txt#L1-L4)锁定 |
| 问题侧 | 按用户口径称 v0.5.0 问题 | 保存的量化批次实际为 v0.5.1；起始部署为 v0.5.0，[环境记录 L38-L46](CUBESANDBOX_ARM64_MULTIVCPU_RESTORE_ISSUE_BRIEF_20260721.md#L38-L46) |
| 压力客户端 | 两侧使用同源官方 `cube-bench` 方法 | v0.3.0 侧二进制和脚本哈希见[工具 SHA256](remote-results/v0.3.0-arm64-template-compare-20260721-2145/tool-sha256.txt#L1-L2) |

v0.3.0 部署中的 Cubelet 只暴露 `(devel)` Go module 信息，没有 commit。[构建元数据 L1-L4](remote-results/v0.3.0-arm64-template-compare-20260721-2145/preflight/version-build-metadata.txt#L1-L4)

## 3. 测试环境

| 项目 | v0.3.0 ARM64 适配版 | 问题侧 |
| --- | --- | --- |
| 节点 | `192.168.25.65` | `192.168.25.90` |
| 架构 | aarch64 | aarch64 |
| CPU | Kunpeng 950 7592C，384 CPU，2 Socket | Kunpeng 950 7592C，384 CPU，2 Socket |
| NUMA | 4 节点 | 4 节点 |
| 宿主内核 | `6.6.0-132.0.0.111.oe2403sp3.aarch64` | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray` |
| 主对比 Template | 2C2000M | 2C2000M |
| 扩展 Template | 2C4096M，新建 | 问题已覆盖 2/4/8 GiB |

v0.3.0 的宿主信息见[uname](remote-results/v0.3.0-arm64-template-compare-20260721-2145/preflight/uname.txt#L1)和[lscpu L1-L30](remote-results/v0.3.0-arm64-template-compare-20260721-2145/preflight/lscpu.txt#L1-L30)。

问题侧信息见[环境表 L38-L49](CUBESANDBOX_ARM64_MULTIVCPU_RESTORE_ISSUE_BRIEF_20260721.md#L38-L49)。

测试前 API 中 Sandbox=0、CubeShim=0。首次预清理发现 13 个历史 task 目录；按原脚本重启 Cubelet 后归零，再开始计量。

证据：

- [清理前 L1-L3](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-create-perf/create-c1-n20-pre.before.txt#L1-L3)
- [清理后 L1-L3](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-create-perf/create-c1-n20-pre.after.txt#L1-L3)

为匹配问题侧隔离条件，计量期间临时停止宿主 Kubernetes kubelet。全部测试结束后已恢复。

## 4. 测试方法

### 4.1 Template 构建

使用现有 ARM64 browser 镜像新建 2C4096M Template。请求固定 CPU=2000m、内存=4096 MiB、TAP 网络和 `/json/version` 探针。[完整请求 L1-L17](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-build/request.json#L1-L17)

构建结果必须同时满足 job、Template、artifact 和唯一目标节点均为 `READY`。

### 4.2 同口径压力

两侧均执行以下四档，预热均为 3：

| 用例 | 并发 | 计量请求 |
| --- | ---: | ---: |
| `create-c1-n20` | 1 | 20 |
| `create-c10-n200` | 10 | 200 |
| `create-c20-n300` | 20 | 300 |
| `create-c50-n500` | 50 | 500 |

用例定义见[测试脚本 L235-L250](scripts/run_cubesandbox_official_create_perf_resilient.sh#L235-L250)。每档前后检查 Sandbox、Shim 和 task，并在必要时先恢复干净状态。[恢复逻辑 L69-L137](scripts/run_cubesandbox_official_create_perf_resilient.sh#L69-L137)

### 4.3 guest 可用性门禁

每次执行：创建 Sandbox、从 CubeMaster 取得 TAP IP、请求 guest `9000/json/version`、确认 HTTP 200、删除 Sandbox。

TAP IP 提取见[生命周期脚本 L50-L63](scripts/cube_template_create_rate.py#L50-L63)，guest 探针见[L178-L192](scripts/cube_template_create_rate.py#L178-L192)，删除与最终判定见[L205-L249](scripts/cube_template_create_rate.py#L205-L249)。

### 4.4 日志判定

以本轮 Sandbox ID 过滤 CubeShim、VMM、Cubelet 和 CubeAPI 原始日志，再扫描以下签名：

```text
rcu stall / rcu_preempt
timer handling issue
Receive packet timeout / ttrpc err
reset guest time failed
wait vm shutdown event failed
Kernel panic / panicked at
context deadline exceeded / failed to run container
```

## 5. Template 构建结果

主构建 job `fb9adc2a-...` 和 Template `tpl-b42e3187...` 均为 `READY`，进度 100%，目标节点 1/1 READY。[job 结果 L7-L20](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-build/first-job-final.json#L7-L20)

产物 ext4 大小为 2 GiB，并记录 SHA256 `c9a40c...afeb6`。[产物信息 L21-L31](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-build/first-job-final.json#L21-L31)

最终 Template 快照路径为 `2C4096M`，资源为 `cpu=2000m,mem=4096Mi`。[Template 详情](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-build/first-template-final.json#L1)

初次轮询把“Template 尚未可查询”的 404 当成失败。诊断请求因此重复创建了一个同规格 Template。重复项测试后已删除，[删除记录](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-build/duplicate-delete.txt#L1)；主 Template 保留供复现。

## 6. 同口径压力结果

以下主表使用完全一致的 2C2000M 规格：

| 用例 | v0.3.0 成功 | v0.3.0 错误/回收 Shim | v0.3.0 QPS | 问题侧成功 | 问题侧错误/回收 Shim | 问题侧 QPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| c1/n20 | 20/20 | 0/0 | 13.01 | 19/20 | 1/1 | 0.61 |
| c10/n200 | 200/200 | 0/0 | 92.00 | 190/200 | 10/10 | 5.87 |
| c20/n300 | 300/300 | 0/0 | 105.92 | 285/300 | 15/15 | 8.74 |
| c50/n500 | 500/500 | 0/0 | 65.90 | 485/500 | 15/15 | 15.30 |
| 合计 | 1020/1020 | 0/0 | - | 979/1020 | 41/41 | - |

各档原始数据：

- [v0.3.0 2C2G aggregate L6-L85](remote-results/v0.3.0-arm64-template-compare-20260721-2145/exact-2c2000m/template-create-perf/aggregate.json#L6-L85)
- [问题侧 aggregate L6-L85](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/aggregate.json#L6-L85)

QPS 只用于说明失败超时对批次时长的影响。问题侧失败请求包含约 30 秒等待，因此不能用本表直接评价成功路径的纯性能优劣。

2C4096M 扩展组同样为 1020/1020、错误 0。[扩展组汇总 L87-L89](remote-results/v0.3.0-arm64-template-compare-20260721-2145/template-create-perf/aggregate.json#L87-L89)

## 7. guest 可用性门禁

2C2000M 门禁为创建 100/100、guest 探针 100/100、删除 100/100、完整生命周期 100/100，最终 Sandbox 为空。[2C2G 门禁 L15-L24](remote-results/v0.3.0-arm64-template-compare-20260721-2145/exact-2c2000m/lifecycle-gate-100-guest-http/summary.json#L15-L24)

2C4096M 门禁结果相同。[2C4G 门禁 L15-L24](remote-results/v0.3.0-arm64-template-compare-20260721-2145/lifecycle-gate-100-guest-http/summary.json#L15-L24)

最初尝试 `commands.run` 时，创建和删除均成功，但命令连接失败。这不是 VM 恢复失败：当前 browser Template 未启动 envd。

端口扫描显示 guest 9000 从创建后立即开放，连续观察仍开放；49983、49999 始终关闭。[端口扫描 L3-L22](remote-results/v0.3.0-arm64-template-compare-20260721-2145/port-scan-diagnostic.txt#L3-L22)

因此正式门禁改用 Template 自身定义的 `/json/version` 探针。无效的 envd 尝试完整保留，但不计入 KVM/Template 恢复失败。

## 8. 错误日志对比

### 8.1 v0.3.0 适配版

2C2000M 批次关联 1132 个 Sandbox ID，提取 48680 行 Shim、152820 行 VMM、2264 行 Cubelet 和 2264 行 API 日志。

最终故障签名计数为：Shim 0、VMM 0、Cubelet 0。[2C2G 签名计数 L1-L8](remote-results/v0.3.0-arm64-template-compare-20260721-2145/exact-2c2000m/logs/signature-counts.txt#L1-L8)

2C4096M 及诊断批次关联 1160 个 Sandbox ID，Shim、VMM、Cubelet 和宿主内核签名也均为 0。[2C4G 签名计数 L1-L9](remote-results/v0.3.0-arm64-template-compare-20260721-2145/logs/signature-counts.txt#L1-L9)

两组结束状态均为 Sandbox=0、Shim=0、task=0。

证据：[2C2G 结束状态](remote-results/v0.3.0-arm64-template-compare-20260721-2145/exact-2c2000m/postflight/counts.txt#L1-L3)、[2C4G 结束状态](remote-results/v0.3.0-arm64-template-compare-20260721-2145/postflight/counts.txt#L1-L3)。

完整实例日志已保存为 `cube-shim-test-instances.log.gz`、`vmm-test-instances.log.gz` 和 `cubelet-test-instances.log.gz`，可按 ID 复查零签名结论。

### 8.2 问题侧

问题侧同四档合计错误 41；失败证据统计 40 条 Shim destroy ttrpc timeout 和 107 条 VMM task timeout。

证据：[失败摘要 L1-L4](remote-results/reinstall-v0.5.1-new-kernel-resumed-20260720/core-perf-template-create-20260720-1429/template-create-perf/failure-evidence/summary.txt#L1-L4)。

代表实例 `3563...` 在创建完成后依次出现 destroy ttrpc timeout、CPU1 RCU stall、VM shutdown timeout 和 RCU stack dump。[时间线与原始位置 L54-L64](CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md#L54-L64)

实例 `5991...` 出现同样顺序。[时间线与原始位置 L68-L78](CUBESANDBOX_ARM64_RCU_STALL_LOG_ANALYSIS_20260721.md#L68-L78)

这类错误链在 v0.3.0 两轮有效测试中均未出现。

## 9. 结果解释

结果支持以下判断：该故障不是 ARM64、KVM 或“2 vCPU Template 恢复”必然发生的现象。v0.3.0 适配版在相同 CPU 架构、相同 2C2G 规格和同等压力样本下稳定完成恢复与销毁，并额外通过 100 次 guest 门禁。

它也支持“后续代码路径、状态集合或恢复时序发生变化”这一方向。问题侧已有证据集中在 virtual timer、timer PPI、vGIC 状态和首次 `KVM_RUN` 附近。

但本轮不是单变量 A/B，不能据此锁定某个 commit。至少存在以下差异：

1. 两侧宿主内核后缀不同，问题侧包含 `sbench-irqbypass-xarray` 定制。
2. 两侧 Template 和 guest 镜像不是同一份快照。
3. v0.3.0 部署二进制没有可验证的源码 commit。
4. 问题侧量化批次实际运行 v0.5.1 诊断基线，而非未经修改的 v0.5.0 二进制。

更强的根因确认应在同一宿主、同一内核、同一镜像和同一 Template 产物上，只切换 v0.3.0 与 v0.5.x 的 CubeShim/VMM 二进制。

## 10. 环境恢复与留存

误创建的重复 Template 已删除，主测试 Template `tpl-b42e3187...` 保留且为 READY。[清理后 Template 列表 L1-L4](remote-results/v0.3.0-arm64-template-compare-20260721-2145/postflight/templates-after-duplicate-cleanup.txt#L1-L4)

远程机已恢复测试前服务状态：宿主 kubelet active；测试前停止的 MySQL、Redis、CoreDNS、CubeProxy、DNS 和 WebUI 均为 inactive；CubeMaster、Cubelet、CubeAPI 保持 active。

证据：[最终服务状态 L1-L11](remote-results/v0.3.0-arm64-template-compare-20260721-2145/postflight/restored-service-state-final.txt#L1-L11)。

最终 systemd failed unit 为 0。[systemd 状态 L1-L3](remote-results/v0.3.0-arm64-template-compare-20260721-2145/postflight/systemd-failed-after-restore-final.txt#L1-L3)

全部原始结果位于：

```text
remote-results/v0.3.0-arm64-template-compare-20260721-2145/
```

目录内 `SHA256SUMS` 覆盖所有留存文件，可用于完整性校验。

## 11. 最终判定

本轮结论为“未复现”，不是“理论上不可能复现”。

在完全同规格 2C2000M 下，v0.3.0 适配版完成 1020/1020 压力请求和 100/100 guest 生命周期门禁；在新建 2C4096M Template 下再次完成同等门禁。

与问题侧 41/1020 创建错误、RCU stall、ttrpc/VMM timeout 和残留 Shim 相比，差异显著。当前证据足以确认 v0.3.0 适配版在本测试范围内没有类似可靠性问题。
