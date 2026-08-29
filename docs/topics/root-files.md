# 根目录散落文件

状态：`classified-candidates`。本页是迁移映射草案，不读取高风险文件内容，不移动或改名任何根级对象。

## Markdown 分类候选

| 当前路径 | 分类候选 | 目标 Wiki 主题 | 风险/待确认 |
|---|---|---|---|
| `BDD与cucumber.md` | durable software-engineering | 软件工程/测试方法 | 当前为空；确认补写、历史占位或归档 |
| `Policy模块设计文档.md` | project-local design | 软件工程/设计 | 确认所属项目、source revision 和 canonical |
| `cloud-native-trends-report.md` | durable research/report | Research/Cloud Native | 补检索时间、来源和 last verified |
| `design.md` | durable/project-local candidate | 软件工程/设计 | 标题过泛；确认 scope 和与 Policy 文档关系 |
| `docker镜像编译.md` | how-to | 容器/构建 | 补平台、版本和验证状态 |
| `golang_under_the_hood.md` | durable explanation | 软件工程/Go | 当前为空；不自动删除 |
| `jenkins使用.md` | how-to/reference | 工程效率/CI | 补适用版本和环境边界 |
| `klog日志实践.md` | how-to/explanation | Kubernetes/可观测性 | 确认是否并入 kubelet/tracing 主题 |
| `不同芯片系列.md` | durable reference candidate | 硬件/架构 | 补数据来源、时间和适用范围 |
| `专利修改问题.md` | project/private candidate | 受限项目资料 | 公开前做保密与授权审查 |
| `华泰问题讨论.md` | project/private candidate | 受限项目资料 | 公开前做客户/隐私审查 |
| `容器资源隔离.md` | durable explanation | 容器/Kubernetes | 确认与 cgroup/MPAM/Katalyst 文档关系 |
| `并发问题.md` | durable/project-local candidate | 软件工程/并发 | 标题过泛；确认 scope 和 canonical |
| `指令集学习.md` | durable tutorial/explanation | 硬件/架构 | 确认目标 ISA 与学习状态 |
| `日志.md` | unclassified | 可观测性/历史记录 | 标题过泛；检查内容后再分类 |

## 非 Markdown 对象

| 当前路径 | 分类候选 | 处理边界 |
|---|---|---|
| `k8s-manager.excalidraw`、`tap-plugin.excalidraw` | canonical diagram source | 找到引用文档、owner 和导出图后再迁移 |
| `IO_stack_and_hypervisor.excalidraw` | 未跟踪图源 | 先归属 virtualization/KVM，建立 source/export 关系 |
| `现代Linux_IO技术栈.png` | 未跟踪 derived/publication asset candidate | 找到图源、许可证和引用文档 |
| `tbench-large-scale-text-editing-profile-perf-amd6.tar` | 大型 evidence candidate | 只走 MAT-01；不进入普通 Git/Wiki |
| `记录` | unclassified | 仅确认类型和 scope；分类前不删除 |

## 隔离项

`github-tokens.md` 已被 Git 跟踪，但本 Workspace 不读取内容，也不把它链接或复制到网页。它只进入 MAT-05 私密审计：若确认含凭据，先轮换/吊销，再单独批准历史处理。

## 未来网页公开性

以下根级内容默认不进入公开网页全文：

- 客户、专利或组织内部讨论；
- 未完成敏感审计的文件；
- 无明确来源/许可的图片和第三方材料；
- raw profile、日志和大归档；
- scope、状态和 owner 均未知的内容。

## 下一 Workspace（MAT-04/MAT-05）

1. 逐项确认 scope、owner、status、canonical 和公开级别。
2. 先更新迁移映射，再按小组移动；不统一全部中英文文件名。
3. 移动前记录入链，移动后检查 Markdown 和图片引用。
4. 私密审计与普通分类串行，不在终端或文档输出秘密值。

相关主题：[大文件与生成物](large-files.md) · [事实清单](../meta/INVENTORY.md)
