# 根目录散落文件

状态：`migration-mapped`。逐项迁移映射已完成，见 [ROOT_MIGRATION_MAP](../meta/ROOT_MIGRATION_MAP.md)；本页保留主题摘要。不移动或改名任何根级对象。

## Markdown 分类候选

2026-09-17 盘点已确认 scope 的文件在"分类候选"列标注了结论；详见迁移映射。

| 当前路径 | 分类候选 | 目标 Wiki 主题 | 风险/待确认 |
|---|---|---|---|
| `BDD与cucumber.md` | durable software-engineering | 软件工程/测试方法 | 0 字节空占位；三态决策待用户确认 |
| `Policy模块设计文档.md` | project-local design（已确认：NRI 资源调度项目子模块） | R1 项目目录 | 与 `design.md` 同项目同组迁移 |
| `cloud-native-trends-report.md` | durable research/report | Research/Cloud Native | 与 `Paperwork/cloud-native-report-2026-02.md` 为姊妹篇（长期趋势 vs 季度进展），非重复 |
| `design.md` | project-local design（已确认：容器资源调度 runtimeHook/NRI 框架设计） | R1 项目目录 | 与 Policy/并发问题/日志.md 同项目聚类 |
| `docker镜像编译.md` | how-to | 容器/构建 | 补平台、版本和验证状态 |
| `golang_under_the_hood.md` | durable explanation | 软件工程/Go | 0 字节空占位；三态决策待用户确认 |
| `jenkins使用.md` | how-to/reference | 工程效率/CI | 补适用版本和环境边界 |
| `klog日志实践.md` | how-to/explanation | Kubernetes/可观测性 | 确认是否并入 kubelet/tracing 主题 |
| `不同芯片系列.md` | external-reference placeholder（已确认：仅一条 EPYC wiki 链接） | 硬件/架构 | 无自有正文；三态决策待用户确认 |
| `专利修改问题.md` | project/private candidate | 受限项目资料 | 公开前做保密与授权审查；内容未读取 |
| `华泰问题讨论.md` | empty placeholder（已确认：2 字节，非正文） | 受限项目资料 | 空占位但命名指向客户相关；处置走保密审查 |
| `容器资源隔离.md` | external-link collection（已确认：openEuler rubik 混部引擎链接集） | 容器/Kubernetes | 与 `katalyst分析/` 同主题域；确认归置 |
| `并发问题.md` | project-local bug record（已确认：NUMA-aware 调度问题） | R1 项目目录 | 与 `design.md` 同项目同组迁移 |
| `指令集学习.md` | external-reference placeholder（已确认：ARM 向量指令集/内核同步链接集） | 硬件/架构 | 无自有正文；三态决策待用户确认 |
| `日志.md` | mixed（已确认：kata-cpuset-nri 开发计划 + 明文凭据段） | 拆分候选 | 凭据风险见迁移映射；先轮换再拆分迁移 |

## 非 Markdown 对象

| 当前路径 | 分类候选 | 处理边界 |
|---|---|---|
| `k8s-manager.excalidraw`、`tap-plugin.excalidraw` | canonical diagram source | 入链为零；找到引用文档、owner 和导出图后再迁移 |
| `IO_stack_and_hypervisor.excalidraw` | 未跟踪图源 | 先归属 virtualization/KVM，建立 source/export 关系 |
| `现代Linux_IO技术栈.png` | 未跟踪 derived/publication asset candidate | 找到图源、许可证和引用文档 |
| `tbench-large-scale-text-editing-profile-perf-amd6.tar` | 大型 evidence candidate | 只走 MAT-01；不进入普通 Git/Wiki |
| `记录` | credential file（已确认：含外部模型 API key） | 只走 MAT-05；轮换前不迁移、不公开、不删除 |

## 隔离项

以下已跟踪文件含明文凭据风险，均只进入 MAT-05 私密审计；若确认有效，先轮换/吊销，再单独批准历史处理：

- `github-tokens.md`（内容未读取，按命名与既有结论隔离）。
- `记录`（已确认含一个 Gemini 形态 API key）。
- `日志.md` 的凭据段（已确认含一个 DeepSeek 形态 API key，出现两次；正文开发计划部分的拆分迁移需在轮换后单独批准）。

本 Workspace 不在任何文档、issue、commit message 或报告中输出上述秘密值。

## 未来网页公开性

以下根级内容默认不进入公开网页全文：

- 客户、专利或组织内部讨论；
- 未完成敏感审计的文件；
- 无明确来源/许可的图片和第三方材料；
- raw profile、日志和大归档；
- scope、状态和 owner 均未知的内容。

## 下一 Workspace（MAT-04/MAT-05）

1. ~~逐项确认 scope、owner、status、canonical 和公开级别。~~ 已完成：见 [ROOT_MIGRATION_MAP](../meta/ROOT_MIGRATION_MAP.md)。
2. 用户审阅映射、确认各 Group 目标目录与空文件三态决策。
3. 先处置凭据风险（轮换 `记录` 与 `日志.md` 中的 API key），再按小组移动；不统一全部中英文文件名。
4. 每组迁移前记录入链（当前已验证为零），迁移后检查 Markdown 和图片引用。
5. 私密审计与普通分类串行，不在终端或文档输出秘密值。

相关主题：[大文件与生成物](large-files.md) · [事实清单](../meta/INVENTORY.md) · [迁移映射](../meta/ROOT_MIGRATION_MAP.md)
