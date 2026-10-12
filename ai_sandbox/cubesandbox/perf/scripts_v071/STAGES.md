# v0.7.1 Template 启动阶段口径

源码基准为 `v0.7.1`，commit `31d911e430fdf8a8879bd062b8e78066c1a8e89d`。本地 `origin` 已核对为 TencentCloud/CubeSandbox；分析工作区 HEAD 相对该 tag 的已跟踪差异仅在 `tools/machconf`，本文引用的启动源码相同。所有链接固定到上述 commit，避免后续主分支移动。

这些数据可以给出启动调用树、主要耗时分布和部分真实时间窗口，不能拼成各段互斥、总和恰好等于客户端延迟的完整瀑布图。尤其要区分持续时间、累计时间、并行子任务、传播副本和派生残差。

## 客户端与 Master

| 指标/事件 | 精确边界与解释 | 源码 |
| --- | --- | --- |
| `benchmark.create` / `create_ms` | `time.Now()` 在构造 HTTP 请求之前；在 `client.Do(req)` 返回后计时。通常截止收到响应头，不包含后续 `ReadAll`、JSON 解码。失败判定发生在这些后续步骤，所以成功样本仍要求响应体处理成功。 | [cube-bench HTTP计时](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/examples/cube-bench/runner.go#L25) |
| CubeAPI | handler 调用 service；service 构造 Master 请求并等待响应。成功日志有 sandbox/template ID，但普通请求日志并不能独立建立所有入口到出口的精确成对窗口。 | [API handler](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeAPI/src/handlers/sandboxes.rs#L178)、[API→Master](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeAPI/src/services/sandboxes.rs#L276) |
| Master `cube-e2e`（response `ext_info`） | 从 `CreateSandbox` 内设置 `startTime` 到成功返回 defer 中 `setProbeInfo`；包含调度、Cubelet RPC、Master 后处理。不覆盖 CubeAPI 前处理、HTTP 网络和响应传输。毫秒取整。 | [Master请求起点/日志](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L105)、[response计时和probe传播](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L701) |
| Master stat `cube-e2e` | 从同一 `startTime` 到 `Wait()` 后设置的 `endTime`；比 response ext_info 的结束稍早，二者不能假定完全相等。stat 由 goroutine 异步输出。 | [Master结束点](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L151)、[Master stat定义](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L510) |
| Master `cubemaster-inner` | `endTime-startTime` 减最后一次 Cubelet RPC 的持续时间；这是残差，重试时还混有之前尝试等成本。 | [Master stat定义](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L510) |
| Master `cubemaster-inner-handle` | `endTime-cubeletEndTime`；反映最后一次 Cubelet 返回后的处理窗口。 | [Master stat定义](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L510) |
| Master `cubemaster-post-redis` / `cubemaster-post-spec` | 分别测 Redis 代理映射写入和 MySQL sandbox spec 持久化；两个任务并行，不能相加作为后处理壁钟耗时。只有操作实际执行时才输出。 | [并行后处理](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L328)、[Master stat定义](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L510) |
| Master schedule / buffer handle | `startHandleTime-startTime`；包含进入调度处理前的窗口，不等价于纯队列等待。 | [Master stat定义](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L510) |

## Cubelet：并行工作流与累计计时

默认 create 工作流为：`[createid, appsnapshot] → [images, volume, storage, network, netfile, cube-sandbox-store] → [cgroup] → [cubebox]`。方括号内并行，组之间等待完成后再推进；须核对实际部署配置，不能只凭源码默认值认定现场设置。定义见 [默认workflow](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/config/config.toml#L177)；每个 action 计时见 [workflow action计时](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/plugins/workflow/engine.go#L476)。

| 指标 | 精确边界与解释 | 源码 |
| --- | --- | --- |
| `cubebox-service` | 从参数检查、默认值设置之后的 `start` 到 service 返回的 defer；不含更早的 cross-node prepare、pause package 展开及参数检查。是工作流外层窗口。 | [service计时起点](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L250)、[service结束及异步输出](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L312) |
| `network` / `storage` / `cubebox` 等 | 各 workflow action 的 `Create()` 调用持续时间。network 与 storage 处在并行组；不能顺序堆叠。 | [workflow action计时](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/plugins/workflow/engine.go#L476) |
| `storage` 内部 | `prepareRequestVolumes` 与 `prefetchRestoreMemoryVolURL` 并行，等待后写 backend metadata。Template rootfs 克隆及恢复内存路径准备不是简单串行和；没有全部独立起止日志。 | [storage并行准备](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/storage/local.go#L831) |
| `create-sandbox-metadata` | `containerd.NewContainer` 元数据创建，不是 VM 创建。 | [metadata创建](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/cube_container_create.go#L1324) |
| `sandbox-create` | 从 `taskStart` 到 `c.NewTask` 返回，包含 Shim 创建任务。错误提前返回可能没有此阶段 metric。 | [NewTask计时](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/cube_container_create.go#L1353) |
| `sandbox-start` | **同一个** `taskStart` 到后续 `Wait`、`Start`、状态更新完成。包含 `sandbox-create`，不是 Start RPC 独立耗时。 | [NewTask计时](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/cube_container_create.go#L1353)、[累计start](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/cube_container_create.go#L1375) |
| `sandbox-probe` | `doProbe` 全函数窗口；在 runContainer 完成之后执行，可能包含多种就绪检查。没有配置的部分不可擅自解释为真实探测操作。 | [probe调用位置](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/cube_container_create.go#L428)、[probe计时](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/probe.go#L82) |
| `cubebox-service-inner` | `service - 所有probe - images - volume`；没有减 storage/network，并且被减项可能并行，不是纯 Cubelet overhead。 | [派生指标公式](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L446) |
| `cubebox-inner` | `cubebox - 所有sandbox/container前缀metric之和`；其中累计 start/create 会重复扣除，因此可能为负，也不能当独立阶段。 | [派生指标公式](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L446) |
| Master `sandbox-probe` / `all-probe` | 前者传播 Cubelet 数值；后者累加所有名称含 `-probe` 的值，不能再次与 Cubelet probe 相加。多容器并行时这个和也不是独立壁钟窗口。 | [response计时和probe传播](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L701) |

子阶段命名由容器索引生成：索引 `0` 变为 `sandbox`，其余变为 `container-索引`，见 [metric命名](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/plugins/workflow/metric.go#L27)。本次单容器 Template 可以用 Sandbox ID 关联；多容器时还需保留 Container ID 和调用身份。

## Shim、VMM 与 Guest

| 指标/日志 | 精确边界与解释 | 源码 |
| --- | --- | --- |
| `CreatePodSandbox` | Shim TaskService create 请求外层，包括 load spec、sandbox lock、初始化、VM 恢复、Agent 连接、Guest sandbox/container 创建及事件发送。后续非首次 container 调用用 `CreatePodContainer`。 | [Shim create全链路](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/service/task_srv.rs#L328) |
| `LaunchVmm` | 主要覆盖 `VmmInstance::new`；配置转换在 timer 之前。 | [LaunchVmm](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/hypervisor/cube_hypervisor.rs#L88) |
| `RestoreVm` | CH mutex 获取之后，发送 `VmRestore` 到收到返回。**不含**上层 snapshot metadata 校验、配置构造等；也不能等同于“VM 启动到应用可用”。 | [RestoreVm](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/hypervisor/cube_hypervisor.rs#L173)、[restore准备](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/sandbox/sb.rs#L923) |
| `start vm start → agent is ready` | 同 Shim 请求日志时钟的较大窗口，覆盖 launch、restore/boot 和 Agent 连接；其中子段已经包含在窗口内。Template restore 成功走 app snapshot 分支时跳过普通 vsock ready 等待。 | [VM启动](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/sandbox/sb.rs#L866)、[Agent ready](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/sandbox/sb.rs#L472) |
| `ResetVm` | Guest 时间重置和 RNG reseed 两个 RPC；client lock 在 timer 之前。 | [ResetVm](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/sandbox/sb.rs#L438) |
| `CreateSandbox` | storages/DNS 准备完成后开始计时，覆盖请求构造、client lock 和 Guest CreateSandbox RPC。 | [CreateSandbox](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/sandbox/sb.rs#L495) |
| `CreateContainer` | 包括可选 passfd、storages/spec/custom files 准备、client lock、Guest RPC 和本地状态设置。 | [CreateContainer](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/container/mod.rs#L573) |
| `load spec finish at` / `start sandbox finish at` / `start container finish at` | 都以同一次 create 请求的 `Instant` 为起点，是累计值。只有同实例同调用内做差才可得到相邻边界间隔。 | [Shim create全链路](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/service/task_srv.rs#L328) |
| Guest recv → restore branch | 从 `[cube-strace]recv create container` 到 `create container by restore`，仅包括复制/转换 OCI 与选择 restore 分支。 | [Guest restore路径](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/agent/src/rpc.rs#L152) |

Guest restore 分支标记之后，还有锁等待、查找恢复进程、日志 reader 重置、可选 IO 重连、`start_exec_process` 等操作（[Guest restore路径](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/agent/src/rpc.rs#L152)）。因此 `Shim CreateContainer - Guest recv→restore branch` 只能叫“未细分残差”，不能直接命名为 Guest exec、挂载或进程启动耗时。普通创建分支的 add devices/storage/bundle/init/start 五段日志不能套用于 Template restore。

## 日志和 metrics 的准确性边界

- Cubelet 成功阶段短于 **5 ms** 不输出 stat；失败阶段不受此抑制条件限制（[stat抑制与输出](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L497)）。缺失不是零，也不能一概证明 `<5 ms`，还可能是路径未执行、失败早退、日志关闭或采集缺口。部分深层 helper 还有 1 ms 记录门槛（[1ms helper门槛](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/storage/image_volume.go#L25)）。
- Cubelet 把已记录的 duration 在请求末尾通过异步 goroutine 集中输出。因此 stat 的时间戳是输出时间，不是子阶段结束时间，**不能 `timestamp-CostTime` 还原各阶段开始时间**（[service结束及异步输出](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L312)、[stat抑制与输出](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/cubebox/service.go#L497)）。
- Shim `StatItem` 没有时间戳；`CostTime` 是 `Instant.elapsed().as_millis()` 整数毫秒，成功/失败为 `Ok`/`Err`。队列 `try_send` 失败被忽略，可丢记录（[Shim stat输出](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/log/mod.rs#L394)、[Shim计时器](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeShim/shim/src/log/stat_defer.rs#L75)）。只能用明确 request marker 构造可验证时间窗口，不能凭 stat 文件行序定时。
- Go stat `CostTime` 是毫秒、保留微秒量级；response ext_info 和 Shim stat 则为整数毫秒。不同精度应分别保留（[Go stat开关与单位](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/pkgs/CubeLog/metric.go#L189)）。
- Host 与 Guest 时钟不可直接相减。Guest 会在 ResetVm 中主动设置时间；转发的 Guest 日志还存在异步传输。Guest 子段只使用其内嵌 `ts` 相减，并核对同实例、同调用、非负。跨进程 duration 对比也不是自动得到新的实测区间。
- `/v1/metrics` 是 Prometheus 聚合端点；scheduler/resource 有各自独立路径（[metrics端点](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/Cubelet/services/server/server.go#L250)）。快照差值用于资源压力、计数及覆盖检查；不能为缺失的逐 sandbox 启动 span 补造精确时间轴。累计 histogram 如存在，其桶差值也仅是区间聚合分布，需要检查进程重启、counter reset、并发背景任务及样本群体。
- Master stat 受 `EnableLogMetric` 开关影响（[Go stat开关与单位](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/pkgs/CubeLog/metric.go#L189)）。现场无该文件/未开启时，post-redis/spec 等就是不可观测，不能从 response 推导出假精确值。保留采集缺口即可，不能为了完成报表假设零耗时。
- 不同覆盖率或不同调用集的分位数不能相减；同一实例有多次同名 stage 时也不能静默取第一条。应分别展示覆盖实例数、记录数、失败数、重复记录和缺失数。

## 正式 100 与预热 3 的关联证明

官方 `RunWarmup` 循环串行执行 3 次，返回后才开始正式 benchmark（[串行预热](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/examples/cube-bench/runner.go#L131)）。Master 起始 marker 为 `CreateSandbox:{JSON}`，成功响应为 `CreateSandbox_rsp:{JSON}`；失败响应另用 `CreateSandbox_rsp fail:`（[Master请求起点/日志](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/sandbox_run.go#L105)）。请求 JSON 关联字段为 **`requestID`**；响应 `CreateCubeSandboxRes` 显式字段没有 JSON tag，实际为 **`RequestID`**，外层日志为 `RequestId`。Master 成功码为 **200**，不是 0（[响应类型](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/types/types.go#L112)、[成功码](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/errorcode/error.go#L19)）。响应包含 `sandbox_id`、`ret`、`ext_info`（[requestID类型](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/types/types.go#L25)、[成功响应字段](https://github.com/TencentCloud/CubeSandbox/blob/31d911e430fdf8a8879bd062b8e78066c1a8e89d/CubeMaster/pkg/service/sandbox/util.go#L1081)）。

只有同时满足专用 Template 独占、测试前后空集、103 个唯一 owned ID、清理 ledger drained、官方工作负载和 3 条 warmup success 证据、服务 PID/start_ticks/hash/boot 稳定、完整无缺口 Master 日志、103 组唯一成功请求响应对与 owned 集合一致，并证明按请求开始时间排序的前三组串行且第四组在第三组响应后，才能将最早三组**推断**为服务端 warmup、余下 100 组为 formal。按响应完成顺序分组不成立。这个证明只建立服务端阶段归属，仍没有建立 cube-bench raw `seq` 到 Sandbox ID 的映射。

本次 suite 在 benchmark 前还执行 1 次 Guest canary preflight，并验证清理后 inventory 为空。因此完整 Master 日志有 104 组 Create 对，只有 ledger 中的 103 个 ID 属于预热和正式负载。分类器要求额外组恰好 1 个、创建及成功删除确认都在首个 owned 请求之前，且固定 hash 的 suite preflight/case 成功；删除确认本身不等同于彻底清理，以 suite 的空 inventory 检查共同证明。额外组单独保留，不混入 warmup 3/formal 100，也不丢弃未知额外请求。
