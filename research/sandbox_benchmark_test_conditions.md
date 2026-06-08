# AI 沙箱中的 CPU Benchmark 测试条件与环境收敛

## 目标

本文件在前一版 `cpu_focused_benchmark_filter.md` 的基础上继续收敛：面向 Kata / E2B / Firecracker / Docker 等 AI 沙箱环境，筛选适合用 Fixed Output 和 Replay Trajectory 模式执行的 benchmark，并给出统一测试条件。

本轮目标不是评估模型能力，而是评估 CPU 负载特征、沙箱执行开销、并发吞吐、资源隔离和本地 evaluator 性能。因此需要进一步降低大模型推理、实时网络、LLM Judge 和主观评分的影响。

## 一、测试执行模式定义

| 模式 | 说明 | 大模型影响 | 适合用途 |
|---|---|---|---|
| Full Agent | 完整运行 Agent，让模型自主规划、执行、提交结果 | 高 | 端到端产品表现，不作为 CPU 主测 |
| Fixed Output | 固定 Agent 产物，只运行本地评测阶段 | 低 | 测 evaluator、测试脚本、容器、文件 IO |
| Replay Trajectory | 重放一次记录好的命令、文件操作和工具调用轨迹 | 很低 | 测 harness、进程调度、工具运行、日志开销 |
| Hybrid Replay | 重放主要轨迹，但允许少量本地分支，例如失败后重跑测试 | 中低 | 更接近真实 Agent，但仍能控制变量 |

本报告建议 CPU 主测优先使用：

1. Fixed Output
2. Replay Trajectory
3. Hybrid Replay

Full Agent 只作为补充，不进入 CPU 性能结论的主数据。

## 二、沙箱环境特征

| 沙箱 | 优点 | 风险/限制 | 适合 benchmark |
|---|---|---|---|
| Docker | 启动快、生态成熟、镜像复用方便、最适合批量 benchmark | 隔离弱于 VM，宿主机内核共享，安全边界较弱 | SWE-bench、Terminal-bench、DSBench、MLE-bench、AlphaEval 子集 |
| Firecracker | 微 VM 隔离强，冷启动成本可控，适合严肃隔离测试 | 镜像制作和网络/磁盘配置复杂，GUI 支持弱 | 代码、终端、数据处理、无 GUI evaluator |
| Kata Containers | 容器接口 + VM 隔离，便于从 Docker 迁移 | 启动慢于 Docker，部分文件系统/网络语义需验证 | Docker 可运行任务的安全增强版本 |
| E2B | 面向 AI agent 的托管沙箱，易集成代码执行和会话 | 托管环境变量多，底层资源不可完全控制，长期性能数据需谨慎解释 | 代码执行、轻量数据任务、Agent 轨迹 replay |

结论：

- CPU 基线与可重复性：优先 Docker。
- 隔离开销对比：Docker vs Kata vs Firecracker。
- AI 产品形态验证：E2B 可作为现实部署参考，但不建议作为唯一性能基准。
- GUI/Web benchmark：Docker 最容易落地；Firecracker/Kata 需要额外验证浏览器、Xvfb、Playwright、字体和系统依赖。

## 三、统一测试条件

### 1. CPU 与内存

| 参数 | 建议 |
|---|---|
| CPU 配额 | 固定 1c、2c、4c、8c 四档 |
| CPU pinning | 使用固定 core set，避免跨 NUMA 或调度漂移 |
| SMT/超线程 | 记录开启状态；关键实验建议分别测 SMT on/off |
| 频率 | 尽量固定 governor，例如 performance；记录 turbo 状态 |
| 内存 | 固定 4GB、8GB、16GB 三档，按 benchmark 分层 |
| swap | 主测关闭或固定配置，避免结果不可解释 |

### 2. 文件系统与镜像

| 参数 | 建议 |
|---|---|
| 镜像 | 固定 digest，不用 floating tag |
| 依赖 | 预构建基础镜像，单独记录 cold install 与 warm run |
| 工作目录 | 每次任务新建干净目录 |
| 缓存 | 区分 cold cache 与 warm cache，两者不要混合 |
| 日志 | 统一采集 stdout/stderr、trace、resource metrics |

