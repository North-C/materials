# AgentENV 架构

AgentENV 在隔离且支持快照的 Firecracker microVM 中运行 AI Agent。系统以**存储子系统**为核心，为 VM 提供可挂载的分层块设备，并通过 ublk 恢复内存快照。每个节点还包含负责沙箱生命周期的 **Orchestrator**，多节点部署则由 Gateway 和 Scheduler 组成的**分布式控制平面**负责路由。

## 系统总览

```
                    ┌───────────────────────────────────────────────────────────┐
                    │                       AgentENV Node                       │
                    │                                                           │
                    │  ┌──────────┐   ┌──────────────┐                          │
                    │  │ API      │──>│ Orchestrator │                          │
                    │  │ (Axum)   │   │ (lifecycle)  │                          │
                    │  └──────────┘   └──────┬───────┘                          │
                    │                        │                                  │
                    │              ┌─────────▼───────────┐                      │
                    │              │  Firecracker VM     │                      │
                    │              │                     │                      │
                    │              │  /dev/vda (tools)   │                      │
                    │              │  /dev/vdb (user fs)─┼───┐                  │
                    │              │  VM memory ─────────┼───┼──┐               │
                    │              │                     │   │  │               │
                    │              └─────────────────────┘   │  │               │
                    │                                        │  │               │
                    │    Block device path:                  │  │               │
                    │              ┌────────────────────────▼──┐│               │
                    │              │  ublk (/dev/ublkbN)       ││               │
                    │              │  userspace block device   ││               │
                    │              └────────────┬──────────────┘│               │
                    │                           │               │               │
                    │              ┌─────────────▼─────────────┐│               │
                    │              │  overlaybd                ││               │
                    │              │  ┌───────┐ ┌───────┐      ││               │
                    │              │  │ upper │ │layer 0│ ...  ││               │
                    │              │  │ (r/w) │ │(r/o)  │      ││               │
                    │              │  └───────┘ └───────┘      ││               │
                    │              └───────────────────────────┘│               │
                    │                                           │               │
                    │    Memory restore path:                   │               │
                    │              ┌────────────────────────────▼───┐           │
                    │              │  ublk (/dev/ublkbM)            │           │
                    │              │  read-only memory block device │           │
                    │              │  (shared across same-snapshot  │           │
                    │              │   sandboxes via refcounting)   │           │
                    │              └────────────┬───────────────────┘           │
                    │                           │                               │
                    │              ┌─────────────▼──────────────┐               │
                    │              │  overlaybd (mem layers)    │               │
                    │              │  ┌───────┐ ┌───────┐       │               │
                    │              │  │snap N │ │snap 0 │ ...   │               │
                    │              │  │(r/o)  │ │(r/o)  │       │               │
                    │              │  └───────┘ └───────┘       │               │
                    │              └────────────────────────────┘               │
                    └───────────────────────────────────────────────────────────┘
```

## 存储系统

关于 OCI `userImage` 如何成为 guest 可写根文件系统，以及 tools drive 在启动过程中的作用，请参阅[沙箱基础镜像的数据流](./sandbox-base-image.md)。

存储子系统把分层镜像文件转换为 VM 可挂载的块设备，并在恢复快照时提供基于 ublk 的内存恢复能力。当前存储系统主要由以下四个 crate 组成。

### overlaybd (`storage/overlaybd/`)

OverlayBD 是基于 LSMT（Log Structured Merge Tree）的分层镜像格式。

**镜像结构**：每个层文件包含一个 `HeaderTrailer`（magic `LSMT\0\1\2`、UUID、flags、index/data offsets）和一个 `DiskSegmentMapping` 数组。

每条映射占 16 字节，以位字段保存 50-bit offset、14-bit length、55-bit physical offset、zeroed flag 和 layer tag。不可变的压缩只读层位于底部，顶部只有一个可写 upper layer。

**读取路径**：`ImageFile` 根据 segment index 从上到下查找各层。第一个包含目标块范围映射的层返回数据；upper layer 中没有映射的范围继续落到下层查找。

