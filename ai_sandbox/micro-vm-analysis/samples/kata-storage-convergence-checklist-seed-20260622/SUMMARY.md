# Kata Storage Convergence Checklist Seed

## 1. 目标

把 `Kata device 已进入 VM 但 rootfs / volume / guest-visible storage 未收敛` 的排查动作，固定为一份可复用 seed。

本目录承接：

- [Share-fs / Rootfs / Volume 到 Agent 链路](../../kata-containers/analysis/sharefs-rootfs-volume-agent-chain.md)
- [存储、rootfs 与共享文件系统跨项目专题分析](../../storage-rootfs-sharefs-cross-project.md)

## 2. 升级状态

- 当前状态：`seed`
- 目标升级路径：`seed -> real -> validated`

这不是失败回放。

它是一个把 `translation -> CreateContainerRequest.storages -> add_storages() -> mount convergence` 问题落成样本目录的种子包。

当前更准确的状态是：

它已经是一个 **codepath-derived baseline seed**，不是纯空白占位。

也就是说，它已经吸收了仓库内现成的：

1. `handler_rootfs()` / `handler_volumes()` 的分类路径
2. `CreateContainerRequest.storages` 的构造路径
3. guest `add_storages()` / `mount_from()` 的落地路径

但还没有真实 host/guest 对照日志，所以不能直接升级为 `real`。

与前面几个非网络 seed 一样，本目录现在也包含了更可执行的回填入口：

- [evidence-targets.txt](./evidence-targets.txt)
- [collection-runbook.md](./collection-runbook.md)

它们的作用不是新增结论，而是把 `seed -> real` 的最低证据门槛固定下来。

## 3. 本 seed 关注的问题

1. `handler_rootfs()` / `handler_volumes()` 是否真的生成了 agent `Storage`
2. `CreateContainerRequest.storages` 是否真的传到了 guest
3. guest agent `add_storages()` / `mount_from()` 是否真正落地
4. 问题停在 hypervisor device、agent storage，还是 guest mount 收敛

## 4. 当前已知证据入口

- rootfs 分类：
  [kata-containers/src/runtime-rs/crates/resource/src/rootfs/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/resource/src/rootfs/mod.rs:66)
- volume 分类：
  [kata-containers/src/runtime-rs/crates/resource/src/volume/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/resource/src/volume/mod.rs:52)
- CreateContainerRequest：
  [kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/container_manager/container.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/container_manager/container.rs:230)
- guest `add_storages()`：
  [kata-containers/src/agent/src/storage/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/agent/src/storage/mod.rs:253)
- guest `mount_from()`：
  [kata-containers/src/agent/rustjail/src/mount.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/agent/rustjail/src/mount.rs:755)

## 5. 当前缺口

1. 缺真实 CreateContainerRequest.storages 对照
2. 缺 guest agent `add_storages()` / `mount_from()` 的真实日志
3. 缺“device 已进 VM 但 guest rootfs/volume 未可用”的真实观测

## 6. 已有可直接复用的准真实入口

当前仓库已经有几类可以直接拿来回填 seed 的入口：

1. `handler_rootfs()` / `handler_volumes()` 的分类入口已经明确：
   - `ShareFsRootfs`
   - `BlockRootfs`

   证据：
   [kata-containers/src/runtime-rs/crates/resource/src/rootfs/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/resource/src/rootfs/mod.rs:66)
   [kata-containers/src/runtime-rs/crates/resource/src/volume/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/resource/src/volume/mod.rs:52)

2. `CreateContainerRequest.storages` 的构造位置已经明确。

   证据：
   [kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/container_manager/container.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/container_manager/container.rs:260)

3. guest 侧 `add_storages()` 与 `mount_from()` 的落地位置已经明确。

   证据：
   [kata-containers/src/agent/src/storage/mod.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/agent/src/storage/mod.rs:253)
   [kata-containers/src/agent/rustjail/src/mount.rs](/home/lyq/Projects/Micro-VM/kata-containers/src/agent/rustjail/src/mount.rs:755)

4. 当前工作树里还已经存在一批 `CreateContainerRequest` JSON 形态样本，可作为比纯代码路径更强的“request propagation”对照入口。

   它们虽然仍不是 guest 运行日志，但已经包含真实格式的 `storages` 数组、`driver`、`source`、`mount_point` 等字段。

   例如：
   [state/createcontainer/testcases.json](/home/lyq/Projects/Micro-VM/kata-containers/src/tools/genpolicy/tests/policy/testdata/state/createcontainer/testcases.json:257)
   [volumes/emptydir/testcases.json](/home/lyq/Projects/Micro-VM/kata-containers/src/tools/genpolicy/tests/policy/testdata/createcontainer/volumes/emptydir/testcases.json:167)

## 7. 当前建议的最小回填顺序

1. 先补 rootfs / volume 分类与 agent `Storage` 生成证据
2. 再补 `CreateContainerRequest.storages` 到 guest 的传递证据
3. 再补 `add_storages()` / `mount_from()` 的落地证据
4. 最后补 guest rootfs / volume 是否真正可用

如果当前没有新的运行日志，最现实的中间推进是：

1. 先把现有 JSON `CreateContainerRequest` 样本摘入 `host.txt` / `api.txt`
2. 再把它和 `handler_rootfs()` / `handler_volumes()` 的分类路径对齐
3. 但仍不要把这一步误算成 `real`

如果下一轮已经拿到一包真实日志，建议再按下面两份小文件快速过一遍：

- [minimum-log-bundle.txt](./minimum-log-bundle.txt)
- [decision-table.txt](./decision-table.txt)

前者用来判断“这包证据够不够资格回填”，后者用来判断“它仍停在 request propagation、guest storage landing，还是终于够资格升级成 `real`”。

## 9. 当前工作树状态

按当前工作树现状，这份 seed 已经比纯代码路径多走了一步：

1. 已有 `CreateContainerRequest` JSON 样本；
2. 还没有 guest `add_storages()` / `mount_from()` 运行日志；
3. 也还没有最终 rootfs/volume 可用性观测。

因此它当前最准确的位置是：

`stronger request propagation evidence`

而不是：

`real`

## 8. 进入真实样本前的最低要求

1. 至少一份 rootfs / volume translation 记录
2. 至少一份 `CreateContainerRequest.storages` 证据
3. 至少一份 guest agent storage / mount 落地记录
4. 至少一份 guest rootfs / volume 最终可用性观测

具体还缺哪些真实证据，已经单独列为：

- [missing-evidence.txt](./missing-evidence.txt)

## 10. 升级护栏

这份 seed 当前最容易被误判成 `real` 的情况是：

- 只有 `CreateContainerRequest.storages`
- 只有 request-shaped JSON 样本
- 或只有 guest 进入 storage landing，但还没证明最终 rootfs/volume 可用性

这些都还不够。

只有当同一批证据同时覆盖：

1. translation
2. `CreateContainerRequest.storages`
3. guest `add_storages()` / `mount_from()`
4. rootfs/volume 最终可用性

才应该考虑升级。

如果下一轮已经拿到一包真实日志，建议先对照：

- [minimum-log-bundle.txt](./minimum-log-bundle.txt)
- [decision-table.txt](./decision-table.txt)
- [bundle-template.txt](./bundle-template.txt)
