# CubeSandbox Template 并发创建优化说明

更新时间：2026-08-07

## 1. 文档范围

本文说明 CubeSandbox 基于 Template 并发创建沙箱时保留在
`perf/v0.5.1-validated-optimal-20260729` 分支中的优化。内容覆盖每项优化的
上下文场景、瓶颈、实现方法、适用边界和已有验证数据。

仓库口径：

- 上游基线：CubeSandbox `v0.5.1`，提交 `a164417f497234a0d787cb328b0ae96480b1569b`。
- 目标架构：ARM64 宿主机、openEuler guest。
- Template 规格：2 vCPU、2 GiB 内存、1 GiB writable layer。
- OCI 基线：`cubesandbox-bench/sandbox-code-envd-ci:arm64-slim`。
- 压测重点：Template create-only，典型压力为 `c50/n500`。
- Readiness：端口 49999 的 HTTP Probe；cross-stage early probe 关闭，保留标准 Probe。

这里的 Template restore 不是重新执行完整 OCI 冷启动。MicroVM、guest 内核、
cube-agent、容器进程和应用服务从保存状态恢复，宿主侧随后完成设备恢复、guest
校时、必要的 mount 修复、日志转发和 readiness 确认。

## 2. 创建链路与并发放大点

一次 Template 创建请求的主要路径如下：

```text
SDK / CubeAPI
  -> CubeMaster
  -> Cubelet
     -> containerd task
        -> CubeShim
           -> Hypervisor restore
              -> GIC / MSI-X route restore
           -> connect guest-agent
           -> reset guest time / reseed RNG
           -> CreateSandbox（按需）
           -> CreateContainer（按需）
           -> init log forwarding
     -> HTTP readiness Probe :49999
        -> native code server
           -> envd :49983
```

在 `c50/n500` 下，以下小开销会被同时放大：

- 每个 restored VM 的无效 MMDS 定时轮询和 virtio-net 中断。
- 每个 shim 的线程、日志 syscall 和逐消息 flush。
- 每条中断 route 单独触发的 KVM routing table 刷新。
- 已保存对象仍重复执行的 guest-agent RPC。
- 每个 sandbox 为 init 日志转发再建立一条 vsock 连接。
- Probe 首次略早时产生的完整 500 ms 等待。
- 每次 `/health` 再查询 envd 所产生的跨 TAP 请求放大。

## 3. 优化总览

| 提交 | 层次 | 优化目标 |
|---|---|---|
| `768a14f` | cubelog | 避免小写 `info` 回退为 DEBUG |
| `509cda2` | Cubelet | 对启动 Probe 增加有界 25 ms quick retry |
| `c87cbff` | CubeShim | 跳过没有 virtio-fs/传播挂载工作的 restore RPC |
| `4e568d5` | CubeShim | 并行 guest 校时、RNG 重播种及可重叠 setup |
| `62836e7` | CubeShim | `check_agent=false` 时不建立 health 连接 |
| `4ce3bbb` | CubeShim | 日志批量写并减少 Tokio worker |
| `b3301f8` | Hypervisor | 批量恢复 ARM64 GIC/MSI-X route |
| `a8ee9c7` | guest envd | Template 捕获期 MMDS prime，restore 后停止轮询 |
| `51d36b0` | guest code server | 监听前等待 envd，并把 ready cache 保存进 Template |
| `b7d9402` | OCI 构建 | 固定输入并从源码构建 ARM64 优化镜像 |
| `2aca144` | CubeShim | restore 时复用 guest-agent 连接转发 init 日志 |

## 4. 日志级别规范化

提交：`768a14f perf(cubelog): honor configured log level casing`

### 上下文

CubeSandbox 服务配置通常使用小写 `info`。原 `StringToLevel` 只识别全大写值，
无法识别时回退到 DEBUG。高并发创建会把不必要的 DEBUG 序列化、channel 发送和
磁盘写放大。

### 实现

`cubelog/logger.go` 在匹配前执行：

```go
strings.ToUpper(strings.TrimSpace(level))
```

同时增加大小写、首尾空白和未知级别回退测试。c50 实验中日志增量由约 31 MiB
降至 4.24 MiB。该改动不改变合法大写配置和未知配置仍回退 DEBUG 的兼容行为。

