# 一页 PPT 内容：共同链路相似，差异在“复用资产 + 节点执行链”

## 副标题

API 独立入口 → 控制面 → 节点执行 → 资产准备 → 冷/热启动 → guest ready → 路由返回；基于 2026-08-27 latest stable 源码，Source-backed，不含性能排名。

## 图例与阅读方式

- 深色圆角框只表示对外 API 入口；内部组件从下一层开始，API 名称不再与组件清单混写。
- 蓝/青/紫实线分别表示三个平台的主执行链；橙色为冷创建，绿色为 snapshot/paused 热恢复，两条真实分支在 VMM 层汇合。
- 每列采用相同抽象层级：API → 控制面 → 节点执行 → 资产 → 冷/热 → VMM → Guest → 路由返回。

## 三列内容

### CubeSandbox

版本：`v0.6.0@8721dd15` [C1]

定位：自建 Cube Sandbox 控制面；CubeAPI/CubeMaster 负责请求与调度，Cubelet/CBRI/CubeShim 承担节点执行，Cloud Hypervisor/KVM 承担 MicroVM 生命周期。

创建 / 恢复链：

1. **API 层**：接收 `POST /sandboxes`。
2. **控制面**：CubeAPI 将请求交给 CubeMaster；解析 template，调用 `scheduler.Select` 选择宿主机。
3. **节点执行**：CubeMaster dispatch 到 Cubelet；经 CBRI 进入 CubeShim。
4. **资产准备**：CubeCow 准备 rootfs；建立 TAP/CubeVS 网络；快照路径携带 snapshot annotations。
5. **冷 / 热分叉**：冷路径由 CubeShim `boot_vm`；热路径由 `restore_vm` 恢复快照。
6. **VMM**：两条路径汇入 CubeHypervisor，再进入 Cloud Hypervisor/KVM。
7. **Guest ready**：通过 vsock 等待 guest agent/envd ready。
8. **状态 / 路由返回**：CubeMaster 成功路径写入 sandbox status 与 proxy/spec metadata，CubeAPI 返回可用信息；CubeProxy/CubeEgress 分别承接后续入站代理与 egress 策略。

技术标签：Cloud Hypervisor/KVM、CubeCow reflink、TAP/eBPF CubeVS、CubeEgress、systemd/Helm。

差异化结论：复杂度放在自建控制面、CubeCow 与网络/egress 策略闭环，强调平台边界可控。[C2]

### AgentENV

版本：`v0.1.3@7f4a9b9f` [A1]

定位：E2B 兼容 Gateway/Scheduler/Node runtime；Gateway 和 Scheduler 处理入口与 assignment，Node Orchestrator 主控节点生命周期。

创建 / 恢复链：

1. **API 层**：Gateway 接收 `POST /sandboxes` 与 E2B headers。
2. **控制面**：Gateway 请求 Scheduler；Scheduler 选择 Node，assignment 在 Sandbox ready 后记录。
3. **节点执行**：Node Orchestrator 将 Image/Snapshot 转成 `LaunchPlan`，交给 `FirecrackerSandbox`。
4. **资产准备**：从 Firecracker、Network、ublk warm pools 获取资源；OverlayBD 提供 rootfs。
5. **冷 / 热分叉**：冷路径创建 fresh VM；热路径按 snapshot 或 paused 状态恢复。
6. **VMM**：两条路径汇入 FirecrackerSandbox/Firecracker/KVM。
7. **Guest ready**：`wait_for_ready` 等待 envd，guest API 开始可响应。
8. **路由返回**：记录 assignment，由 Gateway proxy 到目标 Node，返回可用 Sandbox。

技术标签：Firecracker/KVM、FirecrackerPool、OverlayBD/ublk、Network warm pool、E2B headers。

差异化结论：复杂度集中在节点侧预热池，以及 VM、块设备和网络资产的复用。[A2]

### E2B-infra

版本：`2026.29@557445ff` [E1]

定位：E2B 云平台自身基础设施；API orchestrator、placement 与 node orchestrator 分层，并用 catalog/proxy 发布 Sandbox 路由。

创建 / 恢复链：

1. **API 层**：`PostSandboxes` handler 接收 `POST /sandboxes`。
2. **控制面**：API orchestrator reserve capacity，使用 BestOfK placement 选择 node。
3. **节点执行**：经 node gRPC 进入 node orchestrator 的 create/resume service。
4. **资产准备**：解析 Template cache，两条路径准备 NBD rootfs 和 network slot；snapshot 恢复路径额外初始化 UFFD memory。
5. **filesystem-only / snapshot 分叉**：`Server.Create` 对 filesystem-only template 调用 `RebootSandbox` 冷启动，只保留 filesystem；对含内存状态的 snapshot template 调用 `ResumeSandbox`。
6. **VMM**：两条路径汇入 Firecracker process/control 与 KVM。
7. **Guest ready**：写入 MMDS，并由 `WaitForEnvd` 确认 guest 就绪。
8. **路由返回**：发布 Redis catalog，client-proxy 据此转发并返回可用 Sandbox。

