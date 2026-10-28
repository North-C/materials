# AMD 9654 社区 v0.7.1 vs BoostKit 2babb6f7 · nvme1 部署 cube-perf-bench 全矩阵对照

日期：2026-10-27 至 10-28。类型：实测。**状态：部分完成**。

- 场景 2（BoostKit）：全矩阵完成，22:51–23:17 CST（14:51–15:17Z）。
- 场景 1（社区原版）：已完成 27 项，23:50–00:06 CST（15:50–16:06Z）。clone-c20n100 第 1 次因 `no more resource` 失败，之后外部 VM 在场，剩余 6 项未执行。
- 10-28 补充：经用户认可，在外部 VM 在场的条件下重测 c100。社区 A 组五轮完成；B/A2 未测，因为另一用户在 09:53:50 停掉了整套 Cube 栈。见文末补充一节。

## 结论（截至 2026-10-28 10:00 CST）

**c100n100 五轮（唯一可按五轮规则判定的指标）**：**仍无法判定**。
- 10-27 夜（无外部 VM）：BoostKit 整轮中位 119.8 ms（115.7–128.9）；社区未测。
- 10-28（外部 VM 在场，独立条件）：社区中位 125.2 ms（117.1–130.1）；BoostKit 未测。
- 两次条件不同，不跨条件计算收益。

**已完成的 27 项，均为单次调用，只作描述性对比：**
- **pause 时延明显更短。** BoostKit pause c1/c5/c10 为 34.1 / 63.2 / 94.7 ms，社区为 114.4 / 178.5 / 216.4 ms，低 56–70%。今天早上 loop 盘 A1/B campaign 的方向和幅度相同（115.6→38.0 ms 等）。两个独立部署结果一致，但每档只有一次调用，没有五轮区间，因此记为“观察到明显差异，未按五轮判定”。
- **resume 没有明确改善。** c1/c5 低 12–15%，c10 仅 -3.3%（945.5→913.9 ms）。c10 的约 0.9 s 在两个版本都出现。
- **snapshot 有差异。** c1/c5 低 34% / 23%，c10 仅 -4.9%。有效的 dirty 档位（d0/d10/d50）快照耗时低 21% / 43% / 47%。BoostKit 的快照写入量读数为 -1（缺观测），所以只能说“快照耗时更短”，不能写成“同等脏页下更快”。
- **其余项目无明确差异**（多在 ±7% 以内，单次调用）：startup 四档、rollback、create、clone c1/c10。

**差异的归属**：BoostKit 组同时改变了四个组件和 `dirty_log=true`。以上差异属于组合处理，不能归因于单个补丁或开关。

**数据有效性**：dirty d100/200/500/800/1024 两组都无效。模板 `/dev/shm` 只有 64 MiB，上游脚本忽略写入错误，结论沿用同日上午 loop 盘对照中的诊断（该诊断报告未公开，要点见“合理性问题”第 1 条）。表中列出这五档，但不计算差值。

## 被测对象与基线

| 组件 | 场景 1 社区 | 场景 2 BoostKit |
| --- | --- | --- |
| 发布包基线 | 社区 v0.7.1-amd64 发布包，源码 `31d911e430fdf8a8879bd062b8e78066c1a8e89d` | 同左，只替换下面四个组件 |
| Cubelet / cubecli | 社区 `594a4d8c…` / `3944214b…` | BoostKit `2babb6f7405677c04b7fed1563c6a5d53a8e771b` 原生构建 `37f8bfc5…` / `de8c50a3…` |
| shim / runtime（`cube-shim/bin` 与 `component_versions/cube-shim/v0.7.1/bin` 两处副本） | 社区 `d72fa20d…` / `8676d2a1…` | BoostKit `82c305a1…` / `f9fcbd37…` |
| Cubelet `dynamicconf/conf.yaml` | 社区 `3b7ce838…`（无 `dirty_log`，即默认关闭） | `eb9faaff…`（`host.memory.dirty_log: true`） |
| Cubelet `config.toml` | `793623e7…`（两组相同） | 同左 |
| CubeMaster / CubeAPI | 社区 `6045a96e…` / `9bafe4e0…` | 同左（未替换） |
| guest agent / guest image / 宿主内核 | 社区发布包；内核 6.6.0 | 同左 |

