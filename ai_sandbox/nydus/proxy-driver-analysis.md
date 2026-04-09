# Proxy Driver 深度解析

## 概述

Proxy Driver 是 nydus-snapshotter 的一种 `fs_driver` 模式，专为 Kata Containers 设计。它的核心思想是：**snapshotter 不启动 nydusd，而是把 Nydus 镜像信息"打包"进 Kata Virtual Volume，交给 Guest VM 内部的 nydusd 去处理。**

---

## 1. fs_driver 的全部选项

在 nydus-snapshotter 的配置中（`config/config.go:115-118`），共有 5 种 fs_driver：

| fs_driver | 说明 | nydusd 位置 | 适用场景 |
|-----------|------|------------|---------|
| `fusedev` | Host 上启动 nydusd，通过 FUSE 提供文件系统 | Host | runc 容器 |
| `fscache` | Host 上启动 nydusd，通过 EROFS+fscache 提供文件系统 | Host | 高性能容器（内核 >= 5.19） |
| `blockdev` | Host 上启动 nydusd，通过块设备提供文件系统 | Host | 块设备场景 |
| `nodev` | 无守护进程模式 | 无 | 特殊场景 |
| **`proxy`** | **不启动 nydusd，交给 Guest VM 内部处理** | **Guest VM 内部** | **Kata Containers 大规模部署** |

---

## 2. Proxy Driver 与其他模式的本质区别

### 传统模式（fusedev / fscache / blockdev）

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│ containerd  │────→│ snapshotter │────→│  Host nydusd  │ ← nydusd 在宿主机
└─────────────┘     └─────────────┘     └──────┬───────┘
                                                  │ FUSE / fscache
                                                  ▼
                                           ┌─────────────┐
                                           │ Guest 容器   │
                                           └─────────────┘
```

- snapshotter 负责拉取镜像、启动 nydusd、管理生命周期
- nydusd 运行在 Host 上，为 Guest 提供文件系统服务
- 数据路径：Guest → Host nydusd → Registry（多一跳）

### Proxy Driver 模式

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│ containerd  │────→│ snapshotter │────→│ Kata 运行时   │
└─────────────┘     └─────────────┘     └──────┬───────┘
       │                                        │
       │  snapshotter 不启动 nydusd！            │
       │  而是把镜像信息塞进 mount options        ▼
       │                                ┌──────────────────┐
       │                                │    Guest VM       │
       │                                │ ┌──────────────┐ │
       │   ─── Kata Virtual Volume ───→ │ │  Guest nydusd │ │ ← nydusd 在 VM 内
       │                                │ └──────────────┘ │
       │                                │ ┌──────────────┐ │
       │                                │ │  容器进程     │ │
       │                                │ └──────────────┘ │
       │                                └──────────────────┘
```

- snapshotter 只负责编码镜像信息，不启动任何 nydusd
- nydusd 运行在 Guest VM 内部，自己从 Registry 拉取数据
- 数据路径：Guest nydusd → Registry（直连，少一跳）

**一句话总结：传统模式是 Host 提供文件服务，Proxy 模式是让 Guest 自己拉取镜像并提供文件服务。**

---

## 3. Proxy Driver 的工作流程（逐步拆解）

### 第一步：snapshotter 配置不启动 nydusd

配置文件 `config-proxy.toml`（`misc/snapshotter/config-proxy.toml`）：

```toml
version = 1
root = "/var/lib/containerd/io.containerd.snapshotter.v1.nydus"
address = "/run/containerd-nydus/containerd-nydus-grpc.sock"
daemon_mode = "none"      # ← 不启动任何 nydusd 守护进程

[daemon]
fs_driver = "proxy"       # ← proxy 模式

[snapshot]
enable_kata_volume = true  # ← 启用 Kata Virtual Volume 注入
```

官方文档（`docs/setup_snapshotter_by_daemonset.md:131`）明确说明：

> **NOTE:** The fs_driver (`blockdev` and `proxy`) do not need nydusd, so they do not need nydusd config.

### 第二步：容器创建时 snapshotter 调用 mountProxy

当 containerd 创建容器并调用 snapshotter 的 `Mounts()` 时，代码路径如下（`snapshot/snapshot.go:474-477`）：

```go
func (o *snapshotter) Mounts(ctx context.Context, key string) ([]mount.Mount, error) {
    snap, err := snapshot.GetSnapshot(ctx, o.ms, key)

    // 判断是否应该走 proxy 模式
    if treatAsProxyDriver(info.Labels) {
        return o.mountProxy(ctx, *snap)
    }
    // ... 其他模式
}
```

`mountProxy()` 函数（`snapshot/snapshot.go:1040-1082`）构造 mount 信息：

