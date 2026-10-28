# v0.7.1 · AMD 9654 重建原模板 · cube-perf-bench 全项统一报告

日期：2026-10-28（20:21–22:00 CST）。类型：实测。**状态：完成（runner 列表 32 项 + 扩展 pause-c100，共 33 项；density 为上游手动项，不可执行）**，但 dirty d100–d1024 五档工作量无效，clone-c10n100 见下文。

上级报告：[REPORT.md](REPORT.md)。那里记录模板对照（peer-final-check 约 932 ms 对重建原模板 127.4 ms）和 profiler 瓶颈分析；本文汇总重建原模板上 cube-perf-bench 的全部测试项。

## 结论

- **全部可执行项都已在同一组件、同一模板上完成。**
  - c100n100、snapshot c10、c50n500 每项 5 次（另有 1 次外部热身），其余项与 10-27 矩阵一样各 1 次上游调用。
  - 合计 rc 全部为 0。
- **只有三项有五轮统计**：
  - c100n100 整轮中位 127.4 ms（125.7–133.3）。
  - c50n500 整轮中位 657.7 ms（638.3–682.2）。
  - snapshot c10 wall_avg 中位 93.6 ms（90.9–97.4）。
- **其余为单次调用，只作描述。** 本次没有同条件对照组（只有一套组件、一个模板），所以**不判定任何优化效果**。
  - 表中并列 10-27 nvme1 的 BoostKit（B）与社区（A）单次结果，只供参考。它们用的是已删除的 `tpl-3d73a659` 和不同的组件构建，不计算收益。
- **描述性观察**（单次、跨条件，不是结论）：
  - pause c1/c5/c10 暂停 38.7 / 70.4 / 104.3 ms，与 10-27 BoostKit（34.1 / 63.2 / 94.7）同一量级，远低于 10-27 社区（114–216 ms）。vmm.log 显示本次 696 次 pause 全部走了 PR #32 的 dirty-log 写出路径，见“pause 与 dirty_log”一节。
  - pause-c10 resume avg 607.9 ms，但 5 轮内 min 397.6、max 907.2，呈双峰。10-27 两组都约 0.9 s，这一项只能说本次有部分轮次未出现约 0.9 s 的等待。拆解后，0.9 s 来自少数实例的就绪探针多等一个 500 ms 周期；常态约 400 ms 主要是 resume 重建 VM 后 guest 变慢，随并发线性增长。见“resume c10 约 0.9 s 的来源”一节。
  - snapshot c1 为 30.9 ms（10-27：B 36.2、A 54.6）。dirty d0/d10/d50 快照 31.4 / 47.1 / 51.4 ms，与 10-27 BoostKit 接近。
  - clone-c10n100 三次结果分别是 859.0、800.4、909.9 ms：前两次窗口有外部创建，干净的一次反而最高，比 10-27 BoostKit 的 748.7 高 21.5%。上游每次调用只跑 `--rounds 2`，离散很大，10-27 报告也已指出 clone 结果不稳定。不作判定。
  - startup、create、rollback、clone 多数与 10-27 两组在 ±10% 内，个别项（create-c20 +15%、rollback-c10 +7%、clone-c20n100 +10%）高于 10-27 BoostKit。单次调用，不判定。
- **数据有效性**：
  - dirty d100/200/500/800/1024 工作量无效：模板 `/dev/shm` 只有 64 MiB，上游脚本忽略写入错误。结论沿用 10-27 的诊断。
  - 本次 dirty 写入量读数全部为 -1，与 10-27 BoostKit 相同：上游脚本从 VMM 日志取不到写入字节数。
  - 首轮有 4 项的窗口里出现了外部创建，已重测替换。原结果保留，但不作为样本。

## 被测对象与条件

