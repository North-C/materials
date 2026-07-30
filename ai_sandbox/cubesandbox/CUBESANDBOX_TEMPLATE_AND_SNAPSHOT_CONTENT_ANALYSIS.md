# CubeSandbox 模板与快照内容分析

## 1. 文档目的

本文说明 CubeSandbox 如何设计、构建、保存和恢复 Template 与 Snapshot。

内容同时覆盖 OCI 镜像、Guest OS、Guest kernel、VM 元数据、rootfs、memory、CubeCow 与 XFS reflink，重点回答以下问题：

- OCI 镜像如何进入 CubeSandbox 并成为 Template。
- Template 和 Snapshot 分别保存哪些内容。
- `tpl-*` 与 `snap-*` 为什么位于同一目录，以及它们如何关联。
- `memory`、`build-rootfs`、`config.json` 和 `state.json` 分别是什么。
- 哪些数据位于 XFS，哪些数据位于普通 ext4 文件系统。
- 如何判断一个 Template 或 Snapshot 是否完整、可恢复。

本文中的远端路径和容量数据来自 2026-07-29 对 `root@192.168.25.90` 的只读检查。

## 2. 核心结论

CubeSandbox 的 Template 或 Snapshot 都不是单个镜像文件，而是一组相互关联的数据。

一份可恢复状态至少包含：

1. VM 配置与设备状态。
2. Guest 物理内存快照。
3. 容器可写 rootfs 状态。
4. Guest image、Guest kernel 和 OCI rootfs 等输入制品的身份或引用。
5. 将上述数据关联起来的本地 catalog 和控制面记录。

Template 是从 OCI 镜像启动并初始化完成后的稳定基线。Snapshot 是从一个正在运行的 Sandbox 提交出的某一时刻状态。

两者使用相同的 VMM 快照格式和 CubeCow 存储能力，因此位于同一个 `cube-snapshot/cubebox` 命名空间，但生命周期和来源不同。

## 3. 先建立四层数据模型

理解 CubeSandbox Template 和 Snapshot 时，应把逻辑资源、输入制品、VMM 元数据和大块状态分开。

### 3.1 第一层：逻辑资源

CubeAPI 和 CubeMaster 管理用户看到的 Template、Snapshot 和 Sandbox ID，例如：

```text
tpl-589cb01990b64282bc6bda9d
snap-be47a778befd459196c1d43c
```

这些 ID 是控制面资源标识，不是某个单独文件的路径。

### 3.2 第二层：不可变输入制品

微虚拟机启动和容器运行依赖三类输入：

| 制品 | 作用 | `.90` 上的典型位置 |
| --- | --- | --- |
| Guest kernel | 启动 MicroVM 的 Linux 内核 | `/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux` |
| Guest image | Guest 根文件系统和 `cube-agent` | `/usr/local/services/cubetoolbox/cube-image/cube-guest-image-cpu.img` |
| OCI rootfs artifact | 用户容器的只读应用文件系统 | `/usr/local/services/cubetoolbox/cubebox_os_image/rfs-*/rfs-*.ext4` |

Guest image 和 OCI rootfs 不是同一个概念。

Guest image 提供 VM 内部控制环境。OCI rootfs 提供用户容器看到的 `/usr`、`/bin`、应用代码和依赖。

### 3.3 第三层：VMM 快照元数据

默认保存在：

```text
/usr/local/services/cubetoolbox/cube-snapshot/cubebox/
```

这里保存 `config.json`、`state.json`、`metadata.json`、`memory.dev` 和 `catalog.json`。

这些文件体积较小，负责描述如何解释和恢复外部 rootfs 与 memory 数据。

### 3.4 第四层：大块可变状态

默认保存在：

```text
/data/cubelet/storage/cubecow-reflink/volumes/
```

这里保存：

- Guest RAM 对应的 memory 文件。
- Template 构建时的 writable rootfs。
- 提交后的 Template rootfs。
- Sandbox rootfs clone。
- 运行时 Snapshot 的 rootfs 和 memory clone。

`.90` 上该目录位于 `/dev/nvme3n1` 的 XFS 文件系统。

## 4. 总体关系

完整关系可以概括为：

