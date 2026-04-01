# Cloud Hypervisor + Nydus 实现细节与性能原理分析报告

## 项目范围与分析目标

本文聚焦当前仓库主线代码中的 `Cloud Hypervisor + Nydus` 场景，重点分析：

1. 启动链路如何串起来
2. `Cloud Hypervisor`、`nydusd`、Kata runtime、agent、rootfs 组织之间如何分工
3. `virtio-fs-nydus`、`rafs`、`overlay` 在数据流上的关系
4. 性能收益来自哪里
5. 性能代价与当前实现边界是什么

本文以主线代码现状为准，不以外部设计目标或社区预期替代实现事实。

---

## 一、结论摘要

从当前仓库实现看，`Cloud Hypervisor + Nydus` 是一个真实存在且基本闭环的性能优化路径。

它的核心思路不是优化 VM 冷启动本身，而是把容器镜像准备过程改造成：

- 宿主机侧由 `nydusd` 提供 `virtiofs` 服务
- guest 侧通过共享文件系统访问 Nydus 暴露出来的目录和 RAFS 挂载结果
- 最终将只读镜像层和可写快照层组合成容器 rootfs

这条链路在当前代码中已经能清楚看到：

- 配置层允许 `shared_fs = "virtio-fs-nydus"`
- `cloudHypervisor` 会把 `nydusd` 当作特殊的 virtiofs daemon 启动
- `kata-agent` 会把共享挂载点切换到 Nydus 专用目录
- runtime-rs 侧存在 `rafs_mount + overlay` 的 rootfs 组装实现

因此，对 `Cloud Hypervisor` 场景来说，Nydus 不是“规划中的能力”，而是当前代码中最值得继续深挖的现实优化路径。

---

## 二、这项优化到底优化了什么

`Cloud Hypervisor + Nydus` 优化的不是 VMM 启动，而是容器 rootfs 准备链路。

在传统 OCI 镜像路径下，容器启动前往往要完成：

1. 拉取镜像层
2. 解压镜像层
3. 在本地准备 overlay lowerdir
4. 把 rootfs 暴露给 guest

Nydus 的作用是把其中很大一部分“启动前必须完成”的工作改成：

- 通过 RAFS 元数据表达镜像内容
- 运行时按需访问镜像文件
- 通过专门的 daemon 和共享文件系统暴露给 guest

因此它优化的是：

- 镜像冷启动等待
- 大镜像解压与展开成本
- 多层镜像和海量小文件镜像带来的准备成本

如果把启动耗时拆成两段，那么：

- `Cloud Hypervisor` 负责 VM 建起来
- `Nydus` 负责镜像 rootfs 更快变得可用

这两者的优化对象不同，但在最终容器启动时延中会叠加体现。

---

## 三、配置入口与能力声明

## 3.1 Cloud Hypervisor 配置模板

在以下配置模板中，`shared_fs` 都明确允许 `virtio-fs-nydus`：

- `src/runtime/config/configuration-clh.toml.in`
- `src/runtime-rs/config/configuration-cloud-hypervisor.toml.in`

这说明从配置模型上，主线代码已经把 `Cloud Hypervisor + Nydus` 视为正式支持场景，而不是实验性拼接。

## 3.2 Hypervisor 能力声明

在 Go runtime 的 `src/runtime/virtcontainers/clh.go` 中，`Capabilities()` 会在启用共享文件系统时声明文件共享能力。

这意味着：

- CH 会向 Kata 上层表明自己支持文件共享
- 这样 agent 和 rootfs 管理路径才会选择 shared-fs 方案，而不是 block 或 9p 等其他路径

这一点虽然不是 Nydus 独有，但它是 Nydus 路径能成立的前提。

---

## 四、总体架构：组件怎么分工

`Cloud Hypervisor + Nydus` 这条链路可以拆成五个关键角色：

### 4.1 Kata runtime

职责：

- 解析配置和 OCI/rootfs 信息
- 识别当前 shared-fs 类型是 `virtio-fs-nydus`
- 启动并管理 `nydusd`
- 配置 Cloud Hypervisor 的 virtio-fs 设备
- 把 rootfs 相关元数据传给 guest

### 4.2 Cloud Hypervisor

职责：

- 启动 VM
- 通过 vhost-user/virtio-fs 方式把宿主机共享目录接入 guest
- 提供 guest 内的共享文件系统访问入口

CH 本身不负责解析 Nydus 镜像格式，也不直接完成 RAFS 逻辑。它扮演的是“共享文件系统承载层”。