| 项 | 值 |
| --- | --- |
| 部署 | 另一用户 10-28 19:10 CST 重部署的 BoostKit v0.7.1。源码 `2babb6f7405677c04b7fed1563c6a5d53a8e771b`，工作树干净 |
| 组件 SHA | Cubelet `506b8a83…`、CubeMaster `68dd0cef…`；运行中 shim `2153cb46…` / runtime `c8875540…`；conf.yaml `5cb8ed03…`（`dirty_log: true`）；config.toml `54b93a53…` |
| 组件一致性 | 本文所有门禁记录（c100 8、snap10 7、c50 15、29 项 45、重测 10+）中 7 个文件的 SHA 完全一致。vmm.log 版本行全部为 `2babb6f7` |
| 补丁矩阵 | 没有改变任何组件或开关。BoostKit 2babb6f7 已编入（含 boostkit/CubeSandbox PR #32，即 `86f6d9b9`），`dirty_log` 配置开启。pause 路径已确认生效（见下文“pause 与 dirty_log”）；snapshot / dirty 写入量读数仍为 -1 |
| 模板 | `tpl-4feed5ee40f648a7869a6579`，20:20 按已删除的 `tpl-3d73a659` 参数重建。sandbox-code:isnotfc-20261022-amd64@sha256:801e4703…，2000m / 2048Mi，1G 可写层，xfs，探针 49999 `/health` |
| 内核 / 主机 | 6.6.0，boot_id `d95db03f…`；2×EPYC 9654；THP always，numa_balancing 1，HugePages 100352 预留未用；/data 为 nvme1n1 XFS |
| 工具 | cube-perf-bench community-native `6b577a3e…`；cube-bench `3614d21c…`（`CPB_NO_TUI=1`，bash 启动）；上游 Python 脚本来自社区源码 `31d911e4`，SDK 0.7.0 |
| 门禁 | 每项前：库存为空、TAP ≥600 Ready、无冲突进程、load1 ≤4。只有负载超限时每 30 s 重试；遇到外部占用时，等主机连续 3 次（共 30 s）空闲再重试 |
| 清理与审计 | 每项后只删本模板实例，确认库存为 0。每项前后保存 `/snapshots`（未公开），前后全部一致，他人已有快照未受影响。CubeAPI 窗口审计统计其他模板的创建 |

**指标**（ms，越低越好）：
- startup：整轮 = `summary.total_time_s × 1000`；avg / P95 为单次 create 请求时延。
- snapshot / rollback / create / clone：wall = 一批并发操作从发起到全部返回；per = wall ÷ 并发数。
- pause：pause / resume 为一批并发暂停 / 恢复的 wall。
- dirty：先写入 N MB 再打快照，snap = 快照耗时，create = 建沙箱耗时。

## 结果

“本次”一列：
- c100n100 / c50n500 / snapshot-c10 是 5 次中位；
- 其余为 1 次上游调用，调用内部的轮数见下一节说明。

