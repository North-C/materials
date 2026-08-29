# Materials 后续 Orca Workspace Backlog

状态：`in-progress`。MAT-00 内容目录、CubeSandbox/research 项目入口和内容整理报告阶段已完成；后续内容迁移仍按独立 Workspace 推进，网页 Wiki 构建 deferred。默认不删除、不改写历史、不 push；若任务需要这些动作，必须另行取得明确授权。

## 依赖概览

| ID | Workspace | 依赖 | 主要冲突 |
|---|---|---|---|
| MAT-00 | 内容目录与四主题索引 | 已接受的信息架构 | 只允许建立跨域索引，不跨域迁移原文 |
| MAT-01 | 大文件与生成物治理 | 本治理骨架获审阅 | 与 MAT-03 的 research tar/vendor、MAT-05 的敏感审计有路径交集 |
| MAT-02 | CubeSandbox 内容收敛 | 本治理骨架获审阅 | 与 MAT-06 链接基线、公开文章 canonical 有交集 |
| MAT-03 | research 证据与版本目录治理 | MAT-01 的存储原则 | 主检出区两处 Dockerfile 修改；与 MAT-01 的版本 tar/vendor 有交集；phase 1 已建立保护清单 |
| MAT-04 | 根目录散落文档归类 | 根 README 迁移映射规则 | 与 MAT-01 的根级 tar/图、MAT-05 的高风险文件冲突 |
| MAT-05 | 私密敏感文件审计 | 仓库所有者授权和安全处置窗口 | 禁止与普通内容迁移并行修改同一路径 |
| MAT-06 | Markdown 链接检查器 | 至少 MAT-02 或 MAT-03 完成一项 | legacy 绝对路径和仓库外 evidence 会产生噪声 |
| MAT-07 | 已跟踪缓存收敛 | MAT-01 确认保留边界 | 与 benchmark 包的可复现性/打包方式有交集 |
| MAT-08 | Wiki 构建、全文纳入与网页发布（deferred） | MAT-02、MAT-03、MAT-04 至少完成相关 allowlist | 与敏感审计、许可证、托管平台和 push 权限冲突 |

## MAT-00：内容目录与四主题索引

状态：`completed`。

输入：

- 已接受的信息架构、inventory、迁移计划和根 README。
- 大文件、CubeSandbox、research、根目录散落文件四个优先冲突域。
- 已有事实清单和项目目录入口。

边界：

- 只新增 Markdown 目录、主题摘要和分类映射。
- 不读取敏感文件，不复制主检出区 dirty/untracked 内容，不迁移原始路径。
- 不保留网页生成器、构建依赖或发布 workflow。

验收：

- 根 README、内容目录、四个主题和治理页互相可达。
- 目录不成为第二份正文事实源；每个主题明确后续独立 Workspace。
- 根 `.gitignore` 保持两条最小规则。
- ADR 0002 记录网页目标及 deferred 状态。

历史验证记录：曾在隔离临时目录验证静态站原型；生成器与依赖已移出当前交付，后续不得把该记录当作当前网页发布状态。

补充交付：`docs/meta/CONTENT_ORGANIZATION_REPORT.md` 汇总当前内容整理结果、canonical 候选、风险登记和下一步建议，作为审阅入口。

冲突关系：可同时读取四个域的既有清单，但任何实际内容修改必须转入 MAT-01/02/03/04。

## MAT-01：大文件与生成物治理

状态：`phase-1-in-progress`。已建立 Git LFS 路径规则和大对象 manifest；598 MB tar 暂不纳入，vendor tar 不处理，现有 virtualization PDFs 允许 LFS 上传；尚未提交大对象。

输入：

- 598,772,736 B 未跟踪 perf tar。
- 6 份已跟踪 LFS PDF 与 `virtualization/.gitattributes`。
- 未跟踪 vendor tar、Excalidraw、PNG、日志、`.marscode`、`tmp/.../dconf/user`。
- 已跟踪和未跟踪的 `__pycache__/`、`*.pyc`。

边界：

