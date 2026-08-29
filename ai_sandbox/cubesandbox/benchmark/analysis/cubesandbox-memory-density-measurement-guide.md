# CubeSandbox 单机密度内存测量指南

## 目标

本指南回答三个问题：平台 N=0 固定成本是多少、每个 Sandbox 的独占与共享成本是多少、整机可用内存为何随密度变化。

它修正只看 `free -h` 单点的归因局限，但保留社区报告的累计密度视角用于描述性对照。

## 1. 结论口径先固定

必须分开报告：

1. CubeMaster、Cubelet、CubeAPI、network-agent 等固定组件；
2. 每 Sandbox 的 CubeShim/VMM PSS与USS；
3. Sandbox cgroup 的 anon/file/kernel；
4. Snapshot memory mapping 的共享与私有部分；
5. `MemAvailable` 整机差值；
6. 清理后的回收和未闭合项。

禁止把 PSS、cgroup和 `MemAvailable` 相加成一个“总内存”。

## 2. Phase A：身份与互斥

任何创建前先保存：

- hostname、boot ID、uname、kernel config/hash；
- CPU、NUMA、THP、HugePages、swap、PSI；
- XFS mount、reflink、quota、空间与 inode；
- 组件 disk/proc exe SHA-256、PID/start ticks、systemd unit；
- Template ID、CPU/memory、replica、fingerprint、memory/rootfs实体；
- endpoint、node Ready、failed units；
- Sandbox/Snapshot/shim/task/VMM/TAP/cgroup集合；
- 登录会话和 benchmark/trace/build活动。

现场非零、身份漂移或存在其他操作者时停止，不接管资源。

## 3. 内存对象模型

### 3.1 Host 全局

至少采集：

```text
MemTotal MemFree MemAvailable Active Inactive
AnonPages Mapped Cached Shmem
Slab SReclaimable SUnreclaim
PageTables SecPageTables KernelStack
Dirty Writeback
```

同时采 `/proc/vmstat`、PSI、NUMA node meminfo/numastat、diskstats、sockstat和选定 slab。

### 3.2 固定组件

对 CubeMaster、Cubelet、CubeAPI、network-agent、containerd和管理容器记录：

- `/proc/PID/smaps_rollup`；
- `/proc/PID/status`；
- `/proc/PID/stat` 的 fault/start ticks；
- systemd/container cgroup memory与分项；
- PID、exe、hash和cgroup path/inode。

### 3.3 动态 Sandbox

使用精确 Sandbox ID 建立：

```text
Sandbox ID -> CubeShim/VMM PID -> cgroup -> TAP
           -> rootfs -> Snapshot memory dev/inode
```

不能只按进程名计数，也不能把 PID复用后的样本拼接。

## 4. N=0 控制包络

先确认 Sandbox/Snapshot/shim/task/VMM/TAP为零，再连续采 5–10 分钟。

推荐频率：Host每2秒、组件 PSS/USS和cgroup每15秒。

输出每项的 median、min/max、P5/P95和MAD。保存 boot/hash/PID start前后不变证据。

N=0 同时给出自然 load、blocked、Dirty/Writeback、fault/reclaim和组件 allocator漂移。

## 5. 密度点与时序

推荐主矩阵：`N=1、10、50、100`。只有全部门禁通过，才考虑 300和500。

每个 tier 从确认的 N=0 独立开始：

```text
pre-create 30s
  -> 创建并登记全部ID
  -> requested=success=running=target
  -> settle 30s
  -> settled window 90s
  -> 单次精确DELETE
  -> cleanup/cooldown回到control envelope
```

Host sampler从创建前持续到 cleanup结束。settled窗口内至少做3个全 Sandbox深样本。

关键密度至少3轮。交错顺序以分离密度与cache/年龄效应：

| 轮次 | 顺序 |
|---|---|
| R1 | 1→10→50→100 |
| R2 | 100→50→10→1 |
| R3 | 10→1→100→50 |

不执行 `drop_caches`。记录冷/热顺序，而不是修改系统制造“同样缓存”。

## 6. 每个深样本

### 6.1 进程

从 `smaps_rollup` 保存：

```text
Rss Pss Pss_Anon Pss_File Pss_Shmem
Shared_Clean Shared_Dirty
Private_Clean Private_Dirty
Anonymous Swap SwapPss
```

定义：

```text
USS_nonhugetlb = Private_Clean + Private_Dirty
```

`Private_Hugetlb` 若存在则单列。

### 6.2 Snapshot mapping

从 `/proc/PID/smaps` 按 pathname、dev和inode筛选同一 Snapshot memory。

分别汇总 mapping RSS、PSS、Private、Shared和Anonymous。