| 项目 | 指标 | 本次（tpl-4feed5ee） | 10-27 BoostKit B-nvme1 | 10-27 社区 A-nvme1 | 状态 |
| --- | --- | --- | --- | --- | --- |
| startup-c1n20 | 整轮 / avg / P95 | 897.3 / 44.8 / 47.1 | 852.8 / 42.5 / 49.3 | 867.9 / 43.3 / 44.9 | 有效 |
| startup-c10n200 | 整轮 / avg / P95 | 975.9 / 47.8 / 52.4 | 934.4 / 46.5 / 54.7 | 921.5 / 45.6 / 51.3 | 有效 |
| startup-c20n300 | 整轮 / avg / P95 | 774.8 / 50.6 / 55.8 | 751.0 / 48.5 / 58.2 | 767.6 / 50.2 / 58.2 | 有效 |
| startup-c50n500 | 整轮 / avg / P95 | 657.7 / 63.0 / 77.3 | 658.3 / 62.9 / 75.8 | 650.8 / 62.3 / 79.5 | 有效；五次中位；total_ms 逐次 665.3 / 638.3 / 657.7 / 643.3 / 682.2 |
| extended-startup-c100n100 | 整轮 / avg / P95 | 127.4 / 90.1 / 122.0 | 119.8 / — / — | 未测 | 有效；五次中位；total_ms 逐次 125.7 / 127.4 / 126.7 / 130.5 / 133.3 |
| extended-startup-c200n200 | 整轮 / avg / P95 | 214.9 / 140.1 / 203.6 | 231.5 / 151.0 / 219.6 | 未测 | 有效 |
| extended-startup-c200n200 (首测，外部创建) | 整轮 / avg / P95 | 242.0 / 156.0 / 235.5 | 231.5 / 151.0 / 219.6 | 未测 | 窗口有外部创建，不作样本 |
| extended-startup-c300n300 | 整轮 / avg / P95 | 306.7 / 179.5 / 299.3 | 319.4 / 187.2 / 299.3 | 未测 | 有效 |
| snapshot-c1 | wall avg / wall P95 / per avg | 30.9 / 31.9 / 30.9 | 36.2 / 44.8 / 36.2 | 54.6 / 58.6 / 54.6 | 有效 |
| snapshot-c5 | wall avg / wall P95 / per avg | 55.0 / 56.7 / 11.0 | 55.0 / 61.4 / 11.0 | 71.8 / 75.2 / 14.4 | 有效 |
| snapshot-c10 | wall avg / wall P95 / per avg | 93.6 / 97.0 / 9.4 | 92.4 / 97.7 / 9.2 | 97.2 / 102.4 / 9.7 | 有效；五次中位；wall_avg 逐次 97.4 / 90.9 / 92.8 / 93.6 / 96.0 |
| rollback-c1 | wall avg / wall P95 / per avg | 79.1 / 124.8 / 79.1 | 73.2 / 78.3 / 73.2 | 77.1 / 111.2 / 77.1 | 有效 |
| rollback-c5 | wall avg / wall P95 / per avg | 164.8 / 175.7 / 33.0 | 172.4 / 201.2 / 34.5 | 171.7 / 191.7 / 34.3 | 有效 |
| rollback-c10 | wall avg / wall P95 / per avg | 351.1 / 373.6 / 35.1 | 327.5 / 342.0 / 32.8 | 308.8 / 322.8 / 30.9 | 有效 |
| pause-c1 | pause avg / resume avg / resume P95 | 38.7 / 85.5 / 105.0 | 34.1 / 83.4 / 84.1 | 114.4 / 94.5 / 106.8 | 有效 |
| pause-c5 | pause avg / resume avg / resume P95 | 70.4 / 197.1 / 208.9 | 63.2 / 191.8 / 193.7 | 178.5 / 226.6 / 235.3 | 有效 |
| pause-c10 | pause avg / resume avg / resume P95 | 104.3 / 607.9 / 907.2 | 94.7 / 913.9 / 933.7 | 216.4 / 945.5 / 958.9 | 有效 |
| extended-pause-c100 | pause avg / resume avg / resume P95 | 1558.4 / 5264.7 / 5362.7 | 1734.0 / 5303.5 / 5401.8 | 未测 | 有效 |
| dirty-d0 | snap avg / create avg / 写入 MB | 31.4 / 58.4 / -1.0 | 41.9 / 59.2 / -1.0 | 53.3 / 61.7 / 6.5 | 有效 |
| dirty-d10 | snap avg / create avg / 写入 MB | 47.1 / 70.7 / -1.0 | 48.8 / 65.3 / -1.0 | 85.2 / 59.5 / 39.0 | 有效 |
| dirty-d50 | snap avg / create avg / 写入 MB | 51.4 / 66.1 / -1.0 | 57.4 / 63.1 / -1.0 | 109.1 / 63.9 / 120.6 | 有效 |
| dirty-d100 | snap avg / create avg / 写入 MB | 60.3 / 73.6 / -1.0 | 66.3 / 64.9 / -1.0 | 140.4 / 64.8 / 193.5 | 工作量无效（shm 64 MiB） |
| dirty-d200 | snap avg / create avg / 写入 MB | 70.5 / 67.0 / -1.0 | 78.2 / 65.0 / -1.0 | 172.6 / 60.7 / 295.4 | 工作量无效（shm 64 MiB） |
| dirty-d500 | snap avg / create avg / 写入 MB | 97.8 / 67.2 / -1.0 | 94.9 / 61.0 / -1.0 | 264.8 / 58.9 / 600.8 | 工作量无效（shm 64 MiB） |
| dirty-d800 | snap avg / create avg / 写入 MB | 115.9 / 61.3 / -1.0 | 119.4 / 59.4 / -1.0 | 351.9 / 60.7 / 907.9 | 工作量无效（shm 64 MiB） |
| dirty-d1024 | snap avg / create avg / 写入 MB | 130.9 / 55.6 / -1.0 | 133.6 / 64.2 / -1.0 | 434.9 / 66.2 / 1136.3 | 工作量无效（shm 64 MiB） |
| create-c1 | wall avg / wall P95 / per avg | 66.9 / 72.1 / 66.9 | 63.5 / 67.1 / 63.5 | 64.1 / 71.6 / 64.1 | 有效 |
| create-c10 | wall avg / wall P95 / per avg | 85.0 / 94.8 / 8.5 | 92.5 / 97.5 / 9.3 | 91.3 / 96.2 / 9.1 | 有效 |
| create-c20 | wall avg / wall P95 / per avg | 123.1 / 150.9 / 6.2 | 106.7 / 111.7 / 5.3 | 113.9 / 122.7 / 5.7 | 有效 |
| create-c50 | wall avg / wall P95 / per avg | 183.5 / 207.3 / 3.7 | 168.8 / 181.2 / 3.4 | 172.9 / 175.6 / 3.5 | 有效 |
| create-c50 (首测，外部创建) | wall avg / wall P95 / per avg | 176.5 / 178.4 / 3.5 | 168.8 / 181.2 / 3.4 | 172.9 / 175.6 / 3.5 | 窗口有外部创建，不作样本 |
| clone-c1n1 | wall avg / wall P95 / per avg | 138.5 / 147.3 / 138.5 | 145.1 / 153.8 / 145.1 | 154.6 / 170.7 / 154.6 | 有效 |
| clone-c10n100 | wall avg / wall P95 / per avg | 909.9 / 928.1 / 9.1 | 748.7 / 753.5 / 7.5 | 784.2 / 851.1 / 7.8 | 有效 |
| clone-c10n100 (重测1，外部创建) | wall avg / wall P95 / per avg | 800.4 / 845.5 / 8.0 | 748.7 / 753.5 / 7.5 | 784.2 / 851.1 / 7.8 | 窗口有外部创建，不作样本 |
| clone-c10n100 (首测，外部创建) | wall avg / wall P95 / per avg | 859.0 / 861.5 / 8.6 | 748.7 / 753.5 / 7.5 | 784.2 / 851.1 / 7.8 | 窗口有外部创建，不作样本 |
| clone-c20n100 | wall avg / wall P95 / per avg | 781.9 / 805.0 / 7.8 | 710.5 / 800.6 / 7.1 | 未测 | 有效 |
| clone-c50n100 | wall avg / wall P95 / per avg | 1624.1 / 1625.9 / 16.2 | 1892.0 / 1928.4 / 18.9 | 未测 | 有效 |
| clone-c50n100 (首测，外部创建) | wall avg / wall P95 / per avg | 1649.9 / 1765.1 / 16.5 | 1892.0 / 1928.4 / 18.9 | 未测 | 窗口有外部创建，不作样本 |

