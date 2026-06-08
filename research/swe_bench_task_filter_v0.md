# SWE-bench 无模型测试用例筛选 v0

## 目标

本文面向当前这条主线：参考 Terminal-Bench 的构建方式，为 SWE-bench 构造一批不依赖实时模型请求的本地测试用例，用于 CPU、文件系统、测试执行和沙箱开销分析。

这里的重点不是评估模型解题能力，而是把 SWE-bench 拆成可重复、可离线、可确定评分的本地执行负载：

1. 固定 `repo + base_commit`
2. 固定 `patch` 或固定变更轨迹
3. 固定 `test_patch`
4. 只运行 patch apply、测试执行、结果汇总和 verifier

本文的 `v0` 任务表，优先服务于：

- Fixed Patch / Fixed Output
- Replay Trajectory
- Docker / Kata / Firecracker 中的离线执行
- CPU 与 repo/test IO 负载分析

## SWE-bench 当前包含的内容

截至 2026-05-12，SWE-bench 官方文档列出的主要数据集变体如下：

| 数据集 | 规模 | 用途 |
|---|---:|---|
| SWE-bench Full | 2294 | 完整评估集，覆盖更广 |
| SWE-bench Lite | 534 | 更适合快速迭代和 smoke |
| SWE-bench Verified | 500 | 人工确认可解，适合作为正式主集 |
| SWE-bench Multimodal | 100 dev / 500 test | 含截图/UI，偏多模态 |
| SWE-bench Multilingual | 300 | 9 种语言、42 个仓库 |

对当前“无模型请求 + CPU 负载分析”的目标，推荐顺序是：

1. `SWE-bench Lite`：只做 runner 调通和 smoke。
2. `SWE-bench Verified`：作为正式 `v0` 主集来源。
3. `SWE-bench Full`：后续扩展，不进入首轮。
4. `Multimodal` / `Multilingual`：暂不纳入首轮。

原因很直接：

- `Verified` 的实例质量更稳定，适合构造固定 patch / 固定轨迹的离线回放。
- `Lite` 适合先验证 harness 和镜像，但它不是最适合当最终主集。
- `Multimodal` 会引入截图、前端 UI、浏览器和视觉依赖。
- `Multilingual` 会把 Python 单栈 repo 扩展成多语言、多构建系统、多依赖矩阵，环境噪声更大。

## 实例结构

官方数据集文档里，每个实例的核心字段包括：

- `repo`
- `instance_id`
- `base_commit`
- `problem_statement`
- `patch`
- `test_patch`
- `FAIL_TO_PASS`
- `PASS_TO_PASS`
- `environment_setup_commit`

`SWE-bench Verified` 还额外给出：

- `difficulty`

这套结构天然适合当前目标，因为它已经把“环境、目标修复、测试 oracle”拆开了。

## Verified 的 repo 分布

基于官方 `SWE-bench Verified` 元数据，500 个实例当前分布在 12 个 Python 仓库中：

| Repo | 实例数 |
|---|---:|
| `django/django` | 231 |
| `sympy/sympy` | 75 |
| `sphinx-doc/sphinx` | 44 |
| `matplotlib/matplotlib` | 34 |
| `scikit-learn/scikit-learn` | 32 |
| `astropy/astropy` | 22 |
| `pydata/xarray` | 22 |
| `pytest-dev/pytest` | 19 |
| `pylint-dev/pylint` | 10 |
| `psf/requests` | 8 |
| `mwaskom/seaborn` | 2 |
| `pallets/flask` | 1 |

这说明两件事：

1. 首轮完全没有必要追求 repo 覆盖“看起来平均”。
2. 更合理的做法是优先选纯 Python、测试链路清晰、依赖噪声低的 repo，再从中挑实例。

## 当前筛选口径

`v0` 先按下面的规则筛：

### 保留条件

1. 只选 `SWE-bench Verified`。
2. `difficulty` 限在 `<15 min fix` 和 `15 min - 1 hour`。
3. `FAIL_TO_PASS` 数量先控制在 `1-2`，最多不超过 `3`。
4. `PASS_TO_PASS` 先控制在 `5-100`，保留一定回归测试负载，但不引入极端长尾。
5. `patch` 和 `test_patch` 尽量小，便于后续做 fixed-patch replay。
6. 优先纯 Python 库问题，避免数据库、浏览器、前端构建、外部服务和系统级依赖。

