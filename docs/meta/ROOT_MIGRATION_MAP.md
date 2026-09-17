---
status: proposed
scope: item-level migration map for tracked root-level scattered documents (MAT-04)
last_verified: 2026-09-17
canonical: false
---

# 根级散落文档迁移映射

本页是 MAT-04 的逐项迁移映射：在 `docs/topics/root-files.md` 的分类候选之上，补齐每份文件的已验证元数据、入链、项目聚类和目标目录，供用户审阅后再按小组执行 Git rename。本页本身不移动、不改名、不删除任何文件。

## 事实基线（2026-09-17 盘点验证）

- 根级散落内容共 15 份 Markdown、1 个无扩展名文件（`记录`）、2 份已跟踪 Excalidraw；全部已被 Git 跟踪。
- 除治理页（`docs/topics/root-files.md`、`docs/meta/INVENTORY.md`）外，**15 份 Markdown 与 2 份 Excalidraw 的入链均为零**。`ai_sandbox/` 下对 "design.md" 的文本命中经核实全部是 `nydus-design.md`、`p2p-design.md`、`kata-guest-image-management-design.md` 等其它文件名的子串，不是对根级 `design.md` 的引用。
- Provenance 简单：所有根级散落文件均只有 1 个 commit（2026-02-13 批量入库）；`cloud-native-trends-report.md` 与 `日志.md` 在 2026-06-08 有过一次更新。无逐文件演进历史，迁移不改写历史的成本为零。
- 主检出区另有 3 个未跟踪根级对象（6.5 MB `IO_stack_and_hypervisor.excalidraw`、1.5 MB `现代Linux_IO技术栈.png`、598 MB perf tar），不在本映射范围（MAT-01）。

## 凭据风险登记（不含任何秘密值）

以下已跟踪文件包含明文凭据类内容，已随 2026-02-13 的提交进入 Git 历史：

| 文件 | 大小 | 风险 | 处置 |
|---|---|---|---|
| `记录` | 57 B | 含一个外部模型 API key（Google/Gemini 形态） | 归入 MAT-05；轮换前不得迁移、不得公开 |
| `日志.md` | 1.1 KB | 混合体：kata-cpuset-nri 开发计划正文 + 一个外部模型 API key（DeepSeek 形态，出现两次） | 先轮换 key；正文拆分迁移需在轮换后单独批准 |
| `github-tokens.md` | 93 B | 命名指向凭据；内容未读取 | 维持既有 MAT-05 结论 |

对本映射的约束：上表文件**不进入任何迁移小组**；`记录` 从"unclassified"更正为"凭据文件"。相关 key 需要用户在仓库外轮换/吊销；历史处理方案按 MAT-05 单独授权。

## 项目聚类与迁移小组

盘点发现根级文档不是 15 个孤立项，而是少数几个项目/主题的聚落。每组是未来一个独立 commit 候选，组内一起迁移。

### Group R1：容器资源调度 / NRI 项目文档（4 份，强关联）

`design.md`（21.8 KB，"框架设计"，runtimeHook/statesinformer/NRI/cgroup reader 结构图）、`Policy模块设计文档.md`（372 B，容器变更请求资源调整模块骨架）、`并发问题.md`（350 B，NUMA-aware 调度 bug 记录）、`日志.md` 的开发计划部分，共同指向同一个容器资源调度项目（runtimeHook + Proxy/NRI + kata Pod cpuset 约束，`日志.md` 中项目名为 kata-cpuset-nri）。

| 文件 | 迁移动作 | 前置条件 |
|---|---|---|
| `design.md` | ✅ 已执行（2026-09-17）：`nri-resource-policy/design.md`，作为 canonical 设计文档 | — |
| `Policy模块设计文档.md` | ✅ 已执行（2026-09-17）：`nri-resource-policy/Policy模块设计文档.md`，与 `design.md` 同目录互链 | — |
| `并发问题.md` | ✅ 已执行（2026-09-17）：`nri-resource-policy/并发问题.md`，定位为该项目的问题记录 | — |
| `日志.md` | **暂不迁移**：先完成凭据轮换，再把开发计划正文拆出（key 段不搬运），并入 `nri-resource-policy/` | MAT-05 轮换完成 |

入链为零，迁移时无需修复其它文档的引用；移动后在 `docs/topics/root-files.md` 与新目录 README 记录新旧路径映射。

### Group R2：外部参考占位（2 份）

`不同芯片系列.md`（58 B，仅一条 EPYC wiki 链接）、`指令集学习.md`（332 B，ARM neon/sve/sme 与内核同步机制的链接集）。两份都是纯外部链接占位，无自有正文。

迁移动作：已确认（2026-09-17 用户同意）按占位方案 1 处理——**保留在根级，主题页已标注 placeholder**；不迁移、不删除。若未来硬件/架构主题形成目录，再议收编。

### Group R3：混部/资源隔离研究链接（1 份）

`容器资源隔离.md`（435 B）：openEuler rubik 容器混部引擎的链接集。与 `katalyst分析/`（Katalyst 混部）同主题域。

迁移动作：✅ 已执行（2026-09-17）：以纯 Git rename 并入 `katalyst分析/` 作为混部引擎对照资料，并新增该目录 README（记录 Katalyst 与 rubik 的方案对照关系与引用注意）。

### Group R4：工程 how-to（2 份）

`docker镜像编译.md`（1.7 KB，通用操作）、`jenkins使用.md`（1.4 KB，CI 使用笔记）。

