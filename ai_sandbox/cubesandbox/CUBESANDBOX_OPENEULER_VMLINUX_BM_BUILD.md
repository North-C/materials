# CubeSandbox openEuler ARM64 `vmlinux-bm` 构建手册

## 1. 目标和产物说明

本文记录在 `root@192.168.25.65` 上，使用 openEuler 24.03 LTS-SP3 的内核源码和发行版配置，为 CubeSandbox 构建 ARM64 Guest Kernel 的完整过程。

最终运行时产物名为：

```text
vmlinux-bm
```

需要特别注意，CubeSandbox 所称的 `vmlinux-bm` 实际是 Linux 构建输出中的未压缩 ARM64 启动映像：

```text
arch/arm64/boot/Image
```

它不是构建目录根部带调试信息的 ELF 文件 `vmlinux`。不能直接执行以下错误复制：

```bash
# 错误：这个 vmlinux 是 ELF 调试/链接产物，不是 CubeSandbox 所需的启动 Image。
cp build/vmlinux vmlinux-bm
```

正确关系是：

```text
build/arch/arm64/boot/Image -> output/vmlinux-bm
```

## 2. 本次构建基线

| 项目 | 本次使用值 |
| --- | --- |
| 构建主机 | `root@192.168.25.65` |
| 构建架构 | AArch64 原生编译 |
| 构建操作系统 | openEuler 24.03 LTS-SP3 |
| 内核源码包 | `kernel-source-6.6.0-132.0.0.111.oe2403sp3.aarch64` |
| 源码目录 | `/usr/src/linux-6.6.0-132.0.0.111.oe2403sp3.aarch64` |
| 编译器 | GCC `12.3.1-105.oe2403sp3` |
| 基础配置 | openEuler 源码包自带 `.config` |
| CubeSandbox 配置增量 | `kernel-cubesandbox.fragment` |
| 内核 release | `6.6.0-cubesandbox.guest.oe2403sp3` |
| 构建目录 | `/opt/cubesandbox-guest-build/openeuler-kernel-6.6.0-132-cubesandbox` |

本次构建不要求与 CubeSandbox 社区的 `configs/kernel-oc9.aarch64.config` 完全一致。配置策略是以 openEuler 发行版 ARM64 配置为基础，仅把 CubeSandbox Guest 启动和容器运行所需的关键能力补齐或从模块提升为内建。

## 3. 准备构建环境

登录 `.65`：

```bash
ssh root@192.168.25.65
```

确认系统和架构：

```bash
cat /etc/os-release
uname -m
```

预期至少包含：

```text
PRETTY_NAME="openEuler 24.03 (LTS-SP3)"
aarch64
```

安装内核源码和构建依赖：

```bash
dnf install -y \
  kernel-source \
  gcc \
  make \
  bc \
  bison \
  flex \
  openssl-devel \
  elfutils-libelf-devel \
  dwarves \
  perl \
  python3 \
  rsync \
  diffutils \
  findutils \
  tar \
  xz
```

如果需要严格复现本文版本，应安装并确认具体 RPM，而不是直接接受仓库中的更新版本：

```bash
rpm -q kernel-source gcc make bc bison flex \
  openssl-devel elfutils-libelf-devel dwarves python3
```

本次对应的源码包必须显示为：

```text
kernel-source-6.6.0-132.0.0.111.oe2403sp3.aarch64
```

## 4. 准备 CubeSandbox 配置增量

本次实际使用的配置增量已归档在本地：

[`kernel-cubesandbox.fragment`](artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/kernel-cubesandbox.fragment)

它主要确保以下能力直接编入内核：

| 类别 | 关键配置 |
| --- | --- |
| Guest 根盘 | `CONFIG_VIRTIO_PMEM=y`、`CONFIG_BLK_DEV_PMEM=y`、`CONFIG_LIBNVDIMM=y` |
| 根文件系统 | `CONFIG_EXT4_FS=y`、`CONFIG_DAX=y`、`CONFIG_FS_DAX=y` |
| OCI 镜像层 | `CONFIG_VIRTIO_FS=y`、`CONFIG_FUSE_FS=y`、`CONFIG_OVERLAY_FS=y` |
| Shim/Agent 通信 | `CONFIG_VSOCKETS=y`、`CONFIG_VIRTIO_VSOCKETS=y` |
| 基础 virtio 设备 | `CONFIG_VIRTIO_PCI=y`、`CONFIG_VIRTIO_MMIO=y`、`CONFIG_VIRTIO_NET=y` |
| ARM64 串口 | `CONFIG_SERIAL_AMBA_PL011=y`、`CONFIG_SERIAL_AMBA_PL011_CONSOLE=y` |
| 容器隔离 | namespace、cgroup、seccomp 相关配置 |
| 容器网络 | bridge、veth、tun、netfilter、nftables/iptables 相关配置 |

