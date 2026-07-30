# CubeSandbox openEuler Guest 新内核 Template 核心性能测试

测试时间：2026-07-27  
测试节点：`192.168.25.90`  
参考方法：[CubeSandbox 性能基准测试：基于 Template 创建沙箱](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html#%E4%B8%89%E3%80%81%E5%9F%BA%E4%BA%8E-template-%E5%88%9B%E5%BB%BA%E6%B2%99%E7%AE%B1)

## 1. 结论

服务、openEuler guest、Template 和 1000 TAP 配置均已确认生效，但本次环境不能产出完整的 100% 成功启动性能矩阵：

- `c1/n20` 为 `20/20`，是唯一满足验收条件的启动性能档位。
- 首轮 `c10/n200`、`c20/n300`、`c50/n500` 分别失败 6、9、13 次，错误均落在 `reset guest time failed`。
- 按“失败后清理资源并重跑直到 100%”的要求，`c10/n200` 又独立执行 44 轮，共 8800 个正式请求；没有一轮达到 `200/200`，最佳为 `199/200`。
- 44 轮合计成功 8579、失败 221，成功率 97.489%，每轮失败 1 到 9 个。该问题具有稳定统计特征，不能再视为偶发噪声。
- 累计密度已实际达到 100、300、500、1000 个存活 guest；1000 点连续三次确认 `API/shim/task=1000/1000/1000`。
- 1000 点可用内存为 2152.870 GiB，按空载基线差值计算约 24.236 MiB/VM。
- 测试结束后服务健康，模板代码执行成功，运行时回到 `0 sandbox / 0 shim / 0 task / 0 TAP up`。

因此，新 host 内核没有消除 openEuler guest 下的 `reset guest time failed`。除 `c1/n20` 外，启动延迟数据只能作为失败轮观测值，不能作为正式性能成绩。

## 2. 测试环境

| 项目 | 配置或结果 |
|---|---|
| Host kernel | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` |
| Host CPU / 内存 | 384 logical CPU / 约 2.2 TiB RAM |
| Guest OS | openEuler 24.03 LTS-SP3 |
| Guest image | `20260609-222734` |
| Guest image SHA-256 | `1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da` |
| Guest kernel | `6.6.119-49.6`，SHA-256 `7c227b2b...676d8e5` |
| Template ID | `tpl-e368280ed28a46dbb70e0161` |
| Template image | `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` |
| Template image digest | `sha256:cc200de2c966fef8f366102a35f5d22a623ae911ea66069a4a77061ed0d5f04e` |
| Template 规格 | 2 vCPU / 2000 MiB |
| Writable layer | 1 GiB |
| Probe / ports | `49999 /health`；暴露 `49999`、`49983` |
| TAP 配置 | `tap_init_num=1000` |
| 测试工具 | `cube-bench`，`create-only`，启动矩阵 `-w 3` |

`/etc/os-release` 是直接用 `debugfs` 从当前 guest image 读取的；Template 元数据记录的 guest image version 与镜像目录中的版本均为 `20260609-222734`。

`.90` 无法稳定访问 Docker Hub，因此 Template 容器镜像从 `.61` 的本地 Docker cache 导出并校验后导入。为使构建使用本地 Docker，构建期间临时关闭 CubeMaster native exporter；Template READY 后已恢复原始 `.one-click.env` 并重启 CubeMaster，文件对比一致。

## 3. 启动延迟与并发扩展

每档执行前后都清空 API 沙箱；失败残留 shim 在确认无 task 后回收，并等待 API、shim、task、TAP 回到空载状态。以下延迟统计只覆盖 `cube-bench` 记录到的成功创建，但“有效性”按整轮是否 100% 成功判定。

| 并发 | 请求数 | 成功/失败 | avg | min | p95 | max | 单沙箱均摊 | 吞吐 | 有效性 |
|:---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 20 | 20 / 0 | 43.37 ms | 38.21 ms | 48.71 ms | 49.13 ms | 49.98 ms | 20.01 个/s | 有效 |
| 10 | 200 | 194 / 6 | 58.24 ms | 44.62 ms | 111.20 ms | 178.94 ms | 48.27 ms | 20.10 个/s | 无效 |
| 20 | 300 | 291 / 9 | 73.32 ms | 49.25 ms | 129.88 ms | 151.58 ms | 31.61 ms | 30.69 个/s | 无效 |
| 50 | 500 | 487 / 13 | 163.36 ms | 61.20 ms | 248.83 ms | 746.46 ms | 35.63 ms | 27.33 个/s | 无效 |

后三档不能与参考网页的 100% 成功数据直接比较。失败请求会等待约 8 秒的 guest RPC timeout，也会显著拉低整轮 wall-time 吞吐。

### c10/n200 重试验收

| 指标 | 结果 |
|---|---:|
| 完整重试轮数 | 44 |
| 正式请求总数 | 8800 |
| 成功 | 8579 |
| 失败 | 221 |
| 聚合成功率 | 97.489% |
| 100% 成功轮数 | 0 |
| 单轮最少 / 最多失败 | 1 / 9 |
| 平均每轮失败 | 5.023 |
| 最佳一轮 | 199/200 |

日志中出现 228 个 `reset guest` 文本片段，其中包含 221 个正式请求错误及 warmup 错误。没有发现 `tap fd unavailable`，说明 c10 重试失败不是 TAP 数量不足导致的。

## 4. 累计存活密度

密度测试从空载开始，按 `100 + 200 + 200 + 500` 累计创建。每个批次若出现失败，先回收“shim ID 无对应 containerd task 目录”的失败 shim，再只补建缺口；达到目标后才采样内存。

| 存活沙箱数 | 系统可用内存 | 相对基线减少 | 单 VM 均摊开销 | 状态校验 |
|---:|---:|---:|---:|---|
| 0（基线） | 2176.537 GiB | 0 | - | API/shim/task = 0/0/0 |
| 100 | 2175.298 GiB | 1.240 GiB | 12.694 MiB | 100/100/100 |
| 300 | 2171.914 GiB | 4.623 GiB | 15.779 MiB | 300/300/300 |
| 500 | 2167.757 GiB | 8.780 GiB | 17.982 MiB | 500/500/500 |
| 1000 | 2152.870 GiB | 23.667 GiB | 24.236 MiB | 1000/1000/1000，连续 3 次 |

单 VM 数值按 `(基线 MemAvailable - 当前 MemAvailable) / 存活沙箱数` 计算。该指标包含 CubeSandbox 进程、页缓存和测试期间的系统波动，适合按参考网页方法观察密度趋势，不代表 guest 已预占 2 GiB 内存。

### 密度创建批次

| 目标 | 首批请求 | 首批成功/失败 | 补建过程 | 最终存活 |
|---:|---:|---:|---|---:|
| 100 | 100 | 98 / 2 | 2/2 | 100 |
| 300 | 200 | 197 / 3 | 3/3 | 300 |
| 500 | 200 | 198 / 2 | 2/2 | 500 |
| 1000 | 500 | 431 / 69 | 68/69，再 1/1 | 1000 |

1000 点首批错误列表同时包含 `reset guest` 和 `tap fd unavailable`。原因是池目标恰好为 1000：从 500 向 1000 创建时，失败的 reset guest shim 在批次返回前仍占有 TAP，后续并发请求没有余量。network-agent 在失败恢复过程中将物理 TAP 数动态补充到 1198；最终所有接口均为 DOWN，但没有直接删除 network-agent 管理的额外接口。

## 5. 最终状态

| 检查项 | 最终结果 |
|---|---|
| Cubelet | `active` |
| CubeMaster | `active` |
| network-agent | `active`，`/healthz = ok` |
| CubeAPI | `{"status":"ok","sandboxes":0}` |
| 沙箱 / shim / task | `0 / 0 / 0` |
| TAP 配置 / 物理数 / UP 数 | `1000 / 1198 / 0` |
| Template | `READY` |
| SDK 代码执行 | 输出 `12345`，无 error |

唯一已知的非 CubeSandbox failed systemd unit 是此前已有的 `NetworkManager-wait-online.service`，不影响本次 CubeSandbox 服务健康判定。

## 6. 证据索引

- [最终环境状态](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/evidence/final-state.txt)
- [Template 完整元数据](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/evidence/template-final.json)
- [测试后 SDK smoke](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/evidence/post-test-sdk-smoke.log)
- [首轮启动矩阵聚合](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/startup-latency/aggregate.json)
- [c10 44 轮重试聚合](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/retries-v2/create-c10-n200/startup-latency/retry-aggregate.json)
- [累计密度数据](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/density-rerun/density/points.tsv)
- [1000 点三次状态门禁](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/density-rerun/density/active-1000.manual-gate.log)
- [最终密度清理记录](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/density-rerun/density/final-manual-cleanup.log)
- [完整远端文件校验清单](remote-results/cubesandbox-core-perf-openEuler-new-kernel-20260727-120429/SHA256SUMS)

