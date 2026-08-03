# CubeSandbox 分段时延 Profiling 汇总

整理日期：2026-08-03

## 1. 文档目的与范围

本文合并仓库中 2026-07-23 至 2026-07-29 针对 CubeSandbox Template 创建路径进行的分段时延测试。重点场景是 ARM64 节点上的 `create-only c50n500`：50 并发、500 个正式请求、3 个 warmup，创建完成后保留实例，因而同一轮也是从 0 逐步增长到 503 个 2U2G MicroVM 的密度测试。

纳入以下四类证据：

1. CubeMaster/Cubelet/CubeShim 结构化日志中的创建阶段耗时；
2. TAP 上的 TCP/HTTP readiness 抓包；
3. host 上的 CPU、调度和 vCPU wakeup-to-run 观测；
4. 针对最终热点进行的 OCI、Probe 和 CubeShim A/B。

普通吞吐矩阵、Snapshot/Clone/Pause/Resume 延迟和 ARM64 定时器正确性实验不属于同一条 Template 创建分段口径，本文只在它们能解释创建关键路径时引用。`perf record`/`perf stat` 轮次属于 CPU profiling，不提供请求级阶段拆分，也不并入分段表。

## 2. 结论摘要

1. 历次 profile 一致表明，`RestoreVm`、`ResetVm` 和 `CreateContainer` 的直接执行时间通常是个位数到十几毫秒，不能单独解释早期 200-400ms 的端到端时延；主要等待位于 guest 恢复后到 readiness 首次成功之间。
2. 7 月 23 日最早的两段观测中，`cube-e2e` avg 为 260.72ms，Probe avg 为 90.50ms；7 月 27 日完整 profile 进一步把长尾关联到逐步升高的 guest 密度和无效 MMDS 轮询。
3. 关闭 host NUMA balancing 并把 Probe 调整为 100ms 后，稳定基线约为 241.47ms。通过 MMDS-prime 在 guest 时钟恢复后停止 envd 的无效 MMDS 轮询，三轮均值降到 202.72ms，改善 16.05%。
4. early HTTP Probe 使 readiness 与 VM/容器启动重叠，但单独只能把两轮均值降到 196.21ms；它证明串行等待可优化，却不是剩余时延的唯一来源。
5. native code server v3 在 Template 构建时等待 envd 健康后才监听 49999，并让 restore 后的 `/health` 命中快照内 readiness cache。配合 early Probe 时四轮 c50 avg 均值为 134.31ms；关闭 early Probe、保留同一 v3 Template 后为 138.63ms。v3 是平均时延达标的主要条件，early Probe 的主要收益体现在吞吐和极端长尾。
6. 7 月 29 日继续细分后发现，Snapshot restore 路径中重复建立 init-log vsock 连接及空 `CreateContainer` RPC 成为新的热点。复用已有连接并在严格无传播配置时跳过空 RPC 后，`task.Start - sandbox-create` avg 从 35.28ms 降到 0.95ms，最终 c50 三轮 avg 为 78.60ms、吞吐为 502.93/s。
7. 各层阶段存在包含和并行关系，不能相加。尤其 early Probe 的 `sandbox-probe` 从提前启动到健康响应，内部覆盖 RestoreVm、ResetVm 和容器启动。

## 3. 统一计时模型

### 3.1 创建链路

```text
API 创建请求
  -> CubeMaster cube-e2e / sandbox-probe
  -> Cubelet cubebox-service
       -> sandbox-start / sandbox-create
       -> CubeShim CreatePodSandbox
            -> LaunchVmm
            -> RestoreVm
            -> ResetVm
            -> CreateContainer / task.Start
       -> host 经 TAP 发起 HTTP readiness Probe
            -> TCP connect
            -> GET /health:49999
            -> guest code server / envd ready
  -> CubeMaster 返回创建成功
```

默认串行路径先完成 VM/容器启动，再执行 Probe。early Probe 路径让 Probe 与 `runContainer` 并行，但仍要求两条分支都成功后才返回。

### 3.2 指标含义

