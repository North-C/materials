# 基于 Template 启动沙箱的现有观测能力

本文基于 [SDK 基于 Template 启动沙箱](./template-sandbox-launch.md) 中梳理的调用链，只记录当前源代码已经存在的 trace span、结构化日志和 Prometheus 指标。

尚未实现的观测建议不会混入现状说明。

现有能力可以把一次 Template 创建粗略分成调度、模板加载、节点内创建、ublk/远程存储和 assignment 写入，但还不能完整拆分 Firecracker 恢复内部的每个阶段。

## 观测数据分布

Gateway、Scheduler、AgentENV Node 和 ublk daemon 是四个独立进程，各自输出日志并暴露自己的 Prometheus 指标。

Node 内部的 tracing span 不会跨越 gRPC 或 HTTP 自动传播到 Gateway、Scheduler 和 ublk daemon，因此当前没有一个可直接查询的分布式 trace 能覆盖完整创建请求。

Node 的日志格式由 `AENV_LOG_FORMAT` 控制，可选 `compact`、`pretty` 或 `json`；默认过滤器为 `agentenv=info,envd=info,uvm_ublk=info`。

`AENV_LOG_SPAN_EVENTS` 默认为 `off`，所以 `#[tracing::instrument]` 创建的 span 默认不会输出独立的进入、退出和关闭事件。排查现有 debug 日志时需要通过 `RUST_LOG` 显式打开相关 crate。

ublk daemon 是独立进程，默认指标监听地址为 `0.0.0.0:9103`。它的日志和 OverlayBD 指标不属于 Node 进程的 `/metrics`，采集系统需要分别抓取。

查询时还应保留 instance 或 job 维度，避免把多个节点的数据混在一起。

## 创建主链路已有指标

| 位置 | 指标 | 主要标签 | 在 Template 创建中表示什么 |
|---|---|---|---|
| Gateway | `agentenv_gateway_http_request_duration_seconds` | `method`、`route`、`route_source`、`status` | SDK 看到的 Gateway 总耗时；`POST /sandboxes` 且 `route_source="schedule"` 对应新建请求 |
| Gateway | `agentenv_gateway_scheduler_rpc_duration_seconds` | `rpc`、`status` | `Schedule` 和成功响应后的 `RecordAssignment` RPC 耗时 |
| Gateway | `agentenv_gateway_upstream_proxy_duration_seconds` | `route`、`status` | 请求转发到 Node 后的耗时，包含 Node 同步创建和响应处理 |
| Scheduler | `agentenv_scheduler_rpc_duration_seconds` | `rpc`、`status` | Scheduler 各 gRPC 方法的服务端耗时 |
| Scheduler | `agentenv_scheduler_schedule_duration_seconds` | `strategy`、`status` | 节点过滤与选择耗时 |
| Scheduler | `agentenv_scheduler_schedule_assignments_total` | `strategy` | 成功调度次数，不表示沙箱最终创建成功 |
| Scheduler | `agentenv_scheduler_observed_nodes` | `status` | `ready`、`connecting`、`unhealthy` 等状态下的节点数 |
| Node | `agentenv_http_request_duration_seconds` | `method`、`route`、`route_source`、`status` | Node API 的 HTTP 总耗时；`route="/sandboxes"` 对应 Template 创建入口 |
| Node | `agentenv_sandbox_stage_duration_seconds` | `operation`、`stage`、`status` | Template 创建使用 `operation="create_warm"`，已有 `load_snapshot` 和 `create_sandbox` 两个阶段 |
| Node | `agentenv_sandbox_stage_inflight` | `operation`、`stage` | 当前正在模板加载或创建沙箱的请求数，可直接观察 Node 内部并发压力 |

`create_warm` 是 Template 创建路径的 `operation` 名称，不是阶段。其下的 `load_snapshot` 和 `create_sandbox` 才是可比较阶段，用于判断耗时主要位于模板加载还是沙箱启动。

`create_warm` 也不表示请求命中了 warm pool。即使 Firecracker、network、ublk 或 artifact cache 全部 miss，请求仍记录在该 operation 下，因此不能用它判断缓存或资源池命中情况。

`load_snapshot` 覆盖 `SnapshotManager::load_runnable`，包括 snapshot record 读取和 runtime artifact resolve。

`create_sandbox` 从 Orchestrator 接收请求开始，直到沙箱完成 envd readiness/init、元数据转为 `Running` 并发布 proxy route 后结束。因此，它不是单纯的 Firecracker resume 时间。

`SandboxStageTimer` 的 `status` 只有 `ok` 和 `error`。被上游取消的 `time` future 不会记录 duration，但 in-flight guard 会在 future 被丢弃时递减。

