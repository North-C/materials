# Materials 分批迁移计划

- 状态：`in-progress`（内容目录与项目入口整理已授权；网页 Wiki 构建 deferred）
- 原则：每批一个边界清晰的 Orca Workspace；先建入口和 provenance，再考虑移动；任何批次都不自动删除文件。

## 全局护栏

- 主检出区只读；迁移只在独立 worktree 进行。
- 每批开始记录 HEAD、`git status --short`、范围内路径清单和必要 hash。
- 不执行 `git clean/reset/checkout`，不改写历史，不 push，不发布。
- 原始日志、结果、图片、归档和二进制在完成分类前按 evidence candidate 保护。
- 不把 `tmp/`、`logs/`、`results/`、`images/` 整体忽略。
- 不读取或复制凭据。敏感审计与内容迁移分离。
- 每批只处理列明的 scope；跨批冲突回到 backlog，不顺手修复。

## 批次 0：治理基线与根导航

本 Workspace 已完成此批次。

范围：

- 根 `README.md`
- `docs/meta/` 下 inventory、information architecture、migration plan、ADR、backlog
- 仅忽略 `__pycache__/` 与 `*.pyc` 的最小根 `.gitignore`

验收：

- 既有已跟踪路径全部保留。
- 根 README 能到达 CubeSandbox、Micro-VM、virtualization/KVM、research、benchmark/evidence。
- 事实、建议和待确认项分开。
- 新增 Markdown 的相对链接可解析。
- diff 不含凭据模式或大型二进制。

回滚：删除本批新增文件即可；不需要反向移动既有内容。

## 批次 0.5：跨项目内容目录与优先主题索引

本 Workspace 已完成此批次；它是跨域只读目录例外，不授权跨域内容迁移。

范围：

- `docs/index.md`、内容目录使用方式和四个优先主题页。
- 大文件、CubeSandbox、research、根目录散落文件的分类与迁移映射。
- ADR 0002：记录网页 Wiki 目标与 deferred 状态。

动作：

1. 为四个优先主题建立 Markdown 入口、scope、分类、canonical 候选和下一 Workspace。
2. 只链接已提交内容；不复制主检出区 dirty/untracked 成果。
3. 不保留静态站生成器、依赖锁、构建脚本或发布 workflow。

验收：

- 内容目录和四个主题从根 README 可达。
- 新增 Markdown 的相对链接无错误。
- `.gitignore` 仍仅包含 `__pycache__/` 与 `*.pyc`。
- 主检出区状态未被改变，现有已跟踪路径未移动或删除。

回滚：删除内容目录和主题页即可；不需要恢复任何原始内容路径。

## 批次 0.6：CubeSandbox 与 research 项目入口整理

本 Workspace 已完成此批次，只整理 README 与目录关系，没有移动技术正文、脚本或证据。

范围：

- 新增 `ai_sandbox/cubesandbox/README.md`。
- 整理 `research/README.md` 的 scope、分类、canonical 候选、状态和证据入口。
- 让根 README、内容目录和两个项目 README 形成双向可达关系。

验收：

- CubeSandbox 可按架构/生命周期、benchmark、性能、问题修复、操作构建、公开文章和证据进入。
- research 可区分 durable conclusions、toolkit、task fixtures、evidence 和 version/vendor。
- 不覆盖主检出区两处 modified Dockerfile 和 70 个 untracked 成果。
- 不宣布尚未逐篇审阅的文档为 verified canonical。

回滚：撤回两个 README 的索引变更；所有正文与证据仍在原路径。

## 批次 0.7：内容整理报告与交付口径

本 Workspace 已完成此批次。它把当前内容整理结果合并为一个可审阅入口，不引入网页构建。

范围：

- 新增 `docs/meta/CONTENT_ORGANIZATION_REPORT.md`。
- 汇总仓库入口、治理骨架、项目入口、主题索引、canonical 候选、风险登记和下一步建议。
- 从 `docs/index.md` 增加报告入口。

验收：

- 报告不复制敏感文件、大型对象、日志正文或主检出区未跟踪成果。
- 报告明确区分已完成整理、尚未迁移内容和后续 Workspace。
- 网页 Wiki 仍为 deferred。

回滚：删除该报告并移除内容目录中的单条入口即可；不影响任何原始内容路径。

## 批次 1：高风险路径与大文件决策

