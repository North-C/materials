# 二、镜像、快照与内存数据流

## 1. 数据对象与驻留位置

| 对象 | 权威位置 | RAM / Page Cache 中的内容 | 生命周期/共享方式 |
|---|---|---|---|
| OCI image layers | SSD：Cubelet/containerd image content 与 snapshotter 数据 | 热文件页可能进入 Page Cache | 多个 Template/实例共享只读层 |
| Template rootfs | SSD：`/data/cubelet/storage/cubecow-reflink` 下的 cubecow 对象（默认配置） | 被访问的块进入 Page Cache | 创建实例时 reflink/CoW 派生 writable rootfs |
| Sandbox writable rootfs | SSD：sandbox 专属 cubecow volume | 热文件页在 Page Cache | 写时分配；删除 sandbox 后回收 |
| VM 配置 | SSD：快照目录 `snapshot/config.json` 或 Pause 目录 `config.json` | 恢复时解析出的 `VmConfig` | 小型 JSON，含 CPU、内存、设备和后端配置 |
| VM 状态 | SSD：`snapshot/state.json` 或 Pause 目录 `state.json` | 恢复时构造 vCPU、设备、内存管理器状态 | 序列化的迁移组件树，不含大块 Guest RAM 字节 |
| Template/Snapshot Guest memory | SSD：cubecow memory volume（通过 `memory_vol_url` 传给 VMM） | 映射页、已缺页读取的工作集、Page Cache | 多实例共享底层快照，写时私有化 |
| 无外部 memory volume 的 VM memory | SSD：快照目录 `memory-ranges` | 同上 | Pause 默认走这一形态 |
| Snapshot catalog | SSD：Cubelet 本地 catalog/元数据目录 | Cubelet map/cache 中的索引项 | `snapshot_id -> rootfs_vol/memory_vol/meta_dir` |
| CubeMaster 业务元数据 | MySQL/Redis 等控制面存储 | 本地 cache、任务状态 | 当前 v5 设计避免把物理路径作为跨节点权威信息 |
| 运行 sandbox 的 Guest RAM | Host RAM | 实际触碰的 Guest 匿名页；未触碰的 2 GiB 地址空间不等于实占 2 GiB | sandbox 运行期间存在；CoW 写入才产生私有页 |
| Paused sandbox 控制状态 | Host RAM | CubeShim、container map、`SandBoxState::Paused`、RPC/监控元数据 | Guest VM 已删除，控制面对象仍存在 |

“在 Page Cache”与“保存在 SSD”不矛盾：Page Cache 是 SSD 文件的缓存。报告 Clone 明确说明磁盘文件已在 Page Cache，因此数据权威副本仍在 SSD，但本轮不产生冷读 IO。

## 2. 从镜像构建 Template

1. CubeMaster 接收 `create-from-image`，记录镜像、CPU/内存、writable layer、端口和 probe 配置。
2. Cubelet 拉取 OCI manifest/config/layers，内容落盘；解包出的只读层由本机 image/snapshotter 管理。
3. 创建临时 sandbox，派生 build rootfs，启动 VMM/Guest/agent，等待 probe ready。
4. Template 的首个内存基线没有可增量覆盖的 base，因此当前 `AppSnapshot` 明确选择 `snapshotTypeFull`。
5. VMM 暂停 VM，将 `config.json`、`state.json` 写入临时元数据目录，把全量 Guest memory 写入新建的 cubecow memory volume。
6. build rootfs 通过 cubecow/XFS reflink 制作 Template rootfs snapshot；销毁临时 sandbox。
7. 临时目录原子 rename 为最终目录，catalog 记录逻辑 Template 与本机物理对象的映射。

这意味着“基于镜像创建 Template”不是仅保存 OCI layer 列表：Template 还包含已启动 Guest 的 VM 状态和内存基线，因此从 Template 启动能绕过传统 boot/init 的大部分路径。

## 3. 基于 Template 创建 sandbox（3.2、3.3）

### SSD 数据流

