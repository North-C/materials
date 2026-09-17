# CubeSandbox 历史镜像创建压力测试报告

> 复验说明（2026-07-27 10:59）：本报告首轮压测未在每轮之间严格保证 TAP 资源可用，原始错误计数仅保留为历史记录，不再作为资源受控的结论依据。严格清理 Sandbox/shim/task、重置并校验健康 TAP 池后，两次完整四轮矩阵合计在 2040 次请求中复现 9 次 `reset guest time failed`，且 TAP FD 错误为 0。以 [严格 TAP 隔离复验报告](CUBESANDBOX_HISTORICAL_IMAGE_PRESSURE_ISOLATED_TAPS_20260727.md) 为准。

日期：2026-07-27（Asia/Shanghai）  
目标机：`root@192.168.25.90`  
Template：`tpl-abold-83570639543444b0`

## 结论

问题已经复现，不能确认历史自编译镜像没有问题。

历史镜像在串行创建下保持稳定，但并发 10 的两轮独立测试共 700 次正式请求中出现 3 次 `reset guest time failed`。该镜像没有消除 reset 故障，只是此前 20 次串行 A/B 样本没有命中并发压力下的低概率窗口。

## 测试不变量

- guest 镜像版本：`20260609-222734`
- guest 镜像 SHA-256：`1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da`
- Cubelet SHA-256：`88e5e224fdfb9b1fca5d4722cfa273c49aa7048dffdb28fb88adbc44ddee4c96`
- cube-shim SHA-256：`4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d`
- guest kernel SHA-256：`7c227b2ba09988bb4380a95658d1ebe6e17e2f95fac60ed6eb6e42f4a676d8e5`
- Host kernel：`6.6.0-132.0.0.111.oe2403sp3.aarch64`
- Template 状态：`READY`，`guest_image_version=20260609-222734`，`compat_status=OK`

测试前为 `sandboxes/shims/tasks=0/0/0`，CubeAPI 健康。

## 压测方法

沿用现有 `cube-bench` create-only 口径。每档先执行 3 次预热，再运行正式请求；每档前后检查并清理 Sandbox、shim 和 task。发生错误后保存报告、进程列表和服务日志，并停止提升并发度。

原计划矩阵为：

| Case | 并发 | 正式请求 |
|---|---:|---:|
| `create-c1-n20` | 1 | 20 |
| `create-c10-n200` | 10 | 200 |
| `create-c20-n300` | 20 | 300 |
| `create-c50-n500` | 50 | 500 |

标准矩阵在 c10 首次复现后停止。为排除单次偶发或客户端误报，运行时恢复干净后又独立执行了一轮 `c10/n500`；确认同型 reset 后不再执行 c20/c50。

## 结果

| Case | 成功 | 错误 | reset 错误 | 其他错误 | 遗留 shim |
|---|---:|---:|---:|---:|---:|
| `c1/n20` | 20/20 | 0 | 0 | 0 | 0 |
| `c10/n200` | 199/200 | 1 | 1 | 0 | 1 |
| 独立 `c10/n500` | 497/500 | 3 | 2 | 1 | 2 |

汇总：

- 全部正式请求：`716/720` 成功，4 次错误。
- c10：`696/700` 成功，4 次错误。
- c10 reset 故障：`3/700`，复现率约 `0.429%`。
- c10 其他错误：`1/700`，为 network-agent tap FD 不可用，与 reset 分开统计。
- 3 次 reset 均对应遗留 shim；runner 恢复后每轮均回到 `sandboxes/shims/tasks=0/0/0`。

性能数据：

| Case | 吞吐 | create 平均 | create P95 |
|---|---:|---:|---:|
| `c1/n20` | 16.70 QPS | 47.09 ms | 49.69 ms |
| `c10/n200` | 21.57 QPS | 107.01 ms | 226.01 ms |
| 独立 `c10/n500` | 23.10 QPS | 279.65 ms | 645.72 ms |

## 错误链

3 次 reset 的错误链一致：

```text
HTTP 500
CubeMaster returned error code -1
failed to run container
failed to create shim task
Create sandbox failed: reset guest time failed
ttrpc err: Receive packet timeout Elapsed(())
```

第一次 c10 测试的失败实例为 `165e605422e54d329b8bb2bfe5d104be`。独立复验中的两个 reset 实例为：

- `7214adfae35a4369aa9744d7d26ac58c`
- `048cfadca96b4e6aa4d5b6f364848670`

独立复验的第三个错误为：

```text
register network-agent tap for pool failed:
tap fd unavailable for sandbox
```

该错误没有进入 guest reset 链，也没有对应遗留 shim。

两个捕获窗口中均未发现 `reset reseed random failed`、RCU stall/starved、timer handling issue、`Recv len invalid`、kernel OOM 或 hung-task 迹象。因此，本轮能确认 reset RPC 的 ttrpc receive timeout，但没有再次捕获此前社区镜像失败窗口中的 RCU/timer 特征。

## 对此前结论的影响

2026-07-25 的历史镜像隔离轮次为串行 `20/20`，只能说明短串行样本未命中。当前压力结果证明：

- 历史镜像替换没有解决 `reset guest time failed`。
- 镜像确实会影响故障概率或触发条件，但不是唯一充分条件。
- 后续比较必须使用相同并发、相同请求数和相同清理方式；不能直接用社区镜像的 11 次串行数据与历史镜像的 c10 压测复现率比较。
- 当前更合理的范围仍包括快照初态、并发恢复时序、guest vCPU/IRQ 状态、Shim reset 交互以及 host KVM/GIC 行为。

## 最终状态

截至 `2026-07-27T10:14:42+08:00`：

- `.90` 仍使用历史镜像 `20260609-222734`。
- `cube-sandbox-cubelet.service` 为 `active/running`。
- CubeAPI 返回 `{"status":"ok","sandboxes":0}`。
- `sandboxes/shims/tasks=0/0/0`。
- 没有压测进程继续运行。

远端完整实验目录：

`/home/lyq/guest-image-create-pressure-20260727-100955`

## 本地证据

- [聚合结果](remote-results/guest-image-create-pressure-20260727-100955/aggregate-summary.json)
- [标准矩阵日志](remote-results/guest-image-create-pressure-20260727-100955/official-matrix-r1/run.log)
- [首次 c10 报告](remote-results/guest-image-create-pressure-20260727-100955/official-matrix-r1/create-c10-n200.json)
- [独立 c10 复验报告](remote-results/guest-image-create-pressure-20260727-100955/repeat-c10-n500/repeat-c10-n500.json)
- [首次 reset 的 Cubelet 证据](remote-results/guest-image-create-pressure-20260727-100955/evidence/matrix-r1-initial-reset-Cubelet.log)
- [独立复验 Cubelet 日志增量](remote-results/guest-image-create-pressure-20260727-100955/evidence/repeat-Cubelet-req.delta.log)
- [最终远端状态](remote-results/guest-image-create-pressure-20260727-100955/evidence/final-state.txt)
- [证据哈希](remote-results/guest-image-create-pressure-20260727-100955/SHA256SUMS)

下一步应在相同 c10/n700 口径下重新测试社区镜像，并对历史镜像的 reset 失败实例采集 Shim/VMM、首个 post-restore IRQ/timer 状态和 guest 侧 idle/IRQ trace。这样才能量化镜像差异，并继续定位并发恢复触发条件。
