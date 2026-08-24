# PASS WITH CAVEATS：MMDS-prime 2U2G + opt235 三轮 c50n500 稳定性报告

目标：`root@192.168.25.90`<br>
测试日期：2026-08-21<br>
正式轮：R1/R2/R3，每轮 3 warmup、c=50、n=500、create-only、不重试<br>
正式样本：1500

## 1. 结论摘要

三轮全部成功：

- 1500/1500 formal 请求成功，0 error。
- pooled Avg 80.290 ms，P50 76.909 ms，P95 117.035 ms，P99 133.690 ms。
- pooled formal wall time 2.922 s，加权吞吐 513.321 sandbox/s。
- 三轮 Avg CV 1.489%，P50 CV 0.689%，吞吐 CV 1.060%，中心性能稳定。
- P95 CV 7.866%、P99 CV 5.045%，尾延迟存在可见轮间波动，主要由 R2 较高尾部贡献。
- 每轮 500/500，无 `no enough resource`、`no more resource`、filter reject、deadline/reset timeout。
- 每轮峰值均为 503 个 Sandbox/Shim/task/TAP，after 均回到 0。

当前组合在请求成功率和中心时延上表现稳定，但连续复测存在重要系统恢复成本：每轮结束后会短期累计约 10,000 个 `kvm-irqfd-cleanup` kworker。R2/R3 启动前分别等待约 314/339 秒才重新满足 `threads<=8000`；R3 后额外约 229 秒才回到该门禁。不能忽略这部分轮间冷却时间。

结论为 **PASS WITH CAVEATS**：功能和 formal 性能稳定性通过；尾延迟和 KVM irqfd cleanup 恢复延迟需要继续跟踪。

## 2. 当前测试身份

### 2.1 硬件与操作系统

| 项目 | 当前值 |
|---|---|
| 架构 | ARM64 / aarch64 |
| 服务器 | Huawei / Kunpeng 950 7592C |
| CPU | 384 logical CPU，2 socket，96 core/socket，2 thread/core |
| 频率 | 1.2–2.3 GHz，boost disabled |
| NUMA | 4 node；每 node 96 CPU |
| 内存 | 约 2.43 TB |
| OS | OpenCloudOS 9.4 |
| Kernel | `6.6.80-29-xarray-hz1000+` |
| Kernel build | `#1 SMP Fri Aug 21 11:02:15 CST 2026` |
| Boot ID | `d2169cfa021c43f28d80d3066a7e24de` |

Kernel/内存策略：

- `CONFIG_HZ_1000=y`，`CONFIG_HZ=1000`。
- `kernel.numa_balancing=0`。
- THP enabled/defrag 当前选择 `madvise`。
- `HugePages_Total=0`，`ShmemHugePages=0 kB`。
- `/data/cube-shm` 没有独立 mount。

### 2.2 存储

- `/data`、`/data/cubelet`、Template memory 均位于 `/dev/mapper/opencloudos-root`。
- filesystem：XFS。
- XFS：`reflink=1`、`ftype=1`、`crc=1`、`rmapbt=1`。
- 容量约 800 GiB，测试前可用约 723 GiB，inode 使用约 1%。
- Template memory 是 2,097,152,000-byte XFS regular file，不使用 tmpfs/huge。

### 2.3 服务绑定与资源配置

Cubelet/CubeMaster 启动脚本均使用：

```text
numactl -N 0,1 --localalloc
```

运行态：

| 服务 | CPU affinity | Mems allowed |
|---|---|---|
| Cubelet | 0–191 | 0–3 |
| CubeMaster | 0–191 | 0–3 |
| CubeAPI | 0–383 | 0–3 |

Cubelet raw quota：

- `mcpu_limit=768000`
- `mem_limit=3474612Mi`
- `mvm_limit=0`

测试前 quickcheck OK，failed units=0，节点 healthy/RUNNING；Sandbox/Shim/task/TAP-in-use 均为 0。

### 2.4 Template / guest 优化

