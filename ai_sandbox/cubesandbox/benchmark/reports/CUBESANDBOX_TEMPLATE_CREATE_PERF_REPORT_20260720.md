# CubeSandbox v0.5.1 ARM64 Template 创建性能测试报告

测试时间：2026-07-20 14:25:59 至 14:32:54（Asia/Shanghai）

## 结论

已按官方 Template 创建测试设计完成四个并发档位，并在每轮结束后执行资源整理。

- 总请求：1020
- 成功：979
- 失败：41
- 总成功率：95.98%
- 41 个失败全部为约 30 秒后返回 `create HTTP 408`
- 每个失败均留下一个异常 CubeShim，四轮共回收 41 个
- 每轮整理后均达到 `Sandbox=0`、`CubeShim=0`、runtime task=0

因此，本轮获得了可复现的性能数据，但没有达到官方报告各档 100% 成功率的前提，不能作为正常状态下的正式性能验收结果。

## 测试环境

| 项目 | 值 |
| --- | --- |
| 主机 | `192.168.25.90` |
| 架构 | ARM64 |
| Host 内核 | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-8394b32f` |
| CubeSandbox | `v0.5.1-arm64` |
| CubeSandbox commit | `a164417f497234a0d787cb328b0ae96480b1569b` |
| Template | `tpl-80e1fa6aefa14f80854a23d0` |
| Template 状态 | `READY`, replica `1/1 READY` |
| Template 规格 | `cpu=2000m,mem=2000Mi` |
| 镜像 | `cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code:latest` |
| 镜像 digest | `sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d` |
| Writable layer | 1G |
| Probe | HTTP `49999/health` |
| 暴露端口 | 49999、49983 |
| Sandbox CIDR | `10.100.0.0/18`，与宿主机网段不重叠 |
| 存储 | NVMe XFS，挂载 `/data/cubelet` |

## 测试设计

测试使用官方 `cube-bench` 的 `create-only` 模式，各档均执行 3 次 warm-up，warm-up 不计入统计：

```text
c=1,  n=20,  w=3
c=10, n=200, w=3
c=20, n=300, w=3
c=50, n=500, w=3
```

每轮流程：

1. 验证 Sandbox、CubeShim、runtime task 均为 0。
2. 执行对应 `cube-bench` 测试并保存 JSON 和原始日志。
3. 通过 CubeAPI 删除本轮 Sandbox。
4. 检测 API 删除后仍残留的 CubeShim 和 task。
5. 如有残留，在确认 Sandbox 已为 0 后停止 Cubelet，只回收匹配的 CubeShim，再启动 Cubelet。
6. 再次验证 Sandbox、CubeShim、runtime task 均为 0，才进入下一轮。

## 测试结果

`avg` 和 `p95` 仅统计成功创建的请求；整轮耗时和吞吐包含失败请求的约 30 秒超时，因此能反映用户实际观察到的整轮结果。

| 并发 | 请求 | 成功/失败 | 成功率 | avg | p95 | 整轮耗时 | 有效吞吐 | 回收异常 Shim |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 20 | 19 / 1 | 95.00% | 50.246 ms | 104.825 ms | 31.184 s | 0.609/s | 1 |
| 10 | 200 | 190 / 10 | 95.00% | 68.194 ms | 142.570 ms | 32.377 s | 5.868/s | 10 |
| 20 | 300 | 285 / 15 | 95.00% | 120.425 ms | 647.424 ms | 32.602 s | 8.742/s | 15 |
| 50 | 500 | 485 / 15 | 97.00% | 158.084 ms | 277.884 ms | 31.705 s | 15.297/s | 15 |
| **总计** | **1020** | **979 / 41** | **95.98%** | - | - | - | - | **41** |

全部 41 个失败的外层错误一致：

```text
create HTTP 408:
```

失败请求耗时约 30001 至 30002 ms。由于失败请求不进入 `create.avg/p95` 的成功样本统计，不能单独依据这些延迟值判断系统整体性能正常。

## 官方数据对比

官方 2026-06-01 报告在相同 2 vCPU / 2 GiB Sandbox 设计下公布的数据如下，且明确说明所有档位成功率均为 100%。

| 并发 | 官方 avg | 官方 p95 | 官方吞吐 | 本机成功率 | 本机有效吞吐 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 47.8 ms | 57.4 ms | 17.9/s | 95.00% | 0.609/s |
| 10 | 88.7 ms | 116.9 ms | 101.4/s | 95.00% | 5.868/s |
| 20 | 98.1 ms | 175.8 ms | 180.9/s | 95.00% | 8.742/s |
| 50 | 276.1 ms | 508.4 ms | 147.6/s | 97.00% | 15.297/s |

本机吞吐明显偏低的直接原因是每档都有 30 秒超时请求，整轮 wall time 被拖到约 32 秒。成功请求自身仍能在数十到数百毫秒完成，但这不能抵消 3% 至 5% 的创建失败。

## 底层故障证据

按每轮 API 清理后仍残留的 CubeShim 提取了 41 个实际失败 Sandbox ID：

- 41 个失败 ID
- 40 条 `destroy sandbox failed:ttrpc err: Receive packet timeout`
- 107 条 VMM `Task/State` 或 `Task/Kill got error timed out`
- 本轮没有出现字面量 `reset guest time failed`

这说明本轮外层 408 对应 Guest/ttrpc 不再响应和高 CPU CubeShim 残留。它与先前故障属于同一恢复后 Guest 无响应现象，但本轮证据不足以把所有失败直接表述为 `reset guest time failed`。

## 每轮资源整理

| 轮次 | 清理前异常 Shim | 清理后 Sandbox | 清理后 Shim | 清理后 task |
| --- | ---: | ---: | ---: | ---: |
| c1/n20 | 1 | 0 | 0 | 0 |
| c10/n200 | 10 | 0 | 0 | 0 |
| c20/n300 | 15 | 0 | 0 | 0 |
| c50/n500 | 15 | 0 | 0 | 0 |

清理日志中的部分 DELETE 404/408 是 API 列表与异步删除之间的竞态；runner 会继续轮询并以最终三项资源计数为准。四轮都在清理完成后才启动下一轮。

## 最终状态

测试结束后的独立复核结果：

- `cube-sandbox-control.target`: active
- `cube-sandbox-cubelet.service`: active
- failed systemd units: 0
- CubeAPI: `{"status":"ok","sandboxes":0}`
- Sandbox: 0
- CubeShim: 0
- runtime task: 0
- Template: `READY`, replica `1/1 READY`

## 证据索引

- `template-create-perf/aggregate.json`: 四档聚合结果
- `template-create-perf/create-c*-n*.json`: 每档原始 `cube-bench` JSON
- `template-create-perf/create-c*-n*.log`: 每档原始命令输出
- `template-create-perf/create-c*-post.before.txt`: API 清理后、强制恢复前的残留计数
- `template-create-perf/create-c*-post.after.txt`: 每轮最终清理计数
- `template-create-perf/create-c*-post.recovered-shim-pids.txt`: 实际回收的 Shim PID
- `template-create-perf/failure-evidence/failed-sandbox-ids.txt`: 41 个失败 Sandbox ID
- `template-create-perf/failure-evidence/CubeShim-failed.log`: 失败 ID 对应 CubeShim 日志
- `template-create-perf/failure-evidence/CubeVmm-failed.log`: 失败 ID 对应 VMM 日志
- `template-create-perf/failure-evidence/Cubelet-failed.log`: 失败 ID 对应 Cubelet 日志
- `template-create-perf/SHA256SUMS-ALL`: 全部远端证据文件校验值

聚合结果 SHA256：

```text
f4a1f67478a8eae0335a9e4e58831fbb092c0238dacc09c01d9706b0586ae014  aggregate.json
```
