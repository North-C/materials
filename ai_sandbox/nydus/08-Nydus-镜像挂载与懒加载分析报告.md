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

![Nydus fs_driver 挂载与懒加载路径对比图](docs/images/nydus-fs-drivers-comparison.svg)

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

## 七、从镜像加载到容器启动: 主流程展开

在进入文字展开前,可以先看一张把“镜像加载、挂载实例化、容器启动、首次读文件、懒加载回填”串起来的总图:

![Nydus 镜像加载、容器启动与懒加载总流程图](docs/images/nydus-image-startup-lazyload-flow.svg)

这张图想表达的不是某个单点实现细节,而是整条运行链路的职责切分:

- `containerd` 负责把镜像引用变成一次容器启动任务
- `nydus-snapshotter` 负责把 Nydus 镜像准备成可挂载对象
- `fs_driver` 决定走 FUSE 还是 EROFS 路线
- overlayfs 负责把 lower layer 接成最终 rootfs
- 文件首次读取时再通过 bootstrap 的 chunk 映射触发按需取数

如果把这张图的阅读顺序进一步压缩,可以理解成:

```text
先准备可挂载的元数据视图 -> 再实例化 rootfs -> 最后在读路径上按需补齐数据
```

前面的章节回答了“挂载路径怎么分”。  
但如果从容器运行时的整体视角看,还需要回答另一个更实际的问题:

> 一个 Nydus 镜像,到底是怎样从“远端镜像”变成“容器里可见的 rootfs”的?

这个过程可以拆成两个阶段:

1. **镜像准备阶段**: 把 bootstrap、blob 定位信息和挂载参数准备好
2. **rootfs 实例化阶段**: 把 Nydus 文件系统真正接到容器 rootfs 上

以 `containerd + nydus-snapshotter` 为例,主流程可以概括为:

```text
镜像引用 -> containerd 解析 manifest -> snapshotter 准备 Nydus 元数据
-> 启动/复用 nydusd -> 建立 FUSE 或 EROFS 挂载
-> overlayfs 组织 rootfs -> runtime 启动容器进程
```

### 7.1 镜像准备阶段在做什么

这一阶段的重点不是“把整张镜像拉到本地”,而是“把足够支撑挂载的信息准备齐”。

核心动作包括:

1. containerd 根据镜像引用拉取 manifest 和配置
2. `nydus-snapshotter` 识别这是 Nydus 镜像,而不是普通 OCI 解压路径
3. snapshotter 提取或定位 bootstrap
4. snapshotter 收集 blobs 的后端位置、认证信息、缓存参数
5. snapshotter 根据 `fs_driver` 决定后续要走 FUSE 还是 EROFS 路线

这里最关键的点是:

- **bootstrap 决定文件系统“长什么样”**
- **blob 定位信息决定文件内容“去哪里拿”**
- **fs_driver 决定文件系统“用什么方式挂出来”**

所以在镜像准备阶段,系统真正准备的是:

- 一个可被挂载的元数据视图
- 一套可被按需访问的数据来源
- 一条明确的挂载实例化路径

### 7.2 rootfs 实例化阶段在做什么

当 snapshotter 完成准备后,真正的容器 rootfs 还没有完成。  
此时还需要把 Nydus 挂载结果接入容器运行时最终看到的目录树。

这一步通常可以理解为:

1. 启动或复用 `nydusd`
2. `nydusd` 按所选驱动暴露挂载入口
3. 宿主机侧形成 lower layer
4. overlayfs 将 lower、upper、work 组合成容器 rootfs
5. runtime 基于该 rootfs 创建并启动容器进程

其中有一个很容易混淆但非常重要的事实:

> 容器“启动起来”并不等于“镜像数据已经完整下载完”。

Nydus 加速的关键正是把这两件事拆开:

- **启动路径上优先保证 rootfs 可见**
- **数据路径上再按读取行为触发下载**

这也是为什么 Nydus 常常能缩短冷启动时间:  
启动阶段只需要先拿到“挂载所需的最小必要信息”,而不是等待所有 layer 内容完整展开。

### 7.3 `fusedev` 与 `fscache` 在启动路径上的差异

如果只看“容器最终能看到文件系统”,`fusedev` 和 `fscache` 都能做到。  
但它们把“文件系统功能”放在了不同位置:

- `fusedev`: 用户态 `nydusd` 负责主要文件系统逻辑
- `fscache`: 内核 EROFS 负责主要文件系统解析,`nydusd` 负责按需供数

所以在启动路径上:

- `fusedev` 更像“先起一个用户态文件系统,再把它接到 overlayfs”
- `fscache` 更像“先建立一个内核文件系统视图,再准备一个用户态数据补给面”

换句话说,两者都能完成 rootfs 实例化,只是:

- 一个把文件系统主体放在用户态
- 一个把文件系统主体放在内核态

---

