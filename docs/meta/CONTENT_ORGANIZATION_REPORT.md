# Materials 内容整理报告

- 状态：`phase-1-content-organization`
- 日期：2026-08-27
- 范围：内容入口、分类规则、canonical 候选、证据边界和后续 Workspace 输入
- 不包含：网页 Wiki 构建、全文迁移、文件移动/改名、大文件提交、敏感文件审计

本报告汇总当前 Workspace 在“文档内容整理”上的结果。它不是新的事实源；长期事实仍保留在项目目录中的原始文档、证据包和后续 manifest 中。

## 已完成的整理

### 仓库入口

- 新增根 `README.md`，说明 materials 仓库用途、快速导航、内容状态和落盘流程。
- 新增 `docs/index.md` 作为仓库内 Markdown 内容目录；网页 Wiki 构建已推迟。
- 新增 `docs/CONTENT_CATALOG.md`，明确目录页、内容层、证据层的关系。
- 保留最小 `.gitignore`，仅忽略 `__pycache__/` 与 `*.pyc`。

### 治理骨架

- `docs/meta/INVENTORY.md` 记录已提交基线、主检出区 dirty/untracked 状态、大文件候选、重复/孤儿风险和敏感边界。
- `docs/meta/INFORMATION_ARCHITECTURE.md` 记录目标信息架构、分类判定树、目录职责、命名、状态和 provenance 规则。
- `docs/meta/MIGRATION_PLAN.md` 按批次拆分治理顺序，明确每批输入、边界、验收和回滚。
- `docs/meta/TASK_BACKLOG.md` 把后续 Orca Workspace 拆为大文件、CubeSandbox、research、根目录散落文件、敏感审计、链接检查、缓存治理和网页构建。
- `docs/meta/decisions/0001-materials-information-architecture.md` 记录已接受的信息架构决策。
- `docs/meta/decisions/0002-repository-native-web-wiki.md` 记录网页 Wiki 目标已推迟。

### 项目入口

- `ai_sandbox/cubesandbox/README.md` 已成为 CubeSandbox 项目级导航入口。
- `ai_sandbox/cubesandbox/CONTENT_CONVERGENCE.md` 已整理 CubeSandbox canonical、supersede、evidence 和 duplicate candidates。
- CubeSandbox 已新增 benchmark reports、perf 和 AP1R debug bundle 的第一版 manifest。
- `ai_sandbox/cubesandbox/EVIDENCE_AVAILABILITY.md` 已把旧文档中的 `remote-results/`、`source_code/` 和 Verification 绝对路径映射到本地只读归档。
- `research/README.md` 已整理为 research 项目级导航入口。
- `research/agent_cpu_sandbox_toolkit/README.md` 已补充状态边界，说明 clean checkout 与主检出区未跟踪成果之间的复现缺口。
- `research/CONTENT_CONVERGENCE.md` 已整理 research 研究结论、toolkit、task fixture、evidence 和版本快照的 canonical map。
- `research/DIRTY_INPUT_MANIFEST.md` 已记录主检出区 research 范围 2 个 modified 与 58 个 untracked file-level entries，作为后续导入保护清单。

### 主题索引

- `docs/topics/large-files.md`：登记大文件、LFS PDF、vendor tar、Excalidraw、日志/CSV/TSV、缓存和机器本地对象的策略候选。
- `docs/topics/cubesandbox.md`：建立 CubeSandbox 的跨项目主题地图。
- `docs/topics/research.md`：区分 research 的研究结论、toolkit、task fixture、raw/derived evidence、vendor input 和版本快照。
- `docs/topics/root-files.md`：记录根目录散落 Markdown、图源、PNG、大 tar 和高风险文件的迁移候选。

## 当前 canonical 候选

| Scope | 当前入口 | 状态 |
|---|---|---|
| 仓库导航 | `README.md` | accepted navigation |
| 治理规则 | `docs/meta/INFORMATION_ARCHITECTURE.md` 与 ADR 0001 | accepted |
| 内容目录 | `docs/index.md` 与 `docs/CONTENT_CATALOG.md` | in-progress |
| 大文件策略 | `docs/topics/large-files.md` | candidate map |
| CubeSandbox 项目导航 | `ai_sandbox/cubesandbox/README.md` | in-progress canonical index |
| CubeSandbox 主题地图 | `docs/topics/cubesandbox.md` | indexed |
| research 项目导航 | `research/README.md` | in-progress canonical index |
| research 收敛图 | `research/CONTENT_CONVERGENCE.md` | phase-1 canonical map |
| research dirty 输入保护 | `research/DIRTY_INPUT_MANIFEST.md` | protection manifest |
| research 主题地图 | `docs/topics/research.md` | indexed |
| 根目录散落文件映射 | `docs/topics/root-files.md` | candidate map |
| 网页 Wiki 决策 | ADR 0002 | deferred |

