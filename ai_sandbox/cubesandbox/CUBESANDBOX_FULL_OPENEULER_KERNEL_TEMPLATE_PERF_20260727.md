# CubeSandbox 完整 openEuler Guest Kernel Template 并发性能复测

测试时间：2026-07-27  
测试节点：`192.168.25.90`  
参考方法：[CubeSandbox 性能基准测试：基于 Template 创建沙箱](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html#%E4%B8%89%E3%80%81%E5%9F%BA%E4%BA%8E-template-%E5%88%9B%E5%BB%BA%E6%B2%99%E7%AE%B1)

## 1. 结论

新编译的 openEuler `vmlinux-bm` 已在 `.90` 上实际生效。本次新建 Template 绑定的 kernel artifact、Template 兼容性元数据以及沙箱内 `uname -r` 均指向同一个新内核：

```text
6.6.0-cubesandbox.guest.oe2403sp3
sha256:c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e
```

四档 Template 并发创建均在第一次尝试达到 100% 成功，总计 `1020/1020`，没有触发重试：

- `c1/n20`：`20/20`
- `c10/n200`：`200/200`
- `c20/n300`：`300/300`
- `c50/n500`：`500/500`

Cubelet 日志中没有发现 `reset guest`、`guest time` 或 reset timeout 特征。与此前使用 OpenCloudOS/CubeSandbox `6.6.119-cube.bm.guest.001` 内核时的同类测试相比，本轮没有复现 `reset guest time failed`。这强烈表明此前问题与 guest kernel 实现或配置相关，但单轮全成功还不能代替长时间稳定性结论。

随后又连续追加 5 轮相同矩阵，新增 `5100/5100` 成功。连同首次测试共完成 6 轮、24 个档位、`6120/6120` 个正式创建请求；所有档位都在 attempt 1 通过，没有触发重试，全部日志仍未发现 reset/guest-time 特征。这比单轮结果更有力地支持问题与旧 guest kernel 相关，但仍不等同于无限时长下的故障率为零。

## 2. 新内核应用确认

| 检查项 | 结果 |
|---|---|
| 运行时入口 | `cube-kernel-scf/vmlinux -> vmlinux-bm` |
| 部署文件摘要 | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| Template kernel artifact 摘要 | 与部署文件完全一致 |
| Template kernel version | `6.6.0-cubesandbox.guest.oe2403sp3@sha256:c5515719...b976e` |
| Template 兼容策略 | `STRICT`，状态 `OK` |
| 沙箱内 `uname -r` | `6.6.0-cubesandbox.guest.oe2403sp3` |
| 编译工具链 | openEuler GCC `12.3.1-105.oe2403sp3` |
| 旧内核备份 | `vmlinux-bm.backup-20260727-194055`，摘要 `7c227b2b...676d8e5` |

当前基础 guest image 通过 `debugfs` 读取 `/etc/os-release`，确认为 `openEuler 24.03 LTS-SP3`。在 Template 沙箱内执行命令时看到的 Ubuntu 22.04 是 `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` 的容器 rootfs，不是 MicroVM guest kernel 或基础 guest image。

## 3. 测试环境

| 项目 | 配置或结果 |
|---|---|
| Host kernel | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` |
| Guest image OS | openEuler 24.03 LTS-SP3 |
| Guest image version | `20260609-222734` |
| Guest image SHA-256 | `1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da` |
| Guest kernel | `6.6.0-cubesandbox.guest.oe2403sp3` |
| Guest kernel SHA-256 | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| Template ID | `tpl-297f00a33adb43de957bbf90` |
| Template image | `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` |
| Template image digest | `sha256:cc200de2c966fef8f366102a35f5d22a623ae911ea66069a4a77061ed0d5f04e` |
| Template 规格 | 2 vCPU / 2000 MiB |
| Writable layer | 1 GiB |
| 测试工具 | `cube-bench`，`create-only`，warmup 3 |
| TAP 门禁 | 至少 1000；实际 1198 |

第一次 Template 构建因 native exporter 访问 Docker Hub 时连接被重置而失败。随后临时设置 `CUBEMASTER_NATIVE_ROOTFS_EXPORT_ENABLED=false`，使用 `.90` 已缓存的同一 ARM64 镜像重新构建，第二次成功。测试结束后已撤销该临时 systemd manager 环境变量并重启 CubeMaster，恢复原始服务环境。

## 4. Template 并发创建性能

每档开始前和结束后都要求连续通过资源门禁：`sandbox=0`、`shim=0`、`task=0`、`tap_in_use=0` 且 TAP 总数不低于 1000。四档前后记录均为 `0/0/0/0`，实际 TAP 总数为 1198。

| 并发 | 请求数 | 成功/失败 | avg | min | p95 | max | 总耗时 | 单沙箱均摊 | 吞吐 |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 20 / 0 | 43.29 ms | 39.19 ms | 47.58 ms | 47.86 ms | 1.035 s | 51.73 ms | 19.33 个/s |
| 10 | 200 | 200 / 0 | 65.83 ms | 47.20 ms | 113.28 ms | 153.70 ms | 1.494 s | 7.47 ms | 133.85 个/s |
| 20 | 300 | 300 / 0 | 89.87 ms | 50.73 ms | 109.78 ms | 656.61 ms | 1.743 s | 5.81 ms | 172.15 个/s |
| 50 | 500 | 500 / 0 | 363.66 ms | 61.57 ms | 1197.93 ms | 1408.05 ms | 3.843 s | 7.69 ms | 130.12 个/s |

`c20/n300` 获得本轮最高吞吐 `172.15 个/s`。并发提升到 50 后平均值和 P95 明显上升，吞吐下降到 `130.12 个/s`，但没有创建失败。

## 5. 五轮追加复测

追加复测连续执行 5 个完整轮次，每轮均包含四档并发矩阵。每轮及每档之间继续执行相同的资源清理和连续空载门禁。

| 追加轮次 | 请求数 | 成功 | 失败 | 是否重试 |
|:---:|---:|---:|---:|:---:|
| 1 | 1020 | 1020 | 0 | 否 |
| 2 | 1020 | 1020 | 0 | 否 |
| 3 | 1020 | 1020 | 0 | 否 |
| 4 | 1020 | 1020 | 0 | 否 |
| 5 | 1020 | 1020 | 0 | 否 |

### 六轮累计性能

下表将首次测试和 5 轮追加测试合并。`avg`、`p95` 和吞吐为 6 轮算术平均；括号内是各轮最小值到最大值。

| 并发/每轮请求 | 累计成功/失败 | avg 均值（范围） | p95 均值（范围） | 吞吐均值（范围） |
|---|---:|---:|---:|---:|
| c1/n20 | 120 / 0 | 44.95 ms（43.10-47.59） | 52.39 ms（47.34-61.28） | 19.02/s（17.99-19.93） |
| c10/n200 | 1200 / 0 | 58.21 ms（54.37-65.83） | 73.83 ms（63.36-113.28） | 150.45/s（133.85-160.28） |
| c20/n300 | 1800 / 0 | 87.86 ms（86.32-89.87） | 109.27 ms（107.03-112.38） | 185.02/s（163.45-201.96） |
| c50/n500 | 3000 / 0 | 366.22 ms（333.56-416.39） | 1248.92 ms（1048.60-1379.16） | 123.26/s（106.16-141.18） |

六轮累计 `6120/6120`，24 个档位全部为 attempt 1。追加测试的 Cubelet 日志、benchmark 日志以及每轮自动生成的 reset/timeout 特征文件均为空。

## 6. 最终状态

| 检查项 | 最终结果 |
|---|---|
| Cubelet / CubeMaster | `active / active` |
| network-agent / CubeAPI | `active / active` |
| CubeAPI health | `status=ok` |
| 沙箱 / shim / task | `0 / 0 / 0` |
| TAP 物理数 / UP 数 | `1198 / 0` |
| Template | `READY`，兼容状态 `OK` |
| 测试状态 | `complete` |

替换内核后 Cubelet 第一次启动遇到 workflow 插件探测竞态，systemd 自动重试后恢复 `active`；在 Template 构建及后续六轮性能测试期间服务保持健康。

## 7. 证据索引

- [内核部署、备份与 guest image 身份](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/evidence/kernel-deployment.txt)
- [沙箱内实际 kernel 身份](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/evidence/kernel-identity/guest-identity.txt)
- [Template 运行时元数据](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/evidence/template-runtime.json)
- [Template 首次构建失败记录](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/evidence/template-build-watch.log)
- [Template 第二次构建成功记录](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/evidence/template-build-watch-attempt-2.log)
- [Template 导出环境恢复记录](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/evidence/template-export-environment-restored.txt)
- [四档性能聚合](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/startup-latency/aggregate.json)
- [reset/timeout 特征扫描](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/startup-latency/reset-timeout-signatures.txt)
- [最终资源状态](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/evidence/final-state.txt)
- [完整文件校验清单](remote-results/cubesandbox-template-perf-full-openEuler-kernel-20260727-194518/SHA256SUMS)
- [追加五轮聚合](remote-results/cubesandbox-template-perf-full-openEuler-kernel-multiround-20260727-200024/multiround-aggregate.json)
- [六轮累计聚合](remote-results/cubesandbox-template-perf-full-openEuler-kernel-multiround-20260727-200024/combined-six-round-aggregate.json)
- [追加轮次逐轮结果](remote-results/cubesandbox-template-perf-full-openEuler-kernel-multiround-20260727-200024/rounds-summary.tsv)
- [追加测试最终状态](remote-results/cubesandbox-template-perf-full-openEuler-kernel-multiround-20260727-200024/evidence/final-state.txt)
- [追加测试完整校验清单](remote-results/cubesandbox-template-perf-full-openEuler-kernel-multiround-20260727-200024/SHA256SUMS)
