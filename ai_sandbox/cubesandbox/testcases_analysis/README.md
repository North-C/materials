# CubeSandbox 基准测试用例分析

本目录分析 [CubeSandbox 核心操作性能基准测试报告](https://cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)，并以 `source_code/CubeSandbox` 当前代码（commit `953d17b936f6be6eb55445f08fea4cb758a2b305`，2026-08-04）为实现依据。

## 文档导航

- [01_benchmark_matrix.md](01_benchmark_matrix.md)：测试功能、测试项、输入变量、统计指标和报告结果。
- [02_dataflow_and_storage.md](02_dataflow_and_storage.md)：逐项分析镜像、rootfs、内存快照、元数据在 RAM、Page Cache、SSD 之间的数据流。
- [03_sequences_and_findings.md](03_sequences_and_findings.md)：Template/Snapshot 创建、Rollback、Clone、Pause/Resume 的调用时序、性能解释与测试局限。
- [04_source_evidence.md](04_source_evidence.md)：实现结论到代码位置的证据索引。
- [diagrams/](diagrams/)：可编辑 `.drawio` 与可直接查看的 `.svg` 图。

## 最重要的结论

1. **Pause 数据在 SSD，不只在内存。** 当前 Pause 将 VM 的 `config.json`、`state.json` 和全量 `memory-ranges` 写入 `/data/cubelet/root/pausevm/<sandbox-id>/`，随后执行 `vm_delete()`，释放 Guest VM 对象及其 RAM 映射。内存中继续保留的是 CubeShim 进程、sandbox/container 元数据、状态 `Paused`、控制通道与 Cubelet/CubeMaster 的生命周期记录，不是 2 GiB Guest RAM。
2. **普通 Snapshot 是持久化的“内存 + 设备/CPU 状态 + rootfs CoW 对象”。** VM 配置和状态 JSON 位于快照元数据目录；Guest 内存写入 cubecow memory volume；rootfs 通过 XFS reflink/cubecow 形成 CoW 快照。Snapshot 删除前可独立于源 sandbox 存在。
3. **基于 Template/Snapshot 启动不是全量拷贝。** rootfs 派生 CoW writable volume，内存快照通过文件或块设备映射并按缺页访问；启动只需要先读小型配置/状态及恢复关键工作集，因此报告中恢复耗时基本不随脏页总量增长。
4. **Clone 在当前 SDK 中不是单一服务端 clone 原语。** 它是 `create_snapshot()`、并发 `Sandbox.create(template=snapshot_id)`、`delete_snapshot()` 的组合，测得的 wall time包含临时快照制作。
5. **报告与当前代码有版本差异。** 报告记录 2026-06-01 的实现和数据；当前仓库已经支持 `Full`、`Incremental(PagemapAnon)`、`SoftDirty` 三种内存写入模式，但 Pause 路径仍使用默认 `Full`。

## 图表

| 图 | 类型 | 内容 |
|---|---|---|
| [01_benchmark_scope.svg](diagrams/01_benchmark_scope.svg) | 流程图 | 全部测试项、变量和指标 |
| [02_template_snapshot_dataflow.svg](diagrams/02_template_snapshot_dataflow.svg) | 数据流图 | 镜像/Template/Snapshot/实例在 SSD、Page Cache、RAM 间流转 |
| [03_snapshot_clone_rollback.svg](diagrams/03_snapshot_clone_rollback.svg) | 流程图 | Snapshot、create-from-snapshot、Clone、Rollback 的共享与派生关系 |
| [04_pause_resume_sequence.svg](diagrams/04_pause_resume_sequence.svg) | 顺序图 | Pause 持久化、VM 删除与 Resume 恢复时序 |

## 口径说明

- “SSD”表示持久化文件系统或其上的 cubecow/XFS reflink 对象；即使数据当前命中 Linux Page Cache，权威副本仍在持久化存储。
- “RAM”区分 Guest RAM、VMM/shim 常驻内存和 Linux Page Cache。`free -h` 的 `available` 变化不能把这三者精确拆开。
- 图中的路径采用当前仓库默认配置。部署可修改 `data_path`、snapshot 目录等配置，结论应理解为数据类型和生命周期，而不是固定路径承诺。
