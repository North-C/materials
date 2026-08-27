# CubeSandbox、AgentENV、E2B-infra 三个平台源码对比

分析日期：2026-08-27
受众：技术管理 / 架构评审，3–5 分钟单页汇报
证据边界：pinned stable 源码、配置、测试与官方 release/tag/commit；不运行远端环境，不做性能排名。

## 1. 结论

三个平台共享同一条 MicroVM Sandbox 抽象链：`API/SDK 请求 → 调度/节点选择 → 模板/资产解析 → rootfs/memory/network 准备 → VMM 启动或 snapshot/template 恢复 → guest agent/envd ready → route/assignment → 返回可用`。

真正的架构分歧不在“是否提供 Sandbox API”，而在三点：

1. **控制面边界**：CubeSandbox 和 AgentENV 都强调 E2B 风格/兼容入口，但 CubeSandbox 是 CubeAPI/CubeMaster/Cubelet 自建控制面，AgentENV 是 Gateway/Scheduler/Node runtime；E2B-infra 是 E2B 云平台自身。
2. **热恢复资产模型**：CubeSandbox 使用 Cloud Hypervisor snapshot restore + CubeCow reflink；AgentENV 使用 Firecracker + RunnableSnapshot/LaunchPlan + OverlayBD/ublk；E2B-infra 使用 Firecracker snapshot resume + NBD overlay + UFFD memory + MMDS/envd。
3. **复用和运维复杂度放置位置**：CubeSandbox 更偏平台自建组件闭环；AgentENV 更偏节点侧 warm pools；E2B-infra 更偏生产云控制面、routing catalog、Terraform/Nomad 交付。

## 2. 版本范围

主对比固定 latest stable release。默认分支 HEAD 仅用于“版本演化观察”，不进入能力表。

| 项目 | 主分析版本 | 完整 commit | commit date / release | 默认分支 HEAD | 口径 |
|---|---|---|---|---|---|
| CubeSandbox | `v0.6.0` | `8721dd151971ce3c2966482bbd32904ad98f378e` | commit `2026-07-24T08:11:29Z`；release `2026-07-24T08:14:00Z` | `master@b2605d50808d32edab8e3b6d1b501529e6b1f5e3` | `v0.7.0-rc1` 是 prerelease，不进入主对比。 |
| AgentENV | `v0.1.3` | `7f4a9b9f198e350fbf1e514b837eabb277ecb2f8` | author `2026-08-20T06:22:47Z`；committer `2026-08-20T06:43:51Z`；release `2026-08-20T07:19:58Z` | `main@4a2d610454dfda2321442a50b5a54708af058833` | 使用 latest stable。 |
| E2B-infra | `2026.29` | `557445ffddda8d9a27f6f529a3f4d7732cf81a13` | commit `2026-07-16T09:50:15Z`；release `2026-07-28T13:17:55Z` | `main@d843e3f00d708e292c31a5841a2fe1fcfc1f2997` | monorepo 组件 tag 不替代平台 release。 |

证据分类：以上版本行均为 **Official release fact**，由 GitHub Releases/tags/API 与 `git ls-remote` 复核；本节表格保留完整 tag、commit、日期和分析选择。

## 3. 产品定位与边界

| 项目 | 面向谁 | 控制面 / 数据面边界 | 交付形态 | 主要隔离与复用目标 |
|---|---|---|---|---|
| CubeSandbox | 需要自建 MicroVM Sandbox、同时保留 E2B 风格 API/路由的 Agent/云原生平台。 | CubeAPI 接外部请求；CubeMaster 调度与 template/snapshot；Cubelet/CBRI、CubeShim、guest agent 执行本机生命周期。 | one-click systemd 与 Helm chart；chart `appVersion` 落后，不能当 v0.6.0 镜像事实。 | KVM/Cloud Hypervisor MicroVM、snapshot restore、CubeCow reflink、TAP/eBPF、CubeProxy/CubeEgress。 |
| AgentENV | 需要 E2B 兼容 API、自建 Gateway/Scheduler/Node runtime 的 Agent 执行平台。 | Gateway/API 与 proxy；Scheduler 选择 node；Node Orchestrator 执行 Firecracker sandbox 生命周期。 | docker-compose 与 K8s manifest；runtime DaemonSet privileged、KVM、ublk daemon、`/dev` mount。 | Firecracker/KVM、RunnableSnapshot/LaunchPlan、FirecrackerPool、Network warm pool、OverlayBD/ublk、proxy assignment。 |
| E2B-infra | E2B 云平台自身基础设施。 | API handler/API orchestrator 做 token、template、concurrency、placement、routing；node orchestrator 做 template cache、NBD/UFFD、Firecracker、envd。 | Terraform AWS/GCP + Cloudflare/Nomad + Nomad job modules。 | Firecracker snapshot resume、NBD overlay/cache、UFFD memory、MMDS/envd、Redis routing catalog、network slot pool。 |