```text
Guest kernel -------------------------------+
                                             |
Guest image --------------------------------+----> MicroVM
                                             |       |
OCI rfs-*.ext4 ----> readonly container base+       |
                                                     |
build-rootfs --------> writable container state     |
                                                     |
                  AppSnapshot                        |
                       |                             |
                       +--> config/state/metadata <--+
                       +--> Template memory
                       +--> Template rootfs
                               |
                               +--> Sandbox clone
                                        |
                                        +--> CommitSandbox
                                                 |
                                                 +--> Runtime Snapshot
```

Template 和 Snapshot 都捕获“VM 状态 + 内存状态 + 可写磁盘状态”，但它们的创建起点不同。

## 5. OCI 镜像如何成为 Template

### 5.1 接收 Template 创建请求

用户提交 OCI Image、CPU、内存、启动命令、环境变量、probe 和 `--writable-layer-size`。

CubeMaster 将这些参数规范化，并生成 Template 规格指纹。影响 rootfs 或运行环境的关键参数会成为 Template 身份的一部分。

### 5.2 将 OCI 镜像转换为 ext4 artifact

CubeMaster 拉取并解析 OCI 镜像，将镜像层构造成不可变 ext4 rootfs artifact。

控制节点上的典型保存位置是：

```text
/data/CubeMaster/storage/
└── rfs-<artifact-id>/
    └── rfs-<artifact-id>.ext4
```

artifact 记录至少包含 ID、SHA256、大小、下载 token 和 Template 规格指纹。

这一阶段处理的是 OCI 内容，不会把 Guest kernel 或 Guest image 打包进 OCI artifact。

### 5.3 将 artifact 分发到 Cubelet

CubeMaster 为目标节点生成下载信息。Cubelet 下载并校验 ext4 artifact，节点上的典型路径为：

```text
/usr/local/services/cubetoolbox/cubebox_os_image/
└── rfs-<artifact-id>/
    └── rfs-<artifact-id>.ext4
```

VMM 将该文件作为只读 pmem 设备提供给 Guest。

### 5.4 创建 Template 构建 Sandbox

CubeMaster 生成一次临时 Sandbox 创建请求。

请求中包含一个名为 `cube_rootfs_rw` 的 writable volume，并把它挂载到容器 `/`。其容量来自 `--writable-layer-size`。

因此，容器 rootfs 不是简单复制 OCI ext4，而是由两部分构成：

```text
OCI rfs-*.ext4       readonly base
        +
cube_rootfs_rw       writable state
        =
容器运行时看到的 rootfs
```

### 5.5 启动应用并等待就绪

临时 Sandbox 使用指定 CPU、内存、command、args、env 和 probe 启动。

应用启动后产生的日志、缓存、临时文件和初始化结果会进入可写层，进程及页缓存状态则进入 Guest RAM。

只有达到 AppSnapshot 的就绪条件后，Cubelet 才会固化 Template。

### 5.6 执行 AppSnapshot

Cubelet 为 Template 创建一个空 memory volume，然后调用 `cube-runtime snapshot --app-snapshot`。

AppSnapshot 面对的是新构建 Sandbox，没有上一代 memory 基底，因此使用完整内存快照。

Hypervisor 将：

- Guest RAM 写入外部 memory 文件。
- VM 静态配置写入 `config.json`。
- vCPU 和设备运行状态写入 `state.json`。
- 内存范围等信息写入 `metadata.json`。

随后 Cubelet 从 `build-rootfs` 创建最终 Template rootfs reflink snapshot，并销毁临时构建 Sandbox。

## 6. Template 的目录和文件

### 6.1 元数据目录

默认格式为：

```text
/usr/local/services/cubetoolbox/cube-snapshot/cubebox/
└── tpl-<template-id>/
    └── <CPU>C<MEMORY>M/
        ├── catalog.json
        ├── memory.dev
        ├── metadata.json
        └── snapshot/
            ├── config.json
            └── state.json
```

例如 2 vCPU、2000 MiB Template：

```text
/usr/local/services/cubetoolbox/cube-snapshot/cubebox/
└── tpl-589cb01990b64282bc6bda9d/
    └── 2C2000M/
        ├── catalog.json
        ├── memory.dev
        ├── metadata.json
        └── snapshot/
            ├── config.json
            └── state.json
```

### 6.2 `config.json`

