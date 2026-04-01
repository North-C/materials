# Cloud Hypervisor Snapshot/Restore 与 Kata VM Templating 现状分析报告

日期：2026-03-27

## 1. 报告目标

本文单独分析以下问题：

1. `cloud-hypervisor` 本身是否支持 `snapshot / restore`
2. 为什么这项能力在当前 `Kata Containers` 仓库中没有真正打通
3. 社区中与 `VM Templating` 相关的已合并与未合并提交分别做了什么
4. 这些线索对后续 `Kata + Cloud Hypervisor` 启动时延优化意味着什么

本文只聚焦：

- `Cloud Hypervisor` 的 VM 状态保存/恢复能力
- `Kata` 运行时对该能力的接入状态
- 社区中与 `VM Templating` 直接相关的 PR/提交

不展开镜像侧优化（`Nydus / SOCI / eStargz`），因为那部分已在其他报告中单独分析。

## 2. 结论摘要

结论可以先压缩成四点：

1. `Cloud Hypervisor` 官方确实支持 `snapshot / restore`，这是 VMM 层真实存在的能力，而不是概念。
2. 但在当前 `Kata` 主线仓库中，无论 Go runtime 还是 runtime-rs，`CH` 路径上的 `pause / save / resume` 都没有形成真正可用的快照恢复闭环。
3. 社区里已经有一条 `VM Templating` 功能线被合入，但当前落地的是 **QEMU-only** 路径，而不是 `Cloud Hypervisor`。
4. 社区曾有一个专门给 `Cloud Hypervisor` 增加 VM Templating 的 PR `#4030`，但它最终关闭未合并。该 PR 的讨论很好地暴露了 `CH templating` 真正的工程难点：测试缺失、实现与 CH 内部文件格式耦合、以及与 `virtio-fs/file-backed memory` 的兼容性冲突。

## 3. Cloud Hypervisor 官方能力：支持 Snapshot/Restore

从 `Cloud Hypervisor` 官方文档和 API 来看，`snapshot / restore` 是明确支持的：

- 提供 `vm.pause`
- 提供 `vm.snapshot`
- 提供 `vm.restore`
- 还提供 `send-migration / receive-migration`

这说明从 **VMM 语义** 上说，`CH` 具备把“已初始化 VM”保存下来并重新恢复的基础条件。

官方资料：

- Cloud Hypervisor API：<https://github.com/cloud-hypervisor/cloud-hypervisor/blob/main/docs/api.md>
- Cloud Hypervisor live migration：<https://github.com/cloud-hypervisor/cloud-hypervisor/blob/main/docs/live_migration.md>
- Snapshot/Restore 文档：<https://intelkevinputnam.github.io/cloud-hypervisor-docs-HTML/docs/snapshot_restore.html>

但这只能证明：

- `CH` 本身能做快照/恢复

不能自动推出：

- `Kata` 已经能在 `CH` 后端上用这套能力做 `templating / vm cache / fast restore`

这是两个不同层次的问题。

## 4. Kata 当前为什么没有打通

### 4.1 Go runtime 路径：CH 的 Pause/Save/Resume 仍是空实现

在当前仓库的 Go runtime 中，`cloudHypervisor` 的这三个接口只是记录日志然后返回 `nil`：

- `PauseVM()`
- `SaveVM()`
- `ResumeVM()`

代码位置：

- [src/runtime/virtcontainers/clh.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/clh.go)

这一点意味着：

- 工厂层、缓存层、模板层即使有统一接口
- `CH` 后端也没有真的把 VM 暂停、保存、恢复起来

所以在 Go runtime 语义上，`CH` 目前并不具备可用的 VM template / VM cache 闭环。

### 4.2 runtime-rs 路径：CH 的 pause/save/resume 同样没有真正实现

runtime-rs 的抽象层面提供了：

- `pause_vm`
- `save_vm`
- `resume_vm`

见：

- [src/runtime-rs/crates/hypervisor/src/lib.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/hypervisor/src/lib.rs)

但落到 `CH` 的具体实现时，当前仍然只是返回 `Ok(())`：

- [src/runtime-rs/crates/hypervisor/src/ch/inner_hypervisor.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/hypervisor/src/ch/inner_hypervisor.rs)

这说明 runtime-rs 虽然在 trait 设计上已经把 `save/restore` 留出来了，但 `CH` 这条后端并没有真正接通到 Cloud Hypervisor 的快照 API。

### 4.3 runtime-rs 已有模板框架，但当前只支持 QEMU

runtime-rs 最近已经合入了一条完整的 `VM template` 功能线，包括：

- `factory init / status / destroy`
- 模板 VM 创建
- 模板文件保存
- 从模板启动 VM

相关提交在本地仓库中可见：

- `runtime-rs: introduce VM template lifecycle and integration`
- `runtime-rs: boot vm from template`
- `kata-ctl: add factory subcommands for VM template management`
- `docs: add guide on VM templating usage in runtime-rs`

