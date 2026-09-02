# CubeSandbox Benchmark 镜像构建与测试材料

本目录收集 `cube-bench-suite` 镜像构建、CubeSandbox Template/SDK 测试、结果汇总和参数设计所需的源码与文档。这里不保存大体积镜像 tar 包，只保留可复现流程需要的源文件和 checksum。

## 目录结构

```text
benchmark/
├── analysis/                      # benchmark口径、内存记账模型和测量方法专题
├── docker/
│   ├── cube-bench-suite-envd/      # CubeSandbox 适配构建上下文（依赖已有 benchmark 源镜像）
│   └── cubesandbox-base-compat/    # cubesandbox-base 兼容构建参考
├── scripts/                        # 可复用测试脚本、SDK/envd runner、CSV 汇总脚本和脚本指南
├── docs/                           # benchmark 使用、参数设计、复用方式和镜像 tag 说明
├── reports/                        # 已完成部署/benchmark 报告样例
└── checksums/                      # 已导出镜像 tar.gz 的 sha256 元数据
```

## 核心文件

- `docker/cube-bench-suite-envd/Dockerfile`：基于 `cubesandbox-base` 重建 benchmark 镜像，满足 CubeSandbox 自定义镜像/Template 要求。
- `docker/cube-bench-suite-envd/run-benchmark`：镜像内 benchmark 统一 wrapper。
- `docker/cube-bench-suite-envd/health_server.py`：镜像默认启动服务，用于 Template 探活。
- `scripts/cube_bench_sdk.py`：通过 E2B-compatible SDK 创建/连接 Sandbox 并执行 benchmark。
- `scripts/run_cube_bench_envd.py`：直接通过 envd Process API 执行 benchmark。
- `scripts/cube_bench_reusable.py`：可在其它 CubeSandbox 环境复用的标准库 runner。
- `scripts/summarize_cube_bench_*.py`：将 runner 结果汇总为 CSV。

## `cube-bench-suite` 来源与项目边界

`cube-bench-suite` 最初不是在 `agent_vm_bench` 仓库中制作的。它是在独立的
CubeSandbox 验证项目 `/home/lyq/Projects/Verification/cubesandbox` 下设计和验证，最初的
本地临时构建上下文为 `/tmp/cube-bench-image`，ARM64 节点上的构建上下文为
`root@192.168.25.90:/home/lyq/cube-bench-image`。相关镜像、wrapper、SDK runner 和验证文档
后来才整理进入本 `materials` 仓库。

当前 `docker/cube-bench-suite-envd/Dockerfile` 是 CubeSandbox Template 适配层，不是能够
从零获取全部上游源码的原始构建入口：它通过 `BENCH_SOURCE_IMAGE` 接收已经包含
`/opt/cube-bench` 的 `cube-bench-suite` 源镜像，再把 benchmark 源码、二进制和 Go 工具链
复制到 `cubesandbox-base`。因此复现实验时必须同时固定：

- `BENCH_SOURCE_IMAGE` 的 tag、image ID 或 registry digest；
- `CUBESANDBOX_BASE_IMAGE` 的 digest；
- 下表中的 benchmark commit、release 和归档文件 checksum；
- 镜像内 `run-benchmark versions` 输出的实际运行时版本。

## 语言运行时与上游测试项目

“语言运行时源码仓库”和“镜像实际运行的 benchmark 项目”是两个不同层次。除 Go 工具链
来自原始 `golang:1.25.0` 基础镜像外，PHP、Python、Node.js 和 OpenJDK 由构建时的
Debian/Ubuntu 软件源安装；本项目没有从这些运行时源码仓库自行编译，也没有为它们记录
上游源码 commit。下面的运行时仓库链接用于说明实现归属，真正作为 benchmark 输入固定的
是“测试项目与版本”列。