`config.json` 是 Hypervisor 的 VM 配置快照。

它通常描述：

- vCPU 数量、拓扑和功能。
- Guest 内存大小和 dirty-log 配置。
- Guest kernel 或恢复 payload 信息。
- OCI pmem 设备。
- writable rootfs 磁盘。
- TAP、MAC、virtio queue 和网络配置。
- vsock CID 和 socket。
- virtiofs、rng 等设备。

该文件不包含完整内存或 rootfs 数据，只保存配置和路径关系。

### 6.3 `state.json`

`state.json` 是 Hypervisor 序列化的运行状态。

它通常包括：

- vCPU 通用寄存器和系统寄存器。
- vCPU 运行状态。
- GIC、ITS 和中断控制器寄存器。
- virtio block、net、vsock 等设备状态。
- VM 内部组件的 snapshot tree。

`state.json` 必须与对应 memory、配置和设备模型一起使用，不能单独恢复 VM。

### 6.4 `metadata.json`

`metadata.json` 保存快照格式、内存区域和恢复所需的辅助描述。

它体积很小，但决定 Hypervisor 应如何解释 memory 文件中的地址范围。

### 6.5 `memory.dev`

`memory.dev` 记录当次快照使用的外部 memory 文件路径。

它是路径桥梁，不是内存内容本身。

### 6.6 `catalog.json`

`catalog.json` 是 Cubelet 的本地索引。

它将逻辑 Template ID 映射到以下对象：

- `snapshot_path` 和 `meta_dir`。
- `rootfs_vol` 与 `rootfs_kind`。
- `memory_vol` 与 `memory_kind`。
- `build_rootfs_vol` 与 `build_rootfs_kind`。
- `rootfs_size_bytes`。
- `kind: template`。

设备路径不会被视为永久身份。Cubelet在激活 CubeCow 对象后会重新解析实际路径。

## 7. Template memory 文件是什么

### 7.1 文件语义

`*-memory` 是 Guest 物理地址空间的原始快照，不是 ext4 文件系统，也不是普通 core dump。

它可能包含：

- 正在运行的 Guest kernel 数据。
- `cube-agent`、`envd` 和 code server 进程状态。
- 进程堆、栈和内存映射。
- Guest 页缓存。
- 内核数据结构与内存中的设备表。

vCPU 寄存器和大部分设备寄存器由 `state.json` 保存，并不全部位于 memory 文件。

### 7.2 为什么 `file` 显示 Device Tree Blob

`.90` 上 ARM64 memory 文件的开头为：

```text
d0 0d fe ed
```

这是 Flattened Device Tree 的 magic。ARM64 Guest 物理地址起始区域放置了 DTB，因此 `file` 只根据文件头把整个 memory 文件识别成 Device Tree Blob。

该识别结果不表示 memory 文件里只有 DTB。DTB 后面仍然是 Guest RAM 的其他地址范围。

### 7.3 逻辑大小和物理占用

`.90` 上一个 2U、2000 MiB Template 的 memory 文件为：

```text
逻辑大小：2,097,152,000 bytes，即 2000 MiB
物理分配：约 229 MiB
```

未写入的零页以 sparse hole 表示，因此物理占用可以明显小于逻辑内存容量。

## 8. `build-rootfs` 是什么

### 8.1 它不是 OCI 基础镜像

`build-rootfs` 是 Template 构建 Sandbox 的 writable 工作层。

OCI 的 `rfs-*.ext4` 是只读基础内容，`build-rootfs` 只保存启动和运行期间产生的可写状态。

### 8.2 文件系统格式

Cubelet 使用以下方式初始化该卷：

```text
mkfs.ext4 -F -O ^has_journal <device-path>
```

因此它是关闭 journal 的 ext4 文件系统。

`.90` 实测根目录包含：

```text
/
├── lost+found/
├── disk/
└── containerd/
```

它不会重复保存 OCI 镜像中的全部 `/usr`、`/bin` 和应用文件。

### 8.3 从 build 到最终 rootfs

AppSnapshot 完成后，Cubelet 调用 CubeCow，从 `build-rootfs` 创建 canonical Template rootfs snapshot。

可简化为：

```text
tpl-<id>-build-rootfs
        |
        +-- FICLONE --> tpl-<id>-rootfs
```

