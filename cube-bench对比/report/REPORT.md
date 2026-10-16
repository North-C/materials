# cube-bench 六轮 profile 汇总

已完成 6/6 轮；在 测试机 的相同服务端环境和 sandbox-code:latest 镜像下，交替运行 v0.7.1 / master 同源码组与 v0.5.1 客户端，每组 3 轮。

v0.7.1 / master（同源码组）：3 轮正式总时长均值 495.173 ms，范围 452.731–518.510 ms；合并 300 个有效请求，AVG 348.081 ms、P95 511.408 ms。

v0.5.1：3 轮正式总时长均值 472.687 ms，范围 459.944–484.979 ms；合并 300 个有效请求，AVG 346.085 ms、P95 474.396 ms。

两组请求均值接近，v0.7.1 相对 v0.5.1 的合并请求 AVG 差为 1.995 ms（+0.58%）。整轮时长和尾延迟存在轮间波动；这 6 轮观测不能将差异归因于客户端源码，也不代表服务端升级收益。

完整性验证通过：正式请求成功 600，独立预热成功 18，清理确认删除或不存在 618 个沙箱。服务 PID / 二进制哈希一致性：true；主机设置一致性：true。最终沙箱数 0，残留压测进程数 0。

## 逐轮正式结果

| 轮次 / 源码组 | 状态 | 正式总时长 ms | AVG ms | P50 ms | P95 ms | P99 ms | 请求 max ms | 有效 n | 成功 / 尝试 | 成功率 | 预热成功 / 计划 | 清理 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| round-01-v071 | complete | 514.278 | 365.198 | 389.725 | 510.862 | 512.545 | 513.703 | 100 | 100/100 | 100.0% | 3/3 | verified_empty |
| round-02-v051 | complete | 459.944 | 331.282 | 344.437 | 452.958 | 457.119 | 458.752 | 100 | 100/100 | 100.0% | 3/3 | verified_empty |
| round-03-v071 | complete | 518.510 | 362.938 | 408.740 | 514.808 | 517.729 | 517.982 | 100 | 100/100 | 100.0% | 3/3 | verified_empty |
| round-04-v051 | complete | 473.138 | 357.517 | 384.467 | 470.552 | 471.888 | 472.012 | 100 | 100/100 | 100.0% | 3/3 | verified_empty |
| round-05-v071 | complete | 452.731 | 316.106 | 340.678 | 447.812 | 452.401 | 452.530 | 100 | 100/100 | 100.0% | 3/3 | verified_empty |
| round-06-v051 | complete | 484.979 | 349.457 | 349.455 | 480.958 | 483.901 | 484.192 | 100 | 100/100 | 100.0% | 3/3 | verified_empty |

## 版本级合并请求样本

| 源码组 | 有效样本 / 计划 | AVG ms | P50 ms | P95 ms | P99 ms | 请求 max ms | 成功率 | 三轮正式总时长 ms（按序） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v0.7.1 / master（同源码组） | 300/300 | 348.081 | 354.371 | 511.408 | 515.841 | 517.982 | 100.0% | 514.278 / 518.510 / 452.731 |
| v0.5.1 | 300/300 | 346.085 | 364.711 | 474.396 | 481.847 | 484.192 | 100.0% | 459.944 / 473.138 / 484.979 |

## 核心阶段：AVG / P95；已观察实例 / 计划请求