## 八、从首次读文件到懒加载回填: 主流程展开

容器启动后,真正体现 Nydus 价值的流程才开始: **按需读取**。

这里要回答的问题是:

> 当应用在容器里第一次读取某个文件时,系统到底如何定位并拿到对应的数据块?

可以先把它压缩成一句话:

```text
读文件不是直接读“完整本地文件”,而是先查元数据映射,再按需取 chunk
```

### 8.1 懒加载流程的共性

无论是 `fusedev` 还是 `fscache`,懒加载都遵循同一个基础逻辑:

1. 应用发起 `open/read`
2. 文件系统层先根据 inode 和 offset 找到对应 chunk
3. 检查 chunk 是否已经命中本地缓存
4. 未命中则向后端请求 blob 中对应范围的数据
5. 数据返回后写入缓存/页缓存
6. 再把结果返回给应用

这里 bootstrap 的作用非常关键。  
它并不保存完整文件内容,但它保存了“这个文件的哪个逻辑区间对应哪个 blob/chunk”。

因此 bootstrap 在懒加载里更像:

- 文件系统命名空间的目录
- inode 到 chunk 的索引表
- 按需下载的数据定位表

### 8.2 `fusedev` 路线中的懒加载

在 `fusedev` 路线中,应用读文件后,请求先进入内核 FUSE,再转给用户态 `nydusd`。

这时 `nydusd` 主要做三件事:

1. 解析 bootstrap,把文件偏移转换成 chunk 请求
2. 查询本地 blobcache 是否已有目标数据
3. 未命中时从 registry/对象存储等后端拉取对应 blob 范围

也就是说,在 `fusedev` 路线里:

- 元数据理解在 `nydusd`
- 数据获取在 `nydusd`
- 缓存控制也主要由 `nydusd` 配置驱动

所以它是一条典型的“用户态主导懒加载路径”。

### 8.3 `fscache` 路线中的懒加载

在 `fscache` 路线中,应用读文件后,真正先处理请求的是内核 EROFS。

流程上会变成:

1. 内核 EROFS 根据挂载得到的 RAFS 元数据视图解析文件
2. 发现目标页或 chunk 尚未就绪
3. 内核借助 `fscache/cachefiles` 发起按需数据请求
4. 用户态 `nydusd` 的 fscache service 负责从远端取回数据
5. 数据回填到内核缓存后,再由 EROFS 完成本次读请求

这条链路的本质变化是:

- 文件系统读语义主要在内核
- 用户态不再直接扮演 FUSE 文件系统
- `nydusd` 更专注于“远端数据供应”和“缓存协同”

因此它是一条“内核主导读路径,用户态提供数据”的懒加载模式。

### 8.4 为什么懒加载能加速,但又不等于没有代价

懒加载的收益来自把数据下载延后到真正访问时刻。  
但代价也很明确:

- 首次访问冷数据时会遇到远端拉取延迟
- 热点文件越集中,收益越明显
- 启动阶段若立刻扫描大量文件,懒加载收益会被削弱

所以从整体上看,Nydus 不是“取消下载”,而是把下载从:

- **启动前集中下载**

变成:

- **运行时按访问分布下载**

它优化的是**时间分布**和**实际命中率**,而不是让文件内容凭空出现。

---

## 九、从整体角度看各项技术到底在做什么

如果只记术语,很容易把 Nydus 理解成一堆并列组件。  
但从整体架构上看,这些技术其实是在分工完成三类事情:

1. **识别并准备镜像**
2. **把镜像实例化成 rootfs**
3. **在运行时按需补齐文件内容**

### 9.1 `containerd`

`containerd` 是容器生命周期的总调度入口。  
它负责:

- 接收拉镜像、创建容器、启动任务等请求
- 调用 snapshotter 准备 rootfs
- 把最终挂载结果交给运行时

它本身并不理解 Nydus 的全部文件系统细节,但它负责把镜像准备动作串起来。

### 9.2 `nydus-snapshotter`

`nydus-snapshotter` 是 Nydus 和 containerd 之间的连接层。  
它的核心职责不是提供文件系统本体,而是:

- 识别 Nydus 镜像
- 提取 bootstrap 和镜像元信息
- 生成挂载所需配置
- 启动或复用 `nydusd`
- 向 containerd 返回可用的挂载信息

因此 snapshotter 的角色更接近:

> rootfs 实例化编排器

### 9.3 `nydusd`

`nydusd` 是真正把 Nydus 镜像运行起来的核心执行者。  
但它在不同路径里的角色不同:

- 在 `fusedev` 中,它是用户态文件系统本体
- 在 `fscache` 中,它更像按需数据服务端

所以不能笼统地说 `nydusd` 就是“挂载进程”。  
更准确的理解是:

> `nydusd` 是 Nydus 运行时执行面,负责把 bootstrap、后端数据和缓存策略变成可读文件系统能力

