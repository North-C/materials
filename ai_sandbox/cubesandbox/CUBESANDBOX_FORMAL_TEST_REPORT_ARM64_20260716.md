# CubeSandbox v0.5.0 ARM64 正式测试报告

测试日期：2026-07-16  
测试节点：`root@192.168.25.90`  
结果目录：`/home/lyq/cube-bench-formal-arm64-2c4g-20260716-212309`

## 1. 验收结论

本次测试结论为：**SDK 内部 benchmark 通过，CubeSandbox 核心操作性能验收不通过。**

- `scripts/cube_bench_sdk.py` 正式套件共 19 项，19 项通过，完整输出均通过 SDK `files.read` 保存。
- Template 创建延迟与密度命令已按官方文章的 `cube-bench` 参数执行，成功请求可形成统计数据，但创建成功率仅为 93.8%～97.5%，未达到性能基准所需的稳定性前提。
- 官方 Snapshot / Rollback / Clone / Pause-Resume 矩阵共 25 条命令，0 条完成目标操作测量；全部在 Sandbox 创建或 VM 恢复阶段失败。
- 主要错误为 `reset guest time failed`、`reset reseed random dev failed`、`context deadline exceeded`，并伴随失败 shim 无法自动回收。
- 测试结束后已恢复 `tap_init_num=500`，移除临时 postcheck 配置；当前 Sandbox、运行时 Snapshot、残留 shim 均为 0，Cubelet、network-agent、CubeAPI、CubeProxy 均为 `active`。

因此，当前集群可以运行单个及部分连续 SDK benchmark，但不具备可信执行官方核心操作性能基准的稳定性，不能据此判定集群核心性能达标。

## 2. 测试环境