| 阶段 | 01-v071 | 02-v051 | 03-v071 | 04-v051 | 05-v071 | 06-v051 |
| --- | --- | --- | --- | --- | --- | --- |
| master.cube-e2e | 295.980 / 434 ms; 100/100 | 284.920 / 364 ms; 100/100 | 296.870 / 440 ms; 100/100 | 324.730 / 405 ms; 100/100 | 263.800 / 342 ms; 100/100 | 304.980 / 407 ms; 100/100 |
| cubelet.cubebox-service | 290.480 / 425.875 ms; 100/100 | 277.821 / 356.789 ms; 100/100 | 287.342 / 427.209 ms; 100/100 | 319.162 / 395.418 ms; 100/100 | 258.827 / 338.516 ms; 100/100 | 300.313 / 400.240 ms; 100/100 |
| cubelet.network | 22.932 / 45.425 ms; 72/100 | 31.821 / 36.213 ms; 90/100 | 16.796 / 52.170 ms; 74/100 | 49.152 / 70.053 ms; 60/100 | 33.563 / 73.362 ms; 82/100 | 15.834 / 31.133 ms; 73/100 |
| cubelet.storage | 14.688 / 27.085 ms; 79/100 | 17.078 / 23.267 ms; 90/100 | 16.923 / 28.284 ms; 79/100 | 25.336 / 43.047 ms; 77/100 | 16.222 / 25.825 ms; 87/100 | 16.756 / 26.619 ms; 86/100 |
| cubelet.cubebox | 211.132 / 297.061 ms; 100/100 | 191.461 / 236.591 ms; 100/100 | 210.476 / 311.428 ms; 100/100 | 210.909 / 265.725 ms; 100/100 | 185.888 / 247.281 ms; 100/100 | 212.909 / 276.826 ms; 100/100 |
| cubelet.sandbox-start | 155.531 / 246.809 ms; 100/100 | 140.805 / 183.970 ms; 100/100 | 152.895 / 256.780 ms; 100/100 | 157.185 / 209.998 ms; 100/100 | 130.964 / 178.312 ms; 100/100 | 157.247 / 219.425 ms; 100/100 |
| cubelet.sandbox-create | 141.576 / 202.304 ms; 100/100 | 132.653 / 170.619 ms; 100/100 | 141.909 / 215.877 ms; 100/100 | 149.517 / 204.919 ms; 100/100 | 123.279 / 154.364 ms; 100/100 | 147.007 / 187.338 ms; 100/100 |
| cubelet.sandbox-probe | 28.563 / 41.600 ms; 100/100 | 31.879 / 53.789 ms; 100/100 | 30.678 / 47.871 ms; 100/100 | 31.302 / 50.761 ms; 100/100 | 34.712 / 62.319 ms; 100/100 | 34.122 / 64.140 ms; 100/100 |
| shim.CreatePodSandbox | 55.910 / 86 ms; 100/100 | 57.590 / 82 ms; 100/100 | 59.450 / 88 ms; 100/100 | 61.660 / 90 ms; 100/100 | 60.170 / 96 ms; 100/100 | 59.520 / 83 ms; 100/100 |
| shim.CreateContainer | 16.080 / 34 ms; 100/100 | 18.260 / 29 ms; 100/100 | 17.570 / 35 ms; 100/100 | 16.140 / 25 ms; 100/100 | 15.900 / 26 ms; 100/100 | 17.820 / 31 ms; 100/100 |
| shim.RestoreVm | 17.500 / 45 ms; 100/100 | 13.720 / 24 ms; 100/100 | 17.610 / 45 ms; 100/100 | 15.210 / 24 ms; 100/100 | 15.200 / 24 ms; 100/100 | 15.410 / 27 ms; 100/100 |
| master.trace.bufferhandle | N/A / N/A ms; 0/100 | N/A / N/A ms; 0/100 | N/A / N/A ms; 0/100 | N/A / N/A ms; 0/100 | N/A / N/A ms; 0/100 | N/A / N/A ms; 0/100 |

## 统计边界与证据限制

客户端 create_ms 从请求准备到 client.Do 返回响应头计时，不包含随后读取响应体和 JSON 解码；CubeMaster cube-e2e 仅覆盖内部 CreateSandbox 到 setProbeInfo，不覆盖模板前处理、API 和完整 HTTP 链路。

比较对象为两个 cube-bench 客户端源码组，每组 3 轮；v0.7.1 与 master 的源码一致性由独立证据链接说明。服务端沿用 测试机 环境，镜像 sandbox-code:latest；此处不代表服务端版本升级实验。

每轮先独立进程预热 c1n3w0，再正式 c100n100w0、create-only、-no-tui JSON。预热不计入正式 total_time_s，且不复用客户端连接。正式计时包含调度与结果收集，不等于单请求 max，也不等于采集窗口。

