# c100n100：CubeMaster Go 环境与历史 NUMA 恢复实验

**已完成15轮正式c100n100：1500/1500成功、0错误、0超时，45次预热成功，1545个实例均清理。** 整轮中位数为基线508.002ms、Go组合477.626ms（−5.98%）、Go+NUMA组合374.930ms（−26.20%，相对Go组合−21.50%）。这是分块实验中的观测变化，包含重启和系统漂移影响，不是单项参数的因果结论。最终保留800/32/8GiB环境及历史node1约束，服务健康；GOGC实际策略有源码覆盖，见下文。

本报告及同目录文件来自独立执行 session，目标机为 `测试机`。原会话未并行执行远端压测/部署，原 workspace 未提交内容保持不动。原实验执行时没有提交或推送；当前文件为供 materials 仓库发布的脱敏副本。

## 实验边界与身份

- 服务端重新校验为社区 v0.7.1 ARM64，commit `31d911e430fdf8a8879bd062b8e78066c1a8e89d`；二进制、运行进程和三项版本基准容器镜像一致。证据：[version-before.json](version-before.json)。
- 客户端固定 v0.7.1 构建 SHA256 `ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511`，Go 1.25.0 ARM64，trimpath、CGO_ENABLED=0；不把客户端与 master 源码相同当作服务端身份依据。
- 模板 `template-anonymous`，现场 READY，2 vCPU / 2048 MiB / 1 GiB 可写层。模板保存的原始镜像为 `sandbox-code@sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d`；本机镜像 ID `sha256:79972015a4a2b48b18a2165af61606d87e7d859143165fcd33f104fbd8590bee`。没有拉新 sandbox-code 镜像、重建模板或替换服务端二进制。
- 双路 Kunpeng950、384逻辑CPU、4 NUMA节点；cgroup v1。根分区初始约24 GiB可用，本次远端证据在数据盘 `private-path-redacted`。THP enabled/defrag、numa_balancing、静态大页未修改。

## 参数语义与配置

基线现场读取 `/proc` 和 systemd 均为 `GOGC=400, GOMAXPROCS=16, GOMEMLIMIT=4GiB`，没有CPU quota或硬内存限额阻止候选。按交接建议选加倍一档 `800 / 32 / 8GiB`；这是实验候选，不是用户逐项指定的数值。

**GOGC 有应用覆盖。** 部署身份对应的 v0.7.1 `main.go:30` 无条件调用 `debug.SetGCPercent(90)`。Go 官方本地文档说明 SetGCPercent 覆盖初始GOGC；因此环境800不能证明运行时GC目标800，按源码应为90。剥离符号的部署二进制无法用 `go tool objdump`直接反汇编验证，运行时未暴露实时GC百分比。GOMEMLIMIT为Go软内存限制，不是RSS/cgroup硬上限；没有重编译或打补丁改变这些语义。证据：[对应源码](cubemaster-v071-main.go)、[Go文档](go-runtime-semantics.txt)。不能将性能变化归因于GOGC单项，最多比较整套环境配置与其实际生效部分。

NUMA原始映射来自 `测试机 private-path-redacted` 与精确历史docker update记录：五原生服务及八容器全部CPU96–191、节点1。这不是凭空把服务集中到同一节点。详细逐组件历史、oneshot及未启用组件原因见 [numa-history.md](numa-history.md)。

原生服务用 `CPUAffinity=96-191`、`NUMAPolicy=bind`、`NUMAMask=1`恢复；cgroup v1上的AllowedCPUs/AllowedMemoryNodes只作声明，不能单独证明限制。实际验收依靠全线程affinity及numa_maps策略。八容器通过docker cpuset真实约束，并在systemd追加有限轮询ExecStartPost；不会仅限制docker CLI包装进程。在线修改不保证所有既存内存页迁移，hook在未来容器启动后应用约束，存在短启动窗口。

逐状态、逐组件的声明/实际约束/不适用项目见 [configuration-matrix.md](configuration-matrix.md)。最终全线程和容器负载原始证据为 [all-final.json（公开精简快照）](config-snapshot.json)，严格核对记录为 [combined-validation.json](combined-validation.json)。容器某些nginx worker的亲和性是96–191内更小的子集，合法满足限制；初版校验误要求完全相等而拒绝，改为集合包含检查后3178项通过，原拒绝记录保留。采集器随后修正容器exe跨namespace路径解析，重新只读采集最终快照，未改变性能轮数据。

