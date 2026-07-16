# 第二批真实镜像 lower page-cache 收益空间测试

测试主机：`192.168.25.65`（aarch64，openEuler，Linux 6.6）

测试日期：2026-07-14

containerd namespace：`ubcache-real`

## 1. 测试目标与结论边界

本批测试回答：真实容器工作负载运行后，有多少镜像 lower 文件页驻留在节点本地 page cache 中，理论上可能由通过验证的 UB/DAX lower 数据路径移出本地 DRAM。

本批只有本地 overlayfs 基线 B0，不包含 NBD-erofs 或 DAX-erofs，因此：

- 能估计 lower page-cache 容量收益空间；
- 能记录当前业务吞吐、延迟、匿名内存和 writable upper 基线；
- 不能证明 DAX 可用，也不能测量 UB/DAX 相对本地 warm page cache 的读取性能下降；
- 表中的 `lower / cgroup peak` 只是容量占比，不是 PoC 已实现的实际节省率。

## 2. 统计方法

### 2.1 lower 文件集合

每个用例通过 containerd overlayfs 创建一个 held container，在业务进程启动前遍历初始 rootfs：

- 只记录非空 regular file；
- 排除 `/proc`、`/sys`、`/dev`、`/run`、`/ubcache-tools` 和 `/ubcache-metrics`；
- 只记录与 rootfs 相同 `st_dev` 的文件，不计 bind mount；
- 使用 `(st_dev, st_ino)` 去除 hardlink，防止同一页被多个路径重复统计。

`logical_bytes` 是去重后 lower 文件逻辑大小，不是镜像压缩包大小，也不是 containerd content store 大小。

### 2.2 targeted cold 与驻留统计

测试不执行全局 `drop_caches`。对 manifest 中每个文件调用：

```text
posix_fadvise(fd, 0, 0, POSIX_FADV_DONTNEED)
```

驱逐后运行一次 cold workload，再运行一次不重新驱逐的 warm workload。每阶段结束后对同一 manifest 文件执行 `mmap + mincore`，逐文件统计 resident page，并在文件尾按实际文件大小截断页对齐放大。

核心指标：

```text
lower_hot_bytes = sum(unique lower inode resident bytes)
lower_resident_ratio = lower_hot_bytes / lower_logical_bytes
lower_to_cgroup_peak = lower_hot_bytes / max(cgroup usage samples)
```

cold 与 warm 阶段都会停止并重新启动业务服务，因此二者负载一致；两阶段之间仅保留 lower page cache 和该容器 upperdir。

### 2.3 cgroup、进程、upper 与宿主机

远端使用 cgroup v1。workload 运行期间每 200 ms 采样：

- `memory.usage_in_bytes`；
- `memory.stat.cache`、`rss`、`mapped_file`；
- `pgfault`、`pgmajfault`；
- `memory.max_usage_in_bytes`。

`cgroup peak` 取时序样本中的最大 `memory.usage_in_bytes`。压测客户端运行在被测容器 cgroup 中，因此会计入 peak；挂载自 `/ubcache-tools` 的压测二进制不计入 lower manifest。OTel 用例的独立 Flagd 容器不计入被测服务 cgroup。

同时采集：

- 主要服务进程 `/proc/PID/status` 的 `VmRSS/RssAnon/RssFile`；
- 从 containerd task rootfs 的 `findmnt` 结果解析 overlay upperdir，并统计 bytes/inode；
- 宿主机 `/proc/meminfo`、`/proc/vmstat` 和 memory PSI 快照；
- workload 自身的吞吐、P50/P95/P99、错误和服务启动时间。

### 2.4 多镜像同机合并

对每个 resident path，按 overlay lowerdir 顺序解析到实际 containerd snapshot 文件，再读取宿主机 `(st_dev, st_ino)`：

