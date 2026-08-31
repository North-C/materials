# CubeSandbox 宿主机内存开销报告

## 0. 结论先行

- 测试 Host：`<test-host>`。独立档位正式通过上限为 `N=50`；独立与社区式累计测试均完整测到 `N=100`。
- 2026-08-30最新恢复验证仍停在 `N=0`：根盘已恢复到约117 GiB free、Redis RDB持续成功，但旧包络preflight 151个样本未通过且0创建；随后新600秒 N=0窗口发生2次 `node_exporter` memcg OOM，故新包络 `valid=false`。
- 累计测试仍未提交任何 `N=300` POST；`N=300/500/1000` 未测，不外推。此前存储故障已解除，当前硬停止原因变为同期宿主Kubernetes workload的重复memcg OOM，不归因于CubeSandbox。
- 实际 kernel 为 `6.6.0-132.0.0.111.oe2403sp3.aarch64`，不是原目标 `<original-target-host>` 的 6.6.119；本报告只代表 `<test-host>` 独立环境。
- boot ID：`<runtime-id>`；cgroup：`v1`。
- 下表中的 PSS/USS、cgroup 和整机 `MemAvailable` 是平行视角，未相加。`MemAvailable/N` 只称整机摊销，不称 Sandbox RSS。

### 0.1 核心组件随 Sandbox 数量变化

单位为 MiB；PSS/USS 为各正式轮 settled 窗口中值再跨轮取中值。cgroup 是对应 unit 的 `memory.current`/v1 usage，中间可能含 unit 子进程和 page charge。

| N | 指标 | CubeMaster | Cubelet | CubeAPI | network-agent | containerd | Docker daemon |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | PSS | 270.410 | 172.424 | 7.223 | 129.680 | 175.915 | 144.366 |
| 0 | USS | 270.406 | 172.418 | 7.195 | 129.676 | 175.910 | 144.332 |
| 0 | cgroup | 1243.758 | 57.086 | 10.508 | 134.703 | 410.262 | 3917.969 |
| 1 | PSS | 270.176 | 172.427 | 7.246 | 129.883 | 175.089 | 142.694 |
| 1 | USS | 270.172 | 172.422 | 7.223 | 129.879 | 175.084 | 142.660 |
| 1 | cgroup | 1245.467 | 57.086 | 10.518 | 134.711 | 424.168 | 3916.277 |
| 10 | PSS | 270.179 | 172.742 | 9.629 | 131.479 | 174.977 | 142.722 |
| 10 | USS | 270.176 | 172.738 | 9.617 | 131.477 | 174.973 | 142.688 |
| 10 | cgroup | 1246.508 | 57.086 | 12.918 | 136.363 | 411.934 | 3914.277 |
| 50 | PSS | 278.698 | 182.590 | 11.806 | 132.315 | 174.530 | 142.937 |
| 50 | USS | 278.695 | 182.586 | 11.801 | 132.312 | 174.527 | 142.902 |
| 50 | cgroup | 1296.406 | 57.086 | 15.441 | 138.746 | 405.613 | 3915.070 |
| 100（独立观察） | PSS | 288.823 | 224.632 | 14.457 | 144.241 | 174.854 | 143.771 |
| 100（独立观察） | USS | 288.820 | 224.629 | 14.453 | 144.238 | 174.852 | 143.738 |
| 100（独立观察） | cgroup | 1310.797 | 57.086 | 17.871 | 168.980 | 405.488 | 3916.250 |

### 0.2 Sandbox 均摊与整机变化

| N | 正式轮 | 每 Sandbox PSS P50/P95 | 每 Sandbox USS P50/P95 | 每 Sandbox cgroup P50/P95 | 整机 MemAvailable 摊销中值 |
|---:|---:|---:|---:|---:|---:|
| 0 | 1 | — | — | — | — |
| 1 | 1 | 58.885/60.861 | 58.855/60.832 | 6.648/8.027 | 27.779 MiB/实例 |
| 10 | 1 | 17.321/18.937 | 12.402/13.719 | 5.973/7.691 | 25.673 MiB/实例 |
| 50 | 1 | 13.368/14.768 | 12.367/13.727 | 5.488/7.242 | 16.440 MiB/实例 |
| 100（独立观察） | 0 | 12.891/14.256 | 12.391/13.734 | 5.770/7.375 | 15.538 MiB/实例 |

### 0.3 N=100 measurement window（非正式通过点）

N=100 的 90 秒 measurement window 已完整结束，100/100 Sandbox 创建、关联和采样成功；随后 100 个 owned ID 均只 DELETE 一次并全部归零。measurement 结束约 2 分 46 秒后，非 CubeSandbox 的 `dnf-makecache.service` 因 Docker CE 外部仓库 TLS reset 失败，导致全局 failed-unit cleanup gate 在 600 秒内不能通过。因此下表可用于机制观察，但不计入正式回归/CI：

| 指标 | N=100 观测值 |
|---|---:|
| CubeMaster / Cubelet / CubeAPI / network-agent PSS | 288.823 / 224.632 / 14.457 / 144.241 MiB |
| containerd / Docker daemon PSS | 174.854 / 143.771 MiB |
| 每 Sandbox PSS P50/P95 | 12.892 / 14.256 MiB |
| 每 Sandbox USS P50/P95 | 12.391 / 13.734 MiB |
| Snapshot mapping PSS P50/P95 | 9.030 / 10.373 MiB |
| Snapshot mapping USS P50/P95 | 8.748 / 10.086 MiB |
| 每 Sandbox cgroup v1 current P50/P95 | 5.771 / 7.375 MiB |
| 整机 `MemAvailable` 摊销 | 15.538 MiB/实例 |

该轮 measurement 前后 `oom_kill/pswpin/pswpout/allocstall*` 全部零增量；最终 Sandbox/Snapshot/shim/task/VMM/TAP 均为 0。精确边界见 `<local-evidence-root>/n100-r1/posthoc-status.json`。

### 0.4 社区式累计 N=0 -> 100 结果与停止点

用户要求按社区报告继续累计到 1000。`community-cumulative-r2` 使用同一 run 内 N=0 基线、两批 c50 创建到 N=100、100/100 `cubecli exec <id> /bin/true`、30 秒 settle、90 秒多点采样；N=100 tier 本身成功。其后进入 N=300 前置门禁时，CubeMaster/CubeAPI inventory 异常变空而 Cubelet仍有100，故没有提交 N=300 POST，并触发本 run 精确清理。