这一步直接验证共享 base 是否存在，不能用进程总 RSS替代。

### 6.3 cgroup

cgroup v2保存：

```text
memory.current memory.peak memory.stat memory.events
anon file kernel kernel_stack pagetables sec_pagetables slab_*
```

cgroup v1保存 usage、max_usage、failcnt和 `memory.stat`。

明确标注 v1 first-touch charge和 usage fuzz，禁止把单个 cgroup cache当PSS公平份额。

## 7. 统计公式

### 7.1 社区兼容口径

```text
Host摊销(N,r)
  = [median(MemAvailable_pre) - median(MemAvailable_settled)] / N
```

只能称“整机 `MemAvailable` 摊销”。

### 7.2 每实例分布

每个 Sandbox先聚合其全部动态角色，再计算：

```text
PSS_per_sandbox
USS_per_sandbox
cgroup_current_per_sandbox
Snapshot_mapping_PSS_per_sandbox
```

输出 `n/min/P50/median/P95/max`。分位数应说明算法。

### 7.3 固定截距与边际斜率

分别拟合：

```text
tracked_PSS(N) = alpha_PSS + beta_PSS*N + error
tracked_USS(N) = alpha_USS + beta_USS*N + error
cgroup_total(N) = alpha_cgroup + beta_cgroup*N + error
Host_delta(N) = alpha_host + beta_host*N + error
```

`alpha_host` 包含整个 Host，不称平台固定成本。

同时输出 OLS、R²、residual、Theil-Sen和按整轮重采样的bootstrap CI。

保留每点 `delta/N` 和相邻点边际斜率，检查非线性。

## 8. 判因矩阵

| 观测组合 | 优先解释 |
|---|---|
| Snapshot `Pss_File/N`下降，USS/anon上升 | CoW正常，Guest私有写页盖过共享收益 |
| PSS/USS稳定，Cached/slab/page table上升 | rootfs/cache或内核附加成本 |
| Sandbox分项稳定，组件PSS上升 | 控制面/运行时状态增长 |
| 分项稳定，只有MemAvailable漂移 | Host噪声、回收估计或未覆盖内核项 |
| 高密度出现PSI/allocstall/pgscan突变 | 进入压力状态，停止简单外推 |
| cleanup后对象归零但cache未回落 | 自然cache/charge残留，不称泄漏 |

任何解释都应有同窗证据。时间相邻不是因果证明。

## 9. 停止条件

任一项发生即停止升级：

- boot、hash、Template或PID start漂移；
- 外部worker/登录会话开始操作；
- create、readiness、probe或denominator失败；
- OOM、swap、allocstall、持续PSI或服务异常；
- cleanup没有回到before集合；
- cooldown超时；
- 采集器自身耗时足以干扰被测窗口。

失败不重试、不补请求、不提高门禁。

## 10. 精确清理

API一旦返回ID，立即写入并fsync owned ledger。

每个ID最多发送一次DELETE。失败后不扩大到进程kill、目录删除或全量清理。

cleanup按集合比较：Sandbox、Snapshot、shim、task、VMM、TAP、cgroup都必须回到before集合。

`MemAvailable`回升不是清理完成的充分条件。

## 11. Evidence 结构

```text
evidence-root/
  run-context.json
  phase-a/
  n0/
  density/<round>/<N>/
  memory-samples.csv
  process-map.csv
  cgroup-memory.csv
  component-density.csv
  per-sandbox-distribution.json
  density-trend.json
  secret-scan.txt
  SHA256SUMS
```

每个derived字段应记录 source file、filter、单位转换、聚合顺序和脚本hash。

公开文档只引用脱敏后的字段和占位 evidence root，不发布内部IP、token、绝对路径或认证信息。

## 12. 报告最小主表

主表一：`N × component`，列 CubeMaster、Cubelet、CubeAPI、network-agent、containerd和管理容器的 PSS、USS、cgroup current。

主表二：`N × Sandbox`，列每实例 PSS/USS/cgroup的 P50/P95/min/max、Snapshot mapping和Host摊销。

缺失密度点明确写“未测/门禁停止”，不得用回归外推填表。

## 参考资料

- [社区单机密度内存表审计](community-density-memory-report-audit.md)
- [CubeSandbox CoW 与宿主机内存记账模型](cubesandbox-cow-memory-accounting-model.md)
- [Linux PSI](https://docs.kernel.org/accounting/psi.html)
- [Linux cgroup v1 memory](https://docs.kernel.org/6.6/admin-guide/cgroup-v1/memory.html)
- [Linux cgroup v2 memory](https://docs.kernel.org/6.6/admin-guide/cgroup-v2.html#memory-interface-files)
