# Nydus 镜像挂载与懒加载分析报告

## 项目概述

Nydus 是面向容器镜像分发和按需加载场景设计的镜像加速方案。它的关键价值不在于“把镜像换一种格式保存”,而在于把镜像文件系统的 **元数据视图** 和 **文件内容数据** 解耦,从而支持:

- 按需挂载文件系统视图
- 按需下载真正用到的数据块
- 复用数据块与缓存
- 缩短容器启动路径上的镜像准备时间

从运行时视角看,Nydus 的主线问题只有两个:

1. 镜像最终通过什么机制挂载成容器可见的 rootfs
2. 文件真正被读取时,数据块如何触发懒加载并回填

---

## 一、Nydus 镜像的基本对象

Nydus 并不是简单地把 OCI layer 完整解压到本地后再挂载,而是把镜像拆成两类核心对象:

- **bootstrap**: 文件系统元数据,描述目录树、inode、chunk 映射关系
- **data blobs**: 真正的文件内容

因此,容器启动时通常先完成的是“文件系统视图可见”,而不是“所有文件内容都已落盘”。  
当进程真正读取文件时,系统再按需获取对应 chunk,这就是懒加载。

可以把它理解成:

```text
容器启动 = 先挂出文件系统视图
文件读取 = 再按需获取内容数据
```

---

## 二、核心问题: `fs_driver` 到底决定了什么

在 `nydus-snapshotter` 中,`fs_driver` 本质上是一个挂载路径选择器。  
它回答的问题是:

> Nydus 文件系统最终通过什么机制挂到宿主机/容器可见的 rootfs 上?

常见选项包括:

- `fusedev`
- `fscache`
- `blockdev`
- `proxy`

从架构上看,它们可以先分成两大类:

- **FUSE 路线**: `fusedev`
- **EROFS 路线**: `fscache`、`blockdev`

因此,如果你选择使用 EROFS,本质上是在切换整条挂载路径,而不是在 FUSE 上再叠加一个开关。  
也就是说,在同一条实例化路径上:

- `EROFS` 与 `FUSE` 是互斥的
- `fscache` 和 `fusedev` 是不同 `fs_driver`

---

## 三、三种主要挂载/懒加载路径

### 3.1 `fusedev`: FUSE 挂载路径

这是最经典、也最容易理解的 Nydus 路线。

基本流程:

1. snapshotter 准备 bootstrap 和后端配置
2. 启动 `nydusd`
3. `nydusd` 在宿主机创建 FUSE mountpoint
4. overlayfs 将该挂载点作为 lower layer 使用
5. 进程读文件时,内核通过 `/dev/fuse` 将请求发给 `nydusd`
6. `nydusd` 根据 bootstrap 定位缺失 chunk,必要时从 registry 拉取 blob 数据

这条路径的特征是:

- 文件系统语义主要在用户态 `nydusd`
- 懒加载流程主要由 `nydusd` 驱动
- 常见缓存类型是 `blobcache`

可以理解为:

```text
应用读文件 -> 内核 FUSE -> nydusd -> bootstrap/data blobs
```

### 3.2 `fscache`: EROFS + 懒加载路径

`fscache` 代表的是另一条完全不同的挂载链路。  
它不再通过 FUSE 暴露文件系统,而是走内核 EROFS。

基本流程:

1. snapshotter 选择 `fs_driver = "fscache"`
2. `nydusd` 不再创建 FUSE mountpoint
3. 宿主机通过内核 EROFS 挂载 RAFS 文件系统
4. 应用读文件时,内核 EROFS 解析 bootstrap 中的元数据
5. 如果目标 chunk 尚未命中,内核通过 `fscache` 向用户态请求数据
6. `nydusd` 的 fscache service 拉取缺失数据并回填给内核缓存

这条路径的特征是:

- 文件系统语义更多由内核 EROFS 实现
- `nydusd` 更像数据提供者,而不是 FUSE 文件系统本体
- 缓存核心由内核 `fscache` 管理

