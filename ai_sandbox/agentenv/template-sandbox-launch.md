# SDK 基于 Template 启动沙箱的代码路径与并发分析

本文分析用户通过 E2B-compatible SDK，以 `templateID` 创建沙箱时，AgentENV 内部经历的控制流和数据流。重点不是逐个罗列函数，而是说明各组件如何接力，以及同一 Template 被高并发启动时哪些资源会复用、哪些步骤仍然独立执行。

## 核心结论

在 AgentENV 中，Template 的运行时形态是 **committed snapshot**，不是另一种容器镜像格式。

SDK 发起 `POST /sandboxes` 后，节点先把 `templateID` 解析成 `RunnableSnapshot`。Orchestrator 随后创建新的 sandbox ID，并让 Firecracker 从 snapshot 的 VM state、memory image 和 rootfs layers 恢复一个新实例。

接口只有在 guest 内的 `envd` 就绪、初始化完成，并且节点发布了 proxy route 后才返回 `201`。因此 SDK 收到成功响应时，沙箱已经可以使用；代价是整个创建过程占用一条同步 HTTP 请求。

高并发启动同一个 Template 时，主要复用点有：

- snapshot artifact 的本地缓存和同 key 请求合并；
- 同一 memory image 对应的共享只读 ublk 设备；
- Linux page cache 中的 snapshot memory pages；
- Firecracker process、network slot 和 ublk device warm pool；
- rootfs 与 memory 的不可变 OverlayBD lower layers。

主要风险则集中在：调度阶段没有容量预留和 Template affinity、首次 artifact 获取形成同 key 等待、warm pool 容量小于突发量时退化到冷路径，以及同步创建请求可能超过 Gateway 或 SDK timeout。

## 完整调用链

```text
SDK
 |  POST /sandboxes { templateID, ... }
 v
Gateway
 |  Schedule(NewSandbox hint)
 v
Scheduler
 |  resource filter -> round_robin/random -> Node
 v
Node API: sandboxes_post
 |  SnapshotManager::load_runnable(templateID)
 |    repository.get(id or alias)
 |    SnapshotRuntimeResolver::resolve
 |      vm_state + manifest + memory/rootfs image.json
 v
Orchestrator::create_sandbox
 |  SandboxLaunchSource::Snapshot
 |  LaunchPlan::for_create_from_snapshot
 |  FirecrackerSandboxFactory::build_from_snapshot
 v
FirecrackerSandbox::start_resume
 |  warm Firecracker + network slot, or cold create
 |  per-sandbox rootfs upper + exclusive ublk
 |  shared memory ublk for the same Template
 |  Firecracker PUT /snapshot/load
 |  resume VM
 v
envd health -> envd init
 |  metadata: Creating -> Running
 |  publish node-local proxy route
 v
Node returns 201 + x-agentenv-sandbox-id
 |  Gateway RecordAssignment(sandbox -> node)
 v
SDK receives a ready sandbox ID
```

这条链路包含两类信息：

- **控制流**决定请求发到哪个节点、沙箱处于什么状态、什么时候可以对外服务。
- **数据流**把 snapshot metadata 转换成节点本地文件路径，再转换成 Firecracker 可以使用的块设备和 memory backend。

## 1. SDK 发送 Template 创建请求

外部 E2B SDK 不在本仓库中，但它与 AgentENV 的边界是 E2B-compatible HTTP API。仓库中的 Rust CLI client 展示了同样的请求格式：

```rust
pub fn create_sandbox(&self, template_id: &str, timeout: Option<u32>) -> Result<String> {
    let body = NewSandbox {
        template_id,
        timeout,
    };
    let resp = handle_status(self.post("/sandboxes").send_json(&body))?;
    let sandbox: Sandbox = resp.into_json()?;
    Ok(sandbox.sandbox_id)
}
```

序列化后的核心字段是：

```json
{
  "templateID": "template-or-snapshot-id",
  "timeout": 300
}
```

`NewSandbox` 还可以携带环境变量、metadata、网络策略、auto pause/resume 和 custom extension params。这些字段不会修改 committed snapshot，而是在本次 launch 时覆盖或补充 snapshot 中的配置。

关键源代码：

- `crates/aenv/src/client/sandboxes.rs`
- `src/api/openapi.yml`
- `src/api/generated/src/apis/sandboxes.rs`

## 2. Gateway 调度节点

如果 SDK 直接连接单节点，这一层不存在。多节点部署中，Gateway 收到不含 sandbox ID 的 `POST /sandboxes` 后，把它识别为新建请求，并调用 Scheduler 的 `Schedule` RPC。

Gateway 会读取请求体生成 `NewSandboxHint`，然后恢复 request body，确保后续反向代理仍能转发完整请求。为了防止认证前的大请求消耗过多内存，hint 提取最多缓冲 64 KiB。

当前 `NewSandboxHint` 只包含 metadata，不包含 `templateID`，也不包含该 Template 对应的 CPU、memory 或 artifact 信息。

Scheduler 先使用最近一次 heartbeat 中的节点指标执行可选的 resource limit filter，再使用 `round_robin` 或 `random` 选择节点。内置策略本身不根据负载排序，heartbeat 数据只参与阈值过滤。

选出节点后，Gateway 把原始 `POST /sandboxes` 转发给该节点。此时 Scheduler 尚未写入 sandbox-to-node binding，因为 sandbox ID 还没有生成。

### 已有并发设计

- `RoundRobinStrategy` 使用 atomic counter，不需要全局互斥锁。
- Scheduler 的 node registry 提供 snapshot 视图，调度时不持有长时间锁。
- 可配置 `max_sandbox_starting_count`、CPU 和 memory 阈值，提前过滤过载节点。
- 已有 sandbox 的 `LookupNode` 可以交给 query-only scheduler replica；Redis 可以共享 binding，提高 data plane 可用性。
- Gateway 优先从成功响应的 `x-agentenv-sandbox-id` header 读取 ID，不必缓冲响应 body。

### 高并发风险

- `Schedule` 不做容量 reservation。大量请求可能基于同一份 heartbeat 同时通过过滤，然后共同压到一个节点。
- scheduler reporter 启用后默认每 5 秒上报一次 heartbeat，突发启动产生的 `Creating` 数量不会立即反映到 Scheduler。
- `templateID` 没有进入 scheduling hint，因此当前不能按 snapshot cache、P2P artifact 或 memory warm state 做节点亲和调度。
- 内置策略只做轮询或随机选择，不比较候选节点的实时负载。
- 创建、写 binding 等 control plane 操作仍依赖 primary scheduler；query-only replica 只能承担读路径。