累计轮的组件 PSS/USS/cgroup 单位均为 MiB，同一行来自同一 settled 窗口：

| N | 指标 | CubeMaster | Cubelet | CubeAPI | network-agent | containerd | Docker daemon |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0 | PSS | 262.891 | 180.429 | 31.672 | 115.473 | 173.368 | 151.258 |
| 0 | USS | 262.887 | 180.422 | 31.645 | 115.469 | 173.363 | 151.223 |
| 0 | cgroup | 1356.645 | 57.086 | 35.121 | 159.457 | 409.355 | 3925.277 |
| 100 | PSS | 317.921 | 268.995 | 38.617 | 115.093 | 173.073 | 151.340 |
| 100 | USS | 317.918 | 268.992 | 38.613 | 115.090 | 173.070 | 151.309 |
| 100 | cgroup | 1435.395 | 57.086 | 42.129 | 161.727 | 411.402 | 3926.066 |

累计 N=100 的 Sandbox 与 Host 口径如下：

| 指标 | N=100累计轮 |
|---|---:|
| 每 Sandbox PSS P50/P95/min/max | 15.240 / 15.751 / 14.902 / 15.955 MiB |
| 每 Sandbox USS P50/P95/min/max | 14.664 / 15.172 / 14.332 / 15.344 MiB |
| Snapshot mapping PSS P50/P95/min/max | 11.153 / 11.608 / 10.902 / 11.719 MiB |
| Snapshot mapping USS P50/P95/min/max | 10.852 / 11.301 / 10.594 / 11.418 MiB |
| Sandbox cgroup v1 current P50/P95/min/max | 7.258 / 7.773 / 6.781 / 11.254 MiB |
| Host `MemAvailable` 差值/N | 20.372 MiB/实例 |

同一累计轮从 N=0 到 N=100 的 Host 变化为：`AnonPages +17.003`、`Cached +1.533`、`PageTables +0.521`、`SecPageTables +0.255`、`KernelStack +0.321`、`Slab +0.114 MiB/实例`。整段无 `oom_kill/swap/allocstall/pgscan/pgsteal` 增量，因此这个 N=100 点不是内存回收压力点。

清理时100个 owned ID各只发送一次 DELETE；由于 Redis 已进入 `MISCONF`，100次响应均为 HTTP 500。没有重试，也没有 kill/删目录/restart。随后只读核验 Master、Cubelet、CubeAPI、shim/VMM/TAP均为0，说明运行时对象已消失；但 Redis proxy-map 是否留下逻辑脏状态无法在损坏现场可靠确认，记为 unknown。当时在管理员修复根盘与 Redis 前禁止继续测试。

### 0.5 磁盘清理后的恢复验证与最新 N=0

2026-08-30在用户明确授权清理历史 `vmcore`、旧备份和部分未引用Docker镜像后，根盘可用空间恢复到约117 GiB；Redis容器为healthy，且日志连续记录RDB `DB saved on disk`与`Background saving terminated with success`。同一boot、组件hash和Template fingerprint均未漂移，Phase A通过。

随后执行两个全新attempt：

1. `community-cumulative-r3`：使用旧10分钟control envelope，151个preflight样本始终因 `threads > 13901`失败；0 Sandbox创建、0 DELETE，最终资源空。
2. `n0-post-cleanup-r1`：使用授权的 `observe-baseline`重新采600秒 N=0，共302个正式Host样本、41个组件深样本。资源始终为空，但窗口中 `oom_kill +2`，因此派生包络 `valid=false`，没有启动累计R4或任何密度创建。

OOM一手日志显示两次均为Kubernetes burstable memcg内的 `node_exporter`，不是CubeSandbox进程：

| 时间 | constraint | 被终止对象 | anon RSS |
|---|---|---|---:|
| 2026-08-30 00:07:28 +08:00 | `CONSTRAINT_MEMCG` | `node_exporter` PID 1904984 | 140640 KiB |
| 2026-08-30 00:11:17 +08:00 | `CONSTRAINT_MEMCG` | `node_exporter` PID 1995910 | 142676 KiB |

窗口结束后00:18:28又发生第3次相同 `node_exporter` memcg OOM，证明这是持续的宿主基线异常，而不是单个采样毛刺。没有修改Pod/cgroup限制、重启workload或清零计数来绕过门禁。

最新N=0组件观察值如下。单位MiB；这些值可描述当前固定进程观察，但由于同期OOM，**不能作为密度回归截距或有效容量基线**。

| 指标 | CubeMaster | Cubelet | CubeAPI | network-agent | containerd | Docker daemon |
|---|---:|---:|---:|---:|---:|---:|
| PSS median | 283.781 | 190.722 | 42.531 | 113.020 | 166.221 | 141.738 |
| USS median | 283.777 | 190.715 | 42.500 | 113.016 | 166.215 | 141.703 |
| cgroup median | 1328.434 | 57.086 | 46.000 | 161.258 | 2235.742 | 3880.020 |
| PSS sample min/max | 275.367/303.758 | 190.706/191.222 | 42.528/42.531 | 113.020/114.074 | 163.439/174.748 | 140.489/142.830 |

`containerd.service` cgroup包含其层级下的通用Kubernetes/containerd charge，2.236 GiB不是containerd进程PSS，也不能归给CubeSandbox。

## 1. 环境与身份

- uname：`Linux <hostname> 6.6.0-132.0.0.111.oe2403sp3.aarch64 #1 SMP Mon Dec 29 23:09:17 CST 2025 aarch64 aarch64 aarch64 GNU/Linux`
- cgroup mode：`v1`。
- 独立 run：4/5整轮成功，正式密度0/1/10/50；独立 N=100 measurement成功但整轮健康门禁失败。累计 R2 的 N=0与N=100 tier成功，整轮在 N=300前失败。
- 该 Host 是 openEuler 24.03 LTS-SP3 ARM64、kernel 6.6.0；官方 BMI5 表是 OpenCloudOS/TencentOS 4、x86_64、kernel 6.6.119，二者只比较机制，不比较绝对数值。
- 用户明确授权 `<test-host>` 用 10 分钟 N=0 control envelope 代替 `<original-target-host>` 绝对 load/threads门禁；没有修改任何 Host参数。N=0 共 300 个 Host样本、40 个组件深样本，OOM/swap/allocstall零增量。
- Template：`<template-id>`，READY replica位于 `<test-host>`，`cpu=2000m,mem=2000Mi`；VMM memory 2,097,152,000 bytes，`prefault=false/shared=false/hugepages=false`，memory base为 CubeCow reflink volume。
- `<test-host>` 为 cgroup v1且无 PSI；cgroup使用量是 first-touch/fuzzy charge，只作为与 PSS/Host平行的参考，不能公平分摊共享页。
- 每个 run 的 boot、二进制 SHA-256、systemd PID/start ticks 和 unit start identity 均由 runner 前后校验；原值见各 run 的 `identity-before.json`/`identity-after.json`。

