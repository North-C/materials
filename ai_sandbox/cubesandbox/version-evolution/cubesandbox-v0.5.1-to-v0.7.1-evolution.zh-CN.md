# CubeSandbox v0.5.1 至 v0.7.1 机制与组件演进报告

分析日期：2026 年 10 月 14 日。比较范围：官方 `v0.5.1` 至 `v0.7.1` 正式版本。

CubeSandbox 在这一阶段保留了 MicroVM 隔离、模板恢复启动、写时复制和 eBPF 网络的基础路线，主要变化发生在**组件职责、沙箱状态的存储与恢复、网络创建路径，以及集群的部署和升级机制**。因此，v0.5.1 的测试仍可说明早期架构的行为，但其中对创建瓶颈、暂停资源占用、恢复位置和指标口径的判断，需要在 v0.7.1 重新验证。

演进可概括为三个阶段：v0.6.0 引入 Kubernetes 部署和可插拔 Volume，并开始拆分运维服务；v0.7.0 引入 S3 跨节点状态恢复、组件多版本和网络子系统重构；v0.7.1 独立模板中心、增加 CLM 主备，并完善外部挂载与增量快照语义。**控制面高可用、跨节点恢复、计算节点无损升级是三个不同能力，不能相互替代。**

## 1 比较基线与版本时间线

源码比较固定在以下 tag，未将当前工作区的性能追踪、网络和 workflow 未提交改动计入官方版本变化，也未纳入 v0.7.2 及后续版本。

| 版本 | 官方发布说明日期 | 源码提交 | 本阶段定位 |
| --- | --- | --- | --- |
| v0.5.1 | 2026-07-10 | `a164417f` | 已具备独立 CLM、自动暂停恢复、三值 timeout 和 host-mount 白名单的基线 |
| v0.6.0 | 2026-07-24 | `8721dd15` | Kubernetes、Volume 插件、CubeOps、节点隔离与 guest cgroup v2 |
| v0.7.0 | 2026-08-28 | `d0081641` | 跨节点恢复、多版本运行时、网络内嵌 Cubelet、节点运维迁移 |
| v0.7.1 | 2026-09-11 | `31d911e4` | 模板中心与 CLM 高可用、外部挂载快照支持、存储和恢复语义完善 |