**开关矩阵**（BoostKit 相对社区，按 AGENTS 规范区分三种状态）：

| 项 | 场景 1 | 场景 2 | 说明 |
| --- | --- | --- | --- |
| BoostKit 2babb6f7 组件补丁（Cubelet/shim/runtime 中的全部提交） | 未编入 | 编入 | 无统一运行时开关；对照组是社区原始构建，不是“编入但关闭”的组 |
| `dirty_log` | 关闭（社区默认，配置中没有该键） | 开启（`true`） | 运行时配置；没有单独测“BoostKit 组件 + dirty_log 关闭” |

**实际生效证据**：
- vmm.log 中 Hypervisor 版本行依次为：BoostKit `v0.7.1-boostkit (2babb6f7…)` 共 18033 次；切换到社区后，社区 `v0.7.1 (31d911e4…)` 共 2362 次，之后没有再出现 boostkit 版本行。见 [vmm-version-sequence-part1.txt](raw/nvme1-A/results/vmm-version-sequence-part1.txt)。
- 运行中 Cubelet 可执行文件的 SHA 与磁盘上的一致。
- 每项开测前的门禁都记录了七个文件的 SHA：B 组 55 份一致，A 组 35 份一致，全部为 boot_id `d95db03f…`。
- `dirty_log` 只能确认配置值。B 组 dirty 写入量读数为 -1，dirty_log 对快照路径的具体作用，**由本次数据未能单独证实**。

**测试对象与工具**：
- 模板 `tpl-3d73a6599076488fa140c6da`：镜像 `sandbox-code:isnotfc-20261022-amd64@sha256:801e4703…`，2000m / 2048Mi，1G 可写层，探针 49999 `/health`，XFS backend。
- 工具：cube-perf-bench `a84d31b`；cube-bench `3614d21c…`（v0.7.1 源码 amd64 构建），`CPB_NO_TUI=1`，由 bash 启动；SDK cubesandbox 0.7.0；上游 checkout `31d911e4`。

**主机**：
- 2×EPYC 9654，384 线程，1.5 TB，内核 6.6.0。
- THP always，NUMA balancing 1，预留 100352×2 MiB HugePages（未使用），governor performance。
- /data 为 nvme1n1 XFS（10-27 上午全新部署）。
- 共享机：多用户 IDE agent、频繁 pgrep 的监控进程，以及 10-21 起常驻的 sys_monitor；空载 load 约 2–4。
- NUMA：两版 Cubelet（31d911e 与 2babb6f7）都把 `usePoolV2` 硬编码为 false，沙箱进入只有 cpu/memory 控制器的 v1 cgroup 池，没有 cpuset 或内存绑定；`cube.numa_node` 只是标签，vmm.log 中 `affinity`/`numa` 均为 None。因此两组的 VMM 都由内核自由调度，NUMA 放置不是本次的处理变量。

## 执行与有效性

| 项 | 场景 1 社区 | 场景 2 BoostKit |
| --- | --- | --- |
| 组件切换 | `swap-components.sh A2` 第 3 次成功（15:48:53Z）；前两次 quickcheck 失败后自动回滚，见下 | 上午部署时已切换 |
| 执行项 | 27/33：列表项 27 个 rc=0；clone-c20n100 第 1 次 rc=1（留档）；clone-c20n100、clone-c50n100、c200、c300、c100×(1+5)、pause-c100 待执行 | 33/33 rc=0 |
| 门禁 | 每项前检查：空库存，TAP ≥600 且全部 Ready、无 owner，无 VM/perf/编码/benchmark 进程，load1 ≤ 4（超出时自动等 30 s 重试，共 5 次） | 同左 |
| 外部创建审计 | 逐项 CubeAPI 日志窗口内，0 个其他模板的创建（[window-audit-part1.txt](raw/nvme1-A/results/window-audit-part1.txt)） | 0（[window-audit.txt](raw/nvme1-B/results/window-audit.txt)） |
| 清理 | 只删本模板实例，每项后确认库存为空 | 同左 |

