# Cloud Hypervisor + Nydus 配置与优化指南

## 适用范围

本文面向当前 Kata Containers 主线代码中的 `Cloud Hypervisor + Nydus` 场景，整理如何在 Kata 中启用 Nydus，以及如何配置相关优化项。

目标是回答三个问题：

1. 在 Kata 中如何启用 `Nydus`
2. 哪些配置属于 Kata，哪些前提在 Kata 之外
3. 与性能直接相关的优化项该如何调

本文以当前仓库代码和文档为依据。

---

## 一、先说结论

在 Kata 中，`Nydus` 不是单独一个 `enable_nydus = true` 开关，而是由三部分共同组成：

1. `containerd + nydus-snapshotter` 负责提供 Nydus 类型 rootfs
2. Kata 配置 `shared_fs = "virtio-fs-nydus"`
3. `Cloud Hypervisor` 通过 `nydusd` 作为特殊的 virtio-fs daemon 接入共享文件系统

所以你真正要做的是：

- 在容器运行时链路上启用 `nydus-snapshotter`
- 在 Kata `clh` 配置里切到 `virtio-fs-nydus`
- 再根据 workload 调整 `virtio_fs_cache`、`virtio_fs_cache_size`、预取文件列表等优化项

---

## 二、Kata 侧最小配置

## 2.1 Go runtime 配置

配置模板入口：

- `src/runtime/config/configuration-clh.toml.in`

核心配置项如下：

```toml
[hypervisor.clh]
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"

virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
virtio_fs_extra_args = []
```

### 配置项含义

- `shared_fs = "virtio-fs-nydus"`
  - 告诉 Kata 不再使用普通 `virtio-fs`，而是走 Nydus 共享文件系统路径
- `virtio_fs_daemon = "/usr/local/bin/nydusd"`
  - 指向 `nydusd` 可执行文件，而不是普通 `virtiofsd`
- `virtio_fs_cache`
  - 控制 guest 侧 virtio-fs cache 策略
- `virtio_fs_cache_size`
  - 控制 DAX cache 大小，单位 MiB
- `virtio_fs_extra_args`
  - 透传给 `nydusd`

代码依据：

- `src/runtime/config/configuration-clh.toml.in`
- `src/runtime/virtcontainers/clh.go`

## 2.2 runtime-rs 配置

配置模板入口：

- `src/runtime-rs/config/configuration-cloud-hypervisor.toml.in`

对应配置如下：

```toml
[hypervisor.cloud-hypervisor]
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"

virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
virtio_fs_extra_args = []
```

代码依据：

- `src/runtime-rs/config/configuration-cloud-hypervisor.toml.in`

---

## 三、Kata 之外的前提条件

Kata 本身不负责把普通 OCI 镜像转换成 Nydus rootfs。它负责的是“消费已经是 Nydus 语义的 rootfs”。

因此在 Kata 之外，至少还需要：

1. `containerd`
2. `nydus-snapshotter`
3. `nydusd`
4. Nydus 镜像或能产出 Nydus rootfs 的镜像链路

仓库 how-to 文档给出的前提是：

1. 使用 `nydus` 最新分支
2. 部署 `nydus` containerd 环境
3. 启动 `nydus-snapshotter` 时启用 `enable_nydus_overlayfs`
4. 使用 Kata 最新代码并配置 `virtio-fs-nydus`

文档依据：

- `docs/how-to/how-to-use-virtio-fs-nydus-with-kata.md`

换句话说，Kata 不是 Nydus 的上游生产者，而是 Nydus rootfs 的运行时承载者。

## 3.1 `enable_nydus_overlayfs` 如何设置

这个开关不在 Kata 配置里，而在 `nydus-snapshotter` 自己的配置文件里。

典型做法是在 `containerd-nydus-grpc` 使用的 TOML 配置中设置：

```toml
[snapshot]
enable_nydus_overlayfs = true
nydus_overlayfs_path = "nydus-overlayfs"
```

一个更完整的最小示例可以写成：

```toml
version = 1
address = "/run/containerd-nydus/containerd-nydus-grpc.sock"

[daemon]
nydusd_config = "/etc/nydus/nydusd-config.fusedev.json"
nydusd_path = "/usr/local/bin/nydusd"
nydusimage_path = "/usr/local/bin/nydus-image"
fs_driver = "fusedev"

[snapshot]
enable_nydus_overlayfs = true
nydus_overlayfs_path = "nydus-overlayfs"
enable_kata_volume = false
sync_remove = false
```

常见使用方式是让 `containerd-nydus-grpc` 显式加载该配置文件，例如：

```bash
containerd-nydus-grpc \
  --config /etc/nydus/config.toml \
  --nydusd-config /etc/nydus/nydusd-config.json
```

