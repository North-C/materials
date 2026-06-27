# CubeSandbox Guest-Visible Restore Checklist Seed

## 1. 目标

把 `CubeSandbox restore/rollback/update 成功但 guest 不可用` 的排查动作，固定为一份可复用 seed。

本目录承接：

- [Cloud Hypervisor 与 CubeSandbox：Restore 后 Guest 不可用验证清单](../../ch-cubesandbox-restore-guest-unavailability-checklist.md)
- [Cloud Hypervisor 与 CubeSandbox：Backend / Notifier / Restore 交叉线](../../ch-cubesandbox-backend-notifier-restore-crossline.md)

## 2. 升级状态

- 当前状态：`seed`
- 目标升级路径：`seed -> real -> validated`

这不是失败回放。

它是一个把 `platform request -> backend rebind -> worker wakeup -> guest-visible state` 问题落成样本目录的种子包。

后续只要拿到真实 restore/update 请求、ready 路径、worker 唤醒证据和 guest agent 可见性日志，就可以直接在这个目录上补齐。

当前更准确的状态是：

它已经是一个 **codepath-derived baseline seed**，不是纯空白占位。

也就是说，它已经吸收了仓库内现成的：

1. `VmRestore` / `VmResumeFromSnapshot` / `VmSetFs` / `VmAddDevice` 请求链
2. `VsockServerReady` / `VmShutdown` / probe 这类 ready 路径
3. `FsEvent` / `back_state` / worker 唤醒 / guest device wait 的关键日志锚点

但还没有真实控制面与 guest 对照日志，所以不能直接升级为 `real`。

## 3. 本 seed 关注的问题

1. `VmRestore` / `VmResumeFromSnapshot` / `VmSetFs` / `VmAddDevice` 是否真的进了 VMM
2. 当前节点 TAP / tap fd / fs backend / server state 是否重新绑定成功
3. worker 是否真的被唤醒
4. guest agent 是否真的完成设备可见、mount、ready 收敛

## 4. 当前已知证据入口

- CubeShim restore / set_fs：
  [CubeSandbox-sandbox-clone/CubeShim/shim/src/hypervisor/cube_hypervisor.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/CubeShim/shim/src/hypervisor/cube_hypervisor.rs:173)
- fs pending message：
  [CubeSandbox-sandbox-clone/hypervisor/vmm/src/device_manager.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/vmm/src/device_manager.rs:1173)
- net worker：
  [CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/net.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/net.rs:694)
- native virtio-fs restore：
  [CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/fs.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/hypervisor/virtio-devices/src/fs.rs:916)
- guest device wait：
  [CubeSandbox-sandbox-clone/agent/src/device.rs](/home/lyq/Projects/Micro-VM/CubeSandbox-sandbox-clone/agent/src/device.rs:267)

## 5. 当前缺口

1. 缺一份控制面成功但 guest 不可用的真实日志
2. 缺一份 worker 被唤醒但 guest-visible state 未收敛的真实证据
3. 缺 restore/rollback 前后 ready 状态对照

## 6. 当前建议的最小回填顺序

1. 先补 restore / resume / set_fs / add_device 请求与返回
2. 再补 `VsockServerReady` / `VmShutdown` / vsock probe 这些 ready 信号
3. 再补 TAP/tap fd、`FsEvent`、`back_state`、worker 唤醒证据
4. 最后补 guest agent 看见设备、mount 成功、ready 收敛的证据

## 7. 进入真实样本前的最低要求

1. 至少一份控制面请求成功记录
2. 至少一份 worker / backend 重绑记录
3. 至少一份 guest agent 可见性 / mount / ready 记录

具体还缺哪些日志，已经单独列为：

- [missing-evidence.txt](./missing-evidence.txt)

如果下一步要直接开始采证，可以先按：

- [evidence-targets.txt](./evidence-targets.txt)

如果要直接按步骤抓一轮最小日志集，可以再看：

- [collection-runbook.md](./collection-runbook.md)

里的顺序抓最小证据集。

如果下一轮已经拿到一包真实日志，建议再按下面两份小文件快速过一遍：

- [minimum-log-bundle.txt](./minimum-log-bundle.txt)
- [decision-table.txt](./decision-table.txt)
- [bundle-template.txt](./bundle-template.txt)

前者用来判断“这包日志够不够资格回填”，后者用来判断“它该留在 seed、归到 success baseline、归到 control-plane failure，还是升级成新的 guest-visible failure real”。

`bundle-template.txt` 则更具体：

- 它直接规定了下一包日志最理想应该包含哪些文件
- 能帮助把同一次尝试的 control-plane、worker/backend、guest-visible 证据放在同一个 bundle 里

## 8. 升级护栏

这份 seed 现在已经不缺“解释框架”，更缺的是正确升级。

在真实日志回填前，先固定三条护栏：

1. 如果只看到控制面失败，例如 `sandbox is not running`，不要升级到这份 `guest-visible failure real`；应继续归到
   `cubesandbox-rollback-sandbox-not-running-real-20260622`
2. 如果只看到成功 restore / rollback / ready，对照的仍然是
   `cubesandbox-guest-visible-restore-baseline-real-20260622`
3. 只有当同一批证据同时覆盖
   - 控制面成功
   - worker/backend 推进
   - guest-visible 收敛失败
   才能把本 seed 升成新的失败类 `real`