可以理解为:

```text
应用读文件 -> 内核 EROFS -> 内核 fscache -> nydusd fscache service -> 远端 blobs
```

### 3.3 `blockdev`: EROFS + 块设备路径

`blockdev` 同样属于 EROFS 阵营,但它和 `fscache` 的目标不完全一样。

关键区别是:

- `fscache` 关注“文件读取时按需回填数据”
- `blockdev` 关注“把处理后的镜像组织成块设备,再由 EROFS 直接挂载”

因此,`blockdev`:

- 不属于 FUSE 路线
- 也不等价于 `fscache`
- 而是另一条 EROFS 后端路径

它更接近:

```text
应用读文件 -> 内核 EROFS -> block device backend
```

---

## 四、对比图: `fusedev` / `fscache` / `blockdev`

![Nydus fs_driver 挂载与懒加载路径对比图](diagrams/e2b-architecture/themes/solarized-light/nydus-fs-drivers-comparison.svg)

这张图可以帮助快速抓住差别:

- `fusedev` 是用户态文件系统路径
- `fscache` 是内核 EROFS + 内核缓存协同路径
- `blockdev` 是 EROFS + 块设备路径

---

## 五、`shared mode` 不是镜像格式,而是 daemon 复用策略

`shared mode` 很容易被误解成镜像挂载格式的一部分,其实不是。  
它回答的问题是:

> `nydusd` 进程是一个挂载实例对应一个,还是多个实例共享一个?

可以简单理解为:

- **dedicated**: 一个挂载实例对应一个 `nydusd`
- **shared**: 多个挂载实例复用一个 `nydusd`

前面提到 `fscache` 只支持 `shared` 模式,意思是:

- `fscache` 更接近一个共享的数据服务端
- 它不是“每个挂载点单独起一个 FUSE daemon”的工作方式

所以要分清:

- `fs_driver` 决定“怎么挂载”
- `shared/dedicated` 决定“`nydusd` 怎么复用”

---

## 六、`proxy` 应该如何理解

`proxy` 是另一个容易混淆的术语。  
它不属于上面三条标准本地挂载主线中的任何一条。

从 `nydus-snapshotter` 的说明看:

- `proxy` 与 `blockdev` 一样,不需要 `nydusd` 配置
- 它更接近代理式/转发式文件系统接入路径

因此在概念上可以把它理解为:

- **不是 FUSE**
- **也不是典型的本地 EROFS + fscache**
- 而是一条特殊的代理式路径

所以在理解顺序上,建议不要先拿 `proxy` 去类比 `fusedev` / `fscache`,而是先把前面三条主线搞清楚,再把它视作特殊模式。

---

## 七、概念速查表

| 术语 | 回答的问题 | 角色 |
|-----|-----------|------|
| `fs_driver` | 文件系统怎么挂出来 | 挂载路径选择器 |
| `fusedev` | 用什么挂载 | FUSE 路线 |
| `fscache` | 用什么挂载 | EROFS + fscache 路线 |
| `blockdev` | 用什么挂载 | EROFS + 块设备路线 |
| `proxy` | 用什么接入 | 代理式特殊路径 |
| `shared mode` | `nydusd` 怎么复用 | 进程复用策略 |

---

## 八、结论

如果把这几个概念压缩成一句话:

- 想走经典 Nydus 用户态文件系统路径,选 `fusedev`
- 想走内核 EROFS 的懒加载路径,选 `fscache`
- 想走块设备式 EROFS,选 `blockdev`
- `shared/dedicated` 决定的是 daemon 复用方式,不是镜像格式

所以当你问“使用 EROFS 是否和 FUSE 配置互斥”时,更准确的表达应该是:

> 在 Nydus 的挂载路径选择上,`fusedev` 与 `fscache/blockdev` 属于不同 `fs_driver`,因此是互斥选择,而不是叠加配置。

从设计视角看,这也是理解 Nydus 镜像挂载与懒加载流程的最关键切分线。