每轮和版本聚合的请求分位数均由有效成功 raw.create_ms 样本按 nearest-rank：排序后第 ceil(p×N) 项计算；版本级合并 3 轮，完整时 N=300，绝不平均各轮 P95/P99。原工具可能采用不同分位数索引，其 create 汇总另保留在 JSON。

请求成功率使用原始 summary.successful/(successful+errors)，并保留生产者报告值。缺失和无效数据保留 null/N/A，缺轮不会补零或伪装成 300 个样本。

归属 limited 表示模板独占声明及 CLI inventory 差集等有限证据；客户端 seq 未映射到 sandbox ID，不能建立逐请求端到端分解。阶段统计仅描述已观察日志记录，覆盖率按实例统计。

Cubelet 成功阶段低于 5 ms 可能不记日志，覆盖不足不等于失败或耗时为零；master_stat 缺失时其内部 trace 阶段不可测。嵌套阶段不能相加，也不能把跨群体均值之差命名为网络耗时。

结论仅描述本次已采集轮次的观测；样本、环境时变与日志覆盖限制不支持因果结论或泛化性能回归判断。报告不嵌入原始日志或配置。

这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。

## 环境与构建证据

| 环境项 | 取值 |
| --- | --- |
| 目标 / 环境核验 UTC | 测试机 / 2026-10-16T04:01:15.702424+00:00 |
| 镜像 | cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code:latest |
| arm64 manifest digest | sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d |
| 模板 / 状态 / 资源 | template-anonymous / READY / cpu=2000m, mem=2048Mi |
| 初始沙箱数 / loadavg | 0 / 0.22 0.14 0.15 1/6236 1039790 |
| THP / defrag / NUMA balancing | always madvise [never] / always defer defer+madvise madvise [never] / 0 |
| 工作负载 | 独立预热 c1n3w0；正式 c100n100w0；create-only；no-tui=true；JSON |
| Profiler commit | 912b1ba2e65b6a261201cff1c4bb2de8e88f5ac5 |
| 重试策略 | No benchmark reruns to select results; cleanup network retries permitted |

| 构建项 | v0.7.1 / master（同源码组） | v0.5.1 |
| --- | --- | --- |
| commit | 31d911e430fdf8a8879bd062b8e78066c1a8e89d | a164417f497234a0d787cb328b0ae96480b1569b |
| 等价 master commit | 5741deb433b7e2b9c9d2dcadb1c87214de74bd24 | N/A |
| cube-bench tree | fa4895544c890a6204b5defbb1750e7217b7f980 | 8f1f5b660e7f7a8f02c4678ceadcfb0e9c02446c |
| binary SHA256 | ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511 | 17cfe223a9cb1f40db9753e74eebecc08b106cf2ec5fc7a05b352719e3e6c6e4 |
| Go 工具链 | go version go1.25.0 linux/arm64 | go version go1.25.0 linux/arm64 |
| 构建命令 | go build -mod=readonly -trimpath -o cube-bench-v0.7.1-linux-arm64 . | go build -mod=readonly -trimpath -o cube-bench-v0.5.1-linux-arm64 . |
| 构建环境 | CGO_ENABLED=0, GOOS=linux, GOARCH=arm64, GOARM64=v8.0, GOTOOLCHAIN=local | CGO_ENABLED=0, GOOS=linux, GOARCH=arm64, GOARM64=v8.0, GOTOOLCHAIN=local |

完整环境和构建字段保留于 [summary.json](summary.json)，并可沿下列链接核对原始 JSON 证据。

[plan](../plan.json)
[host](../preflight/host.json)
[registry](../preflight/registry-manifest.json)
[verification](../verification.json)
[final-state](../preflight/final-state.json)

[源码一致性证据](../version-evidence/v071-master/README.md)

## 每轮证据与状态

### round-01-v071

归属 limited；master_stat unavailable；独立预热 193.234 ms；清理剩余 0。 实际记录的采集缺口仅为 master_stat:no_readable_start_offset（master_stat 不可用）；下方保留的分析器通用警告不表示本轮已发现 rotation/truncation。