与之不同，`MetricGuard` 在未调用 `finish` 就被释放时会以 `status="canceled"` 记录耗时。

## 存储与设备已有指标

| 位置 | 指标 | 主要标签 | 与 Template 创建的关系 |
|---|---|---|---|
| Node | `agentenv_ublk_operation_duration_seconds` | `operation`、`status` | rootfs 使用 `create_runtime_overlaybd`；首次共享内存设备获取使用 `acquire_shared_memory`；关闭时还会出现 `release`、`delete` |
| Node | `agentenv_snapshot_oss_operation_duration_seconds` | `operation`、`status` | OSS backend 的 `get_bytes`、`get_to_file`、`exists` 等远程对象操作耗时 |
| ublk daemon | `agentenv_overlaybd_remote_metadata_duration_seconds` | `source`、`registry`、`status` | OverlayBD 远程元数据读取耗时 |
| ublk daemon | `agentenv_overlaybd_remote_read_duration_seconds` | `source`、`registry`、`operation`、`status` | rootfs 或 memory layer 的远程数据读取耗时 |
| ublk daemon | `agentenv_overlaybd_remote_read_bytes_total` | `source`、`registry`、`operation` | OverlayBD 远程读取字节数 |
| ublk daemon | `agentenv_overlaybd_zfile_pread_duration_seconds` | `codec`、`status` | 压缩层本地 pread 耗时 |
| ublk daemon | `agentenv_overlaybd_zfile_decompress_duration_seconds` | `codec` | 压缩块解压耗时 |

进程内已经存在的 shared memory device 会直接从 `shared_mem_devices` 返回，此时不会执行 `acquire_shared_memory` 计时。

因而该指标只反映真正进入 daemon acquire 的请求，不能单独作为共享内存命中率的分母。

OSS 指标也不能直接等价为 artifact cache 命中率。内存索引命中、本地文件命中和 singleflight 等待都不会产生 OSS 下载指标；POSIX repository 和 P2P 命中的数据路径也不同。

当前 `LocalArtifactCache` 只在驱逐失败、索引锁 poisoned 等异常上记录 warning，没有正常命中、miss 或等待耗时指标。

## 已有 span 与关键日志

Node 的主 span 从生成的 `sandboxes_post` handler 进入 `create_sandbox` 和 `launch_sandbox`。`launch_sandbox` 先触发 `start_resume`，再进入独立的 `wait_for_ready`，两者是顺序阶段而不是父子关系。

HTTP handler、Orchestrator 和 Firecracker 分别通过 `#[tracing::instrument]` 建立 span，其中 `create_sandbox` 明确记录 `sandbox_id`。

`launch_sandbox` 和 `start_resume` 依赖父 span 上下文，没有单独记录 `template_id` 或 canonical `snapshot_id`。

| 阶段 | 级别 | 已有消息或字段 | 能判断的事件 |
|---|---|---|---|
| Orchestrator 接收创建 | `info` | `creating sandbox`、`timeout`，父 span 含 `sandbox_id` | 创建任务已进入 Node |
| Orchestrator 启动后端 | `debug` | `sandbox start requested` | `start_nowait` 已成功返回 |
| Orchestrator 完成启动 | `info` | `sandbox launch completed` | envd ready/init、状态持久化和 proxy route 已完成 |
| Firecracker pool 命中 | `debug` | `using warm firecracker from pool`、`slot`、`pool_work_dir` | Firecracker process 与 network slot 同时复用 |
| snapshot resume 开始 | `debug` | `starting sandbox from snapshot config`、`fc_cwd`、`vm_state_path` | 已进入恢复配置阶段 |
| network pool 命中 | `debug` | `reused warm network slot from pool`、`slot` | 独立网络池命中 |
| network slot 分配完成 | `debug` | `allocated network slot for resume`、`slot` | 未随 Firecracker pool 获取 slot，随后完成网络分配 |
| shared memory 进程内复用 | `debug` | `reusing shared memory ublk device`、`key`、`dev_id` | 同 snapshot 的共享设备 Weak reference 命中 |
| shared memory 获取 | `info` | `created or acquired shared memory ublk device`、`key`、`dev_id`、`path` | 进程内未命中，已从 daemon 获取或创建 |
| ublk pool 命中 | `debug` | `reusing warm device from pool`、`dev_id`、`mode` | daemon idle pool 命中 |
| ublk pool miss | `debug` | `pool miss: creating new device`、`mode` | daemon 需要创建新设备 |
| ublk acquire 结果 | `info` | `acquired ... overlaybd device (reused/new)`、`dev_id`、`path` | 可区分 exclusive/shared 以及 reused/new |
| Gateway 路由 | `debug` | `gateway routed request`、`route_source`、`node_id`、`upstream_endpoint` | 请求被调度到哪个 Node |
| Scheduler 选择 | `debug` | `scheduler selected node`、`strategy`、`hint`、`node_id`、候选节点数 | 调度选择及过滤结果 |
| assignment 写入 | `debug` 或 `warn` | `gateway recorded sandbox assignment` 或 `record assignment failed` | 创建成功后的 binding 是否即时写入 |