```go
func (o *snapshotter) mountProxy(ctx context.Context, s storage.Snapshot) ([]mount.Mount, error) {
    // 1. 构造 overlayfs 的标准选项
    overlayOptions := []string{
        fmt.Sprintf("workdir=%s", o.workPath(s.ID)),
        fmt.Sprintf("upperdir=%s", o.upperPath(s.ID)),
    }

    // 2. 构造 lowerdir（父 snapshot 的 upper 路径）
    parentPaths := make([]string, 0)
    for _, id := range s.ParentIDs {
        parentPaths = append(parentPaths, o.upperPath(id))
    }
    overlayOptions = append(overlayOptions, fmt.Sprintf("lowerdir=%s", strings.Join(parentPaths, ":")))

    // 3. 把 Nydus 镜像信息编码为 Kata Virtual Volume 选项
    options, err := o.mountWithProxyVolume(rafs.Rafs{
        FsDriver:    config.GetFsDriver(),   // "proxy"
        Annotations: make(map[string]string),
    })
    overlayOptions = append(overlayOptions, options...)

    // 4. 返回 fuse.nydus-overlayfs 类型的 mount
    return []mount.Mount{{
        Type:    "fuse.nydus-overlayfs",
        Source:  "overlay",
        Options: overlayOptions,
    }}, nil
}
```

### 第三步：关键函数 mountWithProxyVolume

这个函数（`snapshot/mount_option.go:170-190`）把 Nydus 镜像元信息打包进 Kata 能识别的 volume 描述：

```go
func (o *snapshotter) mountWithProxyVolume(rafs rafs.Rafs) ([]string, error) {
    source := rafs.Annotations[label.CRIImageRef]  // 镜像引用地址

    // 强制保证 source 非空（Kata runtime-rs 有非空校验）
    if len(source) == 0 {
        source = KataVirtualVolumeDummySource
    }

    // 把所有 annotations 编码为 key=value 格式
    for k, v := range rafs.Annotations {
        options = append(options, fmt.Sprintf("%s=%s", k, v))
    }

    // 构造 Kata Virtual Volume，类型为 "image_guest_pull"
    opt, err := o.prepareKataVirtualVolume(
        label.NydusProxyMode,                // volume 类型标记
        source,                              // 镜像引用
        KataVirtualVolumeImageGuestPullType,  // "image_guest_pull" ← 关键！
        "", options, rafs.Annotations,
    )
    return []string{opt}, nil
}
```

其中 `KataVirtualVolumeImageGuestPullType` 定义在 `snapshot/mount_option.go:320`：

```go
const (
    KataVirtualVolumeOptionName          = "io.katacontainers.volume"
    KataVirtualVolumeDirectBlockType     = "direct_block"
    KataVirtualVolumeImageRawBlockType   = "image_raw_block"
    KataVirtualVolumeLayerRawBlockType   = "layer_raw_block"
    KataVirtualVolumeImageNydusBlockType = "image_nydus_block"
    KataVirtualVolumeLayerNydusBlockType = "layer_nydus_block"
    KataVirtualVolumeImageNydusFsType    = "image_nydus_fs"
    KataVirtualVolumeLayerNydusFsType    = "layer_nydus_fs"
    KataVirtualVolumeImageGuestPullType  = "image_guest_pull"  // ← Proxy Driver 使用这个
)
```

### 第四步：Kata 运行时解析 Virtual Volume

最终返回给 containerd 的 mount options 包含类似这样的 Kata Virtual Volume 信息：

```
Type: "fuse.nydus-overlayfs"
Source: "overlay"
Options: [
    "workdir=/var/lib/.../work",
    "upperdir=/var/lib/.../upper",
    "lowerdir=/var/lib/.../parent",
    "io.katacontainers.volume={\"type\":\"image_guest_pull\",\"source\":\"registry.example.com/nginx\",...}"
]
```

Kata 运行时读取 mount options 后：

1. 识别到 `io.katacontainers.volume` 选项
2. 解析 JSON，发现 `type = "image_guest_pull"`
3. 知道需要 **在 Guest VM 内部拉取镜像**，而不是从 Host 的 rootfs 启动
4. 启动 Guest VM 时注入 Virtual Volume 配置

### 第五步：Guest VM 内部完成所有工作

```
Guest VM 启动
    │
    ▼
Kata Agent 解析 Virtual Volume
    │  type = "image_guest_pull"
    │  source = "registry.example.com/nginx"
    ▼
Guest 内部启动 nydusd
    │  配置: backend = registry, repo = nginx
    │  直接从 Registry 拉取 bootstrap + blob
    ▼
Guest 内部挂载 RAFS (FUSE)
    │
    ▼
容器进程启动，访问文件
    │  数据在 Guest 内部按需加载
    ▼
完成
```