但同时也有一个非常关键的提交：

- `runtime-rs: Only QEMU supports templating`

本地提交记录可见：

- [git log 输出中的相关提交](/home/test/lyq/Micro-VM/kata-containers/.git)

更直接的证据来自代码：

- `TemplateVm::new_hypervisor()` 当前只接受 `QEMU`
- 非 QEMU 直接报 `Unsupported hypervisor`

代码位置：

- [src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs)

这意味着：

- 当前主线 Kata 已经把模板化能力落地了
- 但落地对象是 `QEMU`
- `Cloud Hypervisor` 没有进入这条模板化闭环

## 5. 社区中与 VM Templating 相关的两条线

### 5.1 已合并：runtime-rs 的 QEMU VM Templating

GitHub PR 搜索可以看到：

- `runtime-rs: introduce VM template lifecycle and integration`，PR `#11828`，已于 `2025-10-29` 合并  
  来源：<https://github.com/kata-containers/kata-containers/pulls?q=is%3Apr+%22vm+templating%22>

这条线最终形成了现在仓库里的能力：

- `factory`
- `template`
- `vm`
- `kata-ctl factory init/status/destroy`

配套文档：

- `What Is VM Templating and How To Enable It`
- `How to Use Template in runtime-rs`

但这条线的落点很明确：

- 是 `QEMU` 模板化
- 不是 `Cloud Hypervisor` 模板化

### 5.2 未合并：Cloud Hypervisor VM Templating PR #4030

社区曾出现一个明确面向 `CH` 的 PR：

- `runtime:Add VM templating support for kata with Cloud Hypervisor`
- PR `#4030`
- 状态：`Closed`

来源：

- GitHub PR 搜索结果显示该 PR 为 closed：  
  <https://github.com/kata-containers/kata-containers/pulls?q=is%3Apr+templating+cloud+hypervisor>
- PR 页面：  
  <https://github.com/kata-containers/kata-containers/pull/4030>

这个 PR 的价值很大，因为它不是泛泛地“讨论支持 CH”，而是明确尝试过把 `VM Templating` 接到 `Cloud Hypervisor` 上。

PR 页面中能确认的关键信息包括：

- 目标分支名：`vm_templating_support_for_clh`
- 作者说明：`The VM templating only supports QEMU, Cloud Hypervisor should be supported too.`
- 该 PR 最终没有合并

PR 讨论里暴露的关键问题：

1. **缺少测试闭环**
   - 维护者直接追问是否做过测试，并指出当时并没有现成的 VM templating tests，既不针对 QEMU，也不针对 CH。

2. **实现对 CH 内部文件格式耦合**
   - review 中明确质疑：为什么 Kata 要依赖 CH 内部实现细节，例如 `state.json`、`config.json` 这些 snapshot/restore 文件名。
   - 这是一个很典型的信号：PR 可能没有通过稳定抽象层接能力，而是对 CH 的内部文件结构做了假设。

3. **与 virtio-fs / file-backed memory 的冲突**
   - 讨论中明确写到：当前实现下，VM templating 不能与 `file based memory` 或 `virtiofs` 一起工作。
   - 原因是：
     - 模板 VM 创建时要求 `file-backed memory` 且 `shared=on`
     - 后续实例又需要 `shared=off`
     - 但 `virtio-fs` 又依赖 `shared=on`
   - 这和 Kata 文档中对模板与 `virtio-fs` 不兼容的表述是一致的，只是这个 PR 把冲突在 `CH` 上更直白地暴露了出来。

4. **PR 范围不够聚焦**
   - review 里还要求把 `ResizeMemory()` 相关改动拆出去，说明这个 PR 混入了与 templating 不完全同一主题的修改，增加了评审难度。

综合来看，`#4030` 并不是一个“没人做过”的方向，而是：

- 社区已经有人尝试过
- 实现遇到抽象边界、测试、兼容性三方面阻力
- 最终没有进入主线

## 6. 为什么 QEMU Templating 合入了，而 CH Templating 没有

结合主线现状和 PR 线索，可以把原因归纳成四类。

### 6.1 QEMU 在 Kata 里是模板化的成熟路径

当前 Kata 的模板化设计本来就是围绕 QEMU 逐步形成的：

- `pause/resume/save` 语义成熟
- 模板文件组织方式稳定
- 工厂语义清晰
- 文档、CLI、配置都先围绕 QEMU 演进

而 `CH` 虽然官方支持 snapshot/restore，但 Kata 并没有完成与之对应的抽象适配。

### 6.2 CH 的快照能力不等于 Kata 的模板能力

要把 `CH` 快照能力变成 Kata 可用的模板能力，至少要解决：

- runtime 如何发起 pause/save/restore
- agent 连接如何在 restore 后恢复
- 网络设备、块设备、共享目录如何在恢复点前后保持一致
- 模板文件路径和元数据如何抽象，而不是耦合到 CH 内部文件名