**写入路径**：所有写入都追加到 upper layer。对应 index 先在内存中更新，并在 sync 时落盘。

**存储后端**（通过 `VirtualFile` trait 插拔）：
- `LocalFile`：通过 io_uring 执行 pread/pwrite，可选 O_DIRECT。
- `registryfs_v2`：从 OCI Registry 远程读取镜像层。
- `tar`：读取 tar archive。
- 可选缓存层：缓存解压后的数据块。

**压缩**：使用 zstd level 3，并通过 random-access jump table 和 CRC32C checksum 支持随机读取和完整性检查。

**快照**：`ImageFile::create_snapshot_and_restack()` 是 pause 的主要路径。它通过 `LSMTFile::close_seal_and_reopen()` 封存当前 upper layer，使其成为最新的 lower layer，再原地打开一个新的可写 upper。

`image/snapshot.rs::export_upper_as_snapshot_layer()` 保留了供打包和导出流程使用的显式 upper export 路径。

**关键文件**：
- `image/image_file.rs`：提供高层镜像抽象。
- `lsmt/file/`：负责 LSMT 堆叠；`readonly.rs` 定义 `LSMTReadOnlyFile`，`readwrite.rs` 定义 `LSMTFile`，`stack.rs` 提供 open/merge/stack helpers。
- `lsmt/format.rs` 与 `lsmt/index.rs`：分别定义二进制格式和管理 segment mapping。
- `compression/zfile.rs`：负责压缩。
- `image/snapshot.rs`：负责显式 upper export。

### ublk (`storage/ublk/`)

ublk crate 基于 Linux ublk kernel driver 实现异步 userspace block device server，把 OverlayBD image 或原始 CoW 文件暴露为 `/dev/ublkbN` 块设备。

**设备生命周期**：
1. `UVMUblkCtrlBuilder` 通过 io_uring `UringCmd` 向 `/dev/ublk-control` 发送 `ADD`。
2. Kernel 分配 device ID，并创建 control device `/dev/ublkcN` 和 block device `/dev/ublkbN`。
3. 系统为每个 queue 启动 worker thread，每个线程持有 thread-local `AsyncIoRing` 和通过 slab 分配的 I/O slots。
4. Kernel 将 block I/O 分发到 mmap 的 `ublksrv_io_desc` 数组，userspace 随后异步处理请求。
5. `delete_dev()` 负责销毁设备。

**Target 实现**（`UVMUblkTarget` trait）：
- `OverlaybdTarget`：封装 `ImageFile`，提供完整的分层镜像 I/O。
- `BasicCowTarget`：在只读 origin file 上按 chunk 实现 copy-on-write。每个 chunk 通过 `AtomicU8` 跟踪 `Origin -> Copying -> Cow` 状态，避免重复复制，并合并相邻读取请求。

**I/O buffer**：`AutoRegBuffer` 在 kernel 6.8+ 上通过 sparse buffer table 实现 zero-copy；`UserBuffer` 使用传统内存分配方式。

**关键文件**：`lib.rs` 提供 public API；`ctrl.rs` 实现 device controller；`dev.rs` 管理 device 和 queue；`queue.rs` 处理 I/O descriptor；其余入口包括 `io_buffer.rs`、`impls/cow.rs` 和 `impls/overlaybd_target.rs`。

### ublk-daemon (`storage/ublk-daemon/`)

`uvm-ublk-daemon` 是常驻进程，在同一进程中管理全部 ublk 设备，并通过 Unix domain socket 与 AgentENV node 通信。

- RPC 支持为 sandbox rootfs/extra drives 创建 OverlayBD runtime、为非 runtime 调用方创建原始 OverlayBD/COW 设备，以及 warm-pool acquire/release、resize capability query、restack snapshot、delete 和 shutdown。
- Node runtime 通过 `UblkDaemonClient` 启动并监控 daemon process。
- 面向节点的单例 `UblkDeviceManager` 位于 `src/sandbox/ublk/device.rs`，它把设备生命周期操作委托给 daemon client，device ID 则由 daemon 分配。

