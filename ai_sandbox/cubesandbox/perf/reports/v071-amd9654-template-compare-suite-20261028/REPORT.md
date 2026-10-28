# v0.7.1 · AMD 9654 c100n100：另一用户的模板 peer-final-check vs 重建原模板 · 同组件对照与 profiler 瓶颈

日期：2026-10-28（19:3x–22:00 CST）。类型：实测 + 诊断。**状态：c100n100 两模板各五轮完成；重建原模板上 cube-perf-bench 全部可执行项已完成，统一汇总见 [SUITE-REPORT.md](SUITE-REPORT.md)。**

## 结论

- **模板是主因**：同一套组件（下表 SHA 全部一致）、同一门禁与驱动，
  - peer-final-check（`tpl-8a157507644a426f9e7a6326`）：c100n100 整轮中位 **934.1 ms**（930.4–940.4），19:56 复测中位 **931.7 ms**（924.6–934.8）；
  - 重建原模板（`tpl-4feed5ee40f648a7869a6579`，参数同已删除的 `tpl-3d73a659…`）：中位 **127.4 ms**（125.7–133.3）。
  - 两组区间完全不重叠，peer-final-check 约为重建原模板的 7.3 倍（+633%）。判定：**观察到明显差异，且归因于模板**（组件、内核、主机状态相同；模板之间多个参数同时不同，不能归因于单个参数）。
- **瓶颈位置**（profiler 45df527，peer-final-check 两轮 r1/r2）：每个实例恢复后约 750 ms 的 guest 侧停顿。
  - CubeShim `ResetVm` 呈双峰：min 8–9 ms、p50 760–761 ms、avg 406–428 ms（103 个实例）。约一半实例在等 agent ready。
  - 其余实例的停顿出现在 `CreateContainer`：p50 4 ms，p95 751 ms。
  - `RestoreVm` 只有 8 ms，CubeMaster 约 5 ms，Cubelet 存储 25–37 ms，都不是瓶颈。
- **settle gate 不是原因**：两个模板的构建日志都是 `settle-gate: skipped`，但重建原模板很快。
- **模板差异（候选原因，未单独验证）**：

  | 参数 | peer-final-check | 重建原模板 |
  | --- | --- | --- |
  | 内存 | 2000Mi | 2048Mi |
  | 就绪探针 | **无** | `/health`:49999，周期 500 ms |
  | `com.exposed_ports` | 无 | 49999 |
  | 可写层 / system disk | 20Gi / 20 | 1G / 1 |
  | storage backend 注解 | 无 | xfs |
  | rootfs artifact | `rfs-1ab81e50…` | `rfs-79da86b8…` |
  | 注解 `envd.version` | 0.5.11 | 无 |

  **推测**：没有就绪探针时，模板快照可能在 guest 内服务就绪之前就已截取，导致每次恢复后仍要等约 750 ms。这一点没有对照实验证实。另一用户的 `tpl-eafc8a29…`（peer-isnotfc-bench-1028）与 peer-final-check 的 spec fingerprint 和 rootfs artifact 完全相同，本次未测。

- **snapshot create c10（重建原模板）**：5 次正式调用的 wall_avg 中位 **93.6 ms**（90.9–97.4），单快照摊销 per_avg 9.1–9.7 ms。只在一个模板上测过，没有对照组，**只作描述，不判定优化效果**。
- **startup c50n500（重建原模板）**：五轮整轮中位 **657.7 ms**（638.3–682.2），2500/2500 成功，客户端 avg 中位 63.0 ms。同样只作描述。

## 被测对象与基线

| 项 | 值（三组相同） |
| --- | --- |
| 部署 | 另一用户于 10-28 19:10 CST 重新部署的 BoostKit v0.7.1；源码 HEAD `2babb6f7405677c04b7fed1563c6a5d53a8e771b`，工作树干净 |
| Cubelet / CubeMaster | `506b8a83…` / `68dd0cef…`，均为 `v0.7.1 (2babb6f7) built 2026-10-28T10:12:08Z` |
| 运行中 shim（`component_versions/cube-shim/v0.7.1/bin`） | containerd-shim-cube-rs `2153cb46…`、cube-runtime `c8875540…`；vmm.log 版本行为 `v0.7.1 (2babb6f7…) built 2026-10-22T13`，见 [vmm-version-sequence.txt](raw/results-origtpl-2021/vmm-version-sequence.txt) |
| `cube-shim/bin` 副本（不在运行路径） | `425c8e94…` / `0f533118…` |
| conf.yaml / config.toml | `5cb8ed03…`（`dirty_log: true`）/ `54b93a53…` |
| 内核 / 主机 | 6.6.0，boot_id `d95db03f…`；2×EPYC 9654；THP always，numa_balancing 1，HugePages 100352 预留未用 |
| 补丁矩阵 | 本次没有改变任何组件或开关，处理变量只有模板；BoostKit 2babb6f7 已编入，`dirty_log` 配置开启（实际作用未单独证实） |