| 运行时 | 运行时实现仓库 / 镜像内来源 | 测试项目与固定版本 | `cube-bench-suite` 实际执行内容 |
|---|---|---|---|
| Go | [`golang/go`](https://github.com/golang/go)；原始构建基于 `golang:1.25.0` | [`golang/benchmarks@7ba6f826adc166100228319b6a94683fb0d32ed4`](https://github.com/golang/benchmarks/commit/7ba6f826adc166100228319b6a94683fb0d32ed4) | `build` 完整编译和链接 `cmd/go`；`http` 测试本机 Go HTTP client/server；`json` 对约 2 MiB 树形数据做 marshal/unmarshal；`garbage` 反复解析 `net/http` 源码以施压 GC。 |
| PHP | [`php/php-src`](https://github.com/php/php-src)；发行版 `php-cli` 等软件包 | [`pantheon-deprecated/php-bench@533b459f2256ee11a65586ccbea225cea6fbcb8a`](https://github.com/pantheon-deprecated/php-bench/commit/533b459f2256ee11a65586ccbea225cea6fbcb8a) | PHPBench `0.8.1-pantheon1` 的默认 `cpu` suite，覆盖循环、数组、字符串、类型转换、函数调用、hash 和正则等解释器微基准。 |
| Python | [`python/cpython`](https://github.com/python/cpython)；发行版 `python3` 软件包 | [`python/pyperformance@216cbeb5f828b8ee5864f9bb52f3563d2d1a4846`](https://github.com/python/pyperformance/commit/216cbeb5f828b8ee5864f9bb52f3563d2d1a4846) | 默认选择 `python_startup`、`json_dumps`、`json_loads`、`richards`、`scimark`；formal 模式使用 pyperformance rigorous 采样。 |
| Node.js / V8 | [`nodejs/node`](https://github.com/nodejs/node)；发行版 `nodejs` 软件包 | [`dai-shi/benchmark-octane@a627d34e14b214619404e7ed9e94b83fb17adf91`](https://github.com/dai-shi/benchmark-octane/commit/a627d34e14b214619404e7ed9e94b83fb17adf91) | Node.js 版 Octane 2.0，包含 Richards、DeltaBlue、Crypto、RayTrace、RegExp、Splay、NavierStokes、PdfJS、Gameboy、CodeLoad、Box2D、zlib、TypeScript 等，并输出 `Score (version 9)`。 |
| Java / OpenJDK | [`openjdk/jdk`](https://github.com/openjdk/jdk)；发行版 `default-jdk-headless` 软件包 | [`mork-optimization/scimark` 2.2 release](https://github.com/mork-optimization/scimark/releases/tag/scimark-2.2) | 执行 `java -jar scimark-2.2.jar -large`，覆盖 FFT、SOR、Monte Carlo、Sparse Matrix Multiply 和 LU，输出近似 Mflops 的 Composite Score。 |

PHPBench 原 clone URL 为 `https://github.com/pantheon-systems/php-bench.git`，当前 GitHub
规范地址已经重定向到 archived 仓库 `pantheon-deprecated/php-bench`。镜像中的副本也不是
该 commit 的逐字节原样副本：为兼容较新 PHP，构建时增加了可配置 error reporting，并在
4 个 CPU 用例中显式执行字符串到浮点数的转换。复现该 workload 时，不能只记录上游 commit，
还必须保留这些本地兼容修改。

### 非语言运行时 benchmark

| Case | 上游项目与固定版本 | 实际执行内容 |
|---|---|---|
| `sysbench-memory` / `sysbench-memory-all` | [`akopytov/sysbench` 1.0.20](https://github.com/akopytov/sysbench/releases/tag/1.0.20) | 使用内建 `memory` workload，覆盖顺序读、顺序写、随机读、随机写。 |
| `sysbench-prime` / `sysbench-prime-matrix` | [`akopytov/sysbench` 1.0.20](https://github.com/akopytov/sysbench/releases/tag/1.0.20) | 使用内建 `cpu --cpu-max-prime` workload；未执行数据库 workload。 |

固定输入的来源标识如下；这些值同时由镜像内 `/opt/cube-bench/SOURCES.md` 输出：

```text
golang-benchmarks: 7ba6f826adc166100228319b6a94683fb0d32ed4
php-bench:         533b459f2256ee11a65586ccbea225cea6fbcb8a
pyperformance:     216cbeb5f828b8ee5864f9bb52f3563d2d1a4846
benchmark-octane:  a627d34e14b214619404e7ed9e94b83fb17adf91
scimark-2.2.jar:   sha256:3c8dc0faeebb0435bd8033aea5a1f3abd7252aa0befd3b43cb5e37625d6d3774
sysbench-1.0.20:   sha256:e8ee79b1f399b2d167e6a90de52ccc90e52408f7ade1b9b7135727efe181347f
```

### 历史 `lmbench` 项目

最初的 `cube-bench-suite` 还包含
[`intel/lmbench@a33716428dc2e717ce3e7dfce767302583eb8fdc`](https://github.com/intel/lmbench/commit/a33716428dc2e717ce3e7dfce767302583eb8fdc)，
但只调用其中的 `bw_mem` 读写带宽测试，并未运行完整 lmbench suite。当前
`run-benchmark` 已移除 `lmbench-mem`，由 `sysbench-memory` 和
`sysbench-memory-all` 承担内存 workload；旧部署报告中的 `lmbench-mem` 结果只能作为
历史镜像结果，不能与当前 case 列表混为一谈。

## 内存开销分析

- [社区单机密度内存表审计](analysis/community-density-memory-report-audit.md)：复算累计/边际值，说明现有表能证明和不能证明什么。
- [CubeSandbox CoW 与宿主机内存记账模型](analysis/cubesandbox-cow-memory-accounting-model.md)：区分 rootfs reflink、Snapshot `MAP_PRIVATE`、PSS/USS、cgroup和`MemAvailable`。
- [CubeSandbox 单机密度内存测量指南](analysis/cubesandbox-memory-density-measurement-guide.md)：给出N=0、阶梯密度、多视角采样、判因、清理和evidence规范。
- [CubeSandbox 宿主机内存开销实测报告](analysis/cubesandbox-memory-footprint-report.md)：给出独立N=0/1/10/50、N=100观察点、累计N=100和N=300前停止证据。
- [CubeSandbox 宿主机内存开销测试计划](analysis/cubesandbox-memory-footprint-test-plan.md)：记录对象模型、采样schema、门禁、统计、精确清理和失败收敛方法。
- [CubeSandbox `.90` 当前宿主机内存开销正式报告](analysis/cubesandbox-memory-footprint-90-current-report.md)：给出同run累计N=0/100/300/500/1000、组件增长、清理和严格门禁结果。
- [Cubelet cgroup v1采集纠错](analysis/cubelet-cgroup-v1-collection-erratum.md)：撤回错误层级的Cubelet cgroup值，保留PSS/USS并说明采集器修复。

## Go build / perf 行为

新版 wrapper 默认运行：

```bash
GO_BENCH_CASES=build,http,json,garbage
GO_BENCH_DISABLE_PERF=1
```

`build` 子项仍会执行上游 `golang.org/x/benchmarks` 的 `BenchmarkBuild` 主测试；`GO_BENCH_DISABLE_PERF=1` 通过临时 `perf` shim 关闭上游 build profiler，避免未安装/未授权 `perf` 的环境出现 `perf record` 报错。需要真实 perf profile 时，可显式设置：

```bash
GO_BENCH_DISABLE_PERF=0
```

但这要求镜像内有 `perf`，并且容器/宿主机提供相应权限。

## 本地 amd64 构建

前提：本地已有 benchmark 源镜像和 cubesandbox-base：

```bash
docker image inspect cube-bench-suite:upstream-amd64
docker image inspect ghcr.io/tencentcloud/cubesandbox-base:2026.16
```

构建：

```bash
docker build \
  -f docker/cube-bench-suite-envd/Dockerfile \
  --build-arg BENCH_SOURCE_IMAGE=cube-bench-suite:upstream-amd64 \
  --build-arg CUBESANDBOX_BASE_IMAGE=ghcr.io/tencentcloud/cubesandbox-base:2026.16 \
  -t cube-bench-suite:upstream-amd64-20260716-build-noperf \
  -t cube-bench-suite:upstream-amd64 \
  docker/cube-bench-suite-envd
```

验证 Go build 子项：

```bash
docker run --rm --entrypoint /bin/bash \
  cube-bench-suite:upstream-amd64-20260716-build-noperf \
  -lc 'mkdir -p /tmp/cube-build-test && cd /tmp/cube-build-test &&
       export CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results
       export GO_BENCH_CASES=build GO_BENCH_DISABLE_PERF=1 GO_BENCH_REPEATS=1
       run-benchmark go-benchmark'
```

验证默认服务：

```bash
docker run -d --name cube-bench-verify cube-bench-suite:upstream-amd64-20260716-build-noperf
docker exec cube-bench-verify curl -fsS http://127.0.0.1:49999/health
docker exec cube-bench-verify curl -fsS http://127.0.0.1:49983/health
docker rm -f cube-bench-verify
```

导出：

```bash
docker save cube-bench-suite:upstream-amd64-20260716-build-noperf \
  | gzip -c > cube-bench-suite_upstream-amd64-20260716-build-noperf.tar.gz
sha256sum cube-bench-suite_upstream-amd64-20260716-build-noperf.tar.gz \
  > cube-bench-suite_upstream-amd64-20260716-build-noperf.tar.gz.sha256
```

## 远端 arm64 构建

远端机器示例：`root@192.168.25.90`。

前提：远端已有 arm64 源镜像和 arm64 base：

```bash
docker image inspect cube-bench-suite:upstream-arm64-20260715-5e54db9
docker image inspect cubesandbox-base:2026.16-arm64-local
```

构建：

```bash
docker build \
  -f docker/cube-bench-suite-envd/Dockerfile \
  --build-arg BENCH_SOURCE_IMAGE=cube-bench-suite:upstream-arm64-20260715-5e54db9 \
  --build-arg CUBESANDBOX_BASE_IMAGE=cubesandbox-base:2026.16-arm64-local \
  -t cube-bench-suite:upstream-arm64-20260716-build-noperf \
  -t cube-bench-suite:upstream-arm64 \
  docker/cube-bench-suite-envd
```

验证：

```bash
docker run --rm --entrypoint /bin/bash \
  cube-bench-suite:upstream-arm64-20260716-build-noperf \
  -lc 'mkdir -p /tmp/cube-build-test && cd /tmp/cube-build-test &&
       export CUBE_BENCH_OUT_DIR=/tmp/cube-bench-results
       export GO_BENCH_CASES=build GO_BENCH_DISABLE_PERF=1 GO_BENCH_REPEATS=1
       run-benchmark go-benchmark'
```

推送到远端本机 registry：

```bash
docker tag cube-bench-suite:upstream-arm64-20260716-build-noperf \
  127.0.0.1:5000/cube-bench-suite:upstream-arm64-20260716-build-noperf
docker push 127.0.0.1:5000/cube-bench-suite:upstream-arm64-20260716-build-noperf
```

导出：

```bash
docker save cube-bench-suite:upstream-arm64-20260716-build-noperf \
  | gzip -c > cube-bench-suite_upstream-arm64-20260716-build-noperf.tar.gz
sha256sum cube-bench-suite_upstream-arm64-20260716-build-noperf.tar.gz \
  > cube-bench-suite_upstream-arm64-20260716-build-noperf.tar.gz.sha256
```

## CubeSandbox Template 测试

创建 Template 时建议使用新版 registry tag，例如：

```bash
cubemastercli template create-from-image \
  --image 127.0.0.1:5000/cube-bench-suite:upstream-arm64-20260716-build-noperf \
  --registry-username admin \
  --registry-password passw0rd \
  --writable-layer-size 8G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health \
  --cpu 8000 \
  --memory 16000 \
  --instance-type cubebox \
  --network-type tap \
  --allow-internet-access \
  --json
```

SDK 测试示例：

```bash
export E2B_API_URL=http://127.0.0.1:3000
export E2B_API_KEY=e2b_000000
export SSL_CERT_FILE=/root/.local/share/mkcert/rootCA.pem

python3 scripts/cube_bench_sdk.py \
  --template-id <template_id> \
  --suite smoke \
  --delete
```

结果汇总：

```bash
python3 scripts/summarize_cube_bench_sdk_csv.py \
  --results-dir <results_dir> \
  --output <summary.csv>
```

更多参数和输出解读见：

- `docs/BENCHMARK_USAGE.md`
- `docs/BENCHMARK_PARAMETER_DESIGN.md`
- `docs/BENCHMARK_REUSE.md`
- `scripts/CUBE_BENCH_SDK_GUIDE.md`
- `scripts/RUN_CUBE_BENCH_ENVD_GUIDE.md`

## Lifecycle benchmark 报告

- [Runtime Snapshot / Dirty / Rollback / Clone / Pause 社区对齐测试（2026-08-24）](reports/CUBESANDBOX_RUNTIME_SNAPSHOT_PAUSE_CLONE_COMMUNITY_ALIGNED_20260824.md)
  - [机器可读 CSV](reports/CUBESANDBOX_RUNTIME_SNAPSHOT_PAUSE_CLONE_COMMUNITY_ALIGNED_20260824.csv)
  - [Evidence manifest](reports/CUBESANDBOX_RUNTIME_SNAPSHOT_PAUSE_CLONE_COMMUNITY_ALIGNED_20260824.evidence-manifest.md)

## 已知导出镜像校验

本目录只保存 checksum，不保存大体积 tar 包：

- `checksums/cube-bench-suite_upstream-amd64-20260716-build-noperf.tar.gz.sha256`
- `checksums/cube-bench-suite_upstream-arm64-20260716-build-noperf.tar.gz.sha256`

对应 tar 包可按上面的导出命令重新生成。
