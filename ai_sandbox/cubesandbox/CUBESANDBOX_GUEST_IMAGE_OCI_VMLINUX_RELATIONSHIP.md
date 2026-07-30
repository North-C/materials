# CubeSandbox Guest image、OCI 镜像与 vmlinux 的关系

## 1. 核心结论

CubeSandbox 中的 Guest image 是微虚拟机内部的基础系统盘，不是用户 OCI 镜像的基础层。

- `vmlinux-bm` 提供微虚拟机使用的 Linux 内核。
- `cube-guest-image-cpu.img` 提供微虚拟机的根文件系统、基础用户态和 `cube-agent`。
- 用户提交的 OCI 镜像提供最终容器的应用程序、依赖和容器文件系统。

三者的启动和装载关系如下：

```text
CubeShim / VMM
├── vmlinux-bm
│   └── 启动微虚拟机的 Linux 内核
│
├── cube-guest-image-cpu.img
│   └── /dev/pmem0 -> 虚拟机根目录 /
│       └── /sbin/init -> cube-agent
│
└── 用户 OCI 镜像
    └── 在宿主机拉取并解包镜像层
        └── 通过 virtiofs 共享进微虚拟机
            └── cube-agent 组装容器 rootfs 并启动用户进程
```

## 2. 三个组件分别负责什么

| 组件 | 主要作用 | 用户容器是否直接看到 |
| --- | --- | --- |
| `vmlinux-bm` | 提供内核、系统调用、设备驱动、namespace 和 cgroup 等能力 | 是，容器中的 `uname -r` 来自该内核 |
| Guest image | 提供 VM 根文件系统、`cube-agent`、系统库和挂载工具 | 通常不会作为用户容器 rootfs 暴露 |
| 用户 OCI 镜像 | 提供容器应用、依赖及容器自己的 `/etc`、`/usr` 等目录 | 是，构成用户看到的容器 rootfs |

## 3. 文件与运行时数据所在位置

### 3.1 `.90` 测试机上的当前生效位置

在 `root@192.168.25.90` 上，one-click 安装根目录为：

```text
/usr/local/services/cubetoolbox
```

2026-07-27 实机核对到的 VM 相关文件如下：

| 内容 | `.90` 上的位置 | 说明 |
| --- | --- | --- |
| Guest image | `/usr/local/services/cubetoolbox/cube-image/cube-guest-image-cpu.img` | VM 的只读 ext4 根文件系统 |
| Guest image 版本 | `/usr/local/services/cubetoolbox/cube-image/version` | Guest image 构建版本标识 |
| Guest Agent 版本 | `/usr/local/services/cubetoolbox/cube-image/agent-version` | 镜像内 `cube-agent` 的版本标识 |
| 普通 VM 内核文件 | `/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-bm` | 实际的 ARM64 内核启动映像 |
| 活动内核入口 | `/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux` | 当前是指向 `vmlinux-bm` 的符号链接 |
| 可选 PVM 内核 | `/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-pvm` | 仅在安装包提供并启用 PVM 时使用 |

CubeSandbox 运行时读取的是 `cube-kernel-scf/vmlinux`。普通 VM 模式下，它的关系为：

```text
/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux
    -> vmlinux-bm
```

检查当前生效文件可以执行：

```bash
ls -lh \
  /usr/local/services/cubetoolbox/cube-image/cube-guest-image-cpu.img \
  /usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux \
  /usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-bm

readlink -f /usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux

sha256sum \
  /usr/local/services/cubetoolbox/cube-image/cube-guest-image-cpu.img \
  /usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-bm
```

不要只替换 `vmlinux-bm` 后就根据文件名判断内核已经生效，应同时确认活动入口 `vmlinux` 最终解析到哪个文件。

### 3.2 用户 OCI 镜像在 `.90` 上的位置

用户 OCI 镜像没有一个类似 `cube-guest-image-cpu.img` 的固定单文件路径。Cubelet 会把镜像元数据、解包后的层和 snapshot 数据分散保存在其 root 目录中。

`.90` 当前配置为：

```text
Cubelet 持久数据根目录：/data/cubelet/root
Cubelet 运行状态目录：  /data/cubelet/state
Cubelet 配置文件：      /usr/local/services/cubetoolbox/Cubelet/config/config.toml
```

主要子目录包括：