这种拆分让独立进程持有 ublk device ownership 和 io_uring control，而 node server 只负责编排生命周期状态。

### storage-util (`storage/util/`)

该 crate 提供 ublk 和 OverlayBD 共用的 io_uring 抽象。

- `AsyncIoRing<S>`：通用异步 io_uring wrapper，使用基于 slab 的 `RingFuture` 传递 CQE，同时支持标准 64B 和扩展 128B SQE。
- `IoRingWorker`：启动持有 thread-local io_uring instance 的专用 worker thread，并通过 MPSC channel 提交任务，避免跨线程加锁。
- `ReloadableIDAllocator`：基于 bitmap 和 free list 以 O(1) 完成 ID 分配与回收，并支持在重启时重新载入已占用 ID。

### 沙箱集成（`src/sandbox/ublk/` + `src/sandbox/extra_drive.rs`）

- `device.rs`：持有进程级 `UblkDeviceManager`，通过 `uvm-ublk-daemon` 创建、删除并生成所有 runtime ublk device 的快照。
- `overlaybd.rs`：为 rootfs 和 attached drives 生成 runtime config，包括重写路径和创建指向 layer file 的 symlink。
- `extra_drive.rs`：准备用户指定的额外块设备，并在失败时回滚。只读盘和可写盘遵循相同的 per-sandbox device lifecycle，唯一语义差异是 OverlayBD 是否生成 writable upper。

### 内存快照恢复

内存快照恢复使用 ublk-backed OverlayBD device，而不是 userfaultfd。Resume 时，系统根据多层 memory OverlayBD layers 创建只读 ublk device，并以 `BackendType::File` memory backend 交给 Firecracker。Firecracker mmap 该设备，首次写入页面时通过 COW 将其复制到匿名内存，因此底层设备始终不会被修改。

**共享机制**：从同一 snapshot template 启动的多个沙箱通过引用计数共享一个 memory ublk device，使 Linux page cache 可以在使用相同 memory image 的沙箱之间复用，从而显著减少并发启动时的 I/O。

**内存快照创建**：Pause 时，Firecracker native diff snapshot（`SnapshotType::Diff`）生成 sparse `mem.bin`，内部通过 mincore 查找 present pages。

随后，`convert_sparse_mem_to_overlaybd` 将 sparse file 打包为 OverlayBD 层，并与历史 snapshot 的 parent layers 堆叠成完整的分层内存镜像。

> **说明**：`storage/uffd-core/` 保留了另一套基于 userfaultfd 的内存恢复实现，仅供参考，不参与 workspace build。

## 节点内子系统

每个节点都是运行在 Linux host 上的 AgentENV server binary（`src/bin/server.rs`）。Host 必须提供 `/dev/kvm`，并配置一种 virtualization mode。默认使用 KVM；PVM 当前仅支持 x86_64，并要求 host 已加载 `kvm_pvm` module。

| 子系统 | 位置 | 职责 |
|--------|------|------|
| API layer | `src/api/` | Axum HTTP server、OpenAPI endpoints、sandbox service reverse proxy，以及 node/admin APIs |
| Orchestrator | `src/orchestrator/` | Sandbox lifecycle state machine、自动回收、资源指标计算、累计创建计数，以及跨重启的 paused-sandbox persistence |
| Observability | `src/observability/` | Node identity、machine info、请求时 host metrics 采集、admin API 的 node snapshot，以及可选 Scheduler heartbeat |
| Sandbox | `src/sandbox/` | Firecracker VM、network namespace、rootfs、envd 通信、ublk devices，以及 network/block/Firecracker warm pools |
| Snapshot + Template Builder | `src/snapshot/`、`src/template/` | `src/snapshot/` 管理 committed snapshot storage 和 runtime resolution；`src/template/` 提供面向用户的 snapshot builder |
| P2P artifact transport | `src/p2p/` | 可选的 artifact lookup、publish 和 fetch 层，支持 disabled 与 iroh-backed transport |
| Config | `src/cfg.rs` | Firecracker paths、machine specs、timeouts、shared pool、observability、P2P 和 Scheduler report 的 TOML 配置 |

