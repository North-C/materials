# CubeSandbox v0.5.1 ARM64 Template 创建性能复测报告

测试时间：2026-07-20 15:08:02 至 15:13:28（Asia/Shanghai）

## 结论

远端服务器重启后，CubeSandbox 健康检查正常，因此重新执行了官方设计的四档 Template 创建测试。复测结果如下：

- 总请求：1020
- 成功：980
- 失败：40
- 总成功率：96.08%
- 40 个失败全部为约 30 秒后返回 `create HTTP 408`
- 40 个失败对应 40 个 API 清理后仍残留的 CubeShim
- 每轮资源整理后均为 `Sandbox=0`、`CubeShim=0`、runtime task=0
- 测试结束后 CubeSandbox 服务、API、Template 和资源状态均正常

本次复测比上一轮仅多成功 1 次（980 对 979），故障模式和故障比例没有实质变化。服务本身可以启动并通过健康检查，但 Template 创建路径仍无法达到官方基准的 100% 成功率，本次数据不能作为正常状态下的正式性能验收结果。

## 测试前健康门禁

服务器于 2026-07-20 15:04:29 完成重启。等待启动流程完成后，于 15:07:38 进行独立健康检查：

- 安装目录 `quickcheck.sh`：`OK`
- `cube-sandbox-control.target`：active
- `cube-sandbox-cubelet.service`：active
- CubeSandbox failed units：0
- CubeAPI：`{"status":"ok","sandboxes":0}`
- Sandbox / CubeShim / runtime task：0 / 0 / 0
- Template：`READY`，replica `1/1 READY`
- 高 CPU Cube 进程：0

宿主机存在一个与 CubeSandbox 无关的 `NetworkManager-wait-online.service` failed 状态；NetworkManager 本身 active，CubeSandbox 的网络、API 和全部 quickcheck 项均正常。

## 测试环境

