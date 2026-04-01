# Nydus Snapshotter 第十一层：完整性校验与数据可信性边界

## 本层回答的问题

前面几层已经把 Nydus 的核心运行链路拆开了:

- snapshotter 识别并挂载远程 rootfs
- `nydusd` 或内核 EROFS 提供文件系统视图
- 运行时按 chunk 从 backend 拉数据
- prefetch 负责降低冷启动 miss

但这里还剩下一个必须单独回答的问题:

> 在“镜像不先全量落盘、数据按需从远端取回”的前提下，Nydus 如何保证最终读到的元数据和文件内容是可信的？

因此第十一层要把下面几类机制放到同一条链路里:

1. bootstrap 签名验证
2. metadata digest 校验
3. data chunk digest 校验
4. cache 回读校验
5. tarfs/blockdev 路径上的 dm-verity 支线

这一层的重点不是“有哪些安全名词”，而是:

> 哪个对象由谁校验，在哪个阶段校验，失败后会怎样影响整条挂载和读路径。

---

## 一、先给“完整性”一个准确定位

Nydus 总设计文档把它的一个关键特性直接写成:

> End-to-end image data integrity

相关文档:

- `docs/nydus-design.md`
- `service/README.md`

这说明完整性校验在 Nydus 里不是外围增强项，而是主链路能力的一部分。

但“end-to-end integrity”不能笼统理解成“只要有一个开关打开就全都安全了”。  
从当前代码和文档看，Nydus 实际上把可信性拆成了几层:

- 元数据自身是否被篡改
- bootstrap 是否来自可信发布者
- chunk 数据是否与元数据里记录的 digest 一致
- 缓存中的旧数据是否仍然有效
- 某些 block/tarfs 场景下，是否通过 dm-verity 提供块级校验

因此更准确的说法是:

> Nydus 的完整性保证不是单点机制，而是一组分层校验链条。

---

## 二、metadata 完整性：先保证“文件系统长什么样”这件事没被改

`docs/nydus-design.md` 在 `Integrity Validation` 一节里把 metadata 完整性分成两部分:

- 先做基本的字段合法性检查
- 再做整体 digest 校验

文档中明确提到:

- metadata 会携带 digest 信息
- 运行时访问 metadata 时会进行 read verification
- 如果 sanity check 或 digest check 失败，就认为 metadata 已损坏

这说明 metadata 校验解决的问题是:

> 在真正去读数据之前，先保证 bootstrap 所描述的 inode、目录树、chunk 映射本身是可信的。

因为一旦 metadata 被篡改，即使后面的 chunk 数据本身没问题，系统也可能:

- 找错 inode
- 找错 blob
- 找错 chunk offset

所以从整体链路看，metadata 完整性是:

> 整条懒加载读路径的前置可信基础。

---

## 三、bootstrap 签名验证：snapshotter 在挂载前先做“来源可信”检查

除了 metadata 自身的 digest 机制，`nydus-snapshotter` 还提供了更外层的一道校验:

- bootstrap signature verify

相关代码:

- `nydus-snapshotter/pkg/signature/signature.go`
- `nydus-snapshotter/pkg/filesystem/fs.go`
- `nydus-snapshotter/config/config.go`
- `nydus-snapshotter/pkg/label/label.go`

### 3.1 签名从哪里来

snapshotter 约定使用镜像 label:

- `containerd.io/snapshot/nydus-signature`

也就是 `label.NydusSignature`。

`pkg/signature/signature.go` 会从这个 label 里读取 base64 编码的签名数据。

### 3.2 什么时候要求必须验证

`config.ValidateConfig()` 里明确规定:

- 如果开启 `ImageConfig.ValidateSignature`
- 就必须提供 `PublicKeyFile`

这说明签名验证不是随意触发的隐式行为，而是:

> 由 snapshotter 配置显式开启的挂载前强校验。

### 3.3 在哪一步真正执行

`pkg/filesystem/fs.go` 在为 RAFS instance 准备完 daemon 和 bootstrap 后，会直接调用:

- `fs.verifier.Verify(labels, bootstrap)`

也就是说，这一步发生在:

- lower layer 正式 mount 之前
- `nydusd` 或 EROFS 真正开始服务读请求之前

因此 bootstrap 签名验证的位置可以理解成:

> snapshotter 对“这份 bootstrap 是否来自可信发布者”的入口把关。

### 3.4 失败后意味着什么

