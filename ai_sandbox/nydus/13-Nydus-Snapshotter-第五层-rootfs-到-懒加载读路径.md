# Nydus Snapshotter 第五层：从 rootfs 到懒加载读路径

## 本层回答的问题

容器已经启动、rootfs 已经可见之后，第一次 `open/read` 是如何真正进入 Nydus 懒加载路径的？

这一层要把“启动路径”和“读路径”真正接起来，回答:

> Nydus lower layer 挂好之后，请求怎样沿着 FUSE 或 EROFS/fscache 走到后端 blob 数据？

---

## 一、rootfs 可见不等于数据已经完整就绪

在 Nydus 模式下，容器启动完成时，通常已经具备:

- 可解析的 bootstrap 元数据
- 可被 overlay/rootfs 使用的 lower layer

但这并不意味着所有文件内容都已经落到本地。

这也是 Nydus 冷启动快的核心原因:

- 启动阶段优先保证元数据视图可用
- 数据内容只在真正访问时按需获取

从运行时视角看，这一步的本质是:

> rootfs ready 只是“文件系统入口 ready”，不是“所有 chunk 已经 ready”。

---

## 二、懒加载的共同逻辑

无论是 `fusedev` 还是 `fscache`，懒加载都遵循同一个基础过程:

1. 应用发起 `open/read`
2. 文件系统层根据 inode 和 offset 查找 chunk 映射
3. 检查本地缓存是否命中
4. 未命中则按 blob/chunk 范围请求后端数据
5. 数据回填本地缓存或内核页缓存
6. 将结果返回给应用

其中 bootstrap 的作用并不是提供文件内容，而是提供:

- 目录树
- inode
- chunk 映射
- blob 定位关系

因此在懒加载路径里，bootstrap 本质上是:

> 读路径的索引入口

---

## 三、`fusedev` 路径：读请求先进入 FUSE，再进 `nydusd`

在 `fusedev` 路线里，lower layer 是一个由 `nydusd` 挂出的 FUSE 文件系统。

因此容器进程第一次读文件时，链路大致是:

```text
container process
-> kernel VFS
-> FUSE
-> nydusd
-> RAFS metadata lookup
-> blobcache / backend
-> return data
```

这条路径成立的原因是:

- snapshotter 在 `fusedev` 下调用了 `nydusd` 的 `Mount()` API
- `nydusd` 自己成为这个 lower layer 的文件系统执行主体

相关代码:

- `nydus-snapshotter/pkg/daemon/client.go`
- `src/bin/nydusd/api_server_glue.rs`

所以在 `fusedev` 中，`nydusd` 同时负责:

- 文件系统语义解释
- inode/chunk 定位
- 后端数据获取
- blobcache 缓存命中与回填

这是一条典型的:

> 用户态主导的懒加载读路径

---

## 四、`blobcache` 在 `fusedev` 路径中的作用

`fusedev` 中最常见的本地缓存形态是 `blobcache`。

它的作用是:

- 保存已经拉取过的 blob 数据
- 避免重复远端读取
- 为后续读请求提供更快命中

因此在 `fusedev` 路线里，可以把 `blobcache` 理解为:

> `nydusd` 在用户态控制下维护的远端 blob 本地缓存层

Nydus 文档里也明确指出，blobcache 会把已获取的数据保存在工作目录里，不会反复从远端获取。

相关文档:

- `docs/nydus-design.md`

---

## 五、`fscache` 路径：读请求先进入内核 EROFS，再按需让 `nydusd` 供数

`fscache` 路线与 `fusedev` 的根本差异在于:

- lower layer 不是 FUSE
- lower layer 是内核 EROFS mountpoint

因此第一次读文件时，请求路径变成:

```text
container process
-> kernel VFS
-> kernel EROFS
-> lookup inode/chunk in bootstrap
-> check fscache/cachefiles
-> if miss, request data from nydusd
-> fill cache
-> return data
```

在这条链路里，内核 EROFS 负责:

