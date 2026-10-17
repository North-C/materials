# .90 · agentwarn 模板 c100n100 复测（2026-10-17）

按「.90 · c100n100 性能调优」工作区的方法执行：1 轮 pilot 排除统计，5 轮正式测试，每轮同进程 `-w 3` 预热，启用 `-no-tui`。

- 模板：`tpl-381852bfe518c30bb815e163`（`agent.log=warn`），2 vCPU / 2048Mi / 1G 可写层。
- 正式五轮整轮耗时：156.814、162.335、158.030、159.490、165.847 ms；中位数 **159.490 ms**。
- 正式请求 **500/500 成功**；含 pilot 和预热共 **618 个实例全部清理**。
- 已测量的主要服务端窗口为沙箱创建、VM 启动和健康探测。组件统计每轮为预热与正式混合的 `unknown_phase=103`，不能当作正式 100 实例分布。
- 当前内核、THP defrag、RCU 和 MADV_RANDOM 开关状态与历史 s13 不同；此前本会话约 414 ms 轮的模板、预热方式和客户端构建也不同，不作单因素因果归因。

## 报告与数据

- [完整分析报告](RESULT_REPORT.md)
- [完整数据包（已脱敏，保留全部 398 个原交付文件）](result.tar.gz) · [包 SHA256](result.tar.gz.sha256)
- [逐轮 CSV](round-summary.csv) · [阶段对比 CSV](stage-comparison.csv) · [机器可读摘要](result-summary.json)
- [每轮 HTML、时间轴、原始 JSON 与清理回执入口](RESULT_REPORT.md#证据完整性与交付)
- [发布说明与验证](PUBLICATION.md) · [脱敏文件映射](PUBLICATION-MANIFEST.json) · [公开文件 SHA256](SHA256SUMS)

原始采集报告中的“不推送外部仓库”描述初次交付范围；本次依照用户随后明确要求发布到 materials。只替换 6 份日志中的模板下载令牌，所有日志记录、性能数值和时间戳均保留；私有原始数据包保持不变。