## 4. 主要组件

### CubeSandbox

| 组件 | 职责 | 证据 |
|---|---|---|
| CubeAPI | E2B 风格 `/sandboxes`、snapshot、pause/resume、connect 路由；将 `NewSandbox` 映射到 CubeMaster request。 | `CubeAPI/src/routes.rs:77-130`；`CubeAPI/src/services/sandboxes.rs:153-291` |
| CubeMaster | 解析/默认化请求，解析 template/snapshot，调度 host，调用 Cubelet，成功后写 sandbox/proxy/spec。 | `CubeMaster/pkg/service/httpservice/cube/sandbox_create.go:24-170`；`CubeMaster/pkg/service/sandbox/sandbox_run.go:104-340` |
| Cubelet / CBRI | 本机创建入口；cubebox 插件解析 app image/kernel/rootfs；ext4 image 经 `genPmemOpt` 写入 `AnnotationPmem`。 | `Cubelet/plugins/cbri/local.go:70-81`；`Cubelet/plugins/cbri/cubeboxcbri/cubebox.go:102-260`、`:351-399` |
| CubeShim / CubeHypervisor | 创建 VM 目录、启动/恢复 VMM、等待 vsock、调用 guest agent；Cloud Hypervisor API 封装 create/boot/snapshot/pause/resume/restore。 | `CubeShim/shim/src/sandbox/sb.rs:139-202`、`:832-999`；`CubeShim/shim/src/hypervisor/cube_hypervisor.rs:75-183` |
| CubeCow | reflink backend，FICLONE-capable FS 探测，snapshot sibling file。 | `cubecow/src/config/mod.rs:20-83`；`cubecow/src/engine/reflink.rs:131-177`、`:443-462` |
| Guest/app rootfs devices | 默认 guest image 是 virtio-pmem `/dev/pmem0`，kernel root 为 ext4 + DAX + ro；CBRI 添加的 app ext4 image 使用 offset 1，从 `/dev/pmem1` 起 ro,DAX 挂载。 | `CubeShim/shim/src/hypervisor/config.rs:28`、`:72-77`、`:98-101`；`CubeShim/shim/src/sandbox/pmem.rs:13`、`:29-43`；`CubeShim/shim/src/sandbox/sb.rs:343-348`；`hypervisor/vmm/src/device_manager.rs:2183-2187`、`:2715-2775` |
| network-agent / CubeVS / CubeEgress / CubeProxy | TAP `EnsureNetwork`、eBPF redirect、L7 egress policy、proxy registry 和 route。 | `Cubelet/network/plugin_tap.go:351-520`；`network-agent/api/v1/network_agent.proto:153-185`；`CubeEgress/lua/access_phase.lua:180-325`；`CubeProxy/lua/proxy_registry.lua:1-137` |

### AgentENV

