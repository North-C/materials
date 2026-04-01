# Nydus Snapshotter 第七层：`nydusd` 的内部职责边界

## 本层回答的问题

前六层里，`nydusd` 已经多次出现:

- 它会被 `nydus-snapshotter` 启动或复用
- 它在 `fusedev` 路径里负责挂出文件系统
- 它在 `fscache` 路径里负责按需供数
- 它还暴露管理 API、指标和升级能力

但如果不单独把它拎出来分析，就很容易产生一个模糊印象:

> 好像所有运行时事情都是 `nydusd` 在做

这一层的目标，就是把 `nydusd` 从整条链路里单独抽离出来，明确它和:

- `nydus-snapshotter`
- 内核 FUSE / EROFS
- blob backend / cache
- runtime / shim

之间的职责边界。

---

## 一、先给 `nydusd` 一个准确定位

从 `nydusd` 的 CLI 和 `nydus-service` 文档看，它本质上不是单一“挂载进程”，而是一个 **多服务运行时容器**。

它可以承载:

- fuse service
- virtio-fs service
- fscache service
- blobcache service

相关位置:

- `src/bin/nydusd/main.rs`
- `service/README.md`

所以更准确的描述应该是:

> `nydusd` 是 Nydus 的运行时执行面，用于承载不同文件系统接入方式和数据服务能力。

它并不是简单等于:

- “FUSE daemon”
- “下载器”
- “缓存进程”

而是这些能力的统一宿主。

---

## 二、`nydusd` 不负责什么

在分析它的职责前，先把它**不负责**的事情说清楚。

`nydusd` 通常不负责:

- 决定 containerd 何时调用 snapshotter
- 识别镜像 layer 是 bootstrap 还是 data blob
- 决定某个 snapshot 该走 `Prepare` 还是 `Commit`
- 决定 overlay rootfs 何时被 runtime 组装
- 维护 containerd 那套 snapshot 元数据存储语义

这些事情属于:

- `containerd`
- `nydus-snapshotter`
- shim / runtime

所以从边界上看:

> `nydusd` 不是容器生命周期调度器，而是被外部调度起来的运行时服务执行器。

---

## 三、`nydusd` 的第一类职责：承载文件系统服务

这是 `nydusd` 最直观、也最核心的职责。

从 `service/README.md` 和 `service/src/fusedev.rs` 可以看出，`nydusd` 可以承载面向文件系统入口的服务。

### 3.1 在 `fusedev` 路径里

它负责:

- 创建 FUSE server
- 将 RAFS backend 挂接到 VFS
- 从 `/dev/fuse` 接收请求
- 调度工作线程处理请求

相关位置:

- `service/src/fusedev.rs`
- `docs/rafs-and-transport-protocols.md`

在这个模式下，`nydusd` 的角色可以概括为:

> 用户态文件系统本体

### 3.2 在 virtio-fs 路径里

它仍然承载文件系统服务，但请求入口不再是 `/dev/fuse`，而是 vhost-user / virtqueue。

因此:

- 文件系统核心语义仍是同一套 RAFS backend
- 区别只是传输协议不同

这说明 `nydusd` 的一个重要内部特征是:

> 它把“文件系统语义”和“请求传输通道”做了分离

---

## 四、`nydusd` 的第二类职责：承载 fscache 数据服务

在 `fscache` 路径里，`nydusd` 的角色发生明显变化。

它不再是文件系统本体，而是一个:

> 内核 EROFS 的按需数据提供者

文档和代码都说明了这点:

- `docs/nydus-fscache.md`
- `docs/rafs-and-transport-protocols.md`
- `service/src/fs_cache.rs`

在这个模式下，`nydusd` 主要负责:

1. 打开 `/dev/cachefiles`
2. 绑定 ondemand 模式
3. 建立 blob 对象命名空间
4. 接收来自 fscache 的 OPEN / READ / CLOSE 等请求
5. 从后端读取数据并写回缓存文件

这意味着在 `fscache` 模式里，`nydusd` 已经不再负责:

- 文件名解析
- inode 查找
- 目录树遍历

这些工作都转移给了:

- 内核 EROFS

所以这一路径中 `nydusd` 的定位更准确地说是:

> 面向 fscache 的 blob 数据服务端

---

## 五、`nydusd` 的第三类职责：承载 blobcache 与后端访问能力

无论是 `fusedev` 还是 `fscache`，只要需要从远端拉数据，`nydusd` 就必须接住下面这部分能力:

- 访问 registry / OSS / S3 / localfs 等 backend
- 定位 blob/chunk
- 拉取数据
- 回填 blobcache 或协同 fscache 缓存
- 提供 backend / blobcache metrics

这说明 `nydusd` 的另一个关键职责不是“挂载”，而是:

> 把 RAFS 索引所指向的远端数据，变成可被本地文件系统读请求消费的数据块。

相关线索:

- `service/README.md`
- `docs/nydus-design.md`
- `src/bin/nydusd/api_server_glue.rs`

因此从内部结构上看，`nydusd` 至少同时承载两层能力:

- 文件系统服务能力
- 存储后端数据服务能力

---

## 六、`nydusd` 的第四类职责：暴露管理与控制 API

`nydusd` 不是一个只会阻塞处理 I/O 的黑盒进程。  
它还暴露了完整的管理 API。

