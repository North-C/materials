# CubeSandbox 2U2G Template c50n500 优化报告

## 1. 当前结论

- 当前线上仍使用自编译 openEuler guest image 与 openEuler guest kernel，未切回社区 guest image。
- 已定位主要热点：镜像中的 envd 0.5.13 会每 50ms 轮询 CubeSandbox 未提供的 Firecracker MMDS，持续制造 guest WFI、arch timer 和 virtio-net 中断。
- 第一阶段稳定版本在 Template 构建/ResetVm 窗口保留 MMDS 轮询，guest 时钟恢复后停止轮询。c50n500 三轮均为 500/500，平均延迟 **202.72ms**，相对 241.47ms 基线降低 16.05%。
- 达标阶段使用 guest 内原生 Go code server v3：envd 健康前不监听 49999，并配合 Cubelet restore 后立即开始、5ms 周期的 early HTTP probe。c50n500 四轮均为 500/500，avg 分别为 **130.88、134.99、135.86、135.51ms**，四轮均值 **134.31ms**、p95 均值 **234.93ms**、QPS 均值 **317.55**。
- 2026-07-28 按要求关闭 early probe、保留同一个 v3 Template 后，正式矩阵四组均首轮成功，c1n20/c10n200/c20n300/c50n500 avg 为 **39.00/53.84/58.70/138.61ms**，合计 1020/1020；c50 又重复 3 轮，四轮合计 2000/2000、avg 均值 **138.63ms**、p95 均值 **231.93ms**、p99 均值 **524.55ms**、QPS 均值 **264.02**。
- 完全关闭、1ms 取消和 20ms 宽限虽然部分成功请求更快，但均出现 HTTP 408、`reset guest time failed` 或残留 shim，不能作为有效优化结果。openEuler guest image 保持不变。
- 2026-07-28 继续验证了 KVM halt-poll、Shim 空连接和四种 MMDS 退出机制。所有请求成功的候选均未优于 202.72ms 稳定均值；更激进的 MMDS 退出候选连续出现 2-6 个失败请求，已全部拒绝。
- GICv4-only 曾完成 1500/1500 请求，c50 三轮均值 201.47ms，仅比稳定均值快 0.61%；后续两次单独启用 GICv4 的复测分别在 TAP 扩池约 453/1000、275/1000 时导致主机失联并非正常重启。GICv4-only 及其与 vtimer IRQ bypass 的组合均因稳定性与收益不足而拒绝。
- guest 内部 exec HTTP probe 完成 500/500，但 avg 升至 438.42ms、p95 升至 1310.52ms，确认用 containerd exec 绕过 TAP 探针是明显负优化，已回退。
- **关闭 early probe 后仍稳定达到 170ms 目标**：四轮 c50 avg 均低于 140ms，平均延迟相对开启时只增加 4.32ms（3.22%），但 p99 均值增加 65.19%、QPS 降低 16.86%，说明 early probe 对平均延迟收益较小、对批次尾部和吞吐仍有明显作用。当前保留 early-probe v2 Cubelet 二进制但配置为关闭，继续使用原生 code-server v3 Template、openEuler guest image/kernel 和安全 host 启动参数；GICv4 不启用。

## 2. Sandbox-code 镜像背景与固定测试条件

### 2.1 官方 quickstart 中的两平面架构

