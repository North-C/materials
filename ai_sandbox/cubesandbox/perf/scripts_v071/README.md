# CubeSandbox v0.7.1 · Template c100n100 时间轴工具

面向 192.168.25.90 的官方 ARM64 v0.7.1：并发 100、正式请求 100、串行预热 3 次，sandbox-code Template 为 2 vCPU / 2048 MiB / 1G 可写层。保留现有服务与配置，采集日志增量和 Prometheus 快照；只清理本轮专用模板下有归属证据的实例。

- [旧 scripts_v2 准确性审计](AUDIT_V2.md)
- [v0.7.1 Template 启动阶段口径（含同步、并行、异步与计时覆盖流程图）](STAGES.md#启动流程与计时覆盖关系)
- [2026-10-12 原版实测报告](../reports/v071-c100n100-20261012/REPORT.md)
- [网络微秒补解析与精细观测报告（重测待独占窗口）](../reports/v071-c100n100-fine-20261012/REPORT.md)
- [2026-10-14 优化版＋NUMA0 实测与更细拆解报告（第三份）](../reports/v071-c100n100-optimized-20261014/REPORT.md)
- [三份报告统一索引](../README.md)

## 文件与依赖

| 文件 | 作用 |
| --- | --- |
| `run_verified.py` / `verify_target.py` | 核验发布清单、实际运行二进制、进程身份、空资源、模板资源与 Master 并发；包围一次采集 |
| `capture.py` | 新目录采集日志增量、前后 metrics、1秒宿主机采样；检测 inode、截断、行边界和大小上限 |
| `run_single_case.py` | SHA256 固定已部署 suite 和官方 cube-bench，严格只执行 c100n100，保留原门禁、归属账本和清理 |
| `classify_phases.mjs` | 依据完整 Master 请求/响应、成功预热、账本和稳定身份，证明正式100/预热3；失败保留 unknown |
| `analyze.mjs` | 输出 JSON、阶段 CSV、逐实例 CreateContainer 详情、覆盖率、结果状态和同实例 Cubelet 残差 |
| `metrics.mjs` | 逐标签 counter/histogram 前后差分、重置检测、桶分位估计；Gauge 单列快照变化 |
| `timeline.mjs` | 输出逐实例 `timeline.json`、可筛选的离线 `timeline.html`，仅画有边界证据的 Shim 局部时间轴 |
| `network_details.mjs` | 解析已有网络Go duration，输出ns统计及缺失/0语义、逐实例字段 |
| `precision.mjs` / `precision_timeline.mjs` | 解析观测版Cubelet span与Shim纳秒计时，分时钟画图，回填duration仅列表 |
| `observation.patch` | v0.7.1源码补丁；CUBE_PERF_TRACE=1开启，默认关闭；需单独构建部署 |
| `reference/deployed-suite/` | 固定 suite 的执行、汇总与门禁代码，供复核和离线测试；来源与 hash 见 `source.json` |

采集端需要 Linux、Python 3.9+、已安装的 CubeSandbox Python SDK（套件功能预检使用）、fuser、可访问本机部署的 root 权限。分析端需要 Node.js 18+。脚本不安装依赖、不重新编译 cube-bench。`--suite-dir` 推荐指向 90 机器已部署的完整 suite；这里只打包 c100n100 所需的 Python 文件，没有打包官方二进制或其他压测案例。

版本固定为 `31d911e430fdf8a8879bd062b8e78066c1a8e89d`。官方 cube-bench SHA256：

```text
d7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d
```

## 在 90 机器执行

先确保专用 Template READY、由 sandbox-code 构建且规格正确；它在整个测试窗口内仅供本任务使用。2026-10-12 实测模板为 `tpl-cf2b04fdd4604b7c84e157fa`，构建请求和镜像 digest 保存在实测结果中。不要把历史模板 ID 当作永久有效配置。

在部署机器上运行，`--output` 必须是尚不存在的目录，其父目录须已创建：

```bash
python3 run_verified.py \
  --output /data/cubelet/perf-evidence/v071-c100n100-NEW/capture \
  --suite-dir /data/cubelet/perf-evidence/20261010T112540Z/suite \
  --benchmark-binary /data/cubelet/perf-evidence/20261010T112540Z/suite/cube-bench-v071-linux-arm64 \
  --template-id tpl-cf2b04fdd4604b7c84e157fa
```

流程是静默门禁 → 1个功能预检实例并清理 → 再次静默门禁 → 官方 `cube-bench -c 100 -n 100 -w 3 -m create-only --no-tui` → 清理本轮最多103个实例 → 身份复核。功能预检执行 `print('cube-bench-ready')`；正式100个实例的指标是 HTTP Create，不逐个执行应用代码压测。

门禁要求连续5次负载/运行时/TAP/磁盘检查通过；原 suite 内存容量预估按其已有空闲实例预算，`verify_target.py`另行核验2u2g模板和Master并发100。现有沙箱、外来模板实例、身份变化、失败清理或门禁超时会使本轮失败。失败输出应保留；换新目录重试，不覆盖历史证据。采集成功不等于压测成功：同时核对 `adapter-status.json`、`suite-results/report.json`、删除账本及 `verified-run.json`。

## 离线分析

将完整 capture 目录复制到分析端后：

```bash
node classify_phases.mjs CAPTURE
node analyze.mjs CAPTURE \
  --phase-classification CAPTURE/phase-classification.json \
  --details-out CAPTURE/create-container-details.jsonl > CAPTURE/analysis.json
node timeline.mjs CAPTURE --phase-classification CAPTURE/phase-classification.json
```

分类器输出 `classified` 才能传入 `--phase-classification`。它不修改原始 `owned-sandbox-ids.json`。若输出 `unverified`，不传分类文件运行 analyze/timeline，结果单独列 unknown_phase，不能将其称为正式请求分布。分类器不建立官方 raw `seq` 与 Sandbox ID 的对应关系。

`analysis.json` 含 formal、warmup、unknown_phase 三组，所有时间单位为毫秒；分位数采用 nearest rank。`stage-latency.csv` 包含父子关系、覆盖率、成功/失败/未知数量；正式 API 只统计成功且时长有效的 raw 样本。Cubelet/Master 成功码200（兼容OK=0），Shim为 `Ok`。同实例残差只对唯一成功记录配对，不减总体P95。

独立 metrics 分析：

```bash
node metrics.mjs CAPTURE/evidence/metrics-before.prom CAPTURE/evidence/metrics-after.prom
```

这些快照覆盖整个采集区间，包括预检、预热和清理；不能自动归属于正式100请求。Histogram保留原单位；吞吐量 histogram 不是 latency。Summary分位不做差。缺系列默认不补零；重置/非法/非单调数据不输出可信均值或分位；桶分位明确是估计及范围。

## 必须保留的观测限制

1. Cubelet成功且小于5ms的stat可不输出，缺失不是零。部分覆盖阶段的分布只描述已观测记录。
2. Cubelet在请求结束后批量异步写Trace，日志时间戳不能反推阶段终点；Shim stat无时间戳，只能列duration。时间轴只画明确marker，累计时钟起点与host日志起点近似对齐。
3. network/storage等同step并行；sandbox-start包含sandbox-create；CreatePodSandbox包含VM/Agent阶段；Master Probe是传播副本。不能把所有阶段相加。
4. 本机若未启用Master stat，保留missing标记，不改部署配置以补数据。日志轮转、截断、超限同样报告缺口。
5. `create_ms`在HTTP `client.Do`返回后计时，通常到响应头，不包含后续读body/解码；它不等价于独立验证所有应用功能就绪。
6. 原始请求日志可能包含环境或访问凭据。实测报告只发布筛选后的结果和原始文件哈希，完整日志留在采集目录。

## 离线验证

```bash
python3 -m unittest discover -s . -p 'test_*.py' -q
node --test test_*.mjs
```

测试覆盖归属和串行边界、实际200/Ok结果码、缺失/重复/乱序日志、metrics重置/桶结构、部分时间轴、runner单项选择与账本清理。测试不访问部署，不把模拟通过当作实测成功。

## 可选精细观测（v0.7.1+perftrace）

已有原版capture无需改部署即可运行：

```bash
node network_details.mjs CAPTURE --phase-classification CAPTURE/phase-classification.json
```

网络输出`network-details.json/csv`，单位ns；原版日志受各自父阶段1ms门槛控制，0累加器不等同零时延，重复记录排除统计。实际覆盖率始终保留。

观测版补丁在干净v0.7.1上应用，编译细节与依赖来源见细分报告。开启与关闭应使用相同二进制，开启变量须通过Cubelet服务环境传递给Shim。Template会优先使用`component_versions/cube-shim/v0.7.1`组件路径，部署不能只替换全局shim；应以实际运行进程exe和环境验收。`run_verified.py`不会部署或重启服务。

部署且验真后，在原运行命令追加`--observation-manifest observation-on.json`或`observation-off.json`。清单必须包含schema_version=1、固定base_commit、patch_sha256、mode和两个patched组件的sha256/commit；身份文件和分类证据显式保留它。关闭模式仍是重编译的观测版，不冒充官方原版。

```bash
node precision.mjs CAPTURE --phase-classification CAPTURE/phase-classification.json
node precision_timeline.mjs CAPTURE/precision.json
```

精细输出单位ns。Cubelet按kind/stage区分action与metric，批次覆盖单独核验；duration_backfill无精确起止。Shim按ClockId/OperationId区分调用，累计点只有同operation唯一且递增时才差分。两类时钟独立展示，不跨进程相减。`DroppedRecordsBefore=0`不能单独证明无尾部丢失，需检查完整覆盖与源日志缺口。

第二份报告的细分数值来自原 capture 网络补解析；perftrace 观测版已构建通过，但其重测仍未完成。第三份报告另行归档了优化版＋NUMA0 的实际 c100n100 结果，该构建没有新增 perftrace 端点，不能作为观测版重测结果。不要把解析单测或合成viewer检查当作c100n100性能结果。
