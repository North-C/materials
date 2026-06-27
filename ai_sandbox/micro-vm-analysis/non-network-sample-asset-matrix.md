# 非网络横线样本资产矩阵

本文把当前非 ARM64 网络主线上的样本资产收成一张矩阵。

目标不是新增架构结论。

目标是回答三个更实际的问题：

1. 存储、I/O 虚拟化、中断虚拟化三条横线，当前分别有哪些样本资产可用？
2. 哪些资产已经是 `real`，哪些还只是 `seed` / baseline seed？
3. 下一步最值得把哪一份 `seed` 升级成 `real`？

源码基线：当前工作树。

关联专题：

- [存储、rootfs 与共享文件系统跨项目专题分析](./storage-rootfs-sharefs-cross-project.md)
- [Virtio 传输与设备数据路径跨项目专题分析](./virtio-data-path-cross-project.md)
- [中断与事件通知跨项目专题分析](./interrupt-event-notification-cross-project.md)

## 1. 核心结论

当前非网络主线已经不缺结构。

我们已经有：

1. 三条横线专题
2. 两组交叉专题
3. 一份 `Cloud Hypervisor + CubeSandbox` restore 后 guest 不可用验证清单
4. 四个重点项目的 checklist seeds
5. 五份 `real`

当前真正缺的是：

把“最成熟的 seed”升级成更多 `real`，而不是继续扩目录或补框架。

## 2. 资产总表

| 资产 | 项目 | 主要服务哪条横线 | 当前状态 | 当前最强价值 | 仍缺什么 |
|---|---|---|---|---|---|
| [CH backend/notifier/restore seed](./samples/ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md) | Cloud Hypervisor | I/O / 中断 / restore 交叉线 | `seed` | `doc_test_derived baseline seed` | 真实 backend 重连、真实 guest 可见性 |
| [CH backend/notifier/restore baseline real](./samples/ch-backend-notifier-restore-baseline-real-20260622/SUMMARY.md) | Cloud Hypervisor | I/O / 中断 / restore 交叉线 | `real` | 成功基线，对照 restore 命令、产物布局、`restored` 事件 | 真实失败样本 |
| [CubeSandbox guest-visible restore seed](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md) | CubeSandbox | 存储 / I/O / 中断 交叉线 | `seed` | `codepath_derived baseline seed`，覆盖控制面到 guest-visible state | 真实 host/guest 对照日志 |
| [CubeSandbox guest-visible restore baseline real](./samples/cubesandbox-guest-visible-restore-baseline-real-20260622/SUMMARY.md) | CubeSandbox | 存储 / I/O / 中断 交叉线 | `real` | 成功基线，证明 create/snapshot/clone/rollback 后 guest-visible state 可回到预期值 | 中间层时序日志 |
| [CubeSandbox rollback `sandbox is not running` real](./samples/cubesandbox-rollback-sandbox-not-running-real-20260622/SUMMARY.md) | CubeSandbox | rollback / lifecycle / restore 相关控制面问题 | `real` | 失败类真实样本，证明 control-plane window 异常 | 更底层的 CubeMaster/Cubelet/Shim 时序日志 |
| [CubeSandbox `no more resource` real](./samples/cubesandbox-no-more-resource-real-20260613/SUMMARY.md) | CubeSandbox | 调度 / 配额 / create-only / clone 并发控制面问题 | `real` | 失败类真实样本，证明 scheduler quota / capacity exhaustion | 更细的 quota/overcommit 策略与长期对照 |
| [CubeSandbox `/dev/shm` capacity real](./samples/cubesandbox-dev-shm-capacity-real-20260613/SUMMARY.md) | CubeSandbox | 存储 / snapshot benchmark precondition | `real` | 失败类真实样本，证明 dirty-page benchmark 在写脏页前就被 `/dev/shm` 容量挡住 | 更长期的模板规格对照与 guest-visible 对照 |
| [Firecracker rootfs/backing/restore seed](./samples/fc-rootfs-backing-restore-checklist-seed-20260622/SUMMARY.md) | Firecracker | 存储线 | `seed` | `codepath_derived baseline seed`，覆盖 root 表达与 backing file 依赖 | 真实 restore 对照与 guest 设备可见性 |
| [Kata storage convergence seed](./samples/kata-storage-convergence-checklist-seed-20260622/SUMMARY.md) | Kata Containers | 存储线 | `seed` | `codepath_derived baseline seed`，覆盖 translation -> request -> guest mount | 真实 CreateContainerRequest / add_storages / mount 日志 |

