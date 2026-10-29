# EPYC 9654：持续运行版本 c100 复测与日志 profiler

日期：2026-10-29；实验窗口 17:27–17:34 CST。状态：B/D/F 各五轮完成，1500/1500 正式请求与45/45预热成功；五轮阶段分析完成。此为当时快照。

普通前测 B 整轮中位130.501ms；交错普通 D / 采集 F 为129.468 / 132.245ms，组中位差+2.777ms。五个配对差有正有负，不声称固定或零开销。最慢请求集中在 Cubelet 早期/storage 区间；底层锁、I/O与调度根因尚未确认。

| 入口 | 内容 |
| --- | --- |
| [主报告](REPORT.md) | 测试条件、15轮对照、开销边界、版本与补丁状态 |
| [阶段分解](STAGES.md) | 按顺序和包含关系编排；全部已知阶段、覆盖与入口缺口 |
| [逐轮数据](data/rounds.csv) / [组间统计](data/comparison.json) | 15轮正式计时及五对 F−D |
| [阶段逐轮表](data/stage-rounds.csv) / [阶段汇总](data/stage-summary.json) | formal/warmup分列、缺失不补零 |
| [最慢请求摘要](data/tail-summary.json) / [F5变化](data/f5-stage-variation.json) | 匿名同请求关联与其他波动区间 |
| [组件与源码身份](evidence/provenance.json) / [审计摘要](evidence/audit-summary.json) | 实际SHA、未知构建来源、完成与清理状态 |
| [发布范围](PUBLICATION.md) / [数据投影](data/DATA-PROJECTION.zh-CN.md) / [SHA256](SHA256SUMS) | 脱敏方法、原件与副本边界及公开文件校验 |

当前组件没有可用的 frontdoor 入口观测，Client→API、API→Master仍为缺失。此前[入口打点报告](../v071-c100n100-epyc9654-frontdoor-profiler-20261029/README.md)属于另一组构建与重启条件，不与本批拼接阶段或计算收益。

[返回性能索引](../../README.md)
