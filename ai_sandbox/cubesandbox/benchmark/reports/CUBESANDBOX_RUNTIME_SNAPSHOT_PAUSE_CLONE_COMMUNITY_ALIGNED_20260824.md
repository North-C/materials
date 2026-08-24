# CubeSandbox Runtime Snapshot / Pause / Resume / Clone 社区对齐测试报告

| 字段 | 值 |
|---|---|
| 状态 | `verified` |
| 最后验证 | 2026-08-24 |
| 被测主机 | ARM64，OpenCloudOS 9.4，Linux `6.6.80-29-xarray-hz1000+` |
| Template | `tpl-8611260b90284868b61fe4d7`，2 vCPU / 2000 MiB |
| CubeAPI | custom `92b81197815823b23ec91906fbeaa7321d69da2c6136d9c757a5446684244bc1` |
| CubeSandbox 源码参考 | `72af66c349301ec8f750f21796a08e65dbb85e73` |
| host 优化构建 | `6646d3837d28edb8a3e65f9a93da06994f7e83f4` |
| 报告类型 | 社区脚本同口径复测；跨批次汇总，不是严格单变量 A/B |
| 证据清单 | [同名 evidence manifest](CUBESANDBOX_RUNTIME_SNAPSHOT_PAUSE_CLONE_COMMUNITY_ALIGNED_20260824.evidence-manifest.md) |

## 摘要

本报告直接使用 CubeSandbox 仓库中未修改的社区 lifecycle benchmark 脚本，复测 Runtime Snapshot、dirty sensitivity、从 Snapshot 创建、Rollback、Clone、Pause/Resume。命令参数、`time.monotonic()` 边界、warm-up、并发模型、nearest-rank 分位数和 aggregate 格式与社区报告保持一致。

社区历史值来源：[CubeSandbox 核心操作性能基准报告](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)。

主要结果：

- Runtime Snapshot c1/c5/c10 的整批平均时延为 88.0/101.8/121.2 ms。
- 从 Snapshot 创建 c1/c10/c20/c50 为 49.8/66.1/82.8/144.2 ms。
- dirty 从 6.5 MiB 增至 1133.6 MiB 时，Snapshot 平均时延从 82.5 ms 增至 447.4 ms；脚本中的 warm restore-create 维持在约 47–49 ms。
- Rollback c1/c5/c10 为 56.0/79.7/111.8 ms。c10 首次 warm-up 失败，独立复测成功；两个 attempt 均保留。
- Clone n1/c1 为 189.4 ms；n100/c10/c20/c50 为 720.5/492.8/396.2 ms。
- Pause c1/c5/c10 为 514.2/590.8/572.9 ms；Resume 为 14.5/18.7/24.2 ms。
- 每个成功 case 后均验证 Sandbox、Snapshot、shim、task、VMM、TAP 和 failed units 回到基线；没有通过提高门禁或 kill 内核线程掩盖恢复成本。

这些数字可以与社区表做同口径的描述性比较，但不能把差值归因到 MMDS-prime、opt235、HZ=1000、NUMA、Page Cache 或 CubeAPI 中的任一变量。

## 1. 测试环境

### 1.1 Host 与固定配置

| 项目 | 配置 |
|---|---|
| 架构 / OS | aarch64 / OpenCloudOS 9.4 |
| Kernel | `6.6.80-29-xarray-hz1000+`，`CONFIG_HZ=1000` |
| NUMA | `kernel.numa_balancing=0` |
| THP | `madvise` |
| HugePages | `HugePages_Total=0` |
| 存储 | XFS，`reflink=1`，`ftype=1` |
| Cubelet/CubeMaster | `numactl -N 0,1 --localalloc`，CPU affinity 0–191 |
| quota | 768000m / 3474612Mi，`mvm_limit=0` |

关键组件 SHA-256：

