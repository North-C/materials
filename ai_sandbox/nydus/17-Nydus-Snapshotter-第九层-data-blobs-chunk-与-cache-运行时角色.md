# Nydus Snapshotter 第九层：data blobs / chunk / cache 的运行时角色

## 本层回答的问题

前一层已经把 `bootstrap` 拎出来单独分析过了。  
如果说 bootstrap 解决的是:

- 文件系统长什么样
- 文件内容去哪里找

那么这一层要回答的就是:

> 文件内容本身到底以什么形式存在，运行时又是怎样按需把它取回来并缓存起来的？

因此第九层的重点是三个对象:

1. `data blobs`
2. `chunk`
3. `cache`

也就是把 Nydus 运行链路里“真正承载文件内容”的那一半拆清楚。

---

## 一、先给 data blobs 一个准确定位

Nydus 文档里说得很明确:

- blob 是容器镜像的数据部分
- 文件内容会被拆成一个或多个固定长度 chunk

相关文档:

- `docs/nydus-design.md`

所以 data blobs 本质上不是:

- 目录树
- inode 结构
- 挂载元数据

它们真正承载的是:

> 文件内容字节本身

从整体架构看，可以把 data blobs 理解成:

- bootstrap 之外的内容面
- 懒加载真正去读取的远端对象

如果用一句话总结:

> bootstrap 决定“读什么”，data blobs 承担“读出来的内容是什么”。

---

## 二、为什么 Nydus 要把文件内容切成 chunk

这一步是 Nydus 按需加载能力的基础。

文档中提到，文件数据会被拆成固定长度 chunk，典型是 1MB。

切 chunk 的意义不是“为了好看”，而是为了同时解决几个问题:

### 2.1 支持随机访问

如果一个大文件只存成一个整体对象，那么想读其中 4KB，往往也得先把大块数据完整取回来。  
切成 chunk 后，运行时可以只请求真正涉及的 chunk 范围。

### 2.2 支持按需加载

按需加载的核心不是“晚点下载整个文件”，而是:

> 只下载真正读到的文件片段对应的 chunk

### 2.3 支持缓存命中和复用

chunk 是缓存的自然粒度。  
只有把内容切成 chunk，系统才能标记:

- 哪些 chunk 已经在本地
- 哪些 chunk 还没命中

### 2.4 支持压缩、校验和去重

chunk 也是:

- 压缩单位
- digest 校验单位
- 去重单位

因此 chunk 不是 Nydus 的细节实现，而是:

> Nydus 数据面所有运行时能力的最小工作单元

---

## 三、运行时为什么不会“直接读 blob”，而是先读 chunk

从应用进程视角，读请求通常是:

- `read(fd, 4096)`
- `mmap`
- 页级访问

而从 backend 视角，远端对象往往是:

- registry blob
- oss/s3 object
- 本地 blob 文件

这两者的粒度天然不一致。  
Nydus 用 chunk 把二者桥接起来。

运行时会先做:

1. 根据 inode + offset 算出需要哪些 chunk
2. 再把这些 chunk 对应到 blob 中的压缩范围
3. 最后再决定是否命中缓存，或从 backend 读取

因此真实的数据路径不是:

```text
应用 -> 直接读 blob
```

而是:

```text
应用 -> 文件偏移 -> chunk -> blob 范围 -> backend / cache
```

这意味着，真正对接应用语义和远端对象语义的中间层就是:

- chunk 映射

---

## 四、cache 在 Nydus 里为什么是必要层，而不是附加优化

Nydus 的设计目标之一是支持按需加载。  
但如果所有 miss 都直接打到远端 backend，延迟会非常高。

因此 `storage/src/cache/mod.rs` 一开头就明确说明:

> cache layer 是放在 RAFS 文件系统与 backend 存储之间的性能层，用来把远端数据缓存到本地，并把小请求合并成更大的请求。

相关代码:

- `storage/src/cache/mod.rs`

这说明 cache 在 Nydus 里不是“可有可无的性能锦上添花”，而是:

> 按需加载可用性和性能之间的平衡层

如果没有 cache，Nydus 仍然可以理论上工作，但:

- 延迟会显著变差
- 重复访问成本会高很多
- 网络放大和请求放大会更明显

---

## 五、`blobcache` 的运行时角色

`blobcache` 是最典型的用户态缓存形态，常见于 `fusedev` 路线。

文档里明确指出:

- 已经获取的 blob 数据会保存在本地 work dir
- 后续不会重复从远端获取

相关文档:

- `docs/nydus-design.md`

从运行时角度看，`blobcache` 主要承担四个职责:

### 5.1 作为远端数据的本地副本层

把已经下载过的 blob 数据保存到本地文件中。

### 5.2 作为 chunk 命中判断的基础

系统需要知道:

- 这个 blob 的哪些 chunk 已经准备好了
- 哪些范围仍然需要从后端获取

### 5.3 作为请求合并和放大的承载层

为了提升后端性能，Nydus 不一定每次只取一个最小 chunk，而可能会把相邻请求合并成更大的 backend range request。

### 5.4 作为后续读请求的复用来源

一旦 chunk 已命中，下次读就可以直接从本地缓存返回。

因此 `blobcache` 可以理解为:

> 用户态 Nydus 数据路径中的 L1 本地内容缓存层

---

## 六、`fscache` 的运行时角色

`fscache` 虽然名字里也有 cache，但它和 `blobcache` 不是同一层次的东西。

### 6.1 `blobcache`

更偏:

- Nydus 用户态管理的本地 blob 缓存

### 6.2 `fscache`

更偏:

- Linux 内核和用户态供数服务协作的缓存框架

在 `EROFS + fscache` 路线中，运行时的数据路径大致是:

1. 内核根据 bootstrap 找到 chunk
2. 去 fscache 检查是否已缓存
3. 未命中则让 `nydusd` 作为供数端从 backend 拉数据
4. 写入缓存文件
5. 更新 chunk_map
6. 后续由 fscache / 页缓存直接命中

相关文档:

- `docs/rafs-and-transport-protocols.md`
- `docs/nydus-fscache.md`

因此 `fscache` 的角色不是“另一个 blobcache 实现”，而是:

> 内核读路径中的缺页回填与缓存协调层

---

## 七、chunk map 为什么重要

前面说 cache 需要知道哪些 chunk 已命中，真正承担这件事的数据结构就是 chunk map。

相关代码和文档线索中都可以看到:

- `chunk_map`
- ready / not ready 标记
- `.chunk_map` 文件

这说明运行时并不只是“有缓存目录就算缓存了”，而是必须回答:

- 某个 blob 的哪些 chunk 真的已经准备好？

chunk map 解决的就是这个问题。

它的作用可以概括为:

### 7.1 命中判断

决定某次读请求是否能直接从本地返回。

### 7.2 断点与恢复

即使缓存文件存在，也不代表其中所有 chunk 都已完整准备好。  
chunk map 让系统能够区分:

- 已经可读的范围
- 尚未就绪的范围

### 7.3 缓存回填后的状态更新

当后端数据取回并写入本地后，chunk map 会同步更新 ready 状态。

因此 chunk map 是:

> 把“缓存文件存在”提升为“哪些数据范围真的可读”的关键状态层

---

## 八、backend 在这条链路里的角色

在 Nydus 中，backend 可以是多种形式:

- registry
- OSS
- S3
- localfs
- localdisk
- http proxy 等

相关文档与代码:

- `storage/README.md`
- `storage/src/factory.rs`

从运行时角度看，backend 的职责很单纯:

- 按 blob/range 提供原始数据

它通常不负责:

- 理解 inode
- 理解目录树
- 理解 rootfs
- 理解容器启动

所以 backend 是:

> Nydus 数据面的原始内容来源

而不是文件系统本身。

---

## 九、把 bootstrap 与 data blobs 重新对照一次

为了避免再次把这两者混在一起，可以做一个最小对照:

| 对象 | 主要回答的问题 |
|------|----------------|
| `bootstrap` | 文件系统是什么样、文件内容去哪里找 |
| `data blobs` | 文件内容字节本身是什么 |
| `chunk` | 文件偏移如何映射到 blob 范围 |
| `cache` | 已经取回的内容如何复用和命中 |
| `backend` | 缺失内容从哪里来 |

这张表说明:

- bootstrap 是索引面
- data blob 是内容面
- chunk 是桥接粒度
- cache 是性能与状态面
- backend 是供给面

这五者合起来，才构成完整的数据路径。

---

## 十、从 `fusedev` 和 `fscache` 看数据面有什么变化

虽然二者的文件系统执行面不同，但数据面其实有一部分共性。

### 10.1 相同点

- 都需要通过 chunk 把文件偏移映射到 blob 范围
- 都需要从 backend 取回缺失数据
- 都需要一个本地缓存命中体系
- 都需要某种 chunk 就绪状态跟踪

### 10.2 不同点

`fusedev`:

- 数据路径更偏用户态
- 常用 `blobcache`
- `nydusd` 同时负责文件系统解释和缓存控制

`fscache`:

- 数据路径更偏内核态协调
- 内核通过 `fscache/cachefiles` 管理缓存命中和缺页
- `nydusd` 负责供数和 blob 对象管理

因此两条路径差别主要在:

- 谁来主导缓存协同

而不是:

- 数据是不是仍然来自同一类 blob/chunk/backend 结构

---

## 十一、prefetch 在数据面里的位置

除了按需 miss 后再取数，Nydus 还支持 prefetch。

文档里提到 prefetch 有两类:

- fs level prefetch
- blob level prefetch

相关文档:

- `docs/prefetch.md`

从数据面角度看，prefetch 的角色是:

> 在真正 miss 之前，提前把可能要读的数据放进 cache，提高首轮读命中率

因此 prefetch 不是单独一条新数据路径，而是:

- 对现有 data blobs / chunk / cache 体系的一种预热策略

---

## 十二、从整体角度重新定义 Nydus 的数据面

如果把这一层所有对象压缩成一句话，可以这样描述:

> Nydus 的数据面由 data blobs、chunk 映射、cache 和 backend 共同组成：data blobs 承载真正文件内容，chunk 把文件偏移映射到 blob 范围，cache 决定哪些内容已经可以本地命中，backend 则在 miss 时提供原始数据来源。

也可以再进一步抽象成四层:

1. **内容层**: data blobs
2. **寻址层**: chunk
3. **命中层**: cache / chunk map
4. **供给层**: backend

而 bootstrap 则位于它们之前，负责告诉系统如何进入这条数据路径。

---

## 本层关键代码与文档位置

- `docs/nydus-design.md`
- `docs/nydus-fscache.md`
- `docs/rafs-and-transport-protocols.md`
- `docs/prefetch.md`
- `storage/README.md`
- `storage/src/cache/mod.rs`
- `storage/src/factory.rs`
- `nydus-snapshotter/pkg/cache/manager.go`

---

## 本层结论

第九层的结论是:

> 在 Nydus 运行时里，bootstrap 负责“知道去哪找”，而 `data blobs / chunk / cache / backend` 负责“把真正内容按需拿回来并复用起来”。其中 data blobs 是文件内容载体，chunk 是最小寻址与缓存粒度，cache 决定命中与回填状态，backend 提供原始数据来源，它们共同构成了 Nydus 懒加载的数据面。
