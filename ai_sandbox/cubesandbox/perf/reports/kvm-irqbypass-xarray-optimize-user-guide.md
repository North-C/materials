# KVM irqbypass XArray 锁竞争优化 用户指南

## 介绍

### 简介

本文介绍如何在 openEuler ARM64 宿主机内核中合入 KVM irqbypass XArray 优化补丁，
重新编译并安装内核 RPM，从而降低 [CubeSandbox](https://github.com/TencentCloud/CubeSandbox)
高并发启动和 Snapshot restore 场景中的 KVM irqfd 注册锁竞争。

在 KVM 虚拟化中，irqfd、eventfd、VGIC、Virtio MSI-X 等路径会通过 irqbypass
manager 关联 producer 和 consumer。原实现使用全局链表保存对象，注册时需要在同一个
mutex 保护下遍历链表并按 token 匹配对象。

[CubeSandbox](https://cubesandbox.com/zh/guide/introduction.html) 在 ARM64 高并发创建
Sandbox、从 Snapshot 创建 Sandbox、Rollback、Clone、Pause/Resume 等流程中，会集中触发
VM restore、VGIC route 恢复和 Virtio MSI-X irqfd 注册。并发度升高后，
`irq_bypass_register_consumer()` 的 mutex 等待可能成为启动延迟和尾延迟的主要来源。

KVM irqbypass XArray 补丁将 producers 和 consumers 从链表改为 XArray，以 token
指针作为索引，将注册路径中的线性遍历改为直接查找。该优化不改变 Guest 可见行为，
主要降低宿主机 KVM 高并发 irqfd 注册时的锁等待。

### 功能架构

KVM irqbypass XArray 优化由对象存储结构、注册查找路径和异常回滚路径共同组成。

| 模块 | 功能 |
|---|---|
| producer/consumer 存储结构 | 将全局链表替换为 XArray，分别维护 producers 和 consumers。 |
| token 快速查找 | 使用 token 指针作为 XArray index，通过 `xa_load()` 查找匹配对象。 |
| 注册与注销路径 | 使用 `xa_insert()`、`xa_erase()` 替换链表插入和删除。 |
| 失败回滚路径 | 在 connect 失败时擦除已插入对象，避免残留脏状态。 |

典型流程如下。

1. KVM 创建 irqfd 时注册 irqbypass consumer。
2. irqbypass manager 根据 token 在 XArray 中查找对应 producer。
3. 如果 producer 已存在，则执行 connect；否则先记录 consumer。
4. unregister 时按 token 查找并删除对象。
5. 高并发下避免每次注册都遍历全局链表，缩短 mutex 持有时间。

### 补丁来源

补丁来源为 Linux KVM 社区邮件列表中的 irqbypass XArray 优化补丁。推荐以公开邮件列表
或经过审核的补丁归档为准。

| 补丁 | 来源 |
|---|---|
| KVM: irqbypass: Convert producers/consumers single linked list to XArray | https://lore.kernel.org/all/20230801115646.33990-1-likexu@tencent.com/ |
| v2 patch series | https://lore.kernel.org/all/20230802051700.52321-1-likexu@tencent.com/ |

如果目标内核基线缺少 producer unregister 相关修复，建议同时评估 v2 patch series 中的
前置修复补丁，避免只移植 XArray 主补丁后留下兼容性风险。

### CubeSandbox 相关链接与术语

本文涉及的 CubeSandbox 组件和测试术语如下。

| 术语 | 说明 | 参考链接 |
|---|---|---|
| CubeSandbox | 面向 AI Agent 和代码执行场景的高性能沙箱系统，提供 E2B 兼容 API、模板、快照、克隆、回滚等能力。 | [项目仓库](https://github.com/TencentCloud/CubeSandbox)、[中文简介](https://cubesandbox.com/zh/guide/introduction.html) |
| Sandbox | CubeSandbox 对外暴露的沙箱实例。一次 Sandbox 创建通常会在宿主机侧完成模板解析、运行态准备、VMM 启动或恢复等工作。 | [快速开始](https://cubesandbox.com/zh/guide/quickstart.html) |
| Template | CubeSandbox 用来创建 Sandbox 的模板。模板通常来自 OCI 镜像或已有运行态，包含 rootfs、启动命令、端口、探针等信息。 | [模板概览](https://cubesandbox.com/zh/guide/templates.html)、[从 OCI 镜像制作模板](https://cubesandbox.com/zh/guide/tutorials/template-from-image.html) |
| Snapshot / Rollback / Clone | CubeSandbox 的运行态状态管理能力。Snapshot 保存运行态，Rollback 回退到指定状态，Clone 从运行中 Sandbox 派生多个副本。 | [快照、回滚与克隆](https://cubesandbox.com/zh/guide/snapshot-rollback-clone.html) |
| Pause / Resume | CubeSandbox 的暂停和恢复能力，属于运行态生命周期操作。它和用户可见的 runtime Snapshot 不是同一个对象。 | [Snapshot 运行机制分析](https://cubesandbox.com/zh/guide/snapshot-runtime-deep-dive.html) |
| CubeSandbox API / CubeAPI | CubeSandbox 的 E2B 兼容 REST API，默认监听 `3000` 端口。`cube-bench` 和 Python SDK 测试脚本都会通过该 API 创建或操作 Sandbox。 | [快速开始](https://cubesandbox.com/zh/guide/quickstart.html)、[鉴权配置](https://cubesandbox.com/zh/guide/authentication.html) |
| Cubelet | CubeSandbox 节点侧组件，负责节点上的镜像、模板、Sandbox 生命周期和 VMM 调度等操作。 | [服务管理与日志](https://cubesandbox.com/zh/guide/service-management.html) |
| VMM restore | CubeSandbox 在从 Template、Snapshot 或 pause checkpoint 恢复 Sandbox 时，底层 VMM 重建 VM 状态的过程。该路径会恢复 VGIC、Virtio 设备和 irqfd/MSI-X 状态。 | [Snapshot 运行机制分析](https://cubesandbox.com/zh/guide/snapshot-runtime-deep-dive.html) |
| cube-bench | CubeSandbox 仓库中的 Go CLI 压测工具，用于并发驱动 CubeAPI 创建或删除 Sandbox，输出 avg、P50、P95、P99、吞吐等指标。 | [examples/cube-bench](https://github.com/TencentCloud/CubeSandbox/tree/master/examples/cube-bench)、[性能基准报告](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html) |
| Snapshot benchmark scripts | CubeSandbox 仓库中的 Python 基准脚本集合，用于测试 Snapshot、Dirty Page、从 Snapshot 创建、Rollback、Clone、Pause/Resume。 | [examples/snapshot-rollback-clone](https://github.com/TencentCloud/CubeSandbox/tree/master/examples/snapshot-rollback-clone) |

## 环境要求

启用本特性之前，请确认软硬件环境满足要求。

**硬件要求**

| 项目 | 说明 |
|---|---|
| 处理器 | ARM64 服务器处理器 |
| 虚拟化支持 | 宿主机已启用 KVM |
| 磁盘空间 | 预留足够空间保存内核源码、中间编译文件和 RPM 包 |

**软件要求**

| 项目 | 版本或说明 |
|---|---|
| OS | openEuler 或兼容 openEuler kernel RPM 构建流程的系统 |
| 内核源码 | 与目标宿主机内核版本匹配的 openEuler kernel 源码 |
| 构建工具 | `gcc`、`make`、`rpm-build`、`bc`、`bison`、`flex`、`elfutils-libelf-devel` 等 |
| 验证工具 | [`cube-bench`](https://github.com/TencentCloud/CubeSandbox/tree/master/examples/cube-bench)、`perf`、[CubeSandbox API](https://cubesandbox.com/zh/guide/quickstart.html) 或等价高并发 VM 创建测试工具 |

安装常用构建依赖：

```bash
sudo dnf install -y \
  git gcc gcc-c++ make bc bison flex \
  openssl-devel elfutils-libelf-devel ncurses-devel \
  dwarves rpm-build rsync perl tar xz
```

## 获取并合入 KVM irqbypass XArray 优化补丁

### 获取补丁

1. 从公开邮件列表或内部补丁归档下载补丁。

   ```bash
   mkdir -p ~/kernel-patches
   curl -L "<patch-series-mbox-url>" \
     -o ~/kernel-patches/kvm-irqbypass-xarray.mbox
   ```

2. 确认补丁主题和改动范围。

   ```bash
   grep -E '^Subject:' ~/kernel-patches/kvm-irqbypass-xarray.mbox
   git apply --stat ~/kernel-patches/kvm-irqbypass-xarray.mbox || true
   ```

3. 确认补丁至少覆盖以下文件。

   ```text
   include/linux/irqbypass.h
   virt/lib/irqbypass.c
   ```

### 获取目标内核源码

1. 克隆 openEuler kernel 源码，并切换到与目标宿主机匹配的分支或 tag。

   ```bash
   git clone <openeuler-kernel-source-url> kernel
   cd kernel
   git checkout <base-kernel-branch-or-tag>
   ```

2. 确认当前源码基线。

   ```bash
   git branch --show-current
   git describe --tags --always
   uname -r
   ```

3. 如果需要复用当前运行内核配置，可以复制当前内核 config。

   ```bash
   cp /boot/config-$(uname -r) .config
   make olddefconfig
   ```

### 合入补丁

1. 合入补丁前，确认源码目录干净。

   ```bash
   git status --short
   ```

   若命令没有输出，表示当前工作区没有未提交修改。

2. 新建工作分支。

   ```bash
   git checkout -b kvm-irqbypass-xarray
   ```

3. 使用 mbox 合入补丁。

   ```bash
   git am --3way ~/kernel-patches/kvm-irqbypass-xarray.mbox
   ```

   如果补丁是普通 diff 文件，使用以下命令。

   ```bash
   git apply --check ~/kernel-patches/kvm-irqbypass-xarray.patch
   git apply ~/kernel-patches/kvm-irqbypass-xarray.patch
   git add include/linux/irqbypass.h virt/lib/irqbypass.c
   git commit -m "KVM: irqbypass: use XArray for producer and consumer lookup"
   ```

4. 如果出现冲突，先查看当前补丁。

   ```bash
   git am --show-current-patch=diff
   ```

   解决冲突后继续。

   ```bash
   git status
   git add <resolved-files>
   git am --continue
   ```

   放弃本轮合入。

   ```bash
   git am --abort
   ```

5. 合入后确认关键文件已变化。

   ```bash
   git diff --stat <base-kernel-branch-or-tag>..HEAD -- \
     include/linux/irqbypass.h virt/lib/irqbypass.c
   ```

## 编译并安装内核

### 编译前准备

开始编译前，请确认系统已安装 openEuler 内核 RPM 构建依赖，且构建目录有足够空间保存
源码、中间文件和 RPM 包。

```bash
git status --short
df -h .
```

如果构建环境没有发行版签名密钥，可能需要清空本地证书配置。

```bash
./scripts/config --set-str SYSTEM_TRUSTED_KEYS ""
./scripts/config --set-str SYSTEM_REVOCATION_KEYS ""
make olddefconfig
```

是否需要这样做取决于源码配置和构建环境。生产环境如果启用了 Secure Boot 或内核模块签名，
请按组织内核签名流程处理。

### 编译 config 文件

如果使用 openEuler 默认配置：

```bash
make openeuler_defconfig
```

如果使用当前宿主机配置：

```bash
cp /boot/config-$(uname -r) .config
make olddefconfig
```

### 设置内核版本后缀

为了能在 `uname -r` 和 GRUB 中清楚区分补丁内核，建议设置唯一 localversion 后缀。

```bash
./scripts/config --set-str LOCALVERSION "-irqbypass-xarray"
make olddefconfig
make kernelrelease
```

期望输出中包含自定义后缀，例如：

```text
<base-kernel-release>-irqbypass-xarray
```

### 编译 RPM

在内核源码根目录执行。构建时间与服务器配置、内核配置和并发数有关。

```bash
make binrpm-pkg -j"$(nproc)"
```

构建完成后，RPM 包通常生成在 `~/rpmbuild/RPMS/$(uname -m)/`。

```bash
ls -lh ~/rpmbuild/RPMS/$(uname -m)/kernel-*.rpm
```

如果需要同时生成源码包，可以使用：

```bash
make rpm-pkg -j"$(nproc)"
```

### 安装 RPM

1. 安装前确认当前内核和已安装内核列表。

   ```bash
   uname -r
   rpm -qa | grep '^kernel' | sort
   ```

2. 安装本次构建的内核 RPM。

   ```bash
   sudo dnf install -y ~/rpmbuild/RPMS/$(uname -m)/kernel-*.rpm
   ```

   如果包管理器提示同版本冲突，通常说明 localversion 或 RPM release 没有区分开。
   优先重新设置唯一后缀并重新构建。

3. 确认 GRUB 已发现新内核。

   ```bash
   sudo grubby --info=ALL | grep -E '^(index|kernel|title)='
   ```

4. 设置默认启动项。

   ```bash
   sudo grubby --set-default /boot/vmlinuz-<patched-kernel-release>
   ```

5. 重启系统使新内核生效。

   ```bash
   sudo reboot
   ```

6. 系统重启后，确认当前运行内核已切换到新版本。

   ```bash
   uname -r
   ```

## 使用 KVM irqbypass XArray 优化特性

本特性在内核层面自动生效。安装包含该补丁的内核并重启后，KVM irqbypass 注册路径会
使用 XArray 查找逻辑，无需修改 [CubeSandbox](https://github.com/TencentCloud/CubeSandbox)、
QEMU、VMM 或 Guest 镜像。

### 验证特性是否生效

1. 确认当前内核版本已更新。

   ```bash
   uname -r
   ```

2. 确认 KVM 和 [CubeSandbox 服务](https://cubesandbox.com/zh/guide/service-management.html)状态正常。

   ```bash
   lsmod | grep kvm
   systemctl --failed --no-pager
   ```

3. 运行高并发启动测试。建议使用与补丁前相同的
   [Template](https://cubesandbox.com/zh/guide/templates.html)、并发度和请求数。
   下面示例中的 `cube-bench` 是 CubeSandbox 仓库提供的 Go CLI 压测工具，用于并发调用
   CubeAPI 创建或删除 Sandbox。

   ```bash
   cube-bench \
     --api-url http://127.0.0.1:3000 \
     --api-key <api-key> \
     --template <template-id> \
     --concurrency 50 \
     --total 500 \
     --warmup 3 \
     --mode create-only \
     --no-tui \
     --output <result.json>
   ```

4. 对比 create avg、p95、p99、throughput 和 success rate。

5. 使用 `perf lock` 观察锁竞争是否下降。

   ```bash
   sudo perf lock record -a -- <benchmark-command>
   sudo perf lock contention --caller | grep -E 'irq_bypass|kvm' || true
   ```

   补丁生效后，`irq_bypass_register_consumer()` 的 mutex 等待应明显下降，或不再是主要热点。

### 在 CubeSandbox ARM64 场景中的作用

[CubeSandbox ARM64](https://github.com/TencentCloud/CubeSandbox) 适配中，高并发启动和
[Snapshot restore](https://cubesandbox.com/zh/guide/snapshot-rollback-clone.html) 会集中经过
[VMM restore](https://cubesandbox.com/zh/guide/snapshot-runtime-deep-dive.html) 路径。
VGIC legacy irqfd route 恢复、Virtio PCI MSI-X restore、eventfd/irqfd 注册都可能进入
KVM irqbypass manager。

该补丁的直接作用是缩短 irqbypass 注册路径中的全局查找和 mutex 持有时间。对
[CubeSandbox](https://cubesandbox.com/zh/guide/introduction.html) 而言，它主要改善以下场景：

| 场景 | 预期作用 |
|---|---|
| Template 高并发创建 Sandbox | 降低多 VM 并发 restore 时的 KVM irqfd 注册锁等待。 |
| 从 Snapshot 创建 Sandbox | 降低并发恢复 VGIC 和 Virtio MSI-X 时的尾延迟。 |
| Clone / Rollback / Resume | 当操作触发大量 irqfd 注册或恢复时，减少控制路径被 KVM 锁竞争放大的概率。 |
| ARM64 高核心数宿主机 | 并发越高，链表遍历和全局 mutex 越容易放大；XArray 查找收益更明显。 |

该补丁不改变 [CubeSandbox API](https://cubesandbox.com/zh/guide/authentication.html)、
模板格式、Guest 文件系统或容器镜像，也不直接优化单个 Sandbox 的固定启动成本。如果单并发
已经是主要瓶颈，应继续分析 VMM restore 分段、VGIC、Virtio 设备恢复、网络 TAP 或调度资源
过滤等路径。

## 回退方法

安装补丁内核前，应保留至少一个已知可启动的旧内核。

查看启动项：

```bash
sudo grubby --info=ALL | grep -E '^(index|kernel|title)='
```

切回旧内核：

```bash
sudo grubby --set-default /boot/vmlinuz-<old-kernel-release>
sudo reboot
```

确认回退成功：

```bash
uname -r
```

确认业务稳定后，可以按需删除补丁内核包：

```bash
sudo dnf remove 'kernel*<patched-kernel-release>*'
```

删除前请确认当前没有运行在该内核上。

## 注意事项

- 本特性仅影响 KVM 宿主机侧 irqbypass 注册路径，不改变 Guest 可见行为。
- 补丁主要改善高并发场景。低并发或单 VM 固定开销不一定有明显收益。
- 合入补丁前应确认目标内核基线是否已有等价修复，避免重复合入。
- 合入 v1 单补丁时，应检查 producer unregister 相关修复是否已存在；否则优先评估 v2 patch series。
- 构建出的内核应设置唯一 localversion，便于 `uname -r`、GRUB 和 RPM 包区分。
- 生产环境启用前，应先在测试节点完成功能、性能和回退验证。
- 若启用了 Secure Boot 或内核模块签名，应按组织签名流程处理，不建议直接清空签名配置。
- 记录变更时不要包含 SSH 密钥、私有仓库地址、访问令牌或机器登录信息。

## 常见问题

### 补丁无法直接合入

先确认源码基线是否过旧或过新。可以尝试 `git am --3way`，或手工将 XArray 改动移植到
`include/linux/irqbypass.h` 和 `virt/lib/irqbypass.c`。

移植后重点检查注册失败路径是否会正确 `xa_erase()`，避免对象插入后连接失败造成脏状态。

### RPM 安装后 `uname -r` 没有后缀

通常是没有设置 `CONFIG_LOCALVERSION`，或者安装的不是新构建出的 RPM。

```bash
make kernelrelease
rpm -qp --queryformat '%{NAME} %{VERSION}-%{RELEASE}\n' <rpm>
```

### 性能没有改善

先确认当前瓶颈是否仍是 `irq_bypass_register_consumer()`。如果 `perf lock` 中热点已经转移，
需要继续分析 [VMM restore](https://cubesandbox.com/zh/guide/snapshot-runtime-deep-dive.html)、
VGIC、Virtio PCI MSI-X、网络 TAP 或调度资源过滤等路径。