| 目录 | 内容 |
| --- | --- |
| `/data/cubelet/root/io.containerd.cri.v1.images` | CRI 镜像相关数据和 UID 信息 |
| `/data/cubelet/root/io.cubelet.internal.v1.images` | Cubelet 内部镜像数据及 rootfs |
| `/data/cubelet/root/io.containerd.snapshotter.v1.overlayfs/snapshots` | overlayfs snapshot 数据 |
| `/data/cubelet/root/io.containerd.snapshotter.v1.native/snapshots` | native snapshot 数据 |
| `/data/cubelet/root/io.containerd.runtime.v2.task` | 正在运行的 containerd shim task 数据 |
| `/data/cubelet/root/volume/layer` | CubeSandbox 使用的层卷目录 |
| `/data/cubelet/root/volume/layer_backfile` | 层卷对应的后端文件 |

具体 OCI 镜像对应哪些 snapshot 目录由 Cubelet/containerd 元数据维护，目录编号是动态生成的。不要把某个 snapshot 目录当作稳定的镜像文件路径，也不要在服务运行时手工替换或删除这些目录。

### 3.3 VM 内部的位置

Guest image 启动后，在 VM 内部的对应关系是：

```text
/dev/pmem0    Guest image 对应的块设备
/             /dev/pmem0 挂载得到的 Guest 根文件系统
/sbin/init    cube-agent 的启动入口
```

OCI 镜像的只读层通过 virtiofs 映射到 VM 内，再由 `cube-agent` 组装为每个容器自己的 rootfs。其 Guest 内部挂载路径由运行时动态生成，不应依赖一个固定绝对路径。

### 3.4 本地归档和 `.65` 编译机上的位置

本地工作区保存的完整 openEuler Guest image 与配套内核位于：

```text
/home/lyq/Projects/Verification/cubesandbox/artifacts/guest-images/arm64-openEuler-verification-v0.5.0-20260727-full/
├── cube-guest-image-cpu.img
├── vmlinux-bm
├── cube-agent
├── version
├── agent-version
├── kernel.config
├── kernel-cubesandbox.fragment
├── BUILD_INFO.md
└── SHA256SUMS
```

单独归档的 openEuler 内核构建制品位于：

```text
/home/lyq/Projects/Verification/cubesandbox/artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/
├── vmlinux-bm
├── kernel.config
├── openeuler-base.config
├── kernel-cubesandbox.fragment
├── System.map
├── BUILD_INFO.md
└── SHA256SUMS
```

完整编译步骤见 [`CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md`](CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md)。

`root@192.168.25.65` 上保留的完整运行时布局为：

```text
/opt/cubesandbox-guest-build/openEuler-full-v0.5.0-20260727/runtime-layout/
├── cube-image/cube-guest-image-cpu.img
└── cube-kernel-scf/vmlinux-bm
```

`.65` 上的 openEuler 内核编译目录为：

```text
/opt/cubesandbox-guest-build/openeuler-kernel-6.6.0-132-cubesandbox
```

Guest image 的社区构建入口位于本地源码树：

```text
/home/lyq/Projects/Verification/cubesandbox/source_code/CubeSandbox/deploy/guest-image/Dockerfile
```

这些是构建或归档位置，不会被 `.90` 上正在运行的 CubeSandbox 自动读取。要使其生效，仍需复制到 `.90` 的安装目录、更新活动内核链接、重启 Cubelet，并新建 Template 验证。

## 4. Guest image 的作用

CubeSandbox 创建微虚拟机时，会把 Guest image 作为 virtio-pmem 设备映射进 VM，并将其作为第一个 pmem 设备，即 `/dev/pmem0`。

默认内核命令行包含：

```text
root=/dev/pmem0
rootfstype=ext4
rootflags=dax,errors=remount-ro ro
```

这表示：

- Guest image 使用 ext4 文件系统。
- VM 将它挂载为根目录 `/`。
- 根文件系统以只读方式挂载。
- 文件系统采用 DAX 访问方式，减少额外的页缓存和数据复制。

CubeSandbox 源码也直接说明 `pmem0 is the guest root image`。相关实现位于：

- [`CubeShim/shim/src/hypervisor/config.rs`](source_code/CubeSandbox/CubeShim/shim/src/hypervisor/config.rs)
- [`CubeShim/shim/src/sandbox/pmem.rs`](source_code/CubeSandbox/CubeShim/shim/src/sandbox/pmem.rs)

