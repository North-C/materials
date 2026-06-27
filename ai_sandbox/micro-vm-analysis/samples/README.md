# 样本资产目录

本目录保存样本资产。

其中大部分仍然是 ARM64 网络样本，但现在也开始承接非网络横线的 checklist seed。

完整分组索引见：[样本目录索引](./INDEX.md)。

当前包含四个 ARM64 网络模板：

1. `kata-arm64-network-backend-diff-template`
2. `ch-arm64-network-hotplug-failure-template`
3. `fc-arm64-network-guest-visibility-template`
4. `cubesandbox-arm64-network-midlogs-template`

另外已经有多份 seed / real 目录：

1. `cubesandbox-arm64-network-tap-fd-unavailable-20260613`
2. `ch-arm64-network-hotplug-seed-20260618`
3. `kata-arm64-network-backend-diff-seed-20260618`
4. `fc-arm64-network-guest-visibility-seed-20260618`
5. `ch-arm64-network-restore-seed-20260618`
6. `fc-arm64-network-restore-seed-20260618`
7. `kata-arm64-network-backend-diff-qemu-seed-20260618`
8. `kata-arm64-network-backend-diff-ch-seed-20260618`
9. `kata-arm64-network-backend-diff-dragonball-seed-20260618`
10. `kata-arm64-network-route-convergence-seed-20260618`
11. `ch-backend-notifier-restore-checklist-seed-20260622`
12. `cubesandbox-guest-visible-restore-checklist-seed-20260622`
13. `fc-rootfs-backing-restore-checklist-seed-20260622`
14. `kata-storage-convergence-checklist-seed-20260622`
15. `ch-backend-notifier-restore-baseline-real-20260622`
16. `cubesandbox-rollback-sandbox-not-running-real-20260622`
17. `cubesandbox-no-more-resource-real-20260613`
18. `cubesandbox-dev-shm-capacity-real-20260613`

使用顺序：

1. 如果做 ARM64 网络样本，先读 [ARM64 网络下一批真实样本目标图](../arm64-network-next-target-map.md)
2. 如果做非网络横线，先读对应的专题分析或验证清单
   再读 [非网络样本采集 Runbook](../non-network-sample-collection-runbook.md)
3. 进入目标模板或目标 seed 目录
4. 如果是 seed，优先按下面顺序读：
   - `fill-guide`
   - `evidence-targets`
   - `collection-runbook`
   - `minimum-log-bundle`
   - `decision-table`
   - `bundle-template`
   - 如果当前工作树里已经有 `request-shaped` 或 `doc/test-derived` baseline 样本，也先把这些本地样本摘入目录，再等新的运行证据
5. 再按该目录下的 `checklist.md` 执行采样或核验
6. 参考 `commands.txt` 或 `starter-commands.txt` 组织最小命令
7. 按 `SUMMARY.md`、`api.txt`、`host.txt`、`guest.txt`、`classification.md` 回填证据

当前 `samples/` 目录统一使用四种升级状态：

1. `template`
2. `seed`
3. `real`
4. `validated`

具体每个目录当前属于哪一档，见 [样本目录索引](./INDEX.md)。

除了 ARM64 网络样本外，目录里现在也开始承接非网络横线的 checklist seed：

1. `ch-backend-notifier-restore-checklist-seed-20260622`
2. `cubesandbox-guest-visible-restore-checklist-seed-20260622`
3. `fc-rootfs-backing-restore-checklist-seed-20260622`
4. `kata-storage-convergence-checklist-seed-20260622`

当前四份 non-network 重点 seed 已经都不只是“代码路径说明型 seed”，而是可以直接承接下一轮真实日志回填的采证包：

1. `ch-backend-notifier-restore-checklist-seed-20260622`
2. `fc-rootfs-backing-restore-checklist-seed-20260622`
3. `kata-storage-convergence-checklist-seed-20260622`
4. `cubesandbox-guest-visible-restore-checklist-seed-20260622`

它们都已经具备：

- `fill-guide`
- `evidence-targets`
- `collection-runbook`
- `minimum-log-bundle`
- `decision-table`
- `bundle-template`
- `bundle-skeleton`（或已明确等价的最小目录骨架）

也就是说，这几份 seed 现在都不只是“告诉你该收什么”，而是已经给出：

1. 最小证据门槛
2. 单次 attempt 的推荐 bundle 形态
3. 拿到 bundle 后如何分桶和决定是否升级成 `real`

如果只看 request-side 当前最强的本地资产，也可以直接这样记：

1. `ch-backend-notifier-restore-checklist-seed-20260622`
   documented CLI/sample request
2. `fc-rootfs-backing-restore-checklist-seed-20260622`
   parser/test-derived request sample
3. `kata-storage-convergence-checklist-seed-20260622`
   extracted JSON request sample
4. `cubesandbox-guest-visible-restore-checklist-seed-20260622`
   documented minimal/full request sample

这四类都 still 只是 request-side 基线，不替代真实 runtime / guest 运行证据。

所以后续最值的动作，不是继续补抽象结构，而是拿真实 host/guest 证据直接尝试把其中一份升级成 `real`。

同时已经出现五份非网络横线 `real` 样本：

1. `ch-backend-notifier-restore-baseline-real-20260622`
2. `cubesandbox-guest-visible-restore-baseline-real-20260622`
3. `cubesandbox-rollback-sandbox-not-running-real-20260622`
4. `cubesandbox-no-more-resource-real-20260613`
5. `cubesandbox-dev-shm-capacity-real-20260613`

其中：

- `cubesandbox-rollback-sandbox-not-running-real-20260622`
  属于 lifecycle / control-plane window failure
- `cubesandbox-no-more-resource-real-20260613`
  属于 scheduler quota / capacity failure
- `cubesandbox-dev-shm-capacity-real-20260613`
  属于 storage / snapshot benchmark precondition failure

最后这一份不能误归成 guest-visible failure。

如果你要继续推进下一份失败类 `real`，当前最缺的不是结构，而是：

- `cubesandbox-guest-visible-restore-checklist-seed-20260622/missing-evidence.txt`

里列出的那组 host/guest 对照日志。
