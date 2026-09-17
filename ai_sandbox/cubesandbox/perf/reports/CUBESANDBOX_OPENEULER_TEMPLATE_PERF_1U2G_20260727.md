# CubeSandbox openEuler 1U2G Template 并发性能复测

测试时间：2026-07-27  
测试节点：`192.168.25.90`  
测试 Template：`tpl-7fee89b502d54ce08b9046cf`

## 1. 结论

独立构建的 1U2G Template 已通过身份和兼容性检查，并连续完成 5 轮并发创建矩阵。每轮包含 `c1/n20`、`c10/n200`、`c20/n300` 和 `c50/n500`，总计 `5100/5100` 个正式请求成功；20 个档位全部在 attempt 1 通过，没有触发重试。

Cubelet 和 benchmark 日志中均未发现 `reset guest`、`guest time`、reset timeout 或 reset failed 特征。测试完成后沙箱、shim、task 和在用 TAP 均为 0，CubeSandbox 核心服务保持健康。

## 2. Template 与 Guest 身份

| 检查项 | 结果 |
|---|---|
| Template ID | `tpl-7fee89b502d54ce08b9046cf` |
| Template 状态 | `READY` |
| 兼容策略 / 状态 | `STRICT / OK` |
| Template 规格 | 1 vCPU / 2000 MiB |
| Writable layer | 1 GiB |
| 容器镜像 | `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` |
| 容器镜像摘要 | `sha256:cc200de2c966fef8f366102a35f5d22a623ae911ea66069a4a77061ed0d5f04e` |
| Guest image | openEuler 24.03 LTS-SP3，版本 `20260609-222734` |
| Guest kernel | `6.6.0-cubesandbox.guest.oe2403sp3` |
| Guest kernel SHA-256 | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| 沙箱内 `nproc` | `1` |
| TAP 资源 | 1198，门禁要求至少 1000 |

实际沙箱内 `/proc/version` 显示内核由 openEuler GCC `12.3.1-105.oe2403sp3` 编译。沙箱内 `/etc/os-release` 显示 Ubuntu 22.04，是 benchmark 容器 rootfs 的身份，不代表 MicroVM 基础 guest image 或 guest kernel。

构建期间临时设置 `CUBEMASTER_NATIVE_ROOTFS_EXPORT_ENABLED=false`，复用节点上已校验的本地 ARM64 镜像。Template READY 后已撤销该 systemd manager 环境变量并重启 CubeMaster；最终状态为 `<unset>`。

## 3. 测试方法

每个档位使用 `cube-bench` 的 `create-only` 模式和 3 次 warmup。档位开始前和结束后均要求资源状态连续三次满足：

```text
sandbox=0, shim=0, task=0, tap_in_use=0, tap_total>=1000
```

如正式请求没有达到 100% 成功，测试脚本会先清理运行时，再重复该档位直至满足条件。本次所有档位均在第一次执行成功。

## 4. 五轮结果

| 轮次 | 请求数 | 成功 | 失败 | 是否重试 |
|:---:|---:|---:|---:|:---:|
| 1 | 1020 | 1020 | 0 | 否 |
| 2 | 1020 | 1020 | 0 | 否 |
| 3 | 1020 | 1020 | 0 | 否 |
| 4 | 1020 | 1020 | 0 | 否 |
| 5 | 1020 | 1020 | 0 | 否 |

下表中的 `avg`、`p95` 和吞吐为五轮算术平均，括号内为五轮最小值到最大值；`max` 为五轮中观察到的最大单请求延迟。

| 并发 / 每轮请求 | 累计成功 / 失败 | avg 均值（范围） | p95 均值（范围） | max | 吞吐均值（范围） |
|---|---:|---:|---:|---:|---:|
| c1/n20 | 100 / 0 | 53.47 ms（52.67-54.54） | 56.77 ms（56.34-57.32） | 58.20 ms | 16.13/s（15.88-16.33） |
| c10/n200 | 1000 / 0 | 65.75 ms（65.09-66.67） | 75.70 ms（73.66-78.93） | 90.37 ms | 132.80/s（130.49-134.74） |
| c20/n300 | 1500 / 0 | 89.14 ms（86.30-91.56） | 115.86 ms（111.87-121.30） | 137.78 ms | 194.50/s（188.98-198.91） |
| c50/n500 | 2500 / 0 | 229.13 ms（228.66-230.12） | 274.86 ms（270.07-278.50） | 324.63 ms | 197.96/s（197.10-199.03） |

## 5. 与 2U2G 五轮结果对比

两组结果来自同一节点、相同镜像、相同 guest image/kernel 和相同并发矩阵，均为连续五轮。正数表示 1U2G 指标高于 2U2G，负数表示低于 2U2G。

| 并发 | avg：1U / 2U | avg 变化 | p95：1U / 2U | p95 变化 | 吞吐：1U / 2U | 吞吐变化 |
|:---:|---:|---:|---:|---:|---:|---:|
| 1 | 53.47 / 45.28 ms | +18.11% | 56.77 / 53.35 ms | +6.41% | 16.13 / 18.96/s | -14.92% |
| 10 | 65.75 / 56.68 ms | +15.99% | 75.70 / 65.94 ms | +14.81% | 132.80 / 153.77/s | -13.64% |
| 20 | 89.14 / 87.46 ms | +1.92% | 115.86 / 109.17 ms | +6.13% | 194.50 / 187.60/s | +3.68% |
| 50 | 229.13 / 366.74 ms | -37.52% | 274.86 / 1259.11 ms | -78.17% | 197.96 / 121.89/s | +62.41% |

低并发时 2U2G 的平均延迟和吞吐更好。并发 50 时，1U2G 的尾延迟明显更稳定，五轮吞吐也更高。该结果说明当前 2U2G 路径在高并发下存在更明显的调度或恢复尾延迟，但本次是顺序 A/B 测试，不能仅凭该表断言减少 vCPU 必然提升高并发性能；若要确认因果，应进行交替轮次并同时采集 host CPU、NUMA、run queue 和 KVM 线程调度数据。

## 6. 最终状态

| 检查项 | 最终结果 |
|---|---|
| Cubelet / CubeMaster | `active / active` |
| network-agent / CubeAPI | `active / active` |
| CubeAPI health | `status=ok, sandboxes=0` |
| 沙箱 / shim / task | `0 / 0 / 0` |
| TAP 总数 / 在用数 | `1198 / 0` |
| reset/guest-time 扫描 | 0 字节 |
| 本地证据校验 | `SHA256SUMS: OK` |

## 7. 证据索引

- [Template 构建结果](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/evidence/template-final.json)
- [Template 完整运行时元数据](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/evidence/template-runtime.json)
- [实际沙箱 Guest kernel 身份](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/evidence/kernel-identity/guest-identity.txt)
- [五轮性能聚合](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/five-round-aggregate.json)
- [五轮逐轮成功率](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/rounds-summary.tsv)
- [1U2G 与 2U2G 对比](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/one-u-vs-two-u-comparison.json)
- [Cubelet reset/timeout 扫描](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/cubelet-reset-timeout-signatures-all.txt)
- [最终资源状态](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/evidence/final-state.txt)
- [完整文件校验清单](remote-results/cubesandbox-template-perf-1u2g-openEuler-20260727-202321/SHA256SUMS)
