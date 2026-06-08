# SWE-bench CPU 性能基准工具设计

## 目标

当前目标不是评估 LLM 是否能修复 issue，而是利用 SWE-bench 中真实软件工程任务的本地执行负载，构建一个面向 CPU 服务、沙箱运行时和测试执行链路的性能分析基准工具。

工具应把 SWE-bench 实例转换成可重复、可离线、可分阶段计时和可横向比较的 workload。最终要回答的问题是：

1. 不同 CPU 配额、内存配额和沙箱运行时下，代码仓库测试类负载的性能差异有多大。
2. 不同任务类型、依赖重量、测试数量和运行时长，对 CPU、内存、文件 IO、进程调度和启动开销的影响是什么。
3. 在没有实时模型请求的前提下，如何稳定复现 agent coding workload 的本地执行部分。
4. 同一批 SWE-bench 任务能否形成 smoke、short、medium、long、heavy dependency 等多档基准。

## 非目标

首轮不做以下事情：

1. 不实时调用 LLM，不比较模型解题能力。
2. 不让模型动态生成 patch，不把 patch 质量作为核心指标。
3. 不追求完整覆盖 SWE-bench Full。
4. 不把 Django、浏览器、多服务、数据库 backend 等复杂环境作为 v0 主线。
5. 不用单一总分掩盖负载差异，优先输出分阶段指标和资源画像。

SWE-bench 的 `FAIL_TO_PASS` / `PASS_TO_PASS` 结果只用于确认 fixed patch 或 replay 是否正确，不代表模型能力评分。

## 核心运行模式

### 1. Fixed Patch

固定 SWE-bench 官方 `patch`，执行：

1. checkout `repo + base_commit`
2. 应用 `test_patch`
3. 应用固定 `patch`
4. 运行目标测试
5. 解析 `FAIL_TO_PASS` / `PASS_TO_PASS`
6. 输出资源指标和确定性 pass/fail

这是 v0 主模式。它最适合隔离测试执行、依赖加载、repo IO 和沙箱开销。

### 2. Broken Patch / Negative Case

只应用 `test_patch`，不应用修复 patch，或应用一个预定义失败 patch。

用途：

- 验证 evaluator 能正确识别失败路径
- 观察失败测试的耗时和日志规模
- 避免所有样本都走 pass 路径导致负载单一

### 3. Replay Trajectory

固定一段命令轨迹，例如：

1. checkout repo
2. inspect 文件
3. apply patch
4. run subset tests
5. rerun failed tests
6. collect result

v1 再加入该模式。它用于模拟 agent 工具调用链路，但仍不调用模型。

### 4. Test Only

预构建好 repo、依赖和 patch 后，只重复运行测试阶段。

用途：

- 分离沙箱启动和测试执行
- 观察测试 runner、import、编译缓存、临时文件 IO
- 做高并发吞吐测试

## 负载分层

工具需要把任务按负载特征分层，而不是只按 repo 名称分层。

| 负载层 | 目标时长 | 主要特征 | 典型来源 |
|---|---:|---|---|
| smoke | 5-30 秒 | patch 小、F2P 少、依赖轻 | `requests`, 小型 `sympy` |
| short | 30-90 秒 | 测试路径明确，P2P 中等 | `sympy`, `pylint`, `xarray` |
| medium | 90 秒-5 分钟 | 测试框架或科学库加载明显 | `pytest`, `sphinx`, `astropy` |
| long | 5-15 分钟 | P2P 较多或测试重复放大 | `pytest`, `scikit-learn`, `matplotlib` |
| heavy dependency | 不固定 | import/依赖加载重，环境噪声更高 | `scikit-learn`, `matplotlib`, `seaborn` |
| negative path | 不固定 | 失败测试、异常日志、evaluator 失败路径 | 任意 repo 的 no-patch 运行 |

v0 不应强行追求 15 分钟以上任务。长负载可以通过以下方式构造：

1. 选择 P2P 较多的实例。
2. 固定重复运行测试阶段 `repeat=N`。
3. 对同一 repo 运行多个 instance batch。
4. 在资源受限档位下运行，例如 1c/2GB 或 2c/4GB。

## 输入

### 1. 任务清单

建议使用 YAML 或 JSONL 固定任务列表。

```yaml
version: swe-cpu-v0
dataset: SWE-bench_Verified
tasks:
  - instance_id: sympy__sympy-12481
    repo: sympy/sympy
    base_commit: "<sha>"
    workload_class: smoke
    mode: fixed_patch
    expected_result: pass
    f2p_count: 1
    p2p_count: 7
    patch_source: dataset
    test_patch_source: dataset
    timeout_seconds: 300
    repeat: 1
```

任务清单必须是版本化产物，不能在每次运行时动态筛选。

### 2. 数据集元数据

从 SWE-bench Verified 固定以下字段：

- `repo`
- `instance_id`
- `base_commit`
- `patch`
- `test_patch`
- `FAIL_TO_PASS`
- `PASS_TO_PASS`
- `environment_setup_commit`
- `difficulty`

这些字段应缓存到本地，避免运行时访问网络。