### 暂缓条件

以下实例类型暂不进入 `v0`：

- `difficulty = >4 hours`
- 大量 `PASS_TO_PASS` 的极重回归集
- 标题或测试语义明显依赖数据库/服务端组件
- 明显需要浏览器、UI、截图或前端构建链
- 多语言、多运行时、多服务协同实例

## 为什么先少碰 Django

`django/django` 在 Verified 中占比最高，但不建议首轮直接把它当主力。

原因不是它不重要，而是：

- 部分问题会牵涉数据库、client binary、URL routing、模板、ORM 等多层环境差异。
- 同样是 Python repo，它的环境噪声比 `requests`、`sympy`、`pylint`、`xarray` 这类库更大。
- 对当前目标，repo/test/patch 负载应该尽量和“复杂服务环境”解耦。

因此 `v0` 先把 Django 作为补充观察对象，不作为第一批主集。

## v0 推荐任务清单

下面这批任务是当前最适合先落地为 no-LLM testcase 的候选。它们来自官方 `SWE-bench Verified` 元数据筛选，属于启发式 `v0`，后续仍需通过本地环境验证。

### A. Smoke 集

用途：先打通 repo checkout、patch apply、测试执行、结果汇总。

| Repo | Instance | Difficulty | F2P | P2P | Patch 行数 | Test Patch 行数 | 备注 |
|---|---|---|---:|---:|---:|---:|---|
| `psf/requests` | `psf__requests-1142` | `<15 min fix` | 1 | 5 | 20 | 18 | 依赖轻，适合最早打通 |
| `sphinx-doc/sphinx` | `sphinx-doc__sphinx-7889` | `<15 min fix` | 1 | 5 | 15 | 37 | 文档工具链，局部测试清晰 |
| `sympy/sympy` | `sympy__sympy-12481` | `<15 min fix` | 1 | 7 | 19 | 20 | 纯库逻辑，环境噪声低 |
| `sympy/sympy` | `sympy__sympy-16766` | `<15 min fix` | 1 | 7 | 16 | 24 | 纯 Python 代码路径 |
| `pylint-dev/pylint` | `pylint-dev__pylint-4970` | `<15 min fix` | 1 | 17 | 13 | 16 | CLI/tooling 负载清晰 |
| `scikit-learn/scikit-learn` | `scikit-learn__scikit-learn-13328` | `<15 min fix` | 1 | 9 | 14 | 66 | 测试链比 requests 略重 |
| `astropy/astropy` | `astropy__astropy-7166` | `<15 min fix` | 1 | 6 | 35 | 31 | 科学计算库路径 |
| `pydata/xarray` | `pydata__xarray-4629` | `<15 min fix` | 1 | 32 | 13 | 18 | pandas/xarray 风格数据路径 |

### B. Main 集

用途：作为 `v0` 主集，开始产生更稳定的 repo/test/IO/CPU 负载。

| Repo | Instance | Difficulty | F2P | P2P | Patch 行数 | Test Patch 行数 | 备注 |
|---|---|---|---:|---:|---:|---:|---|
| `psf/requests` | `psf__requests-2931` | `15 min - 1 hour` | 1 | 84 | 23 | 16 | 回归集更完整 |
| `sphinx-doc/sphinx` | `sphinx-doc__sphinx-8269` | `<15 min fix` | 1 | 5 | 12 | 73 | 测试 patch 稍大，但 repo 仍轻 |
| `pylint-dev/pylint` | `pylint-dev__pylint-6903` | `<15 min fix` | 1 | 8 | 18 | 59 | CLI/进程参数路径明显 |
| `pytest-dev/pytest` | `pytest-dev__pytest-6202` | `<15 min fix` | 1 | 72 | 14 | 40 | 测试框架自身回归负载 |
| `pytest-dev/pytest` | `pytest-dev__pytest-7432` | `<15 min fix` | 1 | 77 | 14 | 36 | 适合看 test runner 路径 |
| `scikit-learn/scikit-learn` | `scikit-learn__scikit-learn-13779` | `<15 min fix` | 2 | 18 | 13 | 42 | 数值库 + 测试链路 |
| `astropy/astropy` | `astropy__astropy-14539` | `15 min - 1 hour` | 2 | 46 | 13 | 73 | 科学库回归更完整 |
| `pydata/xarray` | `pydata__xarray-3151` | `15 min - 1 hour` | 1 | 66 | 26 | 30 | 数据处理路径更重 |
| `matplotlib/matplotlib` | `matplotlib__matplotlib-20676` | `<15 min fix` | 2 | 32 | 18 | 40 | 开始引入图形库测试 |
| `matplotlib/matplotlib` | `matplotlib__matplotlib-23412` | `15 min - 1 hour` | 1 | 46 | 16 | 45 | 适合作为更重一档 |