每轮门禁前读取 7 个文件的 SHA：results 10 份、rerun 11 份、origtpl 8 份，全部一致（门禁 JSON 未公开，结论见各 `run.log`）。

**模板**：

- peer-final-check：另一用户在 19:21 构建，2000m / 2000Mi。runner 要求 2048Mi，所以用 runner 的本地副本 `cube-perf-bench-2000mi`（只把第 253–254 行模板内存检查的 2048Mi 改为 2000Mi；runner 不在公开仓库，副本未发布）。
- 重建原模板：原 `tpl-3d73a659…` 已被删除（返回 template not found）。20:20 按原参数重建：sandbox-code:isnotfc-20261022-amd64@sha256:801e4703…，2000m / 2048Mi，1G 可写层，xfs，探针 49999 `/health`。请求与提交回执见 [template-rebuild-20261028/](raw/template-rebuild-20261028/)。
- 三个模板的完整 create request 见 [template-info/](raw/template-info/)。下载 URL 的查询串已删去，`cube.master.rootfs.artifact.token` 替换为 `[REDACTED]`，地址替换为 `host-lan-ip`。

**工具**：cube-perf-bench community-native（`6b577a3e…`），cube-bench `3614d21c…`，`CPB_NO_TUI=1`，由 bash 启动，每次内部 `-w 3`。

## 方法

- 每组：1 次外部热身（排除）+ 5 次正式。
- 每次运行前门禁要求：库存为空、TAP ≥600 Ready、无冲突进程、load1 ≤4。
- 每次运行后只删除本模板、本轮开始后创建的实例，并确认库存归零。
- CubeAPI 窗口审计确认窗口内没有外部创建。
- 指标：`summary.total_time_s × 1000`，即 100 个并发创建的整轮耗时（ms，越低越好），不是单实例延迟。

## 结果（ms）

| 轮 | peer-final-check 19:3x | peer-final-check 复测 19:56 | 重建原模板 20:21 |
| --- | --- | --- | --- |
| 热身（排除） | 932.7 | 935.4 | 137.9 |
| 1 | 934.5 | 932.8 | 125.7 |
| 2 | 930.4 | 931.7 | 127.4 |
| 3 | 934.1 | 930.6 | 126.7 |
| 4 | 933.0 | 934.8 | 130.5 |
| 5 | 940.4 | 924.6 | 133.3 |
| **中位（min–max）** | **934.1（930.4–940.4）** | **931.7（924.6–934.8）** | **127.4（125.7–133.3）** |
| 客户端 avg（5 轮范围） | 628.5–681.1 | 627.5–700.2 | 87.8–97.3 |
| 客户端 p50 / p95（5 轮范围） | 825.0–840.9 / 913.3–923.4 | 821.3–845.5 / 912.8–921.3 | 86.6–102.2 / 116.0–122.8 |
| 成功 / 错误 | 500/0 | 500/0 | 500/0 |
| 窗口外部创建 | 0 | 0 | 0 |
| 测前 load1 | 2.88–3.77 | 2.30–2.67 | 1.86–3.93 |

- 重建原模板对 peer-final-check（取复测中位）：127.4 / 931.7 = 0.137，即 -86.3%。
- 与历史数据的关系（只作描述，不计算收益）：10-27 夜间 BoostKit（2babb6f7 原生构建、原模板 `tpl-3d73a659…`、无外部 VM）为 119.8 ms（115.7–128.9）。本次组件是另一用户 10-28 的重新构建，模板是重建版本，条件不同。

## snapshot create c10（重建原模板，20:54–20:58 CST）

- 用户 20:5x 指示：在原模板上继续测 snapshot create 10 并发。
- 组件：7 个文件的 SHA 与上面 c100 组完全相同（7 份门禁一致），vmm.log 版本行仍为 2babb6f7。
- 用法：上游 `bench_snapshot_concurrency.py -c 10 -n 5`（社区源码 31d911e，经 cube-perf-bench `snapshot-c10`）。
  - 每次调用先建 10 个沙箱，并发调用 `create_snapshot()`，再删除快照。
  - 每次调用 = 1 轮内部预热 + 5 轮正式。脚本输出 5 轮的 wall_avg / min / p95 / max 和单快照摊销 per_avg。
  - 本次共 1 次外部热身调用（排除）+ 5 次正式调用，每次调用的 wall_avg 记作一个样本。