## 5. 标准 Probe 有界快速重试

提交：`509cda2 perf(cubelet): retry startup probes promptly`

### 上下文

Template restore 后，端口可能在第一次 Probe 后数十毫秒内就 ready。标准 Probe
周期为 500 ms 时，第一次略早会直接增加一个完整周期的创建延迟。

### 实现

`Cubelet/pkg/telnet/telnet.go` 为 HTTP/TCP 启动检查增加：

- quick retry 周期 25 ms。
- 最多两次 quick retry。
- 只在 `SuccessThreshold == 1`、`FailureThreshold > 1` 且标准周期大于 25 ms 时启用。
- quick retry 失败不消耗 `FailureThreshold`，下一次标准周期检查仍是下一个逻辑失败。
- Ping 和不满足启动语义的 Probe 保持原逻辑。

这是标准 Probe 内部的小窗口优化，不是已经回退的 cross-stage early probe。

## 6. 跳过无实际工作的 restore RPC

提交：`c87cbff perf(cubeshim): skip no-op snapshot restore RPCs`

### 上下文

Application Snapshot restore 后，sandbox 和 container 已经存在于 guest 保存状态中。
restore 阶段再次调用 `CreateSandbox`、`CreateContainer` 的实际作用只剩特定修复：

- `CreateSandbox` 负责恢复时的 virtio-fs setup。
- `CreateContainer` 启动 guest helper，进入 container mount namespace 修复传播挂载。

没有上述工作时，RPC、guest fork/exec 和 setns 都是空开销。

### 实现

- storage 中不存在 `driver == "virtio-fs"` 时跳过 restore `CreateSandbox`。
- OCI spec 同时不存在 `cube.propagation.exec.mounts` 和
  `cube.propagation.container.umounts` 时跳过 restore `CreateContainer`。
- 跳过 `CreateContainer` 时仍创建 `ContainerState` 并结束统计，保证宿主状态机完整。
- 冷启动、Template 创建以及存在任一传播 annotation 的 restore 保持原 RPC。

在后续 400 QPS 阶段观测中，`CreateContainer` avg 从 19.09 ms 降至 0.08 ms，
p95 从 152 ms 降至 1 ms。该数据同时包含当时环境中的其他优化，不能解释为该
提交在任意环境下的独立收益。

## 7. 并行 guest restore setup

提交：`4e568d5 perf(cubeshim): parallelize guest restore setup`

### 上下文

恢复后的 guest 需要校准 wall clock，并向随机设备重新注入宿主随机数。两项 RPC
互不依赖；需要 virtio-fs setup 时，`CreateSandbox` 与 guest reset 也没有数据依赖。
原实现串行等待这些步骤。

### 实现

- clone 已建立的 `AgentServiceClient`。
- 使用 `tokio::try_join!` 并行执行 `set_guest_date_time` 和
  `reseed_random_dev`。
- Application Snapshot restore 且仍需 `CreateSandbox` 时，再将整个
  `reset_guest` 与 `create_sandbox` 重叠。
- 任一分支失败仍通过 `try_join!` 返回原错误；非 Application Snapshot 路径保持
  原先的先 reset、后 create 顺序。

## 8. 按需建立 health client

提交：`62836e7 perf(cubeshim): avoid unused agent health connection`

### 上下文

restore 完成后当前调用是 `monitor_vm(false)`，只检查 Hypervisor 退出事件。
旧实现无论 `check_agent` 是否为 true，都会为每个 sandbox 额外建立 guest-agent
health 连接。

### 实现

health client 改为 `Option<HealthClient>`。只有 `check_agent=true` 时才调用
`connect_agent`；纯 Hypervisor monitor 不创建连接。定时 health check 分支受同一
布尔条件保护，因此 `unwrap` 只会发生在 client 已创建的路径。

## 9. CubeShim 日志批量写和单 worker

提交：`4ce3bbb perf(cubeshim): batch log writes on one worker`

### 上下文

原日志线程对每条 log/stat 消息分别 `write_all + flush`。正常 shim 还创建两个
Tokio worker。并发创建 50 个 shim 时会增加线程、上下文切换、文件 syscall 和
页缓存同步压力。