[HTML](../round-01-v071/runs/20261016T040607Z-4a181a42/analysis/report.html) · [CSV](../round-01-v071/runs/20261016T040607Z-4a181a42/analysis/stage-latency.csv) · [JSON](../round-01-v071/runs/20261016T040607Z-4a181a42/analysis/analysis.json) · [timeline HTML](../round-01-v071/runs/20261016T040607Z-4a181a42/analysis/timeline.html) · [timeline JSON](../round-01-v071/runs/20261016T040607Z-4a181a42/analysis/timeline.json) · [precision](../round-01-v071/runs/20261016T040607Z-4a181a42/analysis/precision.json) · [raw JSON](../round-01-v071/runs/20261016T040607Z-4a181a42/capture/startup-latency/benchmark.raw.json) · [cleanup](../round-01-v071/evidence/cleanup.json) · [runner-validation](../round-01-v071/runs/20261016T040607Z-4a181a42/capture/startup-latency/runner-validation.json) · [prewarmup](../round-01-v071/runs/20261016T040607Z-4a181a42/capture/startup-latency/prewarmup.json)

- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- 这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。

### round-02-v051

归属 limited；master_stat unavailable；独立预热 185.536 ms；清理剩余 0。 实际记录的采集缺口仅为 master_stat:no_readable_start_offset（master_stat 不可用）；下方保留的分析器通用警告不表示本轮已发现 rotation/truncation。

[HTML](../round-02-v051/runs/20261016T040647Z-ecdba122/analysis/report.html) · [CSV](../round-02-v051/runs/20261016T040647Z-ecdba122/analysis/stage-latency.csv) · [JSON](../round-02-v051/runs/20261016T040647Z-ecdba122/analysis/analysis.json) · [timeline HTML](../round-02-v051/runs/20261016T040647Z-ecdba122/analysis/timeline.html) · [timeline JSON](../round-02-v051/runs/20261016T040647Z-ecdba122/analysis/timeline.json) · [precision](../round-02-v051/runs/20261016T040647Z-ecdba122/analysis/precision.json) · [raw JSON](../round-02-v051/runs/20261016T040647Z-ecdba122/capture/startup-latency/benchmark.raw.json) · [cleanup](../round-02-v051/evidence/cleanup.json) · [runner-validation](../round-02-v051/runs/20261016T040647Z-ecdba122/capture/startup-latency/runner-validation.json) · [prewarmup](../round-02-v051/runs/20261016T040647Z-ecdba122/capture/startup-latency/prewarmup.json)

- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- 这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。

### round-03-v071

归属 limited；master_stat unavailable；独立预热 205.969 ms；清理剩余 0。 实际记录的采集缺口仅为 master_stat:no_readable_start_offset（master_stat 不可用）；下方保留的分析器通用警告不表示本轮已发现 rotation/truncation。

[HTML](../round-03-v071/runs/20261016T040715Z-fb59979b/analysis/report.html) · [CSV](../round-03-v071/runs/20261016T040715Z-fb59979b/analysis/stage-latency.csv) · [JSON](../round-03-v071/runs/20261016T040715Z-fb59979b/analysis/analysis.json) · [timeline HTML](../round-03-v071/runs/20261016T040715Z-fb59979b/analysis/timeline.html) · [timeline JSON](../round-03-v071/runs/20261016T040715Z-fb59979b/analysis/timeline.json) · [precision](../round-03-v071/runs/20261016T040715Z-fb59979b/analysis/precision.json) · [raw JSON](../round-03-v071/runs/20261016T040715Z-fb59979b/capture/startup-latency/benchmark.raw.json) · [cleanup](../round-03-v071/evidence/cleanup.json) · [runner-validation](../round-03-v071/runs/20261016T040715Z-fb59979b/capture/startup-latency/runner-validation.json) · [prewarmup](../round-03-v071/runs/20261016T040715Z-fb59979b/capture/startup-latency/prewarmup.json)

- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- 这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。

### round-04-v051

归属 limited；master_stat unavailable；独立预热 211.244 ms；清理剩余 0。 实际记录的采集缺口仅为 master_stat:no_readable_start_offset（master_stat 不可用）；下方保留的分析器通用警告不表示本轮已发现 rotation/truncation。