两组都存在的条件差异：
- MinIO 与 Web UI 在 10-27 17:02 被另一次栈重启停掉，两组运行时都处于停止状态。社区切换时的 quickcheck 用临时 env 跳过了这两项检查，文件权限 0600，用后即删。
- TAP 数为 601/602，不是恰好 600，门禁放宽为 ≥600。

## 结果（ms；B 相对 A = (B−A)/A；单次调用，非五轮）

| 项目 | 指标 | 社区 A-nvme1 | BoostKit B-nvme1 | B 相对 A |
| --- | --- | --- | --- | --- |
| startup-c1n20 | avg / P95 | 43.3 / 44.9 | 42.5 / 49.3 | -1.8% / +9.8% |
| startup-c10n200 | avg / P95 | 45.6 / 51.3 | 46.5 / 54.7 | +2.0% / +6.6% |
| startup-c20n300 | avg / P95 | 50.2 / 58.2 | 48.5 / 58.2 | -3.4% / 0.0% |
| startup-c50n500 | avg / P95 | 62.3 / 79.5 | 62.9 / 75.8 | +1.0% / -4.7% |
| startup c200n200 / c300n300（扩展） | avg | 未完成 | 151.0 / 187.2 | — |
| snapshot c1 / c5 / c10 | wall avg | 54.6 / 71.8 / 97.2 | 36.2 / 55.0 / 92.4 | -33.7% / -23.4% / -4.9% |
| rollback c1 / c5 / c10 | wall avg | 77.1 / 171.7 / 308.8 | 73.2 / 172.4 / 327.5 | -5.1% / +0.4% / +6.1% |
| pause c1 / c5 / c10 | pause avg | 114.4 / 178.5 / 216.4 | 34.1 / 63.2 / 94.7 | -70.2% / -64.6% / -56.2% |
| pause c1 / c5 / c10 | resume avg | 94.5 / 226.6 / 945.5 | 83.4 / 191.8 / 913.9 | -11.7% / -15.4% / -3.3% |
| pause c100（扩展） | pause / resume | 未完成 | 1734.0 / 5303.5 | — |
| dirty d0 / d10 / d50 | snap avg | 53.3 / 85.2 / 109.1 | 41.9 / 48.8 / 57.4 | -21.4% / -42.7% / -47.4% |
| dirty d0 / d10 / d50 | create avg | 61.7 / 59.5 / 63.9 | 59.2 / 65.3 / 63.1 | -4.1% / +9.7% / -1.3% |
| dirty d0 / d10 / d50 | 快照写入 MB | 6.5 / 39.0 / 120.6 | N/A（-1） | — |
| dirty d100 / d200 / d500 / d800 / d1024 | snap avg | 140.4 / 172.6 / 264.8 / 351.9 / 434.9 | 66.3 / 78.2 / 94.9 / 119.4 / 133.6 | **工作量无效，不计算** |
| create c1 / c10 / c20 / c50 | wall avg | 64.1 / 91.3 / 113.9 / 172.9 | 63.5 / 92.5 / 106.7 / 168.8 | -0.9% / +1.3% / -6.3% / -2.4% |
| clone c1n1 / c10n100 | wall avg | 154.6 / 784.2 | 145.1 / 748.7 | -6.1% / -4.5% |
| clone c20n100 / c50n100 | wall avg | 未完成 | 710.5 / 1892.0 | — |
| **c100n100 ×5 整轮 total_ms** | 中位（min–max） | 未完成 | **119.8（115.7–128.9）**；逐轮 116.7 / 128.9 / 124.7 / 119.8 / 115.7 | — |
| c100n100 ×5 | 客户端 avg / P99 中位 | 未完成 | 85.3 / 117.0 | — |

- 逐项细表（含 P95、per_avg）：[comparison-nvme1.md](derived/comparison-nvme1.md)；完整 CSV 含早上 loop 盘三组：[comparison.csv](derived/comparison.csv)。
- 早上 loop 盘结果来自不同存储、不同模板端口，并且不是全新部署，**不与本表合并计算收益**。

## 合理性问题