### 沙箱网络

沙箱网络由进程级 `NetworkManager`（`src/sandbox/network/manager.rs`）和每个 slot 独立的 `Slot` object（`src/sandbox/network/slot.rs`）共同管理。

- 每个 slot 根据 `[network.internal]` 和稳定 index 生成地址组。默认网段为 `10.11.0.0/16` 与 `10.12.0.0/16`，VM tap link 固定为 `169.254.0.20/30`。Slot 同时持有一个 sandbox network namespace 对应的 host veth name、namespace path 和 iptables rules。
- Network policy 支持基础 allow/deny 策略和显式 egress rules。`/sandboxes/{sandboxID}/network` endpoint 可在运行时替换每个沙箱的 `allowOut`（CIDR/IP/domain patterns）和 `denyOut`（仅 CIDR/IP）规则，其中 allow 始终优先。
- `allocate_any()` 优先从 warm-slot pool 获取 slot；没有可用项时，按需创建 namespace、veth、tap 和 iptables 配置。
- Warm-pool maintenance 由一个基于 Condvar 的后台 worker 执行，并使用 low/high watermarks 控制容量。
- `release()` 将 slot 放回 warm pool。启用 maintenance 后，即使容量已经超过 high watermark，也会先入队，再由 worker 异步清理。
- `[pool]` 提供共享 watermarks，`[pool.network].maintenance_enabled` 控制 network worker 是否运行。
- `NetworkManager` 是进程级单例。Orchestrator shutdown 会在删除剩余沙箱后显式调用 `NetworkManager::shutdown()`，清空缓存 slot，并避免 teardown 期间发生新的并发分配。
- 正常退出时应调用 `NetworkManager::shutdown()`。此外，manager 还提供 `Drop` 和 `libc::atexit` handler，在异常关闭或测试结束时 best-effort 清理残留 namespace 和 veth interface。

Snapshot resume 还可以通过 `[pool.firecracker]` 预创建 `(network slot, Firecracker process)`。恢复时，warm entry 将 network slot、process 和 Firecracker CWD 转交给沙箱，从而避开关键路径上的进程启动和 API socket 等待。

`[pool.block]` 控制 ublk daemon 的 OverlayBD warm-device pool。它沿用顶层 watermarks，但由于可复用块设备与镜像和容量相关，需要从请求路径异步补充。

### 可观测性数据流

节点可观测性由请求时的 host metrics 采集和 node snapshot 投影共同组成。

- `src/orchestrator/metrics.rs` 定义每种 lifecycle state 如何计入 running、starting、paused、CPU 和 memory 汇总值。
- `src/orchestrator/service.rs::metrics_snapshot()` 在收到请求时，根据当前 sandbox metadata 计算资源汇总值。只有 create success 和 failure total 使用增量 counter。
- `src/observability/identity.rs` 解析稳定的 node identity，包括 node ID、cluster ID、service instance ID、package version 和 build-time commit。
- `src/observability/machine.rs` 从 `/proc/cpuinfo` 读取静态 machine descriptor。
- 每次请求 node snapshot 时，`src/observability/host.rs` 都会采集 host CPU、memory 和 disk usage。CPU percent 根据两次 `/proc/stat` sample 计算；首次请求使用 100ms 采样窗口，避免返回人为的零值。
- `src/observability/service.rs` 将 Orchestrator counters、identity、machine info、请求时 host metrics 和当前 sandbox ID roster 合并为 `NodeSnapshot`，供 admin endpoints 返回，并由 heartbeat report 复用。
- `src/observability/reporter.rs` 可通过 gRPC 定期向 Scheduler 发送 `Heartbeat`，并在 shutdown 时 best-effort 调用 `UnregisterNode`。
- Scheduler report 可在 TOML 的 `[observability.scheduler_report]` 中配置，并使用 `[cluster].scheduler_endpoint` 作为共享 Scheduler 地址。
- `AENV_OBSERVABILITY_SCHEDULER_REPORT_ENABLED`、`AENV_OBSERVABILITY_SCHEDULER_ENDPOINT` 和 `AENV_OBSERVABILITY_REPORT_INTERVAL_SECS` 可以覆盖 reporter 开关、地址和周期。
- 如果 P2P transport 提供 local endpoint，reporter 会将其加入 Scheduler heartbeat，供其他节点发现。