| 项目 | 值 |
|---|---|
| Template ID | `tpl-8611260b90284868b61fe4d7` |
| Spec | 2000m / 2000Mi |
| Status | READY，1/1 replica READY |
| Image | community-aligned ARM64 envd MMDS-prime |
| Image digest | `sha256:50830f12f7c7792b4c3744edc85c5c3723abb968321491cd7f643a8dba5811fc` |
| Rootfs artifact | `rfs-9be9677cbb8f9d0425e3b5a7` |
| Rootfs SHA-256 | `53715711aa89977feb772ca102fddb87752caf1edc2fee93e6b00c4cde6c1535` |
| Fingerprint | `9be9677cbb8f9d0425e3b5a711bf25b82c420f0b19613dc9e9767b2d9e2dee20` |
| Probe | HTTP `/health`:49999，period 500 ms，timeout 30000 ms |
| Writable layer | 1G |

envd MMDS-prime：

- envd SHA-256：`3d4e431b2f5f168171b560de427b3c28efa30738c1f5ef016977917e7b8f92a1`
- startup script SHA-256：`265140ddb7f4b65c2e5fb54a52b9bb2432030c2c485fe61156f8fd3a2c2bee46`
- snapshot memory 中 `-prime-mmds-until-unix` 命中 1 次。

该优化在 Template 捕获期间保留 MMDS polling，并在保存的绝对 deadline 到期后停止后续 polling，减少恢复后已有 VM 的背景 MMDS 活动。

### 2.5 host opt235 四件套

构建 commit：`6646d3837d28edb8a3e65f9a93da06994f7e83f4`。

合入优化：

1. `509cda25`：startup probe 失败后更快重试。
2. `c87cbff7`：AppSnapshot restore 无 propagation mount fixup 时跳过无操作的 Guest CreateSandbox/CreateContainer RPC。
3. `62836e7a`：避免未使用的 Agent health connection。

| 组件 | SHA-256 |
|---|---|
| Cubelet | `2cd30b08a3caaa8a5a0524475c6d438e80d547c4bc09b39b434f561b577ff605` |
| cubecli | `77d27a70ec519a86160af1d94a965b6897c5e4149d64ce96b7827daefd977fc2` |
| CubeShim | `43ba0150e4a7a89d2255e1810a92a1a50b150bf25154cf78be9b27d39fc9e28c` |
| cube-runtime | `a783633798501ec27ac95646ddaae7b555e7f860896904b0dd855cb61cbdebd8` |

其他组件：

| 组件 | 身份 |
|---|---|
| CubeMaster | 社区 v0.5.1，`4901f854...` |
| cubemastercli | 社区 v0.5.1，`100f3ae8...` |
| network-agent | 社区 v0.5.1，`b6c6ba80...` |
| CubeAPI | 用户接受的 custom dev，`92b81197...` |

因此整体身份是基于 v0.5.1 的组合优化环境，不是纯社区 release。

## 3. 测试方法

每轮固定：

- `PROFILE_MODE=performance`
- `ENABLE_HEAVY_PROFILING=0`
- `ENABLE_SCHED_PROFILING=0`
- `CASE_CONCURRENCY=50`
- `CASE_REQUESTS=500`
- warmup=3
- create-only
- `RETRY_UNTIL_SUCCESS=0`
- 独立、唯一 OUT_DIR

每轮前 runner 强制：

- Template ID/CPU/memory/fingerprint/probe 一致。
- CubeMaster/Cubelet/CubeShim/CubeAPI 四哈希一致。
- MemAvailable 与 `/data` 空间门禁。
- 无 bpftrace。
- 连续 5 次满足：threads≤8000、load1≤5、procs_blocked=0、Dirty≤16384 KiB、Writeback=0。
- Sandbox/Shim/task/TAP 回到空 baseline。

三轮是计划内独立重复，不是失败重试；任一轮失败会终止后续测试。实际三轮均一次成功。

## 4. 三轮结果

| Round | Success | Avg | P50 | P90 | P95 | P99 | Max | Wall | Throughput |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R1 | 500/500 | 79.966 | 76.824 | 92.747 | 111.790 | 133.315 | 133.829 | 0.974 s | 513.238/s |
| R2 | 500/500 | 81.888 | 77.545 | 95.075 | 129.796 | 142.659 | 145.280 | 0.987 s | 506.784/s |
| R3 | 500/500 | 79.015 | 76.250 | 91.669 | 109.079 | 126.142 | 128.114 | 0.961 s | 520.115/s |

