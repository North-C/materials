# CubeSandbox CoW 与宿主机内存记账模型

## 结论

CoW 只降低“仍保持只读的共享基底”成本，不保证整机 `MemAvailable` 差值除以实例数单调下降。

本文源码结论固定于 CubeSandbox commit `09274501dd12e47dbed2dcc77d8eb67dd661d49c`。其他部署必须重新核验二进制和配置。

如果共享 Snapshot resident base 为固定的 `S`，每实例独占成本为固定的 `P`，理想化平均 PSS 才近似为：

```text
PSS_per_instance(N) ≈ P + S/N
```

社区表测量的不是这个量。它还混入 Guest 私有写页、VMM/CubeShim、页表、KVM、内核栈、slab、网络、文件缓存和平台状态。

## 1. 两类不同的 CoW

### 1.1 rootfs：XFS reflink

CubeCow 使用 `FICLONE` 为每个 Sandbox 创建独立 rootfs 文件，同时共享未修改的磁盘 extent。

相关实现：

- [`cubecow/src/engine/reflink.rs`](https://github.com/TencentCloud/CubeSandbox/blob/09274501dd12e47dbed2dcc77d8eb67dd661d49c/cubecow/src/engine/reflink.rs#L748-L806)
- [`Cubelet/storage/cubecow_volume_manager.go`](https://github.com/TencentCloud/CubeSandbox/blob/09274501dd12e47dbed2dcc77d8eb67dd661d49c/Cubelet/storage/cubecow_volume_manager.go#L137-L161)

它首先节省存储 extent，不等于“所有 rootfs 宿主页缓存只保留一份”。

每个 Sandbox 仍有独立 inode、ext4 元数据和写时复制结果。文件读取、写入和元数据活动仍可能增加 Page Cache 与 slab。

### 1.2 Guest memory：file-backed `MAP_PRIVATE`

快速恢复会打开 Snapshot memory 文件，并以 `MAP_PRIVATE | MAP_NORESERVE` 创建 Guest RAM region。

实现见：

- [Snapshot restore](https://github.com/TencentCloud/CubeSandbox/blob/09274501dd12e47dbed2dcc77d8eb67dd661d49c/hypervisor/vmm/src/memory_manager.rs#L1326-L1375)
- [RAM region flags](https://github.com/TencentCloud/CubeSandbox/blob/09274501dd12e47dbed2dcc77d8eb67dd661d49c/hypervisor/vmm/src/memory_manager.rs#L1494-L1545)

默认 `prefault=false`，因此 API 返回 running 不表示整份 Guest memory 已进入 RAM。

页面会处于三种状态：

| 状态 | Host 结果 |
|---|---|
| 尚未访问 | 没有 PTE，不 resident |
| 只读访问 | file-backed，可复用同一 page cache 页 |
| Guest 写入 | 触发 CoW，形成该 VMM 的私有匿名页 |

`MAP_NORESERVE` 只是不预留完整提交量。页面一旦 fault 并被写入，仍会占用物理内存。

## 2. 完整宿主机分解

将相对 N=0 的整机变化写成：

```text
ΔH(N) = S(N) + U(N) + K(N) + C(N) + P(N) + E(N)
```

其中：

- `S(N)`：当前 resident 的共享 Snapshot/base 文件页；
- `U(N)`：VMM、CubeShim 和 Guest 私有匿名页；
- `K(N)`：页表、KVM 二级页表、内核栈、slab、socket、TAP；
- `C(N)`：rootfs、Snapshot 和其他文件缓存；
- `P(N)`：CubeMaster、Cubelet、containerd 等平台动态状态；
- `E(N)`：采样时序、自然漂移和其他 Host 活动。

整机均摊为：

```text
A(N) = ΔH(N) / N
```

只有 `S` 固定、`U/K/C/P` 严格线性且 `E=0` 时，`S/N` 才保证拉低平均值。

真实系统不满足这些充分条件，因此 `A(N)` 可以上升、下降或分段变化。

## 3. 为什么共享收益会被盖过

### 3.1 Guest 私有页持续增加

Guest kernel、agent、日志、timer、网络和 allocator 都可能写入恢复后的页面。

每次写入都会把共享 file-backed 页转换为该 VMM 的私有匿名页。实例运行越久，累计私有页可能越多。

### 3.2 每实例运行时对象不会共享

每个 Sandbox 仍需要 CubeShim/VMM 状态、vCPU、virtio device、vsock、eventfd/irqfd、线程和文件描述符。

这些对象不因 Snapshot memory 共享而消失。

### 3.3 私有匿名页默认不做 KSM 合并

当前 MemoryConfig 的 `mergeable` 默认关闭。

见 [`vm_config.rs`](https://github.com/TencentCloud/CubeSandbox/blob/09274501dd12e47dbed2dcc77d8eb67dd661d49c/hypervisor/vmm/src/vm_config.rs#L159-L188)。

已经 CoW 私有化的相同内容不会自动重新合并成共享页。

### 3.4 内核成本可能分段增长

页表、KVM 二级页表、内核栈、cgroup、socket、TAP queue、dentry/inode 和 slab 会随实例、线程、mapping 和设备增长。

slab page、哈希表和 allocator arena 常按页或容量扩张，不必呈现完全平滑的线性曲线。

### 3.5 平台组件也有边际成本

CubeMaster、Cubelet、CubeAPI、network-agent 和 containerd 会保存 Sandbox 元数据、连接、队列和 cache。

这些都进入整机差值，但不属于 Sandbox VMM RSS。

## 4. 四种记账视角

| 视角 | 表达什么 | 共享页行为 | 适合回答 |
|---|---|---|---|
| RSS | 单进程 resident mapping | 每个映射都计整页 | 单进程看到多少 resident |
| PSS | 按映射数分摊 resident 页 | 一页由 k 个进程共享时各计 1/k | 公平分摊的进程视图 |
| USS | `Private_Clean + Private_Dirty` | 只计该进程独占页 | 实例删除后可直接释放多少 |
| cgroup memory | 页面和内核对象的 charge | 不等于 PSS公平分摊 | 资源限制与 charge 视图 |
| MemAvailable | 不触发 swap/OOM 的可用内存估计 | 含可回收 cache/slab 启发式 | Host容量与压力趋势 |

这些量必须并列展示，不能相加。

### 4.1 `MemAvailable` 是估算值

Linux 会从 free pages、file LRU 和 reclaimable kernel memory估算 `MemAvailable`。

它不是 `MemTotal - CubeSandbox物理占用`。算法还受 watermark 和“并非所有 cache/slab 都能回收”的估计影响。

见 [Linux 6.6 `/proc/meminfo`](https://docs.kernel.org/6.6/filesystems/proc.html#meminfo)。

### 4.2 cgroup charge 不是 PSS

cgroup v1 对共享页使用 first-touch charge，而不是按映射数分摊。

`memory.usage_in_bytes` 还是为性能优化的近似值。已删除 cgroup 的 file cache charge 也可能延迟到内存压力时迁移或回收。

见 [cgroup v1 shared-page accounting](https://docs.kernel.org/6.6/admin-guide/cgroup-v1/memory.html#shared-page-accounting)。

cgroup v2 提供 `anon`、`file`、`kernel`、`pagetables`、`sec_pagetables`、`slab_*` 等分项。

见 [cgroup v2 memory.stat](https://docs.kernel.org/6.6/admin-guide/cgroup-v2.html#memory-interface-files)。

## 5. 如何判断 CoW 是否正常

以下现象支持“CoW 正常，但其他项盖过收益”：

| 观测 | 解释 |
|---|---|
| Snapshot `Pss_File/N` 下降 | 共享 base 的比例分摊在下降 |
| `USS/Pss_Anon` 上升 | Guest 写页正在私有化 |
| cgroup file偏斜 | first-touch charge，不等于共享失效 |
| `PageTables/KernelStack/Slab` 上升 | 内核附加成本增长 |
| 控制面 PSS随 N 上升 | 平台边际状态增长 |

以下现象需要进一步调查：

| 观测 | 下一步 |
|---|---|
| VMM没有共同 Snapshot mapping | 核对 restore path、Template和 fast restore条件 |
| `Pss_File` 不共享且 USS接近完整工作集 | 检查实际部署是否复制 memory或启用了不同配置 |
| 高密度出现 reclaim/PSI | 将该点标记为压力状态切换，不与无压力点直接回归 |

## 6. 正确的核心问题

不要问：

> 为什么有 CoW，整机均摊还不下降？

应拆成三个可验证问题：

1. 同一 Snapshot memory 的共享 `Pss_File` 是否随映射者增加而摊薄？
2. 每实例 `USS/Pss_Anon`、runtime和内核边际项是否增长？
3. `MemAvailable` 与 PSS/cgroup 的差异能否由 cache、slab、页表和 Host漂移解释？

只有这三个问题同时有数据，才能判断增长机制。

## 参考资料

- [CubeSandbox 社区密度内存表审计](community-density-memory-report-audit.md)
- [CubeSandbox 沙箱资源指标](https://docs.cubesandbox.com/zh/guide/resource-metrics.html)
- [Linux `proc_pid_smaps`](https://man7.org/linux/man-pages/man5/proc_pid_smaps.5.html)
- [Linux TUN/TAP](https://docs.kernel.org/networking/tuntap.html)
- [Linux `drop_caches`](https://docs.kernel.org/6.6/admin-guide/sysctl/vm.html#drop-caches)
