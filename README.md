# Materials 技术材料库

本仓库长期保存技术总结、实验结论、源码解读、图表、复现实验脚本与证据。它不是单一软件项目，也不是临时文件中转站；同一主题可以同时包含解释文档、操作指南、参考资料、脚本和原始证据，但这些内容应有清晰入口、状态和来源关系。

当前治理状态：`accepted`。信息架构与治理规则已于 2026-08-20 接受。网页 Wiki 是后续展示目标，但构建已于 2026-08-27 推迟；当前优先整理项目 README、canonical 文档、证据入口和迁移映射。既有已跟踪内容仍保留在原路径，实际迁移继续按 [迁移计划](docs/meta/MIGRATION_PLAN.md) 分批执行。

## 内容目录

- [内容目录首页](docs/index.md)：跨项目导航与当前分类入口。
- [内容目录使用方式](docs/CONTENT_CATALOG.md)：单一事实源、项目入口和证据关系。
- [优先主题](docs/topics/index.md)：大文件、CubeSandbox、research 和根目录散落文件。

## 快速导航

### AI Sandbox 与 Micro-VM

- [CubeSandbox 项目入口](ai_sandbox/cubesandbox/README.md)：架构、生命周期、性能、问题修复、操作、文章和证据导航。
- [CubeSandbox benchmark 入口](ai_sandbox/cubesandbox/benchmark/README.md)：镜像构建、测试脚本、报告和 checksum。
- [CubeSandbox 测试用例与数据流分析](ai_sandbox/cubesandbox/testcases_analysis/README.md)：Template、Snapshot、Clone、Pause/Resume 的分析与图表。
- [CubeSandbox ARM64 irqbypass 工程总结](ai_sandbox/cubesandbox/articles/cubesandbox-arm64-irqbypass-engineering-story.md)：面向读者的长期结论文档。
- [CubeSandbox AP1R 调试证据包](ai_sandbox/cubesandbox/debug/arm64-vgic-ap1r-nmi-active-20260806/README.md)：带说明、校验和、数据和证据的归档示例。
- [Micro-VM 跨项目分析入口](ai_sandbox/micro-vm-analysis/README.md)：Firecracker、Cloud Hypervisor、Kata Containers、CubeSandbox 的学习路线、专题和样本。
- [AgentENV 架构说明](ai_sandbox/agentenv/architecture.md)：Agent Sandbox 架构与相关设计文档入口。
- [Kata Containers 专题目录](ai_sandbox/kata-containers/)：架构、生命周期、snapshot/restore 与 Nydus 资料。

### Virtualization 与 KVM

- [ARM64 KVM 学习地图](virtualization/arm64_KVM学习阅读地图.md)：ARM 架构手册与虚拟化主题的阅读导航。
- [KVM/QEMU 系列入口](kvm/01_KVM-Qemu分析_概述.md)：CPU、内存、中断、timer 与 virtio 系列解读。
- [Virtio 资料目录](virtualization/virtio/)：规范、源码解读、图片和外部参考资料。

### Research、benchmark 与证据

- [Agent benchmark CPU 负载研究](research/README.md)：研究结论、筛选方法、PoC 和版本快照入口。
- [CubeSandbox benchmark 报告](ai_sandbox/cubesandbox/benchmark/reports/)：汇总报告与结果 CSV。
- [Kata 启动延迟原始结果](results-direct-lite/)：配置、raw、logs、workloads 和 summary；当前缺目录级 provenance manifest，使用前先核对采集上下文。
- [Agent browser 内存容量材料](ai_sandbox/memory_compress/)：报告、CSV 和 JSON 数据。

### 其他领域

- [Kubelet 源码解析](kubelet源代码解析/)
- [Tracing](tracing/)
- [软件工程](软件工程/)
- [日常项目简析](每日项目简析/)

## 内容状态

新建或实质更新的成熟文档应在文档头或所属项目 README 中声明以下状态之一：

| 状态 | 含义 |
|---|---|
| `draft` | 草稿，结构或结论尚未完成，不应作为可靠依据。 |
| `in-progress` | 正在验证或补充证据，可供协作但结论可能变化。 |
| `verified` | 已按所列来源、版本和证据核验；必须给出 `last_verified` 与 `source_revision`。 |
| `historical` | 保留用于历史追溯，不代表当前实现或当前环境。 |

旧文件名中的 `TODO`、`Doing`、日期或版本号只是历史提示，不等同于上述状态。迁移前以所属 README 或索引的显式声明为准。

## 内容落盘流程

1. 先确定内容所属的长期领域或项目，并检查该目录 README 中的 scope 和 canonical docs。
2. 区分结论文档、项目内文档、原始证据和可重新生成产物；分类规则见 [信息架构](docs/meta/INFORMATION_ARCHITECTURE.md#分类判定树)。
3. 结论与证据分开保存。结论文档链接 evidence manifest；manifest 记录来源、采集时间、配置、源码 revision、hash 和复现状态。
4. 在边界清晰的 Orca Workspace 中提交一次可回滚变更。不要顺手整理其他目录，也不要自动删除旧入口。
5. 审阅前检查相对链接、canonical 冲突、敏感信息、文件体积、Git diff 和 Git status。
6. 大文件先按策略判定。程序生成物优先放仓库外或发布附件；确需版本化的二进制再单独评估 Git LFS，禁止未经审阅迁移历史。

## 从当前结构过渡

- 当前路径继续有效；本轮不批量移动、改名或删除任何既有文件。
- 顶层继续按长期领域和项目导航，不把整个仓库强制拆成 `tutorial/`、`how-to/`、`reference/`、`explanation/` 四个大桶。
- Diátaxis 类型用于项目内部文档的写作目的和局部组织。目录较小时可只在 README 中标注类型，不必预建空目录。
- 每次后续迁移先在项目 README 或迁移映射中指定 canonical 文档、旧路径、目标路径和兼容期，再处理链接和副本。
- 原始日志、测试数据、二进制、图片和归档在完成分类及 provenance 审阅前都按证据候选保护，不因目录名含 `tmp`、`logs`、`results` 或日期就删除。

## 治理资料

- [事实清单与风险](docs/meta/INVENTORY.md)
- [内容整理报告](docs/meta/CONTENT_ORGANIZATION_REPORT.md)
- [大对象 manifest](docs/meta/LARGE_OBJECT_MANIFEST.md)
- [目标信息架构](docs/meta/INFORMATION_ARCHITECTURE.md)
- [分批迁移计划](docs/meta/MIGRATION_PLAN.md)
- [信息架构决策记录](docs/meta/decisions/0001-materials-information-architecture.md)
- [网页 Wiki 延后记录](docs/meta/decisions/0002-repository-native-web-wiki.md)
- [后续 Workspace backlog](docs/meta/TASK_BACKLOG.md)