因此，sandbox metadata store 是当前资源统计的事实来源，独立的 create counters 则保留累计历史。

可观测性子系统有两个相互独立的配置范围。

- `observability.enabled`：控制是否创建 node observability service。关闭后，node/admin observability endpoints 会降级，而不是尝试合成不完整的 snapshot。
- `observability.scheduler_report.enabled`：控制是否向 Scheduler 发送 heartbeat，可由 `AENV_OBSERVABILITY_SCHEDULER_REPORT_ENABLED` 覆盖。启用后必须配置 `[cluster].scheduler_endpoint` 或 `AENV_OBSERVABILITY_SCHEDULER_ENDPOINT`。

### P2P Artifact 传输

`src/p2p/` 为需要在 runtime nodes 之间交换已校验文件的模块提供项目级 artifact transport 抽象。调用方依赖 `P2pTransport` trait，主要操作包括 `lookup`、`lookup_with_hints`、`fetch`、`publish`、`unpublish`、`local_endpoint` 和 `shutdown`。

默认的 `DisabledP2pTransport` 不执行实际传输：lookup 不返回 descriptor，publish 是 no-op，fetch 返回 `TransportDisabled`。

`IrohBlobsP2pTransport` 后端会启动内嵌 `iroh` endpoint，通过 `iroh-blobs` 提供 artifact bytes，并在同一 endpoint 上运行小型 AgentENV catalog protocol，将稳定 artifact key 映射为与传输实现无关的 descriptor。

每个 P2P artifact key 表示一个逻辑 artifact。Lookup 最多返回一个 descriptor，优先查询 local catalog，再按顺序查询已发现的 peers。

Descriptor 包含 stable key、provider node ID、可选 provider endpoint、backend-specific locator string 和模块定义的 JSON metadata。Backend locator 对调用方保持不透明；在 iroh 中，它是用于 content-addressed fetch 的 `iroh-blobs` hash。

Remote fetch 成功后，本地节点会 best-effort 发布已获取的 blob。该节点由此成为后续 peer 的 provider，使 artifact 能够在 cluster 中逐步扩散。

Peer discovery 由 `P2pPeerDiscovery` 隔离。在常规多节点部署中，`SchedulerPeerDiscovery` 定期调用 Scheduler 的 `ListP2pPeers`，按 backend 和 cluster 过滤，并排除本地节点。`StaticP2pPeerDiscovery` 与 `NoopP2pPeerDiscovery` 分别用于测试以及 disabled/local-only 场景。

Snapshot publish 也将 P2P 作为 best-effort 加速路径。Snapshot repository commit 成功后，`SnapshotManager` 发布固定的 Firecracker artifacts 和 OverlayBD layers。

对于固定 artifacts，OSS-backed resolution 先尝试 P2P，再访问 object storage。POSIX-backed resolution 不使用 P2P，因为 POSIX repository path 已经是 committed artifact source。

OverlayBD layer read 由 OverlayBD P2P HTTP facade 加速，而不是由 snapshot resolver 处理。

详细设计见 [P2P Artifact Transport](./p2p-design.md)。

**Node API endpoints**（兼容 E2B）：

- `POST /sandboxes`：创建沙箱。
- `GET /sandboxes`：列出沙箱。
- `GET /sandboxes/{id}`：获取 sandbox metadata。
- `DELETE /sandboxes/{id}`：删除沙箱。
- `POST /sandboxes/{id}/pause`：暂停沙箱并保存状态。
- `POST /sandboxes/{id}/resume`：从快照状态恢复沙箱。
- `GET /nodes`：返回 node-level observability snapshots。
- `GET /nodes/{id}`：返回节点详情和当前运行的沙箱。
- `ANY /proxy`、`ANY /proxy/{path}`、routing-header fallback 和已配置的 sandbox proxy hosts：将请求反向代理到 sandbox service。