1. **dirty d100 及以上档位的工作量无效（两组都是）**。原镜像在 2 GiB 规格下 `/dev/shm` 只有 64 MiB，上游 dirty 脚本忽略 guest 中的写入错误。10-27 已有独立诊断：标称 1024 MiB 的文件实际只有 67108864 bytes，并报 ENOSPC。本模板使用同镜像、同规格，沿用该诊断，未在本模板上单独复核。社区组快照写入量仍随档位增长（d1024 为 1136 MB），说明 guest 内存确实被写脏，但标称的文件写入没有完成，所以不作为对应工作量的样本。要测大写入量，需改用 4 GiB / shm 1536 MiB 的补正条件（10-27 已建，独立索引）。
2. **BoostKit 快照写入量读数为 -1**。-1 是上游脚本从 VMM 日志取不到写入字节，不代表写入量为 0，原因与 BoostKit 日志格式有关，未进一步核对。
3. **resume 在 c5→c10 出现跳变，c10 约 0.9 s**，两个版本都有。早上的诊断显示与探针 100 ms 超时加 500 ms 周期相容，但根因未证实。c10 的 resume 主要在测排队。
4. **clone 离散大**：上游每档只跑 `--rounds 2`；BoostKit nvme1 上 c20（710.5）比 c10（748.7）还快。另外，**两轮之间不等上一轮的克隆销毁完**，见下面的失败记录。
5. **除 c100 外每项只调用 1 次**，没有轮间区间。按“每组五轮”规则，只有 c100 能判定；上面 ±7% 以内的差异都不能下结论。
6. 口径：
   - startup `total_ms` 在低并发档位是串行总耗时，跨档位不可比。
   - c200/c300 受 Master `create_concurrent_limit: 100` 限制，主要在测排队。

## 场景 1 执行记录（未完成部分）

1. **组件切换，A2 共尝试 3 次。**
   - 第 1 次：quickcheck 因 MinIO 未运行而失败，自动回滚。回滚后的 quickcheck 同样失败，标为 ROLLBACK_FAILED，文件和服务都保持 B 状态。
   - 第 2 次：用临时 env 设 `CUBE_SANDBOX_MINIO_ENABLED=0` 后，又因 Web UI 未运行失败，回滚情况同上。
   - 第 3 次：再加 `WEB_UI_ENABLE=0` 后成功。
   - 三份日志见 `raw/nvme1-A/results/swap-A2*.log`。
2. **clone-c20n100 第 1 次失败（rc=1，16:06:08Z）。**
   - 第 2 轮 101 个克隆中 97 个成功，4 个在 16:05:58Z 返回 CubeMaster 130597 `no more resource`。
   - 当时 Master 日志显示第 1 轮约 100 个克隆仍在异步销毁（该 10 s 内 DestroySandbox 166 次）。Master 调度启用了 cpu/mem 过滤，两轮叠加约 200 个 2 vCPU 实例。**推断**是配额被尚未释放的实例占满，未直接读取节点可分配量证实。
   - 窗口审计显示这段时间没有外部创建。
   - BoostKit 组同项通过，可能只是时序上没碰到，不作为版本差异。
   - 失败结果保留在 [clone-c20n100-attempt1-no-more-resource](raw/nvme1-A/results/clone-c20n100-attempt1-no-more-resource/stderr.log)，不作为性能样本。
3. **续跑受阻。**
   - 第一次续跑：跨过零点后，脚本按日期找 `cube-api-2026-10-28.log`，该文件不存在（CubeAPI 仍写 10-27 文件），`stat` 失败，在开跑前退出。已改为取最近修改的日志。
   - 第二次续跑：`host-conditions.py` 拒绝覆盖上一次留下的文件，在开跑前退出。旧文件已改名留档。
   - 第三次续跑：门禁发现 00:10:55 CST 新起的外部 libvirt VM（下文记为 `foreign-vm`）（96 vCPU、约 196 GiB，绑 socket1 NUMA 6/7），按规则拒绝。三次都没有创建任何实例。