Guest image 内最重要的程序是 `cube-agent`。镜像构建时会将其设置为 `/sbin/init`，因此内核启动完成后，首先进入 CubeSandbox 的 Guest Agent，而不是完整发行版常见的 systemd 启动流程。

`cube-agent` 负责在 VM 内执行以下工作：

- 接收 CubeShim 通过 vsock/ttrpc 发送的请求。
- 挂载 virtiofs、pmem 等存储设备。
- 组装用户容器的 rootfs。
- 应用 OCI process、mount、namespace、cgroup 等配置。
- 创建、启动、停止和销毁容器进程。

Agent 创建容器的入口可参考：

- [`agent/src/rpc.rs`](source_code/CubeSandbox/agent/src/rpc.rs)
- [`agent/src/mount.rs`](source_code/CubeSandbox/agent/src/mount.rs)

因此，Guest image 更接近“微虚拟机内部的控制环境和基础系统盘”，而不是供用户选择的容器基础镜像。

## 5. 用户 OCI 镜像如何进入微虚拟机

用户通过 CubeSandbox API 指定的 OCI 镜像，通常先由宿主机上的 containerd/Cubelet 拉取并解包。解包后的只读镜像层以宿主机目录的形式记录在 `HostLayers` 中。

相关代码位于：

- [`Cubelet/internal/cube/store/image/image.go`](source_code/CubeSandbox/Cubelet/internal/cube/store/image/image.go)
- [`Cubelet/pkg/container/rootfs/rootfs.go`](source_code/CubeSandbox/Cubelet/pkg/container/rootfs/rootfs.go)

随后，Cubelet/CubeShim 将这些宿主机目录配置为 virtiofs 共享目录。VM 启动后，`cube-agent` 在 Guest 内挂载这些目录，并把 OCI 镜像层作为 overlay rootfs 的只读 lower layers。

其数据路径可以简化为：

```text
OCI registry
    |
    v
宿主机拉取、校验并解包 OCI 镜像
    |
    v
HostLayers（只读镜像层目录）
    |
    v
virtiofs
    |
    v
Guest 内的 overlay lower layers
    |
    +-- 可写 upper/work 层（具体后端取决于配置）
    |
    v
用户容器 rootfs
```

virtiofs 和 rootfs 信息的生成、传递代码位于：

- [`Cubelet/pkg/container/virtiofs/virtiofs.go`](source_code/CubeSandbox/Cubelet/pkg/container/virtiofs/virtiofs.go)
- [`CubeShim/shim/src/container/rootfs.rs`](source_code/CubeSandbox/CubeShim/shim/src/container/rootfs.rs)

用户容器最终看到的是 OCI 镜像组装出的文件系统，而不是 Guest image 的根文件系统。

例如：

```bash
cat /etc/os-release
```

该命令通常显示用户 OCI 镜像所属的发行版。如果 OCI 镜像是 Ubuntu，即使 Guest image 是 openEuler，容器中通常仍会显示 Ubuntu。

## 6. OCI 镜像与 vmlinux 的关系

OCI 镜像只提供用户态程序，不携带一个由 CubeSandbox 启动的独立内核。容器里的所有进程最终都使用微虚拟机的 `vmlinux-bm`。

因此，在容器内执行：

```bash
uname -r
```

显示的是 `vmlinux-bm` 的内核版本，而不是 OCI 镜像所来源发行版的内核版本。

这与普通容器共享宿主机内核的模型类似，但 CubeSandbox 中共享的是所在微虚拟机的内核：

```text
传统容器：用户容器 -> 宿主机内核
CubeSandbox：用户容器 -> 微虚拟机 vmlinux-bm -> VMM/KVM -> 宿主机内核
```

用户 OCI 镜像必须满足以下基本兼容要求：

- CPU 架构必须匹配，例如 ARM64 VM 应使用 `linux/arm64` OCI 镜像。
- 用户态程序依赖的 Linux 系统调用必须由 `vmlinux-bm` 支持。
- OCI 镜像对 namespace、cgroup、文件系统或安全特性的要求必须得到该内核满足。

OCI 镜像可以使用 Ubuntu、Alpine、openEuler 等不同用户态发行版，不要求与 Guest image 的发行版一致。

