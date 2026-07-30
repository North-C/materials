# CubeSandbox 社区 guest image 切换、回退与 2U2G 复测

测试时间：2026-07-27  
测试节点：`192.168.25.90`

## 1. 结论

社区初始 `cube-guest-image` 已完成切换和多次实际创建验证，但稳定复现 `reset guest time failed`：前置身份验证失败 1 次；随后两轮完整 `c1/n20` 正式尝试共 `40` 个请求，仅成功 `5` 个、失败 `35` 个。两轮连同 warmup 在 CubeShim 文件日志中记录了 `40` 次 reset 超时，无法继续作为有效性能测试环境。

按预定条件，guest image 已回退到自编译 openEuler 24.03 LTS-SP3。回退后重新执行 `c1/n20`、`c10/n200`、`c20/n300`、`c50/n500` 四档测试，全部在 attempt 1 通过，总计 `1020/1020` 成功，真实文件日志中没有发现 reset 超时、RCU stall 或 timer handling issue。

回退后的 `c50/n500` 结果为：

```text
avg     317.08 ms
p95    1264.86 ms
max    1563.20 ms
吞吐    133.27 sandbox/s
```

相比上一轮 2U2G 基线，`c50/n500` 的 avg 降低 `22.07%`、吞吐提高 `24.59%`；距离 `170 ms` avg 目标仍需再降低约 `46.39%`。

## 2. 固定测试条件