4. **等待外部 VM 退出**：测试机上的 `tools/wait-then-resume.sh` 每 60 s 检查一次，最多等 6 h。当没有 qemu-kvm/ffmpeg/x265 进程且 load1 ≤ 4、连续 3 次满足时，自动续跑剩余 6 项（clone-c20n100 重测、clone-c50n100、c100 预热+5、c200、c300、pause-c100），每项仍走同一门禁。第一个看守等满 6 h 后放弃（06:13 CST）：外部 VM 在整个期间都没有退出（运行 6 h，平均约 3.5 核），没有开跑任何项。06:20 CST 起换第二个看守继续等，上限 12 h。09:47 CST 按用户决定停止第二个看守，改为在 VM 在场的条件下重测 c100（见下一节）。上述社区剩余 5 个矩阵项（clone c20/c50、c200、c300、pause-c100）**未测**。

## 10-28 补充：外部 VM 在场条件下的 c100 A→B→A（部分完成）

**条件**：
- 用户在 10-28 09:47 认可在外部 VM 在场的情况下重测 c100。该 VM 即 `foreign-vm`，pid 421105。
- 当时 VM CPU 近乎空闲，但占用了 196 GiB 内存，全部是 node6/7 上的 HugePages，`HugePages_Free=0`。10-27 夜里两组运行时 HugePages 全部空闲，所以**这是独立条件**，不与 10-27 的 A/B 合并计算收益。
- 门禁和切换脚本的副本只放行该 pid 与 guest 名，其他规则不变。每轮前后都采样 VM 的 CPU 时间和整机繁忙度。
- 设计是社区 A → BoostKit B → 社区 A2，每组 1 次外部热身加 5 轮正式，用 A 前后两组检查漂移。

**A 组（社区 31d911e，dirty_log 默认关闭）完成 5/5 轮**，09:49–09:52 CST：

| 轮 | 整轮 total_ms | 成功/错误 | 客户端 avg | P95 | P99 | 本轮 VM 平均占用（核） | 整机繁忙 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 热身（排除） | 145.9 | 100/0 | 107.0 | 140.2 | 144.4 | 0.18 | 6.7% |
| 1 | 117.1 | 100/0 | 84.4 | 111.4 | 115.5 | 0.44 | 5.2% |
| 2 | 130.1 | 100/0 | 97.6 | 123.0 | 127.3 | 0.63 | 5.4% |
| 3 | 124.8 | 100/0 | 88.6 | 119.1 | 120.6 | 0.16 | 5.3% |
| 4 | 125.2 | 100/0 | 90.3 | 115.3 | 118.0 | 0.16 | 6.2% |
| 5 | 127.9 | 100/0 | 95.9 | 121.0 | 125.5 | 0.76 | 5.9% |
| **中位（min–max）** | **125.2（117.1–130.1）** | | 90.3 | 119.1 | 120.6 | | |

- VM 占用按 100 Hz 的 jiffies 统计，采样窗口只有约 0.67 s，精度较粗。
- 逐项 CubeAPI 窗口审计显示 0 个外部创建（[window-audit.txt](raw/nvme1-vm-20261028/results/window-audit.txt)）。

**B 组与 A2 组未测**：
- 09:53:47 CST，B 切换成功：四组件 2babb6f7 加 `dirty_log: true`，quickcheck 通过，见 [swap-B.log](raw/nvme1-vm-20261028/results/swap-B.log)。
- **3 秒后（09:53:50）**，另一用户的 IDE agent 执行了 `systemctl stop cube-sandbox-control.target`，3 秒后又停了 `cube-sandbox-compute.target`，整套 Cube 栈全部停止。见 [foreign-stack-stop-journal.txt](raw/nvme1-vm-20261028/results/foreign-stack-stop-journal.txt)。B 组第一轮之前的门禁因 API 连接被拒退出，没有创建任何实例。
- 对方是在主动操作这套部署，因此**没有自行重启栈**。截至 10-28 09:54 CST，磁盘上的组件为 BoostKit 2babb6f7 加 dirty_log=true，与 10-27 上午部署时的默认状态相同，服务处于停止状态。这是历史记录，不代表测试机现状。

**判定**：本条件下只有 A 组，**无法做 A/B 判定**。仅作描述：A 组中位 125.2 ms，与 10-27 夜间 BoostKit（无 VM 条件）的 119.8 ms（115.7–128.9）范围重叠，但条件不同，不能计算收益。


## 发布说明与文件清单

