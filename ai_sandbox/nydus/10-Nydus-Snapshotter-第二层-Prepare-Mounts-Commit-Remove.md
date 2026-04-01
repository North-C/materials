# Nydus Snapshotter 第二层：Prepare / Mounts / Commit / Remove 调用链

## 本层回答的问题

`nydus-snapshotter` 是如何利用 containerd snapshotter 的标准调用链，把 Nydus 镜像接入容器启动流程的？

这一层重点不是 `nydusd` 内部细节，而是:

> 同样是 snapshotter API，Nydus 在 `Prepare -> Mounts -> Commit -> Remove` 这条标准链路上做了哪些改造？

---

## 一、containerd 的标准 snapshotter 语义

从 containerd 的常见工作方式看，snapshotter 主要承担四类动作:

1. `Prepare`: 为只读层解包或为容器可写层启动做准备
2. `Mounts` / `View`: 返回当前 snapshot 需要的挂载信息
3. `Commit`: 把 active snapshot 提交成 committed snapshot
4. `Remove`: 删除 snapshot 及其关联资源

普通 overlayfs snapshotter 的默认假设通常是:

- 只读层需要被本地 unpack
- 启动容器时，把各层本地目录拼成 overlay rootfs

而 `nydus-snapshotter` 的改造点就在于:

> 它不默认“每层都要本地解包”，而是先按镜像层语义做分流。

---

## 二、`Prepare()` 是 Nydus 介入调用链的关键入口

`Prepare()` 的代码入口在:

- `nydus-snapshotter/snapshot/snapshot.go`

它先做一部分标准动作:

1. 创建 active snapshot
2. 准备 snapshot 目录
3. 将 snapshot 信息写入 MetaStore

这一部分仍然是标准 snapshotter 行为。

但和普通 snapshotter 的分叉点在于，`Prepare()` 并不会默认“下一步一定是本地 unpack”，而是调用:

- `nydus-snapshotter/snapshot/process.go`

中的 `chooseProcessor()` 决定当前 snapshot 应该如何处理。

---

## 三、只读层 Prepare：决定“解包”还是“跳过”

在镜像拉取和解包阶段，containerd 会对只读层调用 `Prepare()`。  
`nydus-snapshotter` 会根据 labels 判断当前层类型。

### 3.1 普通 OCI 层

如果当前层不是 Nydus 特殊层，就走 `defaultHandler`:

- 返回普通 bind/overlay mount
- 让 containerd 继续执行标准 unpack

### 3.2 Nydus bootstrap 层

bootstrap 层通常仍需要在本地可见，因为后续挂载要依赖它。  
因此它也可能走接近本地处理的路径。

### 3.3 Nydus data blob 层

data blob 层不会像普通 layer 一样被解包到本地目录。  
它会走 `skipHandler`，阻止 containerd 把它当普通 layer 处理。

这一步的关键意义是:

> `nydus-snapshotter` 把镜像的“元数据层”和“数据层”拆开处理，数据层跳出传统 unpack 路径。

相关代码:

- `nydus-snapshotter/snapshot/process.go`

---

## 四、可写层 Prepare：决定“本地 rootfs”还是“远程 rootfs”

当 `Prepare()` 作用在容器启动时的 active writable snapshot 上，逻辑就变了。

此时 `chooseProcessor()` 会:

1. 查父链里是否有 Nydus meta layer
2. 如果有，就进入 `remoteHandler`
3. 如果没有，就继续走普通本地 snapshot 路径

`remoteHandler` 会做三件事:

1. 调用 `sn.fs.Mount()` 实例化远程 lower layer
2. 调用 `sn.fs.WaitUntilReady()` 等待它进入可用状态
3. 调用 `sn.mountRemote()` 生成最终给 runtime 的 mount slice

也就是说:

> 对 Nydus 容器启动来说，真正的远程 lower layer 实例化，核心发生在 `Prepare()` 阶段。

相关代码:

- `nydus-snapshotter/snapshot/process.go`

---

## 五、`Mounts()` / `View()` 的作用：把已准备好的 lower layer 交给 runtime

`nydus-snapshotter` 中的 `Mounts()` / `View()` 并不是重新做一遍远程挂载，而是:

- 判断当前 snapshot 是否已经有可用的 Nydus lower layer
- 如有必要，补齐 ready 状态
- 返回 overlay 或远程 mount 结果

### 5.1 `mountNative()`

对应普通 snapshotter 路径:

- bind mount
- overlay mount

### 5.2 `mountRemote()`

对应 Nydus 远程路径:

- lowerdir 指向 Nydus lower layer
- active snapshot 追加 upperdir/workdir
- 最终返回 overlay mount slice

因此 `Mounts()` 的意义可以概括成:

> 把“已经实例化好的 lower layer”包装成 containerd/runtime 可以直接消费的挂载描述。

关键代码:

- `nydus-snapshotter/snapshot/snapshot.go`

---

## 六、`Commit()`：提交的是 snapshot 状态，不是远程 blob 内容

`Commit()` 的代码仍然很标准:

1. 找到 active snapshot
2. 计算 `upperPath` 的本地磁盘占用
3. 调用 `storage.CommitActive()` 提交

重要的是要理解:

- 它提交的是 snapshot 生命周期状态
- 它提交的是本地 upperdir 的使用量
- 它不是把远程 blob “转存成已解包 layer”

所以在 Nydus 里，`Commit()` 保留了 containerd snapshotter 的通用语义，但远端数据仍然保持按需访问模式。

相关代码:

- `nydus-snapshotter/snapshot/snapshot.go`

---

## 七、`Remove()`：回收的不只是目录，还有远程实例状态

`Remove()` 在 Nydus 中比普通 overlayfs snapshotter 更重。

它除了:

- 从存储里删除 snapshot key
- 删除 snapshot 目录

还会根据模式处理:

- 卸载 Nydus 远程挂载
- 解除 RAFS instance 与 daemon 的关联
- 在引用归零时销毁 daemon
- 回收 tarfs / blockdev 状态
- 在 `syncRemove` 下做即时清理

因此 `Remove()` 回收的不只是本地目录树，更是:

> 一个远程文件系统实例的生命周期状态。

相关代码:

- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/pkg/filesystem/fs.go`

---

## 八、和普通 overlayfs snapshotter 的关键分叉点

如果要把这条调用链与普通 overlayfs snapshotter 做对比，可以压缩成下面几句话:

- 普通 overlayfs snapshotter 假设每一层都要本地 unpack
- `nydus-snapshotter` 在 `Prepare()` 中先判断层是否应该被 unpack
- 对 Nydus 镜像，真正重要的是先找到 bootstrap 并实例化远程 lower layer
- 最终 runtime 看到的仍是 overlay mount，但 lowerdir 的来源已经变成 Nydus 文件系统视图

因此它不是改写了 containerd 的 snapshotter 协议，而是:

> 在标准 snapshotter 调用链内部，替换了 lower layer 的构造方式。

---

## 本层关键代码位置

- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/snapshot/process.go`
- `nydus-snapshotter/pkg/label/label.go`

---

## 本层结论

第二层的关键结论是:

> `nydus-snapshotter` 借用 containerd 标准的 `Prepare -> Mounts -> Commit -> Remove` 调用链，在 `Prepare()` 这一步把“远程 lower layer 实例化”注入进容器 rootfs 的构建过程里。
