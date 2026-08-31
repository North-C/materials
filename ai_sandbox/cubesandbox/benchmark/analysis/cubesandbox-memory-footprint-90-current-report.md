# CubeSandbox `.90` 宿主机内存开销正式报告

## 0. 结论先行

本轮在当前`.90` custom 6.6.0环境完成了同一run累计 `N=0→100→300→500→1000` 全套测量：1000/1000 Sandbox创建、1000/1000 Guest probe、1000/1000单次DELETE全部成功；最终Sandbox/CubeShim/VMM/TAP归零，冻结的8个既有Snapshot逐项不变，OOM/swap/reclaim/allocstall全零增量。

测试身份：

- Host：`<test-host>`；boot ID：`<runtime-id>`。
- kernel：`6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2`；用户明确接受为本轮正式身份。
- Template：`<template-id>`，READY、本地replica、`cpu=2000m,mem=2000Mi`；fingerprint `c884bd9cd8cfa1cf378163743b3234c64531e43d1cd1728757ade80d7a605c64`。
- API：`http://127.0.0.1:3000`；Cubelet内嵌containerd socket：`/data/cubelet/cubelet.sock`。
- cgroup v1、无PSI；PSS/USS、cgroup charge和`MemAvailable`是平行视角，未相加。

### 0.1 每Sandbox与整机主结果

单位MiB。PSS/USS/cgroup列依次为`min/P50/P95/max`；Host列是同一run N=0中位数与各settled窗口中位数之差再除以N。

| N | Sandbox PSS | Sandbox USS | Snapshot mapping PSS | Snapshot mapping USS | cgroup current | Host `MemAvailable`摊销 |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 26.354/27.085/27.750/28.428 | 25.105/25.848/26.516/27.188 | 22.579/22.955/23.581/24.095 | 21.641/22.027/22.656/23.152 | 15.039/16.234/17.328/21.203 | 31.038 |
| 300 | 26.019/26.901/28.141/28.712 | 25.605/26.484/27.727/28.301 | 22.252/22.981/24.235/24.718 | 21.941/22.668/23.922/24.422 | 15.102/16.469/17.969/22.195 | 30.242 |
| 500 | 25.855/27.378/28.811/30.140 | 25.605/27.129/28.562/29.902 | 22.123/23.504/24.937/26.224 | 21.934/23.316/24.750/26.047 | 15.266/16.898/18.625/22.852 | 31.354 |
| 1000 | 26.354/27.710/29.194/31.781 | 26.230/27.586/29.070/31.660 | 22.551/23.897/25.366/27.829 | 22.457/23.805/25.273/27.738 | 14.047/17.402/19.113/23.016 | 32.511 |

2,000 MiB Guest配置内存不是Host resident。N=1000时每Sandbox PSS P50约27.71 MiB、USS P50约27.59 MiB。

### 0.2 核心组件内存

每格为`PSS/USS/cgroup current`，单位MiB；值来自同一density settled窗口的中位数。system `containerd.service`在本部署中inactive，Cubelet内嵌containerd，因此不列为固定进程。

| N | CubeMaster | Cubelet | CubeAPI | network-agent | Docker daemon |
|---:|---:|---:|---:|---:|---:|
| 0 | 118.961/118.961/371.711 | 171.425/171.340/—* | 8.191/8.191/9.605 | 130.833/130.785/138.500 | 411.004/411.004/757.734 |
| 100 | 123.695/123.695/405.973 | 261.757/261.738/—* | 12.789/12.789/13.719 | 126.595/126.578/138.949 | 411.004/411.004/752.207 |
| 300 | 121.613/121.613/573.246 | 392.355/392.344/—* | 9.836/9.836/11.602 | 118.597/118.586/139.258 | 411.004/411.004/741.078 |
| 500 | 133.309/133.309/1150.617 | 534.460/534.449/—* | 10.098/10.098/11.352 | 118.283/118.273/137.465 | 411.012/411.012/742.656 |
| 1000 | 179.828/179.828/3151.156 | 896.071/896.062/—* | 10.035/10.035/11.707 | 120.993/120.984/152.262 | 411.016/411.016/739.387 |