### 3. 网络

| 参数 | 建议 |
|---|---|
| 主测网络 | 默认禁用外网 |
| 依赖下载 | 预下载或镜像内置 |
| Web 任务 | 使用本地服务或固定 mock server |
| API 调用 | Fixed/Replay 模式下禁用模型 API |

### 4. 并发

| 档位 | 建议 |
|---|---|
| 单任务 | 获取单 benchmark 负载画像 |
| N=CPU 核数 | 测满载吞吐 |
| N=2x CPU 核数 | 测超卖与排队 |
| 混合负载 | 代码 + 数据 + GUI/Web 组合，观察资源争用 |

### 5. 采集指标

| 类别 | 指标 |
|---|---|
| 时间 | wall time、user time、sys time、task queue time |
| CPU | per-core utilization、CPU throttling、run queue |
| 调度 | context switch、process/thread count |
| IO | read/write bytes、IOPS、IO wait、文件数量 |
| 内存 | RSS、page fault、cache、OOM |
| 沙箱 | boot/start time、teardown time、image pull/load time |
| Benchmark | evaluator time、test time、trace size、artifact size |

## 四、Benchmark 进一步筛选结论

### 主测集

| Benchmark | 推荐模式 | 推荐沙箱 | 保留原因 | 注意事项 |
|---|---|---|---|---|
| Terminal-bench | Replay Trajectory / Fixed Output | Docker、Kata、Firecracker | CLI、进程、文件系统、容器负载清晰 | 需要固定命令轨迹，避免模型规划差异 |
| SWE-bench | Fixed Output / Replay Trajectory | Docker、Kata、Firecracker | patch 应用、测试执行、repo IO 可重复 | 优先使用已知 patch 或固定 diff |
| DSBench | Fixed Output / Replay Trajectory | Docker、Kata、E2B | 数据处理脚本 CPU 特征明显 | 固定数据集和脚本，禁用外网 |
| MLE-bench CPU 子集 | Fixed Output / Replay Trajectory | Docker、Kata、Firecracker | 训练/评测脚本可产生稳定 CPU 负载 | 只选 CPU-only、短中时长任务，排除 GPU 重任务 |
| AlphaEval 规则化子集 | Fixed Output / Replay Trajectory | Docker、Kata | 生产型任务、规则 evaluator、多格式文件 | 只保留低 LLM Judge 任务 |

主测集用于形成 CPU 性能结论。

### 条件扩展集

| Benchmark | 推荐模式 | 推荐沙箱 | 条件 |
|---|---|---|---|
| OSWorld | Replay Trajectory | Docker 优先，Kata/Firecracker 需验证 | 只有在 GUI/Xvfb/截图栈可稳定运行时保留 |
| WebArena | Replay Trajectory / Fixed State | Docker | 使用本地 Web 服务和固定动作序列，禁用实时外网 |
| AppWorld | Replay Trajectory | Docker、E2B | 适合测 app 状态验证和工具执行，但不进入主结论 |
| OfficeQA / OdysseyBench | Replay Trajectory | Docker 或桌面 VM | 依赖办公软件环境，部署成本高 |
| BFCL | Fixed Output | Docker、E2B | 只作为轻量 orchestration baseline |
| MCP-Universe | Replay Trajectory | Docker、E2B | 固定 MCP server 和工具调用序列后可用 |

扩展集用于补充 GUI/Web/工具编排负载，不建议与主测集混合计算总分。

### 暂缓或剔除

| Benchmark | 处理 | 原因 |
|---|---|---|
| AlphaEval HR | 剔除 | 主观判断强，CPU 信号弱 |
| AlphaEval Technology Research | 剔除 | 强依赖实时搜索、模型综合和 LLM Judge |
| AlphaEval Finance 长报告任务 | 剔除 | LLM Judge 和主观评分占比高 |
| BrowseComp / BrowseComp-V3 | 剔除 | 搜索策略和外网状态主导 |
| MMLU / GPQA / FrontierMath / AIME | 剔除 | 主要测模型推理，不测 CPU 执行 |
| PaperBench / CORE-Bench | 暂缓 | 任务长且依赖复杂，可后续做稳定性压力测试 |
| AgentLAB / STING / Unsafer | 剔除 | 安全行为评估，不适合 CPU 主测 |
| MemoryArena / Collective Behavior | 剔除 | 多 Agent 交互变量过多 |