如果你使用 systemd，通常就是修改 `nydus-snapshotter` 对应 service 的 `ExecStart`，确保它带上 `--config /etc/nydus/config.toml`，然后重启：

```bash
sudo systemctl restart nydus-snapshotter
sudo systemctl restart containerd
```

### 这一项的作用

`enable_nydus_overlayfs = true` 的含义是：

- 让 `nydus-snapshotter` 使用 `nydus-overlayfs`
- 从而以 overlayfs 相关方式把 Nydus rootfs 暴露给下游运行时

这也是 Kata 文档在 `Cloud Hypervisor + Nydus` 场景中明确要求打开该项的原因。

### 来源

- Kata 仓库 how-to 明确要求：
  - “Start `nydus-snapshotter` with `enable_nydus_overlayfs` enabled”
  - 文件：`docs/how-to/how-to-use-virtio-fs-nydus-with-kata.md`
- `nydus-snapshotter` 官方示例配置包含：
  - `enable_nydus_overlayfs = false`
  - `nydus_overlayfs_path = "nydus-overlayfs"`
  - 来源：<https://raw.githubusercontent.com/containerd/nydus-snapshotter/main/misc/snapshotter/config.toml>
- `nydus-snapshotter` 官方 README 说明了通过 `--config /etc/nydus/config.toml` 启动：
  - 来源：<https://github.com/containerd/nydus-snapshotter>

## 3.2 `containerd + nydus-snapshotter + Kata` 的完整联动配置

如果你希望整条链路真正联起来，仅有 `nydus-snapshotter` 配置还不够，还需要在 `containerd` 中：

1. 注册 `nydus-snapshotter` 为 `proxy snapshotter`
2. 让 CRI 或对应 runtime 使用 `nydus` snapshotter
3. 保证实际运行容器时选择 Kata runtime

一个典型的 `containerd` 配置片段如下：

```toml
[plugins."io.containerd.grpc.v1.cri".containerd]
  disable_snapshot_annotations = false
  discard_unpacked_layers = false

[proxy_plugins.nydus]
  type = "snapshot"
  address = "/run/containerd-nydus/containerd-nydus-grpc.sock"

[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata]
  runtime_type = "io.containerd.kata.v2"
  snapshotter = "nydus"
```

### 配置项说明

- `disable_snapshot_annotations = false`
  - 允许 snapshotter 相关注解继续向下游传递
- `discard_unpacked_layers = false`
  - 避免把下游还需要使用的信息过早丢弃
- `[proxy_plugins.nydus]`
  - 把 `containerd-nydus-grpc` 注册成一个名为 `nydus` 的 snapshotter
- `[...runtimes.kata]`
  - 指定某个 Kata runtime 在 CRI 路径下默认使用 `nydus` snapshotter

### 关于 runtime 名称

这里的 `kata` 只是示例名。你本机实际可能是：

- `kata`
- `kata-clh`
- `kata-qemu`
- 发行版自定义名字

你需要把节名替换成你环境里真实的 runtime 名称，例如：

```toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-clh]
  runtime_type = "io.containerd.kata.v2"
  snapshotter = "nydus"
```

如果你的 `containerd` 版本较旧，不支持 runtime-specific snapshotter，则还可能需要设置全局：

```toml
[plugins."io.containerd.grpc.v1.cri".containerd]
  snapshotter = "nydus"
```

修改后重启：

```bash
sudo systemctl restart containerd
sudo systemctl restart nydus-snapshotter
```

### 来源

- Kata 仓库 how-to 中给出了 `proxy_plugins.nydus` 和 `snapshotter = "nydus"` 的配置方式：
  - 文件：`docs/how-to/how-to-pull-images-in-guest-with-kata.md`
- Kata 仓库安装文档给出了 containerd 中 Kata runtime 的典型注册方式：
  - `runtime_type = "io.containerd.kata.v2"`
  - 文件：`docs/install/container-manager/containerd/containerd-install.md`

## 3.3 让运行请求真正走到 `nydus + kata` 链路

配置文件改完之后，实际发起 workload 时也要确保：

1. 选择 Kata runtime
2. 选择 `nydus` snapshotter，或者由 runtime-specific snapshotter 自动落到 `nydus`

### `crictl` 路径

仓库 how-to 对 `virtio-fs-nydus` 的例子是：

```bash
crictl run -r kata nydus-container.yaml nydus-sandbox.yaml
```

其中 `nydus-sandbox.yaml` 会带：

```yaml
annotations:
  "io.containerd.osfeature": "nydus.remoteimage.v1"
```

来源：

- `docs/how-to/how-to-use-virtio-fs-nydus-with-kata.md`

### `nerdctl` 路径

如果你走 `nerdctl`，仓库设计文档给了一个直接示例：