关键源代码：

- `services/gateway/internal/server.go`
- `services/gateway/internal/schedule_hint.go`
- `services/scheduler/internal/service.go`
- `services/scheduler/internal/filter.go`
- `services/scheduler/internal/strategy.go`

## 3. Node API 把 Template 解析成 RunnableSnapshot

Node API 的 `sandboxes_post` 首先执行：

```rust
self.snapshot_manager.load_runnable(&body.template_id)
```

`SnapshotManager::load_runnable` 分成两步：

1. `repository.get(id_or_alias)` 读取 committed `SnapshotRecord`。
2. `SnapshotRuntimeResolver::resolve` 把持久化记录转换为当前节点可直接使用的 `RunnableSnapshot`。

`RunnableSnapshot` 包含：

| 数据 | 作用 |
|---|---|
| `SnapshotRecord` | Template identity、资源规格、运行配置和 committed layer 描述 |
| `FirecrackerSnapshotManifest` | 当前节点上的 `vm_state`、memory、rootfs 和 attached drive 路径 |
| `RuntimeArtifactLease` | 在启动窗口内 pin 住缓存文件，避免被并发 GC 淘汰 |

### POSIX repository

POSIX resolver 直接使用 repository 中的 `vm_state.bin` 和 manifest，同时为 memory、rootfs 和 attached drives 生成节点本地 OverlayBD `image.json`。

### OSS repository

OSS resolver 会把固定 artifact 放入 `LocalArtifactCache`。`vm_state.bin` 和 manifest 优先尝试 P2P，失败后回退到 object storage。OverlayBD layers 通常只生成远程可读描述，由运行时按需读取。

OSS managed layer 的存在性检查使用最多 16 个并发请求，避免逐层串行 HEAD；但 memory、rootfs、attached drives 等大阶段仍按代码顺序解析。

### 已有并发设计

- `LocalArtifactCache` 对同一个 cache key 实现 singleflight。同一 Template 的并发请求只允许一个请求下载或生成文件，其余请求等待相同结果。
- cache handle 使用 refcount pin 住启动所需文件，避免运行中的 artifact 被 LRU eviction 删除。
- P2P-first 可以让其他节点提供已缓存 artifact，object storage 保持最终回退路径。
- OverlayBD layer 可以保留远程 URL，不要求启动前下载完整 layer。
- 本地 runtime `image.json` 按 snapshot ID 使用稳定路径，可以跨请求复用。

### 高并发风险

- 第一次 cache miss 只有一个 singleflight leader 执行下载；同一 Template 的所有 follower 会等待它。它避免重复 I/O，但也形成明确的 head-of-line waiting。
- 每次启动仍会读取 snapshot record 并构造 `RunnableSnapshot`，没有整个 runnable object 的进程级缓存。
- OSS 首次加载受 P2P/object storage latency、带宽和 cache disk 写入速度影响。
- 固定 artifact 和各类 image config 主要按阶段顺序处理，首次启动延迟可能叠加。
- cache 空间不足会触发异步 LRU eviction；持续在大量 Template 间切换时可能出现 cache churn。

关键源代码：

- `src/snapshot/manager.rs`
- `src/snapshot/types/snapshot.rs`
- `src/snapshot/artifact_cache.rs`
- `src/snapshot/runtime_support.rs`
- `src/snapshot/repository/backends/posixfs/runtime.rs`
- `src/snapshot/repository/backends/oss/resolver.rs`

## 4. Orchestrator 创建 LaunchPlan

Node API 把 `RunnableSnapshot` 放进：

```rust
SandboxLaunchSource::Snapshot(Box::new(snapshot))
```

`Orchestrator::create_sandbox` 先生成新的 `SandboxId`，然后在 cancellation-safe Tokio task 中执行创建。即使 SDK 或 Gateway 提前断开连接，已经开始的生命周期操作也不会在任意 await 点被取消，从而避免留下半创建的 VM 或设备。

`create_sandbox_inner` 会验证 snapshot 的 virtualization mode，继承 snapshot 中的资源和运行版本，并合并本次请求的 env vars、network policy 和 custom extension params。

随后生成 `LaunchPlan::for_create_from_snapshot`，调用 factory：

```text
FirecrackerSandboxFactory::build_from_snapshot
  -> FirecrackerSandbox::from_snapshot
  -> FirecrackerSnapshotConfig::from_runnable_snapshot
  -> LaunchMode::Resume
```

这里的 `Resume` 表示从 committed Template snapshot 创建新实例，不是恢复某个已有 sandbox ID。

### `create_sandbox -> start_resume` 的调用路径

这条路径跨过了 factory trait 和 backend trait object，源代码中没有一行直接写出：

```rust
orchestrator.create_sandbox(...).start_resume(...)
```

实际调用由下面八步组成。

第一步，`create_sandbox` 只负责生成 sandbox ID，并把工作交给 cancellation-safe task：

```rust
self.run_cancellation_safe("create", sandbox_id, async move {
    this.create_sandbox_inner(sandbox_id, request).await
})
.await
```

第二步，`create_sandbox_inner` 在 `SandboxLaunchSource::Snapshot` 分支中构造的是 orchestrator 层的 `LaunchPlan::Create`：

```rust
self.launch_sandbox(LaunchPlan::for_create_from_snapshot(
    sandbox_id,
    snapshot,
    launch_config,
    transitional_metadata,
    NewTimeout::Set(timeout.unwrap_or(self.default_sandbox_timeout)),
))
.await
```

第三步，`launch_sandbox` 调用 `build_sandbox`。后者识别 `CreateLaunchSource::Snapshot`，再调用 factory trait：

```rust
CreateLaunchSource::Snapshot { snapshot } => self
    .factory
    .build_from_snapshot(snapshot, plan.launch_config.clone()),
```

`Orchestrator` 对 factory 使用泛型参数 `F: SandboxBackendFactory`。默认 `F` 是 `FirecrackerSandboxFactory`，因此这里通常是编译期单态化后的 trait 调用，不是 `dyn` trait object 的运行时分派。

第四步，默认 factory implementation 创建具体的 `FirecrackerSandbox`，但向上返回 `Box<dyn SandboxBackend>`：

```rust
fn build_from_snapshot(
    &self,
    snapshot: &RunnableSnapshot,
    launch_config: SandboxLaunchConfig,
) -> Result<Box<dyn SandboxBackend>> {
    let sandbox = FirecrackerSandbox::from_snapshot(snapshot, &launch_config)?;
    Ok(Box::new(sandbox))
}
```