| 组件 | 职责 | 证据 |
|---|---|---|
| Gateway / API | 控制 API、手写 proxy router、E2B 兼容 header 与 lifecycle API。 | `src/api/server.rs:8-39`；`src/api/openapi.yml:1330-1644`、`:1822-1938` |
| Scheduler | docker/K8s 部署中独立 scheduler，配置节点与 round-robin。 | `deploy/docker-compose.yml:37-101`；`deploy/docker/config/default.json:1-27`；`deploy/k8s/base/scheduler-deployment.yaml:1-52` |
| Node Orchestrator | `create_sandbox_inner`、`resume_sandbox_inner`、`launch_sandbox`；生成 LaunchPlan、启动 backend、等待 ready、写 proxy route。 | `src/orchestrator/service.rs:347-511`、`:1276-1408`、`:1972-2142` |
| FirecrackerSandbox / FirecrackerPool | start/start_nowait/wait_for_ready/pause/snapshot/fork；全局 Firecracker warm pool。 | `src/sandbox/firecracker/sandbox.rs:264-340`、`:571-640`；`src/sandbox/firecracker/pool.rs:44-144` |
| NetworkManager / WarmPool | netns/veth/address plan、slot create/release、fill/drain。 | `src/sandbox/network/manager.rs:57-140`、`:294-372`；`crates/warm-pool/src/lib.rs:82-106`、`:245-291` |
| OverlayBD / ublk / FC drives | user image 走 OverlayBD runtime → host ublk device → `user-rootfs` symlink → Firecracker Drive1，guest 内为可写 `/dev/vdb`；Drive0 在 guest 内为只读 `/dev/vda` tools root；`add_drive` 调 FC virtio-blk API。 | `src/sandbox/firecracker/sandbox.rs:1198-1228`、`:1432-1456`、`:1668-1730`；`src/sandbox/firecracker/instance.rs:309-337` |
| envd / proxy | `wait_for_ready` 等待 envd 并通知 ublk ready；proxy 支持 E2B header、fallback 与 auto-resume。 | `src/sandbox/firecracker/sandbox.rs:594-629`；`src/api/proxy.rs:82-147`、`:799-880` |

### E2B-infra

| 组件 | 职责 | 证据 |
|---|---|---|
| API handlers | `PostSandboxes` 处理 template、token、network/egress、volumes、startSandbox。 | `packages/api/internal/handlers/sandbox_create.go:59-336` |
| API orchestrator / placement | discovery、sandbox store、nodes、BestOfK placement、routing catalog、snapshot cache、Redis storage。 | `packages/api/internal/orchestrator/orchestrator.go:45-129`；`packages/api/internal/orchestrator/create_instance.go:138-394`；`packages/api/internal/orchestrator/placement/placement_best_of_K.go:15-190` |
| node orchestrator server | gRPC `Server.Create` 获取 template cache，选择 ResumeSandbox 或 RebootSandbox。 | `packages/orchestrator/pkg/server/sandboxes.go:75-280` |
| Firecracker process/control | start script、unshare/netns、FC API socket、Create/Resume/loadSnapshot/setMMDS。 | `packages/orchestrator/pkg/sandbox/fc/process.go:159-667`；`packages/orchestrator/pkg/sandbox/fc/client.go:42-166`、`:319-435` |
| template/build | Template 包含 files/memfile/rootfs/snapfile/metadata；build layer 支持 cold create。 | `packages/orchestrator/pkg/sandbox/template/template.go:16-24`；`packages/orchestrator/pkg/template/build/layer/create_sandbox.go:110-177` |
| rootfs/storage device | Template rootfs 进入 NBD cache/overlay，host provider path 可为 `/dev/nbdX`；FC process 等待 path 后调用 `PutGuestDriveByID` 配置 guest root drive。`/dev/nbdX` 不是 guest 设备名。 | `packages/orchestrator/pkg/sandbox/sandbox.go:421-425`、`:853-883`；`packages/orchestrator/pkg/sandbox/rootfs/nbd.go:35-170`；`packages/orchestrator/pkg/sandbox/fc/process.go:419-440`；`packages/orchestrator/pkg/sandbox/fc/client.go:215-240` |
| envd/MMDS/network/proxy/cloud | envd init + MMDS token hash；network slot pool；Redis catalog/client-proxy/node proxy；Terraform/Nomad AWS/GCP。 | `packages/orchestrator/pkg/sandbox/envd.go:259-335`；`packages/envd/internal/api/init.go:43-188`；`packages/orchestrator/pkg/sandbox/network/pool.go:24-233`；`packages/shared/pkg/sandbox-catalog/catalog_redis.go:26-113`；`iac/provider-aws/main.tf:1-41`；`iac/provider-gcp/main.tf:1-33` |

## 5. 三条创建/恢复流程

### CubeSandbox

