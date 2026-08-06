# CubeSandbox aprmask + fixed cube-runtime 多资源模板并发验证

## 结论

验证通过。在 `.65` 的 `aprmask` 内核与修复版 `cube-runtime` 组合上，修复前的错误未复现：

- 25/25 个模板构建 READY；
- 7,500/7,500 次基于模板的并发沙箱创建成功；
- `reset guest time failed`：API 响应 0 次，新增 CubeShim 日志 0 次；
- VM boot/start/resume/restore 错误：0 次；
- 新增 dmesg 中 RCU stall/timer handling 特征：0 次；
- 150/150 轮资源清理通过，无残留沙箱或 shim，TAP 均恢复至开测基线。

这是对本次指定矩阵和压力模型的回归结论，不代表对所有负载的绝对证明。

## 环境

| 项目 | 值 |
|---|---|
| 远端 | `192.168.25.65` (`master`) |
| 内核 | `6.6.0-sbench-irqbypass-xarray-v2-aprmask` |
| cube-runtime SHA256 | `a68d64cd29c84d544b2c8a4e1f9d6ab2d60d7d451f9ecd1ffccb811d4749ea9f` |
| 镜像 | `192.168.25.65:2900/bench/sandbox-code:latest` |
| 资源配置 | 1U/2G、2U/2G、3U/2G、4U/2G、5U/2G |
| 模板数 | 每档 5 个，共 25 个；严格串行构建 |
| 每模板压力 | 6 轮 x 每轮并发 50，共 300 次 |
| 总创建数 | 25 x 300 = 7,500 |
| 测试时段 | 2026-08-05 20:12:07 至 20:39:50 +08:00 |

## 分档结果

API 延迟统计仅计算 `POST /sandboxes`，单位为秒。

| 配置 | 模板 | 创建 | 成功 | 失败 | 平均 | P50 | P95 | P99 | 最大 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1U/2G | 5 | 1,500 | 1,500 | 0 | 0.088753 | 0.080897 | 0.165857 | 0.181953 | 0.220343 |
| 2U/2G | 5 | 1,500 | 1,500 | 0 | 0.084437 | 0.085415 | 0.106615 | 0.119449 | 0.175087 |
| 3U/2G | 5 | 1,500 | 1,500 | 0 | 0.078148 | 0.079301 | 0.098116 | 0.108785 | 0.122858 |
| 4U/2G | 5 | 1,500 | 1,500 | 0 | 0.076104 | 0.075656 | 0.099911 | 0.121220 | 0.137269 |
| 5U/2G | 5 | 1,500 | 1,500 | 0 | 0.084841 | 0.082057 | 0.123899 | 0.137056 | 0.152077 |

每个模板均为 300/300，详见 `validate4/summary.tsv`。

## TAP 与清理

按要求将 Cubelet 配置中的 `tap_init_num` 从 500 提升至 1000，并重启 network-agent 完成预热。

- TAP 宿主链接基线：1000；
- network-agent 可分配池基线：984；
- 差值 16 为 Cubelet 长期预取的 TAP FD；
- 每轮清理后要求沙箱 0、测试新增 shim 0；
- TAP 必须连续 3 次达到 `links=1000, pool=984, abnormal=0, quarantined=0` 才进入下一轮；
- 150 轮全部通过，无清理或 TAP 门禁失败。

远端当前仍保持 `tap_init_num = 1000`。修改前备份：

`/usr/local/services/cubetoolbox/Cubelet/config/config.toml.before-tap1000-20260805-195630`

## 证据索引

- `template-build/templates.tsv`：25 个模板及 READY 状态；
- `validate4/totals.tsv`：最终判定计数；
- `validate4/summary.tsv`：逐模板汇总；
- `validate4/results.tsv`：7,500 次请求明细、耗时和分类；
- `validate4/cleanup-summary.tsv`：150 轮资源/TAP 恢复结果；
- `validate4/responses/`：逐请求创建、删除原始响应；
- `validate4/cube-shim-req.delta.log`：本轮 CubeShim 日志增量；
- `validate4/dmesg.delta.log`：本轮内核日志增量；
- `tap1000-preflight/`：TAP 配置变更与预热证据。

执行脚本：`scripts/validate_aprmask_multi_resource_templates_65.sh`。
