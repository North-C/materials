# 沙箱基础镜像的数据流

AgentENV 不会把每个沙箱预先构建成一个独立的完整磁盘镜像。新建沙箱时，系统会组合两块职责不同的磁盘：

- **Tools Drive** 是 AgentENV 维护的小型只读 ext4 镜像，负责启动 guest，并提供 `envd` 和启动脚本。
- **用户镜像** 来自 API 请求，例如 `ubuntu:24.04`。AgentENV 将它转换或解析为可写的 OverlayBD 块设备，并在启动过程中把它切换为 guest 的实际根文件系统。

这种设计让普通 OCI 镜像不需要预装 AgentENV 程序也能运行。多个沙箱可以共享同一组不可变镜像层，同时分别保存自己的写入数据。

## 完整链路

```text
POST /sandboxes，携带 userImage
             |
             v
      ImageResolver
  规范化镜像引用，读取 manifest
       和 image config
             |
       +-----+------------------+
       |                        |
       v                        v
普通 OCI layers          OverlayBD-native layers
下载缺失数据              保留远程 layer 描述
转换为 .commit            运行时按需读取
       |                        |
       +------------+-----------+
                    v
       缓存基础 image.json
       其中只包含不可变 lower layers
                    |
                    v
          ublk daemon 启动
  创建沙箱独占的 writable upper，
  生成运行时 image.json
                    |
                    v
             /dev/ublkbN
                    |
                    v
   Firecracker 将其挂载为 /dev/vdb
                    |
                    v
 tools drive 中的 /init 挂载 /dev/vdb，
              执行 pivot_root
                    |
                    v
       用户镜像成为实际根文件系统
```

组件之间传递的主要数据并不复杂。API 把镜像引用交给 `ImageResolver`；解析器返回缓存的 OverlayBD 配置路径，以及环境变量、工作目录、用户、入口命令等 OCI 运行参数。

Orchestrator 把配置路径传给 Firecracker sandbox factory。沙箱启动时，ublk daemon 根据该配置创建块设备，再把设备路径返回给 sandbox。

## 1. 解析用户请求的镜像

Cold sandbox API 会先解析 `userImage`，再通知 orchestrator 启动虚拟机。短镜像名会根据 `image.resolver.search_registries` 补全。

例如默认配置会先把 `ubuntu:24.04` 解析为 `docker.io/library/ubuntu:24.04`：

```toml
default_image = "ubuntu:24.04"
search_registries = ["docker.io", "ghcr.io"]
```

`ImageResolver` 使用 `regctl` 获取当前主机架构对应的 Linux manifest，并读取 OCI image config。image config 中的 `ENV`、`WORKDIR`、`USER`、`ENTRYPOINT` 和 `CMD` 会继续传入沙箱启动配置。

解析缓存以不可变的镜像标识为依据，而不是直接依赖可能变化的 tag。因此，相同镜像的后续启动可以安全地复用已有结果。

如果目标 registry 启用了 OCI referrer 查询，解析器会先寻找源镜像关联的 OverlayBD-native referrer。找到并验证成功后直接使用；查询失败或不存在时，继续处理原始镜像。

## 2. 生成不可变的 OverlayBD Lower Layers

接下来的处理方式由源镜像格式决定。

### 普通 OCI 镜像

普通 OCI 镜像由有序的 tar layers 组成。AgentENV 会先检查内容寻址的转换缓存。如果所有 layer 都已经存在对应的 `.commit` 文件，就直接复用，不再下载镜像内容。

只要有 layer 尚未转换，`regctl image copy` 就会把镜像写入临时 OCI layout。AgentENV 随后按照 manifest 中的顺序处理每一层：

1. 第一层创建文件系统，并确定虚拟磁盘布局。
2. 后续每一层都基于它之前的完整 lower stack 应用变更。
3. 每一步的结果都会封装为不可变的 OverlayBD `.commit` 文件。
4. 完成的 `.commit` 文件进入内容寻址缓存。

转换后的 layer 使用 64 GiB 虚拟地址空间。这个数值表示块设备对 guest 呈现的容量，并不意味着每个镜像都会占用 64 GiB 主机存储；OverlayBD 只保存实际存在的数据和索引。

### OverlayBD-native 镜像

OverlayBD-native 镜像已经包含封装好的块镜像层，因此不需要再次下载并转换完整 blob。

AgentENV 只记录 layer 的 digest、size、本地缓存目录提示以及 registry blob URL。运行时，`registryfs_v2` 可以通过 HTTP range request 满足前台块读取，同时由后台任务逐步填充本地缓存。

两条路径最终都会生成一个缓存的基础 `image.json`。其中 `lowers` 描述按顺序排列的不可变层，`upper` 保持为空，使该配置可以被多个沙箱共享。

## 3. 为每个沙箱增加可写状态

Orchestrator 将缓存的 `image.json` 路径传给 Firecracker sandbox factory。新建沙箱的根文件系统默认可写，并使用 log-structured upper layer。

