# Benchmark 参数设计文档

本文档定义 `cube-bench-suite` 中各 benchmark 的参数含义、默认值、推荐配置和结果解读口径。目标是让不同机器、不同架构、不同 Sandbox 规格下的测试结果具备可复现性和可比性。

## 设计目标

1. **Smoke 可用性验证**：快速确认镜像、Template、Sandbox、envd 命令通道和 benchmark 入口都能工作。
2. **正式性能取数**：固定资源、镜像、Template 和参数，多次运行后比较性能指标。
3. **跨机器对比**：确保每次测试记录足够的上下文，避免将参数差异误解为性能差异。

## 通用参数

| 参数 | 默认值 | 作用 | 建议 |
|---|---:|---|---|
| `CUBE_BENCH_HOME` | `/opt/cube-bench` | benchmark 安装根目录 | 不建议修改 |
| `CUBE_BENCH_OUT_DIR` | `/tmp/cube-bench-results` | benchmark 中间结果输出目录 | Template/SDK 模式下建议固定并打包保存 |

每次测试至少保存：

- 镜像 tag 和 digest
- Template ID
- Sandbox ID
- CPU/Memory 规格
- 架构：`amd64` 或 `arm64`
- `run-benchmark <case>` 命令
- 环境变量参数
- stdout/stderr/exit code
- 运行时间和重复次数

## 推荐测试档位

### Smoke 档

用于验证功能是否可用，耗时较短，不作为正式性能结论。

| Case | 推荐参数 |
|---|---|
| `sysbench-memory-all` | `SYSBENCH_MEMORY_TIME=5 SYSBENCH_MEMORY_TOTAL_SIZE=10G SYSBENCH_MEMORY_BLOCK_SIZE=1K SYSBENCH_MEMORY_THREADS=<CPU核数>` |
| `sysbench-prime` | `SYSBENCH_TIME=5 SYSBENCH_MAX_PRIME=5000 SYSBENCH_THREADS=<CPU核数>` |
| `go-benchmark` | `GO_BENCH_REPEATS=1` |
| `php-benchmark` | `PHPBENCH_ITERATIONS=100000` |
| `python-benchmark` | `PYPERFORMANCE_BENCHMARKS=python_startup,json_dumps PYPERFORMANCE_MODE=fast` |
| `node-octane` | 默认 |
| `java-scimark` | 默认 |

### Formal 档

用于正式对比。建议每个 case 至少运行 3 次，取中位数或报告均值和标准差。

| Case | 推荐参数 |
|---|---|
| `sysbench-memory-all` | `SYSBENCH_MEMORY_TIME=30 SYSBENCH_MEMORY_TOTAL_SIZE=100G SYSBENCH_MEMORY_BLOCK_SIZE=1G SYSBENCH_MEMORY_THREADS=2` |
| `sysbench-prime` / `sysbench-prime-matrix` | `SYSBENCH_TIME=30 SYSBENCH_THREADS=2 SYSBENCH_MAX_PRIME=<1000|2000|3000|5000|10000|20000|30000|50000|100000>` |
| `go-benchmark` | `GO_BENCH_REPEATS=3` 或更高 |
| `php-benchmark` | `PHPBENCH_ITERATIONS=2000000` |
| `python-benchmark` | `PYPERFORMANCE_MODE=rigorous`，按需扩大 `PYPERFORMANCE_BENCHMARKS` |
| `node-octane` | 默认，多次运行取中位数 |
| `java-scimark` | 默认，多次运行取中位数 |

## 各 Benchmark 参数设计

### 1. `sysbench-memory` / `sysbench-memory-all`

执行内容：

```bash
sysbench --threads=<threads> --time=<time> \
  --memory-block-size=<block_size> \
  --memory-total-size=<total_size> \
  --memory-scope=<scope> \
  --memory-oper=<read|write> \
  --memory-access-mode=<seq|rnd> \
  memory run
```