## 3. 按横线查看

### 存储线

当前可直接用的资产：

- [Firecracker rootfs/backing/restore seed](./samples/fc-rootfs-backing-restore-checklist-seed-20260622/SUMMARY.md)
- [Kata storage convergence seed](./samples/kata-storage-convergence-checklist-seed-20260622/SUMMARY.md)
- [CubeSandbox guest-visible restore seed](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md)
- [CubeSandbox guest-visible restore baseline real](./samples/cubesandbox-guest-visible-restore-baseline-real-20260622/SUMMARY.md) 作为成功对照面
- [CubeSandbox rollback `sandbox is not running` real](./samples/cubesandbox-rollback-sandbox-not-running-real-20260622/SUMMARY.md) 作为“不是 rootfs 收敛问题，而是更早的 lifecycle window 问题”的反例
- [CubeSandbox `no more resource` real](./samples/cubesandbox-no-more-resource-real-20260613/SUMMARY.md) 作为“不是 guest-visible 闭环问题，而是 scheduler capacity 问题”的反例
- [CubeSandbox `/dev/shm` capacity real](./samples/cubesandbox-dev-shm-capacity-real-20260613/SUMMARY.md) 作为“不是 guest-visible 闭环问题，而是 benchmark tmpfs 容量前置条件问题”的反例

当前缺口：

1. 还没有 Firecracker 存储失败类 `real`
2. 还没有 Kata storage convergence 类 `real`
3. 还没有 CubeSandbox guest-visible storage/mount 失败类 `real`

这里要额外防止一个误桶：

`/dev/shm` 容量不足样本属于 storage / snapshot benchmark precondition failure，
不是 guest-visible storage convergence failure。

### I/O 虚拟化线

当前可直接用的资产：

- [CH backend/notifier/restore seed](./samples/ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md)
- [CH backend/notifier/restore baseline real](./samples/ch-backend-notifier-restore-baseline-real-20260622/SUMMARY.md)
- [CubeSandbox guest-visible restore seed](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md)
- [CubeSandbox guest-visible restore baseline real](./samples/cubesandbox-guest-visible-restore-baseline-real-20260622/SUMMARY.md)

当前缺口：

1. 还没有一份 CH 的失败类 `real`
2. 还没有一份能证明 “控制面成功但 worker/guest-visible state 没闭环” 的 CubeSandbox `real`

这里需要特别强调：

当前仓库已经有：

1. `CubeSandbox guest-visible restore` 成功基线 `real`
2. `CubeSandbox rollback sandbox is not running` 控制面失败 `real`
3. `CubeSandbox no more resource` 调度容量失败 `real`
4. `CubeSandbox /dev/shm capacity` benchmark precondition 失败 `real`

但还没有：

同一组证据里同时证明

- 控制面成功
- worker/后端阶段至少部分推进
- 最终停在 guest-visible state 收敛

的失败类 `real`。

这也是为什么当前 `cubesandbox-guest-visible-restore-checklist-seed-20260622`
现在最重要的不是再补解释，而是守住升级护栏：

- 纯控制面失败，继续归 `sandbox is not running` 那份 `real`
- 纯成功路径，继续归 success baseline `real`
- 只有“控制面成功 + worker/backend 推进 + guest-visible 收敛失败”三者同证时，才升级成新的 failure `real`

### 中断虚拟化线

当前可直接用的资产：

- [CH backend/notifier/restore seed](./samples/ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md)
- [CH backend/notifier/restore baseline real](./samples/ch-backend-notifier-restore-baseline-real-20260622/SUMMARY.md)
- [CubeSandbox guest-visible restore seed](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md)
- [CubeSandbox guest-visible restore baseline real](./samples/cubesandbox-guest-visible-restore-baseline-real-20260622/SUMMARY.md)
- [CubeSandbox rollback `sandbox is not running` real](./samples/cubesandbox-rollback-sandbox-not-running-real-20260622/SUMMARY.md) 作为“不是 irqfd/MSI-X 故障，而是控制面 window 异常”的负样本

