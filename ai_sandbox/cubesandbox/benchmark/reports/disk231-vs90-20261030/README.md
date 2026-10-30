# .231 / .90 磁盘对比报告与证据

日期：2026-10-30。对象：123.60.230.231与192.168.25.90。类型：磁盘盘点、fio实测汇编与公开规格核查；资料整理完成，未新增实验。

**[阅读完整报告](REPORT.md)**

报告涵盖系统盘/数据盘实际路径、全部可见盘、TB/TiB换算、XFS与健康状态、内核/平台/预处理差异、.231四类各五轮、.90六份历史fio、公开规格及业务归因限制。

| 入口 | 内容 |
| --- | --- |
| [REPORT.md](REPORT.md) | 结论、条件、全部正式轮次、公开规格和未验证项 |
| [PUBLICATION.md](PUBLICATION.md) | 原件范围、发布处理、未包含内容和复核边界 |
| [source-manifest.json](source-manifest.json) | 原始工作区路径、原件与公开副本SHA256 |
| [.231统计](derived/host231-summary.json) / [.90历史统计](derived/host90-history.json) | 可追溯到随包原件的数值 |
| [P5530规格](derived/p5530-public-specs.json) / [HWE相关规格](derived/host90-public-specs.json) | 外部来源与规格层级，保留精确型号缺口 |
| [离线核验器](tools/verify.py) / [核验结果](validation.json) / [SHA256SUMS](SHA256SUMS) | 不访问远端的完整性与数值核验 |

两机主比较为.231五轮中位数对.90历史单轮，非同期单因素对照。P5530 960GB官网随机读30万IOPS；HWE6A精确后缀适用的厂家性能表尚未确认。系统盘独立性能、.90在用数据盘写性能、换盘业务收益均未测。