| 指标 | 计时范围 | 关系 |
|---|---|---|
| API 创建总延迟 | benchmark 客户端发起请求到收到成功响应 | 最外层；正式请求 500 个 |
| CubeMaster `cube-e2e` | CubeMaster 单实例创建主路径 | 接近 API 总延迟，但边界不同 |
| CubeMaster/Cubelet `sandbox-probe` | Probe 启动到首次接受健康结果 | 默认路径近似后置等待；early 路径与启动阶段重叠 |
| Cubelet `cubebox-service` | Cubelet 单实例创建服务主路径 | 包含启动、Probe 及外围处理 |
| Cubelet `sandbox-start` | Cubelet 启动 sandbox 的内部路径 | 包含 Shim 创建主路径及 Cubelet 开销 |
| Shim `CreatePodSandbox` | Shim 创建/恢复 MicroVM 主路径 | 包含 RestoreVm、ResetVm 等子阶段 |
| Shim `RestoreVm` / `ResetVm` | 恢复 VMM 状态 / 校正 guest 状态 | `CreatePodSandbox` 子阶段 |
| Shim `CreateContainer` | restore 后容器侧准备 | Shim 子阶段；后期进一步细分到 `task.Start` |

结构化日志关联包含 3 个 warmup，因此阶段统计通常是 503 个实例；API benchmark 汇总只包含 500 个正式请求。不同层使用的时钟、日志边界和毫秒取整不同，数值应按趋势解释，不应通过相减构造未经采集的“剩余阶段”。

### 3.3 固定环境与主要变量

7 月 27 日后的主线测试均在 `192.168.25.90` ARM64 节点执行，host 为 192 物理核/384 逻辑 CPU、4 NUMA node，使用 openEuler guest image/kernel、2U2G Template、1GiB writable layer、1000 个预创建 TAP。主要变量依次为：

| 阶段 | 主要变量 |
|---|---|
| 早期基线 | host NUMA balancing、Probe period/timeout |
| MMDS-prime | OCI 内 envd 的 MMDS 轮询生命周期 |
| early Probe | Probe 启动时机、delay 和 period |
| native code server | 49999 readiness 状态机及 envd 健康缓存 |
| Shim 优化 | init-log vsock 连接复用、空 CreateContainer RPC |

各轮使用的 Template 和 OCI 版本并不完全相同。下表用于展示热点如何迁移，不代表一次只改变一个变量的严格全因子实验；只有原报告明确标记为同 Template/同运行态 A/B 的结果才能用于单项归因。

## 4. 历史测试与结果

### 4.1 2026-07-23：最早的 e2e/Probe 两段观测

Template `tpl-67ae0b72bad044bba4394490` 的 quick-Probe 轮次首次导出了 503 个实例的 `e2e` 和 `probe` 阶段：

| 指标 | avg | p50 | p95 | p99 | max |
|---|---:|---:|---:|---:|---:|
| CubeMaster e2e | 260.72ms | 254ms | 385ms | 440ms | 460ms |
| Probe | 90.50ms | 81ms | 163ms | 179ms | 200ms |

同轮 API 正式请求为 500/500，avg 269.54ms、p95 389.09ms、QPS 167.04。随后两轮 API avg 分别为 253.98ms 和 242.43ms，但未归档阶段汇总，不能把第一轮的 Probe 分布直接套用到后两轮。

这一阶段已确认 Probe 是显著组成部分，但两段数据还不足以判断 Probe 自身在消耗 CPU，还是在等待 guest 服务就绪。

### 4.2 2026-07-27：四层日志关联建立完整基线

后续分析脚本按 InstanceId 关联 CubeMaster、Cubelet 和 CubeShim 日志，并统一输出 avg/p50/p95/max。主要单轮 profile 如下，单位均为 ms：

| 轮次 | API avg / p95 | Master e2e avg | Master Probe avg | Cubelet service avg | Cubelet start avg | Shim Pod avg | Restore avg | Reset avg | CreateContainer avg |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 初始完整 profile | 385.91 / 1500.28 | 376.00 | 248.18 | 369.62 | 114.19 | 103.36 | 25.59 | 30.78 | 3.25 |
| NUMA balancing off | 264.38 / 690.02 | 255.86 | 206.26 | 249.56 | 36.83 | 27.06 | 9.11 | 5.42 | 2.42 |
| period/timeout=20ms | 279.88 / 463.11 | 271.73 | 226.68 | 266.20 | 32.85 | 23.95 | 8.06 | 5.00 | 2.10 |
| period/timeout=100ms | 241.87 / 668.20 | 233.49 | 180.07 | 225.27 | 38.41 | 28.55 | 9.55 | 5.82 | 2.58 |
| MMDS-prime profile | 206.01 / 585.86 | 196.92 | 106.63 | 188.71 | 74.14 | 50.71 | 17.98 | 11.86 | 4.54 |
| MMDS-prime + 去空 health connect | 207.74 / 606.12 | 199.35 | 106.32 | 191.01 | 76.66 | 53.72 | 23.26 | 11.17 | 3.80 |
| MMDS-prime + early Probe d75/p20 | 199.38 / 308.12 | 191.84 | 178.84 | 185.57 | 38.27 | 28.25 | 8.49 | 8.43 | 1.83 |