之后创建普通 Sandbox 时，Cubelet 从 `tpl-<id>-rootfs` 再创建 Sandbox rootfs clone。

### 8.4 为什么目录名和文件名可能不同

CubeCow 以 origin volume 目录组织 reflink lineage。

因此可能看到：

```text
tpl-tpl-589cb01990b64282bc6bda9d-build-rootfs/
└── tpl-tpl-589cb01990b64282bc6bda9d-rootfs
```

外层 `build-rootfs` 表示 origin lineage，内层 `rootfs` 是提交后的 Template rootfs 对象。

`tpl-tpl-*` 不是两级 Template。原因是业务 Template ID 已经以 `tpl-` 开头，而 CubeCow 对象命名函数又增加了 `tpl-` 前缀。

### 8.5 `.90` 容量样例

同一个 1 GiB writable layer 的实测结果为：

```text
逻辑大小：1,073,741,824 bytes，即 1 GiB
物理分配：约 616 KiB
```

这说明 Template 初始化时对 writable layer 的修改较少。主要应用内容仍来自只读 OCI artifact。

## 9. 运行时 Snapshot 如何创建

### 9.1 Snapshot 的来源

运行时 Snapshot 由 `CommitSandbox` 创建，输入必须是一个正在运行的 Sandbox。

它捕获提交时刻的：

- 当前 VM 配置和设备状态。
- 当前 Guest RAM。
- 当前 Sandbox writable rootfs。

与 AppSnapshot 不同，CommitSandbox 不需要重新构建 OCI rootfs，也不会创建 `build-rootfs`。

### 9.2 rootfs 提交

Cubelet 解析正在运行 Sandbox 的当前 rootfs CubeCow 对象，并从该对象创建 Snapshot rootfs。

因此 Snapshot rootfs 包含从 Template 启动后产生的文件变化。

### 9.3 memory 提交

如果 Cubelet 能找到上一代 Snapshot 或最近恢复基底的 memory 对象，会先对基底执行 reflink clone。

Hypervisor 只需把本轮改变的内存页写入 clone，共享页继续引用父对象的 XFS extent。

如果基底 catalog 或 memory 对象已经丢失，Cubelet 会创建空 memory volume，并退化为完整内存快照。

### 9.4 提交后的状态绑定

成功提交后，Cubelet 将当前 Sandbox 的 runtime snapshot binding 更新为新 Snapshot ID。

下一次 CommitSandbox 应以这次提交为基底，避免跳过中间一代已经写入的内存变化。

## 10. Snapshot 的目录和文件

正常运行时 Snapshot 的目录格式为：

```text
/usr/local/services/cubetoolbox/cube-snapshot/cubebox/
└── snap-<snapshot-id>/
    └── <CPU>C<MEMORY>M/
        ├── catalog.json
        ├── memory.dev
        ├── metadata.json
        └── snapshot/
            ├── config.json
            └── state.json
```

目录格式与 Template 相同，因为两者都由同一套 Hypervisor snapshot/restore 协议消费。

运行时 Snapshot 的 `catalog.json` 通常记录：

```json
{
  "snapshot_id": "snap-xxx",
  "rootfs_vol": "tpl-snap-xxx-rootfs",
  "rootfs_kind": "snapshot",
  "memory_vol": "tpl-snap-xxx-memory",
  "memory_kind": "snapshot",
  "kind": "runtime_snapshot"
}
```

当完整内存快照使用独立 volume 时，`memory_kind` 也可能是 `volume`。恢复逻辑必须尊重 catalog 中的实际类型。

运行时 Snapshot 不产生 `build_rootfs_vol`。该字段只属于 AppSnapshot 构建 Template 的流程。

## 11. `tpl-*` 与 `snap-*` 的关系

### 11.1 为什么位于同一目录

二者都代表可被 CubeShim 和 Hypervisor 恢复的 Cubebox 状态，所以共享：

```text
/usr/local/services/cubetoolbox/cube-snapshot/cubebox/
```

同一父目录表示格式和管理入口一致，不表示它们是同一种业务资源。

### 11.2 主要区别

