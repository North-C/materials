# Cloud Hypervisor Backend / Notifier / Restore Baseline Record

本目录不是失败样本。

它是一份 **real baseline record**：

基于仓库内已经存在的官方 snapshot/restore 文档与测试夹具事件片段，固定一份“restore 成功”的最小对照面。

关联资产：

- [Cloud Hypervisor backend/notifier/restore checklist seed](../ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md)
- [Cloud Hypervisor 与 CubeSandbox：Restore 后 Guest 不可用验证清单](../../ch-cubesandbox-restore-guest-unavailability-checklist.md)

## 1. 场景

- 日期：`2026-06-22`
- 样本类型：`real baseline`
- 目标：固定一份 restore 成功基线，后续所有失败样本都与它对照

## 2. 已确认的成功基线

1. snapshot/restore 的标准命令路径存在且文档化
2. restore 后默认状态是 `paused`
3. `resume=true` 可自动恢复
4. `event == "restored"` 是可解析的成功信号
5. snapshot 目录的成功基线布局是：
   - `config.json`
   - `memory-ranges`
   - `state.json`

## 3. 这份 baseline 解决什么问题

它不是为了证明某次失败。

它是为了给后续 `transport/backend/controller/guest-visible` 的真实失败样本提供“成功时至少应该长什么样”的对照面。

## 4. 当前局限

这份 baseline 仍然不是完整运行日志包。

它缺：

1. 一次真实主机上的完整 event.json
2. 一次真实 backend/socket/fd 重连观测
3. 一次真实 guest 设备可见性观测

因此它属于：

- `real`：因为引用了仓库里已存在、可复现的文档/测试基线片段
- 但不是 `validated`：因为还没有真实主机/guest 全链路对照