所有表中轮次均为 500/500 成功。初始完整 profile 的 host 一度出现 runnable 303、blocked 699、iowait 峰值约 66%，属于明显受扰动的单轮观测；后续稳定基线以 period/timeout=100ms 的三轮均值 241.47ms 为准，而不是把 385.91ms 当作稳定对照。

20ms Probe 比 100ms Probe 更慢，说明过短 timeout/period 会产生重试放大。`RestoreVm`、`ResetVm` 和 `CreateContainer` 的直接耗时仍远小于 Master/Cubelet Probe，热点已收敛到 guest readiness 与高密度背景负载。

### 4.3 MMDS-prime：消除 ready VM 的持续背景干扰

基础 OCI 的 envd 0.5.13 每 50ms 轮询当前平台未提供的 Firecracker MMDS。随活跃 VM 增长，该行为持续制造 WFI、arch timer、virtio-net IRQ 和调度压力。单 ready VM 对照中，原始 envd 的 WFI exits 约为 359.6/s；`SIGSTOP envd` 后约 17.4/s，`-isnotfc` 后约 35/s。

MMDS-prime 在 Template 构建/ResetVm 窗口保留轮询，guest realtime 恢复并越过绝对 deadline 后停止轮询。三轮稳定结果为：

| 轮次 | 成功 | API avg | p95 |
|---|---:|---:|---:|
| run1 | 500/500 | 199.59ms | 586.34ms |
| run2 | 500/500 | 202.92ms | 576.71ms |
| run3 | 500/500 | 205.64ms | 579.15ms |
| 均值 | 1500/1500 | 202.72ms | 580.73ms |

相对 241.47ms 稳定基线，avg 降低 38.75ms（16.05%）。完整 profile 中 host runnable 峰值从 100ms 基线轮的约 201 降至 24，证明已消除大规模背景竞争。

直接关闭 MMDS、1ms 取消和 20ms grace 虽然部分成功样本更快，却出现 HTTP 408、`reset guest time failed` 或残留 shim，不能纳入有效优化结果。性能数字必须与 500/500 成功和清理门禁一起解释。

### 4.4 Probe 路径：重叠有效，但不是全部根因

early Probe 将 host/TAP HTTP Probe 提前到 `runContainer` 之前，使其与 RestoreVm、ResetVm 和容器启动重叠。MMDS-prime OCI 上的主要 A/B 为：

| 配置 | 成功 | API avg | p95 | QPS |
|---|---:|---:|---:|---:|
| delay=50ms, period=100ms | 500/500 | 202.35ms | 346.08ms | 212.91 |
| delay=75ms, period=100ms | 500/500 | 197.75ms | 317.89ms | 212.25 |
| delay=50ms, period=20ms | 500/500 | 204.79ms | 282.26ms | 214.40 |
| delay=75ms, period=20ms run1 | 500/500 | 193.05ms | 306.77ms | 214.48 |
| delay=75ms, period=20ms profile | 500/500 | 199.38ms | 308.12ms | 211.31 |
| delay=100ms, period=20ms | 500/500 | 195.71ms | 330.85ms | 208.70 |

delay=75ms/period=20ms 两轮 avg 均值为 196.21ms，仅比 MMDS-prime 稳定均值改善 6.50ms（3.21%）。该 profile 的 `sandbox-probe` avg 约 179ms，但它从 Probe 提前启动开始计时，覆盖了约 38ms 的 `sandbox-start`，二者不能相加。

### 4.5 TAP/HTTP 抓包：Probe 主要在等待 guest 响应

对 503 个 TAP 的 readiness 流量抓包并关联实例后得到：

| 网络阶段 | avg | p95 |
|---|---:|---:|
| TCP connect | 69.30ms | 100.89ms |
| HTTP request-to-response | 35.43ms | 192.93ms |
| 首个 SYN 到首个响应 | 92.85ms | 295.39ms |
| 首个 SYN 到客户端最终接受的响应 | 172.13ms | 678.73ms |

每个 TAP 平均发送 1.423 次请求。100ms client timeout 会取消一部分最终能够返回的请求，但延长到 200/600ms、缩短到 20ms、hedged Probe 和连接/响应 timeout 分离均未改善平均时延。这说明 Probe 更多是在观测 guest 尚未可服务，而不是自身构成全部等待。

### 4.6 vCPU 调度跟踪：排除普遍性 host 唤醒瓶颈