---

## 4. Proxy Driver 的触发条件

并非所有容器都会走 proxy 路径。`treatAsProxyDriver()` 函数（`snapshot/snapshot.go:1362-1376`）定义了触发条件：

```go
func treatAsProxyDriver(labels map[string]string) bool {
    isProxyDriver := config.GetFsDriver() == config.FsDriverProxy     // 配置是否为 proxy
    isProxyLabel := label.IsNydusProxyMode(labels)                     // 镜像是否标记为 proxy
    _, isProxyImage := labels[label.CRIImageRef]                       // 是否有 CRI 镜像引用

    switch {
    case isProxyDriver && isProxyImage:
        return false  // 配置为 proxy 但这是普通 OCI 镜像 → 不走 proxy
    case isProxyDriver != isProxyLabel:
        return true   // 配置和标签不一致 → 走 proxy（兼容其他 snapshotter 准备的层）
    default:
        return false
    }
}
```

在 Prepare 流程中（`snapshot/process.go:61-138`），有两条路径会触发 proxy：

**路径 1 — 只读层标记为 proxy：**

```go
// snapshot/process.go:72-79
case config.GetFsDriver() == config.FsDriverProxy:
    if ref := labels[label.CRILayerDigest]; len(ref) > 0 {
        labels[label.NydusProxyMode] = "true"  // 标记为 proxy 模式
        handler = skipHandler                    // 跳过常规处理
    }
```

**路径 2 — 父 snapshot 是 proxy 模式：**

```go
// snapshot/process.go:131-133
if treatAsProxyDriver(pInfo.Labels) {
    handler = proxyHandler  // 走 mountProxy 路径
}
```

---

## 5. Proxy Driver 与 Kata Virtual Volume 类型的关系

Kata Containers 的 Virtual Volume 机制支持多种类型（`snapshot/mount_option.go:312-320`）：

| Virtual Volume 类型 | 说明 | nydusd 在哪 |
|---------------------|------|------------|
| `direct_block` | 直接块设备 | Host |
| `image_raw_block` | 镜像原始块设备 | Host |
| `layer_raw_block` | 层级原始块设备 | Host |
| `image_nydus_block` | Nydus 块设备（整镜像） | Host |
| `layer_nydus_block` | Nydus 块设备（分层） | Host |
| `image_nydus_fs` | Nydus 文件系统（整镜像） | Host |
| `layer_nydus_fs` | Nydus 文件系统（分层） | Host |
| **`image_guest_pull`** | **Guest 内拉取镜像** | **Guest VM** |

Proxy Driver 专门使用 `image_guest_pull` 类型，这是唯一一种让 Guest 自己拉取并处理镜像的类型。

---

## 6. Proxy Driver 的优势与适用场景

### 优势

| 维度 | 传统模式（Host nydusd） | Proxy Driver |
|------|----------------------|-------------|
| **Host 资源消耗** | 每个 Pod 的 nydusd 占用 Host CPU/内存 | nydusd 运行在 Guest 内，不消耗 Host 资源 |
| **网络路径** | Guest → Host → Registry（多一跳） | Guest → Registry（直连） |
| **隔离性** | 多个 Pod 的 nydusd 共享 Host | 每个 Pod 的 nydusd 隔离在各自 VM 内 |
| **安全边界** | Host 需要访问 Registry 凭证 | 只有 Guest 需要 Registry 凭证 |
| **Snapshotter 负担** | 需要管理 nydusd 生命周期（启停、升级、恢复） | 完全不管 nydusd（`daemon_mode = none`） |
| **Host 稳定性** | nydusd 崩溃影响所有 Pod | nydusd 崩溃只影响单个 VM |
| **可扩展性** | Host 上 nydusd 数量有上限 | 每个 VM 独立，无上限 |

### 适用场景

- **大规模 Kata Containers 集群**：成百上千个 Pod，Host 上管理 nydusd 不可行
- **多租户环境**：每个租户的 Pod 需要强隔离
- **安全敏感场景**：Host 不应持有 Registry 凭证
- **网络优化**：减少 Host 中转，Guest 直连 Registry

### 不适用场景

- **runc 容器**：没有 Guest VM，proxy 模式无法工作
- **少量 VM 部署**：传统模式更简单，调试更方便
- **需要共享缓存的场景**：传统模式下多个 Pod 可以共享 Host 上的 blob 缓存

---

## 7. 与其他 "proxy" 概念的区别

Nydus 中有 **3 个完全不同的 "proxy"**，极易混淆：

### 对比表

