# 样本目录索引

本文是 `analysis/samples/` 目录的总索引。

目标不是新增分析结论。

目标是把当前已经存在的样本资产，按“模板 / 种子 / 真实案例”三类重新分组，减少后续继续推进时的导航成本。

源码基线：当前工作树。

## 1. 如何使用这份索引

如果你准备第一次开始采样，先看“模板目录”。

如果你想参考一个已填示范目录，先看“样本种子”和“真实案例目录”。

如果你已经知道要采哪个项目，直接跳到对应项目小节即可。

## 2. 总体分组

| 状态 | 含义 |
|---|---|
| `template` | 还没填真实证据，只提供结构、checklist、starter commands、fill guide |
| `seed` | 已经按模板填了基础字段，但还没有真实失败日志 |
| `real` | 使用仓库内已有真实案例或真实报告填出的样本目录 |
| `validated` | 已经过进一步核验，证据闭环更完整 |

当前目录中还没有 `validated` 样本。

## 3. 模板目录

| 项目 | 目录 | 用途 |
|---|---|---|
| Kata | [kata-arm64-network-backend-diff-template](./kata-arm64-network-backend-diff-template/) | backend 差异真实样本模板 |
| Cloud Hypervisor | [ch-arm64-network-hotplug-failure-template](./ch-arm64-network-hotplug-failure-template/) | runtime `add-net` / hotplug 失败模板 |
| Firecracker | [fc-arm64-network-guest-visibility-template](./fc-arm64-network-guest-visibility-template/) | guest visibility / interrupt visibility 模板 |
| CubeSandbox | [cubesandbox-arm64-network-midlogs-template](./cubesandbox-arm64-network-midlogs-template/) | 中间层日志样本模板 |

## 4. ARM64 网络样本种子目录

| 项目 | 目录 | 升级状态 | 当前状态 |
|---|---|---|---|
| Kata | [kata-arm64-network-backend-diff-seed-20260618](./kata-arm64-network-backend-diff-seed-20260618/) | `seed` | backend 差异三路签名已落目录，缺真实日志 |
| Kata | [kata-arm64-network-backend-diff-qemu-seed-20260618](./kata-arm64-network-backend-diff-qemu-seed-20260618/) | `seed` | QEMU 子路径种子，目标签名 `QMP not initialized` |
| Kata | [kata-arm64-network-backend-diff-ch-seed-20260618](./kata-arm64-network-backend-diff-ch-seed-20260618/) | `seed` | CH 子路径种子，目标签名 `open named tuntap` |
| Kata | [kata-arm64-network-backend-diff-dragonball-seed-20260618](./kata-arm64-network-backend-diff-dragonball-seed-20260618/) | `seed` | Dragonball 子路径种子，目标签名 `insert network device` |
| Kata | [kata-arm64-network-route-convergence-seed-20260618](./kata-arm64-network-route-convergence-seed-20260618/) | `seed` | route convergence 种子，目标签名 `update routes request failed` |
| Cloud Hypervisor | [ch-arm64-network-hotplug-seed-20260618](./ch-arm64-network-hotplug-seed-20260618/) | `seed` | `_test_net_hotplug()` 已转成样本目录，缺真实失败输出 |
| Cloud Hypervisor | [ch-arm64-network-restore-seed-20260618](./ch-arm64-network-restore-seed-20260618/) | `seed` | restore / GIC-state 协同问题已落目录，缺真实回归日志 |
| Firecracker | [fc-arm64-network-guest-visibility-seed-20260618](./fc-arm64-network-guest-visibility-seed-20260618/) | `seed` | guest visibility 路径已落目录，缺真实 guest 症状 |
| Firecracker | [fc-arm64-network-restore-seed-20260618](./fc-arm64-network-restore-seed-20260618/) | `seed` | restore / arch-state 问题已落目录，缺真实回归日志 |

## 5. 非网络横线 checklist seeds

