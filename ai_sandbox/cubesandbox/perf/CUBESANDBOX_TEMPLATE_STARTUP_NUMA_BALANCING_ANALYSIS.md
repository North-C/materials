# 一次被误认为磁盘 I/O 的 NUMA 页迁移：CubeSandbox Template 并发启动长尾分析

## 结论先行

在一台 4 NUMA、384 CPU 的 ARM64 服务器上，使用 3U2G Template 执行 `c50n500` 并发启动时，创建延迟会在实例积累到约 250 至 350 个后突然升高。

最初的异常表现是：vCPU 调度等待达到 400 至 500ms，主机 `iowait` 达到 42% 至 69%，同时有数百个线程处于 blocked 状态。这看起来很像磁盘拥塞，但磁盘并不忙。

进一步采样发现，大多数 blocked 线程都是 CubeSandbox 的 `vcpu0/1/2`，等待在 `migration_entry_wait_on_locked` 和 `folio_lock_killable`。

同一时间，NUMA hint fault 达到 76,812 次/s，成功迁移 59,443 pages/s，迁移失败 12,821 pages/s。关闭自动 NUMA balancing 后，blocked 从 548 降到 0，`iowait` 从 51.15% 降到 0.012%。

API 平均延迟下降 38.9%，P95 下降 67.7%，吞吐提高 59.6%。这说明主要问题不是 NVMe，也不是某一个 CubeShim 函数，而是 Guest vCPU 在访问迁移中的内存页时被阻塞。

## 1. 测试场景

本次实验固定使用同一个 READY Template：

| 项目 | 配置 |
|---|---|
| 节点 | ARM64，384 个逻辑 CPU，4 个 NUMA node |
| Template | 3U2G，openEuler Guest |
| 测试 | `c50n500`，50 并发，共 500 个正式请求 |
| 实例行为 | 创建后保留，测试结束统一清理 |
| Host NUMA balancing | `kernel.numa_balancing=1` |
| THP | `enabled=always` |
| VMM vCPU affinity | `None` |
| VMM memory zones | `None` |

`c50n500` 不只是 50 个 VM 同时恢复。已创建的 VM 会继续运行，因此实例数增长到 300 时，主机上已有约 900 个 Guest vCPU 线程，后续批次仍会继续增加。

这使测试同时具备两种压力：每一批有 50 个 VM 并发恢复，主机上的存量 vCPU 和内存映射又持续增长。

## 2. bpftrace 首先暴露了调度长尾

早期实验使用 `bpftrace` 监听 `sched_wakeup` 和 `sched_switch`，记录 vCPU 被唤醒后等待多久才真正获得 CPU。

核心采样逻辑如下：

```bpftrace
tracepoint:sched:sched_wakeup
/args->comm == "vcpu0" || args->comm == "vcpu1" || args->comm == "vcpu2"/ {
  @runnable_since[args->pid] = nsecs;
}

tracepoint:sched:sched_switch
/@runnable_since[args->next_pid]/ {
  $wait_us = (nsecs - @runnable_since[args->next_pid]) / 1000;
  @wait_sum_us = sum($wait_us);
  @wait_max_us = max($wait_us);
  delete(@runnable_since[args->next_pid]);
}
```

三轮结果都抓到了 400ms 以上的单次 vCPU runnable wait：

| 轮次 | vCPU wait Avg | 单次 Max | Max blocked | Max iowait |
|---|---:|---:|---:|---:|
| 1 | 47.2us | 500.2ms | 1242 | 69.14% |
| 2 | 59.8us | 428.7ms | 827 | 57.22% |
| 3 | 38.7us | 424.0ms | 1327 | 42.30% |

这里必须区分采样口径：`bpftrace` 采集的是 vCPU 调度等待；`iowait` 来自低频 Host sampler 对 `/proc/stat` 的读取。它们在同一压力窗口出现，但不能直接相加，也不能仅凭相关性判断根因。

而且 bpftrace 本身会增加跟踪开销。旧轮次开始时的主机冷却状态也不完全一致，因此这些数据只能证明“长尾与 vCPU 调度等待共同出现”，不能证明 bpftrace 没有影响结果。

## 3. 禁用 bpftrace 后问题仍然存在

正式性能轮关闭了所有 bpftrace，并增加冷却门禁。开始测试前必须连续五次满足：线程数不高于 8000、`load1` 不高于 5、blocked 为 0、Dirty 不高于 16MiB、Writeback 为 0。

两轮无 bpftrace 的 `c50n500` 仍在第 251 至 350 个请求附近出现长尾：