## 7. Guest image 与 vmlinux 的兼容要求

Guest image 和 `vmlinux-bm` 是相互独立的两个制品，但必须能够配套启动。

主要兼容条件包括：

- CPU 架构一致，例如二者均为 AArch64。
- 内核可以识别 Guest image 使用的 ext4 文件系统。
- 内核支持 DAX 和 virtio-pmem，并可以从 `/dev/pmem0` 挂载根文件系统。
- 内核支持 virtiofs，以便访问宿主机上的 OCI 镜像层。
- 内核支持 vsock，以便 CubeShim 与 `cube-agent` 通信。
- 内核支持 devtmpfs、namespace、cgroup、overlayfs 等容器运行所需能力。
- 内核提供的 ABI 能够运行 Guest image 中的 `cube-agent` 及其辅助程序。

Guest image 通常不会携带完整的内核模块集合，因此启动和运行所需的关键驱动应直接编入 `vmlinux-bm`，而不是仅编译为可加载模块。

将 Guest image 从 TencentOS 或 Ubuntu 替换为 openEuler，并不强制要求内核也来自 openEuler；只要上述接口兼容即可。不过，将 Guest image 和内核都基于 openEuler 构建，可以减少发行版配置差异，并使补丁、配置和问题复现来源更明确。

## 8. 对 `reset guest failed` 的排查意义

三者的启动顺序决定了故障定位范围：

```text
加载 vmlinux-bm
    -> 挂载 Guest image
    -> 启动 cube-agent
    -> Shim 与 Agent 建立连接
    -> 共享 OCI 镜像层
    -> 创建用户容器
```

如果 `reset guest failed` 发生在 VM 重置、恢复或等待 `cube-agent` 就绪的阶段，优先检查：

- Guest image 中的 `cube-agent` 是否正确启动。
- Guest image 的 ext4/DAX/pmem 状态是否正常。
- `vmlinux-bm` 与 Cloud Hypervisor 的 snapshot/reset/restore 行为是否兼容。
- vsock 通信和 Agent 重连是否成功。
- Guest image 与内核版本、配置是否匹配。

此时用户 OCI 镜像通常尚未进入主要执行路径，因此 OCI 镜像内容一般不是首要怀疑对象。

但是，如果失败发生在用户容器销毁之后、VM reset 之前，还需要检查：

- OCI rootfs 的 overlay mount 是否完整卸载。
- virtiofs 共享目录是否仍被占用。
- 容器使用的额外 pmem 或可写层是否清理完成。
- Agent 内是否残留容器、mount namespace 或进程状态。

因此，替换 Guest image 进行 A/B 测试可以判断 Guest 用户态和 `cube-agent` 是否参与触发问题，但不能单独排除 `vmlinux-bm`、VMM snapshot/restore 或 OCI rootfs 清理路径的问题。

## 9. 快速识别当前使用的是哪一层

| 要确认的信息 | 建议检查方式 | 信息来源 |
| --- | --- | --- |
| 容器的用户态发行版 | 容器内执行 `cat /etc/os-release` | 用户 OCI 镜像 |
| 容器实际使用的内核 | 容器内执行 `uname -a` | `vmlinux-bm` |
| VM 基础用户态发行版 | 挂载 Guest image 后检查 `/etc/os-release`，或通过 Guest 调试环境检查 | Guest image |
| Guest Agent 版本 | 检查 Guest image 中的 `/sbin/init` 或制品中的 `agent-version` | Guest image 构建产物 |
| VM 根盘来源 | 检查安装目录中的 `cube-guest-image-cpu.img` 及其 SHA-256 | CubeSandbox 部署制品 |
| 内核来源和配置 | 检查 `vmlinux-bm` 的构建记录、版本及 Kernel config | 内核构建制品 |

## 10. 总结

可以把 CubeSandbox 的三层关系概括为：

```text
vmlinux-bm       = 微虚拟机的内核
Guest image      = 微虚拟机的系统盘和控制环境
用户 OCI 镜像   = 最终容器的应用文件系统
```

Guest image 决定 VM 内 `cube-agent` 如何启动和管理容器，OCI 镜像决定用户进程看到什么文件系统，`vmlinux-bm` 则决定二者共同依赖的内核能力和运行时行为。
