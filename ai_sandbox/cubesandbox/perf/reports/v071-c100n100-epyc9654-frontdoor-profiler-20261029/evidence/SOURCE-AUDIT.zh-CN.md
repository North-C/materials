# EPYC9654 F1 入口时延源码审计与窄窗口 SQL 证据

日期：2026-10-29。类型与状态：**固定源码审计及既有日志验证完成；连接池、日志锁及请求调度的耗时占比尚待 trace 验证。** 对象为 EPYC9654 机器的 F1 轮；本文依据当时的源码快照与指定 5 秒 journal 窗口，公开整理未新增构建、部署、重启或压测。

## 结论与证据边界

F1 的 Master middleware 与 `cube-e2e` 差距主要位于业务创建前的模板解析。阶段分析通过同一 Master 请求标识关联，得到正式 100 请求的 `templateresolve` mean 26.821 ms，其中 request 2.310、locality 15.462、bind 7.706 ms；middleware 减去 cube-e2e 和模板解析后，残差 mean 1.981 ms。这里引用[逐轮阶段数据](../data/stage-rounds.csv)中的 `F-b1-p5`，没有再次聚合阶段数据，也没有把残差命名为日志耗时。

源码确认：**template cache hit / locality hit 并不意味着不访问数据库。** 本场景普通 app-template 命中路径仍串行执行 snapshot miss 探测、replica 点查、replica 列表查询。实际共享 MySQL 连接池配置为 max_open_conns=20、max_idle_conns=5（测试时只读回读，见[构建与环境清单](BUILD-AND-ENVIRONMENT.zh-CN.md)）；100 并发下连接申请排队是优先验证对象。源码和日志尚不能证明这 20 个连接实际饱和，更不能把所有 locality/bind 时间等同于 MySQL 服务端执行时间。

窄窗口日志进一步证实：`snapshot_table.go:29` 的 expected record-not-found 查询实际发生，105 条 SQL 调用耗时 mean 6.339、median 2.714、P95 14.960、max 29.837 ms。GORM 在打印日志前读取 elapsed，故这些毫秒级耗时不能全部解释为**该条**日志的格式化、锁等待或写入。日志自身开销仍可能另外增加，并且其他请求的日志、调度及 DB 连接竞争都可能影响 SQL 调用墙钟时间。

## 固定来源

源码仓库 `https://gitcode.com/boostkit/CubeSandbox`；上游基点 `2babb6f7405677c04b7fed1563c6a5d53a8e771b`，tree `608397465872e2050e823fd4ebf1207d3d1208f0`。

按顺序应用：

1. EPYC9654 机器 原现场 3 文件 dirty 补丁，SHA256 `d10d4366db67aaeb0acfae63fe16058152ba829cd5dff25b8e5aae7cc3192c13`。形成 U commit `9ddc0a6f4501d72c155bfbb4f0b1a7054b06aeb0`、tree `285f21316b8fbbe1b402a50ae94d660e4582c414`。
2. profiler commit `f1f6b0156d7b0c53094326f04527bb45aaeca382` 的 `frontdoor-server.patch`，SHA256 `c24254fc66a1d1e3d1536f0029d64eb8dd07bb475a6369a861860ddf58683eeb`。形成 P commit `747e5c1b71d992f780df4a1e7aa12b5bfa82b96a`、tree `a679b91d35a1a3cc317c21f0dbd566397dc8b446`。