当前缺口：

1. 还没有一份 CH 的失败类 `real`
2. 还没有一份 CubeSandbox 的 guest-visible / ready / worker 闭环失败类 `real`

同样地，这里也不能把控制面失败样本误算成中断失败样本。

`sandbox is not running` 证明的是 lifecycle/control-plane window，
不是 irqfd/MSI-X/route/controller 失败。

## 4. 最值得升级的下一批

如果只按收益比排序，当前建议如下：

1. [CubeSandbox guest-visible restore seed](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md)  
   原因：现在已经有一份 CubeSandbox 成功基线 `real`、两份控制面失败 `real`，再加上一份 benchmark precondition failure `real`；再补一份 guest-visible 失败 `real`，就能把同一项目的几类问题域拆干净。

2. [Firecracker rootfs/backing/restore seed](./samples/fc-rootfs-backing-restore-checklist-seed-20260622/SUMMARY.md)  
   原因：存储线里 Firecracker 仍没有任何 `real`。

3. [Kata storage convergence seed](./samples/kata-storage-convergence-checklist-seed-20260622/SUMMARY.md)  
   原因：Kata 的 storage translation / guest mount 收敛目前仍只有 seed。

4. [CH backend/notifier/restore seed](./samples/ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md)  
   原因：CH 已有成功基线 `real`，现在更需要的是失败类 `real`，但优先级略低于 CubeSandbox guest-visible 失败样本。

## 5. `real` 覆盖表

下面这张表只回答一件事：

非网络三条横线里，哪些项目已经有 `real`，而且这些 `real` 属于成功基线还是失败样本。

| 项目 | 存储线 | I/O 虚拟化线 | 中断虚拟化线 | 当前说明 |
|---|---|---|---|---|
| Cloud Hypervisor | 成功基线 `real` | 成功基线 `real` | 成功基线 `real` | 已有 restore 成功对照面，仍缺失败类 `real` |
| CubeSandbox | 成功基线 `real` + 两类控制面失败 `real` + 一类 precondition failure `real` | 成功基线 `real` + 两类控制面失败 `real` | 成功基线 `real` + 两类控制面失败 `real` | 已有成功、lifecycle window 失败、scheduler capacity 失败、benchmark precondition 失败四类样本，仍缺 guest-visible 闭环失败 `real` |
| Firecracker | 无 `real` | 无 `real` | 无 `real` | 仅有强 `seed` / baseline seed |
| Kata Containers | 无 `real` | 无 `real` | 无 `real` | 仅有强 `seed` / baseline seed |

这张表的关键用途是防止误判当前阶段。

当前不是“所有项目都还没有真实样本”。

更准确地说：

1. `Cloud Hypervisor` 已有一份成功基线 `real`
2. `CubeSandbox` 已有一份成功基线 `real`、两份控制面失败 `real` 和一份 benchmark precondition failure `real`
3. `Firecracker` 与 `Kata` 仍没有任何非网络 `real`

因此下一步最值的动作，不应该平均用力，而应该优先把现有 `real` 最少、但资产成熟度已足够高的项目往前推。

## 6. 当前证据强度表

除了看有没有 `real`，还需要看“当前工作树里最强的证据已经到哪一层”。

这张表只回答一个问题：

如果今天就拿当前工作树做判断，每个重点 non-network seed 现在最强能走到哪一步。

| 项目 / seed | 当前最强证据层级 | 这意味着什么 | 还缺什么才可能升 `real` |
|---|---|---|---|
| Cloud Hypervisor `ch-backend-notifier-restore` | `doc/test-derived baseline` | 已有 restore 命令路径、`restored` 事件样本、snapshot 目录布局、transport/notifier/controller 锚点 | 真实 restore 请求、真实 backend/notifier/controller 观测、真实 guest-visible 结果 |
| Firecracker `fc-rootfs-backing-restore` | `codepath-derived baseline` | 已有 root expression、backing/restore 语义、snapshot 只保存可重建引用的边界 | 真实 restore 请求、真实 backing consistency、真实 guest 设备可见性与 rootfs 可用性 |
| Kata `kata-storage-convergence` | `stronger request propagation` | 除了 codepath 外，当前工作树里已有真实形态的 `CreateContainerRequest` JSON 样本 | guest `add_storages()` / `mount_from()` 运行证据，以及最终 rootfs/volume 可用性 |
| CubeSandbox `cubesandbox-guest-visible-restore` | `codepath-derived baseline + upgrade guards` | 控制面、ready、worker/backend、guest-visible 证据锚点和完整升级规则都已具备 | 一包新的同 attempt host/guest 日志，能同时证明控制面成功、worker 推进、guest-visible 收敛失败 |

