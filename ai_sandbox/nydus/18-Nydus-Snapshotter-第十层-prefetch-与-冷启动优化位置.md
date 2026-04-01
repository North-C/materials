# Nydus Snapshotter 第十层：prefetch 与冷启动优化位置

## 本层回答的问题

前一层已经把:

- `data blobs`
- `chunk`
- `cache`

这三个数据面对象拆开了。  
但如果运行时完全只靠“读到哪里，拉到哪里”的纯懒加载策略，冷启动阶段仍然会遇到一个现实问题:

- 应用启动时往往会在极短时间内集中访问一批关键文件
- 这些文件虽然不算整个镜像的全部内容，但也不是零散到完全不可预测

因此第十层要回答的是:

> `prefetch` 在 Nydus 体系里到底处于什么位置，它为什么能成为介于“纯懒加载”和“全量预取”之间的一层冷启动优化机制？

更具体地说，这一层要把下面几件事连起来:

1. 静态 prefetch hint
2. 动态 prefetch files
3. fs-level prefetch
4. blob-level prefetch
5. warming / 冷启动优化

---

## 一、先给 prefetch 一个准确定位

Nydus 文档对 prefetch 的定位很明确:

- 它试图把多个 backend 读取合并成更大的读取
- 用户通常知道容器启动时哪些文件更可能被访问

相关文档:

- `docs/prefetch.md`

这说明 prefetch 不是“把整个镜像预先下载完”，而是:

> 在容器真正触发按需读之前，提前把一小部分高概率会访问的数据拉近到本地缓存侧。

因此它既不是:

- 传统镜像的全量 unpack
- 完全被动的 read-miss 才取数

也不是另一个独立挂载模式。  
它更准确的定位是:

> 叠加在懒加载之上的主动热身层

也可以理解成:

- 懒加载负责“没准备的数据也能按需拿到”
- prefetch 负责“把大概率马上会用到的数据先准备好”

---

## 二、为什么纯懒加载还需要 prefetch

从整体链路看，Nydus 已经做到了:

- 启动容器时先挂 bootstrap
- 文件真正读取时再按 chunk 去 backend 拉数据

这已经比传统全量解包快很多。  
但冷启动路径仍然可能被一连串首次 miss 拖慢。

比如一个服务刚启动时，常见会连续读取:

- 动态链接器相关文件
- 主程序二进制
- 运行时库
- 配置目录
- 初始化脚本

如果这些访问全部退化成:

```text
第一次 open/read
-> miss
-> 去 backend 拉 chunk
-> 回填 cache
-> 再返回给应用
```

那么虽然每次都“只拉需要的部分”，启动延迟仍然会被多个 miss 叠加。

因此 prefetch 解决的问题不是“让 Nydus 支持懒加载”，因为它本来就支持；  
prefetch 真正解决的是:

> 让应用启动阶段的一批高概率首次 miss，尽量在真正读到之前就被消化掉。

---

## 三、Nydus 的 prefetch 不是全局自动策略，而是显式 hint 驱动

这一点非常关键。  
`docs/prefetch.md` 里明确写到:

- 当前 Nydus 只能依据显式 hint 发起 prefetch
- hint 来源要么是 bootstrap 里的 prefetch table
- 要么是启动 `nydusd` 时通过 `--prefetch-files` 传入

文档还特别说明，目前并不存在这类“全局自动策略”:

- 低优先级慢速预取整个 blob
- 用户 IO 触发的通用块级 readahead 策略
- 读到一个子文件就自动预取整个父目录

因此从系统行为上讲，Nydus 的 prefetch 更接近:

> 一种 hint-based optimization

而不是:

> 一个默认无条件开启、会自动学习所有 workload 的通用预测系统

这意味着在分析冷启动优化时，不能把 prefetch 误解成“系统天然知道该提前拉什么”。  
真正决定 prefetch 效果的，是 hint 的来源和质量。

---

## 四、文件系统层 prefetch：最符合 Nydus 主链路的一种预取

`docs/prefetch.md` 里把第一类 prefetch 称为 `File System Level`。

它的核心机制是:

- 从 RAFS 层发起 prefetch 请求
- 先理解文件、目录和 chunk 的关系
- 再把需要的 chunk 从 backend 拉到本地缓存

文档中明确说:

- fs-level prefetch 会把所需 chunk 拉到 local storage
- 后续 read IO 可以直接命中 blobcache

这说明 fs-level prefetch 的关键特征是:

> 它理解文件系统语义，并且会真正把数据提前填入缓存层。

因此在整体链路里，它的位置是:

