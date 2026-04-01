# Nydus Snapshotter 第四层：从 mount slice 到容器 rootfs

## 本层回答的问题

当 `nydus-snapshotter` 已经准备好了 lower layer，并返回一组 mount slice 之后，containerd、shim 和 runtime 是如何把它变成容器最终可见的 rootfs 的？

这一层要回答的是:

> Nydus 是怎样嵌入 containerd 原本的 rootfs 组装流程的？

---

## 一、先抓住这一层的本质

Nydus 并没有让 containerd 学会一种全新的 rootfs 组装协议。  
从 runtime 的视角看，最终消费的依然是常见 mount 语义:

- `bind`
- `overlay`
- `fuse.nydus-overlayfs`

因此这一层的关键不是“containerd 认识了 Nydus 文件系统”，而是:

> snapshotter 返回的 lowerdir，已经不再是普通解包目录，而是 Nydus 准备好的远程文件系统视图。

---

## 二、`mountRemote()` 返回的仍然是 overlay 语义

`mountRemote()` 会构造这些核心 mount option:

- `lowerdir=...`
- `upperdir=...`
- `workdir=...`
- 可选 `volatile`

然后把它们返回给 containerd。

关键代码:

- `nydus-snapshotter/snapshot/snapshot.go`

这说明 containerd/runtime 看到的仍然是“overlay rootfs 组装模型”。

真正的区别在于:

- 普通 overlayfs snapshotter 的 `lowerdir` 指向本地已解包 layer
- `nydus-snapshotter` 的 `lowerdir` 指向 Nydus lower layer

因此 Nydus 是替换了 lower layer 的来源，而不是替换了 rootfs 的组装方式。

---

## 三、默认路径：containerd 把它当普通 overlay mount 消费

如果没有启用:

- `enableNydusOverlayFS`
- `enableKataVolume`

那么 `mountRemote()` 会直接返回标准:

- `Type: overlay`
- `Source: overlay`
- `Options: lowerdir/upperdir/workdir`

也就是说，在最普通的运行路径里:

- snapshotter 负责把 lowerdir 准备好
- containerd/shim 继续按原有 overlay 方式挂 rootfs
- runtime 对 Nydus 是基本无感的

因此这条默认路径可以概括成:

> Nydus 在 snapshotter 侧完成接入，runtime 侧继续使用原有 overlay 模型。

---

## 四、`nydus-overlayfs` helper：为标准 mount 流程携带额外 Nydus 信息

有些场景下，snapshotter 需要把更多 Nydus 私有上下文传给后续执行方。  
这时它会返回:

- `Type: fuse.nydus-overlayfs`
- `Source: overlay`
- `Options: overlay options + extraoption=...`

相关代码:

- `nydus-snapshotter/snapshot/mount_option.go`

`extraoption` 里会编码这些信息:

- bootstrap 路径
- daemon 配置内容
- snapshotdir
- 文件系统版本

这意味着 `nydus-overlayfs` 的职责不是充当真正的文件系统，而是:

> 作为一个 mount helper / 参数转运器，把 Nydus 私有配置通过标准 mount slice 往下传。

---

## 五、runc 路径：helper 过滤私有参数后执行真正的 overlay mount

在 runc/containerd-shim-runc-v2 路径里，`nydus-overlayfs` 的作用很直接:

1. 解析 `fuse.nydus-overlayfs` mount 请求
2. 过滤掉 `extraoption=` 和 Kata volume 选项
3. 保留真实的 `lowerdir/upperdir/workdir`
4. 最后自己执行一次 overlay mount syscall

相关代码:

- `nydus-snapshotter/cmd/nydus-overlayfs/main.go`

也就是说，对 runc 来说，实际调用链近似于:

```text
containerd -> mount.fuse -> nydus-overlayfs -> mount overlay -> rootfs ready
```

这说明在 runc 场景里:

- `extraoption` 只是透传上下文
- 最终 rootfs 仍然是 overlayfs

---

## 六、Kata 路径：mount slice 可能继续被 shim 解析和转发

Kata 场景更特殊。  
这里 snapshotter 可能不只是返回宿主机 overlay mount，而是把额外信息通过:

- `extraoption`
- `io.katacontainers.volume=...`

编码进 mount slice 中。

相关代码:

- `nydus-snapshotter/snapshot/mount_option.go`
- `docs/nydus-overlayfs.md`

这意味着对 Kata 来说，mount slice 不一定立即落成宿主机上的最终 rootfs，而可能继续被:

- `containerd-shim-kata-v2`

解析，然后把 Nydus 相关信息继续传给 guest runtime 或 VM 内部的 Nydus 组件。

因此在 Kata 路径里，snapshotter 不只是返回挂载参数，它还承担:

> 运行时跨边界元信息编码

的职责。

---

## 七、`proxy` / Kata volume 说明 snapshotter 还在承担 mount 语义扩展

在 `proxy` 或 Kata virtual volume 场景里，snapshotter 返回的 mount 信息里可能还包括:

- proxy mode annotation
- CRI 层 digest
- image/layer raw block 相关信息
- dm-verity 相关 volume 描述

相关代码:

- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/snapshot/mount_option.go`

这一层说明:

> Nydus snapshotter 不只是返回 mount list，它还在把 rootfs 构造过程需要的附加语义打包后传给下游 runtime。

---

## 八、这一层的职责分工

如果把这一层的角色切分清楚，可以总结成:

### 8.1 `nydus-snapshotter`

负责:

- 决定 lowerdir 指向哪里
- 决定返回 `overlay` 还是 `fuse.nydus-overlayfs`
- 需要时把 Nydus 私有参数编码进 mount options

### 8.2 `containerd`

负责:

- 接收 snapshotter 返回的 mount slice
- 把 mount slice 传给 shim / runtime

### 8.3 shim / mount helper

负责:

- 根据 mount type 选择实际执行路径
- runc 场景执行 overlay mount
- Kata 场景继续解释额外参数

### 8.4 runtime

负责:

- 基于最终 mount 结果启动容器进程

---

## 本层关键代码位置

- `nydus-snapshotter/snapshot/snapshot.go`
- `nydus-snapshotter/snapshot/mount_option.go`
- `nydus-snapshotter/cmd/nydus-overlayfs/main.go`
- `docs/nydus-overlayfs.md`

---

## 本层结论

第四层的关键结论是:

> Nydus 并没有替换 containerd 的 rootfs 组装协议，它是通过 snapshotter 返回的 mount slice，把“远程 lower layer”无缝嵌进了 containerd 原本的 overlay rootfs 流程。
