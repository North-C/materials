# CubeSandbox Profiling 指标与社区源码对照

更新日期：2026-08-06

## 1. 目的与适用范围

本文解释 `scripts_v2/run_c50_profile.sh` 和 `scripts_v2/analyze_c50_profile.mjs` 输出的创建阶段指标，逐项说明它们来自哪一份日志、由哪段社区源码计时、计时窗口实际包含什么，以及指标之间是顺序、包含、传播还是派生关系。

### 源码版本

本文基于 TencentCloud CubeSandbox 社区版 `v0.5.1`：

| 项目 | 值 |
|---|---|
| 上游项目 | `TencentCloud/CubeSandbox` |
| 发布标签 | `v0.5.1` |
| Git commit | `a164417f497234a0d787cb328b0ae96480b1569b` |
| Commit 日期 | `2026-07-11` |
| Commit 标题 | `chore: bump image tag from v0.5.1-rc12 to v0.5.1 (#915)` |

路径约定：本文中的 `CubeMaster/...`、`Cubelet/...`、`CubeShim/...` 和 `agent/...` 源码链接，均以 CubeSandbox `v0.5.1` 源码根目录为基准；`scripts_v2/...` 链接则以 profiling 工具目录的上一级为基准。链接不依赖本地源码检出目录的名称。

本文引用的 CubeMaster、Cubelet、CubeShim 和 Guest Agent 指标源码均与该标签提交一致。early Probe、MMDS、native code server 等后续实验性改动不属于本文的基线语义。若线上二进制不是基于 `v0.5.1` 的上述 commit 构建，或 `/etc/cubelet/config.toml` 覆盖了社区默认 workflow，必须先核对部署版本和配置，不能只凭同名指标推断代码边界。

## 2. 从源码到 `analysis.json` 的数据路径