```bash
nerdctl run \
  --runtime io.containerd.kata.v2 \
  --snapshotter nydus \
  --label io.kubernetes.cri.image-name=docker.io/library/busybox:latest \
  --rm docker.io/library/busybox:latest uname -r
```

来源：

- `docs/design/kata-guest-image-management-design.md`

这也说明“完整联动配置”不仅是把服务启动起来，还包括：

- `containerd` 能找到 `nydus` snapshotter
- runtime 请求最终选择 Kata
- workload 请求最终落到 `nydus` snapshotter

---

## 四、为什么只改 Kata 配置还不够

从代码看，Kata 识别 Nydus rootfs 的方式不是“看到某个全局开关”，而是识别具体的 rootfs 类型和额外 mount 信息。

比如：

- rootfs 类型：`fuse.nydus-overlayfs`
- 额外参数：`extraoption=...`

这些信息最终会被解析成：

- `source`
- `config`
- `snapshotdir`
- `fs_version`

代码依据：

- `src/libs/kata-types/src/mount.rs`

这意味着如果上游 snapshotter 没有把 rootfs 以 Nydus 形式交给 Kata，那么 Kata 侧即使改成了 `virtio-fs-nydus`，也不会自动把普通镜像变成 Nydus。

---

## 五、最小可用配置思路

如果你的目标是先跑通 `Cloud Hypervisor + Nydus`，建议按下面顺序配置。

## 5.1 第一步：启用 nydus-snapshotter

确保 `containerd` 使用 `nydus-snapshotter`，并且它已经能提供 Nydus rootfs。

仓库 how-to 中明确要求：

- 启动 `nydus-snapshotter` 时启用 `enable_nydus_overlayfs`

这是基础前提。

## 5.2 第二步：Kata 切换到 Cloud Hypervisor

确保运行时使用的是 `clh` 或 runtime-rs 对应的 `cloud-hypervisor` 配置。

## 5.3 第三步：把 shared-fs 切到 Nydus 模式

Go runtime：

```toml
[hypervisor.clh]
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"
```

runtime-rs：

```toml
[hypervisor.cloud-hypervisor]
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"
```

## 5.4 第四步：先使用保守优化项跑通

推荐先用：

```toml
virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
virtio_fs_extra_args = []
```

这是一组比较稳妥的初始值。

---

## 六、核心优化项怎么理解

## 6.1 `virtio_fs_cache`

配置入口：

- `src/runtime/config/configuration-clh.toml.in`
- `src/runtime-rs/config/configuration-cloud-hypervisor.toml.in`

可选值包括：

- `never`
- `metadata`
- `auto`
- `always`

### 建议理解

- `never`
  - 最保守
  - 元数据和数据都尽量不缓存
  - 一般性能最差，但语义最稳
- `metadata`
  - 只缓存元数据
  - 数据不缓存
  - 比 `never` 稍好，但对数据路径优化有限
- `auto`
  - 比较适合作为默认起点
  - 在性能和一致性之间做折中
- `always`
  - 最激进
  - 通常性能最好
  - 但缓存语义也最强，需要你自己确认 workload 是否能接受

### 实操建议

如果你现在主要目标是：

- 先跑通功能：用 `auto`
- 压冷启动性能：在跑通后尝试 `always`

---

## 6.2 `virtio_fs_cache_size`

这个值控制 DAX cache 大小，单位是 MiB。

代码上很关键的一点是：

- 在 guest 侧是否使用 DAX，不只看 `virtio_fs_cache`
- 还看 `virtio_fs_cache_size != 0`

`kata-agent` 的逻辑是：

- 只有当 cache 模式不是 `never` / `metadata`
- 且 `virtio_fs_cache_size != 0`
- 才会给 virtio-fs 挂载加上 DAX 相关选项

代码依据：

- `src/runtime/virtcontainers/kata_agent.go`

### 实操建议

- 如果你想让 CH + Nydus 路径利用 DAX，就不要把它设成 `0`
- 一个比较稳妥的起点是 `1024`
- 对大镜像或热点文件较多的场景，可以尝试 `2048`

示例：

```toml
virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
```

或

```toml
virtio_fs_cache = "always"
virtio_fs_cache_size = 2048
```

---

## 6.3 `virtio_fs_extra_args`

这个字段会透传给 `nydusd`。

代码依据：

- `src/runtime/virtcontainers/clh.go`
- `src/runtime-rs/config/configuration-cloud-hypervisor.toml.in`

它适合用来做两类事情：

1. 打开更详细的日志
2. 传递 Nydus 自身支持的 daemon 参数

最简单的用途是调试：

```toml
virtio_fs_extra_args = ["--log-level=debug"]
```

如果不确定参数兼容性，建议一开始留空：

```toml
virtio_fs_extra_args = []
```

---

## 七、Nydus 专项优化项：预取文件列表