## 方法与计时

每状态5轮。每轮独立c1n3预热，然后 `c100 n100 w0 create-only -no-tui`；正式JSON只含100个请求。轮间固定5秒，清理在正式计时外。每轮在空库存门禁后运行；模板独占声明、CLI前后集合和API清单相互核对，清理仅针对本轮记录的3+100个ID，逐ID保存回执，不做全局清空。

正式整轮时间取 `summary.total_time_s`；不把约20多秒的日志/CLI采集窗口当作创建耗时。请求时延取raw.create_ms，nearest-rank P50/P95/P99；该时延测到HTTP响应头，不等同应用完全就绪。状态比较使用5轮统计的中位数，并列轮间范围；500条请求并非500次独立重复实验。吞吐为100/正式整轮时间。

同一profiler保存Cubelet/Shim/组件日志、Cubelet metrics前后快照、逐阶段统计和HTML profile。没有修改采样工具或为了采样替换服务版本。当前入口未做CubeMaster连续CPU、GC、调度、IO采样；不能据此解释GC次数、停顿、跨NUMA访存或瞬时CPU瓶颈。运行约束采样是单独的只读验收，不是连续性能profile。

## 结果与逐轮证据

# c100n100 三状态数据汇总

状态：**complete**。每状态目标至少5轮；仅 accepted 轮纳入聚合。

| 状态 | 有效轮数 | 整轮ms 中位数[最小,最大] | 请求均值ms | P50ms | P95ms | P99ms | QPS |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline (complete) | 5 | 508.002 [465.367, 530.843] | 355.943 | 381.851 | 502.879 | 505.426 | 196.849 |
| go (complete) | 5 | 477.626 [461.005, 485.658] | 340.199 | 361.112 | 472.615 | 473.240 | 209.369 |
| combined (complete) | 5 | 374.930 [296.704, 414.637] | 278.672 | 293.911 | 372.723 | 373.451 | 266.717 |

上述请求均值/分位数/QPS也是各轮数值的中位数；完整各指标轮间范围、池化请求分位数见 comparison.json。

| 比较（候选−参照） | 整轮ms Δ (%) | 均值ms Δ (%) | P95ms Δ (%) | P99ms Δ (%) | QPS Δ (%) |
|---|---:|---:|---:|---:|---:|
| go_vs_baseline | -30.376 (-5.98%) | -15.744 (-4.42%) | -30.264 (-6.02%) | -32.186 (-6.37%) | 12.519 (6.36%) |
| combined_vs_baseline | -133.073 (-26.20%) | -77.271 (-21.71%) | -130.156 (-25.88%) | -131.975 (-26.11%) | 69.867 (35.49%) |
| combined_vs_go | -102.697 (-21.50%) | -61.527 (-18.09%) | -99.892 (-21.14%) | -99.789 (-21.09%) | 57.348 (27.39%) |

