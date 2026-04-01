# Cloud Hypervisor + Nydus 简化配置指南

## 使用目标

这是一份最小化、按层次展开的配置指南，只保留 `Cloud Hypervisor + Nydus` 跑通所需的关键配置和少量优化项。

配置分四层：

1. `containerd`
2. `nydus-snapshotter`
3. `Kata + Cloud Hypervisor`
4. 可选优化项

---

## 一、containerd 层

作用：让 `containerd` 能识别并使用 `nydus-snapshotter`。

编辑 `/etc/containerd/config.toml`，加入：

```toml
[plugins."io.containerd.grpc.v1.cri".containerd]
  disable_snapshot_annotations = false
  discard_unpacked_layers = false

[proxy_plugins.nydus]
  type = "snapshot"
  address = "/run/containerd-nydus/containerd-nydus-grpc.sock"
```

如果你希望某个 Kata runtime 默认使用 `nydus` snapshotter，再加：

```toml
[plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-clh]
  runtime_type = "io.containerd.kata.v2"
  snapshotter = "nydus"
```

说明：

- `kata-clh` 只是示例名，替换成你本机真实的 Kata runtime 名称
- 如果 containerd 太旧，不支持 runtime-specific snapshotter，可以直接把全局 `snapshotter` 设成 `nydus`

修改后重启：

```bash
sudo systemctl restart containerd
```

来源：

- [how-to-pull-images-in-guest-with-kata.md](/home/test/lyq/Micro-VM/kata-containers/docs/how-to/how-to-pull-images-in-guest-with-kata.md)
- [containerd-install.md](/home/test/lyq/Micro-VM/kata-containers/docs/install/container-manager/containerd/containerd-install.md)

---

## 二、nydus-snapshotter 层

作用：让 `nydus-snapshotter` 以 overlayfs 方式提供 Nydus rootfs。

编辑 `/etc/nydus/config.toml`，至少包含：

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

启动方式示例：

```bash
containerd-nydus-grpc \
  --config /etc/nydus/config.toml \
  --nydusd-config /etc/nydus/nydusd-config.json
```

如果用 systemd：

```bash
sudo systemctl restart nydus-snapshotter
```

说明：

- `enable_nydus_overlayfs = true` 是 Kata 文档明确要求打开的项
- `nydusd_path` 必须指向真实存在的 `nydusd`

来源：

- [how-to-use-virtio-fs-nydus-with-kata.md](/home/test/lyq/Micro-VM/kata-containers/docs/how-to/how-to-use-virtio-fs-nydus-with-kata.md)
- <https://raw.githubusercontent.com/containerd/nydus-snapshotter/main/misc/snapshotter/config.toml>
- <https://github.com/containerd/nydus-snapshotter>

---

## 三、Kata + Cloud Hypervisor 层

作用：让 Kata 在 `clh` 场景下使用 `nydusd` 作为共享文件系统后端。

如果你用 Go runtime，改 Kata 的 `clh` 配置：

```toml
[hypervisor.clh]
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"

virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
virtio_fs_extra_args = []
```

如果你用 runtime-rs，改对应配置：

```toml
[hypervisor.cloud-hypervisor]
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"

virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
virtio_fs_extra_args = []
```

说明：

- `shared_fs = "virtio-fs-nydus"` 是启用 Kata Nydus 路径的核心项
- `virtio_fs_daemon` 在这个场景下应当指向 `nydusd`，不是普通 `virtiofsd`
- `auto + 1024` 适合作为第一版稳妥配置

来源：

- [configuration-clh.toml.in](/home/test/lyq/Micro-VM/kata-containers/src/runtime/config/configuration-clh.toml.in)
- [configuration-cloud-hypervisor.toml.in](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/config/configuration-cloud-hypervisor.toml.in)
- [clh.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/clh.go)

---

## 四、运行请求层

作用：确保 workload 真正走到 `kata + nydus` 这条链路。

### `crictl` 示例

```bash
crictl run -r kata nydus-container.yaml nydus-sandbox.yaml
```

`nydus-sandbox.yaml` 里至少带：

```yaml
annotations:
  "io.containerd.osfeature": "nydus.remoteimage.v1"
```

### `nerdctl` 示例

```bash
nerdctl run \
  --runtime io.containerd.kata.v2 \
  --snapshotter nydus \
  --label io.kubernetes.cri.image-name=docker.io/library/busybox:latest \
  --rm docker.io/library/busybox:latest uname -r
```

说明：

- `crictl` 路径通常通过 runtime 名称和 sandbox 注解触发
- `nerdctl` 路径最直接，显式指定 `--runtime` 和 `--snapshotter`

来源：

- [how-to-use-virtio-fs-nydus-with-kata.md](/home/test/lyq/Micro-VM/kata-containers/docs/how-to/how-to-use-virtio-fs-nydus-with-kata.md)
- [kata-guest-image-management-design.md](/home/test/lyq/Micro-VM/kata-containers/docs/design/kata-guest-image-management-design.md)

---

## 五、可选优化项

### 1. 更激进的 virtio-fs cache

```toml
virtio_fs_cache = "always"
virtio_fs_cache_size = 2048
```

作用：优先提升镜像访问性能。

### 2. 调试模式

```toml
virtio_fs_cache = "metadata"
virtio_fs_cache_size = 0
virtio_fs_extra_args = ["--log-level=debug"]
```

作用：先排查链路，再做性能优化。

### 3. 预取热点文件

给 sandbox 增加注解：

```yaml
annotations:
  io.katacontainers.config.hypervisor.prefetch_files.list: "/path/to/prefetch_file.list"
```

作用：降低首访抖动。

来源：

- [annotations/mod.rs](/home/test/lyq/Micro-VM/kata-containers/src/libs/kata-types/src/annotations/mod.rs)
- [nydus_rootfs.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/resource/src/rootfs/nydus_rootfs.rs)

---

## 六、最小跑通清单

如果你只想先跑通，按这个顺序做：

1. 配好 `containerd` 的 `proxy_plugins.nydus`
2. 配好 `nydus-snapshotter`，开启 `enable_nydus_overlayfs = true`
3. 把 Kata `clh` 配成 `shared_fs = "virtio-fs-nydus"`
4. `virtio_fs_daemon` 指向 `nydusd`
5. 用 `crictl` 或 `nerdctl --snapshotter nydus` 发起 workload

最小 Kata 配置就是：

```toml
shared_fs = "virtio-fs-nydus"
virtio_fs_daemon = "/usr/local/bin/nydusd"
virtio_fs_cache = "auto"
virtio_fs_cache_size = 1024
virtio_fs_extra_args = []
```
