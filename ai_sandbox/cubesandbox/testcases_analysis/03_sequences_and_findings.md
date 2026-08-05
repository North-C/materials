# 三、流程、顺序与性能解释

## 1. Template 冷启动流程

参见 [02_template_snapshot_dataflow.svg](diagrams/02_template_snapshot_dataflow.svg)。端到端计时从客户端发起 `POST /sandboxes` 开始，到 CubeAPI 收到 ready/running 响应结束，包含：

`SDK/HTTP → CubeAPI → CubeMaster 调度 → Cubelet 派生 rootfs/memory → containerd/CubeShim → VMM restore → Guest agent/probe ready → 响应`

20 并发吞吐最佳、50 并发尾延迟恶化，说明瓶颈从单实例恢复固定开销转为宿主 CPU 调度、TAP/资源池、Cubelet 工作队列及共享存储/Page Cache 竞争。报告仅给整体 API 延迟，不能据此把 508 ms p95 全部归因于 VMM restore。

## 2. Snapshot 顺序

参见 [03_snapshot_clone_rollback.svg](diagrams/03_snapshot_clone_rollback.svg)。普通 Snapshot 对源 VM 的停顿窗口是：

1. 停止/排空 exec 与日志转发相关工作。
2. `vm.pause`，确保 vCPU 与可迁移设备静止。
3. 快照 `VmConfig`、vCPU/设备/内存管理器状态。
4. 写 memory volume 的 Full/Incremental/SoftDirty 数据。
5. rootfs cubecow reflink 与 catalog 原子发布。
6. `vm.resume`，源 sandbox 继续运行。

同一 sandbox 串行 Snapshot 是正确性要求：两个增量写若共享同一 base/dirty window，会产生竞态和不可恢复的组合状态。并发测试用 N 个独立 sandbox，测的是宿主写入与调度扩展能力，不是单 sandbox 的并行 checkpoint 能力。

## 3. Clone 与 create-from-snapshot 的计时差异

`bench_create_concurrency.py` 在测量前只制作一次 Snapshot，warm-up 一次恢复并丢弃，然后 timer 只包住并发 `Sandbox.create(template=snap_id)`。因此其结果代表热缓存下的恢复 fan-out。

`bench_clone_concurrency.py` 的 timer 包住 `src.clone()`。当前 SDK 的 `clone()` 内部包含 Snapshot 制作、N 次 create 和 Snapshot 删除，所以 Clone 与 4.3 不可直接当作同一计时边界比较。

报告文字称 Clone 调 `POST /sandboxes/{id}/clone`，但当前仓库 SDK 并没有依赖单一服务端 clone 原语。分析当前代码时应以组合语义为准；若要复现实验原报告历史版本，应 checkout 报告对应 tag/commit 后再次确认 API。

## 4. Rollback 顺序

当前代码的关键优化是“丢弃当前 VM，再恢复目标”，不先保存当前 VM：

`锁 sandbox → 校验 ownership/locality → 从 snapshot rootfs 派生 new gen → disconnect agent → VmDelete current → VmRestore target → reconnect → 持久化 new gen → 删除 old rootfs`

这使 Rollback 不承担 Pause 那样的全量当前内存写盘成本。失败语义也更强硬：目标恢复失败时，当前 VM 已删除，没有临时 checkpoint 可自动退回。

### 报告计时边界校正

报告说明每个 sandbox 需要先 `create_snapshot()` 再 `rollback()`，但当前 `bench_rollback_concurrency.py` 的 timer 在全部专属 Snapshot 制作完成后才启动。准备动作和被测动作不能仅凭自然语言合并；主结果表应明确标注：

- preparation：创建 sandbox、创建专属 Snapshot；
- measurement：可选 dirty write + 并发 rollback wall；
- cleanup：删除 Snapshot、销毁 sandbox。

因此表中 81.6 ms 是 rollback 路径（默认 `dirty_mb=0`）的恢复耗时，不是“Snapshot + Rollback”总耗时。建议未来报告直接列出 timer 边界代码或输出分阶段 latency。

## 5. Pause/Resume 顺序

参见 [04_pause_resume_sequence.svg](diagrams/04_pause_resume_sequence.svg)。核心顺序：

### Pause

`CubeAPI pause → CubeMaster UpdateSandbox → Cubelet containerd task Pause → CubeShim disconnect_agent → 创建 pausevm/<id> → VMM VmPauseToSnapshot → pause vCPU/devices → 写 config/state → 全量写 memory-ranges → sync → VmDelete → CubeShim state=Paused`

### Resume

`CubeAPI resume/connect → CubeMaster UpdateSandbox → Cubelet task Resume → CubeShim VmResumeFromSnapshot → 读 config/state → memory-ranges 作为 backing → 重建 VM → agent reconnect/reset → monitor/OOM watcher → state=Normal`

Resume 后 pause snapshot 目录通常保留到 sandbox 资源清理；下次 Pause 会先重建该目录。保留旧目录并不表示 Resume 后仍依赖旧快照作为持续写入目标，运行时新写仍在 Guest RAM/rootfs writable 层。

## 6. 测试设计局限与建议

| 局限 | 对结论的影响 | 建议补充指标 |
|---|---|---|
| Snapshot/Rollback 多数只有 3-5 轮 | p95 常等于 max，置信度弱 | 至少 30-100 轮，报告 p50/p90/p95/p99 和 CI |
| warm cache 为主 | 低估首次部署/节点迁移/冷 SSD 读取 | 分开 cold-cache 与 warm-cache，不用生产机执行 drop_caches |
| `free available` 是系统级粗指标 | 混合 Guest RAM、Page Cache、slab、进程内存 | 增加 cgroup memory.current、RSS/PSS、anon/file、KVM 页表、slab 分项 |
| 仅 idle density | 不能代表真实 Agent workload | 设计 0/10/50/100% memory dirty 与文件写入档位 |
| wall/per 容易混淆 | `per` 被误解为单请求 latency | 同时输出每请求分布、batch wall、throughput |
| Clone 缓存已热 | 高估跨节点/冷启动扩展性 | 记录 major faults、read bytes、Page Cache hit、Snapshot locality |
| 没有 CPU/IO 同步观测 | 无法确定 50 并发瓶颈 | 输出 iostat、PSI、CPU steal/iowait、run queue、NVMe latency |
| Snapshot 只看写入总量 | 无法验证增量 base 与稀疏度 | 记录模式、base ID、dirty pages、实际写 bytes、fsync 时间 |
| Pause 固定 2 GiB | 难以验证线性关系 | 增加 512 MiB/1/2/4/8 GiB 与实际 touched set 两轴测试 |

## 7. 建议的验收断言

- Snapshot 后修改文件/内存，再从 Snapshot 创建，必须看到 Snapshot 时刻状态。
- Snapshot 删除前源 sandbox 可删除；Snapshot 仍应能创建新 sandbox。
- Rollback 只能使用同一源 sandbox 创建的 Snapshot，跨 sandbox 应返回 conflict/precondition failure。
- Pause 完成后确认 VMM Guest RSS 显著下降，同时 `/data/cubelet/root/pausevm/<id>` 存在且可跨进程重启恢复。
- Resume 后进程 PID/变量、文件内容、网络配置和 agent RPC 可用；再次 Pause/Resume 不受旧事件影响。
- N clone 中一个失败时，SDK 应清理已成功 siblings，临时 Snapshot 删除为 best-effort 且不遮蔽首个创建错误。