`*` Cubelet的历史cgroup值不可用。采集器当时使用systemd `ControlGroup=/system.slice/cube-sandbox-cubelet.service`，但cgroup v1下Cubelet进程真实memory controller路径是`/cube_sandbox/cubelet`；表中原先重复出现的69.648 MiB来自错误层级，不能称为Cubelet charge。历史raw没有读取真实路径，无法事后补算；PSS/USS取自`/proc/<pid>/smaps_rollup`，不受此问题影响。CubeMaster cgroup在N=1000达到约3.08 GiB，但进程PSS仅179.8 MiB，同样说明cgroup charge不能直接称为主进程resident。

### 0.3 Cubelet为什么随Sandbox数量大幅增长

这是**已观测到的Cubelet进程私有匿名内存增长**，不是Snapshot共享文件页被重复计入。下表是每个density的3个settled深样本中位数，单位MiB（fault与线程除外）：

| N | PSS | Pss_Anon | Pss_File | Pss_Shmem | Private_Dirty | AnonHugePages | Threads | 累计minor fault |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 171.425 | 112.871 | 56.956 | 1.598 | 114.469 | 106 | 40 | 131745 |
| 100 | 261.757 | 199.633 | 56.886 | 5.238 | 204.871 | 170 | 79 | 138679 |
| 300 | 392.355 | 323.812 | 56.879 | 11.664 | 335.477 | 236 | 79 | 180822 |
| 500 | 534.460 | 459.703 | 56.878 | 17.879 | 477.582 | 274 | 84 | 350376 |
| 1000 | 896.071 | 805.645 | 56.876 | 33.551 | 839.195 | 474 | 84 | 875529 |

N=0→1000的Cubelet PSS增加724.646 MiB，即端点摊销约0.725 MiB/Sandbox；五点OLS斜率为0.716 MiB/Sandbox，R²=0.999407。其中`Pss_Anon`增加692.773 MiB、`Pss_Shmem`增加31.953 MiB，`Pss_File`反而减少0.080 MiB；`Private_Dirty`增加724.727 MiB，几乎与全部PSS增量一一对应。线程只从40增至84且N=300后基本稳定，所以不能用OS线程栈解释持续增长；`AnonHugePages`从106增至474 MiB，证明大量增长位于THP支持的匿名映射，但没有heap profile时不能仅凭该字段把每一页都命名为Go heap。全程major fault保持4、无swap/OOM/reclaim，因此也不是内存压力或换页造成的异常膨胀。

当前源码给出了与现象一致的所有权机制：Cubelet进程内嵌containerd server（`Cubelet/services/server/server.go:98-105`），并在内存`cache.Indexer`中保存每个Sandbox的`CubeBox`及template/container/block/image多组索引（`Cubelet/pkg/store/cubebox/store.go:24-115`）。每个`CubeBox`包含container map、端口、cgroup、NUMA/queue、runtime endpoint、PodConfig、virtiofs、volume、网络、hotplug、status、local template、image reference、metrics baseline等动态对象（`Cubelet/pkg/store/cubebox/cubebox.go:109-170`）；删除时数据库和indexer条目一并移除（`Cubelet/pkg/store/cubebox/store.go:260-268`）。因此最稳妥的归因是：**Cubelet/内嵌containerd为存活Sandbox保留的每实例控制面状态、索引及其allocator容量，形成约0.725 MiB/实例的私有匿名边际。**