Guest image 不携带完整的 `/lib/modules`，所以根盘、文件系统、virtiofs、vsock 和启动期设备驱动不能只设置为 `m`。

从本地工作机把 fragment 发送到 `.65`：

```bash
scp \
  /home/lyq/Projects/Verification/cubesandbox/artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/kernel-cubesandbox.fragment \
  root@192.168.25.65:/var/tmp/kernel-cubesandbox.fragment
```

## 5. 创建隔离构建目录

以下命令在 `.65` 上以 root 执行：

```bash
set -euo pipefail

KERNEL_SOURCE=/usr/src/linux-6.6.0-132.0.0.111.oe2403sp3.aarch64
KERNEL_BUILD_ROOT=/opt/cubesandbox-guest-build/openeuler-kernel-6.6.0-132-cubesandbox-rebuild
KERNEL_SOURCE_COPY=$KERNEL_BUILD_ROOT/source
KERNEL_BUILD_OUTPUT=$KERNEL_BUILD_ROOT/build
KERNEL_INPUT=$KERNEL_BUILD_ROOT/input
KERNEL_OUTPUT=$KERNEL_BUILD_ROOT/output
KERNEL_FRAGMENT=/var/tmp/kernel-cubesandbox.fragment

test "$(uname -m)" = "aarch64"
test -d "$KERNEL_SOURCE"
test -f "$KERNEL_SOURCE/.config"
test -f "$KERNEL_FRAGMENT"
test ! -e "$KERNEL_BUILD_ROOT"

install -d -m 0755 \
  "$KERNEL_BUILD_ROOT" \
  "$KERNEL_BUILD_OUTPUT" \
  "$KERNEL_INPUT" \
  "$KERNEL_OUTPUT"
cp -a "$KERNEL_SOURCE" "$KERNEL_SOURCE_COPY"
cp "$KERNEL_SOURCE/.config" "$KERNEL_INPUT/openeuler-base.config"
cp "$KERNEL_FRAGMENT" "$KERNEL_INPUT/kernel-cubesandbox.fragment"
```

这里使用新的 `-rebuild` 目录，避免覆盖本次已验证构建。不要直接在 `/usr/src` 下执行清理或编译，因为 RPM 安装的源码树可能包含发行版生成文件，并且应保留为原始输入。

清理复制后的源码树：

```bash
make -C "$KERNEL_SOURCE_COPY" mrproper
```

确认基础配置副本仍然存在：

```bash
test -s "$KERNEL_INPUT/openeuler-base.config"
sha256sum "$KERNEL_INPUT/openeuler-base.config"
```

本次原始 openEuler base config 的 SHA-256 为：

```text
d54ca44a91cc7c5b810198f7d36bf1086afaf7c26c6b51d110c887f5422c723c
```

如果使用了更新的 `kernel-source` 包，该摘要发生变化是正常的，但必须在构建记录中保存新的 RPM 版本和摘要。

## 6. 合并 Kernel config

使用内核自带的 `merge_config.sh` 将 CubeSandbox fragment 叠加到 openEuler base config：

```bash
ARCH=arm64 "$KERNEL_SOURCE_COPY/scripts/kconfig/merge_config.sh" \
  -m \
  -O "$KERNEL_BUILD_OUTPUT" \
  "$KERNEL_INPUT/openeuler-base.config" \
  "$KERNEL_INPUT/kernel-cubesandbox.fragment"
```

随后执行 `olddefconfig`，让内核根据依赖关系补全最终配置：

```bash
make -C "$KERNEL_SOURCE_COPY" \
  O="$KERNEL_BUILD_OUTPUT" \
  ARCH=arm64 \
  olddefconfig
```

验证 fragment 中的每项请求都被最终 Kconfig 接受：

