# AgentENV 架构总览与核心流程

本文从组件协作和数据流的角度解释 AgentENV。重点不是逐项列出模块，
而是说明一个请求如何进入系统、沙箱如何运行，以及运行中的状态如何变成
可以再次启动的快照。

更深入的存储格式、ublk 实现和目录结构见 [AgentENV 架构](./architecture.md)。

## 系统定位

AgentENV 是面向 AI Agent 的微虚拟机沙箱平台。它对外提供与 E2B 兼容的
HTTP API，对内使用 Firecracker 运行隔离的 Linux microVM。用户可以创建、
访问、暂停、恢复、复制和删除沙箱，也可以把运行中的沙箱保存为快照，或通过
模板构建出可重复使用的运行环境。

系统围绕一个双向过程组织：

1. 将 OCI image 或 committed snapshot 解析为 Firecracker 可以挂载的块设备
   和内存镜像，然后启动 microVM。
2. 将 microVM 运行期间产生的文件系统、附加盘和内存变化重新捕获为 snapshot
   artifacts，供以后恢复或构建模板。

`Orchestrator` 连接这两个方向。它决定生命周期状态如何变化，
`SandboxBackend` 管理实际运行的 Firecracker 进程，存储系统则负责 VM 看到的块数据。

## 整体协作关系

```text
Client
  |
  v
Gateway ---- Schedule / LookupNode ----> Scheduler
  |
  v
Node API -> Orchestrator -> SandboxBackend -> Firecracker VM -> envd
                 |                |
                 |                +-> network namespace / proxy route
                 |
                 +-> ublk daemon -> OverlayBD -> local cache / OCI registry
                 |
                 +-> SnapshotManager -> snapshot repository
                                      -> optional P2P advertisement
```

图中包含两类不同的流：

- 控制流经过 Gateway、Scheduler、Node API 和 `Orchestrator`。它决定请求应该
  到达哪个节点，以及当前状态是否允许执行创建、暂停或恢复等操作。
- 数据流发生在 Firecracker、ublk 和 OverlayBD 之间。root filesystem、
  attached drives 和 memory snapshot 的数据不会经过 Gateway 或 Scheduler。

这种分离让控制平面只维护路由和状态信息，而高频块 I/O 始终留在运行沙箱的
节点上。

## 组件职责与边界

### Gateway 与 Scheduler

Gateway 是面向客户端的 HTTP 入口。在创建沙箱时，它通过 `Schedule` 请求选择节点；访问已有沙箱时，它通过 `LookupNode` 找到持有该沙箱的节点，再转发 HTTP
或 WebSocket 请求。

Scheduler 只负责节点选择、sandbox-to-node binding、节点心跳和 P2P artifact位置提示。它不启动 Firecracker，也不保存 VM 内存、文件系统或快照文件。

### Node API 与 Orchestrator

每个运行节点都有独立的 Rust API server。API 完成协议转换和参数校验后，将生命周期操作交给 `Orchestrator`。

`Orchestrator` 是节点内沙箱状态的协调者。它管理 `Creating`、`Running`、
`Pausing`、`Paused`、`Resuming`、`Snapshotting`、`Forking` 和 `Killing`等状态，并确保同一个沙箱不会同时执行互相冲突的操作。它还维护 proxy route、超时回收、生命周期事件和暂停状态的持久化。

### SandboxBackend 与 Firecracker

`SandboxBackend` 把生命周期编排与具体虚拟化实现隔开。
`FirecrackerSandbox` 负责 Firecracker 进程、network namespace、MMDS、块设备、`envd` 连接以及 custom extension hooks。

VM 内的 `envd` 提供进程执行、文件操作和 readiness 检查。客户端调用进程或文件 API 时，请求最终到达 `envd`；客户端访问 VM 内的 HTTP 服务时，请求通过proxy route 进入对应 network namespace。

### ublk 与 OverlayBD

OverlayBD 将多个只读层和一个沙箱专属的可写 upper layer 组合成完整磁盘视图。
基础层可以由多个沙箱共享，运行期间的写入只进入当前沙箱的 upper layer。

`uvm-ublk-daemon` 把 OverlayBD image 暴露为 `/dev/ublkbN`。Firecracker 只需要
挂载普通块设备，不需要知道数据来自本地文件、OCI Registry 还是缓存。
daemon 集中管理设备生命周期和 io_uring worker，也能通过 warm pool 复用设备。

### SnapshotManager 与 Template Builder

`SnapshotManager` 将捕获结果提交到 POSIX 或 OSS repository，并在配置 P2P 时
进行 best-effort 发布。repository 中的 commit 是快照的权威结果；P2P 发布失败
不会回滚已经完成的 repository commit。

Template 不是另一种存储格式。Template Builder 从 OCI image 或已有 snapshot
启动临时沙箱，执行 `RUN`、`ENV`、`WORKDIR` 等声明式步骤，再把结果发布为新的
committed snapshot。因此，从 template 创建沙箱最终仍然进入 snapshot resolve
和 resume 流程。

## 创建与访问流程

1. Client 通过 Node API 或 Gateway 发起创建请求。多节点部署中，Gateway 先让
   Scheduler 选择目标节点。
2. Node API 校验请求并调用 `Orchestrator`。后者分配 `SandboxId`，写入
   `Creating` 状态，并解析 `userImage` 或 template snapshot。
3. `FirecrackerSandbox` 准备 network namespace，并通过 ublk daemon 创建 rootfs、
   attached drives 以及恢复时需要的 memory device。
4. OverlayBD 把共享只读层与当前沙箱的 writable upper layer 组合起来，ublk
   将这个磁盘视图交给 Firecracker。
