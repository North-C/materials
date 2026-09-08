# openEuler 24.03 LTS-SP1 合并 irqbypass XArray 补丁指南

本文说明如何基于 openEuler 24.03 LTS-SP1 官方内核源码，合入配套的 irqbypass XArray 补丁，生成具有独立版本名的 ARM64 内核 RPM。

本文对应的已验证基线为：

```text
官方源码版本：6.6.0-145.1.20.157.oe2403sp1
目标架构：aarch64
补丁版本：kvm-irqbypass-xarray-v2
补丁 SHA256：b160d84635f49a0c2e4367210003e08fb9cc1fca43273396e2911e85cb8db575
最终 kernelrelease：6.6.0-145.1.20.157.oe2403sp1.aarch64-sbench-irqbypass-xarray-v2
```

## 1. 补丁解决什么问题

原始 irqbypass manager 使用两个全局链表保存 IRQ producer 和 consumer。注册或注销对象时，需要在线性链表中根据共享 `token` 查找匹配对象。

补丁将 producer/consumer 容器改为 XArray，并将非空 `token` 指针转换为 `unsigned long` 索引。注册和注销路径使用 `xa_load()`、`xa_insert()`、`xa_erase()` 定位对象，减少临界区内的线性遍历。

补丁没有移除 irqbypass 全局 mutex，XArray 也不应被描述成“无锁”。mutex 仍用于保护 producer/consumer 配对、连接回调和模块引用计数的一致性。

## 2. 配套补丁

执行本文流程前，需要准备普通 unified diff 格式的补丁文件：

```text
kvm-irqbypass-xarray-v2.patch
SHA256 b160d84635f49a0c2e4367210003e08fb9cc1fca43273396e2911e85cb8db575
```

补丁应从受信任的交付渠道获取。下载或复制后必须先验证 SHA256，不要对来源或内容不明的补丁执行内核构建。

## 3. 功能性源码改动

补丁只修改两个功能源码文件：

| 文件 | 修改内容 |
|---|---|
| `include/linux/irqbypass.h` | 删除 `linux/list.h`；删除 producer/consumer 中仅供链表管理使用的 `struct list_head node`；注释由 list 更新为 XArray |
| `virt/lib/irqbypass.c` | 用两个 `DEFINE_XARRAY` 替换全局链表；注册、匹配、注销改用 XArray；连接失败时回滚已插入项；模块退出时销毁 XArray |

补丁统计：

```text
 include/linux/irqbypass.h |   8 ---
 virt/lib/irqbypass.c      | 127 +++++++++++++++++++++++----------------------
 2 files changed, 65 insertions(+), 70 deletions(-)
```

没有修改以下内容：

- KVM、IRQFD、eventfd 调用方；
- ARM64 架构代码；
- `__connect()`、`__disconnect()` 的回调语义；
- irqbypass 对外导出函数的名称和签名；
- Kconfig 和 Makefile。

兼容性注意：补丁删除了两个公开结构体中的 `node` 字段。当前官方源码树内调用方可以正常构建，但如果目标环境存在直接访问或初始化 `.node` 的 out-of-tree 模块，需要先检查并适配这些模块，不能只验证内核本体。

### 3.1 头文件变化

producer 和 consumer 不再嵌入 irqbypass manager 私有链表节点：

```c
struct irq_bypass_producer {
-       struct list_head node;
        void *token;
        /* callbacks ... */
};

struct irq_bypass_consumer {
-       struct list_head node;
        void *token;
        /* callbacks ... */
};
```

### 3.2 容器变化

```c
-static LIST_HEAD(producers);
-static LIST_HEAD(consumers);
+static DEFINE_XARRAY(producers);
+static DEFINE_XARRAY(consumers);
```

### 3.3 注册路径

注册 producer/consumer 时：

