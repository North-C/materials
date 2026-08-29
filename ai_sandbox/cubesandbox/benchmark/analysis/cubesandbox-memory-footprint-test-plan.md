# CubeSandbox 宿主机内存开销测试计划

## 0. 文档状态与当前阻塞

- 文档日期：2026-08-29（Asia/Shanghai）。
- 本地工作树：`<local-worktree>`。
- 本地源码 HEAD：`09274501dd12e47dbed2dcc77d8eb67dd661d49c`；tree：`3b1b2fce653aa10073ac7a41e97e83d1cc613320`。
- 2026-08-29 对 `<original-target-host>` 的只读 SSH始终不可用；当前 `<original-target-host>` 的 boot/kernel/hash/Template/资源状态仍未确认，未在 `<original-target-host>` 创建或删除任何对象。
- 用户随后授权把 `<test-host>` 作为可选现场。Orca 筛选未发现另一个正在运行的 `<test-host>` worker；只读 SSH 确认该机 hostname=`<hostname>`、boot ID=`<boot-id>`、kernel=`6.6.0-132.0.0.111.oe2403sp3.aarch64`。进一步只读审计确认 API Sandbox/Snapshot、shim/VMM/virtiofsd/in-use TAP 为 0，但该机为 cgroup v1、没有 PSI、存在 `dnf-makecache.service` failed，约 13.4k threads、27–29 个 blocked task、Dirty 约 76 MiB，Kubernetes 控制面持续占用 CPU；load1 在 20.65→11.48→12.77 间仍远高于 5。它既不是本任务要求核对的 6.6.119 环境，也同时违反多项 G0/G2 门禁，因此未创建或删除任何 Sandbox。
- Orca 只读状态显示相关历史测试 worktree 的 agent 已结束、旧 SSH 终端已断开；这只能证明 Orca 中已知终端状态，不能替代远端登录/进程核验。
- 当前工作树没有 `.codegraph/`；CodeGraph MCP 返回 `not initialized`。未获授权前不执行 `codegraph init -i`，本计划仅引用已逐项读取的当前源码文件。
- 用户在看到 `<test-host>` 的 kernel/cgroup/负载差异后明确授权继续：把 `<test-host>` 作为独立环境，先以 10 分钟纯只读 N=0 建立 control envelope，再以该包络替代 `<original-target-host>` 专用的绝对 load/threads/blocked/Dirty 门禁。该授权不允许修改 `<test-host>` 参数，也不允许把 `<test-host>` 与 `<original-target-host>/6.6.119` 合并成一条结果。
- 独立档位执行状态：`<test-host>` Phase A、N=0、N=1/10/50成功；N=100 measurement完成并精确清理，但随后非 Cube `dnf-makecache.service` 因外部仓库 TLS reset进入 failed，整轮 cleanup health gate超时。独立轮正式上限 N=50，N=100为带失败边界的观察点。
- 用户随后要求按社区 create-only累计顺序继续到 N=1000。累计 R1在 N=100因新增 Guest probe使用c50并发而0/100超时，保留失败并精确清理；单实例 c1诊断证明 probe接口可用。累计 R2改为顺序 probe，N=100创建/ready/probe/settled全部成功。
- R2在 N=300首个 POST之前发现 CubeMaster/CubeAPI inventory异常；只读诊断确认宿主根分区100%满、Redis RDB `No space left on device`并进入 `MISCONF`。本 worker停止提交并进入精确清理。100个 owned ID各 DELETE一次，均返回500且不重试；最终 Master/Cubelet/API、shim/VMM/TAP运行时对象均为0，但 Redis proxy-map一致性为unknown。
- N=300/500/1000均未提交、未测、不得外推。当前现场禁止继续测试，直到管理员释放根分区、恢复Redis持久化、核对可能的proxy-map残留，并重新完整通过Phase A。
- 方法缺陷披露：最初 Phase A已记录 `/` 仅余约357 MiB，但旧 gate未检查文件系统可用空间。现已把默认 `root free >= 10 GiB`加入 Phase A和未来累计 runner；既有结果和失败不被追溯改写。

恢复执行的前提不是“SSH 能连通”本身，而是重新从头通过本计划的 G0、G1、G2，并额外证明根分区空闲不少于10 GiB、Redis persistence健康、proxy-map与Master/Cubelet空集一致。历史报告中的 boot ID、hash、Template ID、endpoint 状态和空载资源不得自动继承。

## 1. 目标、结论边界与非目标

### 1.1 目标

在不改变系统行为参数的前提下，对当前 `<original-target-host>` 现场形成四组可交叉验证、但不互相相加的测量：

1. CubeSandbox 控制面和通用宿主服务在 `N=0` 时的固定内存开销及自然漂移。
2. running Sandbox 从 `N=1` 到可安全达到的最大观测点的边际内存斜率、每点摊销和非线性。
3. 每个 Sandbox 的 PSS/USS、cgroup `anon/file/kernel` 和 Snapshot file mapping 的共享/独占构成。
4. `before -> create peak -> settled -> after cleanup` 的回收曲线，以及 Sandbox/shim/task/VMM/TAP/cgroup/threads 的归零与自然冷却。

### 1.2 只允许得出的结论

- 当前已核验 boot、组件、Template、参数和窗口下的观测结果。
- 固定组件 PSS/USS/cgroup 开销、每实例边际斜率及其置信区间。
- 在已观测密度范围内的共享、独占、cgroup 记账和 Host 全局变化趋势。
- 清理后的回收时间和未闭合项的证据化解释边界。

### 1.3 禁止的结论