- 只读取元数据、hash 和必要 manifest 信息；不展开大型归档正文。
- 不自动添加 LFS、不迁移历史、不上传对象、不删除原件。
- `logs/`、`results/`、`images/` 不做目录级 ignore。

验收：

- 每个大文件/二进制候选有 owner、role、source、hash、可重建性、敏感级别和目标存储决策。
- 598 MB tar 未进入普通 Git，仓库内有拟议 manifest/sidecar 方案。
- 已有 PDF LFS 状态和许可证/来源风险被记录，但历史未改变。
- generated 与 evidence 的冲突有人工结论，未按名称猜测删除。

冲突关系：与 MAT-03 共同涉及 research version/vendor tar；与 MAT-04 共同涉及根级 tar 和图；与 MAT-07 共同涉及 bytecode。

## MAT-02：CubeSandbox 内容收敛

状态：`phase-2-in-progress`。已新增项目 README、`CONTENT_CONVERGENCE.md`、benchmark reports manifest、perf manifest、AP1R debug manifest 和 evidence availability map；部分 checksum 已复核，raw provenance 和脚本收敛仍待执行。

输入：

- `ai_sandbox/cubesandbox/` 全部现有子域。
- 顶层日期报告、中英文总结、articles、benchmark、debug、bug-fixes、perf、testcases_analysis。
- 已验证完全重复的两组 perf 脚本。

边界：

- 第一阶段只建 CubeSandbox README、主题索引、canonical/status/provenance 映射。
- 不重跑远程实验，不改技术结论，不删除旧报告。
- 不同时重构 research 或根目录。

验收：

- README 能按“概览、源码/机制、操作、性能、问题/修复、证据、历史”导航。
- AP1R、Template restore、irqbypass、benchmark 各有一个明确 canonical 入口和 source revision。
- 每个公开结论能链接到仓库内 manifest，或明确标记仓库外 evidence unavailable/controlled。
- 重复脚本经过调用方和历史检查，形成保留/收敛提案；本阶段不自动删除。

冲突关系：与 MAT-06 的链接规则强相关；若同时修改 CubeSandbox README 或 perf 脚本，应串行执行。

## MAT-03：research 证据与版本目录治理

状态：`phase-1-in-progress`。已整理 research README、`CONTENT_CONVERGENCE.md` 和 `DIRTY_INPUT_MANIFEST.md`，标出 clean-clone 缺口与主检出区 dirty/untracked 输入；主检出区成果审阅、版本 provenance 和 evidence manifest 仍待执行。

输入：

- `research/README.md`、`agent_cpu_sandbox_toolkit/`、`versions/v0/`、`agent_ai_trend/research-notes/`。
- 主检出区 2 个已修改 Dockerfile 和 research 下大量未跟踪任务、工具、trajectory、tar/vendor。
- 本 Workspace 中的 `research/CONTENT_CONVERGENCE.md` 与 `research/DIRTY_INPUT_MANIFEST.md`。

边界：

- 首先保护并吸收用户 dirty 状态，不覆盖、不 checkout。
- 不运行大规模 benchmark，不重新生成版本包。
- 自包含 task 内的重复依赖只有在确认打包模型后才可抽取。

验收：

- 研究结论、toolkit source、task fixture、raw evidence、derived results、vendor input 分类清楚。
- `versions/v0/README.md` 说明冻结范围、source revision、生成命令、hash、存储位置和后续版本关系。
- research 根 README 能找到所有 canonical 报告和可复现入口。
- dirty input manifest 区分 local/private state、source/tool、task fixture、raw evidence、vendor 和 version archive。
- 两处 modified Dockerfile 的保留与合并方案经用户确认。

冲突关系：先采用 MAT-01 的大文件策略；与 MAT-07 的缓存规则有交集；主检出区 dirty 路径使其不能与其他修改 toolkit 的 Workspace 并行。

## MAT-04：根目录散落文档归类

输入：

- 15 份根级 Markdown、已跟踪/未跟踪图源与 PNG。
- 空 Markdown、近似主题文件和相邻目录 `Ops_records/`、`Paperwork/`、`软件工程/`、`每日项目简析/`。

边界：