### 4.3 nydusd

职责：

- 以 `virtiofs` 模式运行
- 通过 API socket 接受 mount/umount 指令
- 管理 `passthrough_fs` 和 `rafs` 挂载
- 把宿主机上的共享目录和 Nydus 镜像内容组织成 guest 可访问形态

它是整条链路里最关键的中间层。

### 4.4 kata-agent

职责：

- 在 guest 内接收来自 runtime 的 storage 定义
- 挂载共享文件系统到特定 guest 目录
- 继续把最终 rootfs 交给容器创建流程

agent 负责把“共享文件系统已经接进 VM”这件事，转化为“容器 rootfs 已经就绪”。

### 4.5 rootfs 组织层

职责：

- 把只读的 RAFS 镜像视图
- 和可写的 snapshot/work 目录
- 组合成最终 overlay rootfs

这一层在 runtime-rs 里表达得更清楚。

---

## 五、Go runtime 视角：Cloud Hypervisor 如何接入 Nydus

## 5.1 `createVirtiofsDaemon()` 是第一关键入口

代码位置：

- `src/runtime/virtcontainers/clh.go`

`cloudHypervisor.createVirtiofsDaemon(sharedPath string)` 会根据 `SharedFS` 类型决定启动哪种 daemon：

- 普通 `virtio-fs` 场景：启动 `virtiofsd`
- `virtio-fs-nydus` 场景：启动 `nydusd`

当 `SharedFS == config.VirtioFSNydus` 时，代码会构造一个 `nydusd` 实例，核心参数包括：

- `path`: `VirtioFSDaemon`
- `sockPath`: virtiofs socket 路径
- `apiSockPath`: nydusd API socket 路径
- `sourcePath`: sharedPath
- `extraArgs`
- `startFn: startInShimNS`

这里最重要的一点是：在 Kata 的抽象里，Nydus 不是完全另一套共享机制，而是被实现成了 **特殊的 virtiofs daemon**。

这解释了为什么配置名是 `virtio-fs-nydus`，而不是一个完全独立的 shared-fs 类型。

## 5.2 为什么 `nydusd` 在 shim netns 中启动

代码位置：

- `src/runtime/virtcontainers/nydusd_linux.go`

`startInShimNS()` 会把 `nydusd` 放到 shim 的 network namespace 中启动。代码注释写得很直接：

- `nydusd` 需要访问宿主机网络

这背后的含义是：

- Nydus 可能需要通过网络访问远端镜像内容
- 因此 daemon 必须位于适合访问宿主网络的位置
- 它不能完全被当作 guest 内自给自足的文件系统逻辑

所以从部署视角看，Nydus 是一个强宿主机侧能力。

## 5.3 `CreateVM()` 阶段做了什么

代码位置：

- `src/runtime/virtcontainers/clh.go`

`CreateVM()` 在 CH 中并不立即创建和启动 VM，而是先把内部结构搭好：

1. 设置 HypervisorConfig
2. 初始化 VM 配置对象 `clh.vmconfig`
3. 配置 kernel、memory、CPU、console、image/initrd 等
4. 初始化 CH API socket
5. 创建 CH API client
6. 构造 `virtiofsDaemon`
7. 处理 initdata

这里与 Nydus 最相关的是第 6 步：

- `clh.virtiofsDaemon, err = clh.createVirtiofsDaemon(...)`

这意味着在 `CreateVM()` 阶段，Kata 已经根据 `SharedFS` 类型决定：

- 这次 VM 的共享文件系统后端是普通 `virtiofsd`
- 还是 `nydusd`

也就是说，Nydus 不是在容器 rootfs 阶段才临时拼上去，而是在 VM 建模阶段就已经进入 hypervisor 配置路径。

## 5.4 `StartVM()` 阶段做了什么

在 `StartVM()` 中，流程是：

1. 创建 VM store 目录
2. 处理 SELinux label
3. 调用 `setupVirtiofsDaemon(ctx)`
4. 启动 Cloud Hypervisor 进程
5. 通过 CH API 完成 `CreateVM + BootVM`

这意味着：

- `nydusd` 是在 VMM 启动前先起来的
- 这样当 VM 真正启动时，virtio-fs 后端已经就绪

这对共享文件系统场景非常关键，因为 guest 启动后会尽快挂载共享目录，不能等 VM 启动后再慢慢补 daemon。

---

## 六、`nydusd` 自身的工作方式

## 6.1 进程形态

代码位置：

- `src/runtime/virtcontainers/nydusd.go`

