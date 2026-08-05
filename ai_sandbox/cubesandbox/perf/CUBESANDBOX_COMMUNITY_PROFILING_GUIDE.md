# CubeSandbox 社区版创建链路 Profiling 采集指南

适用版本：TencentCloud/CubeSandbox `v0.5.0`，提交 `30b4e25ab16891187c775e002816274427f541f1`

本文说明如何使用社区版本已有的创建阶段插桩，采集 CubeMaster、Cubelet 和 CubeShim 的分段时延，并使用本目录脚本生成统一汇总。

本文只描述社区原生能力。early Probe、MMDS-prime、native code server v3 和后续 Shim 优化均不属于社区 `v0.5.0` 的默认行为。

## 1. 文件清单

| 文件 | 用途 |
|---|---|
| [`run_c50_profile.sh`](./run_c50_profile.sh) | 执行 c50/n500，截取三层日志增量，同时采集 host、进程和 bpftrace 证据 |
| [`analyze_c50_profile.mjs`](./analyze_c50_profile.mjs) | 按 `InstanceId` 关联 benchmark、CubeMaster、Cubelet 和 CubeShim 数据，计算分段统计 |
| [`run_cubesandbox_openeuler_template_perf.sh`](./run_cubesandbox_openeuler_template_perf.sh) | 执行 create-only benchmark、资源门禁和测试后清理 |
| [`sample_c50_host.sh`](./sample_c50_host.sh) | 以固定间隔采集 `/proc` CPU、调度、内存、Shim 和 VMM 数量 |
| [`CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md`](./CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md) | 历史测试结果和热点迁移背景 |

四个脚本均为历史测试使用的原始版本。`run_c50_profile.sh` 调用 benchmark runner 和 host sampler，执行前需要按第 5 节准备运行目录。

## 2. 是否需要开启插桩

不需要额外的 profiling 开关。社区版已经在 Sandbox 创建路径中调用 `RecordCreateMetric` 或 CubeShim `StatDefer`。

只要部署的二进制包含社区 `v0.5.0` 对应源码，创建请求就会自动产生分段数据。采集脚本只负责截取和关联日志，不会给服务动态注入探针。

需要确认以下日志存在且运行用户可读：

```text
/data/log/CubeMaster/cubemaster-req.log
/data/log/Cubelet/Cubelet-req.log
/data/log/Cubelet/Cubelet-stat.log
/data/log/CubeShim/cube-shim-req.log
/data/log/CubeShim/cube-shim-stat.log
/data/log/CubeVmm/vmm.log
```

## 3. 社区原生插桩

### 3.1 创建链路

```text
API benchmark
  -> CubeMaster cube-e2e
     -> Cubelet cubebox-service
        -> sandbox-start
           -> sandbox-create
           -> CubeShim CreatePodSandbox
              -> LaunchVmm / RestoreVm / ResetVm / CreateContainer
        -> sandbox-probe
  -> API response
```

缩进表示通常的包含关系，不表示表中 Avg 或分位数可以直接相加、相减。

对应的默认串行路径可用下列条状图表示。横向位置表示大致先后与包含关系，不代表实际时长比例：

```text
Timeline            |0----------------------------------------------> end
API create total    |[================================================]
cube-e2e            | [==============================================]
cubebox-service     |   [==========================================]
sandbox-start       |    [==========================]
sandbox-create      |    [====================]
CreatePodSandbox    |     [==================]
LaunchVmm/RestoreVm |      [=====]
ResetVm             |            [====]
CreateContainer     |                 [===]
sandbox-probe       |                              [==============]
```

外层长条包含内层阶段；`sandbox-probe` 在社区默认路径中位于 `sandbox-start` 之后。`LaunchVmm` 与 `RestoreVm` 依创建模式二选一。`all-probe` 是 Probe 指标之和，因此不作为独立计时条绘制。

### 3.2 指标及源码位置