第五步，`FirecrackerSandbox::from_snapshot` 把 snapshot 转成 `FirecrackerSnapshotConfig`，并把内部启动模式保存为 `LaunchMode::Resume`：

```rust
let snapshot_config = Self::snapshot_config_for_launch(snapshot, launch_config)?;

Self::build(
    launch_config.sandbox_id,
    LaunchMode::Resume(snapshot_config),
)
```

这里有两个名字相似但层次不同的状态：

- Orchestrator 层仍然是 `LaunchPlan::Create`，因为它在创建一个新的 sandbox ID。
- Firecracker backend 层是 `LaunchMode::Resume`，因为虚拟机从 snapshot 恢复执行状态。

第六步，`launch_sandbox` 得到 `Box<dyn SandboxBackend>` 后调用：

```rust
sandbox.start_nowait().await
```

这是实际的 trait object 动态分派点。运行时对象是 `FirecrackerSandbox`，所以进入它的 `SandboxBackend` implementation。

第七步，trait implementation 只是一个转发桥：

```rust
async fn start_nowait(&mut self) -> Result<()> {
    FirecrackerSandbox::start_nowait(self).await
}
```

第八步，具体实现检查第五步保存的 `LaunchMode`。Template 路径保存的是 `Resume`，因此最终调用私有方法 `start_resume`：

```rust
match &self.launch {
    LaunchMode::Fresh(config) => self.start_fresh(config.clone()).await,
    LaunchMode::Resume(config) => self.start_resume(config.clone()).await,
}
```

因此，完整且精确的路径是：

```text
Orchestrator::create_sandbox
  -> create_sandbox_inner
  -> LaunchPlan::Create(CreateLaunchSource::Snapshot)
  -> launch_sandbox
  -> build_sandbox
  -> SandboxBackendFactory::build_from_snapshot
  -> FirecrackerSandboxFactory::build_from_snapshot
  -> FirecrackerSandbox::from_snapshot
  -> FirecrackerSandbox::build(LaunchMode::Resume)
  -> Box<dyn SandboxBackend>::start_nowait
  -> <FirecrackerSandbox as SandboxBackend>::start_nowait
  -> FirecrackerSandbox::start_nowait
  -> LaunchMode::Resume branch
  -> FirecrackerSandbox::start_resume
```

对应源码位置：

- `src/orchestrator/service.rs:320`：`create_sandbox`
- `src/orchestrator/service.rs:360`：Template snapshot 分支
- `src/orchestrator/service.rs:1909`：`launch_sandbox`
- `src/orchestrator/service.rs:2081`：`build_sandbox`
- `src/sandbox/backend.rs:263`：`SandboxBackendFactory` trait
- `src/sandbox/firecracker/factory.rs:144`：默认 factory implementation
- `src/sandbox/firecracker/sandbox.rs:512`：`from_snapshot`
- `src/sandbox/backend.rs:172`：`SandboxBackend` trait
- `src/sandbox/firecracker/sandbox.rs:260`：backend trait implementation
- `src/sandbox/firecracker/sandbox.rs:567`：按 `LaunchMode` 分支
- `src/sandbox/firecracker/sandbox.rs:1383`：`start_resume`

### 启动与状态写入的重叠

`launch_sandbox` 先执行 `sandbox.start_nowait()`。该调用完成资源准备、snapshot load 和 VM resume，但不等待 `envd` ready。

VM 开始运行后，Orchestrator 才把 sandbox handle 写入内存表，并持久化 `Creating` metadata。随后 `wait_for_ready()` 与 guest 启动并行推进。最后将状态从 `Creating` 原子更新为 `Running`。

### 已有并发设计

- 每个 sandbox backend 使用独立 `Arc<Mutex<_>>`，不同 sandbox 的启动不会共用同一 backend lock。
- sandbox map、proxy route table 和 metadata store 使用短时间 `RwLock`；慢速 Firecracker/ublk/envd 操作不在这些全局写锁内执行。
- 状态更新使用 expected-state 检查，避免并发生命周期操作覆盖彼此。
- 创建任务 cancellation-safe，失败路径按启动阶段回收 VM、ublk、network slot、metadata 和 route。
- `start_nowait` 让 guest boot 与 metadata 写入重叠，缩短串行 critical path。

### 高并发风险

- 节点内部没有针对 create 的 admission semaphore 或有界等待队列。通过 API 的启动请求会直接并发进入 artifact、network、ublk 和 Firecracker 路径。
- Orchestrator 的 `Creating` metadata 在 `start_nowait` 之后才写入；资源准备期间的请求尚未进入 starting count。
- metadata store 和全局 map 的锁区间较短，但在极高 QPS 下仍是共享写入点，需要通过压测判断影响。
- **cancellation-safe 意味着上游 timeout 不会停止后端创建。它保证状态完整，但可能产生“客户端已经放弃、节点仍继续消耗资源”的时间窗口。**

关键源代码：

- `src/orchestrator/service.rs`
- `src/orchestrator/launch_plan.rs`
- `src/orchestrator/store/in_memory.rs`
- `src/sandbox/firecracker/factory.rs`

## 5. Firecracker 从 Template Snapshot 恢复

`FirecrackerSandbox::start_resume` 是数据路径的核心，按以下顺序恢复实例。

### 5.1 获取 Firecracker process 和 network slot

如果请求没有自定义 stdout/stderr 路径，代码先尝试从 `FirecrackerPool` 取得一个已经启动且 API socket ready 的 Firecracker process。这个 warm entry 同时携带已经准备好的 network namespace 和 slot。

Pool miss 时，系统通过 `NetworkManager::allocate_any` 获取 slot，再创建 work directory，并在对应 netns 中启动新的 Firecracker process。

### 5.2 创建独立 rootfs runtime

Template 的 rootfs lower layers 可以共享，但每个 sandbox 都需要独立 writable upper。ublk daemon 根据 snapshot rootfs `image.json` 创建 runtime config，并返回 exclusive `/dev/ublkbN`。

启用 block warm pool 时，daemon 优先复用 idle ublk device，通过 `swap_state` 把 target 指向当前 rootfs。支持 `UBLK_F_UPDATE_SIZE` 的内核还可以复用不同容量的 idle device。

### 5.3 复用 memory ublk device

Memory snapshot 是只读的。同一节点上使用相同 memory `image.json` 的 sandbox，通过 canonical config path 命中同一个 `SharedMemDevice`。

该 handle 使用 `Arc` 引用计数；最后一个 sandbox 释放后才删除底层设备。ublk daemon 还维护 shared device refcount，处理主进程中并发首次 acquire 的竞争。