1. 将 `token` 转为 `unsigned long`；
2. `xa_load()` 检查相同 token 是否已经注册；
3. `xa_insert()` 保存当前对象；
4. `xa_load()` 查找另一端的匹配对象；
5. 调用原有 `__connect()`；
6. 如果连接失败，用 `xa_erase()` 回滚刚插入的对象。

### 3.4 注销路径

注销时通过 token 直接加载对象，校验对象指针一致后执行 `__disconnect()` 和 `xa_erase()`。

### 3.5 模块退出

```c
static void __exit irqbypass_exit(void)
{
        xa_destroy(&producers);
        xa_destroy(&consumers);
}
module_exit(irqbypass_exit);
```

## 4. 准备官方 SP1 源码

以下命令使用独立目录，不覆盖系统源码树：

```bash
BUILD_ROOT=/var/tmp/openeuler-sp1-irqbypass-build
SOURCE_REPO=https://repo.openeuler.org/openEuler-24.03-LTS-SP1/update/source/
KERNEL_NVR=6.6.0-145.1.20.157.oe2403sp1

mkdir -p "$BUILD_ROOT/download"
mkdir -p "$BUILD_ROOT/rpmbuild"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
```

确认系统具备 `dnf download`、`rpm`、`rpmbuild`、`patch`、`make`、GCC、binutils、OpenSSL、ELF/BTF 等内核构建依赖。

只从 openEuler 24.03 LTS-SP1 source repo 下载源码包：

```bash
dnf --disablerepo='*' \
  --repofrompath=oe2403sp1-source,"$SOURCE_REPO" \
  --enablerepo=oe2403sp1-source \
  download --source \
  --destdir "$BUILD_ROOT/download" \
  "kernel-$KERNEL_NVR"
```

对本指南的已验证源码包，应得到：

```text
kernel-6.6.0-145.1.20.157.oe2403sp1.src.rpm
SHA256 cee10830e7841ce139f96b30d7d32b6319e66f8e1e1005b69510d32b273516ba
```

先验证文件身份：

```bash
sha256sum "$BUILD_ROOT/download/kernel-$KERNEL_NVR.src.rpm"
rpm -qp --qf '%{NAME}|%{VERSION}|%{RELEASE}|%{ARCH}\n' \
  "$BUILD_ROOT/download/kernel-$KERNEL_NVR.src.rpm"
```

将 SRPM 内容安装到隔离的 rpmbuild 目录：

```bash
rpm -ivh \
  --define "_topdir $BUILD_ROOT/rpmbuild" \
  "$BUILD_ROOT/download/kernel-$KERNEL_NVR.src.rpm"
```

解开官方源码树：

```bash
mkdir -p "$BUILD_ROOT/source"

tar -xzf "$BUILD_ROOT/rpmbuild/SOURCES/kernel.tar.gz" \
  -C "$BUILD_ROOT/source" \
  --strip-components=1

test -f "$BUILD_ROOT/source/include/linux/irqbypass.h"
test -f "$BUILD_ROOT/source/virt/lib/irqbypass.c"
```

## 5. 合并补丁

将包内补丁复制到构建目录：

```bash
install -m 0644 kvm-irqbypass-xarray-v2.patch \
  "$BUILD_ROOT/kvm-irqbypass-xarray-v2.patch"

sha256sum "$BUILD_ROOT/kvm-irqbypass-xarray-v2.patch"
```

必须先执行零 fuzz dry-run：

```bash
cd "$BUILD_ROOT/source"

patch --dry-run --fuzz=0 -p1 \
  < "$BUILD_ROOT/kvm-irqbypass-xarray-v2.patch"
```

预期只出现：

```text
checking file include/linux/irqbypass.h
checking file virt/lib/irqbypass.c
```

dry-run 成功后正式应用：

```bash
patch --fuzz=0 -p1 \
  < "$BUILD_ROOT/kvm-irqbypass-xarray-v2.patch"
```