| 指标 | 社区源码位置 | 计时含义 |
|---|---|---|
| `cube-e2e` | `CubeMaster/pkg/service/sandbox/sandbox_run.go` 的 `dealMetric`、`setProbeInfo` | CubeMaster 创建上下文开始到创建完成 |
| `all-probe` | 同文件 `setProbeInfo` | 对 Cubelet 返回的全部 `*-probe` 求和，不是新计时器 |
| `cubebox-service` | `Cubelet/services/cubebox/service.go` | Cubelet 创建服务外层 |
| `sandbox-create` | `Cubelet/services/cubebox/cube_container_create.go` 的 `runContainer` | `c.NewTask()` 调用耗时 |
| `sandbox-start` | 同文件 `runContainer` | 从 `c.NewTask()` 前到 `task.Start()` 后的累计耗时 |
| `sandbox-probe` | `Cubelet/services/cubebox/probe.go` 的 `doProbe` | 标准串行 Probe 从启动到成功、失败或超时 |
| 指标命名 | `Cubelet/plugins/workflow/metric.go` | 将索引 `0` 的 `probe/create/start` 转成 `sandbox-*` |
| Shim 分段 | `CubeShim/shim/src/log/stat_defer.rs` | 使用 `StatDefer` 记录 `CalleeAction` 和 `CostTime` |