- 不把 2000 MiB Guest 配置内存称为 Host resident。
- 不把 `MemAvailable` 差值称为 Sandbox RSS 或 VMM RSS。
- 不把 RSS 直接相加作为物理总量。
- 不把 PSS、USS、cgroup `memory.current` 与 `MemAvailable` delta 相加。
- 不把 `memory.current` 直接等同于 PSS；共享页在 cgroup 和 PSS 中的记账语义不同。
- 不把 `MemAvailable` 与任意分项强行“闭合”；`MemAvailable` 是包含回收估计的可用性指标，不是互斥分类总和。
- 不把单次或少量密度点外推到 934/1000；未通过门禁的目标不形成正式数据点。
- 不根据当前 HEAD 倒推远端部署实现；部署版本必须由远端二进制和运行行为重新确认。

### 1.4 非目标和禁止操作

- 不做性能优化、参数调优、部署、二进制替换、服务 restart/stop、驱动 reload、reboot 或安装软件包。
- 不改 sysctl、NUMA balancing、THP、HugePages、swap、quota、绑核、SELinux、firewalld。
- 不执行 `drop_caches`、OOM/压力测试、破坏性 workload，且不提高 `threads <= 8000` 门禁。
- 不 kill `kvm-irqfd-cleanup` kworker。
- 不删除、暂停、恢复或干预非本 run 创建的对象。
- 不 commit、push 或创建 PR。

## 2. 已核对的方法与当前源码事实

### 2.1 社区方法和历史证据的使用方式

已读取社区数据形成指南的 `dataflow.md`、`evidence.md`、`review-method.md`、`matrix.md`、`snapshot.md` 和 `pause-resume.md`，以及 6.6.119、Snapshot/Pause/Clone 的既有计划和报告。它们只提供对象模型、timer、门禁和证据链入口。

历史密度的 `total_delta / N` 只保留为：

```text
host_memavailable_amortized_mib
  = (MemAvailable_N0_KiB - MemAvailable_N_KiB) / 1024 / N
```

它是“整机 `MemAvailable` 摊销”，混合匿名页、Page Cache、slab、页表、内核对象、控制面漂移与同期其他负载。历史 100/300/500 的 21.177/21.589/23.006 MiB/实例是线索，不是本轮基线；934 处的资源错误不构成 1000 点，也不是内存耗尽证据。

### 2.2 当前 `resource-metrics` 的精确边界

当前 HEAD 中：

- `host_sandbox` 从 CubeBox 保存的 `CGroupPath` 读取 Host cgroup，范围包含 shim、VMM 和其他被放入该 cgroup 的 Host 侧进程；它不是 guest workload 视角。入口见 `Cubelet/plugins/cube/internals/resourcemetrics/host_sandbox_sampler.go:38-40,250-283`。
- cgroup v2 的 `UsageSnapshot` 通过 cgroup manager `Stat()` 得到 usage；当前导出的 memory 字段只有 `MemoryCurrentBytes`、limit 和 `memory.events:max`，见 `Cubelet/plugins/cube/internals/cgroup/handle/v2/manager.go:382-401,427-469`。
- Prometheus `cubesandbox_host_sandbox_memory_current_bytes` 原样导出该 total，见 `Cubelet/plugins/cube/internals/resourcemetrics/prometheus.go:31-40,121-140`。
- 当前产品指标不导出 `memory.stat` 的 `anon/file/kernel/pagetables/slab` 明细。因此本测试必须直接读取对应 cgroup 文件，不能用 Prometheus total 推测分层。
- Host cgroup 是可复用池；当前路径常量为 `/cube_sandbox/sandbox` 和 `/cube_sandbox_v2/sandbox`，见 `Cubelet/plugins/cube/internals/cgroup/handle/interface.go:29-37`。累计 counter 有 assignment baseline，但 `memory.current` 是当前 gauge。每轮必须同时记录 Sandbox ID、cgroup path、cgroup inode 和 assignment 时刻，防止把复用槽位的前一对象当成本对象。
- `guest_workload` 与 `host_sandbox` 是不同 cgroup 视角，不能相加。本测试的 Guest workload 指标仅作解释字段，不作为 Host 物理内存主口径。

### 2.3 当前源码的 Snapshot memory 映射语义

当前 HEAD 的 VMM restore：

- `new_from_snapshot` 在 fast restore 分支打开 Snapshot memory file 并传给 MemoryManager，见 `hypervisor/vmm/src/memory_manager.rs:1326-1368`。
- Snapshot file RAM region 使用 `MAP_PRIVATE | MAP_NORESERVE`；只有 `prefault=true` 才加 `MAP_POPULATE`，见 `hypervisor/vmm/src/memory_manager.rs:1494-1545`。

因此多个 VMM 可能共享同一 Snapshot file 的只读驻留页，并在写入时形成私有 CoW 页。该机制支持使用 PSS 做比例分摊、USS/Private 做独占观察；它不证明远端当前部署二进制一定与 HEAD 相同。远端必须用 version/hash、`/proc/<pid>/maps`/`smaps`、VMM 日志和 Template 实体路径重新验证。

### 2.4 runner 复用边界

- 社区 `cube-bench` 使用容量为 C 的 semaphore 提交 goroutine；`wall/N` 是吞吐摊销而不是单请求 latency，见 `examples/cube-bench/runner.go:152-178`。
- 分位数采用 nearest-rank：`ceil(N*p/100)-1`，见 `examples/cube-bench/stats.go:15-30`。
- 既有 6.6.119 runner 已具备唯一 metadata、精确 ID 所有权、失败分母和门禁框架，但只采有限 Host 字段。后续可复用其 HTTP/ownership/cooldown 骨架，内存采样必须新增，不复用历史 expected hash、boot ID 或 Template ID。
- 远端不安装 `smem`、`jq`、`numastat` 或 Node。优先直接解析 `/proc` 和 cgroup；JSON/统计使用已有 `python3` 标准库。

## 3. 内存对象模型与去重规则

### 3.1 A — Host 全局视图