1. 由 Template rootfs reflink 派生 sandbox rootfs，新对象初始共享数据块。
2. 由 Template memory snapshot 建立恢复源；当前 cubecow backend 会为恢复解析逻辑 memory volume 并提供块设备/文件路径。
3. 读取快照 `config.json` 与 `state.json`，替换本实例的 TAP、vsock、磁盘/pmem/virtiofs 后端信息。
4. 恢复 VMM，关键内存页按映射/缺页进入 RAM；Guest 写页转为实例私有 CoW 数据。

### RAM 中保存什么

- VMM/CubeShim 进程与 Rust/Go runtime 开销。
- KVM vCPU、页表、virtio queue、eventfd、vsock、TAP 等宿主结构。
- Guest 启动后实际触碰的匿名页，而不是预先分配完整 2 GiB。
- 文件和 memory volume 的 Linux Page Cache；多实例读相同底层页时可复用。
- Cubelet 的 sandbox/container metadata、状态对象、索引和监控 goroutine。

因此 3.3 测到约 25 MB/idle VM 是上述项目的混合摊销。它不等于“VM 固定开销”，也不等于“2 GiB 内存压缩到 25 MB”。随着 sandbox 写入自己的 2 GiB，匿名私有页会接近额定容量。

## 4. 创建 Snapshot（4.1、4.2）

普通应用 Snapshot 的逻辑步骤：

1. CubeAPI 调 CubeMaster 创建 Snapshot job；CubeMaster 对 sandbox/request/resource 加锁并约束同一 sandbox 串行。
2. Cubelet 解析 sandbox 当前 rootfs、已有恢复基线和 snapshot catalog。
3. 为 memory 创建目标 cubecow snapshot/volume，为 rootfs 创建 reflink snapshot。
4. CubeShim 对运行 VM 执行 `vm.pause` → `vm.snapshot` → `vm.resume`；与 Pause 不同，普通 Snapshot 完成后原 VM继续运行。
5. VMM 将 `VmConfig` 写 `config.json`，将 vCPU、device manager、memory manager 等迁移状态树写 `state.json`。
6. 内存字节写入外部 `memory_vol_url`；若未提供外部 volume，则写目录内 `memory-ranges`。
7. Cubelet 原子发布元数据目录并写 catalog；CubeMaster 标记 Snapshot ready。

### 三种内存模式（当前代码）

| 模式 | 写入内容 | 前置条件 | 适用路径 |
|---|---|---|---|
| `Full` | 所有 snapshot memory ranges | 无 base 要求 | 新 Template 基线；Pause 默认值 |
| `Incremental` | pagemap 判定的匿名 CoW 页，覆盖到已有完整 base | 目标 memory blob 必须已存在 | 从已绑定基线派生 Snapshot |
| `SoftDirty` | 首轮无 tracker 时退化为 anon 全量并 arm；稳态写 `anon ∩ soft-dirty` | 已有 base，且内核支持 `/proc/self/clear_refs` | 连续 checkpoint 的最小增量 |

报告 4.2 的“Dirty Page”来自 VMM 日志，并非 Python 写入字节数。Guest 后台活动、页对齐、allocator/tmpfs 元数据和其他匿名页会使实测值大于理论预写值。

## 5. 基于 Snapshot 创建（4.3）

Snapshot 与 Template 在控制面都可作为 `template` 参数，但 Snapshot 带有源 sandbox 的运行状态。

- rootfs：从 Snapshot rootfs reflink 派生新 gen，底层块共享，实例写入时私有化。
- memory：新实例恢复时读取同一快照 memory object；不会为每个实例先复制整个快照。
- config/state：每次读取并修正实例特有设备后端、CID/TAP/vsock 等。
- RAM：只在访问时建立工作集；多个并发恢复可共享 Page Cache 中的快照页。

所以 1.1 GiB 的 Snapshot 与 7 MB 的 Snapshot 都可在约 60-85 ms 达到 running。这个指标不是“已把全部 1.1 GiB 读入 RAM”；后续访问冷页仍可能付出缺页与 SSD 读取成本。

## 6. Rollback（4.4）

当前实现是原 sandbox ID 下的 VM/rootfs 替换：