社区源码可从 [TencentCloud/CubeSandbox v0.5.0](https://github.com/TencentCloud/CubeSandbox/tree/v0.5.0) 查看。

### 3.3 CubeShim 阶段

| `CalleeAction` | 主要实现文件 |
|---|---|
| `CreatePodSandbox` | `CubeShim/shim/src/service/task_srv.rs` |
| `LaunchVmm` / `RestoreVm` | `CubeShim/shim/src/hypervisor/cube_hypervisor.rs` |
| `ResetVm` | `CubeShim/shim/src/sandbox/sb.rs` |
| `CreateContainer` | `CubeShim/shim/src/container/mod.rs` |

CubeShim 的 `StatDefer` 在构造时保存 `Instant::now()`，在显式 `stat()` 或对象析构时输出耗时，目标文件为 `/data/log/CubeShim/cube-shim-stat.log`。

### 3.4 派生指标

报告中的 `task.Start - sandbox-create` 不是社区源码中的独立插桩。

`sandbox-create` 在 `c.NewTask()` 返回后记录；`sandbox-start` 沿用相同起点，在 `task.Start()` 返回后记录。因此可以在同一请求上用二者之差近似表示后半段等待。

该差值仍可能包含 `task.Wait()`、状态处理和调用边界开销，不应写成严格等于 containerd `task.Start()` 函数体耗时。

## 4. 日志和关联方式

CubeMaster、Cubelet 和 CubeShim 各自使用独立日志。分析脚本通过 `InstanceId` 选择同一批 Sandbox，再按阶段字段聚合。

| 数据源 | 阶段字段 | 主要数据 |
|---|---|---|
| CubeMaster response | `ext_info` key | `cube-e2e`、`sandbox-probe`、`all-probe` |
| Cubelet stat | `Callee` | `cubebox-service`、`sandbox-start`、`sandbox-create` 等 |
| CubeShim stat | `CalleeAction` | `CreatePodSandbox`、`RestoreVm`、`ResetVm` 等 |
| benchmark JSON | `create_ms` | API 客户端看到的单请求创建时延 |

Cubelet `reportTrace` 会跳过成功且小于 5ms 的阶段日志。阶段缺行可能表示耗时低于输出阈值，不表示该阶段没有执行。

Cubelet 仍会把已记录指标写入响应 `ExtInfo`，但当前分析脚本的 Cubelet 阶段统计来自 `Cubelet-stat.log`，因此短阶段的 count 可能少于创建实例数。

## 5. 采集前准备

### 5.1 运行节点

脚本必须在实际运行 CubeSandbox 的测试节点上执行。不要在只有源码和报告的开发机上执行。

节点需要满足：

1. CubeMaster、Cubelet、CubeShim、CubeAPI 正常运行；
2. `/data/log` 中的上述日志存在；
3. `http://127.0.0.1:9998/v1/metrics` 可访问；
4. 已安装 Bash、Node.js、`jq`、`rg`、`curl`、`bpftrace`、`ps`、`pgrep`、`systemctl`、`journalctl`、`timeout` 和 `stat`；
5. 执行用户有权读取日志并运行 bpftrace；
6. 已准备 `cube-bench` 可执行文件和有效 Template，测试前资源满足清理门禁。

### 5.2 工具目录

准备独立运行目录：

```text
/path/to/c50-profile-runtime/
└── tools/
    ├── run_cubesandbox_openeuler_template_perf.sh
    └── sample_c50_host.sh
```

可以直接从本目录安装两个脚本：

```bash
PROFILE_RUNTIME=/path/to/c50-profile-runtime
install -d "$PROFILE_RUNTIME/tools"
install -m 755 ./perf/run_cubesandbox_openeuler_template_perf.sh "$PROFILE_RUNTIME/tools/"
install -m 755 ./perf/sample_c50_host.sh "$PROFILE_RUNTIME/tools/"
```

`run_cubesandbox_openeuler_template_perf.sh` 负责 benchmark，并应将启动标记和结果写入 `$OUT_DIR/run.log` 与 `$OUT_DIR/startup-latency/`。

`sample_c50_host.sh` 负责生成 `host-samples.csv`。当前采集脚本固定从 `$BASE_DIR/tools/sample_c50_host.sh` 调用它。

### 5.3 输出目录

每次运行必须使用新的 `OUT_DIR`。采集脚本会删除该目录中的 `run.log`，不要把它指向包含其他资料的共享目录。

推荐命名：

```text
/path/to/results/profile-c50-run1
/path/to/results/profile-c50-run2
/path/to/results/profile-c50-run3
```

## 6. 执行采集

进入本目录所在仓库：

```bash
cd ~/Projects/materials/ai_sandbox/cubesandbox
```

执行标准社区串行 Probe 的 c50/n500 profile：

```bash
sudo env \
  BASE_DIR=/path/to/c50-profile-runtime \
  OUT_DIR=/path/to/results/profile-c50-run1 \
  BENCH=/path/to/cube-bench \
  TEMPLATE_ID=tpl-xxxxxxxxxxxxxxxxxxxxxxxx \
  CASE_NAME=profile-c50-n500 \
  ./perf/run_c50_profile.sh
```

如果 runner 不在 `$BASE_DIR/tools/`，可单独传入：

```bash
sudo env \
  BASE_DIR=/path/to/c50-profile-runtime \
  RUNNER=/path/to/run_cubesandbox_openeuler_template_perf.sh \
  OUT_DIR=/path/to/results/profile-c50-run1 \
  BENCH=/path/to/cube-bench \
  TEMPLATE_ID=tpl-xxxxxxxxxxxxxxxxxxxxxxxx \
  CASE_NAME=profile-c50-n500 \
  ./perf/run_c50_profile.sh
```

非默认部署还可以传入 `API_URL`、`API_KEY` 和 `TAP_TARGET`。这些变量会由采集脚本继续传递给 benchmark runner。

脚本固定向 runner 传入：

```text
RUN_STARTUP=1
RUN_DENSITY=0
RETRY_UNTIL_SUCCESS=0
TAP_TARGET=1000
CASE_MATRIX="profile-c50-n500 50 500"
```

`RETRY_UNTIL_SUCCESS=0` 用于保留真实失败，避免自动重试掩盖可靠性问题。

## 7. 采集过程

`run_c50_profile.sh` 按以下顺序工作：

1. 记录各日志文件的 inode 和字节偏移；
2. 保存运行前的 `/v1/metrics`；
3. 等待 benchmark 输出 `STARTUP_BEGIN`；
4. 并行采集 host 样本、进程快照和 8 秒 bpftrace；
5. 执行 50 并发、500 个正式请求的 benchmark；
6. 保存运行后的 `/v1/metrics`；
7. 根据偏移截取本轮日志增量；
8. 保存 runner 和 watcher 退出码。

如果日志在测试期间发生 rotation，脚本会复制当前文件，并写入 `log-rotation-warnings.txt`。该轮数据需要人工确认是否覆盖完整测试窗口。

## 8. 生成汇总

采集成功后执行：

```bash
node ./perf/analyze_c50_profile.mjs \
  /path/to/results/profile-c50-run1 \
  > /path/to/results/profile-c50-run1/analysis.json
```

快速查看核心字段：

```bash
jq '{
  benchmark,
  correlated_instances,
  cubemaster_stages,
  cubelet_stages,
  shim_stages,
  host_summary
}' /path/to/results/profile-c50-run1/analysis.json
```

输出结构：

| 字段 | 含义 |
|---|---|
| `benchmark` | 500 个正式 API 请求的原始汇总 |
| `benchmark_blocks` | 按请求序号每 50 个一组，用于观察密度增长趋势 |
| `correlated_instances` | 从 Cubelet 根阶段识别并关联的实例数 |
| `cubemaster_stages` | `cube-e2e`、`sandbox-probe`、`all-probe` |
| `cubelet_stages` | 按 Cubelet `Callee` 聚合的阶段 |
| `shim_stages` | 按 CubeShim `CalleeAction` 聚合的阶段 |
| `host_summary` | runnable、blocked、iowait、线程数等峰值 |
| `host_intervals` | 相邻 host 样本计算出的时间序列 |
| `bpftrace` | 当前脚本提取的 migration wait 样本数 |

## 9. 如何理解统计值

每个阶段输出 `count`、`avg`、`p50`、`p95` 和 `max`。

`p95` 使用 nearest-rank：排序后取 `ceil(0.95 * count)` 对应样本。不同阶段独立聚合，因此各阶段 p95 通常不是同一个 Sandbox。

不要用外层 p95 减去内层 p95 构造新阶段，也不要把 CubeMaster、Cubelet 和 CubeShim 的 Avg 直接相加。

标准社区路径中，`sandbox-probe` 在 `runContainer` 后执行，通常可理解为启动后的 readiness 等待。但它仍包含请求构造、连接、重试和 guest 响应时间。

默认 c50/n500 runner 通常先执行 3 个 warmup。日志分段可能关联 503 个实例，而 benchmark 只汇总 500 个正式请求，这是两个不同样本集合。

分析时先检查成功率和 `correlated_instances`，再比较 Avg、P50、P95 和 Max。失败轮次不能仅保留成功样本后作为性能基线。

## 10. 常见问题

### 10.1 等待 STARTUP_BEGIN 超时

确认 runner 将以下标记写入 `$OUT_DIR/run.log`：

```text
STARTUP_BEGIN name=profile-c50-n500
```

同时确认 `CASE_NAME` 与 runner 使用的 case 名称一致。

### 10.2 bpftrace 启动失败

检查执行权限、内核 BTF/符号支持以及 bpftrace 安装。详细错误位于：

```text
$OUT_DIR/evidence/bpftrace-launch.log
```

### 10.3 `correlated_instances` 为 0

确认 `cubelet_stat-delta.log` 包含：

```text
"Action":"Create"
"Callee":"cubebox-service"
"InstanceId":"..."
```

还要检查日志字段大小写。分析脚本按社区结构化日志的 `Action`、`Callee`、`CalleeAction`、`CostTime` 和 `InstanceId` 精确匹配。

### 10.4 CubeMaster 阶段为空

确认 `master-delta.log` 中存在成功响应日志，且 `LogContent` 以 `CreateSandbox_rsp:` 开头。响应 JSON 的 `ext_info` 应包含 `cube-e2e`。

### 10.5 阶段 count 不一致

先区分 warmup、正式请求和失败请求。然后考虑 Cubelet 对成功且小于 5ms 阶段的日志过滤，以及日志 rotation 或丢失。

## 11. 有效结果门禁

建议只将满足以下条件的轮次纳入正式对比：

1. benchmark 达到预期成功数，且未通过自动重试隐藏失败；
2. runner、watcher 退出码均为 0；
3. 没有未解释的日志 rotation；
4. 测试后 Sandbox、Shim、task 和 TAP 占用恢复到基线；
5. 没有 HTTP 408、guest reset timeout 或残留资源；
6. Template、OCI、guest image/kernel 和服务二进制版本已记录。

只有配置受控的重复轮次才能进行单变量归因。跨 Template、guest OS 或核心二进制的结果，只能作为不同环境的观察值。

## 12. 社区能力边界

社区 `v0.5.0` 的 Probe 是串行执行：先完成 VM 和容器启动，再开始 readiness Probe。

early Probe 是后续实验性改动，会改变关键路径，不属于本文启动方式。采集社区基线时不要设置 `CUBESANDBOX_EARLY_PROBE`。

本套脚本使用已有结构化日志做请求级分段，并附带低频 CPU stack sampling。它不等同于持续生产监控，也不提供 guest 内部事件的统一时钟时间线。