参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `SYSBENCH_MEMORY_TIME` | `30` | 每个内存子项运行秒数 |
| `SYSBENCH_MEMORY_TOTAL_SIZE` | `100G` | 每个子项总传输数据量上限 |
| `SYSBENCH_MEMORY_BLOCK_SIZE` | `1K` | 每次内存操作块大小 |
| `SYSBENCH_MEMORY_THREADS` | `SYSBENCH_THREADS` 或 `$(nproc)` | 并发线程数 |
| `SYSBENCH_MEMORY_OPER` | `write` | 单项测试操作类型，`read` 或 `write` |
| `SYSBENCH_MEMORY_ACCESS_MODE` | `seq` | 单项测试访问模式，`seq` 或 `rnd` |
| `SYSBENCH_MEMORY_SCOPE` | `global` | 内存 buffer 作用域，`global` 或 `local` |

设计原则：

- `sysbench-memory-all` 是推荐入口，会依次执行 `seq-read`、`seq-write`、`rnd-read`、`rnd-write`。
- 正式测试统一使用 `SYSBENCH_MEMORY_THREADS=2`。
- `SYSBENCH_MEMORY_TIME` 太短时容易受启动抖动影响；正式测试建议不少于 30 秒。
- 正式测试统一使用 `SYSBENCH_MEMORY_TOTAL_SIZE=100G`。
- 正式测试统一使用 `SYSBENCH_MEMORY_BLOCK_SIZE=1G`；该设置会显著改变访问粒度，必须在报告中明确记录。
- `SYSBENCH_MEMORY_SCOPE=global` 表示线程共享全局 memory buffer；如需观察每线程本地 buffer 行为，可单独设置为 `local`，但不能与 `global` 结果混比。

输出解读：

- `transferred (...) MiB/sec`：内存吞吐，越大越好。
- `events per second`：操作吞吐，越大越好。
- latency 的 `avg`、`95th percentile`：越低越好。
- `seq-read` / `seq-write` 代表顺序读写。
- `rnd-read` / `rnd-write` 代表随机读写。

### 2. `sysbench-prime`

执行内容：

```bash
sysbench --threads=<threads> --time=<time> cpu --cpu-max-prime=<max_prime> run
```

参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `SYSBENCH_MAX_PRIME` | `20000` | 单个事件计算素数的上限 |
| `SYSBENCH_PRIME_MAX_LIST` | `1000,2000,3000,5000,10000,20000,30000,50000,100000` | `sysbench-prime-matrix` 使用的素数上限列表 |
| `SYSBENCH_THREADS` | `$(nproc)` | 并发线程数 |
| `SYSBENCH_TIME` | `30` | 测试持续秒数 |

设计原则：

- 正式测试统一使用 `SYSBENCH_THREADS=2`。
- `SYSBENCH_TIME` 太短时结果易受启动抖动影响；正式测试建议不少于 30 秒。
- `SYSBENCH_MAX_PRIME` 越大，单次事件越重；正式测试分别覆盖 `1000, 2000, 3000, 5000, 10000, 20000, 30000, 50000, 100000`。
- `sysbench-prime-matrix` 会按 `SYSBENCH_PRIME_MAX_LIST` 顺序逐个调用 `sysbench-prime`；SDK formal suite 会把每个上限拆成独立结果文件。

输出解读：

- `events per second`：吞吐，越大越好。
- `total number of events`：总事件数，受测试时间影响。
- latency 的 `avg`、`95th percentile`：越低越好。
- fairness 的 stddev 可用于观察线程间负载是否均匀。

### 3. `go-benchmark`

执行内容：

```bash
golang.org/x/benchmarks: build http json garbage
```

参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `GO_BENCH_REPEATS` | `1` | 每个 Go 子项重复次数 |

设计原则：

- Go 子项的耗时跨度很大，`build` 往往远大于其它子项。
- wrapper 会分别输出 `go-build-average`、`go-http-average`、`go-json-average`、`go-garbage-average`，并额外输出一个全局 `go-benchmark-average`。
- 全局 average 是简单平均，容易被 `build` 主导。
- 正式分析应优先分别比较 `BenchmarkBuild`、`BenchmarkHTTP`、`BenchmarkJSON`、`BenchmarkGarbage`。

输出解读：

- `ns/op`：每次操作耗时，越低越好。
- `allocated-bytes/op`：每次操作分配字节数，越低越好。
- `allocs/op`：每次操作分配次数，越低越好。
- `peak-RSS-bytes`：峰值内存。
- stderr 中可能出现 perf 缺失提示；若 exit code 为 0，主指标仍有效。

### 4. `php-benchmark`

执行内容：

