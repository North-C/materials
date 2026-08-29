# Materials 内容目录

这里把 materials 仓库中分散的技术总结、源码解读、实验结论、图表和证据按主题建立导航，但不复制或改写原文。

当前阶段：`content-catalog-in-progress`。网页 Wiki 构建已推迟，当前优先整理项目 README、canonical 候选、状态、证据入口和迁移映射。

## 优先主题

| 主题 | 现在能解决什么问题 | 当前状态 |
|---|---|---|
| [大文件与生成物](topics/large-files.md) | 哪些对象是证据、外部参考、图源或可重建产物；为什么不能直接提交 | `classified-candidates` |
| [CubeSandbox](topics/cubesandbox.md) | 从架构、生命周期、性能、问题修复和证据进入现有材料 | `indexed` |
| [Research](topics/research.md) | 区分研究结论、toolkit、任务、版本快照、trajectory 和 vendor 输入 | `indexed` |
| [根目录散落文件](topics/root-files.md) | 为根级文档、图、风险文件和未分类对象建立迁移映射 | `classified-candidates` |

## 怎么使用

1. 按主题进入目录页，不按文件名猜状态。
2. 在主题页查看 scope、canonical 候选、证据入口和迁移状态。
3. 通过“查看源码”链接进入仓库中的原始 Markdown 或目录。
4. 结论需要引用时，优先引用标为 canonical/verified 的文档及其 evidence manifest。
5. 页面标为 `candidate`、`draft` 或 `historical` 时，不把它当作当前结论。

详细规则见 [内容目录使用方式](CONTENT_CATALOG.md)。

## 治理入口

- [信息架构](meta/INFORMATION_ARCHITECTURE.md)
- [事实清单](meta/INVENTORY.md)
- [内容整理报告](meta/CONTENT_ORGANIZATION_REPORT.md)
- [大对象 manifest](meta/LARGE_OBJECT_MANIFEST.md)
- [按领域提交与 Push 计划](meta/COMMIT_PUSH_PLAN.md)
- [迁移计划](meta/MIGRATION_PLAN.md)
- [后续 Workspace](meta/TASK_BACKLOG.md)
- [网页 Wiki 延后记录](meta/decisions/0002-repository-native-web-wiki.md)

## 当前证据边界

- 主检出区仍是只读盘点对象；2026-08-27 复核时仍为 HEAD `f036fd2`、2 个 modified、70 个 untracked 文件级条目、0 staged；本地 `main` 相对已知 `origin/main` 落后 3 个提交。
- 内容目录不复制大型 tar、PDF、日志、results 或可疑敏感文件。
- `github-tokens.md` 没有被读取或链接；它只保留为私密审计风险项。
- 网页生成和远程发布均已推迟，不属于当前内容整理范围。