| 状态/轮次 | 验收 | 整轮ms | 均值ms | P50 | P95 | P99 | QPS | 成功/错误/超时 | profile |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| baseline/round-01 | accepted | 508.002 | 371.029 | 412.957 | 502.879 | 505.426 | 196.849 | 100/0/0 | [profile](baseline/round-01/runs/20261016T072437Z-ebbb3767/analysis/report.html) |
| baseline/round-02 | accepted | 509.160 | 355.943 | 381.851 | 504.722 | 507.237 | 196.402 | 100/0/0 | [profile](baseline/round-02/runs/20261016T072509Z-032cdf36/analysis/report.html) |
| baseline/round-03 | accepted | 530.843 | 384.739 | 426.382 | 527.810 | 529.625 | 188.380 | 100/0/0 | [profile](baseline/round-03/runs/20261016T072540Z-8b4b1980/analysis/report.html) |
| baseline/round-04 | accepted | 465.367 | 333.455 | 368.078 | 459.463 | 461.775 | 214.884 | 100/0/0 | [profile](baseline/round-04/runs/20261016T072613Z-25c331fd/analysis/report.html) |
| baseline/round-05 | accepted | 481.649 | 333.746 | 350.571 | 477.068 | 479.823 | 207.620 | 100/0/0 | [profile](baseline/round-05/runs/20261016T072646Z-62d8e2af/analysis/report.html) |
| go/round-01 | accepted | 461.005 | 340.199 | 361.112 | 457.892 | 460.548 | 216.917 | 100/0/0 | [profile](go/round-01/runs/20261016T072818Z-a115f54a/analysis/report.html) |
| go/round-02 | accepted | 485.658 | 339.296 | 346.507 | 482.629 | 484.173 | 205.906 | 100/0/0 | [profile](go/round-02/runs/20261016T072906Z-487b7cbb/analysis/report.html) |
| go/round-03 | accepted | 470.179 | 338.108 | 351.719 | 466.353 | 467.336 | 212.685 | 100/0/0 | [profile](go/round-03/runs/20261016T072939Z-9ee6560c/analysis/report.html) |
| go/round-04 | accepted | 482.888 | 344.724 | 366.321 | 480.239 | 481.744 | 207.088 | 100/0/0 | [profile](go/round-04/runs/20261016T073012Z-caff7bf7/analysis/report.html) |
| go/round-05 | accepted | 477.626 | 359.450 | 387.052 | 472.615 | 473.240 | 209.369 | 100/0/0 | [profile](go/round-05/runs/20261016T073045Z-5a710cc5/analysis/report.html) |
| combined/round-01 | accepted | 414.637 | 293.129 | 329.456 | 408.617 | 412.211 | 241.175 | 100/0/0 | [profile](combined/round-01/runs/20261016T074751Z-bea5ecc6/analysis/report.html) |
| combined/round-02 | accepted | 374.930 | 278.672 | 293.911 | 372.723 | 373.451 | 266.717 | 100/0/0 | [profile](combined/round-02/runs/20261016T074823Z-c7ec9141/analysis/report.html) |
| combined/round-03 | accepted | 387.605 | 289.588 | 324.384 | 381.412 | 384.049 | 257.995 | 100/0/0 | [profile](combined/round-03/runs/20261016T074854Z-d728d071/analysis/report.html) |
| combined/round-04 | accepted | 296.704 | 210.722 | 201.556 | 292.953 | 295.422 | 337.036 | 100/0/0 | [profile](combined/round-04/runs/20261016T074925Z-91f9846d/analysis/report.html) |
| combined/round-05 | accepted | 305.345 | 217.177 | 216.748 | 303.168 | 304.236 | 327.498 | 100/0/0 | [profile](combined/round-05/runs/20261016T074957Z-40d1045d/analysis/report.html) |