三轮 runner/performance sampler/watchers 全部 exit 0；每轮错误签名扫描均为 0。

## 5. 1500 样本 pooled 结果

| 指标 | Pooled |
|---|---:|
| Requests | 1500 |
| Successful / Errors | 1500 / 0 |
| Avg | 80.290 ms |
| Stddev | 14.346 ms |
| Min | 53.641 ms |
| P50 | 76.909 ms |
| P90 | 94.101 ms |
| P95 | 117.035 ms |
| P99 | 133.690 ms |
| Max | 145.280 ms |
| Sum formal wall | 2.922 s |
| Weighted throughput | 513.321/s |

pooled 分位数直接由 1500 个 formal `create_ms` 合并后按 nearest-rank 计算；不是三轮分位数的平均。

## 6. 轮间稳定性

下表的标准差和 CV 是三轮 round-level 指标的总体描述统计：

| 指标 | 三轮均值 | Std | CV | Min–Max |
|---|---:|---:|---:|---:|
| Avg | 80.290 ms | 1.195 | 1.489% | 79.015–81.888 |
| P50 | 76.873 ms | 0.530 | 0.689% | 76.250–77.545 |
| P90 | 93.164 ms | 1.421 | 1.526% | 91.669–95.075 |
| P95 | 116.888 ms | 9.194 | 7.866% | 109.079–129.796 |
| P99 | 134.039 ms | 6.762 | 5.045% | 126.142–142.659 |
| Max | 135.741 ms | 7.137 | 5.258% | 128.114–145.280 |
| Throughput | 513.379/s | 5.443 | 1.060% | 506.784–520.115 |
| Formal wall | 0.974 s | 0.010 | 1.060% | 0.961–0.987 |

判断：中心分布和吞吐稳定；R2 的 P95/P99 较高，尾部稳定性弱于 Avg/P50。

## 7. 阶段时延稳定性

三轮每轮 analyzer 均关联 503/503 个实例。

| 阶段 | 三轮 Avg 均值 | Avg CV | 三轮 P95 均值 | P95 范围 |
|---|---:|---:|---:|---:|
| Cubelet cubebox-service | 65.942 ms | 1.515% | 81.564 | 76.906–89.721 |
| Cubelet sandbox-start | 37.190 ms | 0.926% | 43.214 | 42.483–43.941 |
| Cubelet sandbox-probe | 21.875 ms | 0.897% | 28.524 | 28.066–29.302 |
| Shim CreatePodSandbox | 28.508 ms | 1.250% | 34.667 | 34–35 |
| Shim ResetVm | 10.859 ms | 1.641% | 14.000 | 14–14 |
| Shim RestoreVm | 8.773 ms | 0.224% | 10.000 | 10–10 |
| formal create_request_total | 29.074 ms | 1.236% | 34.906 | 34.159–35.463 |
| formal VM start→agent ready | 17.304 ms | 1.167% | 21.028 | 19.788–21.813 |

`CreateContainer` 三轮均记录为 0 ms。候选 `c87cbff7` 在 restore 且无需 propagation mount fixup 时跳过 Guest CreateContainer RPC；同一个 `StatDefer` 仍存在，但提前返回低于整数毫秒分辨率。它表示该子窗口被消除到 <1 ms，不表示完整 Sandbox 创建为 0。

## 8. 主机资源窗口

| Round | Min MemAvailable KiB | Max load1 | Max threads | Max running | Max blocked | Max Dirty KiB | Max Writeback KiB | Max CPU PSI | Memory/IO PSI | pgmigrate_fail |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| R1 | 2,273,494,660 | 12.36 | 20,505 | 21 | 0 | 46,120 | 336 | 0.43 | 0 / 0 | 0 |
| R2 | 2,273,898,996 | 6.84 | 19,820 | 17 | 0 | 46,004 | 320 | 0.44 | 0 / 0 | 0 |
| R3 | 2,273,820,680 | 10.48 | 20,029 | 11 | 0 | 46,464 | 720 | 0.42 | 0 / 0 | 0 |