## 五、各主测 Benchmark 的具体测试条件

### 1. Terminal-bench

推荐定位：终端/命令行沙箱 CPU 基准。

| 项目 | 建议 |
|---|---|
| 主模式 | Replay Trajectory |
| 备用模式 | Fixed Output |
| 沙箱 | Docker -> Kata -> Firecracker |
| 网络 | 禁用 |
| 资源档 | 1c/2c/4c/8c，4GB/8GB |
| 任务选择 | 选择无外网依赖、可确定验证的任务 |
| 采集重点 | shell 命令耗时、进程数、context switch、文件 IO、容器启动时间 |

执行建议：

1. 先用 Full Agent 产生一次成功轨迹。
2. 清理模型调用，只保留命令序列、文件变更和测试步骤。
3. 后续统一 replay，比较不同沙箱和 CPU 配额。

### 2. SWE-bench

推荐定位：代码仓库测试执行 CPU 基准。

| 项目 | 建议 |
|---|---|
| 主模式 | Fixed Output |
| 备用模式 | Replay Trajectory |
| 沙箱 | Docker -> Kata -> Firecracker |
| 网络 | 禁用；依赖预装或镜像内置 |
| 资源档 | 2c/4c/8c，8GB/16GB |
| 任务选择 | 优先选择测试耗时 30 秒到 10 分钟的实例 |
| 采集重点 | 测试执行、编译、依赖加载、repo 文件 IO |

执行建议：

1. 使用固定 patch，不让模型实时生成。
2. 分开统计 patch apply、test setup、test execution、result parse。
3. 单独保留 failed patch 组，用于测试失败路径的 evaluator 开销。

### 3. DSBench

推荐定位：数据分析脚本 CPU/内存/IO 基准。

| 项目 | 建议 |
|---|---|
| 主模式 | Fixed Output |
| 备用模式 | Replay Trajectory |
| 沙箱 | Docker、Kata、E2B |
| 网络 | 禁用 |
| 资源档 | 1c/2c/4c/8c，4GB/8GB/16GB |
| 任务选择 | 表格处理、聚合、特征工程、统计分析任务 |
| 采集重点 | pandas/numpy CPU、内存峰值、page fault、数据读写 |

执行建议：

1. 固定输入数据和分析脚本。
2. 避免需要大模型判断图表或报告质量的任务。
3. 把数据加载、处理、输出、评分拆段计时。

### 4. MLE-bench CPU 子集

推荐定位：CPU-only ML 工程基准。

| 项目 | 建议 |
|---|---|
| 主模式 | Fixed Output |
| 备用模式 | Replay Trajectory |
| 沙箱 | Docker、Kata、Firecracker |
| 网络 | 禁用 |
| 资源档 | 2c/4c/8c，8GB/16GB |
| 任务选择 | 小中型 tabular、classical ML、轻量训练任务 |
| 排除 | 大 GPU 训练、超长训练、外部数据下载任务 |
| 采集重点 | 训练耗时、CPU 利用率、内存带宽、评测脚本耗时 |

执行建议：

1. 固定 baseline solution，不让 Agent 实时调参。
2. 限制训练时间和线程数，例如 `OMP_NUM_THREADS`、`MKL_NUM_THREADS`。
3. 记录 sklearn/xgboost/lightgbm 等库的线程行为。

### 5. AlphaEval 规则化子集

推荐定位：生产型混合负载基准。

