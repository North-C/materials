# Materials 目标信息架构

- 状态：`accepted`（2026-08-20）
- 适用范围：整个 materials Git 仓库
- 本轮影响：只建立规则和入口，不批量移动既有内容

## 目标

让读者能从“领域/项目”找到可靠结论，让维护者能从结论追到证据、脚本和源码版本，同时保留历史资产的可审计性。信息架构应支持长期渐进迁移，而不是要求一次性重排数百个文件。

## 采用的原则与取舍

### Diátaxis 用于项目内部文档类型

[Diátaxis](https://www.diataxis.fr/start-here/) 区分 tutorial、how-to、reference、explanation，分别服务学习实践、完成具体任务、查事实和理解背景。本仓库采用这四种目的来判断项目内部文档的写法与局部导航，但不把仓库顶层强行切成四个大桶。

原因是 materials 同时覆盖 CubeSandbox、Micro-VM、KVM、virtualization、research 等长期领域。用户通常先按主题找内容，再判断要学习、操作、查表还是理解原理。顶层按文档类型会把同一项目的结论、源码版本、证据和脚本拆散。

### Docs as Code 用于维护流程

[Write the Docs: Docs as Code](https://www.writethedocs.org/guide/docs-as-code/) 将版本控制、纯文本、代码评审和自动检查作为文档工作流。本仓库采用 Git、Markdown、边界清晰的 Workspace、diff 审阅和可逐步引入的自动检查。

[Documentation principles](https://www.writethedocs.org/guide/writing/docs-principles/) 强调可浏览、当前、来源唯一、可发现和可定位。本仓库的对应取舍是：

- 通过根 README 和项目 README 提高 discoverability，而不是复制正文到多个入口。
- 每个主题指定 canonical doc，允许摘要重复但禁止多份全文平行维护。
- “verified” 必须绑定时间和 source revision；无法持续核验的旧材料标为 historical。
- 文档尽量靠近所属项目；跨项目结论放领域级入口，并链接项目内证据。

### MADR 保存少量高影响决策

[MADR](https://adr.github.io/madr/) 用精简 Markdown 记录上下文、备选、结果与后果。本仓库只为会影响多个目录或未来迁移的治理决策建立 ADR，例如目录结构、命名、证据和大文件策略；普通文章编辑不建立 ADR。

### 大文件默认不进入普通 Git

[GitHub 大文件文档](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) 说明超过 50 MiB 会警告，超过 100 MiB 会被普通 Git 推送阻止；[Git LFS 文档](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage) 说明 LFS 在仓库中存 pointer、把实际对象存到外部 LFS 存储。

本仓库因此优先把程序生成的大型归档放到对象存储、制品库或 release，并在仓库保留 manifest、hash 和复现方法。只有确需与 Git revision 一起版本化、无法合理重建且许可允许的二进制，才在单独审阅后评估 LFS。任何 LFS 扩展或历史迁移都不是本规则的自动动作。

## Orca 工作模型

- Orca Project：整个 materials Git 仓库，共享一个版本生命周期和治理入口。
- Orca Workspace：一次边界清晰、可审阅、可回滚的整理变更。例如“CubeSandbox 建立项目 README 并标记 canonical”，而不是“整理全仓库”。
- 每个 Workspace 只处理一个主要冲突域；大文件、CubeSandbox、research 和根目录散落文档分别推进。
- 例外是只读的跨域目录 Workspace：可以同时为多个冲突域建立分类页，但不得在同一批次移动、重写或删除这些域的原始内容。

## 内容目录与未来网页展示

当前内容目录与内容存储分层：

- `docs/index.md` 是跨项目目录，`docs/topics/` 是主题导航，`docs/meta/` 是治理页面。
- 现有项目 Markdown 继续是 canonical source，主题页先链接仓库原文，避免创建平行副本。
- 当前优先建立项目 README、canonical/provenance 和迁移映射，不保留网页生成器、依赖或发布配置。
- 项目内容治理完成后，再单独决定网页全文渲染方式。
- GitHub Wiki 不作为事实源，因为它使用独立 Git 仓库和独立历史。
- 大文件、raw evidence、机器状态、客户/专利资料和未审计敏感文件默认不进入未来网页构建。
- 曾验证的静态站原型与工具取舍保留在 ADR 0002，但不属于当前交付范围。

详细决策见 [ADR 0002](decisions/0002-repository-native-web-wiki.md)。

## 目标结构

顶层继续表达长期领域或项目。既有 `ai_sandbox/`、`virtualization/`、`kvm/`、`research/` 等名称在各自迁移获批前保持不变。

```text
materials/
├── README.md                    # 全仓库入口与状态说明
├── docs/
│   ├── index.md                 # 跨项目内容目录
│   ├── topics/                  # 跨项目主题索引，只写摘要和关系
│   └── meta/                    # 治理事实、规则、计划、ADR、backlog
├── <domain-or-project>/         # 既有长期领域或项目目录
│   ├── README.md                # scope、canonical docs、status、evidence
│   ├── explanation/             # 可选：原理、背景、源码解读、结论
│   ├── how-to/                  # 可选：面向任务的操作指南
│   ├── reference/               # 可选：规格、参数、矩阵、术语
│   ├── tutorial/                # 可选：受引导的学习实践
│   ├── scripts/                 # 采集、复现、生成和验证脚本
│   ├── evidence/                # 原始证据及 manifest
│   ├── assets/                  # 图源和文档使用的稳定资产
│   └── archive/                 # 明确 historical 的旧版本，不是垃圾桶
└── ...
```

这些子目录按需创建。小项目可以把少量文档留在项目根目录，由 README 标明 Diátaxis 类型；禁止为了形式完整而创建空目录。

## 目录职责

| 位置 | 职责 | 不应承担 |
|---|---|---|
| 根 `README.md` | 全仓库导航、状态模型、落盘流程、过渡说明 | 复制各项目详细结论 |
| `docs/index.md` | 内容目录首页和优先主题入口 | 项目正文或 raw evidence |
| `docs/topics/` | 跨项目分类、canonical 映射、状态与迁移队列 | 复制原文、无 allowlist 汇总 |
| `docs/meta/` | 全仓库治理事实、信息架构、迁移计划、决策与任务 | 项目技术结论、原始实验数据 |
| 项目 `README.md` | scope、读者入口、canonical docs、证据入口、状态和源码基线 | 大段重复正文 |
| `explanation/` | 为什么、机制、权衡、结论 | 步骤清单和原始日志堆放 |
| `how-to/` | 完成一个真实任务的可执行步骤 | 从零教学或长篇背景 |
| `reference/` | 准确、可查的参数、规格、矩阵、术语 | 观点性分析 |
| `tutorial/` | 有安全路径和预期结果的学习实践 | 生产 runbook |
| `scripts/` | 可复现、可审阅的自动化 | 无来源的结果快照 |
| `evidence/` | 原始输入/输出、环境、hash、manifest | 把解释性结论埋在日志中 |
| `assets/` | canonical 图源及必要导出图 | 无关联文档的图片堆 |
| `archive/` | 已声明 historical、仍有追溯价值的内容 | 未分类内容或待删除内容 |

## 分类判定树

对每个 artifact 依次提问：

1. 它是否是支持结论所需的原始输入、原始输出、环境快照、校验和或不可替代记录？
   - 是：归为 `evidence`，即使扩展名是 Markdown、PNG、JSON、tar 或日志。
   - 若它由原始输入机械生成但报告审计需要保留：标为 `derived evidence`，manifest 必须指向输入和生成命令。
2. 它是否表达跨版本或跨项目仍有价值的解释、结论、方法或学习路线？
   - 是：归为 `durable knowledge`，放在最接近的长期领域，并指定 canonical。
3. 它是否依赖某个项目、组件、部署或 source revision 才成立？
   - 是：归为 `project-local docs`，留在项目边界内并记录 revision。
4. 它是否能从已保存的输入和脚本稳定重建，且本身不承担审计或发布职责？
   - 是：归为 `generated/ephemeral`，默认不版本化。
5. 仍不能判断？
   - 标为 `unclassified evidence candidate`，保持原位，不删除、不忽略，进入 backlog。

同一项目包含多类内容时按职责分开而不拆散项目：

```text
project/
├── README.md             # 导航和状态
├── explanation/result.md # 解释结论，链接 manifest
├── scripts/collect.sh    # 采集方法
├── evidence/run-id/      # 原始数据、配置、manifest
├── assets/diagram.drawio # canonical 图源
└── archive/              # 已明确 historical 的旧结论
```

## 项目 README 最小字段

成熟项目目录的 README 至少说明：

- `scope`：涵盖什么、不涵盖什么。
- `canonical docs`：每个主题的权威入口；若有语言变体，说明主版本和同步关系。
- `evidence`：manifest 或证据包入口。
- `status`：项目级总体状态，以及各关键文档的例外。
- `last_verified`：最近核验日期。
- `source_revision`：源码 commit、发布版本、镜像 digest、论文版本或 `not-applicable`。
- `owners/reviewers`：可选；需要谁确认 canonical 或敏感边界。

## 状态与文档元数据

新文档建议使用短 YAML front matter；现有文档可先在项目 README 索引中补齐，不要求批量加头：

```yaml
---
status: draft | in-progress | verified | historical
scope: one-sentence boundary
last_verified: YYYY-MM-DD | not-yet-verified
source_revision: commit/tag/digest/document-version | not-applicable
canonical: true | false
evidence_manifest: relative/path/to/MANIFEST.md | not-applicable
supersedes: relative/path | none
---
```

规则：

- `verified` 不允许 `last_verified: not-yet-verified`，也不能省略适用的 `source_revision`。
- `historical` 必须说明为何保留以及当前替代入口。
- 同一 scope 同一语言只允许一个 `canonical: true`。
- `draft` 和 `in-progress` 可以提交，但入口必须明确提示不应作为最终依据。
- 文件名不再用 `TODO`、`Doing` 作为唯一状态来源。

## Evidence manifest 规则

每个成熟 evidence bundle 应有 `MANIFEST.md` 或等价的机器可读 manifest，并至少记录：

| 字段 | 要求 |
|---|---|
| evidence ID / run ID | 在项目内唯一且稳定 |
| purpose | 要验证或反驳什么 |
| source | 主机、上游 URL、API、论文或其他来源；敏感地址可脱敏 |
| collected at | 带时区时间；导入第三方资料则记 retrieved at |
| source revision | commit、tag、镜像 digest、内核/组件版本 |
| configuration | 影响结论的参数、资源、架构、数据集 |
| procedure | 命令、脚本路径或 runbook；凭据用占位符，不落盘 |
| artifacts | 相对路径、字节数、SHA-256、角色（raw/derived/report） |
| reproducibility | reproducible / partially reproducible / not reproducible 及原因 |
| redaction | 是否脱敏、脱敏了什么类别，不记录秘密原文 |
| interpretation | 指向结论文档；manifest 自身不替代分析 |

原始证据默认不可原地改写。若必须脱敏，保留“原始对象受控存储位置 + 脱敏副本 hash + 脱敏规则”，不要在公开仓库保留秘密原文。

## 命名规则

- 先保证稳定与可链接，不一次性统一中文/英文。
- 新英文路径使用小写 `kebab-case`；已有中文标题可继续使用中文。
- 日期统一为 `YYYY-MM-DD`；紧凑日期只为兼容既有文件，不用于新路径。
- 版本目录使用明确产品/数据 schema 版本；仅表示进度的 `v0` 应由 README 解释冻结内容和后续关系。
- `final`、`new`、`latest`、`temp`、`Doing`、`TODO` 不作为长期文件名状态。
- 运行目录使用可排序 run ID，例如 `2026-08-20T143000+0800-host-purpose`；不在路径放 token、IP、用户隐私或内部凭据。
- 图源和导出图共享 stem，例如 `data-flow.drawio` 与 `data-flow.svg`，README 指定 canonical source。

## 单一来源与副本

1. 先确认 scope 是否真的相同；语言翻译、发布版和原始研究笔记可以并存，但要声明关系。
2. 为同一结论选择一个 canonical 文档。
3. 旧路径在兼容期保留短指针或在索引中建立迁移映射，不自动删除。
4. 更新所有已知入链并运行相对链接检查。
5. 只有在审阅确认无独有内容、无有效引用、备份与回滚路径明确后，才可在独立 Workspace 提议删除副本。

## 大文件策略 {#large-file-policy}

| 情况 | 默认位置 | 仓库内保留 |
|---|---|---|
| 可重建的大型生成物 | 仓库外对象存储/制品库；必要时 release | manifest、hash、生成脚本、保留期 |
| 原始大型 evidence | 受控对象存储，按敏感级别授权 | 脱敏 manifest、hash、采集配置、结论链接 |
| 第三方大文件 | 稳定上游 URL 或包管理器 | 版本、来源、许可证、hash；离线必要性说明 |
| 必须随 Git 版本化的二进制 | 单独 ADR/评审后考虑 LFS | `.gitattributes` 规则、成本与拉取说明 |
| 小型文本日志/CSV | 可进入 Git，仍需 manifest | 原始/派生角色、hash、revision |

体积门槛不是价值判断：

- `>50 MiB`：不得无说明直接加入普通 Git；先做存储评审。
- `>100 MiB`：不得加入普通 Git；GitHub 会阻止。LFS 也必须先获批准。
- 低于门槛的二进制也要评估 diff 能力、许可证、可重建性和长期成本。
- 不自行执行 LFS 历史迁移、`filter-repo` 或其他历史改写。

## 自动检查边界

当前仓库存在大量绝对本地路径、仓库外 `source_code/`/`remote-results/` 引用和旧入口。全仓库“一刀切”链接检查会产生高噪声，因此本轮不加入脚本。

后续检查器应分两级：

1. 新增/修改 Markdown 的相对链接必须存在，或显式标注 `external-local-evidence`。
2. 全仓库 legacy 报告只生成基线清单，不阻断；各项目迁移后逐步收紧。