`nydusd` 在 Kata 中以守护进程方式运行，其命令参数会被构造成：

- `virtiofs`
- `--apisock <api socket>`
- `--sock <virtiofs socket>`
- `--log-level <info/debug>`

因此它同时承担两套职责：

- 作为 virtio-fs 后端，向 guest 暴露共享文件系统
- 作为 Nydus 控制平面，接受 mount/umount API 请求

## 6.2 启动过程

`Start()` 的核心流程如下：

1. 参数和路径校验
2. 启动 daemon
3. 监听 stdout/stderr
4. 轮询等待 API server ready
5. 执行 `setupShareDirFn()`

其中对 CH + Nydus 来说最重要的是第 5 步。

在 `createVirtiofsDaemon()` 中，Kata 会设置：

- `nd.setupShareDirFn = nd.setupPassthroughFS`

因此 `nydusd` 一旦 ready，就会立刻执行 `setupPassthroughFS()`。

## 6.3 `passthrough_fs` 的作用

`setupPassthroughFS()` 会通过 Nydus API 发起一个 mount 请求，类型是：

- `passthrough_fs`

挂载目标是 guest 中的：

- `/containers`

它的作用可以理解为：

- 为 guest 准备一块能通过 virtio-fs 访问的共享目录基座
- 让后续 rootfs、snapshot、辅助目录都能在这个共享空间下组织

这一层不是最终容器 rootfs，而是整个 Nydus 文件系统布局的底座。

## 6.4 `rafs` 挂载的作用

`nydusd.Mount(opt)` 则是另一类操作，它通过 API 发起：

- `rafs`

类型的挂载。

这一步的含义是：

- 将 Nydus 镜像的 RAFS 元数据和配置加载进来
- 在宿主机侧形成一个可访问的只读镜像视图

从抽象上看：

- `passthrough_fs` 解决的是“共享空间怎么进 guest”
- `rafs` 解决的是“镜像内容如何以 Nydus 方式呈现”

两者缺一不可。

---

## 七、agent 侧如何感知 Nydus

## 7.1 guest 共享挂载点会切换到 Nydus 专用目录

代码位置：

- `src/runtime/virtcontainers/kata_agent.go`

在 `setupStorages()` 中，如果 shared fs 是：

- `config.VirtioFS`
- `config.VirtioFSNydus`

都会生成一个 virtio-fs 类型的 `grpc.Storage`。

但当 shared fs 是 `VirtioFSNydus` 时，挂载点不是普通的 `kataGuestSharedDir()`，而是：

- `kataGuestNydusRootDir()`

代码注释已经说明了这组路径关系：

- virtiofs mountpoint: `/run/kata-containers/shared/`
- 普通共享目录：`/run/kata-containers/shared/containers`
- Nydus 镜像目录：`/run/kata-containers/shared/rafs`

这说明在 guest 视角里，Nydus 并不是简单复用普通共享目录，而是有一套专门的目录布局。

## 7.2 与 DAX 的关系

同一段代码还会根据 `VirtioFSCache` 和 `VirtioFSCacheSize` 判断是否给 guest virtio-fs 挂载加上 `dax` 选项。

逻辑是：

- cache 模式不是 `never` / `metadata`
- 且 `VirtioFSCacheSize != 0`
- 才追加 DAX 选项

这意味着在 CH + Nydus 路径下，性能表现还受 virtio-fs cache 策略影响：

- 开 DAX 可能降低 guest 访问共享内容的复制成本
- 但是否启用并不是 Nydus 自动决定的，而是受共享文件系统配置控制

因此，Nydus 性能分析不能只看镜像格式，还必须把 virtio-fs cache / DAX 一起考虑。

---

## 八、runtime-rs 视角：rootfs 是怎么真正组出来的

Go runtime 更偏向“daemon 管理和 hypervisor 接线”，runtime-rs 则把 rootfs 组织模型写得更清楚。

## 8.1 识别 Nydus rootfs 类型

代码位置：

- `src/runtime-rs/crates/resource/src/rootfs/mod.rs`

当 rootfs layer 的 `fs_type` 等于：

- `fuse.nydus-overlayfs`

时，runtime-rs 会走 `NydusRootfs::new(...)`。

这说明对 runtime-rs 来说，Nydus 是一种明确的 rootfs 类型，而不是普通 shared-fs 的附属模式。

## 8.2 解析 Nydus 额外选项

代码位置：

- `src/libs/kata-types/src/mount.rs`

`NydusExtraOptions` 会从 mount options 中解析：

- `extraoption=<base64>`

解码后的核心字段包括：

