# 分析框架改进意见

本文是对当前 Micro-VM 分析框架的坦诚评估与改进建议。

它不是新的机制分析，而是对“框架本身”的元层面反思：哪里已经做得好、哪里还有真实缺口、结构上怎么改进、优先级怎么排。目的是让后续研究更有效，也让读者更清楚这套材料的边界。

源码基线：当前工作树。评估基于本次系统盘点的结果。

## 1. 先肯定：框架已经做得很好的地方

在提改进之前，必须承认这套框架已经达到的成熟度，否则改进建议会失真。

1. **证据标准严格且一致**。每个结论都要求 `文件路径:行号` / 符号名，区分事实、源码推断、工程判断（`Agent.md` 工作原则）。这在中文技术分析里非常罕见，是这套材料最硬的资产。
2. **分层清晰**。项目级 `*-chain.md`（函数级链路）+ 顶层 `*-cross-project.md`（横向专题）+ `samples/`（证据资产）三层不混。`analysis/README.md` 第 2 节的目录约定有效防止了“源码链路与跨项目判断混回一层”。
3. **机制叙事扎实**。跨项目专题不只是功能清单，而是解释“为什么这样实现、机制如何串联、差异从哪来”。本文档作者审计了中断虚拟化、I/O 虚拟化两份专题，确认它们对四个活跃项目都有源码级深度，并非薄壳。
4. **判错导向**。大量专题落到“怎么分层判错、怎么取证”，例如 [中断与事件通知](./interrupt-event-notification-cross-project.md) 第 10 节的判错顺序表、[ch-cubesandbox restore 验证清单](./ch-cubesandbox-restore-guest-unavailability-checklist.md)。这让分析能直接服务运维，而不只是学术。
5. **诚实标注边界**。`non-network-evidence-gaps.md` 明确写“没有新运行证据时，继续补分析边际收益很低”——这种自我克制比无脑扩文档更有价值。

结论：框架的**机制层**已经接近饱和。改进的重点不应是“加更多机制文档”，而是结构、覆盖均衡性、综合层与可验证性。

## 2. 完整性盘点：每个专题到底缺什么

本次按“每个专题在活跃项目（Firecracker、Cloud Hypervisor、Kata、CubeSandbox）上是否有专门链路”做了盘点。图例：✓ 有专门 chain；⚠ 并入更宽 chain / 不完整；✗ 缺失；— 不适用。

| 专题 | Firecracker | Cloud Hypervisor | Kata | CubeSandbox | 评估 |
|---|---|---|---|---|---|
| 启动/控制面 | ✓ | ✓ | ✓ | ✓ | 完整 |
| CPU/vCPU/KVM | ✓ | ✓ | ✓ | ✓ | 完整 |
| 内存/DMA/IOMMU | ✓ | ✓✓ | ⚠ | ✓ | Kata 委托，可接受 |
| snapshot/restore | ✓ | ✓ | ✓ | ✓✓ | 完整 |
| 存储/rootfs/sharefs | ✓ | ✓ | ✓ | ✓ | 完整 |
| I/O 虚拟化（virtio 数据面） | ✓✓✓ | ✓ | ⚠ 委托 | ⚠ 仅 restore | 已完整（Kata/Cube 按设计委托或 restore 向） |
| 中断虚拟化 | ✓ | ✓ | ✓ | ✓✓ | 完整 |
| 设备模型/隔离 | ✓ | ✓ | ⚠ | ⚠ | 中等 |
| 运行期/热插拔 | ✓ | ✓ | ✓ | ✓ | 完整 |
| 网络 | ✓ | ✓ | ✓ | ✓✓ | 完整（ARM64 网络线最厚） |
| **安全/隔离** | ✓ | ✓（本次补） | ⚠ | ✗ | **本次补了 CH；Kata/Cube 仍散落** |
| **可观测/诊断** | ✓ | ✓ | ✓（本次补） | ✓（本次补聚合） | **本次补了 Kata + CubeSandbox 聚合** |
| 资源/QoS | ✓ | ✓ | ✓ | ✓ | 完整 |
| guest agent | — | — | ✓ | ✓ | 完整 |
| CPU/中断/机器描述 | ✓ | ✓ | ✓ | ✓ | 完整 |
| ARM64/x86 | ✓ | ✓ | ✓ | ✓ | 完整 |

本次已补的三个项目级缺口：

- [Cloud Hypervisor 隔离机制 seccomp+Landlock 链路](../cloud-hypervisor/analysis/isolation-seccomp-landlock-chain.md)
- [Kata Containers 可观测性与诊断机制链路](../kata-containers/analysis/observability-diagnostics-chain.md)
- [CubeSandbox 可观测性与诊断机制链路](../CubeSandbox-sandbox-clone/analysis/observability-diagnostics-chain.md)（聚合现有 arm64-log-* 文档）

盘点结论：**16 个专题里，14 个在活跃项目上完整或按设计委托完整**。真实剩余缺口集中在：