源码边界：本worktree `HEAD=09274501dd12e47dbed2dcc77d8eb67dd661d49c`，现场Cubelet二进制SHA-256为`c58499fd90b46fd370e94aa106fab15803e1be1b22595469881864c84e0417c2`；当前源码能证明结构性所有权和释放路径，但没有逐字节证明现场二进制中具体Go对象的占比。要再拆到对象/调用栈级别需要heap profile；本轮按“不修改、不启停服务”的边界未开启profiling。

## 1. 为什么均摊内存会增长而不违反CoW

本轮确实观察到整机摊销在N=300后上升：`30.242→31.354→32.511 MiB/实例`。这不表示CoW失效。

共享收益可由`PSS-USS`观察：

| N | PSS P50 | USS P50 | 共享分摊差值 |
|---:|---:|---:|---:|
| 100 | 27.085 | 25.848 | 1.237 |
| 300 | 26.901 | 26.484 | 0.417 |
| 500 | 27.378 | 27.129 | 0.249 |
| 1000 | 27.710 | 27.586 | 0.124 |

共享页在单实例PSS中的分摊从约1.24 MiB降到0.12 MiB，符合共享者越多、单实例分摊越小的预期。但同时：

- Snapshot mapping USS P50从22.027增至23.805 MiB，增加约1.78 MiB；更老的累计cohort继续触页和写时复制，私有页增长超过共享摊薄收益。
- Host `AnonPages`每实例从28.041增至28.756 MiB。
- Host `Cached`每实例从0.831增至3.250 MiB，说明累计创建顺序和文件/page cache materialization显著增长。
- PageTables约0.85、SecPageTables约0.56、KernelStack约0.33、Slab约0.73→0.82 MiB/实例，这些内核项不受Snapshot memory共享消除。
- CubeMaster/Cubelet保存的动态状态也随N增长，进入Host差值却不是Sandbox VMM RSS。

因此，CoW只保证仍共享的只读base页按映射者摊薄，不保证`(MemAvailable_N0-MemAvailable_N)/N`单调下降。

## 2. Host变化与边际趋势

Host分项单位为MiB/实例：

| N | AnonPages | Cached | PageTables | SecPageTables | KernelStack | Slab |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 28.041 | 0.831 | 0.857 | 0.558 | 0.333 | 0.727 |
| 300 | 27.924 | 1.151 | 0.852 | 0.561 | 0.331 | 0.752 |
| 500 | 28.359 | 2.033 | 0.853 | 0.555 | 0.330 | 0.788 |
| 1000 | 28.756 | 3.250 | 0.855 | 0.560 | 0.329 | 0.821 |

相邻新增批次的`MemAvailable`边际损失：

| 区间 | MiB/新增Sandbox |
|---|---:|
| 0→100 | 31.038 |
| 100→300 | 29.844 |
| 300→500 | 33.022 |
| 500→1000 | 33.669 |

对五个完整点 `(N, HostDelta_KiB)`做描述性OLS：

- slope：33,334.588 KiB/实例，即32.553 MiB/实例；
- intercept：-304,471.146 KiB；
- R²：0.999364；
- Theil-Sen slope：32,739.386 KiB/实例，即31.972 MiB/实例。

当前只有一条累计序列，没有run-level重复，因此**没有可解释为重复性不确定度的正式95% CI**。派生JSON保留点重采样bootstrap，但明确标为探索性，不能冒充run-level置信区间。

## 3. 全部组件PSS

单位MiB。systemd wrapper和其管理容器分别列示；完整USS和cgroup值见`community-cumulative-components.csv`。

