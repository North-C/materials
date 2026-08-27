# 一页 PPT 内容：共同链路相似，差异在“复用资产 + 节点执行链”

## 副标题

左侧统一阶段轴：API → 调度 → 节点执行 → 并列资产组 → 启动/恢复 → Ready & Route；基于 2026-08-27 latest stable 源码，Source-backed，不含性能排名。

## 图例与阅读方式

- 左侧只出现一次统一阶段名；右侧同一行横向比较 CubeSandbox、AgentENV、E2B-infra，避免在每个平台中重复“控制面/节点执行/资产准备”。
- 每个平台的深色首行只表示 API 入口，并同时给出项目短名、短版本和 `POST /sandboxes`；内部组件从控制面行开始，API 与组件清单不混写。
- 虚线资产容器内的网络、模板/根盘、内存/CoW 是同一准备阶段的三个并列维度，不是时间串行链；主流程从节点执行进入整个资产组，再分叉到冷/热路径。
- 蓝/青/紫表示平台主链；橙色表示冷创建或 filesystem-only reboot，绿色表示 snapshot/paused 恢复；两条路径最终汇入各自的 VMM/Ready/Route 节点。
- 页脚只保留精确版本；完整技术矩阵、结论和证据仍在 `three-platform-source-comparison.md`。

## 三平台横向内容

### CubeSandbox

版本：`v0.6.0@8721dd15` [C1]

定位：自建 Cube Sandbox 控制面；CubeAPI/CubeMaster 负责请求、模板解析与调度，Cubelet/CBRI/CubeShim 承担目标节点执行，Cloud Hypervisor/KVM 承担 MicroVM 生命周期。

阶段内容：

1. **API 入口**：`POST /sandboxes`。
2. **控制面**：`CubeAPI → CubeMaster → scheduler.Select`。
3. **节点执行**：`Cubelet → CBRI → CubeShim`。
4. **资产 · 网络**：Cubelet/CBRI 把 TAP FD 与网络配置交给 CubeShim；network-agent/CubeVS 使用 eBPF 数据面，CubeEgress 承接 egress policy。
5. **资产 · 模板/根盘**：默认 `cube-guest-image-cpu.img` 是 virtio-pmem `/dev/pmem0`，kernel root 使用 ext4 + DAX + ro；Cubelet/CBRI 经 `AnnotationPmem` 添加的 app ext4 image 使用 offset 1，从 `/dev/pmem1` 起以 ro,DAX 挂载。CubeCow `FICLONE` 是 volume/storage reflink，不是加载动作。
6. **资产 · 内存/CoW**：热恢复的内存资产是 `SnapshotInfo` 与 `memory_vol_url`；CoW 只表示 volume/storage 的 reflink/FICLONE 边界，不写成内存 CoW。
7. **启动/恢复**：冷路径 `boot_vm`；热路径 `restore_vm`。
8. **VMM/Ready/Route**：`Cloud Hypervisor/KVM → guest agent/envd → CubeAPI metadata` 返回；CubeProxy/CubeEgress 分别承接后续入站代理与 egress 策略。[C2]

### AgentENV

版本：`v0.1.3@7f4a9b9f` [A1]

定位：E2B 兼容 Gateway/Scheduler/Node runtime；Gateway 和 Scheduler 处理入口与 Node selection，Node Orchestrator 主控节点生命周期。

阶段内容：

1. **API 入口**：Gateway 接收 `POST /sandboxes` 与 E2B headers。
2. **控制面**：`Gateway → Scheduler → Node selection`；Sandbox ready 后记录 assignment。
3. **节点执行**：`Node Orchestrator → LaunchPlan → FirecrackerSandbox`。
4. **资产 · 网络**：NetworkManager 准备 netns/veth 与 address plan，并从 Network warm pool 复用网络资源。
5. **资产 · 模板/根盘**：Image 或 RunnableSnapshot 由 LaunchPlan 选择 load 方式；可写 user image 的设备链为 `OverlayBD runtime → host ublk device → user-rootfs symlink → Firecracker Drive1`，guest 内对应 `/dev/vdb`。Guest `/dev/vda` 是 plain ext4、只读的 tools root drive。
6. **资产 · 内存/CoW**：snapshot 资产包含 `vm_state.bin` 与 OverlayBD memory layer；dirty-page/compression 由选定版本配置控制。
7. **启动/恢复**：冷路径创建 fresh VM；热路径按 snapshot 或 paused 状态恢复。
8. **VMM/Ready/Route**：`Firecracker/KVM → envd → assignment/Gateway proxy`，返回可用 Sandbox。[A2]

### E2B-infra

版本：`2026.29@557445ff` [E1]

定位：E2B 云平台自身基础设施；API orchestrator、BestOfK placement 与 node orchestrator 分层，并用 Redis catalog/client-proxy 发布 Sandbox 路由。