施压窗口中 threads/Dirty/Writeback 高于启动前门禁是现场负载结果；三轮 `procs_blocked=0`、memory/io PSI=0、pgmigrate_fail=0。

## 9. 轮间恢复与 KVM irqfd cleanup

| Gate | Cooldown rows | 从首样本到第 5 个连续通过样本 |
|---|---:|---:|
| R1 前 | 11 | 22.292 s |
| R2 前 | 126 | 314.387 s |
| R3 前 | 138 | 338.511 s |
| R3 后独立恢复 | — | 229 s 到 threads≤8000 |

每轮正式清理后，CubeSandbox 管理面很快显示 Sandbox/Shim/task/TAP=0，但内核仍短期保留约 10,000 个名为 `kvm-irqfd-cleanup` 的 kworker，令 threads 约为 16,000。回收具有批量特征：R3 后 203 秒仍约 10,295 个，210 秒降到 3,642 个，229 秒降到 348 个并通过门禁。

最终冷态核验时：

- threads=5,772
- kworkers=1,956
- kvm-irqfd-cleanup=62
- Sandbox/Shim/task/TAP=0

这不影响 formal 请求成功率，但显著影响连续 benchmark 的可重复调度周期。当前 runner 的 threads 门禁正确阻止了污染状态下的下一轮；不应提高阈值掩盖该现象。

## 10. 清理与最终健康

三轮每轮：

| 时点 | Sandbox | Shim | task | TAP in-use |
|---|---:|---:|---:|---:|
| Before | 0 | 0 | 0 | 0 |
| Peak | 503 | 503 | 503 | 503 |
| After | 0 | 0 | 0 | 0 |

最终：

- quickcheck OK
- CubeMaster/Cubelet/CubeAPI/containerd/control target active
- failed units=0
- node healthy/RUNNING
- opt235 四哈希未变化
- Template READY
- 未运行重试、未手工 kill kworker、未重启服务/主机
- 未修改内核、NUMA、quota、THP、存储、SELinux、firewalld 或 sysctl
- 未 commit/push

## 11. 对比边界

这三轮用于评估当前固定组合自身的稳定性，可以支持“当前组合三轮中心性能稳定”的结论。它不能单独把收益拆分到 MMDS-prime、opt235、HZ=1000、NUMA 策略或 custom CubeAPI 中的任一项。

与先前同 Template 社区 host 四件套单轮相比，opt235 观察值更低；但该 control 只有一轮且时间不相邻，不属于本次三轮稳定性统计。若要得出 host 四件套的严格增益，应执行交替 `community → opt235 → community → opt235`，每个身份至少 3 轮，并让每轮都经过当前 kworker 冷却门禁。

## 12. 时钟说明

- `.90` 报告 `System clock synchronized: no`、chrony stratum 0、Leap status Not synchronised。
- 测试前单次锚点显示本机时钟约比 `.90` 快 126.7 秒，SSH RTT 约 1.16 秒。
- 报告中的远端窗口以 `.90` 日志为准；formal 请求时延、host interval 和阶段时延均来自同机 monotonic/同机日志，不依赖跨主机绝对时间。
- 未修改 NTP/chrony 配置。

## 13. 证据目录

本地脱敏归档：

```text
/home/lyq/Projects/Verification/cubesandbox/remote-results/v051-mmds-prime-2u2g-opt235-c50n500-3rounds-90-20260821T131119Z
```

关键文件：

- `environment-before.txt`：完整硬件、OS、kernel、NUMA、挂载、服务、配置、Template、镜像、二进制与 runner 身份。
- `REMOTE_OUT_DIRS.tsv`：三轮远端唯一结果路径。
- `r1/`、`r2/`、`r3/`：各轮脱敏原始结果、analysis 和 stage-latency。
- `aggregate-3rounds.json`：1500 pooled、轮间稳定性、阶段与 host 汇总。
- `round-summary.csv`：三轮紧凑结果。
- `post-r3-cooldown-poll.txt`：最终 kworker 自然回收时间线。
- `final-cold-state.txt`：最终 quickcheck、哈希、资源和节点状态。
- `SHA256SUMS`：本地全部证据校验和。