### 实现

- 收到第一条消息后用 `try_recv` 排空当前队列。
- log 和 stat 分别拼成字符串 batch，每种类型每批只调用一次 `write_all`。
- 不再逐消息 flush，只在 rotate 时 flush 后退出当前 writer。
- 正常 shim runtime 也固定为一个 Tokio worker，线程 keep-alive 为 100 ms。

该策略优化的是创建风暴下的吞吐，不保证每条日志写入后立即执行 flush；异常掉电时
的最后少量日志持久性与原逐条 flush 行为不同。

## 10. ARM64 中断路由批量恢复

提交：`b3301f8 perf(hypervisor): batch interrupt route restore`

### 上下文

ARM64 VM restore 需要恢复 legacy GIC route 和 PCI MSI-X table。原实现逐项调用
`InterruptSourceGroup::update`，后端每次都可能锁定并刷新完整 KVM GSI routing
table。大量设备和并发 VM 会放大 ioctl 与锁竞争。

### 实现

- `InterruptSourceGroup` 增加兼容默认实现 `enable_selected` 和 `update_many`。
- GIC 在创建 legacy interrupt group 时登记真实使用的 IRQ，只 enable 和恢复这些
  route，不再固定处理全部 32 个 legacy IRQ。
- MSI-X restore 先收集所有未 mask entry，再一次调用 `update_many`。
- KVM 后端先生成全部 `RoutingEntry`，批量更新内存 map，最后调用一次
  `set_gsi_routes`。批处理以一次 GIC batch 或一个 MSI-X table batch 为边界。

该提交只优化 VMM 内部 routing restore，不开启宿主机 GICv4、vtimer IRQ bypass
或其他实验内核参数。

## 11. envd Snapshot-only MMDS prime

提交：`a8ee9c7 perf(envd): bound MMDS polling after restore`

### 根因场景

基线 envd 0.5.13 每 50 ms 请求 Firecracker link-local MMDS 地址
`169.254.169.254`。CubeSandbox 使用 Cloud Hypervisor，guest 中没有对应 MMDS
服务，因此轮询不会成功退出。`PostInit` 还可能再启动最长 60 秒的轮询。

单 VM 中这只是低频后台工作；当 `c50/n500` 逐步保留数百个 ready guest 时，
会持续产生 guest timer、WFI exit、virtio-net IRQ 和宿主调度压力。对照实验中，
停止 envd 或使用 `-isnotfc` 能明显减少这些事件。

但直接禁用 MMDS 不能采纳：在测试的 openEuler guest、Cloud Hypervisor 和
`ResetVm` 组合中，多轮出现 `reset guest time failed`。现有证据支持“Template
捕获和 reset 窗口需要保留原 MMDS 活动”这一经验约束，但尚未证明它是通用协议。

### 实现

envd 基于固定 upstream commit `b8ca332f435370397bf42be614b2a5b620d65d39`
增加参数：

```text
-prime-mmds-until-unix <absolute-unix-seconds>
```

运行阶段如下：

| 阶段 | 时间状态 | 行为 |
|---|---|---|
| OCI 启动 | `deadline = guest realtime + 10s` | 启动原始 MMDS poller |
| Template 捕获 | guest 时间尚未越过 deadline | 保留经验证的 MMDS 活动 |
| clone restore | 从快照恢复 goroutine 和 deadline | poller 继续存在 |
| `ResetVm` | guest realtime 校准到当前时间 | 通常立即越过旧 deadline |
| 下一个 50 ms tick | deadline 已过 | cancel 主 poller |
| `PostInit` | prime 模式标记为 no-MMDS API | 不再启动第二个 60 秒 poller |

保留的 50 ms 检查版本连续三轮 c50/n500 均为 500/500，avg 为
199.59、202.92、205.64 ms。立即关闭、1 ms cancel、20 ms grace 和 timerfd
clean-stop 等更激进方案出现 reset timeout、HTTP 408 或残留 shim，因此未保留。

## 12. Native code server v3

提交：`51d36b0 perf(code-sandbox): add native code server v3`

### 上下文