除了 shared-fs 本身的 cache/DAX 参数，Nydus 在 runtime-rs 路径里还支持一个更直接的优化项：

- `prefetch_files.list`

它通过 sandbox annotation 注入：

- `io.katacontainers.config.hypervisor.prefetch_files.list`

代码依据：

- `src/libs/kata-types/src/annotations/mod.rs`
- `src/runtime-rs/crates/resource/src/rootfs/nydus_rootfs.rs`

### 它做什么

runtime-rs 会读取这个注解对应的 host 文件路径，并将它作为 `prefetch_list_path` 传给 `rafs_mount(...)`。

作用是：

- 在整体懒加载模式不变的前提下
- 对已知热点文件做预热
- 降低首访抖动

### 配置示例

如果你走的是支持该注解的路径，可以在 sandbox annotations 中加：

```yaml
annotations:
  io.katacontainers.config.hypervisor.prefetch_files.list: "/path/to/prefetch_file.list"
```

### 什么时候值得开

适合以下场景：

- 冷启动后会立刻访问一批固定文件
- 应用首包时延敏感
- 镜像大但真正首屏热点文件较少

---

## 八、也可以通过注解动态覆盖的项

当前代码支持通过注解动态覆盖一部分 hypervisor 共享文件系统配置，包括：

- `shared_fs`
- `virtio_fs_daemon`
- `virtio_fs_cache`
- `virtio_fs_cache_size`
- `virtio_fs_extra_args`
- `prefetch_files.list`

代码依据：

- `src/libs/kata-types/src/annotations/mod.rs`

这意味着你可以：

- 保持主配置文件使用比较保守的默认值
- 对特定 Pod / Sandbox 单独调高 cache、加预取列表或切换 daemon 参数

这是比较适合做实验和 A/B 对比的方式。

---

## 九、推荐的三档配置

## 9.1 最小可用档

适合先跑通链路。

```toml
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"
virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
virtio_fs_extra_args = []
```

## 9.2 冷启动优化档

适合优先关注镜像冷启动。

```toml
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"
virtio_fs_cache = "always"
virtio_fs_cache_size = 2048
virtio_fs_extra_args = []
```

并配合：

- `io.katacontainers.config.hypervisor.prefetch_files.list`

## 9.3 调试排障档

适合先定位稳定性和链路问题。

```toml
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"
virtio_fs_cache = "metadata"
virtio_fs_cache_size = 0
virtio_fs_extra_args = ["--log-level=debug"]
```

这组配置性能不一定最好，但更利于把问题定位清楚。

---

## 十、容易误解的几点

## 10.1 `virtio_fs_daemon` 在 Nydus 场景下不是普通 virtiofsd

当 `shared_fs = "virtio-fs-nydus"` 时，Kata 会把 `virtio_fs_daemon` 当作 `nydusd` 路径使用。

所以这里不能继续指向普通 `virtiofsd`。

## 10.2 只改 Kata 配置不会自动让普通镜像变成 Nydus

必须由 `nydus-snapshotter` 或上游链路交付 Nydus rootfs。

## 10.3 `virtio_fs_cache_size = 0` 会影响 DAX 路径

即使你把 cache 模式改成 `auto/always`，如果 cache size 为 `0`，guest 侧也不会真正走 DAX。

## 10.4 预取文件列表不是基础必配项

`prefetch_files.list` 是优化项，不是启用 Nydus 的前提。

先跑通，再加预取，顺序更合理。

---

## 十一、建议的落地顺序

如果你现在要在 `Cloud Hypervisor` 场景中启用 Nydus，建议按下面顺序做：

1. 先确认 `containerd + nydus-snapshotter` 已经跑通
2. 确认 `nydusd` 二进制路径可用
3. 在 Kata `clh` 配置里改成 `shared_fs = "virtio-fs-nydus"`
4. 把 `virtio_fs_daemon` 指向 `nydusd`
5. 先用 `virtio_fs_cache = "auto"`、`virtio_fs_cache_size = 1024`
6. 跑通后再测试 `always + 更大 cache size`
7. 最后针对热点 workload 引入 `prefetch_files.list`

这是当前主线代码下最稳妥的实践顺序。

---

## 十二、最终结论

在 Kata 里启用 `Cloud Hypervisor + Nydus`，最核心的配置只有两项：

```toml
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/path/to/nydusd"
```

但真正决定性能表现的，则主要是下面三项：

```toml
virtio_fs_cache
virtio_fs_cache_size
virtio_fs_extra_args
```

如果你还需要进一步压冷启动首包延迟，再追加：

- `io.katacontainers.config.hypervisor.prefetch_files.list`

也就是说：

- `shared_fs + daemon` 决定“能不能跑”
- `cache + dax + prefetch` 决定“跑得快不快”

这就是当前主线代码中 `Cloud Hypervisor + Nydus` 的配置和优化重点。
