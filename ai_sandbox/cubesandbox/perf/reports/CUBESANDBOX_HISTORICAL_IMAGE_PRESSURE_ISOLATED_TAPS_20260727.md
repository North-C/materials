# CubeSandbox 历史镜像严格 TAP 隔离压力复验

日期：2026-07-27（Asia/Shanghai）  
目标机：`root@192.168.25.90`  
Template：`tpl-abold-83570639543444b0`

## 结论

在每轮开始前清空 Sandbox、shim、task，并确认健康 TAP 池不少于配置值 500 后，两次完整四轮复验都在历史自编译 guest 镜像上复现了 `reset guest time failed`。

第一次为 `1019/1020`，复现 1 次；第二次为 `1012/1020`，复现 8 次。两次合计 `2031/2040` 成功，9 次错误全部为 guest reset ttrpc 接收超时，并分别遗留 1 个 shim；所有残留均已回收。两次测试均未出现 `tap fd unavailable`。

9 个失败请求分配对应 TAP 时，健康池余量最低仍有 186 个，`abnormal=0`、`quarantined=0`。因此，reset 复现不能归因于轮间未清理资源或 TAP 不足；历史镜像没有消除 reset 故障。

## 测试不变量

- guest 镜像版本：`20260609-222734`
- guest 镜像 SHA-256：`1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da`
- Cubelet SHA-256：`88e5e224fdfb9b1fca5d4722cfa273c49aa7048dffdb28fb88adbc44ddee4c96`
- cube-shim SHA-256：`4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d`
- guest kernel SHA-256：`7c227b2ba09988bb4380a95658d1ebe6e17e2f95fac60ed6eb6e42f4a676d8e5`
- Host kernel：`6.6.0-132.0.0.111.oe2403sp3.aarch64`
- Template：`READY`，`guest_image_version=20260609-222734`，`compat_status=OK`
- Cubelet 配置：`tap_init_num=500`

## 资源门禁

每轮执行以下流程：

1. 删除 API 中的全部 Sandbox。
2. 检查 shim 和 containerd task；发现残留时停启 Cubelet 并定向回收。
3. 每轮开始前重启 network-agent，等待健康接口恢复。
4. 连续 3 次确认 TAP 链路数与健康池数量一致、均不少于 500，且异常池和隔离池均为 0。
5. 压测结束后再次清理运行时，并通过相同 TAP 门禁，才进入下一轮。

第一次复验四轮开始前均为：

```text
sandboxes=0
shims=0
tasks=0
tap_links=502
tap_pool=502
abnormal=0
quarantined=0
```

第一次前三轮结束后恢复到相同状态。`c50/n500` 结束后 network-agent 补建了 1 个健康 TAP，链路与健康池均变为 503。第二次复验的每轮开始和结束均为 `tap_links=503`、`tap_pool=503`、`abnormal=0`、`quarantined=0`，且 Sandbox、shim、task 均为 0。

## 压测结果

每档使用 create-only 模式，3 次预热不计入正式请求。

第一次严格复验：

| Case | 成功 | 错误 | reset 错误 | TAP FD 错误 | 回收 shim | 吞吐 | create P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `c1/n20` | 20/20 | 0 | 0 | 0 | 0 | 17.34 QPS | 50.49 ms |
| `c10/n200` | 200/200 | 0 | 0 | 0 | 0 | 87.03 QPS | 188.96 ms |
| `c20/n300` | 299/300 | 1 | 1 | 0 | 1 | 25.09 QPS | 621.19 ms |
| `c50/n500` | 500/500 | 0 | 0 | 0 | 0 | 27.93 QPS | 3835.56 ms |

聚合：`1019/1020` 成功，成功率 `99.902%`；`reset guest time failed=1`，`tap fd unavailable=0`。

第二次严格复验：

| Case | 成功 | 错误 | reset 错误 | TAP FD 错误 | 回收 shim | 吞吐 | create P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `c1/n20` | 20/20 | 0 | 0 | 0 | 0 | 17.61 QPS | 53.14 ms |
| `c10/n200` | 197/200 | 3 | 3 | 0 | 3 | 21.81 QPS | 112.75 ms |
| `c20/n300` | 299/300 | 1 | 1 | 0 | 1 | 29.45 QPS | 619.47 ms |
| `c50/n500` | 496/500 | 4 | 4 | 0 | 4 | 27.38 QPS | 3706.20 ms |

聚合：`1012/1020` 成功，成功率 `99.216%`；`reset guest time failed=8`，`tap fd unavailable=0`。

