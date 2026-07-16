# Benchmark SDK Direct Commands

本文档记录通过 CubeSandbox SDK 直接调用镜像内 benchmark 二进制的命令。

适用场景：

- Sandbox 已由 `cube-bench-suite` template 启动。
- SDK 命令执行通道可用，即镜像内 envd 监听 `49983`。
- 不使用 `run-benchmark` wrapper，而是直接调用已安装的 benchmark 二进制或上游入口。

建议 SDK 中统一使用 `bash -lc '<command>'`，这样可以使用变量、`cd`、管道和 `tee` 保存输出。

结果目录统一使用：

```bash
/tmp/cube-bench-results
```

## SDK 调用模板

```python
result = sandbox.commands.run(
    "bash -lc 'mkdir -p /tmp/cube-bench-results && <benchmark-command>'",
    timeout=120,
)
```

如果需要保存 stdout 到 Sandbox 内文件：

```python
result = sandbox.commands.run(
    "bash -lc 'mkdir -p /tmp/cube-bench-results && <benchmark-command> | tee /tmp/cube-bench-results/<name>.log'",
    timeout=120,
)
```

## sysbench memory

正式测试固定参数：

```bash
--threads=2
--time=30
--memory-block-size=1G
--memory-total-size=100G
--memory-scope=global
```

顺序读取：

```bash
mkdir -p /tmp/cube-bench-results
/opt/cube-bench/bin/sysbench-upstream \
  --threads=2 \
  --time=30 \
  --memory-block-size=1G \
  --memory-total-size=100G \
  --memory-scope=global \
  --memory-oper=read \
  --memory-access-mode=seq \
  memory run | tee /tmp/cube-bench-results/sysbench-memory-seq-read.log
```

顺序写入：

```bash
mkdir -p /tmp/cube-bench-results
/opt/cube-bench/bin/sysbench-upstream \
  --threads=2 \
  --time=30 \
  --memory-block-size=1G \
  --memory-total-size=100G \
  --memory-scope=global \
  --memory-oper=write \
  --memory-access-mode=seq \
  memory run | tee /tmp/cube-bench-results/sysbench-memory-seq-write.log
```

随机读取：

```bash
mkdir -p /tmp/cube-bench-results
/opt/cube-bench/bin/sysbench-upstream \
  --threads=2 \
  --time=30 \
  --memory-block-size=1G \
  --memory-total-size=100G \
  --memory-scope=global \
  --memory-oper=read \
  --memory-access-mode=rnd \
  memory run | tee /tmp/cube-bench-results/sysbench-memory-rnd-read.log
```

随机写入：

```bash
mkdir -p /tmp/cube-bench-results
/opt/cube-bench/bin/sysbench-upstream \
  --threads=2 \
  --time=30 \
  --memory-block-size=1G \
  --memory-total-size=100G \
  --memory-scope=global \
  --memory-oper=write \
  --memory-access-mode=rnd \
  memory run | tee /tmp/cube-bench-results/sysbench-memory-rnd-write.log
```

一次执行四项：

```bash
mkdir -p /tmp/cube-bench-results
for spec in \
  "seq-read read seq" \
  "seq-write write seq" \
  "rnd-read read rnd" \
  "rnd-write write rnd"
do
  set -- $spec
  label="$1"
  oper="$2"
  mode="$3"
  /opt/cube-bench/bin/sysbench-upstream \
    --threads=2 \
    --time=30 \
    --memory-block-size=1G \
    --memory-total-size=100G \
    --memory-scope=global \
    --memory-oper="$oper" \
    --memory-access-mode="$mode" \
    memory run | tee "/tmp/cube-bench-results/sysbench-memory-${label}.log"
done
```

## sysbench prime

正式测试固定线程数：

```bash
--threads=2
--time=30
```

分别测试以下素数上限：