| 对比项 | `tpl-*` | `snap-*` |
| --- | --- | --- |
| 业务对象 | Template | Runtime Snapshot |
| 创建入口 | AppSnapshot | CommitSandbox |
| 来源 | OCI 镜像初始化后的临时 Sandbox | 正在运行的 Sandbox |
| catalog kind | `template` | `runtime_snapshot` |
| rootfs 来源 | `build-rootfs` | Sandbox 当前 rootfs |
| memory 策略 | 完整快照 | 优先增量，必要时完整快照 |
| build rootfs | 有 | 无 |
| 典型用途 | 批量创建 Sandbox | 恢复、克隆、回滚运行状态 |

### 11.3 典型继承链

```text
OCI Image
    |
    v
tpl-A
    |
    +-- rootfs/memory reflink --> Sandbox S1
                                      |
                                      +-- CommitSandbox --> snap-B
                                                               |
                                                               +--> Sandbox S2
                                                                      |
                                                                      +--> snap-C
```

一个 Template 可以派生多个 Sandbox，每个 Sandbox 又可以提交一个或多个 Snapshot。

Snapshot 也可以从上一个 Snapshot 恢复出的 Sandbox 再次提交，因此继承链不一定始终直接指向最初 Template。

### 11.4 不能只根据目录名判断父子关系

`tpl-A` 与 `snap-B` 在元数据目录中是平级目录。

实际继承关系应结合以下信息判断：

1. CubeMaster 中的逻辑资源与来源记录。
2. `catalog.json` 中的 rootfs/memory 对象名与类型。
3. CubeCow snapshot 所在的 origin volume 目录。
4. Sandbox 的 runtime snapshot binding。

### 11.5 `.90` 上的实际 lineage 样例

`snap-be47a778befd459196c1d43c` 曾使用以下 memory 路径：

```text
/data/cubelet/storage/cubecow-reflink/volumes/
└── tpl-tpl-d38241efa019453f9bc2132c-memory/
    └── tpl-snap-be47a778befd459196c1d43c-memory
```

外层目录表明该运行时 memory Snapshot 位于 `tpl-d38241efa019453f9bc2132c` 的 memory origin lineage 中。

这是一种物理存储关联。逻辑父子关系仍应以 catalog 和控制面记录为准。

## 12. 从 Template 或 Snapshot 创建 Sandbox

### 12.1 解析逻辑 ID

Cubelet 根据 Template/Snapshot ID 读取本地 `catalog.json`，获得：

- metadata 目录。
- rootfs CubeCow 对象。
- memory CubeCow 对象。
- 两个对象各自的 `volume` 或 `snapshot` 类型。

### 12.2 创建 rootfs clone

CubeCow 使用 `FICLONE` 从 Template 或 Snapshot rootfs 创建 Sandbox rootfs。

该操作共享原始 XFS extents，不需要复制整个 1 GiB 或更大的磁盘文件。

### 12.3 准备 memory

创建路径会解析基底 memory，并把实际路径作为 `memory_vol_url` 传给 CubeShim 和 Hypervisor。

恢复时可以由多个 Sandbox 读取同一个基底 memory。只有提交下一代 Snapshot 等需要保留变化的路径，才会创建新的 reflink memory 对象。

### 12.4 恢复 VM

CubeShim 向 Hypervisor 提交：

- `source_url`，指向 `snapshot/` 元数据目录。
- `memory_vol_url`，指向外部 Guest RAM 文件。
- 新 Sandbox 的 rootfs disk。
- 新 TAP、MAC、vsock 和其他运行时设备参数。

Hypervisor 读取 `config.json` 和 `state.json`，加载 memory，应用本次创建的设备覆盖，然后恢复 vCPU 运行。

### 12.5 恢复后为什么很快

Template 创建阶段已经完成 Guest boot、agent 初始化和应用启动。

运行时创建不再重复执行完整启动链，而是恢复已暂停的 VM 状态。rootfs 和 memory 又通过 reflink 共享，因此关键路径主要是元数据解析、文件激活、设备重建和 KVM restore。

## 13. CubeCow 与 XFS reflink

### 13.1 为什么使用普通文件

CubeCow 的 reflink backend 将 volume 和 snapshot 表示为 XFS 上的普通文件。

典型布局为：

```text
volumes/
└── <origin-volume>/
    ├── <origin-volume>
    ├── <snapshot-A>
    ├── <snapshot-B>
    └── <sandbox-rootfs>
```

