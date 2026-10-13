#!/usr/bin/env python3
"""Rebuild the report from the published, credential-free analysis artifacts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
analysis = json.loads((ROOT / "analysis.json").read_text())
formal = analysis["phases"]["formal"]
raw = json.loads((ROOT / "c100n100.raw.json").read_text())
timelines = json.loads((ROOT / "timeline.json").read_text())


def table(rows):
    lines = ["| 阶段 | 覆盖 | Avg ms | P50 ms | P95 ms | Max ms |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, stats, total in rows:
        if stats:
            lines.append(f"| {name} | {stats['count']}/{total} | " + " | ".join(f"{stats[k]:.3f}" for k in ("avg", "p50", "p95", "max")) + " |")
        else:
            lines.append(f"| {name} | 0/{total} | 缺失 | 缺失 | 缺失 | 缺失 |")
    return "\n".join(lines)


def stages(section, names):
    return [(name, formal[section][name]["stats"], 100) for name in names]


rows = [("客户端 HTTP Create", analysis["benchmark"]["create"], 100)]
rows += stages("cubemaster_stages", ["cube-e2e"])
rows += stages("cubelet_stages", ["cubebox-service", "cubebox", "sandbox-start", "sandbox-create", "sandbox-probe"])
rows += stages("shim_stages", ["CreatePodSandbox", "LaunchVmm", "RestoreVm", "ResetVm", "CreateSandbox", "CreateContainer"])
partial_rows = stages("cubelet_stages", ["network", "storage", "cgroup", "create-sandbox-metadata", "gen-spec-sandbox"])
residual_rows = stages("cubelet_residuals", ["service_outside_cubebox", "sandbox_after_newtask", "cubebox_outside_task_and_probe"])
detail_rows = [
    (name, formal["create_container_detail"]["timings"][name]["stats"], 100) for name in
    ("vm_start_to_agent_ready", "sandbox_finish_cumulative", "sandbox_to_container_finish", "guest_receive_to_restore_branch")]
warm = analysis["phases"]["warmup"]
warm_rows = [("warmup Cubelet service", warm["cubelet_stages"]["cubebox-service"]["stats"], 3),
             ("warmup Shim CreatePodSandbox", warm["shim_stages"]["CreatePodSandbox"]["stats"], 3)]
representative = sorted((r for r in formal["create_container_detail"]["details"] if r["create_request_total_ms"] is not None),
                        key=lambda r: r["create_request_total_ms"])[49]
rid = representative["instance_id"]
timeline = next(x for x in timelines["instances"] if x["instance_id"] == rid)
events = "\n".join(f"| {e['id']} | {e['relative_ms']:.3f} | {e['clock_domain']} |" for e in timeline["events"] if e["relative_ms"] is not None)

text = f"""# CubeSandbox v0.7.1：90机器 Template c100n100 阶段时延

本轮正式请求 **100/100 成功、0错误**。客户端 Create **平均 {analysis['benchmark']['create']['avg']:.2f} ms，P50 {analysis['benchmark']['create']['p50']:.2f} ms，P95 {analysis['benchmark']['create']['p95']:.2f} ms，最大 {analysis['benchmark']['create']['max']:.2f} ms**。正式批次总时长 **{raw['summary']['total_time_s'] * 1000:.3f} ms**，吞吐 **{raw['summary']['throughput_qps']:.2f} req/s**。本报告是一轮真实测量，不是多轮置信区间或版本回归结论。

## 测试条件与验收