两次合并：

| Case | 成功 | 错误 | reset 错误 | TAP FD 错误 | 回收 shim |
|---|---:|---:|---:|---:|---:|
| `c1/n20` | 40/40 | 0 | 0 | 0 | 0 |
| `c10/n200` | 397/400 | 3 | 3 | 0 | 3 |
| `c20/n300` | 598/600 | 2 | 2 | 0 | 2 |
| `c50/n500` | 996/1000 | 4 | 4 | 0 | 4 |

合计 `2031/2040` 成功，成功率 `99.559%`；reset 复现率为 `9/2040`，约 `0.441%`。

## 失败证据

- Request ID：`aa2af8e8-3331-46a7-a594-2fb94abe81d8`
- Sandbox ID：`c444a1ae4a544d41934128e609189197`
- Sandbox IP / TAP：`10.100.0.54` / `z10.100.0.54`
- TAP 分配时间：`2026-07-27T10:37:03.44264433+08:00`
- reset 报错时间：`2026-07-27T10:37:11.98722755+08:00`

错误链：

```text
failed to create shim task
Create sandbox failed: reset guest time failed
ttrpc err: Receive packet timeout Elapsed(())
failed to shutdown shim task and the shim might be leaked
context deadline exceeded
```

对应 TAP 分配时的 network-agent 状态：

```text
network-agent tap dequeued from pool: name=z10.100.0.54 ifindex=74
pool=238 abnormal=0 quarantined=0
```

该 TAP 于 `10:37:12.369` 回到健康池。测试清理回收残留 shim PID `1825355` 后，Sandbox、shim、task 均归零，TAP 池恢复为 502。

第二次复验的 8 个失败请求分布为：`c10/n200` 3 个、`c20/n300` 1 个、`c50/n500` 4 个。对应 TAP 出池时的健康池余量依次为 449、408、386、307、453、308、245、186，异常池和隔离池始终为 0；各轮清理后健康池均恢复为 503。

## 最终状态

截至第二次复验结束后的 `2026-07-27T10:59:01+08:00`：

- Cubelet 与 network-agent 均为 `active`，健康接口正常。
- `sandboxes/shims/tasks=0/0/0`。
- TAP 链路与健康池均为 503，`abnormal=0`、`quarantined=0`。
- 压测 runner 与 cube-bench 进程均为 0。
- systemd failed units 为 0。

远端完整目录：

`/home/lyq/guest-image-create-pressure-isolated-taps-20260727-103143`

`/home/lyq/guest-image-create-pressure-isolated-taps-20260727-104820`

## 本地证据

- [聚合结果](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/isolated-tap-matrix/aggregate.json)
- [矩阵运行日志](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/isolated-tap-matrix/run.log)
- [c20 结果](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/isolated-tap-matrix/create-c20-n300.json)
- [c20 Cubelet 日志增量](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/isolated-tap-matrix/create-c20-n300.Cubelet-req.delta.log)
- [c20 network-agent 日志增量](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/isolated-tap-matrix/create-c20-n300.network-agent.delta.log)
- [c20 前置 TAP 门禁](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/isolated-tap-matrix/create-c20-n300-pre-after-tap-reset.resources.txt)
- [c20 后置 TAP 门禁](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/isolated-tap-matrix/create-c20-n300-post-after-tap-gate.resources.txt)
- [最终状态](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/evidence/final-state.txt)
- [完整证据哈希](remote-results/guest-image-create-pressure-isolated-taps-20260727-103143/FINAL_SHA256SUMS)
- [第二次聚合结果](remote-results/guest-image-create-pressure-isolated-taps-20260727-104820/isolated-tap-matrix/aggregate.json)
- [第二次矩阵运行日志](remote-results/guest-image-create-pressure-isolated-taps-20260727-104820/isolated-tap-matrix/run.log)
- [第二次 reset 请求清单](remote-results/guest-image-create-pressure-isolated-taps-20260727-104820/evidence/reset-failures.tsv)
- [第二次失败 TAP 关联记录](remote-results/guest-image-create-pressure-isolated-taps-20260727-104820/evidence/reset-tap-correlations.tsv)
- [第二次最终状态](remote-results/guest-image-create-pressure-isolated-taps-20260727-104820/evidence/final-state.txt)
- [第二次完整证据哈希](remote-results/guest-image-create-pressure-isolated-taps-20260727-104820/FINAL_SHA256SUMS)
- [可复用运行器](scripts/run_cubesandbox_create_pressure_isolated_taps.sh)