状态：`phase-1-in-progress`。已新增根 `.gitattributes`，允许获批的归档/PDF 通过 Git LFS 版本化；已新增 `docs/meta/LARGE_OBJECT_MANIFEST.md` 记录候选对象元数据和决策。598 MB tar 暂不纳入，`amd6` 记为笔误，vendor tar 不处理；现有 virtualization PDFs 已上传为 LFS 对象。尚未复制、移动、暂存、提交或删除任何大对象。

输入：

- 未跟踪 598,772,736 B perf tar
- 已跟踪 LFS PDF 与全部现有 LFS 规则
- 未跟踪 vendor tar、Excalidraw、PNG、日志、缓存和机器状态文件
- 已跟踪的 9 个 `.pyc`
- `github-tokens.md` 的跟踪风险，仅限私密审计流程

动作：

1. 只取元数据、hash、来源和可重建性，不展开大型归档内容。
2. 为需要保留的对象建立 manifest，选择 object storage/release/LFS/普通 Git/不版本化。
3. 对已跟踪 bytecode 提出“停止跟踪但保留工作区文件”的独立变更；执行前单独确认。
4. 敏感审计若确认凭据，先轮换，再制定经批准的历史处理方案；不得与普通目录迁移混在一起。

链接/重复验证：manifest 必须被至少一个项目 README 或结论文档引用；同一对象以 hash 去重，不依赖文件名猜测。

回滚：存储迁移前保留原对象和 hash；任何删除、LFS 扩展或历史改写都需要新的明确授权，本批默认不执行。

## 批次 2：CubeSandbox 内容收敛

状态：`phase-2-in-progress`。已新增 `ai_sandbox/cubesandbox/CONTENT_CONVERGENCE.md`，整理 canonical、supersede、evidence 和 duplicate candidates；已新增 benchmark reports、perf、AP1R debug bundle 和外部 evidence availability 的第一版 manifest。尚未移动、删除或重写任何 CubeSandbox 内容。

输入：

- `ai_sandbox/cubesandbox/` 顶层日期报告、`articles/`、`benchmark/`、`bug-fixes/`、`debug/`、`perf/`、`testcases_analysis/`
- 同一问题的中英文总结、分析链、验证报告、公开文章和脚本副本
- 现有 README、SHA256SUMS、CSV/TSV/log 和图表

动作：

1. 新增 CubeSandbox 项目 README，定义 scope、技术主题、canonical docs、状态与 source revision。
2. 按“结论 / how-to / reference / evidence / scripts / assets / historical”建立索引；先不移动。
3. 对 AP1R、Template restore、性能优化、irqbypass 等主题逐个指定 canonical，记录语言/发布变体关系。
4. 对 `perf/` 与 `perf/scripts_v2/` 的完全重复脚本确认调用者和历史意义，再提议收敛。
5. 将仓库外 `remote-results/`、`source_code/` 引用改造成 manifest 中可解释的 provenance，或明确标记 unavailable。

链接验证：对范围内 Markdown 建立基线；每次只修本批触及的链接。根 README 与原入口均应能到达 canonical 文档。

重复验证：全文 hash、语义审阅、Git 历史和调用路径四项至少完成前三项；脚本还必须检查使用方。

回滚：第一阶段只加索引和元数据。后续若移动，使用一批一主题的 Git rename，保留迁移映射；不自动删除旧副本。

## 批次 3：research 证据与版本目录治理

状态：`phase-1-in-progress`。已新增 `research/CONTENT_CONVERGENCE.md` 和 `research/DIRTY_INPUT_MANIFEST.md`，记录 research canonical map、dirty/untracked 输入边界和后续导入前置条件。尚未吸收主检出区两处 modified Dockerfile，也未复制未跟踪工具、task、trajectory、notes 或版本 tar。

输入：

- `research/README.md`
- `research/agent_cpu_sandbox_toolkit/`、Terminal-Bench tasks、trajectory、工具和未跟踪修改/新增文件
- `research/versions/v0/` 与未跟踪版本 tar
- `research/agent_ai_trend/research-notes/`

动作：