如果 49999 提前监听，而每次 `/health` 再同步查询 envd，高频外部 Probe 会穿过
TAP 进入 guest，并继续放大为 envd health 请求。并发 restore 时，这会让尚未 ready
的 guest 同时处理大量连接和 handler。

### 实现

- 用小型静态 Go server 替换原 Python HTTP 控制进程。
- 进程启动时最多等待 envd 10 秒，envd 返回 2xx 后才 bind/listen 49999。
- 首次成功写入 `atomic.Bool envdReady`。
- Template 在 server ready 后捕获，因此快照中保存 `envdReady=true`。
- restore 后 `/health` 直接命中内存缓存，不再逐请求访问 envd。
- `POST /execute` 保留 `application/x-ndjson` 协议，每个请求仍启动独立 Python
  子进程，并保留 timeout、env vars、stdout、result、stderr 和 error 事件语义。

### 已知边界

1. **`envdReady` 是单向 readiness 缓存，不是持续 liveness。**

   envd 第一次返回 2xx 后，`atomic.Bool envdReady` 永久保持 true。Template 捕获并
   restore 这个内存状态后，`/health` 不再访问 envd。如果 envd 在 ready 后退出或
   失效，49999 仍会返回 200。若要增强生产期监控，应采用低频后台 revalidation、
   supervisor 联动退出或让 envd 退出时终止前台 server，不能恢复为每个高频 Cubelet
   Probe 都同步查询 envd，否则会重新引入本次消除的并发热点。

2. **`POST /execute` 本身不重新执行 envd readiness 门禁。**

   正式启动路径默认在监听 49999 前等待 envd，因此正常 Template 中该前提已经成立。
   但如果设置 `CUBE_WAIT_ENVD_BEFORE_LISTEN=0`，server 会立即监听；此时 `/health`
   在 envd 未就绪时返回 503，而 `/execute` 不会主动阻止请求。关闭 pre-listen gate
   后，调用方必须先通过 health 检查再发送 execute。

3. **NDJSON 是响应格式，不代表 stdout 实时流式传输。**

   当前实现使用 `bytes.Buffer` 收集完整 stdout/stderr，等待 Python 子进程退出后才把
   event 写入 HTTP 响应。长任务无法实时看到输出；用户程序产生大量输出时，server
   的内存占用会随输出增长。请求体限制为 16 MiB，但当前没有独立的 stdout/stderr
   大小上限。

4. **没有 server 级并发和资源限制。**

   每个 `/execute` 请求都会启动一个新的 Python 进程。Go HTTP server 可以并发处理
   多个请求，但代码没有 semaphore、队列、最大并发数或 per-request CPU/内存限制。
   实际约束依赖 OCI cgroup、guest 资源和 MicroVM 规格；突发请求可能造成 Python
   进程风暴、内存压力和调度长尾。

5. **native code server 不是安全隔离边界。**

   用户代码能够读取传入的环境变量，并以 `/workspace` 或
   `CODE_INTERPRETER_WORKDIR` 为当前目录访问容器文件系统。安全边界仍由 OCI
   container、guest OS 和 MicroVM 提供。server 没有自行实现 syscall、文件、网络
   或凭据隔离，不能脱离 CubeSandbox 隔离环境直接暴露给不可信请求。

6. **每次执行使用新 Python namespace，但工作目录是共享的。**

   runner 和用户源码写入独立的 `/tmp/cube-execute-*` 并在请求结束后删除，每次请求
   都启动新的 Python 解释器，因此不会保留上一次执行的内存变量。与此同时，Python
   子进程的当前目录默认都是 `/workspace`；并发请求读写相同业务文件时仍可能互相
   影响，需要由调用方或上层执行协议处理文件级隔离。

7. **执行超时和错误通过应用协议表达。**

   `timeout` 默认 60 秒、最小 1 秒，超时通过 `exec.CommandContext` 终止 Python
   进程并返回 `TimeoutExpired` event。Python exception、stderr 和非零退出也转换为
   NDJSON event。除畸形请求 JSON 返回 HTTP 400 外，代码执行失败通常仍是 HTTP 200，
   SDK 必须读取 `error` event，不能只依据 HTTP 状态判断执行成功。