| 项目 | 配置 |
|---|---|
| OCI Image | `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` |
| OCI digest | `sha256:cc200de2c966fef8f366102a35f5d22a623ae911ea66069a4a77061ed0d5f04e` |
| Template | `tpl-297f00a33adb43de957bbf90` |
| Template 规格 | 2 vCPU / 2000 MiB |
| Writable layer | 1 GiB |
| Template 状态 | `READY` |
| 兼容策略 / 状态 | `STRICT / OK` |
| Guest kernel | `6.6.0-cubesandbox.guest.oe2403sp3` |
| Guest kernel SHA-256 | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| Host kernel | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` |
| TAP 资源 | 总数 1198；每档要求至少 1000 个可用 |
| 测试工具 | `cube-bench create-only`，warmup 3 |

每档测试前后均要求连续通过资源门禁：`sandbox=0`、`shim=0`、`task=0`、`tap_in_use=0`，且 Cubelet、network-agent 和健康检查正常。

## 3. 社区镜像复测

社区镜像实际为 TencentOS Server 4，并非 openEuler 用户态：

| 项目 | 值 |
|---|---|
| Guest OS | TencentOS Server 4 |
| Image version | `v0.5.1` |
| Agent version | `v0.5.1` |
| Image SHA-256 | `05890a04f1aab258abda1c400bf00fe7a2f217d21f27b7a807c2d07920cdfd67` |
| Guest kernel | 新编译的 openEuler guest kernel，SHA `c5515719...976e` |

前置身份验证的首个实际创建即返回 HTTP 500，CubeShim 明确记录 `Create sandbox failed:reset guest time failed`，同时 VMM 日志出现 RCU stall 和 `Possible timer handling issue on cpu=1`。

| 尝试 | 并发 / 请求 | 成功 | 失败 | 成功率 | 仅成功请求 avg | 结论 |
|:---:|:---:|---:|---:|---:|---:|---|
| 1 | 1 / 20 | 4 | 16 | 20% | 51.87 ms | 失败，清理 18 个无 task shim |
| 2 | 1 / 20 | 1 | 19 | 5% | 48.97 ms | 失败，清理 22 个无 task shim |
| 合计 | 1 / 40 | 5 | 35 | 12.5% | 不采用 | 两轮均无法满足测试条件 |

两轮中的低 avg 只来自少数成功请求，且总耗时分别为 `144.86 s` 和 `176.72 s`，不能与全成功性能基线直接比较。两轮结束后资源已清理为 `sandbox/shim/task = 0/0/0`、`TAP = 1198/0`，再执行镜像回退。

即使仅做成功样本的删失统计，也没有观察到时延优化：5 个成功请求按两轮样本数加权后的
avg 约为 `51.29 ms`，而回退 openEuler 后同档 `c1/n20` 的完整成功集合 avg 为
`44.02 ms`。社区镜像的成功样本仍慢约 `16.5%`。由于社区镜像仅 `5/40` 成功，失败请求
还分别占用了 `144.86 s` 和 `176.72 s` 的整轮时间，因此不能把少数成功请求的约 50ms
解释为有效性能收益。

社区镜像测试副本保留在远端：

```text
/usr/local/services/cubetoolbox/cube-image.community-v0.5.1-tested-20260727-214700
```

## 4. 回退后的 openEuler 基线

回退后的活动 guest image：

| 项目 | 值 |
|---|---|
| Guest OS | openEuler 24.03 LTS-SP3 |
| Image version | `20260609-222734` |
| Agent version | `v0.5.1` |
| Image SHA-256 | `1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da` |

| 并发 | 请求数 | 成功 / 失败 | avg | min | p95 | max | 总耗时 | 单沙箱均摊 | 吞吐 |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 20 / 0 | 44.02 ms | 39.16 ms | 48.32 ms | 52.28 ms | 1.119 s | 55.96 ms | 17.87/s |
| 10 | 200 | 200 / 0 | 67.89 ms | 46.58 ms | 116.08 ms | 143.11 ms | 1.530 s | 7.65 ms | 130.71/s |
| 20 | 300 | 300 / 0 | 87.73 ms | 50.96 ms | 110.44 ms | 142.21 ms | 1.518 s | 5.06 ms | 197.65/s |
| 50 | 500 | 500 / 0 | 317.08 ms | 75.80 ms | 1264.86 ms | 1563.20 ms | 3.752 s | 7.50 ms | 133.27/s |

## 5. 与上一轮 openEuler 基线对比

| 并发 | avg：本轮 / 上轮 | avg 变化 | p95：本轮 / 上轮 | p95 变化 | 吞吐：本轮 / 上轮 | 吞吐变化 |
|:---:|---:|---:|---:|---:|---:|---:|
| 1 | 44.02 / 44.07 ms | -0.12% | 48.32 / 49.34 ms | -2.06% | 17.87 / 18.67/s | -4.28% |
| 10 | 67.89 / 57.81 ms | +17.44% | 116.08 / 67.95 ms | +70.83% | 130.71 / 144.34/s | -9.44% |
| 20 | 87.73 / 87.57 ms | +0.18% | 110.44 / 109.15 ms | +1.18% | 197.65 / 199.54/s | -0.95% |
| 50 | 317.08 / 406.85 ms | -22.07% | 1264.86 / 1302.38 ms | -2.88% | 133.27 / 106.97/s | +24.59% |

`c10/n200` 的 P95 本轮波动较大，而 `c50/n500` 明显改善。由于这里只是单轮对比，后续评估 170 ms 优化目标时应使用多轮 `c50/n500` 均值与 P95，而不是选取单轮最优值。

## 6. 最终状态

| 检查项 | 结果 |
|---|---|
| 活动 guest image | openEuler，版本 `20260609-222734` |
| Cubelet / network-agent | `active / active` |
| 沙箱 / shim / task | `0 / 0 / 0` |
| TAP 总数 / 在用数 | `1198 / 0` |
| openEuler 正式测试 reset 超时 | 0 |
| VMM RCU stall / timer issue | `0 / 0` |
| 测试总成功数 | `1020 / 1020` |

## 7. 证据索引

- [社区镜像两轮聚合](remote-results/cubesandbox-template-perf-2u2g-community-image-openEuler-kernel-20260727-213225/benchmark/evidence/community-attempts-aggregate.json)
- [社区镜像 reset 计数](remote-results/cubesandbox-template-perf-2u2g-community-image-openEuler-kernel-20260727-213225/benchmark/evidence/community-failure-signature-counts.txt)
- [前置身份验证失败签名](remote-results/cubesandbox-template-perf-2u2g-community-image-openEuler-kernel-20260727-213225/evidence/identity-attempt-1-signatures.txt)
- [镜像回退证据](remote-results/cubesandbox-template-perf-2u2g-community-image-openEuler-kernel-20260727-213225/evidence/rollback-to-openEuler.txt)
- [openEuler 四档聚合](remote-results/cubesandbox-template-perf-2u2g-openEuler-after-community-rollback-20260727-214800/benchmark/startup-latency/aggregate.json)
- [openEuler 文件日志扫描](remote-results/cubesandbox-template-perf-2u2g-openEuler-after-community-rollback-20260727-214800/benchmark/evidence/openEuler-failure-signature-counts.txt)
- [openEuler guest os-release](remote-results/cubesandbox-template-perf-2u2g-openEuler-after-community-rollback-20260727-214800/evidence/active-guest-os-release.txt)
- [最终资源状态](remote-results/cubesandbox-template-perf-2u2g-openEuler-after-community-rollback-20260727-214800/benchmark/evidence/final-state.txt)
- [openEuler 结果 SHA256 清单](remote-results/cubesandbox-template-perf-2u2g-openEuler-after-community-rollback-20260727-214800/SHA256SUMS)
