# CubeSandbox ARM64 v3 OCI 核心性能测试报告

测试日期：2026-07-28

测试节点：`root@192.168.25.90`

参考方法：[CubeSandbox 性能基准测试](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)

## 1. 结论摘要

本轮使用 openEuler guest image、openEuler guest kernel、关闭 early probe 的 Cubelet，以及 native code server v3 OCI 镜像。主要结论如下：

1. Template 并发创建四档均在首次尝试完成，合计 `1020/1020` 成功。`c50n500` 平均创建延迟为 **142.57 ms**，低于 170 ms 目标，吞吐为 **235.44 sandbox/s**。
2. 单机累计创建 1000 个 2U2G 沙箱成功，按 `MemAvailable` 差值计算的摊销内存开销为 **15.67 MiB/VM**。测试后资源完整回收。
3. Snapshot、从 Snapshot 创建、Rollback、单实例 Clone、Pause/Resume 均取得有效样本，但多个场景需要重试。成功样本不能被解释为首次成功率。
4. 原 Template `tpl-d38241efa019453f9bc2132c` 上，`n100` Clone 的 c10/c20/c50 分别连续失败 7/5/5 次，主要错误为 HTTP 408 和 `reset guest time failed`。
5. 使用完全相同的 OCI digest、guest image、guest kernel 和规格重建 Template 后，c10、c20 首次成功，c50 第 2 次成功。有效结果分别为 **811.5/665.2/1183.2 ms wall avg**。
6. 重建显著改变了 Clone 可完成性，说明 Template 构建时保存的运行态会影响后续 restore 稳定性；但 c50 仍复现一次 `reset guest time failed`，因此重建不能视为根治。
7. Pause 明显慢于官网 x86 参考结果，而 Resume 接近或快于参考结果。当前最突出问题仍是高并发 restore/reset 的尾延迟与失败率，而不是普通 Template 创建吞吐。

## 2. 测试环境

### 2.1 Host