| 项目 | 值 |
| --- | --- |
| 主机 | `192.168.25.90` |
| 架构 | ARM64 |
| Host 内核 | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-8394b32f` |
| CubeSandbox | `v0.5.1-arm64` |
| CubeSandbox commit | `a164417f497234a0d787cb328b0ae96480b1569b` |
| Template | `tpl-80e1fa6aefa14f80854a23d0` |
| Template 状态 | `READY`，replica `1/1 READY` |
| Template guest/agent | `v0.5.1` / `v0.5.1` |
| Template 规格 | `cpu=2000m,mem=2000Mi` |
| 镜像 | `cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code:latest` |
| 镜像 digest | `sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d` |
| Writable layer | 1G |
| Probe | HTTP `49999/health` |
| Sandbox CIDR | `10.100.0.0/18`，与宿主机网段不重叠 |
| 存储 | NVMe XFS，挂载 `/data/cubelet` |

## 测试设计

使用官方 `cube-bench` 的 `create-only` 模式，每档执行 3 次 warm-up，warm-up 不计入统计：

```text
c=1,  n=20,  w=3
c=10, n=200, w=3
c=20, n=300, w=3
c=50, n=500, w=3
```

每轮开始前确认 Sandbox、CubeShim、runtime task 均为 0。每轮完成后通过 CubeAPI 删除 Sandbox；若仍有残留 Shim，则停止 Cubelet，仅回收精确匹配的 CubeShim PID，再启动 Cubelet。三项资源全部归零后才进入下一轮。

## 复测结果

`avg` 和 `p95` 仅统计成功创建的请求；整轮耗时和有效吞吐包含失败请求的约 30 秒超时。

| 并发 | 请求 | 成功/失败 | 成功率 | avg | p95 | 整轮耗时 | 有效吞吐 | 回收异常 Shim |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 20 | 20 / 0 | 100.00% | 50.301 ms | 54.396 ms | 1.293 s | 15.470/s | 0 |
| 10 | 200 | 191 / 9 | 95.50% | 59.348 ms | 71.901 ms | 32.424 s | 5.891/s | 9 |
| 20 | 300 | 286 / 14 | 95.33% | 74.889 ms | 121.650 ms | 31.808 s | 8.991/s | 14 |
| 50 | 500 | 483 / 17 | 96.60% | 135.559 ms | 240.124 ms | 31.647 s | 15.262/s | 17 |
| **总计** | **1020** | **980 / 40** | **96.08%** | - | - | - | - | **40** |

全部失败的外层错误一致：

```text
create HTTP 408:
```

失败请求耗时约 30000 至 30002 ms。并发 1 本次未遇到失败，因此该档恢复到约 50 ms 的正常创建耗时；其余三档仍被 30 秒失败请求主导整轮吞吐。

## 与上一轮对比

| 并发 | 上轮成功/请求 | 本轮成功/请求 | 上轮成功率 | 本轮成功率 | 上轮异常 Shim | 本轮异常 Shim |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 19 / 20 | 20 / 20 | 95.00% | 100.00% | 1 | 0 |
| 10 | 190 / 200 | 191 / 200 | 95.00% | 95.50% | 10 | 9 |
| 20 | 285 / 300 | 286 / 300 | 95.00% | 95.33% | 15 | 14 |
| 50 | 485 / 500 | 483 / 500 | 97.00% | 96.60% | 15 | 17 |
| **总计** | **979 / 1020** | **980 / 1020** | **95.98%** | **96.08%** | **41** | **40** |

重启前后总成功率只相差 0.10 个百分点。两轮合计 2040 次请求中有 81 次 HTTP 408，并回收 81 个对应残留 Shim，说明问题具有稳定可复现性，并非一次性的脏资源状态。

## 与官方数据对比

官方报告在相同 2 vCPU / 2 GiB Sandbox 测试设计下公布的数据如下，且各档成功率均为 100%。

| 并发 | 官方 avg | 官方 p95 | 官方吞吐 | 本机成功率 | 本机有效吞吐 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 47.8 ms | 57.4 ms | 17.9/s | 100.00% | 15.470/s |
| 10 | 88.7 ms | 116.9 ms | 101.4/s | 95.50% | 5.891/s |
| 20 | 98.1 ms | 175.8 ms | 180.9/s | 95.33% | 8.991/s |
| 50 | 276.1 ms | 508.4 ms | 147.6/s | 96.60% | 15.262/s |

成功请求自身的 avg/p95 并不差，但 `cube-bench` 的延迟统计排除了失败请求。由于并发 10、20、50 各有 3.4% 至 4.67% 的创建失败，不能用成功样本延迟证明整体性能达标。

## 每轮资源整理

| 轮次 | API 清理后异常 Shim | 清理后 Sandbox | 清理后 Shim | 清理后 task |
| --- | ---: | ---: | ---: | ---: |
| c1/n20 | 0 | 0 | 0 | 0 |
| c10/n200 | 9 | 0 | 0 | 0 |
| c20/n300 | 14 | 0 | 0 | 0 |
| c50/n500 | 17 | 0 | 0 | 0 |

清理期间的部分 DELETE 404/408 是 API 列表与异步删除之间的竞态。runner 会继续轮询，并以最终 Sandbox、Shim、task 三项计数为准。

## 最终状态

2026-07-20 15:14:45 独立终检：

- 安装目录 `quickcheck.sh`：`OK`
- `cube-sandbox-control.target`：active
- `cube-sandbox-cubelet.service`：active
- CubeSandbox failed units：0
- CubeAPI：`{"status":"ok","sandboxes":0}`
- Sandbox：0
- CubeShim：0
- runtime task：0
- 高 CPU Cube 进程：0
- Template：`READY`，replica `1/1 READY`，guest/agent 均为 `v0.5.1`

## 证据索引

- `template-create-perf/aggregate.json`：四档聚合结果
- `template-create-perf/create-c*-n*.json`：每档原始 `cube-bench` JSON
- `template-create-perf/create-c*-n*.log`：每档原始命令输出
- `template-create-perf/create-c*-post.before.txt`：API 清理后、Shim 恢复前的残留计数
- `template-create-perf/create-c*-post.after.txt`：每轮最终清理计数
- `template-create-perf/create-c*-post.processes-before-recovery.txt`：恢复前进程快照，可提取实际失败 Sandbox ID
- `template-create-perf/create-c*-post.recovered-shim-pids.txt`：实际回收的 Shim PID
- `template-create-perf/SHA256SUMS`：测试生成时的证据文件校验值

聚合结果 SHA256：

```text
04b1bd6c398c119d0498ba2b90a1b8f7b0e88618d972267c584f9b0e8b114913  aggregate.json
```
