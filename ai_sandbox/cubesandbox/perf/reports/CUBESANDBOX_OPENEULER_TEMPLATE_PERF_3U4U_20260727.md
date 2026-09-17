# CubeSandbox openEuler 3U2G / 4U2G Template 并发性能测试

测试时间：2026-07-27  
测试节点：`192.168.25.90`

## 1. 结论

3U2G 和 4U2G 各完成一轮完整 Template 并发创建矩阵，每轮均包含 `c1/n20`、`c10/n200`、`c20/n300` 和 `c50/n500`：

| 场景 | 请求数 | 成功 | 失败 | 重试 |
|---|---:|---:|---:|---:|
| 3U2G | 1020 | 1020 | 0 | 0 |
| 4U2G | 1020 | 1020 | 0 | 0 |
| 合计 | 2040 | 2040 | 0 | 0 |

8 个档位全部在 attempt 1 通过。Cubelet 和 benchmark 日志均未发现 `reset guest`、`guest time`、reset timeout 或 reset failed 特征。

## 2. Template 与 Guest 身份

| 检查项 | 3U2G | 4U2G |
|---|---|---|
| Template ID | `tpl-a85eaaca79c745d79709f80c` | `tpl-b29eda9afc4b4fd6b89f1c6f` |
| Template 状态 | `READY` | `READY` |
| 兼容策略 / 状态 | `STRICT / OK` | `STRICT / OK` |
| Template 规格 | 3000m / 2000 MiB | 4000m / 2000 MiB |
| 实际沙箱 `nproc` | 3 | 4 |
| Writable layer | 1 GiB | 1 GiB |
| Guest image | openEuler 24.03 LTS-SP3 | openEuler 24.03 LTS-SP3 |
| Guest kernel | `6.6.0-cubesandbox.guest.oe2403sp3` | `6.6.0-cubesandbox.guest.oe2403sp3` |
| Kernel SHA-256 | `c5515719...b976e` | `c5515719...b976e` |

两种规格均使用 `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim`，镜像摘要为 `sha256:cc200de2c966fef8f366102a35f5d22a623ae911ea66069a4a77061ed0d5f04e`。实际沙箱 `/proc/version` 显示内核由 openEuler GCC `12.3.1-105.oe2403sp3` 编译。

## 3. 测试条件

- `cube-bench`：`create-only`，warmup 3。
- TAP 总数：1198；每档要求至少 1000。
- 每档开始前和结束后连续三次确认 `sandbox/shim/task/tap_in_use = 0/0/0/0`。
- 正式请求未达到 100% 时，清理运行时后重测该档位；本次没有触发重测。

## 4. 3U2G 结果

| 并发 | 请求数 | 成功 / 失败 | avg | min | p95 | max | 总耗时 | 单沙箱均摊 | 吞吐 |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 20 / 0 | 43.14 ms | 39.92 ms | 47.64 ms | 50.40 ms | 1.010 s | 50.49 ms | 19.81/s |
| 10 | 200 | 200 / 0 | 54.32 ms | 44.28 ms | 63.02 ms | 71.15 ms | 1.244 s | 6.22 ms | 160.79/s |
| 20 | 300 | 300 / 0 | 97.17 ms | 64.45 ms | 139.32 ms | 157.40 ms | 1.637 s | 5.46 ms | 183.21/s |
| 50 | 500 | 500 / 0 | 257.73 ms | 66.38 ms | 355.81 ms | 512.16 ms | 2.898 s | 5.80 ms | 172.56/s |

3U2G 本轮最高吞吐出现在并发 20，为 `183.21/s`。

## 5. 4U2G 结果

| 并发 | 请求数 | 成功 / 失败 | avg | min | p95 | max | 总耗时 | 单沙箱均摊 | 吞吐 |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 20 / 0 | 48.79 ms | 45.20 ms | 51.83 ms | 53.54 ms | 1.129 s | 56.45 ms | 17.71/s |
| 10 | 200 | 200 / 0 | 59.35 ms | 48.67 ms | 69.49 ms | 105.19 ms | 1.358 s | 6.79 ms | 147.33/s |
| 20 | 300 | 300 / 0 | 102.44 ms | 57.51 ms | 133.52 ms | 155.15 ms | 1.727 s | 5.76 ms | 173.72/s |
| 50 | 500 | 500 / 0 | 293.14 ms | 73.89 ms | 389.63 ms | 977.50 ms | 3.513 s | 7.03 ms | 142.34/s |

4U2G 本轮最高吞吐同样出现在并发 20，为 `173.72/s`。

## 6. 3U2G 与 4U2G 对比

| 并发 | avg：3U / 4U | 4U 变化 | p95：3U / 4U | 4U 变化 | 吞吐：3U / 4U | 4U 变化 |
|:---:|---:|---:|---:|---:|---:|---:|
| 1 | 43.14 / 48.79 ms | +13.11% | 47.64 / 51.83 ms | +8.80% | 19.81 / 17.71/s | -10.57% |
| 10 | 54.32 / 59.35 ms | +9.26% | 63.02 / 69.49 ms | +10.26% | 160.79 / 147.33/s | -8.38% |
| 20 | 97.17 / 102.44 ms | +5.42% | 139.32 / 133.52 ms | -4.16% | 183.21 / 173.72/s | -5.18% |
| 50 | 257.73 / 293.14 ms | +13.74% | 355.81 / 389.63 ms | +9.50% | 172.56 / 142.34/s | -17.51% |

本次单轮结果中，3U2G 在四个并发档位的平均延迟和吞吐均优于 4U2G；并发 20 时 4U2G 的 P95 略低。每种规格目前只有一轮数据，该差异只能作为后续多轮复测的观察值，不能直接归因为 vCPU 数量。

## 7. 最终状态

| 检查项 | 结果 |
|---|---|
| Cubelet / CubeMaster | `active / active` |
| network-agent / CubeAPI | `active / active` |
| CubeAPI health | `status=ok, sandboxes=0` |
| 沙箱 / shim / task | `0 / 0 / 0` |
| TAP 总数 / 在用数 | `1198 / 0` |
| exporter 临时环境 | 已恢复为 `<unset>` |
| reset/guest-time 扫描 | 0 字节 |
| 本地证据校验 | `SHA256SUMS: OK` |

## 8. 证据索引

- [3U2G Template 元数据](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/3u2g/evidence/template-runtime.json)
- [4U2G Template 元数据](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/4u2g/evidence/template-runtime.json)
- [3U2G 实际 Guest 身份](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/3u2g/evidence/kernel-identity/guest-identity.txt)
- [4U2G 实际 Guest 身份](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/4u2g/evidence/kernel-identity/guest-identity.txt)
- [3U2G / 4U2G 聚合](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/aggregate-3u4u.json)
- [3U2G / 4U2G 对比](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/3u-vs-4u-comparison.json)
- [Cubelet reset/timeout 扫描](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/cubelet-reset-timeout-signatures-all.txt)
- [最终状态](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/evidence/final-state.txt)
- [完整校验清单](remote-results/cubesandbox-template-perf-3u4u-openEuler-20260727-204636/SHA256SUMS)