```bash
grep -E '^(CONFIG_[A-Z0-9_]+=|# CONFIG_[A-Z0-9_]+ is not set$)' \
  "$KERNEL_INPUT/kernel-cubesandbox.fragment" \
  > "$KERNEL_BUILD_ROOT/requested.config"

: > "$KERNEL_BUILD_ROOT/config-mismatches"
while IFS= read -r requested; do
  if ! grep -Fqx "$requested" "$KERNEL_BUILD_OUTPUT/.config"; then
    printf '%s\n' "$requested" >> "$KERNEL_BUILD_ROOT/config-mismatches"
  fi
done < "$KERNEL_BUILD_ROOT/requested.config"

test ! -s "$KERNEL_BUILD_ROOT/config-mismatches"
```

如果最后一条命令失败，应先检查 Kconfig 依赖关系，不能带着被拒绝的关键配置继续部署。本次构建的 `config-mismatches` 为空。

保存最终配置：

```bash
cp "$KERNEL_BUILD_OUTPUT/.config" "$KERNEL_OUTPUT/kernel.config"
```

至少确认以下启动关键项为内建 `y`：

```bash
grep -E '^CONFIG_(ARM64_4K_PAGES|DEVTMPFS|DEVTMPFS_MOUNT|EXT4_FS|DAX|FS_DAX|LIBNVDIMM|BLK_DEV_PMEM|VIRTIO_PMEM|VIRTIO_PCI|VIRTIO_MMIO|VIRTIO_FS|VSOCKETS|VIRTIO_VSOCKETS|OVERLAY_FS)=y$' \
  "$KERNEL_BUILD_OUTPUT/.config"
```

确认本次自定义 release 后缀：

```bash
grep -E '^CONFIG_LOCALVERSION=|^# CONFIG_LOCALVERSION_AUTO is not set$' \
  "$KERNEL_BUILD_OUTPUT/.config"
```

预期为：

```text
CONFIG_LOCALVERSION="-cubesandbox.guest.oe2403sp3"
# CONFIG_LOCALVERSION_AUTO is not set
```

## 7. 编译 ARM64 Image

`.65` 是 AArch64 主机，因此使用原生 GCC，不需要设置 `CROSS_COMPILE`。

本次使用 64 个并行任务：

```bash
make -C "$KERNEL_SOURCE_COPY" \
  O="$KERNEL_BUILD_OUTPUT" \
  ARCH=arm64 \
  -j64 \
  Image 2>&1 | tee "$KERNEL_BUILD_ROOT/build.log"
```

也可以根据机器 CPU 和内存情况调整 `-j`，但应避免无上限并发影响同机业务。

成功结束时，日志尾部应包含类似内容：

```text
LD      vmlinux
NM      System.map
OBJCOPY arch/arm64/boot/Image
```

获取内核 release：

```bash
make -s -C "$KERNEL_SOURCE_COPY" \
  O="$KERNEL_BUILD_OUTPUT" \
  ARCH=arm64 \
  kernelrelease | tee "$KERNEL_OUTPUT/kernel-version"
```

预期为：

```text
6.6.0-cubesandbox.guest.oe2403sp3
```

## 8. 生成 `vmlinux-bm` 制品

把 ARM64 `Image` 复制为 CubeSandbox 约定的文件名：

```bash
install -m 0644 \
  "$KERNEL_BUILD_OUTPUT/arch/arm64/boot/Image" \
  "$KERNEL_OUTPUT/vmlinux-bm"

install -m 0644 \
  "$KERNEL_BUILD_OUTPUT/System.map" \
  "$KERNEL_OUTPUT/System.map"
```

检查文件格式：

```bash
file "$KERNEL_OUTPUT/vmlinux-bm"
```

预期格式为：

```text
Linux kernel ARM64 boot executable Image, little-endian, 4K pages
```

如果显示 `ELF 64-bit LSB executable`，说明错误地复制了 `build/vmlinux`，不能部署给 CubeSandbox。

## 9. 验证嵌入配置

由于 fragment 启用了 `CONFIG_IKCONFIG=y`，可以从最终 `vmlinux-bm` 中重新提取配置：

