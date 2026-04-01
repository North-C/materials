# GHSA-wwj6-vghv-5p64 漏洞通告中文整理

- 原始链接: https://github.com/kata-containers/kata-containers/security/advisories/GHSA-wwj6-vghv-5p64
- 标题: Kata Container 到 Guest micro VM 的权限提升
- 发布日期: 2026-02-19
- 严重级别: Critical
- CVE: CVE-2026-24834
- 受影响组件: `containerd-shim-kata-v2 (kata-containers)`
- 受影响版本: `<= 3.26.0`
- 修复版本: `3.27.0`
- 影响: 容器可逃逸到 Guest micro VM，但不会进一步逃逸到宿主机；对被覆盖镜像的修改也不会持久化
- CVSS v3.1: `9.4` (`CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H`)

## 摘要

在 Kata 与 Cloud Hypervisor 的组合中，存在一个问题：容器内用户可以修改 Guest micro VM 使用的文件系统，最终在该 VM 中以 root 权限执行任意代码。

根据通告当前的判断，这个问题不会影响宿主机，也不会影响同一宿主机上的其他容器或虚拟机。

通告同时补充说明：`arm64` 上的 QEMU 缺少 NVDIMM 只读支持。作者认为，在上游 QEMU 获得该能力之前，Guest 的写入理论上可能到达镜像文件，但这一点尚未验证。

## 细节

### 1. Linux `virtio-pmem`

`virtio-pmem` 的 probe 路径总是把该区域注册为支持异步 flush 的通用 pagemap，但不会把它标记为只读。创建 region 之前只设置了 `ND_REGION_PAGEMAP` 和 `ND_REGION_ASYNC` 标志，因此 `nd_region->ro` 始终未被置位，最终导致对应块设备保持可写。

后续 `pmem_attach_disk()` 会把该 region 以完整的读写语义接入 block layer。块设备写操作最终会调用 `pmem_do_write()`，后者会直接对宿主机提供的共享内存窗口执行带 cache flush 的 `memcpy` 写入。理论上 `nvdimm_check_and_set_ro()` 可以在 region 被标记为只读时把磁盘设置为只读，但由于 `virtio-pmem` 从未设置该标志，这个辅助逻辑实际上没有生效。

### 2. Cloud Hypervisor `virtio_pmem`

`discard_writes=on` 会让 `virtio-pmem` 背后的文件以只读方式打开，并使用 `MAP_PRIVATE` 而不是 `MAP_SHARED` 建立映射。这意味着 Guest 可以修改映射页的私有副本，但这些修改不会回写到底层文件。

Guest 和 Cloud Hypervisor 进程仍然会读取到这些修改后的数据，因为它们存在于私有映射副本中，因此“写入后再读取”看起来是成功的，但这些变化并不会持久化。

一旦映射被释放，或者 VM 被重启，这些基于 copy-on-write 的修改就会消失，而底层 backing file 保持不变。

### 3. Kata 的 `/dev/pmem0`

Kata 在启动每个 Pod/VM 时，会把宿主机上的只读 Guest 镜像通过 DAX 映射进 VM，并通知 Guest 内核将得到的 `/dev/pmem*` 设备挂载为根文件系统。

由于 DAX 会把 backing file 直接映射到 Guest 内存，hypervisor 无法拦截或拒绝单次写操作。因此，只要容器具备足够权限，就可以打开 `/dev/pmem0` 并观察到自己的写入结果，直到 VM 重启或缓存被丢弃为止。

## PoC 说明

把上述行为串起来后，意味着容器中的用户即使不是特权容器，也不需要 `CAP_SYS_ADMIN`，只要拥有 `CAP_MKNOD`，就可以修改 Guest OS 的文件系统，例如替换库文件或二进制文件，从而在容器之外、Guest 内部实现任意代码执行。

攻击者需要计算目标文件在设备中的偏移量，这通常依赖以下信息：

- 分区起始扇区
- 扇区大小（字节）
- 文件系统块大小
- 文件的物理块索引

通告中的 PoC 通过把 `/usr/bin/systemd-tmpfiles` 替换为一个回连到 `localhost` 的 shell，最终在 Guest 中拿到 root shell。定时器会在启动约 15 分钟后触发执行。

PoC 还提到，可以使用 `debugfs` 直接操作 `/dev/pmem0p1` 上的文件系统，从而在不需要挂载权限的情况下获取要修改文件的绝对偏移。

如果只想验证更简单的现象，也可以直接使用 `dd` 向 `/dev/pmem0` 写入数据，然后再读取，会发现数据在被丢弃前是可读的。

## 影响评估

该漏洞的直接影响是：

- 从容器逃逸到 Guest micro VM
- 不会直接逃逸到宿主机
- 对 Guest 镜像的覆盖修改不会持久化到底层镜像文件

## 致谢

- 报告者: `kostya-oai`
- 修复开发: `sprt`
- 修复审阅: `fidencio`
- 修复审阅: `stevenhorsman`