本节背景参考 CubeSandbox 官方 [code-sandbox-quickstart](https://github.com/TencentCloud/CubeSandbox/tree/master/examples/code-sandbox-quickstart)（2026-07-28 读取）。`sandbox-code` 面向 E2B SDK 代码沙箱场景，平台路径被划分为控制面和数据面：

- **控制面（Control Plane）**负责沙箱生命周期。`Sandbox.create()` 经 CubeAPI、CubeMaster 到 Cubelet，由 Cubelet 创建或恢复 KVM MicroVM；guest 内的 `cube-agent` 为 PID 1，并负责拉起 envd 等服务。
- **数据面（Data Plane）**负责创建后的高频代码执行、命令和文件交互。SDK 流量经 CubeProxy 直接进入 sandbox 内服务，不需要让每次 `run_code` 都重新经过 CubeMaster/Cubelet 的生命周期链路。

官方 quickstart 给出的文本架构图如下：

```text
                             用户脚本 (E2B SDK)
                                      │
                                      ▼
        ┌─────────────────────────────┴─────────────────────────────┐
        │                                                           │
 【1. 管理流程 Control Plane】                            【2. 调用流程 Data Plane】
  (如 Sandbox.create / delete)                        (如 run_code, commands.run)
        │                                                           │
        ▼  REST API (端口 3000)                                     ▼  WSS / HTTP
     CubeAPI                                                    CubeProxy
        │                                                           │
        ▼                                                           │
    CubeMaster                                                      │
        │                                                           │
        │                  ┌────────────────────────────────────┐   │
        ▼                  │            KVM MicroVM             │   │
     Cubelet ──────────────┼──► cube-agent ──► envd  ◄──────────┼───┘
                           │     (PID 1)         │              │
                           │                     ▼              │
                           │                Python / Shell      │
                           └────────────────────────────────────┘
```

这张图是逻辑视图。对本报告的 create-only benchmark 而言，计时重点是左侧 `Sandbox.create -> CubeAPI -> CubeMaster -> Cubelet -> MicroVM restore/readiness`；创建后的 `run_code` SDK 门禁则验证右侧数据面确实可用。具体到本次 benchmark OCI，`cube-agent` 负责 guest/container 生命周期衔接，patched envd 和 native code server 由 OCI entrypoint 启动；因此 MMDS-prime 和 code server v3 是 OCI 应用层修改，不是对 PID 1 `cube-agent` 的替换。第 13 节的 early probe 位于 Cubelet 创建路径，第 14 节的 native code server 位于 MicroVM 内的 OCI 服务层，两者优化的是同一次创建过程中不同位置的 readiness 热路径。

### 2.2 `sandbox-code` OCI 镜像如何形成 Template

官方 quickstart 使用以下命令从社区 `sandbox-code:latest` OCI 镜像创建代码沙箱 Template：

```bash
cubemastercli tpl create-from-image \
  --image cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code:latest \
  --writable-layer-size 1G \
  --expose-port 49999 \
  --expose-port 49983 \
  --probe 49999
```

国内仓库为 `cube-sandbox-cn.tencentcloudcr.com`，境外访问推荐 `cube-sandbox-int.tencentcloudcr.com`。这里的 `sandbox-code` 是 **OCI 应用镜像**，不是 MicroVM 的 guest OS image，也不是 guest kernel。几层制品的职责如下：

| 层次 | 本报告中的实例 | 职责与变更影响 |
|---|---|---|
| Guest kernel | `cube-kernel-scf/vmlinux-bm` | MicroVM 内核；决定 KVM、时钟、GIC、virtio 等内核行为 |
| Guest OS image | `cube-image/cube-guest-image-cpu.img` | openEuler guest 基础系统和 `cube-agent` 等 VM 级用户空间；决定 `/etc/os-release` 等 guest OS 内容 |
| OCI application image | `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` 及其优化 digest | 代码沙箱应用 rootfs，包含 envd、Python/code server 和启动脚本；本次 MMDS-prime 与 native code server v3 都在这一层 |
| Template | `tpl-d38241efa019453f9bc2132c` | 将选定的 guest/OCI 运行状态、VM 内存和设备状态保存为可并发 restore 的模板，并附带 2U2G、writable layer、exposed ports 和 Probe 配置 |

因此，“切换 `sandbox-code` 镜像”只替换 OCI 应用层；它不会把 guest OS 从 openEuler 改成 Ubuntu，也不会替换 `vmlinux-bm`。反过来，只替换 guest image/kernel 也不会自动修改 OCI 内的 envd 或 code server。Template 保存的是构建时的组合运行态，任一层发生变化后都必须重新构建 Template，不能假定已有 Template 会动态继承新文件。

本次性能测试没有直接使用 quickstart 的社区 `sandbox-code:latest` digest，而是使用 `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim` 作为基线，再依次构建 MMDS-prime 和 native code server v3 镜像。两者在架构中的职责相同，都是用于构建 Template 的 OCI 应用镜像，但不能把它们视为同一个镜像版本或直接互换测试数据。

相关端口在本次场景中的职责如下：

| 端口/入口 | 所在位置 | 用途 |
|---|---|---|
| `3000` | Host CubeAPI | `Sandbox.create/delete` 等控制面 REST API |
| `49983` | Guest OCI / envd | envd HTTP 服务；为 SDK 命令、文件等能力提供数据面支撑，也是 code server v3 的启动依赖 |
| `49999` | Guest OCI / code server | code interpreter 的 health/execute 服务；本次 Template readiness 使用 `/health:49999` |
| WSS / HTTP | CubeProxy | 创建完成后把 SDK 数据面流量路由到对应 sandbox |

`--expose-port` 让 Template 声明数据面所需端口，`--probe 49999` 则把 49999 作为创建期健康门禁。端口可访问只说明对应 OCI 服务进入可用状态；Cubelet 仍必须完成 RestoreVm/ResetVm 等控制面步骤，这也是 early probe 只能并行重叠、不能绕过创建流程的原因。

### 2.3 固定测试条件

| 项目 | 配置 |
|---|---|
| Host | `root@192.168.25.90`, arm64, 192 physical / 384 logical CPU |
| Host kernel | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` |
| Guest image | `/usr/local/services/cubetoolbox/cube-image/cube-guest-image-cpu.img` |
| Guest image SHA256 | `1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da` |
| Guest kernel | `/usr/local/services/cubetoolbox/cube-kernel-scf/vmlinux-bm` |
| Guest kernel SHA256 | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| Guest OS/kernel | openEuler 24.03 SP3, `6.6.0-cubesandbox.guest.oe2403sp3` |
| 基础 OCI image | `cubesandbox-bench/sandbox-code-envd-ci:arm64-slim`，local image ID `sha256:cc200de2...` |
| 优化 OCI image | `127.0.0.1:5000/cubesandbox-bench/sandbox-code-envd-ci@sha256:21255c98dfb...` |
| 优化 envd | 0.5.13，binary SHA256 `cc197325...`，upstream commit `b8ca332f435370397bf42be614b2a5b620d65d39` |
| 第一阶段稳定 Template | `tpl-0294704e620847b4a07c2f5f`, 2U2G, 1G writable layer |
| 最终达标 OCI image | `127.0.0.1:5000/cubesandbox-bench/sandbox-code-envd-ci@sha256:b741fde1de3dd4cc4f4cc82c089e861e5d53f1d5f0b4492be6f9f98f4652af3a` |
| 最终达标 Template | `tpl-d38241efa019453f9bc2132c`, 2U2G, 1G writable layer |
| Probe | Template HTTP `/health:49999`，标准 `period=500ms`；当前 `CUBESANDBOX_EARLY_PROBE=0`，恢复串行 Probe |
| TAP | 当前预分配 1000；test gate requires at least 1000 and 0 in-use before each case |
| 当前 Cubelet SHA256 | `486688ed1da44d3d9ee861a3734c106e65719d41bfd30ea3f649f0cbfdc4ebc1`（early-probe v2） |
| Cubelet rollback SHA256 | `88e5e224fdfb9b1fca5d4722cfa273c49aa7048dffdb28fb88adbc44ddee4c96` |
| early probe 已启用配置备份 | `/root/cubesandbox-early-probe-backup-20260728-v3-noearly/20-early-probe.conf.enabled` |

Host 保留设置：

- `kernel.numa_balancing=0`
- `kernel.sched_cluster=1`
- `kernel.sched_child_runs_first=0`
- THP=`always`
- CPU governor=`performance`
- KVM `halt_poll_ns=500000`（完成 A/B 后已恢复默认）

## 3. 测试门禁

所有被采纳轮次均执行以下门禁：

1. 测试前删除已部署 sandbox。
2. 连续三次确认 sandbox/shim/task 均为 0。
3. 连续三次确认 TAP 总量不少于 1000，且 in-use 为 0。
4. 确认 Cubelet、network-agent、CubeMaster API 健康。
5. 测试后再次清理并执行相同门禁。
6. 只有请求全成功、bench exit=0 且 post-cleanup 成功的轮次才计入结果。

`create-only` 会保留 warmup 3 + 正式 500 个 sandbox，直到本轮结束后统一清理；因此 c50n500 同时也是 503 个 2U VM 的递增密度测试。

## 4. 基线演进

| 阶段 | avg (ms) | p95 (ms) | throughput (/s) | 结果 |
|---|---:|---:|---:|---|
| 初始 openEuler 单轮 | 317.08 | 1264.86 | 133.27 | 初始参考 |
| NUMA balancing off，旧 probe=500ms | 264.38 | 690.00 | 164.60 | 明显改善 |
| NUMA off + THP never，单轮 | 235.00 | 699.00 | 172.00 | avg 改善，长尾无改善；未保留 |
| probe period/timeout=100ms，run1 | 243.49 | 569.65 | 177.24 | 有效 |
| probe period/timeout=100ms，run2 | 241.91 | 658.09 | 178.39 | 有效 |
| probe period/timeout=100ms，run3 | 239.01 | 705.32 | 178.01 | 有效 |
| 三轮均值 | **241.47** | **644.35** | **177.88** | 当前稳定基线 |

启用 `kernel.sched_cluster=1` 后三轮 avg 分别为 237.15、236.68、241.83ms，均值 238.56ms。提升约 2.92ms，属于小幅收益，当前保留。

## 5. MMDS-prime envd：根因、实现与边界

### 5.1 原始 envd 的问题

基础镜像中的 envd 0.5.13 在启动时调用 `host.PollForMMDSOpts`。该函数按 50ms 周期请求 Firecracker link-local MMDS 地址 `169.254.169.254`；当前 CubeSandbox/Cloud Hypervisor guest 没有对应的 MMDS 服务，因此 goroutine 不会成功返回。`PostInit` 还可能再启动一个最长 60 秒的 MMDS 轮询。对于单个 VM，这只是低频后台工作；当 c50n500 逐步保留 503 个 2U guest 时，它会被放大为持续的定时器、WFI exit、virtio-net IRQ 和调度压力。

单个 ready VM 的实测结果如下：

| 状态 | WFI exits/s | arch timer/s | virtio-net IRQ | envd voluntary ctx switch/s |
|---|---:|---:|---:|---:|
| 原始 envd | 约 359.6 | 约 163.8 | IRQ 33/34 各约 100/s | 约 51.8 |
| `SIGSTOP envd` | 约 17.4 | - | - | - |
| 直接 `-isnotfc` | 约 35 | - | 0 | 约 0 |
| 稳定 MMDS-prime 优化 | 约 40.2 | - | 0 | 约 2.2 |

`SIGSTOP envd` 和 `-isnotfc` 两个对照把 WFI exits 从约 360/s 降到 17-35/s，且 `-isnotfc` 下 virtio-net IRQ 归零。这组对照证明高密度 readiness 退化的主要来源是每个 ready VM 的无效 MMDS 轮询，而不是 Python code server 冷启动。Template restore 恢复的是已经运行的 guest/容器进程，不会为每个 sandbox 重新执行一次完整 OCI 冷启动。

但是，直接使用 `-isnotfc` 或删除 MMDS goroutine 不能采纳：多轮测试均出现 `reset guest time failed`。现有证据说明，在这套 openEuler guest、Cloud Hypervisor 和 ResetVm 实现中，Template 构建及 restore/reset 窗口保留原始 MMDS 活动对可靠性有作用；其更底层的因果关系尚未通过内核/设备级时序跟踪完全证明，因此这里将它记录为经过压力测试验证的约束，而不是 CubeSandbox 的通用协议要求。

### 5.2 MMDS-prime 补丁做了什么

实现位于 `optimizations/envd-mmds-prime/`，基于 envd 0.5.13、upstream commit `b8ca332f435370397bf42be614b2a5b620d65d39`。补丁后的二进制 SHA256 为 `cc19732595b2b507210c4ab0e100115b1d0d956987dabe755df7505ff3a2feac`，核心改动只有以下三处：

1. envd 新增 `-prime-mmds-until-unix <seconds>` 参数，值为 Unix realtime 的绝对秒数；`0` 保持原始行为。
2. 参数大于 0 时，主 MMDS poller 使用独立的 cancellable context 启动；另一个 50ms ticker 检查 `time.Now().Unix() >= deadline`，满足后 cancel poller。
3. `api.New` 接收 `noMMDSAPI=true`，从而禁止 `PostInit` 再创建一个最长 60 秒的 MMDS poller。这里不是立即禁用主 poller，而是只禁止 prime 窗口结束后的二次启动。

OCI 启动脚本在启动 envd 前计算：

```sh
MMDS_PRIME_UNTIL_UNIX="$(($(date +%s) + 10))"
/usr/bin/envd -prime-mmds-until-unix "$MMDS_PRIME_UNTIL_UNIX" -port 49983
```

10 秒不是每个 sandbox 都必须等待的固定延迟，而是写进进程内存并随 Template 保存的绝对截止时间。当前 Template 构建的关键窗口约 1 秒，10 秒用于覆盖构建抖动；一旦 restored guest 的 wall clock 被 ResetVm 校正到截止时间之后，poller 会在下一次 50ms 检查时退出。

### 5.3 Template 构建与恢复时间线

| 阶段 | guest 中的时间/状态 | MMDS-prime 行为 |
|---|---|---|
| OCI 启动 | `t0`，脚本保存 `deadline=t0+10s` | 启动原始 `PollForMMDSOpts`，保留构建期所需活动 |
| Template 快照 | 通常在 `deadline` 前完成 | deadline、poller 和 ticker 都随进程内存进入快照 |
| sandbox restore/ResetVm | 进程从快照点继续；ResetVm 将 realtime 校正为当前时间 | 如果当前时间已越过 deadline，下一次 50ms tick cancel MMDS poller |
| ready 后稳态 | 主 poller 已取消，`PostInit` 也不能重启它 | 不再产生 MMDS virtio-net IRQ；实测 WFI exits 约 40.2/s |

这里必须使用 realtime 绝对时间，不能简单改成“启动后运行 N 秒”的 monotonic timer：快照会把进程和 timer 一并冻结并复制，每个 restored VM 都可能重新消耗完整 N 秒；绝对 deadline 则可利用 ResetVm 的 wall-clock 跳变识别“已经离开 Template 构建时刻”。如果 Template 在生成后 10 秒内立即使用，poller 最多继续运行到 deadline；它仍然不会永久驻留。

### 5.4 配置、观察与回退

| 项目 | 当前值 | 含义 |
|---|---|---|
| envd port | `49983` | envd 本机 HTTP 服务 |
| prime window | `10s` | 启动脚本写入的绝对 deadline 余量 |
| deadline check | `50ms` | 检测 guest realtime 是否越过 deadline |
| `-prime-mmds-until-unix=0` | 默认 | 恢复 envd 原始永久 MMDS 行为 |
| `-isnotfc` | 未使用 | 从启动起完全禁用 MMDS；本环境压力测试不可靠 |

诊断时可检查 envd 命令行是否包含 `-prime-mmds-until-unix`、`/var/log/envd.log` 是否有异常，并在 ready guest 中观察 envd context switches 和 virtio-net IRQ 是否回落。回退不需要修改 guest image/kernel：将 Template/OCI 切回原始 envd 镜像即可。不要只在现有 Template 上替换文件，因为 envd 的运行态已经保存在快照中，必须从目标 OCI 重新构建 Template。

该方案依赖两个前提：Template 快照保存 envd 进程状态，且 restore 后 ResetVm 会校正 `CLOCK_REALTIME`。若未来更换 VMM、时间恢复方式或 envd 版本，需要重新执行 c1 稳定性门禁和多轮 c50，而不能仅根据 ready 后 CPU 指标判断可用。

### 5.5 可靠性边界实验

为同时满足性能与 ResetVm 可靠性，测试了以下边界：

| 版本 | 稳定性门禁 | c50n500 avg / p95 (ms) | 结论 |
|---|---|---:|---|
| 原始 OCI，新建 Template | c1 100/100；c50 500/500 | 247.91 / 951.70 | 证明新建快照机制正常 |
| 完全关闭 MMDS | c50 分别 488/500、483/500、493/500 | 成功样本 182.06、173.44、191.23 | 出现 reset timeout，拒绝 |
| 完全关闭 + 通用 50ms keepalive | c1 99/100 | - | 仍出现 reset timeout，拒绝 |
| MMDS-prime，50ms 检查 | c1 100/100；连续三轮 c50 均 500/500 | 199.59 / 586.34；202.92 / 576.71；205.64 / 579.15 | 稳定候选 |
| MMDS-prime，1ms 取消 | c1 100/100；c50 496/500 | 215.25 / 304.49（仅成功样本） | 4 个 `reset guest time failed`，拒绝 |
| MMDS-prime，检测后宽限 20ms | c1 98/100 | 44.91 / 51.35（仅成功样本） | 2 个 HTTP 408、残留 shim，拒绝 |
| MMDS-prime，10ms deadline ticker | c1 100/100；c50 500/500 | 233.35 / 859.28 | ticker 唤醒增加 5 倍，明显负优化 |
| realtime timerfd + 20ms grace | c1 195/200 | 44.51 / 48.89（仅成功样本） | 5 个失败、5 个残留 shim，拒绝 |
| realtime timerfd + MMDS clean-stop | c1 194/200 | 43.90 / 51.09（仅成功样本） | 6 个失败、6 个残留 shim，拒绝 |
| deadline 合并至 MMDS 50ms ticker | c1 200/200；c50 四轮均失败 | 成功样本均值 218.86 / 351.21 | 合计 1989/2000；最慢请求被失败截断，拒绝 |

稳定候选三轮均值：avg **202.716ms**、p95 **580.731ms**、QPS **200.545**。纯 no-MMDS 的低延迟不能采纳，因为创建失败会人为缩短成功样本分布并降低有效吞吐。

single-ticker c50 四轮完成值如下。`cube-bench` 的 `avg_ms` 和 p95 只基于成功请求，因此表中已经排除了失败请求；这也意味着 p95 的下降存在删失偏差。

| 轮次 | 成功 | 成功样本 avg (ms) | 成功样本 p95 (ms) | 总耗时 (s) |
|---|---:|---:|---:|---:|
| 1 | 497/500 | 214.270 | 335.403 | 31.364 |
| 2 | 496/500 | 220.020 | 339.962 | 31.880 |
| 3 | 498/500 | 220.237 | 354.645 | 31.994 |
| 4 | 498/500 | 220.915 | 374.832 | 31.838 |
| 均值/合计 | 1989/2000 | **218.860** | **351.211** | - |

即使排除失败请求，avg 仍比 202.716ms 稳定均值慢 16.144ms（7.96%）。四轮吞吐只有约 15.6/s，原因是每轮等待失败请求超时约 30 秒，不能用较低的成功样本 p95 宣称优化。

## 6. 稳定候选正式矩阵

2026-07-28 使用 `tpl-0294704e620847b4a07c2f5f`、probe period/timeout=100ms 执行完整矩阵。每组测试前后连续三次确认 sandbox/shim/task 为 0、TAP 总量 1198 且 in-use 为 0；四组均首轮通过。

| 场景 | 成功 | avg (ms) | p95 (ms) | max (ms) | throughput (/s) |
|---|---:|---:|---:|---:|---:|
| c1n20 | 20/20 | 44.679 | 48.647 | 50.001 | 19.057 |
| c10n200 | 200/200 | 58.215 | 66.000 | 84.708 | 150.563 |
| c20n300 | 300/300 | 81.934 | 94.401 | 124.673 | 214.042 |
| c50n500 | 500/500 | **204.118** | **598.520** | 1326.588 | **191.155** |

优化版本 c50 profile（500/500、avg 206.013ms）显示：

| 层级 | avg (ms) |
|---|---:|
| Cubelet `cubebox-service` | 188.713 |
| `sandbox-probe` | 107.124 |
| `cubebox-service-inner` | 81.512 |
| `sandbox-start` | 74.143 |
| `sandbox-create` | 67.231 |
| Shim CreatePodSandbox | 50.708 |
| Shim RestoreVm | 17.980 |
| Shim ResetVm | 11.860 |

同轮 host runnable 最大值从旧 profile 的约 201 降至 24，system CPU 最大约 42.28%，context switch 约 527k/s。MMDS 热点已被消除，但剩余约 33ms 的目标差距转移到 restore/ResetVm 与虚拟中断路径。

## 7. Probe 路径实验

| 实验 | avg (ms) | p95 (ms) | throughput (/s) | 结论 |
|---|---:|---:|---:|---|
| period=20ms, timeout=20ms | 279.88 | - | - | 重试风暴，负优化 |
| period=20ms, timeout=100ms | 246.21 / 246.86 | 610.49 | 181.43 | 无 avg 收益 |
| period=100ms, timeout=200ms | 262.95 | - | - | 负优化 |
| period=100ms, timeout=600ms | 256.87 / 262.17 | - | - | 负优化 |
| 并发 hedged HTTP probe | 269.22 | 877.67 | 169.33 | 请求放大，已回退 |
| 建连/响应超时分离 | 251.99 | 891.82 | 168.58 | 保留慢连接加重竞争，已回退 |
| guest 内 exec HTTP probe，c1n20 | 64.89 | 73.35 | 12.82 | 相比正式 c1 基线 44.68ms 退化 45.2% |
| guest 内 exec HTTP probe，c50n500 | 438.42 | 1310.52 | 73.62 | 500/500，但相比稳定 c50 均值退化 116.3%，已回退 |

两份实验 Cubelet 均先通过 arm64 race test 和 c1n20，再进行 c50n500。guest 内 exec probe 实验已回退；后续采用的 early external HTTP probe v2 及其结果见第 13-15 节。

抓包对 503 个 TAP 的 HTTP readiness 统计：

| 指标 | 结果 |
|---|---:|
| TCP connect avg / p95 | 69.30 / 100.89ms |
| HTTP request-to-response avg / p95 | 35.43 / 192.93ms |
| 首个 SYN 到首个响应 avg / p95 | 92.85 / 295.39ms |
| 首个 SYN 到被 client 接受的响应 avg / p95 | 172.13 / 678.73ms |
| 每 TAP 请求次数均值 | 1.423 |

该结果证明 100ms client timeout 会取消一部分最终可成功的请求，但简单延长、缩短或并发补发都会改变系统负载，实际 A/B 均未改善 avg。

为验证 TAP 网络探针是否可以绕开，Cubelet 实验版通过 containerd task exec 在 guest 内执行
`curl http://127.0.0.1:49999/health`。arm64 候选先通过定向测试、package compile-only 和
race 定向测试，再上线进行 admission test。c50n500 请求全部成功，Shim 日志记录到 861 次
`cubesandbox-internal-probe-http-*` exec，证明实验路径确实生效；但每次探针额外经过
containerd、Shim、guest agent 和进程创建，放大了并发开销。该实验没有失败样本可剔除，
因此 438.42ms 就是完整成功集合的真实均值，不能归因于失败请求的统计方式。

## 8. 原始镜像分阶段热点

完整 profile 的 500 次创建：

| 层级 | avg (ms) | p95 (ms) |
|---|---:|---:|
| Cubelet `cubebox-service` | 225.27 | 652.97 |
| `sandbox-probe` | 180.55 | 605.09 |
| `cubebox-service-inner` | 44.65 | 54.38 |
| `sandbox-start` | 38.41 | - |
| `sandbox-create` | 36.80 | - |
| Shim CreatePodSandbox | 28.55 | 34.00 |
| Shim RestoreVm | 9.55 | - |
| Shim ResetVm | 5.82 | - |

按完成顺序分块后，热点随驻留 VM 数上升：

| 完成序号 | cubebox-service (ms) | sandbox-probe (ms) | inner (ms) |
|---|---:|---:|---:|
| 1-50 | 78.8 | 36.7 | 41.9 |
| 51-100 | 82.3 | 40.5 | 41.8 |
| 201-250 | 243.1 | 199.2 | 43.9 |
| 251-300 | 486.5 | 439.6 | 46.9 |
| 301-350 | 422.4 | 375.9 | 46.4 |
| 451-500 | 302.3 | 251.7 | 50.5 |

Host 创建窗口观测：

- system CPU 最高约 62.07%，busy 约 74.33%。
- runnable/procs_running 最高约 201/199。
- context switch 最高约 720k/s。
- I/O wait 近乎 0，blocked process 为 0。
- 说明瓶颈是 VM/内核调度与 guest readiness，不是磁盘 I/O。

## 9. Host/KVM A/B

| 实验 | avg (ms) | p95 (ms) | throughput (/s) | 结论 |
|---|---:|---:|---:|---|
| profile baseline | 241.87 | 668.20 | 165.93 | 同剖析条件参考 |
| `halt_poll_ns=0` profile | 247.93 | 555.33 | 183.90 | p95/吞吐改善，avg 变差；已恢复 500000 |
| `halt_poll_ns=1000000` | 205.57 | 587.65 | 201.32 | 相比同窗口 500000 对照 202.34ms 退化 |
| `halt_poll_ns=2000000` | 201.50 | 618.01 | 208.70 | 单轮均值波动不足，串行/p95 退化；已恢复 500000 |
| ready VM `cpu.shares=64`，452/503 命中 | 242.91 | 566.80 | 186.81 | p95/吞吐改善，avg 无收益 |

Shim 中 `monitor_vm(false)` 原先仍会建立一个永不使用的 HealthClient vsock 连接。隔离构建并移除此连接后，c50 三轮 avg 为 201.82、207.74、204.94ms，均值 204.83ms；同窗口原 Shim 对照为 202.34ms。该清理没有性能收益，线上 Shim 已恢复 SHA256 `4702fde1...15d`。

单个 2U VM ready 后的 KVM debugfs 采样，在约 1.045 秒内：

- `wfi_exit_stat` 从 203 增长到 550，约 332 WFI exits/s（两个 vCPU 合计）。
- `exits` 从 24623 增长到 25459，约 800 exits/s。
- `halt_wait_ns` 同期增加约 2.08 秒，说明两个 vCPU 大部分时间在 halt/wakeup 循环。

## 10. GICv4 / vtimer IRQ bypass 启动 A/B

2026-07-28 已获授权修改当前默认内核
`6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` 的启动参数。
修改前将 `grub.cfg`、`grubenv`、`/etc/default/grub` 备份到
`/root/cubesandbox-grub-backup-20260728-gicv4/`。

第一轮同时加入：

```text
kvm-arm.vgic_v4_enable=1 kvm-arm.vtimer_irqbypass=1
```

重启后 `/proc/cmdline` 和 dmesg 均确认生效，后者明确打印
`kvm [1]: GICv4 support enabled`。CubeSandbox 服务恢复 active，TAP 后台池接近完成（999/1000）时，主机在 sandbox/shim 均为 0 的情况下失联，随后自动重启。`last -x` 将前一 boot 标记为 `crash`；机器没有持久 journal，也没有 pstore panic 记录，因而无法取得 crash 栈。两个参数随即从默认启动项移除。

为隔离 GICv4 与 vtimer bypass，执行了两组完整对照。GICv4-only 启动恢复 SSH 后立即删除持久参数，因此即使异常重启也会回到安全配置。

| 状态 | 稳定性门禁 | c1n20 avg / p95 (ms) | c50 三轮 avg (ms) | c50 均值 / p95均值 / QPS均值 |
|---|---|---:|---:|---:|
| GICv4 关闭 | TAP 1000/1000；1500/1500 成功 | 47.234 / 53.633 | 194.649、214.749、216.084 | **208.494 / 603.785 / 206.627** |
| 仅 `vgic_v4_enable=1` | TAP 1000/1000；1500/1500 成功 | 46.210 / 53.076 | 185.908、210.759、207.742 | **201.470 / 583.736 / 208.092** |
| GICv4 + `vtimer_irqbypass=1` | 主机自动 crash/reboot | - | - | 拒绝 |

GICv4-only 相比同日关闭状态快 7.024ms（3.37%），但相比此前稳定三轮均值 202.716ms 只快 1.246ms（0.61%），处于轮间波动范围，且远未达到 170ms。

2026-07-28 按用户要求再次只加入 `kvm-arm.vgic_v4_enable=1` 并重启。boot ID
`79b01e73-1521-40bb-8008-8d24d7ed5a8f` 的启动行和 dmesg 均确认 GICv4 生效，CubeSandbox 服务已恢复；但 TAP 池增长到约 453/1000 后主机失联，并以新 boot ID
`cb61dc17-b65c-466d-807b-e0a8b01d5f81` 自动恢复。`last -x` 没有对应的正常 shutdown 记录，持久 journal 与 pstore 仍没有崩溃栈。恢复后立即从默认启动项移除 GICv4，并主动重启到安全配置。最终安全 boot ID 为
`97926d6a-422c-4c6b-8bdb-31c956c29995`，KVM 明确打印 `GICv4 support disabled`；TAP 1000/1000、in-use 0，sandbox/shim/task 均为 0，核心服务 active。

同日再次按用户要求只加入 `kvm-arm.vgic_v4_enable=1`。boot ID
`33ecb5db-946d-420c-bf2b-9ad150663233` 的 `/proc/cmdline` 与 dmesg 明确确认
`kvm [1]: GICv4 support enabled`；为避免重启循环，SSH 恢复后即从下一次启动项移除了该参数，当前 boot 的运行态不受影响。CubeSandbox 核心服务恢复 active，但 TAP 后台池从 70 增长到 275 后主机再次失联，约 8 分钟后以 boot ID
`cc88832c-9f28-4b3e-812e-1639d30f870a` 非正常重启。安全启动的命令行不含实验参数，KVM 打印 `GICv4 support disabled`；默认 GRUB 条目也确认无 `vgic_v4_enable`。前一 boot 没有正常 shutdown 记录，且系统仍无持久 journal 或 pstore crash 栈。本轮 GRUB 备份位于远端
`/root/cubesandbox-grub-backup-20260728-gicv4-user-reenable-2/`。

结论：

- GICv4 单独启用曾完成满池和并发创建，但两次后续复测均在 TAP 扩池阶段发生主机硬锁/非正常重启，不能视为稳定。
- GICv4-only 与 GICv4 + `vtimer_irqbypass` 均出现过主机异常；因缺少 crash 栈，不能宣称已经证明唯一根因。
- 所有 GICv4 实验参数拒绝上线；最终默认启动项不保留任何实验参数。
- guest image、guest kernel 均未替换。

## 11. 证据目录

- 远端总目录：`/home/lyq/cubesandbox-c50-optimization-20260727-220353`
- 本地证据：`artifacts/c50-optimization-20260727`
- 本地 envd 实验归档：`artifacts/c50-optimization-20260727/remote-experiments`（744 个远端文件，约 118MiB，附 `SHA256SUMS`）
- MMDS-prime 稳定三轮：`remote-experiments/envd-mmds-prime/c50-three-valid`
- MMDS-prime 正式矩阵：`remote-experiments/envd-mmds-prime/formal-probe100-matrix/run-20260728-0205`
- MMDS-prime profile：`remote-experiments/envd-mmds-prime/profile-c50`
- 失败边界：`remote-experiments/envd-no-mmds`、`envd-no-mmds-keepalive`、`envd-mmds-prime-fast-cancel`、`envd-mmds-prime-grace20`
- 原始 OCI 新建 Template 对照：`remote-experiments/fresh-original-template-control`
- 稳定 probe100：`experiments/existing-template-probe100/run{1,2,3}`
- 完整 profile：`experiments/probe100-full-profile`
- HTTP 抓包：`experiments/tcp-pcap-observation/run1`
- hedged probe：`experiments/hedged-http-probe`
- 分离超时：`experiments/staged-http-timeout`
- KVM halt poll：`experiments/kvm-halt-poll-zero`
- KVM halt poll 上调：`kvm-halt-poll-1ms-mmds-prime`、`kvm-halt-poll-2ms-mmds-prime`
- MMDS deadline 候选：`envd-mmds-prime-10ms`、`envd-mmds-prime-timerfd-grace20`、`envd-mmds-prime-timerfd-clean-stop`、`envd-mmds-prime-single-ticker`
- Shim 空 HealthClient 连接：`shim-no-unused-health-connect`
- 本轮新增证据校验：`artifacts/c50-optimization-20260727/LATEST_EXPERIMENTS_SHA256SUMS`（654 个文件）
- ready CPU share：`experiments/ready-cpu-shares64`
- guest/KVM post-ready：`experiments/guest-post-ready-observation`
- GICv4 启动 A/B：`gicv4-boot-ab-20260728`（含 GRUB 原始备份和终端结果转录；远端 `/tmp` 原始 JSON 在最终重启时被清除）
- guest 内部 HTTP probe：`internal-http-probe-candidate`（候选 Cubelet、c1/c50 原始 JSON、run log 和 Shim exec 日志）
- early external HTTP probe 与 vCPU wakeup trace：`early-external-http-probe-overlap`
- 原生 code server v1/v2/v3：`native-code-server-v1`、`native-code-server-v2`、`native-code-server-v3`
- 最终正式矩阵：`native-code-server-v3/formal-matrix-d0-p5`
- 最终 SDK create + immediate `run_code`：`native-code-server-v3/sdk-validation.jsonl`
- early probe 关闭后的正式矩阵、c50 重复轮次、SDK 门禁与配置快照：`native-code-server-v3/no-early-probe-20260728`（归档校验见其中的 `ARCHIVE_SHA256SUMS`）

## 12. 当前安全状态

- 当前 Cubelet 二进制仍为 early-probe v2，SHA256 `486688ed...ebc1`，但扩展已通过环境变量关闭；原始 Cubelet 回退文件保存在 `/usr/local/services/cubetoolbox/Cubelet/bin/cubelet.baseline-88e5e224-20260728-early-probe`。
- KVM `halt_poll_ns` 已恢复 `500000`。
- Cubelet parent cgroup `cpu.shares` 已恢复 `1024`。
- 无运行中的实验 watcher、builder 或 ctr events 进程。
- sandbox/shim/task 均为 0，TAP in-use 为 0。
- 已终止 single-ticker 的自动重试和意外启动的第 5 轮；删除其 503 个沙箱，并清理 2 个无 task 的孤立 shim。最终门禁再次确认 sandbox/shim/task 为 0。
- 当前安全 boot ID 为 `cc88832c-9f28-4b3e-812e-1639d30f870a`；默认内核启动参数不含 `vgic_v4_enable` 或 `vtimer_irqbypass`，KVM 日志为 `GICv4 support disabled`。
- GICv4 + vtimer 组合导致一次自动 crash/reboot；GICv4-only 虽曾完成 1500/1500、均值 201.470ms，但后续两次复测分别在 TAP 约 453/1000、275/1000 时导致主机失联并非正常重启。两者均已拒绝并回滚。
- guest 内部 exec HTTP probe 完成 500/500 但 avg 438.425ms，已拒绝；该实验路径已移除。early external HTTP probe v2 二进制保留，但当前配置关闭并使用原串行 Probe。
- CubeMaster、Cubelet、network-agent、Cube API 在最终安全重启后均为 active；TAP 为 1000 总量、0 in-use，sandbox/shim 均为 0。
- 当前 guest image SHA256 为 `1ba4bd9...`，guest kernel SHA256 为 `c551571...`，均为 openEuler 版本。
- 第一阶段稳定 Template 为 `tpl-0294704e620847b4a07c2f5f`；最终达标 Template 为 `tpl-d38241efa019453f9bc2132c`，OCI digest 为 `sha256:b741fde1...52af3a`。
- `/etc/systemd/system/cube-sandbox-cubelet.service.d/20-early-probe.conf` 当前持久化为 `enable=0, delay=0ms, period=5ms`；执行 daemon-reload 并重启 Cubelet 后，unit 与进程环境均验证生效。已启用配置备份在 `/root/cubesandbox-early-probe-backup-20260728-v3-noearly/20-early-probe.conf.enabled`。
- early probe 关闭后的 benchmark 共 2520/2520 成功，另有真实 SDK create + immediate `run_code` 3/3 通过；最终 sandbox/shim/task 均为 0，TAP 为 1000 总量、0 in-use。
- 已执行启动 A/B、两次 GICv4-only 稳定性复测和回滚启动；GRUB 原始备份位于远端 `/root/cubesandbox-grub-backup-20260728-gicv4/`、`/root/cubesandbox-grub-backup-20260728-gicv4-user-reenable/`、`/root/cubesandbox-grub-backup-20260728-gicv4-user-reenable-2/` 及本地 `gicv4-boot-ab-20260728/grub-backup/`。

## 13. Cubelet early probe 创建期并行扩展与效果

### 13.1 定义与适用边界

这里的 **early probe** 是本次实验在 Cubelet 创建路径中加入的调度扩展：不改变 Template 中已有 Probe 的健康判定，只把创建期 Probe 的启动时刻提前，使其与 `runContainer` 中的 VM restore/reset 和容器启动过程重叠。候选 Cubelet v2 SHA256 为 `486688ed...ebc1`。

它不是 CubeSandbox 上游定义的标准 Probe 类型，也不是 sandbox 创建完成后持续运行的 liveness/readiness controller。创建请求结束后，这个 goroutine 和 context 即结束；它不会周期性监控已经 ready 的 sandbox。`early` 只表示“创建过程中更早开始尝试”，不表示降低健康标准或提前返回成功。

### 13.2 串行流程与并行流程

默认路径位于 `source_code/CubeSandbox/Cubelet/services/cubebox/cube_container_create.go`。关闭扩展时，Cubelet 先完整执行 `runContainer`，其中包括 Template VM 的恢复、ResetVm 以及容器任务启动，然后才调用 `doProbe`；`doProbe` 在 `probe.go` 中依次执行 `startProbe` 和 `waitProbe`：

```text
默认串行路径

runContainer（RestoreVm / ResetVm / 启动容器）
    -> doProbe
        -> startProbe
        -> waitProbe
    -> PostCreateContainer
    -> 创建成功
```

开启扩展后，`cube_container_create.go` 在调用 `runContainer` **之前**建立独立 context，并调用 `startProbeWithDelay` 得到带缓冲的结果 channel。随后 `runContainer` 与 Probe 重试并行；`runContainer` 返回成功后，主创建流程仍然必须调用 `waitProbe` 消费结果：

```text
early probe 路径

                      +-> startProbeWithDelay -> HTTP 重试 -> probe result --+
创建请求 -> 建立 context |                                                   +-> waitProbe -> PostCreateContainer -> 创建成功
                      +-> runContainer（RestoreVm / ResetVm / 启动容器） -----+
```

因此 ready 的必要条件没有变化：**`runContainer` 与 Probe 必须同时成功**。即使 Probe 较早成功，结果也只是暂存在 channel 中，主流程仍会先等待 `runContainer` 返回；它不能绕过 RestoreVm/ResetVm。`startProbeWithDelay` 初始化失败、`runContainer` 失败或 `waitProbe` 返回错误时都会取消 early-probe context 并终止创建，成功消费 Probe 结果后也会取消 context，避免残留创建期 goroutine。

### 13.3 探测路径不是 guest 内 exec

early probe 复用 `probe.go` 的标准 `startProbeWithDelay`、`waitProbe` 和 `telnet.Telnet` 实现。Probe 地址取自 `ci.IP`；对于本测试的 HTTP action，Cubelet 在 **host 侧**构造请求，经 TAP 网络访问 guest 的 `GET /health`、端口 `49999`：

```text
Cubelet(host) -> TAP -> guest IP:49999 -> OCI code server /health
```

它与已经拒绝的 guest 内部探针不是同一种实现。后者通过 Shim/containerd exec 在 guest 容器内启动 `curl`，虽然完成 500/500，但 c50 avg 为 438.425ms、p95 为 1310.52ms，进程创建和 exec 控制面成本使其成为明显负优化，已经移除。early probe 不执行 guest 命令，只调整原 host/TAP Probe 在创建流程中的启动时刻。

### 13.4 达标配置、当前回退配置与可复现性注意事项

达标阶段 `.90` 的 systemd drop-in `/etc/systemd/system/cube-sandbox-cubelet.service.d/20-early-probe.conf` 如下；仓库中的恢复配置为 `optimizations/native-code-server/cubelet-early-probe.conf`，远端备份为 `/root/cubesandbox-early-probe-backup-20260728-v3-noearly/20-early-probe.conf.enabled`：

```ini
[Service]
Environment=CUBESANDBOX_EARLY_PROBE=1
Environment=CUBESANDBOX_EARLY_PROBE_DELAY_MS=0
Environment=CUBESANDBOX_EARLY_PROBE_PERIOD_MS=5
```

| 参数 | 达标阶段值 | 作用 |
|---|---:|---|
| `CUBESANDBOX_EARLY_PROBE` | `1` | 启用创建期并行 Probe；关闭时恢复 `runContainer -> doProbe` 串行路径 |
| `CUBESANDBOX_EARLY_PROBE_DELAY_MS` | `0` | 不额外延迟，在 `runContainer` 前立即启动 Probe |
| `CUBESANDBOX_EARLY_PROBE_PERIOD_MS` | `5` | `.90` v2 候选使用的重试周期；服务尚未可达时每 5ms 再尝试一次 |

2026-07-28 按要求回退 early probe 后，当前 drop-in 将 `CUBESANDBOX_EARLY_PROBE` 改为 `0`，其余两项保留为 `0/5`，但在扩展关闭时不参与探测调度。执行 daemon-reload 并重启 Cubelet 后，远端 unit 和进程环境均确认 `enable=0`；运行二进制 SHA256 仍与 v2 候选 `486688ed...ebc1` 一致，因此此次 A/B 只改变探测调度配置，没有替换 Cubelet、v3 Template、guest image 或 guest kernel。关闭后实际使用 Template 标准 Probe 的 `period=500ms`。

这里存在一个必须保留的源码可复现性边界：当前工作树的 `early_probe.go` 只直接定义并读取 enable 和 delay；`probe.go` 默认从请求的 `Probe.PeriodMs` 生成 `telnet.ProbeConfig.Period`，当前工作树中没有直接消费 `CUBESANDBOX_EARLY_PROBE_PERIOD_MS` 的代码。也就是说，达标阶段的 period=5ms 结果对应 `.90` 已部署的 v2 二进制与已验证 systemd 环境，不能仅凭当前工作树的 `early_probe.go` 和 drop-in 宣称可以重新构建出完全相同的二进制。当前关闭扩展的结果不依赖这个 override；后续若重新启用，应补回并提交 v2 的 period override 源码及测试，或明确通过 Template Probe 配置提供 5ms 周期，再重新校验二进制 SHA 和 c50 结果。

### 13.5 delay/period 实验结果

第一阶段 profile 显示 c50 readiness 约 179ms，而 RestoreVm 约 8ms、sandbox-start 约 38ms、sandbox-create 约 36ms。下表是在 MMDS-prime 阶段逐步提前 Probe 并调整重试周期的结果：

| 配置 | 成功 | c50 avg (ms) | p95 (ms) | QPS |
|---|---:|---:|---:|---:|
| delay=50ms, period=100ms | 500/500 | 202.352 | 346.077 | 212.907 |
| delay=75ms, period=100ms | 500/500 | 197.747 | 317.888 | 212.251 |
| v2 delay=50ms, period=20ms | 500/500 | 204.789 | 282.262 | 214.400 |
| v2 delay=75ms, period=20ms run1 | 500/500 | 193.045 | 306.765 | 214.476 |
| v2 delay=75ms, period=20ms profile | 500/500 | 199.384 | 308.123 | 211.313 |
| v2 delay=100ms, period=20ms | 500/500 | 195.707 | 330.852 | 208.702 |
| v2 delay=75ms, period=20ms, GOMAXPROCS=64 | 500/500 | 198.217 | 308.966 | 208.183 |

`delay` 是 early goroutine 启动后的额外等待时间：值越大，实际 Probe 开始得越晚，部分探测会落到 restore 完成之后，重叠收益会被吃掉；值过小时，则会在 TAP、guest 网络或 49999 尚未可用时产生更多失败尝试。`period` 决定服务变为可用后下一次重试的等待粒度，也决定未就绪窗口内的请求数量。将 period 从 100ms 缩短到 20ms 可以降低最坏的重试量化等待，但表中结果并不单调，说明单纯增加探测频率不能消除 guest readiness 本身的热点。

delay=75ms、period=20ms 的两轮均值为 **196.214ms**。相对 MMDS-prime 稳定三轮均值 202.716ms，仅降低 6.502ms（3.21%）：它证明串行等待可以被部分重叠，但单独 early probe 仍远高于 170ms 目标。该阶段将 GOMAXPROCS 从 32 提高到 64 也没有收益，当轮恢复为 32；后续 host 安全重启清除了这一临时 manager 环境，最终 v3 与同状态 v1 控制均未显式设置 GOMAXPROCS。

达标配置改为 delay=0ms、period=5ms，并与 OCI native code server v3 组合。四轮 c50 共 2000/2000，avg 均值 **134.311ms**、p95 均值 234.928ms、QPS 均值 317.549；相对 early probe 单独候选 196.214ms 再降低 61.903ms（31.55%），相对 MMDS-prime 稳定均值降低 68.405ms（33.74%）。

这部分收益不能简单归因于“period 从 20ms 改为 5ms”。early probe 只把等待与 restore 重叠，原 OCI 的 `/health` 仍会把高频 host/TAP 请求传递给 guest code server 和 envd，因此单独只能到约 196ms。v3 则在监听 49999 前确认 envd 健康，并让 restored `/health` 使用快照中的 readiness cache；此时 5ms early probe 才能在网络可访问后快速命中，而不为每次外部尝试同步串联 envd。相同 host/Cubelet 状态下，native v1 控制为 180.475ms，v3 为 134.311ms，进一步支持主要收益来自 v3 对 readiness 热路径的处理，而不是 Probe 频率本身。两者的关系是：**early probe 提供时间重叠，v3 缩短并隔离被重叠的 readiness 热路径**。

回退 A/B 使用同一个 v3 Template，各统计四轮独立 c50：

| early probe | 成功 | avg 均值 (ms) | p95 均值 (ms) | p99 均值 (ms) | max 均值 (ms) | QPS 均值 | 批次总时长均值 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 开启，delay=0ms/period=5ms | 2000/2000 | **134.311** | 234.928 | **317.544** | **456.202** | **317.549** | **1.575** |
| 关闭，标准 period=500ms | 2000/2000 | 138.631 | **231.927** | 524.549 | 1065.900 | 264.020 | 1.900 |
| 关闭相对开启 | - | +4.320 / +3.22% | -3.001 / -1.28% | +207.005 / +65.19% | +609.698 / +133.65% | -53.529 / -16.86% | +0.326 / +20.67% |

因此，v3 已承担大部分平均延迟优化，关闭 early probe 后 avg 仍低于 140ms；early probe 的主要可见收益转移到批次完成时间、吞吐和极端尾部。关闭后的 p95 略低属于轮次波动，不能抵消 p99、max 和总时长的系统性退化；这些长尾与串行路径重新使用 500ms 标准 Probe 周期的量化等待相符，但尚未通过逐请求 trace 证明为唯一原因。

### 13.6 风险、回退与调度热点排除

高频 early probe 有明确的请求放大风险。period=5ms 等价于单个未就绪 sandbox 最多每秒 200 次重试节拍；c50 同时处于未就绪窗口时，理论节拍上限可达每秒 10,000 次，实际请求量取决于 initial delay、单次 Probe 耗时和成功时刻。当前 v3 通过 pre-listen gate 和常量时间 health cache 控制了下游成本，但更换 OCI、health handler 或 envd 行为后必须重新采集请求量、成功率和 reset-timeout，不能默认 5ms 始终安全。

2026-07-28 已实际执行 `CUBESANDBOX_EARLY_PROBE=0` 并重启 Cubelet，恢复原串行路径；该状态通过 2520/2520 benchmark 和 3/3 SDK 门禁，当前继续保留。若以后更重视 c50 吞吐和 p99，可从上述远端备份恢复 `enable=1` 后 daemon-reload/restart；若更重视减少高频探测放大面，则当前关闭配置可作为稳定回退点。无论配置如何，代码中的 `runContainer -> waitProbe` 合流条件都必须保留，禁止因 Probe 提前成功而忽略 RestoreVm/ResetVm 的完成状态或错误。

同配置下使用 bpftrace 跟踪 c50 的 vCPU wakeup-to-run 延迟：vCPU0 78,228 次，平均 7.284us；vCPU1 84,905 次，平均 2.690us。绝大多数样本在 1-4us，约 16,364 次迁移；只有 vCPU0 两个极端样本把 max 拉到 148.45ms。配套 benchmark 为 500/500、avg 197.161ms。由此排除“普遍性的 host vCPU 唤醒/affinity 延迟”作为约 179ms readiness 主瓶颈，不继续做 CPU pinning。

## 14. OCI code server v3：设计、协议与验证

### 14.1 要解决的不是 Python 执行速度

基础 OCI 的启动脚本先把 envd 放到后台，再以前台 Python `ThreadingHTTPServer` 提供 49999 端口。c50 下的热点发生在 sandbox readiness，而不是用户代码执行：Cubelet 需要通过 TAP 访问 `GET /health:49999`，原实现的 health 路径还要在 guest 内访问 envd `GET /health:49983`。当 early probe 缩短到 5ms 后，这条“host probe -> TAP -> code server -> loopback -> envd”的链路会在 50 路创建和数百个保留 VM 上被重复放大。

原生候选只替换 49999 端口的控制面 HTTP server，实际用户代码仍由 `/usr/bin/python3` 子进程执行。因此这里的“原生”是指 Go 实现的 readiness/execute 协议层，不是把 Python code interpreter 改写成 Go，也不改变 guest image、guest kernel 或 envd RPC 实现。

### 14.2 v3 启动状态机

最终镜像在 MMDS-prime OCI digest `sha256:21255c98...dbbb` 上增加静态 ARM64 Go binary 和新启动脚本。binary SHA256 为 `79e869bf6bd9935beb9d5aa79552098573cb383e2b48d6b179a68e8d4e17c79e`。启动顺序如下：

1. shell 计算 `now+10s` 的 MMDS-prime deadline，后台启动 patched envd `:49983`。
2. shell 使用 `exec` 启动 `cube-native-code-server`，使 Go server 成为容器前台进程。
3. Go server 立即请求 `http://127.0.0.1:49983/health`；单次 HTTP client timeout 为 50ms，未成功时按 1ms ticker 重试。
4. 首次得到任意 2xx 后，将进程内 `atomic.Bool envdReady` 置为 true，然后才调用 `ListenAndServe` bind `0.0.0.0:49999`。
5. 10 秒内 envd 始终未健康时调用 `log.Fatal` 退出，容器不会以“49999 可访问但 envd 不可用”的假健康状态继续运行。

这建立了一个可由 Template 保存的不变量：**只要 49999 已经开始监听，`envdReady` 就一定已经为 true**。Template 构建时只有满足这个不变量才可能通过 49999 readiness 并进入可快照状态；sandbox restore 后，listener 和 `envdReady=true` 随进程内存一起恢复。此后的 `/health` 只做一次 atomic load 并直接返回 200，不再为每个外部 probe 串联一次本机 envd HTTP 请求。

达标阶段 Cubelet 的配套 early probe 配置为 delay=0ms、period=5ms。它从 restore 早期就尝试 49999；在端口/网络尚不可用时继续重试，一旦恢复到可访问状态就利用上述快照不变量快速完成 readiness。v3 的重点是把 envd 可用性判断前移到 Template 的 guest 内启动阶段，并把已经验证过的状态保存进快照，而不是让每个 restored sandbox 在并发探针流量中重新判断。后续关闭 early probe 的 A/B 仍使用同一个 v3 Template 并完成全部稳定性门禁，说明 v3 不依赖 early probe 才能正确工作。

### 14.3 v1、v2、v3 的差异

| 版本 | OCI digest | 关键行为 | 结果 |
|---|---|---|---|
| v1 | `sha256:7fc770dd...6ee5` | 立即监听 49999；每次 `/health` 查询本机 envd | period=5ms 最好：500/500，avg 176.343ms；period=2/10ms 分别为 182.016/178.129ms |
| v2 | `sha256:e23faa9a...943` | 单个 `/health` 请求最多阻塞 90ms 等 envd | c1 首轮 19/20；c50 487/500，成功样本 avg 208.016ms；13 个 reset guest time 失败，拒绝 |
| v3 | `sha256:b741fde1...2af3a` | guest 内等待 envd 健康后才 bind/listen 49999 | 四轮 c50 全部 500/500，avg 130.882-135.861ms；采纳 |

v1 证明 Go HTTP 层本身有收益，但它先监听、再由每个 `/health` 请求查询 envd，仍会把探针频率传导到 guest。v2 试图在单个外部请求中等待 envd，结果把连接和 handler 最多占用 90ms；并发下不但没有消除外部请求放大，还引入 13 个 reset-timeout 失败。v3 改为在监听前完成一次 guest 内等待，外部连接不再承担这段等待，因此同时获得最低 avg 和完整成功率。

Docker 单容器 15 轮对照中，v1 health/envd ready 平均为 146.137/150.390ms，v3 为 156.211/153.023ms；v3 并没有改善 OCI 冷启动，甚至 health 均值略慢 10.074ms。c50 却从同状态 v1 的 180.475ms 降至 v3 四轮均值 134.311ms。因此可以排除“Go binary 启动更快”作为主要解释，并合理推断并发收益来自两点：启动阶段不接受 envd 未就绪时的跨 TAP HTTP 请求，以及 restored `/health` 使用快照中已经为 true 的 readiness cache，不再串联 envd。这个机制由代码状态机和 A/B 结果共同支持，但尚未通过逐包 trace 对两部分收益分别定量。

为排除 host 安全重启同时清除临时 `GOMAXPROCS=32` 带来的混杂，在最终 v3 完全相同的 host/Cubelet/drop-in 状态下重新运行 v1 Template：500/500、avg 180.475ms、p95 328.508ms、QPS 234.307，与此前 v1 的 176.343ms 同一量级。v3 四轮均值相对这个同状态控制降低 46.164ms（25.58%），因此最终收益不能用 GOMAXPROCS 状态变化解释。

### 14.4 对外协议兼容性

| 接口/行为 | v3 实现 |
|---|---|
| `GET /`、`GET /health` | envd readiness 已确认后返回 `200 text/plain` 和 `ok`; 未确认时返回 503 |
| `POST /execute` | 接受 JSON，请求体上限 16MiB；返回 `application/x-ndjson` |
| `code` | 必须为 string；每个请求写入独立临时目录并启动一个新的 Python 子进程 |
| `timeout` | 接受 JSON number 或 string；默认 60 秒，最小 1 秒；超时终止子进程并返回 `TimeoutExpired` event |
| 环境变量 | 同时接受 `env_vars` 和 `envVars`，追加到子进程环境 |
| stdout/result | 普通 stdout 转换为 `stdout` event；Python AST 的末尾表达式转换为主 `result` event |
| stderr/error | stderr 形成 `stderr` event；Python exception 或非零退出形成 `error` event |
| 其他路径 | 返回 HTTP 404；畸形 `/execute` JSON 返回 HTTP 400 和 NDJSON error event |

`/execute` 保持基础镜像 `/opt/lightweight-code-interpreter/server.py` 的临时 runner、独立 Python 子进程、timeout、env vars 与 NDJSON stdout/result/error 语义。它不会复用上一次执行的 Python namespace；`CODE_INTERPRETER_WORKDIR` 只是子进程工作目录，runner 和用户源码仍写入独立的 `/tmp/cube-execute-*` 并在请求结束后删除。当前实现收集子进程输出后再写 NDJSON，不应把协议中的多 event 格式理解为实时流式 stdout。

### 14.5 参数、可观测性与已知限制

| 参数 | 默认值 | 作用 |
|---|---|---|
| `ENVD_PORT` | `49983` | envd health 地址端口 |
| `CODE_INTERPRETER_HOST` | `0.0.0.0` | code server bind 地址 |
| `CODE_INTERPRETER_PORT` | `49999` | Cubelet/SDK 访问端口 |
| `CODE_INTERPRETER_WORKDIR` | `/workspace` | Python 子进程工作目录 |
| `PYTHON_EXECUTABLE` | `/usr/bin/python3` | 每次 execute 使用的解释器 |
| `CUBE_WAIT_ENVD_BEFORE_LISTEN` | 非 `0` | 默认启用 10 秒 pre-listen gate；设为 `0` 时立即监听，但 `/health` 在 envd 未就绪时返回 503 |

envd stdout/stderr 写入 `/var/log/envd.log`，Go server 日志进入容器前台日志。排查 Template 构建失败时应先区分三类现象：49999 从未监听通常表示 envd 未在 10 秒内健康；49999 返回 503 表示显式关闭了 pre-listen gate 且 envd 尚未通过；49999 返回 200 但 SDK 失败则属于 readiness 之后的协议或 envd 运行期问题。

当前 `envdReady` 是单向缓存：首次 2xx 后不再周期性检查 envd。因此 v3 保证的是“Template/创建时 envd 曾经健康”，不是 envd 的持续 liveness 监控。如果 envd 在 ready 后崩溃，49999 `/health` 仍可能返回 200；生产化时应增加低频后台 revalidation、让 envd 退出联动终止前台进程，或由独立 supervisor 同时监管两个进程。不能把外部 probe 恢复为每 5ms 同步查询 envd，否则会重新引入本次已消除的高并发热点。

此外，10 秒 gate、50ms 单次 envd timeout 和 1ms guest 内重试是本次测试参数，并非公开稳定 API。更换 envd 版本、基础 OCI 或 Template 构建流程后，需要重新验证 timeout 和快照不变量。回退时应切换到上一 OCI digest 并重建 Template，而不是只替换正在使用的 rootfs 文件。

### 14.6 固定版本与验证门禁

v3 固定信息：

- OCI image：`127.0.0.1:5000/cubesandbox-bench/sandbox-code-envd-ci@sha256:b741fde1de3dd4cc4f4cc82c089e861e5d53f1d5f0b4492be6f9f98f4652af3a`
- Template：`tpl-d38241efa019453f9bc2132c`，2U2G，1G writable layer
- rootfs artifact：`rfs-58c5f1cc76d9100492971bdc`，ext4 SHA256 `d5a1dfbe...c561`
- Cubelet early probe：达标阶段 delay=0ms、period=5ms；当前 `enable=0`，使用标准串行 Probe
- 实现与恢复配置：`optimizations/native-code-server/`

验证分为四层：Go 单元测试覆盖 stdout/result 拆分、envd 前后 health 状态、等待 envd、正常 execute 和畸形请求；Docker 单容器 A/B 检查 cold-start；四轮 c50 检查高并发成功率与延迟；最后使用真实 SDK 做创建后立即执行。

实际 `e2b-code-interpreter==2.8.1` 门禁连续 3/3 通过：每次 Template 创建完成后立即 `run_code("print(12345)\\n21 * 2")`，均得到 stdout `12345`、result `42`，随后成功删除。归档轮次 create latency 为 39.739/39.320/38.596ms，最终 sandbox/shim/task 均为 0。这证明 v3 不是仅让 health 提前成功，SDK envd 和 49999 执行协议在返回时确实可用。

关闭 early probe 后使用同版本 SDK 再执行 3 次，create latency 为 47.840/40.135/41.456ms，`run_code` latency 为 164.920/109.482/112.859ms；3/3 均得到 stdout `12345` 和 result `42` 并成功删除。由此确认回退只改变创建期 Probe 调度，没有破坏 v3 的执行协议或数据面可用性。

## 15. 最终性能结果

### 15.1 early probe 开启的达标阶段

四轮独立 c50 均执行清理与 1000 TAP 空资源门禁，且 reset-timeout signature 为 0：

| 轮次 | 成功 | avg (ms) | p95 (ms) | QPS |
|---|---:|---:|---:|---:|
| admission run1 | 500/500 | 130.882 | 224.272 | 323.567 |
| repeat run2 | 500/500 | 134.990 | 226.794 | 315.280 |
| repeat run3 | 500/500 | 135.861 | 245.710 | 313.002 |
| formal matrix | 500/500 | 135.511 | 242.934 | 318.347 |
| 四轮均值 | **2000/2000** | **134.311** | **234.928** | **317.549** |

相对第一阶段 202.716ms 稳定均值，最终 c50 均值降低 68.405ms（33.74%）；相对 241.47ms 原稳定基线降低 107.159ms（44.38%）。170ms 目标有 35.689ms 余量；尚未达到期望上限中的 100ms。

达标阶段正式矩阵均为首轮成功：

| 场景 | 成功 | avg (ms) | p95 (ms) | max (ms) | QPS |
|---|---:|---:|---:|---:|---:|
| c1n20 | 20/20 | 33.677 | 36.619 | 39.261 | 25.027 |
| c10n200 | 200/200 | 44.947 | 52.985 | 71.385 | 194.172 |
| c20n300 | 300/300 | 58.588 | 90.969 | 148.895 | 285.738 |
| c50n500 | 500/500 | **135.511** | **242.934** | 529.571 | **318.347** |

### 15.2 early probe 关闭后的回退验证

关闭扩展后，每个场景开始前均先删除上一轮 sandbox，并连续三次确认 sandbox/shim/task 为 0、TAP 为 1000 总量且 0 in-use。正式矩阵四组均首轮成功：

| 场景 | 成功 | avg (ms) | p95 (ms) | max (ms) | QPS |
|---|---:|---:|---:|---:|---:|
| c1n20 | 20/20 | 39.000 | 46.207 | 48.172 | 20.948 |
| c10n200 | 200/200 | 53.845 | 103.107 | 115.955 | 164.887 |
| c20n300 | 300/300 | 58.695 | 78.074 | 110.980 | 289.338 |
| c50n500 | 500/500 | **138.610** | **237.325** | 801.969 | **273.828** |

为确认 c50 稳定性，在正式矩阵轮次之外又执行 3 轮：

| 轮次 | 成功 | avg (ms) | p95 (ms) | p99 (ms) | max (ms) | QPS |
|---|---:|---:|---:|---:|---:|---:|
| formal matrix | 500/500 | 138.610 | 237.325 | 267.653 | 801.969 | 273.828 |
| repeat run2 | 500/500 | 138.301 | 223.725 | 747.728 | 1274.879 | 266.738 |
| repeat run3 | 500/500 | 137.679 | 228.059 | 301.291 | 1344.921 | 238.750 |
| repeat run4 | 500/500 | 139.936 | 238.600 | 781.525 | 841.829 | 276.763 |
| 四轮均值 | **2000/2000** | **138.631** | **231.927** | **524.549** | **1065.900** | **264.020** |

正式矩阵加 3 个额外 c50 轮次共 2520/2520，无 HTTP 408、`reset guest time failed` 或残留资源；SDK create + immediate `run_code` 另有 3/3 通过。相对 early probe 开启的四轮均值，关闭后 avg 增加 4.320ms（3.22%），仍稳定低于 170ms；但 p99 增加 207.005ms（65.19%）、QPS 降低 16.86%、批次总时长增加 20.67%。因此 v3 是平均延迟达到目标的主要条件，early probe 可以回退，但开启时对 c50 极端尾部和吞吐更有利。

测试结束后当前状态：安全 boot `cc88832c-9f28-4b3e-812e-1639d30f870a`、`GICv4 support disabled`、四个核心服务 active、TAP 1000/in-use 0、sandbox/shim/task 0。early-probe drop-in 当前为 `enable=0`，已启用版本已备份，可按第 13.4 节恢复。