### 3. 环境描述

每个 repo 应有环境配置：

```yaml
repo: sympy/sympy
image: swe-cpu/sympy:py310-v0
python: "3.10"
install:
  strategy: prebuilt_image
  offline: true
test:
  command_template: "python -m pytest {test_targets} -q"
  env:
    PYTHONWARNINGS: default
    OMP_NUM_THREADS: "1"
```

环境描述需要记录镜像 digest、Python 版本、系统包、pip wheelhouse 版本和测试命令模板。

### 4. 运行矩阵

运行矩阵描述资源档和沙箱运行时：

```yaml
runtimes:
  - runc
  - kata
resources:
  - cpus: 1
    memory: 2g
  - cpus: 2
    memory: 4g
  - cpus: 4
    memory: 8g
repeats: 3
network: disabled
```

v0 建议先使用：

- runtime: `runc`, `kata`
- CPU: `1c`, `2c`, `4c`
- memory: `2GB`, `4GB`, `8GB`
- repeats: `3`
- network: disabled

## 输出

每次运行生成一个 run directory：

```text
runs-swe-cpu/<run_id>/
  run.json
  task.json
  metrics.csv
  phase_metrics.json
  stdout.log
  stderr.log
  test_output.log
  score.json
  patches/
    fix.patch
    test.patch
  artifacts/
```

### run.json

记录一次运行的不可变上下文：

```json
{
  "benchmark": "swe-cpu",
  "version": "v0",
  "run_id": "2026-05-19T120000Z_sympy__sympy-12481_runc_2c",
  "instance_id": "sympy__sympy-12481",
  "repo": "sympy/sympy",
  "base_commit": "<sha>",
  "mode": "fixed_patch",
  "runtime": "runc",
  "cpu_limit": 2,
  "memory_limit": "4g",
  "network": "disabled",
  "image": "swe-cpu/sympy:py310-v0",
  "image_digest": "sha256:<digest>",
  "result": "pass",
  "start_time": "...",
  "end_time": "..."
}
```

### phase_metrics.json

分阶段记录耗时和资源：

```json
{
  "phases": {
    "sandbox_start": {"wall_ms": 820},
    "repo_prepare": {"wall_ms": 1450},
    "apply_test_patch": {"wall_ms": 120},
    "apply_fix_patch": {"wall_ms": 95},
    "test_execution": {"wall_ms": 18420},
    "result_parse": {"wall_ms": 80},
    "artifact_collect": {"wall_ms": 210}
  }
}
```

### metrics.csv

用于批量分析的扁平指标：

```text
run_id,instance_id,repo,workload_class,runtime,cpus,memory,phase,wall_ms,user_ms,sys_ms,max_rss_kb,read_bytes,write_bytes,voluntary_ctxt,involuntary_ctxt,exit_code
```

### score.json

只表达确定性验证结果：

```json
{
  "result": "pass",
  "fail_to_pass": {"passed": 1, "total": 1},
  "pass_to_pass": {"passed": 7, "total": 7},
  "unexpected_failures": [],
  "timed_out": false
}
```

## 指标体系

### 必采指标

| 指标 | 用途 |
|---|---|
| wall time | 用户可见耗时和吞吐 |
| user/system CPU time | 区分用户态测试执行和内核/IO 开销 |
| CPU utilization | 观察配额利用率 |
| max RSS | 内存峰值 |
| read/write bytes | repo checkout、测试缓存、日志 IO |
| context switches | 进程调度和沙箱开销 |
| exit code / timeout | 稳定性 |
| stdout/stderr size | 日志放大和失败路径成本 |

### 可选指标

| 指标 | 用途 |
|---|---|
| cgroup CPU throttling | 判断 CPU quota 是否成为瓶颈 |
| page faults | 观察依赖加载和内存压力 |
| process count | pytest、编译、子进程行为 |
| file count touched | repo/test IO 面 |
| cold/warm cache 标记 | 区分首次运行和重复运行 |
| guest/host split | Kata/Firecracker 中区分 VM 内外开销 |

## 构建流程

### 阶段 0：任务冻结

输入：

- `swe_bench_task_filter_v0.md`
- 官方 SWE-bench Verified 元数据

输出：

- `configs/swe-cpu/tasks-smoke.yaml`
- `configs/swe-cpu/tasks-main.yaml`
- `configs/swe-cpu/tasks-heavy.yaml`

要求：

1. 每个任务必须固定 `instance_id` 和 `base_commit`。
2. 任务清单保存 F2P/P2P 数量、patch 行数、test patch 行数和 workload class。
3. 不在运行时重新筛选任务。

### 阶段 1：repo 和依赖准备

每个 repo 构建一个预装依赖镜像或 rootfs：

```text
images/
  swe-cpu-requests/
  swe-cpu-sympy/
  swe-cpu-pylint/
  swe-cpu-pytest/
  swe-cpu-sphinx/
  swe-cpu-xarray/
  swe-cpu-scikit-learn/
  swe-cpu-astropy/
  swe-cpu-matplotlib/
```

原则：