- **安全/隔离**：Kata（agent policy 散在 agent-rpc-boundary-chain）、CubeSandbox（seccomp/网络策略散在多份 chain）缺专门聚合 chain。
- **可观测/诊断**：crosvm（暂停）。CubeSandbox 已于本次补齐聚合 chain。

## 3. 真实不足（按优先级）

### P0：综合/学习层此前缺失（本次已部分补）

在本次工作前，框架只有“机制层”和“导航索引层”，缺“综合学习层”。一个想从零理解“如何构建高性能 VM”的读者，没有单一入口能把机制串成设计依据。

本次已补三份综合文档：

- [轻量化虚拟机设计全景与学习路线](./vm-design-landscape-overview.md)
- [性能设计依据跨项目专题分析](./performance-design-basis-cross-project.md)
- [安全设计依据跨项目专题分析](./security-design-basis-cross-project.md)

剩余建议：把这三份纳入 `analysis/README.md` 顶部的“第一次进入”推荐顺序，让学习层与机制层双向可达。

### P1：覆盖不均衡——ARM64 网络线过度，安全/可观测线偏薄

框架的文档分布有明显偏置：

- ARM64 网络线：专题、矩阵、失败签名、证据成熟度、样本 runbook、文档索引等约 10+ 份，是全框架最厚的子线。
- 安全/可观测线：项目级 chain 不齐（见第 2 节）。

这不是说 ARM64 网络不重要（它确实是真实判错场景），但当框架自己说“继续补 ARM64 网络框架边际收益已很低”（`README.md` 第 3 节）时，人力应转到偏薄的安全/可观测线。

建议（本次已部分完成）：可观测轴的 CubeSandbox `observability-diagnostics-chain.md` 已于本次补齐（聚合现有 arm64-log-source-map / arm64-log-collection-gap / cube-diag / /readyz / quickcheck），至此四个活跃项目都有专门可观测 chain。仍建议补 CubeSandbox 的 `isolation-security-chain.md`（聚合 CubeShim seccomp / network-agent 策略 / CubeVS eBPF / snapshot mode 隔离语义）与 Kata 的安全聚合 chain，让安全轴在四个活跃项目上对齐。

### P2：定量数据与机制分析脱节

框架有丰富的实测数据（`sandbox-bench/`、`CubeSandbox/.trellis/.../benchmark-*`），但它们基本独立于机制分析：

- 1000 Firecracker 实例密度的实测（`sandbox-bench/docs/high-density-firecracker-notes.md`）没有进入任何启动/密度机制叙事。
- arm64 context-switch 成本（`sandbox-bench/docs/context-switch-cost-experiment.zh.md`，p50 约 1.2µs）没有进入 CPU/调度机制叙事。
- CubeSandbox c100 restore p99 约 2.7s 的调优数据（`.trellis/.../restore-bottleneck-current-summary-zh.md`）只在调优笔记里，没进入 snapshot/restore 机制叙事。

本次综合文档已开始把这些数字串进性能叙事，但机制层 chain 本身仍缺定量锚点。

建议：在关键机制 chain（启动、I/O 数据面、snapshot/restore、CPU/调度）里加“实测锚点”小节，引用 `sandbox-bench/` 对应数据，让“机制”与“性能数字”互相印证。

### P3：crosvm 暂停导致设计空间不完整

crosvm 的 process-per-device 是五个项目里**唯一**的进程级设备隔离范式，对理解“完整设计空间”不可替代。当前框架把 crosvm 设为“暂停继续扩展”（`four-project-deep-routes.md` 第 10 节），导致：

- 跨项目专题里 crosvm 只作“历史背景”一笔带过。
- 综合/学习层（本次新写）只能在设计哲学对照里引用已有 crosvm 文档，无法做新的函数级验证。

这本身是合理的范围控制（避免无限扩面），但代价是设计空间少了一个关键对照点。

建议（可选）：不恢复 crosvm 主线，但在综合层（本次的 landscape 与 design-basis）保留 crosvm 作为“设计范式对照”，并在改进后续若有余力，针对 crosvm 的 process-per-device + Minijail 做一次定向补证（只这一条，不扩面），让进程级隔离范式有源码级闭环。

### P4：runtime-rs 与 Go runtime 的覆盖不对称

Kata 有两套 runtime（Go `src/runtime`、Rust `src/runtime-rs`）。当前链路偏向 Go runtime（多数 chain 引用 `service.go`、`kata_agent.go`）。runtime-rs 的等价机制（事件流、监控、资源）覆盖偏薄。

本次新写的 [Kata 可观测链路](../kata-containers/analysis/observability-diagnostics-chain.md) 第 9 节已标注此缺口。建议后续补 runtime-rs 的事件/监控/资源链路，让 Kata 两套 runtime 的可观测与资源语义对齐。

### P5：CoCo/机密计算的暂缓是正确的，但边界要持续标注

Kata CoCo、TDX/SEV-SNP/CCA 暂缓是合理范围控制。但机密计算是“威胁 ③（恶意 host 窥探 guest）”的主防线，在安全设计依据里必须作为“已知未展开”显式存在，不能让读者误以为框架已覆盖安全全貌。

