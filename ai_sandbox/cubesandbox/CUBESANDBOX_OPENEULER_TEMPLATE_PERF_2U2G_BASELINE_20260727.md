# CubeSandbox openEuler 2U2G Template 并发性能基线

测试时间：2026-07-27  
测试节点：`192.168.25.90`  
Template：`tpl-297f00a33adb43de957bbf90`

## 1. 结论

2U2G Template 已重新完成一轮 `c1/n20`、`c10/n200`、`c20/n300` 和 `c50/n500` 并发创建测试，总计 `1020/1020` 成功。四个档位全部在 attempt 1 通过，没有触发重试，也没有发现 `reset guest`、`guest time`、reset timeout 或 reset failed 特征。

当前需要优化的 `c50/n500` 基线为：

```text
avg     406.85 ms
p95    1302.38 ms
max    1872.08 ms
吞吐    106.97 sandbox/s
```

若目标 avg 为 `170 ms`，需要在当前单轮基线上降低约 `58.2%`。低、中并发性能与此前五轮均值接近，明显的退化仍集中在并发 50 的长尾。

## 2. 测试环境

| 项目 | 配置 |
|---|---|
| Template 规格 | 2 vCPU / 2000 MiB |
| Writable layer | 1 GiB |
| Template 状态 | `READY` |
| 兼容策略 / 状态 | `STRICT / OK` |
| OCI Image | `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` |
| OCI Image digest | `sha256:cc200de2c966fef8f366102a35f5d22a623ae911ea66069a4a77061ed0d5f04e` |
| Guest image | openEuler 24.03 LTS-SP3，版本 `20260609-222734` |
| Guest kernel | `6.6.0-cubesandbox.guest.oe2403sp3` |
| Guest kernel SHA-256 | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| TAP 总数 | 1198 |
| 测试工具 | `cube-bench create-only`，warmup 3 |

每档开始前和结束后均连续通过资源门禁：`sandbox=0`、`shim=0`、`task=0`、`tap_in_use=0` 且 TAP 总数不低于 1000。

## 3. 当前单轮基线

| 并发 | 请求数 | 成功 / 失败 | avg | min | p95 | max | 总耗时 | 单沙箱均摊 | 吞吐 |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 20 / 0 | 44.07 ms | 39.41 ms | 49.34 ms | 50.51 ms | 1.071 s | 53.55 ms | 18.67/s |
| 10 | 200 | 200 / 0 | 57.81 ms | 45.31 ms | 67.95 ms | 77.62 ms | 1.386 s | 6.93 ms | 144.34/s |
| 20 | 300 | 300 / 0 | 87.57 ms | 48.88 ms | 109.15 ms | 125.86 ms | 1.503 s | 5.01 ms | 199.54/s |
| 50 | 500 | 500 / 0 | 406.85 ms | 60.75 ms | 1302.38 ms | 1872.08 ms | 4.674 s | 9.35 ms | 106.97/s |

并发 20 获得本轮最高吞吐 `199.54/s`。并发提高至 50 后，P95 增加到 `1302.38 ms`，吞吐下降到 `106.97/s`，但请求仍全部成功。

## 4. 与此前五轮均值对比

| 并发 | 当前 avg / 历史均值 | avg 变化 | 当前 p95 / 历史均值 | p95 变化 | 当前吞吐 / 历史均值 | 吞吐变化 |
|:---:|---:|---:|---:|---:|---:|---:|
| 1 | 44.07 / 45.28 ms | -2.66% | 49.34 / 53.35 ms | -7.53% | 18.67 / 18.96/s | -1.48% |
| 10 | 57.81 / 56.68 ms | +1.99% | 67.95 / 65.94 ms | +3.05% | 144.34 / 153.77/s | -6.14% |
| 20 | 87.57 / 87.46 ms | +0.13% | 109.15 / 109.17 ms | -0.02% | 199.54 / 187.60/s | +6.36% |
| 50 | 406.85 / 366.74 ms | +10.94% | 1302.38 / 1259.11 ms | +3.44% | 106.97 / 121.89/s | -12.24% |

并发 1、10、20 的 avg 与历史均值偏差均不超过 2.7%。并发 50 的 avg 和吞吐波动明显，说明后续优化与验证不能只依赖单轮结果，应至少使用多轮 `c50/n500` 的均值、P95 和最大值共同判定。

## 5. 最终状态

| 检查项 | 结果 |
|---|---|
| Cubelet / CubeMaster | `active / active` |
| network-agent / CubeAPI | `active / active` |
| CubeAPI health | `status=ok, sandboxes=0` |
| 沙箱 / shim / task | `0 / 0 / 0` |
| TAP 总数 / 在用数 | `1198 / 0` |
| reset/guest-time 扫描 | 0 字节 |
| 本地证据校验 | `SHA256SUMS: OK` |

## 6. 证据索引

- [本轮性能聚合](remote-results/cubesandbox-template-perf-2u2g-baseline-openEuler-20260727-212511/startup-latency/aggregate.json)
- [与此前五轮均值对比](remote-results/cubesandbox-template-perf-2u2g-baseline-openEuler-20260727-212511/historical-comparison.json)
- [重试统计](remote-results/cubesandbox-template-perf-2u2g-baseline-openEuler-20260727-212511/retry-summary.txt)
- [Cubelet reset/timeout 扫描](remote-results/cubesandbox-template-perf-2u2g-baseline-openEuler-20260727-212511/cubelet-reset-timeout-signatures.txt)
- [最终资源状态](remote-results/cubesandbox-template-perf-2u2g-baseline-openEuler-20260727-212511/evidence/final-state.txt)
- [完整校验清单](remote-results/cubesandbox-template-perf-2u2g-baseline-openEuler-20260727-212511/SHA256SUMS)