| 项目 | 配置 |
| --- | --- |
| 架构 | ARM64 / `aarch64` |
| CPU | Kunpeng 950 7592C，2 Socket，384 逻辑 CPU，4 NUMA 节点 |
| 内存 | 2.2 TiB |
| 内核 | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray` |
| 数据盘 | `/dev/nvme3n1`，2.9T，XFS，挂载到 `/data/cubelet` |
| CubeSandbox | v0.5.0 |
| 测试镜像 | `cube-bench-suite:upstream-arm64-20260716-build-noperf` |
| Docker image ID | `sha256:be5ca179ddb9de93d296a43d96fd2084de0e5d064b349f0ca0215eb9a03a9905` |
| Registry digest | `sha256:67f24e83e6c0a516c868e7bb90cee246f76ef134e94ec3af3b36b62a122af173` |
| 镜像归档 SHA256 | `b23c5640d9348922c85ebcdd9aff3cce537233a587e3dcaeb524b5547289bb26` |

正式模板统一使用 2 CPU、4096 MiB 内存和 2G writable layer：

| 用途 | Template ID | Probe |
| --- | --- | --- |
| SDK 正式测试 | `tpl-b0263dbe2d1040b0b224b0cd` | `49983/health`（envd） |
| 官方核心操作矩阵 | `tpl-d5418702228547e8824d3495` | `49999/health`（与官方文章一致） |

两个模板均引用同一 registry digest，Template 信息返回 `cpu=2000m,mem=4096Mi` 和 `READY`。

## 3. SDK 正式套件

状态：**19/19 通过**。首次连续运行完成 17 项后，下一次 Sandbox 创建返回 408；清理 1 个失败 shim 后补跑 Node 和 Java 两项并合并为完整结果集。

### 3.1 Sysbench Memory

固定参数：2 线程、1G block、100G total size、最长 30 秒。

| 模式 | 吞吐 MiB/s | 平均延迟 ms | P95 ms |
| --- | ---: | ---: | ---: |
| 顺序读 | 35281.96 | 57.96 | 58.92 |
| 顺序写 | 48605.47 | 41.97 | 42.61 |
| 随机读 | 632.50 | 3233.14 | 3386.99 |
| 随机写 | 714.79 | 2861.95 | 3095.38 |

### 3.2 Sysbench Prime

固定 2 线程、30 秒。

| max-prime | events/s |
| ---: | ---: |
| 1000 | 338105.13 |
| 2000 | 116925.20 |
| 3000 | 62768.27 |
| 5000 | 30988.84 |
| 10000 | 12340.17 |
| 20000 | 5012.56 |
| 30000 | 2950.36 |
| 50000 | 1508.10 |
| 100000 | 600.96 |

### 3.3 语言运行时

| Benchmark | 指标 | 结果 |
| --- | --- | ---: |
| Go | build average | 36353558250 ns/op |
| Go | http average | 24702 ns/op |
| Go | json average | 13822897 ns/op |
| Go | garbage average | 4833869 ns/op |
| PHP Benchmark Suite | score | 765609 |
| Node Octane | 完成 | exit code 0 |
| Java SciMark | Composite | 2207.75 |
| Python pyperformance | 完整 rigorous 套件 | exit code 0 |

Go Build 正常执行，日志中未出现 `perf` 或 `permission denied` 错误。

## 4. Template 创建性能

使用官方 `examples/cube-bench` v0.5.0 源码和文章中的 `create-only` 参数；每档 3 次 warm-up，成功请求的延迟如下。错误请求不计入延迟分位数，但计入成功率。

| 并发 | 请求数 | 成功率 | avg ms | p95 ms | p99 ms | max ms | 吞吐/s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 20 | 95.0% | 123.3 | 178.2 | 178.2 | 178.2 | 1.07 |
| 10 | 200 | 97.5% | 156.9 | 194.6 | 225.6 | 229.3 | 10.58 |
| 20 | 300 | 97.0% | 181.7 | 240.4 | 277.4 | 305.5 | 15.38 |
| 50 | 500 | 97.2% | 227.1 | 320.1 | 381.5 | 865.2 | 27.31 |

失败请求主要返回 `CubeMaster error 130595: context deadline exceeded`。每档失败数与测试后残留 shim 数一致或接近，说明失败路径没有可靠回收 VM 运行时。

## 5. 单机密度

按文章命令累计请求 100 / 300 / 500 / 1000 个 Sandbox。由于创建失败和异步回收，实际管理实例数没有达到请求目标。

| 请求累计目标 | 实际管理实例 | shim 数 | 可用内存下降 MiB | 按管理实例均摊 MiB |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 100 | 98 | 1386.36 | 13.86 |
| 300 | 242 | 240 | 3798.88 | 15.70 |
| 500 | 388 | 393 | 6398.82 | 16.49 |
| 1000 | 831 | 843 | 14141.57 | 17.02 |

最后一批 500 请求成功率为 93.8%，并出现 `tap fd unavailable`。测试后管理面清理为 0，但仍有 48 个失联 shim；network-agent 状态中发现 1012 个 `z10.100.*` TAP。已备份状态、删除 CubeSandbox TAP 和池状态，并从零重建到默认 500。

内存均摊结果说明空载实例的物理内存开销约为 14～17 MiB，但由于实例数、shim 数不一致且目标 1000 未达成，该数据只能作为观察值，不能作为通过的密度验收结果。

## 6. 核心操作矩阵

严格使用官方文章对应的 v0.5.0 脚本和参数，共执行 25 条命令：

- Snapshot 制作并发：3 档。
- Dirty Page：8 档。
- 基于 Snapshot 创建：4 档。
- Rollback：3 档。
- Clone：4 档。
- Pause / Resume：3 档。

结果：**0/25 完成目标操作测量**。错误统计包含 30 次 `context deadline exceeded`、24 次 `reset guest time failed` 和 2 次 `reset reseed random dev failed`。所有命令均在 Sandbox 创建/恢复准备阶段失败，不能产生 Snapshot、Rollback、Clone 或 Pause/Resume 延迟数据。

在密度测试之前，使用同规格的 envd-probe 模板曾获得两组诊断数据：Snapshot `c=1` wall avg 75.6 ms，`c=5` wall avg 97.9 ms；`c=10` 连续 10 次完整尝试均因创建失败而中止。这些数据不属于最终严格 `49999` 模板矩阵，仅用于说明故障随创建次数放大。

## 7. 根因判断

证据链如下：

1. 镜像在 Docker 中同时正常监听 49983 和 49999，SDK 正式 benchmark 也曾 19/19 完成，排除 benchmark 二进制和 entrypoint 的静态构建错误。
2. Cubelet 日志显示失败 VM 的 agent 和容器可以在几十毫秒内启动，但随后 readiness 探针持续 30 秒不可达。
3. 失败路径随后出现 ttrpc 超时，无法 kill/delete task，并留下不在 CubeMaster 管理面中的 shim。
4. 更换为文章要求的 49999 probe 后问题仍存在，排除单一 envd 端口故障。
5. 从零重建 TAP 池后仍出现 `reset guest time` ttrpc 超时，说明 TAP 池污染会放大故障，但不是唯一根因。

当前最可能的问题是 CubeSandbox v0.5.0 ARM64 的 VM Snapshot 恢复/guest agent 控制通道在连续创建和高密度负载后的稳定性缺陷。该问题发生在 benchmark 目标操作之前。

## 8. 建议

1. 在维护窗口重启计算节点，清除无法由 Cubelet/network-agent 服务重启完全恢复的 KVM/guest 运行态；重启需单独审批，本次未执行。
2. 重启后先执行至少 100 次串行 create-delete 稳定性门禁，要求 100% 成功、CubeMaster=0 时 shim=0，再重新跑核心性能矩阵。
3. 向 CubeSandbox 社区提交 ARM64 问题，附带 `reset guest time`、`reset reseed random dev`、probe timeout、failover shim 泄漏和 `tap fd unavailable` 日志。
4. 在修复前不要用重试后的成功样本替代正式数据；核心操作基准要求准备阶段本身稳定，否则分位数不可信。

## 9. 结果产物

- SDK 完整结果：`sdk-formal-complete/`
- SDK CSV：`sdk-formal-complete/benchmark-summary.csv`
- SDK 归档：`sdk-formal-complete.tar.gz`
- Template 创建与密度原始结果：`core-perf-probe49983-attempt/`
- 官方核心矩阵逐命令结果：`core-perf/`
- TAP 池恢复证据：`core-runtime-recovery/`
- 官方脚本 SHA256：`official-benchmark-scripts.sha256`
- 官方 ARM64 cube-bench SHA256：`cube-bench-binary.sha256`

测试方法来源：[CubeSandbox 核心操作性能基准测试报告](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)。
