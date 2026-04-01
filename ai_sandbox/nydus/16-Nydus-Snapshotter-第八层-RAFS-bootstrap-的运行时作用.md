# Nydus Snapshotter 第八层：RAFS bootstrap 的运行时作用

## 本层回答的问题

在前面的分析中，`bootstrap` 几乎每一层都会出现：

- 镜像识别时，要先找到 bootstrap layer
- `fs.Mount()` 时，要把 bootstrap 交给 `nydusd` 或 EROFS
- rootfs 启动时，要靠 bootstrap 先建立文件系统视图
- 懒加载读路径里，要靠 bootstrap 做 inode 和 chunk 定位

这说明 bootstrap 并不是一个“附带配置文件”，而是整条链路的关键枢纽。

因此第八层要回答的是:

> `RAFS bootstrap` 在整个 Nydus snapshotter 体系里，到底承担什么运行时作用？

更具体地说，要把它和这四件事连接起来:

1. 镜像元数据
2. 挂载视图
3. chunk 定位
4. 懒加载取数

---

## 一、先给 bootstrap 一个准确定位

Nydus 的镜像格式本质上把镜像拆成两部分:

- `bootstrap`: 元数据
- `data blobs`: 文件内容数据

相关文档:

- `docs/nydus-design.md`
- `docs/nydus-image.md`

如果压缩成一句话，bootstrap 的角色是:

> 用来描述“文件系统长什么样，以及文件内容去哪里找”的那部分元数据。

它不是:

- 普通文本配置文件
- 某个 daemon 的局部状态文件
- 文件内容本身

而是:

- 文件系统命名空间描述
- inode 索引
- chunk 映射
- blob 定位表

从运行时角度看，bootstrap 是:

> 一个可挂载、可查询、可驱动懒加载的元数据载体

---

## 二、从磁盘结构上看，bootstrap 里到底有什么

Nydus 文档里明确说明了 RAFS 的全局结构。

### 2.1 Superblock

bootstrap 文件开头会包含 superblock。  
文档中提到:

- superblock 位于 bootstrap 前 8K
- 它记录 RAFS 版本、block size、flags、inode table offset、blob table offset、prefetch table 等

相关文档:

- `docs/nydus-design.md`

因此 superblock 解决的问题是:

> 让运行时知道“这份 bootstrap 是什么格式，以及后续元数据表分别放在哪里”。

### 2.2 Inode table

bootstrap 里还包含 inode 相关元数据，例如:

- inode 号
- 父子关系
- uid/gid/mode
- 文件大小
- 目录 child 索引
- 普通文件 chunk 数量

相关文档:

- `docs/nydus-design.md`

因此 inode table 解决的问题是:

> 把“目录树”和“文件属性”组织成运行时可遍历的文件系统视图。

### 2.3 Chunk / blob 映射信息

对普通文件而言，bootstrap 里不会放完整文件内容，但会放:

- 这个文件被切成多少 chunk
- 每个 chunk 对应哪个 blob
- chunk 在 blob 中的偏移、长度、压缩等信息

相关文档:

- `docs/nydus-design.md`
- `docs/rafs-and-transport-protocols.md`

因此这部分元数据解决的问题是:

> 当读到某个文件某个 offset 时，运行时应该去哪个 blob 的哪个范围取数据。

---

## 三、从镜像视角看，bootstrap 是 metadata layer 的实体化形式

在 container image 视角里，Nydus 镜像会包含:

- 一个 metadata layer
- 一个或多个 data layers

文档中明确说明:

- metadata layer 对应 bootstrap
- data layer 对应 data blobs

相关文档:

- `docs/nydus-design.md`

所以在镜像分发阶段，bootstrap 的身份是:

> Nydus metadata layer 的实际内容

这解释了为什么 `nydus-snapshotter` 在 `Prepare()` 阶段的第一关键任务之一就是:

- 识别 bootstrap layer
- 将 bootstrap 落到本地可用位置

因为没有 bootstrap，后续根本无法回答:

- rootfs 长什么样
- 文件去哪找

---

## 四、从挂载阶段看，bootstrap 是“先挂视图”的基础

Nydus 之所以能缩短启动路径，本质上是因为:

- 它先用 bootstrap 把文件系统视图挂出来
- 不必先把完整 data blobs 下载下来

### 4.1 在 `fusedev` 下

snapshotter 把 bootstrap 路径和 daemon 配置交给 `nydusd`。  
随后 `nydusd` 基于 bootstrap 建立用户态文件系统视图。

因此在 `fusedev` 下，bootstrap 解决的问题是:

> 让 `nydusd` 知道应该向内核暴露怎样的目录树、inode 和文件布局。

### 4.2 在 `fscache` / EROFS 下

RAFS v6 的 bootstrap 兼容内核 EROFS 格式，内核拿到 bootstrap 后可以直接解析:

- SuperBlock
- Inode 表
- Chunk 地址表

相关文档:

- `docs/rafs-and-transport-protocols.md`

因此在 `fscache` 路径里，bootstrap 甚至直接承担:

> 内核文件系统挂载元数据镜像的角色

换句话说，bootstrap 不只是“给用户态进程看的元数据文件”，在 RAFS v6 场景下它还是:

- 内核可直接挂载和解析的文件系统元数据映像

---

## 五、从读路径看，bootstrap 是 inode 查找和 chunk 定位的入口