## v0.1 继续筛选

本轮按 `README.md` 中给出的 SWE-bench 迁移方向继续推进：先基于 `swe_bench_task_filter_v0.md` 的已有口径，仍然服务于 fixed patch / replay runner，而不是扩大到实时模型解题。

数据来源仍限定为官方 `SWE-bench Verified` 的 500 条实例。复核后，满足下面硬条件的候选共有 283 条：

- `difficulty` 为 `<15 min fix` 或 `15 min - 1 hour`
- `FAIL_TO_PASS` 为 `1-3`
- `PASS_TO_PASS` 为 `5-100`
- `patch` 和 `test_patch` 不属于极端大 diff
- 优先纯 Python 库路径，暂缓数据库、浏览器、前端构建、外部服务和系统级依赖

其中，排除明显高环境噪声标题或文件路径后，仍有约 197 条可继续做 metadata-level 筛选。下一步不建议一次性全纳入，而是分成“优先扩展集”和“偏重负载扩展集”。

### C. 优先扩展集

用途：在已有 Smoke/Main 集基础上扩充样本数量，但仍保持低环境噪声和较容易离线复现。该组优先用于 fixed patch runner 的第一轮批量验证。

| Repo | Instance | Difficulty | F2P | P2P | Patch 行数 | Test Patch 行数 | 备注 |
|---|---|---|---:|---:|---:|---:|---|
| `sympy/sympy` | `sympy__sympy-15345` | `<15 min fix` | 1 | 8 | 22 | 20 | 纯符号代码生成路径 |
| `sympy/sympy` | `sympy__sympy-21847` | `<15 min fix` | 1 | 9 | 21 | 37 | 多项式/monomial 逻辑，测试局部 |
| `sympy/sympy` | `sympy__sympy-22714` | `<15 min fix` | 1 | 11 | 12 | 23 | simplify/evaluate 路径，依赖轻 |
| `sympy/sympy` | `sympy__sympy-15017` | `<15 min fix` | 1 | 14 | 12 | 28 | array 长度边界行为 |
| `sympy/sympy` | `sympy__sympy-16450` | `<15 min fix` | 1 | 38 | 12 | 17 | assumptions 路径，回归集适中 |
| `sympy/sympy` | `sympy__sympy-19637` | `<15 min fix` | 1 | 40 | 14 | 11 | parser/locals 边界，patch 很小 |
| `sympy/sympy` | `sympy__sympy-18189` | `<15 min fix` | 1 | 41 | 12 | 25 | diophantine 逻辑，仍属纯库测试 |
| `sympy/sympy` | `sympy__sympy-16886` | `<15 min fix` | 1 | 42 | 12 | 12 | 编码表修正，patch/test 都小 |
| `pylint-dev/pylint` | `pylint-dev__pylint-6386` | `15 min - 1 hour` | 1 | 7 | 80 | 14 | CLI 参数解析路径，适合 runner 验证 |
| `pydata/xarray` | `pydata__xarray-3677` | `15 min - 1 hour` | 1 | 21 | 11 | 21 | Dataset/DataArray merge 路径 |
| `pydata/xarray` | `pydata__xarray-7393` | `15 min - 1 hour` | 2 | 71 | 17 | 14 | dtype/stack 逻辑，P2P 较完整 |
| `pytest-dev/pytest` | `pytest-dev__pytest-10081` | `<15 min fix` | 1 | 63 | 15 | 79 | unittest skip 交互，测试框架自身负载 |
| `pytest-dev/pytest` | `pytest-dev__pytest-7982` | `<15 min fix` | 1 | 78 | 12 | 27 | symlink collection，文件系统路径明显 |
| `pytest-dev/pytest` | `pytest-dev__pytest-10051` | `15 min - 1 hour` | 1 | 15 | 31 | 28 | caplog 状态清理，测试局部 |
| `pytest-dev/pytest` | `pytest-dev__pytest-7236` | `15 min - 1 hour` | 1 | 51 | 39 | 44 | unittest skip + pdb 路径 |
| `pytest-dev/pytest` | `pytest-dev__pytest-7324` | `15 min - 1 hour` | 3 | 58 | 34 | 11 | debug build 崩溃防护，F2P 达上限 |
| `sphinx-doc/sphinx` | `sphinx-doc__sphinx-9320` | `<15 min fix` | 1 | 9 | 25 | 30 | quickstart/conf.py，文档工具链局部 |
| `sphinx-doc/sphinx` | `sphinx-doc__sphinx-7910` | `<15 min fix` | 1 | 16 | 20 | 71 | autodoc 装饰器路径 |
| `sphinx-doc/sphinx` | `sphinx-doc__sphinx-8459` | `<15 min fix` | 1 | 17 | 12 | 32 | autodoc type hints 路径 |
| `sphinx-doc/sphinx` | `sphinx-doc__sphinx-9367` | `<15 min fix` | 1 | 25 | 19 | 14 | tuple 渲染边界，测试轻 |
| `sphinx-doc/sphinx` | `sphinx-doc__sphinx-10323` | `<15 min fix` | 1 | 40 | 15 | 23 | literalinclude 缩进行为 |