因此，“最接近新 `real`” 和 “当前解释框架最完整” 不是同一个维度。

按当前工作树看：

1. `CubeSandbox` 最接近新的 failure `real`
2. `Kata` 最接近新的 request-to-guest-landing 真实证据
3. `Cloud Hypervisor` 与 `Firecracker` 仍主要缺新的实跑证据

这组顺序的实际含义是：

- `CubeSandbox` 不是最简单，而是升级规则最完整、最适合直接接一包新日志做 failure-side 判定
- `Kata` 不是最接近 `real`，而是最接近从 host-side 样本推进到 guest-side 运行证据
- `Cloud Hypervisor` / `Firecracker` 当前则仍主要受限于缺新的 runtime/guest transcript

换句话说，这四份重点 seed 到当前阶段，缺的已经不再是：

- request 字段结构
- bundle 目录形态
- 最小证据门槛
- 分桶规则

它们真正缺的是：

- 新的、同 attempt 的 host/runtime/guest 运行证据

## 7. 证据成熟度梯度

当前这四份重点 seed，虽然都还不是新的 `real`，但它们所处的证据成熟度其实已经分层了。

可以先固定成下面这条梯度：

| 层级 | 含义 | 当前典型样本 |
|---|---|---|
| `codepath-derived baseline` | 只有源码链和语义边界，没有真实请求或真实运行证据 | Firecracker rootfs/backing seed |
| `doc/test-derived baseline` | 有文档、测试夹具或事件样本，可固定成功格式或产物布局 | Cloud Hypervisor backend/notifier seed |
| `request-shaped sample` | 已有真实形态或文档化的 request/JSON 样本，但没有 guest 运行证据 | Kata storage seed / CubeSandbox guest-visible seed |
| `baseline real` | 已有真实成功基线，可作为后续 failure 样本对照 | CH success baseline real / CubeSandbox success baseline real |
| `failure real` | 已有真实失败侧证据，可作为同类问题直接对照 | CubeSandbox `sandbox is not running` real |

这条梯度的用途很直接：

1. 不再把所有 `seed` 当成同一种成熟度
2. 明确下一步是“补哪一层缺口”，而不是只问“为什么还不是 `real`”
3. 也解释了为什么 `Kata` 现在比 `Firecracker` 更适合继续往前推一格，而 `CubeSandbox` 又比两者更适合直接冲新的 failure `real`

这里还要再补一个小但重要的约束：

同属 `request-shaped sample` 这一层，内部也有强弱差异：

1. `json sample`
   最接近真实 host-side 请求体
2. `documented request sample`
   更适合固定字段语义和最小结构
3. `parser/test-derived request sample`
   更适合固定 parser 接受的字段边界

这三者都比纯 codepath 强，但都还不能替代真正的 runtime / guest 运行证据。

## 8. 如何使用这张表

后续如果继续推进，不建议再从零判断“该补什么样本”。

建议顺序是：

1. 先看这张矩阵，选一份最值得升级的 seed
2. 再回到对应横线专题，确认它覆盖的问题边界
3. 然后只围绕这份 seed 回填最小真实证据

如果已经选定某一份 seed，当前更推荐统一按下面顺序操作：

1. 先读该目录的 `fill-guide`
2. 再读 `evidence-targets`
3. 再读 `collection-runbook`
4. 拿到一包新证据后，先过 `minimum-log-bundle`
5. 再用 `decision-table` 判断分桶
6. 如果目录里有 `bundle-template`，优先按它组织单次 attempt 的日志包

这样可以避免一边继续写新框架，一边迟迟不落第一批真正有用的 `real` 样本。

## 9. 当前资产完备度表

除了看“证据强度”，现在还可以直接看“目录里缺不缺操作资产”。

按当前工作树，四份重点 seed 的目录资产完备度已经基本进入同一层级：