当容器启动完成后，应用第一次执行:

- `open("/path/to/file")`
- `read(fd, ...)`

真正第一步发生的并不是远端下载，而是:

- 先查 bootstrap

这一步要做两件事:

### 5.1 路径 / inode 查找

通过目录树和 inode 元数据找到:

- 目标文件的 inode
- 文件属性
- 文件大小

### 5.2 chunk 映射定位

再根据文件 offset 确定:

- 涉及哪个 chunk
- chunk 对应哪个 blob
- 在 blob 里的 offset/length 是多少

也就是说，在懒加载读路径里，bootstrap 本质上是:

> 把高层文件语义翻译成低层 blob/chunk 请求的索引桥梁

没有这一步，就无法从:

- “我要读 `/usr/bin/nginx` 第 4096 字节”

推导出:

- “要去 blob #0 的 offset=172032 取 4096 字节”

---

## 六、从 `fusedev` 和 `fscache` 的差别看，bootstrap 的作用不变，只是解析者变了

这是理解 bootstrap 的关键点之一。

bootstrap 在两条路径里的作用本质相同：

- 描述文件系统视图
- 描述 inode 和 chunk 映射
- 为按需读取提供定位依据

但二者的差别在于:

- **谁来解析 bootstrap**

### 6.1 `fusedev`

解析者是:

- 用户态 `nydusd`

因此读路径是:

- `nydusd` 查 bootstrap
- `nydusd` 计算 chunk 请求

### 6.2 `fscache`

解析者是:

- 内核 EROFS

因此读路径是:

- 内核查 bootstrap
- 内核计算 chunk 请求
- 缺数据时再让 `nydusd` 供数

所以这里最重要的结论是:

> `bootstrap` 的职责没有变，变化的是“谁来解释这份元数据”。

---

## 七、从 prefetch 和优化角度看，bootstrap 还是运行时优化提示的载体

bootstrap 不只承载目录树和 chunk 映射。  
文档里还提到它能承载:

- prefetch table
- blob-level readahead 相关提示

相关文档:

- `docs/prefetch.md`
- `docs/nydus-design.md`

这意味着 bootstrap 还承担:

> 把镜像构建阶段得到的运行时优化提示，带到实际挂载和读路径里。

例如:

- 哪些 inode 值得优先 prefetch
- 哪些 blob 范围适合预热

因此 bootstrap 不是纯静态结构描述，它还是:

- 一份运行时优化 hint 的载体

---

## 八、从 snapshotter 视角看，为什么 bootstrap 比 data blob 更早、更重要

在前面的调用链分析里可以看到:

- data blobs 可以跳过传统 unpack
- bootstrap 必须先被提取、定位、传给运行时

这是因为在启动路径上，系统首先需要的是:

- 文件系统可见性

而不是:

- 文件数据完整性

如果没有 bootstrap，就无法:

- 建立 lower layer
- 返回正确的 rootfs mount
- 响应 `stat/open/readdir`
- 定位任何 chunk

所以从启动优先级上看:

> bootstrap 是 Nydus 镜像“先启动、后取数”设计里最先被消费的对象。

---

## 九、从整体架构上重新定义 bootstrap

如果把前面的各个视角压缩起来，可以给 bootstrap 一个完整定义:

### 9.1 它是镜像元数据层

在镜像分发视角下，它对应 metadata layer。

### 9.2 它是文件系统视图描述

在挂载视角下，它描述目录树、inode、xattr、文件属性。

### 9.3 它是 blob/chunk 索引

在读路径视角下，它负责把文件偏移翻译成 blob/chunk 请求。

### 9.4 它是运行时优化提示载体

在性能视角下，它还携带 prefetch、readahead 等 hint。

因此用一句话概括 bootstrap，最准确的说法是:

> bootstrap 是 Nydus 运行时的元数据中枢，它把镜像层语义、挂载视图、chunk 索引和运行时优化提示统一收敛到一个可被挂载和解析的对象里。

---

## 十、为什么第八层重要

如果不单独把 bootstrap 拎出来看，就很容易把前面所有流程理解成:

- snapshotter 负责启动进程
- `nydusd` 负责读数据

但实际上，真正把这些流程串起来的对象是 bootstrap。

是它让:

- snapshotter 知道挂什么
- `nydusd` 知道暴露什么文件系统
- EROFS 知道如何直接解析目录树
- 读路径知道如何把文件请求映射为 blob/chunk 请求

所以 bootstrap 在整个 Nydus 体系里的地位，类似于:

- ext4 里的超级块 + inode 表 + block mapping 元数据

只不过它被拆出来，单独成为镜像分发和运行时可消费的 metadata object。

---

## 本层关键代码与文档位置

- `docs/nydus-design.md`
- `docs/nydus-image.md`
- `docs/rafs-and-transport-protocols.md`
- `docs/prefetch.md`
- `rafs/src/metadata/layout/v6.rs`

---

## 本层结论

第八层的结论是:

> `RAFS bootstrap` 不是附属元信息，而是 Nydus 运行时的元数据中枢。它既是镜像中的 metadata layer，也是挂载阶段的文件系统视图来源、读路径中的 inode/chunk 索引入口，以及运行时 prefetch/优化提示的承载体。Nydus 能做到“先挂视图、后取数据”，本质上就是因为 bootstrap 把这些能力提前独立出来了。