| 项目 | 目录 | 升级状态 | 当前状态 |
|---|---|---|---|
| Cloud Hypervisor | [ch-backend-notifier-restore-checklist-seed-20260622](./ch-backend-notifier-restore-checklist-seed-20260622/) | `seed` | backend/notifier/restore 清单型种子，面向 I/O / 中断 / restore 交叉线 |
| Firecracker | [fc-rootfs-backing-restore-checklist-seed-20260622](./fc-rootfs-backing-restore-checklist-seed-20260622/) | `seed` | rootfs/backing/restore 清单型种子，面向非 ARM64 存储横线 |
| Kata | [kata-storage-convergence-checklist-seed-20260622](./kata-storage-convergence-checklist-seed-20260622/) | `seed` | storage translation / agent convergence 清单型种子，面向非 ARM64 存储横线 |
| CubeSandbox | [cubesandbox-guest-visible-restore-checklist-seed-20260622](./cubesandbox-guest-visible-restore-checklist-seed-20260622/) | `seed` | guest-visible restore/update 清单型种子，面向平台闭环与 guest 可见性 |

## 6. 真实案例目录

| 项目 | 目录 | 升级状态 | 说明 |
|---|---|---|---|
| Cloud Hypervisor | [ch-backend-notifier-restore-baseline-real-20260622](./ch-backend-notifier-restore-baseline-real-20260622/) | `real` | 基于仓库内 snapshot/restore 文档与 `restored` 事件片段整理的成功基线样本 |
| CubeSandbox | [cubesandbox-guest-visible-restore-baseline-real-20260622](./cubesandbox-guest-visible-restore-baseline-real-20260622/) | `real` | 基于 one-click E2E 结果整理的 guest-visible restore/update 成功基线样本 |
| CubeSandbox | [cubesandbox-arm64-network-tap-fd-unavailable-20260613](./cubesandbox-arm64-network-tap-fd-unavailable-20260613/) | `real` | 基于真实 `tap fd unavailable` 案例与报告填充 |
| CubeSandbox | [cubesandbox-rollback-sandbox-not-running-real-20260622](./cubesandbox-rollback-sandbox-not-running-real-20260622/) | `real` | 基于 rollback/snapshot 并发路径中 `sandbox is not running` 的真实报告整理 |
| CubeSandbox | [cubesandbox-no-more-resource-real-20260613](./cubesandbox-no-more-resource-real-20260613/) | `real` | 基于 `CubeMaster returned error code 130597: no more resource` 的真实控制面容量失败样本 |
| CubeSandbox | [cubesandbox-dev-shm-capacity-real-20260613](./cubesandbox-dev-shm-capacity-real-20260613/) | `real` | 基于 `/dev/shm/dirty: No space left on device` 的真实 benchmark precondition 失败样本 |

## 7. 按项目查看

### Kata

- 模板：
  [kata-arm64-network-backend-diff-template](./kata-arm64-network-backend-diff-template/)
- 种子：
  [kata-arm64-network-backend-diff-seed-20260618](./kata-arm64-network-backend-diff-seed-20260618/)
- 子种子：
  [kata-arm64-network-backend-diff-qemu-seed-20260618](./kata-arm64-network-backend-diff-qemu-seed-20260618/)
- 子种子：
  [kata-arm64-network-backend-diff-ch-seed-20260618](./kata-arm64-network-backend-diff-ch-seed-20260618/)
- 子种子：
  [kata-arm64-network-backend-diff-dragonball-seed-20260618](./kata-arm64-network-backend-diff-dragonball-seed-20260618/)
- 种子：
  [kata-arm64-network-route-convergence-seed-20260618](./kata-arm64-network-route-convergence-seed-20260618/)
- 非网络 seed：
  [kata-storage-convergence-checklist-seed-20260622](./kata-storage-convergence-checklist-seed-20260622/)

### Cloud Hypervisor

- 模板：
  [ch-arm64-network-hotplug-failure-template](./ch-arm64-network-hotplug-failure-template/)
- 种子：
  [ch-arm64-network-hotplug-seed-20260618](./ch-arm64-network-hotplug-seed-20260618/)
- 种子：
  [ch-arm64-network-restore-seed-20260618](./ch-arm64-network-restore-seed-20260618/)
- 非网络 seed：
  [ch-backend-notifier-restore-checklist-seed-20260622](./ch-backend-notifier-restore-checklist-seed-20260622/)
- 真实基线：
  [ch-backend-notifier-restore-baseline-real-20260622](./ch-backend-notifier-restore-baseline-real-20260622/)