### D. 偏重负载扩展集

用途：在 runner 已稳定后引入更重的依赖加载、科学计算、绘图库或更完整回归测试。该组不建议早于 C 组进入首轮 smoke。

| Repo | Instance | Difficulty | F2P | P2P | Patch 行数 | Test Patch 行数 | 备注 |
|---|---|---|---:|---:|---:|---:|---|
| `scikit-learn/scikit-learn` | `scikit-learn__scikit-learn-13496` | `<15 min fix` | 1 | 19 | 34 | 32 | IsolationForest 参数路径 |
| `scikit-learn/scikit-learn` | `scikit-learn__scikit-learn-13135` | `<15 min fix` | 1 | 33 | 12 | 33 | KBinsDiscretizer/kmeans，数值测试 |
| `scikit-learn/scikit-learn` | `scikit-learn__scikit-learn-14894` | `15 min - 1 hour` | 1 | 85 | 23 | 23 | SVM 稀疏路径，P2P 较重 |
| `scikit-learn/scikit-learn` | `scikit-learn__scikit-learn-25931` | `15 min - 1 hour` | 1 | 21 | 44 | 25 | feature names + IsolationForest |
| `scikit-learn/scikit-learn` | `scikit-learn__scikit-learn-13142` | `<15 min fix` | 2 | 54 | 27 | 38 | GaussianMixture，F2P/P2P 都更重 |
| `astropy/astropy` | `astropy__astropy-12907` | `15 min - 1 hour` | 2 | 13 | 12 | 36 | modeling separability，科学库路径 |
| `astropy/astropy` | `astropy__astropy-14365` | `15 min - 1 hour` | 1 | 8 | 21 | 32 | ASCII/QDP 表解析 |
| `astropy/astropy` | `astropy__astropy-13453` | `15 min - 1 hour` | 1 | 9 | 17 | 53 | HTML table 输出，需验证依赖 |
| `astropy/astropy` | `astropy__astropy-8872` | `15 min - 1 hour` | 1 | 80 | 35 | 21 | quantity dtype 行为，P2P 较完整 |
| `matplotlib/matplotlib` | `matplotlib__matplotlib-22719` | `<15 min fix` | 1 | 68 | 21 | 19 | category units warning，绘图库轻入口 |
| `matplotlib/matplotlib` | `matplotlib__matplotlib-24637` | `15 min - 1 hour` | 1 | 29 | 19 | 46 | AnnotationBbox renderer 路径 |
| `matplotlib/matplotlib` | `matplotlib__matplotlib-26291` | `15 min - 1 hour` | 1 | 49 | 12 | 25 | inset axes，绘图依赖需后置验证 |
| `matplotlib/matplotlib` | `matplotlib__matplotlib-22865` | `15 min - 1 hour` | 3 | 57 | 18 | 34 | colorbar drawedges，F2P 达上限 |
| `mwaskom/seaborn` | `mwaskom__seaborn-3069` | `15 min - 1 hour` | 2 | 94 | 46 | 32 | seaborn 唯一可扩展候选，依赖偏重 |
| `pallets/flask` | `pallets__flask-5014` | `<15 min fix` | 1 | 59 | 13 | 15 | Flask Blueprint 校验，作为 Web 框架轻样本 |