- 机器可读表：[derived/unified.csv](derived/unified.csv)。逐项原始输出见各结果目录。
- 10-27 两列来自 [10-27 nvme1 报告](../v071-amd9654-community-vs-boostkit-20261027/REPORT.md) 的 [comparison.csv](../v071-amd9654-community-vs-boostkit-20261027/derived/comparison.csv)。社区组外部 VM 在场后剩余项未测，标为“未测”。10-27 B 的 c100 只有整轮中位。

## pause 与 dirty_log（22:1x 只读核对）

用户提出 pause 偏低，怀疑模板制作时未开 `dirty_log=true`、缺少 PR #32 功能。核对结果：

- **PR #32 已编入**：`2babb6f7` 的历史中包含 `86f6d9b9 !32 perf(hypervisor): write pause snapshots from the KVM dirty log behind a host opt-in`。重新编译 PR #32 不会改变被测代码。
- **开关与模板无关**：Cubelet 每次创建都按本机 `host.memory.dirty_log` 写入 `cube.memory.dirty_log` 注解，并在入口删除调用方传入的同名注解。模板构建时的设置不会带到实例。本机 conf.yaml `5cb8ed03` 为 `dirty_log: true`。
- **实际生效**：按 `windows.tsv` 的 CubeAPI 窗口取出本次 pause 各项的沙箱 ID，在 vmm.log 中逐个对应：

  | 项 | 沙箱 | VmPauseToSnapshot | Incremental | `Saving dirty guest memory` |
  | --- | --- | --- | --- | --- |
  | pause-c1 | 6 | 6 | 6 | 6 |
  | pause-c5 | 30 | 30 | 30 | 30 |
  | pause-c10 | 60 | 60 | 60 | 60 |
  | extended-pause-c100 | 600 | 600 | 600 | 600 |

  该日志行只有在 VM 以 dirty_log 启动、且请求类型允许时才会出现，所以本次每一次 pause 都走了 PR #32 的脏页写出路径。证据见 [derived/pause-dirty-log-evidence.txt](derived/pause-dirty-log-evidence.txt)。