- 先做迁移映射和 canonical 审阅，后移动。
- 不处理大型 tar 的存储，不读取高风险命名文件内容。
- 不强制统一中文/英文文件名。

验收：

- 每个根级文件都有分类、scope、status、canonical/alias、目标目录或“保留根级”的明确决策。
- 每次移动前记录入链，移动后相对链接和图片引用通过。
- 空文件有保留/补写/归档提案，但未因空而自动删除。
- 根 README 的导航和迁移映射同步更新。

冲突关系：根级 tar/图先走 MAT-01；高风险文件只走 MAT-05；避免与其他根 README 修改并行。

## MAT-05：私密敏感文件审计

输入：`github-tokens.md` 的当前跟踪状态和 Git 历史元数据。

边界：

- 需要仓库所有者明确授权，在不会记录终端正文的私密环境执行。
- 不把秘密值写入 issue、报告、commit message、manifest 或聊天。
- 不把“从当前树删除”误当成“从历史清除”。

验收：

- 只报告是否存在凭据类别、是否可能有效、最早/最近影响 revision，不报告值。
- 若确认泄露，先完成轮换/吊销并记录非秘密确认。
- 历史清理、force push 和协作者重新同步另立高风险计划并单独批准。

冲突关系：必须与 MAT-04 串行；不得由普通内容治理 Workspace 顺手处理。

## MAT-06：只读 Markdown 链接与索引检查

输入：现有 Markdown、项目 README、迁移映射和仓库外 evidence 标记约定。

边界：

- 脚本无外部依赖、默认只读、不打开二进制或日志正文。
- 新改文件严格检查；legacy 基线只报告，不立即阻断。
- 不把绝对本地 evidence 路径输出成可能含敏感信息的完整报告。

验收：

- 可检查相对文档链接、图片链接、目录 README、anchor 基本格式和 orphan 候选。
- 支持 allowlist/显式 `external-local-evidence`，且 allowlist 有 owner 和过期条件。
- 同一输入输出稳定，退出码区分新错误与 legacy 提示。

冲突关系：最好在 MAT-02 或 MAT-03 提供一个已治理项目后实施，以验证规则不过度拟合。

## MAT-07：已跟踪缓存与无争议生成物收敛

输入：9 个已跟踪 `.pyc`、未跟踪/忽略的 `__pycache__`，以及本轮新增的最小 `.gitignore`。

边界：

- 仅处理可明确重建的 Python bytecode；不扩展到 logs/results/images/tmp。
- “停止 Git 跟踪”和“删除本地文件”分开；默认保留本地工作副本。
- 先确认 benchmark 包不依赖 bytecode 作为离线交付物。

验收：

- bytecode 不再作为新变更出现。
- 若获批取消跟踪，变更只涉及明确列出的 9 个路径和 ignore；本地运行/测试仍通过。
- 没有证据文件被 ignore 或删除。

冲突关系：采用 MAT-01 的 generated 判定；与 MAT-03 的 toolkit 打包边界串行确认。

## MAT-08：Wiki 构建、全文纳入与网页发布

状态：`deferred`，等待内容入口、canonical、公开 allowlist 和敏感审计成熟。

输入：

- 已通过项目治理的 canonical 文档与 evidence manifest。
- `docs/` 内容目录、未来 allowlist 和公开性分类。
- 用户指定的托管平台、域名或访问控制要求。

边界：

- 不做无 allowlist 的全仓库复制，不使用 symlink 或独立 GitHub Wiki 作为事实源。
- 公开站不包含 raw evidence、客户/专利资料、机器状态、凭据风险文件或无许可二进制。
- CI、Pages 分支、push 和远程发布需要单独明确授权。

验收：

- 目标 canonical 全文可在站内搜索，页面能追到 source revision 和 evidence manifest。
- 严格构建、敏感扫描、许可证检查、链接检查和最小权限审阅通过。
- 发布 revision 可回滚，站点生成物不进入主内容历史。

冲突关系：依赖 MAT-02/03/04 的公开 allowlist，并与 MAT-05 敏感审计串行；托管发布不得与内容迁移混为同一高风险变更。