- 指标：wall = 从发起 10 个并发 create_snapshot 到全部返回的耗时（ms，越低越好）；per_avg = wall / 10。不含建沙箱时间。
- 门禁、清理与审计同 c100：
  - 每次调用前后对比 `/snapshots` 列表，12 份完全一致。主机上原有的他人快照不受影响，本测试创建的快照都已由脚本删除。
  - 脚本会自己删沙箱，`cleanup.json` 显示没有需要补删的实例。
  - CubeAPI 窗口内每次调用 60 个创建（6 轮 × 10），外部创建 0。
  - 测前 load1 2.20–2.71。

| 调用 | wall_avg | wall_min | wall_p95 | wall_max | per_avg |
| --- | --- | --- | --- | --- | --- |
| 热身（排除） | 96.8 | 91.6 | 103.7 | 103.7 | 9.7 |
| 1 | 97.4 | 93.7 | 102.0 | 102.0 | 9.7 |
| 2 | 90.9 | 88.4 | 95.5 | 95.5 | 9.1 |
| 3 | 92.8 | 90.5 | 94.4 | 94.4 | 9.3 |
| 4 | 93.6 | 91.3 | 97.0 | 97.0 | 9.4 |
| 5 | 96.0 | 90.8 | 99.9 | 99.9 | 9.6 |
| **中位（min–max）** | **93.6（90.9–97.4）** | | | | 9.4（9.1–9.7） |

- 上游脚本中 p95 只有 5 个样本，等于 max，所以 wall_p95 与 wall_max 相同。
- 历史数值只作描述，不计算收益：10-27 夜间单次调用，BoostKit 原生构建为 92.4 ms，社区为 97.2 ms，模板是已删除的 `tpl-3d73a659`，组件构建不同。
- 证据：[results-origtpl-snap10-2055/](raw/results-origtpl-snap10-2055/)。每次调用的 `stdout.log`、`invocation.txt`、`cleanup.json`，以及 `windows.tsv`、`host-load.tsv`、`window-audit.txt`。驱动是 [tools/run-origtpl-snap10.sh](raw/tools/run-origtpl-snap10.sh)。

## startup c50n500（重建原模板，21:01–21:08 CST）

- 用户 21:00 指示测一版 c50n500。组件 SHA 与 c100 组相同（15 份门禁一致），vmm.log 版本行仍为 2babb6f7。
- 用法：cube-perf-bench `startup-c50n500`，即 cube-bench `-c 50 -n 500 -w 3 -m create-only`。
  - 每轮 50 并发、共创建 500 个实例，测完后统一删除。
  - 1 次外部热身（排除）+ 5 次正式。
- 指标：
  - 整轮 = `summary.total_time_s × 1000`，500 个创建从开始到全部完成的耗时（ms，越低越好）。
  - 客户端时延 = 单个 create 请求的 avg / p50 / p95 / p99 / max。
- 门禁、清理与审计：
  - 每轮 503 个本模板创建（含 3 个内部预热），外部创建 0，删除后库存为 0。
  - 每轮之间 load1 常在 4 附近，门禁按规则每 30 s 重试：第 1–3 轮各重试 1 次，第 4 轮 3 次，第 5 轮 2 次，之后放行。
  - 放行时 load1 为 3.28–3.96，比 c100 组（1.86–3.93）高，主要来自 Cubelet/CubeMaster 消化上一轮 500 个实例的删除。

| 轮 | 整轮 | 成功/错误 | avg | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 热身（排除） | 649.0 | 500/0 | 62.2 | 60.9 | 76.9 | 93.0 | 94.8 |
| 1 | 665.3 | 500/0 | 63.4 | 61.9 | 78.0 | 85.0 | 86.0 |
| 2 | 638.3 | 500/0 | 60.8 | 59.2 | 75.1 | 86.1 | 88.9 |
| 3 | 657.7 | 500/0 | 63.0 | 61.8 | 77.3 | 89.5 | 91.2 |
| 4 | 643.3 | 500/0 | 61.9 | 60.6 | 72.9 | 88.2 | 90.0 |
| 5 | 682.2 | 500/0 | 65.3 | 62.3 | 96.7 | 102.0 | 104.1 |
| **中位（min–max）** | **657.7（638.3–682.2）** | 2500/0 | 63.0（60.8–65.3） | 61.8（59.2–62.3） | 77.3（72.9–96.7） | 88.2（85.0–102.0） | |