Snapshot 文件保存在最终 origin volume 目录中，便于从目录布局重建索引。

### 13.2 FICLONE 的语义

创建 snapshot 时，CubeCow 调用 Linux `FICLONE`。

新旧文件初始共享相同 extents。任意一方发生写入时，XFS 才为变化范围分配新块。

这带来三个直接效果：

- clone 延迟接近元数据操作，不随逻辑文件大小线性增长。
- 相同 Template 派生大量 Sandbox 时，共享未修改数据。
- Snapshot memory 只需写入发生变化的页。

### 13.3 如何理解 `stat` 与 `du`

`stat` 的文件大小是逻辑容量，`du` 更接近当前分配的物理块。

但 reflink 文件可能共享 extents，逐文件执行 `du` 后直接相加会重复统计共享块。

因此不能用普通 `du` 汇总值作为 CubeCow 独占容量。

## 14. `.90` 上的实际存储边界

### 14.1 CubeCow 数据

```text
路径：/data/cubelet/storage/cubecow-reflink/volumes
设备：/dev/nvme3n1
文件系统：XFS
```

这里保存 rootfs 和 memory 大文件，并提供 reflink 能力。

### 14.2 VMM 元数据

```text
路径：/usr/local/services/cubetoolbox/cube-snapshot
设备：/dev/mapper/openeuler2403s3-root
文件系统：ext4
```

这里保存 config、state、metadata、memory.dev 和 catalog。

### 14.3 CubeMaster OCI artifact

```text
路径：/data/CubeMaster/storage/rfs-*/rfs-*.ext4
```

这是 OCI 转换后的只读 rootfs artifact 存储，不是 Template memory 或 writable rootfs。

因此，“Template 是否保存在 XFS”需要分层回答：

- Template 的 rootfs 和 memory 大块状态保存在 XFS/CubeCow。
- Template 的 VMM 元数据保存在默认快照目录所在的 ext4。
- OCI 基础 artifact 由 CubeMaster artifact store 和节点缓存分别管理。

## 15. 空目录为什么不是有效 Snapshot

只存在以下目录并不表示 Snapshot 可恢复：

```text
/usr/local/services/cubetoolbox/cube-snapshot/cubebox/snap-xxx/
```

有效 Snapshot 至少应存在规格目录和核心元数据：

```text
snap-xxx/2C2000M/
├── catalog.json
├── metadata.json
├── memory.dev
└── snapshot/
    ├── config.json
    └── state.json
```

catalog 引用的 rootfs 和 memory CubeCow 对象也必须存在。

`.90` 上的 `snap-be47a778befd459196c1d43c` 当前只剩 4 KiB 空父目录。

日志证明它过去曾被 VMM restore 使用，但其 `2C2000M`、VMM 元数据和 CubeCow 对象后来已被清理。当前空目录不能再用于恢复。

## 16. Template 和 Snapshot 的完整性检查

### 16.1 检查目录结构

```bash
find /usr/local/services/cubetoolbox/cube-snapshot/cubebox/<id> \
  -maxdepth 4 -printf '%y %s %p\n' | sort
```

确认资源规格目录、`snapshot/config.json`、`snapshot/state.json` 和上层辅助文件存在。

### 16.2 检查 catalog

```bash
jq . \
  /usr/local/services/cubetoolbox/cube-snapshot/cubebox/<id>/<spec>/catalog.json
```

重点检查：

- `snapshot_id` 是否匹配。
- `kind` 是 `template` 还是 `runtime_snapshot`。
- `rootfs_vol`、`rootfs_kind`。
- `memory_vol`、`memory_kind`。
- `snapshot_path` 和 `meta_dir`。

### 16.3 检查 memory

```bash
file /data/cubelet/storage/cubecow-reflink/volumes/<memory-path>
stat /data/cubelet/storage/cubecow-reflink/volumes/<memory-path>
du -h /data/cubelet/storage/cubecow-reflink/volumes/<memory-path>
```

不要因为 ARM64 memory 文件被识别为 Device Tree Blob 就把它当成普通 DTB 文件。

### 16.4 检查 rootfs

```bash
file /data/cubelet/storage/cubecow-reflink/volumes/<rootfs-path>
debugfs -R 'ls -l /' /data/cubelet/storage/cubecow-reflink/volumes/<rootfs-path>
```