每个 Host 样本记录：

- `/proc/meminfo`：`MemTotal`、`MemFree`、`MemAvailable`、`Buffers`、`Cached`、`SwapCached`、`Active*`、`Inactive*`、`AnonPages`、`Mapped`、`Shmem`、`Slab`、`SReclaimable`、`SUnreclaim`、`KernelStack`、`PageTables`、`Percpu`、`VmallocUsed`、`Dirty`、`Writeback`、HugePage 字段。
- `/proc/pressure/{cpu,memory,io}` 的 `some/full` 全行及 total。
- `/proc/vmstat`：`pgfault`、`pgmajfault`、`pgscan_*`、`pgsteal_*`、`allocstall*`、`oom_kill`、`compact_*`、`workingset_refault*`、`pswpin/out`、NUMA counters。
- `/proc/stat`、`/proc/loadavg`、总 threads、`kvm-irqfd-cleanup` 数量。
- NUMA node `meminfo`/`numastat` 的 free/used/anon/file/slab/local/other。
- `/proc/diskstats` 与目标块设备的读写 sectors/requests/time/inflight；若 cgroup `io.stat` 可用则同时保存。
- `/proc/slabinfo` 的 XFS、dentry、inode、kmalloc 相关行作为内核附加证据；不把 slab 名称直接归属给单个 Sandbox。

Host 视图用于容量与差额解释，不用于替代进程或 cgroup 归属。

### 3.2 B — 服务固定开销

按 systemd ownership 和实际进程树分类，不按进程名猜测：

| 类别 | 候选对象 | 报告方式 |
|---|---|---|
| CubeSandbox 控制面/节点面 | CubeMaster、Cubelet、CubeAPI、network-agent | 单进程 PSS/USS/RSS + unit cgroup total/stat |
| CubeSandbox runtime 公共层 | 被配置给 Cube runtime 的 containerd 子进程、公共代理 | 单独列示，不默认并入固定控制面 |
| 通用宿主服务 | containerd 主进程、Docker daemon、systemd、SSH 等 | 单独 control；不称 CubeSandbox 固定开销 |
| 部署管理容器 | MySQL、Redis、registry、Web/UI 等 Docker 容器 | 按容器/systemd ownership 分类并单列 |

每个对象记录 PID、start ticks、exe、disk/proc SHA-256、version、PPID/进程树、systemd unit、cgroup path/inode、CPU/MEM affinity，以及：

- `/proc/<pid>/smaps_rollup` 全字段。
- `/proc/<pid>/status` 的 `VmRSS/RssAnon/RssFile/RssShmem/VmPTE/VmSwap/Threads`。
- `/proc/<pid>/statm` 和 `/proc/<pid>/stat` 的 start ticks/minflt/majflt。
- unit cgroup 的 `memory.current`、`memory.peak`、`memory.stat`、`memory.events`、`memory.events.local`、`memory.swap.current`、`io.stat`。

### 3.3 C — Sandbox 动态对象

必须从本轮精确 Sandbox ID 建立关联，不允许只按进程名计数。每行关系至少是：

```text
run_label -> sandbox_id -> CubeBox/containerd container/task
          -> shim PID/start_ticks -> VMM PID/start_ticks
          -> virtiofsd/相关 PID -> cgroup path/inode
          -> TAP -> Template/Snapshot rootfs/memory path + dev/inode
```

关联证据来自 API、Cubelet/CubeBox 信息、containerd namespace、`/proc/<pid>/cgroup`、父子进程树、完整 cmdline（脱敏）和文件 mapping。任一 Sandbox 无法唯一关联到动态对象时，该密度点不进入正式分布统计。

每个动态进程采集与服务相同的 proc 字段；每个 Sandbox cgroup采集 total、peak、stat、events、swap 和 io。`memory.peak` 需要确认是本对象创建后的新/复用语义；若池复用使 peak 未清零，则保留原值并标记 unusable，不把它当本轮 peak。

### 3.4 D — Sandbox 内存分层

报告分成以下互不混淆的层：

1. Guest 配置内存：Template/API 的逻辑规格，仅作分母/身份字段。
2. VMM/shim 进程 resident：RSS、PSS、USS 和 `Pss_Anon/Pss_File/Pss_Shmem`。
3. Snapshot memory mapping：按 `/proc/<pid>/smaps` 中匹配的 `dev:inode + canonical path` 汇总 mapping PSS、Private、Shared、Anonymous、Referenced。
4. Sandbox cgroup：`memory.current` 及 `memory.stat` 的 `anon/file/kernel`；`kernel_stack/pagetables/slab_*` 是 `kernel` 的子项，不再与 `kernel` 相加。
5. Host 内核/缓存：Host `Cached/Slab/PageTables/KernelStack`、disk IO、fault/reclaim，仅作跨视角解释。
6. rootfs/CoW/XFS metadata：实体文件/块对象、apparent/allocated bytes、extent/reflink 和相关 file/slab 变化；没有直接归属证据时保留为 unknown。

### 3.5 E — 共享/独占与去重

- `RSS = Rss`，只作单进程驻留观察；禁止跨 VMM 直接求和后称物理内存。
- `PSS = Pss`；同一组目标进程的 PSS 可求和作为按映射共享者比例分摊的进程视图。
- `USS_nonhugetlb = Private_Clean + Private_Dirty`。`Private_Hugetlb` 若存在则单列，避免不同 kernel 对 RSS/PSS hugetlb 记账差异。
- `shared_mapping = Shared_Clean + Shared_Dirty` 仅描述该进程 mapping 属性，不等于全局唯一共享页大小。
- `Snapshot_mapping_PSS` 按同一 Snapshot memory 的 dev/inode 过滤后汇总；同时保留每个 VMM 的 mapping USS/PSS。
- cgroup `memory.current` 包含该 cgroup 被 charge 的 anon、file 和 kernel memory；共享 file page 可能只 charge 到一个 cgroup，不能与 PSS逐字节闭合。
- Host `MemAvailable` delta、PSS、USS、cgroup total 是三个平行视角，只做对照和差异解释，不相加。