| 轮次 | API Avg / P95 | VM ready Avg / P95 | CreateContainer Avg / P95 | Max blocked / iowait |
|---|---:|---:|---:|---:|
| R1 | 670.588 / 3742.403ms | 166.567 / 972.476ms | 41.808 / 305ms | 590 / 63.83% |
| R2 | 562.771 / 3382.331ms | 162.015 / 1171.655ms | 44.766 / 235ms | 894 / 63.79% |

这一步排除了两个干扰项：长尾不是 bpftrace 制造的，也不是上一轮未冷却造成的偶发现象。

分段时延还说明，受影响最大的阶段是 `VM start -> agent ready`。`CreateContainer` 也在同一窗口变慢，但它不是整体延迟中唯一或最大的来源。

共同点是这些阶段都依赖 Guest vCPU 继续运行。只要 vCPU 被 Host 阻塞，Guest Agent、进程创建和健康检查都会一起变慢。

## 4. 为什么高 iowait 不是磁盘问题

下一轮采样加入 `/proc/diskstats`，同时观察根盘 `dm-0` 和 Cubelet 数据盘 `nvme3n1`。

| 指标 | 峰值 |
|---|---:|
| Host iowait | 72.69% |
| blocked | 917 |
| 根盘 util | 14.72% |
| 数据盘 util | 23.17% |
| 根盘 await | 0.13ms |
| 数据盘 await | 1.17ms |

更有代表性的一秒中，`iowait=51.01%`、`blocked=917`，但根盘 util 只有 0.22%，数据盘 util 为 0%。块设备队列并没有饱和。

Linux 的 `iowait` 是 CPU 时间核算结果，不等于“磁盘利用率”。线程在内核中进行不可中断等待时也可能让该值升高。是否为磁盘瓶颈，必须同时检查设备 util、await 和队列深度。

采样工具自身也不是原因。Host sampler 每秒只读一次 `/proc` 并追加一行，单轮 CSV 约 3.6KB。空载对照中，数据盘读写增量为 0，额外上下文切换约占正式压测峰值的 0.3%。

## 5. blocked 线程到底在等待什么

当 `procs_blocked >= 100` 时，采样工具只执行一次 D-state 线程快照，并按线程名和 `wchan` 聚合。

触发时 `/proc/stat` 显示 blocked=461。随后逐线程快照得到：

| 等待点 | 线程数 |
|---|---:|
| `migration_entry_wait_on_locked`，`vcpu0/1/2` | 514 |
| `folio_lock_killable`，`vcpu0/1/2` | 209 |
| `rmap_walk_file`，`vcpu0/1/2` | 4 |
| 其他 | 3 |

`/proc/stat` 和逐线程扫描不是原子快照，峰值又变化很快，所以两组数量不需要闭合。重要的是等待点的构成：几乎所有 D-state 线程都是 Guest vCPU，而且集中在内存页迁移路径。

内核函数的注释直接说明了这类等待：

```c
/* mm/filemap.c */
/* Wait for a migration entry referencing the given page to be removed. */
void migration_entry_wait_on_locked(swp_entry_t entry, spinlock_t *ptl)
{
    struct folio *folio = pfn_swap_entry_folio(entry);
    wait_queue_head_t *q = folio_waitqueue(folio);

    init_wait(wait);
    wait_page.folio = folio;
    wait_page.bit_nr = PG_locked;

    /* Register the waiter, then release the page-table lock. */
    if (!folio_trylock_flag(folio, PG_locked, wait))
        __add_wait_queue_entry_tail(q, wait);
    spin_unlock(ptl);

    for (;;) {
        set_current_state(TASK_UNINTERRUPTIBLE);
        if (smp_load_acquire(&wait->flags) & WQ_FLAG_WOKEN)
            break;
        io_schedule();
    }
}
```

页面迁移期间，旧页表项会暂时变成 migration entry。其他 vCPU 再访问该页时不能继续，只能等待迁移结束并恢复映射。

这也解释了为什么症状看起来像磁盘 I/O。等待路径明确调用了 `io_schedule()`，因此时间可能计入 CPU 的 iowait；但线程真正等待的是内存页迁移完成，不是 NVMe 请求。

## 6. 自动 NUMA balancing 如何触发迁移

自动 NUMA balancing 的目标是让线程靠近它经常访问的内存。它会周期性扫描进程地址空间，把部分页表项改成用于采样访问位置的状态。

```c
/* kernel/sched/fair.c */
static void task_numa_work(struct callback_head *work)
{
    pages = sysctl_numa_balancing_scan_size;
    /* Scan a portion of the process address space. */
    nr_pte_updates = change_prot_numa(vma, start, end);
}
```

线程再次访问这些页面时会产生 NUMA hint fault。内核根据页面所在节点和当前执行节点，判断页面是否放错位置。