本目录发布报告、逐项原始输出（cube-bench JSON、上游脚本 stdout/stderr、退出码、调用命令、清理前库存、清理记录、主机条件、时间窗、窗口审计、切换日志）和测试机上实际使用的脚本副本。发布前做了以下替换，其余内容与原件一致：

| 原内容 | 替换为 | 出现位置 |
| --- | --- | --- |
| 测试机内网地址 | `host-lan-ip` | 清理前库存的 `clientID`（1650 处） |
| 测试机主机名 | `test-host` | cube-bench stdout 的 Host 行、journal 摘录（99 处） |
| 测试机上的工作目录 | `/path/to/workdir` | 调用命令、运行日志、脚本（518 处） |
| 外部 VM 的 libvirt 名称 | `foreign-vm` | 门禁/切换脚本放行条件、切换日志（10 处） |
| 另一用户 agent 的产品名 | `IDE agent shell of another user` | journal 摘录（2 处） |
| 部署未启用鉴权时的 API key 占位值 | `e2b_redacted` | `tools/test-env.sh`（6 处） |
| 切换脚本临时文件后缀中的用户名 | `.user-swap-` | `tools/swap-components.sh`（2 处） |

另外：
- 不发布含模板下载 token 的 `template.json` 和每项门禁的 JSON 记录。门禁结论见各 `run.log`、`windows.tsv` 与报告正文。
- 不发布 `*.pid` 文件。
- `raw/` 中的文件保留原始行尾和行末空白（上游表格的对齐空格）；`derived/comparison.csv` 由 Python csv 模块生成，行尾为 CRLF。
- 替换使用不含 shell 元字符的占位值，脚本仍能通过 `bash -n`。但路径占位后不能直接在测试机上运行，使用前需改回实际路径。
- `raw/*/results/tool-sha256*.txt` 记录的是测试机上脚本原件的哈希。发布副本经过替换，与这些哈希不一致。`SHA256SUMS` 只证明本目录发布副本的字节。
- `derived/comparison.csv` 除 A-nvme1/B-nvme1 外，还包含同日上午 loop 盘三组（A1-loop、B-loop、A2-loop）。loop 盘的存储、模板端口和部署都不同，**不与 nvme1 合并计算收益**。

| 路径 | 内容 |
| --- | --- |
| `raw/nvme1-B/` | 场景 2（BoostKit）全矩阵 33 项与 c100 热身+5 轮；`checks/` 是开测前的单项冒烟；`tools/` 为驱动、门禁、切换脚本副本 |
| `raw/nvme1-A/` | 场景 1（社区）已完成的 27 项、clone-c20n100 失败尝试、三次未开跑的续跑日志、两个看守日志、切换日志、窗口审计和 VMM 版本序列；`tools/` 含 `run-resume.sh`、`wait-then-resume.sh` |
| `raw/nvme1-vm-20261028/` | 10-28 外部 VM 在场条件下的 A 组 c100 热身+5 轮、`vm-cpu.tsv`（逐轮 VM CPU 与整机繁忙度）、B 切换日志、外部停栈的 journal 摘录；`tools/` 含 `run-aba.sh`、`run-resume-B.sh`（未运行） |
| `raw/morning-loop/{A1,B,A2}/` | 同日上午 loop 盘 campaign 的同类输出，只作方向参考 |
| `derived/comparison-nvme1.md` | `scripts/compare.py` 生成的 A/B 逐项表 |
| `derived/comparison.csv` | `scripts/summarize.py` 生成的机器可读汇总 |
| `scripts/` | `run-all.sh`（测试机驱动）、`summarize.py`、`compare.py`、`audit_windows.py` |
| `SHA256SUMS` | 本目录发布文件的校验值 |

从本目录重新生成汇总表（只读输入）：

```sh
python3 -I scripts/summarize.py /tmp/comparison.csv \
  A-nvme1=raw/nvme1-A/results B-nvme1=raw/nvme1-B/results \
  A1-loop=raw/morning-loop/A1 B-loop=raw/morning-loop/B A2-loop=raw/morning-loop/A2
python3 -I scripts/compare.py /tmp/comparison.csv A-nvme1 B-nvme1
shasum -a 256 -c SHA256SUMS
```