| 组件 | SHA-256 |
|---|---|
| Cubelet | `2cd30b08a3caaa8a5a0524475c6d438e80d547c4bc09b39b434f561b577ff605` |
| cubecli | `77d27a70ec519a86160af1d94a965b6897c5e4149d64ce96b7827daefd977fc2` |
| CubeShim | `43ba0150e4a7a89d2255e1810a92a1a50b150bf25154cf78be9b27d39fc9e28c` |
| cube-runtime | `a783633798501ec27ac95646ddaae7b555e7f860896904b0dd855cb61cbdebd8` |
| CubeMaster | `4901f854d6417d5059bbb3148da9ddc64af00d9721207c0c66ecb2696394c50c` |
| CubeAPI | `92b81197815823b23ec91906fbeaa7321d69da2c6136d9c757a5446684244bc1` |

### 1.2 Template

| 项目 | 值 |
|---|---|
| Template ID | `tpl-8611260b90284868b61fe4d7` |
| 状态 | READY |
| CPU / Memory | 2000m / 2000Mi |
| Fingerprint | `9be9677cbb8f9d0425e3b5a711bf25b82c420f0b19613dc9e9767b2d9e2dee20` |
| Image digest | `sha256:50830f12f7c7792b4c3744edc85c5c3723abb968321491cd7f643a8dba5811fc` |

## 2. 测试方法和统计口径

直接执行以下社区原脚本：

| 测试 | 脚本 SHA-256 |
|---|---|
| Snapshot concurrency | `b896937eabe210cfddfb63501f471b4e48c873b7149d20da886a1f502f152253` |
| Dirty sensitivity | `301b5276fe351956f8ed5ee1416d864ccbd7a45fa4e2a48f63c2908d8ffea72a` |
| 从 Snapshot 创建 | `332d5cd147dd654ac141d7598028c93756997b1c72ef2deaee80229c28f5d513` |
| Rollback | `0f1d7720bc12192355943f30917e893f73d4e015a0007dcb2288f8490f765229` |
| Clone | `eda015c383c95bae92fe7608aa2f4824c4583cdc571062cf3f8577544ab9e67f` |
| Pause/Resume | `2cba48bf409d26812cbea88a29d9987931a838f5bf6804f5da25652688134593` |

每轮时序：

```text
preparation -> t0 -> 社区脚本被测操作/futures -> t1 -> cleanup -> 资源收敛 -> 冷却门禁
```

- 社区 `wall` 是一轮整批完成时间；`wall/N` 是吞吐摊销，不是单请求 latency。
- nearest-rank：`ceil(N*p/100)-1`。2、3、5 轮的 P95 均等于 max。
- 社区脚本只输出 aggregate，不保留逐轮 wall 数组；本报告不伪造缺失 raw。
- 外层 harness 不进入社区 timer，只记录命令、host samples、日志窗口、对象 ID、物理清理、身份和冷却。
- case 前后要求 CubeAPI disk/runtime SHA 固定，并连续 5 个两秒样本满足：threads≤8000、load1≤5、blocked=0、Dirty≤16384 KiB、Writeback=0。

## 3. Runtime Snapshot concurrency

| c | rounds | 本轮 Avg | 社区 Avg | 差异 | 本轮 Min | 本轮 P95/Max | 本轮 wall/N |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 88.0 | 49.8 | +76.7% | 79.3 | 100.4 | 88.0 |
| 5 | 5 | 101.8 | 71.0 | +43.4% | 96.9 | 107.9 | 20.4 |
| 10 | 5 | 121.2 | 127.2 | -4.7% | 117.4 | 125.5 | 12.1 |

单位均为 ms。当前 fresh source 首次 Snapshot 的 Cubelet 请求类型为 SoftDirty，但 VMM 日志显示 tracker 尚未 arm，实际先走 PagemapAnon，再为下一周期执行 `clear_refs(4)`。因此本表不能称为稳态 SoftDirty delta 性能。

## 4. Dirty sensitivity