所有 Firecracker 实例将同一个 ublk block device 作为 file-backed memory backend。Linux page cache 因此可以共享从 snapshot 读出的页面；guest 对内存的修改由 Firecracker 进程以 copy-on-write 方式私有化。

### 5.4 加载 snapshot 并恢复 guest

Firecracker 收到：

- `vm_state.bin`；
- shared memory ublk device path；
- 新 network namespace 中的 `tap0` override；
- 当前 sandbox 的 MMDS metadata；
- 当前节点配置下的 rootfs I/O limiter。

代码先调用 `PUT /snapshot/load`，保持 VM paused，完成 MMDS 和 limiter 修正后再执行 `resume()`。

### 5.5 Pool 水位配置与生效范围

`low_watermark` 和 `high_watermark` 可以在 AgentENV 的主配置文件中调整。默认配置位于 `config/default.toml`；使用 `AENV_CONFIG_PATH` 时，应修改实际加载的配置文件。

```toml
[pool]
low_watermark = 2
high_watermark = 64

[pool.firecracker]
enabled = true
maintenance_enabled = true
startup_prewarm = true
fill_concurrency = 4
```

`[pool]` 下的两个 watermark 是公共值。`network_pool_config()`、`block_pool_config()` 和 `firecracker_pool_config()` 都会读取它们。因此，目前不能只通过配置为 Firecracker 设置一套独立水位。

```rust
pub fn firecracker_pool_config(&self) -> Option<ResolvedFirecrackerPoolConfig> {
    let pool = &self.pool.firecracker;

    if !pool.enabled {
        return None;
    }

    Some(ResolvedFirecrackerPoolConfig {
        pool: warm_pool::PoolConfig {
            low_watermark: self.pool.low_watermark,
            high_watermark: self.pool.high_watermark,
            maintenance_enabled: pool.maintenance_enabled,
            startup_prewarm: pool.startup_prewarm,
        },
        fill_concurrency: pool.fill_concurrency,
    })
}
```

Firecracker pool 是进程级 `OnceLock` 单例，配置在首次初始化时读入，没有热更新路径。修改 watermark 或 `fill_concurrency` 后需要重启 AgentENV Node。

各参数的实际含义如下：

- `low_watermark`：初始 refill target，也是启动预热目标。Server 启动时最多等待 10 秒，使空闲 Firecracker 数量达到该值；超时后带着已有的部分容量继续启动。
- `high_watermark`：自适应 refill target 的上限。压力使空闲数量跌破 low 后，target 从 low 开始按倍数增长，最高到 high，并在当前进程生命周期内保持。
- `fill_concurrency`：一次 refill batch 并发创建 Firecracker entry 的上限。默认是 4，只作用于 Firecracker pool。
- `startup_prewarm`：控制启动阶段是否主动填充到 low。关闭后会跳过启动预热。
- `maintenance_enabled`：控制后台维护线程。关闭后不会执行自动 refill；请求仍可回退到 Firecracker cold spawn。
- `enabled`：控制是否启用 Firecracker pool。关闭后所有请求都走 cold spawn。

配置校验要求 `low_watermark <= high_watermark`，且 Firecracker `fill_concurrency > 0`。不满足时 Node 会在配置加载阶段失败，而不是运行时静默修正。

不建议把 low 设置为 0 来实现“按需预热”。当前增长逻辑只有在 pool 长度低于 low 时才提高 refill target；`low=0` 时这个条件不会成立，Firecracker pool 会持续退化到 cold spawn。

调高 low 可以提高突发请求的直接命中率，但每个 warm Firecracker entry 都持有一个 Firecracker process、network slot 和工作目录。由于 watermark 还会作用于其他 pool，需要同时核算 PID、文件描述符、网络地址和 ublk 设备容量。

调高 high 主要增加节点经历 burst 后保留的长期 warm capacity，不会让节点启动时立即创建 high 个 entry。调高 `fill_concurrency` 可以加快补充，但会增加同一批次的 process spawn、netns 和 API socket 初始化压力。

### 已有并发设计

- Firecracker pool 把 process spawn、netns 准备和 API socket wait 移出请求 critical path。
- Network、block 和 Firecracker pool 共用 watermark 模型。默认 low watermark 为 2，high watermark 为 64。
- 获取压力会把 fill target 逐步翻倍并向 high watermark 靠近，使经历过 burst 的进程保留更多 warm capacity。
- Firecracker pool refill 使用独立 runtime，每批最多按 `fill_concurrency` 并发创建，默认值为 4。
- ublk pool 的 refill 使用异步任务，并用 atomic flag 合并重复 refill 请求。
- ublk 的 per-image lock 只串行同一 image 的 open/restack，不阻塞无关 Template。
- shared memory device 避免为同一 Template 重复创建 memory block path，并共享 host page cache。
- memory layer background download 在 `envd` ready 后释放，减少后台流量与启动关键读取争抢带宽。

### 高并发风险

- 默认 low watermark 只有 2。突发量明显大于当前 warm 数量时，大部分请求仍会走 netns 创建、process spawn 或 ublk device create 冷路径。
- Network pool maintenance 逐个创建 slot；Firecracker refill 虽可并发，但默认每批只有 4 个，补充速度可能低于突发消耗速度。
- 自定义 stdout/stderr 路径会跳过 Firecracker warm pool。
- rootfs device 和 writable upper 不能在 sandbox 之间共享；每个实例仍需要独立设备状态和本地文件。
- shared memory 的首次 open 仍需解析 OverlayBD image。并发竞争会在两层 entry 检查后复用 winner，但竞争者可能已经做过一次冗余 open/device prepare，随后再清理。
- ublk daemon 集中管理所有设备。代码通过 DashMap、per-image lock 和 worker queues 减少冲突，但单进程 control path、设备数量和 io_uring/ublk 内核资源仍是需要压测的集中点。
- snapshot pages 尚未进入 Linux page cache 时，大量 Firecracker 会同时产生首读压力。共享 device 避免重复缓存，但不能消除第一次远程或磁盘读取的带宽需求。
- background download 的 per-layer concurrency 和全局 in-flight block 数有上限。这些限制能够防止 I/O 风暴，也会限制冷数据完全预热的速度。

关键源代码：

- `src/sandbox/firecracker/sandbox.rs`
- `src/sandbox/firecracker/instance.rs`
- `src/sandbox/firecracker/pool.rs`
- `src/sandbox/network/manager.rs`
- `src/sandbox/ublk/device.rs`
- `storage/ublk-daemon/src/server.rs`
- `storage/ublk-daemon/src/runtime.rs`
- `crates/warm-pool/src/lib.rs`