- 第 5 轮 p95 为 96.7 ms，其余四轮在 72.9–78.0 之间，原因未查。
- 历史数值只作描述，不计算收益：10-27 夜间 BoostKit 单次调用的整轮 658.3 ms、avg 62.9、p95 75.8，社区 avg 62.3、p95 79.5。模板已删除，组件构建也不同。
- 证据：[results-origtpl-c50-2101/](raw/results-origtpl-c50-2101/)，驱动是 [tools/run-origtpl-c50.sh](raw/tools/run-origtpl-c50.sh)。

## profiler 诊断（peer-final-check）

- 工具 cube-startup-profiler `45df527`，capture100 配置，exclusive_template，warmup 3。两轮：r1 962.3 ms，r2 936.2 ms，均 100/100。
- 原计划 5 轮，按用户 19:56 的指示在 r2 之后中止（[progress.log](raw/profiler/progress.log)）。
- 两轮报告：[r1 report.html](raw/profiler/r1/20261028T115207Z-478b04de/analysis/report.html)，[r2 report.html](raw/profiler/r2/20261028T115415Z-8c7c5d04/analysis/report.html)。阶段表见各自的 `analysis/stage-latency.csv`。
- cube-bench `3614d21c` 不打 perf_suite 标记，所以 Shim 阶段归在 `unknown_phase`，含 3 个预热实例，共 103 个。
- 限制：profiler 经 Python 启动 cube-bench，已知会给 Go 带来 STW 风险。但它的整轮耗时与 bash 计时组一致（约 930–960 ms），所以不影响瓶颈定位。r1/r2 不计入五轮计时样本。

| 阶段（103 实例） | r1 avg / p50 / p95 / max | r2 avg / p50 / p95 / max |
| --- | --- | --- |
| CubeShim ResetVm | 405.8 / 760 / 762 / 763 | 427.7 / 761 / 763 / 763 |
| CubeShim CreateContainer | 192.1 / 4 / 751 / 752 | 175.0 / 4 / 751 / 752 |
| CubeShim RestoreVm | 8.2 / 8 / 10 / 11 | 7.9 / 8 / 9 / 10 |
| API create（客户端，100） | 725.8 / 844.5 / 951.5 / 959.5 | 700.3 / 836.3 / 913.7 / 932.3 |

对照 10-27 同机原模板：ResetVm 2.9 ms，CreateContainer 4 ms，agent ready 17.9 ms。

## 执行记录与排除样本

- `results/attempt0-spec-check/`：runner 要求 2048Mi，在另一用户的模板（2000Mi）上 rc=2，没有创建实例，改用 2000mi 副本。
- `results/attempt1-peer-concurrent/`：另一用户的 create_bench c100 在 19:32 开始，门禁因库存非空拒绝，没有创建实例。之后改为看守脚本，等主机连续两次空闲再开跑。
- `raw/tools/run-diag-eafc.sh`：针对 `tpl-eafc8a29…` 的诊断驱动，未执行。
- profiler 只发布 `analysis/` 输出，`capture/` 原始日志（含内网地址与模板下载 token）未公开。

## 文件

- `results/`、`results-rerun-1956/`、`results-origtpl-2021/`：各轮 `cube-bench.json`、entry 日志、`windows.tsv`、`host-load.tsv`、`window-audit.txt`、`run.log`、`tool-sha256.txt`。
- `results-origtpl-snap10-2055/`：重建原模板 snapshot create c10，6 次调用的 stdout、invocation、cleanup，调用前后快照列表、门禁、窗口与审计。
- `results-origtpl-c50-2101/`：重建原模板 startup c50n500，各轮 `cube-bench.json`、invocation、cleanup、门禁（含负载重试）、窗口、审计与 vmm 版本序列。
- `results-origtpl-rest-2115/`、`results-origtpl-rerun4-2152/`、`results-origtpl-rerun-clone10-2158/`、`results-origtpl-rest-attempt0-foreign-hold/`：其余各项、受干扰项的重测与第一次被拒的启动，见统一报告。`derived/`、`scripts/make_summary.py`：统一汇总表与生成脚本。
- `raw/profiler/`：r1/r2 的 `analysis/`、console 日志、清理前库存、driver 与 progress 日志。
- `raw/tools/`：驱动、门禁、看守、审计脚本及 test-env（API key 占位值已替换）。
- `raw/template-info/`、`raw/template-rebuild-20261028/`：模板定义与重建回执。

