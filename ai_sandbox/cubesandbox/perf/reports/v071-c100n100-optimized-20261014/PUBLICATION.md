# 第三份报告：发布范围、证据索引与复现

这是本地 `tools/bottleneck/runs/20261014T013154Z-optimized` 报告的归档发布，记录 **2026-10-14 优化版本＋NUMA0 首轮 c100n100 实测**。没有在发布过程中重新压测，也没有将该轮称为原版 v0.7.1 或精细埋点观测版。

[阅读 Markdown 报告](REPORT.md) · [原始 HTML](REPORT.html) · [原始 TXT](REPORT.txt)

## 有效范围

- 官方 API 样本是正式 100 次：100 成功、0 错误，平均 260.96527 ms、P95 360.840 ms。
- 组件样本是 `unknown_phase=103`，含 3 次预热；严格归属分类未通过，不能将它们标作 formal-only。历史组件基线也按 103 个 owned 实例重新汇总后比较。
- 优化源码为 `9dce2f877d9470908dd68594e4fe38edf365e141`，基于 v0.7.1 `31d911e430fdf8a8879bd062b8e78066c1a8e89d`。Cubelet/CubeAPI 允许 CPU 0–95，内存策略为 local；不意味着全部 guest 内存实际位于 NUMA0。
- 确认轮结束时 Shim SHA-256 漂移，验证退出码为 2，整轮排除。这里没有把确认轮 API 或组件时延混入首轮统计。
- 原报告里“当前 .90”的表述是测试当日的状态。归属诊断末尾“确认轮用于……”描述当时采集目的，最终确认轮被拒绝，以上述排除结论为准。

## 证据索引

| 内容 | 文件 | 使用边界 |
| --- | --- | --- |
| 报告及两轮对照 | [REPORT.md](REPORT.md)、[comparison.csv](comparison.csv)、[comparison.json](comparison.json) | 两次不同配置组合的单轮观测差异，不能拆分 PR 独立收益 |
| 官方正式 API 100 条 | [c100n100.raw.json](capture/startup-latency/c100n100.raw.json) | 仅配置、时延、序号及摘要，不含 API 凭据；没有 sandbox ID 配对 |
| 首轮组件汇总 | [analysis.json](capture/analysis.json)、[阶段 CSV](capture/stage-latency.csv) | unknown_phase=103；部分成功短阶段受日志门槛影响 |
| 相同 103 口径的历史基线 | [baseline-comparable-103.json](baseline-comparable-103.json)、[CSV](baseline-comparable-103.csv) | 不替代原报告的 formal-only 数据 |
| 网络细分 | [network-details.json](capture/network-details.json)、[CSV](capture/network-details.csv) | JSON 单位 ns；各行覆盖率不同，零累计字段不证明实际零成本 |
| 同实例 NewTask 差值 | [paired-newtask-gap.json](paired-newtask-gap.json) | 103 对；均值 51.454883 ms、P95 107.670 ms，不是纯调度等待 |
| 实例时间线 | [timeline.html](capture/timeline.html)、[timeline.json](capture/timeline.json)、[CreateContainer 明细](capture/create-container-details.jsonl) | 由已有日志重建的部分时间线，不是跨进程精确单调时钟 |
| 精细计时可用性 | [precision.json](capture/precision.json)、[CSV](capture/precision.csv) | 该构建没有新增 perftrace 端点，不可虚构子步骤时延 |
| 归属与清理 | [owned-sandbox-ids.json](capture/owned-sandbox-ids.json)、[清理账本](capture/suite-results/c100n100.delete.json) | 仅 103 个本轮 owned；外来实例未纳入、未由本轮清理 |
| 分类拒绝 | [phase-classification.json](capture/phase-classification.json)、[归属诊断](first-run-attribution-note.txt) | 保留 unverified 和失败检查；不人为改写 104 对合同 |
| 首轮身份与 NUMA 核验 | [before](capture/service-identity-before.json)、[after](capture/service-identity-after.json)、[verified-run.json](capture/verified-run.json)、[退出码](run.exit) | 固定哈希、进程和允许 CPU/策略核验，不测实际内存页位置 |
| 确认轮排除证据 | [hash error](capture-confirmation/service-identity-after-error.json)、[版本漂移](post-confirmation-version-drift.json)、[退出码](run-confirmation.exit) | 只发布拒绝证据，不发布或统计其时延结果 |
| 源码阶段边界 | [source-boundaries.txt](source-boundaries.txt) | 行号对应优化 HEAD；不对应本地未部署 perftrace 改动 |
| 原文件校验清单 | [source-artifacts.json](source-artifacts.json) | 记录每个导入文件的原始 SHA-256、大小和发布处理方式 |

## 公开范围

公开报告、数值汇总、实例 ID、组件身份与拒绝证据。没有复制原始请求日志、完整 `capture/evidence/`、环境转储或运行命令日志。发布文件已扫描 Authorization/Bearer、API key、access token、secret、password、私钥标记和 JWT 格式，未发现命中；同时核对 API raw 仅含测试配置与时延、身份文件仅含版本/哈希/进程/模板资源等元数据。

文件中的源日志路径、哈希和远端路径是证据定位信息，不承诺原始日志在公开仓库可下载。由于完整日志未公开，此归档可以复现报告渲染和数值汇总核验，不能仅凭公开包重新执行原始日志归属分类。完整原始证据继续保留在原工作区和测试机。

## 报告复现

从本目录运行：

```sh
python3 build_report.py
```

只依赖 Python 标准库和本目录的已保存 JSON，无网络和远端操作。渲染脚本生成 `REPORT.html`、`REPORT.txt`、`REPORT.md`、`comparison.json`、`comparison.csv`。HTML/TXT 与本地原报告保持字节一致；脚本仅增加 Markdown 渲染与相对链接，不重新解释原始计时数据。其原版本 SHA-256 保存在 `source-artifacts.json`。

校验未改写的导入文件：

```sh
python3 - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('.')
for item in json.loads((root / 'source-artifacts.json').read_text())['files']:
    if item['publication'] == 'byte-identical copy':
        assert hashlib.sha256((root / item['path']).read_bytes()).hexdigest() == item['source_sha256'], item['path']
print('Original artifact hashes: PASS')
PY
```

发布前另外核对了 100 条 API 样本平均值及 nearest-rank P95、103 个归属样本、首轮前后组件哈希/进程/NUMA、分类拒绝、确认轮退出码及全部报告相对链接。发布过程未更改原工作区文件。