### 1.1 二进制 hash

| 路径 | SHA-256 |
|---|---|
| `/usr/local/services/cubetoolbox/CubeAPI/bin/cube-api` | `592c7b45c0c3655abb128c5059264cdf1b0b8388c565475577350569c12882be` |
| `/usr/local/services/cubetoolbox/CubeMaster/bin/cubemaster` | `4901f854d6417d5059bbb3148da9ddc64af00d9721207c0c66ecb2696394c50c` |
| `/usr/local/services/cubetoolbox/Cubelet/bin/cubecli` | `27212ca7a27a013563fd10f6c748ae61aff18eeb3d43f2035322de501555fc29` |
| `/usr/local/services/cubetoolbox/Cubelet/bin/cubelet` | `742508f69735a22beae783b77f7c307056e2b3dd443a2434a26e3d75eb967bc5` |
| `/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs` | `c3d9bd094a8fc9d86b4b06a684ee574f8f8e023479c1f4088b8597c2a6c03d46` |
| `/usr/local/services/cubetoolbox/cube-shim/bin/cube-runtime` | `a68d64cd29c84d544b2c8a4e1f9d6ab2d60d7d451f9ecd1ffccb811d4749ea9f` |
| `/usr/local/services/cubetoolbox/network-agent/bin/network-agent` | `b6c6ba8082d47b22273b09ac69fb33da6af4fc08e4b6da72b50b5e95ea0b11d8` |

## 2. 组件明细

除核心矩阵外，下面保留全部 systemd/Docker component。`runs` 是该密度成功 run 数。

