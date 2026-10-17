# AI Sandbox 与 MicroVM 资料导航

[返回 Materials](../README.md) · [CubeSandbox 专题](cubesandbox/README.md)

## 平台与组件

| 主题 | 入口 |
| --- | --- |
| CubeSandbox | [完整分类与阅读入口](cubesandbox/README.md) |
| Firecracker | [架构分析](01-Firecracker-架构分析报告.md) |
| Cloud Hypervisor | [架构分析](02-Cloud-Hypervisor-架构分析报告.md) |
| StratoVirt | [架构分析](03-StratoVirt-架构分析报告.md) |
| Kata Containers | [架构概览](04-Kata-Containers-架构分析报告.md)、[专题目录](kata-containers/)：生命周期、快照、性能、配置与安全通告 |
| gVisor | [架构分析](05-gVisor-架构分析报告.md) |
| Agent Sandbox | [架构分析](06-Agent-Sandbox-架构分析报告.md) |
| E2B | [整体介绍](E2B/07-1-E2B-整体介绍.md)、[组件与启动流程](E2B/07-2-E2B-组件架构与沙箱启动流程.md)、[专题目录](E2B/) |
| agentenv | [架构分析](agentenv/architecture-analysis.md)、[专题目录](agentenv/)：模板启动、可观测性、基础镜像与 P2P |
| Nydus | [挂载与懒加载概览](08-Nydus-镜像挂载与懒加载分析报告.md)、[逐层实现分析](nydus/) |
| faasd | [架构分析](08-faasd-架构分析报告.md) |

## 跨平台研究与实践

| 类别 | 入口 | 范围 |
| --- | --- | --- |
| MicroVM 跨项目分析 | [总索引](micro-vm-analysis/README.md) | 启动、CPU/中断、内存、网络、存储、安全隔离与快照恢复 |
| ARM64 网络专项 | [文档索引](micro-vm-analysis/arm64-network-document-index.md) | 观测、故障特征、样本覆盖与证据缺口 |
| 平台比较 | [对比资料目录](micro-vm-analysis/sandbox-platform-comparison/) | 各报告固定版本下的平台比较 |
| 内存与浏览器容量 | [内存专题](memory_compress/) | 内存压缩与浏览器容量报告、CSV 和运行记录 |
| 从零构建 MicroVM | [实践指南](从零构建MicroVM实践指南.md)、[DEMO 计划](MicroVM-DEMO实现计划.md) | 实践说明与实现计划，完成情况以各文档正文为准 |
| 图稿 | [通用图稿目录](diagrams/) | 平台架构图附件；其他图稿随对应专题保存 |

根目录的平台概览与各平台子目录中的深入分析并存；引用时保留具体文件路径。文件名包含 `TODO`、`Doing` 的笔记按过程资料阅读，不作为完成报告。