```bash
"$KERNEL_SOURCE_COPY/scripts/extract-ikconfig" \
  "$KERNEL_OUTPUT/vmlinux-bm" \
  > "$KERNEL_OUTPUT/kernel.config.extracted"

cmp "$KERNEL_OUTPUT/kernel.config" \
  "$KERNEL_OUTPUT/kernel.config.extracted"
```

`cmp` 无输出且退出码为 0，表示嵌入配置与构建配置完全一致。

再次从最终产物检查关键能力：

```bash
grep -E '^CONFIG_(VIRTIO_PMEM|EXT4_FS|DAX|FS_DAX|VIRTIO_FS|VSOCKETS|VIRTIO_VSOCKETS|OVERLAY_FS)=y$' \
  "$KERNEL_OUTPUT/kernel.config.extracted"
```

生成校验清单：

```bash
cd "$KERNEL_OUTPUT"
sha256sum \
  vmlinux-bm \
  kernel.config \
  kernel.config.extracted \
  kernel-version \
  System.map \
  > SHA256SUMS
sha256sum -c SHA256SUMS
```

本次已经部署验证的 `vmlinux-bm` 信息为：

```text
size:    41576960 bytes
sha256:  c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e
release: 6.6.0-cubesandbox.guest.oe2403sp3
```

新编译时，构建时间、构建用户或工具链变化可能使二进制摘要不同。不要强行要求新构建匹配上述 SHA-256；应验证文件格式、内核 release、最终 config，并记录新产物自己的摘要。

## 10. 归档构建结果

建议至少保存：

```text
vmlinux-bm
kernel.config
kernel.config.extracted
openeuler-base.config
kernel-cubesandbox.fragment
kernel-version
System.map
build.log
config-mismatches
SHA256SUMS
```

把构建输入和日志复制到输出目录，并为完整归档重新生成校验清单：

```bash
install -m 0644 \
  "$KERNEL_INPUT/openeuler-base.config" \
  "$KERNEL_OUTPUT/openeuler-base.config"
install -m 0644 \
  "$KERNEL_INPUT/kernel-cubesandbox.fragment" \
  "$KERNEL_OUTPUT/kernel-cubesandbox.fragment"
install -m 0644 \
  "$KERNEL_BUILD_ROOT/config-mismatches" \
  "$KERNEL_OUTPUT/config-mismatches"
install -m 0644 \
  "$KERNEL_BUILD_ROOT/build.log" \
  "$KERNEL_OUTPUT/build.log"

cd "$KERNEL_OUTPUT"
sha256sum \
  vmlinux-bm \
  kernel.config \
  kernel.config.extracted \
  openeuler-base.config \
  kernel-cubesandbox.fragment \
  config-mismatches \
  kernel-version \
  System.map \
  build.log \
  > SHA256SUMS
sha256sum -c SHA256SUMS
```

本次构建的本地归档位于：

```text
/home/lyq/Projects/Verification/cubesandbox/artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727
```

其中：

- [`BUILD_INFO.md`](artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/BUILD_INFO.md) 记录构建身份。
- [`kernel.config`](artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/kernel.config) 是最终配置。
- [`openeuler-base.config`](artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/openeuler-base.config) 是发行版基础配置。
- [`build.log`](artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/build.log) 是完整编译日志。
- [`SHA256SUMS`](artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/SHA256SUMS) 是归档校验清单。

`.65` 上本次原始构建目录仍保留在：

```text
/opt/cubesandbox-guest-build/openeuler-kernel-6.6.0-132-cubesandbox
```

完整 Guest 运行时布局位于：

```text
/opt/cubesandbox-guest-build/openEuler-full-v0.5.0-20260727/runtime-layout
```

## 11. 部署到 CubeSandbox

one-click 部署中，普通 Guest Kernel 的目标文件为：

```text
/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-bm
```

运行时实际入口为：

```text
/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux -> vmlinux-bm
```

部署前必须满足：

- 当前没有正在运行的 Sandbox。
- 当前没有 Template 构建任务。
- 已备份旧 `vmlinux-bm`。
- 已记录新旧文件 SHA-256。
- Cubelet 和 CubeMaster 在替换期间停止。

推荐先传到临时路径：

```bash
scp \
  /home/lyq/Projects/Verification/cubesandbox/artifacts/kernels/arm64-openEuler-6.6.0-cubesandbox-20260727/vmlinux-bm \
  root@192.168.25.90:/var/tmp/vmlinux-bm.openEuler.new
```

