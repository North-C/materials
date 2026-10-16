# 三状态配置与实际生效矩阵

本表只读核对 baseline、Go-only、Go+NUMA 三状态，以及正式轮完成后的最终快照。CPU/内存节点限制必须区分 systemd 声明、进程 affinity/mempolicy、容器实际 cpuset 和物理页面位置。

证据时间均为 UTC：

| 状态 | 采集时间 | 原始证据 |
|---|---|---|
| 基线 | 2026-10-16T07:26:09.787645+00:00 | [all-before.json（公开精简快照）](config-snapshot.json) |
| 仅提高 Go 参数 | 2026-10-16T07:28:30.568980+00:00 | [all-go.json（公开精简快照）](config-snapshot.json) |
| 组合配置就绪 | 2026-10-16T07:46:21.762247+00:00 | [all-combined.json（公开精简快照）](config-snapshot.json) |
| 最终复核（修正 exe 采集后） | 2026-10-16T07:52:59.093136+00:00 | [all-final.json（公开精简快照）](config-snapshot.json) |

## CubeMaster Go 环境

| 状态 | GOGC | GOMAXPROCS | GOMEMLIMIT | 实际环境证据 |
|---|---:|---:|---|---|
| 基线 | 400 | 16 | 4GiB | `/proc/MainPID/environ`，[all-before.json（公开精简快照）](config-snapshot.json) |
| Go-only | 800 | 32 | 8GiB | `/proc/MainPID/environ`，[all-go.json（公开精简快照）](config-snapshot.json) |
| Go+NUMA最终 | 800 | 32 | 8GiB | `/proc/MainPID/environ`，[all-final.json（公开精简快照）](config-snapshot.json) |

三值均为实测运行进程环境，800/32/8GiB 是本实验选择的加倍候选；没有把它们误写为用户逐项指定。其他组件未调整这三个 Go 参数。

## 五个原生组件

下表中的 systemd 名称均为 `cube-sandbox-<组件>.service`。基线与 Go-only 的 NUMA 设置相同：CPUAffinity 空、NUMAPolicy=n/a、NUMAMask 空、AllowedMemoryNodes 空；AllowedCPUs 除 Cubelet 为 0-383 外均为 96-191，但实际原生线程仍可用 0-383。

组合配置的五个服务全部声明 `CPUAffinity=96-191`、`NUMAPolicy=bind`、`NUMAMask=1`、`AllowedCPUs=96-191`、`AllowedMemoryNodes=1`；前后快照确认真正生效的是 sched affinity 和 bind:1 内存策略。

| 组件 | 基线实际 CPU / mems / policy | Go-only实际 CPU / mems / policy | 最终实际 CPU / mems / policy | 线程数：基线→Go→组合就绪→最终 |
|---|---|---|---|---|
| cubemaster | 0-383 / 0-3 / default | 0-383 / 0-3 / default | 96-191 / 0-3 / bind:1 | 24→38→38→39 |
| cubelet | 0-383 / 0-3 / default | 0-383 / 0-3 / default | 96-191 / 0-3 / bind:1 | 186→186→40→147 |
| cube-api | 0-383 / 0-3 / default | 0-383 / 0-3 / default | 96-191 / 0-3 / bind:1 | 18→18→17→17 |
| cube-templatecenter | 0-383 / 0-3 / default | 0-383 / 0-3 / default | 96-191 / 0-3 / bind:1 | 71→71→39→39 |
| cubeops | 0-383 / 0-3 / default | 0-383 / 0-3 / default | 96-191 / 0-3 / bind:1 | 67→67→37→38 |

**原生进程的实际 v1 cpuset 仍在根 `/`：cpuset.cpus=0-383、cpuset.mems=0-3，effective 值相同。** 因而不能声称 AllowedCPUs/AllowedMemoryNodes 已形成原生服务 cgroup 隔离。CPU 限制由 CPUAffinity 生效；主线程 numa_maps 的所有已采样 mapping policy 为 bind:1。`Mems_allowed_list=0-3` 与 bind:1 并不矛盾，前者是 cpuset 可用节点，后者是内存分配策略。

五个原生组件最终完整线程采样均成功、非零线程，thread_errors/process_errors 为空，cpuset 祖先读取完整。numa_maps 采集的是主线程视图，并未逐线程独立读取每个线程的 mempolicy。原生进程实际页面仍有跨节点记录，不能据 bind:1 宣称所有既有/文件共享页已迁移到 node1。

## 八个容器组件与其 systemd wrapper