| seed | fill-guide | evidence-targets | collection-runbook | minimum-log-bundle | decision-table | bundle-template | bundle-skeleton | request-shaped sample | request template | missing-evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| CH backend/notifier/restore | yes | yes | yes | yes | yes | yes | yes | documented | yes | yes |
| Firecracker rootfs/backing | yes | yes | yes | yes | yes | yes | yes | parser/test-derived | yes | yes |
| Kata storage convergence | yes | yes | yes | yes | yes | yes | yes | json sample | yes | yes |
| CubeSandbox guest-visible restore | yes | yes | yes | yes | yes | yes | yes | documented | yes | yes |

这里唯一值得单独注意的差异是：

- `Kata` 的 request-shaped sample 最接近真实执行输入
- `CH` 与 `CubeSandbox` 当前更像 documented request-shaped sample
- `Firecracker` 则更像 parser/test-derived request-shaped sample

但这不改变优先级。因为 `CubeSandbox` 当前离 failure `real` 最近，缺的不是目录资产，而是一包新的同 attempt host/guest 运行证据。

如果把 request-side 再压成更细的成熟度，当前也可以直接这样看：

| seed | request-side strongest form |
|---|---|
| CH backend/notifier/restore | documented CLI/sample request |
| Firecracker rootfs/backing | parser/test-derived JSON request |
| Kata storage convergence | extracted JSON request sample |
| CubeSandbox guest-visible restore | documented minimal + documented full request sample |

这张小表的意义是：

1. 后续不必再靠记忆判断“哪份 seed 的 request-side 样本更接近真实输入”
2. 也更容易解释为什么 `Kata` 和 `CubeSandbox` 在 request 层比 `Firecracker` 更适合先往前推

## 10. 从 `seed` 升到 `real` 的最低证据门槛

这部分只回答一个问题：

如果下一步真的开始升级某一份 `seed`，最少要补哪些证据，才不至于伪造 `real`。

| seed | 升级到 `real` 的最低门槛 |
|---|---|
| [CH backend/notifier/restore seed](./samples/ch-backend-notifier-restore-checklist-seed-20260622/SUMMARY.md) | 1. 一次真实 restore 请求 2. 一段真实 `event.json` 或等价 `restored` 事件 3. 一类真实 backend/notifier/controller 观测 4. 一次 guest 设备可见性检查 |
| [CubeSandbox guest-visible restore seed](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/SUMMARY.md) | 1. 一次真实 `VmRestore`/`VmResumeFromSnapshot`/`VmSetFs`/`VmAddDevice` 相关请求 2. 一段真实 `VsockServerReady`/probe/`VmShutdown` 或 worker 唤醒日志 3. 一次 guest agent 可见性或 mount/ready 收敛观测 |
| [Firecracker rootfs/backing/restore seed](./samples/fc-rootfs-backing-restore-checklist-seed-20260622/SUMMARY.md) | 1. 一次真实 snapshot/restore 请求 2. root block/pmem 与 cmdline 的真实对应关系 3. backing file/disk path/pmem path 的真实观测 4. 一次 guest `/dev/vd*`/`/dev/pmem*` 或 rootfs 可用性检查 |
| [Kata storage convergence seed](./samples/kata-storage-convergence-checklist-seed-20260622/SUMMARY.md) | 1. 一次真实 `CreateContainerRequest.storages` 证据 2. 一段真实 `add_storages()` / `mount_from()` 日志 3. 一次 guest rootfs/volume 可用性观测 |

这四条门槛的共同点是：

必须同时覆盖：

1. 控制面请求或输入
2. 中间层日志或状态
3. guest 可见结果

只满足其中一层，最多只能继续算 `seed` 或 `baseline seed`，不应该升级成 `real`。

对 Firecracker 这条线，也要额外强调一句：

`restore succeeded` 本身还不是 `real`。

它只能证明 VMM restore 流程通过。只有再补上 root expression、backing consistency，以及 guest 设备可见性和 rootfs 可用性，才能把样本从 `codepath-derived baseline seed` 升成真正的 `real`。

对 Kata 这条线，再额外强调一句：

`CreateContainerRequest.storages` 本身还不是 `real`。

它只能证明 host 侧 translation 和 request propagation 成立。只有再补上 guest `add_storages()` / `mount_from()` 以及最终 rootfs/volume 可用性观测，才能把样本从 `codepath-derived baseline seed` 升成真正的 `real`。