本流程不是 Git merge/cherry-pick。官方源码来自 SRPM 中的 tarball，补丁以标准 unified diff 直接应用；`--fuzz=0` 禁止上下文模糊匹配。

## 6. 展示合并后的修改状态

### 6.1 显示修改文件和统计

```bash
git apply --stat "$BUILD_ROOT/kvm-irqbypass-xarray-v2.patch"
```

即使源码树不是 Git 仓库，`git apply --stat` 也可用于读取补丁统计，不会修改文件。

### 6.2 确认 XArray 标记

```bash
grep -nE 'DEFINE_XARRAY|xa_(load|insert|erase)|xa_destroy' \
  "$BUILD_ROOT/source/virt/lib/irqbypass.c"
```

### 6.3 使用反向 dry-run 确认补丁已经应用

```bash
cd "$BUILD_ROOT/source"

patch --dry-run --fuzz=0 -R -p1 \
  < "$BUILD_ROOT/kvm-irqbypass-xarray-v2.patch"
```

如果反向 dry-run 能准确检查上述两个文件，说明当前源码状态包含这份补丁。这里只使用 `--dry-run`，不会真的回退源码。

### 6.4 已验证的合入后文件 SHA256

本指南对应的官方源码基线合入后：

```text
2ad55afb0824cbe5ecc913d0bdfef7c4ac5a805cbdd912ce1c3b4e2b46b103be  include/linux/irqbypass.h
8facfe90ab13c9dd5ee7ae7368163398f63b4b91b01a71bd60ae8b3e4866c268  virt/lib/irqbypass.c
```

验证命令：

```bash
sha256sum \
  "$BUILD_ROOT/source/include/linux/irqbypass.h" \
  "$BUILD_ROOT/source/virt/lib/irqbypass.c"
```

## 7. 配置独立内核版本

不要复用官方内核的同名 release，否则可能覆盖 `/boot` 或 `/lib/modules` 中的现有文件。

以当前系统已安装的对应官方内核配置为起点：

```bash
BASE_KERNEL=6.6.0-145.1.20.157.oe2403sp1.aarch64
LOCAL_SUFFIX=-145.1.20.157.oe2403sp1.aarch64-sbench-irqbypass-xarray-v2

cd "$BUILD_ROOT/source"

cp -a "/boot/config-$BASE_KERNEL" .config
scripts/config --set-str LOCALVERSION "$LOCAL_SUFFIX"
scripts/config --disable LOCALVERSION_AUTO
make olddefconfig
```

检查关键配置和最终 release：

```bash
grep '^CONFIG_IRQ_BYPASS_MANAGER=' .config
grep -E 'CONFIG_LOCALVERSION|CONFIG_LOCALVERSION_AUTO' .config
make -s kernelrelease
```

预期：

```text
CONFIG_IRQ_BYPASS_MANAGER=y
CONFIG_LOCALVERSION="-145.1.20.157.oe2403sp1.aarch64-sbench-irqbypass-xarray-v2"
# CONFIG_LOCALVERSION_AUTO is not set
6.6.0-145.1.20.157.oe2403sp1.aarch64-sbench-irqbypass-xarray-v2
```

## 8. 准备 openEuler 官方证书输入

直接使用内核树的 `binrpm-pkg` 时，配置会引用 `certs/openeuler-cert.pem`。该文件来自 SRPM 的官方证书材料，但不会由前面的源码 tar 解包自动放到目标名字。

构建前复制：

```bash
install -m 0644 \
  "$BUILD_ROOT/rpmbuild/SOURCES/openeuler_kernel_cert.cer" \
  "$BUILD_ROOT/source/certs/openeuler-cert.pem"

install -m 0644 \
  "$BUILD_ROOT/rpmbuild/SOURCES/x509.genkey" \
  "$BUILD_ROOT/source/certs/x509.genkey"
```

不要通过关闭 `CONFIG_SYSTEM_TRUSTED_KEYS`、模块签名或其他安全配置来绕过缺失文件。

