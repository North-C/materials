---
status: deferred
date: 2026-08-27
date-updated: 2026-08-27
decision-makers: repository owner
consulted: none
informed: repository reviewers
---

# Defer the repository-native web Wiki until content organization converges

网页 Wiki 仍是长期展示目标，但当前实施已推迟。静态站原型验证只作为工具调研证据；生成器配置、依赖锁和构建脚本不进入当前内容整理交付。

## Context and Problem Statement

已接受的信息架构要求 materials 保持一个 Git 生命周期、按领域/项目导航、避免正文副本，并通过 manifest 连接结论与证据。现在需要让这些内容最终以网页 Wiki 形式浏览、搜索和审阅。

需要决定：使用独立 GitHub Wiki、复制全仓库 Markdown，还是在本仓库内维护一个静态站展示层？

## Decision Drivers

- Markdown 和 Git 仍是单一事实源。
- 不把 GitHub Wiki 变成第二个仓库和第二套权限/历史。
- 不复制未分类日志、大文件、二进制或潜在敏感材料到网页。
- 支持中文导航、搜索、面包屑、稳定 URL 和静态部署。
- 当前不移动数百个既有文件，允许逐项目纳入全文渲染。
- 构建必须可在独立环境重现，不污染最小 `.gitignore`。

## Considered Options

- GitHub Wiki 独立仓库。
- 将全仓库 Markdown 和资产复制到一个网页目录。
- 仓库内维护精选索引页，由 Material for MkDocs 生成静态 Wiki；正文逐项目纳入。
- 使用 Zensical 作为新一代静态站生成器。
- 继续使用根 README，不提供网页站点。

## Decision Outcome

Chosen option: “先维护仓库内 Markdown 内容目录，推迟网页生成器和发布”，因为项目入口、canonical、provenance 和公开 allowlist 尚未收敛。现在引入网页工具会把展示问题和内容治理混在一起。

具体决策：

1. `docs/index.md` 是跨项目内容目录；`docs/topics/` 是主题分类层；`docs/meta/` 是治理层。
2. 现有项目文档仍是 canonical 内容源。第一阶段主题页使用仓库链接，不复制正文。
3. 当前不保留网页生成器配置、依赖锁、构建脚本、CI 或发布 workflow。
4. 恢复网页工作前，CubeSandbox、research 和根目录至少完成入口与公开级别整理。
5. 未来发布内容采用 allowlist；大文件、raw evidence、机器状态、客户/专利资料和未审计敏感文件默认排除。

### Consequences

- Good, because 当前变更集中在内容关系，不被展示工具牵制。
- Good, because 技术正文继续靠近项目，避免 Wiki 副本漂移。
- Good, because 内容目录可以直接成为未来网页导航输入。
- Bad, because 当前没有网页搜索、面包屑或静态站预览。
- Bad, because 网页工具选择需要在未来重新验证。
- Neutral, because Zensical 是面向未来的候选，但当前主机上 `0.0.57` 和 `0.0.43` 的官方最小项目均退出 0 却生成 0 个文件，暂不采用。
- Neutral, because 最终托管平台和 canonical `site_url` 尚未决定，不启用依赖站点 URL 的 instant navigation。

### Confirmation

- 当前 worktree 不包含网页生成器、依赖锁、构建脚本或 `site/`。
- 根 README、内容目录、主题页和项目 README 的相对链接通过检查。
- `.gitignore` 仍只有 `__pycache__/` 与 `*.pyc`。
- 恢复网页工作时另行确认生成器、托管目标、URL、访问控制、公开 allowlist 和敏感审计。

历史原型证据：Material for MkDocs 9.7.7 曾在隔离临时目录生成 60 个文件、14 个 HTML、129 条搜索索引记录；这不代表当前交付包含或发布了网页站点。

## Pros and Cons of the Options

### GitHub Wiki

- Good, because 原生具有 Wiki 页面体验。
- Bad, because 它是独立 Git 仓库，容易形成两套历史、权限和 canonical。

### Copy all repository content

- Good, because 站内全文覆盖快。
- Bad, because 会复制大文件、证据、缓存和潜在敏感内容，并制造事实源副本。

### Repository-native Material for MkDocs index

- Good, because 与 Docs as Code 和当前 project-first 架构一致。
- Good, because 可用 allowlist 渐进扩展，静态输出易部署。
- Bad, because 首期只是导航型 Wiki，需要后续纳入 canonical 全文。

### Zensical

- Good, because 是 Material for MkDocs 团队面向新项目的后继，架构仍在发展。
- Bad, because 当前主机的两个已发布版本都出现“成功退出但空输出”，无法满足独立运行健康证据。
- Neutral, because 后续版本修复后可在独立 Workspace 重新评估，不影响 Markdown 内容模型。

### README only

- Good, because 工具最少。
- Bad, because 缺少跨主题网页导航、搜索和独立发布能力。

## More Information

- [Material for MkDocs: Installation](https://squidfunk.github.io/mkdocs-material/getting-started/)
- [Material for MkDocs: Navigation](https://squidfunk.github.io/mkdocs-material/setup/setting-up-navigation/)
- [Material for MkDocs: Search](https://squidfunk.github.io/mkdocs-material/setup/setting-up-site-search/)
- [Zensical: Get started](https://zensical.org/docs/get-started/)
- [内容目录使用方式](../../CONTENT_CATALOG.md)
- [信息架构](../INFORMATION_ARCHITECTURE.md)