## 待办 / 未测

- 重建原模板上 cube-perf-bench 其余各项已完成（21:26–22:00），见 [SUITE-REPORT.md](SUITE-REPORT.md)。另一用户的模板上除 c100 外的项目都未测。
- 定位单一原因（例如只给另一用户的模板加探针重建，或测 `tpl-eafc8a29`）：未做。

## 发布说明与文件清单

本目录发布两份报告、逐项原始输出（cube-bench JSON、上游脚本 stdout/stderr、退出码、调用命令、清理前库存、清理记录、时间窗、测前负载、窗口审计、运行与看守日志、VMM 版本序列）、profiler 分析输出、模板定义和测试机上实际使用的脚本副本。发布前做了以下替换，其余内容与原件一致：

| 原内容 | 替换为 |
| --- | --- |
| 测试机内网地址 | `host-lan-ip` |
| 测试机主机名 | `test-host` |
| 测试机上的工作目录 / 家目录 | `/path/to/workdir` / `/path/to/home` |
| 本次结果目录名中的另一用户名 | `nvme1-peertpl-20261028` |
| 另一用户的用户名及其模板名前缀 | `user-b`、`peer-final-check`、`peer-isnotfc-bench-1028`；文件名 `run-peertpl.sh`、`attempt1-peer-concurrent/` |
| 重建模板别名中的本人用户名 | `user-nvme1-v071-rebuild-1028` |
| 部署未启用鉴权时的 API key 占位值 | `e2b_redacted` |
| 模板下载 URL 查询串 / `cube.master.rootfs.artifact.token` | `?[query-removed]` / `[REDACTED]` |

另外不发布：
- 每项门禁 JSON（`gates/`）、测前后主机条件 JSON（含内核命令行与其他用户进程）、`/snapshots` 列表（含他人快照）。门禁结论见各 `run.log`、`windows.tsv` 与正文。
- profiler 的 `capture/` 原始日志（含内网地址与 token）、`owned.ids`、各轮 `template.json` 与 `*.pid`。
- 2000Mi runner 副本（runner 本身未公开）。

说明：
- 模板 ID、沙箱 ID、组件 SHA 保留原值。
- `raw/*/tool-sha256.txt` 是测试机上脚本原件的哈希，发布副本经替换后与之不一致；`SHA256SUMS` 只证明本目录发布副本的字节。
- 路径占位后脚本仍能通过 `bash -n`，但不能直接在测试机上运行。
- `derived/rest-2115.csv`、`rerun4-2152.csv`、`rerun-clone10-2158.csv` 由 10-27 报告的 `scripts/summarize.py` 生成；`derived/pause-dirty-log-evidence.txt` 是 22:1x 在测试机上只读统计 vmm.log 的结果。

| 路径 | 内容 |
| --- | --- |
| `REPORT.md` | 模板对照（c100n100 两模板各五轮）、profiler 瓶颈、snapshot c10、c50n500 |
| `SUITE-REPORT.md` | 重建原模板上 cube-perf-bench 全部可执行项的统一汇总，含 pause 与 dirty_log 核对 |
| `raw/results/`、`raw/results-rerun-1956/` | peer-final-check c100n100 两组（含两次未开跑的尝试） |
| `raw/results-origtpl-2021/`、`raw/results-origtpl-snap10-2055/`、`raw/results-origtpl-c50-2101/` | 重建原模板 c100n100、snapshot c10、c50n500 |
| `raw/results-origtpl-rest-2115/`、`raw/results-origtpl-rerun4-2152/`、`raw/results-origtpl-rerun-clone10-2158/`、`raw/results-origtpl-rest-attempt0-foreign-hold/` | 其余 29 项、受干扰项重测、第一次被拒的启动 |
| `raw/profiler/` | peer-final-check 两轮 profiler 的 `analysis/` 与驱动日志 |
| `raw/template-info/`、`raw/template-rebuild-20261028/` | 三个模板的 create request 与重建回执 |
| `raw/tools/` | 驱动、门禁、看守、窗口审计脚本副本；驱动调用的 `tools/cleanup-owned.py`、`tools/host-conditions.py` 在工作目录中，未包含 |
| `derived/`、`scripts/make_summary.py` | 统一汇总表与生成脚本 |
| `SHA256SUMS` | 本目录发布文件的校验值 |

从本目录重新生成统一汇总表（只读输入，需同级的 10-27 报告目录）：

```sh
python3 -I scripts/make_summary.py
shasum -a 256 -c SHA256SUMS
```