技术标签：Firecracker/KVM、NBD overlay、UFFD memory、MMDS/envd、Terraform/Nomad。

差异化结论：复杂度放在云编排、snapshot assets 与 routing catalog，体现 E2B 原生云交付耦合。[E2]

## 底部 Executive takeaways

1. **共同抽象 [X1]**：三者都把外部请求转换为 placement、资产准备、MicroVM 启动/恢复、guest ready 和 route publication。
2. **核心分歧**：Cube 是 Cloud Hypervisor + CubeCow + CubeVS；AgentENV 是 Firecracker + warm pools + OverlayBD/ublk；E2B 是 Firecracker + NBD/UFFD/MMDS。
3. **工程选型**：不按未经同条件验证的性能数字排序；评审控制边界、复用资产模型、网络策略位置与运维耦合。

## 页脚

CubeSandbox `v0.6.0@8721dd151971ce3c2966482bbd32904ad98f378e` · AgentENV `v0.1.3@7f4a9b9f198e350fbf1e514b837eabb277ecb2f8` · E2B-infra `2026.29@557445ffddda8d9a27f6f529a3f4d7732cf81a13`

分析日期 2026-08-27 · Source-backed · API 与组件分层 · 默认分支 HEAD 新能力未混入 · 不含性能排名 · 证据见 `three-platform-source-comparison.md`

## 90 秒讲稿

**0–12 秒**：三个平台都把一个 Sandbox 请求转换为同一类 MicroVM 执行链：调度节点、准备资产、冷启动或热恢复、等待 guest ready，再发布路由。图里深色框只表示 API；下面才是平台内部组件，因此接口和架构组件不会混在一起。

**12–31 秒**：CubeSandbox 左列从 `POST /sandboxes` 进入 CubeAPI/CubeMaster，完成 template 解析和调度；目标节点经 Cubelet、CBRI 到 CubeShim，再准备 CubeCow rootfs 与 TAP/CubeVS。冷路径 `boot_vm`，热路径 `restore_vm`，最终汇入 CubeHypervisor 和 Cloud Hypervisor/KVM；等 agent/envd ready 后，CubeMaster 写入 proxy/spec metadata 并由 CubeAPI 返回，CubeProxy/CubeEgress 承接后续访问面。

**31–50 秒**：AgentENV 中列由 Gateway 和 Scheduler 建立 Node assignment，Node Orchestrator 把 Image 或 Snapshot 转成 LaunchPlan。它会复用 Firecracker、Network 和 ublk pools，rootfs 使用 OverlayBD；随后 fresh 与 snapshot/paused resume 两条路径汇入 Firecracker，等 envd ready，再记录 assignment 并由 Gateway proxy 返回。

**50–69 秒**：E2B-infra 右列由 API orchestrator reserve capacity，并用 BestOfK placement 选择 node；node orchestrator 准备 Template cache、NBD rootfs 和 network slot，snapshot 路径再初始化 UFFD memory。用户 create 在这里不是统一的 Firecracker Create：filesystem-only template 走 `RebootSandbox` 冷启动，snapshot template 走 `ResumeSandbox` 恢复内存状态；随后写 MMDS、等待 envd，再发布 Redis catalog 路由。

**69–82 秒**：所以核心差异不在 API 形状，而在复用什么资产、节点侧承担多少复杂度：Cube 自建 Cloud Hypervisor、CubeCow 与网络策略；AgentENV 强调 VM/块设备/网络池化；E2B 把 NBD、UFFD、MMDS 与云编排、catalog 组合起来。

**82–90 秒**：选型时应评审平台控制边界、热恢复资产模型、网络和 egress 策略位置、以及对现有 E2B 工作流和云基础设施的耦合，不做缺乏同条件证据的性能排名。

## 脚注映射

- `[C1]` CubeSandbox release baseline：`version-baselines.md`。
- `[C2]` CubeSandbox component/flow evidence：`cubesandbox-components-flow.md`。
- `[A1]` AgentENV release baseline：`version-baselines.md`。
- `[A2]` AgentENV component/flow evidence：`agentenv-components-flow.md`。
- `[E1]` E2B-infra release baseline：`version-baselines.md`。
- `[E2]` E2B-infra component/flow evidence：`e2b-infra-components-flow.md`。
- `[X1]` Cross-platform abstract flow：`technology-matrix.md`。