八个容器的 unit 最终也声明相同 CPUAffinity/bind:1/AllowedCPUs/AllowedMemoryNodes，并追加本实验 ExecStartPost cpuset helper。实际容器运行在 `/docker/<ID>`，与 systemd wrapper 不同；必须检查容器内全部进程/线程。

基线及 Go-only：所有 wrapper 实际 CPU=0-383、mems=0-3、policy=default。组合配置中只有 Egress 因 Cubelet 依赖重建并启动了新 wrapper，其实际 CPU=96-191、mems=0-3、policy=bind:1；其余七个 wrapper 保留原 PID，仍 CPU=0-383、mems=0-3、policy=default。**这七个 wrapper 的 bind 声明已持久化，但没有重启生效；实际服务负载由下表容器 cpuset 限制。** 避免重启 Proxy/LCM 也避免了现有启动脚本无条件 pull tag 的镜像漂移路径。

| Unit组件 / 实际容器 | 基线与Go-only实际容器 CPU / mems / policy | 组合就绪及最终实际容器 CPU / mems / policy | 最终进程数 / 线程数 | wrapper最终实际 policy |
|---|---|---|---:|---|
| coredns / `cube-proxy-coredns` | 96-191 / 0-3 / default | 96-191 / 1 / default | 1 / 106 | default（旧wrapper未重启） |
| cube-egress / `cube-egress` | 0-383 / 0-3 / default | 96-191 / 1 / default | 3 / 3 | bind:1 |
| cube-lifecycle-manager / `cube-lifecycle-manager` | 96-191 / 0-3 / default | 96-191 / 1 / default | 1 / 43 | default（旧wrapper未重启） |
| cube-proxy / `cube-proxy` | ⊆96-191 / 0-3 / default | ⊆96-191 / 1 / default | 387 / 387 | default（旧wrapper未重启） |
| minio / `cube-sandbox-minio` | 96-191 / 0-3 / default | 96-191 / 1 / default | 1 / 105 | default（旧wrapper未重启） |
| mysql / `cube-sandbox-mysql` | 96-191 / 0-3 / default | 96-191 / 1 / default | 1 / 54 | default（旧wrapper未重启） |
| redis / `cube-sandbox-redis` | 96-191 / 0-3 / default | 96-191 / 1 / default | 1 / 6 | default（旧wrapper未重启） |
| webui / `cube-webui` | 96-191 / 0-3 / default | 96-191 / 1 / default | 385 / 385 | default（旧wrapper未重启） |

CubeProxy 的 387 个进程/线程中，291 个 affinity 为96-191，另96个以每CPU三个线程分布在96–127的单CPU集合；它们均是目标集合的子集，不能误报为未遵守约束。

八个容器 HostConfig 均为 cpus=96-191、mems=1；实际叶 cpuset 文件与 effective 值同样为96-191/1。两个祖先 `/docker`、根 `/` 均为0-383/0-3。容器所有被枚举线程的 Mems_allowed_list=1、CPU集合均包含于96-191，全部主线程 numa_maps 为 default。这表示 default 分配受 cpuset 节点1限制，不等于容器执行过 set_mempolicy(bind)。容器改动是在线 cpuset 更新，未对既存页面做完整迁移；不能承诺全部RSS位于node1。

## 其他组件的适用性

| 项目 | 最终状态 / 证据 | 本次处理理由 |
|---|---|---|
| cube-sandbox-dns.service | active/exited，MainPID=0；NUMAPolicy=n/a；原历史无NUMA映射 | oneshot宿主DNS路由配置，无常驻Cube进程；不修改无关dnsmasq |
| cube-sandbox-cube-egress-net.service | active/exited，MainPID=0；NUMAPolicy=n/a；原历史无NUMA映射 | oneshot iptables/ip-rule配置，随依赖恢复；无常驻线程可绑定 |
| cube-sandbox-s3lvol.service | inactive/dead，MainPID=0；原历史无NUMA映射 | 未启用数据面，不为此实验启动或新增历史不存在的映射 |
| cube-sandbox-control.target / compute.target | systemd target，无负载PID | 依赖编排对象，不适用进程CPU/内存策略 |
| Shim/VMM | 由Cubelet创建，无独立长期unit | 见下方精确owned sandbox样本，不能仅凭继承假定 |
| cube-ingress / cube-sandbox-containerd unit | 本机不存在这些独立unit | 不创建虚构组件；Cubelet内嵌运行时不作为另一个独立systemd服务修改 |
| Docker daemon、Grafana、Prometheus等 | 不属于本次CubeSandbox组件恢复范围 | 未修改无关服务，未恢复历史监控node2映射 |

