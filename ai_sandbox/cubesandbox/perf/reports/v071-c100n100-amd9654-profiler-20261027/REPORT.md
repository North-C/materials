# v0.7.1 · AMD 9654 · Template c100n100 启动阶段剖析（profiler 五轮）

日期：2026-10-27（运行时间 03:33–03:36 CST；bash 基线 01:53–01:55 CST）
类型与状态：实测报告。profiler 五轮正式 c100n100 全部 100/100 成功、实例归属已采用、每轮精确清理；另附同日 bash 启动的 cube-bench 五轮基线。宿主机参数未修改，未做环境 A/B。
对象与来源：CubeSandbox v0.7.1-amd64 one-click 单节点；采集工具 cubesandbox-startup-profiler 912b1ba；原始日志未发布（见[发布说明](#发布说明与文件清单)）。

## 结论与适用范围

- **单请求约 117 ms（r1–r4 客户端均值）中，最大的一段是进入 CubeMaster 之前，约 42 ms（约 36%）。** 第一个请求在客户端开始后 3.5–5 ms 就到达 Master，其余请求在之后 43–66 ms 内陆续到达，正好对应轮内时延从约 60 ms 爬升到约 140 ms。该段是估算值，无法细分到 cube-bench 建连、CubeAPI 转发或 Master 入口排队。
- **Cubelet→Shim 约 26 ms**（其中 storage 约 18–20 ms）和 **Shim 结束→Master 回复约 21 ms**（其中 `sandbox-probe` 固定约 15 ms），两段与 .90（ARM）的同口径数据基本一致。
- **VM 恢复不是常态瓶颈。** start vm→agent ready 约 18 ms，`RestoreVm` 约 14 ms；Shim 启动 VM 之前只有 0.3 ms（.90 上这一段是 12–47 ms）。
- **r5 整体抬升，原因未查明。** `RestoreVm` avg 51.5 ms，Master 到达跨度 125 ms，客户端 min 147 ms；probe、CreateContainer、Cubelet→Shim 都没有变慢。没有采集宿主机计数器，不做归因。
- 适用范围：单台 AMD 9654 节点，THP=always、NUMA balancing 开启、有共存服务，单模板，五轮。不是同条件跨硬件结论，也不是优化前后对比。

## 环境与身份

| 项 | 值 |
| --- | --- |
| 机器 | AMD 9654 x86 测试机（云主机，测试机地址未公开）：2× AMD EPYC 9654，384 线程，8 NUMA，1.5 TB；openEuler 24.03 SP3，内核 6.6.0-145.3.34.165.oe2403sp3.x86_64 |
| 内存策略 | THP `always`，defrag `madvise`，`kernel.numa_balancing=1`，`99-e2b-hugepages.conf` 预留 150418×2 MiB HugePages（测试时几乎未使用）；CPU governor `performance`，boost 开启 |
| 共存负载 | Harbor（约 10 个容器）、2 个 Java、postgres、安全代理 qaxsafed；测试期间负载约 0.04，未停止 |
| CubeSandbox | release `v0.7.1-amd64`，git_commit `31d911e430fdf8a8879bd062b8e78066c1a8e89d`，built_at 2026-09-11；PVM 关闭；`create_concurrent_limit: 100` |
| 组件哈希（sha256 前 16 位，运行中二进制） | cubemaster `6045a96ea76df0c4`，cubelet `594a4d8c68395d0a`，cube-api `9bafe4e0702b2014`，containerd-shim-cube-rs `d72fa20dfc78c81e`，cube-runtime `8676d2a1a1cd79c4`；VMM 内嵌在 shim 中，guest agent 版本未记录 |
| 模板 | `tpl-947123cfa84540d68f7c5933`，READY；镜像 `cube-sandbox/sandbox-code@sha256:743d264fad8c9dc9a49f07e931166d24d025363360ae770ca4b70e3f19540944`；规格 `cpu=2000m,mem=2000Mi`；可写层大小和探针配置未记录 |
| runner | cube-perf-suite `dc271ba6a10e308de7e010e058baca41c1800496` 中的 `examples/cube-bench`，Go 1.25.14 构建，二进制 sha256 `8f68ae5c690d9ac8af82b7777e23bda190e1baa97717423e8fef38afd9de8c60` |
| profiler | cubesandbox-startup-profiler 912b1ba（tar sha256 `19315d4e873653567b9f9fe35567fb383637229ca50ff1fed1c6bd1521c5e840`），Python 3.11.6，Node 20.18.2 |

## 方法

**profiler 五轮**（[驱动脚本](scripts/run-profiler-5rounds.sh)，root 运行以读取 `/data/log`）：每轮执行 `python3 capture_100.py --config capture100.local.json --output-root <dir>/rN`。配置为 `warmup: 3`、`metrics_url: http://127.0.0.1:9998/v1/metrics`、`cubemastercli.exclusive_template: true`。工具内部依次运行：

```sh
cube-bench -c 1 -n 3 -w 0 -m create-only -no-tui -t <template> -o <run>/warmup/benchmark.raw.json      # 独立进程预热
cube-bench -c 100 -n 100 -w 0 -m create-only -no-tui -t <template> -o <run>/capture/startup-latency/benchmark.raw.json
```

- 每轮前导出 `CUBE_PERF_RUN_ID`，cube-bench 会把它写入创建请求的 metadata `perf_suite_run`。轮后按该标签 `DELETE` 本轮 103 个实例（全部返回 204），确认 `GET /sandboxes` 为 0 后再等 30 s。
- 5 轮的 CLI 归属均为“已采用”：formal=100、warmup=0、unknown_phase=0，状态为 `declared`（依据模板独占声明和前后快照推定，不是客户端 seq 与实例的逐条映射）。
- 注意：cube-bench 由 Python（`capture_100.py` → subprocess）启动。

**逐请求配对**（[pair_host_boundaries.py](scripts/pair_host_boundaries.py)，沿用 .90 2026-10-24 的脚本，只改了目录布局）：用 Master `CreateSandbox` 的 requestID 关联 Cubelet `RunCubeSandboxRequest`，再用 Master 回复中的 sandbox_id 关联 Shim 时间线。5 轮均 100/100 配对，无缺失、重复或倒序。全部是同一宿主机墙钟的日志边界，包含执行和等待。

**进入 Master 之前的估算**（[derive.py](scripts/derive.py)）：CubeAPI 只在完成时写 `sandbox.created`，没有请求到达日志。以“最后一条 `sandbox.created` − `summary.total_time_s`”近似客户端开始时刻 t0，再计算各请求 Master 开始日志相对 t0 的偏移。

**bash 基线**（[驱动脚本](scripts/run-bash-baseline-5rounds.sh)）：bash 直接运行 `cube-bench -c 100 -n 100 -w 3 -m create-only --no-tui -o roundN.json`，同进程预热 3 次，按标签清理，每轮间隔 30 s。

## 总体结果

profiler 正式轮（[round-summary.csv](derived/round-summary.csv)，单位 ms）：

| 轮次 | 整轮 | 客户端 avg | min | P50 | P95 | P99 | max | 成功 |
| :-: | --: | --: | --: | --: | --: | --: | --: | :-: |
| r1 | 152.0 | 111.8 | 67.3 | 120.8 | 145.8 | 149.1 | 150.6 | 100/100 |
| r2 | 169.8 | 129.2 | 71.0 | 142.6 | 162.4 | 163.9 | 169.7 | 100/100 |
| r3 | 162.2 | 117.7 | 74.9 | 125.3 | 151.9 | 157.4 | 160.7 | 100/100 |
| r4 | 147.6 | 109.8 | 83.5 | 106.8 | 140.3 | 146.4 | 147.1 | 100/100 |
| **r5** | **208.0** | **168.2** | **147.4** | 155.4 | 198.4 | 200.2 | 205.2 | 100/100 |

bash 基线（[bash-baseline/](bash-baseline/)）：五轮客户端 avg 为 111.1 / 126.0 / 113.3 / 96.1 / 98.7 ms，P99 为 144.0 / 162.5 / 153.3 / 133.3 / 140.9 ms，500/500 成功。profiler r1–r4 的 avg 与之区间重叠。两者预热方式不同（独立进程 vs 同进程），不作为重复样本合并。

## 逐请求相邻区间

区间互不重叠，可以在同一请求内求和；均值之和不等于整轮时间。来源：[paired-host-boundaries.json](derived/paired-host-boundaries.json)、[pre-master-estimate.csv](derived/pre-master-estimate.csv)。

| 区间平均值 ms | r1 | r2 | r3 | r4 | r1–r4 均值 | r5 |
| --- | --: | --: | --: | --: | --: | --: |
| ① 客户端开始→Master 开始（估算） | 38.9 | 49.5 | 45.6 | 32.4 | **41.6** | 57.7 |
| ② Master 开始→Cubelet 开始 | 2.9 | 6.9 | 5.1 | 5.6 | 5.1 | 5.0 |
| ③ Cubelet 开始→Shim 开始 | 25.2 | 26.5 | 26.7 | 25.6 | **26.0** | 20.8 |
| ④ Shim 开始→start vm | 0.3 | 0.3 | 0.3 | 0.3 | 0.3 | 0.3 |
| ⑤ start vm→agent ready | 17.9 | 16.1 | 16.3 | 22.6 | **18.2** | **55.7** |
| ⑥ agent ready→Shim 结束 | 9.0 | 9.9 | 10.1 | 10.0 | 9.8 | 10.2 |
| ⑦ Shim 结束→Master 回复 | 22.1 | 22.4 | 20.2 | 20.1 | **21.2** | 20.1 |
| Master 窗口（②–⑦） | 77.3 | 82.0 | 78.6 | 84.2 | 80.5 | 112.1 |
| ⑧ Master 回复→CubeAPI `sandbox.created` | 0.4 | 0.2 | 0.3 | 0.2 | 0.3 | 0.2 |
| Master 开始日志跨度 | 54.7 | 66.2 | 61.4 | 42.7 | — | 124.7 |

①+Master 窗口（约 122 ms）与客户端均值（约 117 ms）只能近似对上，差异来自 t0 估算。

## 组件内阶段

来源：各轮 `analysis/stage-latency.csv`，formal 群体；汇总见 [stage-summary.csv](derived/stage-summary.csv)。父子阶段互相包含，不能相加。

| 组件.阶段 | 父阶段 | r1–r4 avg | r1–r4 P95 | r5 avg | r5 P95 |
| --- | --- | --: | --: | --: | --: |
| CubeMaster.cube-e2e | api.create | 76.8–83.7 | 94–99 | 111.7 | 150 |
| Cubelet.cubebox-service | master.cube-e2e | 68.3–75.6 | 85–90 | 103.9 | 144.7 |
| ├ service_outside_cubebox（配对残差，主要是 storage） | cubebox-service | 16.8–18.5 | 40–45 | 13.6 | 22.3 |
| └ Cubelet.cubebox | cubebox-service | 50.7–58.8 | 62–84 | 90.3 | 136.4 |
| 　├ sandbox-start ⊃ sandbox-create | cubebox | 32.5–39.6 | 43–66 | 72.3 | 118.6 |
| 　│ └ CubeShim.CreatePodSandbox | sandbox-create | 25.7–32.5 | 37–60 | 65.6 | 112 |
| 　│ 　├ RestoreVm | CreatePodSandbox | 11.7–18.0 | 23–46 | **51.5** | **98** |
| 　│ 　├ CreateContainer | CreatePodSandbox | 4.0–4.5 | 5–8 | 4.1 | 5 |
| 　│ 　├ ResetVm | CreatePodSandbox | 2.9–3.5 | 5–7 | 3.8 | 7 |
| 　│ 　├ LaunchVmm | CreatePodSandbox | 0.9–1.4 | 1–4 | 1.0 | 1 |
| 　│ 　└ CreateSandbox | CreatePodSandbox | 0.6–0.8 | 1–2 | 0.7 | 1 |
| 　├ sandbox-probe | cubebox | 14.4–15.9 | 17–21 | 15.0 | 16.9 |
| 　└ cubebox 其余残差 | cubebox | 2.4–3.2 | 7–14 | 1.9 | 3.4 |

- Cubelet `storage` 只在超过阈值时记录（覆盖 71–79/100），`create-sandbox-metadata` 只覆盖 11–16/100，表中这两项的均值都是被记录样本的条件均值。
- `sandbox-probe` 每轮都在 14.4–15.9 ms，r5 也一样，形态像固定轮询间隔。这一点是推断，未核对 probe 实现。

## 与 .90 的对照

.90 数据来自 2026-10-24 同一 profiler 的三轮采集（ARM，K2/86f6d9b，T1 模板，THP never）。原报告未归档到本仓库，这里只引用其中的配对区间均值。两台机器的架构、版本、模板和内存策略都不同，**只对照形态，不作硬件结论**。同一台 AMD 9654 在 2026-10-19 的阶段汇总见 [950 与 AMD 9654 分级对比](../c100n100-950-amd9654-stage-comparison-20261019/README.md)（API 单请求均值 112.4 ms），但两次是否为同一部署未核实。

| 区间 avg ms | .90 r1–r3 | AMD 9654 r1–r4 |
| --- | --- | --- |
| Master→Cubelet | 3.4–6.3 | 2.9–6.9 |
| Cubelet→Shim | 22.7–31.4 | 25.2–26.7 |
| Shim 开始→start vm | 11.9–47.3 | 0.3 |
| start vm→agent ready | 20.4–23.4 | 16.1–22.6 |
| agent ready→Shim 结束 | 6.0–7.3 | 9.0–10.1 |
| Shim 结束→Master 回复 | 22.0–23.1 | 20.1–22.4 |
| Master 开始日志跨度 | 76.8–106.2 | 42.7–66.2 |

## 后续方向（未执行）

1. 在 CubeAPI 记录请求到达和转发时间，拆分 ① 的约 42 ms：cube-bench 新建约 100 个连接、CubeAPI→Master 连接池或并发上限、Master 入口排队。
2. 细分 Cubelet storage（rootfs/可写层准备），确认有无锁或串行。
3. 核对 probe 的首次探测时机和轮询间隔。
4. 在授权前提下对 THP 和 NUMA balancing 做一次只改一个因素的 A/B，同时采集 `/proc/vmstat`（compact_*、thp_*、numa_*）和 `perf sched`，判断 r5 类尖峰是否来自内存管理。

## 限制

- cube-bench 由 Python 父进程启动。.90 上发现过 Python 祖先导致 40–80 ms 的 Go STW；本机 r1–r4 与 bash 基线区间重叠，没看到明显影响，但五轮样本不足以排除。r5 的抬升发生在服务端 RestoreVm，不能单用这一点解释。
- profiler 是独立进程预热加正式 w0，与同进程 `-w 3` 不完全等价。
- ① 是基于 t0 近似的估算。组件阶段是群体统计，不能与客户端样本逐条对应。
- 单机五轮，共存负载不受控；模板可写层和探针配置未记录。

## 发布说明与文件清单

本目录只发布派生数据和 profiler 分析输出，不包含原始日志。原始采集（Cubelet/Shim/Master/VMM/CubeAPI 日志增量、metrics 快照、cubemastercli 清单、console 输出）含测试机公网地址、主机名和请求内容，未公开；它们只保存在测试机和作者本地，属于历史来源，其他读者无法访问。因此：

- 未公开原始日志，所以无法从本目录重跑 `pair_host_boundaries.py` 和 `derive.py` 的 pre-master 部分；`round-summary.csv` 和 `stage-summary.csv` 可以由 `rounds/*/analysis` 中已发布的文件核对。
- `rounds/rN/analysis/` 删除了 `inventory-evidence/`（含节点地址），其余文件与原件字节一致。因此 `report.html` 和 `REPORT.md` 中指向 `inventory-evidence` 的各 1 处链接失效。
- 两个驱动脚本中的 API key 占位值替换为 `<redacted>`（部署未启用鉴权，原值只是占位字符串）。bash 基线的终端输出（含主机名）未发布，只发布 cube-bench JSON 和进度日志。

| 路径 | 内容 |
| --- | --- |
| `rounds/rN/analysis/` | 各轮 profiler 输出：`report.html`、`timeline.html`、`stage-latency.csv`、`analysis.json`、`benchmark-inputs/` 等；对应 run ID 见 [RUN-IDS.txt](rounds/RUN-IDS.txt) |
| `derived/round-summary.csv` | 客户端逐轮统计 |
| `derived/stage-summary.csv` | formal 阶段逐轮 avg/P95/覆盖 |
| `derived/pre-master-estimate.csv` | 进入 Master 之前的估算与 Master→CubeAPI 返回开销 |
| `derived/paired-host-boundaries.json` | 逐请求配对边界（500 行） |
| `derived/profiler-progress.log` | 每轮开始、退出码、删除数量（103×204）和清理结果 |
| `bash-baseline/` | bash 基线五轮 cube-bench JSON 与进度日志 |
| `scripts/` | 配对、派生脚本和两个驱动脚本（会在测试机上创建并删除实例） |
| `SHA256SUMS` | 本目录发布文件的校验值（只证明发布副本字节） |

```sh
shasum -a 256 -c SHA256SUMS
```

报告查看入口：[r1 report.html](rounds/r1/analysis/report.html) · [r5 report.html](rounds/r5/analysis/report.html) · [r5 timeline.html](rounds/r5/analysis/timeline.html)。
