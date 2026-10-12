# SWE 回放测试数据与图表

本目录保存 2026-10-09–10 的 `.95` 功能验证、`.90` 两批密度测试和准入检查的发布副本。
2026-10-12 的工作是从已有归档提取、脱敏、校验和绘图，没有重新执行测试。

- [结果报告与图表](20261009-10/README.md)
- [所有回放轮次汇总 CSV](20261009-10/summary.csv) / [JSON](20261009-10/summary.json)
- [逐文件来源、变换和 SHA256](20261009-10/evidence-manifest.json)
- [发布校验与图表修正来源](20261009-10/publication-info.json)；全包校验使用上一级 [SHA256SUMS](../SHA256SUMS)。
- [提取脚本](tools/export_results.py) / [发布图绘制脚本](tools/render_charts.py)

## 目录与读取方法

`20261009-10/runs/` 按测试轮次保留原生结果结构，包含 run_summary、轨迹索引、逐轨迹结果、
逐步时间序列、文本报告、Excel、Gantt，以及实际采集到的 VM/主机监控数据与 SVG。
`batch1/`、`batch2/` 包含脱敏配置、从日志提取的进度表、宿主采样 CSV 和对比图。

较大的 JSON/JSONL/CSV 使用 gzip；`.xlsx`、`.png`、`.svg` 可以直接下载或预览。
轨迹索引和 run_summary 的文件引用已调整到发布目录，压缩文件扩展名为 `.gz`。
读取 gzip 不需要导入镜像或连接平台，例如在本目录执行：

```bash
python3 - <<'PY'
import gzip, json
from pathlib import Path
run = Path('20261009-10/runs/batch2-384')
series = next(run.glob('*_lifecycle_series.jsonl.gz'))
with gzip.open(series, 'rt') as f:
    steps = [json.loads(line) for line in f]
print('steps:', len(steps))
print('timed-out steps:', sum(bool(s.get('timed_out')) for s in steps))
PY
```

Excel 和原生 JSON 的统计读取时刻可能不同，比较跨轮 wall/吞吐统一使用 run_summary。
原生 `summary.csv` 有分节标题，不是统一字段的平表；不要直接与顶层 `summary.csv` 合并。

## 发布处理与复现

- 保留原始数值、时间戳、退出码、超时和执行异常字段；普通非零退出码未改写为成功。
- JSON 中省略动作文本及 stdout/stderr；原生报告本来就不保证完整保留命令输出。
- 地址、用户目录、模板 ID 脱敏；32 位十六进制运行标识替换为稳定的 SHA256 派生别名，便于跨表关联。
- 图表修正在结果报告中单列。原始归档及旧图仍保存在原项目，manifest 记录每个发布文件的原始来源和哈希。
- 未上传平台服务日志、完整终端日志、凭据、镜像 tar 或轨迹输入。进度 CSV 只提取日志中的数值统计行。

提取工具为本次发布新增的自定义离线工具；绘图使用 Matplotlib 3.10.9 / NumPy 2.2.6。
原生 benchmark 的版本和命令见结果报告，两者不是同一执行工具。
输入 `--source` 为含 `validation/` 的原项目目录；`--output` 必须不存在。

```bash
python3 tools/export_results.py --source /absolute/path/to/density-bench --output /tmp/density-results-publication
python3 tools/render_charts.py /tmp/density-results-publication
```

提取流程只读取原归档并写新目录；没有 Docker、平台 API、SSH 或删除调用。
本目录的报告与索引是人工维护文档，绘图脚本只生成校正版图。