| N | 组件 | runs | PSS median/min/max | USS median | RSS median | cgroup median |
|---:|---|---:|---:|---:|---:|---:|
| 0 | containerd | 1 | 175.915/175.915/175.915 | 175.910 | 177.047 | 410.262 |
| 0 | cube-egress | 1 | 2.304/2.304/2.304 | 1.578 | 3.676 | 25.039 |
| 0 | cube-lifecycle-manager | 1 | 30.008/30.008/30.008 | 30.008 | 30.012 | 28.969 |
| 0 | cube-proxy | 1 | 2.059/2.059/2.059 | 1.934 | 4.098 | 16214.004 |
| 0 | cube-proxy-coredns | 1 | 89.684/89.684/89.684 | 89.684 | 89.688 | 101.527 |
| 0 | cube-sandbox-coredns.service | 1 | 46.411/46.411/46.411 | 44.848 | 49.480 | 54.445 |
| 0 | CubeAPI | 1 | 7.223/7.223/7.223 | 7.195 | 8.684 | 10.508 |
| 0 | cube-sandbox-cube-egress.service | 1 | 45.321/45.321/45.321 | 43.758 | 48.383 | 48.598 |
| 0 | cube-sandbox-cube-lifecycle-manager.service | 1 | 1.210/1.210/1.210 | 0.574 | 8.820 | 34.121 |
| 0 | cube-sandbox-cube-proxy.service | 1 | 1.245/1.245/1.245 | 0.609 | 8.855 | 36.145 |
| 0 | Cubelet | 1 | 172.424/172.424/172.424 | 172.418 | 173.715 | 57.086 |
| 0 | CubeMaster | 1 | 270.410/270.410/270.410 | 270.406 | 271.512 | 1243.758 |
| 0 | cube-sandbox-mysql | 1 | 493.293/493.293/493.293 | 493.293 | 493.297 | 7369.980 |
| 0 | cube-sandbox-mysql.service | 1 | 1.210/1.210/1.210 | 0.574 | 8.820 | 42.051 |
| 0 | network-agent | 1 | 129.680/129.680/129.680 | 129.676 | 130.781 | 134.703 |
| 0 | cube-sandbox-redis | 1 | 20.734/20.734/20.734 | 20.734 | 20.738 | 31.004 |
| 0 | cube-sandbox-redis.service | 1 | 1.214/1.214/1.214 | 0.578 | 8.809 | 40.988 |
| 0 | cube-sandbox-webui.service | 1 | 1.210/1.210/1.210 | 0.574 | 8.820 | 47.855 |
| 0 | cube-webui | 1 | 0.108/0.108/0.108 | 0.102 | 1.465 | 258.730 |
| 0 | Docker daemon | 1 | 144.366/144.366/144.366 | 144.332 | 146.762 | 3917.969 |
| 0 | postgres | 1 | 7.597/7.597/7.597 | 6.410 | 12.266 | 17.695 |
| 1 | containerd | 1 | 175.089/175.089/175.089 | 175.084 | 176.170 | 424.168 |
| 1 | cube-egress | 1 | 2.304/2.304/2.304 | 1.578 | 3.676 | 25.039 |
| 1 | cube-lifecycle-manager | 1 | 29.953/29.953/29.953 | 29.953 | 29.957 | 28.891 |
| 1 | cube-proxy | 1 | 2.059/2.059/2.059 | 1.934 | 4.098 | 16214.023 |
| 1 | cube-proxy-coredns | 1 | 89.625/89.625/89.625 | 89.625 | 89.629 | 101.480 |
| 1 | cube-sandbox-coredns.service | 1 | 46.474/46.474/46.474 | 44.910 | 49.543 | 54.508 |
| 1 | CubeAPI | 1 | 7.246/7.246/7.246 | 7.223 | 8.711 | 10.518 |
| 1 | cube-sandbox-cube-egress.service | 1 | 45.384/45.384/45.384 | 43.820 | 48.445 | 48.660 |
| 1 | cube-sandbox-cube-lifecycle-manager.service | 1 | 1.210/1.210/1.210 | 0.574 | 8.820 | 34.121 |
| 1 | cube-sandbox-cube-proxy.service | 1 | 1.245/1.245/1.245 | 0.609 | 8.855 | 36.145 |
| 1 | Cubelet | 1 | 172.427/172.427/172.427 | 172.422 | 173.719 | 57.086 |
| 1 | CubeMaster | 1 | 270.176/270.176/270.176 | 270.172 | 271.277 | 1245.467 |
| 1 | cube-sandbox-mysql | 1 | 493.305/493.305/493.305 | 493.305 | 493.309 | 7381.154 |
| 1 | cube-sandbox-mysql.service | 1 | 1.210/1.210/1.210 | 0.574 | 8.820 | 41.949 |
| 1 | network-agent | 1 | 129.883/129.883/129.883 | 129.879 | 130.984 | 134.711 |
| 1 | cube-sandbox-redis | 1 | 20.734/20.734/20.734 | 20.734 | 20.738 | 30.850 |
| 1 | cube-sandbox-redis.service | 1 | 1.214/1.214/1.214 | 0.578 | 8.809 | 41.004 |
| 1 | cube-sandbox-webui.service | 1 | 1.210/1.210/1.210 | 0.574 | 8.820 | 47.637 |
| 1 | cube-webui | 1 | 0.108/0.108/0.108 | 0.102 | 1.465 | 258.748 |
| 1 | Docker daemon | 1 | 142.694/142.694/142.694 | 142.660 | 145.090 | 3916.277 |
| 1 | postgres | 1 | 7.597/7.597/7.597 | 6.410 | 12.266 | 17.695 |
| 10 | containerd | 1 | 174.977/174.977/174.977 | 174.973 | 176.059 | 411.934 |
| 10 | cube-egress | 1 | 2.304/2.304/2.304 | 1.578 | 3.676 | 25.043 |
| 10 | cube-lifecycle-manager | 1 | 30.109/30.109/30.109 | 30.109 | 30.113 | 29.047 |
| 10 | cube-proxy | 1 | 2.059/2.059/2.059 | 1.934 | 4.098 | 16214.035 |
| 10 | cube-proxy-coredns | 1 | 89.469/89.469/89.469 | 89.469 | 89.473 | 101.340 |
| 10 | cube-sandbox-coredns.service | 1 | 46.724/46.724/46.724 | 45.160 | 49.793 | 54.758 |
| 10 | CubeAPI | 1 | 9.629/9.629/9.629 | 9.617 | 11.105 | 12.918 |
| 10 | cube-sandbox-cube-egress.service | 1 | 45.384/45.384/45.384 | 43.820 | 48.445 | 48.660 |
| 10 | cube-sandbox-cube-lifecycle-manager.service | 1 | 1.209/1.209/1.209 | 0.574 | 8.820 | 34.121 |
| 10 | cube-sandbox-cube-proxy.service | 1 | 1.244/1.244/1.244 | 0.609 | 8.855 | 36.145 |
| 10 | Cubelet | 1 | 172.742/172.742/172.742 | 172.738 | 174.035 | 57.086 |
| 10 | CubeMaster | 1 | 270.179/270.179/270.179 | 270.176 | 271.281 | 1246.508 |
| 10 | cube-sandbox-mysql | 1 | 493.445/493.445/493.445 | 493.445 | 493.449 | 7389.492 |
| 10 | cube-sandbox-mysql.service | 1 | 1.209/1.209/1.209 | 0.574 | 8.820 | 41.949 |
| 10 | network-agent | 1 | 131.479/131.479/131.479 | 131.477 | 132.582 | 136.363 |
| 10 | cube-sandbox-redis | 1 | 20.750/20.750/20.750 | 20.750 | 20.754 | 30.484 |
| 10 | cube-sandbox-redis.service | 1 | 1.213/1.213/1.213 | 0.578 | 8.809 | 40.676 |
| 10 | cube-sandbox-webui.service | 1 | 1.209/1.209/1.209 | 0.574 | 8.820 | 48.020 |
| 10 | cube-webui | 1 | 0.108/0.108/0.108 | 0.102 | 1.465 | 259.234 |
| 10 | Docker daemon | 1 | 142.722/142.722/142.722 | 142.688 | 145.117 | 3914.277 |
| 10 | postgres | 1 | 7.597/7.597/7.597 | 6.410 | 12.266 | 17.695 |
| 50 | containerd | 1 | 174.530/174.530/174.530 | 174.527 | 175.613 | 405.613 |
| 50 | cube-egress | 1 | 2.304/2.304/2.304 | 1.578 | 3.676 | 25.043 |
| 50 | cube-lifecycle-manager | 1 | 29.840/29.840/29.840 | 29.840 | 29.844 | 28.988 |
| 50 | cube-proxy | 1 | 2.059/2.059/2.059 | 1.934 | 4.098 | 16214.062 |
| 50 | cube-proxy-coredns | 1 | 89.250/89.250/89.250 | 89.250 | 89.254 | 101.121 |
| 50 | cube-sandbox-coredns.service | 1 | 46.566/46.566/46.566 | 45.004 | 49.637 | 54.633 |
| 50 | CubeAPI | 1 | 11.806/11.806/11.806 | 11.801 | 13.289 | 15.441 |
| 50 | cube-sandbox-cube-egress.service | 1 | 45.414/45.414/45.414 | 43.852 | 48.477 | 48.691 |
| 50 | cube-sandbox-cube-lifecycle-manager.service | 1 | 1.209/1.209/1.209 | 0.574 | 8.820 | 34.125 |
| 50 | cube-sandbox-cube-proxy.service | 1 | 1.244/1.244/1.244 | 0.609 | 8.855 | 36.145 |
| 50 | Cubelet | 1 | 182.590/182.590/182.590 | 182.586 | 183.883 | 57.086 |
| 50 | CubeMaster | 1 | 278.698/278.698/278.698 | 278.695 | 279.801 | 1296.406 |
| 50 | cube-sandbox-mysql | 1 | 493.527/493.527/493.527 | 493.527 | 493.531 | 7402.098 |
| 50 | cube-sandbox-mysql.service | 1 | 1.209/1.209/1.209 | 0.574 | 8.820 | 41.996 |
| 50 | network-agent | 1 | 132.315/132.315/132.315 | 132.312 | 133.418 | 138.746 |
| 50 | cube-sandbox-redis | 1 | 20.762/20.762/20.762 | 20.762 | 20.766 | 30.445 |
| 50 | cube-sandbox-redis.service | 1 | 1.213/1.213/1.213 | 0.578 | 8.809 | 40.887 |
| 50 | cube-sandbox-webui.service | 1 | 1.209/1.209/1.209 | 0.574 | 8.820 | 47.777 |
| 50 | cube-webui | 1 | 0.108/0.108/0.108 | 0.102 | 1.465 | 258.547 |
| 50 | Docker daemon | 1 | 142.937/142.937/142.937 | 142.902 | 145.332 | 3915.070 |
| 50 | postgres | 1 | 7.597/7.597/7.597 | 6.410 | 12.266 | 17.695 |

