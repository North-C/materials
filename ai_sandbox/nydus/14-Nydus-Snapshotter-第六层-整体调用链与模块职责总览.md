# Nydus Snapshotter 第六层：整体调用链与模块职责总览

## 本层回答的问题

前五层已经分别拆开了:

- `nydus-snapshotter` 做了什么
- containerd 标准调用链怎样被改造
- `fs.Mount()` 如何分叉到 `fusedev` / `fscache` / `proxy`
- mount slice 如何落成 rootfs
- rootfs 如何继续接到懒加载读路径

第六层要做的事情是把这些拆开的链路重新合起来，回答:

> 从整体架构看，`containerd -> snapshotter -> nydusd -> overlayfs -> runtime -> read path` 这条链路到底是怎样分层协作的？

这层的重点不是新增某个局部实现细节，而是形成一张完整的“职责地图”。

---

## 一、先把整条链路压缩成一句话

如果只保留最核心的主线，可以把 Nydus snapshotter 体系压缩成下面这句话:

> `containerd` 负责触发 snapshot 生命周期，`nydus-snapshotter` 负责把 Nydus 镜像实例化成远程 lower layer，runtime 负责把它拼成最终 rootfs，容器进程真正读文件时再通过 `fusedev` 或 `fscache` 进入按需取数路径。

换句话说，这套体系完成的是三件事:

1. **识别镜像并决定处理路径**
2. **把镜像实例化成容器可见 rootfs**
3. **在运行时按需取回真正的数据内容**

---

## 二、整体调用链的六段分层

把整条链路按职责切分，可以分成六段。

### 2.1 第一段：镜像与任务入口层

主要组件:

- `containerd`
- CRI / nerdctl / ctr

这层负责:

- 接收拉镜像、创建容器、启动任务请求
- 调用 snapshotter API
- 将 snapshotter 返回的 mount slice 继续交给 shim/runtime

从架构上看，这一层解决的是:

> 谁来触发一次 rootfs 准备与容器启动流程

---

### 2.2 第二段：快照生命周期编排层

主要组件:

- `nydus-snapshotter`
- snapshot lifecycle: `Prepare / View / Mounts / Commit / Remove`

这层负责:

- 识别镜像层类型
- 判断哪些层走 unpack，哪些层跳过
- 判断是否需要实例化远程 lower layer
- 管理 snapshot 元数据和目录状态

这层解决的问题是:

> containerd 的标准快照调用链，在遇到 Nydus 镜像时该如何改写

---

### 2.3 第三段：远程 lower layer 实例化层

主要组件:

- `Filesystem.Mount()`
- `Manager`
- `Daemon`
- RAFS runtime instance

这层负责:

- 选择 `fs_driver`
- 创建 RAFS 实例
- 生成 daemon 配置
- 启动或复用 `nydusd`
- 挂出 FUSE / EROFS / proxy 路径

这层解决的是:

> 一个“可被懒加载”的 Nydus lower layer 怎样真正被创建出来

---

### 2.4 第四段：rootfs 组装层

主要组件:

- `mountRemote()`
- overlayfs
- `nydus-overlayfs`
- `containerd-shim-*`

这层负责:

- 把 Nydus lower layer 变成 mount slice
- 把 lowerdir / upperdir / workdir 组织成 overlay rootfs
- 必要时透传 `extraoption` 或 Kata volume

这层解决的是:

> Nydus lower layer 怎样无缝接入 containerd 原本的 rootfs 组装模型

---

### 2.5 第五段：文件系统执行层

主要组件:

- `fusedev` 路线中的 `nydusd`
- `fscache` 路线中的内核 EROFS

这层负责:

- 接住容器进程发出的 VFS 读请求
- 解析 inode、目录树和 chunk 映射
- 决定是否命中本地缓存

这层解决的是:

> 容器第一次读文件时，由谁来主导文件系统读语义

---

### 2.6 第六段：后端数据获取与缓存层

主要组件:

- registry / OSS / S3 / local blob source
- blobcache
- fscache / cachefiles

这层负责:

- 在缓存未命中时获取缺失 blob 数据
- 把数据回填本地缓存或页缓存
- 为后续读请求提供命中

这层解决的是:

> 缺失 chunk 从哪里来，以及拿回来后如何被复用

---

## 三、从整体上看各模块分别回答什么问题

如果换一个角度，不按时序切，而是按“模块回答什么问题”来切，可以得到下面这张职责表。