“canonical index”只表示导航入口已收敛，不表示其中每篇技术文档已经被逐段审阅为最新结论。

## 分类规则落地

同一项目可以同时包含结论、脚本、原始数据、图片和归档。当前采用以下落点：

| 内容类型 | 放置原则 | 当前例子 |
|---|---|---|
| durable knowledge | 放在长期领域或项目目录；由 README 标明 status、last verified 和 evidence | CubeSandbox 公开文章、research 研究总结 |
| project-local docs | 留在所属项目内；项目 README 建阅读顺序和 canonical 候选 | CubeSandbox benchmark/how-to、research toolkit README |
| evidence | 原始证据与解释性结论分开；由 README 或 manifest 说明来源、时间、配置、revision、hash、可复现性 | CubeSandbox debug bundle、benchmark CSV/TSV/log |
| generated/ephemeral | 只在确定可重建且非证据后才忽略或取消跟踪 | `__pycache__/`、`*.pyc` |

默认规则：不知道是否可重建、是否唯一、是否敏感时，先标为 evidence candidate，不移动、不删除、不加入 ignore。

## 重要风险登记

| 风险 | 当前处理 |
|---|---|
| 约 598 MB 未跟踪 perf tar | 暂时不纳入；`amd6` 已确认为笔误，未来 canonical 名称应使用 `amd64`；主检出区原文件不在本 Workspace 改名 |
| 约 154 MiB ARM ARM PDF | 已由 `virtualization/.gitattributes` 管理为 LFS；现状不改，后续核对来源/授权/LFS 成本 |
| 未跟踪 vendor tar | 本 Workspace 不处理 |
| Excalidraw 与导出图 | 图源按 canonical source candidate 保护；导出图按 derived asset 处理 |
| 日志、CSV、TSV、JSONL、profile | 分类前均按 evidence 或 derived evidence，不做目录级 ignore |
| 已跟踪 `.pyc` | 新 `.pyc` 由最小 `.gitignore` 阻止；已跟踪对象需 MAT-07 单独批准收敛 |
| `github-tokens.md` | 只记录跟踪风险；未读取内容，后续 MAT-05 私密审计 |
| 本地 `main` 落后已知 `origin/main` 3 个提交 | 当前内容整理仍基于 `f036fd2`；后续 Workspace 开始前重新确认基线和 dirty/untracked 清单 |

MAT-01 phase 1 已补充 [Large Object Manifest](LARGE_OBJECT_MANIFEST.md)，并新增根 `.gitattributes` 让获批的归档/PDF 走 Git LFS。manifest 不等于提交授权；598 MB tar 当前明确暂不纳入。

## 尚未做的内容迁移

- 没有移动、改名或删除既有已跟踪内容。
- 没有吸收主检出区两处 modified Dockerfile。
- 没有复制主检出区 70 个 untracked 成果到当前 Workspace。
- 没有读取 `github-tokens.md`、大型 tar、PDF 正文或大日志正文。
- 没有建立静态站生成器、依赖锁、CI、发布配置或预览站。

## 下一步建议

1. MAT-01：先处理大文件和生成物治理，产出 artifact manifest 与存储决策。
2. MAT-02：继续 CubeSandbox，按 AP1R、Template/Snapshot、benchmark/perf、公开文章分主题做 canonical/supersede 映射。
3. MAT-03：继续 research，已完成第一版 dirty input 保护清单；下一步审阅两处 modified Dockerfile 与未跟踪工具/task/trajectory，再决定哪些内容纳入 Git。
4. MAT-04：逐项审阅根目录散落文件，先确认公开级别、owner、scope 和目标目录，再进行小批移动。
5. MAT-08：网页 Wiki 构建继续推迟，等待 MAT-02/03/04 的 allowlist 和敏感审计成熟。

## 本轮验收口径

- 根 README、内容目录、主题页、项目 README 和治理页互相可达。
- 新增/修改 Markdown 的相对链接可解析。
- 当前 Workspace 不含网页构建依赖或发布配置。
- `.gitignore` 仍只有两条无争议规则。
- `git status` 仅显示当前 Workspace 的文档治理变更。
- 敏感字符串检查不命中新增/修改文档。
