# 独立 PR4＋guest warn：c100n100 复测与瓶颈抓取（2026-10-19）

**[打开 report.html](results/bottleneck-c100/capture/inner-round/runs/20261019T041508Z-ca010a49/analysis/report.html)** · [逐轮数据](round-summary.csv) · [历史整轮对比](historical-comparison.csv) · [历史阶段对比](stage-comparison.csv) · [阶段时间线](analysis/timeline.html) · [归档与脱敏说明](PUBLICATION.md)

切换至独立 PR4 后，三轮正式 c100n100 墙钟中位数 **189.82299 ms**，300/300 请求成功。随后独立抓取轮 **198.05185 ms**，100/100 成功。Cubelet 全部线程允许 CPU **0–383**，NUMA 策略 **default**，未绑定 socket。其余组件维持既有绑定和 Go 参数。本归档只整理这次已有数据，没有追加测试或变更远端配置。

## 逐轮结果与计时口径

| 角色 | 整轮墙钟 ms | 请求 P50 ms | P95 ms | P99 ms | 成功/失败 |
| --- | ---: | ---: | ---: | ---: | ---: |
| pilot | 186.07541 | 164.927 | 180.870 | 184.551 | 100/0 |
| 正式 1 | 189.82299 | 150.171 | 185.657 | 186.986 | 100/0 |
| 正式 2 | 184.64082 | 163.610 | 181.360 | 183.190 | 100/0 |
| 正式 3 | 197.10993 | 165.259 | 192.202 | 194.639 | 100/0 |
| 独立瓶颈抓取 | 198.05185 | 173.016 | 193.639 | 195.455 | 100/0 |

正式三轮均值 190.52458 ms，范围 184.64082–197.10993 ms。pilot 与抓取轮不混入正式中位数；未挑选最快轮次。依据用户“180 ms 左右”的目标，采集前采用约 160–200 ms 作为执行瓶颈抓取的判断范围，三轮均落在范围内；这不是补丁因果收益或稳定性置信区间。

协议固定为 **c=100 / n=100 / w=3 / create-only / no-tui**。3 次同进程串行预热不计入官方 `summary.total_time_s`。不是 w0 冷启动，CSV 中 `batch_requests_per_second` 是单波成功数/墙钟，不是稳态吞吐。请求分位数按 raw 最近秩计算。原始结果及按 ID 清理回执见 [evidence-export](results/evidence-export/)。

每轮前连续 3 次确认库存为 0、无 bench/shim/perf/bpftrace 测试进程且 load1<4，间隔 5 秒；轮间清理后冷却 10 秒，第三轮等待负载恢复后才启动。缓存沿用现场，不做 drop_caches、定向逐出或 prefault。正式轮开始前后的身份、门槛等待与协议记录保存在 [results](results/) 的 `*-identity-*.json`、`*-gate.json`、[design.json](results/design.json)。

## 实际版本与配置

| 项目 | 本次实际状态 / 证据 |
| --- | --- |
| 补丁 | 独立 PR4 `999e115abca7ae39dff86dffe28896b3155ebcf5`，base `31d911e430fdf8a8879bd062b8e78066c1a8e89d`；[构建身份](reference/build-version-pr4.json) |
| Shim SHA256 | `c887a2ebcae57fe9998d8312ab19ba56ea7a5a79c89d11545cbed61e37c24b0f` |
| Runtime SHA256 | `76803184bd8069e88522eebea4e1bed564a7da9dde8c6c124a6bfcda8113f0fa` |
| 模板 | 既有 Tw `tpl-9550591684db0b683bb6a3b5`，2 vCPU / 2048 MiB / 1G 可写层，guest `agent.log=warn` |
| MADV | 运行中 shim 继承 `CUBE_FILE_BACKED_MEMORY_MADV_RANDOM=1`，四类目标 VMA 均有 `rr`；[功能探针](results/functional-probe.json) |
| Cubelet | 全部线程 CPU 0–383，Mems 0–3；systemd CPU/NUMA 绑定字段为空，最终 518 个 numa_maps 条目策略均 default；[完成审计](results/completion-audit.json) |
| 其他组件 | Master/API/TemplateCenter/Ops CPU 96–191、bind:1；保持进入本轮时配置 |
| Go 参数 | Master 环境 GOMAXPROCS=32、GOMEMLIMIT=8GiB、GOGC=800。既有源码调查显示 GOGC 会被 SetGCPercent(90) 覆盖，不能把环境 800 称为有效 GC 阈值 |
| 内核与 RCU | `6.6.0-with-softdirty+`；rcu_expedited=0、rcu_normal=0 |
| benchmark SHA256 | `ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511` |