### 2.1 累计轮全部组件 N=0 与 N=100 对照

单位为 MiB。systemd wrapper与其管理的 Docker容器是两个不同对象，按名称分别列示；不能把 wrapper cgroup和容器 cgroup相加后再称为物理内存。`cube-proxy`、MySQL等很大的 cgroup current包含该层级 charge，不等于进程 PSS。

| 组件 | N0 PSS | N0 USS | N0 cgroup | N100 PSS | N100 USS | N100 cgroup |
|---|---:|---:|---:|---:|---:|---:|
| cube-sandbox-cubemaster.service | 262.891 | 262.887 | 1356.645 | 317.921 | 317.918 | 1435.395 |
| cube-sandbox-cubelet.service | 180.429 | 180.422 | 57.086 | 268.995 | 268.992 | 57.086 |
| cube-sandbox-cube-api.service | 31.672 | 31.645 | 35.121 | 38.617 | 38.613 | 42.129 |
| cube-sandbox-network-agent.service | 115.473 | 115.469 | 159.457 | 115.093 | 115.090 | 161.727 |
| cube-sandbox-coredns.service | 47.286 | 45.723 | 54.633 | 47.285 | 45.723 | 54.633 |
| cube-sandbox-cube-egress.service | 44.509 | 42.945 | 48.660 | 44.508 | 42.945 | 48.660 |
| cube-sandbox-cube-lifecycle-manager.service | 1.210 | 0.574 | 34.125 | 1.209 | 0.574 | 34.250 |
| cube-sandbox-cube-proxy.service | 1.245 | 0.609 | 36.145 | 1.244 | 0.609 | 36.145 |
| cube-sandbox-mysql.service | 1.210 | 0.574 | 41.930 | 1.209 | 0.574 | 42.027 |
| cube-sandbox-redis.service | 1.213 | 0.578 | 40.941 | 1.213 | 0.578 | 40.660 |
| cube-sandbox-webui.service | 1.210 | 0.574 | 47.746 | 1.209 | 0.574 | 47.777 |
| containerd.service | 173.368 | 173.363 | 409.355 | 173.073 | 173.070 | 411.402 |
| docker.service | 151.258 | 151.223 | 3925.277 | 151.340 | 151.309 | 3926.066 |
| cube-egress | 2.321 | 1.605 | 25.156 | 2.321 | 1.605 | 25.156 |
| cube-proxy | 2.059 | 1.934 | 16214.297 | 2.059 | 1.934 | 16214.324 |
| cube-lifecycle-manager | 31.000 | 31.000 | 31.047 | 31.152 | 31.152 | 31.309 |
| cube-webui | 0.108 | 0.102 | 258.691 | 0.108 | 0.102 | 258.980 |
| cube-sandbox-redis | 20.863 | 20.863 | 30.848 | 20.891 | 20.891 | 30.328 |
| cube-sandbox-mysql | 497.602 | 497.602 | 7545.449 | 497.645 | 497.645 | 7559.523 |
| cube-proxy-coredns | 89.285 | 89.285 | 100.234 | 90.691 | 90.691 | 102.156 |
| postgres | 7.597 | 6.410 | 17.695 | 7.597 | 6.410 | 17.695 |

## 3. 每 Sandbox 分布与共享/独占

- `PSS` 按共享 mapping 比例分摊；`USS_nonhugetlb = Private_Clean + Private_Dirty`。RSS 仅保留单进程观察，不跨 VMM求物理总量。
- Snapshot mapping 使用 run 配置中的 path filter，从 `/proc/<pid>/smaps` 按 pathname/dev/inode 保存；mapping PSS/USS见 `per-sandbox-distribution.json`。
- cgroup current 含 anon/file/kernel charge；共享 file page 的 charge 不等同于 PSS比例，因此二者不做逐字节闭合。

| N | 样本数 | PSS min/P50/P95/max | USS min/P50/P95/max | cgroup min/P50/P95/max | Snapshot mapping PSS P50/P95 |
|---:|---:|---:|---:|---:|---:|
| 1 | 2 | 58.885/58.885/60.861/60.861 | 58.855/58.855/60.832/60.832 | 6.648/6.648/8.027/8.027 | 34.844/36.320 |
| 10 | 30 | 15.178/17.321/18.937/19.026 | 10.355/12.402/13.719/13.809 | 3.512/5.973/7.691/7.723 | 11.578/12.974 |
| 50 | 150 | 11.054/13.368/14.768/15.271 | 10.078/12.367/13.727/14.207 | 2.871/5.488/7.242/7.922 | 9.299/10.657 |
| 100（独立观察） | 300 | 10.747/12.891/14.256/14.769 | 10.238/12.391/13.734/14.242 | 3.543/5.770/7.375/8.012 | 9.030/10.373 |

### 3.1 为什么社区报告的均摊值反而增长

结论：**这不违反 CoW。CoW预测下降的是“共享 base在单 Sandbox PSS中的分摊”，社区表计算的是整机 `MemAvailable` 差值/N；后者没有单调下降保证。**