```c
/* mm/memory.c */
static vm_fault_t do_numa_page(struct vm_fault *vmf)
{
    target_nid = numa_migrate_prep(folio, vma, vmf->address,
                                   nid, &flags);

    if (target_nid != NUMA_NO_NODE &&
        migrate_misplaced_folio(folio, vma, target_nid)) {
        flags |= TNF_MIGRATED;
    }
}
```

迁移函数把 folio 从原 NUMA node 隔离出来，再以异步方式迁往目标 node：

```c
/* mm/migrate.c */
int migrate_misplaced_folio(struct folio *folio,
                            struct vm_area_struct *vma, int node)
{
    isolated = numamigrate_isolate_folio(NODE_DATA(node), folio);
    list_add(&folio->lru, &migratepages);
    nr_remaining = migrate_pages(&migratepages, alloc_misplaced_dst_folio,
                                 NULL, node, MIGRATE_ASYNC,
                                 MR_NUMA_MISPLACED, &nr_succeeded);
}
```

对普通应用，这通常能改善长期内存局部性。对 Template 并发恢复，它可能在短时间内形成反效果。

每个恢复出的 VMM 都拥有较大的 Guest 内存映射。vCPU 没有固定在某个 NUMA node，内存也没有和同一组 CPU 绑定。存量实例增加后，调度器更容易让 vCPU 跨 node 运行。

VMM 配置本身支持 CPU 和内存绑定，但当前实验日志显示两者都没有启用：

```rust
pub struct CpusConfig {
    pub boot_vcpus: u8,
    pub max_vcpus: u8,
    pub affinity: Option<Vec<CpuAffinity>>,
}

pub struct MemoryZoneConfig {
    pub id: String,
    pub size: u64,
    pub host_numa_node: Option<u32>,
}

pub struct MemoryConfig {
    pub size: u64,
    pub zones: Option<Vec<MemoryZoneConfig>>,
}
```

本轮实际配置是 `affinity: None`、`zones: None`、`prefault: false`。因此 vCPU 的执行位置和 Guest 内存页的位置没有稳定对应关系。

最终形成如下链路：

```text
存量 VM 和 vCPU 持续增加
        ↓
vCPU 更频繁地跨 NUMA node 调度
        ↓
自动 NUMA balancing 扫描 VMM 地址空间
        ↓
Guest 内存访问触发 NUMA hint fault
        ↓
内核迁移被判断为 misplaced 的 folio
        ↓
其他 vCPU 访问迁移页并进入 D-state
        ↓
VM ready、CreateContainer、Probe 同时出现长尾
```

## 7. vmstat 把等待点和迁移速率对齐

D-state 快照只能说明某一刻线程在哪里等待。为了确认等待是否由持续的大规模迁移造成，下一轮同时计算 `/proc/vmstat` 的每秒增量。

在 `iowait=51.15%` 的同一个窗口内：

| 指标 | 每秒增量 |
|---|---:|
| NUMA hint fault | 76,812/s |
| 成功迁移 | 59,443 pages/s |
| 迁移失败 | 12,821 pages/s |
| 根盘 util | 1.42% |
| 数据盘 util | 10.49% |

此时没有 direct reclaim、kswapd 或 compaction 峰值。证据不再只是“vCPU 恰好在迁移函数里”，而是 hint fault、页迁移、迁移失败和 vCPU blocked 在同一时间窗口共同升高。

## 8. 关闭 NUMA balancing 的单因素验证

最终实验只改变一个变量：将 `kernel.numa_balancing` 从 1 临时改为 0。Template、镜像、并发、采样频率和冷却门禁全部保持不变，测试完成后恢复为 1。

| 指标 | NUMA on | NUMA off | 变化 |
|---|---:|---:|---:|
| API Avg | 534.483ms | 326.688ms | -38.9% |
| API P95 | 2912.638ms | 942.261ms | -67.7% |
| QPS | 56.246 | 89.791 | +59.6% |
| Request Avg | 230.962ms | 95.246ms | -58.8% |
| VM ready Avg | 129.452ms | 52.387ms | -59.5% |
| CreateContainer Avg | 34.842ms | 15.406ms | -55.8% |
| `spawn -> helper` Avg | 18.966ms | 5.847ms | -69.2% |
| Max blocked | 548 | 0 | 消失 |
| Max iowait | 51.15% | 0.012% | 接近归零 |
| 页迁移 | 59,443/s | 1,134/s | 大幅下降 |
| 迁移失败 | 12,821/s | 0 | 消失 |

多个相互独立的指标同时改善：迁移等待消失、Guest 依赖阶段变快、API 尾延迟下降、吞吐上升。这构成了比单纯相关性更强的因果证据。