这次将两处调用不存在 `.inst` 文件的失效 shim 包装脚本，备份后替换为 PR4 二进制；runtime 原字节已一致，仍成套核验复制。没有重启服务或修改 CPU/NUMA、Go、RCU、缓存设置。路径与旧/新哈希见 [部署清单](results/deployment-manifest.json)，进入状态见 [entry-state.json](results/entry-state.json)。失效包装脚本造成的全失败轮不能充当正常版本的性能基线。

`rr` 证明映射 advice 已生效，不证明已有文件页缓存全部变为 4 KiB，也不保证时延收益。本轮功能探针确实保留了既有 present PTE 的无 fault folio 采样，并以 compound head/tail 判据验证：agent 与 rootfs 的已分类样本仍属于 **2 MiB folio**（分别观察到 4096、12800 个基础页，落在 N2）；memory 样本混合 4/8/16/64 KiB，另有 817 个 tail-only 未知样本及 1 个竞态样本；guest image 无 present 样本。详见 [采样摘要](folio-sample-summary.csv) 和 [原始探针](results/functional-probe.json)。

这只是独立功能探针时点可见文件页的观察，计数是基础页数而不是唯一 folio 数；未访问缓存页不在样本内，动态 procfs 读取也不是原子快照。该证据不能推出整轮所有缓存布局，更不能单凭大 folio 的存在解释时延。本次未做缓存受控实验或 MADV/RCU 开关对照。PR4 二进制独立于 PR3，但能够复用此前已经创建的 warn 快照。

## 和先前数据对比

下表是历史描述，**环境并不相同，不能把差值归因于 PR4、NUMA 或日志级别某一个因素**。整轮墙钟与单请求平均值没有混用。更完整的机器可读条件和来源见 [historical-comparison.csv](historical-comparison.csv)。

| 历史组 | 正式/有效轮数 | 整轮墙钟 ms | 主要条件差异 |
| --- | ---: | ---: | --- |
| [10/12 社区原版](../v071-c100n100-20261012/REPORT.md) | 1 | 496.32901 | T0、旧 xarray 内核、TAP4000、旧 bench |
| [10/14 优化组合＋NUMA0](../v071-c100n100-optimized-20261014/REPORT.md) | 1 | 364.89465 | 多项组合改动、T0、Cubelet/API CPU0–95、NUMA local；漂移确认轮排除 |
| [10/17 agentwarn/w3](../v071-c100n100-agentwarn-w3-20261017/REPORT.md) | 5 | 中位 159.49012；156.81380–165.84701 | 旧 warn 模板、Shim-C、Cubelet CPU0–191/bind0–1；RCU0、旧 MADV 文件开关不存在 |
| 本次正式参考 | 3 | 中位 189.82299；184.64082–197.10993 | 独立 PR4、Tw、Cubelet CPU0–383/default NUMA、MADV 环境开关 1、RCU0 |
| 本次独立抓取 | 1 | 198.05185 | 同部署，独立日志/metrics 抓取轮，不并入正式统计 |

历史 s13 的约 153.684 ms 也不是当前独立 PR4 的隔离结果：它使用 Shim-C 组合、旧 xarray 内核、旧 warn 模板、Cubelet CPU0–191/bind0–1、RCU1、文件开关 MADV，以及不同缓存准备。来源见前次归档的 [s13 摘要](../v071-c100n100-agentwarn-w3-20261017/reference/s13-baseline-summary.json)。

### 可见组件阶段

以下均以每轮 **103 个组件实例（100 计时＋3 预热，unknown_phase）**为母体。10/17 列是 5 个轮均值的中位数，其余是单轮均值；均不是正式 100 请求的延迟分布。阶段存在父子和累计关系，不能相加。