优先使用 `debugfs` 进行只读检查，避免在服务运行期间随意 mount 或修改活跃文件。

### 16.5 检查文件系统边界

```bash
findmnt -T /data/cubelet/storage/cubecow-reflink/volumes
findmnt -T /usr/local/services/cubetoolbox/cube-snapshot
```

这可以确认 reflink 数据与 VMM 元数据是否位于预期设备。

## 17. 生命周期与操作注意事项

### 17.1 不要手工删除单个文件

Template/Snapshot 元数据、CubeCow rootfs、memory 和控制面记录必须协调清理。

手工删除其中一个文件可能留下 catalog 漂移、孤立对象或无法恢复的逻辑资源。

### 17.2 Template 与 Snapshot 可能共享 lineage

即使 `tpl-*` 与 `snap-*` 在元数据目录中平级，它们的 rootfs/memory 仍可能位于同一个 CubeCow origin 目录并共享 extents。

清理应通过 CubeSandbox 的 Template/Snapshot 删除接口执行。

### 17.3 Guest kernel 或 Guest image 更新后应重建 Template

memory 中保存的是旧 Guest kernel 和 agent 已经运行后的状态，`state.json` 又依赖对应设备模型和寄存器语义。

替换 Guest kernel、Guest image、cube-agent 或关键 Hypervisor 组件后，旧 Template 可能仍引用或承载旧运行状态。

稳妥做法是重新构建 Template，并验证版本 catalog、恢复成功率和高并发稳定性。

### 17.4 OCI artifact 与 Template 不能混为一谈

重建 `rfs-*.ext4` 只改变 OCI 容器文件系统输入。

只有重新执行 AppSnapshot，才会重新生成包含初始化应用状态、Guest RAM、rootfs 和 VMM state 的完整 Template。

## 18. 源码入口

以下源码是本文分析的主要依据：

- OCI artifact 构建：[`artifact_build.go`](source_code/CubeSandbox/CubeMaster/pkg/templatecenter/artifact_build.go)
- Template 创建请求：[`template_request.go`](source_code/CubeSandbox/CubeMaster/pkg/templatecenter/template_request.go)
- Template 副本创建：[`store.go`](source_code/CubeSandbox/CubeMaster/pkg/templatecenter/store.go)
- AppSnapshot：[`appsnapshot.go`](source_code/CubeSandbox/Cubelet/services/cubebox/appsnapshot.go)
- CommitSandbox：[`template_ops.go`](source_code/CubeSandbox/Cubelet/services/cubebox/template_ops.go)
- CubeCow snapshot 对象：[`cubecow_snapshot_artifacts.go`](source_code/CubeSandbox/Cubelet/storage/cubecow_snapshot_artifacts.go)
- CubeCow volume 管理：[`cubecow_volume_manager.go`](source_code/CubeSandbox/Cubelet/storage/cubecow_volume_manager.go)
- 本地 snapshot catalog：[`snapshot_catalog.go`](source_code/CubeSandbox/Cubelet/storage/snapshot_catalog.go)
- 外部 memory 文件处理：[`memory_manager.rs`](source_code/CubeSandbox/hypervisor/vmm/src/memory_manager.rs)
- XFS reflink backend：[`reflink.rs`](source_code/CubeSandbox/cubecow/src/engine/reflink.rs)
- 总体架构：[`overview.md`](source_code/CubeSandbox/docs/architecture/overview.md)

## 19. 最终心智模型

理解 CubeSandbox Template 与 Snapshot 时，可以记住以下模型：

```text
Template = OCI 初始化后的稳定 VM 基线
         = VM metadata + full memory + committed writable rootfs

Snapshot = 运行中 Sandbox 的某一时刻状态
         = VM metadata + current memory + current writable rootfs

快速创建 = restore metadata
         + reflink rootfs/memory
         + 重建本次 Sandbox 的网络和 vsock
```

`tpl-*` 是可重复使用的基线，`snap-*` 是运行状态的提交点。二者共享格式和存储引擎，但来源、catalog 类型、内存策略和生命周期不同。

目录只是索引入口。真正可恢复性取决于 metadata、rootfs、memory、catalog 和运行时制品是否完整且相互兼容。
