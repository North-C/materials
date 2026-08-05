# 一、测试功能、测试项与指标

## 1. 测试环境与统计口径

报告环境是 Tencent Cloud BMI5 裸金属：96 逻辑 CPU、375 GiB RAM、3.84 TB NVMe/XFS；sandbox 规格为 2 vCPU、2 GiB 内存、1 GiB writable layer，存储使用 `/data/cubelet/storage/` 上的 CoW reflink。测试前执行 warm-up，以降低首次 Page Cache 冷读噪声。

| 指标 | 定义 | 解读注意事项 |
|---|---|---|
| `avg` | 测量轮次算术平均 | 容易受极端值影响 |
| `min` | 最小观测值 | 近似展示最理想热路径 |
| `p95` | nearest-rank 95 分位 | 样本仅 3 或 5 轮时通常等于最大值，统计稳定性有限 |
| `max` | 最大观测值 | 展示尾延迟，但不能替代 p99 |
| `wall` | 第一项请求发出到最后一项完成的批次端到端时间 | 包含排队、调度、API、存储与恢复 |
| `per` | `wall / 操作数` | 是吞吐摊销，不是单请求延迟 |
| throughput | `操作数 / wall` | 与 `per` 互为倒数关系 |
| success rate | 成功请求 / 总请求 | 报告 Template 创建各档均为 100% |

脚本的 p95 使用 `ceil(N*0.95)-1` 的 nearest-rank 实现。并发测试中的 `per` 不能表述成“一个 sandbox 只花了 3.6 ms”；它表示同批并行工作的平均吞吐成本。

## 2. 测试矩阵

| 编号 | 功能 | 测试操作/边界 | 自变量 | 核心指标 | 主要资源 |
|---|---|---|---|---|---|
| 3.1 | 部署校验 | Template 创建 sandbox，执行 Hello World | 无 | 成功/失败 | 全链路可用性 |
| 3.2 | Template 冷启动与扩展 | `POST /sandboxes(template_id)` 到 `running` | concurrency=1/10/20/50；请求数=20/200/300/500 | avg/min/p95/max、per、throughput、成功率 | CPU 调度、VMM 恢复、TAP、Page Cache |
| 3.3 | 单机密度 | 累计保留 100/300/500/1000 个 idle sandbox | live sandbox 数 | `free available`、摊销内存/VM | Guest 实际触页、VMM/shim、页表、网络对象 |
| 4.1 | Snapshot 并发 | N 个独立运行 sandbox 各做一次 Snapshot | concurrency=1/5/10 | wall avg/min/p95/max、per-snapshot | 内存写入、rootfs reflink、NVMe 并行度 |
| 4.2 | Snapshot 脏页敏感度 | `/dev/shm` 写 0..1024 MB 后 Snapshot，再从其创建 | write size/实测 dirty bytes | snapshot 与 create 的 avg/min/p95/max | anon/soft-dirty 扫描、内存快照写带宽 |
| 4.3 | 从 Snapshot 创建 | 一个 Snapshot 并发恢复 N 个 sandbox 到 running | concurrency=1/10/20/50 | wall avg/min/p95/max、per-sandbox | CoW 派生、状态恢复、Page Cache 共享 |
| 4.4 | Rollback | 每个 sandbox 建自己的 Snapshot，再原地回滚 | concurrency=1/5/10 | wall avg/min/p95/max、per-rollback | 新 rootfs gen、VM delete/restore、旧 rootfs 清理 |
| 4.5 | Clone | 源 sandbox 临时 Snapshot，创建 N 个副本 | n=1/100；concurrency=1/10/20/50 | wall avg/min/p95/max、per-clone | 一次 Snapshot + N 次恢复 + CoW/Page Cache 共享 |
| 4.6a | Pause | N 个 sandbox 并发 pause | concurrency=1/5/10 | wall avg/min/p95/max、per-pause | **全量 Guest memory 持久化**、NVMe |
| 4.6b | Resume | 同一批 paused sandbox 并发 resume | concurrency=1/5/10 | wall avg/min/p95/max、per-resume | 状态 JSON 读取、内存映射/缺页、agent 重连 |

## 3. 报告结果汇总

### 3.1 Template 冷启动

| 并发 | 请求数 | avg | min | p95 | max | 摊销/实例 | 吞吐 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 47.8 ms | 43.5 ms | 57.4 ms | 60.4 ms | 55.8 ms | 17.9/s |
| 10 | 200 | 88.7 ms | 45.8 ms | 116.9 ms | 119.1 ms | 9.9 ms | 101.4/s |
| 20 | 300 | 98.1 ms | 47.7 ms | 175.8 ms | 232.6 ms | 5.5 ms | 180.9/s |
| 50 | 500 | 276.1 ms | 60.6 ms | 508.4 ms | 681.3 ms | 6.8 ms | 147.6/s |