| 正式阶段（各轮均值的中位数ms） | baseline | go | combined | 覆盖率中位数 baseline/go/combined |
|---|---:|---:|---:|---|
| API/create | 355.943 | 340.199 | 278.672 | 1.00 / 1.00 / 1.00 |
| Cubelet/cgroup | 66.347 | 56.425 | 22.644 | 0.89 / 0.89 / 0.72 |
| Cubelet/create-sandbox-metadata | 19.592 | 19.937 | 15.943 | 0.76 / 0.75 / 0.64 |
| Cubelet/cube-sandbox-store | 7.090 | 6.128 | 7.167 | 0.11 / 0.04 / 0.04 |
| Cubelet/cubebox | 199.574 | 208.376 | 133.217 | 1.00 / 1.00 / 1.00 |
| Cubelet/cubebox-inner | 41.975 | N/A | 33.081 | 0.01 / N/A / 0.04 |
| Cubelet/cubebox-service | 278.898 | 287.916 | 195.354 | 1.00 / 1.00 / 1.00 |
| Cubelet/cubebox-service-inner | 247.536 | 254.102 | 172.574 | 1.00 / 1.00 / 1.00 |
| Cubelet/gen-spec-sandbox | 11.243 | 14.348 | 9.372 | 0.54 / 0.47 / 0.11 |
| Cubelet/network | 31.443 | 35.492 | 9.338 | 0.64 / 0.72 / 0.42 |
| Cubelet/sandbox-create | 138.054 | 143.134 | 89.913 | 1.00 / 1.00 / 1.00 |
| Cubelet/sandbox-probe | 30.892 | 32.627 | 22.718 | 1.00 / 1.00 / 1.00 |
| Cubelet/sandbox-start | 144.502 | 152.380 | 98.822 | 1.00 / 1.00 / 1.00 |
| Cubelet/storage | 17.302 | 20.025 | 14.365 | 0.80 / 0.87 / 0.74 |
| Cubelet/workflow | 7.496 | 5.233 | 6.632 | 0.12 / 0.05 / 0.14 |
| CubeShim/CreateContainer | 15.620 | 15.440 | 13.560 | 1.00 / 1.00 / 1.00 |
| CubeShim/CreatePodSandbox | 61.270 | 65.140 | 46.980 | 1.00 / 1.00 / 1.00 |
| CubeShim/CreateSandbox | 1.810 | 1.730 | 2.010 | 1.00 / 1.00 / 1.00 |
| CubeShim/LaunchVmm | 1.200 | 1.150 | 1.690 | 1.00 / 1.00 / 1.00 |
| CubeShim/ResetVm | 12.460 | 14.480 | 5.260 | 1.00 / 1.00 / 1.00 |
| CubeShim/RestoreVm | 17.320 | 19.080 | 16.450 | 1.00 / 1.00 / 1.00 |
| CubeMaster/cube-e2e | 287.070 | 294.820 | 202.790 | 1.00 / 1.00 / 1.00 |
| CubeMaster/sandbox-probe | 30.360 | 32.130 | 22.200 | 1.00 / 1.00 / 1.00 |
| CubeMaster/all-probe | 30.360 | 32.130 | 22.200 | 1.00 / 1.00 / 1.00 |
| CubeMaster trace/bufferhandle | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CubeMaster trace/cube-e2e | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CubeMaster trace/cubemaster-inner | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CubeMaster trace/cubemaster-inner-handle | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CubeMaster trace/cubemaster-post-redis | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CubeMaster trace/cubemaster-post-spec | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| Cubelet paired residual/service_outside_cubebox | 86.549 | 86.454 | 30.769 | 1.00 / 1.00 / 1.00 |
| Cubelet paired residual/sandbox_after_newtask | 6.448 | 8.819 | 10.425 | 1.00 / 1.00 / 1.00 |
| Cubelet paired residual/cubebox_outside_task_and_probe | 23.944 | 23.719 | 13.662 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/shim_create_container | 15.620 | 15.440 | 13.560 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/create_request_total | 61.822 | 65.673 | 47.496 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/vm_start_to_agent_ready | 30.311 | 32.128 | 25.305 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/load_spec_cumulative | 0.000 | 0.000 | 0.000 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/sandbox_finish_cumulative | 46.410 | 48.350 | 33.550 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/container_finish_cumulative | 61.280 | 65.140 | 46.980 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/sandbox_to_container_finish | 16.130 | 16.010 | 14.160 | 1.00 / 1.00 / 1.00 |
| CreateContainer detail/guest_receive_to_restore_branch | 0.425 | 0.542 | 0.167 | 0.99 / 0.99 / 0.99 |
| CreateContainer detail/normal_add_devices | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CreateContainer detail/normal_add_storage | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CreateContainer detail/normal_setup_bundle | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CreateContainer detail/normal_init_container | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CreateContainer detail/normal_start_container | N/A | N/A | N/A | 0.00 / 0.00 / 0.00 |
| CreateContainer detail/restore_path_unresolved | 15.180 | 14.898 | 13.545 | 0.99 / 0.99 / 0.99 |
| Cubelet/cube-storage-db | N/A | 6.644 | 5.625 | N/A / 0.01 / 0.01 |
| Cubelet/appsnapshot | N/A | N/A | 7.063 | N/A / N/A / 0.01 |
| Cubelet/createid | N/A | N/A | 8.083 | N/A / N/A / 0.03 |
| Cubelet/images | N/A | N/A | 5.795 | N/A / N/A / 0.01 |
| Cubelet/netfile | N/A | N/A | 6.664 | N/A / N/A / 0.07 |
| Cubelet/volume | N/A | N/A | 5.814 | N/A / N/A / 0.01 |

