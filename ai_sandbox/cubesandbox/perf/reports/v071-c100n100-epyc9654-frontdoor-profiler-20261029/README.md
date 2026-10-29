# EPYC 9654 机器：c100 入口阶段与 profiler 开销

日期：2026-10-29。类型：实测报告与脱敏派生数据。状态：七组各五轮完成，3500/3500 正式请求成功；额外 Go trace 未采集。

[返回性能索引](../../README.md) · [主报告](REPORT.md) · [离线 HTML](report.html) · [完整阶段表](STAGES.md) · [逐轮对照](COMPARISON.md)

本批补齐 Client→API→Master 入口，并找到 SID 分配前的模板解析阶段。完整 profiler 五轮共500个正式请求、15个预热请求；模板解析的逐轮均值中位数为34.408 ms，热缓存路径仍有三次数据库查询。

未打入口补丁 U 与完整采集 F 的整轮中位数为174.288/170.883 ms，均值为173.434/176.190 ms，配对差值正负混合。不能据更低的中位数宣称 profiler 提升性能或零开销。SQL池等待、日志锁、调度的独立占比尚未取得实测轨迹。

## 从这里阅读

| 资料 | 内容 |
| --- | --- |
| [主报告](REPORT.md#entry-breakdown) | 35轮配置对照、1–10入口主链、Master嵌套阶段和瓶颈边界 |
| [HTML报告](report.html#entry-breakdown) | 下载本专题后本地打开；层级表格与图表，GitHub文件页本身不执行HTML |
| [79项阶段表](STAGES.md) | 395行逐轮统计、覆盖及未观测项，不将缺失补零 |
| [数据说明与复算](data/README.zh-CN.md) | 35轮、3500个客户端样本、515个匿名阶段请求与离线验证 |
| [构建与环境](evidence/BUILD-AND-ENVIRONMENT.zh-CN.md) | 固定基点、U/P源码快照、逐补丁状态、组件SHA和生效证据摘要 |
| [源码与SQL证据](evidence/SOURCE-AUDIT.zh-CN.md) | 三次查询、日志路径、计时边界及105条安全SQL元数据 |
| [执行记录](EXECUTION-NOTES.md) | 清理歧义、轮转补验和负载门禁等待；未丢弃快慢轮次 |
| [额外轨迹状态](RUNTIME-TRACE-STATUS.md) | 未采原因，未覆盖另一会话部署；不混入35轮 |
| [发布范围](PUBLICATION.md) | 原件/公开副本、脱敏、未公开证据及验证限制 |
| [公开校验清单](SHA256SUMS) | 本专题文件SHA256，不代替原始运行有效性证明 |

## 复核

在本专题目录执行 `python3 -I data/verify_public_data.py --verify data`；脚本仅读取本地附件，不连接机器或发起压测。按照 [数据说明](data/README.zh-CN.md) 查看验证覆盖和统计口径。使用 `shasum -a 256 -c SHA256SUMS` 校验公开文件字节。

本报告仅代表固定源码、模板和运行条件的这批实验，不代表机器当前状态，不与历史其他模板或主机混合计算收益。
