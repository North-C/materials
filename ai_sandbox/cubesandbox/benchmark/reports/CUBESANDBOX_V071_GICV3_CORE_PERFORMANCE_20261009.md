---
title: CubeSandbox v0.7.1 GICv3 核心性能测试结果
date: 2026-10-09
description: Kunpeng 950 ARM64 单机环境下的 Template 创建、密度、Snapshot、Rollback、Clone 与 Pause/Resume 实测结果。
---
# CubeSandbox v0.7.1 GICv3 核心性能测试结果

公开归档版：测试日期为2026-10-08–09，归档日期为2026-10-10。测量数值、轮数和失败边界不变；仅脱敏站点身份、部署路径与本地证据入口。详见[证据清单](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md)。

CSV下载：[测试结果](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.csv) · [环境与测试条件](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.environment.csv) · [字段说明](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#csv-字段与行数)。

## 一、测试概况

测试于北京时间 **2026年10月8日晚至10月9日凌晨**，在 `benchmark-host` 单机完成。本报告按[社区性能报告](https://docs.cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)的测试项组织，仅呈现本轮环境、方法与结果，不混入历史版本成绩和排障过程。

本轮完成 **32个非密度测试档位**；另进行了两次目标1500实例的密度测试，均完整验证到1000实例，未达到1500。本文是已有数据的独立整理，没有重新执行测试。


| 测试项             | 完成情况                   | 代表性结果                                      |
| --------------- | ---------------------- | ------------------------------------------ |
| Template创建      | 7/7档；1620/1620正式请求成功   | c50n500平均163.98ms，P95 232.32ms             |
| 单机密度            | 两次完整健康验证到1000；1500目标未达 | WFI=Y时，1000实例的内存差值摊销26.46MiB/实例            |
| Snapshot并发      | 3/3档                   | c1平均40.9ms；c10整批平均90.0ms                   |
| 脏页量与Snapshot/恢复 | 8/8档，每档3轮              | 写入1024MiB时，Snapshot平均351.7ms，热恢复创建平均69.6ms |
| 从Snapshot并发创建   | 4/4档                   | c50整批平均214.9ms                             |
| Rollback        | 3/3档                   | c10整批平均258.3ms                             |
| Clone           | 4/4档                   | n100c20整批平均745.1ms                         |
| Pause / Resume  | 3/3档，每档同时测两个操作         | c10整批平均258.4 / 239.1ms                     |


除明确标为密度第一次的WFI=N数据外，本文性能结果均在 **GICv3、WFI=Y** 条件下取得。不同测试项的计时单位并不相同：创建表是逐请求延迟，生命周期并发表是整批耗时。

## 二、测试环境与统一条件

### 2.1 测试机器


| 项目                 | 实际环境                                                        |
| ------------------ | ----------------------------------------------------------- |
| 节点                 | `benchmark-host`，ARM64单机；压测客户端与服务端同机                         |
| CPU                | HiSilicon Kunpeng 950 7592C；BIOS标称2.3GHz                    |
| CPU拓扑              | 2 Socket × 96 Core × 2 Thread = **384逻辑CPU**                |
| NUMA               | 4节点：0–95、96–191、192–287、288–383                             |
| 物理内存               | OS可见2261.41GiB，约2.21TiB；`MemTotal=2371257028KiB`            |
| 操作系统               | openEuler 24.03 LTS-SP3，aarch64                             |
| 内核                 | `6.6.0-9999.sp3.vnmi.xarray.d383a36d`                       |
| 数据盘                | `/dev/nvme3n1`，XFS，挂载 `/data/cubelet`；文件系统约3.20TB / 2.91TiB |
| 数据盘余量              | 测试收尾约2.69TB可用；每档门槛至少20GiB                                   |
| 日志盘                | `/data/log`与根分区同盘；测试收尾约31.47GB可用；门槛至少8GiB                   |
| KVM中断配置            | GICv3；本boot日志明确GICv4关闭，DVMBM/IPIV关闭                         |
| WFI / halt polling | 非密度核心测试均为 `force_wfi_trap=Y`；`halt_poll_ns=500000`          |
| CPU放置              | 本轮未做显式绑核；所查控制服务CPU允许集0–383、NUMA允许集0–3                       |
| boot ID            | `boot-redacted`                      |


CPU型号与拓扑于10月9日上午只读补采，boot ID与测试时一致；动态空间/负载采用测试期间原始记录，不用补采时状态倒填。硬件来源见[现场清单（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)。

### 2.2 软件、服务与资源配置


| 项目            | 测试条件                                                               |
| ------------- | ------------------------------------------------------------------ |
| CubeSandbox   | 官方v0.7.1，源码 `31d911e430fdf8a8879bd062b8e78066c1a8e89d`             |
| 组件身份          | Cubelet/Master/API哈希在测试前后相同；运行中的Shim已核对官方v0.7.1哈希                  |
| API / Proxy   | `http://127.0.0.1:3000` / `benchmark-host:18080`                    |
| Master创建并发限制  | `create_concurrent_limit=100`                                      |
| CPU逻辑额度       | `mcpu_limit=3020000m`，Master库存3020核                                |
| 内存逻辑额度        | 配置 `3100000Mi`，Master有效库存3089760MiB                                |
| TAP预建         | 1500；每档开始前要求Ready≥1500且无Active/Cleaning等状态                         |
| 宿主机内存保留       | 套件设定至少64GiB实际可用内存                                                  |
| MySQL / Redis | MySQL 8.0.46 / Redis 7.4.9；同机Docker依赖服务                            |
| 数据库条件         | 保留迁移版本 `20260916120000`；Snapshot相关测试在单列默认值兼容配置后执行，非全新初始化的v0.7.1数据库 |
| Python工具环境    | Python3.11.6，cubesandbox SDK0.7.0，requests2.34.2，urllib3 2.7.0     |
| Guest数据面依赖    | httpx0.28.1 / httpcore1.0.9；未使用历史共享AsyncClient压测脚本                 |


CPU/内存额度是调度超配额度，不代表物理资源增加。数据库兼容核查另见[独立说明（本地诊断索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#环境条件)，不作为本报告的性能归因。

### 2.3 镜像与沙箱规格


| 项目         | 实际设置                                                                      |
| ---------- | ------------------------------------------------------------------------- |
| Template   | `tpl-redacted`，本轮专用                                       |
| 沙箱规格       | **2vCPU / 2048MiB**                                                       |
| 原始镜像       | `cube-sandbox-cn.tencentcloudcr.com/cube-sandbox/sandbox-code`            |
| 固定镜像digest | `sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d` |
| 可写层        | 2GiB                                                                      |
| 暴露端口       | 49999、49983                                                               |
| 健康探针       | 49999，`/health`；Template构建与Guest代码执行预检均通过                                 |
| 负载         | 基础sandbox-code环境；除脏页测试外，未添加业务负载；Rollback/Clone未增加额外脏页写入                   |


镜像使用固定digest，不能用测试后的 `latest` 指向替代本轮身份。Template已构建完成；以下创建时间**不包含镜像拉取和Template构建**。

### 2.4 测试隔离与指标定义

各测试档串行运行。用户提供独占窗口；每档清理后重新等待资源池恢复。开始前要求连续5次检查满足：无KVM/task/Shim、未见识别到的编译/压测进程、blocked=0、load1&lt;5，并满足TAP和磁盘门槛。


| 指标              | 本报告含义                                             |
| --------------- | ------------------------------------------------- |
| avg / min / max | 对本项实际样本求平均/最小/最大；默认单位ms                           |
| P95 / P99       | 原生工具输出的分位数；不能跨测试项混用样本单位                           |
| Template创建延迟    | 单个Go客户端请求发出至HTTP `Client.Do` 返回；不包含独立的Guest应用就绪验证 |
| wall            | 生命周期一整批操作从计时开始到所有SDK调用完成；包括该批并发调度开销               |
| per             | 批次wall除以该批操作数的摊销时间，**不是逐请求平均延迟**                  |
| QPS             | 原生工具成功请求数除以该档正式计时总时长                              |
| MiB / GiB       | 分别为2²⁰ / 2³⁰字节；内存差值不是进程RSS                        |


3.2的 `-w 3` 实际表示3次串行预热创建，不是3轮完整N请求。每档只有一次正式原生调用。Python生命周期脚本按各自原逻辑预热，正式轮数在各表列出；2/3/5轮样本的nearest-rank P95均等于最大值。

## 三、基于 Template 创建沙箱

### 3.1 工具与执行方式

创建和密度测试直接调用**官方Go `cube-bench`**，源码为v0.7.1。外围套件只负责选档、门禁、结果保存和精确清理，没有用Python/HTTPX客户端替代创建压测。

测量二进制（路径为公开占位示意）：`/opt/cube-perf-evidence/suite-v3/cube-bench-v071-linux-arm64`。SHA256：`d7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d`。

以下保留本轮有效参数，主机名、Template ID和部署路径使用公开占位名，认证值不展示。示例不是实测环境的逐字节配置，复跑须替换这些占位名，不能跳过独占确认、资源检查或清理。

```sh
export E2B_API_URL=http://127.0.0.1:3000
export CUBE_API_URL=http://127.0.0.1:3000
export CUBE_PROXY_NODE_IP=benchmark-host
export CUBE_PROXY_PORT_HTTP=18080
export CUBE_TEMPLATE_ID=tpl-redacted
# E2B_API_KEY / CUBE_API_KEY 使用本地测试环境授权值，不在报告保存。
cd /opt/cube-perf-evidence/suite-v3
```

### 3.2 启动延迟与并发扩展

每档保持创建出的沙箱存活（create-only），该档结束后再清理；不同档位不叠加实例。请求均为默认 `network-policy=none`。

```sh
RESULT_DIR=/path/to/new-results  # 替换为已准备的新结果目录
./cube-bench-v071-linux-arm64 -c 1   -n 20  -w 3 -m create-only --no-tui -o "$RESULT_DIR/c1n20.json"
./cube-bench-v071-linux-arm64 -c 10  -n 200 -w 3 -m create-only --no-tui -o "$RESULT_DIR/c10n200.json"
./cube-bench-v071-linux-arm64 -c 20  -n 300 -w 3 -m create-only --no-tui -o "$RESULT_DIR/c20n300.json"
./cube-bench-v071-linux-arm64 -c 50  -n 500 -w 3 -m create-only --no-tui -o "$RESULT_DIR/c50n500.json"
./cube-bench-v071-linux-arm64 -c 100 -n 100 -w 3 -m create-only --no-tui -o "$RESULT_DIR/c100n100.json"
./cube-bench-v071-linux-arm64 -c 200 -n 200 -w 3 -m create-only --no-tui -o "$RESULT_DIR/c200n200.json"
./cube-bench-v071-linux-arm64 -c 300 -n 300 -w 3 -m create-only --no-tui -o "$RESULT_DIR/c300n300.json"
```

本轮准确的绝对argv仅在本地原始report.json中留存。上面的命令清单不包含轮间清理步骤，不应当作无间隔批处理脚本直接粘贴执行。


| 档位       | 成功/请求数  | avg    | min    | P50    | P95     | P99     | max     | QPS    |
| -------- | -------: | ------: | ------: | ------: | -------: | -------: | -------: | ------: |
| c1n20    | 20/20   | 59.07  | 52.83  | 56.93  | 69.77   | 73.52   | 73.52   | 16.90  |
| c10n200  | 200/200 | 75.81  | 64.65  | 75.59  | 84.84   | 90.27   | 92.00   | 130.23 |
| c20n300  | 300/300 | 91.48  | 74.21  | 90.40  | 107.86  | 126.02  | 128.21  | 214.38 |
| c50n500  | 500/500 | 163.98 | 102.20 | 157.95 | 232.32  | 269.51  | 286.35  | 296.04 |
| c100n100 | 100/100 | 293.99 | 129.93 | 308.25 | 385.94  | 386.89  | 388.23  | 255.20 |
| c200n200 | 200/200 | 467.80 | 163.05 | 507.41 | 673.82  | 678.09  | 680.88  | 293.01 |
| c300n300 | 300/300 | 656.82 | 148.95 | 684.32 | 1021.23 | 1029.45 | 1031.33 | 289.63 |


单位：延迟ms，吞吐次/s。正式请求 **1620/1620成功，失败0**；预热另计21次，不进入上表。含预热的1641个自有实例均完成清理。

本表数值按十进制四舍五入保留两位小数；原始JSON未改写。后续Python表保留上游脚本输出的一位小数精度。

本轮c50n500吞吐296.04次/s；更高并发档的请求延迟明显增加。c100/n100至c300/n300属于短突发负载，与c50/n500的持续时间不同，不据一次结果确定“最佳并发”。[原始结果与逐档命令（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)

### 3.3 单机部署密度与内存开销

使用同一官方二进制，以 `-c 20 -n 20 -w 0 -m create-only` 分批递增；目标累计100、300、500、1000、1500。每个采样点检查全部实例归属/状态和Guest健康，等待15秒后读取宿主机 `MemAvailable`。

内存摊销定义为：`(空载MemAvailable − 当前MemAvailable) / 存活实例数`。它包含宿主机整体变化，不能等同于VM进程RSS或应用运行后的内存需求。


| 健康实例数 | WFI=N 可用内存GiB | WFI=N 摊销MiB/实例 | WFI=Y 可用内存GiB | WFI=Y 摊销MiB/实例 |
| -----: | -------------: | --------------: | -------------: | --------------: |
| 100   | 2172.35       | 20.35          | 2171.50       | 19.83          |
| 300   | 2167.46       | 23.45          | 2166.69       | 23.03          |
| 500   | 2161.38       | 26.52          | 2160.64       | 26.20          |
| 1000  | 2147.96       | 27.00          | 2147.60       | 26.46          |
| 1500  | 未完成           | —              | 未完成           | —              |



| 轮次    | 最高完整健康档 | 停止时批次目标 | 该批成功/请求 | 累计成功创建 | 最终目标   |
| ----- | -------: | -------: | -------: | ------: | ------ |
| WFI=N | 1000    | 1160    | 19/20   | 1159   | 1500未达 |
| WFI=Y | 1000    | 1200    | 16/20   | 1196   | 1500未达 |


两轮均出现创建失败后停止，成功实例均已清理。1159/1196只是累计创建成功数，**不是完整健康验收容量**；1000也不是生产容量上限承诺。第二轮附带只读vmstat采样，不把这两轮差异解释为纯WFI性能收益。

原始记录：[WFI=N（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据) · [WFI=Y（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)。

## 四、Snapshot 相关操作

4.1、4.3–4.6使用社区 `examples/snapshot-rollback-clone` Python脚本，固定来源 `cf571c65e41ca9f43012a1c3914575aef3cd6c21`。这些操作由SDK控制面执行，不是Go cube-bench；与历史共享HTTPX异步池压测路径不同。

除4.2使用下文明确的准备修正版外，五个生命周期测量脚本与该社区修订逐字节一致。命令工作目录示意为 `benchmark-host:/opt/cube-perf-evidence/suite-v3/examples/snapshot-rollback-clone`；统一环境同3.1。

### 4.1 Snapshot制作耗时与并发

每轮先准备C个独立沙箱，再并发调用Snapshot；计时不含源沙箱创建和后续清理。每档预热一整轮，正式5轮，轮间等待1秒。

```sh
python3 bench_snapshot_concurrency.py -c 1  -n 5
python3 bench_snapshot_concurrency.py -c 5  -n 5
python3 bench_snapshot_concurrency.py -c 10 -n 5
```


| 并发  | 正式轮数 | wall avg | wall min | wall P95 | wall max | per摊销 |
| ---: | ----: | --------: | --------: | --------: | --------: | -----: |
| 1   | 5    | 40.9     | 39.6     | 41.6     | 41.6     | 40.9  |
| 5   | 5    | 67.8     | 65.6     | 73.6     | 73.6     | 13.6  |
| 10  | 5    | 90.0     | 85.6     | 93.6     | 93.6     | 9.0   |


单位ms。共80次正式Snapshot操作完成（5×1+5×5+5×10），预热另计。c10整批平均90.0ms，每次Snapshot的摊销为9.0ms，不代表每个请求仅耗时9.0ms。[原始4.1日志（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)

### 4.2 Snapshot制作耗时与脏页写入量

每轮新建沙箱，在 `/dev/shm/dirty` 写指定数据后计时Snapshot。随后从该Snapshot恢复一次并销毁作预热，再计时第二次恢复创建；每档3个正式轮，轮间等待0.5秒。

统一准备条件：Guest可见 `/dev/shm` 显式扩至1536MiB，使用1MiB块写入，核对实际字节与文件大小。沙箱仍为2GiB内存；扩容不增加内存额度。工具标为“上游测试准备修正版”，准备不计入Snapshot时间。

```sh
cd /opt/cube-perf-evidence/suite-v5/examples/snapshot-rollback-clone
export VMM_LOG=/data/log/CubeVmm/vmm.log
# 各档为0、10、50、100、200、500、800、1024；每档之间由套件做门禁。
DIRTY_MIB=100  # 此例展示100MiB档
python3 bench_snapshot_dirty.py -d "$DIRTY_MIB" -n 3 --shm-size-mib 1536 --write-chunk-mib 1
```

Snapshot结果：


| Guest写入MiB | 内存快照实际写入均值MiB | Snapshot avg | min   | P95   | max   |
| ----------: | -------------: | ------------: | -----: | -----: | -----: |
| 0          | 22.8          | 52.5         | 50.8  | 53.9  | 53.9  |
| 10         | 38.7          | 72.8         | 70.6  | 76.4  | 76.4  |
| 50         | 76.6          | 81.9         | 79.9  | 84.5  | 84.5  |
| 100        | 130.7         | 104.0        | 99.8  | 111.7 | 111.7 |
| 200        | 229.5         | 126.6        | 114.5 | 134.4 | 134.4 |
| 500        | 536.2         | 211.2        | 198.4 | 220.6 | 220.6 |
| 800        | 845.1         | 288.5        | 263.2 | 313.2 | 313.2 |
| 1024       | 1074.8        | 351.7        | 341.1 | 369.5 | 369.5 |


同一Snapshot的热恢复创建结果：


| Guest写入MiB | 恢复avg | min  | P95  | max  |
| ----------: | -----: | ----: | ----: | ----: |
| 0          | 56.6  | 55.9 | 57.6 | 57.6 |
| 10         | 58.5  | 54.9 | 60.9 | 60.9 |
| 50         | 58.2  | 54.7 | 62.8 | 62.8 |
| 100        | 61.1  | 56.3 | 65.8 | 65.8 |
| 200        | 56.6  | 54.6 | 58.9 | 58.9 |
| 500        | 57.2  | 54.4 | 59.2 | 59.2 |
| 800        | 65.9  | 59.9 | 69.8 | 69.8 |
| 1024       | 69.6  | 58.2 | 81.1 | 81.1 |


时间单位ms；8档24轮均完成，21个非零写入轮均核对目标字节数。快照实际写入量来自本轮VMM日志，包含Guest其他内存变化，不等同于指定文件大小。

Snapshot平均耗时随写入量从52.5ms增至351.7ms；热恢复创建平均为56.6–69.6ms。这是SDK返回口径，不证明所有内存页已读入或应用已恢复就绪。旧准备条件的小档结果不混入本表。[原始日志及命令（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)

### 4.3 基于Snapshot并发创建沙箱

每档先制作Snapshot，再做一次单沙箱恢复预热。正式每轮从同一Snapshot并发创建C个沙箱，计时至该批SDK创建完成；每档3轮，轮间等待1秒，不计Snapshot准备与清理。

```sh
python3 bench_create_concurrency.py -c 1  -n 3
python3 bench_create_concurrency.py -c 10 -n 3
python3 bench_create_concurrency.py -c 20 -n 3
python3 bench_create_concurrency.py -c 50 -n 3
```


| 并发 / 每轮数量 | 正式轮数 | wall avg | wall min | wall P95 | wall max | per摊销 |
| ---------: | ----: | --------: | --------: | --------: | --------: | -----: |
| 1         | 3    | 64.5     | 59.1     | 68.3     | 68.3     | 64.5  |
| 10        | 3    | 92.3     | 91.7     | 93.0     | 93.0     | 9.2   |
| 20        | 3    | 121.3    | 119.7    | 122.8    | 122.8    | 6.1   |
| 50        | 3    | 214.9    | 206.8    | 219.3    | 219.3    | 4.3   |


单位ms。共243次正式创建完成，预热另计。c50整批平均214.9ms，与3.2的Template逐请求时间不是同一种指标。[原始4.3日志（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)

### 4.4 Rollback

每个沙箱先建立自己的checkpoint，再并发回滚。源沙箱及checkpoint准备不计时；本轮 `dirty_mb=0`，未增加回滚前写脏负载。每档整轮预热一次，正式5轮，轮间等待1秒。

```sh
python3 bench_rollback_concurrency.py -c 1  -n 5
python3 bench_rollback_concurrency.py -c 5  -n 5
python3 bench_rollback_concurrency.py -c 10 -n 5
```


| 并发  | 正式轮数 | wall avg | wall min | wall P95 | wall max | per摊销 |
| ---: | ----: | --------: | --------: | --------: | --------: | -----: |
| 1   | 5    | 105.1    | 98.1     | 116.0    | 116.0    | 105.1 |
| 5   | 5    | 176.2    | 152.1    | 207.0    | 207.0    | 35.2  |
| 10  | 5    | 258.3    | 249.9    | 270.1    | 270.1    | 25.8  |


单位ms。共80次正式Rollback完成；本项未测应用状态修改后的就绪时间，不扩大为业务一致性验证。[原始4.4日志（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)

### 4.5 Clone

每轮准备一个源沙箱，计时 `src.clone(n=N, concurrency=C)` 整体返回。本轮 `dirty_mb=0`；每档整轮预热一次，正式轮数见表，轮间等待1秒。计时包含SDK clone内部流程，不仅是某一个创建请求。

```sh
python3 bench_clone_concurrency.py -n 1   -c 1  --rounds 5
python3 bench_clone_concurrency.py -n 100 -c 10 --rounds 2
python3 bench_clone_concurrency.py -n 100 -c 20 --rounds 2
python3 bench_clone_concurrency.py -n 100 -c 50 --rounds 2
```


| 每轮克隆数 | 并发  | 正式轮数 | wall avg | wall min | wall P95 | wall max | per摊销 |
| -----: | ---: | ----: | --------: | --------: | --------: | --------: | -----: |
| 1     | 1   | 5    | 123.5    | 121.8    | 127.7    | 127.7    | 123.5 |
| 100   | 10  | 2    | 810.0    | 799.8    | 820.2    | 820.2    | 8.1   |
| 100   | 20  | 2    | 745.1    | 736.4    | 753.7    | 753.7    | 7.5   |
| 100   | 50  | 2    | 923.3    | 452.6    | 1393.9   | 1393.9   | 9.2   |


单位ms。共605个正式克隆完成，预热另计。n100c50两轮分别落在452.6–1393.9ms，波动明显；两轮均值不足以确认并发最优点。[原始4.5日志（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)

### 4.6 Pause / Resume

每轮准备C个沙箱，分别计时整批Pause和整批Resume。每档整轮预热一次，正式5轮，轮间等待2秒；源沙箱创建和销毁不计入两个操作时间。脚本允许预热失败后重试一次，本轮原始日志未记录该重试。

```sh
python3 bench_pause_resume_concurrency.py -c 1  -n 5
python3 bench_pause_resume_concurrency.py -c 5  -n 5
python3 bench_pause_resume_concurrency.py -c 10 -n 5
```

Pause结果：


| 并发  | 正式轮数 | wall avg | wall min | wall P95 | wall max | per摊销 |
| ---: | ----: | --------: | --------: | --------: | --------: | -----: |
| 1   | 5    | 161.8    | 145.1    | 183.0    | 183.0    | 161.8 |
| 5   | 5    | 230.1    | 211.2    | 255.2    | 255.2    | 46.0  |
| 10  | 5    | 258.4    | 251.6    | 274.9    | 274.9    | 25.8  |


Resume结果：


| 并发  | 正式轮数 | wall avg | wall min | wall P95 | wall max | per摊销 |
| ---: | ----: | --------: | --------: | --------: | --------: | -----: |
| 1   | 5    | 81.8     | 73.7     | 89.4     | 89.4     | 81.8  |
| 5   | 5    | 142.9    | 138.3    | 148.5    | 148.5    | 28.6  |
| 10  | 5    | 239.1    | 235.2    | 242.3    | 242.3    | 23.9  |


单位ms。正式Pause、Resume各80次完成。单实例Pause/Resume分别平均161.8/81.8ms；c10整批分别258.4/239.1ms。[原始4.6日志（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)

## 五、结果适用范围

1. 本报告只对应上述同一节点、镜像、2vCPU/2GiB规格和计时口径；不与社区x86机器或其他历史Template直接计算性能增益，也不是GICv3/GICv4受控A/B。
2. 32个非密度档完成不等于全部33档通过；1500密度目标仍未达到。未完成部分不补零，不以累计创建成功数替代健康验收容量。
3. 创建每档只执行一次正式原生调用；生命周期仅2–5轮。Python原始脚本只输出时间汇总，没有逐轮时延文件，不能额外估计可靠置信区间或合并分位数。
4. 每档前有静默门禁，但未持续证明整个测量期间无背景干扰；收尾曾观察到短时系统负载尖峰。因此应把本报告视为当前条件下的基线，而非稳定生产SLO保证。
5. HTTP/SDK返回耗时不是完整应用就绪时间，本文不标为严格V1.20合规结果；热恢复数据不能替代冷恢复数据。

测试结束时API沙箱数为0，KVM/task/Shim为空，TAP Ready1500；原有两个Snapshot及本轮Template保留。清理与静默验收对应目标机10月9日01:32左右的观测，不表示之后机器始终空闲。

## 附录：工具与原始数据索引


| 项目       | 来源与身份                                                                                                |
| -------- | ---------------------------------------------------------------------------------------------------- |
| Go创建/密度  | 官方 `tencentcloud/CubeSandbox` v0.7.1 / `31d911e4`，实际二进制SHA见3.1                                       |
| 五个生命周期脚本 | 社区 `cf571c65e41ca9f43012a1c3914575aef3cd6c21`，每个SHA与argv保存在所属run的report.json                         |
| 脏页脚本     | 上游准备修正版；SHA256 `ef92e6d01b4e0ee7aaf62b6d791509f363189aa7071fd8a15f7069459872a2e2`；计时/预热/统计不变，准备状态已披露 |
| 编排入口     | `<suite-source-root>/run_suite.py`；reference profile，非完整V1.20矩阵                       |
| 结果位置     | `<local-evidence-root>`；维护者本地保存原始副本，原始证据未随本次公开上传 |


- [创建、快照、恢复、回滚、克隆与暂停恢复原始数据清单（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)
- [密度原始数据清单（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)
- [原始文件远端/本地SHA一致性核验（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)
- [可复用完整套件源码包（仅本地留存；见索引）](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.evidence-manifest.md#原始证据)：需另配官方Go二进制；不复用历史输出目录。