1. CubeAPI `POST /sandboxes` handler 接请求。
2. CubeAPI service 规范化 template/env/ports/network/volumes，并调用 CubeMaster。
3. CubeMaster handler 解析 template/snapshot，`scheduler.Select` 选择 host，调用 Cubelet。
4. Cubelet/CBRI 解析 app image、kernel/rootfs、snapshot annotations；默认 guest base root 是 virtio-pmem `/dev/pmem0` + ext4/DAX/ro，CBRI `AnnotationPmem` 添加的 app ext4 image 从 `/dev/pmem1` 起；TAP 插件调用 network-agent `EnsureNetwork`。
5. CubeShim `start_vm`：snapshot path 存在时优先 `restore_vm`，否则 `boot_vm` 冷启动。
6. VM ready 后 Shim 等待 vsock、调用 guest agent 创建/恢复容器；CubeMaster/CubeAPI 返回 envd/token/proxy 信息。

冷/热边界：cold path 是 `boot_vm + CreateContainer`；hot path 是 Cubelet 写 snapshot annotations、CubeShim 构造 `RestoreConfig` 并调用 Cloud Hypervisor restore。

### AgentENV

1. Gateway/API `POST /sandboxes` 接请求，OpenAPI 与 proxy 支持 E2B 兼容 header。
2. Scheduler 选择 Node，Node Orchestrator 执行生命周期。
3. `create_sandbox_inner` 按 snapshot 或 image 分支构造 LaunchPlan；resume path 校验 owner/state/paused_state。
4. `launch_sandbox` 构建 backend、保护 artifact、`start_nowait()`、插入 handle/persist state。
5. FirecrackerSandbox 根据 LaunchMode Fresh/Resume 启动；user image 走 `OverlayBD → host ublk → FC virtio-blk Drive1`，guest Drive1 是 `/dev/vdb`，guest Drive0 `/dev/vda` 为只读 tools root；FirecrackerPool 和 NetworkManager warm pool 参与资产准备。
6. `wait_for_ready` 等 envd、通知 ublk ready、init envd；Orchestrator 写 proxy route，返回可用。

冷/热边界：fresh path 来自 image/FreshSandboxBuildSpec；热恢复来自 RunnableSnapshot 或 paused_state resume，要求 virtualization mode 匹配。

### E2B-infra

1. API `PostSandboxes` 解析 template alias/cache、token、network、volumes、timeout。
2. API orchestrator 做 team concurrency、active start 去重，构造 sandbox metadata/request。
3. BestOfK placement 选择 node，并通过 nodemanager gRPC 调 node `Sandbox.Create`。
4. node orchestrator `Server.Create` 获取 template cache，构造 sandbox config，选择 ResumeSandbox 或 filesystem-only RebootSandbox。
5. Resume path 准备 files、UFFD memory 和 network slot；Template rootfs 走 `NBD cache/overlay (host /dev/nbdX) → FC guest root drive`，由 `PutGuestDriveByID` 设置 host path/root flag，再 `loadSnapshot/resumeVM`；cold build path 用 `Factory.CreateSandbox`。
6. `WaitForEnvd` init envd；MMDS 提供 token hash；routing catalog/client-proxy/node proxy 建立路由。

冷/热边界：主用户 create 对 full snapshot template 走 ResumeSandbox；filesystem-only template 走 RebootSandbox，源码注释明确 RAM、processes、open sockets lost；template build 使用 cold `Factory.CreateSandbox`。

设备链 trace 边界（Inference）：CodeGraph 对 `genPmemOpt -> make_virtio_pmem_device`、`create_overlaybd_runtime_device -> add_drive`、`NewNBDProvider -> PutGuestDriveByID` 都未返回单条直接路径。静态桥接分别是 Go CBRI annotation → containerd shim/Rust config → Cloud Hypervisor device manager、OverlayBD/ublk manager → `user-rootfs` symlink → Firecracker `/drives/<id>` API、NBD Provider path → FC process/symlink → `PutGuestDriveByID`。“无直接 trace”不等于“无调用”，也不能写成同进程函数调用。

## 6. 技术矩阵

