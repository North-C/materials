# CubeSandbox Guest-Visible Restore Baseline Record

本目录不是失败样本。

它是一份 **real baseline record**：

基于仓库内已经存在的 ARM64 one-click E2E 产物，固定一份 `CubeSandbox` 在 snapshot/create-from-snapshot/rollback 场景下 guest-visible state 成功收敛的最小对照面。

关联资产：

- [CubeSandbox guest-visible restore checklist seed](../cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md)
- [CubeSandbox Rollback `sandbox is not running` 样本记录](../cubesandbox-rollback-sandbox-not-running-real-20260622/SUMMARY.md)

## 1. 场景

- 日期：`2026-06-11`
- 节点架构：`aarch64`
- 样本类型：`real baseline`
- 目标：固定一份 `sandbox create -> command/data-plane -> snapshot -> clone -> rollback` 全链成功基线

## 2. 已确认的成功基线

1. one-click install：`PASS`
2. quickcheck：`PASS`
3. template create：`READY`
4. sandbox create：`PASS`
5. guest 内命令返回 `v1` 与 `aarch64`
6. snapshot create/list：`PASS`
7. create from snapshot：`PASS`
8. rollback：`PASS`
9. rollback 后再次读取到 `v1`
10. final health：`PASS`

另外，现有 one-click 安装产物还能证明两件前置条件：

1. `network-agent readyz` 检查成功
2. `cube-api` / `cubemaster` / `network-agent` 等控制面服务在收尾时仍处于 `active running`

## 3. 这份 baseline 解决什么问题

它不是为了证明哪次失败。

它是为了告诉我们：

当 `CubeSandbox` 在 ARM64 上正常工作时，至少应该看到：

1. sandbox 可以成功启动
2. guest 命令可执行
3. snapshot / clone / rollback 可以闭环
4. rollback 后 guest-visible state 可以回到预期值

## 4. 当前局限

这份 baseline 仍然不是底层全量日志包。

它缺：

1. `CubeShim` 的 `vm ready, vsock is listening` 原始日志
2. `network-agent` / `CubeVS` 的结构化原始日志
3. guest agent `add_storages()` / mount / PCI wait 的原始日志

因此它属于：

- `real`：因为引用了仓库内现成 E2E 真实结果
- 但不是 `validated`：因为还没有完整中间层时序日志