[官方 3.3 节](https://docs.cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)只保存了：

| N | `free available` | 报告均摊 |
|---:|---:|---:|
| 0 | 359.5 GiB | — |
| 100 | 357.4 GiB | ~21.5 MB |
| 300 | 352.5 GiB | ~23.8 MB |
| 500 | 347.3 GiB | ~25.0 MB |
| 1000 | 334.3 GiB | ~25.7 MB |

报告公式是 `(当前 used - 基线 used)/N`，在 MemTotal不变时等价于 `(Available(0)-Available(N))/N`。按显示的一位小数反算新增批次边际：

| 新增区间 | `MemAvailable` 边际损失 |
|---|---:|
| 0→100 | 21.504 MiB/新增实例 |
| 100→300 | 25.088 MiB/新增实例 |
| 300→500 | 26.624 MiB/新增实例 |
| 500→1000 | 26.624 MiB/新增实例 |

所以更准确的描述是：**最初100个点偏低，后续边际约26.6 MiB并趋稳，累计平均向后续斜率收敛**，并不是单位成本持续无界恶化。原表只有单次 `free -h`、0.1 GiB显示精度，没有固定 settle、多时间点、PSS/USS/cgroup/Host分项或 density raw；无法从旧表认定唯一根因。

理想化 CoW 模型：

```text
HostDelta(N) = SharedBaseResident(N)
             + PrivateAnon(N)
             + SandboxProcess(N)
             + KernelAndNetwork(N)
             + FileCacheAndControlPlane(N)
             + HostNoise(N)

average(N) = HostDelta(N) / N
```

只有当共享 resident base从低 N起就是固定常数、每实例私有项恒定、其余项严格线性且无噪声时，`SharedBase/N` 才必然拉低总平均。当前实现并不满足这些充分条件：

- VMM快速恢复把 Snapshot memory file以 `MAP_PRIVATE|MAP_NORESERVE` 映射；`prefault=false`。未访问页不 resident，只读页可共享，Guest写页转成每 VMM私有匿名页。源码见 `hypervisor/vmm/src/memory_manager.rs:1326-1375,1494-1545`。
- 每个 Sandbox仍有独立 CubeShim/VMM状态、Guest kernel/agent写页、页表/KVM二级页表、内核栈、TAP/vsock/socket、cgroup和slab对象。
- rootfs `FICLONE` 共享的是 XFS extent，不等于所有独立 inode的 page cache/元数据只保留一份。
- Linux `MemAvailable` 是包含 file LRU和可回收 slab估计的启发式量，不是 `MemTotal - CubeSandbox物理内存`。[Linux 6.6 meminfo](https://docs.kernel.org/6.6/filesystems/proc.html#meminfo)
- PSS才把一页按映射者数量分摊；`MAP_PRIVATE`写页会成为私有匿名页。[Linux smaps](https://docs.kernel.org/6.6/filesystems/proc.html#chapter-1-collecting-system-information)
- cgroup v1共享页是 first-touch charge，`memory.usage_in_bytes` 还是近似值，不能当公平 PSS。[Linux cgroup v1 memory](https://docs.kernel.org/6.6/admin-guide/cgroup-v1/memory.html#shared-page-accounting)

本次 `<test-host>` 数据直接验证了 CoW方向：

| N | 每 Sandbox PSS | 每 Sandbox USS | Snapshot mapping PSS | Snapshot mapping USS | Host `MemAvailable` 摊销 |
|---:|---:|---:|---:|---:|---:|
| 1 | 59.873 | 59.844 | 35.582 | 35.582 | 27.779 MiB |
| 10 | 17.358 | 12.402 | 11.587 | 8.746 | 25.673 MiB |
| 50 | 13.368 | 12.371 | 9.301 | 8.732 | 16.440 MiB |
| 100（观测） | 12.892 | 12.391 | 9.030 | 8.748 | 15.538 MiB |

关键判读：

1. Mapping PSS从35.6降到约9.0 MiB，说明共享 base确实被更多实例摊薄。
2. Mapping USS稳定在约8.7 MiB，说明 Guest启动后约有这一量级页面已经私有化/独触，形成不能继续靠共享消除的下限。
3. N=50/100时，Host每实例主要增量可由匿名页和内核项解释：

| Host分项（MiB/实例） | N=50 | N=100观测 |
|---|---:|---:|
| `AnonPages` | 13.591 | 13.001 |
| `Cached` | 0.556 | 0.391 |
| `PageTables` | 0.477 | 0.473 |
| `SecPageTables` | 0.237 | 0.237 |
| `KernelStack` | 0.339 | 0.332 |
| `Slab` | 0.281 | 0.193 |

4. 核心四组件 PSS从 N=0 的约579.7 MiB增加到 N=50 的约605.4 MiB，即约0.51 MiB/实例的控制面边际；它也计入整机差值，却不是 Sandbox VMM RSS。
5. N=1时单一 file mapping会在 smaps中表现为 Private_Clean/全额PSS，但文件页仍可回收，故 PSS约59.9 MiB而 `MemAvailable`损失只有27.8 MiB；再次说明两个视角不能闭合相加。

因此，社区历史增长最合理的候选是：累计 create-only使高 N点同时代表更老的 cohort和更长的后台触页/写页时间；低密度工作集尚未完全 materialize；再叠加每实例私有匿名页、内核/控制面边际、page cache与单点舍入。**旧报告缺 raw，无法进一步把其中某一项认定为已验证唯一根因；本次 `<test-host>` 独立档位没有复现“均摊上升”，而是按 CoW预期下降并在约15–16 MiB附近收敛。累计轮只得到 N=100 的20.372 MiB/实例，缺少 N=300/500/1000，不能判断累计曲线方向。**

## 4. 边际回归与非线性检查

OLS、Theil-Sen 和 10,000 次 run-level bootstrap 使用相同 run-level 点；CI 为 percentile 2.5%/97.5%。当前每密度仅 1 个成功 run，CI 只能作探索性敏感度，不能当稳定重复置信区间。仅解释到正式通过上限。

| 视角 | OLS slope | 95% CI | intercept | R² | Theil-Sen slope |
|---|---:|---:|---:|---:|---:|
| 核心组件 + Sandbox PSS (KiB/实例) | 13579.697 | 13101.600..61305.000 | 623590.871 | 0.9953 | 13725.142 |
| 核心组件 + Sandbox USS (KiB/实例) | 12680.573 | 7729.333..61280.000 | 611902.265 | 0.9946 | 13087.880 |
| 核心组件 PSS (KiB/实例) | 533.015 | -5.000..547.325 | 593191.520 | 0.9990 | 507.390 |
| Sandbox PSS total (KiB/实例) | 13046.682 | 12554.275..61310.000 | 30399.351 | 0.9947 | 13217.752 |
| Sandbox cgroup total (bytes/实例) | 5680619.085 | 5575884.800..7694336.000 | 2409918.956 | 0.9997 | 5914132.480 |
| 整机 MemAvailable loss (KiB/实例) | 16438.640 | 14471.150..28446.000 | 32579.747 | 0.9869 | 21442.158 |

每点 residual、相邻密度和所有 bootstrap 元数据见 `density-trend.json`。若 slope 随区间明显变化，正文只能描述非线性，不用单一 slope 外推。

## 5. before -> peak -> settled -> cleanup

- Host 每 2 秒采样；deep sample 固定读取组件/Sandbox proc 与 cgroup。create peak 是离散采样观察峰值，不称绝对瞬时峰值。
- DELETE 只针对 fsync ledger 中本 run 的精确 ID，每个 ID 最多一次。最终资源和 failed units见各 run `result.json`。
- `memory-samples.csv` 保留 pre_create/create/settled/delete/cleanup_cooldown，足以独立复算 MemAvailable、PSI、reclaim、fault、NUMA和 threads回收曲线。

## 6. 失败、停止点与观测上限

| run | success | error | cleanup error |
|---|---|---|---|
| `n0-r1` | true | — | — |
| `n1-r1` | true | — | — |
| `n10-r1` | true | — | — |
| `n100-r1` | false | RuntimeError: cleanup/cooldown did not pass within timeout | — |
| `n50-r1` | true | — | — |
| `community-cumulative-r1` | false | N=100 Guest probe在 c50并发下0/100成功；方法失败 | 100/100一次DELETE，最终空 |
| `community-probe-c1` | true | 单 Sandbox顺序 probe诊断成功 | 1/1一次DELETE，最终空 |
| `community-cumulative-r2` | false（N=100 tier成功） | N=300前控制面异常；收到本 worker SIGTERM进入清理 | 100次DELETE均500；最终运行时资源空，Redis逻辑状态unknown |
| `community-cumulative-r3` | false | 旧control envelope preflight 151样本未通过 | 0创建/0删除，最终空 |
| `n0-post-cleanup-r1` | runner完成、包络无效 | 600秒 N=0内 `oom_kill +2` | 0创建/0删除，最终空 |

本报告独立轮最高正式点为 `N=50`；累计轮最高完整 measurement tier 为 `N=100`。任何更高目标、部分成功或门禁失败点均不外推。

- N=100 measurement完成且资源归零，但被随后发生的非 Cube `dnf-makecache.service` failed阻断整轮健康验收；保留为观察点。
- 累计 R1 的 N=100 create/readiness成功，但新增 Guest probe用 c50并发导致0/100超时；失败被保留。单实例 c1诊断随后证明接口本身可用，R2改为顺序 probe，而 create仍保持c50。
- 累计 R2 的 N=100创建100/100、Guest probe 100/100、settled采样和 tier门禁均成功。N=300前控制面出现异常，未提交任何 N=300 create请求；N=300/500/1000均未测。
- 只读诊断发现 `/` 为 ext4、492 GiB、可用0、使用率100%；Redis容器 unhealthy，日志反复记录 RDB `No space left on device`，DELETE返回 `MISCONF ... stop-writes-on-bgsave-error`。这是存储故障，不是内存耗尽。
- Phase A其实已记录根分区仅余约357 MiB，但旧 gate没有据此失败关闭。这是本测试方法的明确缺陷；脚本已增加默认 `root free >= 10 GiB` 门禁，历史 attempt不被追溯改写为成功。
- R2 的100个 DELETE均已尝试一次且不重试；最终 Master/Cubelet/API、shim/VMM/TAP运行时集合为空。Redis proxy-map 是否残留为 unknown，因此不得把本现场称为完全健康清理。
- 存储清理后Redis持久化已恢复；R3没有通过旧threads包络且未创建。随后重采的10分钟N=0因 `node_exporter` memcg OOM无效，故没有R4，也没有任何新的N=100/300/500/1000点。
- 原计划的关键密度三轮重复没有继续，原因同上；因此当前回归和 bootstrap只用于探索趋势，不能作为稳定置信区间。
- 没有执行 `systemctl reset-failed`、服务重启、参数修改、drop_caches或进程 kill来美化结果。

## 7. 公式与口径

```text
host_memavailable_delta(N,r) = median(MemAvailable_pre) - median(MemAvailable_settled)
host_memavailable_amortized = host_memavailable_delta / N
tracked_pss = sum(core component PSS) + sum(worker Sandbox process PSS)
tracked_uss = sum(core component USS_nonhugetlb) + sum(worker Sandbox process USS_nonhugetlb)
nearest_rank(p) = sorted[ceil(n*p/100)-1]
```

`MemAvailable` 是含回收估计的 Host 可用性指标；PSS 是进程 mapping分摊；cgroup 是 charge。差异通过 Cached/Slab/PageTables/KernelStack/fault/IO/NUMA证据解释，证据不足即 `unknown`。

## 8. Evidence 与复现

Raw evidence 与 runner 脚本保留在受控本地，没有发布到 Materials。下列路径均相对于 `<local-evidence-root>`。

- `memory-samples.csv`：Host before/peak/settled/cleanup时序。
- `process-map.csv`：组件与 Sandbox进程 PID/start ticks/exe/PSS/USS/selected mappings。
- `cgroup-memory.csv`：unit/Sandbox cgroup current/peak/stat/events。
- `component-density.csv`：本报告组件矩阵的直接输入。
- `per-sandbox-distribution.json`：每 Sandbox样本与分布。
- `density-trend.json`：run-level主值、回归、CI和 residual。
- 每个 run 子目录：identity、owned/delete ledger、host/deep raw和最终资源状态。
- `community-cumulative-r1/`：第一次累计 attempt；保留 N=100 probe方法失败和精确清理。
- `community-probe-c1/`：单实例 probe接口诊断，create/probe/delete各一次。
- `community-cumulative-r2/` 与 `community-cumulative-r2-derived/`：同 run N=0/N=100原始数据、100/100 probe、派生组件/均摊表及故障清理。
- `community-cumulative-r2-current-blocker.txt`：根盘100%、Redis unhealthy、最终运行时对象0的只读快照。
- `evidence/<run-label>/`：磁盘清理后的全新Phase A、R3 preflight-only失败、600秒N=0无效包络、OOM/Redis恢复证据及最新组件观察。
- `final-live-state.txt`：最终 boot/hash、核心服务 active、Sandbox/Snapshot/shim/VMM/TAP=0及已知非 Cube failed unit。
- `validation.json`：独立轮、累计轮、诊断 probe 的 ledger/at-most-once/final-resource/JSON/CSV/secret验证。
- `SHA256SUMS`：最终 evidence文件完整性清单；文件数以清单为准。

复算命令：

```bash
python3 <local-tools-root>/analyze.py --evidence-root <local-evidence-root>
python3 <local-tools-root>/analyze_cumulative.py --run-dir <local-evidence-root>/community-cumulative-r2 --output-root <local-evidence-root>/community-cumulative-r2-derived
python3 <local-tools-root>/render_report.py --evidence-root <local-evidence-root> --host <host> --output SANDBOX_MEMORY_FOOTPRINT_REPORT.zh-CN.md
```

## 9. 指标观察方法与复现命令

本节给出报告中每类数字的直接观察入口。正式数据由 `measure.py`/`measure_cumulative.py` 用Python标准库读取相同内核接口并写入带时间戳JSONL；下面的命令用于人工单点复核。命令均为只读，不包含认证header，也不读取进程环境变量。

### 9.1 Host内存、压力、fault与NUMA

| 报告指标 | 直接来源 | 单点观察命令 |
|---|---|---|
| `MemTotal/MemAvailable/AnonPages/Cached/Mapped/Shmem/Slab/PageTables/SecPageTables/KernelStack/Dirty/Writeback` | `/proc/meminfo` | `grep -E '^(MemTotal|MemAvailable|AnonPages|Cached|Mapped|Shmem|Slab|SReclaimable|SUnreclaim|PageTables|SecPageTables|KernelStack|Dirty|Writeback):' /proc/meminfo` |
| OOM/swap/reclaim/fault | `/proc/vmstat` | `grep -E '^(oom_kill|pswpin|pswpout|pgfault|pgmajfault|pgscan_|pgsteal_|allocstall)' /proc/vmstat` |
| PSI | `/proc/pressure/{cpu,memory,io}` | `for f in /proc/pressure/{cpu,memory,io}; do echo "$f"; cat "$f"; done`；`<test-host>`对应文件不可用时明确记缺失 |
| NUMA节点 | node sysfs | `for n in /sys/devices/system/node/node[0-9]*; do cat "$n/meminfo"; cat "$n/numastat"; done` |
| threads/load/blocked | `/proc/loadavg`、`/proc/stat`、线程列表 | `cat /proc/loadavg; grep '^procs_blocked ' /proc/stat; ps -eLo tid= | wc -l` |
| IO与内核对象 | `/proc/diskstats`、`/proc/slabinfo`、sockstat | `cat /proc/diskstats; grep -E '^(xfs_|dentry |inode_cache |kmalloc-|task_struct )' /proc/slabinfo; cat /proc/net/sockstat{,6}` |

Host时间序列每2秒写入 `host-samples.jsonl`；主值使用指定phase内样本中位数，而不是单次 `free -h`。本报告的整机摊销按：

```text
(median(MemAvailable_N0) - median(MemAvailable_settled_N)) / 1024 / N
```

### 9.2 进程PSS、USS、RSS与Snapshot mapping

先用systemd取得稳定PID和cgroup，再记录 `/proc/PID/stat` 的start ticks，采样前后必须一致：

```bash
systemctl show <unit> --no-pager \
  -p MainPID -p ControlGroup -p MemoryCurrent -p MemoryPeak -p TasksCurrent
readlink /proc/<pid>/exe
awk '{print $1,$2,$10,$12,$14,$15,$20,$22}' /proc/<pid>/stat
cat /proc/<pid>/smaps_rollup
grep -E '^(Name|State|VmRSS|RssAnon|RssFile|RssShmem|VmPTE|VmSwap|Threads):' /proc/<pid>/status
cat /proc/<pid>/statm
cat /proc/<pid>/numa_maps
```

字段形成规则：

```text
PSS_KiB = smaps_rollup:Pss
USS_nonhugetlb_KiB = Private_Clean + Private_Dirty
RSS_KiB = smaps_rollup:Rss
```

Snapshot mapping不靠进程总RSS推断，而是解析 `/proc/<pid>/smaps`，只保留pathname匹配已冻结Template memory路径的VMA，并同时记录`dev/inode/perms/Pss/Shared_Clean/Shared_Dirty/Private_Clean/Private_Dirty/Anonymous`：

```bash
grep -n -A30 '<template-memory-path>' /proc/<cube-shim-pid>/smaps
stat -c 'dev=%d inode=%i size=%s mtime_epoch=%Y' <template-memory-path>
```

部署中的VMM位于 `containerd-shim-cube-rs`进程内，报告没有虚构独立 `cloud-hypervisor`进程，也没有跨进程直接相加RSS。

### 9.3 cgroup v1 memory

从 `/proc/<pid>/cgroup` 找到`memory` controller路径，再读取：

```bash
cat /proc/<pid>/cgroup
cg=/sys/fs/cgroup/memory/<resolved-path>
stat -c 'inode=%i' "$cg"
cat "$cg/memory.usage_in_bytes"
cat "$cg/memory.max_usage_in_bytes"
cat "$cg/memory.failcnt"
cat "$cg/memory.stat"
```

报告中的`cgroup current`来自`memory.usage_in_bytes`；`rss/cache/mapped_file/pgtable`来自`memory.stat`。cgroup v1共享页按charge归属且usage为近似值，所以只与PSS平行对照，不相加、不要求逐字节闭合。

### 9.4 Sandbox归属、readiness与清理

高密度时CubeAPI列表可能分页截断，因此全量集合以Master和Cubelet CLI交叉验证：

```bash
/usr/local/services/cubetoolbox/CubeMaster/bin/cubemastercli list --all -q
/usr/local/services/cubetoolbox/Cubelet/bin/cubecli cubebox ls -a -q --no-trunc
ctr -n cubens tasks ls -q
ctr -n cubens containers ls -q
for p in /sys/class/net/z*/operstate; do [ "$(cat "$p")" = up ] && echo "$p"; done
```

每个创建成功ID立即fsync写入`owned-ids.jsonl`；每个新ID只执行一次Guest probe：

```bash
/usr/local/services/cubetoolbox/Cubelet/bin/cubecli exec <owned-id> /bin/true
```

清理只对owned ledger中的精确ID发送一次 `DELETE /sandboxes/<id>`；`delete-events.jsonl`记录HTTP状态。最终要求Master、Cubelet、API、shim、task、VMM、TAP和cgroup集合回到before manifest。

### 9.5 统计与派生

```bash
python3 <local-tools-root>/analyze.py --evidence-root <local-evidence-root>
python3 <local-tools-root>/analyze_cumulative.py \
  --run-dir <local-evidence-root>/community-cumulative-rN \
  --output-root <local-evidence-root>/community-cumulative-rN-derived
```

- P50/P95使用nearest-rank：`sorted[ceil(n*p/100)-1]`。
- 组件主值先在每run settled窗口取中值，再跨成功run取中值。
- OLS、Theil-Sen和bootstrap只接受完整成功密度点；失败、未提交和无效N=0不会补值。
- `memory-samples.csv`、`process-map.csv`、`cgroup-memory.csv`分别保存Host、进程/mapping和cgroup的raw-to-derived输入。