从 `src/bin/nydusd/api_server_glue.rs` 可以看到，它至少支持这些请求类型:

- `ConfigureDaemon`
- `GetDaemonInfo`
- `Start`
- `Mount`
- `Remount`
- `Umount`
- `ExportBackendMetrics`
- `ExportBlobcacheMetrics`
- `GetConfig`
- `UpdateConfig`
- `CreateBlobObject`
- `DeleteBlobObject`
- `DeleteBlobFile`

这说明 `nydusd` 还承担:

> 可编排、可观测、可控制的服务接口层

也正因为有这一层，`nydus-snapshotter` 才能通过 daemon client 去做:

- `Mount()`
- `BindBlob()`
- `GetCacheMetrics()`
- hot upgrade / failover

---

## 七、`nydusd` 的第五类职责：承载状态迁移、升级和接管能力

在 `nydus-failover-upgrade.md` 以及相关代码里可以看出，`nydusd` 还支持:

- failover
- hot upgrade
- takeover / restore

这说明 `nydusd` 并不是一个“死了就重新拉起即可”的无状态 worker。  
它内部保存着一部分重要运行态，例如:

- FUSE 连接相关状态
- fscache 文件句柄和对象状态
- backend filesystem state
- 挂载实例状态

因此在高可用和升级场景里，`nydusd` 还承担:

> 运行态接管与恢复载体

这也是为什么 snapshotter 不只是用 `exec.Command` 启动一个进程，而是把它作为受控 daemon 管理。

---

## 八、`nydusd` 和 `nydus-snapshotter` 的边界

这组边界最容易混。

### 8.1 `nydus-snapshotter` 负责

- 理解 containerd snapshot 生命周期
- 识别镜像层类型
- 决定实例化路径
- 生成 daemon 配置
- 启动 / 复用 / 回收 `nydusd`
- 返回给 containerd 可用的 mount slice

### 8.2 `nydusd` 负责

- 按指定配置运行具体文件系统服务
- 承担 FUSE / virtio-fs / fscache 相关执行逻辑
- 访问 blob backend
- 提供缓存、指标和管理 API

所以两者的边界可以压缩成一句话:

> `nydus-snapshotter` 决定“何时、以什么方式运行 Nydus”，`nydusd` 负责“把这种运行方式真正执行出来”。

---

## 九、`nydusd` 和内核的边界

这组边界在 `fusedev` 和 `fscache` 两种模式下不同。

### 9.1 `fusedev`

内核负责:

- VFS 层入口
- FUSE 传输机制

`nydusd` 负责:

- 文件系统语义
- 元数据解析
- chunk 定位
- 数据获取

### 9.2 `fscache`

内核负责:

- EROFS 文件系统语义
- inode/目录解析
- 页缓存与 fscache 协同

`nydusd` 负责:

- 按需提供缺失 blob 数据
- 管理 fscache 侧 blob 对象

因此 `nydusd` 和内核的边界不是固定的，而是随 `fs_driver` 改变。

这也说明:

> `nydusd` 并不是永远都在做“同一种文件系统工作”，它的职责会随着接入路径发生收缩或扩张。

---

## 十、`nydusd` 和后端存储的边界

`nydusd` 虽然负责访问远端 blob 数据，但它通常不负责:

- 定义镜像仓库协议本身
- 定义对象存储协议本身
- 定义 container registry 分发协议本身

它做的是:

- 读取自身配置
- 用统一的数据访问层连接 backend
- 根据 RAFS 元数据需要去拉取指定 blob/chunk 范围

所以 `nydusd` 不是外部存储系统本身，而是:

> 一个面向文件系统懒加载场景的数据访问适配层

---

## 十一、从整体角度看 `nydusd` 的真正角色

如果把前面的职责压缩成一组更抽象的定义，可以这样理解 `nydusd`:

### 11.1 它是文件系统服务宿主

在 `fusedev` / virtio-fs 模式下，它承载文件系统服务本体。

### 11.2 它是数据服务宿主

在 `fscache` 模式下，它承载按需 blob 数据服务。

### 11.3 它是运行时控制面暴露者

它提供 mount、metrics、config、upgrade 等可编排接口。

### 11.4 它是运行态状态的持有者

它承载了需要被接管、恢复和升级的运行时状态。

因此，如果只用一句话描述 `nydusd`，最合适的说法是:

> `nydusd` 是 Nydus 的运行时执行宿主，根据不同接入路径承载文件系统服务、数据服务、管理接口和运行态状态。

---

## 本层关键代码与文档位置

- `src/bin/nydusd/main.rs`
- `src/bin/nydusd/api_server_glue.rs`
- `service/README.md`
- `service/src/fusedev.rs`
- `service/src/fs_cache.rs`
- `docs/nydus-fscache.md`
- `docs/rafs-and-transport-protocols.md`
- `docs/nydus-failover-upgrade.md`

---

## 本层结论

第七层的结论是:

> `nydusd` 不是一个单一职责进程，而是 Nydus 的运行时执行宿主。在 `fusedev` 路径里它是用户态文件系统本体，在 `fscache` 路径里它是内核 EROFS 的数据提供者，同时它还承载 blob 后端访问、缓存服务、管理 API 以及升级接管等运行态能力。