- 日期：2026-10-12；90机器记录的官方报告时间为 `{raw['timestamp']}`。采集窗口 `{analysis['capture']['started_at']}` 至 `{analysis['capture']['ended_at']}`。目录名使用控制机时间；不将控制机与90机器的绝对时钟混减。
- 目标：192.168.25.90，Linux ARM64，双路 Kunpeng 950 7592C，192物理核/384逻辑CPU、4 NUMA节点，约2.21 TiB内存；宿主kernel `6.6.0-9999.sp3.vnmi.xarray.d383a36d`。运行时配置使用 `cubecow`，`force_wfi_trap=Y`、`halt_poll_ns=500000`。详见 [environment.json](environment.json)。
- API：node-local `http://127.0.0.1:3000`；官方 cube-bench 参数 `-c 100 -n 100 -w 3 -m create-only --no-tui`。本轮没有重编译或修改被测服务、关闭日志或重启服务。
- 运行版本：v0.7.1，commit `31d911e430fdf8a8879bd062b8e78066c1a8e89d`。CubeAPI、CubeMaster、Cubelet、TemplateCenter的运行进程二进制SHA256与发布清单相符，前后PID/start_ticks/boot ID相同；Shim二进制与发布清单一致，runtime SHA256另存于环境文件。
- Template：`tpl-cf2b04fdd4604b7c84e157fa`，**2 vCPU / 2048 MiB / 1G可写层**；使用已有READY本机副本。来源 `cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code@sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d`，构建job `7c6f7d99-1a97-4b47-ade5-ce07bb3a57f4`。这是 Template restore 测试，不含模板构建/镜像下载时间。[构建请求、返回job/template及READY核验](template-build-provenance.json)
- Master并发限制100。两次静默门禁均通过：连续5次检查，TAP Ready=4000，无KVM持有者、运行时task或外部沙箱，负载和磁盘余量满足原门槛。
- 套件先创建1个功能预检实例执行Python，再清理并重过门禁；之后3次串行预热+100正式请求。本轮日志共104组创建，**正式100、预热3、独立预检1**，绝未把104混成正式样本。
- suite状态 `complete`、adapter成功、归属账本 `drained`；正式/预热103个实例已清理，最终API sandbox数0。前后服务身份稳定。[验收](verified-run.json)、[账本](c100n100.delete.json)

客户端 `create_ms` 的起点在构造HTTP请求前，终点在 `client.Do` 返回时，通常是收到响应头；不含后续body读取和JSON解码耗时。虽然正式100次Create均成功并通过模板既有readiness probe，本指标不是逐个应用功能执行测试；功能执行仅由独立预检验证。

## 正式100请求：主阶段

下面各行均覆盖相同100个正式实例，API raw和Sandbox ID没有逐条映射。除客户端计时外，组件记录成功状态全部核验通过。**各行有嵌套、累计或跨组件关系，不能相加；也不能把两行P95相减。** P50/P95使用nearest-rank，与工具CSV一致。

{table(rows)}

调用关系：`HTTP → Master → Cubelet workflow → cubebox → sandbox-start（含NewTask）→ Shim CreatePodSandbox（含VM恢复、Agent RPC和CreateContainer）`，随后Cubelet执行readiness probe。前置工作流为：`[createid, appsnapshot] → [images, volume, storage, network, netfile, cube-sandbox-store] → [cgroup] → [cubebox]`；同一方括号内并行。配置已从运行中Cubelet使用的文件核验。

## 前置与细分阶段：必须连同覆盖率读取

{table(partial_rows)}

Cubelet成功且耗时小于5ms时会省略stat，部分深层helper另有门槛。这些不足100条的Avg/P50/P95仅代表已输出日志的条件分布，可能偏向慢样本。缺失不补零，也不将所有缺失一概判定为小于5ms。network与storage在同一并行step，cgroup位于下一step，不在cubebox内部。

## 同实例配对残差

先按Sandbox ID验证同一次成功调用且每个阶段仅一条，再逐实例计算差值，最后求统计，绝非总体P95相减。

{table(residual_rows)}

- `service_outside_cubebox = cubebox-service - cubebox`：服务窗口中位于cubebox之外的工作，主要包括前置workflow，也可能含收尾；不等同于一个连续的纯调度阶段。
- `sandbox_after_newtask = sandbox-start - sandbox-create`：同一taskStart起点，NewTask完成后至Wait/Start及随后状态处理结束。
- `cubebox_outside_task_and_probe = cubebox - sandbox-start - sandbox-probe`：spec/metadata及其他非连续工作残差。

本轮平均耗时的定位重点是：**NewTask累计窗口154.27ms、cubebox之外的服务工作98.41ms、probe40.92ms**。cgroup已观测92条中平均60.15ms、最大190.16ms；network已观测77条中P95为121.14ms，值得继续观察。Shim CreatePodSandbox平均77.54ms，RestoreVm18.26ms、CreateContainer19.88ms，现有证据不支持“全部耗时由VM恢复或Guest容器创建单点造成”。NewTask与Shim覆盖边界不同，本报告不把跨进程总体差值命名为某个实测子阶段。锁竞争、调度、文件系统或CPU等具体因果仍需要新增细粒度计时/采样才能区分。