### 9.4 `bootstrap`

`bootstrap` 的功能不是“保存镜像数据”,而是“保存文件系统组织方式”。

它至少承担三层作用:

- 描述目录树和 inode
- 描述文件逻辑偏移到 chunk 的映射
- 为运行时懒加载提供定位依据

因此 bootstrap 是:

- 挂载阶段的元数据基础
- 懒加载阶段的索引基础

### 9.5 `data blobs`

`data blobs` 才是真正的文件内容载体。  
它们通常保存在 registry 或外部对象存储中,由运行时按需读取。

从整体角度看,blob 的作用是:

- 作为远端内容源
- 作为缓存回填的原始数据来源
- 与 bootstrap 配合完成“视图先挂、内容后取”

### 9.6 `overlayfs`

在容器场景里,应用最终看到的 rootfs 往往不是单一挂载点,而是 overlayfs 组合结果。

它的职责是:

- 把 Nydus 提供的只读 lower layer 接入容器根文件系统
- 与 upper/work 组合成容器可写视图

所以 overlayfs 不负责 Nydus 懒加载本身,但它负责把 Nydus lower layer 变成容器真正使用的 rootfs。

### 9.7 `RAFS`

RAFS 可以理解为 Nydus 使用的镜像文件系统格式/布局。  
它定义的是:

- 元数据如何组织
- 文件如何映射到 chunk
- 运行时如何基于这些描述完成挂载和按需读取

因此 RAFS 是 Nydus 镜像“可运行”的格式基础。

### 9.8 `FUSE`

FUSE 的作用是让用户态程序有机会实现文件系统语义。  
在 Nydus 中,它对应的是 `fusedev` 这条路线。

它解决的问题是:

- 不依赖内核专用文件系统实现
- 由用户态 `nydusd` 接住 VFS 请求并完成文件读取

代价是:

- 读路径会经过用户态/内核态切换

### 9.9 `EROFS`

EROFS 在 Nydus 体系里代表的是“把文件系统主体能力交回内核”。  
它让:

- 文件系统解析
- 页缓存协同
- 读路径的一部分关键语义

更多发生在内核里。

因此当选择 `fscache` 或 `blockdev` 时,本质上是在选择 EROFS 主导的挂载模型。

### 9.10 `fscache`

`fscache` 不是一个新的文件系统,而是一套内核缓存与按需供数协作机制。  
在 Nydus 里它回答的问题是:

> 当 EROFS 发现某个数据块本地没有时,怎样向外部请求并缓存回来?

所以它的角色是:

- 内核按需读缺页时的桥梁
- 内核缓存与用户态数据服务之间的协作接口

### 9.11 `blobcache`

`blobcache` 更常出现在 `fusedev` 路线里。  
它的作用不是替代文件系统,而是把已经获取过的 blob 数据缓存下来,减少重复远端读取。

所以它的角色是:

- 远端 blob 的本地缓存层
- 懒加载命中优化层

---

## 十、把两条主线压缩成一句话

如果从整体架构看 Nydus,可以把它压缩成下面两句话:

- **镜像加载 + 容器启动**: 先用 bootstrap 把文件系统视图挂出来,再把这个视图接进容器 rootfs
- **懒加载**: 真正读取文件时,再根据 bootstrap 的 chunk 映射按需获取 blob 数据并回填缓存

所以 Nydus 的核心并不是“换一种镜像压缩格式”,而是把容器镜像运行过程拆成:

- 元数据先服务启动
- 数据内容按需服务运行

这也是它能同时影响冷启动、网络流量和缓存复用效率的根本原因。

---

## 十一、概念速查表

| 术语 | 回答的问题 | 角色 |
|-----|-----------|------|
| `fs_driver` | 文件系统怎么挂出来 | 挂载路径选择器 |
| `fusedev` | 用什么挂载 | FUSE 路线 |
| `fscache` | 用什么挂载 | EROFS + fscache 路线 |
| `blockdev` | 用什么挂载 | EROFS + 块设备路线 |
| `proxy` | 用什么接入 | 代理式特殊路径 |
| `shared mode` | `nydusd` 怎么复用 | 进程复用策略 |

---

## 十二、结论

如果把这几个概念压缩成一句话:

- 想走经典 Nydus 用户态文件系统路径,选 `fusedev`
- 想走内核 EROFS 的懒加载路径,选 `fscache`
- 想走块设备式 EROFS,选 `blockdev`
- `shared/dedicated` 决定的是 daemon 复用方式,不是镜像格式

所以当你问“使用 EROFS 是否和 FUSE 配置互斥”时,更准确的表达应该是:

> 在 Nydus 的挂载路径选择上,`fusedev` 与 `fscache/blockdev` 属于不同 `fs_driver`,因此是互斥选择,而不是叠加配置。

从设计视角看,这也是理解 Nydus 镜像挂载与懒加载流程的最关键切分线。