- 文件系统元数据解析
- inode 查找
- chunk 映射定位
- 页缓存协同

而 `nydusd` 的角色则变成:

> 当内核发现目标数据不在本地缓存时，作为按需数据提供者把 blob 数据补回来。

---

## 六、`fscache` 路线里的 `/dev/cachefiles` 协作机制

Nydus 文档对这条链路描述得很清楚。

在 `fscache` 模式下，`nydusd` 会先注册成 fscache 数据提供者:

- 打开 `/dev/cachefiles`
- 绑定 ondemand 模式

然后 EROFS 挂载完成后，内核在缓存未命中时会通过 cachefiles 接口向 `nydusd` 发起请求。

相关文档:

- `docs/nydus-fscache.md`
- `docs/rafs-and-transport-protocols.md`

这说明 `BindBlob()` 的含义并不是“挂文件系统”，而是:

> 把 `nydusd` 置于一个可响应内核按需读缺页请求的服务端状态。

---

## 七、`fusedev` 和 `fscache` 的真正分界线

从懒加载角度看，二者都支持:

- 首次访问按需取数
- 本地缓存命中优化
- 避免启动前完整拉取全量镜像数据

但真正的分界线不是“谁支持懒加载”，而是:

> 谁主导文件系统读路径

### 7.1 `fusedev`

- 请求先进入 FUSE
- `nydusd` 负责文件系统语义
- `nydusd` 负责数据获取和缓存控制

### 7.2 `fscache`

- 请求先进入内核 EROFS
- 内核负责文件系统语义
- `nydusd` 负责按需数据供应

因此：

- `fusedev` 是“用户态文件系统 + 懒加载”
- `fscache` 是“内核文件系统 + 用户态供数”

---

## 八、为什么 snapshotter 还要关心 cache metrics

虽然 snapshotter 不直接处理每一次 `read()`，但它会在实例 ready 后通过 daemon API 获取 cache metrics，并把 `UnderlyingFiles` 记录回 RAFS instance。

相关代码:

- `nydus-snapshotter/pkg/filesystem/fs.go`
- `nydus-snapshotter/pkg/daemon/client.go`

这一步的意义在于:

- 让 snapshotter 知道该实例实际用了哪些底层缓存文件
- 为 cache usage 统计提供依据
- 为 remove / cleanup 时避免误删仍在使用的缓存对象

因此 snapshotter 虽然不主导读请求，但它维护了:

> 懒加载运行态与缓存对象之间的管理视图

---

## 九、把启动路径和读路径接成完整闭环

把前几层的分析串起来，可以得到完整闭环:

```text
containerd Prepare
-> snapshotter 识别 Nydus 镜像
-> fs.Mount() 实例化 lower layer
-> mountRemote() 返回 overlay mount slice
-> runtime 启动容器
-> process open/read
-> fusedev: FUSE -> nydusd -> blobcache/backend
   或
-> fscache: EROFS -> fscache -> nydusd -> backend
-> 数据回填
-> 应用读到内容
```

这说明:

- 启动路径解决的是“先把文件系统入口挂出来”
- 读路径解决的是“真正读文件时如何按需补齐数据”

两者共同构成 Nydus 的整体价值闭环。

---

## 本层关键代码位置

- `nydus-snapshotter/pkg/daemon/client.go`
- `nydus-snapshotter/pkg/filesystem/fs.go`
- `src/bin/nydusd/api_server_glue.rs`
- `docs/nydus-fscache.md`
- `docs/rafs-and-transport-protocols.md`
- `docs/nydus-design.md`

---

## 本层结论

第五层的关键结论是:

> `nydus-snapshotter` 负责把“可懒加载的文件系统入口”接入 rootfs；真正的懒加载发生在容器启动之后的读路径里，`fusedev` 由 `nydusd` 主导文件系统语义和数据获取，`fscache` 由内核 EROFS 主导文件系统语义、由 `nydusd` 负责缺失数据供应。