同配置下的 bpftrace 记录了 c50 中 vCPU wakeup-to-run：vCPU0 78,228 次，avg 7.284us；vCPU1 84,905 次，avg 2.690us。绝大多数样本为 1-4us，约 16,364 次 migration；只有 vCPU0 的两个极端样本把 max 拉到 148.45ms。配套 benchmark 为 500/500、avg 197.16ms。

因此不能把约 179ms readiness 普遍归因于 host vCPU runnable-to-running 或 affinity 延迟。证据仍未闭合 guest 内部从时钟恢复、envd 首次调度、监听 49999 到处理首个 SYN 的统一时间线。

### 4.7 Native code server v3：将 readiness 状态保存进快照

v3 在 guest 内先轮询 envd `:49983/health`，首次得到 2xx 后才监听 49999；`envdReady=true` 和 listener 随 Template 一起进入快照。restore 后 `/health` 只读取 readiness cache，不再让每个高频外部 Probe 同步串联一次 envd HTTP 请求。

| 配置 | 成功 | avg 均值 | p95 均值 | p99 均值 | QPS 均值 |
|---|---:|---:|---:|---:|---:|
| v3 + early Probe d0/p5，4 轮 | 2000/2000 | 134.31ms | 234.93ms | 317.54ms | 317.55 |
| 同一 v3 Template，关闭 early Probe，4 轮 | 2000/2000 | 138.63ms | 231.93ms | 524.55ms | 264.02 |

关闭 early Probe 后 avg 只增加 4.32ms（3.22%），但 p99 增加 207.01ms、QPS 降低 16.86%。这说明 v3 承担了平均时延的主要优化，early Probe 更明显地改善批次完成时间和极端长尾。

这一阶段没有归档与前述格式完全一致的四层 `analysis.json`，因此不能把 134.31ms 或 138.63ms 进一步拆成同口径的 Restore/Reset/Probe 表。它们只用于端到端演进和机制 A/B。

### 4.8 2026-07-29：Shim 内部阶段继续细分

在 v3 Template 基础上继续分析发现，Snapshot restore 已建立 guest-agent 控制连接，但 `task.Start` 仍同步建立第二条 vsock 连接用于 init 日志；同时，无传播配置时 `CreateContainer` RPC 仍启动 guest 子进程进入 mount namespace，却不执行实际挂载或卸载。

最终实现仅在 Snapshot restore 时复用已有日志连接，并且只在 OCI spec 同时缺少 `cube.propagation.exec.mounts` 与 `cube.propagation.container.umounts` 时跳过空 RPC：

| 阶段 | 优化前 avg / p95 | 优化后 avg / p95 | avg 改善 |
|---|---:|---:|---:|
| `task.Start - sandbox-create` | 35.28 / 196.23ms | 0.95 / 2.57ms | -34.33ms / -97.3% |
| Shim `CreateContainer` | 19.09 / 152ms | 0.08 / 1ms | -19.01ms / -99.6% |

最终 c50n500 三轮全部 500/500，API avg 分别为 76.51、78.92 和 80.37ms，均值 78.60ms；p95 均值 136.72ms，吞吐均值 502.93/s。该结果还通过 c1n20、串行 create+run_code 10/10 和 c20 create+run_code 100/100 门禁。

## 5. 热点迁移总览

| 演进阶段 | 代表性 c50 avg | 主要热点判断 | 后续动作 |
|---|---:|---|---|
| 7/23 quick Probe | 269.54ms | Probe 是显著组成部分，尚不能区分观察与消耗 | 增加跨服务日志关联 |
| 7/27 稳定 100ms Probe 基线 | 241.47ms | 高密度下 readiness 长尾；VM 子操作较短 | 查 ready VM 背景负载 |
| MMDS-prime | 202.72ms | 消除 envd/MMDS 持续 IRQ 后，剩余在 guest readiness | 并行 Probe、网络抓包 |
| early Probe d75/p20 | 196.21ms | 串行量化等待只占小部分 | 优化 guest 49999 readiness 状态机 |
| native code server v3 | 134.31ms | 外部 Probe 不再重复串联 envd | 验证关闭 early Probe |
| v3，early Probe 关闭 | 138.63ms | 平均值稳定，p99/吞吐仍受 500ms 串行 Probe 影响 | 深挖 Shim 启动路径 |
| Shim 连接/RPC 优化 | 78.60ms | `task.Start` 与空 `CreateContainer` 热点基本消除 | 进入新的亚 100ms 基线 |

从 241.47ms 稳定基线到 78.60ms 最终结果，avg 共降低 162.87ms（67.45%）。该数字是整条方案演进的结果，不应解释为三个独立改动百分比可直接相乘；其中 Template、OCI、Probe 调度和 Shim 均发生过变化。