如果签名不匹配，`fs.Mount()` 会直接返回错误，挂载流程中止。  
所以这层校验不是运行后告警，而是:

> 挂载前阻断。

---

## 四、签名验证和 metadata digest 校验不是一回事

这两者很容易混淆，但职责不同。

### 4.1 bootstrap 签名验证

更偏:

- 发布者身份与来源可信性
- “这份 bootstrap 是否由我信任的签名方生成”

### 4.2 metadata digest 校验

更偏:

- bootstrap 内容在读取时是否发生损坏或篡改
- “这份 metadata 的结构和内容是否自洽”

因此这两层关系更接近:

- 签名验证解决来源真实性
- digest 校验解决内容一致性

如果只做签名验证，不代表运行时每次访问 metadata 都不再需要校验；  
反过来，只做 metadata digest，也不等于已经验证“发布者是谁”。

所以从可信性链路看，这两层是互补关系，而不是替代关系。

---

## 五、data chunk 完整性：真正读到的数据还要再过一层 digest 校验

`docs/nydus-design.md` 同时明确写到:

- data 被切成 chunk
- 每个 chunk 的 digest 会保存在 chunk info 里
- data integrity validation 与 metadata 类似

这说明在 Nydus 里，文件内容的可信性不是“相信 backend 返回什么就是什么”，而是:

> 每个 chunk 都有与元数据绑定的摘要，用来在读出数据后做内容校验。

这件事正是按需加载体系里最关键的一步。  
因为 backend 可以是:

- registry
- OSS / S3
- 本地文件系统
- Dragonfly 分发体系

如果没有 chunk 级别校验，懒加载路径上任何一次远端读取都可能把错误内容静默带进 rootfs。

---

## 六、运行时真正做 chunk 校验的地方，在 storage/cache 这一层

`storage/src/cache/mod.rs` 对这条链路写得非常直接。

代码里先定义了:

- `need_validation()`

然后在 `read_chunk_from_backend()` 里:

1. 从 backend 读取 chunk 原始数据
2. 必要时解密 / 解压
3. 调用 `validate_chunk_data()`

而 `validate_chunk_data()` 又会根据条件决定是否检查:

- `chunk.has_crc32()`
- `self.need_validation()`
- `force_validation`

最终通过:

- CRC32
- 或 chunk digest/hash

来确认 buffer 内容是否匹配 chunk info 里记录的值。

这说明真正的数据完整性校验点，不是在 snapshotter 里，而是在:

> Nydus 数据面执行实际读 IO 的那一层。

也就是说，整条读路径是:

```text
应用 read
-> 定位 chunk
-> 从 backend 或 cache 取回数据
-> 解压 / 解密
-> 校验 digest / crc
-> 校验通过后才返回给上层
```

这一步才是“最终读到的数据可信”的关键落点。

---

## 七、cache 不是绕过校验，反而是校验链的一部分

很多人会误以为:

- 远端数据会校验
- 本地 cache 命中就直接信任

但从 storage 层代码看，事情没这么简单。

`storage/src/cache/cachedfile.rs`、`filecache/mod.rs`、`fscache/mod.rs` 等实现里都出现了:

- `cache_validate`
- `need_validation`
- “read and validate data from cache”

而 `storage/src/cache/mod.rs` 的注释也明确指出:

> 从 blob cache 读取的数据在使用前应被校验。

这意味着 cache 在 Nydus 里的角色不是“逃避校验的捷径”，而是:

> 仍然处于可信性约束之下的性能层。

所以完整的语义应该是:

- cache 用来减少重复取数
- validation 用来防止把损坏的缓存重新喂给应用

这两者并不冲突。

---

## 八、`digest_validate` 开关决定的是运行时数据校验强度

在 `nydus-snapshotter/config/daemonconfig/fuse.go` 里，FUSE daemon 配置里包含:

- `DigestValidate bool`

`service/README.md` 的示例配置也能看到这个字段。

这说明对 FUSE 路径而言，运行时 chunk digest 校验是:

> 通过 daemon 配置显式控制的一项能力。

从整体角度看，它影响的是:

- 从 backend 拉回 chunk 后是否强制做 digest 校验
- cache 回读时是否需要进入校验路径

因此它属于:

> 数据面运行时可信性策略

而不是 snapshotter 外围的镜像识别逻辑。

---