1. 区分 durable research conclusion、toolkit source、task fixture、raw trajectory、derived result 和 vendor input。
2. 为 `versions/v0` 定义版本含义、source revision、生成方式和可重建性；版本 tar 优先仓库外保存，仓库内保留 hash/manifest。
3. 每个 benchmark task 明确自包含边界，避免误把重复 `mini_pytest.py` 当作无意义副本。
4. 为 vendor archive 记录上游、版本、许可证、hash 与离线需求。
5. 先吸收主检出区的两处 Dockerfile 修改归属，再决定 canonical；不得覆盖用户改动。

链接验证：`research/README.md` 覆盖所有 canonical 研究报告、toolkit 入口、收敛图和 dirty input manifest；版本 README 能反向链接源与 manifest。

重复验证：区分“自包含测试夹具的有意复制”和“平行维护的实现”；只有后者进入收敛提案。

回滚：元数据/索引与文件迁移拆批；不覆盖主检出区 dirty 文件，不删除版本快照。

## 批次 4：根目录散落文档归类

输入：

- 根级 15 份 Markdown、2 份已跟踪 Excalidraw、未跟踪图源/PNG/大型 tar 和高风险命名文件
- `Ops_records/`、`Paperwork/`、`软件工程/`、`每日项目简析/` 等相邻主题

动作：

1. 逐份确定 scope、状态、canonical、入链和目标领域；先更新根 README 中的迁移映射。
2. 空 Markdown 先确认是否保留为 backlog 占位，不以零字节为删除理由。
3. 图源先建立与引用文档/导出图的关系，再决定目标目录。
4. 对可能含敏感信息的文件只走批次 1 的私密审计，不在本批读取或搬运。
5. 用户审阅映射后，再按小组 Git rename；不一次性统一中英文命名。

链接验证：记录每个旧路径的已知入链；移动后检查新旧入口、图片引用和跨目录相对链接。

重复验证：对根级与项目内同名/近似标题做逐段比对，选 canonical，保留独有信息和来源。

回滚：每组迁移独立 commit 候选；本计划本身不提交。若验证失败，撤回该组变更而不影响其他组。

## 批次 5：链接与索引检查渐进收紧

输入：前四批建立的 README、manifest、迁移映射，以及全仓库 legacy 链接基线。

动作：

1. 添加无外部依赖、只读的 Markdown 相对链接检查器。
2. 新增/修改文件错误作为硬失败；legacy 缺失路径先作为报告。
3. 为合法的仓库外证据引用定义显式标记，不把绝对本地路径误判为可移植链接。
4. 项目完成迁移后，从 legacy allowlist 移除该项目并收紧检查。

验收：脚本不修改内容；输出稳定；CI/本地结果一致；不存在把凭据或日志正文打印到报告的路径。

回滚：移除检查器和 CI gate 不影响内容路径；legacy 基线仍可作为审计记录。

## 批次 6：网页 Wiki 构建、全文纳入与发布（deferred）

输入：完成治理的项目 README、canonical docs、evidence manifest、公开 allowlist 和当前本地 Wiki 构建。

动作：

1. 逐项目决定 canonical 文档迁入 `docs/`，或由只读同步器复制到临时构建目录。
2. 对公开站执行敏感信息、许可证、绝对路径、内部地址和大文件检查。
3. 用户确认托管平台、canonical `site_url`、域名、访问控制和发布分支。
4. 独立 Workspace 增加 CI 构建；发布动作单独授权，不使用预览服务器承担生产流量。

验收：网页可搜索 canonical 全文；源码 revision 和 evidence manifest 可达；构建可重现；未发布任何 denylist 内容。

回滚：撤下静态站或回退发布 revision，不改变原始 Git 内容和证据存储。

## 每批统一验收清单

- [ ] `git status --short` 只出现本 Workspace 预期路径。
- [ ] `git diff --name-status` 没有意外删除、移动或二进制加入。
- [ ] 既有用户改动未被覆盖。
- [ ] 新增/修改 Markdown 的相对链接存在，或已声明为仓库外引用。
- [ ] canonical 冲突已列出并经人工确认。
- [ ] evidence manifest 包含来源、时间、配置、revision、hash 和复现状态。
- [ ] 没有输出或新增 token、密码、Cookie、私钥、认证头等敏感内容。
- [ ] 大于 50 MiB 的对象有存储决策；大于 100 MiB 的对象没有进入普通 Git。
- [ ] 原始证据没有被原地改写；无自动删除。
- [ ] 回滚步骤已验证为局部且不依赖历史改写。