| 组件 | N0 | N100 | N300 | N500 | N1000 |
|---|---:|---:|---:|---:|---:|
| cube-sandbox-cubemaster.service | 118.961 | 123.695 | 121.613 | 133.309 | 179.828 |
| cube-sandbox-cubelet.service | 171.425 | 261.757 | 392.355 | 534.460 | 896.071 |
| cube-sandbox-cube-api.service | 8.191 | 12.789 | 9.836 | 10.098 | 10.035 |
| cube-sandbox-network-agent.service | 130.833 | 126.595 | 118.597 | 118.283 | 120.993 |
| cube-sandbox-coredns.service | 30.896 | 30.896 | 30.896 | 30.896 | 30.404 |
| cube-sandbox-cube-egress.service | 29.502 | 29.533 | 29.693 | 29.443 | 29.631 |
| cube-sandbox-cube-lifecycle-manager.service | 0.811 | 0.774 | 0.768 | 0.767 | 0.765 |
| cube-sandbox-cube-proxy.service | 0.838 | 0.802 | 0.795 | 0.794 | 0.792 |
| cube-sandbox-mysql.service | 0.806 | 0.771 | 0.764 | 0.763 | 0.761 |
| cube-sandbox-redis.service | 0.807 | 0.771 | 0.764 | 0.763 | 0.761 |
| cube-sandbox-webui.service | 0.803 | 0.767 | 0.760 | 0.759 | 0.757 |
| system containerd.service | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| docker.service | 411.004 | 411.004 | 411.004 | 411.012 | 411.016 |
| cube-egress | 7.600 | 7.600 | 7.600 | 7.600 | 7.600 |
| cube-proxy-coredns | 120.934 | 120.363 | 120.664 | 120.645 | 120.285 |
| cube-proxy | 3.316 | 3.316 | 3.316 | 3.316 | 3.316 |
| cube-sandbox-mysql | 449.426 | 492.305 | 499.621 | 504.539 | 511.562 |
| cube-webui | 1.260 | 1.260 | 1.260 | 1.260 | 1.260 |
| cube-lifecycle-manager | 29.801 | 31.836 | 30.879 | 29.742 | 31.277 |
| cube-sandbox-redis | 35.461 | 35.516 | 35.586 | 35.621 | 35.746 |

## 4. 环境与方法边界

