# Collection Runbook

目标：
为
`fc-rootfs-backing-restore-checklist-seed-20260622`
补齐一组可以升级成 `real` 的最小证据集合。

这份 runbook 不新增架构结论。

它只回答：

1. 下一轮应该抓哪些证据
2. 抓取顺序是什么
3. 抓到什么程度才值得升级 `real`

## 1. 最小目标

同一轮证据里，至少同时覆盖：

1. restore 请求成功
2. root expression 与目标 root device 的对应关系
3. backing file / disk path / pmem path 的一致性
4. guest 设备可见性
5. rootfs 最终是否真正可用

如果缺任何一段，都不要升 `real`。

## 2. 推荐采集顺序

### A. Restore input and success

至少保留一组：

- snapshot 请求
- restore 请求
- 返回值或成功标志

建议记录：

```bash
# create snapshot / restore commands
# API request/response or command transcript
```

### B. Root expression

至少保留一组：

- kernel cmdline
- root expression
- root 设备意图

建议 grep：

```bash
rg -n "root=/dev/vda|root=PARTUUID|root=/dev/pmem" <captured-config-or-cmdline>
```

### C. Backing consistency

至少保留一组：

- restore 前 disk/pmem path
- restore 后 disk/pmem path
- backing 对象是否仍然存在且语义一致

建议记录：

```bash
ls -l <disk-or-pmem-path>
stat <disk-or-pmem-path>
```

以及 restore 输入里对路径的引用。

### D. Guest visibility

至少保留一组：

- `/dev/vd*`
  或
- `/dev/pmem*`

建议记录：

```bash
ls /dev/vd* /dev/pmem* 2>/dev/null
lsblk
cat /proc/cmdline
```

### E. Rootfs usability

至少保留一组：

- rootfs 已可用
  或
- rootfs 不可用但设备可见
  或
- 连设备都不可见

建议记录：

```bash
mount
findmnt /
cat /proc/mounts
```

以及 boot 是否真正进入 userspace。

## 3. 最小目录回填顺序

拿到证据后，按下面顺序回填当前 seed：

1. `api.txt`
   写 snapshot / restore 请求、返回值、输入来源
2. `host.txt`
   写 root expression 与 backing consistency
3. `logs.txt`
   写 host/guest 实际日志和命令输出路径
4. `guest.txt`
   写 `/dev/vd*` / `/dev/pmem*` 与 rootfs 可用性
5. `classification.md`
   收敛 `final_bucket` 与 `confidence`

## 4. 升级门槛

满足下面条件后，才把这份 seed 升成 `real`：

1. 同一批证据里能证明 restore 已成功
2. 同一批证据里能证明 root expression 成立
3. 同一批证据里能证明 backing file / device path 一致
4. 同一批证据里能证明 guest 是否看到目标设备
5. 同一批证据里能证明 rootfs 是否真正可用

如果只有：

- restore success + cmdline
  仍然只能算 `seed`

如果只有：

- guest 启动失败，但缺 backing/path 证据
  不能安全分类为 Firecracker rootfs/backing `real`

## 5. 最常见误判

### 误判一

restore 请求成功
=
rootfs 语义已经恢复

这是错误的。

restore 成功只证明 VMM state 恢复流程通过，不证明 backing 对象和 guest rootfs 一定成立。

### 误判二

guest 看到 `/dev/vd*`
=
rootfs 已可用

这也是错误的。

设备可见仍不等于 rootfs 真正可挂载、可启动。

## 6. 与现有资产的关系

这份 seed 的源码型对照材料是：

- [Firecracker 存储 / rootfs / share-fs 边界链路](../../firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md)
- [Firecracker virtio block 数据链路](../../firecracker/analysis/virtio-block-data-path-chain.md)
- [存储、rootfs 与共享文件系统跨项目专题分析](../../storage-rootfs-sharefs-cross-project.md)