| 概念 | 出现位置 | 是什么 | 解决什么问题 |
|------|---------|--------|------------|
| **Proxy Driver** | nydus-snapshotter 配置<br>`fs_driver = "proxy"` | snapshotter 的一种模式，不启动 Host nydusd | 让 Kata Guest 自己管理镜像 |
| **HTTP Proxy Backend** | nydusd 存储后端配置<br>`type = "http-proxy"` | 一种存储后端，通过 HTTP 服务器访问 blob | 无 Registry/OSS 时访问本地 blob |
| **Registry Proxy** | nydusd 后端配置<br>`proxy.url = "http://..."` | P2P 加速代理（如 Dragonfly） | 大规模集群的镜像分发加速 |

### 详细区分

**Proxy Driver**（本节主题）：
```toml
# nydus-snapshotter 配置
[daemon]
fs_driver = "proxy"    # snapshotter 的行为模式
```
- 属于 **snapshotter 层**的概念
- 决定"谁"来运行 nydusd（Host 还是 Guest）
- 只与 Kata Containers 相关

**HTTP Proxy Backend**：
```json
// nydusd 配置
{
  "device": {
    "backend": {
      "type": "http-proxy",
      "config": {
        "addr": "http://localhost:8000"
      }
    }
  }
}
```
- 属于 **nydusd 存储后端**的概念
- 决定从"哪里"获取 blob 数据
- 实现在 `storage/src/backend/http_proxy.rs`

**Registry Proxy（P2P 加速）**：
```json
// nydusd 配置
{
  "device": {
    "backend": {
      "type": "registry",
      "config": {
        "proxy": {
          "url": "http://dragonfly:65001",
          "fallback": true
        }
      }
    }
  }
}
```
- 属于 **网络代理**的概念
- 决定通过"什么路径"访问 Registry
- 典型实现是 Dragonfly dfdaemon

---

## 8. 关键代码参考

| 文件:行号 | 内容 |
|-----------|------|
| `nydus-snapshotter/misc/snapshotter/config-proxy.toml` | Proxy 模式配置示例 |
| `nydus-snapshotter/config/config.go:115-118` | FsDriver 常量定义 |
| `nydus-snapshotter/snapshot/snapshot.go:474-477` | Mounts() 中判断是否走 proxy |
| `nydus-snapshotter/snapshot/snapshot.go:1040-1082` | mountProxy() 实现 |
| `nydus-snapshotter/snapshot/snapshot.go:1362-1376` | treatAsProxyDriver() 触发条件判断 |
| `nydus-snapshotter/snapshot/process.go:61-64` | proxyHandler 定义 |
| `nydus-snapshotter/snapshot/process.go:72-79` | 只读层 proxy 标记逻辑 |
| `nydus-snapshotter/snapshot/process.go:131-133` | 父 snapshot proxy 判断 |
| `nydus-snapshotter/snapshot/mount_option.go:170-190` | mountWithProxyVolume() 实现 |
| `nydus-snapshotter/snapshot/mount_option.go:312-320` | Kata Virtual Volume 类型常量 |
| `nydus-snapshotter/snapshot/mount_option.go:442-445` | image_guest_pull 类型校验 |

---

## 9. 架构总结

```
                        fs_driver 的选择
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        fusedev/fscache   blockdev       proxy
              │              │              │
              │              │              │
    ┌─────────┴────┐  ┌────┴─────┐  ┌────┴──────────┐
    │ Host nydusd   │  │ Host     │  │ Host 不启动    │
    │ FUSE/EROFS   │  │ nydusd   │  │ 任何 nydusd    │
    └──────┬───────┘  │ 块设备   │  └──────┬────────┘
           │          └────┬─────┘         │
           │               │               │
    ┌──────┴──────┐       │        ┌──────┴──────────┐
    │ Guest 容器   │       │        │ Kata Virtual     │
    │ 通过 Host    │       │        │ Volume 注入      │
    │ 访问文件系统  │       │        └──────┬──────────┘
    └─────────────┘       │               │
                          │        ┌──────┴──────────┐
                   ┌──────┴────┐ │  Guest VM 内部    │
                   │ Guest 容器  │ │  Guest nydusd     │
                   │ 通过块设备  │ │  直接访问 Registry│
                   │ 访问文件系统│ │                   │
                   └───────────┘ └──────────────────┘
```

**Proxy Driver 的本质是"责任下放"**：snapshotter 不再负责在 Host 上管理 nydusd 和准备 rootfs，而是把镜像信息告诉 Kata 运行时，由 Guest VM 内部的 nydusd 自己去拉取镜像、解析 RAFS、提供文件系统。这样做的好处是 Host 上零 nydusd 进程、零额外开销，每个 Pod 完全自治。
