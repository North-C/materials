# CubeSandbox `runContainer` 与 `sandbox-probe` 调用链分析

本文说明 Cubelet 创建 Sandbox 时，`runContainer` 与 `sandbox-probe` 的执行顺序，以及请求从 Cubelet 经 containerd、CubeShim、VMM 到 guest-agent 的完整链路。

分析基于 `source_code/CubeSandbox` 当前 profiling 分支。Early Probe 是该分支新增的可选优化，不属于社区版本的默认执行路径。

## 1. 核心结论

社区默认路径在 Cubelet 编排层面是串行的：`runContainer` 成功返回后才启动 Probe，Probe 成功后才执行 `PostCreateContainer`。

Probe 的网络操作由 goroutine 执行，但 Cubelet 会立即等待结果。因此，这种内部异步实现不会使 Sandbox 创建请求提前返回，也不会与前面的 `runContainer` 重叠。

当前 profiling 分支提供可选的 Early Probe。启用后，Probe goroutine 会在 `runContainer` 之前启动，两者可以重叠，但创建请求最终仍会等待二者都成功。

## 2. 默认 Probe 时序

默认执行流程如下：

```text
createContainers
  -> runContainer
     -> NewContainer
     -> NewTask
     -> Wait（注册退出通知）
     -> Start
  -> doProbe
     -> startProbe
        -> Telnet
           -> go probe(...)
     -> waitProbe
  -> PostCreateContainer
```

调用入口位于：

```text
Cubelet/services/cubebox/cube_container_create.go:321-366
```

其中，`runContainer()` 在第 323 行被同步调用。如果它返回错误，函数会直接退出，不会进入 Probe。

默认分支在第 361-365 行调用 `doProbe()`。只有 Probe 成功返回后，第 366 行的 `PostCreateContainer()` 才会执行。

### 2.1 Probe 内部为何看起来是异步的

`doProbe()` 位于：

```text
Cubelet/services/cubebox/probe.go:82-90
```

它先调用 `startProbe()` 获得结果 channel，然后立即调用 `waitProbe()` 等待结果。

实际探测由以下代码启动：

```text
Cubelet/pkg/telnet/telnet.go:157-163
```

```go
go probe(ctx, p, retCh)
```

goroutine 只负责异步执行 TCP、Ping 或 HTTP 探测。`waitProbe()` 仍会阻塞当前创建流程，等待以下任一事件：

- Probe 成功或失败；
- 容器通过 `ci.ExitCh` 退出；
- 创建上下文超时或取消。

`waitProbe()` 位于：

```text
Cubelet/services/cubebox/probe.go:165-197
```

因此，默认路径应理解为“Probe 的 I/O 在 goroutine 中运行，但创建工作流同步等待 Probe 结果”。

## 3. Early Probe 优化路径

当前 profiling 分支新增以下开关：

```bash
export CUBESANDBOX_EARLY_PROBE=1
export CUBESANDBOX_EARLY_PROBE_DELAY_MS=0
```

开关定义位于：

```text
Cubelet/services/cubebox/early_probe.go:12-26
```

未设置 `CUBESANDBOX_EARLY_PROBE=1` 时，Early Probe 默认关闭。

启用后的时序为：

```text
startProbeWithDelay -> Probe goroutine -------------------+
       |                                                  |
       +-> runContainer -> NewTask -> Wait -> Start ------+
                                                          |
                                                     waitProbe
                                                          |
                                               PostCreateContainer
```

相关编排代码位于：

```text
Cubelet/services/cubebox/cube_container_create.go:302-365
```

第 308-320 行先启动 Probe，第 321-348 行再同步执行 `runContainer()`。`runContainer` 成功后，第 355-360 行通过 `waitProbe()` 汇合两个分支。

即使 Probe 提前成功，结果也只会写入带缓冲的 channel。创建流程仍需等待 `runContainer` 返回，随后才能读取 Probe 结果并继续。

如果 `runContainer` 失败，Cubelet 会取消 Early Probe，并返回容器启动错误。

## 4. `runContainer` 如何发送请求

`runContainer()` 位于：

```text
Cubelet/services/cubebox/cube_container_create.go:1238-1315
```

它不直接发送 HTTP 请求。Cubelet 使用 containerd Go Client，通过 containerd 的 Containers 和 Tasks 服务完成容器创建。

containerd 再通过 runtime-v2 shim 接口和 Unix Socket，将 Task 请求转发给 `containerd-shim-cube-rs`。CubeShim 与 guest-agent 之间主要通过基于 vsock 的 ttrpc 通信。

整体链路如下：

```text
Cubelet
  -> containerd Go Client
     -> containerd Containers / Tasks 服务
        -> runtime-v2 CubeShim（ttrpc）
           -> VMM API
           -> guest-agent（ttrpc over vsock）
```

## 5. `runContainer` 分步调用链

### 5.1 `NewContainer`：创建 containerd 元数据

代码位置：

```text
Cubelet/services/cubebox/cube_container_create.go:1245-1254
```