## 分布式控制平面

`services/` 中的多节点控制平面负责在多个 AgentENV backend nodes 之间路由客户端流量。

```
    Client ──HTTP──> Gateway (:8080) ──gRPC──> Scheduler (:9090)
                        │                          │
                        │    ┌─────────────────────┘
                        │    │ node selection / lookup
                        ▼    ▼
                   Node A (:8000)    Node B (:8000)
```

**Gateway**（`services/gateway/`）是 HTTP reverse proxy。它从 header（`x-agentenv-sandbox-id` / `e2b-sandbox-id`）或已配置的 host-based proxy domain（`{port}-{sandboxID}.{domain}`）中提取 sandbox data-plane route。

Host-based route 只对显式配置的 `gateway.sandbox_proxy_domains` 生效。Sandbox ID 必须符合 RFC 952/1123 DNS label 规范，完整的 `{port}-{sandboxID}` label 也不能超过 63 个字符。

Runtime node 使用 `[sandbox_proxy].domains` 配置相同形式的 URL，并在 sandbox metadata 中返回第一个 domain。多节点部署可以用同一个 `SANDBOX_PROXY_DOMAINS` 值配置 Gateway 和 runtime node。

`/sandboxes/{id}/pause` 等 sandbox control-plane route 从 URL path 中读取 sandbox ID；data-plane traffic 不会只根据 URL path 推断。创建新沙箱时，Gateway 调用 `Schedule()` 选择节点；访问已有沙箱时调用 `LookupNode()`；创建成功后调用 `RecordAssignment()` 建立 sandbox-to-node binding。

没有显式 routing header 时，Gateway 还负责聚合 `GET /sandboxes`、`GET /v2/sandboxes` 和 `GET /nodes` 的 cluster 结果。对于 `GET /nodes/{id}`，Gateway 先通过 Scheduler 定位节点，再将请求转发到目标节点。

**Scheduler**（`services/scheduler/`）是 gRPC service，支持可插拔 node discovery、sandbox-to-node binding，以及 runtime node 上报的 observed-node snapshot。

它提供 `Schedule`、`LookupNode`、`RecordAssignment`、`Heartbeat`、`ListObservedNodes`、`ListP2pPeers`、`GetNode` 和 `UnregisterNode` 等 RPC。

Scheduler 支持默认的 round_robin 和 random 策略，proto contract 位于 `services/api/proto/scheduler.proto`。对于 P2P，Scheduler 只保存并返回 heartbeat 中的 opaque peer endpoint；artifact catalog lookup 和 byte transfer 始终在节点之间直接完成。

Binding 生命周期：

- Sandbox 创建成功后，`RecordAssignment` 立即写入初始 binding。
- Runtime heartbeat 包含该节点完整的 sandbox ID roster。Scheduler 将这个 roster 视为节点事实来源，并删除最新 heartbeat 中已不存在的 binding。
- `binding_ttl` 表示 routing information 的新鲜度，不等同于 sandbox timeout。若 Gateway 或 heartbeat 不再刷新某个 binding，Scheduler 会在下次 lookup 或 roster reconcile 时将其删除。
- `UnregisterNode` 删除 observed-node record，并主动清除该节点持有的所有 bindings。

Node discovery 模式：

- `static`：使用配置中的显式 `scheduler.nodes` 列表。
- `kubernetes`：监听 headless `agentenv-nodes` Service 的 EndpointSlice，把 ready DaemonSet Pod IP 作为 backend endpoint。

**持久化与 HA 边界**：Binding 默认保存在内存中。Scheduler 重启后，系统根据新创建的沙箱和 heartbeat roster 重新建立 binding。配置 `scheduler.redis_addr` 后，binding 转存到 Redis，query-only Scheduler replica 可以为已有沙箱的 data traffic 提供 `LookupNode`。

Scheduling、sandbox creation、assignment write、node API、P2P Scheduler API 和其他控制操作仍依赖 primary Scheduler。无论使用哪种模式，observed-node state 和 P2P artifact index 都只保存在内存中，属于临时状态。

**部署命令**：