```bash
php index.php iterations=<iterations> format=json
```

参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `PHPBENCH_ITERATIONS` | `2000000` | 每个 PHP micro benchmark 的迭代次数 |

设计原则：

- Smoke 可降低迭代次数以缩短时间。
- 正式测试必须固定 `PHPBENCH_ITERATIONS`。
- 迭代次数越低，结果越容易受抖动影响。

输出解读：

- `total_time`：总耗时，越低越好。
- `results.<test>`：每个 PHP 子测试耗时，越低越好。
- `score`：综合分，越高越好。
- `percentile_times`：各子项耗时占比，可用于定位主要耗时来源。

### 5. `python-benchmark`

执行内容：

```bash
pyperformance run --benchmarks <benchmarks> --fast|--rigorous
```

参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `PYPERFORMANCE_BENCHMARKS` | `python_startup,json_dumps,json_loads,richards,scimark` | 选择 pyperformance 子项 |
| `PYPERFORMANCE_MODE` | `fast` | `fast` 或 `rigorous` |
| `PYPERFORMANCE_RIGOROUS` | `0` | 设置为 `1` 时强制 rigorous |

设计原则：

- Smoke 使用少量子项和 `fast`。
- 正式测试使用 `rigorous`，并固定 benchmark 子项集合。
- 如果输出提示结果不稳定，应增加采样或减少系统干扰。

输出解读：

- `Mean`：平均耗时，越低越好。
- `std dev`：波动，越低越稳定。
- pyperformance 会生成 JSON 结果文件，默认位于 `CUBE_BENCH_OUT_DIR/pyperformance.json`。

### 6. `node-octane`

执行内容：

```bash
node run.js
```

参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| 无 wrapper 参数 | - | 当前直接运行上游 Octane |

设计原则：

- Node/V8 JIT 对启动状态和系统抖动敏感。
- 正式测试建议重复运行多次，取中位数。
- 对比时必须固定 Node/V8 版本。

输出解读：

- 每个子项分数越高越好。
- `Score (version 9)` 是综合分，越高越好。
- `duration` 是运行耗时，不是主要性能分数。

### 7. `java-scimark`

执行内容：

```bash
java -jar scimark-2.2.jar -large
```

参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| 无 wrapper 参数 | `-large` | 当前固定使用 SciMark large 规模 |

设计原则：

- 当前 wrapper 固定 large 数据规模，适合减少过小问题规模造成的噪声。
- 正式测试建议多次运行，取中位数。
- 对比时必须固定 JDK 版本。

输出解读：

- `Composite Score`：综合分，越高越好。
- FFT、SOR、Monte Carlo、Sparse matmult、LU：子项分数，越高越好。

## 结果判定规则

1. 先看 exit code：非 0 表示该 case 失败，不应纳入性能统计。
2. 再看 benchmark 主指标：
   - bandwidth / throughput / score：越大越好。
   - latency / time / ns/op / ms / stddev：越小越好。
3. stderr 不等价于失败，必须结合 exit code 和工具语义判断。
4. 不同参数下的结果不可直接比较。

## 正式报告建议字段

每次正式测试建议汇总为如下表格：

| Case | 参数 | 主指标 | 单位 | 趋势 | 重复次数 | 聚合方式 |
|---|---|---|---|---|---:|---|
| sysbench-memory-all | `TIME=30 TOTAL=100G BLOCK=1G THREADS=2` | seq/rnd read/write throughput | MiB/s | 越大越好 | 3+ | median |
| sysbench-prime | `TIME=30 THREADS=2 PRIME=1000/2000/3000/5000/10000/20000/30000/50000/100000` | events/sec | events/s | 越大越好 | 3+ | median |
| go-benchmark | `GO_BENCH_REPEATS=3` | build/http/json/garbage average ns/op | ns/op | 越小越好 | 3+ | median |
| php-benchmark | `PHPBENCH_ITERATIONS=2000000` | score / total_time | score/s | score 越大越好，time 越小越好 | 3+ | median |
| python-benchmark | `PYPERFORMANCE_MODE=rigorous` | Mean | ms | 越小越好 | pyperformance 内部采样 | pyperformance report |
| node-octane | default | Score | score | 越大越好 | 3+ | median |
| java-scimark | `-large` | Composite Score | score | 越大越好 | 3+ | median |