## 4. Phase A — 现场身份、工具和并发门禁

SSH 恢复后必须重新开一个新的只读 capture，从第一项开始，不复用本次失败 attempt。

### 4.1 G0：Host 和部署身份

保存并核验：

1. 时间、timezone/NTP、hostname、uname、boot ID、cmdline、OS、uptime。
2. running kernel image/config/initramfs 的 path/stat/SHA-256；聚焦保存 KVM/ARM64 NMI/VGIC/irqfd/HZ/PREEMPT/NUMA/THP/HugePage/memcg/cgroup v2/PSI/XFS/swap config。
3. CPU 型号、online CPU、NUMA topology/distance、node memory、NUMA balancing、THP/defrag、HugePages、swap、PSI。
4. `/`、`/data`、`/data/cubelet` 的 mount/source/XFS feature/reflink/quota/空间/inode。
5. systemd unit ownership、Fragment/DropIn/ExecStart/MainPID/start time/ControlGroup/MemoryCurrent/TasksCurrent；failed units。
6. CubeMaster、Cubelet、CubeAPI、network-agent、CubeShim、cube-runtime/VMM、cubecli 的 disk/proc exe、version/commit/SHA-256/ELF。
7. containerd/Docker 管理容器的 image digest、名称、状态和 cgroup；输出不含环境变量或 secret。
8. API/Master/Cubelet/network-agent endpoint HTTP status；node `Healthy/RUNNING`、capacity/quota/update time。
9. Template 分页列表；选择一个 READY、replica READY、固定 `<original-target-host>`、2U2G、probe 明确的 Template，保存 CPU/memory/fingerprint/image/guest kernel/rootfs/Snapshot memory/config/state identity。
10. Template JSON 和 artifact URL 先机械脱敏 `token/key/signature/credential/cookie/Authorization`，再进入 evidence。

`/` 的 `statvfs` 可用空间必须不少于10 GiB；同时保存 `/data` 与 `/data/cubelet` 空间/inode。任一目标文件系统低于门禁、身份字段无法取得、身份在测试期间漂移或服务不健康，立即停止。该10 GiB是采集安全下限，不是容量结论，也不授权删除文件。

### 4.2 G1：操作者与资源

同时核验 Orca 和远端：

- Orca `<original-target-host>` 相关 worktree/terminal/agent 的 state、last output 和 SSH terminal。
- 远端 `who -u`、`w`、TTY 子进程，以及 benchmark/worker/trace/build/test/perf/bpftrace/fio/stress 等活动。
- Sandbox 和 Runtime Snapshot 的 before ID 集合。
- CubeShim、containerd `cubens` task/container、VMM、virtiofsd、proxy、pausevm、Snapshot/CubeCow worker。
- TAP 总池与真正 in-use/up/USED 集合分开。
- Sandbox cgroup 目录及 inode；监听端口和本轮工具会使用的路径。

只有以下条件同时成立才通过：

1. 没有其他 worker 或人工会话正在操作 `<original-target-host>`。
2. Sandbox、Runtime Snapshot、shim、task、VMM、virtiofsd、in-use TAP 和动态 Sandbox cgroup 都等于确认后的 `N=0` 基线；预建 down TAP 池单独登记。
3. 无无法解释的 pausevm、Snapshot/CubeCow 或孤儿对象。
4. 当前资源集合与 before manifest 可精确保存。

若存在任何非零或身份不明对象，停止并报告，不接管、不清理。

### 4.3 工具核验与 fallback

| 能力 | 首选 | fallback/停止条件 |
|---|---|---|
| 进程 PSS/USS | `/proc/<pid>/smaps_rollup` | 不可读则停止该对象的正式统计；不安装 `smem` |
| mapping 分层 | `/proc/<pid>/smaps` + maps dev/inode | 不使用 `pmap` 输出替代 PSS |
| cgroup | unified cgroup v2 `memory.*` | `<test-host>` 已明确授权使用 cgroup v1 `usage/stat/failcnt`；必须标注 first-touch/fuzzy charge，不能与 v2 或 PSS混用 |
| NUMA | `/proc/<pid>/numa_maps`、node sysfs | `numastat -p` 仅在已安装时补充；不安装 |
| JSON | `python3` 标准库 | `jq` 不是依赖 |
| disk IO | `/proc/diskstats`、cgroup `io.stat` | `iostat` 仅在已安装时补充 |
| 分析 | `python3` 标准库 | Node/NumPy/SciPy 不是依赖 |

采集器先在 `N=0` 对服务 PID 做一次 dry collection，验证 schema、单位、PID start ticks 和脱敏；dry collection 不修改系统。

## 5. 采样时序与原始数据 schema

### 5.1 三类时间

每条记录同时保存：

- `epoch_ns`：跨文件关联和日志窗口。
- `monotonic_ns`：本机 duration、settle、cooldown 唯一计时来源。
- `boot_id`：排除跨 boot 拼接。

远端 NTP 未核验前，绝对 wall time 不用于性能结论。

### 5.2 一轮的边界

```text
pre-N=0 envelope
  -> create_start
  -> create_peak sampling
  -> all requested == successful == running == target
  -> settle_delay 30s
  -> settled_window 90s
  -> delete only owned IDs once
  -> cleanup/cooldown sampling until gates pass or 600s timeout
```

