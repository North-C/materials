# CubeSandbox：材料归档专项规则

本文件补充 [仓库规则](../../AGENTS.md)，适用于 `ai_sandbox/cubesandbox/` 全部子目录。先读 [专题导航](README.md) 和目标子目录的索引；通用命名、证据、脱敏和交付要求以仓库规则为准。

## 1. 具体放到哪里

以下路径均相对于本目录；带占位符的路径是新增材料的命名示例，不是已有文件。

| 新材料类型 | 存放位置 | 必须维护的入口 |
| --- | --- | --- |
| 系统架构与图稿 | `architecture/` | 本目录 `README.md`；保留图稿源文件和导出文件的对应关系 |
| 版本变化、源码差异 | `version-evolution/` | 本目录 `README.md` |
| benchmark 方法、参数、使用说明 | `benchmark/docs/` | `benchmark/README.md` |
| workload 镜像、适配 Dockerfile | `benchmark/docker/` | `benchmark/README.md` 的来源与核心文件说明 |
| benchmark runner / 汇总脚本 | `benchmark/scripts/` | 对应使用指南和 `benchmark/README.md` |
| 核心性能、Template、生命周期测试报告 | `benchmark/reports/` | `benchmark/README.md` 的对应报告分类 |
| 内存、CoW、密度记账分析与勘误 | `benchmark/analysis/` | `benchmark/README.md` 的内存分析入口 |
| SWE 回放指南、脚本和逐轮结果 | `benchmark/swe-replay-density/`；结果放 `results/<date-or-run>/` | 回放 README 及结果索引；新日期/批次增加入口 |
| 创建时延、阶段剖析、优化前后测量 | `perf/reports/<topic-version-date>/` | `perf/README.md` |
| 通用计时边界、指标来源等说明 | `perf/` 下具名专题文档 | `perf/README.md` |
| c100n100 优化复现、配置与补丁 | `c100n100-perf-tuning/` 的对应文档或独立子专题 | 该目录 `README.zh-CN.md`；测试方法变更同步测试指南 |
| 调查中问题、复现、日志与假设 | `debug/<issue-date>/` | 新问题目录 README 和本目录 `README.md` |
| 根因确认后的修复与验证 | `bug-fixes/` 下具名报告及配套分析目录 | 本目录 `README.md`，并从原调查包链接修复报告 |
| 测试用例的源码与流程解读 | `testcases_analysis/` | 该目录 `README.md` |
| 工程叙事文章 | `articles/` | 本目录 `README.md`，文章回链报告与证据 |
| 新的构建、适配或机制专题，现有分类无法容纳 | 在本目录下新建职责明确的子目录和 README | 本目录 `README.md`，说明与现有分类的边界 |

不要继续向本目录根部添加长文件名的零散测试报告。根目录既有文档、仓库顶层的 `cube-bench对比/` 和 `cube-bench-go-numa-20261016/` 是历史存放位置，不是新实验的默认模板；新实验按上表归类，历史包仍在原位追加其自身的勘误或说明。

新材料优先复用最近的专题索引；只有新增主题、目录或常用入口时，才扩展本目录 README，避免把每个 run 的附件铺进总索引。

## 2. 三种常见操作

- **新增创建时延报告**：新建 `perf/reports/<topic-version-date>/REPORT.md`，将该轮数据和图表保存在同目录，更新 `perf/README.md`。示例名称中的日期必须替换为实际运行日期。
- **给同一测试追加一轮**：保留该主题的累计报告和既有数据，新建独立 run 目录，补充结果、环境差异、失败与清理状态，再更新所属索引；不同条件的轮次不能无说明地合并统计。
- **已有判断被新证据推翻**：保留旧证据，在旧报告显著位置加日期、勘误摘要与后续报告链接；新文写明哪些结论被替代。不得静默覆盖旧数据或以“最新版”抹去调查过程。

## 3. CubeSandbox 测试证据要求

除仓库规则中的工具与命令信息，还应记录下列与结论相关的身份和条件；缺失项明确标注，不从日志样式、Go 运行时版本或镜像 tag 猜测：

- CubeSandbox 源码 commit / release，以及实际部署的 CubeMaster、Cubelet、CubeShim、VMM、guest agent 等相关组件版本或哈希；区分源码、构建产物和运行中进程。
- 测试机别名、CPU 架构、主机与 guest 内核、GIC 模式、cgroup、NUMA/CPU 绑定、THP、存储与网络条件；按实验影响范围记录具体值。
- Template ID、源镜像 digest、guest 配置、vCPU、内存、可写层、探针及 MMDS-prime / envd 等相关配置。
- runner 仓库、版本/commit、二进制校验、模式、并发数、正式样本数、预热方式、重试与超时；区分同进程预热和独立预热。
- API 请求耗时、整轮 wall-clock、组件阶段、guest 就绪等各自的计时起止与单位；标明正式/预热归属及各表的分母，重叠或异步阶段不能直接相加。
- 资源独占或干扰情况、配额、TAP 池及测试前后库存；记录本轮创建资源的标识和清理证据。未知或失败的清理状态必须保留。

执行用户指定的 Template 并发启动测试时，只使用指定的原生 `cube-bench` 入口、参数和统计方式。路径或版本不明确时先澄清；不要替换成 Python/HTTPX、自定义并发器或额外 wrapper 后仍称为同一测试。其他 workload 的 runner 依其测试设计选择，但须单独记录方法。

API / Template READY、guest 命令成功、应用可用、完整生命周期和资源清理是不同的验证项。create-only 的 `DELETE avg=0` 不能作为删除性能结果；Docker smoke、单次功能回放和构建通过不能作为平台密度或性能完成证据。

优化对比先固定基线与条件，一次只改变一个待验证因素。若历史实验存在版本、预热、模板、配额或主机状态漂移，只报告观察到的差异和限制，不把多因素差异归因为某个版本或参数。失败、异常及未执行轮次也必须收录。

## 4. 工具与资料的维护边界

- `benchmark` 回答测什么、怎么测和结果如何；`perf` 回答阶段耗时与观测边界；`c100n100-perf-tuning` 记录配置、补丁和复测方法。报告互相链接，证据只存一份。
- 增补镜像材料时区分上游 workload 来源、语言运行时、已有 benchmark 源镜像和 CubeSandbox 适配层。先核对 [benchmark 来源说明](benchmark/README.md)，不要把适配 Dockerfile 描述为完整原始构建入口。
- `perf/scripts_v2`、`perf/scripts_v071` 是历史脚本归档。通用 profiler 的维护位置以 [perf 索引](perf/README.md) 为准；不要在此另建功能分叉。修订历史脚本须说明对应报告与版本，不能宣称旧报告由新脚本产生。
- 发布脱敏的证据子集时，逐项说明哪些日志、配置、metrics 或原始样本没有包含，及因此无法完成的复核；发布副本的校验不等于原件的校验。
- 文档补充不隐含重新测试、部署补丁、改变模板或清理远程资源。只有实际完成并留有证据的步骤，才能标记已验证。