1. 验证 Snapshot 归属于该 sandbox、位于同一节点且 cubecow backend 可用。
2. 从 Snapshot rootfs 派生更大的 generation，保留 Snapshot 对象不变。
3. 构建 `RestoreConfig`，其中 `source_url` 指向 Snapshot 元数据目录，`memory_vol_url` 指向 Snapshot memory 对象，并替换磁盘设备。
4. CubeShim 断开 agent，直接 `VmDelete` 当前 VM；**不会先保存当前状态**，因此避免一次无用的全量内存写盘。
5. 在同一个 VMM 进程内从目标 Snapshot 恢复，重连 agent/monitor/OOM watcher。
6. Cubelet 持久化新 rootfs gen，更新 runtime snapshot binding，删除旧 rootfs；失败时旧对象清理由延迟路径处理。

Rollback 后当前执行状态被目标 Snapshot 覆盖。Snapshot 本体仍为只读恢复基线；sandbox 的后续写入落到新的 rootfs gen 和新的私有内存页。

## 7. Clone（4.5）

当前 Python SDK 的 `clone(n, concurrency)`：

1. 对源 sandbox 执行 `create_snapshot()`。
2. 用临时 `snapshot_id` 并发调用 `Sandbox.create()` N 次。
3. 无条件 best-effort 删除临时 Snapshot。
4. 任一创建失败时，清理已成功的 sibling sandbox，再抛出首个错误。

因此：

- 单 clone 约 220 ms 大于单次 create-from-snapshot 约 64 ms，差值主要包含临时 Snapshot 制作、API 往返与清理。
- 100 clone 时，Snapshot 只制作一次；并发恢复共享 Snapshot rootfs/memory 和 Page Cache。
- 每个 clone 获得独立 writable rootfs 与私有写页，但不会复制全部底层磁盘/内存数据。
- 报告注明 Page Cache 已热，故 5.4-8.7 ms 的 `per` 不能外推到冷缓存或跨节点 Snapshot 分发场景。

## 8. Pause / Resume（4.6）

### Pause 精确回答：保存在哪里

**持久化到 SSD：**

- `/data/cubelet/root/pausevm/<sandbox-id>/config.json`：VM 配置。
- `/data/cubelet/root/pausevm/<sandbox-id>/state.json`：vCPU、VM、device manager、memory manager、virtio 等序列化状态树。
- `/data/cubelet/root/pausevm/<sandbox-id>/memory-ranges`：Guest snapshot memory ranges。Pause 未设置 `memory_vol_url` 和 snapshot type，默认是 `Full`。
- sandbox rootfs 本来就在 `/data/cubelet/storage/...` 的 cubecow 持久化对象中；Pause 不复制一份新 rootfs。

`config.json` 和 `state.json` 在写完后显式 `sync_all()`；这解释了 Pause 是持久化语义，而不是只冻结进程。

**Pause 后 RAM 中继续保留：**

- CubeShim/containerd-shim 进程及 `SandBox`/`Container` 对象。
- `SandBoxState::Paused`、sandbox ID、OCI spec、container/exec 元数据和 Cubelet 状态缓存。
- 用于后续 Resume 的控制通道和后端资源描述；Cubelet 当前还会保留磁盘资源计费，因为 pause snapshot 占存储。
- Linux 可能继续缓存刚写出的快照页，但这只是可回收 Page Cache。

**Pause 后 RAM 中不再保留：**

- 当前 Guest VM 对象和其完整 Guest RAM 映射。VMM 的 `vm_pause_to_snapshot()` 顺序是 `vm_pause()`、`vm_snapshot()`、`vm_delete()`。
- Guest agent 连接和旧 monitor/OOM watcher；Resume 后会重新连接和创建。

### Resume 数据流

1. 从同一路径读取 `config.json`、`state.json`、`memory-ranges`。
2. `VmRestore` 重新构造 VM/vCPU/device/memory manager，建立 Guest memory backing。
3. 重连 Guest agent，执行 reset，重新绑定各 container 的 client。
4. 重启 OOM watcher 和 VM monitor，把 shim 状态置回 `Normal`。

Resume 快是因为它无需再次写 2 GiB，也不要求在返回前扫描/读完全部 memory-ranges。Pause 的 ~558 ms 则由全量内存顺序写和 `sync` 主导；10 并发时 NVMe 并行使吞吐摊销下降，但每个请求的真实完成时间仍约 682 ms。