1. 网络只允许在 image build 阶段使用。
2. benchmark run 阶段禁网。
3. Python wheels 固定版本并缓存。
4. 系统包和 Python 版本进入 image manifest。

### 阶段 2：单实例 runner

实现 `run_swe_task.py`：

```text
run_swe_task.py
  --task-config configs/swe-cpu/tasks-smoke.yaml
  --instance-id sympy__sympy-12481
  --runtime runc
  --cpus 2
  --memory 4g
  --mode fixed_patch
  --output-root runs-swe-cpu
```

runner 需要分段执行：

1. 创建 sandbox
2. 准备 repo workspace
3. checkout base commit
4. 应用 test patch
5. 应用 fix patch 或 negative patch
6. 运行 F2P/P2P 测试
7. 解析结果
8. 采集 artifacts 和 metrics

### 阶段 3：批量矩阵 runner

实现 `run_swe_matrix.py`：

```text
run_swe_matrix.py
  --task-config configs/swe-cpu/tasks-main.yaml
  --runtime runc,kata
  --resources 1c2g,2c4g,4c8g
  --repeats 3
  --mode fixed_patch
```

功能：

1. 展开任务、runtime、资源档和 repeat。
2. 支持失败重试，但重试必须单独标记。
3. 支持并发运行，但默认先串行保证可解释性。
4. 每个 run 独立目录，避免结果覆盖。

### 阶段 4：汇总与报告

输出：

- `summary.csv`
- `summary_by_task.csv`
- `summary_by_runtime.csv`
- `summary_by_workload_class.csv`
- `report.md`

报告至少包含：

1. 每个任务的 pass/fail/timeout。
2. 每个阶段耗时占比。
3. runc vs Kata 的 wall time、CPU time、RSS、IO 对比。
4. 资源档扩展性，例如 1c -> 2c -> 4c。
5. 异常样本列表。

## 推荐目录结构

```text
agent_cpu_sandbox_toolkit/
  configs/
    swe-cpu/
      tasks-smoke.yaml
      tasks-main.yaml
      tasks-heavy.yaml
      repos.yaml
      matrix-v0.yaml
  tools/
    run_swe_task.py
    run_swe_matrix.py
    summarize_swe_cpu.py
  swe-bench-cache/
    metadata/
    patches/
    repos/
    wheels/
  runs-swe-cpu/
  reports/
```

如果短期不想改动 toolkit，也可以先在 research 目录生成上述 config 和设计文档，再迁移到 toolkit。

## v0 最小可交付

v0 应先交付一个小而稳定的工具闭环：

| 项目 | 要求 |
|---|---|
| 任务数 | 8-12 个 |
| repo | `requests`, `sympy`, `pylint`, `xarray` 优先 |
| runtime | runc + Kata |
| 资源档 | 1c/2GB, 2c/4GB |
| mode | fixed_patch + negative case |
| repeats | 3 |
| 输出 | run.json, phase_metrics.json, metrics.csv, score.json, summary.csv |

v0 成功标准：

1. 所有任务可离线运行。
2. fixed patch 的 F2P/P2P 结果可稳定复现。
3. negative case 能稳定失败并被 scorer 识别。
4. runc/Kata 同一任务可横向比较。
5. 每个阶段都有独立耗时。

## v1 扩展

v1 再加入：

1. `pytest`, `sphinx`, `scikit-learn`, `astropy`, `matplotlib` 等中重负载。
2. Replay Trajectory 模式。
3. Firecracker 或 cloud-hypervisor 路径。
4. cgroup throttling、page fault、process count 等更细指标。
5. 长负载构造：repeat、batch、多实例同 repo 串行运行。
6. 并发吞吐测试：固定 N 个 worker 压测 CPU 服务。

## 风险与约束

| 风险 | 影响 | 对策 |
|---|---|---|
| 旧 repo 依赖难安装 | 任务不可复现 | 每个 repo 固定镜像，优先 Verified 低噪声实例 |
| 测试选择不等于完整 SWE-bench harness | 和官方分数不可比 | 明确本工具只测 CPU workload，不发布模型分数 |
| patch apply 失败 | 任务失效 | 任务冻结阶段做预验证 |
| pytest 目标解析不稳定 | F2P/P2P 误判 | 保存原始测试输出和解析日志 |
| cache 影响结果 | 多次运行波动 | 标记 cold/warm，必要时清理 workspace |
| Kata/VM 内指标采集不足 | host/guest 难拆分 | v0 先采 host-side，v1 加 guest agent |

## 当前推荐推进顺序

1. 从 `swe_bench_task_filter_v0.md` 的 A 组里选 6-8 个任务，补 2-4 个 C 组任务。
2. 生成 `tasks-smoke.yaml` 和 `repos.yaml`。
3. 先实现本机或 runc fixed patch runner，不急着接 Kata。
4. 加入 phase metrics 和 score parser。
5. 批量跑 runc 形成 baseline。
6. 接入 Kata，对比启动开销、测试执行和 IO。
7. 再引入 D 组重负载。

这样构建出来的工具本质上是 SWE-bench-derived CPU workload benchmark，而不是 SWE-bench 模型评测器。