| 维度 | CubeSandbox | AgentENV | E2B-infra |
|---|---|---|---|
| VMM | Cloud Hypervisor/RustVMM/KVM。 | Firecracker/KVM。 | Firecracker/KVM。 |
| 模板/快照 | VM snapshot + memory volume URL + app snapshot container id；Cloud Hypervisor restore。 | RunnableSnapshot/LaunchPlan；pause state 包含 `vm_state.bin`、OverlayBD memory/rootfs state。 | Template files/memfile/rootfs/snapfile/metadata；snapshot resume + UFFD；fs-only reboot 不保留内存状态。 |
| rootfs/存储设备链 | guest base root 为 virtio-pmem `/dev/pmem0` + ext4/DAX/ro；app ext4 image 从 `/dev/pmem1` 起；CubeCow FICLONE 只属于 volume/storage CoW。 | user image 为 `OverlayBD → host ublk → FC virtio-blk`，guest 内为 `/dev/vdb`；guest `/dev/vda` 是只读 tools root；memory snapshot backend 独立。 | Template rootfs 为 `NBD cache/overlay (host /dev/nbdX) → FC guest root drive`；UFFD 是独立内存链。 |
| 网络/egress | TAP + network-agent + eBPF CubeVS + CubeEgress + CubeProxy。 | NetworkManager warm pool + proxy route/header/auto-resume。 | network slot pool + Redis routing catalog + client-proxy/node-local proxy。 |
| guest 控制 | vsock/ttrpc guest agent；CubeAPI 返回 envd metadata/token。 | envd wait/init；ublk ready notification；token/config。 | envd init + MMDS token hash；FC setMmds。 |
| 调度/池化 | CubeMaster scheduler；CubeCow/network-agent 复用；v0.6.0 未确认 VM warm pool。 | FirecrackerPool、Network warm pool、block pool low/high watermark。 | BestOfK placement、network slot new/reused pool、NBD device pool。 |
| 部署/运维 | one-click systemd + Helm chart。 | docker-compose + Kubernetes manifests。 | Terraform AWS/GCP + Cloudflare/Nomad + Nomad job modules。 |
| 安全边界 | MicroVM、seccomp allowlist、CubeEgress policy/audit、proxy token/registry。 | API/proxy auth；测试覆盖 envd/traffic token 不可作为控制面 auth。 | team concurrency、secure envd token、MMDS hash、proxy traffic token、cloud secrets/env。 |
| ARM64 | 源码/配置存在 arm64/aarch64 路径；未运行验证。 | install/artifact 路径存在 arm64/aarch64；未运行验证。 | runtime 有 arch-aware path 和 arm64 SMT 处理；完整云交付 ARM64 未确认。 |

## 7. 版本演化观察

以下是 **Official release/history observation**，不是主对比能力：

- CubeSandbox `v0.6.0` 到 `master@b2605d...` 有 228 commits；候选变化包括 network-agent 生命周期/归属、跨节点 pause/snapshot、S3/remote CoW、Pause/Resume 内存所有权。
- AgentENV `v0.1.3` 到 `main@4a2d610...` 有 20 commits；候选变化包括 OverlayBD/ublk I/O、domain-based egress、过期 Sandbox 原子认领。
- E2B-infra `2026.29` 到 `main@d843e3f...` 有 308 commits；候选变化包括 envd live-upgrade/pause freeze、snapshot/rootfs 并行、filesystem-only resume。

这些变化需要单独固定 HEAD 源码后复核，不能回填到本报告主矩阵。

## 8. 证据索引