- 各镜像 lower hot set 直接求和得到同机驻留上界；
- 相同 inode 只取各用例最大 resident bytes，得到同机驻留下界；
- 因为没有保存逐页 bitmap，同一 inode 被两个 workload 访问不同页时，真实 union 位于上下界之间。

同宿主机、相同 lower inode 的多个容器本来就共享 page cache，因此结果不得按同机容器副本数相乘。集群机会近似为每个使用该镜像的节点一份 hot set。

## 3. 镜像与 workload

| 用例 | ARM64 manifest digest | workload |
|---|---|---|
| Redis 7.4 | `sha256:31fb2d98f60123bf0cf70b73b685304843ebce2daaad95f7c7555af14c3cfc58` | 每阶段重启 Redis；50 万 SET + 50 万 GET，64 clients，pipeline 16，1 KiB value，100 万 keyspace |
| MySQL 8.4 | `sha256:28474aba911e2a51b664e5c77d6ffe5657ae4b27550ff588e8c54db426023c44` | 10 万行 InnoDB 表；16 个长连接执行 3.2 万 SELECT + 3.2 万 UPDATE；512 MiB buffer pool |
| OTel Java Ad | `sha256:a1f09618595d14ff51ffa3c4140128f2155c0f3dc0cfacb1933309b25a43b469` | 原始 JDK 21 服务和 Java Agent；本地 Flagd；`ghz` 32 并发执行 1 万次成功 `GetAds` RPC |
| OTel Python Recommendation | `sha256:f6704465b8bedbd1f9dad45561a063b98ae1e8f158c95332ee432bff48244439` | 原始服务；固定 Product Catalog stub；本地 Flagd；32 并发执行 1 万次成功 RPC |
| OTel mock LLM | `sha256:b841451279fc34334cac883d413961fca204f7fe36218bfddf9305cdfb7de451` | 原始 Flask/OpenFeature 依赖；固定 chat-completion 请求；32 并发执行 2,000 次成功 HTTP 请求 |
| OpenHands Agent Canvas | `sha256:ed2af236d1de716fe320531a461579c257b12450ab1855a5d3bc32bfb7b6909f` | 启动 agent-server、automation(SQLite) 和前端代理；并发访问首页、health 和 OpenAPI 1,000 次；不调用 LLM |
| Ollama | `sha256:8f3760da9e4f897f1f9e40e475132910f3842c582332a64717841e3d0e2041d2` | 启动 Ollama 服务；串行执行 200 次 `ollama list`；不安装模型、不加载模型权重、不执行推理 |

## 4. 容量结果

以下全部使用 hardlink 去重后的 cold 结果；warm lower resident 与 cold 相同。

| 用例 | lower logical | lower hot set | lower resident | cgroup peak | lower / cgroup peak | cold upperdir |
|---|---:|---:|---:|---:|---:|---:|
| Redis 7.4 | 127.66 MiB | 23.75 MiB | 18.61% | 558.82 MiB | 4.25% | 0.02 MiB |
| MySQL 8.4 | 747.09 MiB | 96.41 MiB | 12.90% | 533.86 MiB | 18.06% | 255.0 MiB |
| OTel Java Ad | 372.17 MiB | 125.62 MiB | 33.75% | 1,032.84 MiB | 12.16% | 0.02 MiB |
| OTel Recommendation | 93.45 MiB | 45.23 MiB | 48.41% | 172.37 MiB | 26.24% | 4.45 MiB |
| OTel mock LLM | 90.20 MiB | 45.14 MiB | 50.04% | 170.75 MiB | 26.44% | 4.44 MiB |
| OpenHands Agent Canvas | 3,850.82 MiB | 353.45 MiB | 9.18% | 1,267.86 MiB | 27.88% | 56.0 MiB |
| Ollama（无模型） | 4,017.33 MiB | 92.03 MiB | 2.29% | 215.00 MiB | 42.80% | 0.04 MiB |

