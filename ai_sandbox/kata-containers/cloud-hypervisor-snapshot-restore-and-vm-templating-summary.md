# Cloud Hypervisor Snapshot/Restore 与 Kata VM Templating 汇报摘要

日期：2026-03-27

## 1. 核心结论

1. `Cloud Hypervisor` 官方原生支持 `snapshot / restore`，这是 VMM 层真实存在的能力。
2. 但在当前 `Kata` 主线仓库中，这条能力没有在 `cloud-hypervisor` 后端上真正打通。
3. 社区已经合入了 `VM Templating` 能力，但当前主线只支持 `QEMU`，不支持 `Cloud Hypervisor`。
4. 社区曾尝试为 `Cloud Hypervisor` 增加 `VM Templating`，代表性 PR 是 `#4030`，但最终未合并。

## 2. 为什么说 CH 本身支持 Snapshot/Restore

`Cloud Hypervisor` 官方文档和 API 明确提供：

- `vm.pause`
- `vm.snapshot`
- `vm.restore`
- `send-migration / receive-migration`

这说明从 VMM 角度看，`CH` 具备把“已初始化 VM”保存并恢复的基础能力。

参考：

- <https://github.com/cloud-hypervisor/cloud-hypervisor/blob/main/docs/api.md>
- <https://github.com/cloud-hypervisor/cloud-hypervisor/blob/main/docs/live_migration.md>
- <https://intelkevinputnam.github.io/cloud-hypervisor-docs-HTML/docs/snapshot_restore.html>

## 3. 为什么说 Kata 没有打通

### Go runtime

在 Go runtime 中，`cloudHypervisor` 的：

- `PauseVM()`
- `SaveVM()`
- `ResumeVM()`

当前只是记录日志后返回 `nil`，没有真正调用 CH 的快照/恢复路径。

代码位置：

- [src/runtime/virtcontainers/clh.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/clh.go)

### runtime-rs

在 runtime-rs 中，trait 层已经定义了：

- `pause_vm`
- `save_vm`
- `resume_vm`

但 `CH` 的具体实现仍然只是直接返回 `Ok(())`，没有真正接通到底层快照 API。

代码位置：

- [src/runtime-rs/crates/hypervisor/src/lib.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/hypervisor/src/lib.rs)
- [src/runtime-rs/crates/hypervisor/src/ch/inner_hypervisor.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/hypervisor/src/ch/inner_hypervisor.rs)

因此，当前更准确的说法是：

- `CH` 支持快照/恢复
- `Kata` 还没有把这条能力工程化成可用的 `templating / restore / vm cache` 路径

## 4. VM Templating 的主线现状

`Kata` 社区后来已经合入一条 `runtime-rs` 的模板能力线，包括：

- 模板生命周期管理
- `factory init / status / destroy`
- 从模板启动 VM

但主线明确收敛成了：

- `Only QEMU supports templating`

也就是说：

- 模板功能已经进入主线
- 当前落地对象是 `QEMU`
- 不是 `Cloud Hypervisor`

关键代码位置：

- [src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs)
- [src/runtime-rs/crates/runtimes/virt_container/src/factory/template.rs](/home/test/lyq/Micro-VM/kata-containers/src/runtime-rs/crates/runtimes/virt_container/src/factory/template.rs)

## 5. 社区里未合并的 CH Templating 尝试

社区曾有一个专门面向 `Cloud Hypervisor` 的 PR：

- `runtime:Add VM templating support for kata with Cloud Hypervisor`
- PR `#4030`
- 状态：`Closed`

参考：

- <https://github.com/kata-containers/kata-containers/pull/4030>

这个 PR 至少说明两点：

1. 社区确实尝试过给 `CH` 增加模板支持。
2. 这条能力最终没有进入主线。

从 PR 讨论看，主要问题集中在：

- 缺少模板化测试闭环
- 实现依赖 CH 内部文件细节，如 `state.json`、`config.json`
- 与 `virtio-fs` / file-backed memory 的兼容性存在冲突

## 6. 对当前研究工作的意义

对 `Kata + cloud-hypervisor + Nydus` 场景，应该把问题分成两层理解：

- 从理论上：`CH snapshot/restore` 是可行方向
- 从主线工程上：当前仓库还不能直接利用这条能力

因此，后续优化路线可以分成两类：

### 短期可验证

- `warm sandbox pool`
- host 侧资源池化
- `QEMU + template` 对照实验

### 长期值得投入

- 在 Kata 中补齐 `CH` 的 `pause / save / restore`
- 设计不依赖 CH 内部文件格式的抽象
- 处理 `virtio-fs` 与模板/快照的兼容边界

## 7. 汇报用一句话结论

可以把这部分工作概括为：

> `Cloud Hypervisor` 本身具备 snapshot/restore 能力，但 `Kata` 当前尚未将该能力在 `CH` 后端上打通；社区已有过 `CH VM Templating` 尝试但未合并，而当前主线真正落地的模板能力仍然是 `QEMU-only`。