| ID | Claim class | 结论 | 证据 |
|---|---|---|---|
| C1 | Official release fact | CubeSandbox baseline 为 `v0.6.0@8721dd...`。 | 本文件第 2 节“版本范围” |
| C2 | Local/source fact | CubeSandbox create path 为 CubeAPI → CubeMaster → Cubelet/CBRI → CubeShim → guest agent/proxy。 | `CubeAPI/src/services/sandboxes.rs:153-291`；`CubeMaster/pkg/service/sandbox/sandbox_run.go:104-340`；`Cubelet/plugins/cbri/cubeboxcbri/cubebox.go:102-260`；`CubeShim/shim/src/sandbox/sb.rs:832-999` |
| C3 | Local/source fact | CubeSandbox 使用 Cloud Hypervisor、CubeCow reflink、TAP/network-agent/eBPF、CubeEgress。 | `CubeShim/shim/src/hypervisor/cube_hypervisor.rs:75-183`；`cubecow/src/engine/reflink.rs:131-177`；`Cubelet/network/plugin_tap.go:351-520`；`CubeEgress/lua/access_phase.lua:180-325` |
| C4 | Local/source fact | Cube guest base root 是 virtio-pmem `/dev/pmem0` + DAX；CBRI app ext4 image 从 `/dev/pmem1` 起；FICLONE 是 storage CoW。 | `Cubelet/plugins/cbri/cubeboxcbri/cubebox.go:140-142`、`:351-399`；`CubeShim/shim/src/hypervisor/config.rs:28`、`:72-77`、`:98-101`；`CubeShim/shim/src/sandbox/pmem.rs:13`、`:29-43`；`CubeShim/shim/src/sandbox/sb.rs:343-348`；`hypervisor/vmm/src/device_manager.rs:2715-2775` |
| A1 | Official release fact | AgentENV baseline 为 `v0.1.3@7f4a9b...`。 | 本文件第 2 节“版本范围” |
| A2 | Local/source fact | AgentENV create/resume path 为 API/Gateway → Scheduler/Node → LaunchPlan → FirecrackerSandbox → envd/proxy route。 | `src/orchestrator/service.rs:347-511`、`:1276-1408`、`:1972-2142`；`src/sandbox/firecracker/sandbox.rs:571-640`；`src/api/proxy.rs:82-147` |
| A3 | Local/source fact | AgentENV 明确有 FirecrackerPool、Network warm pool、OverlayBD/ublk。 | `src/sandbox/firecracker/pool.rs:44-144`；`src/sandbox/network/manager.rs:57-140`；`src/sandbox/ublk/device.rs:25-105` |
| A4 | Local/source fact | AgentENV user image 通过 OverlayBD/host ublk 接入 Firecracker virtio-blk，guest 内为 `/dev/vdb`；guest `/dev/vda` 是只读 tools root。 | `src/sandbox/firecracker/sandbox.rs:1198-1228`、`:1432-1456`、`:1668-1730`；`src/sandbox/firecracker/instance.rs:309-337` |
| E1 | Official release fact | E2B-infra baseline 为 `2026.29@557445...`。 | 本文件第 2 节“版本范围” |
| E2 | Local/source fact | E2B create path 为 API → API orchestrator/BestOfK → node orchestrator → Resume/Reboot/Create → envd/MMDS/proxy。 | `packages/api/internal/handlers/sandbox_create.go:59-336`；`packages/api/internal/orchestrator/create_instance.go:138-394`；`packages/api/internal/orchestrator/placement/placement_best_of_K.go:15-190`；`packages/orchestrator/pkg/server/sandboxes.go:75-280`；`packages/orchestrator/pkg/sandbox/sandbox.go:753-1165` |
| E3 | Local/source fact | E2B 存储/恢复核心为 Firecracker + NBD overlay/cache + UFFD + MMDS/envd + routing catalog。 | `packages/orchestrator/pkg/sandbox/fc/process.go:159-667`；`packages/orchestrator/pkg/sandbox/rootfs/nbd.go:35-170`；`packages/orchestrator/pkg/sandbox/block/cache.go:62-204`；`packages/orchestrator/pkg/sandbox/envd.go:259-335`；`packages/shared/pkg/sandbox-catalog/catalog_redis.go:26-113` |
| E4 | Local/source fact | E2B Template rootfs 通过 NBD cache/overlay host `/dev/nbdX` path 接入 Firecracker guest root drive；不声称 guest 看到 `/dev/nbdX`。 | `packages/orchestrator/pkg/sandbox/sandbox.go:421-425`、`:853-883`；`packages/orchestrator/pkg/sandbox/fc/process.go:419-440`；`packages/orchestrator/pkg/sandbox/fc/client.go:215-240`；`packages/orchestrator/pkg/sandbox/rootfs/nbd.go:35-170` |
| X1 | Inference from Local/source facts | 三者共享统一抽象链，但控制面边界和资产复用模型不同。 | C2/A2/E2 三套证据共同支撑；完整矩阵见本文件第 6 节。 |

## 9. 限制

- 未运行任何远端环境、未创建真实 Sandbox、未验证性能或容量。
- 所有“支持/不支持”只限 pinned stable 源码、配置或测试能确认的状态。
- ARM64 只写源码/配置可见路径和限制，不写运行通过。
- README、release note、提交标题只作为入口或版本演化线索，不作为实现事实的唯一证据。
- CodeGraph 对跨服务动态 dispatch 不一定返回单条直接 trace；本报告记录静态源码桥接点和 RPC/service 边界，不把“无直接 trace”误写为“无调用”。