七个用例直接相加的 lower hot set 上界为 **781.63 MiB/节点**。按实际 containerd lower inode 合并后的下界为 **762.31 MiB/节点**；184 个 inode 被多个镜像复用，最大重叠约 19.32 MiB。Ollama 与前六个镜像没有复用相同的 containerd lower inode，因此没有扩大该重叠量。

这个区间只代表同时活跃上述七个 workload 的节点。不同部署组合应按实际活跃镜像重新计算，不能把镜像逻辑大小当作节省量。

## 5. 业务基线

| 用例 | cold | warm | 说明 |
|---|---|---|---|
| Redis | SET 398.1k、GET 604.6k RPS；P99 4.11/2.19 ms | SET 394.9k、GET 593.1k RPS；P99 4.18/2.26 ms | Redis 进程 RSS 527.6 MiB，主要是匿名 key/value 数据 |
| MySQL | 64k query / 2.194 s，约 29.2k qps | 64k query / 2.166 s，约 29.5k qps | cold 初始化和启动 8.26 s，warm 启动 1.04 s；数据目录不属于 lower |
| OTel Java Ad | 3,794.8 RPS，P99 33.21 ms | 3,884.0 RPS，P99 23.32 ms | 10,000/10,000 RPC 为 `OK` |
| OTel Recommendation | 451.5 RPS，P99 92.33 ms | 448.5 RPS，P99 91.33 ms | 10,000/10,000 RPC 为 `OK`；依赖为固定 stub |
| OTel mock LLM | 272.1 RPS，P99 3,581.6 ms | 261.1 RPS，P99 3,615.1 ms | 2,000/2,000 HTTP 200；Flask/Flagd 路径存在明显尾延迟，只作基线 |
| OpenHands | 296.7 RPS，P99 1,045 ms | 298.4 RPS，P99 1,007 ms | 1,000/1,000 HTTP 200；混合首页、health 和 OpenAPI，P99 不代表 Agent token 延迟 |
| Ollama（无模型） | 启动 0.342 s；平均 47.67 ms，P99 52.74 ms | 启动 0.240 s；平均 43.76 ms，P99 51.28 ms | 每阶段 200/200 次 `ollama list` 成功；串行客户端；不代表模型加载或推理延迟 |

这些性能数值仅证明 workload 执行成功并提供 B0 基线。没有 B2 对照时，不得据此判断 UB/DAX 性能代价。

## 6. 热点与收益评估

### Redis：低收益对照

lower hot set 仅 23.75 MiB，而 Redis 进程约 520 MiB 为匿名业务数据。snapshotter 能影响的比例约 4.25%，不适合作为核心收益场景。热点主要是 `redis-server`、`redis-cli`、`redis-benchmark`、OpenSSL 和 libc。

### MySQL：中等 lower 收益，必须隔离数据页

lower hot set 96.41 MiB，主要是 `mysqld`、客户端和共享库。cold upperdir 约 255 MiB，warm 后约 275 MiB；InnoDB 文件、buffer pool 和数据库 page cache 不会因 image snapshotter 自动消失。该场景可验证运行时 lower 收益，但不能用数据库总缓存宣称 ubcache 收益。

### Java 微服务：绝对值较高，匿名内存仍占主导

lower hot set 125.62 MiB，主要来自 JDK modules、`libjvm.so`、CDS archive、OpenTelemetry Java Agent 和业务 JAR。绝对容量值得验证，但在该压测 cgroup 中只占约 12.16%。

### Python 微服务：绝对值小，相对占比高

Recommendation 和 mock LLM 各形成约 45 MiB lower hot set，约占测试 cgroup peak 的 26%。热点高度相似，包括 grpc C extension、libpython、OpenSSL、yaml 和 OpenFeature 依赖。两镜像共享部分 containerd base snapshot，联合部署时不能直接按 90 MiB 计算。

### OpenHands：本批最有价值的目标

hardlink 去重后 lower hot set 为 353.45 MiB，约占测试 cgroup peak 的 27.88%。热点包括：