全部阶段的分组、逐轮原始统计、覆盖率、timing_kind、包含关系和绝对/相对变化见 stage-comparison.json。

口径与局限：

- 每状态目标至少5轮；状态统计只纳入原始字段、预热、归属和清理全部通过的轮次。失败/缺失轮保留，不补零。
- 整轮耗时来自正式 summary.total_time_s，不是采集窗口、请求最大值或请求时延之和。
- 请求时延从构造请求到HTTP响应头，不等于应用就绪。预热为独立进程c1n3，不复用正式HTTP连接。
- 各轮分位数及池化分位数用nearest-rank；500请求共享5轮环境，不能当作500个独立实验。
- 阶段记录保留formal/warmup/unknown_phase与覆盖率；成功且不足5ms的Cubelet阶段可能不记录，缺失不等于0。
- 阶段间有包含关系，不可累加；阶段P95之差不代表该阶段贡献；客户端seq不能逐条映射服务器实例。
- Go三参数同时调整，只能比较参数组合；按状态顺序测试可能受到缓存、进程年龄和时间漂移影响。
- timeout只按原始明确错误文本分类；未提供完整失败文本时为未知，不把全部错误归类超时。

## 已获得的 Cubelet CPU / GC / 内存快照

现有30份Prometheus快照来自Cubelet端口9998。每轮前后差分的CPU累计秒增量中位数（范围）为：基线23.92（19.17–25.75）、Go组合26.09（23.91–26.67）、组合9.91（9.49–11.36）；GC观测数增量中位数均为1，STW累计暂停增量中位数分别0.413、0.458、0.363ms。详细逐轮内存、goroutine、线程前后值及HELP/TYPE语义见 [cubelet-metrics.md](cubelet-metrics.md) 与 [cubelet-metrics.json](cubelet-metrics.json)。

这些差分覆盖约21–22秒采集窗口（Go一轮37.09秒），包括正式创建和CLI/后台工作；不能除以0.3–0.5秒正式时长当CPU利用率，也不是RSS峰值或CubeMaster GC证据。组合期间Cubelet窗口CPU消耗下降与主路径改善方向一致，但仍受前述重启/缓存/窗口工作量影响，不单独建立NUMA因果。

## 启动恢复与异常证据

NUMA切换首次执行在Egress启动前检查处返回非零：其既有prepare脚本只等Cubelet bootstrap 60秒。Cubelet当时正在恢复历史网络状态；没有运行第三组压测，也没有全局清理旧TAP/BPF数据。Cubelet约07:34:17 UTC首次启动，07:40:29完成4002条TAP检查，随后同步扫描stale policy maps；07:45:43记录 `keep=4002 deleted=0` 并报告成功启动640.79秒，07:46:05完成HTTP/gRPC、Egress和节点1/1健康门禁。首次启动至boot约11分26秒。

恢复期间Cubelet NRestarts=1、Egress NRestarts=10。这些真实暂态失败已保留，不能写成服务切换零故障。Cubelet源码先re-exec再终止父进程，启动脚本提前记录父PID会触发一次systemd重试；与既有基线和现场证据一致。扫描持续推进、无对应OOM/内核告警，后续静默阶段由最终GC完成日志证实；因此采用有上限等待保留恢复进度，未反复重启或抹掉配置。未超出预定07:50 UTC回退截止点即恢复可用，故没有执行回滚。不能据此宣称NUMA对恢复耗时完全无影响。

证据：[启动调查结论](numa-history/startup-current/RESULT.md)、首次配置日志（原始私有证据未公开）、就绪采样（原始私有证据未公开）、节点清单（原始私有证据未公开）。第三组数据均在服务恢复之后采集。

## 最终状态与清理

最终[final-check.json](final-check.json)确认15轮、1545个互异ID全部清理，API库存空，按完整ID扫描无对应进程，CubeShim进程为0；13个长期服务active。八容器image ID与实验前相同，服务端[版本复核](version-final.json)仍一致。模板前后只有本次查询生成的requestID不同，镜像digest、rootfs、资源和其余create_request未变：template-comparison.json（原始私有证据未公开）。THP、numa_balancing、静态大页维持原值。