[HTML](../round-04-v051/runs/20261016T040743Z-217078a6/analysis/report.html) · [CSV](../round-04-v051/runs/20261016T040743Z-217078a6/analysis/stage-latency.csv) · [JSON](../round-04-v051/runs/20261016T040743Z-217078a6/analysis/analysis.json) · [timeline HTML](../round-04-v051/runs/20261016T040743Z-217078a6/analysis/timeline.html) · [timeline JSON](../round-04-v051/runs/20261016T040743Z-217078a6/analysis/timeline.json) · [precision](../round-04-v051/runs/20261016T040743Z-217078a6/analysis/precision.json) · [raw JSON](../round-04-v051/runs/20261016T040743Z-217078a6/capture/startup-latency/benchmark.raw.json) · [cleanup](../round-04-v051/evidence/cleanup.json) · [runner-validation](../round-04-v051/runs/20261016T040743Z-217078a6/capture/startup-latency/runner-validation.json) · [prewarmup](../round-04-v051/runs/20261016T040743Z-217078a6/capture/startup-latency/prewarmup.json)

- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- 这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。

### round-05-v071

归属 limited；master_stat unavailable；独立预热 190.829 ms；清理剩余 0。 实际记录的采集缺口仅为 master_stat:no_readable_start_offset（master_stat 不可用）；下方保留的分析器通用警告不表示本轮已发现 rotation/truncation。

[HTML](../round-05-v071/runs/20261016T040810Z-20f11a40/analysis/report.html) · [CSV](../round-05-v071/runs/20261016T040810Z-20f11a40/analysis/stage-latency.csv) · [JSON](../round-05-v071/runs/20261016T040810Z-20f11a40/analysis/analysis.json) · [timeline HTML](../round-05-v071/runs/20261016T040810Z-20f11a40/analysis/timeline.html) · [timeline JSON](../round-05-v071/runs/20261016T040810Z-20f11a40/analysis/timeline.json) · [precision](../round-05-v071/runs/20261016T040810Z-20f11a40/analysis/precision.json) · [raw JSON](../round-05-v071/runs/20261016T040810Z-20f11a40/capture/startup-latency/benchmark.raw.json) · [cleanup](../round-05-v071/evidence/cleanup.json) · [runner-validation](../round-05-v071/runs/20261016T040810Z-20f11a40/capture/startup-latency/runner-validation.json) · [prewarmup](../round-05-v071/runs/20261016T040810Z-20f11a40/capture/startup-latency/prewarmup.json)

- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- 这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。

### round-06-v051

归属 limited；master_stat unavailable；独立预热 200.633 ms；清理剩余 0。 实际记录的采集缺口仅为 master_stat:no_readable_start_offset（master_stat 不可用）；下方保留的分析器通用警告不表示本轮已发现 rotation/truncation。

[HTML](../round-06-v051/runs/20261016T040838Z-0006bebc/analysis/report.html) · [CSV](../round-06-v051/runs/20261016T040838Z-0006bebc/analysis/stage-latency.csv) · [JSON](../round-06-v051/runs/20261016T040838Z-0006bebc/analysis/analysis.json) · [timeline HTML](../round-06-v051/runs/20261016T040838Z-0006bebc/analysis/timeline.html) · [timeline JSON](../round-06-v051/runs/20261016T040838Z-0006bebc/analysis/timeline.json) · [precision](../round-06-v051/runs/20261016T040838Z-0006bebc/analysis/precision.json) · [raw JSON](../round-06-v051/runs/20261016T040838Z-0006bebc/capture/startup-latency/benchmark.raw.json) · [cleanup](../round-06-v051/evidence/cleanup.json) · [runner-validation](../round-06-v051/runs/20261016T040838Z-0006bebc/capture/startup-latency/runner-validation.json) · [prewarmup](../round-06-v051/runs/20261016T040838Z-0006bebc/capture/startup-latency/prewarmup.json)

- Phase labels are caller-declared, not independently verified against benchmark execution.
- Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.
- Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.
- Phase map is caller-declared, NOT independently verified against benchmark execution.
- 这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。