- Host sampler：从 create 前 30 秒开始到 cleanup 结束，每 2 秒一次。
- settled window：固定 90 秒；Host 每 2 秒，服务 proc/cgroup 每 15 秒。
- 全 Sandbox 深采样：settled window 的 0/45/90 秒各一次 `smaps_rollup + status + statm + stat + cgroup memory.*`。
- `/proc/<pid>/smaps` mapping 和 `numa_maps` 因读取成本更高，在 45 秒点对全部 Sandbox 做一次；N>=300 时先在 N=100 记录采集 wall/CPU 开销，若采集本身干扰明显则停止升级，而不是抽样后假装全量。
- create peak：使用 Host/cgroup outer sampler 中的最大值；不把采样器观察到的离散 peak 称为绝对瞬时峰值。
- 每个窗口记录采样耗时、丢失 PID、PID start tick变化和错误；PID 消失不能填 0。

### 5.3 核心 CSV 字段

`memory-samples.csv` 每行一个 Host timestamp：

```text
run_label,round,density,phase,sample_no,epoch_ns,monotonic_ns,boot_id,
memtotal_kib,memfree_kib,memavailable_kib,active_kib,inactive_kib,
anonpages_kib,mapped_kib,cached_kib,shmem_kib,slab_kib,
sreclaimable_kib,sunreclaim_kib,pagetables_kib,kernelstack_kib,
dirty_kib,writeback_kib,psi_*,pgfault,pgmajfault,reclaim_*,oom_kill,
node*_memfree_kib,node*_anon_kib,node*_file_kib,
disk_reads,disk_sectors_read,disk_writes,disk_sectors_written,
threads,kvm_irqfd_cleanup,load1,procs_running,procs_blocked,
sandbox_count,shim_count,task_count,vmm_count,virtiofsd_count,tap_in_use
```

`process-map.csv` 每行一个进程深样本：

```text
run_label,round,density,phase,deep_sample_no,sandbox_id,role,pid,
start_ticks,ppid,exe,exe_sha256,unit,cgroup_path,cgroup_inode,
rss_kib,pss_kib,pss_anon_kib,pss_file_kib,pss_shmem_kib,
shared_clean_kib,shared_dirty_kib,private_clean_kib,private_dirty_kib,
private_hugetlb_kib,uss_nonhugetlb_kib,anonymous_kib,swap_kib,swappss_kib,
vmrss_kib,rssanon_kib,rssfile_kib,rssshmem_kib,vmpte_kib,
minflt,majflt,numa_node*_pages,snapshot_mapping_*
```

`cgroup-memory.csv` 每行一个 cgroup 深样本：

```text
run_label,round,density,phase,deep_sample_no,sandbox_id,owner_class,
cgroup_path,cgroup_inode,memory_current,memory_peak,memory_swap_current,
anon,file,kernel,kernel_stack,pagetables,percpu,sock,vmalloc,
slab_reclaimable,slab_unreclaimable,shmem,file_mapped,file_dirty,
inactive_anon,active_anon,inactive_file,active_file,workingset_*,
events_low,events_high,events_max,events_oom,events_oom_kill,
events_local_*,io_stat_raw
```

raw 文件保留原字段，CSV 中未知/不存在字段留空，不写 0。

## 6. Phase B — `N=0` 固定基线

### 6.1 前置断言

- G0/G1/G2 通过。
- Sandbox/Snapshot/shim/task/VMM/virtiofsd/in-use TAP/动态 cgroup 为确认的零集合。
- boot、PID start、exe hash、unit start time在窗口前后不变。

### 6.2 窗口

- 连续 10 分钟。
- Host 每 2 秒：约 301 个样本。
- 服务 proc/cgroup 每 15 秒：约 41 个样本。
- 第 0/300/600 秒保存完整 process tree、unit ownership 和 Docker management container inventory。

### 6.3 输出

对每个固定组件分别报告：

- RSS/PSS/USS 的 median、min、max、nearest-rank P50/P95。
- `Private/Shared Clean/Dirty`、PSS anon/file/shmem。
- unit cgroup `memory.current` 的 median/min/max；`anon/file/kernel` 分层。
- `memory.current - process PSS sum` 作为语义差异观察值，不称遗漏内存。
- N=0 全局 `MemAvailable` 的 median/min/max、MAD、P5/P95，形成 control envelope。

服务固定开销主值定义为：

```text
platform_fixed_pss = median_t(sum PSS of verified CubeSandbox fixed processes)
platform_fixed_uss = median_t(sum USS_nonhugetlb of same processes)
```

containerd/Docker/MySQL/Redis 等不确定归属对象分别列示，不默认并入 `platform_fixed_*`。

## 7. Phase C — running Sandbox 阶梯密度

### 7.1 固定输入

- 同一 live-verified READY Template、replica、CPU、memory、fingerprint、guest kernel/rootfs/Snapshot memory dev+inode。
- 同一 API endpoint、请求 body、timeout、`distributionScope=["<original-target-host-ip>"]` 和 probe。
- 唯一 run label：`<run-label>`。
- metadata 至少含 `run_label/round/density/seq/worker`。
- 除 N=1 外，create 最大在途数固定 `C=10`；密度测试不以创建吞吐为目标。
- 不做未登记 warmup，不通过 `drop_caches` 控制 cache。

### 7.2 主矩阵与顺序效应

主矩阵：`N=1,10,50,100`。关键点至少三轮，每轮都从 `N=0` 独立创建并完整清理：

| 轮 | 顺序 | 目的 |
|---|---|---|
| R1 | 1 -> 10 -> 50 -> 100 | 冷到暖的递增序列 |
| R2 | 100 -> 50 -> 10 -> 1 | 分离密度与累计 Page Cache 顺序 |
| R3 | 10 -> 1 -> 100 -> 50 | 平衡剩余顺序效应 |

表中的箭头表示独立 tier 的执行次序；每个 tier 清理到 N=0 后才进入下一个，不复用上一 tier 的 Sandbox。

