# Nydus Snapshotter 第一层：实现了什么功能

## 本层回答的问题

从 containerd snapshotter 的常规构建方式出发，`nydus-snapshotter` 到底实现了哪些核心功能？

这里先不深入调用链细节，只回答一件事：

> 它在 containerd 体系里，究竟扮演了一个什么样的角色？

---

## 一、先看它在 containerd 里的基本身份

`nydus-snapshotter` 的二进制入口是 `containerd-nydus-grpc`，它以 **containerd remote snapshotter / proxy plugin** 的形式运行，并通过 Unix socket 挂到 containerd 的 `proxy_plugins` 上。

从这个身份上看，它首先不是：

- 纯镜像转换工具
- 单纯的下载器
- 单纯的 `nydusd` 启动脚本

而是一个 **能被 containerd 当作 snapshotter 使用的远程快照器插件**。

对应入口代码:

- `nydus-snapshotter/cmd/containerd-nydus-grpc/main.go`
- `nydus-snapshotter/README.md`

---

## 二、它实现了完整的 snapshotter 生命周期接口

从代码上看，`nydus-snapshotter` 并不是只实现了某一个 Prepare 或 Mount 钩子，而是实现了完整的 snapshotter 生命周期接口。

核心逻辑集中在:

- `nydus-snapshotter/snapshot/snapshot.go`

它实现了这些标准能力:

- `Prepare`
- `View`
- `Mounts`
- `Commit`
- `Remove`
- `Stat`
- `Update`
- `Usage`
- `Walk`
- `Close`

这意味着，对 containerd 来说，它首先就是一个“标准 snapshotter”。

但 Nydus 的关键不是“它实现了这些接口”，而是：

> 它在这些标准接口内部，加入了 Nydus 镜像识别、远程 rootfs 实例化、daemon 编排和懒加载接入能力。

---

## 三、它实现的第一个重要功能：镜像类型识别和层分类

普通 overlayfs snapshotter 往往默认每一层都应该被本地 unpack。  
而 `nydus-snapshotter` 不这么假设。

在 `Prepare()` 中，它会根据 snapshot labels 判断当前层属于哪一类:

- Nydus bootstrap layer
- Nydus data blob layer
- 普通 OCI layer
- stargz layer
- tarfs layer
- proxy 模式层

相关代码:

- `nydus-snapshotter/snapshot/process.go`
- `nydus-snapshotter/pkg/label/label.go`

这一步的意义是:

- 决定哪些层走普通 unpack
- 决定哪些层跳过下载/解包
- 决定哪些层需要启动远程挂载

所以它实现的不是“无差别快照管理”，而是：

> 对镜像层做语义识别后，再决定 containerd 该如何消费这些层。

---

## 四、它实现的第二个重要功能：把 Nydus 镜像实例化成可挂载 rootfs

这是 `nydus-snapshotter` 的核心功能。

它不只是识别 Nydus 镜像，还负责把镜像变成容器启动时可以直接使用的 lower layer。

这件事包括:

1. 找到 bootstrap
2. 收集 blob 后端和认证信息
3. 选择 `fs_driver`
4. 启动或复用 `nydusd`
5. 建立 FUSE / EROFS / 代理式 lower layer
6. 返回可供 runtime 使用的 mount slice

关键代码:

- `nydus-snapshotter/snapshot/process.go`
- `nydus-snapshotter/pkg/filesystem/fs.go`
- `nydus-snapshotter/snapshot/snapshot.go`

因此它的核心输出不是“文件数据”，而是：

- 一个已经准备好的 lower layer
- 一组 runtime 可消费的挂载描述

---

## 五、它实现的第三个重要功能：管理 nydusd 生命周期

`nydus-snapshotter` 并不是只在容器启动时“临时调用一下 `nydusd`”。  
它实际上实现了完整的 daemon 编排能力。

包括:

- 创建 dedicated daemon
- 复用 shared daemon
- 生成 daemon 配置
- 持久化 daemon / RAFS 实例状态
- 等待 daemon 进入运行态
- 在 remove / teardown 时回收 daemon 和实例

关键代码:

- `nydus-snapshotter/pkg/filesystem/fs.go`
- `nydus-snapshotter/pkg/manager/manager.go`
- `nydus-snapshotter/pkg/daemon/daemon.go`

因此 `nydus-snapshotter` 不是单纯的 snapshot 元数据存储器，而是一个：

> Nydus 运行时编排器

---

## 六、它实现的第四个重要功能：把远程 lower layer 包装成 containerd 能消费的 mount 结果

对 runtime 来说，最重要的问题不是“镜像内部怎么组织”，而是：

> rootfs 最终怎么 mount？

`nydus-snapshotter` 实现了这一步的适配能力。  
它会按场景返回:

- `bind`
- `overlay`
- `fuse.nydus-overlayfs`
- 附带 `extraoption` 的 overlay mount
- Kata / proxy 特殊 mount

关键代码:

- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/snapshot/mount_option.go`

所以它不仅管理远程文件系统，还负责把它包装成 containerd/shim/runtime 真正能执行的 mount slice。

---

## 七、它实现的第五个重要功能：维护运行时状态、清理、恢复和观测

`nydus-snapshotter` 还是一个长期运行的服务进程，因此它还实现了大量工程化能力:

- 本地 MetaStore / BoltDB 维护 snapshot 状态
- orphan snapshot 目录清理
- cache usage 统计
- sync remove
- daemon 恢复
- placeholder snapshot recovery
- metrics / pprof / system controller
- cgroup 管理
- failover / hot upgrade 支持

关键代码:

- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/pkg/metrics/*`
- `nydus-snapshotter/pkg/system/*`
- `nydus-snapshotter/pkg/manager/*`

这说明它不是一个“请求来了处理一下、处理完就结束”的轻量插件，而是一个有长期状态和恢复机制的运行时服务。

---

## 八、从 containerd 视角总结它的职责

如果用一句话压缩 `nydus-snapshotter` 的功能，可以表述为:

> `nydus-snapshotter` 是 containerd 的 remote snapshotter，它负责识别 Nydus 镜像及相关变体，决定哪些层需要跳过传统 unpack，启动或复用 `nydusd`/EROFS 路径来实例化远程 lower layer，并把最终 mount 结果交给 runtime 使用，同时维护 daemon、cache、恢复和观测能力。

换句话说，它不是“另一个 overlayfs snapshotter”，而是:

- 一个 snapshotter
- 一个 Nydus rootfs 编排器
- 一个 `nydusd` 生命周期控制器
- 一个懒加载运行时接入层

---

## 本层关键代码位置

- `nydus-snapshotter/cmd/containerd-nydus-grpc/main.go`
- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/snapshot/process.go`
- `nydus-snapshotter/pkg/filesystem/fs.go`
- `nydus-snapshotter/pkg/manager/manager.go`
- `nydus-snapshotter/pkg/daemon/daemon.go`

---

## 本层结论

第一层的结论不是“它实现了 snapshotter 接口”这么简单。  
更准确的说法是:

> `nydus-snapshotter` 借助 containerd 的 snapshotter 接口，把 Nydus 镜像的远程挂载、懒加载、daemon 编排和 rootfs 组装能力接进了容器运行时。
