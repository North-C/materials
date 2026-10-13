"""Create a Chinese Markdown summary from one suite run's original results."""

import argparse
import json
import re
from pathlib import Path


SECTION_NAMES = {
    "3.2": "Template 创建", "3.3": "在线密度", "4.1": "Snapshot 并发",
    "4.2": "脏页与 Snapshot 恢复", "4.3": "从 Snapshot 创建", "4.4": "回滚并发",
    "4.5": "克隆并发", "4.6": "暂停/恢复并发",
}

# These columns are emitted by the original benchmark scripts, in this order.
LOG_COLUMNS = {
    "4.1": ("concurrency", "rounds", "wall_avg", "wall_min", "wall_p95", "wall_max", "per_avg"),
    "4.2": ("write_MB", "dirty_MB_avg", "snap_avg", "snap_min", "snap_p95", "snap_max",
            "create_avg", "create_min", "create_p95", "create_max"),
    "4.3": ("concurrency", "n_total", "rounds", "wall_avg", "wall_min", "wall_p95", "wall_max", "per_avg"),
    "4.4": ("concurrency", "rounds", "wall_avg", "wall_min", "wall_p95", "wall_max", "per_avg"),
    "4.5": ("n", "conc", "rounds", "wall_avg", "wall_min", "wall_p95", "wall_max", "per_avg"),
    "4.6": ("concurrency", "rounds", "pause_avg", "pause_min", "pause_p95", "pause_max",
            "per_pause", "resume_avg", "resume_min", "resume_p95", "resume_max", "per_resume"),
}


def cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def number(value, digits=1):
    return f"{float(value):.{digits}f}"


def link(name, folder):
    return f"[{cell(name)}]({name})" if (folder / name).is_file() else "缺失"


def log_stats(path, section):
    if not path.is_file():
        return None
    expected = LOG_COLUMNS[section]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if tuple(line.split()) != expected:
            continue
        for row in lines[index + 1:]:
            parts = row.split()
            if len(parts) == len(expected) and all(re.fullmatch(r"-?\d+(?:\.\d+)?", part) for part in parts):
                return dict(zip(expected, (float(part) for part in parts)))
    return None