20 并发是该机器的吞吐甜点；50 并发进入排队区，吞吐反降且 p95 显著增大。

### 3.2 单机密度

| 活跃 sandbox | available memory | 摊销内存/VM |
|---:|---:|---:|
| 0 | 359.5 GiB | - |
| 100 | 357.4 GiB | ~21.5 MB |
| 300 | 352.5 GiB | ~23.8 MB |
| 500 | 347.3 GiB | ~25.0 MB |
| 1000 | 334.3 GiB | ~25.7 MB |

这是 idle/light-load 的摊销值，不代表运行负载写满 2 GiB 后仍只占 25 MB。

### 3.3 Snapshot 并发

| 并发 | 轮次 | wall avg | wall min | wall p95/max | per |
|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 49.8 ms | 47.3 ms | 54.1 ms | 49.8 ms |
| 5 | 5 | 71.0 ms | 62.7 ms | 81.0 ms | 14.2 ms |
| 10 | 5 | 127.2 ms | 79.6 ms | 155.6 ms | 12.7 ms |

每个并发请求作用于不同 sandbox；同一 sandbox 的 Snapshot 请求会内部串行化。

### 3.4 脏页规模

| 预写 | 实测写入 | Snapshot avg | Snapshot p95 | 从 Snapshot 创建 avg | 创建 p95 |
|---:|---:|---:|---:|---:|---:|
| 0 MB | 7.1 MB | 45.7 ms | 47.4 ms | 64.8 ms | 68.6 ms |
| 10 MB | 38.9 MB | 75.7 ms | 79.2 ms | 60.7 ms | 66.1 ms |
| 50 MB | 120.7 MB | 107.7 ms | 112.3 ms | 64.4 ms | 70.6 ms |
| 100 MB | 195.0 MB | 138.6 ms | 139.9 ms | 66.5 ms | 71.1 ms |
| 200 MB | 296.7 MB | 174.2 ms | 176.2 ms | 63.7 ms | 66.8 ms |
| 500 MB | 602.5 MB | 289.4 ms | 293.1 ms | 64.0 ms | 66.5 ms |
| 800 MB | 908.4 MB | 392.8 ms | 394.1 ms | 60.9 ms | 65.8 ms |
| 1024 MB | 1136.4 MB | 486.9 ms | 510.8 ms | 68.4 ms | 84.6 ms |

Snapshot 制作近似随写入量线性增长；恢复只建立映射并恢复运行所需工作集，因此约 60-85 ms，未随快照体积线性增长。

### 3.5 恢复、Rollback、Clone、Pause/Resume

| 项目 | 并发/规模 | wall avg | p95/max | per |
|---|---:|---:|---:|---:|
| 从 Snapshot 创建 | 1 | 63.9 ms | 66.1 ms | 63.9 ms |
| 从 Snapshot 创建 | 10 | 89.9 ms | 93.6 ms | 9.0 ms |
| 从 Snapshot 创建 | 20 | 118.9 ms | 167.1 ms | 5.9 ms |
| 从 Snapshot 创建 | 50 | 180.3 ms | 260.7 ms | 3.6 ms |
| Rollback | 1 | 81.6 ms | 97.4 ms | 81.6 ms |
| Rollback | 5 | 189.6 ms | 243.2 ms | 37.9 ms |
| Rollback | 10 | 266.1 ms | 305.1 ms | 26.6 ms |
| Clone | n=1,c=1 | 219.6 ms | 234.7 ms | 219.6 ms |
| Clone | n=100,c=10 | 870.4 ms | 880.2 ms | 8.7 ms |
| Clone | n=100,c=20 | 638.6 ms | 656.3 ms | 6.4 ms |
| Clone | n=100,c=50 | 540.9 ms | 590.5 ms | 5.4 ms |
| Pause | 1 | 558.4 ms | 590.3 ms | 558.4 ms |
| Pause | 5 | 656.9 ms | 683.2 ms | 131.4 ms |
| Pause | 10 | 682.1 ms | 699.3 ms | 68.2 ms |
| Resume | 1 | 41.8 ms | 65.1 ms | 41.8 ms |
| Resume | 5 | 28.2 ms | 34.2 ms | 5.6 ms |
| Resume | 10 | 35.7 ms | 41.7 ms | 3.6 ms |

Clone 的 wall 包含临时 Snapshot。Rollback 的准备阶段虽为每个 sandbox 制作专属 Snapshot，但 timer 在这些 Snapshot 完成后才启动；表中 wall 只包含可选 dirty write 与并发 `rollback()`，不包含 `create_snapshot()`。详见 [03_sequences_and_findings.md](03_sequences_and_findings.md)。