- `source`
- `config`
- `snapshotdir`
- `fs_version`

它们分别表示：

- RAFS 元数据位置
- Nydus 配置
- 可写快照目录
- Nydus 文件系统版本

这说明 Kata 在 OCI mount 语义之上，增加了一段 Nydus 专用控制信息。

## 8.3 `rafs_mount()` 如何接入 virtio-fs 设备

代码位置：

- `src/runtime-rs/crates/resource/src/share_fs/share_virtio_fs.rs`

`rafs_mount(...)` 的工作不是在 guest 里直接 mount，而是：

1. 构造一个 `ShareFsMountConfig`
2. 指定：
   - `fstype: RAFS`
   - `source: rafs_meta`
   - `mount_point: rafs_mnt`
   - `config`
   - `prefetch_list_path`
3. 再通过 `do_update_device(... DeviceConfig::ShareFsCfg(...))`
   更新 virtio-fs 设备配置

这意味着 runtime-rs 的做法是：

- 把 RAFS 挂载请求作为 shared-fs 设备配置的一部分下发
- 让共享文件系统设备承担镜像只读视图的承载

这比单纯“起个 daemon 再 mount 一把”更明确地体现了它的设备模型。

## 8.4 最终 rootfs 结构

代码位置：

- `src/runtime-rs/crates/resource/src/rootfs/nydus_rootfs.rs`

`NydusRootfs::new(...)` 的主要逻辑是：

1. 获取可选的 `prefetch_file.list`
2. 解析 `NydusExtraOptions`
3. 调用 `rafs_mount(...)` 挂载只读镜像元数据
4. 在共享目录下创建容器 rootfs 目录
5. 将 `snapshot_dir` 通过 `share_rootfs()` 暴露给 guest
6. 组装 overlay 参数：
   - `lowerdir = RAFS lower 层`
   - `upperdir = snapshotdir/fs`
   - `workdir = snapshotdir/work`
7. 生成一个 `Storage`，类型是 overlayfs

因此最终容器看到的 rootfs 不是直接的 RAFS，也不是直接的 virtio-fs 目录，而是：

- 下层：RAFS 只读镜像层
- 上层：snapshot 可写层
- 最终：overlay rootfs

这正是 `Cloud Hypervisor + Nydus` 真正的落地形态。

---

## 九、完整数据流：从镜像元数据到容器 rootfs

把前面的实现串起来，完整数据流可以概括为：

1. 上层把 Nydus 类型 rootfs 信息交给 Kata runtime
2. Kata 识别 shared-fs 为 `virtio-fs-nydus`
3. Cloud Hypervisor 路径选择启动 `nydusd` 而不是普通 `virtiofsd`
4. `nydusd` 在 shim netns 中启动，准备 virtiofs socket 和 API socket
5. `nydusd` 建立 `passthrough_fs`
6. runtime 根据 mount 信息发起 `rafs` 挂载
7. guest 侧通过 virtio-fs 挂载到 Nydus 专用共享目录
8. runtime-rs 或 agent 侧继续把：
   - RAFS lower 层
   - snapshot upper/work 层
   组合成 overlay rootfs
9. 容器最终运行在这个 overlay rootfs 上

这条链路的关键点在于：

- CH 只是共享承载层
- Nydus 负责只读镜像视图
- overlay 负责容器的 POSIX 可写语义

所以这是一个三层模型，而不是单一文件系统。

---

## 十、性能收益来源

## 10.1 避免传统镜像解压与完全展开

最大收益来自避免：

- 传统 OCI 层逐层解压
- 启动前完全准备所有文件
- 大量小文件提前落盘

这会显著减少镜像冷启动的前置耗时。

## 10.2 按需读取镜像内容

Nydus 倾向于让 guest 在真正访问文件时，才去触发底层数据访问。

因此：

- 如果容器启动阶段只访问很小一部分文件
- 就不需要为整个镜像付出完整准备成本

这对大镜像和分层复杂镜像尤其有利。

## 10.3 把只读层与可写层解耦

通过：

- RAFS 提供只读镜像层
- snapshotdir 提供可写层

Kata 能把“镜像内容表达”和“容器写入语义”分开处理。

这比传统完整展开后的 overlay lowerdir 更节省前置准备时间。

## 10.4 可选预取降低首访抖动

runtime-rs 中存在 `prefetch_file.list` 逻辑，说明当前实现支持：

- 在保留懒加载主体模式的同时
- 对已知热点文件提前预热

这有助于降低懒加载常见的“首个请求触发远端拉取”抖动。

