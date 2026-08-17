# openEuler agent-browser NUMA-3 内存容量压缩实验报告

## 1. 实验结论

在本实验的固定浏览器负载下，4 GiB 基线压缩 50% 和 60% 后仍处于稳定区：
三次重复均为 5/5 成功，未发生 cgroup OOM kill，平均延迟与基线差异在
2% 以内。压缩 70%（剩余 1229 MiB）是明确拐点：三次运行均发生任务失败和
2--3 次子进程 OOM kill，任务成功率降至 69.23%，吞吐降至基线的约 42%。

压缩 80%（剩余 819 MiB）不是比 70% 更稳定。虽然其中两次正式测试为 5/5
成功，但每次均发生 9 次 cgroup OOM kill，浏览器通过杀死或回收子进程缩小了
存活工作集；预热或正式阶段仍有快照失败。该非单调结果是失效恢复路径，不应
解释为 819 MiB 比 1229 MiB 性能更好。

## 2. 实验对象与环境

| 项目 | 配置 |
|---|---|
| 测试主机 | `root@192.168.25.65` |
| OS / 内核 | openEuler 24.03 LTS-SP3 / `6.6.0-sbench-irqbypass-xarray-v2-aprmask` |
| CPU | Kunpeng 950 7592C，384 逻辑 CPU，4 NUMA 节点 |
| Docker | 18.09.0，arm64 |
| 仓库提交 | `d28fb24f5ab31bdf4223ea0243b24fd34bb49e38` |
| 镜像 | `openeuler-agent-browser:24.03-lts-sp3-linuxarm64` |
| 镜像 ID | `sha256:f612a48773bf7b771968aca9bd4aa183f9bde3e7ad38988d998660c6dcf36f04` |
| CPU 约束 | 2 vCPU，`cpuset-cpus=289,291`，分别属于物理核 144、145 |
| NUMA 约束 | `cpuset-mems=3`；NUMA-3 CPU 范围 288--383 |
| Swap | 主机无 swap；容器 `memory-swap` 与 `memory` 设置为相同值 |

完整主机信息见 `environment.txt`，每次容器实际资源设置见
`raw/cap*-resources.txt`，cgroup 前后快照见 `raw/cap*-cgroup.txt`。

## 3. 测试方法

测试流程依据仓库 `docs/bench-core-usage-zh.md` 及现有 browser 脚本：每个样本
使用全新容器，依次执行 create-only、资源绑定、9 页预热、正式 round-robin
任务、指标停止和容器清理。每个容量条件独立重复三次，避免浏览器标签页状态在
样本间累积。

正式测试配置为 160 秒上限、最多 5 轮、每轮 1 个任务、轮间隔 5 秒。测试页
使用实验目录内 10 个确定性本地页面：每页包含 1200 个 DOM 卡片，并分配、触碰
24 MiB JavaScript 数组；其中 9 页用于预热，`Benchmark.html` 用于正式测试。
采用本地页面是因为仓库默认的 `192.168.110.10:8080` 页面服务在测试主机不可达。
因此，本报告衡量的是该固定负载，不能与公网页面测试直接横向比较。

原始 browser 镜像是最小化镜像，只包含 `agent-browser`，没有默认配置所检查的
OpenClaw 和 llama 端口。实验临时将就绪检查改为执行
`agent-browser --version`；原文件和实验补丁分别保存在
`compat/_ready.py.original` 与 `compat/_ready.py`。bench-core 报告中的
“Ports Ready”文字是未同步修改的展示文本，实际检查的是 CLI。测试结束后远端
仓库恢复原文件。

容量压缩定义为从 4096 MiB 基线移除的比例：

| 压缩比例 | 容器可用内存 |
|---:|---:|
| 0% | 4096 MiB |
| 50% | 2048 MiB |
| 60% | 1638 MiB |
| 70% | 1229 MiB |
| 80% | 819 MiB |

## 4. 指标采集与口径

容器 CPU、绑定 CPU 利用率、memory usage/cache/working set/RSS、PID 数和
`memory.numa_stat` 约每秒采集一次。Docker CPU 的 100% 表示一个逻辑 CPU；
本实验容器上限为 200%。OOM 以 cgroup v1 `memory.oom_control` 的
`oom_kill` 增量为准。Docker `.State.OOMKilled=false` 只说明容器 init 进程
未被杀死，不能排除 Chromium 子进程 OOM。

NUMA-3 内存带宽由 SCCL9 的 12 个 HiSilicon DDRC PMU 同时采集，每秒汇总
`flux_rd` 和 `flux_wr`。按照 openEuler libkperf 的 HiSilicon DDRC 计算口径，
带宽为 `flux * 32 / interval / 1e9` GB/s。SCCL9 PMU 的 `cpumask` 为 288，
对应 NUMA-3。该值是节点级 uncore 带宽，无法按 cgroup 归因，可能包含同节点
其他进程流量。计算依据：