```text
bootstrap / prefetch hint
-> RAFS 层识别要预热哪些文件
-> 换算成一组 chunk
-> 向 backend 发起合并后的读取
-> 将数据提前填入本地 cache
-> 应用真正 read 时尽量直接命中
```

这条路径和 Nydus 主链路高度一致，因为它仍然建立在:

- bootstrap 元数据
- inode/chunk 映射
- cache 回填

这三件核心机制之上。

---

## 五、bootstrap 中的 prefetch table：构建期写入的静态 hint

Nydus 文档里明确说明:

- `nydus-image` 可以在镜像转换时根据给定文件列表写入 prefetch table
- prefetch table 会以最小化形式写进 bootstrap
- 表项本质上是用于 hint 的 inode 列表

相关文档:

- `docs/prefetch.md`
- `docs/nydus-design.md`

这说明 prefetch 的第一类来源不是运行时动态学习，而是:

> 镜像构建阶段就把“启动时可能先读哪些文件”编码进 bootstrap。

从整体视角看，这件事非常重要，因为它把:

- workload 启动行为
- 镜像构建布局
- 运行时预取

这三件事串了起来。

也就是说，bootstrap 不只负责:

- 文件系统视图
- inode/chunk 定位

它还可以携带:

> 冷启动优化提示

因此 prefetch table 可以看成 bootstrap 元数据能力的又一次延伸。

---

## 六、动态 `--prefetch-files`：运行时注入的第二类 hint

除了静态写入 bootstrap 的 prefetch table，Nydus 还支持在启动 `nydusd` 时额外传入:

- `--prefetch-files <prefetch-files>`

`docs/prefetch.md` 明确说:

- 即使镜像构建时没有写 prefetch hint
- 仍然可以在 mount 时指定 prefetch files
- 这和 bootstrap 里的 prefetch table 不冲突
- RAFS 会先加载 prefetch table，再考虑额外传入的 files list

这意味着:

> 运行时可以在不重建镜像的前提下，给这次挂载附加一组临时优化提示。

从系统设计上看，这个能力很实用，因为它把 prefetch 从“镜像固化策略”扩展成了“运行时可注入策略”。

---

## 七、nydus-snapshotter 怎样把动态 prefetch 注入到 nydusd

这一层在 `nydus-snapshotter` 里也有明确实现。

### 7.1 snapshotter 侧维护 image -> prefetch-files 映射

`nydus-snapshotter/pkg/prefetch/prefetch.go` 维护了一个全局映射:

- key 是 image reference
- value 是 prefetch files 字符串

这说明 snapshotter 内部已经把“某个镜像对应哪些预取文件”做成了运行态状态。

### 7.2 system controller 暴露设置入口

`nydus-snapshotter/pkg/system/system.go` 里有 `setPrefetchConfiguration()`，会:

- 读取 HTTP 请求体
- 调用 `prefetch.Pm.SetPrefetchFiles(body)`

这表明 snapshotter 自己提供了一个控制面入口，用来把 prefetch 列表灌进运行时状态。

### 7.3 daemon 启动命令会消费这份映射

在 `nydus-snapshotter/pkg/manager/daemon_adaptor.go` 里，构造 `nydusd` 启动命令时会:

- 根据 `imageReference` 读取 prefetch info
- 如果存在，就追加 `command.WithPrefetchFiles(prefetchfiles)`
- 然后从 map 里删掉这条记录

所以这一整条注入链路可以概括成:

```text
外部组件 / system controller
-> snapshotter 记录 image -> prefetch-files
-> snapshotter 启动 nydusd 时拼上 --prefetch-files
-> nydusd/RAFS 在 mount 初始化阶段执行预取
```

这说明 snapshotter 在 prefetch 体系里的角色不是“执行预取”，而是:

> 作为运行时控制面，把 workload 侧的优化 hint 转交给 nydusd。

---

## 八、NRI optimizer 把 prefetch 从“人工经验”推进到“基于访问行为生成”

`nydus-snapshotter/docs/optimize_nydus_image.md` 进一步说明了另一条更工程化的优化路径。

文档里提到:

- optimizer 作为 NRI plugin 订阅容器事件
- 在容器启动过程中观察哪些文件被打开和读取
- 生成访问文件列表
- 再把这些文件列表用于构建优化过的 Nydus 镜像

这意味着 prefetch hint 的来源不一定只能靠人工经验写文件清单，  
还可以来自:

> 对真实 workload 启动行为的观测

进一步说，这条链路把 prefetch 演进成了一个闭环:

```text
观察容器启动访问模式
-> 生成 accessed files list
-> 转换镜像时写入 prefetch patterns
-> 启动时优先预热这些关键文件
```

所以从整体架构看，optimizer 的意义不是增加一个新的挂载路径，  
而是提升 prefetch hint 的质量，使冷启动优化更贴近真实 workload。