不过，关闭 balancing 后 runnable 峰值从 394 上升到 1375，system 峰值从 47.39% 上升到 89.23%。原先被内存迁移阻塞的 vCPU 开始同时运行，CPU 调度成为下一层压力。

因此，`kernel.numa_balancing=0` 是有效的诊断手段，但不是已经验证的生产默认配置。

## 9. 对 CubeSandbox 的实际影响

这次实验修正了一个早期判断：耗时并不主要集中在 Shim `CreateContainer`。

`CreateContainer` 内部的 `spawn -> helper entry` 确实被放大，但 `VM start -> agent ready` 的绝对长尾更大。二者同时变慢，是因为它们都依赖 Guest vCPU，而 vCPU 在 Host 内存迁移路径中等待。

因此不能把各阶段看成彼此独立的串行成本，也不能把 `CreateContainer` 的 P95 直接解释为该函数内部某个锁的耗时。

更准确的关系是：Host NUMA 页迁移是共同的外部放大器，它同时拉长 VM 恢复、Guest exec 和 readiness Probe。

## 10. 更稳妥的优化方向

第一步应交替重复 NUMA on/off 多轮实验，继续使用相同冷却门禁。单轮消融足以确认方向，但不足以评估长期稳定性和 NUMA-off 的局部性损失。

产品化方向应优先让 vCPU 和 Guest 内存落在同一个 NUMA node，而不是全局关闭自动 balancing。

可行方案包括：

1. 为每个 VMM 设置 vCPU affinity，只允许其在一个 NUMA node 的 CPU 集合内运行。
2. 使用 `MemoryZoneConfig.host_numa_node` 或等价的 `cpuset.mems`，让 Guest 内存从同一 node 分配。
3. 在 Cubelet 层按 NUMA node 分片放置 VM，同时约束该 node 的 CPU、内存和存量 VM 数量。
4. 保留每个 node 的启动余量，避免新恢复 VM 与大量存量 vCPU 争用同一批 CPU。
5. 对 AMD EPYC 9654 等平台记录实际 NPS 配置。NPS1/NPS2/NPS4 会改变 OS 可见的 NUMA 数，不能只按 `amd64` 或 CPU 型号比较。

验证 CPU/内存绑定时，应继续观察同一组指标：`numa_hint_faults`、`numa_pages_migrated`、`pgmigrate_fail`、blocked、D-state wchan、各阶段 P95 和吞吐。

目标不是让页迁移计数绝对为零，而是避免并发恢复窗口出现迁移风暴，并确保 Guest vCPU 不再成批等待 migration entry。

## 11. 如何复用本次定位方法

遇到“高 iowait + 启动变慢”时，可以按以下顺序判断：

1. 用 `/proc/stat` 确认 iowait 和 blocked 是否在同一窗口升高。
2. 用 `/proc/diskstats` 检查设备 util、await 和队列，先确认磁盘是否真的繁忙。
3. 在 blocked 峰值只采一次 D-state `wchan`，避免持续跟踪干扰性能。
4. 用 `/proc/vmstat` 对齐 NUMA hint fault、迁移成功和迁移失败速率。
5. 最后做可回滚的单因素消融，不要只凭调用栈下结论。

本项目对应工具为：

- `run_c50_profile.sh`：执行固定 Template 的并发测试与冷却门禁。
- `sample_c50_host.sh`：低频采集 `/proc/stat`、`/proc/vmstat` 和磁盘数据。
- `analyze_c50_profile.mjs`：按正式请求窗口汇总 Host 与分阶段时延。

## 12. 证据边界

当前结论适用于本次 4 NUMA ARM64 节点、3U2G Template、no-stdout 插桩镜像和 `c50n500` 场景。

NUMA balancing 是 Linux 的通用机制，并非 ARM64 独有。不同 CPU 架构、插槽数、NUMA/NPS 配置、内核版本和 VMM 放置策略，都可能使问题出现、减轻或不跨过可见阈值。

R6 只有一轮，因此还不能把全局 NUMA-off 写成生产建议。下一阶段需要验证的是 VMM CPU/内存同节点绑定，而不是继续围绕 NVMe 或采样日志优化。

## 参考源码与原始证据

- Linux NUMA 扫描：`kernel/sched/fair.c::task_numa_work`
- Linux hint fault：`mm/memory.c::do_numa_page`
- Linux 页迁移：`mm/migrate.c::migrate_misplaced_folio`
- Linux 迁移等待：`mm/filemap.c::migration_entry_wait_on_locked`
- VMM NUMA 配置：`hypervisor/vmm/src/vm_config.rs`
- 原始实验：`artifacts/cubesandbox-createcontainer-profile-v2-20260812/`
- 跨轮汇总：`performance-cooldown-summary.csv`
