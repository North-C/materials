# Nydus Snapshotter 第三层：`fs.Mount()` 与 `fs_driver` 分叉

## 本层回答的问题

当 `Prepare()` 决定容器需要走 Nydus 远程 rootfs 路径后，`fs.Mount()` 内部到底做了什么？

更准确地说，这一层要回答:

> `fusedev`、`fscache`、`proxy` 这些 `fs_driver`，分别是怎样把“一个 bootstrap + 一组 blobs”变成真正的 lower layer 的？

---

## 一、`fs.Mount()` 的本质角色

`fs.Mount()` 的入口在:

- `nydus-snapshotter/pkg/filesystem/fs.go`

它不是简单执行一次 mount syscall，而是一个完整的 **远程文件系统实例化流程**。

它的职责包括:

1. 决定本次实例化实际走哪个 `fs_driver`
2. 创建 RAFS 运行时实例
3. 生成 daemon 配置
4. 启动或复用 daemon
5. 调用对应路径完成 lower layer 建立
6. 把实例状态持久化到 snapshotter 自己的 store

因此 `fs.Mount()` 更准确的理解是:

> Nydus lower layer 的实例化编排入口

---

## 二、第一步：确定驱动路径和 daemon 组织方式

`fs.Mount()` 一开始会先判断:

- 当前是否启用了 `fusedev`
- 当前是否启用了 `fscache`
- 当前是否要改走 `blockdev`
- 当前是否处于 `proxy` 模式

同时它还会判断 daemon 组织方式:

- `fscache` 默认走 shared daemon
- `fusedev + shared mode` 走 shared daemon
- 其他情况通常使用 dedicated daemon

这一步的意义是:

- 决定 mountpoint 放在哪里
- 决定一个实例是否复用已有 `nydusd`
- 决定后续应该调用 FUSE 挂载还是 EROFS 挂载

因此在真正挂载前，`fs.Mount()` 先完成的是:

> 运行模式决策

---

## 三、第二步：创建 RAFS 运行时实例

代码中会创建:

- `rafs := NewRafs(snapshotID, imageID, fsDriver)`

这个 RAFS 对象并不是“静态镜像文件”，而是这次运行中的文件系统实例。

它后续会承载这些运行态信息:

- `snapshotID`
- `imageID`
- `fs_driver`
- `mountpoint`
- `daemonID`
- annotations
- underlying cache files

因此从这里开始，snapshotter 已经不再只是处理 layer，而是在维护一个:

> 可运行的 Nydus 文件系统实例

---

## 四、第三步：为 `fusedev` / `fscache` 准备 daemon 配置

对 `fusedev` 和 `fscache` 来说，`fs.Mount()` 有一套共同准备步骤:

1. 找 bootstrap 文件
2. 获取 cache 目录
3. 把 `*.blob.meta` 复制或硬链接到 cache 目录
4. 获取 shared daemon 或创建 dedicated daemon
5. 生成本实例对应的 daemon 配置
6. 将配置写入磁盘
7. 把 RAFS instance 关联到 daemon
8. 做 bootstrap 签名校验

这一套动作说明:

> Nydus 的 mount 不是“临时拼几个参数调用一下”，而是先把一个完整的运行时配置对象准备好，再让 daemon 或内核按这份配置完成实例化。

相关代码:

- `nydus-snapshotter/pkg/filesystem/fs.go`

---

## 五、`fusedev` 分支：由 `nydusd` 自己挂出用户态文件系统

对 `fusedev` 来说，真正的 lower layer 是通过 `nydusd` 自己挂出来的。

共享模式下，`fs.mountRemote()` 会设置好 mountpoint 后调用:

- `d.SharedMount(r)`

随后在 `SharedMount()` 中，`fusedev` 会走:

- `sharedFusedevMount()`

它的动作很直接:

1. 读取当前实例对应的配置文件
2. 找到 bootstrap
3. 调用 `client.Mount(mountpoint, bootstrap, config)`

也就是说，真正产生 lower layer 的动作是:

> 由 snapshotter 通过 daemon API，请 `nydusd` 把 RAFS 实例挂成一个 FUSE 文件系统。

所以这条路径可以压缩成:

```text
snapshotter -> nydusd Mount API -> FUSE mountpoint -> overlay lowerdir
```

在这条路径上:

- 文件系统解释权在用户态 `nydusd`
- 懒加载控制也主要由 `nydusd` 驱动

---

## 六、`fscache` 分支：由内核 EROFS 挂出文件系统，`nydusd` 提供数据

`fscache` 路线的 lower layer 形成方式完全不同。

共享模式下，`SharedMount()` 会走:

- `sharedErofsMount()`

它的动作是:

1. 创建 fscache workdir
2. 读取 fscache daemon 配置
3. 调用 `client.BindBlob(config)`，让 `nydusd` 具备按需供数能力
4. 生成 `fscacheID`
5. 调用 `erofs.Mount(domainID, fscacheID, mountpoint)`

而 `erofs.Mount()` 最终执行的是:

- `mount("erofs", ...)`

因此这条路径的真实链路是:

```text
snapshotter -> nydusd BindBlob -> kernel mount erofs -> overlay lowerdir
```

这说明在 `fscache` 下:

- lower layer 不是 `nydusd` 自己挂出来的
- lower layer 是内核 EROFS 挂出来的
- `nydusd` 的角色退化成 fscache 数据服务端

所以 `fscache` 的本质不是“另一种 FUSE 参数”，而是:

> 把文件系统主体交给内核，把数据供给交给用户态

---

## 七、`proxy` 分支：本地不真正挂载，只做占位和透传

`proxy` 分支非常轻。

它不会像 `fusedev` / `fscache` 那样:

- 启动 `nydusd`
- 挂出 FUSE 文件系统
- 挂出 EROFS 文件系统

它主要做的是:

- 记录 proxy mode annotation
- 记录 CRI 层 digest
- 设置一个 snapshot 本地目录下的占位 mountpoint

这意味着 `proxy` 更接近:

> 为后续外部 agent / guest runtime / 代理式拉取机制保留状态和上下文

而不是标准意义上的“本机 lower layer 挂载路径”。

---

## 八、shared / dedicated 影响的是实例组织方式，而不是文件系统语义

`shared` 与 `dedicated` 这一层也很容易混淆。

实际上它们主要决定的是:

- mountpoint 挂在哪个目录
- `nydusd` 是单实例复用还是一挂载一实例
- RAFS instance 与 daemon 的关联关系

但它们并不改变这条根本分叉:

- `fusedev`：用户态文件系统主导
- `fscache`：内核文件系统主导

因此 shared/dedicated 是:

> 实例组织策略

不是:

> 文件系统语义分叉点

---

## 九、`WaitUntilReady()` 说明 ready 的含义是“运行态就绪”

在 `fs.Mount()` 之后，snapshotter 还会调用 `WaitUntilReady()`。

它不是只检查 mountpoint 是否存在，而是会:

1. 找到 RAFS instance 对应的 daemon
2. 等待 daemon 状态进入 `RUNNING`
3. 获取 cache metrics
4. 回填 `UnderlyingFiles`
5. 更新 RAFS instance 存储记录

因此 snapshotter 定义的 ready 不是“mount syscall 成功”，而是:

> 这个 lower layer 背后的 runtime、cache、实例元信息都已经稳定可用

---

## 本层关键代码位置

- `nydus-snapshotter/pkg/filesystem/fs.go`
- `nydus-snapshotter/pkg/daemon/daemon.go`
- `nydus-snapshotter/pkg/utils/erofs/erofs.go`

---

## 本层结论

第三层的关键结论是:

> `fs.Mount()` 是 Nydus lower layer 的实例化核心。它根据 `fs_driver` 选择 FUSE、EROFS 或 proxy 等不同路径，并把 RAFS 实例、daemon 配置、挂载点和运行态状态组织成一个真正可被 overlay/rootfs 使用的 lower layer。