组合第3轮在正式JSON已写出后，额外只读采样一个CLI确认的本轮预热sandbox：22个Shim线程含VMM/vCPU线程，全部CPU96–191、主线程映射策略bind:1。其实际cpuset仍在根0–383/0–3，页面分布跨NUMA节点，不等于全部已有内存迁移到node1；这是样本验收而非全部1545实例的逐线程证明。证据：[combined-sandbox-round03.json](combined-sandbox-round03.json)。采样在正式计时后，未加到正式创建耗时；第一次试图采已清理round1未找到live实例也保留为unavailable。

## 归因限制

前两组/proc/loadavg的总调度实体约6040→21900，API空库存并不代表宿主回收已完全稳定。组合开始前已回落约5949；组合期间一次分类采样显示约11944个实体中7779为kworker，不能将此前全部增长倒推为同一原因，也不能断言沙箱泄漏。第一、二组共1030个ID在组合前已确认无对应进程。组合前3轮375–415ms、后2轮297/305ms，仍有明显轮间变化；5秒轮间间隔不足以证明完全静默。

Go组合虽客户端中位数改善约6%，但Cubelet cubebox-service阶段均值中位数278.898→287.916ms、传播的CubeMaster cube-e2e287.070→294.820ms反而上升；不能据此声称核心服务路径全面改善。更细的precision batch样本和Master trace缺失项应按覆盖率理解。独立审计见[data-audit.md](data-audit.md)。

这是一台机器按baseline→Go→Go+NUMA顺序执行的分块试验，包含服务重启、进程年龄、缓存热度和系统漂移的影响。尤其NUMA恢复必须重启Cubelet并经过历史网络状态恢复，不能把前后全部差异归因于NUMA本身。未进行无界参数搜索，三Go变量一起改动不能区分单项贡献。小幅差异和重叠范围不应写成确定的优化收益。

阶段表保留正式集合覆盖率与缺失值；Cubelet部分成功短阶段不记日志，缺失不能填零。阶段父子嵌套、并行与传播值不相加；P95之差不是阶段贡献。CubeMaster trace缺失项明确标N/A；官方客户端无法将请求seq逐条映射到sandbox ID，组件与请求只做集合级比较。

## 备份、恢复与数据位置

公开复现方法与新一轮快照/回滚脚本见 [配置方法与脚本](CONFIGURATION.md)。原实验私有回退备份及 `restore.sh` 未公开；下列记录仅解释原实验的恢复能力，不能从本公开包直接执行。

原unit/drop-in共40个文件已保存时间及SHA256：backup-manifest.json（原始私有证据未公开）。独立新增drop-in及systemd control属性修改均保留diff；原服务文件、镜像与二进制未替换。远端私有目录含原始配置和备份，权限受限，不应直接发布。**该目录还包含容器systemd ExecStartPost正在引用的container_cpuset.py，保留组合配置期间不要删除该目录；如需清理目录，应先执行恢复移除hook。**

原实验私有目录中的 `restore.sh rollback-all` 可恢复实验前配置；`rollback-numa`只撤回NUMA、保留较高Go环境；`rollback-go`只撤回Go环境。脚本不依赖CubeAPI可用，不删除任何沙箱，容器按all-before.json逐个恢复原cpuset；任何恢复错误会记录并返回非零，仍需检查端口、节点覆盖与服务健康。恢复Cubelet可能再次触发历史TAP/eBPF恢复，不能仅凭active认定完成。回滚脚本已语法审查，正常完成时不执行回滚，保留用户要求的最终组合。

每轮原始JSON：`<state>/round-NN/runs/<timestamp>/capture/startup-latency/benchmark.raw.json`；profile：同轮`analysis/report.html`与`analysis.json`；清理：`<state>/round-NN/evidence/cleanup.json`。逐轮可点击profile链接和完整绝对/相对比较表见上文，机器可读汇总为[comparison.json](comparison.json)、[rounds.csv](rounds.csv)、[stage-comparison.json](stage-comparison.json)。
