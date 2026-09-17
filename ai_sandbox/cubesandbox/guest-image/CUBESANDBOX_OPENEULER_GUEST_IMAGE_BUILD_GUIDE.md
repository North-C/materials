# CubeSandbox ARM64 openEuler Guest image 构建指南

## 1. 目标与适用范围

本文记录如何基于 Verification 版本的 ARM64 适配，以
`openeuler/openeuler:24.03-lts-sp3` 为基础用户态，构建 CubeSandbox 使用的：

```text
cube-guest-image-cpu.img
```

本文对应的已验证构建环境为：

| 项目 | 值 |
| --- | --- |
| 构建机 | `root@192.168.25.65` |
| 构建机架构 | AArch64 |
| 构建机系统 | openEuler 24.03 LTS-SP3 |
| CubeSandbox 版本 | Verification `v0.5.0` |
| 源码提交 | `30b4e25ab16891187c775e002816274427f541f1` |
| Guest 基础镜像 | `openeuler/openeuler:24.03-lts-sp3` |
| Agent 版本 | `v0.5.0` |
| 文件系统 | ext4，4 KiB block |
| VM 根设备 | `/dev/pmem0` |
| Guest init | `/sbin/init`，实际为静态链接的 `cube-agent` |

Guest image 的构建严格来说是“组装 rootfs 并生成 ext4 镜像”，不是编译一个操作系统内核。内核 `vmlinux-bm` 是独立制品，不会被写进 Guest image。

## 2. 最终产物结构

推荐通过 CubeSandbox 自带的 `build-vm-assets.sh` 生成完整运行时布局：

```text
runtime-layout/
├── cube-image/
│   ├── cube-guest-image-cpu.img
│   ├── version
│   └── agent-version
├── cube-kernel-scf/
│   ├── vmlinux -> vmlinux-bm
│   └── vmlinux-bm
└── cube-shim/
    ├── bin/
    │   ├── containerd-shim-cube-rs
    │   └── cube-runtime
    └── conf/config-cube.toml
```

其中 Guest image 内部至少包含：

```text
/etc/os-release       openEuler 发行版身份
/sbin/init            cube-agent
/etc/rc.local         默认空启动脚本
/etc/hostname
/etc/hosts
/etc/resolv.conf
/bin、/usr、/lib*     openEuler 基础用户态及运行工具
```

## 3. 构建流程概览

```text
Verification ARM64 源码
    |
    +-- builder 容器编译静态 aarch64 cube-agent
    |
    +-- openEuler Dockerfile 构建基础容器镜像
            |
            v
        docker export rootfs
            |
            v
        将 cube-agent 注入 /sbin/init
            |
            v
        mkfs.ext4 -b 4096 -d rootfs
            |
            v
        e2fsck + resize2fs 最小化
            |
            v
        保留 32 MiB 空间并按 2 MiB 对齐
            |
            v
        cube-guest-image-cpu.img
```

自动化入口和关键实现位于：

- [`build-vm-assets.sh`](source_code/CubeSandbox/deploy/one-click/build-vm-assets.sh)
- [`agent/Makefile`](source_code/CubeSandbox/agent/Makefile)
- [`docker/Dockerfile.builder`](source_code/CubeSandbox/docker/Dockerfile.builder)
- [本次 openEuler Dockerfile](artifacts/guest-images/arm64-openEuler-verification-v0.5.0-20260727-full/Dockerfile)

## 4. 构建机准备

### 4.1 登录并确认环境

```bash
ssh root@192.168.25.65

uname -m
cat /etc/os-release
docker --version
mkfs.ext4 -V
```

预期架构为 `aarch64`，系统为 openEuler 24.03 LTS-SP3。

### 4.2 安装宿主机工具

```bash
dnf install -y \
  docker-engine \
  make \
  git \
  tar \
  gzip \
  python3 \
  coreutils \
  e2fsprogs \
  util-linux \
  file

systemctl enable --now docker
```

必须确认 `mkfs.ext4` 支持 `-d`，该参数负责从目录直接填充 ext4 镜像：

```bash
mkfs.ext4 -h 2>&1 | grep -- '-d'
```

本次 `.65` 使用的是 `e2fsprogs 1.47.0`。

宿主机不需要直接安装 Rust、musl 或静态 libseccomp。`cube-agent` 在项目统一 builder 容器内编译，所需 Rust 工具链、musl target 和静态 libseccomp 已由 builder 镜像提供。