## 6. 已排除或拒绝的方向

| 方向 | 结果 | 结论 |
|---|---|---|
| Probe 20ms timeout/period | avg 279.88ms | 重试放大，负优化 |
| timeout 200/600ms | avg 约 257-263ms | 不能消除 guest 未就绪 |
| hedged HTTP Probe | avg 269.22ms | 请求放大 |
| guest 内 containerd exec `curl` | 500/500，avg 438.42ms | exec/agent/进程创建成本过高 |
| 完全关闭/激进停止 MMDS | 成功样本更快但出现 reset timeout/408 | 不满足可靠性门禁 |
| KVM halt poll 1ms/2ms | 无稳定收益 | 拒绝 |
| ready VM CPU shares 下调 | 无稳定收益 | 拒绝 |
| Cubelet GOMAXPROCS=64 | avg 198.22ms | 无收益 |
| CPU pinning | 普遍 wakeup-to-run 仅微秒级 | 没有证据支持继续投入 |
| GICv4-only | 收益约在轮间波动内，后续两次主机异常重启 | 稳定性不可接受 |

## 7. 结论边界与后续复测要求

1. 只有 500/500 成功、无 HTTP 408/`reset guest time failed`、测试后 sandbox/shim/task/TAP-in-use 归零的轮次才可作为有效性能结果。
2. API、Master、Cubelet、Shim 和网络阶段的起止边界不同；early Probe 引入并行后尤其禁止把阶段 avg 相加。
3. p95 不能替代极端尾部。关闭 early Probe 的 v3 A/B 中 p95 略低，但 p99、max 和批次总时长明显变差。
4. Template 保存 guest 进程、listener、timer 和 readiness cache 的运行态。更换 OCI、envd、VMM、时间恢复方式或重新构建 Template 后，历史数字不能直接外推。
5. 下一轮若要继续做统一分段，应在同一 InstanceId 上补齐 guest 内部事件：ResetVm 发起/完成、vCPU 首次进 guest、guest clock 恢复、envd 首次调度、49999 listen、首个 SYN、accept、首个 health response。所有事件需要可换算到同一时钟域。
6. 最终 Shim 优化后的 78.60ms 是当前新的端到端基线，但尚缺同轮完整四层 `analysis.json`。后续复测应沿用现有分析格式，才能确定新热点转移到 CubeMaster/Cubelet 外围、网络还是 guest 内其他路径。

## 8. 证据索引

| 内容 | 路径 |
|---|---|
| 7/23 quick-Probe 分段汇总 | `remote-results/template-create-perf-20260723/quick-probe-c50-r1/stage-summary.json` |
| 7/23 quick-Probe 原始逐实例数据 | `remote-results/template-create-perf-20260723/quick-probe-c50-r1/stages.jsonl` |
| 初始完整 profile | `artifacts/c50-optimization-20260727/baseline-profile-2/analysis.json` |
| NUMA balancing off | `artifacts/c50-optimization-20260727/experiments/numa-balancing-off-run1/analysis.json` |
| 20ms Probe | `artifacts/c50-optimization-20260727/experiments/existing-template-probe20/run1/analysis.json` |
| 100ms Probe 完整 profile | `artifacts/c50-optimization-20260727/probe100-full-profile/analysis.json` |
| MMDS-prime 完整 profile | `artifacts/c50-optimization-20260727/envd-mmds-prime/profile-c50/analysis.json` |
| 去空 health connect profile | `artifacts/c50-optimization-20260727/shim-no-unused-health-connect/profile-c50/analysis.json` |
| early Probe d75/p20 profile | `artifacts/c50-optimization-20260727/early-external-http-probe-overlap/v2-delay75-period20/profile-c50-run1/analysis.json` |
| readiness 初步原因分析 | `CUBESANDBOX_READINESS_INITIAL_ROOT_CAUSE_ANALYSIS_20260728.md` |
| C50 优化完整报告 | `CUBESANDBOX_C50_OPTIMIZATION_REPORT_20260727.md` |
| native v3、early Probe 关闭 A/B | `artifacts/c50-optimization-20260727/native-code-server-v3/no-early-probe-20260728/SUMMARY.md` |
| 400 QPS / Shim 优化 | `CUBESANDBOX_TEMPLATE_400QPS_OPTIMIZATION_20260729.md` |
| 分段采集脚本 | `scripts/run_c50_profile.sh` |
| 分段关联分析脚本 | `scripts/analyze_c50_profile.mjs` |