---

## 九、blob-level prefetch：它也是预取，但不等于“提前填充 blobcache”

`docs/prefetch.md` 里还定义了第二类 prefetch: `Blob Level`。

它和 fs-level prefetch 的差别非常关键:

- 它直接对 blob 的连续区域做预取
- 不理解文件、目录和 chunk 语义
- 它不会把数据写进 blobcache 或其它同类缓存
- 它工作在 `StorageBackend` 层

文档还说明:

- blob-level prefetch 目前主要对 `LocalFs` backend 有意义
- 典型方式是借助 Linux `readahead(2)` 把一段底层数据提前读入页缓存

因此 blob-level prefetch 更准确的理解不是:

> 提前把应用要读的文件内容缓存好

而是:

> 提前让底层存储对象的某段连续区域在 backend 侧变得更容易被后续读取

这也说明为什么它和 fs-level prefetch 不能混为一谈:

- fs-level prefetch 面向文件语义和 cache 命中
- blob-level prefetch 面向底层对象连续区域和 backend readahead

---

## 十、warming 和 prefetch 的关系：都是热身，但粒度不同

在 `nydus-snapshotter/config/daemonconfig/fuse.go` 里，`FuseDaemonConfig` 除了 `FSPrefetch` 外，还定义了:

- `Warmup uint64`

代码里的注释写得比较克制:

> 开启 warmup 后，nydus daemon 可以缓存更多数据以提高命中率

这说明 `warmup` 的定位与 `prefetch` 接近，但并不完全等同。

从已公开代码和注释能安全得出的结论是:

- `prefetch` 更强调“依据明确 hint 预先拉取一批目标数据”
- `warmup` 更强调“为了提高命中率而扩大热身或缓存准备程度”

因此可以把二者关系理解成:

- `prefetch` 偏向有目标、有列表的预取
- `warmup` 偏向更宽泛的缓存加热能力

但就当前仓库中能直接确认的信息而言，不能把 `warmup` 过度解释成某一种确定的后台算法。  
更稳妥的说法是:

> `warmup` 也是冷启动优化的一部分，但它在语义上比显式 prefetch 更宽。

---

## 十一、可观测性：prefetch 不是黑盒，运行时能看到效果

`nydus-snapshotter/pkg/daemon/types/types.go` 里的 `CacheMetrics` 定义了多项 prefetch 指标，例如:

- `PrefetchDataAmount`
- `PrefetchRequestsCount`
- `PrefetchWorkers`
- `PrefetchUnmergedChunks`
- `PrefetchCumulativeTimeMillis`
- `PrefetchBeginTime*`
- `PrefetchEndTime*`
- `DataAllReady`

这说明 prefetch 并不是一个完全不可见的“后台魔法”，  
而是一个能够被运行态观测和统计的优化过程。

从整体运维角度看，这些指标至少可以帮助回答:

- 这次是否真的发生了 prefetch
- 预取了多少数据
- 预取持续了多久
- 数据是否已经准备完成

因此 prefetch 在体系里不仅是优化机制，也是一类可运营、可验证的运行态行为。

---

## 十二、把 prefetch 放回整条启动链路里看

到这里可以把 prefetch 放回前面几层已经建立的主链路里:

```text
镜像构建期
-> 根据经验或 optimizer 生成 prefetch hint
-> 写入 bootstrap prefetch table

容器启动前
-> snapshotter 识别镜像并准备 bootstrap / lower layer
-> 如有需要，通过 system controller / image mapping 注入动态 prefetch-files
-> nydusd 启动时带上 prefetch hint

挂载初始化阶段
-> RAFS 根据 hint 将目标文件换算成 chunk
-> 向 backend 发起合并读取
-> 将数据提前填入 cache，或在 blob-level 上触发 backend readahead

应用真正启动读文件时
-> 尽量直接命中已经预热的数据
-> 未命中部分再回退到普通懒加载路径
```

因此 prefetch 和懒加载不是互斥关系，而是:

> prefetch 先尽量消化掉一部分高概率冷启动 miss，懒加载再兜底处理剩余的随机访问。

---

## 十三、一句话总结这一层

第十层的核心结论是:

> `prefetch` 是 Nydus 懒加载体系上的主动热身层，它依赖 bootstrap 中的静态 hint 或运行时注入的动态 files list，在挂载初始化阶段提前把一批高概率会访问的数据推近缓存侧，从而降低容器冷启动阶段的首次 miss 成本。

进一步压缩成一句更工程化的话就是:

> 懒加载解决“可以晚点拉”，prefetch 解决“哪些数据最好别等真正读到时再拉”。