| 项目 | 本次测试 | 官网参考环境 |
|---|---|---|
| 架构 | ARM64 | x86_64 |
| CPU | Kunpeng 950 7592C, 2 socket x 96 core x 2 thread | Intel Xeon Platinum 8255C, 96 logical CPU |
| 逻辑 CPU | 384 | 96 |
| NUMA | 4 nodes | 2 nodes |
| 内存 | 2,428,167,331,840 bytes，约 2.21 TiB | 375 GiB |
| Host kernel | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` | OpenCloudOS 6.6.119 |
| Cubelet early probe | `CUBESANDBOX_EARLY_PROBE=0` | 未说明 |
| 数据盘 | `/dev/nvme3n1`, XFS, 3.0T，使用率 4% | NVMe XFS, 3.84 TB |
| TAP | 1000 个预创建接口 | 未说明 |

Host 根分区使用率为 98%，但 Cubelet 数据盘 `/data/cubelet` 使用率仅 4%；性能数据与官网环境不构成同硬件等价对比。

### 2.2 Guest 与 OCI

| 层次 | 固定配置 |
|---|---|
| Guest OS image | `/usr/local/services/cubetoolbox/cube-image/cube-guest-image-cpu.img` |
| Guest OS | `openEuler 24.03 (LTS-SP3)`，由 `debugfs` 只读读取镜像内 `/etc/os-release` 确认 |
| Guest image SHA256 | `1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da` |
| Guest kernel | `/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-bm` |
| Guest kernel version | `6.6.0-cubesandbox.guest.oe2403sp3` |
| Guest kernel SHA256 | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| OCI image | `127.0.0.1:5000/cubesandbox-bench/sandbox-code-envd-ci` |
| OCI digest | `sha256:b741fde1de3dd4cc4f4cc82c089e861e5d53f1d5f0b4492be6f9f98f4652af3a` |
| OCI 服务 | envd + native code server v3 |
| SDK | `cubesandbox==0.5.0`，wheel SHA256 `99b6c4683a45626970fb71a8bf334f979004ea225c28d9c87026a7ff060d51de` |

### 2.3 Template

| 项目 | 原 Template | 重建 Template |
|---|---|---|
| Template ID | `tpl-d38241efa019453f9bc2132c` | `tpl-0b2fea9aae424766846c46a2` |
| OCI digest | `b741fde1...` | `b741fde1...` |
| 规格 | 2000m CPU / 2000Mi memory | 2000m CPU / 2000Mi memory |
| Writable layer | 1G | 1G |
| 网络 | TAP | TAP |
| 暴露端口 | 49983、49999 | 49983、49999 |
| Readiness probe | `GET /health:49999` | `GET /health:49999` |
| 状态 | READY | READY，1/1 replica READY |
| Rootfs artifact | 构建前已有 | `rfs-58c5f1cc76d9100492971bdc` |

重建 Template 的功能门禁执行 `run_code("21 * 2")` 返回 42，随后沙箱、快照、shim、task 和占用 TAP 均归零。

## 3. 测试方法

- 参数和轮次遵循官网文章配套脚本：Template 创建 `c1n20/c10n200/c20n300/c50n500`；Snapshot 和 Pause/Resume 每档 5 轮；dirty page 和从 Snapshot 创建每档 3 轮；Clone `n1` 测 5 轮、`n100` 测 2 轮。
- Snapshot、Rollback、Clone 等脚本在正式轮次前均执行 1 轮 warm-up。
- 每个测试用例前后均检查服务健康，并要求沙箱、快照、shim、task、占用 TAP 为 0，TAP 总数不少于 1000。
- 失败用例不进入延迟统计，但保留退出码和日志并重新尝试。表中“尝试”表示选中有效样本来自第几次尝试。
- 官网列仅用于量级参考。架构、CPU 数、内存、guest、OCI 镜像和软件改动均不同，不能据此归因单一优化。

## 4. 从 Template 创建沙箱

所有四档均为原 Template 首次尝试成功。

| 并发 | 请求数 | 成功 | avg | min | p95 | max | 摊销 | 吞吐 | 官网 avg |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 20/20 | 37.02 ms | 32.60 ms | 39.98 ms | 43.49 ms | 43.14 ms | 23.18/s | 47.8 ms |
| 10 | 200 | 200/200 | 45.90 ms | 38.45 ms | 55.44 ms | 67.94 ms | 5.73 ms | 174.42/s | 88.7 ms |
| 20 | 300 | 300/300 | 59.14 ms | 43.89 ms | 78.10 ms | 121.45 ms | 3.47 ms | 288.44/s | 98.1 ms |
| 50 | 500 | 500/500 | **142.57 ms** | 50.18 ms | 219.80 ms | 1328.14 ms | 4.25 ms | 235.44/s | 276.1 ms |

`c50n500` 的平均值达到目标，但最大值 1328.14 ms 明显高于 p95，说明尾部仍有长延迟样本。

## 5. 单机部署密度

该测试按 0 -> 100 -> 300 -> 500 -> 1000 累计创建，达到目标后读取 Host `MemAvailable`。每个点均首次完成。

| 活跃沙箱 | MemAvailable | 相对 0 点减少 | 摊销内存 | 官网摊销内存 |
|---:|---:|---:|---:|---:|
| 0 | 2175.071 GiB | - | - | - |
| 100 | 2174.238 GiB | 0.833 GiB | 8.532 MiB/VM | ~21.5 MB/VM |
| 300 | 2171.441 GiB | 3.630 GiB | 12.391 MiB/VM | ~23.8 MB/VM |
| 500 | 2168.365 GiB | 6.706 GiB | 13.734 MiB/VM | ~25.0 MB/VM |
| 1000 | 2159.773 GiB | 15.298 GiB | **15.665 MiB/VM** | ~25.7 MB/VM |

本表反映 Host 可用内存差值，不等于 guest 声明的 2 GiB。CubeSandbox 使用按需分配与共享/CoW 机制，空闲恢复态沙箱的常驻物理内存远小于声明上限。

## 6. Snapshot

### 6.1 Snapshot 创建并发

三档均首次获得有效样本。

| 并发 | 轮次 | wall avg | wall min | wall p95/max | per avg | 官网 wall avg |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 77.0 ms | 70.4 ms | 83.0 ms | 77.0 ms | 49.8 ms |
| 5 | 5 | 96.4 ms | 90.5 ms | 103.2 ms | 19.3 ms | 71.0 ms |
| 10 | 5 | 113.6 ms | 99.7 ms | 120.0 ms | 11.4 ms | 127.2 ms |

### 6.2 Dirty page

| 写入量 | 实际 dirty avg | Snapshot avg | Snapshot p95 | 从该快照创建 avg | 尝试 | 官网 Snapshot avg |
|---:|---:|---:|---:|---:|---:|---:|
| 0 MB | 3.2 MB | 88.6 ms | 123.7 ms | 43.9 ms | 2 | 45.7 ms |
| 10 MB | 32.3 MB | 83.9 ms | 89.8 ms | 42.0 ms | 2 | 75.7 ms |
| 50 MB | 113.7 MB | 104.5 ms | 107.2 ms | 42.5 ms | 1 | 107.7 ms |
| 100 MB | 179.0 MB | 129.3 ms | 140.8 ms | 40.7 ms | 2 | 138.6 ms |
| 200 MB | 281.2 MB | 155.4 ms | 156.2 ms | 44.2 ms | 2 | 174.2 ms |
| 500 MB | 586.5 MB | 228.9 ms | 246.4 ms | 46.3 ms | 1 | 289.4 ms |
| 800 MB | 891.8 MB | 304.2 ms | 314.1 ms | 41.9 ms | 2 | 392.8 ms |
| 1024 MB | 1119.7 MB | 359.4 ms | 364.9 ms | 42.1 ms | 1 | 486.9 ms |

Snapshot 时间随 dirty page 增长，1024 MB 相对 50 MB 增长约 3.44 倍；从生成的快照再次创建沙箱维持在 40.7-46.3 ms，未随 dirty page 同比例增长。

### 6.3 从 Snapshot 创建

| 并发/总数 | 轮次 | wall avg | wall min | wall p95/max | per avg | 尝试 | 官网 wall avg |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1/1 | 3 | 45.3 ms | 42.3 ms | 47.0 ms | 45.3 ms | 1 | 63.9 ms |
| 10/10 | 3 | 78.2 ms | 63.1 ms | 107.1 ms | 7.8 ms | 1 | 89.9 ms |
| 20/20 | 3 | 114.9 ms | 85.5 ms | 166.8 ms | 5.7 ms | 2 | 118.9 ms |
| 50/50 | 3 | 223.8 ms | 184.2 ms | 269.1 ms | 4.5 ms | 1 | 180.3 ms |

## 7. Rollback

| 并发 | 轮次 | wall avg | wall min | wall p95/max | per avg | 尝试 | 官网 wall avg |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 105.2 ms | 90.8 ms | 115.1 ms | 105.2 ms | 1 | 81.6 ms |
| 5 | 5 | 161.1 ms | 153.1 ms | 176.0 ms | 32.2 ms | 2 | 189.6 ms |
| 10 | 5 | 229.2 ms | 212.9 ms | 251.5 ms | 22.9 ms | 5 | 266.1 ms |

c10 在 4 个失败尝试后才得到有效样本；失败包括 `reset guest time failed` 和 HTTP 408。延迟本身优于官网参考不能覆盖这一可靠性问题。

## 8. Clone

### 8.1 有效延迟

| 场景 | Template | 轮次 | wall avg | wall min | wall p95/max | per avg | 尝试 | 官网 wall avg |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| n1 c1 | 原 Template | 5 | 144.7 ms | 129.5 ms | 156.9 ms | 144.7 ms | 2 | 219.6 ms |
| n100 c10 | 重建 Template | 2 | 811.5 ms | 799.0 ms | 824.0 ms | 8.1 ms | 1 | 870.4 ms |
| n100 c20 | 重建 Template | 2 | 665.2 ms | 502.8 ms | 827.7 ms | 6.7 ms | 1 | 638.6 ms |
| n100 c50 | 重建 Template | 2 | 1183.2 ms | 1021.7 ms | 1344.7 ms | 11.8 ms | 2 | 540.9 ms |

c10 与 c20 和官网处于相近量级；c50 不但没有继续加速，反而比 c20 慢 78%，且首个尝试发生 reset 超时。这表明当前节点在 Clone c50 下进入不稳定区间。

### 8.2 Template 重建 A/B

| Template | c10 | c20 | c50 | 观察 |
|---|---:|---:|---:|---|
| `tpl-d382...` | 7 次完成尝试均失败 | 5 次完成尝试均失败，另 1 次人工中止 | 5 次完成尝试均失败 | HTTP 408 与 guest reset timeout |
| `tpl-0b2f...` | 第 1 次成功 | 第 1 次成功 | 第 1 次 reset timeout，第 2 次成功 | 同 OCI/guest/kernel/spec |

这是本轮最有价值的对照：变量主要是重新执行 Template 构建并生成新的 rootfs/VM 保存态。结果强烈提示旧 Template 本身存在不良运行态或快照链状态，但新 Template 的 c50 仍可复现相同 reset 错误，因此底层竞态仍然存在。

## 9. Pause / Resume

| 并发 | 轮次 | Pause wall avg | Pause per avg | Resume wall avg | Resume per avg | 尝试 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 1101.9 ms | 1101.9 ms | 16.4 ms | 16.4 ms | 1 |
| 5 | 5 | 1163.9 ms | 232.8 ms | 22.8 ms | 4.6 ms | 1 |
| 10 | 5 | 1442.4 ms | 144.2 ms | 30.3 ms | 3.0 ms | 2 |

官网 Pause wall avg 为 558.4/656.9/682.1 ms，本机约为其 1.97/1.77/2.11 倍；官网 Resume wall avg 为 41.8/28.2/35.7 ms，本机 Resume 为 16.4/22.8/30.3 ms。c10 首次 Resume 发生 `reset guest time failed`，第 2 次才形成有效样本。

## 10. 失败与可靠性

下列失败均保留在原始证据中，没有进入延迟均值：

| 测试组 | 失败次数 | 主要错误 |
|---|---:|---|
| Dirty page 8 档 | 5 | guest reset timeout、HTTP 408 |
| 从 Snapshot 创建 4 档 | 1 | HTTP 408 |
| Rollback 3 档 | 5 | guest reset timeout、HTTP 408 |
| Clone n1 | 1 | HTTP 408 |
| 原 Template Clone n100 | 17 个完成失败尝试 | guest reset timeout、HTTP 408 |
| Pause/Resume 3 档 | 1 | Resume guest reset timeout |
| 重建 Template Clone n100 | 1 | c50 guest reset timeout |

失败后曾出现孤立 shim、占用 TAP 和临时 Snapshot。最终清理流程改为：先终止压测、确认无真实 task、停止 Cubelet、精确清理 shim、恢复 Cubelet、使用 `cubemastercli snapshot delete` 删除运行时快照，再将无沙箱关联的占用 TAP 置为 DOWN。未删除任何既有 READY Template。

## 11. 最终状态

测试结束时：

| 项目 | 状态 |
|---|---:|
| CubeMaster / Cubelet / network-agent / CubeAPI | 全部 active |
| Sandboxes | 0 |
| Runtime snapshots | 0 |
| Shim | 0 |
| Task | 0 |
| TAP total | 1000 |
| TAP in use | 0 |
| 重建 Template | READY，1/1 replica READY |

## 12. 数据归档

- 本地根目录：`artifacts/cubesandbox-core-perf-v3-20260728/`
- 原 Template 全套结果：`artifacts/cubesandbox-core-perf-v3-20260728/original-template/`
- 重建 Template 与 Clone 复测：`artifacts/cubesandbox-core-perf-v3-20260728/rebuilt-template/`
- 压测封装：`scripts/run_cubesandbox_core_perf_v3.sh`
- 每个结果目录均包含命令、退出码、选中样本、服务日志、资源门禁和 SHA256 清单。

后续若要证明 Template 重建的因果关系，应在相同服务进程和空闲资源条件下交替构建多份 Template，对每份分别执行固定次数的 c50 Clone，而不是只对一份新旧 Template 做重复请求。建议至少各构建 5 份，并同时报告首次成功率、完整成功率、reset timeout 率和有效延迟分布。