## 6. Ready、Proxy Route 与 Gateway Binding

VM resume 后，Orchestrator 调用 `wait_for_ready()`：

1. 按配置的 deadline 轮询 `envd /health`，单次 health probe 最长 1 秒。
2. `envd` ready 后通知 OverlayBD 可以开始 memory 和 rootfs background download。
3. 调用 `envd /init`，传入本次 launch 合并后的 env vars、workdir 和 user。
4. 把 metadata 从 `Creating` 更新为 `Running`。
5. 根据 sandbox 的 host interaction IP 发布节点内 proxy route。

### 6.1 Node 生成 `201` 和 sandbox ID 响应头

`Orchestrator::create_sandbox` 成功返回 `SandboxMetadata` 后，Node handler 从 `metadata.id` 取得 sandbox ID。它把完整 sandbox model 放进响应体，同时把同一个 ID 放进 `x_agentenv_sandbox_id` 字段。

```rust
match timer
    .time("create_sandbox", self.orchestrator.create_sandbox(request))
    .await
{
    Ok(metadata) => {
        let sandbox_id = metadata.id.to_string();
        Ok(
            SandboxesPostResponse::Status201_TheSandboxWasCreatedSuccessfully {
                body: self.sandbox_model(metadata),
                x_agentenv_sandbox_id: Some(sandbox_id),
            },
        )
    }
    Err(err) => Ok(SandboxesPostResponse::Status500_ServerError(
        Self::internal_error(&err),
    )),
}
```

这里返回的不是普通 JSON，而是 OpenAPI 生成的 `SandboxesPostResponse` 枚举。生成的 Axum adapter 再把枚举转换成 HTTP `201`、JSON body 和真实响应头。

```rust
if let Some(x_agentenv_sandbox_id) = x_agentenv_sandbox_id {
    let x_agentenv_sandbox_id = match header::IntoHeaderValue(x_agentenv_sandbox_id).try_into() {
        Ok(val) => val,
        Err(e) => {
            return Response::builder()
                .status(StatusCode::INTERNAL_SERVER_ERROR)
                .body(Body::from(format!("An internal server error occurred handling x_agentenv_sandbox_id header - {e}")))
                .map_err(|e| { error!(error = ?e); StatusCode::INTERNAL_SERVER_ERROR });
        }
    };

    let mut response_headers = response.headers_mut().unwrap();
    response_headers.insert(
        HeaderName::from_static("x-agentenv-sandbox-id"),
        x_agentenv_sandbox_id,
    );
}
let mut response = response.status(201);
```

响应体中的 ID 面向 SDK；响应头中的 ID 面向 Gateway。两者来自同一个 `metadata.id`，不存在第二次分配 ID 的过程。

### 6.2 Gateway 保留调度结果

创建请求进入 Gateway 时不含 sandbox ID，因此 Gateway 先调用 `Schedule`，并把返回的 `node` 保存在当前请求的局部变量中。此时 Scheduler 只完成节点选择，还不能建立 binding。

```go
if hasSandbox {
	resp, err := s.queryOnlyScheduler.LookupNode(
		routingCtx,
		&schedulerv1.LookupNodeRequest{SandboxId: sandboxID},
	)
	// ...
	node = resp.GetNode()
} else {
	resp, err := s.scheduler.Schedule(routingCtx, &schedulerv1.ScheduleRequest{
		Hint: hint,
	})
	// ...
	node = resp.GetNode()
}

s.proxyRequest(
	w,
	r.Clone(upstreamCtx),
	r.Context(),
	upstreamURL,
	node,
	proxyRequestOptions{
		recordAssignment: shouldRecordAssignment(r, routeSource, hasSandbox),
		hostRoute:        hostRoute,
		flushImmediately: longLived,
	},
)
```

`shouldRecordAssignment` 只对会创建新 sandbox 的成功请求开启记录。Template 启动对应“不含已有 sandbox ID 的 `POST /sandboxes`”。`POST /sandboxes-cold` 和 fork 也复用这套机制。

```go
func shouldRecordAssignment(r *http.Request, routeSource routeSource, hasSandbox bool) bool {
	if r.Method != http.MethodPost {
		return false
	}
	path := strings.TrimRight(r.URL.Path, "/")
	if !hasSandbox {
		return path == "/sandboxes" || path == "/sandboxes-cold"
	}
	if routeSource != routeSourcePath {
		return false
	}

	parts := strings.Split(strings.Trim(path, "/"), "/")
	return len(parts) == 3 && parts[0] == "sandboxes" && strings.TrimSpace(parts[1]) != "" && parts[2] == "fork"
}
```

因此，`sandbox -> node` 的两端来自不同阶段：`sandbox` 来自 Node 的创建结果，`node` 来自 Gateway 之前的调度结果。Gateway 是唯一同时持有这两项信息的组件。

### 6.3 Gateway 在转发响应前写入 assignment

Gateway 使用 Go `ReverseProxy.ModifyResponse` 检查 Node 响应。只有本请求需要记录 assignment，且 Node 返回 2xx 时，才进入 binding 逻辑。

```go
ModifyResponse: func(resp *http.Response) error {
	if !options.recordAssignment || resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil
	}
	return s.recordAssignmentFromResponse(originalCtx, resp, node)
},
```

`recordAssignmentFromResponse` 优先读取 `x-agentenv-sandbox-id`，也兼容 `e2b-sandbox-id`。命中响应头后，它直接调用 Scheduler，不读取响应体。

```go
func (s *Server) recordAssignmentFromResponse(
	ctx context.Context,
	resp *http.Response,
	node *schedulerv1.Node,
) error {
	recordCtx, cancelRecord := context.WithTimeout(
		ctx,
		recordAssignmentTimeout(s.requestTimeout),
	)
	defer cancelRecord()

	if sandboxID, ok := sandboxIDFromHeaders(resp.Header); ok {
		s.recordAssignment(recordCtx, sandboxID, node, "response_header")
		return nil
	}

	// 没有响应头时才读取并恢复 body，兼容从 JSON 提取一个或多个 ID。
	// ...
}
```

这个 header 快路径避免了 Gateway 缓冲创建响应，也避免了读取失败或响应体超过 `maxRespSize` 后把成功响应改成 `502`。对应单元测试明确断言：有 header 时，response body 不会被读取或关闭。

真正的 gRPC 请求包含新 sandbox ID 和先前选中的完整 Node：