```bash
# local dev (single node)
make start-server && make -C services run-scheduler && make -C services run-gateway

# docker compose (multi-node)
make deploy-up     # gateway + scheduler + 2 backend nodes
make deploy-down   # teardown

# kubernetes (gateway + scheduler + daemonset runtime nodes)
make k8s-render
make k8s-apply
```

在 Kubernetes 部署中，AgentENV runtime node 以 privileged DaemonSet 运行，使每个 host 恰好拥有一个 runtime Pod，并允许它访问 `/dev/kvm`、执行 iptables/network namespace 操作，以及使用 hostPath-backed workspace cache。

同一 host 上的 Runtime Pods 必须使用该 host 选定的 KVM/PVM mode。Deployment helpers 在 render/apply 时根据 `config/default.toml` 生成 DaemonSet ConfigMap，使 AgentENV runtime config 保持单一来源。

## 目录结构

```
storage/
├── overlaybd/src/              # layered image format (core)
│   ├── image/                  # high-level image abstraction
│   │   ├── image_file.rs       # ImageFile: reads/writes across the layer stack
│   │   ├── image_service.rs    # shared io_uring and image services
│   │   ├── helper.rs           # runtime upper preparation, path rewriting
│   │   └── snapshot.rs         # explicit upper export
│   ├── lsmt/                   # LSMT layer stacking
│   │   ├── file/               # LSMTReadOnlyFile, LSMTFile, stack helpers
│   │   ├── format.rs           # binary format (HeaderTrailer, DiskSegmentMapping)
│   │   └── index.rs            # segment mapping
│   ├── compression/zfile.rs    # zstd compression + jump tables
│   └── backend/                # pluggable VirtualFile backends
│       ├── local.rs            # LocalFile backend (io_uring)
│       ├── registryfs_v2.rs    # OCI registry backend
│       └── tar.rs              # tar archive backend
├── ublk/src/                   # userspace block device server
│   ├── lib.rs                  # public API
│   ├── ctrl.rs                 # /dev/ublk-control interface
│   ├── dev.rs                  # device + queue management
│   ├── queue.rs                # I/O descriptor handling
│   ├── io_buffer.rs            # zero-copy + traditional buffers
│   └── impls/                  # target implementations
│       ├── cow.rs              # BasicCowTarget
│       └── overlaybd_target.rs # OverlaybdTarget
├── ublk-daemon/src/            # ublk daemon (unix socket RPC)
│   ├── client.rs               # daemon client used by node runtime
│   ├── server.rs               # daemon server + request loop
│   └── protocol.rs             # RPC message types
├── util/src/                   # shared io_uring abstractions
│   ├── io_ring/                # AsyncIoRing, IoRingWorker
│   └── id_allocator.rs         # bitmap-based ID allocation
└── uffd-core/src/              # userfaultfd memory restore (excluded from workspace, retained for reference)
    ├── handler.rs              # UffdHandle, page fault event loop
    ├── backend.rs              # MemoryImageBackend trait
    ├── overlaybd.rs            # OverlaybdMemoryImage backend
    ├── process_vm_reader.rs    # ProcessVmReader (process_vm_readv)
    └── scm.rs                  # SCM_RIGHTS fd passing

src/
├── bin/server.rs               # node binary entrypoint
├── api/                        # HTTP API layer
├── orchestrator/               # sandbox lifecycle
├── observability/              # node identity + host/runtime metrics projection
├── sandbox/                    # Firecracker VM management
│   ├── extra_drive.rs          # extra drive preparation
│   └── ublk/                   # storage integration
│       ├── device.rs           # daemon-backed ublk device lifecycle
│       └── overlaybd.rs        # runtime config materialization
├── snapshot/                   # committed snapshot model, repository backends, runtime resolution
├── template/                   # user-facing template builder over snapshots
└── cfg.rs                      # TOML config

services/                       # distributed control plane (Go)
├── gateway/                    # HTTP reverse proxy
├── scheduler/                  # gRPC node selection + binding
├── api/proto/                  # protobuf contracts
└── shared/                     # config, logging
```