## 5. 准备源码和构建目录

`.65` 上本次使用的 Verification 源码位于：

```text
/opt/cubesandbox-guest-build/verification-v0.5.0/CubeSandbox
```

为新构建创建独立目录。不要复用已经归档的 `runtime-layout`，因为 `build-vm-assets.sh` 会清理其目标运行时布局和 Guest 临时目录。

下面的 `BUILD_ID` 应替换为本次唯一标识：

```bash
REPO=/opt/cubesandbox-guest-build/verification-v0.5.0/CubeSandbox
BUILD_ID=openeuler-guest-v0.5.0-YYYYmmdd-HHMMSS
BUILD_ROOT=/opt/cubesandbox-guest-build/$BUILD_ID

test -d "$REPO"
test ! -e "$BUILD_ROOT"
install -d -m 0755 "$BUILD_ROOT/input"
```

如果重新同步源码，应记录准确的 tag、commit 和工作区修改。源码副本不含 `.git` 时，后续必须显式设置 `CUBE_COMMIT`，避免版本显示为 `unknown`。

## 6. 准备 openEuler Guest Dockerfile

当前社区源码中的默认 Guest Dockerfile 使用 TencentOS。构建 openEuler Guest 时不要直接改写默认文件，而是使用环境变量指定独立 Dockerfile。

本地已归档的 openEuler Dockerfile 位于：

```text
/home/lyq/Projects/Verification/cubesandbox/artifacts/guest-images/arm64-openEuler-verification-v0.5.0-20260727-full/Dockerfile
```

从本地工作机传到 `.65` 新建的输入目录。以下命令在本地工作机的新终端执行，因此需要把 `BUILD_ID` 重新设置为第 5 节使用的同一个值：

```bash
BUILD_ID=openeuler-guest-v0.5.0-YYYYmmdd-HHMMSS

scp \
  /home/lyq/Projects/Verification/cubesandbox/artifacts/guest-images/arm64-openEuler-verification-v0.5.0-20260727-full/Dockerfile \
  root@192.168.25.65:/opt/cubesandbox-guest-build/$BUILD_ID/input/Dockerfile.openEuler
```

Dockerfile 内容如下：

```dockerfile
FROM openeuler/openeuler:24.03-lts-sp3

WORKDIR /work

RUN dnf install -y --setopt=install_weak_deps=False --setopt=tsflags=nodocs \
        util-linux \
        busybox \
 && dnf clean all \
 && rm -rf /var/cache/yum /var/cache/dnf /var/log/yum.log /var/log/dnf.* \
           /usr/share/doc /usr/share/man /usr/share/info \
           /usr/share/licenses /usr/share/groff \
           /usr/share/locale/* /usr/lib/locale/* \
           /tmp/* /var/tmp/*

CMD ["bash"]
```

`util-linux` 提供 mount、umount、blkid 等运行工具；`busybox` 提供精简 shell 和常用 applet。Guest image 不运行完整 systemd，`cube-agent` 会替代镜像原有的 `/sbin/init`。

## 7. 编译 ARM64 cube-agent

### 7.1 设置版本信息

在 `.65` 上执行：

```bash
cd "$REPO"

export CUBE_VERSION=v0.5.0
export CUBE_COMMIT=30b4e25ab16891187c775e002816274427f541f1
export CUBE_BUILD_TIME="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
```

### 7.2 构建 builder 镜像和二进制

```bash
make builder-image
make agent shim
```

`make agent` 在 builder 中执行 `agent/Makefile`，默认使用：

```text
aarch64-unknown-linux-musl
```

并启用静态链接。`make shim` 同时生成 `containerd-shim-cube-rs` 和 `cube-runtime`，供后续 `build-vm-assets.sh` 组装运行时布局。

输出位置为：

```text
$REPO/_output/bin/cube-agent
$REPO/_output/bin/containerd-shim-cube-rs
$REPO/_output/bin/cube-runtime
```

检查 Agent：

```bash
file "$REPO/_output/bin/cube-agent"
ldd "$REPO/_output/bin/cube-agent" 2>&1 || true
sha256sum "$REPO/_output/bin/cube-agent"
```

预期 `file` 显示 `ARM aarch64` 和 `statically linked`，`ldd` 显示它不是动态可执行文件。

本次已归档 Agent 的身份为：