日期采用发布说明中的版本日期，不用源码提交时间代替；例如 v0.5.1 tag 对应提交的日期为 7 月 11 日。发布范围依据 [v0.5.1 release](https://github.com/TencentCloud/CubeSandbox/releases/tag/v0.5.1)、[v0.6.0 release](https://github.com/TencentCloud/CubeSandbox/releases/tag/v0.6.0)、[v0.7.0 release](https://github.com/TencentCloud/CubeSandbox/releases/tag/v0.7.0)、[v0.7.1 release](https://github.com/TencentCloud/CubeSandbox/releases/tag/v0.7.1)，具体机制以下文固定 tag 的源码和文档为准。

### v0.5.1 已经具备的能力

以下能力不是本次版本区间内首次引入：

- RustVMM/KVM MicroVM 隔离、模板启动和本地 COW 快照、克隆、回滚。
- ARM64 支持、AutoPause/AutoResume、腾讯云 Terraform 集群部署。
- CubeProxy 入向代理、CubeVS/eBPF 网络、CubeEgress L7 策略与凭据注入。
- 独立 `cube-lifecycle-manager`。v0.5.1 已将其从 CubeProxy sidecar 拆出，通过 Redis 发现多个 CubeProxy 副本。
- timeout 的“省略取服务端默认、`-1` 永不超时、`0` 立即超时、正数为 TTL”语义；host-mount 路径白名单；Node SDK 预览版。

v0.7.1 的 CLM 主备是在独立 CLM 基础上增加故障接管；Volume 插件是在已有 host-mount 之外增加存储生命周期抽象；多版本机制是在已有组件版本检查之外增加历史版本保留和选择能力。[基线说明](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/changelog/v0.5.1.md)、[v0.5.1 架构](https://github.com/TencentCloud/CubeSandbox/blob/v0.5.1/docs/zh/architecture/overview.md)

## 2 组件职责的变化

| 组件或机制 | v0.5.1 | v0.6.0 至 v0.7.1 的变化 | 影响 |
| --- | --- | --- | --- |
| CubeAPI | 沙箱 API 与 Web/运维相关逻辑同处一个模块 | v0.6.0 将 Web、运维逻辑拆到 CubeOps | 用户 API 与管理业务可以分别部署和演进 |
| CubeMaster | 调度、生命周期编排、节点管理、模板制作等职责集中 | v0.7.0 节点管理迁入 CubeOps；v0.7.1 模板物理构建拆到 CubeTemplateCenter | 控制请求与部分重型管理工作解耦 |
| CubeOps | 尚无独立组件 | v0.6.0 新增；v0.7.0 接管节点管理；v0.7.1 增加组件仓库 | 管理面逐步形成独立服务和分发入口 |
| CubeTemplateCenter | 无独立服务，模板构建在 CubeMaster 内 | v0.7.1 独立，负责镜像处理、artifact 构建和物理存储 | 模板构建可独立扩容，减少对 API 进程 CPU/IO 的竞争 |
| CLM | 已独立；支持协调多个 CubeProxy | v0.6.0 加强状态同步；v0.7.0 改进恢复协调；v0.7.1 增加主备选举 | 从代理可扩展推进到生命周期协调服务可接管 |
| Cubelet 与 network-agent | 网络代理是独立服务 | v0.7.0 网络管理内嵌 Cubelet，独立 `network-agent/` 目录被移除 | 创建链路减少跨进程调用，网络回收责任更集中 |
| CubeShim、VMM、cube-agent | 执行 VM 与 guest 内工作负载管理 | passfd IO、guest 指标、多版本选择、暂停退出与恢复流程更新 | 运行时核心仍在，但 IO、暂停和观测行为变化明显 |
| cubecow 与 CubeS3lvol | 本地 XFS COW 为主要快照路径 | v0.7.0 增加 CubeS3lvol 及 S3 后端 | 从本机状态资产扩展到满足条件时可跨机恢复 |
| 公共库与协议 | 各模块内包含多份协议及数据库等实现 | 到 v0.7.1 收敛到 `pkgs/`，包括公共 proto、CubeDB、CubeLog | 构建和二次开发需同步调整依赖及生成代码路径 |

组件拆分并未把所有流程移出 CubeMaster。例如 CubeTemplateCenter 不负责节点调度和 Cubelet RPC：CubeMaster 仍持有模板业务状态、构建 job 编排、节点分发和回调处理。故不能把“模板中心独立”解读为“所有模板业务都绕过 Master”。[模板中心职责设计](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/dev/templatecenter-design.md)、[公共协议合并 #1600](https://github.com/TencentCloud/CubeSandbox/pull/1600)

## 3 控制面与高可用机制

### 运维流逐步从控制请求中拆分

v0.6.0 首先从 CubeAPI 拆出 CubeOps；v0.7.0 再把 CubeMaster 中的节点管理迁入 CubeOps，包括节点注册和状态管理相关职责，节点命令入口也从 `cubemastercli node` 迁到 `cubeopscli`。CubeMaster 继续消费节点信息完成调度。

这会直接影响部署拓扑和升级顺序。旧版本的节点上报目标和新版本不同，不能只替换二进制而沿用全部端点配置。v0.7.1 的升级指南要求先保证 CubeOps 可用，再启动依赖它的 CubeMaster 和新版计算节点。[节点管理迁移 #1384](https://github.com/TencentCloud/CubeSandbox/pull/1384)、[固定版本升级指南](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/kubernetes/upgrade.md)

### 模板中心使构建和在线控制请求分离

v0.5.1 中，拉 OCI 镜像、解包、制作 ext4 等重型工作与在线控制请求位于同一 CubeMaster 进程。v0.7.1 的 CubeTemplateCenter 接管这些物理构建工作，CubeMaster 创建和持久化 job、接收结果并编排分发。

机制上的收益包括构建权限集中管理、构建 CPU/IO 与管控进程分离，以及模板产物使用共享存储后支持多副本访问。对于“边制作模板边高并发创建沙箱”的场景，这是实质变化；对于模板已经预热、测试期间没有构建的场景，不能据此推断创建吞吐必然大幅提升。[实现 #1659](https://github.com/TencentCloud/CubeSandbox/pull/1659)、[模板中心设计](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/dev/templatecenter-design.md)

多副本需要配套 artifact 存储。使用 S3 或共享存储时，各副本才能读到相同产物；本地独立磁盘不具备相同保障。v0.7.1 Helm 的 Master 和模板中心默认仍为单副本，artifact 默认也不是 S3-backed。存量本地 artifact 不会因打开 S3 配置自动迁移；`tpl merge` 负责存储迁移，`tpl redo` 负责重新分发或必要时重建。[Helm values](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/deploy/kubernetes/chart/values.yaml)、[迁移语义](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/dev/templatecenter-design.md)

### CLM 主备与依赖服务的边界

v0.7.0 先改进了跨副本恢复等待：Redis Pub/Sub 用作唤醒提示，Redis 中的状态仍是依据，并保留 100 毫秒轮询兜底。它减少某些等待窗口，但没有取消轮询或改成只依靠消息通知的状态机。[恢复唤醒 #1393](https://github.com/TencentCloud/CubeSandbox/pull/1393)、[resumer 实现](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/cube-lifecycle-manager/internal/resumer/resumer.go#L380)

v0.7.1 CLM 通过 Redis 租约选择执行单例维护任务的 leader，使用 `SET NX PX` 获取租约，并通过事务续租和释放。备用副本仍能处理恢复请求和同步状态，并非完全闲置。选举关闭时保留单实例行为。[CLM leader 实现](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/cube-lifecycle-manager/internal/leader/lease.go)、[主备实现 #1667](https://github.com/TencentCloud/CubeSandbox/pull/1667)

发布说明的“全链路高可用”指 Cube 控制面服务具备相应部署机制。最终集群可用性仍取决于实际副本数、负载均衡、Redis、数据库和共享对象存储；单实例 MinIO 或单库部署不会因升级组件而自动变成高可用。它也不表示计算节点崩溃后能恢复尚未持久化的 VM 内存状态。[组件仓库部署边界](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/component-multiversion.md)、[跨节点恢复条件](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/cross-node-snapshot.md)

### 调度容量与资源准入

调度仍延续候选过滤、评分和选择框架，但 v0.7.1 的 #1575 移除了 Master 对节点上报 quota 再乘一次 overcommit ratio 的处理。旧的 `overcommit_ratio` / `overcommit_ratio_conf` 配置仍可解析，却会被忽略并告警；准入基于节点上报 quota 及已分配量等条件计算。因此，相同配置文件在两个版本中不一定代表相同有效可调度容量。[调度变更 #1575](https://github.com/TencentCloud/CubeSandbox/pull/1575)、[CPU 过滤器](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/CubeMaster/pkg/selector/filter/cpufilter.go#L43)、[配置兼容处理](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/CubeMaster/pkg/base/config/config.go#L276)

v0.7.0 修正 CPU/内存数量精度，v0.7.1 修复非法规格被解析成零而绕过资源过滤的问题。对容量上限、资源不足拒绝率和高并发分配结果的比较，需要核对实际 quota 和请求解析结果，不能只对照 YAML 文本。[数量精度 #1397](https://github.com/TencentCloud/CubeSandbox/pull/1397)、[非法规格修复 #1463](https://github.com/TencentCloud/CubeSandbox/pull/1463)

## 4 存储与沙箱状态机制

### Volume 插件和 VM 快照后端是两条不同的链路

v0.6.0 新增 Volume 框架，通过 Create、Destroy、Attach、Detach 四个 hook 对接存储，插件既可为可执行程序，也可通过 RPC 提供服务。控制端管理卷生命周期，计算节点在沙箱使用时 Attach/Detach。它解决的是“用户数据如何挂到沙箱中”。[Volume 框架 #997](https://github.com/TencentCloud/CubeSandbox/pull/997)、[Volume 插件协议](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/volume-plugin.md)

v0.7.0 的 CubeS3lvol 则服务于 VM 状态和 COW 快照：基于 SPDK 构建以 S3 为后端的远程写时复制块设备，结合本地 WAL、journal、缓存和异步对象存储同步，并通过 NVMe-oF/TCP 在宿主侧访问。它解决的是“暂停包和快照如何持久化、共享和恢复”。因此，给沙箱挂一个 S3 Volume，并不会自动让这个沙箱具备跨节点暂停恢复能力。[CubeS3lvol #1490](https://github.com/TencentCloud/CubeSandbox/pull/1490)、[CubeS3lvol 实现说明](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/CubeS3lvol/README.md)

| 使用对象 | 主要目的 | 与跨机恢复的关系 |
| --- | --- | --- |
| Host Mount | 访问宿主目录 | 外部路径没有集群身份，恢复固定在源节点 |
| Plugin Volume | 管理外部业务数据卷 | 目标节点必须能 Attach；卷本身不决定 VM 状态是否可跨机 |
| cubecow XFS 后端 | 本地 VM 快照和暂停包 | 仍然受本机放置约束 |
| cubecow S3 后端与 CubeS3lvol | 共享 VM 暂停包和快照状态 | 满足同步完成与兼容条件后可跨机 |
| 模板中心 artifact S3 存储 | 保存模板构建产物 | 支持模板服务多副本，不等于自动开启 VM 的 S3 后端 |
| CubeOps 组件仓库 | 分发历史组件版本 | 补齐恢复所需二进制，不代替 VM 快照存储 |

### 跨节点恢复是有条件的暂停后恢复

v0.7.0 引入的跨机能力在发布时标记为预览；v0.7.1 完善该路径。它基于持久化包重新恢复 VM，不能当作不停机 live migration。源码和指南规定的主要条件包括：

1. 模板创建时选择 `backend=s3`，其派生沙箱、暂停包和快照继承该后端；既有 XFS 资产不会因部署 MinIO 自动转换。
2. 远端状态必须为 `ready`。本地 Pause/Snapshot 完成与远端同步完成是两个不同时间点；同步未就绪仍可能本机恢复，但不能跨机。
3. 调度优先源节点，源节点不可调度才评估跨节点目标；不是每次恢复都重新选择全局最空闲节点。
4. 目标必须通过兼容性校验。v0.7.1 以 `cpuid_hash` 和 `host_kernel_release` 做相等匹配，并拒绝带非空 KVM module taint 的目标。
5. raw host-mount 固定源节点。Plugin Volume 可随 VM 跨机恢复，但目标必须有对应 driver 和后端访问能力。

这些条件来自 [v0.7.1 跨机指南](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/cross-node-snapshot.md) 和 [restoreplace 实现](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/CubeMaster/pkg/restoreplace/placement.go)。对照官网 v0.7.0 文章时，应采用这些实现约束，而不能把文章中的“沙箱跨机器流动”扩展为任意节点之间的无条件迁移。

### Pause 的资源释放和增量状态处理发生变化

v0.5.1 已经通过内部全量快照恢复暂停的 VM，并非仅停住 vCPU；其内存文件不作为 cubecow catalog 暴露。v0.7.0 的 #1322 将 Pause/Resume 转入 cubecow 包流程：保存重建信息，清理活动运行时，恢复时重新创建同一 sandbox ID，并恢复网络和挂载。到 v0.7.1，具体清理由 Cubelet 在快照成功后完成，而不是把 shim 提前退出视为成功。暂停态删除也不再需要先恢复再销毁。[v0.5.1 内部全量恢复](https://github.com/TencentCloud/CubeSandbox/blob/v0.5.1/Cubelet/services/cubebox/update.go#L504)、[v0.7.1 暂停后清理](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/Cubelet/services/cubebox/pause_cow.go#L418)

v0.7.1 的 #1639 进一步采用类似 Snapshot 的增量内存导出并保留 XFS pause package；#1688 修复 S3 恢复后再次制作 Snapshot 退化为全量内存导出的问题。增量依赖可用基底，基底不存在或相关克隆失败时仍有全量导出的回退路径，不能理解为每一次 Pause 都是增量。[内存基底选择与回退](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/Cubelet/services/cubebox/snapshot_base_memory.go#L235)

因此，应分别观察 Pause 返回时间、后台同步时间、暂停后的进程与内存占用、Resume 时间，以及恢复后的第二次 Snapshot。仅比较一次 Pause API 时延无法覆盖这一阶段的机制收益和额外开销。[Pause 重构 #1322](https://github.com/TencentCloud/CubeSandbox/pull/1322)、[增量 Pause #1639](https://github.com/TencentCloud/CubeSandbox/pull/1639)、[S3 增量修复 #1688](https://github.com/TencentCloud/CubeSandbox/pull/1688)

v0.7.1 还引入或完善了两项存储生命周期行为：仍被运行沙箱引用的快照可以逻辑删除，物理存储在引用释放后回收；同桶跨节点恢复可以使用对象存储服务端复制，减少经客户端中转的数据路径。快照删除成功不再意味着占用空间立即归零，同桶优化也不能推广到所有跨桶或跨后端恢复。[快照删除 #1620](https://github.com/TencentCloud/CubeSandbox/pull/1620)、[延迟删除与同桶恢复 #1663](https://github.com/TencentCloud/CubeSandbox/pull/1663)

同版 #1701 将 S3 REF export 的寿命绑定到快照删除，避免仅因 TTL 到期失去可恢复引用。另一方面，v0.7.1 跨机指南仍列出恢复后短期内再次 Pause/Snapshot 的等待限制，以及部分底层拒删对象需后续处理的情况。连续恢复与快照、删除后的最终空间回收应按实际路径验收，不能由单次 API 成功推断全部后台工作完成。[引用保留 #1701](https://github.com/TencentCloud/CubeSandbox/pull/1701)、[已知问题](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/cross-node-snapshot.md)

### 外部挂载快照保存的是引用

v0.7.1 支持对含 Host Mount 或 Plugin Volume 的沙箱执行快照、恢复、回滚和克隆，但**不会把外部目录或卷的数据复制进 VM 快照**。

| 操作 | VM 内存与根文件系统 | 外部目录或 Volume |
| --- | --- | --- |
| Snapshot | 记录可恢复状态 | 记录挂载配置或稳定 Volume ID |
| Restore / FromSnap | 恢复记录的状态 | 重新挂载，看到外部存储当前数据 |
| Rollback | 回到快照状态 | 外部数据不回滚 |
| Clone | 产生独立 VM 状态 | 继续引用同一外部目录或卷 |

Plugin Volume 快照不会持久化运行时 `private_data`，恢复时重新查询卷记录并 Attach。调度器目前也不保证检查卷 topology、multi-attach 或目标 driver 能力；这些条件不满足时创建会失败。对于带共享数据的 Agent 分支实验，“VM 克隆隔离”不能被解释为“外部数据也分叉隔离”。[Host Mount 语义](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/persistent-storage.md#host-mount-沙箱的快照)、[Volume 语义](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/volume-plugin.md)、[实现 #1654](https://github.com/TencentCloud/CubeSandbox/pull/1654)、[实现 #1656](https://github.com/TencentCloud/CubeSandbox/pull/1656)

## 5 网络与运行时热路径

### 网络创建由独立进程调用转为 Cubelet 内部管理

v0.7.0 将 network-agent 嵌入 Cubelet，网络控制流程由 `Cubelet/network/` 管理；CubeVS/eBPF 数据面继续存在。这里改变的是控制路径和设备生命周期，不是取消虚拟交换或换成另一套隔离技术。

网络优化包含 TAP 生命周期重构、策略下发延迟优化，以及减少空闲 TAP 耗尽时的不必要 netlink dump。对高并发创建而言，需要区分“从 TAP 池取得设备”与“池耗尽后新建设备”两种路径。v0.5.1 中归因于 network-agent RPC、策略下发或设备创建的瓶颈，不能直接沿用到 v0.7.1。[网络内嵌 #1285](https://github.com/TencentCloud/CubeSandbox/pull/1285)、[策略和高密度 TAP 优化 #1318](https://github.com/TencentCloud/CubeSandbox/pull/1318)、[v0.7.1 网络运行时](https://github.com/TencentCloud/CubeSandbox/tree/v0.7.1/Cubelet/network/runtime)

v0.5.1 已经修复过 TAP 回收和残留策略问题；后续重构继续加强 Pause/Resume、节点重启和失败回收路径。v0.7.1 又修复 TAP 名超长被内核截断，以及网关 ARP 尚未就绪时初始化失败的问题。这些修复更直接影响错误率和尾延迟，不能仅用平均创建时延衡量。[TAP 名修复 #1552](https://github.com/TencentCloud/CubeSandbox/pull/1552)、[启动期 ARP 修复 #1609](https://github.com/TencentCloud/CubeSandbox/pull/1609)

其中 #1318 的具体做法是缓存 eBPF HashOfMaps 的 inner map 文件描述符，减少 create/apply/reaper 中重复 outer lookup 带来的同步 RCU 等待；缓存未命中仍要 lookup，并非取消内核 RCU。每个活跃 TAP 最多保留约三个这类 FD，直到 TAP 销毁或陈旧状态清理。因此网络时延改善伴随进程 FD 常驻量变化，高密度测试应一并观察。[inner map 缓存实现](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/CubeNet/cubevs/inner_cache.go#L11)

### 网络策略与代理兼容能力扩展

| 阶段 | 变化 | 对测试或应用的意义 |
| --- | --- | --- |
| v0.6.0 | `maskRequestHost`；MITM 证书 SAN；traffic token 失败返回 403；Connect 流禁用 gzip | Host 依赖应用、TLS 校验和流式 RPC 行为更完整 |
| v0.7.0 | 运行中更新 egress 策略；自定义 L7 端口；CubeProxy 明文 gRPC ingress；CubeVS 同子网 MAC 学习 | 策略可动态调整，协议和网络拓扑覆盖扩大 |
| v0.7.1 | 慢首包代理超时从 60 秒扩大至 2 小时；限制单条凭据注入大小为 2048 字节 | LLM 长等待与异常输入的成功率/错误行为变化 |

例如，v0.5.1 下的慢首包失败，不能直接解释为 v0.7.1 下的 VM 性能限制；失败次数下降也不等于执行本身更快。[Host 配置](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/changelog/v0.6.0.md)、[动态策略 #1399](https://github.com/TencentCloud/CubeSandbox/pull/1399)、[代理超时 #1655](https://github.com/TencentCloud/CubeSandbox/pull/1655)、[凭据上限 #1606](https://github.com/TencentCloud/CubeSandbox/pull/1606)

动态网络更新采用全量替换语义，省略的字段可能被清空。更新后已建立流在下一包重新检查，不再允许的 TCP 会话可被重置；已有 DNS 学习项仍可能保留至 TTL 到期，所以不能承诺所有域名撤权即时生效。端口配置也发生迁移：CubeEgress admin 默认端口改为 9091，避免与 CubeProxy 明文 gRPC 的 9090 冲突。[动态策略实现](https://github.com/TencentCloud/CubeSandbox/commit/bbaa495c)、[网络内嵌变更](https://github.com/TencentCloud/CubeSandbox/pull/1285)

### guest cgroup 与进程 IO

v0.6.0 通过 guest 内核参数启用 cgroup v2。这里指沙箱内的工作负载资源层级，不表示所有宿主机都强制从 cgroup v1 切换到 v2。[guest cgroup 变更 #899](https://github.com/TencentCloud/CubeSandbox/pull/899)

v0.7.0 引入 passfd IO：Shim 将 stdin/stdout/stderr 的文件描述符经 Unix socket `SCM_RIGHTS` 交给 VMM，由 vsock 后端接入 guest agent，避免逐块 IO 经过原先的 RPC streaming 转发路径，同时补充暂停恢复后的 IO 重连。控制 RPC 仍然存在，不能称为整个运行时“去 RPC 化”。[passfd 提交](https://github.com/TencentCloud/CubeSandbox/commit/2aec7dd7f3d19cf7aff3a8caa8d3fa5d98cd45da)、[Shim FD 传递](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/CubeShim/shim/src/common/utils.rs#L562)、[guest passfd](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/agent/src/passfd_io.rs)

此优化直接针对 Shim/agent 管理的进程 IO。SDK 的命令、文件或 RunCode 可能经过 envd/Jupyter 和代理路径；评估性能时应先确定调用链，不能将底层 passfd 优化按同样比例套到所有 SDK 请求。

v0.6.0 还增加模板级 ivshmem opt-in，属于显式实验选项；v0.7.1 对 virtiofsd 增加白名单下的根目录修改限制和伪造 readdirplus 防护。这分别扩展了可选设备能力和收紧了宿主文件访问边界，不应归入默认创建性能收益。[ivshmem #858](https://github.com/TencentCloud/CubeSandbox/pull/858)、[virtiofsd 加固 #1612](https://github.com/TencentCloud/CubeSandbox/pull/1612)

## 6 组件多版本与升级机制

v0.7.0 将“检查组件版本是否一致”推进为“保留并选择历史组件版本”。`cube-agent` 也从 guest image 中解耦，以独立 ext4 产物交付，新增 `guest-init` 承担 VM 的 PID 1 初始化职责。新模板和快照记录依赖版本，创建或恢复按所绑定版本选择组件，而不是一律使用当前 toolbox。

v0.7.1 在此基础上新增 CubeOps 组件仓库。计算节点本地没有所需版本时，可以从仓库按需下载；组件包括 `cube-shim`、`cube-image`、`cube-agent`、`cube-kernel-scf`。中心产物存于对象存储，节点通过下载地址获取内容。[多版本 #1316](https://github.com/TencentCloud/CubeSandbox/pull/1316)、[agent 解耦 #1234](https://github.com/TencentCloud/CubeSandbox/pull/1234)、[组件仓库 #1353](https://github.com/TencentCloud/CubeSandbox/pull/1353)

这一能力有三个实际边界：

- 所需旧版本必须仍在节点或仓库中；缺失时不会用新版组件替代以假装兼容。
- 历史迁入的副本可能只绑定部分组件，不享有新模板完整的 stable restore 保证。不能承诺所有 v0.5.1 模板在升级后都自动无损可用。
- 首次下载大型组件会进入创建/恢复耗时；做版本性能对比前需要预装并记录组件缓存状态。

版本库还会增加磁盘占用，中心删除不等于自动清理节点副本。[v0.7.1 多版本指南](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/component-multiversion.md)

内核和 guest image 产物从 v0.7.0 起独立发布，主版本构建引用固定产物。因此实验不能只记录“CubeSandbox v0.7.1”，还应记录 shim、agent、guest image、guest kernel、宿主 kernel 与虚拟化模式。[独立产物发布 #1324](https://github.com/TencentCloud/CubeSandbox/pull/1324)

对直接跨越 v0.5.1 的升级还需特别区分“新机制可用”和“旧数据已验证迁移”：v0.7.1 指南明确写明，0.7.0 前后的 DB/文件布局变化较大，旧数据适配测试只覆盖到 v0.6.0，且针对旧数据清理场景。因此不能把该机制当作 v0.5.1 全部存量快照可直接无损迁移的保证。[旧数据适配范围](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/cross-node-snapshot.md#L394)

组件仓库还伴随默认 create RPC 预算由 300 秒增加至 600 秒，以容纳首次组件下载等等待。这与模板 AppSnapshot RPC 的默认 300 秒是不同配置；测试中的超时失败减少不一定意味着请求执行更快。[create 默认预算](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/CubeMaster/pkg/base/config/config.go#L945)

## 7 部署与运维变化

v0.6.0 的 Kubernetes Helm 部署同时覆盖控制面和计算面，发布时明确标记预览。到 v0.7.1，计算面仍有重要升级约束：`cube-node` Big Pod 重建可能销毁 netns，进而中断挂在其上的 TAP 和 CubeVS 网络。`hostNetwork` 可缓解网络命名空间变化这一项风险，但不能据此宣称整个计算面升级零中断。[Kubernetes 升级指南](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/kubernetes/upgrade.md)

其他部署变化如下：

| 变化 | 首次或后续阶段 | 升级含义 |
| --- | --- | --- |
| PostgreSQL 元数据后端 | v0.6.0；v0.7.1 补一键部署外部 PostgreSQL | 底层支持与安装器接入不是同一次交付 |
| `CUBE_AUTO_MIGRATION` | v0.6.0 | 可将数据库迁移从普通服务启动中分离，控制升级时机 |
| Redis Sentinel 可选支持 | v0.7.0 | 支持对接主节点发现和故障切换，默认 standalone 部署不会自动变成 Sentinel |
| Cubelet state tmpfs 动态扩容 | v0.6.0 | 高密度场景的状态存储限制发生变化 |
| 节点隔离、后续节点删除 | v0.6.0 / v0.7.0 | 隔离阻止新调度，既有沙箱继续运行；不等于自动排空迁移 |
| CubeS3lvol Kubernetes sidecar | v0.7.1 | K8s 也可部署跨机状态后端 |
| CubeS3lvol 显式 opt-in | v0.7.1 | `[cow.s3] enable=true`；one-click 为 `ONE_CLICK_ENABLE_S3LVOL=1`；Helm 为 `cubeS3lvol.enabled=true` |
| Helm `redis.db` 统一 | v0.7.1 | 同一 Redis 下各集群需要统一配置自身逻辑库，避免组件视图不一致 |

尤其要区分“部署了 MinIO”“启用 CubeS3lvol”和“使用 S3 模板”三个动作。v0.7.1 默认关闭 CubeS3lvol；从此前隐式使用 S3 的部署升级时，必须显式开启。文档还给出每节点约 2 核、18 GiB 内存和默认 512 GiB 稀疏 WAL 镜像的规划参考；这些是该后端的部署资源要求，512 GiB 不是启动时立即占用的物理磁盘，也不能作为每个沙箱的内存开销。[跨机部署与存储规划](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/cross-node-snapshot.md)、[开启开关 #1622](https://github.com/TencentCloud/CubeSandbox/pull/1622)、[K8s 集成 #1637](https://github.com/TencentCloud/CubeSandbox/pull/1637)

Redis Sentinel 接入可追溯至 [#998](https://github.com/TencentCloud/CubeSandbox/pull/998)。此外，Master HTTP 在 v0.6.0 从 gorilla/mux 改为 gin，属于服务实现变化；不能仅由框架切换推断 API 吞吐提升。[HTTP 重构 #922](https://github.com/TencentCloud/CubeSandbox/pull/922)

## 8 SDK 和可观测性变化

### SDK 能力逐步对齐

v0.6.0 增加模板别名，初期主要覆盖创建时设置和 Python 使用；v0.7.0 扩展到既有模板别名管理和 Go/Node/Python，Volume CRUD 与挂载也在 Go、Node 补齐。其间修复了 Go PTY/协议帧、私有沙箱 traffic token、Python X-API-Key 和 Node Authorization 等问题。[模板别名 #1120](https://github.com/TencentCloud/CubeSandbox/pull/1120)、[Go Volume #1269](https://github.com/TencentCloud/CubeSandbox/pull/1269)、[Node Volume #1277](https://github.com/TencentCloud/CubeSandbox/pull/1277)

timeout 的基本三值语义在 v0.5.1 已存在，v0.7.1 修复的是实际实现中的边界，包括 NEVER_TIMEOUT 被误判过期、Resume 新 timeout 丢失，以及 Node/Python 命令特殊 timeout 导致请求不返回。复用旧测试脚本时，需要同时记录 SDK 版本和测试调用的 timeout 字段，而不是把 server idle TTL、创建 RPC deadline、命令执行 timeout 混作一个参数。[Resume 修复 #862](https://github.com/TencentCloud/CubeSandbox/pull/862)、[命令 timeout 修复 #1485](https://github.com/TencentCloud/CubeSandbox/pull/1485)

### 资源指标从计数读取扩展到生命周期记账

v0.7.0 增加 guest `Task.Stats` 传输与 Cubelet 生命周期感知的资源指标。它区分两种统计视角：

- `host_sandbox`：宿主侧沙箱 cgroup，包含 Shim、VMM 等宿主资源记账。
- `guest_workload`：guest 内工作负载容器 cgroup，不含 cube-agent 等管理进程。

两者不能直接相加，也不能将 host cgroup 内存直接当作 guest 工作集或按比例分摊的物理内存。默认导出 `host_sandbox`；guest 视角要求新 agent 能力和 cgroup v2。旧模板可能仍能运行，却不支持新增 guest 指标。[指标传输 #1090](https://github.com/TencentCloud/CubeSandbox/pull/1090)、[生命周期指标 #1122](https://github.com/TencentCloud/CubeSandbox/pull/1122)

指标由后台有界并发采样并缓存，`/v1/metrics/resource` 抓取只读缓存；原 `/v1/metrics` 仍存在。新建、clone 和 rollback 会调整 guest 统计周期/基线，pause/resume 保留相应周期，暂停或陈旧样本停止导出而不是报零。这既改变观测语义，也引入可配置后台采样工作，性能比较应固定启用范围和频率。[资源指标指南](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/guide/resource-metrics.md)、[采样插件默认值](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/Cubelet/plugins/cube/internals/resourcemetrics/plugin.go)

## 9 对 v0.5.1 测试结论的影响

以下是根据机制变化得到的复测重点，不是已经测得的 v0.7.1 性能增幅。发布说明中“更快”或“延迟下降”的描述不足以推导当前机器上的 C100/N100 吞吐、P99 或提升百分比。

| 旧测试或结论 | 为什么需要复核 | v0.7.1 应如何对照 |
| --- | --- | --- |
| 高并发 create 的网络开销 | network-agent 内嵌、策略下发与 TAP 分配改变 | 分别测 TAP 充足/耗尽、无规则/有规则；记录创建子阶段及错误率 |
| 相同规格下的容量上限 | Master overcommit 倍率取消，资源规格解析修复 | 核对节点实际 quota、Redis 分配量和有效准入规则 |
| 并发 create 的模板缓存竞争 | v0.7.0 修复共享运行模板被并发修改和本地缓存竞态 | 相同模板与多模板负载分开；同时观察正确性与 P95/P99 |
| 模板构建拖慢在线请求 | v0.7.1 独立模板中心 | 将预热模板创建与并发模板构建混合负载分开 |
| 暂停后资源仍被占用 | Pause 包、shim 退出和增量链路改变 | 测 API 时延之外的进程数、cgroup 内存、磁盘与远端同步 |
| 快照和恢复固定原节点 | S3 引入跨机能力，但仍有放置约束 | 分 XFS 本机、S3 本机、S3 跨机；等待 remote ready 后再迁移 |
| Snapshot 恢复后再次快照的耗时 | v0.7.1 修复增量退化 | 固定脏页量，比较连续 Snapshot 及 Resume 后 Snapshot |
| exec 或日志吞吐 | passfd、日志恢复与 SDK 路径修复 | 区分底层 runtime exec、envd Commands 和 Jupyter RunCode |
| CPU/内存指标或单机密度 | 新指标有不同记账范围和生命周期基线 | 同时保留宿主系统指标，明确 host/guest scope，避免指标口径替换 |
| 旧模板直接与新模板比较 | 多版本机制可能让旧模板继续运行旧 agent/kernel | 记录模板绑定组件；另测新版组件重建模板，分开“兼容”与“升级收益” |
| SDK 成功率和超时 | timeout、auth、token、长首包行为均有修复 | 固定 SDK 和请求参数，区分执行更快与原有失败被修复 |

并发模板问题可追溯到 [运行模板复制 #1366](https://github.com/TencentCloud/CubeSandbox/pull/1366) 和 [Master 缓存竞态 #1376](https://github.com/TencentCloud/CubeSandbox/pull/1376)。

对于当前高并发瓶颈分析，优先建立一个可比较的基础组：同一硬件、宿主内核和虚拟化模式，同等规格与工作负载，使用本机 XFS、预热模板和组件缓存，固定策略、TAP 池、日志及指标配置。然后单独增加新功能变量：S3 后端、跨机恢复、Volume、模板构建并发和多副本控制面。这样才能区分核心创建路径变化与新能力的附加成本。

建议保留 create、exec、snapshot、pause、resume、delete 的端到端时延、P50/P95/P99、成功率，以及 CPU、RSS/cgroup 内存、磁盘 IO、网络流量；S3 场景另记 remote ready 时间和后台存储资源。官方版本与当前工作区的优化/追踪版本应分别标记，避免将本地修改效果记到官方 v0.7.1。

## 10 阅读来源与复核入口

发布说明适合确定交付阶段，博客适合理解设计动机；涉及限制条件时，以固定 `v0.7.1` 的实现和指南为准。

| 来源 | 阅读重点 |
| --- | --- |
| [官网博客目录](https://cubesandbox.com/zh/blog/) | 版本文章与技术专题入口 |
| [v0.6.0 官网文章](https://cubesandbox.com/zh/blog/posts/2026-07-24-cubesandbox-v0.6.0-release) | Kubernetes、Volume 和 CubeOps 的引入动机 |
| [v0.7.0 官网文章](https://cubesandbox.com/zh/blog/posts/2026-08-28-cubesandbox-v0.7.0-release) | 跨机、多版本和网络重构；其中 Coming Soon 不属于已交付能力 |
| [v0.7.1 中文变更说明](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/changelog/v0.7.1.md) | 高可用、外部挂载、默认开关与修复 |
| [完整版本差异](https://github.com/TencentCloud/CubeSandbox/compare/v0.5.1...v0.7.1) | 逐文件与逐提交追溯 |
| [固定版本架构概览](https://github.com/TencentCloud/CubeSandbox/blob/v0.7.1/docs/zh/architecture/overview.md) | 组件总体位置 |

本文的性能影响属于基于机制的分析，没有代替在目标机器上执行版本对照测试。有关已有 v0.5.1 结果的具体数值归因，需要将其原始脚本、配置和测量边界与上述变化逐项对齐。