8. **健康缓存收益依赖正确的 Template 捕获时机。**

   只有在 envd 已健康、native server 已将 `envdReady` 设为 true 且 49999 已监听后
   创建的 Template，restore 才能直接利用缓存。更换 OCI、启动脚本或绕过 readiness
   门禁后必须重新构建并验证 Template，不能假设旧快照自动具备 v3 状态机。

## 13. ARM64 OCI 可复现构建

提交：`b7d9402 build(code-sandbox): reproduce optimized ARM64 image`

### 上下文

如果优化只存在于远端实验二进制，无法审计 envd 基线、确认补丁是否应用，也无法
可靠重建相同 Template。

### 实现

多阶段 Dockerfile：

- 锁定 base image digest。
- 锁定 envd upstream commit。
- 锁定 Go builder `golang:1.26.2-bookworm`。
- 构建时应用 MMDS-prime patch，并静态编译 `linux/arm64` envd。
- 对 native code server 执行 `go test ./...` 和 `go vet ./...` 后再编译。
- final stage 只复制两个二进制和启动脚本，不提交本地预编译产物。
- 启动脚本计算 `now + 10s` deadline，后台启动 envd，前台 exec native server。

更换 OCI、guest image 或 guest kernel 后必须重建 Template；旧 Template 不会自动
继承新的 rootfs 文件或进程状态。

## 14. Restore 复用 guest-agent 连接转发 init 日志

提交：`2aca144 perf(cubeshim): reuse restore agent connection for init logs`

### 上下文

`SandBox::create_sandbox` 在 VM restore 后已经调用 `connect_agent`，并将
`AgentServiceClient` 传给 container。随后 `Container::start_log_forward` 为读取 init
stdout/stderr 又同步调用一次 `AsyncUtils::connect_agent`，建立第二条 vsock 连接。

在高并发 restore 中，第二次握手位于 `task.Start` 热路径。VM 刚恢复时，大量 shim
同时发起 vsock 连接，造成排队和长尾。日志转发必须在 init 输出管道填满前启动，
因此不能简单延后到创建完成之后。

### 实现

`CubeShim/shim/src/container/mod.rs` 根据启动类型选择 client：

```text
app_snapshot_restore = true
  -> clone 已经建立的 self.client
  -> 用同一底层 guest-agent 连接启动 init stdout/stderr forwarding

app_snapshot_restore = false
  -> 保持原逻辑
  -> 新建专用 vsock log connection
```

restore 分支 clone client 前只短暂持有 `Mutex`，随后把 clone 交给后台日志任务；不会
在整个流式读取期间持有 `self.client` 的 Rust `Mutex`。Template 创建和普通冷启动
继续使用专用连接，因为此时 init 尚未启动，控制 RPC 与长时间日志读取仍需要隔离。

日志协议没有变化：`exec_id` 仍为空，stdout/stderr 仍分别写入 bundle 下的文件，
pause/snapshot/kill/destroy 仍通过 watch channel 取消并等待 forwarding task。

### 已有阶段数据

后续部署二进制同时包含本优化和“跳过空 `CreateContainer` RPC”。在相同 2U2G
Template、c50/n500、每轮清理资源的条件下：

| 指标 | 优化前 | 优化后 |
|---|---:|---:|
| `task.Start - sandbox-create` avg | 35.28 ms | 0.95 ms |
| `task.Start - sandbox-create` p95 | 196.23 ms | 2.57 ms |
| CubeShim `CreateContainer` avg | 19.09 ms | 0.08 ms |
| CubeShim `CreateContainer` p95 | 152 ms | 1 ms |

三轮 c50/n500 共 1500/1500 成功，avg latency 均值 78.599 ms，p95 均值
136.724 ms，平均吞吐 502.93/s。串行 create + run_code 为 10/10，c20/n100
create 后立即 run_code 为 100/100，结果均正确。

这些数据来自部署阶段组合，不是当前分支最终源码头在同一二进制上的独立 A/B，
因此不能把全部收益归因于连接复用单项。

### 风险与验收边界