| 阶段（均值，ms） | 10/12 重算 103 | 10/14 有效轮 | 10/17 轮均值中位 | 本次抓取 |
| --- | ---: | ---: | ---: | ---: |
| Cubelet cubebox-service | 314.773 | 197.594 | 82.039 | 119.951 |
| Cubelet cubebox | 219.162 | 151.587 | 72.960 | 106.603 |
| sandbox-create | 150.995 | 106.368 | 50.020 | 63.997 |
| sandbox-probe | 40.081 | 23.601 | 18.695 | 31.325 |
| Shim CreatePodSandbox | 76.214 | 54.913 | 40.786 | 48.379 |
| RestoreVm | 17.932 | 25.388 | 8.359 | 10.146 |
| ResetVm | 19.078 | 5.243 | 11.301 | 11.583 |
| CreateContainer | 19.796 | 12.117 | 7.223 | 10.136 |

10/12 使用 [重算的 103 样本分析](../v071-c100n100-optimized-20261014/baseline-comparable-103.json)，没有混入其旧报告的 formal100 均值。其余源文件逐项列于 [stage-comparison.csv](stage-comparison.csv)。本次完整覆盖/P95/残差见 [analysis.json](analysis/analysis.json)、[阶段 CSV](analysis/stage-latency.csv)。

本次可见耗时主要集中在完整 sandbox 创建与应用探测：sandbox-create 平均 63.997 ms，probe 平均 31.325 ms/P95 51.920 ms；RestoreVm 与 CreateContainer 各约 10 ms。匹配同实例的 service_outside_cubebox 平均 13.347 ms、cubebox_outside_task_and_probe 平均 10.074 ms，说明还有宿主侧可见流程间隔，但残差不是 CPU 函数分类，不能命名为具体锁或调度等待。

## 工具、证据边界与清理

使用 `v071-c100n100-bottleneck/tools/bottleneck` 的 capture/analyze/network_details/timeline 工具；隔离适配器连接已有按 ID 清理的 w3 runner，没有运行会强制 Cubelet 绑定和 TAP4000 的旧 wrapper。工具 SHA 与准备阶段说明见 [工具来源记录](reference/tool-analysis-review.txt)，完成后的独立分析复核见 [analysis-review.txt](reference/analysis-review.txt)。准备记录保留其当时“待核验”措辞；本轮最终身份以功能探针和完成审计为准。

- 原生 HTML 报告及全部依赖保留原目录；[外层 capture](results/bottleneck-c100/capture/) 与 [离线补充分析](analysis/) 同时归档。源 manifest 中的绝对路径指向原始现场，不要求在 materials 中存在。
- 7 份采集日志原始 SHA 匹配，无轮转/截断/超限缺口；可选 master_stat 缺失。脱敏后两个日志的字节哈希改变，公开数据以 [SHA256SUMS](SHA256SUMS) 为准，原 manifest 不改写。
- 组件 103 个 ID 完整，API seq1..100 完整，但缺少正式 seq→组件 ID 的精确映射；因此组件 unknown_phase 不强行分类。成功且不足 5 ms 的部分 Cubelet 日志被抑制，network 细计时也有输出门槛；缺失不是零。guest warn 使 guest INFO 细分不可见。
- 这是日志/metrics/时间线抓取，**没有 perf、pprof、Go trace 或 perftrace 插桩**。不能据此证明 CPU 热点、RCU 等待、缺页或 NUMA 访问的确切因果。外层 metrics 包含预热、分析与清理，不是纯计时窗口。
- capture 和内层 runner 退出 0；后续编排 postcheck 因 `cmd` 名称遮蔽抛 TypeError。保留 [恢复审计](results/bottleneck-postcheck-recovery.json)，另做只读核验身份不变、库存0；没有重跑或筛选该轮。错误不能抹去，也不能把后处理错误当作 100 个 API 请求失败。
- 5 轮合计 **500/500 计时请求成功**；含预热与独立功能探针，**516 个唯一自有实例全部清理**。最终库存0、无测试进程，PR4 留在现场，Cubelet 全 CPU/default NUMA。见 [完成审计](results/completion-audit.json)、[交付审计](results/delivery-audit.json)。

本目录新增归档，不覆盖 10/12、10/14、10/17 或原 17 组补丁报告。范围、脱敏、源与公开哈希的区别见 [PUBLICATION.md](PUBLICATION.md)。