- `openhands-agent-server`：98.9 MiB resident；
- Node：88.0 MiB resident；
- grpc、cryptography、tokenizers、libpython 等 Python/native 依赖。

未去重路径统计会得到约 477 MiB；差异来自 uv cache 与安装目录的 hardlink，因此最终结论必须使用 353.45 MiB。当前 workload 未执行真实 Agent 对话、Chromium 操作和代码工具链，353.45 MiB 更接近控制面工作集，不是完整 Agent 任务的上界。

### Ollama：镜像大，但无模型服务只触发少量运行时页

Ollama 镜像 lower logical 为 3.92 GiB，其中包含多套 CUDA 库；无模型服务和 `list` API 只形成 92.03 MiB lower hot set。热点为 `/usr/bin/ollama`（33.94 MiB resident）、libllama/ggml、系统共享库，以及每个只驻留约 6 MiB 的若干 CUDA 大文件。Ollama 进程 `VmRSS` 为 38.0 MiB，测试 cgroup peak 为 215.00 MiB。

该结果只说明镜像内服务运行时页的机会，不能外推到模型场景。模型权重没有进入 OCI lower，后续若通过 UB 共享模型，需要作为独立的只读对象或 volume 数据路径评估；模型加载、推理 KV cache、GPU/CPU 后端选择和首 token 延迟也必须另建测试项。

## 7. 当前判断

1. 收益空间真实存在，但强烈依赖 workload。单镜像观测范围从 Redis 的 23.75 MiB 到 OpenHands 的 353.45 MiB；镜像逻辑大小与运行时 lower hot set 没有线性关系，Ollama 是明显例子。
2. OpenHands、Java 微服务和 MySQL 是后续 DAX 对照最有价值的三个真实镜像；Redis 是必要负向对照。
3. Python 微服务单体绝对收益有限，但在轻量服务 cgroup 中占比可达约 26%；多服务部署必须按共享 lower inode 计算 union。
4. 这些值是“每个活跃节点约一份”的容量机会，不是“每容器一份”。
5. 是否值得进入通用 PoC，仍取决于 B2 能否移除这些本地页，以及 warm read/P99 相对 B0 的退化是否处于既定阈值。

## 8. 已知限制

- 每个 case 当前只有一次 cold/warm 探索性运行，没有 5 次重复、中位数和离散程度，不能作为正式性能结论。
- 业务客户端位于被测 cgroup，cgroup peak 包含客户端；lower manifest 排除了工具挂载。
- OTel Flagd 位于独立容器，不计入服务 cgroup；完整栈容量需要另行统计所有依赖。
- Recommendation 使用固定 Product Catalog stub，验证的是该服务业务路径，不是完整电商拓扑。
- OpenHands 未配置 LLM，也未执行 Agent task；结果不包含模型 API、sandbox workspace 或工具执行产生的额外工作集。
- Ollama 没有安装模型，只验证服务启动和 `list` API；结果不包含模型权重、模型加载或推理路径。
- 多镜像 union 只有 inode 级上下界，没有逐页 bitmap，因此不报告伪精确单值。

## 9. 原始数据

- `redis-7.4-dedupe/20260714T133854Z/`
- `mysql-8.4-dedupe/20260714T133959Z/`
- `otel-ad-java-dedupe/20260714T134044Z/`
- `otel-recommendation-python-dedupe/20260714T134120Z/`
- `otel-llm-python-dedupe/20260714T134229Z/`
- `openhands-agent-canvas-dedupe/20260714T134301Z/`
- `ollama-no-model-dedupe/20260714T135621Z/`
- `batch2-dedupe-inodes.tsv`：七个用例的宿主机 lower inode 映射，用于计算同机 union 上下界。

每个目录包含 manifest、targeted eviction、cold/warm lower scan、top-50 热文件、cgroup 200 ms 时序、upperdir、服务进程、业务结果和宿主机快照。