复用后，init stdout/stderr streaming 和后续 guest-agent 控制/执行 RPC 共享底层
ttrpc/vsock 连接。早期压力测试曾观察到高并发 `run_code` 秒级延迟和超时；后续
c20/n100 功能门禁全部正确，但并发执行耗时仍有约 0.1-6.1 秒波动。

因此当前结论是：

- 对 create-only 热路径收益显著。
- 已有串行和 c20 并发功能正确性证据。
- 尚不能宣称 c50 并发 `run_code` 尾延迟已经解决。
- 发布前应同时验收 create-only、create 后立即 execute、持续 execute 和动态
  Snapshot clone，不能只以创建 QPS 作为门禁。

## 15. 性能数据口径

不同数据来自不同阶段，不能直接相加或视为同一最终二进制的递进结果。

| 阶段 | 结果 | 说明 |
|---|---|---|
| CubeSandbox 核心 restore 组合 | c50/n500 三轮 1500/1500，avg 195.340 ms | 核心源码组合 A/B |
| 稳定 MMDS-prime | 三轮均 500/500，avg 199.59/202.92/205.64 ms | native code server 前的 OCI 阶段 |
| code server v3，early probe 关闭 | 四轮 2000/2000，avg 138.631 ms，p95 231.927 ms，QPS 264.020 | v3 Template 正式矩阵 |
| 日志连接复用 + 空 RPC 跳过 | 三轮 1500/1500，avg 78.599 ms，p95 136.724 ms，QPS 502.93 | 后续部署组合 |

当前分支汇总的是各阶段保留源码。分支最终头增加新提交后，仍应在相同 ARM64 节点、
相同 guest/OCI、1000 TAP 和严格资源清理条件下重新执行一次完整组合回归。

## 16. 明确未纳入的候选

- cross-stage early probe：平均 c50 仅额外改善 3.22%，已回退；标准 Probe quick
  retry 仍保留。
- GICv4、vtimer IRQ bypass、`nohlt`：收益不足或出现宿主机失联/创建失败。
- `maxcpus=1`：破坏 2U/3U/4U Template 语义。
- 延迟异步建立专用日志连接：动态 Snapshot clone 出现 GICv3 ITS restore
  `EINVAL`。
- 立即关闭或激进停止 MMDS：出现 reset timeout、HTTP 408 或残留 shim。
- guest 内 containerd exec HTTP Probe：c50 avg 和 p95 明显恶化。
- 社区 guest image：多轮出现 `reset guest time failed`。

## 17. 发布前验证建议

最低门禁：

1. `cargo fmt --check`、`cargo check --workspace --locked` 和依赖完整环境下的
   `cargo test --workspace --locked`。
2. c1/n20 基础创建、执行和删除。
3. c20/n100 create 后立即 `run_code`，校验 stdout/result。
4. c50/n500 create-only 至少三轮，记录成功率、avg、p95、p99、QPS。
5. c50 create 后分批和持续执行，专门验证共享 agent connection 的队头阻塞。
6. Pause/Resume 和动态 Snapshot clone，检查 GIC/ITS restore。
7. 每轮前后确认 sandbox、shim、task 为 0，TAP 总数和 in-use 数符合门禁。
8. 日志中不存在 HTTP 408、`reset guest time failed`、guest timeout、残留 shim。
9. native code server 分别验证 envd 启动失败、ready 后退出以及
   `CUBE_WAIT_ENVD_BEFORE_LISTEN=0`，确认 readiness 与 liveness 语义符合预期。
10. `/execute` 验证 timeout、Python exception、非零退出、大 stdout/stderr 和多请求
    并发，记录 guest 内存、进程数和尾延迟。

## 18. 相关源码

- `Cubelet/pkg/telnet/telnet.go`
- `cubelog/logger.go`
- `CubeShim/shim/src/sandbox/sb.rs`
- `CubeShim/shim/src/container/mod.rs`
- `CubeShim/shim/src/log/mod.rs`
- `hypervisor/devices/src/gic.rs`
- `hypervisor/pci/src/msix.rs`
- `hypervisor/vmm/src/interrupt.rs`
- `examples/code-sandbox-quickstart/images/arm64-performance/`
- `PERFORMANCE_VALIDATED_OPTIMAL_20260729.md`