```bash
mkdir -p /tmp/cube-bench-results
for prime in 1000 2000 3000 5000 10000 20000 30000 50000 100000
do
  /opt/cube-bench/bin/sysbench-upstream \
    --threads=2 \
    --time=30 \
    cpu \
    --cpu-max-prime="$prime" \
    run | tee "/tmp/cube-bench-results/sysbench-prime-${prime}.log"
done
```

单项示例：

```bash
/opt/cube-bench/bin/sysbench-upstream --threads=2 --time=30 cpu --cpu-max-prime=20000 run
```

## Go benchmark

四个子项目分别调用。正式结果应分别读取每个子项输出中的 `ns/op`，不要只看全局平均值。

```bash
mkdir -p /tmp/cube-bench-results
/opt/cube-bench/bin/go-upstream/http | tee /tmp/cube-bench-results/go-http.log
/opt/cube-bench/bin/go-upstream/json | tee /tmp/cube-bench-results/go-json.log
/opt/cube-bench/bin/go-upstream/build | tee /tmp/cube-bench-results/go-build.log
/opt/cube-bench/bin/go-upstream/garbage | tee /tmp/cube-bench-results/go-garbage.log
```

对应输出：

- `BenchmarkHTTP`
- `BenchmarkJSON`
- `BenchmarkBuild`
- `BenchmarkGarbage/...`

主要指标：

- `ns/op`：越低越好。
- `allocated-bytes/op`：越低越好。
- `allocs/op`：越低越好。
- `peak-RSS-bytes`：峰值内存。

## PHP Benchmark Suite

```bash
mkdir -p /tmp/cube-bench-results
cd /opt/cube-bench/upstream/php-bench
PHPBENCH_ERROR_REPORTING=1 \
  php index.php iterations=2000000 format=json \
  | tee /tmp/cube-bench-results/php-benchmark.json
```

主要指标：

- `score`：越高越好。
- `total_time`：越低越好。
- 各子测试耗时：越低越好。

## Python pyperformance

正式测试建议使用 `--rigorous`。

```bash
mkdir -p /tmp/cube-bench-results
/opt/cube-bench/bin/pyperformance run \
  --benchmarks python_startup,json_dumps,json_loads,richards,scimark \
  --rigorous \
  --output /tmp/cube-bench-results/pyperformance.json \
  --python "$(command -v python3)" \
  | tee /tmp/cube-bench-results/python-benchmark-run.log

/opt/cube-bench/bin/pyperformance show \
  /tmp/cube-bench-results/pyperformance.json \
  | tee /tmp/cube-bench-results/python-benchmark-show.log
```

主要指标：

- `Mean`：越低越好。
- `std dev`：越低表示波动越小。
- JSON 文件：`/tmp/cube-bench-results/pyperformance.json`。

## Node Octane

```bash
mkdir -p /tmp/cube-bench-results
cd /opt/cube-bench/upstream/benchmark-octane
node run.js | tee /tmp/cube-bench-results/node-octane.log
```

主要指标：

- 每个子项分数：越高越好。
- `Score`：综合分，越高越好。

## Java SciMark

```bash
mkdir -p /tmp/cube-bench-results
java -jar /opt/cube-bench/upstream/scimark-2.2.jar -large \
  | tee /tmp/cube-bench-results/java-scimark.log
```

主要指标：

- `Composite Score`：越高越好。
- FFT、SOR、Monte Carlo、Sparse matmult、LU 子项分数：越高越好。

## 打包结果

所有命令完成后，可在 Sandbox 内打包结果：

```bash
cd /tmp
tar -czf cube-bench-results.tar.gz cube-bench-results
```

通过 SDK 文件接口读取：

```python
data = sandbox.files.read("/tmp/cube-bench-results.tar.gz", format="bytes")
```

如果 SDK 文件读取接口不可用，也可以用命令将 tar 包 base64 输出：

```bash
base64 /tmp/cube-bench-results.tar.gz
```