Firecracker、network 和 ublk 的 debug 日志可以人工判断单次请求是否命中 pool，但现有日志没有统一 request ID，ublk daemon 又处于独立进程。

`sandbox_id`、`dev_id`、路径和时间戳可以辅助关联，但无法保证在高并发下形成无歧义的端到端链路。

## 使用现有指标定位瓶颈

先比较 Gateway 总耗时、Gateway `Schedule` RPC、Gateway upstream proxy 和 Node `create_warm` 两个阶段。

若 `Schedule` 升高，瓶颈在节点选择或 Scheduler；若 `load_snapshot` 升高，继续查看 OSS；若 `create_sandbox` 升高，继续查看 ublk 和 OverlayBD，并结合 Firecracker、network、envd 日志判断。

```promql
histogram_quantile(0.99, sum by (le) (rate(agentenv_gateway_http_request_duration_seconds_bucket{method="POST",route="/sandboxes",route_source="schedule"}[5m])))

histogram_quantile(0.99, sum by (le,stage) (rate(agentenv_sandbox_stage_duration_seconds_bucket{operation="create_warm",status="ok"}[5m])))

sum by (stage) (agentenv_sandbox_stage_inflight{operation="create_warm"})

histogram_quantile(0.99, sum by (le,operation) (rate(agentenv_ublk_operation_duration_seconds_bucket{operation=~"create_runtime_overlaybd|acquire_shared_memory",status="ok"}[5m])))
```

高并发排查时，应同时保留按 instance 或 node 切分的视图。聚合后的集群 P99 能说明整体退化，却可能掩盖某个 Node 的 warm pool 耗尽、artifact 冷缓存或 ublk daemon 排队。

## 当前观测盲区

社区代码当前没有 OpenTelemetry exporter、跨进程 trace ID 传播或端到端 trace。

已有 tracing span 主要用于日志上下文，默认也不输出 span 生命周期事件，所以不能把 span close time 直接当作稳定的阶段指标。

Firecracker resume 内部的 rootfs device、network、shared memory、API socket、load snapshot、resume 和 envd ready 没有分别计时。

`create_sandbox` 变慢时，只能结合 ublk 指标和 debug 日志缩小范围，不能直接得到各阶段的 P95/P99。

Firecracker pool、network pool、ublk pool、artifact cache 和 shared memory cache 都没有统一的 hit/miss counter。

ublk daemon 的日志最接近完整 hit/miss 信号；其他 pool 只能从命中日志与后续行为间接判断，因此当前无法用 Prometheus 准确计算这些命中率。

现有指标也没有直接展示 warm pool refill latency、snapshot singleflight 等待时间、envd readiness/init 耗时、Firecracker API 调用耗时和 ublk daemon 请求排队时间。

这些项目应被视为后续观测设计的候选项，而不是社区代码已经提供的能力。

## 主要源代码位置

- `src/observability/prometheus.rs`：Node HTTP、沙箱阶段计时和 `MetricGuard`。
- `src/api/impls/sandbox.rs`：`create_warm` 的 `load_snapshot` 与 `create_sandbox` 计时。
- `src/logging.rs`：Node 日志格式、过滤器和 span lifecycle 配置。
- `src/orchestrator/service.rs`：创建、启动、ready 和状态持久化日志。
- `src/sandbox/firecracker/sandbox.rs`：Firecracker pool、snapshot resume 和 envd ready 日志。
- `src/sandbox/network/manager.rs`：network pool 复用和维护日志。
- `src/sandbox/ublk/device.rs`：ublk 操作指标与 shared memory device 日志。
- `src/snapshot/artifact_cache.rs`：artifact cache、singleflight 和驱逐逻辑。
- `src/snapshot/repository/backends/oss/client.rs`：OSS 操作耗时与上传字节指标。
- `storage/ublk-daemon/src/server.rs`：ublk pool 命中、miss、acquire 和 release 日志。
- `storage/overlaybd/src/metrics.rs`：OverlayBD 远程读取和压缩层指标。
- `services/gateway/internal/metrics.go`：Gateway HTTP、proxy 和 Scheduler RPC 指标。
- `services/scheduler/internal/metrics.go`：Scheduler RPC、调度和节点状态指标。