| `analysis.json` 区域 | 原始数据 | 采集脚本位置 | 汇总方式 |
|---|---|---|---|
| `benchmark.create` | `cube-bench` 创建请求结果 | [`run_cubesandbox_openeuler_template_perf.sh`](scripts_v2/run_cubesandbox_openeuler_template_perf.sh#L251) | 直接读取正式请求的 `create_ms`；不含 3 个 warmup |
| `cubemaster_stages` | `/data/log/CubeMaster/cubemaster-req.log` 中 `CreateSandbox_rsp:` 的 `ext_info` | [`run_c50_profile.sh`](scripts_v2/run_c50_profile.sh#L22) | 解析 `cube-e2e`、`sandbox-probe`、`all-probe` |
| `cubelet_stages` | `/data/log/Cubelet/Cubelet-stat.log` | [`run_c50_profile.sh`](scripts_v2/run_c50_profile.sh#L22) | 按 `Callee` 分组 `CostTime` |
| `shim_stages` | `/data/log/CubeShim/cube-shim-stat.log` | [`run_c50_profile.sh`](scripts_v2/run_c50_profile.sh#L22) | 按 `CalleeAction` 分组 `CostTime` |
| `create_container_detail` | `cube-shim-req.log` 的精简事件流，加上 Shim Stat 日志 | [`run_c50_profile.sh`](scripts_v2/run_c50_profile.sh#L114) | 按 `InstanceId` 关联边界，再计算直接时延和诊断残差 |
| `host_summary` / `host_intervals` | `/proc/stat`、`/proc/loadavg`、`/proc/meminfo` 和进程数 | [`sample_c50_host.sh`](scripts_v2/sample_c50_host.sh#L16) | 对相邻采样点求 counter 差值和峰值 |
| `bpftrace` | 19 Hz on-CPU 栈采样 | [`run_c50_profile.sh`](scripts_v2/run_c50_profile.sh#L53) | 当前只汇总包含 `migration_entry_wait` 的 VM kernel 样本数 |

分析器先从 Cubelet 中选择 `Action=Create && Callee=cubebox-service` 的记录，将其 `InstanceId` 作为本轮关联集合，再过滤 Cubelet、CubeShim 和 CubeMaster 数据。实现见 [`analyze_c50_profile.mjs`](scripts_v2/analyze_c50_profile.mjs#L533)。因此，`correlated_instances` 是成功进入 Cubelet 结构化创建计时链的实例数，不等同于客户端正式请求数。

## 3. 创建链路和真实执行关系

社区默认配置见 [`Cubelet/config/config.toml`](Cubelet/config/config.toml#L145)。Engine 逐个执行 step，同一步中的 action 通过 `errgroup` 并行执行，见 [`engine.go`](Cubelet/plugins/workflow/engine.go#L334) 和 [`engine.go`](Cubelet/plugins/workflow/engine.go#L412)。默认创建链路是：

```text
cube-bench Create API
└─ CubeMaster CreateSandbox: cube-e2e
   └─ Cubelet RunCubeSandbox: cubebox-service
      ├─ step 1: createid || appsnapshot                       并行
      ├─ step 2: images || volume || storage || network ||
      │          netfile || cube-sandbox-store                 并行
      ├─ step 3: cgroup
      └─ step 4: cubebox
         ├─ gen-spec-sandbox
         ├─ create-sandbox-metadata
         ├─ sandbox-start                                      累计窗口
         │  └─ sandbox-create                                  NewTask 窗口
         │     └─ CubeShim CreatePodSandbox                    Shim 外层
         │        ├─ LaunchVmm
         │        ├─ RestoreVm                                 Template 路径
         │        ├─ connect_agent                             无独立 StatDefer
         │        ├─ ResetVm
         │        ├─ CreateSandbox
         │        └─ CreateContainer
         │           └─ Guest Agent do_create_container
         └─ sandbox-probe                                      task.Start 后执行
```

这里的 `||` 表示同一步并行。尤其要注意：`network`、`storage` 是 `cubebox-service` 内、`cubebox` 之前的兄弟 action，不是 `cubebox` 的子阶段。当前 v2 `stage-latency.csv` 将它们缩进到 `cubebox` 下是旧版展示模型，不能据此认定源码包含关系；应以本节和实际部署的 Cubelet workflow 配置为准。

## 4. 通用统计口径

### 4.1 `count/avg/min/p50/p95/max`

分析器把日志中的 `CostTime` 转为毫秒数，按阶段分组后输出样本数、均值、最小值、P50、P95 和最大值。分位数采用 nearest-rank，源码见 [`analyze_c50_profile.mjs`](scripts_v2/analyze_c50_profile.mjs#L37)。

这些统计不是请求时间线本身。父阶段和子阶段的 P95 可能来自不同的 InstanceId，不能用汇总后的 P95 相减；要做阶段差值，必须先在同一 InstanceId 内相减，再对差值求统计量。

### 4.2 为什么阶段 `count` 可能小于 503

Cubelet 会记录所有 `CreateContext` metric，但写 `Cubelet-stat.log` 时会跳过“成功且小于 5 ms”的记录：

```go
if m.Error() == nil && m.Duration() < 5*time.Millisecond {
    continue
}
```

对应源码为 [`service.go`](Cubelet/services/cubebox/service.go#L412)。所以 `network.count=60` 或 `storage.count=24` 的含义是“分别有 60、24 个可见的 5 ms 以上样本”，不是只有这些请求执行了该 action。对这类阶段，日志 Avg 是慢样本条件均值，不能当作全体请求 Avg。

CubeShim 的 `StatDefer` 没有这个 5 ms 过滤，作用域退出时总会写一条整数毫秒记录，见 [`stat_defer.rs`](CubeShim/shim/src/log/stat_defer.rs#L74)。

### 4.3 500 与 503

`run_c50_profile.sh` 固定执行 `c50n500`，runner 先做 3 个 warmup。客户端 `benchmark.create` 只统计 500 个正式请求，而组件日志通常包含 warmup，因此常见 `count=503`。不同样本集合之间不能逐项相减。

## 5. CubeMaster 指标

### 5.1 指标来源

CubeMaster 在 `CreateSandbox` 入口保存 `startTime`，返回前由 defer 调用 `setProbeInfo()`，实现见 [`sandbox_run.go`](CubeMaster/pkg/service/sandbox/sandbox_run.go#L101) 和 [`sandbox_run.go`](CubeMaster/pkg/service/sandbox/sandbox_run.go#L645)。成功响应被写成 `CreateSandbox_rsp:<json>`；分析器从其中的 `ext_info` 读取三个字段，见 [`analyze_c50_profile.mjs`](scripts_v2/analyze_c50_profile.mjs#L558)。

| 输出指标 | 源码产生方式 | 实际代码含义 | 关系与限制 |
|---|---|---|---|
| `cube-e2e` | `time.Since(c.startTime).Milliseconds()` | 从 CubeMaster `CreateSandbox` 函数入口到返回 defer 执行时的服务端总时延，包含选机、调用 Cubelet、响应组装等 | 位于客户端 API 窗口内，但两端时钟和边界不同，不能用 API Avg 直接减它解释网络耗时 |
| `sandbox-probe` | Cubelet 响应 `ExtInfo` 中同名 key 被原样复制 | Cubelet 实际执行的 readiness Probe 时延 | 传播副本，不是 CubeMaster 又执行了一次 Probe；不能与 Cubelet `sandbox-probe` 相加 |
| `all-probe` | 对 Cubelet `ExtInfo` 中所有包含 `-probe` 的值求和 | 所有容器 Probe metric 的聚合值 | 单容器 Template 通常等于 `sandbox-probe`；它不是额外阶段 |

CubeMaster 还会向自己的 Trace 日志写一个 `CalleeAction=cube-e2e` 的计时，见 [`sandbox_run.go`](CubeMaster/pkg/service/sandbox/sandbox_run.go#L475)。当前分析器没有使用这条 Trace，而是使用响应 `ext_info`。两者名称相同，不应混为两个阶段。

## 6. Cubelet 指标

### 6.1 指标如何生成和改名

Cubelet `RunCubeSandbox` 在服务入口开始计时，defer 中记录 `cubebox-service`、生成派生 metric 并异步输出 Trace，见 [`service.go`](Cubelet/services/cubebox/service.go#L237)。每个 workflow action 则由 Engine 围绕 `flow.Create()` 计时，以 `flow.ID()` 作为 `Callee`，见 [`engine.go`](Cubelet/plugins/workflow/engine.go#L426)。

容器内部 metric 会根据 container index 改名。index `0` 被命名为 `sandbox`，例如：

| 原始 ID | sandbox 容器输出名 |
|---|---|
| `CubeNewContainerId` | `create-sandbox-metadata` |
| `CubeContainerSpecId` | `gen-spec-sandbox` |
| `create` | `sandbox-create` |
| `start` | `sandbox-start` |
| `probe` | `sandbox-probe` |

改名逻辑见 [`metric.go`](Cubelet/plugins/workflow/metric.go#L27)。非零 index 会生成 `container-N-*`。

### 6.2 各阶段源码边界

| `cubelet_stages` 名称 | 计时源码 | 计时开始与结束 | 如何理解 |
|---|---|---|---|
| `cubebox-service` | [`service.go`](Cubelet/services/cubebox/service.go#L237) | `RunCubeSandbox` 服务逻辑开始，到函数返回 defer | Cubelet 服务最外层，包括所有 workflow step、响应组装前的大部分逻辑 |
| `createid`、`appsnapshot`、`images`、`volume`、`storage`、`network`、`netfile`、`cube-sandbox-store`、`cgroup`、`cubebox` | [`engine.go`](Cubelet/plugins/workflow/engine.go#L412) | 每个 plugin 的 `flow.Create()` 调用前后 | action 自己的完整执行时间；同一步 action 可能并行，不能把同一步 Avg 相加 |
| `network` | [`network/plugin.go`](Cubelet/network/plugin.go#L139) | network delegate `Create` 全函数 | TAP 路径包括配置解析、`EnsureNetwork`、分配结果和本地 metadata 同步；核心 RPC 见 [`plugin_tap.go`](Cubelet/network/plugin_tap.go#L429) |
| `storage` | [`storage/local.go`](Cubelet/storage/local.go#L742) | storage plugin `Create` 全函数 | 包括 volume 准备、restore memory volume URL 预取、backend metadata 写入；其中准备和预取并行 |
| `cubebox` | [`cube_container_create.go`](Cubelet/services/cubebox/cube_container_create.go#L87) | cubebox plugin `Create` 全函数 | 容器 spec、containerd container/task 创建、启动、Probe 和后处理的外层窗口 |
| `gen-spec-sandbox` | [`cube_container_create.go`](Cubelet/services/cubebox/cube_container_create.go#L245) | 生成该容器 spec 前后 | sandbox OCI spec 构造，不是 Shim 阶段 |
| `create-sandbox-metadata` | [`cube_container_create.go`](Cubelet/services/cubebox/cube_container_create.go#L1214) | `l.client.NewContainer()` 前后 | containerd container metadata 创建；发生在 `NewTask` 之前 |
| `sandbox-create` | [`cube_container_create.go`](Cubelet/services/cubebox/cube_container_create.go#L1243) | `c.NewTask()` 前后 | containerd NewTask 调用窗口；首次 sandbox task 会进入 CubeShim `TaskService.create`，因此包含 Shim `CreatePodSandbox` |
| `sandbox-start` | [`cube_container_create.go`](Cubelet/services/cubebox/cube_container_create.go#L1243) | 与 `sandbox-create` 使用同一 `taskStart`，结束于 `task.Start()` 和状态更新之后 | 累计窗口，包含 `sandbox-create`、`task.Wait()`、`task.Start()` 和状态更新；不能与 `sandbox-create` 相加 |
| `sandbox-probe` | [`probe.go`](Cubelet/services/cubebox/probe.go#L82) | `doProbe` 入口到 Probe 结果确认 | 包括参数校验、initial delay、TCP/Ping/HTTP 尝试、重试和结果等待；社区默认路径在 `runContainer` 成功后调用，调用顺序见 [`cube_container_create.go`](Cubelet/services/cubebox/cube_container_create.go#L287) |
| `cubebox-service-inner` | [`service.go`](Cubelet/services/cubebox/service.go#L361) | `cubebox-service - probeMetric - volumeMetric` | 数学派生残差，不对应连续代码块；`volumeMetric` 这里只累计 `images` 和 `volume` 两类 ID，不包括 `storage` |
| `cubebox-inner` | 同上 | `cubebox - 所有 sandbox/container 前缀 metric 之和` | 数学派生残差；内部 metric 有嵌套时可能重复扣减，不应当作严格的“未打点代码耗时” |

`sandbox-start - sandbox-create` 可以在同一 InstanceId 上近似定位 `task.Wait + task.Start + 状态更新`，但不能直接用两个汇总 P95 相减。

## 7. CubeShim 指标

### 7.1 `StatDefer` 的公共语义

CubeShim 所有这些阶段都使用 [`StatDefer`](CubeShim/shim/src/log/stat_defer.rs#L55)：构造时保存 `Instant::now()`，对象离开作用域时以 `elapsed().as_millis()` 写 `CostTime`。因此：

- 单位是整数毫秒，小于 1 ms 会显示为 0；
- 正常路径调用 `set_ok()`，异常路径仍会由 `Drop` 写记录，但 Ret 不同；
- 当前分析器按 `Action=Create` 和 `InstanceId` 过滤，没有再按 Ret 过滤，正式解读前应同时确认压测无失败。

### 7.2 各 `CalleeAction` 的代码窗口

| `shim_stages` 名称 | 计时源码 | 实际包含内容 | 明确不包含或容易误读的部分 |
|---|---|---|---|
| `CreatePodSandbox` | [`task_srv.rs`](CubeShim/shim/src/service/task_srv.rs#L86) | 首次 task create 的 Shim 最外层：load spec、sandbox lock、sandbox 初始化、VM/Agent/sandbox 创建、container 创建和 TaskCreate event 发送 | 初始 action 名是 `CreatePodContainer`，发现 `!sb.inited()` 后改成 `CreatePodSandbox`；它不是单独一个 RPC |
| `CreatePodContainer` | 同上 | sandbox 已初始化时的 task create 外层窗口 | Template 首容器通常是 `CreatePodSandbox`；后续容器才可能出现本名称 |
| `LaunchVmm` | [`cube_hypervisor.rs`](CubeShim/shim/src/hypervisor/cube_hypervisor.rs#L75) | `VmmInstance::new(vmm_config)` 和本地状态设置 | timer 在 vmm config 和通知 channel 准备之后才开始 |
| `RestoreVm` | [`cube_hypervisor.rs`](CubeShim/shim/src/hypervisor/cube_hypervisor.rs#L173) | 向 Cloud Hypervisor 发送 `ApiRequest::VmRestore` 并等待响应 | CH mutex 获取发生在 timer 之前；snapshot metadata 校验和 `RestoreConfig` 准备位于外层 [`sb.rs`](CubeShim/shim/src/sandbox/sb.rs#L838)，也不在该指标内 |
| `CreateVm` | [`cube_hypervisor.rs`](CubeShim/shim/src/hypervisor/cube_hypervisor.rs#L113) | 冷启动路径的 `ApiRequest::VmCreate` | Template restore 正常不走此分支；CH mutex 获取和 config 转换在 timer 之前 |
| `BootVm` | [`cube_hypervisor.rs`](CubeShim/shim/src/hypervisor/cube_hypervisor.rs#L126) | 冷启动路径的 `ApiRequest::VmBoot` 和状态设置 | Template restore 正常不走此分支；CH mutex 获取在 timer 之前 |
| `ResetVm` | [`sb.rs`](CubeShim/shim/src/sandbox/sb.rs#L402) | `SetGuestDateTime`、读取 RNG、`ReseedRandomDev` 两个 Agent RPC | Agent client mutex 获取在 timer 之前，所以其锁等待不在 `ResetVm` 内 |
| `CreateSandbox` | [`sb.rs`](CubeShim/shim/src/sandbox/sb.rs#L436) | Agent `CreateSandbox` 请求构造、client 锁等待、RPC、OOM watcher 和 VM monitor 启动 | `start_vm`、`connect_agent`、`ResetVm`、add_device、storage/DNS 收集在 timer 之前，不包含在该指标内 |
| `CreateContainer` | [`container/mod.rs`](CubeShim/shim/src/container/mod.rs#L429) | Agent `CreateContainerRequest` 构造、client 锁等待、完整 ttrpc、Guest 处理、RPC 返回和 Shim `ContainerState` 更新 | 它不是 Guest 单一函数的纯执行时间；其中包含跨进程通信和排队 |
| `addDev-*` | [`cube_hypervisor.rs`](CubeShim/shim/src/hypervisor/cube_hypervisor.rs#L197) | 对应设备的 `VmAddDevice` 请求 | 动态名称；是否出现取决于 Template 和设备配置 |

`CreatePodSandbox` 的主要顺序可由 [`sb.rs`](CubeShim/shim/src/sandbox/sb.rs#L436) 直接读出：`start_vm -> connect_agent -> agent is ready -> ResetVm -> CreateSandbox`，返回 `TaskService.create` 后再执行 `CreateContainer`。

## 8. `create_container_detail` 指标

这些字段不是全部来自 `shim-stat`。采集脚本还从 `cube-shim-req.log` 保留一组文本 marker，分析器在同一 InstanceId 内配对，具体实现见 [`analyze_c50_profile.mjs`](scripts_v2/analyze_c50_profile.mjs#L375)。

### 8.1 `direct_timings_ms`

| 字段 | 源码 marker / timer | 计算方式 | 实际含义 |
|---|---|---|---|
| `shim_create_container` | Shim `CreateContainer` 的 `StatDefer` | 直接读取 `CostTime` | 第 7.2 节所述完整 Shim/Agent RPC 窗口 |
| `create_request_total` | `create req start` 与 `create req finish`，见 [`task_srv.rs`](CubeShim/shim/src/service/task_srv.rs#L91) | 同一 Shim 日志时钟的两个 RFC3339 时间戳相减 | 整个 `TaskService.create` 外层，与 `CreatePodSandbox` 近似同窗，但边界和精度不同 |
| `vm_start_to_agent_ready` | `start vm start`，见 [`sb.rs`](CubeShim/shim/src/sandbox/sb.rs#L781)；`agent is ready`，见 [`sb.rs`](CubeShim/shim/src/sandbox/sb.rs#L446) | 同一 Shim 日志时钟相减 | 跨越 LaunchVmm、restore/boot、必要的 ready 等待和 `connect_agent`；是重叠窗口，不能再与这些子阶段相加 |
| `sandbox_finish_cumulative` | `start sandbox finish at:<ms>`，见 [`task_srv.rs`](CubeShim/shim/src/service/task_srv.rs#L137) | `TaskService.create` 的同一个 `Instant` 从 T0 累计 | T0 到 `sb.create_sandbox()` 返回的位置，不是独立子阶段 |
| `container_finish_cumulative` | `start container finish at:<ms>`，见 [`task_srv.rs`](CubeShim/shim/src/service/task_srv.rs#L156) | 同上 | T0 到 `sb.create_container()` 返回的位置，不是独立子阶段 |
| `sandbox_to_container_finish` | 上述两个累计值逐实例相减 | `container_finish - sandbox_finish` | sandbox 完成后的 container 创建窗口，与 `shim_create_container` 近似同窗 |
| `guest_receive_to_restore_branch` | Guest `[cube-strace]recv create container` 到 `create container by restore` | 使用 Guest JSON 内嵌的 `ts` 相减 | Guest handler 收到请求后，复制/转换 OCI spec、读取 annotation 并决定进入 restore 分支的时间 |

`load spec finish at:<ms>` 也会写入逐实例 JSONL 的 `load_spec_cumulative_ms`，源码见 [`task_srv.rs`](CubeShim/shim/src/service/task_srv.rs#L101)，但当前没有进入 `direct_timings_ms` 汇总。

### 8.2 Guest restore 分支和诊断残差

Guest 的 restore 分支位于 [`agent/src/rpc.rs`](agent/src/rpc.rs#L157)：

```text
recv marker
-> grpc_to_oci
-> 读取 annotation
-> restore branch marker
-> 获取 sandbox mutex
-> 查找快照容器 PID
-> start_exec_process
   -> 获取 WAIT_PID_LOCKER
   -> spawn helper
   -> wait helper 退出
-> RPC 返回
```

`guest_receive_to_restore_branch` 只覆盖图中的前三个箭头。它不包含 Shim 到 Guest 的请求传输、restore branch 之后的 mutex/PID 查找、`start_exec_process` 或 RPC 返回。

`diagnostic_residual_ms.restore_path_unresolved` 的公式是：

```text
Shim CreateContainer - Guest receive_to_restore_branch
```

这是跨层外窗口减内窗口后的剩余量，混合了 Shim 请求构造、client lock、RPC 发送/返回、Guest branch 后处理和 Shim 状态更新。它只能说明“热点仍在这些未拆开的部分中”，不能命名为 `start_exec_process` 实测时延。

`start_exec_process` 的社区源码见 [`container.rs`](agent/rustjail/src/container.rs#L1670)，helper 入口见 [`rootfs.rs`](agent/cube/src/rootfs.rs#L82)。`exec a child process` 与 `exec process start` 目前只作为 marker coverage；Guest stdout/stderr 经 wrapper 异步转发，分析器不会用其外层到达时间做时延相减。

### 8.3 normal-create 路径

非 restore 路径会在 Guest 打印一条五段汇总日志，源码见 [`agent/src/rpc.rs`](agent/src/rpc.rs#L198)。分析器将其放入 `normal_path_agent_timings_ms`：

| 字段 | Guest 实际代码范围 |
|---|---|
| `add_devices` | 调整 OCI spec 中的设备，使其对应 Guest 内真实设备 |
| `add_storage` | 挂载 rootfs/volume，并把 mount 结果写入 sandbox 状态；包含 sandbox mutex 等待 |
| `setup_bundle` | namespace/device-cgroup/hooks 更新、写 bundle spec、构造 `CreateOpts` |
| `init_container` | `LinuxContainer::new` 和 `Process::new` |
| `start_container` | log forwarding 配置、`open_io`、`ctr.start`、shared pidns 和容器状态登记 |

五个字段都使用 `as_millis()`，会分别向下取整；它们不包含函数开头和各 timer 切换间的全部零碎逻辑。日志之后的 `start_time_sync_task()` 也不在五段内，但仍位于外层 Shim `CreateContainer` RPC 中，因此五段之和不要求等于 `shim_create_container`。

## 9. Host、BPF 和其他证据

这些数据用于解释并发压力，不是请求级阶段：

| 输出/文件 | 数据来源 | 如何理解 |
|---|---|---|
| `host-samples.csv` | Linux `/proc/stat`、`/proc/loadavg`、`/proc/meminfo`，以及 `pgrep` | 原始 CPU counter、调度队列、内存和 shim/VMM 进程数；采样间隔默认 100 ms |
| `host_intervals` | 分析器对相邻 `/proc` 样本求差 | `busy_pct`、`system_pct`、`iowait_pct`、context switch/s 等是 host 时间区间指标，不能关联到某个 InstanceId |
| `bpftrace-profile.txt` | 19 Hz profile probe | `cubelet/cubemaster/network-agent` 采 kernel+user stack，vCPU/VMM 线程采 kernel stack；样本数近似 on-CPU 时间占比，不是毫秒时延 |
| `bpftrace.migration_entry_wait_samples` | BPF 输出中匹配 `migration_entry_wait` 的 VM kernel 样本 | 只表示采样命中次数；19 Hz 下不能把一次命中直接换算为一次请求等待 |
| `process-snapshot-*.txt` | `ps -eLo` | 每秒一次进程/线程快照，用于查看 runnable、wchan、CPU 占用和进程增长 |
| `metrics-before.prom` / `metrics-after.prom` | Cubelet `127.0.0.1:9998/v1/metrics` | 压测前后 Prometheus 快照；当前分析器不对它们做阶段时延汇总 |
| `vmm-delta.log` / `api-delta.log` | CubeVmm/CubeAPI 增量日志 | 保留作审计；当前 `analysis.json` 的阶段表没有直接解析它们 |

## 10. 阅读结果时的判断顺序

1. 先确认 `benchmark.successful/errors`、runner 退出码和组件 Ret，避免把失败路径混进基线。
2. 再看 `correlated_instances` 和各阶段 `count`。500/503 差异通常来自 warmup；Cubelet 子阶段 count 偏小通常来自 5 ms 日志阈值。
3. 先比较外层窗口：API、`cube-e2e`、`cubebox-service`、`cubebox`、`sandbox-start`/`CreatePodSandbox`。
4. 只在明确的父窗口内看子阶段，不把父子、传播副本或重叠窗口相加。
5. `sandbox_finish_cumulative`、`container_finish_cumulative` 表示从同一 T0 到两个位置；二者逐实例相减才得到 container 窗口。
6. `sandbox-probe`、`all-probe` 和 `cubebox-service-inner` 分别是传播副本、聚合量和派生残差，不是三个额外串行阶段。
7. 分析 P95/Max 时读取 `create-container-details-v2.jsonl`，按 InstanceId 检查 marker 和 path；不要对汇总分位数做减法。

## 11. 关键源码索引

| 组件 | 关键文件 | 作用 |
|---|---|---|
| CubeMaster | [`sandbox_run.go`](CubeMaster/pkg/service/sandbox/sandbox_run.go#L101) | `cube-e2e` 及 Probe `ext_info` 传播 |
| Cubelet service | [`service.go`](Cubelet/services/cubebox/service.go#L237) | `cubebox-service`、派生 metric、5 ms 输出阈值 |
| Cubelet workflow | [`engine.go`](Cubelet/plugins/workflow/engine.go#L334) | step 串行、同一步 action 并行、action 计时 |
| Cubelet task | [`cube_container_create.go`](Cubelet/services/cubebox/cube_container_create.go#L1207) | metadata、NewTask、Wait/Start 指标 |
| Cubelet Probe | [`probe.go`](Cubelet/services/cubebox/probe.go#L82) | `sandbox-probe` |
| CubeShim outer | [`task_srv.rs`](CubeShim/shim/src/service/task_srv.rs#L86) | `CreatePodSandbox` 和累计 marker |
| CubeShim VM | [`sb.rs`](CubeShim/shim/src/sandbox/sb.rs#L436) | VM restore、Agent 连接、Reset/Create Sandbox 编排 |
| CubeShim timers | [`stat_defer.rs`](CubeShim/shim/src/log/stat_defer.rs#L55) | `CostTime` 公共实现 |
| Guest Agent | [`rpc.rs`](agent/src/rpc.rs#L157) | restore/normal CreateContainer 路径 |
| 采集器 | [`run_c50_profile.sh`](scripts_v2/run_c50_profile.sh#L22) | 日志截取、host/BPF 采样、精简事件流 |
| 分析器 | [`analyze_c50_profile.mjs`](scripts_v2/analyze_c50_profile.mjs#L375) | InstanceId 关联、统计、CSV 关系输出 |