`cubebox-service-inner`源码派生平均281.49ms、P95 387.69ms，减去probe和images/volume，不是纯Cubelet overhead；Master `sandbox-probe`与`all-probe`平均40.47ms，是Cubelet probe的整数毫秒传播副本，不重复计入。

## 可验证的部分时间轴

全部100正式实例均匹配Template `snapshot-restore` 分支；103个正式+预热实例的核心Shim marker完整、无重复、无顺序异常。

{table(detail_rows)}

打开 [timeline.html](timeline.html) 可筛选formal/warmup及实例ID；下载后可直接离线打开。蓝色使用host日志墙钟，橙色使用Shim单调时钟累计值，二者起点近似对齐。没有终点证据的stat只列duration，不伪造位置。Cubelet异步批量stat时间绝不用于反推阶段终点。

示例选择正式实例按Shim请求时长排序的第50个（不是API P50对应实例）：`{rid}`。它的核心边界相对`create req start`如下：

| 边界 | 相对位置 ms | 时钟 |
| --- | ---: | --- |
{events}

`VM start → agent ready`包含VM恢复和Agent连接，**不含随后执行的ResetVm**。`sandbox_finish_cumulative`是累计位置，不是新增可加阶段。Guest recv→restore branch只有98/100：两个recv的嵌套JSON日志缺少开头括号，作为缺失处理；不是Guest没有执行。该窗口仅到restore分支选择，后续passfd/日志恢复、锁和exec没有完整细分timer。不要把剩余时间直接称为`start_exec_process`耗时。

## metrics与缺口

Prometheus前后快照成功、无counter reset或解析问题，但区间约70.56秒，包含门禁、功能预检、预热、正式创建和清理，不能归为0.496秒正式窗口。

- `chi_cubebox_image_forward_latency_milliseconds`：Δcount=0，本轮无该转发耗时样本。
- `cube_cubebox_image_host_pulling_throughput_mib_per_sec`：Δcount=0；它本身也是吞吐量而非时延。
- `containerd_gc_gc_seconds`：Δcount=1，Δsum约0.00008535秒。是采集区间内GC数据，不是Template启动阶段。
- scheduler等Gauge仅保存前后变化，不能从快照恢复过程峰值。1秒host采样也不足以分辨本轮小于0.5秒的正式请求峰值。
- `/data/log/CubeMaster/cubemaster-stat.log`在采集前后均不可用；没有开启该观测配置来改变基线，因此Master调度、Redis/spec后处理保留缺失。其余7个日志增量均无轮转、截断或超限。Guest两条嵌套JSON损坏属于内容缺口，独立于外层JSONL/文件完整性。

现有metrics不能补齐Cubelet小于5ms的阶段，也不能补出完整Guest restore子阶段。因此交付的是**主阶段时延分布 + 有起止证据的局部时间轴 + 明示缺口**。

## 预热与交付文件

{table(warm_rows)}

正式与预热由固定官方runner先3次串行后100并发的代码约定、完整Master请求/响应、稳定服务身份、专用模板归属账本和功能预检排除共同证明。分类结果重新绑定当前源文件SHA256；不能修改标签后继续套用旧分类。[分类证据](phase-classification.json)

- [新版工具和复现步骤](../../scripts_v071/README.md)、[旧脚本审计](../../scripts_v071/AUDIT_V2.md)、[固定v0.7.1源码口径](../../scripts_v071/STAGES.md)
- [官方原始100条结果](c100n100.raw.json)、[完整分析JSON](analysis.json)、[阶段CSV](stage-latency.csv)、[逐实例细节](create-container-details.jsonl)
- [部分时间轴HTML](timeline.html)、[时间轴数据](timeline.json)、[采集manifest](capture-manifest.json)、[原始证据SHA256索引](evidence-index.json)

完整原始日志保存在90机器 `/data/cubelet/perf-evidence/bottleneck-v071-20261012T141529Z/capture`，以及分析工作区同名capture目录。请求日志可能包含凭据或环境，未直接提交到公共仓库；公开结果是筛选后的派生数据及原始文件hash。`build_report.py`可由已发布JSON重建本文；运行分析器需要完整私有capture。
"""
(ROOT / "REPORT.md").write_text(text)
print(ROOT / "REPORT.md")