迁移动作：✅ 已执行（2026-09-17）：以纯 Git rename 并入 `软件工程/`，并新增该目录 README。后续条件：补适用版本/环境边界后再定 canonical 状态。

### Group R5：云原生趋势报告（1 份）

`cloud-native-trends-report.md`（5.8 KB，《云原生领域趋势报告 2020-2026》）。与 `Paperwork/cloud-native-report-2026-02.md`（13 KB，《Cloud Native 领域最新进展报告 2025.12–2026.2`）》**不是重复，是姊妹篇**：一份长期趋势、一份季度进展。已核对标题与正文主题，无收敛提案。

迁移动作：✅ 已执行（2026-09-17）：以纯 Git rename 迁至 `Paperwork/` 与姊妹篇同目录，并在新增的 `Paperwork/README.md` 中记录姊妹篇关系与引用口径（按时间尺度选择）。

### Group R6：Kubernetes 可观测性笔记（1 份）

`klog日志实践.md`（7.1 KB，klog 结构化日志实践，含 Kubernetes 官方 logging 规范链接）。

迁移动作：✅ 已执行（2026-09-17）：以纯 Git rename 并入 `tracing/`，并新增该目录 README，将目录定位扩展为可观测性笔记入口（logging + tracing），避免为单文档开新目录；未来观测类文档增多时可再议目录名。

### 不迁移项

| 文件 | 结论 |
|---|---|
| `BDD与cucumber.md`（0 B） | 空占位；三态决策见下节 |
| `golang_under_the_hood.md`（0 B） | 空占位；三态决策见下节 |
| `华泰问题讨论.md`（2 B） | 实为空占位（非正文）；命名指向客户相关，处置仍走保密审查，迁移前不动 |
| `专利修改问题.md`（179 B） | 受限资料；内容未读取，公开/迁移前走保密与授权审查 |
| `记录`、`日志.md`、`github-tokens.md` | 凭据风险登记表所列，全部走 MAT-05 |
| `k8s-manager.excalidraw`（19.9 KB）、`tap-plugin.excalidraw`（1.2 MB） | 图源；入链为零，尚未找到引用文档与导出图关系，归属明确前不迁移 |

## 空与占位文件决策（已确认）

用户于 2026-09-17 确认按方案 1 处理（保留占位 + 主题页标注 `placeholder`）：

对 `BDD与cucumber.md`、`golang_under_the_hood.md`、`不同芯片系列.md`、`指令集学习.md` 四份"无自有正文"文件，以及 `华泰问题讨论.md`（2 字节空占位，处置另受保密审查约束）：

1. **保留占位**（✅ 已选）：文件名代表明确的待写主题（BDD/cucumber、Go 内部机制）或待展开的参考集，保留在根级，主题页已标注 `placeholder`。
2. **补写后迁移**（备选）：保留至内容补齐，再按主题归类。
3. **归档**（备选）：若主题已被放弃，移入明确的归档位置（不删除）。

任何删除都需要单独授权。

## 执行顺序建议

1. ~~用户先处置凭据风险~~（进行中，用户接管：轮换两处模型 API key；`github-tokens.md` 按 MAT-05 既有流程）。
2. ~~用户审阅本映射，确认各 Group 的目标目录与空文件三态决策。~~ 已完成（2026-09-17）。
3. ~~按 Group 逐个独立 commit 执行 Git rename：R1 → R4 → R5 → R6 → R2/R3~~ 已完成：R1、R4、R5、R6、R3 均以纯 Git rename（R100）执行完毕；R2 按占位方案 1 保留根级。
4. ~~每组迁移后更新映射与入链~~ 已随各执行 commit 完成。
5. **剩余**：`日志.md` 的正文拆分放在凭据轮换完成之后，单独一批。

## 验证记录

- 2026-09-17：15 份 Markdown + `记录` + 2 份 Excalidraw 的跟踪状态、大小、行数、首行标题、入链、单 commit provenance 均已在 worktree 内核实；受限文件（`专利修改问题.md`、`华泰问题讨论.md`、`github-tokens.md`）只采集了元数据；两份 cloud-native 报告的姊妹篇关系已按标题与正文主题核对。
- 2026-09-17（R1 执行）：`design.md`、`Policy模块设计文档.md`、`并发问题.md` 以纯 Git rename（R100，零内容改动）迁入 `nri-resource-policy/`，同批新增该目录 README；新旧路径映射记录于目录 README 的 Provenance 节。
- 2026-09-17（R4 执行）：`docker镜像编译.md`、`jenkins使用.md` 以纯 Git rename（R100，零内容改动）迁入 `软件工程/`，同批新增该目录 README（含既有 3 份文档的导航与迁入 provenance）。
- 2026-09-17（R5 执行）：`cloud-native-trends-report.md` 以纯 Git rename（R100，零内容改动）迁入 `Paperwork/`，同批新增该目录 README，记录与 `cloud-native-report-2026-02.md` 的姊妹篇关系。
- 2026-09-17（R6 执行）：`klog日志实践.md` 以纯 Git rename（R100，零内容改动）迁入 `tracing/`，同批新增该目录 README（目录定位扩展为可观测性笔记入口）。
- 2026-09-17（R3 执行）：`容器资源隔离.md` 以纯 Git rename（R100，零内容改动）迁入 `katalyst分析/`，同批新增该目录 README（记录 rubik 与 Katalyst 的混部方案对照关系）。

相关：[根目录散落文件主题页](../topics/root-files.md) · [任务 backlog](TASK_BACKLOG.md) · [大对象治理](LARGE_OBJECT_MANIFEST.md)