```go
func (s *Server) recordAssignment(
	ctx context.Context,
	sandboxID string,
	node *schedulerv1.Node,
	source string,
) {
	_, err := s.scheduler.RecordAssignment(
		ctx,
		&schedulerv1.RecordAssignmentRequest{
			SandboxId: sandboxID,
			Node:      node,
		},
	)
	if err != nil {
		s.logger.Warn("record assignment failed", /* ... */)
		return
	}
	// ...
}
```

`ModifyResponse` 在响应交给 SDK 前同步执行，因此这次 RPC 会增加创建响应延迟。其 timeout 不超过 Gateway request timeout，并被硬限制在 5 秒。

但 `recordAssignment` 会吞掉 RPC 错误，只记录 warning。Scheduler 暂时不可用时，Node 的 `201` 仍会转发给 SDK，不会因为 binding 写失败而变成创建失败。

### 6.4 Scheduler 保存 binding，供后续请求反查

`RecordAssignment` 的协议很小，只传递 `sandbox_id` 和 `Node`：

```protobuf
message RecordAssignmentRequest {
  string sandbox_id = 1;
  Node node = 2;
}
```

Scheduler 依次检查 sandbox ID、Node ID、endpoint，以及 Node 是否仍在调度节点列表中，然后调用 `BindingStore::Record`。

```go
func (s *Service) RecordAssignment(
	_ context.Context,
	req *schedulerv1.RecordAssignmentRequest,
) (*schedulerv1.RecordAssignmentResponse, error) {
	if strings.TrimSpace(req.GetSandboxId()) == "" {
		return nil, status.Error(codes.InvalidArgument, "sandbox_id is required")
	}
	node := NodeFromProto(req.GetNode())
	if strings.TrimSpace(node.ID) == "" || strings.TrimSpace(node.Endpoint) == "" {
		return nil, status.Error(codes.InvalidArgument, "node_id and endpoint are required")
	}
	if !s.isKnownNode(node) {
		return nil, status.Error(codes.InvalidArgument, "node is not in scheduler node list")
	}
	if err := s.store.Record(req.GetSandboxId(), node, time.Now()); err != nil {
		return nil, status.Error(codes.Unavailable, "binding store unavailable")
	}
	return &schedulerv1.RecordAssignmentResponse{}, nil
}
```

默认的内存实现把 binding 保存为 `sandboxID -> {node, expiresAt}`，并维护 `nodeID -> sandboxIDs` 反向索引。`Record` 会刷新 TTL；默认 TTL 为 30 秒。

配置 `scheduler.redis_addr` 后，Redis 实现使用 Lua 脚本原子更新 sandbox binding 和 Node 反向索引，并为 binding 设置 TTL。它允许 primary scheduler 写入、query-only scheduler replicas 读取同一份映射。

后续请求携带 sandbox ID 时，Gateway 不再调用 `Schedule`，而是调用 `LookupNode`。Scheduler 通过 `BindingStore::Get` 返回此前记录的 Node，Gateway 再把请求代理到该节点。

```text
创建请求：Schedule -> Node 创建 -> 201(header: sandbox ID)
                              -> Gateway RecordAssignment(ID, Node)

后续请求：sandbox ID -> Gateway LookupNode(ID) -> Node -> sandbox
```

启用节点的 Scheduler reporter 后，heartbeat 还会上报当前 `sandbox_ids` roster。Scheduler 的 `ReconcileNode` 会刷新仍存在的 binding，并删除该 Node 已不再报告的 binding，因此 heartbeat 同时承担定期续期、校正和失败补偿。

### 6.5 一致性边界与并发影响

VM 创建与 binding 写入不是一个事务。Node 返回非 2xx 时，Gateway 不记录 binding；Node 已创建成功但连接提前断开时，也可能没有即时 binding，需要等待 heartbeat 补齐。

反过来，SDK 也可能在 Gateway 已记录 binding 后断开连接。此时沙箱和路由都存在，但调用方未必拿到 ID。创建 API 没有把这两个步骤包装成跨组件事务，需要由上层保存请求关联信息，或依赖 timeout action 回收。

高并发创建时，每个成功 sandbox 都产生一次独立 `RecordAssignment` RPC。内存 store 的 `Get`、`Record`、`ReconcileNode` 共用同一把 mutex；大 roster 的 heartbeat reconcile 会暂时阻塞其他 binding 操作。

Redis 模式避免单个 Scheduler 进程持有全部 binding，但每次创建仍有一次同步 Redis Lua 操作。大规模 heartbeat roster 也会放大 gRPC payload 和 Lua 脚本执行时间，需要结合 assignment RPC latency 和 binding lookup miss 监控。

### 6.6 启动末段的其他并发设计

- envd readiness 有总 deadline 和单次 probe timeout，单个失效 VM 不会无限占住请求。
- proxy route 只在 sandbox handle 仍是当前实例时发布，防止旧启动任务覆盖新 generation。
- binding 在创建成功后写入，避免把失败 sandbox 路由到节点。
- heartbeat 中的 sandbox roster 可以补充和校正 binding。

### 6.7 启动末段的其他高并发风险

- `POST /sandboxes` 是同步接口，Gateway、SDK 和 Node API 会一直等待 snapshot resolve、VM restore、envd ready 和 init 完成。
- Gateway 普通请求 timeout 的代码默认值为 30 秒，仓库的 `services/config/local.json` 示例将其配置为 90 秒。排队、cache miss 或 pool miss 使尾延迟超过部署值时，上游可能返回 timeout，但 cancellation-safe 创建仍会继续。
- Gateway 只有收到成功响应后才能立即 `RecordAssignment`。如果连接提前断开，需要等待后续 heartbeat roster 才能补上 binding。
- readiness polling 和 `envd /init` 为每个 sandbox 独立执行。bootstrap HTTP client 特意禁用 idle connection reuse，以避免 IP 被下一代 VM 复用时误用旧连接；这也意味着每个启动至少需要新的 TCP connection。

关键源代码：

- `src/api/impls/sandbox.rs::sandboxes_post`
- `src/api/generated/src/server/mod.rs::sandboxes_post`
- `services/gateway/internal/server.go::handleProxy`
- `services/gateway/internal/server.go::recordAssignmentFromResponse`
- `services/api/proto/scheduler.proto`
- `services/scheduler/internal/service.go::RecordAssignment`
- `services/scheduler/internal/store.go::InMemoryBindingStore`
- `services/scheduler/internal/redis_store.go::RedisBindingStore`

## 同一 Template 突发启动时会发生什么

假设一个冷节点同时收到 100 个相同 Template 的创建请求：