扩展点：

- `N=300`：主矩阵三轮全部通过、采集开销可接受、资源/PSI/reclaim/cleanup 正常后，只执行一轮探索；通过后再决定是否补足三轮。
- `N=500`：只有 N=300 完整通过后才执行一轮探索；不自动重复或继续到 934/1000。
- 单轮扩展点只作为观测点，不给该点独立 CI；不得把它与主矩阵伪装成等重复设计。

#### 社区式累计扩展（用户另行授权）

为直接复核社区 create-only顺序效应，另开唯一 run执行 `same-run N=0 -> 100 -> 300 -> 500 -> 1000`，create固定 c50，tier之间不删除前一 cohort。每个 tier仍须满足完整 denominator、Guest probe、固定 settle、多点内存采样、Template fingerprint、服务/资源/回收/文件系统门禁；任一失败即停止后续 POST并只清理该 run全部 owned ID。这个扩展不取消原计划的“不自动冲击1000”，而是用户在看到独立轮结果后对这一条独立协议的明确授权。

当前执行只形成累计 N=0和N=100：R2的 N=100 tier成功；N=300前根分区/Redis故障触发停止，N=300/500/1000均未提交。恢复后必须开新 run从 N=0重新开始，不能接续旧 cohort或重试旧 DELETE。

### 7.3 成功与 readiness

正式点必须同时满足：

```text
requested == HTTP success == returned unique ID == API running
          == probe success == exact shim/task/VMM/cgroup association == target N
```

任一 create 失败、超时或对象缺失：停止创建，不重试该请求，不补齐到目标，不形成正式密度点；进入本轮 owned-ID 精确清理。

### 7.4 每点采集

必须保留：

- before/pre-create、create peak、settled window、pre-delete、after-delete、cooldown 通过/超时。
- Host 全量样本和每个服务组件样本。
- 每个 Sandbox 的 shim/VMM/virtiofsd PSS/USS/RSS 分布。
- 每个 Sandbox cgroup的 current/peak/anon/file/kernel/pagetables/slab/events/io。
- 同一 Snapshot memory mapping 的 mapping PSS/USS/Shared/Private，按 dev/inode 去重。
- VMM minor/major faults、Host pgfault/pgmajfault、disk read/write 和 NUMA residency。
- create requested/success/failed denominator、whole-round wall、throughput；这些字段与 90 秒内存窗口分开。

## 8. 统计、回归和公式

### 8.1 分位数

所有分布使用 nearest-rank：

```text
k = ceil(n * p / 100) - 1
percentile = sorted_values[clamp(k, 0, n-1)]
```

同时输出 `n/min/P50/median/P95/max`。当 n 很小、P95 等于 max 时明确标注。

### 8.2 每点主值

每个 tier 的 settled 主值使用 90 秒窗口内各 timestamp 的 median；先在同 timestamp 聚合进程，再跨 timestamp 求 median，避免进程数量给某些时刻额外权重。

```text
host_available_delta(N,r)
  = median(MemAvailable_pre_N0,r) - median(MemAvailable_settled,N,r)

host_available_amortized(N,r)
  = host_available_delta(N,r) / N

tracked_pss(N,r,t)
  = sum(PSS_fixed_components) + sum(PSS_worker_sandbox_processes)

tracked_uss(N,r,t)
  = sum(USS_nonhugetlb_fixed_components) + sum(USS_nonhugetlb_worker_processes)

sandbox_cgroup_total(N,r,t)
  = sum(memory.current of exact worker Sandbox cgroups)
```

`host_available_amortized` 只称整机 `MemAvailable` 摊销。

### 8.3 固定截距和边际斜率

分别拟合，不跨视角混合：

```text
tracked_pss(N)          = alpha_pss + beta_pss * N + error
tracked_uss(N)          = alpha_uss + beta_uss * N + error
service_pss(N)          = alpha_service + beta_service * N + error
sandbox_cgroup_total(N) = alpha_cgroup + beta_cgroup * N + error
host_used_available(N)  = alpha_host + beta_host * N + error
snapshot_mapping_pss(N) = alpha_snapshot + beta_snapshot * N + error
```

- `alpha_pss/alpha_uss` 可与 N=0 直接固定组件基线比较。
- `beta_service` 表示控制面随实例增长的边际，不应被塞进固定项。
- `alpha_host` 包含整个 Host 的非 CubeSandbox 基线，不能称平台固定开销。
- `beta_*` 只适用于观测区间，不外推。

### 8.4 回归与不确定性

`regression_ci.py` 使用 Python 标准库并记录固定 seed：

1. OLS：输出 slope/intercept、R²、每点 residual。
2. Theil-Sen：所有有效点对 slope 的 median，intercept 为 `median(y-beta*x)`，用于稳健对照。
3. cluster bootstrap：以“整轮”为重采样单元，10,000 次，输出 slope/intercept 2.5%/97.5% percentile CI；不把同一轮 90 秒内的自相关 timestamp 当独立重复。
4. 同时输出每点 `delta/N` 和相邻密度边际 `(Y_i-Y_j)/(N_i-N_j)`。
5. 若残差呈系统形态、OLS 与 Theil-Sen明显分离或相邻 slope 改变，报告非线性，不用高 R² 掩盖。

扩展点只有一轮时不参与“平衡主矩阵”CI 的主结果；可另做含扩展点的敏感性拟合并标注不等重复。

### 8.5 共享/独占派生

```text
per_sandbox_pss_distribution = distribution(sum PSS of roles for each sandbox)
per_sandbox_uss_distribution = distribution(sum USS of roles for each sandbox)

snapshot_shared_indication
  = sum(snapshot_mapping_PSS) - sum(snapshot_mapping_USS_nonhugetlb)
```

