---
status: accepted
date: 2026-08-20
decision-makers: repository owner
consulted: none yet
informed: repository reviewers
---

# Adopt project-first navigation with typed documentation and manifested evidence

## Context and Problem Statement

Materials 是长期技术知识库，既有 708 个已跟踪文件，内容覆盖多个项目和领域，并混合结论文档、项目内说明、脚本、图、日志、结果、归档和第三方参考资料。根入口、状态、canonical 和 provenance 不统一；同时主检出区有未审阅成果和超过普通 GitHub 文件上限的大型归档。

需要决定：如何在不批量移动、不破坏链接、不丢失证据的前提下，建立可渐进迁移的信息架构、命名/状态规则、原始证据边界和大文件策略？

## Decision Drivers

- 读者先按长期领域或项目寻找内容。
- 同一项目需要把结论、操作、参考、脚本和证据关联起来。
- 既有路径多且外部引用未知，必须保持渐进迁移和可回滚。
- 实验结论必须能追溯到 revision、配置、原始数据和 hash。
- 原始证据不能因名称类似临时产物而被误删。
- 普通 Git 不适合大型生成物，LFS 也有存储、带宽和历史迁移成本。
- 仓库包含潜在敏感路径，治理文档不能复制凭据内容。

## Considered Options

- 顶层按 Diátaxis 四类建立 `tutorial/`、`how-to/`、`reference/`、`explanation/`。
- 保持现有自然增长结构，只增加搜索约定。
- 顶层按领域/项目导航，项目内部按文档目的和 artifact 职责组织，并通过 manifest 连接结论与证据。

## Decision Outcome

Chosen option: “顶层按领域/项目导航，项目内部按文档目的和 artifact 职责组织，并通过 manifest 连接结论与证据”，因为它保留当前读者的主题路径，同时能在项目边界内区分 Diátaxis 文档类型、脚本、资产、证据和历史版本。

具体决策：

1. 整个 Git 仓库是一个 Orca Project；每次边界清晰、可回滚的整理是一个 Orca Workspace。
2. 根 README 是全仓库入口；每个成熟项目 README 记录 scope、canonical docs、evidence、status、last verified 和 source revision。
3. Diátaxis 是项目内部的内容类型和写作目的，不是全仓库顶层分类。
4. 内容另外按 durable knowledge、project-local docs、evidence、generated/ephemeral 判定；混合项目在项目内按职责分开。
5. 原始证据与解释结论分离。结论文档链接 evidence manifest；manifest 记录来源、采集时间、配置、revision、hash、脱敏和复现状态。
6. 新文档使用 `draft`、`in-progress`、`verified`、`historical` 显式状态；不再仅靠文件名中的日期、`TODO` 或 `Doing`。
7. 不一次性统一中英文或改名。新英文路径优先 `kebab-case`，日期用 `YYYY-MM-DD`，旧路径通过映射渐进迁移。
8. 程序生成的大文件优先仓库外对象存储/制品/release。超过 50 MiB 必须先审阅，超过 100 MiB 不进入普通 Git。确需版本化的二进制另行评估 LFS。
9. 本决策不授权删除、LFS 历史迁移、历史改写、push 或发布。

### Consequences

- Good, because 现有路径可以继续工作，根和项目 README 逐步改善可发现性。
- Good, because canonical 与 manifest 降低多份结论平行维护和“结果无来源”的风险。
- Good, because evidence 与 generated 的判定基于职责，而不是危险地按 `logs/`、`results/`、`tmp/` 名称清理。
- Good, because 每个 Workspace 冲突面小，能独立审阅与回滚。
- Bad, because 过渡期会同时存在旧路径和目标规则，索引维护量短期上升。
- Bad, because 为历史文档补 source revision 和 provenance 需要人工判断，不能完全自动化。
- Bad, because 仓库外对象存储需要额外的权限、保留期和可用性治理。
- Neutral, because 某些小型项目不需要完整的 Diátaxis 目录，只需在 README 标注类型。

### Confirmation

本决策已由仓库所有者于 2026-08-20 接受。通过以下方式持续确认实施符合本决策：

- 当前 Workspace 只新增治理骨架和最小 ignore，没有移动/删除既有路径。
- 新增 Markdown 相对链接、敏感模式、Git diff 和 Git status 检查通过。
- 后续至少一个项目 Workspace 按此规则建立 README/canonical/manifest，并复核维护成本；若规则不适用，应新增 ADR 修订或取代本决策。

## Pros and Cons of the Options

### Top-level Diátaxis buckets

- Good, because 四类文档目的清晰。
- Bad, because 同一项目的文档、脚本、证据和版本会跨顶层分散。
- Bad, because 需要大规模移动并破坏大量相对链接。

### Keep the organic structure only

- Good, because 没有迁移成本。
- Bad, because 根入口、canonical、状态、重复和 provenance 问题继续累积。
- Bad, because 大文件和证据只能依赖个人记忆判断。

### Project-first with typed docs and evidence manifests

- Good, because 符合读者按主题导航的方式，并兼容现有目录。
- Good, because Diátaxis、Docs as Code、ADR 和 evidence governance 各自解决不同层次问题。
- Bad, because 需要分批补索引和元数据，不能一次自动完成。

## More Information

- [Diátaxis: Start here](https://www.diataxis.fr/start-here/)
- [Write the Docs: Docs as Code](https://www.writethedocs.org/guide/docs-as-code/)
- [Write the Docs: Documentation principles](https://www.writethedocs.org/guide/writing/docs-principles/)
- [MADR](https://adr.github.io/madr/)
- [GitHub: About large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
- [GitHub: About Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage)
- [事实清单](../INVENTORY.md)
- [迁移计划](../MIGRATION_PLAN.md)
- [ADR 0002：仓库内网页 Wiki](0002-repository-native-web-wiki.md)