```text
size:   12904944 bytes
sha256: 6383e920e5503ed148a53bd7172a8d15d23d6971fb8d18488825008d2af18e3d
```

重新编译时，构建时间等元数据可能使 SHA-256 不同；应记录新产物自己的摘要，而不是强制要求与历史摘要一致。

## 8. 准备配套 vmlinux-bm

Guest rootfs 与内核是两个独立制品，但 `build-vm-assets.sh` 会同时组装完整运行时布局，因此执行脚本时必须提供一个内核文件。

本次 `.65` 上的 openEuler 内核位于：

```text
/opt/cubesandbox-guest-build/openeuler-kernel-6.6.0-132-cubesandbox/output/vmlinux-bm
```

检查文件：

```bash
KERNEL=/opt/cubesandbox-guest-build/openeuler-kernel-6.6.0-132-cubesandbox/output/vmlinux-bm

test -f "$KERNEL"
file "$KERNEL"
sha256sum "$KERNEL"
```

预期类型为：

```text
Linux kernel ARM64 boot executable Image, little-endian, 4K pages
```

不要把内核构建目录中的 ELF `vmlinux` 当作 CubeSandbox 的 `vmlinux-bm`。CubeSandbox 需要的是 `arch/arm64/boot/Image` 格式的 ARM64 启动映像。

## 9. 构建 cube-guest-image

### 9.1 设置构建变量

继续在 `.65` 上执行：

```bash
export ONE_CLICK_WORK_ROOT="$BUILD_ROOT/work"
export ONE_CLICK_RUNTIME_LAYOUT_DIR="$BUILD_ROOT/runtime-layout"

export ONE_CLICK_GUEST_IMAGE_DOCKERFILE="$BUILD_ROOT/input/Dockerfile.openEuler"
export ONE_CLICK_GUEST_IMAGE_CONTEXT_DIR="$BUILD_ROOT/input"
export ONE_CLICK_GUEST_IMAGE_REF=cubesandbox-guest-openeuler:24.03-lts-sp3-arm64
export ONE_CLICK_GUEST_IMAGE_VERSION=v0.5.0-verification-openeuler-arm64-YYYYmmdd

export ONE_CLICK_CUBE_AGENT_BIN="$REPO/_output/bin/cube-agent"
export ONE_CLICK_CUBESHIM_BIN="$REPO/_output/bin/containerd-shim-cube-rs"
export ONE_CLICK_CUBE_RUNTIME_BIN="$REPO/_output/bin/cube-runtime"
export ONE_CLICK_CUBE_KERNEL_VMLINUX="$KERNEL"
```

版本字段含义：

| 环境变量 | 写入或影响的位置 |
| --- | --- |
| `CUBE_VERSION` | `cube-agent` 内部版本和 `cube-image/agent-version` |
| `CUBE_COMMIT` | `cube-agent` 编译身份 |
| `CUBE_BUILD_TIME` | `cube-agent` 编译时间 |
| `ONE_CLICK_GUEST_IMAGE_VERSION` | `cube-image/version` |
| `ONE_CLICK_GUEST_IMAGE_REF` | 构建机上的临时 Docker 镜像 tag |

### 9.2 执行官方构建脚本

```bash
cd "$REPO"
./deploy/one-click/build-vm-assets.sh
```

脚本会依次执行：

1. 校验内核、Docker、e2fsprogs 和预编译二进制。
2. 使用 openEuler Dockerfile 执行 `docker build`。
3. 创建临时容器并通过 `docker export` 导出完整 rootfs。
4. 解包 rootfs，并把原 `/sbin/init` 备份为 `/sbin/init.original`。
5. 把静态 `cube-agent` 及其依赖复制为新的 `/sbin/init`。
6. 写入最小的 `rc.local`、hostname、hosts 和 resolv.conf。
7. 根据 rootfs 大小创建临时稀疏文件。
8. 以 `mkfs.ext4 -F -b 4096 -d rootfs` 生成 ext4 镜像。
9. 使用 `e2fsck` 和 `resize2fs -M` 缩小文件系统。
10. 默认保留 32 MiB 空闲空间，并把最终文件大小向上对齐到 2 MiB。
11. 输出 `version`、`agent-version` 和完整 runtime layout。

必须使用 4 KiB ext4 block。CubeShim 以 `rootflags=dax` 挂载 `/dev/pmem0`，1 KiB block 的 ext4 镜像可能在 Guest 启动阶段失败。

最终文件还必须满足：