核心调用为：

```go
c, err := l.client.NewContainer(ctx, ci.ID, cOpts...)
```

该调用向 containerd Containers 服务创建容器元数据，并应用 OCI Spec、Snapshotter 等 `NewContainerOpts`。

这一步还没有完成 VM 和容器进程启动。对应 profiling 指标为 `new-container`。

### 5.2 `NewTask`：进入 CubeShim 的 `Task.Create`

代码位置：

```text
Cubelet/services/cubebox/cube_container_create.go:1264-1281
```

核心调用为：

```go
task, err := c.NewTask(ctx, ioCreater, taskOpts...)
```

containerd 会启动或连接 CubeShim，然后向它发送 runtime-v2 `Task.Create` ttrpc 请求。

CubeShim 的处理入口为：

```text
CubeShim/shim/src/service/task_srv.rs:86-186
```

`TaskService::create()` 按以下顺序执行：

```text
加载 OCI Spec
  -> 获取 Sandbox 锁
  -> 如果 Sandbox 尚未初始化：
       sb.init()
       sb.create_sandbox().await
  -> sb.create_container().await
  -> 发布 TaskCreate 事件
  -> 返回 CreateTaskResponse
```

`.await` 表示 Rust 运行时可以调度其他任务，但当前 RPC 不会提前返回。containerd 和 Cubelet 必须等待 `CreateTaskResponse`。

### 5.3 `create_sandbox`：启动或恢复 VM

`create_sandbox()` 位于：

```text
CubeShim/shim/src/sandbox/sb.rs:436-510
```

主要调用顺序如下：

```text
start_vm
  -> launch_vmm
  -> restore_vm，或 create_vm + boot_vm
  -> 等待 VsockServerReady
connect_agent
  -> reset_guest（快照恢复路径）
  -> add_device（适用时）
  -> guest-agent CreateSandbox
```

`start_vm()` 位于 `CubeShim/shim/src/sandbox/sb.rs:781-827`。如果快照可用，它先尝试 `restore_vm()`；否则执行 `boot_vm()`。

快照恢复配置在 `CubeShim/shim/src/sandbox/sb.rs:838-908` 构造。最终由以下代码向 VMM 发送恢复请求：

```text
CubeShim/shim/src/hypervisor/cube_hypervisor.rs:173-183
```

发送的请求类型为：

```rust
ApiRequest::VmRestore(restore_config)
```

恢复 VM 后，CubeShim 等待 vsock 服务就绪并连接 guest-agent。快照路径还会调用 `reset_guest()` 校准 Guest 时间并重新播种随机设备。

`reset_guest()` 位于：

```text
CubeShim/shim/src/sandbox/sb.rs:402-434
```

之后，CubeShim 发送 guest-agent `CreateSandbox` RPC，等待 Guest 完成网络、存储和 Sandbox 环境初始化。

### 5.4 `create_container`：在 Guest 中创建容器

Sandbox 初始化后，`TaskService::create()` 调用：

```text
Sandbox::create_container
  -> Container::create_container
  -> guest-agent CreateContainer
```

源码位置：

```text
CubeShim/shim/src/sandbox/sb.rs:911-937
CubeShim/shim/src/container/mod.rs:432-466
```

社区默认路径会向 guest-agent 发送 `CreateContainer` RPC，并等待响应。

当前优化分支有一个例外：使用应用快照恢复，且 OCI Spec 不要求刷新传播挂载时，会跳过重复的 Guest `CreateContainer` 操作。

只有 `create_sandbox` 和 `create_container` 全部成功后，CubeShim 才会返回 `CreateTaskResponse`，Cubelet 中的 `c.NewTask()` 才会结束。

### 5.5 `task.Wait`：注册退出通知

代码位置：

```text
Cubelet/services/cubebox/cube_container_create.go:1296-1300
```

```go
exitCh, err := task.Wait(ctx)
```

此处的 `Wait()` 并不是同步等待容器退出。它注册退出状态通知并返回一个 channel，后续 Probe 可通过 `ci.ExitCh` 感知容器是否提前退出。

### 5.6 `task.Start`：进入 CubeShim 的 `Task.Start`

代码位置：

```text
Cubelet/services/cubebox/cube_container_create.go:1302-1313
```

`task.Start(ctx)` 通过 containerd Tasks 服务向 CubeShim 发送 `Task.Start` 请求。

CubeShim 入口位于：

```text
CubeShim/shim/src/service/task_srv.rs:187-225
```

调用顺序如下：

```text
TaskService::start
  -> Sandbox::start_container
     -> Container::start_container
        -> start_log_forward
        -> guest-agent StartContainer（冷启动路径）
        -> 注册进程退出等待
  -> 发布 TaskStart 事件
  -> 返回 StartResponse
```

具体容器启动实现位于：

```text
CubeShim/shim/src/container/mod.rs:468-504
```

