# CubeSandbox Benchmark 镜像构建与测试材料

本目录收集 `cube-bench-suite` 镜像构建、CubeSandbox Template/SDK 测试、结果汇总和参数设计所需的源码与文档。这里不保存大体积镜像 tar 包，只保留可复现流程需要的源文件和 checksum。

## 目录结构

```text
benchmark/
├── docker/
│   ├── cube-bench-suite-envd/      # benchmark 镜像构建上下文
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

## 已知导出镜像校验

本目录只保存 checksum，不保存大体积 tar 包：

- `checksums/cube-bench-suite_upstream-amd64-20260716-build-noperf.tar.gz.sha256`
- `checksums/cube-bench-suite_upstream-arm64-20260716-build-noperf.tar.gz.sha256`

对应 tar 包可按上面的导出命令重新生成。