## 10.5 virtio-fs + DAX 可能进一步减少 guest 访问开销

当 virtio-fs cache 策略允许时，guest 可以使用 DAX。

这可能带来：

- 更直接的共享文件访问路径
- 降低 guest page cache 和 host 数据路径之间的额外复制

但它是否真正产生收益，取决于：

- cache 模式
- dax cache size
- 工作负载访问模式

因此 DAX 是潜在加速器，不应与 Nydus 本身混为一谈。

---

## 十一、性能代价与约束

## 11.1 路径更长，系统更复杂

相比普通 OCI rootfs，CH + Nydus 的链路更长：

- Kata runtime
- Cloud Hypervisor
- virtio-fs
- nydusd
- RAFS
- overlay

链路更长意味着：

- 调试更复杂
- 故障定位更难
- 某一层的抖动会传播到容器启动体验

## 11.2 首次访问可能出现懒加载抖动

虽然整体准备成本下降了，但首个访问某些文件时，仍可能出现：

- 元数据查询
- 数据拉取
- 页面填充

所以 Nydus 常见的性能特征不是“所有场景都更快”，而是：

- 启动前置成本更低
- 热点访问路径可能需要配合预取

## 11.3 更依赖共享文件系统配置质量

在 CH 场景下，Nydus 的表现高度依赖：

- virtio-fs cache 模式
- DAX 是否启用
- 共享目录组织方式
- nydusd 参数和 API 行为

这意味着性能问题不应只盯着镜像格式本身。

## 11.4 cleanup 仍有不完整之处

runtime-rs 的 `NydusRootfs::cleanup()` 目前仍是未实现状态，只打印 warning。

这说明在主线代码现状下：

- Nydus rootfs 的主路径已经存在
- 但生命周期收尾和资源回收仍有继续完善空间

这类尾部能力虽然不影响主功能存在，但会影响长期稳定性和运维体验。

---

## 十二、当前实现边界与值得验证的问题

## 12.1 Go runtime 与 runtime-rs 的 Nydus 路径并不完全等价

Go runtime 侧更强调：

- daemon 管理
- hypervisor 接线
- agent storage 组织

runtime-rs 侧更强调：

- rootfs 类型建模
- RAFS lower 层接入
- overlay 组装

因此做进一步研究时，需要避免把两条实现路径混成一个统一实现。

## 12.2 CH 承载的是 shared-fs，不是 Nydus 逻辑本身

从实现上看，Cloud Hypervisor 负责的是：

- 把 virtio-fs 后端接进 VM

它不负责：

- RAFS 解析
- Nydus 元数据管理
- snapshotdir 语义

所以如果未来分析性能瓶颈，应先区分问题落在：

- CH 侧共享文件系统
- nydusd
- rootfs 组装
- guest 内 overlay

## 12.3 还需要实测的问题

仅凭源码可以确认能力路径，但还不能确认具体收益大小。后续实测应重点回答：

1. 在 CH 场景下，Nydus 相比普通 virtio-fs rootfs 的冷启动收益有多大
2. cache mode 和 DAX 对首包时延的影响有多大
3. `prefetch_file.list` 能否显著降低应用关键路径抖动
4. 大镜像、深层镜像、小文件密集镜像的收益曲线是否一致

这些都属于“源码分析之后的性能验证题”。

---

## 十三、最终结论

基于当前仓库主线代码现状，可以对 `Cloud Hypervisor + Nydus` 做出以下判断：

### 13.1 这是一个真实存在的主线能力

不是文档宣称，不是接口占位，而是：

- 配置层已接入
- CH 路径已接入
- `nydusd` 已接入
- guest 共享路径已接入
- rootfs 组装逻辑已接入

### 13.2 它优化的是镜像与 rootfs 准备，而不是 VM 冷启动

这点必须与 VM Cache / VM Templating 区分。

### 13.3 它的核心实现模型是“三层组合”

即：

- CH 提供 virtio-fs 承载
- Nydus 提供 RAFS 只读镜像视图
- overlay 提供容器可写 rootfs

### 13.4 它当前是 Cloud Hypervisor 场景下最值得继续深挖的性能方向

因为在当前主线代码里，相比 VM Cache 和 VM Templating：

- Nydus 在 CH 上的实现更完整
- 数据路径更清晰
- 收益来源更明确
- 后续更适合继续做源码级和实验级分析

因此，如果后续继续围绕 `Cloud Hypervisor` 研究 Kata Containers 的性能优化，`Nydus` 应当作为第一优先级。