def summarize(report, folder):
    commands = report.get("commands", [])
    complete = sum(record.get("status") == "complete" for record in commands)
    lines = ["# CubeSandbox 核心性能测试结果", "",
             f"- 运行 ID：`{cell(report.get('run_id', '未知'))}`",
             f"- 执行状态：**{cell(report.get('status', '未知'))}**；已完成 {complete}/{len(commands)} 档",
             f"- 测试配置：`{cell(report.get('profile', '未知'))}`；章节：{cell(', '.join(report.get('sections', [])))}",
             f"- 3.1 Guest 预检：{'通过' if report.get('preflight') == 'passed' else '失败' if report.get('preflight') == 'failed' else '未记录'}。",
             f"- 基准脚本来源修订：`{cell(report.get('source_revision', '未知'))}`",
             "- 原始记录：[report.json](report.json)；数值均来自原始 JSON 或各档日志，未重新测量。", ""]
    if report.get("metric_scope"):
        lines.extend([f"- **计时口径：{cell(report['metric_scope'])}。**",
                      "- 原生 `create_ms` 止于 HTTP 响应，不含平台就绪；此报告不是 V1.20 创建耗时。",
                      "- `warm` 轮仅作预热，不纳入正式 A/B 统计；失败后未发请求的停止行为也不满足 V1.20。", ""])
    if report.get("error"):
        lines.extend([f"**运行失败原因：** {cell(report['error'])}", ""])
    preparation = report.get("dirty_workload_preparation")
    if preparation:
        lines.extend(["## 脏页负载准备口径", "",
                      f"- 工具分类：{cell(preparation.get('tool_category', '未记录'))}。",
                      f"- Guest shm 目标：{cell(preparation.get('shm_size_mib'))} MiB；"
                      f"写入块：{cell(preparation.get('write_chunk_mib'))} MiB（None 表示未启用该选项）。",
                      f"- 脚本 SHA256：`{cell(preparation.get('script_sha256', '未记录'))}`。",
                      "- 准备在计时前完成，但会改变快照时的Guest内存状态；不得与不同准备方式静默合并。",
                      "- 快照/恢复计时与预热未改；原始日志保留挂载、容量及实际写入回执。", ""])
    capacity = report.get("capacity", {})
    if capacity.get("max_live_sandboxes"):
        lines.extend(["## 容量预检", "",
                      f"- 预计峰值存活沙箱：{capacity['max_live_sandboxes']}；空载预算："
                      f"{capacity.get('idle_vm_mib', '?')} MiB × {capacity.get('idle_memory_factor', '?')}。",
                      f"- Master 创建并发基准：{capacity.get('master_create_baseline', '未检查')}。"])
        if capacity.get("node_available_kib"):
            for host, kib in capacity["node_available_kib"].items():
                lines.append(f"- `{cell(host)}` 预检可用内存：{number(kib / 1024 / 1024, 2)} GiB。")
        for warning in capacity.get("warnings", []) + capacity.get("blockers", []):
            lines.append(f"- 提示：{cell(warning)}")
        lines.append("")

    lines.extend(["## 测试明细", "",
                  "| 章节 | 档位 | 状态 | 指标 | 平均 / 值 | P95 | 补充 | 原始数据 |",
                  "| --- | --- | --- | --- | ---: | ---: | --- | --- |"])
    for record in commands:
        section, label, status = (record.get(key, "") for key in ("section", "label", "status"))
        name = f"{section}-{label}.log"
        evidence = link(name, folder)
        prefix = [cell(f"{section} {SECTION_NAMES.get(section, '')}"), cell(label), cell(status)]

        def add(metric, avg="-", p95="-", extra="-", source=evidence):
            lines.append("| " + " | ".join(prefix + [metric, str(avg), str(p95), cell(extra), source]) + " |")

        if status != "complete":
            add("未执行" if status == "unexecuted" else "未完成")
            continue
        if section == "3.2":
            data_name = f"{label}.json"
            data_path = folder / data_name
            if not data_path.is_file():
                add("统计数据缺失")
                continue
            try:
                data = json.loads(data_path.read_text(encoding="utf-8"))
                stats, summary = data["create"], data["summary"]
                metric = ("原生 HTTP 创建延迟 (ms，预热)" if record.get("phase") == "warm" else
                          "原生 HTTP 创建延迟 (ms)" if report.get("metric_scope") else
                          "创建延迟 (ms)")
                extra = (f"成功 {summary['successful']} / {summary['successful'] + summary['errors']}；"
                         f"吞吐 {number(summary['throughput_qps'], 2)} 次/s")
                if report.get("metric_scope"):
                    extra += (f"；P50 {number(stats['p50'])}；P99 {number(stats['p99'])}；"
                              f"MAX {number(stats['max'])}；整轮 {number(summary['total_time_s'], 3)} 秒")
                source = link(data_name, folder)
                if report.get("metric_scope"):
                    source += "；" + link(f"{label}.delete.json", folder)
                add(metric, number(stats["avg"]), number(stats["p95"]), extra, source)
            except (ValueError, KeyError, TypeError):
                add("统计数据无效", source=link(data_name, folder))
        elif section == "3.3":
            points = report.get("density", [])
            if not points:
                add("密度采样缺失", source="[report.json](report.json)")
            for point in points:
                add(f"累计 {point['count']} 个；单实例内存变化 (MiB)",
                    number(point["per_vm_kib"] / 1024, 2),
                    extra=f"节点合计可用 {number(point['available_kib'] / 1024 / 1024, 2)} GiB",
                    source="[report.json](report.json)")
        elif section in LOG_COLUMNS:
            stats = log_stats(folder / name, section)
            if stats is None:
                add("统计行缺失或格式不符")
                continue
            if section == "4.2":
                add("Snapshot 延迟 (ms)", number(stats["snap_avg"]), number(stats["snap_p95"]),
                    f"负载写入 {number(stats['write_MB'])} MiB；内存快照实际写入 {number(stats['dirty_MB_avg'])} MiB")
                add("恢复创建延迟 (ms)", number(stats["create_avg"]), number(stats["create_p95"]))
            elif section == "4.6":
                add("暂停整批墙钟 (ms)", number(stats["pause_avg"]), number(stats["pause_p95"]))
                add("恢复整批墙钟 (ms)", number(stats["resume_avg"]), number(stats["resume_p95"]))
            else:
                extra = f"每实例摊销 {number(stats['per_avg'])} ms（非逐请求均值）"
                if "rounds" in stats:
                    extra += f"；{int(stats['rounds'])} 轮"
                add("整批墙钟耗时 (ms)", number(stats["wall_avg"]), number(stats["wall_p95"]), extra)
    if not commands:
        lines.append("| - | - | 未开始 | 无测试数据 | - | - | - | [report.json](report.json) |")
    lines.extend(["", "注：3.3 的单实例内存变化由各节点 `MemAvailable` 差值估算，不代表进程 RSS。"
                  "4.1/4.3/4.4/4.5/4.6 的分位数来自整批墙钟样本，不是逐请求分位数。"
                  "失败或缺失数据的档位不得用于性能结论。", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path, help="directory containing report.json")
    args = parser.parse_args()
    folder = args.result_dir
    report = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    output = folder / "report.md"
    output.write_text(summarize(report, folder), encoding="utf-8")
    print(f"report: {output}")


if __name__ == "__main__":
    main()