这比“VMM 有 API”复杂得多。

### 6.3 virtio-fs / shared memory 冲突在 CH 路径上更敏感

Kata 在 `Cloud Hypervisor` 上大量依赖 `virtio-fs` 路径。

而模板化往往要求：

- 共享只读内存页
- 特定的 file-backed/shared memory 语义

这就与 `virtio-fs` 的内存共享要求发生冲突。PR `#4030` 的讨论已经明确暴露了这点。

### 6.4 主线最终选择了更保守的路线：先把 runtime-rs 模板做成 QEMU-only

从本地提交历史看，社区最终采取的是：

- 先把 `runtime-rs` 模板能力完整做出来
- 但明确限制为 `QEMU-only`

这是一种典型的工程取舍：

- 先合入有闭环、有测试、可维护的部分
- 暂不把 `CH` 这种实现边界还不稳定的分支一起纳入

## 7. 对后续工作的意义

### 7.1 你的判断方向是对的

如果当前 `CH + Nydus` 已经把镜像侧压下去了，而启动时延仍停在 `~800ms`，那后续最有价值的方向确实应该是：

- `VM 快照/恢复`
- `warm sandbox pool`
- host 侧资源池化

### 7.2 但要把“CH 官方支持快照”和“Kata 已可用”严格区分

当前最准确的表述应该是：

- `Cloud Hypervisor` 官方原生支持快照/恢复
- `Kata 主线` 当前没有把这条能力在 `CH` 后端上打通
- 社区已经有过 `CH templating` 尝试，但未合并

### 7.3 继续推进的现实路线

如果目标是短期验证收益，优先级建议如下：

1. `warm sandbox pool`
2. host 侧 `network / disk / TAP pool`
3. 对照实验：`QEMU + template`

如果目标是长期补齐 `CH` 能力，研究重点应放在：

1. 为 `CH` 在 Kata 中补真实 `pause/save/restore`
2. 设计不依赖 CH 内部文件名的 snapshot 抽象
3. 明确 `virtio-fs`、file-backed memory、templating 之间的兼容边界
4. 补上模板化集成测试

## 8. 最终判断

从今天的代码和社区轨迹看，最准确的判断不是：

- “CH 不支持 snapshot/restore”

而是：

- “CH 支持 snapshot/restore，但 Kata 还没有把这条能力工程化成可用的 templating/restore 路径”

同样，最准确的社区判断也不是：

- “社区没人做过 CH templating”

而是：

- “社区确实做过 `CH VM Templating` 尝试，代表性 PR 是 `#4030`，但它最终没有被合并；主线后来只把 `QEMU-only` 的 runtime-rs 模板能力合入了。”

## 9. 参考资料

### Cloud Hypervisor

- Cloud Hypervisor API: <https://github.com/cloud-hypervisor/cloud-hypervisor/blob/main/docs/api.md>
- Cloud Hypervisor live migration: <https://github.com/cloud-hypervisor/cloud-hypervisor/blob/main/docs/live_migration.md>
- CH snapshot/restore docs: <https://intelkevinputnam.github.io/cloud-hypervisor-docs-HTML/docs/snapshot_restore.html>

### Kata 本地代码

- [src/runtime/virtcontainers/clh.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/clh.go)
- [src/runtime-rs/crates/hypervisor/src/ch/inner_hypervisor.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/hypervisor/src/ch/inner_hypervisor.rs)
- [src/runtime-rs/crates/hypervisor/src/lib.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/hypervisor/src/lib.rs)
- [src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs)
- [src/runtime-rs/crates/runtimes/virt_container/src/factory/template.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/factory/template.rs)
- [src/runtime-rs/crates/runtimes/virt_container/src/lib.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/lib.rs)

### Kata 文档

- <https://github.com/kata-containers/kata-containers/blob/main/docs/how-to/what-is-vm-templating-and-how-do-I-use-it.md>
- <https://github.com/kata-containers/kata-containers/blob/main/docs/how-to/how-to-use-template-in-runtime-rs.md>
- <https://github.com/kata-containers/kata-containers/blob/main/docs/how-to/what-is-vm-cache-and-how-do-I-use-it.md>

### 社区 PR / 线索

- QEMU/runtime-rs 模板 PR 搜索结果：<https://github.com/kata-containers/kata-containers/pulls?q=is%3Apr+%22vm+templating%22>
- runtime-rs: introduce VM template lifecycle and integration (`#11828`, merged)
- Cloud Hypervisor templating PR 搜索结果：<https://github.com/kata-containers/kata-containers/pulls?q=is%3Apr+templating+cloud+hypervisor>
- `runtime:Add VM templating support for kata with Cloud Hypervisor` (`#4030`, closed): <https://github.com/kata-containers/kata-containers/pull/4030>
