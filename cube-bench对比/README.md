# cube-bench 对比 · 2026-10-16

同一 ARM64 测试机、同一官方 sandbox-code:latest 镜像，比较 v0.7.1/master 同源码组与 v0.5.1；交替各三轮，正式 c100n100、独立预热 c1n3，全部 -no-tui JSON。600 个正式请求与 18 个预热请求均成功，618 个测试沙箱清理完成，最终残留 0。

- [中文汇总报告](report/REPORT.md)
- [HTML 汇总报告（下载后用浏览器打开）](report/summary.html)
- [汇总 JSON](report/summary.json) · [逐轮 CSV](report/rounds.csv)
- [v0.7.1/master 源码一致性证据](version-evidence/v071-master/README.md)
- [发布文件哈希与数值保留校验](publication-manifest.json)

这是脱敏发布副本。原始时延、样本顺序、统计与时间戳保留；实例使用轮内一致别名，环境标识已匿名化，文件字节不同于原件。原始组件日志、配置、metrics 与 CLI 清单未公开，不能从此副本重放日志解析。发布清单只校验发布文件；源码及二进制哈希仍指对应源码和构建产物。

每轮目录保留正式和预热的原始 JSON 数据脱敏副本、profile JSON/CSV、HTML 报告与时间轴。别名仅在轮内关联服务端记录，不表示客户端 seq 与 sandbox ID 的映射。归属 limited、master_stat 缺口及 5 ms 日志阈值限制保留；本比较不支持将差异归因于客户端源码。

## 逐轮数据

- [round-01-v071](round-01-v071/runs/20261016T040607Z-4a181a42/analysis/REPORT.md) · [正式 JSON](round-01-v071/runs/20261016T040607Z-4a181a42/capture/startup-latency/benchmark.raw.json) · [预热 JSON](round-01-v071/runs/20261016T040607Z-4a181a42/warmup/benchmark.raw.json)
- [round-02-v051](round-02-v051/runs/20261016T040647Z-ecdba122/analysis/REPORT.md) · [正式 JSON](round-02-v051/runs/20261016T040647Z-ecdba122/capture/startup-latency/benchmark.raw.json) · [预热 JSON](round-02-v051/runs/20261016T040647Z-ecdba122/warmup/benchmark.raw.json)
- [round-03-v071](round-03-v071/runs/20261016T040715Z-fb59979b/analysis/REPORT.md) · [正式 JSON](round-03-v071/runs/20261016T040715Z-fb59979b/capture/startup-latency/benchmark.raw.json) · [预热 JSON](round-03-v071/runs/20261016T040715Z-fb59979b/warmup/benchmark.raw.json)
- [round-04-v051](round-04-v051/runs/20261016T040743Z-217078a6/analysis/REPORT.md) · [正式 JSON](round-04-v051/runs/20261016T040743Z-217078a6/capture/startup-latency/benchmark.raw.json) · [预热 JSON](round-04-v051/runs/20261016T040743Z-217078a6/warmup/benchmark.raw.json)
- [round-05-v071](round-05-v071/runs/20261016T040810Z-20f11a40/analysis/REPORT.md) · [正式 JSON](round-05-v071/runs/20261016T040810Z-20f11a40/capture/startup-latency/benchmark.raw.json) · [预热 JSON](round-05-v071/runs/20261016T040810Z-20f11a40/warmup/benchmark.raw.json)
- [round-06-v051](round-06-v051/runs/20261016T040838Z-0006bebc/analysis/REPORT.md) · [正式 JSON](round-06-v051/runs/20261016T040838Z-0006bebc/capture/startup-latency/benchmark.raw.json) · [预热 JSON](round-06-v051/runs/20261016T040838Z-0006bebc/warmup/benchmark.raw.json)