```text
镜像字节数 % 2097152 == 0
```

这是 virtio-pmem 设备要求的 2 MiB 对齐约束。

## 10. 验证构建产物

### 10.1 基本文件和摘要

```bash
GUEST_DIR="$BUILD_ROOT/runtime-layout/cube-image"
GUEST_IMAGE="$GUEST_DIR/cube-guest-image-cpu.img"

test -f "$GUEST_IMAGE"
test -f "$GUEST_DIR/version"
test -f "$GUEST_DIR/agent-version"

ls -lh "$GUEST_DIR"
cat "$GUEST_DIR/version"
cat "$GUEST_DIR/agent-version"
sha256sum "$GUEST_IMAGE" "$GUEST_DIR/version" "$GUEST_DIR/agent-version"
```

### 10.2 ext4 和 pmem 对齐

```bash
file "$GUEST_IMAGE"
e2fsck -fn "$GUEST_IMAGE"
dumpe2fs -h "$GUEST_IMAGE" 2>/dev/null | grep -E 'Block count|Block size|Free blocks|Filesystem state'

IMAGE_BYTES="$(stat -c '%s' "$GUEST_IMAGE")"
printf 'image bytes: %s\n' "$IMAGE_BYTES"
test "$((IMAGE_BYTES % 2097152))" -eq 0
```

验收条件：

- 文件系统是 ext4。
- block size 是 `4096`。
- `e2fsck -fn` 没有文件系统错误。
- 文件系统状态为 clean。
- 镜像大小是 2 MiB 的整数倍。

### 10.3 检查 openEuler 身份

```bash
debugfs -R 'cat /etc/os-release' "$GUEST_IMAGE" 2>/dev/null
```

预期包含：

```text
NAME="openEuler"
VERSION="24.03 (LTS-SP3)"
```

### 10.4 确认 `/sbin/init` 是正确的 cube-agent

```bash
EXTRACTED_AGENT="$BUILD_ROOT/cube-agent.from-guest-image"

debugfs -R "stat /sbin/init" "$GUEST_IMAGE" 2>/dev/null
debugfs -R "dump /sbin/init $EXTRACTED_AGENT" "$GUEST_IMAGE" 2>/dev/null

file "$EXTRACTED_AGENT"
sha256sum "$REPO/_output/bin/cube-agent" "$EXTRACTED_AGENT"
cmp -s "$REPO/_output/bin/cube-agent" "$EXTRACTED_AGENT"
```

`cmp` 必须成功，证明写入 Guest image 的 `/sbin/init` 与本次编译的 Agent 完全一致。

### 10.5 检查完整运行时布局

```bash
find "$BUILD_ROOT/runtime-layout" -maxdepth 3 -type f -o -type l
readlink -f "$BUILD_ROOT/runtime-layout/cube-kernel-scf/vmlinux"
```

`vmlinux` 应解析到同目录中的 `vmlinux-bm`。

## 11. 归档制品

本地当前已保存的完整 openEuler Guest 制品位于：

```text
/home/lyq/Projects/Verification/cubesandbox/artifacts/guest-images/arm64-openEuler-verification-v0.5.0-20260727-full
```

归档目录至少应保存：

```text
cube-guest-image-cpu.img
cube-guest-image-cpu.img.gz
cube-agent
Dockerfile
version
agent-version
BUILD_INFO.md
SHA256SUMS
```

如果同时归档配套内核，还应包含：

```text
vmlinux-bm
kernel-version
kernel.config
kernel-cubesandbox.fragment
```

复制 raw ext4 镜像时应保留稀疏属性：

```bash
cp --sparse=always "$GUEST_IMAGE" /path/to/archive/cube-guest-image-cpu.img
gzip -1 -c "$GUEST_IMAGE" > /path/to/archive/cube-guest-image-cpu.img.gz
```

然后在归档目录生成校验文件：

```bash
cd /path/to/archive
sha256sum \
  Dockerfile \
  agent-version \
  cube-agent \
  cube-guest-image-cpu.img \
  cube-guest-image-cpu.img.gz \
  version > SHA256SUMS

sha256sum -c SHA256SUMS
```

本次历史制品的核心身份为：

| 文件 | 大小 | SHA-256 |
| --- | ---: | --- |
| `cube-guest-image-cpu.img` | 276824064 bytes，264 MiB | `b27e91b3e7451a62ee050b992be779f899ba698de750b689409fbb26ab72a387` |
| `cube-agent` | 12904944 bytes | `6383e920e5503ed148a53bd7172a8d15d23d6971fb8d18488825008d2af18e3d` |