| 预写 MiB | 本轮 actual MiB | 社区 actual MiB | 本轮 Snapshot Avg | 社区 Snapshot Avg | 差异 | 本轮 Restore Avg | 社区 Restore Avg |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 6.5 | 7.1 | 82.5 | 45.7 | +80.5% | 48.7 | 64.8 |
| 10 | 38.2 | 38.9 | 111.5 | 75.7 | +47.3% | 49.2 | 60.7 |
| 50 | 119.7 | 120.7 | 135.3 | 107.7 | +25.6% | 47.0 | 64.4 |
| 100 | 192.1 | 195.0 | 166.8 | 138.6 | +20.3% | 48.8 | 66.5 |
| 200 | 293.8 | 296.7 | 196.5 | 174.2 | +12.8% | 47.3 | 63.7 |
| 500 | 600.1 | 602.5 | 284.6 | 289.4 | -1.7% | 47.7 | 64.0 |
| 800 | 905.7 | 908.4 | 371.4 | 392.8 | -5.4% | 47.5 | 60.9 |
| 1024 | 1133.6 | 1136.4 | 447.4 | 486.9 | -8.1% | 47.7 | 68.4 |

本轮 actual dirty 与社区值相近。Snapshot 时延随写入量增长；小 dirty 档比社区历史慢，大 dirty 档接近或略快。Restore 列来自脚本主动丢弃第一次 restore 后的 warm 样本，不能解释为一般冷恢复时延，也不能据此证明 Page Cache 是因果。

## 5. 从 Snapshot 创建

| c | rounds | 本轮 Avg | 社区 Avg | 差异 | 本轮 Min | 本轮 P95/Max | 本轮 wall/N |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 49.8 | 63.9 | -22.1% | 48.9 | 51.1 | 49.8 |
| 10 | 3 | 66.1 | 89.9 | -26.5% | 65.3 | 66.6 | 6.6 |
| 20 | 3 | 82.8 | 118.9 | -30.4% | 80.5 | 85.8 | 4.1 |
| 50 | 3 | 144.2 | 180.3 | -20.0% | 119.2 | 161.1 | 2.9 |

单位 ms。脚本在正式计时前执行一次 warm restore，因此表格反映共享 Snapshot 的热/已访问场景。

## 6. Rollback

| c | rounds | 本轮 Avg | 社区 Avg | 差异 | 本轮 Min | 本轮 P95/Max | 本轮 wall/N |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 56.0 | 81.6 | -31.4% | 53.0 | 60.1 | 56.0 |
| 5 | 5 | 79.7 | 189.6 | -58.0% | 76.4 | 83.7 | 15.9 |
| 10 | 5 | 111.8 | 266.1 | -58.0% | 106.2 | 117.4 | 11.2 |

Rollback c10 首次 attempt 在 warm-up 第三个 checkpoint 返回 `130400: sandbox ... is not running`。社区脚本没有覆盖该异常阶段的 cleanup，留下 10 Sandbox 与 3 Snapshot；外层按 failure-state 精确 ID 各执行一次 DELETE，全部返回 204。独立复测 c10 成功，上表使用复测值，但首次失败仍计入测试历史，不能只展示成功 attempt。

## 7. Clone

| n/c | rounds | 本轮 Avg | 社区 Avg | 差异 | 本轮 Min | 本轮 P95/Max | wall/N |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1/1 | 5 | 189.4 | 219.6 | -13.8% | 187.3 | 193.9 | 189.4 |
| 100/10 | 2 | 720.5 | 870.4 | -17.2% | 718.5 | 722.5 | 7.2 |
| 100/20 | 2 | 492.8 | 638.6 | -22.8% | 489.2 | 496.5 | 4.9 |
| 100/50 | 2 | 396.2 | 540.9 | -26.8% | 395.8 | 396.6 | 4.0 |

Clone timer 覆盖 SDK `src.clone()` 的整体返回；当前 SDK 的临时 Snapshot cleanup 语义可能与社区报告期 SDK 不同。`wall/N` 只表示批次吞吐摊销。

## 8. Pause / Resume

| c | Pause 本轮/社区 Avg | 差异 | Pause P95/Max | Resume 本轮/社区 Avg | 差异 | Resume P95/Max |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 514.2 / 558.4 | -7.9% | 550.5 | 14.5 / 41.8 | -65.3% | 14.8 |
| 5 | 590.8 / 656.9 | -10.1% | 630.2 | 18.7 / 28.2 | -33.7% | 19.2 |
| 10 | 572.9 / 682.1 | -16.0% | 597.3 | 24.2 / 35.7 | -32.2% | 25.0 |