适用性来源：[历史及当前unit盘点](numa-history.md)、最初逐服务properties（原始私有证据未公开）；最终07:53 UTC只读复核dns/egress-net/s3lvol仍分别为上述状态。

## 本轮 Shim/VMM 实际样本

证据：[combined-sandbox-round03.json](combined-sandbox-round03.json)，采集于 2026-10-16T07:49:04.831067+00:00。精确归属combined第3轮CLI确认的预热沙箱 `combined-round-03-warmup-001`，template=`template-anonymous`，Shim PID1617824，采集前后start_ticks一致。

- 共22个线程，含 `vmm`、`vcpu0`、`vcpu1`；全线程affinity=96-191、Mems_allowed_list=0-3，无线程读错或集合变化。
- 主线程numa_maps中191个mapping policy均为bind:1；实际cpuset仍为根0-383/0-3。
- 页面节点计数：N0=392、N1=8171、N2=512、N3=32175。这是映射页计数汇总，不是独立物理页或guest匿名页精确归属；明显跨节点，**不能宣称沙箱全内存已搬迁到node1**。
- 这是一个本轮预热沙箱样本，不是100个正式沙箱全覆盖。正式沙箱的统一继承只能作为机制解释，不能替代实测。

## 镜像身份、采集错误及证据边界

八个容器在基线、Go-only、组合就绪、最终的Docker Image ID逐项相同；仅Egress容器ID改变（正常依赖重建），其Image ID不变。下表保留完整值便于审计。

| 容器 | 四状态相同的Image ID | 容器ID是否改变 |
|---|---|---|
| cube-egress | `sha256:7363ab280b3497e1d1f644dae6183c959bc9d40baf8ad98a59c6a03a17074bc4` | 是，仅Egress重建 |
| cube-proxy | `sha256:67957f63c92a4d52190a196a6a2adaaf6fd9664ef37f54f98b2cdc52489102ee` | 否 |
| cube-lifecycle-manager | `sha256:91dfa6829f4dbbf96d3fdc8ef22daea5548a28370ac0ef42510f5be7c14d8546` | 否 |
| cube-webui | `sha256:9808bfe96c4ff5252bd1af78850ed879f1d1a03d941252c48378b39b7578171c` | 否 |
| cube-sandbox-redis | `sha256:80dd823f4d2bf93dd5e418a0ae2817319a1ba279953e234082e54a5a18306223` | 否 |
| cube-sandbox-mysql | `sha256:b7e118f56c5963e079252e0d6e2978c9c010eb7fc7aaaec100e367796b5dd08f` | 否 |
| cube-sandbox-minio | `sha256:8f08aee614800a237906bd48114d733e5ac5bfac4ccdf731f141b0e880d7a253` | 否 |
| cube-proxy-coredns | `sha256:fe81a497e85f174f8d7d5739d14f5184141f4e80596977ff8f838d7062fecf02` | 否 |

模板最终仍READY；template-current.json（原始私有证据未公开） 与 template-final.json（原始私有证据未公开） 的image_info一致：`sandbox-code@sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d`。模板规格仍2000m/2048Mi；preflight.json（原始私有证据未公开）保存初始本地镜像ID及RepoDigests。这里只核对模板固定digest与八个长期容器Image ID，服务器二进制身份另见 [version-before.json](version-before.json) / [version-final.json](version-final.json)。

采集器曾以 `Path(/proc/PID/exe).resolve(strict=True)` 解析容器内可执行路径，宿主不存在相同路径会产生exe ENOENT。组合就绪快照 [all-combined.json（公开精简快照）](config-snapshot.json) 和保留的 all-final-pre-exe-fix.json（原始私有证据未公开） 因此包含exe读取错误。这没有影响线程affinity、cgroup文件或numa_maps读取；不能将旧快照笼统称为零采集错误。主代理已将只读exe路径采集改为readlink，并重采本表引用的 [all-final.json（公开精简快照）](config-snapshot.json)，性能轮原始数据未改。

新最终快照枚举13个unit主进程和780个容器进程，thread_errors/process_errors均为空、线程采样完整且非零、cpuset祖先读取完整；所有13个长期unit均active/running、8个容器均running。该快照证明采样时约束与运行状态，不替代API业务健康测试，也不保证未来新线程/新容器永远不改变约束。