最后一项只称“按 PSS/USS 的共享指示量”，不称唯一物理共享页总量。Snapshot mapping 的 `Shared_*` 和 cgroup file charge同时列出，解释 charge 与 PSS差异。

### 8.6 平行视角差异

保存但不武断归因：

```text
gap_pss = host_available_delta - delta(tracked_pss)
gap_cgroup = host_available_delta - delta(fixed_unit_cgroups + sandbox_cgroups)
```

这些是不同语义量的“诊断差”，不是可加性 residual。解释时依次查：

- Host AnonPages/Mapped/Shmem/Cached/Slab/PageTables/KernelStack 的同窗变化。
- cgroup anon/file/kernel 及其子项。
- process Pss_Anon/File/Shmem、Snapshot mapping、faults。
- disk read/write、workingset refault、reclaim/PSI、NUMA迁移。
- control service随 N 增长、containerd/Docker通用服务漂移。
- 采样误差、异步回收和 `MemAvailable` reclaim heuristic。

证据不足则结论为 `unknown`。

## 9. G2/G3 停止和升级门禁

### 9.1 G2：自然冷却

连续 5 个、间隔 2 秒的样本同时满足：

```text
threads <= 8000
load1 <= 5
procs_blocked == 0
Dirty <= 16384 KiB
Writeback == 0
memory PSI some/full avg10 未出现非零压力趋势
io PSI 无持续压力
```

另外必须满足：

- `oom_kill`、allocstall/reclaim 异常、cgroup `oom/oom_kill/max` 不增长。
- 服务 active、failed units为空、node Healthy/RUNNING、endpoint正常。
- owned Sandbox/Snapshot/shim/task/VMM/virtiofsd/TAP/cgroup全部回到 before集合。

最长等待 600 秒。超时停止后续档位；保存完整冷却曲线，不提高阈值，不 kill kworker。

#### `<test-host>` 经用户授权的 control-envelope 门禁

`<test-host>` 不使用上述为 `<original-target-host>` 定义的绝对数值。替代过程是：

1. 在资源为零、服务健康、无并发 activity、boot/hash固定时，纯只读采 10 分钟 N=0；Host 2 秒一个样本，组件 15 秒一个样本。
2. 若该窗口内 `oom_kill/pswpin/pswpout/allocstall*` 增长、资源非零、boot/hash漂移或服务失败，则 control envelope 无效，不创建 Sandbox。
3. 对 `threads/load1/procs_blocked/Dirty/Writeback` 分别保存 min/P50/P95/max；preflight和 cleanup必须连续 5 个样本不超过各自 N=0 observed max。**不在 max 上增加 margin。**
4. density run 前后 `oom_kill/pswpin/pswpout/allocstall*` 必须零增量；否则该 run失败并停止升级。
5. `<test-host>` 没有 PSI，因此以 vmstat critical counter、blocked、Dirty/Writeback、服务健康和资源回零替代；缺 PSI 明确写入报告，不声称验证了 PSI。

这只是适配 `<test-host>` 固有控制面负载的实验包络，不构成提高或废除 `<original-target-host>` 的 `threads<=8000` 门禁。

### 9.2 G3：单步失败

任一项立即停止升级：

- boot、kernel、组件 hash/PID start、unit start、Template/fingerprint漂移。
- 其他操作者或 worker 活跃。
- 任何 create/readiness/probe/采样请求失败或目标数不相等。
- resource pool/TAP/cgroup/no more resource 错误。
- memory/IO PSI、reclaim、swap、OOM、服务异常。
- `/` 可用空间低于10 GiB、任一目标文件系统空间/inode耗尽、Redis/MySQL等状态存储 persistence或health异常。
- 采集器耗时/CPU/IO 已足以干扰测试。
- cleanup 不归零或冷却超时。

失败不重试、不补请求、不进入更高密度。

## 10. 精确所有权与清理

### 10.1 所有权日志

- API 一旦返回 Sandbox ID，立即 append 到本 run 的 append-only owned ledger，先落证据再继续。
- ledger 记录 `run_label/round/density/seq/id/create_status/create_monotonic_ns`。
- metadata label 与 ledger 双重验证；label 缺失不自动放弃已记录 ID，但必须标记异常并停止创建。
- before 集合中的任何 ID 永远不进入 delete 列表。

### 10.2 删除规则

1. 只遍历 owned ledger 中本 tier 的精确 ID。
2. 每个 ID 最多发送一次 DELETE；记录 HTTP status/body 摘要/monotonic duration。
3. DELETE 失败不重试，不扩大到进程 kill、目录删除或全量 cleanup。
4. 只读轮询 API、shim/task/VMM/virtiofsd/TAP/cgroup 回收。
5. cleanup 集合必须回到该 tier 的 before manifest，而不只是“数量为 0”。
6. 发现未知残留立即停止并报告；不接管。

### 10.3 回收指标

分别记录：

- `t_delete_start`、最后一个 DELETE response、API集合归零、进程归零、TAP归还、cgroup归还、Host control envelope恢复、G2通过。
- before/peak/settled/after-cleanup 的 PSS/USS/cgroup/Host差值。
- `kvm-irqfd-cleanup` 和 threads 的自然峰值、阶跃回落与门禁时间。

“回收完成”要求对象集合归零和健康门禁通过；单独 `MemAvailable` 回升不够。

## 11. 可选 running/paused/clone 扩展

只有 running 主矩阵和清理完全完成后才考虑，且必须重新核验部署语义。

### 11.1 running -> paused

- 只使用本 worker 小规模 `N=1`，必要时 `N=10`。
- 先证明远端部署 Pause 是 legacy pausevm 还是当前 PauseCow；旧报告不能代替当前日志/实体。
- 同一批 ID 比较 running/paused 的逻辑状态、shim/VMM/task/TAP/cgroup、Snapshot/CubeCow/pausevm实体、PSS/USS/file/kernel和 Host变化。
- Pause后若标准删除语义不明确或曾失败，停止，不尝试旁路清理。