1. Scheduler 可能在新 heartbeat 到来前持续认为节点仍有容量，因为 Schedule 不做 reservation。
2. Node 上第一个请求成为 snapshot cache miss 的 singleflight leader，其余请求等待同一 artifact。
3. artifact ready 后，请求同时进入启动路径。最先到达的少量请求命中 warm pools，其余请求退化到冷创建。
4. 第一个 memory ublk acquire 创建 shared device；后续请求复用它，并共享 page cache。
5. 每个请求仍创建独立 rootfs upper、sandbox metadata、Firecracker VM 和 envd readiness loop。
6. 随着 acquisition pressure 增长，warm pool fill target 上升，但 refill 主要改善后续 burst，无法完全吸收已经到达的 100 个请求。
7. 每个 sandbox ready 后分别返回；Gateway 再逐个记录 binding。

因此，同 Template 高并发的扩展性不是简单的“100 次完整冷启动”，也不是“一次恢复复制 100 份”。实际形态是：artifact 和 memory read path 高度共享，而 VM、rootfs writable state、network identity 和 ready handshake 仍按实例增长。

Template 启动链路当前已有的指标、span、结构化日志及观测盲区，单独整理在 [基于 Template 启动沙箱的现有观测能力](./template-sandbox-observability.md)。

## 压测案例：2U2G、30 sandbox/s、共 400 个

以下判断假设 400 个 sandbox 会同时保持 Running。若测试完成后立即释放，稳态资源压力会更低，但 13.3 秒注入窗口内的启动压力仍然存在。

### 负载量化

400 个请求以 30/s 注入只需要约 13.3 秒。若平均创建耗时为 `L` 秒，系统内同时处于创建状态的请求数可近似为 `30 * L`。

例如平均创建耗时为 5 秒时，约有 150 个创建并发；增长到 10 秒时，约有 300 个创建并发。只要完成速率低于 30/s，队列和尾延迟就会持续增长。

400 个 2U2G sandbox 合计声明 800 vCPU 和 800 GiB guest memory。snapshot memory 使用按需读取和 COW，因此初始 host RSS 不等于 800 GiB。

但 guest 写入工作集、页表、Firecracker process 和 CPU 调度开销仍按实例增长。

若有 `N` 个节点且调度均匀，每个节点名义上承受约 `30/N` 次创建每秒和 `400/N` 个实例。实际分布还会受 heartbeat 滞后、resource filter 和调度策略影响。

### 高概率阻塞点

| 优先级 | 环节 | 为什么在该负载下容易阻塞 | 典型表现 |
|---|---|---|---|
| P0 | Node CPU、memory 与 guest ready | 单节点可能同时调度数百个 Firecracker 和最多 800 vCPU；envd health/init 需要 guest 真正获得 CPU | `create_sandbox` 上升，CPU PSI、context switch、envd ready 时间同时上升 |
| P0 | Firecracker 与 network pool miss | 默认 low 只有 2，30/s 下约 67 ms 就会消耗完；后续进入 process spawn、netns、veth 和 iptables 冷路径 | 前几个请求快，随后延迟迅速抬升；debug 日志中 warm hit 比例下降 |
| P0 | 每实例 rootfs ublk 创建 | memory device 可以共享，但每个 sandbox 仍需独立 rootfs runtime upper 和 ublk device | `create_runtime_overlaybd` P95/P99 上升，ublk device 数和 I/O PSI 增长 |
| P1 | snapshot memory/rootfs 首读 | shared memory device 和 page cache 只避免重复缓存，不能消除第一轮远程或磁盘读取 | OverlayBD remote read latency/bytes 与 I/O PSI 同时上升 |
| P1 | Scheduler 放置偏斜 | Schedule 不做 reservation，resource filter 依赖周期性 heartbeat；burst 内可能继续选择已过载节点 | 某些 Node 的 starting count 很高，其他节点仍空闲 |
| P1 | Gateway/SDK timeout | 创建接口同步等待 envd init；Node 在请求取消后仍可能继续创建 | 客户端出现 timeout/504，但 Node sandbox 数仍继续增加 |
| P2 | 首次 Template artifact resolve | 同 Template 的 cache miss 会合并到一个 leader，冷启动初期的请求共同等待该下载 | 只有测试开头的 `load_snapshot` 高，缓存热后明显下降 |

Scheduler RPC 本身通常不是首要计算瓶颈。更值得检查的是它是否把流量压向少数节点，以及 heartbeat 看到的容量是否落后于实际 Creating 数量。

Firecracker refill 每批最多并发 `fill_concurrency` 个 entry。其理论补充速率约为 `fill_concurrency / 单个 entry 创建耗时`；如果低于节点收到的请求速率，pool 在整个注入窗口内都追不上消耗。

Network pool 的 maintenance cycle 逐个创建 slot。pool miss 时，请求线程也会同步执行 `create_network()`，因此大量冷路径会同时调用内核网络和 iptables 相关操作。

ublk daemon 会为每个 RPC 接受独立 Unix socket connection，并并发启动 handler，不是单连接串行服务器。

但所有请求仍共享 daemon process、ublk control ring、ImageService、per-image lock 和内核设备资源。

### 定位步骤

第一步先确认压测工具确实把 30/s 送到了 Gateway。记录“计划发送时间、实际发送时间、响应完成时间、状态码和 sandbox ID”，并对比 Gateway 的请求 `_count` 增长率。

若压测端发送速率不足，先检查 SDK HTTP connection pool、负载发生器 CPU 和本地文件描述符；此时不能把客户端排队误判为 AgentENV 阻塞。

第二步比较 Gateway 的 Schedule RPC 与 upstream proxy：

```promql
histogram_quantile(0.99,
  sum by (le, instance, rpc) (
    rate(agentenv_gateway_scheduler_rpc_duration_seconds_bucket{rpc=~"Schedule|RecordAssignment"}[1m])
  )
)

histogram_quantile(0.99,
  sum by (le, instance) (
    rate(agentenv_gateway_upstream_proxy_duration_seconds_bucket{route="/sandboxes"}[1m])
  )
)
```

如果 Schedule 保持很低而 upstream proxy 上升，调度 RPC 不是阻塞点，继续看 Node。如果 Schedule 上升，再对照 Scheduler 服务端 RPC latency、CPU 和节点过滤结果。

第三步用 Node 已有的两个 stage 切分 Template resolve 与实例启动：

```promql
histogram_quantile(0.99,
  sum by (le, instance, stage, status) (
    rate(agentenv_sandbox_stage_duration_seconds_bucket{operation="create_warm"}[1m])
  )
)

sum by (instance, stage) (
  agentenv_sandbox_stage_inflight{operation="create_warm"}
)
```