5. Firecracker 启动后，节点等待 `envd` ready。成功后 `Orchestrator` 将状态改为
   `Running`，并发布 proxy route。
6. Gateway 在远程创建成功后记录 sandbox-to-node binding，后续请求因此能够回到
   同一个节点。

这里的所有权边界是：Scheduler 选择节点，`Orchestrator` 管理节点内生命周期，
Firecracker 和存储系统持有实时执行数据。

## 暂停、快照与恢复流程

### Pause

Pause 同时包含状态转换和数据转换。`Orchestrator` 先让沙箱离开 `Running`，
Firecracker 再写出 VM state 和 sparse diff memory。存储层封存当前文件系统的
writable layer，并把 sparse memory 转换成 OverlayBD layer。暂停配置和 artifacts
持久化完成后，VM 才停止并释放本次运行使用的网络资源。

Pause 成功后，沙箱停留在 `Paused`。节点正常关闭时也会优先暂停仍在运行的沙箱，
使其可以在节点重启后恢复，而不是直接删除运行状态。

### Snapshot capture

用户主动创建 snapshot 时会复用同一套捕获机制，但最终状态不同：

```text
Running -> Snapshotting -> capture artifacts
        -> repository commit -> resume original VM -> Running
```

`SnapshotManager` 提交捕获结果后，原沙箱恢复运行。若后续 P2P advertisement
失败，只影响加速能力，不影响已经提交的 snapshot。

### Resume

恢复过程沿相反方向解析数据。Snapshot resolver 找到 filesystem、attached-drive、
memory 和 VM-state artifacts。ublk daemon 将多层 memory image 暴露为只读块设备，
Firecracker 将其映射为 memory backend。

从同一 snapshot 创建的多个沙箱可以共享这个只读设备和 host page cache。某个
沙箱修改内存页时，Firecracker 通过 copy-on-write 得到私有页面，不会修改共享的
底层 memory image。

### Capture 失败边界

捕获错误按“原运行时是否还能安全继续”分类。Recoverable error 会尝试把沙箱恢复
到 `Running`。Terminal error 表示运行时已经越过可安全回滚的位置，
`Orchestrator` 会清理沙箱，避免继续暴露状态不确定的 VM。

## 状态与持久化边界

- `Orchestrator` 是节点内 lifecycle state 的事实来源。Paused state 会持久化，
  live Firecracker process 本身不被视为可持久化状态。
- Scheduler binding 默认保存在内存中。配置 `scheduler.redis_addr` 后，binding
  可以由 query-only Scheduler replicas 共享；调度、创建、assignment write、
  node API 和 P2P scheduler API 仍依赖 primary Scheduler。
- Snapshot repository 是 committed snapshot content 的持久化来源。node-local
  image cache 和 P2P transport 只是加速层，可以被重建或绕过。
- Scheduler 中的 observed-node state 和 P2P artifact hints 是临时信息，只用于
  路由和缩小查找范围，不保存 artifact locator、snapshot metadata 或文件内容。

## 主要功能

- 提供与 E2B SDK 兼容的 sandbox、template、process 和 filesystem API。
- 使用 Firecracker microVM、network namespace 和独立块设备隔离沙箱。
- 从 OCI Registry 解析镜像，并通过 OverlayBD 和 ublk 提供共享基础层与私有写层。
- 支持 create、pause、resume、snapshot、fork 和 delete 生命周期操作。
- 将 rootfs、attached drives、memory 和 VM state 组织为可恢复的 committed snapshot。
- 通过 Template Builder 构建可重复使用的 Agent 运行环境。
- 通过 Gateway 和 Scheduler 在多节点间调度并透明转发请求。
- 使用可选 P2P transport 加速 snapshot artifacts 和 OverlayBD layers 的获取。
- 通过 heartbeat 汇报节点、机器、沙箱资源和 P2P endpoint。
- 通过 custom extension hooks 和 network policy 扩展外部集成与网络控制。

## 设计取舍与运行约束

AgentENV 的核心收益来自 snapshot-native 的运行方式。共享只读磁盘层、共享内存
设备和 host page cache 可以降低从同一 template 批量启动沙箱时的 I/O 和内存
成本。按 trait 划分 `SandboxBackend`、snapshot repository 和 `P2pTransport`，
也让生命周期逻辑不必绑定到单一后端。

相应的代价是部署依赖较重。每个 runtime node 都需要 Linux，以及所配置的 KVM
或 PVM 模式、ublk、network namespace、iptables 和相关 host permissions。
此外，运行中的沙箱具有明确的 node affinity：Scheduler binding 负责把请求送回
原节点，当前 fork 也在 source sandbox 所在节点完成，而不是跨节点迁移。

## 主要源码入口

- `src/bin/server.rs`：节点进程入口与组件装配。
- `src/api/`：Axum API、生成的 OpenAPI 接口和 reverse proxy。
- `src/orchestrator/service.rs`：沙箱生命周期与状态转换。
- `src/sandbox/firecracker/sandbox.rs`：`SandboxBackend` 的 Firecracker 实现。
- `src/snapshot/manager.rs`：snapshot publish、resolve 和 P2P publish 入口。
- `src/template/builder.rs`：template build 和 rebuild 流程。
- `src/sandbox/ublk/`：节点与 ublk daemon 的集成。
- `storage/ublk-daemon/`：ublk 设备的集中管理进程。
- `storage/overlaybd/src/image/image_file.rs`：分层磁盘的高层读写入口。
- `src/observability/reporter.rs`：heartbeat 和 lifecycle event 上报。
- `services/gateway/`：多节点 HTTP 入口与请求转发。
- `services/scheduler/`：节点选择、binding、heartbeat 和 P2P hint index。