### 11.2 clone/shared base

- 只在 Snapshot worker 方法与当前部署行为已确认后，小规模 `source=1, clones=1/10`。
- 固定同一 Snapshot base dev/inode，测每个 VMM mapping PSS/USS 与 cgroup file/anon。
- 不扩展为高并发 Clone，也不把 running 密度与 clone 密度混为一条回归。

## 12. Evidence 目录、脱敏与 raw-to-derived lineage

远端 G0/G1 通过后才创建唯一目录：

```text
<local-evidence-root>/
  README.md
  run-context.json
  commands/
  raw/
    phase-a/
    n0/
    density/<round>/<N>/
  sanitized/
  memory-samples.csv
  process-map.csv
  cgroup-memory.csv
  per-sandbox-distribution.json
  density-trend.json
  regression_ci.py
  validate_evidence.py
  secret-scan.txt
  SHA256SUMS
```

### 12.1 raw-to-derived

每个 derived 字段必须在 `density-trend.json` 中记录：

```text
metric name
source files + source columns
filter (run/round/density/phase)
unit conversion
aggregation order
percentile/regression algorithm
script SHA-256
```

`per-sandbox-distribution.json` 保留每个 Sandbox 的精确角色和 sample count，但公开报告可缩写 ID；本地 evidence 保留完整 ID用于复核。

### 12.2 脱敏

- 不采集 systemd Environment、`/proc/<pid>/environ`、shell history、认证 header 或 secret 文件。
- cmdline、Template JSON、日志和 URL 机械替换 token/API key/password/cookie/signature/credential。
- raw 若意外含 secret，先隔离并只保留脱敏副本进入 manifest；回复中不输出 secret，提醒轮换。
- `secret-scan.txt` 为最终 manifest 前置条件。

### 12.3 验证

`validate_evidence.py` 至少断言：

- boot/hash/Template identity 全程一致。
- requested/success/running/associated denominator 一致。
- 每个 process row 的 PID/start ticks一致且映射唯一。
- cgroup path/inode 与 Sandbox assignment 一致。
- CSV row 数、单位、空值和 phase完整。
- owned ledger 与 delete ledger 一一对应；无 before ID 被删除。
- final resource集合等于 before manifest。
- JSON 可解析、CSV列固定、所有 derived可从 raw重算。
- `git diff --check`、secret scan 通过后生成 `SHA256SUMS`。

## 13. 报告结构与验收

最终 `SANDBOX_MEMORY_FOOTPRINT_REPORT.zh-CN.md` 开头直接给：

1. 当前环境的 CubeSandbox 固定组件 PSS/USS/cgroup开销和 N=0噪声。
2. 主矩阵观测范围内每实例 PSS/USS/cgroup/Host `MemAvailable` 边际 slope、95% CI、R²和稳健 slope。
3. 各 N 的 `delta/N`、per-Sandbox P50/P95/min/max，以及是否非线性。
4. Snapshot base mapping 的 PSS/USS/shared/private与 cgroup file/anon对照。
5. before/peak/settled/after-cleanup 和自然回收时间。

正文继续包含：

- 完整 Host/kernel/组件/Template/endpoint/XFS/NUMA/cgroup identity。
- 每个密度点、每轮原始主值和 denominator。
- 公式、百分位算法、bootstrap seed/CI、residual。
- 平台固定、实例独占、共享 base/page-cache、内核附加、Host总变化分别报告。
- MemAvailable/PSS/USS/cgroup不闭合的证据与 unknown。
- 所有失败 attempt、停止点、cleanup和不可回答项。
- 最大正式观测 N；不外推到更高密度。
- evidence目录、脚本、SHA256和复现命令。

### 13.1 用户验收主表

报告必须先给两张可直接决策的主表，不能只给回归图或总量：

1. `N=0/1/10/50/100[/300/500] × component`：CubeMaster、Cubelet、CubeAPI、network-agent、containerd、Docker daemon及管理容器各自的 PSS、USS、unit/container cgroup current；每个数字带正式轮数和 min/max。
2. `N=1/10/50/100[/300/500] × Sandbox`：每 Sandbox PSS/USS/cgroup 的 P50/P95/min/max、Snapshot mapping PSS/USS，以及整机 `MemAvailable` delta/N。

同一 N 的组件表与 Sandbox表必须来自相同 boot/hash/Template和 settled窗口；N=0 单独显示固定开销与自然噪声。缺失密度点明确写 `未测/门禁阻塞`，不得用回归外推填表。

## 14. 当前下一步

当前唯一安全下一步是由现场管理员处理 `<test-host>` 的宿主存储和 Redis；本 worker不删除宿主文件、不修改Redis配置、不restart服务，也不重试旧100个 DELETE。恢复的必要条件：

1. `/` 可用空间不少于10 GiB且inode正常，并说明空间耗尽原因已消除。
2. Redis容器health和RDB/AOF persistence恢复；由管理员核对可能的 Sandbox proxy-map残留与Master/Cubelet/API空集一致。
3. 重新检查 Orca与远端操作者，重新执行完整 Phase A/G0/G1/G2；不能继承旧boot/hash/Template/health。
4. 若资源非零、身份不明、存在并发操作者或任一服务/存储异常，停止并报告。
5. 全部门禁通过后，也必须用新的唯一 run label从same-run N=0重新开始；不得接续 R2、复用旧 cohort或重试旧 DELETE。

`<original-target-host>` 路径仍需等待SSH恢复并完整重新核验；`<test-host>` 的6.6.0数据不得表述为`<original-target-host>/6.6.119`结论。

本计划本身不授权任何远端状态修改。