| 模块 | 它回答的问题 | 它不负责什么 |
|------|--------------|--------------|
| `containerd` | 谁来驱动容器生命周期和 snapshot 调用 | 不负责理解 Nydus 文件系统内部格式 |
| `nydus-snapshotter` | 遇到 Nydus 镜像时，snapshot 流程怎么改写 | 不直接处理每一次读请求 |
| `Filesystem.Mount()` | 远程 lower layer 怎么实例化 | 不直接组装最终 overlay rootfs |
| `nydusd` (`fusedev`) | 如何作为用户态文件系统服务读请求 | 不负责 containerd 生命周期调度 |
| 内核 `EROFS` (`fscache`) | 如何在内核中解析 RAFS 元数据并执行读路径 | 不直接负责远端 registry 认证和配置组织 |
| overlayfs / shim / helper | 怎样把 lowerdir / upperdir / workdir 变成最终 rootfs | 不理解 Nydus blob/chunk 语义 |
| blob backend / cache | 数据从哪里来、如何缓存 | 不负责容器 rootfs 组织 |

这张表的价值在于:

- 避免把所有逻辑都混成“都是 Nydus 在做”
- 方便后续继续分析每一层时知道边界在哪

---

## 四、把 `fusedev` 和 `fscache` 放回整体链路里比较

前面各层已经分别讲过 `fusedev` 和 `fscache`。  
在整体视角下，可以把它们压缩成一组对照。

### 4.1 相同点

- 都通过 `nydus-snapshotter` 接入 containerd
- 都以远程 lower layer 的形式进入 overlay rootfs
- 都依赖 bootstrap 进行元数据和 chunk 映射定位
- 都支持按需取数和缓存复用

### 4.2 不同点

`fusedev`:

- lower layer 由 `nydusd` 作为用户态文件系统挂出
- 读请求先进入 FUSE
- `nydusd` 既负责文件系统解释，也负责数据获取

`fscache`:

- lower layer 由内核 EROFS 挂出
- 读请求先进入内核 EROFS
- `nydusd` 不再扮演文件系统本体，而是按需供数服务端

所以整体上可以把二者理解成:

- `fusedev`: 用户态文件系统模型
- `fscache`: 内核文件系统 + 用户态供数模型

---

## 五、整条链路里的两个关键切分线

如果要从整体架构里抓住最重要的两条切分线，可以总结为:

### 5.1 第一条切分线：启动路径 vs 读路径

启动路径解决的是:

- 怎样尽快把 rootfs 挂出来

读路径解决的是:

- 真正访问文件时，怎样按需把数据补齐

Nydus 的价值就在于把这两条路径解耦。

### 5.2 第二条切分线：用户态主导 vs 内核态主导

`fusedev` 与 `fscache` 的本质区别不是都能不能懒加载，而是:

- 由谁主导文件系统执行语义

这也是理解 Nydus 多种挂载路径的最重要架构边界。

---

## 六、把前五层合成一条完整时序

如果把前五层的内容连成完整时序，可以得到:

```text
1. 用户发起容器创建/启动
2. containerd 调用 nydus-snapshotter Prepare
3. snapshotter 识别镜像层类型
4. 对 Nydus 镜像，snapshotter 调用 fs.Mount() 实例化远程 lower layer
5. snapshotter 返回 overlay 或 fuse.nydus-overlayfs mount slice
6. containerd/shim/runtime 组装 rootfs
7. 容器进程启动
8. 应用第一次 open/read 文件
9. fusedev: FUSE -> nydusd -> blobcache/backend
10. 或 fscache: EROFS -> fscache -> nydusd -> backend
11. 数据回填缓存
12. 应用拿到数据
```

这条时序既能解释:

- 为什么 Nydus 启动快
- 为什么它还能支持懒加载
- 为什么 snapshotter 和 `nydusd` 都是必不可少的

---

## 七、为什么这一层对后续分析重要

前五层主要是“拆开看”。  
第六层的作用是“重新拼回去”，因为后续再往下分析时，容易出现两个问题:

- 过度聚焦某个函数，丢掉整条链路的上下文
- 把多个模块的职责混在一起

这一层的整体图景建立后，后续再继续向下分析时，就可以明确:

- 当前分析的是哪一段
- 它依赖上一段提供什么
- 它最终把结果交给下一段什么组件

因此第六层不是补充材料，而是后续继续深入的坐标系。

---

## 本层关键代码与文档位置

- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/snapshot/process.go`
- `nydus-snapshotter/pkg/filesystem/fs.go`
- `nydus-snapshotter/pkg/daemon/daemon.go`
- `nydus-snapshotter/snapshot/mount_option.go`
- `docs/nydus-overlayfs.md`
- `docs/nydus-fscache.md`
- `docs/rafs-and-transport-protocols.md`

---

## 本层结论

第六层的结论可以压缩成一句话:

> Nydus snapshotter 体系本质上是一条分层协作链：`containerd` 驱动生命周期，`nydus-snapshotter` 改写 snapshot 处理路径，`fs.Mount()` 实例化远程 lower layer，runtime 将其组装成 rootfs，而真正的文件内容则在运行时通过 `fusedev` 或 `fscache` 路径按需补齐。