| 子集 | 建议 |
|---|---|
| Procurement & Operations | 保留，优先级最高 |
| Software Engineering | 保留，使用固定代码产物和 UI/E2E 测试 |
| Healthcare 数值任务 | 保留，剔除政策分析和 LLM Judge |
| Finance 结构化抽取 | 保留，剔除投资长报告和 pitch critique |
| HR | 剔除 |
| Technology Research | 剔除 |

推荐模式：

| 模式 | 用法 |
|---|---|
| Fixed Output | 固定 `results/` 中的答案文件，只运行 `.eval/rubric.py` |
| Replay Trajectory | 重放文件读取、表格处理、测试执行和结果生成流程 |

采集重点：

- rubric.py 执行耗时
- Excel/CSV/PDF 解析耗时
- UI/E2E 测试耗时
- Docker/Kata 启动和文件挂载成本
- evaluator 在并发下的吞吐

## 六、推荐最终收敛版本

### V1：最小稳定主测集

| Benchmark | 模式 | 沙箱 |
|---|---|---|
| Terminal-bench | Replay Trajectory | Docker、Kata |
| SWE-bench | Fixed Output | Docker、Kata |
| DSBench | Fixed Output | Docker、Kata |
| AlphaEval P&O 子集 | Fixed Output | Docker、Kata |

用途：快速建立 CPU 负载画像，适合先跑通监控、指标采集和横向对比。

### V2：完整 CPU 主测集

| Benchmark | 模式 | 沙箱 |
|---|---|---|
| Terminal-bench | Replay Trajectory | Docker、Kata、Firecracker |
| SWE-bench | Fixed Output + Replay | Docker、Kata、Firecracker |
| DSBench | Fixed Output | Docker、Kata |
| MLE-bench CPU 子集 | Fixed Output | Docker、Kata、Firecracker |
| AlphaEval 规则化子集 | Fixed Output + Replay | Docker、Kata |

用途：形成主要 CPU 性能结论。

### V3：扩展验证集

| Benchmark | 模式 | 沙箱 |
|---|---|---|
| OSWorld | Replay Trajectory | Docker GUI 环境 |
| WebArena | Replay Trajectory | Docker 本地 Web 环境 |
| AppWorld | Replay Trajectory | Docker、E2B |
| BFCL / MCP-Universe | Fixed Output / Replay | Docker、E2B |

用途：补充 GUI/Web/工具编排负载，不纳入主分数。

## 七、推荐目录与产物结构

建议每个 benchmark 按相同目录结构保存：

```text
benchmark-runs/
  terminal-bench/
    tasks/
    fixed_outputs/
    trajectories/
    metrics/
    reports/
  swe-bench/
    patches/
    trajectories/
    metrics/
    reports/
  alphaeval-subset/
    fixed_outputs/
    trajectories/
    metrics/
    reports/
```

每次运行至少保存：

```text
run.json
resource_metrics.csv
stdout.log
stderr.log
trace.jsonl
artifacts/
score.json
```

`run.json` 建议字段：

```json
{
  "benchmark": "swe-bench",
  "task_id": "example",
  "mode": "fixed_output",
  "sandbox": "kata",
  "cpu_limit": 4,
  "memory_limit_gb": 8,
  "network": "disabled",
  "image_digest": "sha256:...",
  "start_time": "...",
  "end_time": "...",
  "result": "pass"
}
```

## 八、最终建议

在 Kata / E2B / Firecracker / Docker 中进行 CPU benchmark 时，不建议直接采用完整 Agent benchmark 原始流程。更合理的方式是把 benchmark 拆成可控的本地执行阶段：

1. Fixed Output 测 evaluator、测试脚本、文件 IO、容器开销。
2. Replay Trajectory 测工具链、shell、进程调度、日志和实际操作轨迹。
3. Full Agent 只用于生成轨迹和补充现实端到端观察。

最终推荐收敛为：

```text
主测集：
Terminal-bench
SWE-bench
DSBench
MLE-bench CPU 子集
AlphaEval 规则化子集

扩展集：
OSWorld
WebArena
AppWorld
BFCL / MCP-Universe

剔除/暂缓：
纯问答、数学推理、实时搜索、强主观评分、安全红队、多 Agent 记忆协作类 benchmark
```