- **结论**：pause 38.7 / 70.4 / 104.3 ms 是 dirty_log 开启后的预期量级（只写恢复后被改动的页），不是功能缺失。10-27 社区组没有该补丁，pause 114–216 ms。两者条件不同，仍不计算收益；要量化开关本身，应在同一构建上做 `dirty_log` false/true 对照（需改共享部署的 conf.yaml 并重启 Cubelet，本次未做）。

## resume c10 约 0.9 s 的来源（22:2x 只读诊断）

用户指出 resume c10 约 900 ms 明显偏高，合理范围约 260–330 ms。用 CubeAPI 事件、Cubelet-stat 与 vmm.log 拆解本次 pause 各项（脚本 [scripts/resume_stages.py](scripts/resume_stages.py)，输出 [derived/resume-stage-breakdown.txt](derived/resume-stage-breakdown.txt)）：

- **0.9 s 是长尾，不是常态**：pause-c10 每轮 10 个 resume 中，多数在最后一次 pause 后 373–445 ms 完成。第 3、5 轮各有 1–2 个实例在约 911 ms 完成，客户端 wall 取最慢一个，所以 5 轮为 436 / 411 / 914 / 405 / 912，平均 607.9。
- **长尾 = 就绪探针多等一个周期**：慢实例的 Cubelet `sandbox-probe` 为 602 ms，正常实例 21–97 ms。模板探针周期 500 ms，第一次探测失败就要等到下一次。c10 共 60 次 resume 中有 3 次落在 600 ms 档；c100 的 600 次 resume 中只有 19 次在 100 ms 内，其余落在 600 / 1200 / 1800 / 2400 ms 档。
- **常态约 400 ms 也高于 260–330**，主要在 `sandbox-create`（resume 重建 VM）。它随并发近似线性增长，首次从模板创建则不随并发变化：

  | 项 | 首次创建 sandbox-create p50 | resume sandbox-create p50 | resume sandbox-probe p50 | resume cubebox p50 |
  | --- | --- | --- | --- | --- |
  | pause-c1 | 41 | 54 | 16 | 72 |
  | pause-c5 | 24 | 143 | 34 | 182 |
  | pause-c10 | 24 | 304 | 78 | 385 |
  | extended-pause-c100 | 24 | 3182 | 604 | 4154 |

- **VMM 本身恢复很快，慢在恢复后的 guest**：vmm.log 中 pause 快照恢复的 `vm has been restored` 在进程启动后 9–36 ms，与模板恢复（7–8 ms）接近。但恢复后第一个 vsock 连接的建立耗时，模板恢复约 1.5 ms；pause 快照恢复在 c1 为 14–15 ms，c10 为 102–109 ms。guest 在恢复后响应变慢，且随并发加重。
- **推测（未验证）**：模板恢复的实例共享同一个热的模板内存文件；pause 快照恢复的实例各自映射自己的快照内存文件（日志为 `restore non-shared map`）。这些文件的页缓存可能是冷的，例如 dirty-log 增量快照先克隆底座再写脏页，克隆部分在新 inode 上没有缓存，guest 缺页时需要读盘或走更慢的路径，并发越高越慢。需要用页缓存驻留、块设备读量或缺页 profile 验证。
- 10-27 两组 resume c10 都约 0.9 s，社区组也在内，所以这不是 BoostKit 2babb6f7 引入的退化。

**与另一用户模板的 resume 对照（22:3x 只读，Cubelet 侧耗时）**：

用户指出另一用户的模板 resume 好很多。按 CubeAPI 当日日志把 resume 按模板和批次分组，取每个实例 resume Create 的 Cubelet 耗时（脚本 [scripts/resume_by_tpl.py](scripts/resume_by_tpl.py)，输出 [derived/resume-by-template.txt](derived/resume-by-template.txt)）。数值为“各批 p50 的中位”；“批内最大”近似服务端整批耗时。

| 并发 | 重建原模板 tpl-4feed5ee（有探针）：批次 / sandbox-create / sandbox-probe / 批内最大 | 另一用户 tpl-eafc8a29（无探针）：批次 / sandbox-create / 批内最大 |
| --- | --- | --- |
| 1 | 6 / 54 / 16 / 72 | 155 / 53 / 55 |
| 5 | 6 / 146 / 34 / 185 | 53 / 154 / 173 |
| 10 | 6 / 308 / 76 / 407（两批 886、895） | 68 / 290 / 327（最大 488） |

