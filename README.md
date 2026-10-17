# Materials 技术资料导航

本仓库收录虚拟化、云原生、AI Sandbox、性能测试与工程实践资料。按主题查阅下面的入口；实验报告的版本、机器、日期和证据范围以各自正文为准。

补充材料前先读 [Agent 材料补充规范](AGENTS.md)；CubeSandbox 另有 [专项归档规则](ai_sandbox/cubesandbox/AGENTS.md)，规定存放位置、索引更新和测试证据要求。

## 主题分类

| 类别 | 入口 | 内容 |
| --- | --- | --- |
| CubeSandbox | [专题导航](ai_sandbox/cubesandbox/README.md) | 架构、版本演进、ARM64 适配、镜像与内核、性能、故障修复及历史报告 |
| AI Sandbox 与 MicroVM | [平台资料导航](ai_sandbox/README.md) | Firecracker、Cloud Hypervisor、StratoVirt、Kata、gVisor、E2B、Nydus 与跨项目分析 |
| KVM 与 ARM64 虚拟化 | [KVM](kvm/)、[虚拟化](virtualization/) | KVM/QEMU、CPU、内存、中断、timer、virtio、架构手册与学习路线 |
| Kubernetes 与资源管理 | [kubelet 源代码解析](kubelet源代码解析/)、[Katalyst](katalyst分析/)、[MPAM](mpam/) | kubelet 组件、资源分配、监控与硬件资源隔离 |
| Kata 启动时延 | [基础测试](kata-startup-latency-lite/README.md)、[direct](kata-startup-latency-direct-lite/README.md)、[direct + Nydus](kata-startup-latency-direct-nydus-lite/README.md) | 各测试方式的独立材料；[direct 结果](results-direct-lite/)与[辅助脚本](scripts/)单独保留 |
| AI / Agent 调研与负载 | [研究导航](research/README.md) | Agent 趋势、CPU 需求、benchmark 目录与任务工具包 |
| 可观测性与存储专题 | [tracing](tracing/)、[unified_bus](unified_bus/) | bpftrace 与 ubcache snapshotter 分析 |
| 故障与运维 | [bug-fix](bug-fix/)、[操作记录](Ops_records/) | execSync、kubectl cp 问题与操作记录 |
| 机器环境 | [machine-configs](machine-configs/) | 按机器和日期归档的配置报告；用于核对实验环境 |
| 工程方法与综合文章 | [软件工程](软件工程/)、[每日项目简析](每日项目简析/)、[Paperwork](Paperwork/) | Agent 使用、设计文档、重构、项目分析和综合报告 |

## CubeSandbox 常用入口

| 要查的内容 | 入口 |
| --- | --- |
| 性能报告、阶段耗时与时间轴 | [性能分析索引](ai_sandbox/cubesandbox/perf/README.md) |
| c100n100 优化方法、补丁与复测 | [调优复现指南](ai_sandbox/cubesandbox/c100n100-perf-tuning/README.zh-CN.md) |
| workload、镜像来源、核心性能与生命周期测试 | [Benchmark 索引](ai_sandbox/cubesandbox/benchmark/README.md) |
| SWE 轨迹回放与密度测试 | [回放测试入口](ai_sandbox/cubesandbox/benchmark/swe-replay-density/README.md) |
| v0.7.1 / v0.5.1 对比数据 | [cube-bench 对比](cube-bench对比/README.md) |
| Go 参数与 NUMA 实验 | [实验与配置入口](cube-bench-go-numa-20261016/README.md) |
| 早期 ARM64 问题与测试报告 | [CubeSandbox 根目录文档分类](ai_sandbox/cubesandbox/README.md#根目录文档分类) |

两套顶层 CubeSandbox 实验目录作为独立证据包保留，已纳入专题导航；不要仅凭目录位置把它们当作其他项目。

## 根目录零散资料

| 类别 | 文档 |
| --- | --- |
| 云原生与资源隔离 | [趋势报告](cloud-native-trends-report.md)、[容器资源隔离](容器资源隔离.md)、[Policy 模块设计](Policy模块设计文档.md) |
| 开发与交付 | [Go 内部机制](golang_under_the_hood.md)、[并发问题](并发问题.md)、[BDD 与 Cucumber](BDD与cucumber.md)、[Docker 镜像编译](docker镜像编译.md)、[Jenkins](jenkins使用.md) |
| 日志与设计笔记 | [klog](klog日志实践.md)、[日志](日志.md)、[design](design.md) |
| 硬件基础 | [不同芯片系列](不同芯片系列.md)、[指令集学习](指令集学习.md) |
| 讨论与工作记录 | [华泰问题讨论](华泰问题讨论.md)、[专利修改问题](专利修改问题.md)、[记录](记录) |
| 图稿 | [K8s manager](k8s-manager.excalidraw)、[TAP plugin](tap-plugin.excalidraw) |

## 归档约定

- 先按主题进入，再按文档类型区分：指南、源码分析、测试报告、原始证据和派生结果。
- 报告与配套 CSV、JSON、日志、图表、校验清单共同保留；新增轮次使用独立日期或 run 目录，并更新所属主题索引。
- 历史报告只描述记录时的版本和环境；报告名称中的“根因”“优化”或“当前”不自动代表今天的结论。
- 本次分类通过导航建立主题关系，保留已有文件名与路径；本地草稿、缓存和未跟踪文件不作为正式归档入口。