冷启动时，CubeShim 会发送 guest-agent `StartContainer` RPC。对于应用快照恢复，容器进程通常已经包含在快照中，因此可能跳过该 RPC，但仍会建立日志转发和退出监控。

`task.Start()` 收到成功响应后，Cubelet 更新 PID 和 `StartedAt`。随后 `runContainer()` 才返回。

## 6. 同步与异步边界

下表总结各阶段的行为：

| 操作 | 内部实现 | Cubelet 是否等待 | 是否可与默认 Probe 重叠 |
| --- | --- | --- | --- |
| `NewContainer` | containerd RPC | 是 | 否 |
| `NewTask` | containerd RPC + CubeShim async handler | 是 | 否 |
| VM restore/boot | CubeShim async + VMM request | 是 | 否 |
| Guest `CreateSandbox` | ttrpc/vsock | 是 | 否 |
| Guest `CreateContainer` | ttrpc/vsock | 是 | 否 |
| `task.Wait` | 注册退出 channel | 仅等待注册完成 | 否 |
| `task.Start` | containerd/CubeShim RPC | 是 | 否 |
| Probe 网络尝试 | Go goroutine | `waitProbe` 会等待 | 仅 Early Probe 可重叠 |

Rust 的 `async fn` 和 `.await` 表示线程可以在等待 I/O 时执行其他任务，不表示请求调用方不等待结果。

同理，Probe 使用 goroutine 只表示网络尝试在独立 goroutine 中运行。由于创建流程紧接着调用 `waitProbe()`，默认工作流仍是同步的。

## 7. Profiling 指标口径

### 7.1 `new-container`

记录 `l.client.NewContainer()` 的耗时，主要覆盖 containerd 容器元数据创建。

### 7.2 `sandbox-create`

记录 `c.NewTask()` 的耗时。对于 Pod 的第一个容器，它通常覆盖 CubeShim `Task.Create`、VM 恢复或启动、Guest Sandbox 初始化以及容器创建。

因此，`sandbox-create` 不是一个单一底层操作，而是多个同步子阶段的总耗时。

### 7.3 `sandbox-start`

当前代码从调用 `c.NewTask()` 前记录的 `taskStart` 开始计时，到 `task.Start()` 成功后结束：

```text
Cubelet/services/cubebox/cube_container_create.go:1274-1313
```

因此，`sandbox-start` 是累计指标，包含：

```text
NewTask/Create + Wait 注册 + Start
```

它不能直接理解为纯 `Task.Start` RPC 耗时。

如果需要计算近似的独立 Start 阶段，可以在同一请求、同一容器且采样完整的前提下使用：

```text
近似 Start 耗时 = sandbox-start - sandbox-create
```

该差值还包含 `task.Wait()` 注册、shim endpoint 保存以及两次指标记录之间的少量 Cubelet 本地逻辑，因此只能作为近似值。

### 7.4 `sandbox-probe`

默认路径下，`sandbox-probe` 从 `runContainer` 完成后开始，记录实际等待应用可探测的时间。

Early Probe 路径下，计时从 Probe goroutine 启动时开始，并可与 `runContainer` 重叠。因此该指标不能与默认路径直接按串行阶段相加。

默认路径近似为：

```text
创建总耗时 ~= 前置阶段 + runContainer + sandbox-probe + 后置阶段
```

Early Probe 路径更接近：

```text
重叠区间耗时 ~= max(runContainer, sandbox-probe)
```

具体端到端耗时仍应以 `cube-e2e` 或请求总耗时指标为准。

## 8. 源码索引

| 关注点 | 源码位置 |
| --- | --- |
| Probe 与 `runContainer` 编排 | `Cubelet/services/cubebox/cube_container_create.go:302-366` |
| `runContainer` | `Cubelet/services/cubebox/cube_container_create.go:1238-1315` |
| Probe 创建与等待 | `Cubelet/services/cubebox/probe.go:82-197` |
| Probe goroutine | `Cubelet/pkg/telnet/telnet.go:157-163` |
| Early Probe 开关 | `Cubelet/services/cubebox/early_probe.go:12-26` |
| CubeShim `Task.Create` | `CubeShim/shim/src/service/task_srv.rs:86-186` |
| CubeShim `Task.Start` | `CubeShim/shim/src/service/task_srv.rs:187-225` |
| Sandbox 创建 | `CubeShim/shim/src/sandbox/sb.rs:436-510` |
| VM 启动与恢复选择 | `CubeShim/shim/src/sandbox/sb.rs:781-827` |
| VM 恢复配置 | `CubeShim/shim/src/sandbox/sb.rs:838-908` |
| VMM Restore 请求 | `CubeShim/shim/src/hypervisor/cube_hypervisor.rs:173-183` |
| Guest reset | `CubeShim/shim/src/sandbox/sb.rs:402-434` |
| Sandbox 容器创建 | `CubeShim/shim/src/sandbox/sb.rs:911-937` |
| Guest 容器创建与启动 | `CubeShim/shim/src/container/mod.rs:432-504` |