- **重建 VM 的部分两模板相同**：c10 的 `sandbox-create` 为 308 对 290 ms，c1、c5 也接近。
- **差别全部在就绪探针**：另一用户的模板没有探针，Cubelet 在 `sandbox-create` 结束后就返回。重建原模板多一个 `sandbox-probe`，常态约 76 ms，首探失败时约 600 ms。
- 所以另一用户模板的 c10 整批约 330 ms，落在 260–330 ms 的合理范围；我们的模板常态约 410 ms，偶发约 0.9 s。
- **口径不同**：无探针时 resume 返回不代表 guest 内服务已就绪。同一个无探针模板的 c100n100 创建慢 7 倍（约 932 ms，见 [REPORT.md](REPORT.md)）。
- **限制**：两组数据来自不同用户、不同时段、不同客户端，只比较 Cubelet 服务端阶段，不计算客户端收益。

**可能的改进方向（未测）**：
- 缩短模板探针周期，或让 resume 首探更早或重试更密，以去掉 500 ms 量化长尾，并缩小常态约 76 ms 的探针开销。
- `sandbox-create` 随并发线性增长（c10 约 300 ms、c100 约 3.2 s），两个模板都一样。这是 resume 常态耗时的主体，原因待查（冷页缓存为推测）。

## 执行记录

1. **20:21–20:24**：c100n100，5 次 + 热身，[results-origtpl-2021/](raw/results-origtpl-2021/)。
2. **20:54–20:58**：snapshot c10，5 次 + 热身，[results-origtpl-snap10-2055/](raw/results-origtpl-snap10-2055/)。
3. **21:01–21:08**：c50n500，5 次 + 热身，门禁因负载重试 1–3 次，[results-origtpl-c50-2101/](raw/results-origtpl-c50-2101/)。
4. **21:21**：第一次启动剩余 29 项。另一用户的 `hold_n.py` 持有 10 个 `tpl-eafc8a29` 实例，第一项前门禁拒绝，没有创建实例，[results-origtpl-rest-attempt0-foreign-hold/](raw/results-origtpl-rest-attempt0-foreign-hold/)。之后改为“拒绝即等待空闲”。
5. **21:26–21:48**：29 项依次完成，全部 rc=0，[results-origtpl-rest-2115/](raw/results-origtpl-rest-2115/)。
   - 窗口审计发现 4 项有另一用户的创建：create-c50（3）、clone-c10n100（9）、clone-c50n100（80）、extended-startup-c200n200（5）。
   - 收尾门禁因另一用户新一轮测试（load1 最高 45.65，并出现其实例）未通过，脚本退出，没有写 `conditions-after.json`。门禁记录 `gates/after-attempt-*.json`（未公开）中的组件 SHA 仍一致。
6. **21:52–21:57**：重测这 4 项，[results-origtpl-rerun4-2152/](raw/results-origtpl-rerun4-2152/)。3 项窗口干净；clone-c10n100 仍有 1 个外部创建。
7. **21:58–22:00**：单独再测 clone-c10n100，窗口干净，wall_avg 909.9 ms，[results-origtpl-rerun-clone10-2158/](raw/results-origtpl-rerun-clone10-2158/)。
   - 开测前门禁拒绝过 1 次（另一用户的实例），等到空闲后放行。
   - 收尾门禁时另一用户又在测，等到空闲后通过，22:00:50 写入 `conditions-after.json`（未公开）并结束（ALL DONE）。

**上游脚本每次调用的内部轮数**：
- startup：`-w 3` 预热后正式 N 个；
- snapshot / rollback / pause：`-n 5`，前面另有 1 轮预热；
- dirty / create：`-n 3`；
- clone c1n1：`--rounds 5`；
- clone c10/c20/c50：`--rounds 2`；
- pause-c100（扩展）：`-c 100 -n 5`。

## 限制

- 除三项五轮外，其余都是单次调用，没有轮间区间，不能据此判定差异。
- 共享主机：其他用户的 IDE agent 和监控进程常驻。门禁按项采样，测试中途开始的外部活动只能事后通过窗口审计发现。窗口审计只覆盖 CubeAPI 创建，不能排除其他非 Cube 负载。
- 门禁放行时 load1 为 1.86–3.96，比独占主机时高。
- 与 10-27 对比时，模板（重建 vs 已删除）、组件构建（另一用户 10-28 构建 vs 10-27 原生构建）和主机共享情况都不同。