## 9. 编译 RPM

在 ARM64 openEuler 主机上执行：

```bash
cd "$BUILD_ROOT/source"

nice -n 5 make -j"$(nproc)" binrpm-pkg \
  2>&1 | tee "$BUILD_ROOT/build.log"
```

RPM 默认输出到：

```text
$BUILD_ROOT/source/rpmbuild/RPMS/aarch64/
```

本次已验证产物为：

```text
kernel-6.6.0_145.1.20.157.oe2403sp1.aarch64_sbench_irqbypass_xarray_v2-3.aarch64.rpm
SHA256 520ab63949aa617425d75ffa1fdf6f20513d1da653dcf32452a3cfd090e51b55
```

## 10. 安装前验证

```bash
KERNEL_RPM="$BUILD_ROOT/source/rpmbuild/RPMS/aarch64/kernel-6.6.0_145.1.20.157.oe2403sp1.aarch64_sbench_irqbypass_xarray_v2-3.aarch64.rpm"

rpm -qp --qf '%{NAME}|%{VERSION}|%{RELEASE}|%{ARCH}\n' "$KERNEL_RPM"
rpm -K "$KERNEL_RPM"
rpm -qlp "$KERNEL_RPM" | grep -E '/boot/(vmlinuz|config|System.map)|/lib/modules/'
rpm -ivh --test "$KERNEL_RPM"
```

可以进一步确认编译对象引用了 XArray 操作：

```bash
nm "$BUILD_ROOT/source/virt/lib/irqbypass.o" \
  | grep -E ' (U|T) (xa_(load|insert|erase)|irq_bypass_)' \
  | sort
```

## 11. 可选：新增安装和切换启动项

以下操作会修改目标主机的内核安装和启动配置。执行前应确认维护窗口、控制台访问和重启授权。

只新增安装，不删除其他内核：

```bash
rpm -ivh "$KERNEL_RPM"
```

禁止使用会替换现有内核包的 `rpm -Uvh`。

验证 boot 文件和 module tree：

```bash
KERNEL_RELEASE=6.6.0-145.1.20.157.oe2403sp1.aarch64-sbench-irqbypass-xarray-v2

test -f "/boot/vmlinuz-$KERNEL_RELEASE"
test -f "/boot/initramfs-$KERNEL_RELEASE.img"
test -d "/lib/modules/$KERNEL_RELEASE"
```

设置默认启动项：

```bash
grubby --info="/boot/vmlinuz-$KERNEL_RELEASE"
grubby --set-default="/boot/vmlinuz-$KERNEL_RELEASE"
grubby --default-kernel
```

获得明确重启授权后才执行 reboot。启动后验证：

```bash
uname -r
grubby --default-kernel
systemctl --failed
```

## 12. 回滚边界

- 不卸载旧内核；保留官方 SP1、SP3 和原有自研内核。
- 如果新内核无法启动，从 GRUB 选择此前验证通过的内核。
- 系统恢复后使用 `grubby --set-default=/boot/vmlinuz-<旧版本>` 恢复默认项。
- 回滚启动项不等于删除新 RPM；删除内核必须另行确认准确目标。

## 13. 已验证构建结果

本文对应的验证结果：

```text
源码 RPM SHA256：cee10830e7841ce139f96b30d7d32b6319e66f8e1e1005b69510d32b273516ba
补丁 SHA256：    b160d84635f49a0c2e4367210003e08fb9cc1fca43273396e2911e85cb8db575
构建 RPM SHA256：520ab63949aa617425d75ffa1fdf6f20513d1da653dcf32452a3cfd090e51b55
grubby default: /boot/vmlinuz-6.6.0-145.1.20.157.oe2403sp1.aarch64-sbench-irqbypass-xarray-v2
uname -r:       6.6.0-145.1.20.157.oe2403sp1.aarch64-sbench-irqbypass-xarray-v2
```