在 `.90` 确认环境为空后，以 root 执行：

```bash
set -euo pipefail

KERNEL_DIR=/usr/local/services/cubetoolbox/cube-kernel-scf
KERNEL_NEW=/var/tmp/vmlinux-bm.openEuler.new
KERNEL_DST=$KERNEL_DIR/vmlinux-bm
KERNEL_LINK=$KERNEL_DIR/vmlinux
KERNEL_STAGE=$KERNEL_DIR/.vmlinux-bm.new
STAMP=$(date +%Y%m%d-%H%M%S)

test -f "$KERNEL_NEW"
test -f "$KERNEL_DST"
file "$KERNEL_NEW"
sha256sum "$KERNEL_NEW"

KERNEL_UID=$(stat -c %u "$KERNEL_DST")
KERNEL_GID=$(stat -c %g "$KERNEL_DST")
cp -a "$KERNEL_DST" "$KERNEL_DST.backup-$STAMP"

systemctl stop \
  cube-sandbox-cubemaster.service \
  cube-sandbox-cubelet.service

install -o "$KERNEL_UID" -g "$KERNEL_GID" -m 0644 \
  "$KERNEL_NEW" \
  "$KERNEL_STAGE"
cmp "$KERNEL_NEW" "$KERNEL_STAGE"
mv -f "$KERNEL_STAGE" "$KERNEL_DST"
ln -sfn vmlinux-bm "$KERNEL_LINK"

systemctl start \
  cube-sandbox-cubelet.service \
  cube-sandbox-cubemaster.service
```

替换后检查：

```bash
readlink -f /usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux
sha256sum /usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-bm
systemctl is-active cube-sandbox-cubelet.service
systemctl is-active cube-sandbox-cubemaster.service
curl -fsS http://127.0.0.1:19090/healthz
```

已有 Template 会保留旧的 kernel artifact 或兼容性元数据。必须使用新内核创建一个新 Template，再在新沙箱内执行：

```bash
uname -r
```

预期为：

```text
6.6.0-cubesandbox.guest.oe2403sp3
```

只有安装目录摘要、Template kernel artifact 摘要和沙箱内 `uname -r` 三者一致，才能确认新内核真正生效。

## 12. 常见问题

### 12.1 `vmlinux-bm` 显示为 ELF

原因是复制了 `build/vmlinux`。应改用：

```text
build/arch/arm64/boot/Image
```

### 12.2 Guest 无法挂载 `/dev/pmem0`

优先检查以下配置是否为 `y`：

```text
CONFIG_VIRTIO_PMEM
CONFIG_LIBNVDIMM
CONFIG_BLK_DEV_PMEM
CONFIG_DAX
CONFIG_FS_DAX
CONFIG_EXT4_FS
```

### 12.3 Shim 无法连接 `cube-agent`

优先检查：

```text
CONFIG_VSOCKETS=y
CONFIG_VIRTIO_VSOCKETS=y
```

同时检查 Guest image 内 `/sbin/init` 是否为可执行的 `cube-agent`。

### 12.4 OCI 镜像层无法挂载

优先检查：

```text
CONFIG_FUSE_FS=y
CONFIG_VIRTIO_FS=y
CONFIG_OVERLAY_FS=y
```

### 12.5 新内核文件已替换，但沙箱仍显示旧版本

依次检查：

1. `cube-kernel-scf/vmlinux` 是否仍指向旧文件。
2. Cubelet 和 CubeMaster 是否已重启。
3. 是否仍在使用基于旧内核生成的 Template。
4. 新 Template 的 kernel artifact 摘要是否与安装目录文件一致。

## 13. 本次验证结果

本文记录的 openEuler 内核已部署到 `.90`，并通过新建 Template 验证：

```text
kernel release: 6.6.0-cubesandbox.guest.oe2403sp3
kernel sha256: c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e
```

六轮并发矩阵累计完成 `6120/6120` 次 Sandbox 创建，没有再出现 `reset guest time failed`。详细结果见：

[`CUBESANDBOX_FULL_OPENEULER_KERNEL_TEMPLATE_PERF_20260727.md`](CUBESANDBOX_FULL_OPENEULER_KERNEL_TEMPLATE_PERF_20260727.md)