历史摘要仅用于识别已经归档的这一次构建。新构建受包更新、Docker layer、文件时间和 Agent 构建元数据影响，SHA-256 可以不同。

## 12. 部署和生效验证

部署机上的目标位置为：

```text
/usr/local/services/cubetoolbox/cube-image/cube-guest-image-cpu.img
/usr/local/services/cubetoolbox/cube-image/version
/usr/local/services/cubetoolbox/cube-image/agent-version
```

替换前必须：

- 确认没有运行中的 Sandbox 和 Template 构建任务。
- 备份当前 Guest image、version 和 agent-version。
- 停止 `cube-sandbox-cubelet.service`。
- 使用同一文件系统内的临时文件和 `mv` 完成原子替换。
- 重启 Cubelet 并确认 API 健康。
- 新建 Template；已有 Template 仍绑定旧 Guest image 生成的快照，不会自动切换。

完整替换和回滚步骤见：

- [`CUBESANDBOX_GUEST_IMAGE_REPLACEMENT.md`](CUBESANDBOX_GUEST_IMAGE_REPLACEMENT.md)

Guest image、OCI 镜像和内核的关系见：

- [`CUBESANDBOX_GUEST_IMAGE_OCI_VMLINUX_RELATIONSHIP.md`](CUBESANDBOX_GUEST_IMAGE_OCI_VMLINUX_RELATIONSHIP.md)

## 13. 常见问题

### 13.1 `mkfs.ext4` 不支持 `-d`

说明构建机的 e2fsprogs 太旧。升级 e2fsprogs，不要改成先 mount loop 再复制的临时流程，否则会偏离官方构建路径并引入权限、清理和并发风险。

### 13.2 Agent 架构错误

如果 `file cube-agent` 显示 x86-64，说明 builder 架构或构建目标错误。ARM64 Guest 必须使用 AArch64 Agent。不要仅凭文件名判断架构。

### 13.3 Agent 是动态链接程序

Guest image 可能缺少与编译机完全一致的动态 loader 或库。推荐使用项目默认的 musl 静态构建，使 `/sbin/init` 不依赖 Guest 发行版的 glibc 版本。

### 13.4 Guest 启动时报 DAX/ext4 错误

首先确认 ext4 block size 为 4096。如果镜像正确，还需检查 `vmlinux-bm` 是否把 ext4、DAX、virtio-pmem 等启动关键能力编译为 built-in。

### 13.5 VMM 报 `PmemSizeNotAligned`

检查 raw image 文件大小是否是 2 MiB 的整数倍。不要在归档或传输后任意 truncate 镜像。

### 13.6 容器内显示 Ubuntu 而不是 openEuler

这是正常现象。容器内 `/etc/os-release` 来自用户 OCI 镜像；Guest image 的 openEuler 用户态位于微虚拟机基础根文件系统中。应使用 `debugfs` 或 Guest 调试入口检查 Guest image 身份。

### 13.7 替换后仍使用旧 Guest image

已有 Template 含旧 Guest image 生成的快照。替换部署文件和重启 Cubelet 后，必须创建新 Template，再使用新 Template 创建 Sandbox 验证。

## 14. 构建验收清单

- [ ] 构建机为 AArch64 openEuler 24.03 LTS-SP3。
- [ ] 记录 CubeSandbox tag、commit 和工作区修改。
- [ ] openEuler Dockerfile 固定使用 `openeuler/openeuler:24.03-lts-sp3`。
- [ ] `cube-agent` 是静态链接的 AArch64 ELF。
- [ ] `/sbin/init` 与本次编译的 `cube-agent` 摘要一致。
- [ ] Guest `/etc/os-release` 显示 openEuler 24.03 LTS-SP3。
- [ ] Guest image 是 4 KiB block 的 clean ext4。
- [ ] Guest image 文件大小按 2 MiB 对齐。
- [ ] `version` 和 `agent-version` 内容正确。
- [ ] 配套 `vmlinux-bm` 是 ARM64 boot `Image`，不是 ELF `vmlinux`。
- [ ] 归档包含 BUILD_INFO 和 SHA256SUMS，且校验通过。
- [ ] 部署前保留旧镜像，部署后通过新 Template 验证。
