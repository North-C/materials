# Firecracker Rootfs / Backing / Restore Checklist Seed

## 1. 目标

把 `Firecracker restore 成功但 guest rootfs 或存储语义不成立` 的排查动作，固定为一份可复用 seed。

本目录承接：

- [Firecracker 存储 / rootfs / share-fs 边界链路](../../firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md)
- [存储、rootfs 与共享文件系统跨项目专题分析](../../storage-rootfs-sharefs-cross-project.md)

## 2. 升级状态

- 当前状态：`seed`
- 目标升级路径：`seed -> real -> validated`

这不是失败回放。

它是一个把 `root expression -> backing file -> restore -> guest rootfs visibility` 问题落成样本目录的种子包。

当前更准确的状态是：

它已经是一个 **codepath-derived baseline seed**，不是纯空白占位。

也就是说，它已经吸收了仓库内现成的：

1. root block / pmem 的 cmdline 表达
2. block restore 与 `disk_path` / backing file 语义
3. snapshot 不包含 backing file 字节这一边界

但还没有真实 restore 前后对照日志，所以不能直接升级为 `real`。

与前面几个非网络 seed 一样，本目录现在也包含了更可执行的回填入口：

- [evidence-targets.txt](./evidence-targets.txt)
- [collection-runbook.md](./collection-runbook.md)

它们的作用不是新增结论，而是把 `seed -> real` 的最低证据门槛固定下来。

## 3. 本 seed 关注的问题

1. root block / pmem 设备与 kernel cmdline 是否一致
2. snapshot / restore 后 host backing file 是否仍然语义一致
3. 恢复后的 guest 是否真的重新看到 block / pmem 设备
4. 问题停在 VMM restore 层，还是 guest rootfs 可见性层

## 4. 当前已知证据入口

- root cmdline 写入：
  [firecracker/src/vmm/src/builder.rs](/home/lyq/Projects/Micro-VM/firecracker/src/vmm/src/builder.rs:672)
- pmem root：
  [firecracker/src/vmm/src/builder.rs](/home/lyq/Projects/Micro-VM/firecracker/src/vmm/src/builder.rs:729)
- block restore：
  [firecracker/analysis/virtio-block-data-path-chain.md](/home/lyq/Projects/Micro-VM/firecracker/analysis/virtio-block-data-path-chain.md:162)
- store/rootfs 边界：
  [firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md](/home/lyq/Projects/Micro-VM/firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md:137)

## 5. 当前缺口

1. 缺 restore 前后 block/pmem 设备可见性的真实对照
2. 缺 backing file 实际一致性的真实证据
3. 缺 guest rootfs 最终是否可挂载/可用的真实观测

## 6. 已有可直接复用的准真实入口

当前仓库已经有几类可以直接拿来回填 seed 的入口：

1. `builder.rs` 明确给出 root 表达：
   - `root=/dev/vda`
   - `root=PARTUUID=...`
   - `root=/dev/pmem{i}`

   证据：
   [firecracker/src/vmm/src/builder.rs](/home/lyq/Projects/Micro-VM/firecracker/src/vmm/src/builder.rs:672)

2. `virtio-block-data-path-chain.md` 已经明确了 block restore、backing file 依赖和 `disk_path` 语义。

   证据：
   [firecracker/analysis/virtio-block-data-path-chain.md](/home/lyq/Projects/Micro-VM/firecracker/analysis/virtio-block-data-path-chain.md:162)

3. `snapshot-restore-chain.md` 与 `storage-rootfs-sharefs-boundary-chain.md` 已经明确指出：
   snapshot 保存设备状态和可重建引用，不保存 backing file 字节。

   证据：
   [firecracker/analysis/snapshot-restore-chain.md](/home/lyq/Projects/Micro-VM/firecracker/analysis/snapshot-restore-chain.md:203)
   [firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md](/home/lyq/Projects/Micro-VM/firecracker/analysis/storage-rootfs-sharefs-boundary-chain.md:139)

## 7. 当前建议的最小回填顺序

1. 先补 restore 请求和 snapshot 来源
2. 再补 root block/pmem 与 cmdline 的对应关系
3. 再补 backing file / disk path / pmem path 的一致性证据
4. 最后补 guest 侧设备可见与 rootfs 可用性

如果下一轮已经拿到一包真实日志，建议再按下面两份小文件快速过一遍：

- [minimum-log-bundle.txt](./minimum-log-bundle.txt)
- [decision-table.txt](./decision-table.txt)

前者用来判断“这包证据够不够资格回填”，后者用来判断“它是还停在 backing/device visibility 层，还是终于够资格升级成 `real`”。

## 8. 进入真实样本前的最低要求

1. 至少一份 restore 成功记录
2. 至少一份 backing file / disk path / pmem path 证据
3. 至少一份 guest 侧 rootfs 可见性记录
4. 至少一份 guest rootfs 最终可用性观测

具体还缺哪些真实证据，已经单独列为：

- [missing-evidence.txt](./missing-evidence.txt)

## 9. 当前工作树状态

按当前工作树现状，这份 seed 还停留在：

1. root expression 已有源码锚点
2. backing / restore 边界已有源码锚点
3. 但没有新的真实 restore + guest-visible 证据进入工作树

因此当前最准确的位置仍然是：

`codepath-derived baseline seed`

而不是可直接升级的准真实样本。

## 10. 升级护栏

这份 seed 当前最容易被误判成 `real` 的情况是：

- 只有 root expression 锚点
- 只有 restore 生命周期锚点
- 或只有 guest 设备可见，但还没证明 rootfs 真正可用

这些都还不够。

只有当同一批证据同时覆盖：

1. restore 成功
2. root expression
3. backing consistency
4. guest 设备可见性
5. rootfs 最终可用性

才应该考虑升级。

如果下一轮已经拿到一包真实日志，建议先对照：

- [minimum-log-bundle.txt](./minimum-log-bundle.txt)
- [decision-table.txt](./decision-table.txt)
- [bundle-template.txt](./bundle-template.txt)