- https://gitee.com/openeuler/libkperf/blob/4862b2f0b4890027c3145cf043953b6609c15282/docs/Details.md
- https://www.kernel.org/doc/html/v5.15/admin-guide/perf/hisi-pmu.html

平均延迟只包含成功任务；失败任务的代价通过成功率和按正式窗口计算的吞吐体现。

## 5. 基准与容量压缩结果

| 压缩 | 内存 | 全成功运行 | 任务成功 | 平均延迟 ms | 相对基线 | 吞吐 task/s | CPU 平均 | WS 平均/峰值 MiB | DDR 平均/P95 GB/s | OOM kill/运行 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0% | 4096 | 3/3 | 15/15 | 2794.3 | 0.0% | 0.1282 | 15.59% | 1293.7 / 1456.0 | 0.512 / 1.225 | 0 / 0 / 0 |
| 50% | 2048 | 3/3 | 15/15 | 2739.0 | -2.0% | 0.1292 | 16.06% | 1292.5 / 1424.7 | 0.512 / 1.214 | 0 / 0 / 0 |
| 60% | 1638 | 3/3 | 15/15 | 2762.0 | -1.2% | 0.1289 | 16.48% | 1297.7 / 1436.4 | 0.536 / 1.257 | 0 / 0 / 0 |
| 70% | 1229 | 0/3 | 9/13 | 5622.8 | +101.2% | 0.0541 | 9.12% | 1084.7 / 1229.0 | 0.391 / 0.951 | 2 / 3 / 3 |
| 80% | 819 | 2/3 | 14/15 | 3256.5 | +16.5% | 0.1040 | 18.34% | 742.2 / 819.0 | 0.476 / 1.212 | 9 / 9 / 9 |

基线正式工作集峰值达到 1456 MiB，因此 1638 MiB 尚有约 182 MiB 余量；
1229 MiB 和 819 MiB 均低于该工作集需求。70% 条件的第一次运行只有 1/3
任务成功，唯一成功任务耗时 25.38 秒；另外两次均为 4/5 成功，并出现 CDP
`Accessibility.getFullAXTree` 或开新标签超时。三次一致的任务失效和 OOM
证实 1229 MiB 已越过稳定边界。

80% 条件在预热阶段即累计 5--6 次 OOM kill，正式阶段结束时均累计到 9 次。
被杀的 renderer/子进程释放了内存，使后续新标签有时可以完成，这解释了正式
成功率高于 70% 的非单调现象。对长期服务而言，这仍代表会话或后台标签页状态
丢失，不能作为可用容量点。

DDR 总带宽在 0%、50%、60% 三档分别为 0.512、0.512、0.536 GB/s，差异较小。
70% 时降到 0.391 GB/s，而不是随压力升高；原因是任务大量时间处于超时、回收
和低 CPU 活跃状态。80% 为 0.476 GB/s，但包含频繁子进程重启/回收。由于 PMU
是节点级且主机并非独占，这些数据适合描述本次运行，不应作为容器独占带宽值。

## 6. 数据文件与复现

- `../benchmark_results.csv`：统一逐运行 CSV，现含原 Go 基线和本实验 15 行；
  `bandwidth_compression_pct` 本阶段均为 0。
- `browser-capacity-summary.csv`：按容量条件汇总。
- `browser-runs.json`：每次运行的完整派生指标和状态。
- `raw/`：bench、预热、容器遥测、DDRC、cgroup 和资源绑定原始数据。
- `reports/`：bench-core 原始性能报告。
- `analyze_browser_results.py`：从原始数据重新生成 JSON、汇总 CSV 和统一 CSV。
- `run_capacity_matrix.sh`、`run_capacity_condition.sh`：可断点续跑的测试流程。

统一 CSV 以 `experiment_id` 为稳定唯一键。新的实验 ID 追加为新行；同一实验重新
汇总时替换该 ID 的行，避免重复。字段定义见 `../benchmark_results-schema.md`。

## 7. 局限性与下一阶段

每次正式测试最多只有 5 个任务，样本量适合定位容量拐点，不足以给出生产 SLO
置信区间。实验按容量从高到低顺序执行，没有随机交错；NUMA-3 DDRC 是共享节点
计数器。少量页面在容器启动、应用 `cpuset-mems=3` 之前分配，最终正式窗口的
NUMA-3 本地率按条件为 98.79%--99.97%。

本阶段只改变内存容量，未施加带宽限速。CSV 已预留
`bandwidth_compression_pct`；后续内存带宽压缩实验应保持镜像、页面、CPU、
4096 MiB 容量和重复次数不变，仅改变一个带宽变量，并继续记录节点背景带宽，
以免把共享 NUMA 流量误判为容器自身流量。