启动沙箱时，`UblkDeviceManager` 请求 ublk daemon 在沙箱工作目录中生成运行时镜像。daemon 会依次完成：

1. 读取基础镜像的虚拟容量。
2. 创建该沙箱独占的 writable upper 文件。
3. 生成 `overlaybd/image.json`，把共享 lowers 与私有 upper 组合起来。
4. 当请求的磁盘大小与基础容量不同时，在配置允许的条件下调整文件系统大小。
5. 打开完整 layer stack，并将它暴露为 `/dev/ublkbN`。

只有 lower layers 会被共享，每个沙箱都有独立的 upper：

```text
                    共享的 lower layers
                 layer 0 <- layer 1 <- layer 2
                              /       \
                             v         v
                    sandbox A upper  sandbox B upper
```

到这一步，不可变的基础镜像才变成某个沙箱可写的根文件系统。

## 4. 启动虚拟机并切换根文件系统

新建沙箱时，Firecracker 会接收两块主要磁盘：

| Guest 设备 | 数据来源 | Firecracker 中的角色 | 访问方式 |
|---|---|---|---|
| `/dev/vda` | AgentENV tools ext4 | 启动根设备 | 只读 |
| `/dev/vdb` | 沙箱独占的 OverlayBD ublk 设备 | 用户文件系统 | 读写 |

内核首先从 tools drive 启动 `/init`。该脚本把 `/dev/vdb` 挂载到 `/mnt/user`，再把 AgentENV tools bind mount 到用户文件系统中，随后执行 `pivot_root`。

切换完成后，用户镜像成为 `/`，tools drive 中的程序仍可通过 `/agentenv` 使用。`pivot-init` 会启动受监督的 `envd`，然后选择并执行用户镜像提供的 init 程序。

因此，普通 OCI 镜像可以直接成为沙箱根文件系统，而不需要在镜像中预先加入 AgentENV 的启动程序。

## 5. 构建和准备 Tools Drive

Tools drive 由 `tools-image/` 单独构建，正常启动 AgentENV server 时不会现场重建。其 Dockerfile 执行以下步骤：

1. 从固定的 upstream revision 编译静态 `envd`。
2. 组装包含 BusyBox、`/init`、`/agentenv/pivot-init` 和 `/agentenv/envd` 的最小文件系统。
3. 使用 `mkfs.ext4` 生成 `tools.ext4`。
4. 发布一个只携带 `/tools.ext4` 的 OCI artifact。

默认依赖清单指向 `ghcr.io/kvcache-ai/agentenv-tools:<version>`。安装阶段会下载该 artifact，并把 ext4 文件提取到带版本号的依赖目录。部署环境也可以改为使用本地 tools drive。

本地可复现构建命令保持为：

```bash
make -C tools-image
```

## 组件之间的输入与输出

| 组件 | 输入 | 输出 |
|---|---|---|
| Sandbox API | OCI 镜像引用 | 交给 orchestrator 的已解析镜像请求 |
| `ImageResolver` | 规范化后的 OCI 引用 | 基础 `image.json` 路径和 OCI 运行参数 |
| OCI converter | 有序的 tar layers | 本地不可变 `.commit` lower layers |
| OverlayBD remote path | Native layer 描述 | 可按范围读取的远程 lower layers |
| Orchestrator 和 sandbox factory | 镜像配置路径、资源请求 | Firecracker 启动配置 |
| ublk daemon | 基础 `image.json`、运行时目录 | 私有 upper、运行时 `image.json`、`/dev/ublkbN` |
| Firecracker | Tools ext4、ublk 设备 | Guest 中的 `/dev/vda` 和 `/dev/vdb` |
| Tools drive init | 已启动的 tools 文件系统 | 挂载用户镜像，并将其切换为 `/` |

镜像准备与沙箱执行之间的边界是 OverlayBD 配置路径。镜像解析阶段负责生成可复用的 lower layers；运行时阶段负责创建私有写入状态，并管理块设备的生命周期。

## 关键源代码

- `src/api/impls/sandbox.rs`：解析 cold sandbox 请求中的 `userImage`。
- `src/image/reference.rs`：规范化并校验镜像引用。
- `src/image/resolver.rs`：协调 manifest 查询、运行参数读取、缓存和 OverlayBD 配置生成。
- `src/image/oci_image.rs`：识别 OCI 镜像格式并转换 layers。
- `storage/overlaybd/src/tools/oci.rs`：调用 OverlayBD create、apply 和 commit 工具。
- `storage/ublk-daemon/src/runtime.rs`：创建沙箱独占的 runtime upper 和运行时镜像配置。
- `src/sandbox/firecracker/sandbox.rs`：创建 rootfs ublk 设备，并向 Firecracker 挂载两块磁盘。
- `tools-image/`：构建 tools drive，并保存 guest 启动脚本。