| 对象 | 当前值 |
|---|---|
| hostname/boot | `master` / `<runtime-id>` |
| uname | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` |
| OS | openEuler 24.03 LTS-SP3 |
| cgroup/PSI | v1 / PSI不可用 |
| Host memory | 2,371,256,968 KiB |
| `/data/cubelet` | XFS约3.0 TiB，`reflink=1`、`noquota` |
| API/runtime | `127.0.0.1:3000` / `/data/cubelet/cubelet.sock` |
| Guest配置 | 2 vCPU / 2000 MiB，`prefault=false/shared=false/hugepages=false` |
| 固定Snapshot | 8个既有READY ID，测试前后集合精确相等 |

百分位使用nearest-rank：`sorted[ceil(n*p/100)-1]`。每个density有3个深样本；mapping分布来自中点full-smaps样本，PSS/USS/cgroup分布来自全部3个样本。

## 5. 成功分母、清理与停止门禁

| tier | 新增create | 累计running | 新增probe | settled | critical counters |
|---:|---:|---:|---:|---|---|
| 100 | 100/100 | 100 | 100/100 | 完成 | 全零增量 |
| 300 | 200/200 | 300 | 200/200 | 完成 | 全零增量 |
| 500 | 200/200 | 500 | 200/200 | 完成 | 全零增量 |
| 1000 | 500/500 | 1000 | 500/500 | 完成 | 全零增量 |

- 正式run wall：3,602.206秒。
- 1000次DELETE顺序执行，全部HTTP 204，耗时606.227秒；每个ID最多一次。
- 最后一个DELETE响应后，运行资源在首个cleanup样本即为空。
- threads和`kvm-irqfd-cleanup`自然回落；297.208秒后满足严格`threads≤8000, load≤5, blocked=0, Dirty≤16MiB, Writeback=0`并完成5连样。
- 最终Master/Cubelet/Sandbox/CubeShim/VMM/TAP/task/container为0；8个冻结Snapshot保持不变。
- 没有OOM、swap、direct/kswapd reclaim、allocstall、cgroup failcnt或服务异常。

烟测历史保留：R1旧门禁0创建中断；R2在正常8 KiB Writeback上失败后1次DELETE；R3因错误预期ctr task=target失败后1次DELETE；R4最终1/1 probe与清理成功。正式R5不删除或覆盖这些失败证据。

## 6. 指标观察命令

Host：

```bash
grep -E '^(MemTotal|MemAvailable|AnonPages|Cached|Mapped|Shmem|Slab|SReclaimable|SUnreclaim|PageTables|SecPageTables|KernelStack|Dirty|Writeback):' /proc/meminfo
grep -E '^(oom_kill|pswpin|pswpout|pgfault|pgmajfault|pgscan_|pgsteal_|allocstall)' /proc/vmstat
cat /proc/loadavg
grep '^procs_blocked ' /proc/stat
ps -eLo tid= | wc -l
```

组件/Sandbox进程：

```bash
systemctl show <unit> --no-pager -p MainPID -p ControlGroup -p MemoryCurrent -p TasksCurrent
cat /proc/<pid>/smaps_rollup
grep -E '^(VmRSS|RssAnon|RssFile|RssShmem|VmPTE|VmSwap|Threads):' /proc/<pid>/status
cat /proc/<pid>/stat
cat /proc/<pid>/numa_maps
```

```text
PSS_KiB = smaps_rollup:Pss
USS_nonhugetlb_KiB = Private_Clean + Private_Dirty
```

Snapshot mapping：从`/proc/<cube-shim-pid>/smaps`按冻结的Template memory pathname、dev和inode过滤，读取`Pss/Shared_*/Private_*/Anonymous`。

cgroup v1：

```bash
cat /proc/<pid>/cgroup
cat /sys/fs/cgroup/memory/<resolved-path>/memory.usage_in_bytes
cat /sys/fs/cgroup/memory/<resolved-path>/memory.max_usage_in_bytes
cat /sys/fs/cgroup/memory/<resolved-path>/memory.failcnt
cat /sys/fs/cgroup/memory/<resolved-path>/memory.stat
```

全量归属：

```bash
curl -fsS http://127.0.0.1:3000/health
/usr/local/services/cubetoolbox/CubeMaster/bin/cubemastercli list --all -q
/usr/local/services/cubetoolbox/Cubelet/bin/cubecli cubebox ls -a -q --no-trunc
ctr --address /data/cubelet/cubelet.sock -n cubens tasks ls -q
ctr --address /data/cubelet/cubelet.sock -n cubens containers ls -q
for p in /sys/class/net/z*/operstate; do [ "$(cat "$p")" = up ] && echo "$p"; done
```

## 7. Evidence与复算

Evidence root：`evidence/<run-label>/`。

- `n0-r1/`：独立600秒严格N=0，301个正式Host样本。
- `community-cumulative-r5/`：正式累计raw，1,787个Host样本、15个深样本、1000 owned/probe/delete ledger。
- `community-cumulative-r5-derived/community-cumulative.json`：Host点、Sandbox分布、回归和相邻边际。
- `community-cumulative-components.csv`：全部组件PSS/USS/cgroup；其中历史Cubelet cgroup列按erratum视为无效。
- `CUBELET_CGROUP_ERRATUM.zh-CN.md`：Cubelet cgroup v1路径纠错、正式raw和重启后只读复核边界。
- `validation.json`：denominator、冻结Snapshot、资源回零和secret scan校验。
- `SHA256SUMS`：最终完整性清单。

复算：

```bash
python3 <local-tools-root>/analyze.py --evidence-root <local-evidence-root>
python3 <local-tools-root>/analyze_cumulative.py \
  --run-dir <local-evidence-root>/community-cumulative-r5 \
  --output-root <local-evidence-root>/community-cumulative-r5-derived
```

未修改产品源码、kernel、sysctl、NUMA/THP/hugepage/swap/quota/绑核；未restart CubeSandbox服务；未commit/push。
