# 四、源码证据索引

以下位置均相对 `source_code/CubeSandbox`，用于复核主报告结论。

| 结论 | 代码位置 | 证据 |
|---|---|---|
| cube-bench 计时 POST `/sandboxes` 完整 HTTP 往返 | `examples/cube-bench/runner.go:25` | timer 在 request 前开始，在 `client.Do` 返回后记录；create-only 不删除 |
| p95 是 nearest-rank | `examples/cube-bench/stats.go:16` | `ceil(len*p/100)-1` |
| 从 Snapshot 创建 warm-up | `examples/snapshot-rollback-clone/bench_create_concurrency.py:43` | 先创建 Snapshot，丢弃第一次 restore，再计并发 wall |
| Clone timer 包含 SDK clone 全流程 | `examples/snapshot-rollback-clone/bench_clone_concurrency.py:46` | timer 包住 `src.clone(n, concurrency)` |
| SDK Clone = Snapshot + N create + delete Snapshot | `sdk/python/cubesandbox/sandbox.py:646` | `create_snapshot()`、ThreadPoolExecutor create、finally delete |
| Snapshot job 对 sandbox/request 加锁 | `CubeMaster/pkg/templatecenter/snapshot_ops.go:107` | `withSnapshotWriteLocks`，限制 active Snapshot job |
| Rollback 计时不含前置 Snapshot | `examples/snapshot-rollback-clone/bench_rollback_concurrency.py:58` | 第 60-61 行创建 sandbox/Snapshot，第 63 行才启动 timer |
| 新 Template 内存基线强制 Full | `Cubelet/services/cubebox/appsnapshot.go:283` | 无 base 可 overlay，调用 `snapshotTypeFull` |
| Template 元数据默认目录 | `Cubelet/services/cubebox/appsnapshot.go:35` | `/usr/local/services/cubetoolbox/cube-snapshot` |
| cubecow 默认 SSD 数据目录 | `Cubelet/config/config.toml:93` | backend=cubecow，`data_path=/data/cubelet/storage` |
| rootfs 从 Template 派生 | `Cubelet/storage/cubecow_volume_manager.go:139` | `CreateSandboxRootfsFromTemplate -> RollbackDeriveNewGen` |
| Snapshot VM 先 pause、写快照、再 resume | `CubeShim/shim/src/snapshot/mod.rs:119` | `api_pause_vm`、`api_snapshot_vm`、`store_metadata`、`api_resume_vm` |
| VM 配置与状态写 SSD 并 sync | `hypervisor/vmm/src/vm.rs:2814` | 写 `config.json`/`state.json`，两者 `sync_all()` |
| 内存文件名与外部 memory volume 选择 | `hypervisor/vmm/src/memory_manager.rs:67` | 有 `memory_vol_url` 用外部对象，否则 `memory-ranges` |
| 三种 memory snapshot 模式 | `hypervisor/vmm/src/memory_manager.rs:3102` | Incremental/SoftDirty/Full 分支 |
| SoftDirty 首轮回退并 arm | `hypervisor/vmm/src/memory_manager.rs:2486` | 首轮 pagemap anon；稳态 anon ∩ soft-dirty |
| 基于 Snapshot 恢复读取 source + memory volume | `CubeShim/shim/src/sandbox/sb.rs:838` | 校验 metadata，构造 `RestoreConfig`，调用 `restore_vm` |
| Rollback 派生新 rootfs gen | `Cubelet/services/cubebox/rollback.go:50` | `RollbackDeriveNewGen`，构建 restore config，删除旧 rootfs |
| Rollback 不保存当前 VM | `CubeShim/shim/src/sandbox/sb.rs:1228` | disconnect 后直接 `VmDelete`，再 target restore |
| Pause 目录固定在 SSD | `CubeShim/shim/src/common/mod.rs:27` | `/data/cubelet/root/pausevm` |
| Pause 创建目录并调用 pause-to-snapshot | `CubeShim/shim/src/sandbox/sb.rs:1193` | `recreate_dir`、`pause_vm_cube`、等待 shutdown event |
| Pause 是 pause + snapshot + delete | `hypervisor/vmm/src/lib.rs:616` | `vm_pause()`、`vm_snapshot()`、`vm_delete()` |
| Pause 未传 memory volume/type | `CubeShim/shim/src/hypervisor/cube_hypervisor.rs:289` | `SnapshotConfig{destination_url,..Default}`，因此 Full + `memory-ranges` |
| Resume 从 Pause 目录恢复 | `CubeShim/shim/src/sandbox/sb.rs:1293` | `resume_vm_cube(file:///data/.../pausevm/<id>)` 后 agent 重连 |
| sandbox 清理时删除 Pause 目录 | `CubeShim/shim/src/common/utils.rs:145` | `clean_sandbox_resource` 删除 pause snapshot dir |
| API Pause/Resume 走 UpdateSandbox | `CubeAPI/src/services/sandboxes.rs:254` | action=`pause`；connect 对 paused sandbox action=`resume` |

## 报告与实现版本

- 报告页面日期：2026-06-01。
- 本次分析仓库 HEAD：`953d17b936f6be6eb55445f08fea4cb758a2b305`（2026-08-04）。
- 工作树在分析前已有用户修改；本次没有改动 `source_code/CubeSandbox`。
- 因版本跨度，报告中的结果值保持原样，内部机制以当前代码为准，并在出现差异处显式标注。

## 外部来源

- [中文基准报告](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)
- [英文基准报告](https://cubesandbox.com/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)