### Firecracker

- 模板：
  [fc-arm64-network-guest-visibility-template](./fc-arm64-network-guest-visibility-template/)
- 非网络 seed：
  [fc-rootfs-backing-restore-checklist-seed-20260622](./fc-rootfs-backing-restore-checklist-seed-20260622/)
- 种子：
  [fc-arm64-network-guest-visibility-seed-20260618](./fc-arm64-network-guest-visibility-seed-20260618/)
- 种子：
  [fc-arm64-network-restore-seed-20260618](./fc-arm64-network-restore-seed-20260618/)

### CubeSandbox

- 模板：
  [cubesandbox-arm64-network-midlogs-template](./cubesandbox-arm64-network-midlogs-template/)
- 真实基线：
  [cubesandbox-guest-visible-restore-baseline-real-20260622](./cubesandbox-guest-visible-restore-baseline-real-20260622/)
- 真实案例：
  [cubesandbox-arm64-network-tap-fd-unavailable-20260613](./cubesandbox-arm64-network-tap-fd-unavailable-20260613/)
- 真实案例：
  [cubesandbox-rollback-sandbox-not-running-real-20260622](./cubesandbox-rollback-sandbox-not-running-real-20260622/)
- 真实案例：
  [cubesandbox-no-more-resource-real-20260613](./cubesandbox-no-more-resource-real-20260613/)
- 真实案例：
  [cubesandbox-dev-shm-capacity-real-20260613](./cubesandbox-dev-shm-capacity-real-20260613/)
- 非网络 seed：
  [cubesandbox-guest-visible-restore-checklist-seed-20260622](./cubesandbox-guest-visible-restore-checklist-seed-20260622/)

## 8. 推荐阅读顺序

如果是第一次接触这一层资产，建议按下面顺序读。

1. 先读 [ARM64 网络下一批真实样本目标图](../arm64-network-next-target-map.md)
2. 如果做非网络横线，先读对应的横线专题或验证清单
3. 再读 [非网络样本采集 Runbook](../non-network-sample-collection-runbook.md)
4. 再读 [样本资产目录](./README.md)
5. 然后读这份总索引
6. 最后进入具体模板或具体种子目录
7. 如果进入的是 seed，默认按：
   `fill-guide -> evidence-targets -> collection-runbook -> minimum-log-bundle -> decision-table -> bundle-template`
   的顺序组织一次 attempt 的证据

## 9. 结论

现在 `analysis/samples/` 已经不是单纯的模板目录。

它已经同时包含：

1. 模板
2. 种子
3. 真实案例
4. 非网络横线 checklist seeds

后续继续推进时，最有价值的动作不是再建更多目录。

而是从这份索引里挑一个种子，把它升级成真实样本。

当前四份 non-network 重点 seed 已经不只是“代码路径说明”，而是可以直接承接下一轮真实日志回填的采证包：

1. [fc-rootfs-backing-restore-checklist-seed-20260622](./fc-rootfs-backing-restore-checklist-seed-20260622/)
2. [kata-storage-convergence-checklist-seed-20260622](./kata-storage-convergence-checklist-seed-20260622/)
3. [ch-backend-notifier-restore-checklist-seed-20260622](./ch-backend-notifier-restore-checklist-seed-20260622/)
4. [cubesandbox-guest-visible-restore-checklist-seed-20260622](./cubesandbox-guest-visible-restore-checklist-seed-20260622/)

它们都已经包含：

- `fill-guide`
- `evidence-targets`
- `collection-runbook`
- `bundle-template`（或已明确等价的最小日志包规范）

其中最成熟的四份还已经进一步包含：

- `minimum-log-bundle`
- `decision-table`

所以后续真正的动作，已经不再是“补说明文档”，而是“拿一包真实证据进来，按现成规则做第一次可审计分类”。

如果只想快速判断一份 seed 当前最强的 request-side 资产是什么，可以直接记：

- `CH`：documented CLI/sample request
- `Firecracker`：parser/test-derived request sample
- `Kata`：extracted JSON request sample
- `CubeSandbox`：documented minimal/full request sample

所以后续最值的动作，不是继续解释概念，而是拿真实 host/guest 证据直接尝试把其中一份升级成 `real`。