本次 [安全设计依据](./security-design-basis-cross-project.md) 第 1 节已把 CoCo 定位为威胁 ③ 的主防线并标注暂缓。建议后续在 `coco-pvm-protected-vm-cross-project.md` 顶部加一句“本专题为历史/暂缓参考，机密计算是威胁③主防线，恢复时优先”的引导，避免它被当成废弃文档。

## 4. 结构性改进建议

除了补内容，框架结构本身有三点可改进：

### 4.1 建立“专题完成度看板”并定期刷新

当前完成度判断散落在 `four-project-route-coverage-matrix.md`（路线维度）与各 `README.md`（导航维度），没有一张“专题 × 项目”的完成度看板。

建议：把本文第 2 节的盘点表固化成 `analysis/topic-completeness-matrix.md`，每次补完一个 chain 就更新一格。这样下次任何人（人或 agent）进入框架，能立刻看到哪里还薄，而不是靠读 16 份专题各自判断。

### 4.2 综合层与机制层双向链接

机制层 chain 目前只向上链接到横向专题，不链接到综合层。综合层（本次新写）向下链接到机制，但机制不回链。

建议：在每份机制 chain 的开头“相关横向专题”区，增加“相关综合文档”一行，链接到 landscape / performance-basis / security-basis 中最相关的那份。让读者从任一 chain 都能跳到设计依据层。

### 4.3 给 samples/ 加“机制锚点”反向索引

`samples/` 体系很完整（template/seed/real/validated），但样本与机制 chain 是单向的（chain 引用 sample，sample 不回引 chain 里的具体行号）。

建议：在 `samples/INDEX.md` 为每个 real/baseline 样本标注它印证了哪份 chain 的哪段结论，形成“机制 ↔ 证据”双向索引，提升样本的判错复用价值。

## 5. 推荐的下一步优先级

综合以上，如果继续推进，建议按这个顺序：

1. **P1**：补 CubeSandbox `observability-diagnostics-chain.md` 与 `isolation-security-chain.md`，让安全/可观测在四活跃项目对齐。（最高价值，闭合矩阵）
2. **P0 收尾**：把本次三份综合文档纳入 `README.md` 推荐顺序，并给机制 chain 加综合层回链。（低成本，高可达性）
3. **P2**：给启动/I/O/snapshot/CPU 四条机制 chain 加“实测锚点”小节，引用 sandbox-bench 数据。（让机制与数字互证）
4. **P4**：补 Kata runtime-rs 的事件/监控/资源链路。（闭合 Kata 双 runtime）
5. **P3/P5**：视余力做 crosvm process-per-device 定向补证、CoCo 引导标注。（设计空间完整性与安全全貌）

## 6. 关于“分析完整”的边界判断

最后是一个元判断。框架自己的 `non-network-evidence-gaps.md` 已经说了：**没有新运行证据时，继续补分析边际收益很低**。这个判断在本次盘点后依然成立：

- 机制层 13/16 专题已完整或按设计委托完整。
- 真正稀缺的不是“更多机制文档”，而是“新的运行证据”（真实样本、failure bundle、定量数据）。

因此“分析完整”不应被理解成“把每个专题都写到无限深”，而应理解成：

1. 每个专题在活跃项目上有专门 chain 或明确的委托说明（本次已基本达成）。
2. 机制与定量数据互证（P2，待做）。
3. 综合层把机制收成可推理的设计依据（本次已做）。

达到这三点后，框架的边际改进就应转向“采新证据”而非“写新文档”。这个判断本身也是对框架健康度的正面信号——一个能诚实说出“自己快饱和”的分析框架，比一个无限膨胀的框架更有用。

## 7. 本次工作产出索引

本次工作产出的全部文档与改动：

综合层（新写）：

- [轻量化虚拟机设计全景与学习路线](./vm-design-landscape-overview.md)
- [性能设计依据跨项目专题分析](./performance-design-basis-cross-project.md)
- [安全设计依据跨项目专题分析](./security-design-basis-cross-project.md)
- 本文（分析框架改进意见）

机制层（本次补的项目级缺口）：

- [Cloud Hypervisor 隔离机制 seccomp+Landlock 链路](../cloud-hypervisor/analysis/isolation-seccomp-landlock-chain.md)
- [Kata Containers 可观测性与诊断机制链路](../kata-containers/analysis/observability-diagnostics-chain.md)
- [CubeSandbox 可观测性与诊断机制链路](../CubeSandbox-sandbox-clone/analysis/observability-diagnostics-chain.md)

导航层（改动）：

- Cloud Hypervisor / Kata / CubeSandbox 的 `deep-routes.md` 已加入新 chain 的项目级深挖链接。
- `analysis/README.md` 加入“第 0 节：系统学习入口”，指向综合学习层。
- `analysis/four-project-deep-routes.md` 加入综合学习层索引。
- `analysis/four-project-route-coverage-matrix.md` 更新安全/可观测轴完成度并加 2026-06 更新小节。