### 仍暂缓的类型

继续暂缓以下对象：

1. `django/django` 大多数实例：即使 metadata 通过阈值，仍可能引入 ORM、数据库 backend、migration、template、admin、URL routing 等环境差异。Django 后续应单独开一个专题筛。
2. `PASS_TO_PASS > 100` 的实例：更适合长负载扩展，不适合当前 runner smoke。
3. `difficulty = 1-4 hours` 或 `>4 hours`：先不进入无模型 fixed patch 首轮。
4. 明确涉及浏览器、截图、前端构建、多服务启动或外部网络的实例。
5. test patch 大到难以快速审阅的实例：即使 F2P/P2P 合格，也先放到人工复核队列。

## v0 执行顺序

建议按这三步推进：

1. 先跑 Smoke 集中的 `requests / sympy / pylint / xarray`
2. 再补 `pytest / astropy / scikit-learn / sphinx`
3. 最后引入 `matplotlib`

如果加入 v0.1 扩展集，建议顺序调整为：

1. 固定 A/B 组不变，先验证 patch apply、test patch apply、FAIL_TO_PASS/PASS_TO_PASS 解析。
2. 加入 C 组中的 `sympy / pylint / xarray`，扩大纯库和 CLI 样本。
3. 加入 C 组中的 `pytest / sphinx`，验证测试框架自身和文档构建类路径。
4. 最后加入 D 组中的 `scikit-learn / astropy / matplotlib / seaborn / flask`，用于依赖加载更重的一档。

原因：

- `requests`、`sympy`、`pylint`、`xarray` 更容易先把 no-LLM harness 打通。
- `pytest`、`astropy`、`scikit-learn` 会更明显地放大测试执行与依赖加载负载。
- `matplotlib` 适合保留到后面，作为稍复杂但仍规则可验的一档。

## 不进入 v0 的对象

首轮暂不纳入：

1. `SWE-bench Full`
2. `SWE-bench Multimodal`
3. `SWE-bench Multilingual`
4. `django/django` 的大多数实例
5. 明显依赖外部数据库、client binary、浏览器或服务端启动流程的实例

这些对象不是不重要，而是更适合在 `v1/v2` 中按特定环境专题拆开测。

## 建议的后续验证动作

这份清单还只是 `metadata-level filter`，下一步应做三类验证：

1. 环境验证
   - 镜像或 rootfs 中是否能离线装齐依赖
   - 是否需要额外系统包

2. harness 验证
   - 是否能固定 `base_commit`
   - 是否能离线应用 `test_patch`
   - 是否能分离 patch apply、test setup、test execution、result parse

3. 负载验证
   - 每个实例在 fixed-patch 模式下的 wall time
   - 测试执行阶段 CPU 占比
   - repo IO、日志大小、context switch

## 结论

对当前这个“参考 Terminal-Bench 构造无模型请求 workload”的目标，`SWE-bench Verified` 是最合适的主来源，`Lite` 只负责 smoke，不负责最终主集。

`v0` 最合理的做法不是追求更多实例，而是先拿一批纯 Python、规则测试清晰、环境噪声低的实例，把 `fixed_patch / fixed_output / replay_trajectory` 三种模式做扎实。

当前建议的 `v0` 主线可以概括为：

`requests + sphinx + sympy + pylint + pytest + scikit-learn + astropy + xarray + matplotlib`

## 参考来源

- SWE-bench 官方数据集文档：https://www.swebench.com/SWE-bench/guides/datasets/
- SWE-bench 官方仓库：https://github.com/SWE-bench/SWE-bench