阶段内容：

1. **API 入口**：`PostSandboxes` handler 接收 `POST /sandboxes`。
2. **控制面**：`API orchestrator → reserve → BestOfK placement`。
3. **节点执行**：`node gRPC → node orchestrator` 的 create/resume service。
4. **资产 · 网络**：network slot pool 准备 netns、TAP、IP/MAC，并维护 sandbox map/token。
5. **资产 · 模板/根盘**：Template rootfs 进入 NBD block cache + overlay，host provider path 可为 `/dev/nbdX`；Firecracker 用 `PutGuestDriveByID` 把该 host path 配置成 guest root drive，不表示 guest 也看到 `/dev/nbdX`。NBD/XFS reflink 只属于 storage/overlay 边界。
6. **资产 · 内存/CoW**：snapshot 使用 Memfile/Snapfile，UFFD 提供 lazy memory；不把 NBD/XFS reflink 写成内存 CoW。
7. **启动/恢复**：filesystem-only template 走 `RebootSandbox`；含内存状态的 snapshot template 走 `ResumeSandbox`。
8. **VMM/Ready/Route**：`Firecracker/KVM → MMDS/envd → Redis catalog/client-proxy`，返回可用 Sandbox。[E2]

## 页脚

CubeSandbox `v0.6.0@8721dd151971ce3c2966482bbd32904ad98f378e` · AgentENV `v0.1.3@7f4a9b9f198e350fbf1e514b837eabb277ecb2f8` · E2B-infra `2026.29@557445ffddda8d9a27f6f529a3f4d7732cf81a13`

## 90 秒讲稿

**0–12 秒**：这页改为一条统一阶段轴。横向看，三个 API 都把请求交给控制面和节点执行；纵向看，网络、根盘和内存是同一个资产准备阶段里的并列维度，不是三段串行调用。真正的分歧是每个平台复用什么资产，以及复杂度放在控制面还是节点侧。

**12–31 秒**：CubeSandbox 从 CubeAPI/CubeMaster 调度到 Cubelet、CBRI 和 CubeShim。网络侧是 TAP、CubeVS/eBPF 与 Egress policy；设备侧要区分两层：guest base root 是支持 DAX 的 virtio-pmem `/dev/pmem0`，CBRI 追加的 app ext4 image 从 `/dev/pmem1` 起。CubeCow FICLONE 只负责 storage reflink；内存恢复另用 SnapshotInfo 与 `memory_vol_url`。

**31–50 秒**：AgentENV 由 Gateway/Scheduler 选择 Node，Node Orchestrator 生成 LaunchPlan。网络侧有 netns/veth、address plan 与 warm pool；user image 从 OverlayBD 进入 host ublk，再交给 Firecracker，guest 内是 `/dev/vdb`，而 guest `/dev/vda` 是只读 tools root。内存 snapshot 另走 `vm_state.bin` 与 memory backend。fresh/resume 汇入 Firecracker，envd ready 后由 Gateway proxy 返回。

**50–69 秒**：E2B-infra 由 API orchestrator reserve capacity，再用 BestOfK 选择 node。网络 slot 管理 netns、TAP、IP/MAC；Template rootfs 经 NBD cache/overlay 形成 host `/dev/nbdX` provider path，再配置成 Firecracker guest root drive；Memfile/Snapfile 和 UFFD 是独立内存链。filesystem-only 走 Reboot，snapshot 走 Resume，随后经 MMDS、WaitForEnvd 和 catalog/proxy 返回。

**69–82 秒**：横向收束：Cube 侧重自建 Cloud Hypervisor、CubeCow 和网络策略；AgentENV 侧重 VM、网络和 ublk 的 warm pool 与 OverlayBD；E2B 侧重 NBD、UFFD、MMDS 与云编排/catalog 的组合。三者的资产边界不同，不能用一个“快照能力”标签替代机制比较。

**82–90 秒**：选型时应评审平台控制边界、热恢复资产模型、网络和 egress 策略位置、以及与现有 E2B 工作流和云基础设施的耦合；本页只比较源码机制，不做缺乏同条件证据的性能排名。

## 脚注映射

- `[C1]` CubeSandbox release baseline：见 `three-platform-source-comparison.md` 第 2、8 节。
- `[C2]` CubeSandbox component/flow evidence：见 `three-platform-source-comparison.md` 第 4–6、8 节。
- `[A1]` AgentENV release baseline：见 `three-platform-source-comparison.md` 第 2、8 节。
- `[A2]` AgentENV component/flow evidence：见 `three-platform-source-comparison.md` 第 4–6、8 节。
- `[E1]` E2B-infra release baseline：见 `three-platform-source-comparison.md` 第 2、8 节。
- `[E2]` E2B-infra component/flow evidence：见 `three-platform-source-comparison.md` 第 4–6、8 节。