单位 ms。本机实际部署走 legacy Full pausevm：VMM 记录 `snapshot_type: Full`、`memory_vol_url: None`，Pause 后保留 shim/TAP，Resume 在同一生命周期中恢复。它不是当前 HEAD 的 PauseCow/catalog + 新 backend 路径。

## 9. 资源归还与冷却成本

每个成功 case 后验证：

```text
Sandbox=0, Runtime Snapshot=0, shim=0, task=0,
VMM=0, TAP-in-use=0, failed units=0
```

社区 Snapshot 删除会留下空 metadata 目录；外层只对日志窗口捕获的精确 `snap-*` ID 检查 children=0 后执行 `rmdir`。没有递归删除或清理非本批对象。

高规模 case 会让总 threads 短期升到约 9k–13k，随后出现批量回落。Clone n100 c10/c20/c50 分别需要约 92/85/80 个两秒冷却样本；Rollback c10 复测需要 91 个样本。采样中 `kvm-irqfd-cleanup` 名称计数为 0，这与旧 boot 中约 10k 个同名 kworker 不同；线程具体类型和变化原因尚未确认。

一次从 Snapshot 创建 c1 虽请求和 cleanup 成功，但 600 秒末 threads 仍为 10703，wrapper 按硬门禁返回 cooldown timeout；后续新授权批次重新建立 before gate 后才继续。报告保留该失败，不提高阈值。

## 10. 社区对照的解释边界

已验证事实：

- 脚本、参数、timer、aggregate 字段与社区报告一致。
- 本轮表格来自成功的社区原脚本 stdout；失败和 gate-only attempts 另行保存。
- 本轮使用的 Template、组件 hash、操作系统和清理状态有证据。

不能据此证明：

- 差值由 opt235、MMDS-prime、CubeAPI、HZ=1000、NUMA 或 Page Cache 中某一个变量造成。
- warm restore 数据等同于冷恢复。
- `wall/N` 等同于单请求时延。
- 2/3/5 个 round 的 P95 能稳定表示尾延迟分布。

社区历史表缺逐轮 raw 和报告期 runtime/SDK 完整身份；本轮也是跨多个 92b 批次汇总。两者只适合做描述性同口径比较，不是 fresh paired control/candidate A/B。

## 11. 结论

1. Snapshot 并发从 c1 到 c10 的整批 wall 增长有限，但 c1/c5 比社区历史慢；c10 基本相当。
2. Snapshot 写入量与时延保持明显正相关；约 600 MiB 后，本轮和社区时延接近。
3. 从 Snapshot 创建、Rollback、Clone、Pause/Resume 的本轮 aggregate 均低于社区历史表，但缺严格单变量对照，不能宣称由某项优化带来。
4. Restore-create 在社区脚本的 warm 场景中稳定，但冷页、Page Cache 和首次访问成本仍是未知项。
5. cleanup 后线程恢复成本是连续压测的实际调度约束，必须保留 8000 门禁和自然冷却，不应只报告 API 时延。
6. Rollback c10 暴露一次 preparation 失败；复测成功不消除该可靠性问题，后续应单独追踪 `130400 sandbox not running` 的触发条件。

## 12. 证据与复现

机器可读结果见同目录 CSV。详细证据未复制进 Materials，保存在本机受控目录并由各自 `SHA256SUMS` 校验：

- `spc90-community-20260822T091058Z-31b38a2d`：92b 核心 Snapshot/Pause/Clone。
- `spc90-community-92b-full-20260824T125416Z-18811bfd`：Snapshot/dirty/create/Rollback 与首次失败。
- `spc90-rollback-c10-retest-20260824T134119Z-c68c3d7b`：Rollback c10 独立复测。

完整 provenance、文件路径、报告与证据 SHA-256 见 [evidence manifest](CUBESANDBOX_RUNTIME_SNAPSHOT_PAUSE_CLONE_COMMUNITY_ALIGNED_20260824.evidence-manifest.md)。
