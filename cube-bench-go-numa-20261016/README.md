# CubeSandbox c100n100：Go 参数与 NUMA 实验

本目录包含 2026-10-16 的三状态对比报告、脱敏配置快照、逐轮数据及可复用配置脚本。每状态 5 轮，每轮并发 100、正式创建 100；固定模板、镜像与采集方法。实验结束保留了提高 Go 参数并恢复历史 NUMA 限制的组合配置。

- [完整中文报告](REPORT.zh-CN.md)：结果、归因边界、启动异常及最终健康与清理情况。
- [配置快照](config-snapshot.json)及[逐组件生效矩阵](configuration-matrix.md)：三阶段和最终复核的声明与运行状态。
- [配置方法与回滚说明](CONFIGURATION.md)：快照、预览、应用、实际生效验证、恢复。
- [配置脚本](scripts/go_numa.py)：入口；同目录辅助脚本须一起下载。
- [逐轮汇总](results.md)、[CSV](rounds.csv)和[证据导出校验](publication-evidence-verification.json)：原始时延及统计保真检查。

| 状态 | 整轮耗时中位数 | 相对基线 |
|---|---:|---:|
| 基线 | 508.002 ms | — |
| 提高 CubeMaster 三项 Go 环境参数 | 477.626 ms | -5.98% |
| Go 参数 + 恢复历史 NUMA 限制 | 374.930 ms | -26.20% |

候选环境参数为 `GOGC=800`、`GOMAXPROCS=32`、`GOMEMLIMIT=8GiB`。服务端 v0.7.1 源码另有 `debug.SetGCPercent(90)`，因此环境变量为 800 不等于实际 GC 目标为 800。本实验采用顺序测试，存在预热和运行状态漂移；不能把差异解释为单个参数的独立贡献。

脚本适用于报告中的 cgroup v1、NUMA node 1 对应 CPU 96–191 的部署，包含 5 个原生组件及 8 个容器组件的固定映射。快照、应用和验证会核对拓扑并拒绝不匹配的主机；恢复操作仍尝试执行并记录错误。它不是通用自动调参工具，也不负责删除沙箱。

```sh
# 在目标 Linux 主机上，以 root 执行；先阅读 CONFIGURATION.md。
# STATE 的父目录须已存在，并位于可靠的持久数据盘。
STATE=/data/go-numa-state-$(date -u +%Y%m%dT%H%M%SZ)
python3 scripts/go_numa.py snapshot --state-dir "$STATE"
python3 scripts/go_numa.py plan --state-dir "$STATE"
# 检查 STATE 下的 plan.json 与 plan.private.diff，确认维护窗口及空沙箱库存后：
python3 scripts/go_numa.py apply --state-dir "$STATE" --maintenance-window
python3 scripts/go_numa.py verify --state-dir "$STATE"
# 需要恢复时：
# python3 scripts/go_numa.py restore --state-dir "$STATE"
```

`snapshot` 生成的原始 unit/drop-in 备份和运行信息是私有运维材料，应留在目标主机。启用配置后，systemd 引用 `$STATE/container_cpuset.py`；恢复之前不要删除状态目录。恢复目标是该次快照的状态，不一定是本实验最初基线。

实验执行及最终配置已经在目标主机验证；本目录新整理的可复用脚本经过离线测试与审查，没有为发布而重新在实验主机执行配置变更。既有实验主机已处于最终组合状态，无需重复应用。

公开附件不包含凭据、原始服务配置、完整环境、私有路径和原始服务日志。原始备份仍由实验执行方保管；公开快照用于解释与复核配置，不能替代原始备份完成精确恢复。

`cubemaster-v071-main.go` 来自 CubeSandbox commit `31d911e430fdf8a8879bd062b8e78066c1a8e89d` 的 `CubeMaster/cmd/cubemaster/main.go`，保留原版权声明；对应许可见 [SOURCE-LICENSE.txt](SOURCE-LICENSE.txt)。
