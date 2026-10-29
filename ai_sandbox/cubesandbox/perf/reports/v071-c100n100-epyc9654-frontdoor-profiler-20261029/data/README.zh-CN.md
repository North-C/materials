# EPYC 9654 机器：100 并发 profiler 公开派生数据

日期：2026-10-29。状态：35 轮计时、7 组各五轮、六类对照；五轮完整观测包含 500 formal + 15 warmup。这里是原始证据的匿名派生投影，不是原始日志包。

## 文件与复核

- `benchmark-samples.json`：35 轮 summary 与 3500 个正式 create_ms。`total_time_s` 单位秒，其他请求耗时毫秒；warmup 不计入整轮计时。
- `comparison.json`、`rounds.csv`、`contrasts.csv`：四项指标的逐轮、组内和配对描述统计；七组因素矩阵。U/P/C/S/F 按 block 配对，A_before/A_after 按序号仅描述前后漂移。保留所有快慢轮，没有排除异常值。
- `requests.json`：515 个匿名请求各 79 项值与状态，正式/预热严格分开。编号由轮次、phase 与正式客户端 seq 或 warmup 数组序号生成（原 warmup seq 为 0，另保留 anonymous_index），跨表可关联，不含原 SID/RequestId。
- `stage-definitions.json`、`stage-summary.json`、`stage-rounds.csv`：79 项定义、五轮汇总、395 行统计。P95 用 nearest-rank；轮间统计以五轮为单位，500 请求合并分布仅供描述。包含/并行/残差阶段不能相加，缺失不补零，marker 不作耗时样本。
- `network-details.json`：五轮原 profiler 网络 23 字段的匿名样本、统计及覆盖。单位为 ns，与上述 ms 区分；保留原网络 parser 分位数口径。
- `verify_public_data.py`：仅 Python 标准库、无网络或远端操作。运行 `python3 -I verify_public_data.py --verify .`，从公开值复核 35 轮、7 组、6 类对照的四项指标，以及 500 formal 的全部 395 行与 79 项汇总。以 1e-12 相对/绝对容差验证浮点重算，导出原值不作四舍五入。
- `verification.json`：导出时的离线验证结果；`SOURCE-MANIFEST.json`：每个未公开源文件的逻辑编号、原件 SHA256、对应公开文件 SHA256；`SHA256SUMS`：公开包逐文件校验值（不自校验该清单）。

## 未公开与证据边界

未公开原始日志、配置、身份快照、journal、地址、用户名路径、SID/RequestId、boot/time namespace、绝对时间轴、源码 bundle、二进制或凭据。原始配置与逐次部署/清理门禁不在本子包中；35 valid 和因素身份是既有本地证据的验收结果，公开数值重算不能重新证明环境同一性、资源归属或时钟兼容。原件哈希只固定原件字节，不能让读者从哈希恢复日志。

每轮本地已确认的入口、Master、Cubelet、Shim 关联在导出中保留为同一匿名请求的阶段值；公开值可重算统计，无法从未公开日志独立复做解析或校验原记录时间戳。warmup 的 15 个请求保留逐阶段值，但不混入 500 formal 的汇总。旧 A 组没有逐请求 SID/warmup 导出，计时 100 成功仍保留。

没有新增性能测试或优化。额外 Go runtime trace 因部署前门禁停止，真实样本为 0；不能据阶段差值证明 SQL 池或日志锁耗时。U→F 的中位数和均值方向不一致，五轮证据不足以声称固定开销、零开销或性能收益。
