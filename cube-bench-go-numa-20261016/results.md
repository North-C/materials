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