本审计读取构建机使用的同一 P 隔离源码，审计时回读工作树 clean。U/P commit 是构建快照，不是产品仓库已推送提交。公开[构建与环境清单](BUILD-AND-ENVIRONMENT.zh-CN.md)保留来源摘要；完整 source bundle 与原始构建清单未公开，见[未公开证据](../PUBLICATION.md#unpublished)。[源码摘录](source-excerpts.json)记录 26 个文件的完整 SHA256、原始行号及相关代码。GORM 为构建缓存中精确的 `gorm.io/gorm@v1.25.10`，见[模块源码摘录](gorm-source-excerpts.json)。以下路径与行号均针对该固定 P 源码。

## 三次 SQL 的调用序列

| 顺序 | 外层阶段 | 实际操作与源码证据 | 命中含义 |
| --- | --- | --- | --- |
| 0 | request | `store.go:1723–1730` 从 definition request cache 取克隆并输出 cachehit metric；`cache.go:135–150` 仍克隆请求 | 排除模板定义获取的 miss 路径，不排除后续 SQL |
| 1 | locality | `cubeboxutil.go:453–456,545–550` 先执行 `skipTemplateLocalityReady`；`snapshot_table.go:189–190` → `getSnapshotRecord:28–29` 查询 snapshot 表 | 此调用发生在判断模板 kind 之前；普通 app-template 通常返回预期 not-found |
| 2 | locality | `store.go:2046–2058` 对本地镜像命中节点调用 `isTemplateReplicaSchedulable`；后者 `2032–2034` 按 template/node 点查 replica | `templatelocalityhit` 是查询后才记录，不代表查询已省略 |
| 3 | bind | `cubeboxutil.go:498–500,764–766` → `ResolveTemplateReadyReplica`；`store.go:2009–2010,1799–1807` 列出模板 replica 后筛选 ready/preferred node | 没有复用上一步 replica 查询结果；bind 还包含日志、注解及请求字段合并 |

因此 `tpl-resolve-locality` 比内部 `templatelocality` 多出 snapshot 探测及内层 metric 日志等时间；不能将这个差值直接写成纯 snapshot SQL。热点路径通常三次 SELECT，节点循环或 miss 分支还可能更多。普通 app-template 与真正 snapshot-kind 的引用计数分支不同，不应把后者锁/写操作机械归入当前场景。

DB 使用共享池：`templatecenter/store.go:341–352` → `base/db/db.go:21–23` 返回 `dao.Default()`；`base/db/db.go:31–48` 传递池参数；`pkgs/cubedb/dao/driver/mysql/mysql.go:45–66` 对同一个 `sql.DB` 执行 `SetMaxIdleConns`、`SetMaxOpenConns` 后交给 GORM。20 是共享池最大 open 数，并非每请求 20 个连接，也不是已观测到的活跃数。5 是可保留空闲连接上限，三个串行 warmup 不保证预先建立 20 个连接。

未找到生产代码注册 `sql.DB.Stats` 的 WaitCount/WaitDuration、go_sql_stats 或等价池指标；`/metrics` 默认注册并不自动产生 DBStats。F1 已采的 metrics 来自 Cubelet，不能用作 Master SQL 池证据。

## expected miss 的现场验证

只读 `cube-sandbox-cubemaster.service` 在 `2026-10-29 04:39:06–04:39:11 UTC` 的 journal。读取 318 条 journal entries；MESSAGE 为字节数组，解码后去除 ANSI 颜色。只接受相邻非空的 `snapshot_table.go:28/29 + record not found` 与 snapshot SQL 行，来源进程一致，时间差不超过 1 秒。实际 source 均为 `:29`，即 GORM `First` 终止行；初始定位的 `:28` 是调用起始行。

| 指标 | 值 |
| --- | ---: |
| matched snapshot miss | 105 |
| unmatched source marker / unattributed snapshot query | 0 / 0 |
| mean / median | 6.339 / 2.714 ms |
| P95（nearest-rank）/ max | 14.960 / 29.837 ms |
| min | 0.221 ms |

[安全提取器](extract-snapshot-miss-log-stats.py)和[逐条安全元数据](snapshot-miss-log-stats.json)可复核；只保留时间、来源行、错误类型、表名、rows、elapsed，不保存 SQL 文本、请求内容或整段 journal。外层窗口包含 warmup 及其他潜在操作，实际 105 条不等于正式 100 请求，也不能直接等于 3 warmup + 100 formal。日志缺少 RequestId，未按顺序强配；该分布不能与正式 100 的阶段均值相减。

MySQL driver 用 `gorm.Config{}`（mysql.go:61），GORM `gorm.go:153–155` 补默认 logger；`logger/logger.go:75–80` 默认 Warn 且 `IgnoreRecordNotFoundError=false`，输出到 stdout。`Trace:160–167` 在 `fc()` SQL 格式化、`utils.FileWithLineNum()` 调用栈遍历及 `Printf` **之前**取得 elapsed。故该计时涵盖 GORM/database 调用及其等待，但不等于数据库服务端执行时间，也不含该条日志后续打印耗时。现场 `record not found` 并非失败创建的证据，而是普通模板走 snapshot 探测时的预期结果。

## 日志路径及计时边界

CubeLog 的 metric 路径是同步调用：`base/log/log.go:90–132` DeepCopy 后调用 `CubeLog.Trace`；`pkgs/CubeLog/metric.go:189–214` 在 enable_log_metric 时交给 trace logger。`Entry.writef:253–280` 在锁前格式化/JSON 编码，`291–312` 持每个 logger 的 mutex 执行 writer.Write（当前默认非 asyncFlush 路径）。请求日志和 stat 日志分别设置 writer（`base/log/log.go:40–46`），不是全局同一把文件锁。

`RollFileWriter` 普通路径是追加文件写入（`logwriter.go:59–84`），并包含定期重新打开、达到大小阈值时轮转逻辑；没有每条日志 fsync。若 trace 出现该锁或文件写阻塞，可据此量化，当前不能仅凭同步写源码就宣称它是主要瓶颈。默认 config.asyncFlush=false；审计范围内未找到生产调用 CubeLog.Init 将其改为 true。

现场 log.level=info 时，CubeLog 只有 debug 才开启的 `reportCaller` 不生效（`base/log/log.go:23–28`、`Entry.getCallerPath:120–126`）。但 **GORM 自己的 `utils.FileWithLineNum` 仍执行 runtime.Callers**，不受 CubeLog 开关控制。

阶段计时常在自身 metric 日志前截断：cachehit 日志会计入外层 request；locality 内层 defer 日志会计入外层 locality；bind 的日志和字段合并计入 bind。不能把命名为 metric 的代码当作全部异步。

`sandbox_run.go:116` 才启动 cube-e2e；`163–166` 等待业务完成后取 endTime，再异步启动 dealMetric；该异步函数用已保存起止值计算 cube-e2e（`523–526`）。因此 cube-e2e 排除模板解析以及函数返回 defer 的结果日志，而异步 metric goroutine 仍会与其他请求竞争 CPU/日志锁。

Master ingress 位于 Gin middleware（`gin_middleware.go:34–35`），并不是 accept/read 开始。响应端 `frontdoor.go:82–110` 先记录 master_response_ready 再编码/输出 profiler 日志；middleware 其后还执行 CubeLog.Trace（`:80–83`）。因此 master 总时间不包括自身末尾 profiler/outer Trace 写入，回传段可能包含这部分与 HTTP flush/调度，不能称为纯网络耗时。

## API→Master 的 16.635 ms 不能直接称作网络 RTT

`CubeAPI/src/cubemaster/mod.rs:65–73` 在 URL 构造、request JSON 编码、请求发送之前记录 api_master_dispatch；对端 master_ingress 在 HTTP 连接接入、头部解析及 Gin 路由之后才记录。该段包括序列化、reqwest 连接复用/新建、DNS/connect/请求 write、Tokio 调度、网络、Master accept/HTTP 解析/调度。

`CubeAPI/src/state.rs:42–48` 使用共享 reqwest client；`pool_max_idle_per_host(100)` 是每 host 空闲连接保留上限，不是活跃请求并发上限。未发现此路径的应用级 semaphore。`main.rs:188–198` 构建多线程 Tokio，实际 worker_threads 必须另从安全配置回读，不能拿源码默认替代现场值。

API 文件日志经 `logging/file.rs:57–59,100–106,130–135` 的 unbounded channel 交给后台 task 写；这与 Master CubeLog 的同步写不同。三个串行 warmup 可能只复用少量连接，不能证明正式 100 请求已预建所有 API→Master 或 DB 连接。这里只是可验证机制，尚没有证据把本轮 16.635 ms 主要归因于新连接或运行时调度。

## 最小追加诊断：现有 Go trace 优先

Master 已编入 `net/http/pprof`；`cmd/cubemaster/app/main.go:283–310` 仅在 `cfg.Common.Debug.Address` 非空时监听。配置为 YAML `common.debug.address`（`config.go:73,148–150` 字段未指定 yaml tag，按默认小写字段名读取），源码默认零值为空，未找到地址 CLI 覆盖；不是 `debug_address`。已有 `/debug/pprof/profile`、`/debug/pprof/trace`、pprof index 子树及 `/debug/vars`。源码没有调用 SetMutexProfileFraction/SetBlockProfileRate，因此默认 block/mutex profile 可能没有样本。

正式矩阵结束后拟进行单独诊断，但前置环境检查发现外部编译活动，诊断退出；随后只读检查发现 API/Master 版本已发生变化。这次追加诊断没有修改 debug 配置或服务，也没有取得真实 trace。[诊断停止记录未公开](../PUBLICATION.md#unpublished)。因此下表仅列后续可验证方法，不能当作已执行的实测证据。

| 诊断证据 | 能区分什么 | 判定限制 |
| --- | --- | --- |
| 现有 `/debug/pprof/trace?seconds=5` 覆盖额外 c100，离线 `go tool trace -pprof=sync/net/sched` | `database/sql.(*DB).conn` 的连接申请等待；MySQL readPacket/netpoll；CubeLog writef mutex、文件 syscall；goroutine runnable 延迟 | 需要看完整调用栈及请求活跃窗口；aggregate 阻塞时间是跨 goroutine 累加，不等于每请求墙钟 |
| 另轮 CPU pprof / perf CPU | GORM SQL 格式化/Callers、JSON、日志格式化、HTTP/SQL 驱动 CPU 消耗 | CPU 样本不能证明连接池等待或日志阻塞；诊断开销单列 |
| 已有 perf/eBPF 的 offcpu 栈 | 文件写、futex 等线程级等待 | Go goroutine 挂起后线程可执行其他 goroutine，线程 offcpu 不能替代 Go trace；看到 futex 不足以认定某把日志锁 |
| API/Master socket 连接与发送/接收时间元数据 | 是否新建连接、API 请求发出前等待还是 Master 收包后等待 | 只采进程与连接的匿名关联、时间及字节数，不采 HTTP payload；无 Rust release 调试符号时不承诺完整用户栈 |

优先验证顺序：共享 SQL 池/SQL 调用等待 → GORM/CubeLog 同步日志成本及 Go runnable 延迟 → API 发送前与 Master ingress 前的连接/调度拆分。只有 trace 或直接 DBStats 能确认排队贡献后，才考虑针对性优化。减少多余 snapshot 探测、复用 replica 查询结果、降低预期 not-found 日志成本都是后续代码实验候选；本审计没有修改业务行为，也没有证明这些改动已有收益。


## 公开附件与可复核范围

- [源码摘录](source-excerpts.json)：26 个源文件的原始完整文件 SHA256、固定行号与相关代码；仅替换两处静态监听地址字面量，替换位置在 JSON 的 `publication.excerpt_redactions` 中列明。完整文件 SHA256 对应原源码字节，不是脱敏摘录文件的校验值。
- [GORM 摘录](gorm-source-excerpts.json)：固定模块 `gorm.io/gorm@v1.25.10` 的 3 个源文件及对应 SHA256、行号；只将构建机来源改为公开别名，代码摘录不变。
- [105 条安全 SQL 时延元数据](snapshot-miss-log-stats.json)：保留原提取结果的时间、源码行号、错误类别、表名、rows 与 elapsed；不包含原始 SID、请求标识、进程编号、SQL 文本或日志正文。可离线重算统计量，无法从本附件恢复正式请求归属。
- [提取器](extract-snapshot-miss-log-stats.py)：保留原提取代码，依赖 Python 3 标准库与 `journalctl`，在日志所在机器读取固定服务、固定窗口；代码不部署、不重启、不执行压测，也不连接远程。公开整理只做语法与合成输入验证，没有重新运行现场日志采集。

完整源码包、原始 journal、原始请求日志及未取得的 runtime trace 不作为本公开包附件；各项状态见[未公开证据](../PUBLICATION.md#unpublished)。公开样本能够复核本表 105 条观测的统计量与提取规则，但不能独立核验原始日志完整性、现场连接池占用或逐请求因果归属。发布附件字节的校验值以专题发布清单为准。