不过当前工作树里，Kata 已经不只是“纯代码路径”了。

至少已经存在真实形态的 `CreateContainerRequest` JSON 样本，其中包含 `storages` 数组、`driver`、`source`、`mount_point` 等字段。

这意味着：

- `Kata storage` 现在可以先向“更强的 request propagation 证据”推进
- 但在没有 guest `add_storages()` / `mount_from()` 与最终可用性观测前，仍然不能升级成 `real`

对 Cloud Hypervisor 这条线，同样要额外强调一句：

`event == "restored"` 本身还不是 `real`。

它只能证明 restore 流程成功结束。只有再补上 transport/notifier 重建、controller restore，以及 guest 侧设备可见性结果，才能把样本从 `doc/test-derived baseline seed` 升成真正的 `real`。

当前这四份 seed 虽然都已经有 request template / request-shaped sample 之类的便捷资产，但它们的作用都相同：

- 统一字段结构
- 降低后续回填成本

而不是：

- 提供新的运行时证据

所以它们只能帮助“更快接证据”，不能替代真实证据本身。

## 11. 当前最缺的那组证据

如果只看一条最缺的证据链，当前就是：

`CubeSandbox guest-visible restore/update failure`

更具体地说，当前工作树里还缺一组同时满足下面三点的日志：

1. 控制面请求成功
2. worker / backend 路径继续推进
3. guest-visible state 最终仍未收敛

这件事已经在这份 seed 里被单独列为缺口：

- [CubeSandbox guest-visible missing evidence](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/missing-evidence.txt)

而且这份 seed 现在已经不只是“知道缺什么”，还补齐了：

- [minimum-log-bundle.txt](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/minimum-log-bundle.txt)
- [decision-table.txt](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/decision-table.txt)
- [bundle-template.txt](./samples/cubesandbox-guest-visible-restore-checklist-seed-20260622/bundle-template.txt)

也就是说，下一轮如果真的拿到一包新日志，已经可以直接回答三件事：

1. 这包日志够不够资格回填
2. 它该继续留在 seed、归 success baseline，还是归 control-plane failure
3. 它是否终于足够升级成新的 guest-visible failure `real`

我已经在当前工作树的 `logs/` 与 `tmp/oneclick-artifacts/` 下复查过这组关键签名。

结果是：

- 目前没有命中 `wait a pci`

对另外两条存储线，也可以先下一个更保守的“当前工作树状态”判断：

1. `Kata`
   - 当前工作树里已经存在一批真实形态的 `CreateContainerRequest` JSON 样本；
   - 这些样本足以把 `request propagation` 证据从“纯代码路径”推进到“准真实请求样本”；
   - 但仍缺 guest `add_storages()` / `mount_from()` 与最终可用性观测，所以还不能升级成 `real`。

2. `Firecracker`
   - 当前工作树里仍没有新的真实 restore + guest-visible 设备/ rootfs 证据；
   - 现有最强资产依然是 codepath-derived baseline seed，而不是可升级的准真实样本。
- 没有命中 `Failed to update interface/routes/ARP neighbours`
- 没有命中 `vm ready, vsock is listening`
- 也没有命中 `ApiRequest::VmSetFs` / `FsEvent` / `failed to update filter list`

这说明当前缺的不是“解释”，而是真实日志本身尚未进入工作树。

因此，后续再继续推进时，不建议继续补总览或种子元数据。

最值得做的是：只围绕这份缺口清单补真实日志。

## 12. 当前阶段的最小执行顺序

如果今天就要开始推进一次 non-network 证据回填，最小顺序建议固定为：

1. 先看 [非网络下一批真实样本目标图](./non-network-next-target-map.md)，选一份最值得升级的 seed
2. 再看 [非网络样本采集 Runbook](./non-network-sample-collection-runbook.md)，确认统一动作顺序
3. 再用 [非网络证据包记录模板](./non-network-evidence-bundle-template.md) 给新 bundle 记账
4. 最后回到对应 seed 目录，按 `decision-table` 做升级判定

如果没有新的 host/runtime/guest 运行证据进入工作树，当前最合理的动作通常不是继续扩分析结构，而是停在这里。