- `load_snapshot` 高：检查 artifact cache、OSS/P2P latency 和首次 singleflight 等待。
- `load_snapshot` 低、`create_sandbox` 高：阻塞位于 rootfs device、network/Firecracker、snapshot load/resume 或 envd ready/init。
- inflight 持续增长：Node 完成速率低于到达速率，已经形成积压。

HTTP 取消后，cancellation-safe Orchestrator task 仍可继续运行，但外层 stage timer 可能已经被释放。因此还要同时查看 `/nodes` 中的 `sandboxStartingCount`，不能只依赖 `agentenv_sandbox_stage_inflight`。

第四步检查 ublk 与 OverlayBD：

```promql
histogram_quantile(0.99,
  sum by (le, instance, operation, status) (
    rate(agentenv_ublk_operation_duration_seconds_bucket{
      operation=~"create_runtime_overlaybd|acquire_shared_memory"
    }[1m])
  )
)
```

同一个 Template 的 `acquire_shared_memory` 正常只在首次创建或进程内复用失效时出现。若它大量出现，应检查 snapshot key 是否一致以及 shared device 是否被提前释放。

`create_runtime_overlaybd` 每个 sandbox 都会发生。它的 P99 随并发明显上升时，优先检查 9103 端口上的 ublk daemon 指标、daemon CPU、ublk device 数、磁盘 latency 和 I/O PSI。

第五步观察主机资源曲线，并与每秒完成数对齐：

```bash
vmstat 1
iostat -xz 1
pidstat -dur 1
cat /proc/pressure/cpu
cat /proc/pressure/memory
cat /proc/pressure/io
ps -C firecracker --no-headers | wc -l
```

- CPU PSI 与 context switch 先升高：更像 Firecracker process、guest 调度或 envd fan-out。
- I/O PSI、磁盘 await 或 OverlayBD remote read 先升高：更像 rootfs/memory 首读或 ublk path。
- memory PSI、major fault、swap 或 OOM 事件升高：2G guest 的实际 working set 已超过 host 可承载范围。
- 系统指标平稳但 `create_sandbox` 仍高：需要补充 Firecracker API 与 envd 的阶段计时。

### 建议的对照实验

不要直接从一次 30/s 结果推断单点原因。建议保持 Template 和总量不变，依次做以下对照：

1. 速率阶梯：`5 -> 10 -> 15 -> 20 -> 30/s`，找出 P99 和 inflight 开始非线性增长的拐点。
2. 热缓存与冷缓存：同一节点连续运行两轮。只有第一轮 `load_snapshot` 慢，说明 artifact cold start 占主要影响。
3. 空 guest 与真实 workload：envd init 后不运行任务，再与实际 agent workload 比较，用来分离启动开销和 guest working set 压力。
4. 单节点与多节点：保持集群总速率不变，检查瓶颈是否随节点数近似线性改善，以及调度是否均匀。
5. pool 参数 A/B：提高 low 和 `fill_concurrency` 后复测。如果只有前段延迟改善、后段仍恶化，主瓶颈不在 process/netns 预热。
6. 逐级总量：固定 30/s，分别启动 50、100、200、400 个。若延迟取决于当前 Running 数而不是注入速率，主因更可能是 CPU、memory 或设备规模。

现有指标无法把 `create_sandbox` 进一步拆成 Firecracker restore 与 envd ready。若上述步骤定位到后半段，需要增加细粒度计时。

最小补充点是 `launch_sandbox` 的 `start_nowait`、`wait_for_ready`，以及 `start_resume` 的 rootfs、network/spawn、shared memory、`load_snapshot_file` 和 `resume`。

## 优先验证的瓶颈

以下排序是基于代码结构的风险判断，不代表已有 benchmark 结果。

| 优先级 | 风险 | 判断依据 | 建议观察 |
|---|---|---|---|
| P0 | Scheduler 突发超配 | 无 reservation；Template hint 不含资源；heartbeat 有时间间隔 | 单节点 `starting_sandbox_count` 峰值、Schedule 到 start 的并发数 |
| P0 | 同步创建尾延迟和 timeout | API 必须等待 envd init；取消后后端继续 | Gateway 504、SDK timeout、创建完成但未及时绑定的数量 |
| P1 | warm pool 被瞬时耗尽 | 默认 low=2；refill 速度有限 | 先看现有 debug 日志；当前没有统一 hit ratio 与 refill latency 指标 |
| P1 | 首次 snapshot cache miss | 同 key singleflight、远程 artifact I/O | `load_snapshot` P95/P99 与 OSS latency；当前没有 artifact cache hit ratio |
| P1 | 冷 memory page 首读 | shared device 只能共享一次读取结果，不能消除第一次 I/O | resume 后 page fault/read latency、registry/OSS bandwidth |
| P2 | ublk daemon control path | 所有 block device 由一个 daemon 管理 | acquire/create operation latency、device count、io_uring queue saturation |
| P2 | envd ready fan-out | 每实例独立 probe/init，新建 TCP connection | envd ready latency、connection errors、guest CPU contention |

## 代码路径索引

```text
crates/aenv/src/client/sandboxes.rs
  -> POST /sandboxes

services/gateway/internal/server.go
  -> buildScheduleHint
  -> Scheduler.Schedule
  -> reverse proxy to node

src/api/impls/sandbox.rs::sandboxes_post
  -> SnapshotManager::load_runnable
  -> Orchestrator::create_sandbox

src/snapshot/manager.rs::load_runnable
  -> SnapshotRepository::get
  -> SnapshotRuntimeResolver::resolve

src/orchestrator/service.rs::create_sandbox_inner
  -> LaunchPlan::for_create_from_snapshot
  -> launch_sandbox
  -> SandboxBackendFactory::build_from_snapshot

src/sandbox/firecracker/factory.rs::build_from_snapshot
  -> FirecrackerSandbox::from_snapshot
  -> FirecrackerSandbox::start_resume
  -> UblkDeviceManager::create_overlaybd_runtime_device
  -> UblkDeviceManager::get_or_create_shared_mem
  -> FirecrackerInstance::load_snapshot_file
  -> FirecrackerInstance::resume

src/orchestrator/service.rs::launch_sandbox
  -> SandboxBackend::wait_for_ready
  -> metadata Creating -> Running
  -> publish proxy route

services/gateway/internal/server.go::recordAssignmentFromResponse
  -> Scheduler.RecordAssignment
```
