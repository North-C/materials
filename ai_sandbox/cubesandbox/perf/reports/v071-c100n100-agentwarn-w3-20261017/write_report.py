#!/usr/bin/env python3
"""Render the local report from validated saved summary; no target access."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
s = json.loads((root / 'result-summary.json').read_text())
formal = [r for r in s['rounds'] if r['state'] == 'formal']
pilot = next(r for r in s['rounds'] if r['state'] == 'pilot')
rows = '\n'.join(f"| {i} | {r['total_ms']:.3f} | {r['avg_ms']:.3f} | {r['p50_ms']:.3f} | {r['p95_ms']:.3f} | {r['p99_ms']:.3f} | 100/100 | 103 |" for i, r in enumerate(formal, 1))
stage_by_name = {x['stage']: x for x in s['stage_summary']}
names = ['CubeMaster/cube-e2e', 'Cubelet/cubebox-service', 'Cubelet/cubebox',
    'Cubelet/sandbox-start', 'Cubelet/sandbox-create', 'CubeShim/CreatePodSandbox',
    'Cubelet/sandbox-probe', 'CreateContainer detail/vm_start_to_agent_ready',
    'CubeShim/ResetVm', 'CubeShim/RestoreVm', 'CubeShim/CreateContainer', 'CubeShim/LaunchVmm',
    'Cubelet/network', 'Cubelet/cgroup', 'Cubelet/storage']
stage_rows = []
for name in names:
    x = stage_by_name[name]
    value = f"{x['median_of_round_means_ms']:.3f}" if x['median_of_round_means_ms'] is not None else '缺失'
    old = f"{x['baseline_median_of_round_means_ms']:.3f}" if x['baseline_median_of_round_means_ms'] is not None else '缺失'
    if name == 'Cubelet/network' and old != '缺失':
        old += '（仅 3/5 轮有记录）'
    coverage = str(x['min_observed_per_round']) if x['min_observed_per_round'] == x['max_observed_per_round'] else f"{x['min_observed_per_round']}–{x['max_observed_per_round']}"
    stage_rows.append(f"| {name} | {value} | {coverage}/103 | {old} |")
links = '\n'.join(f"- 第 {i} 轮：[HTML 阶段报告]({r['run']}/analysis/report.html) · [时间轴]({r['run']}/analysis/timeline.html) · [原始 JSON]({r['run']}/capture/startup-latency/benchmark.raw.json) · [清理回执](formal/{r['round']}/evidence/cleanup.json)" for i, r in enumerate(formal, 1))
delta = s['formal_total_ms_median'] - s['baseline_total_ms_median']
text = f'''# .90 调优工作区方法复测：agentwarn 模板 / c100n100 / 同进程 w3

测试日期：2026-10-17。依据用户指定的「.90 · c100n100 性能调优」workspace，以其新模板和测试方法重新执行。机器保持当前部署和系统参数，本次不重启、不部署、不调整优化开关。

## 结果

**5 轮正式测试共 500/500 请求成功，整轮耗时中位数 {s['formal_total_ms_median']:.3f} ms，范围 {s['formal_total_ms_min']:.3f}–{s['formal_total_ms_max']:.3f} ms。**

| 正式轮次 | 整轮 ms | 请求平均 ms | P50 ms | P95 ms | P99 ms | 成功 | 清理实例 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
{rows}

按指南先执行 1 轮 pilot，整轮 **{pilot['total_ms']:.3f} ms**，100/100 成功；pilot 不参与以上中位数或正式结果汇总。每次调用还有同进程串行预热 3 次。共 6 次调用创建并清理 **{s['deleted_including_pilot']} 个实例**，均有逐 ID 删除回执；每轮清理 complete，连续两次库存为空。最终库存为 0 的验证见 `evidence/final-inventory.json`。

正式统计取各轮 `benchmark.raw.json → summary.total_time_s × 1000`。该值排除进程内预热，但包括正式请求调度与结果收集；不是单次请求最大值或平均值。各轮 P95 均为各自 100 个正式请求的分位数，未把轮间 P95 平均值冒充总体 P95。

## 本次严格沿用的方法与模板

- 参考工作区：`/Users/liuyuqing/orca/workspaces/CubeSandbox/c100n100-perf-tuning-90`。
- [原测试指南副本](reference/TESTING-GUIDE.zh-CN.md)、[手动测试说明副本](reference/manual-bench-README.zh-CN.md)已保存。
- `run_series.py`、`run_round_w3.py`、`capture_w3.py`、`state_snapshot.py` 从参考工作区逐字节复制，未修改。来源和 SHA 见 [方法来源](evidence/method-source.json)。本轮 `run_all.py` 仅准备独立目录、记录状态、调用原脚本。
- 每轮门禁：沙箱库存 0，无 cube-bench/CubeShim，load1 < 4；连续 3 次通过、间隔 5 秒；轮后 cooldown 10 秒。负载较高时按原门禁等待，未降低阈值。部分正式轮之前发生过额外负载等待，进度记录见 `pilot/progress.log`、`formal/progress.log`。任何实际测试失败则停止，不挑选重跑。
- 模板：**`tpl-381852bfe518c30bb815e163`**，即调优工作区默认 `agentwarn` 模板；测试前 READY。
- 规格：2 vCPU / 2048Mi / 1G 可写层，ext4，rootfs `rfs-dd2b6baa7183b8077c714eb9-e5190241`；HTTP `/health:49999`，period 500ms、单次超时 2000ms、总超时 30000ms。
- 容器注解：`io.cubesandbox.vm.kernel.cmdline.append=["agent.log=warn"]`。这是相对于旧模板的明确配置差异。见 [模板快照](evidence/template-current.json)。
- cube-bench 来源：`.90:/data/cubelet/c100n100-perf-tuning-90/20261016T104049Z/bin/cube-bench`；本次复制到独立目录 `bin/cube-bench`，未编译或改动。
- 固定 SHA256：`ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511`。这是调优系列使用的 master 构建，历史构建记录表明 bench 源码与 v0.7.1 相同；不是先前 `d7d76854…` 二进制。
- 配置 `warmup=0` 仅禁用 profiler 的独立预热；`capture_w3.py` 明确给 cube-bench 传 **`-w 3`**，3 次预热与正式请求共享客户端。

```sh
cube-bench -c 100 -n 100 -w 3 -m create-only -no-tui \\
  -t tpl-381852bfe518c30bb815e163 -o <每轮 benchmark.raw.json>
```

每轮 command.log 已核验 `-no-tui`，原始 JSON 中 concurrency=100、total=100、warmup=3；无 dry-run。

## 新瓶颈观察

**已测量的服务端主要窗口仍为 sandbox-start / sandbox-create、Shim CreatePodSandbox，以及健康探测。** 下表对各轮已观测到的阶段均值取中位数，便于与调优工作区 s13 的相同方法比较。全覆盖核心阶段均有 5 轮；缺失轮不补零，历史 network 仅 3/5 轮有记录。

重要口径：客户端正式结果为每轮 100 条；CLI 只能确认本次新增的 103 个实例集合。服务端阶段均为 **unknown_phase 103（3 预热 + 100 正式混合）**，没有把前 3 条日志强行归为预热，也没有伪造 formal 100 个实例的映射。

| 阶段 | 本次：轮均值的中位数 ms | 本次每轮覆盖范围 | 历史 s13：轮均值的中位数 ms |
| --- | ---: | ---: | ---: |
{chr(10).join(stage_rows)}

应优先沿任务创建链路继续分解 VM 启动到 agent ready、ResetVm/RestoreVm/CreateContainer，并检查探测的尾延迟。上述阶段存在包含、累计及跨组件关系，不能相加构造整体耗时。客户端正式 100 与服务端混合 103 是不同群体，不能相减后声称获得某段请求耗时。

`agent.log=warn` 使 guest INFO 细分锚点减少：第 1 轮 `guest_receive_to_restore_branch` 为 0/103、路径分类 unknown 103/103。缺失不等于操作未发生或耗时为零。network、cgroup、storage 等短成功日志另受阈值抑制，低覆盖统计只是条件分布。更细根因需要追加明确 span；本次参考方法没有启用 CPU/perf 或周期主机采样，不能据此判断 CPU/IO 饱和、锁争用等根因。

## 与历史及上一轮的关系

调优工作区 s13 的 5 轮整轮中位数为 **{s['baseline_total_ms_median']:.3f} ms**；本次相差 **{delta:+.3f} ms（{delta / s['baseline_total_ms_median'] * 100:+.2f}%）**。历史数字由原始 JSON/CSV 复算，保存于 [基线摘要](reference/s13-baseline-summary.json)。

模板、cube-bench SHA 和同进程 w3 方法与 s13 一致，但当前机器并非当时全部优化状态：

| 项目 | 历史 s13 | 当前 |
| --- | --- | --- |
| 内核 | 6.6.0-9999.sp3.vnmi.xarray.d383a36d | 6.6.0-with-softdirty+ |
| THP enabled / defrag | never / never | never / madvise |
| rcu_expedited | 1 | 0 |
| /run/cube-perf/snap_madv_random | 存在、启用 | 不存在 |
| Shim 文件 SHA | 67d8d06a…614cbad | 相同 |

相同 Shim 二进制不等于相同运行时开关。当前状态见 [前快照](evidence/state-before.json)、[后快照](evidence/state-after.json)、[优化开关](evidence/optimization-flags.json)。本次没有为贴近历史结果而打开开关。

先前本会话的 **414.373 ms** 轮使用旧模板 `tpl-cf2b…`、独立 c1n3 预热、正式 `-w 0` 和 `d7d76854…` 客户端。本次同时改变模板、预热方式及客户端构建，不能把差异单独归因于模板或日志级别；本次应作为按指定调优方法取得的新结果。

## 证据完整性与交付

- 每轮采集/分析/清理完成、100 个正式请求成功、CLI 集合 103 已核验；服务 PID 与运行文件 SHA 在各轮前后稳定。
- 7 路可读日志增量哈希验证通过；实际缺少 `master_stat`。manifest 的 `ownership_phase_unknown`、`owned_counts_differ_from_declared_workload` 对应上述 103 混合归属限制，不是 100 个正式请求失败。
- 原始日志、metrics、每轮 HTML/CSV/JSON/时间轴、逐 ID 清理回执和执行脚本均保留。metrics 属于端点全局采集区间，不是某个实例的独占数据。
- [机器可读结果](result-summary.json) · [逐轮 CSV](round-summary.csv) · [阶段对比 CSV](stage-comparison.csv) · [验收记录](evidence/validation.json) · [SHA256SUMS](SHA256SUMS)

{links}

本地目录：`{root}`。

远端目录：`.90:/root/{root.name}/`。报告和原始数据两处保存；含 API 密钥的配置仅留在远端私有目录，不打包回传，不推送外部仓库。
'''
(root / 'RESULT_REPORT.md').write_text(text)
print(root / 'RESULT_REPORT.md')