## 九、`fusedev` 和 `fscache` 虽然读路径不同，但可信性目标是一致的

前面第五层已经拆过:

- `fusedev` 是用户态 `nydusd` 主导文件系统语义
- `fscache` 是内核 EROFS 主导文件系统语义，`nydusd` 主供数

但这不意味着两条路对完整性的理解不同。  
真正保持一致的是:

> 不管数据最终是经由 FUSE 还是经由 fscache/EROFS 暴露给应用，底层 chunk 数据都必须受 metadata 和 digest 约束。

从工程实现看，差别更多体现在:

- 谁发起实际 IO
- 谁持有 mountpoint
- 谁在 miss 时请求 backend

而不是“某条路径就不需要校验”。

---

## 十、tarfs / blockdev 支线：这里的完整性更多通过 dm-verity 表达

除了 RAFS 主链路，`nydus-snapshotter` 还支持 tarfs / blockdev 这条支线。

相关文档和代码:

- `nydus-snapshotter/docs/tarfs.md`
- `nydus-snapshotter/snapshot/mount_option.go`

文档里明确提到:

- tarfs 支持生成带 dm-verity 信息的 raw disk image
- 通过 `layer_block_with_verity` 或 `image_block_with_verity` 导出模式启用

而 `snapshot/mount_option.go` 里专门定义了:

- `DmVerityInfo`
- `parseTarfsDmVerityInfo()`
- `Validate()`

这里的意义在于:

> tarfs/blockdev 场景下，运行时完整性不再主要表现为“RAFS chunk digest 校验”，而是转化为块设备级别的 dm-verity 校验链。

所以这一支线说明，Nydus snapshotter 的可信性设计并不只绑定一种技术形态，而是:

- RAFS 主链路用 metadata/chunk digest
- block/tarfs 支线可借助 dm-verity

---

## 十一、把“可信性边界”按模块重新划分

到这里，可以把整条完整性链路重新映射到各模块职责上:

### 11.1 snapshotter

负责:

- 校验配置是否合法
- 读取 label 中的 bootstrap signature
- 在 `fs.Mount()` 阶段执行 bootstrap 签名验证

它的可信性边界更偏:

> 挂载前入口把关

### 11.2 bootstrap / metadata

负责:

- 描述 inode、目录树、blob、chunk 映射
- 在访问时接受 metadata digest 与字段合法性校验

它的可信性边界更偏:

> 文件系统语义是否被篡改

### 11.3 storage/cache

负责:

- 对真正读回来的 chunk 数据做 digest / crc 校验
- 必要时对 cache 回读数据再次校验

它的可信性边界更偏:

> 文件内容字节是否真实匹配 metadata 的声明

### 11.4 tarfs / blockdev

负责:

- 在块设备导出模式下通过 dm-verity 提供块级校验

它的可信性边界更偏:

> raw image block 路径上的完整性保障

---

## 十二、把完整性校验放回整条运行链路里

最后把这一层放回主流程，可以得到一条更完整的可信性闭环:

```text
镜像被识别
-> snapshotter 读取 bootstrap label 和签名
-> 如配置要求，先做 bootstrap 签名验证
-> 启动 / 复用 nydusd，挂出 lower layer
-> 运行时访问 bootstrap 时，做 metadata 字段与 digest 校验
-> 应用真正读文件时，按 chunk 从 backend 或 cache 获取数据
-> 解压 / 解密后做 chunk digest 或 crc 校验
-> 校验通过才把数据返回给应用
```

如果走 tarfs/blockdev 支线，则变为:

```text
导出 raw image
-> 携带 dm-verity 信息
-> 运行时由块设备校验链保证数据完整性
```

这说明 Nydus 的完整性设计并不是附着在某一个阶段，而是贯穿:

- 挂载前
- metadata 访问时
- chunk 数据读回时
- 某些 block 模式下的块设备访问时

---

## 十三、一句话总结这一层

第十一层的核心结论是:

> Nydus 的数据可信性并不是靠单一开关完成的，而是由 snapshotter 的 bootstrap 签名验证、RAFS metadata 的运行时 digest 校验、storage/cache 层的 chunk 数据校验，以及 tarfs/blockdev 场景下的 dm-verity 支线共同组成的一条分层完整性链路。

再压缩成一句更工程化的话就是:

> Nydus 不只解决“能按需把数据拉回来”，还要解决“拉回来的元数据和内容在每一层都能被验证为可信”。 
