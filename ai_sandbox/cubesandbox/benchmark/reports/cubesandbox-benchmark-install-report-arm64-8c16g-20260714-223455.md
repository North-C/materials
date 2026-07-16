# CubeSandbox v0.5.0 ARM64 安装与 Benchmark 验证报告

生成时间：2026-07-14

## 结论

- CubeSandbox 服务已在 `192.168.25.90` 完成恢复部署，`/dev/nvme3n1` 已作为 XFS 挂载到 `/data/cubelet`。
- 基于 `cube-bench-suite:upstream-arm64` 重新创建了 8C16G Template：`tpl-130ea9ec9cd146638923e5d4`。
- 使用 CubeAPI 成功启动 Sandbox：`e715d1a891fd4da08286e7fd03dc47d4`，Sandbox IP：`10.100.1.59`。
- 通过 envd `process.Process/Start` 执行 benchmark，所有 smoke 用例返回 `rc=0`。

## 关键修正

- 旧 Template `tpl-1de173b231b34e28aee50b80` 使用 `49983 /health` 作为 readiness probe 时，Cubelet 创建阶段出现 `PortBindingFailed: context deadline exceeded`。
- 新 Template 使用同一镜像和同一资源规格，但将 readiness probe 设置为 `49999 /health`；envd 仍在 `49983` 上运行并用于 SDK/命令执行。
- 验证命令通道：`http://10.100.1.59:49983/process.Process/Start`，Connect JSON framing，`Authorization: Basic cm9vdDo=`。

## Template 信息

- Template ID：`tpl-130ea9ec9cd146638923e5d4`
- Job ID：`4c23ae2a-5234-43f0-8730-ff668b9f09f5`
- Artifact：`rfs-57e1a39124c80f055b0cead6`
- Image：`127.0.0.1:5000/cube-bench-suite:upstream-arm64@sha256:bb819f90a116ca501f6b82c176fc36621ef6d128ff6253f29410084831db0709`
- 资源：`cpu=8000m,mem=16000Mi`
- 状态：`READY`

## Sandbox 信息

- Sandbox ID：`e715d1a891fd4da08286e7fd03dc47d4`
- Sandbox IP：`10.100.1.59`
- CPU：`8`
- Memory MB：`16000`
- State：`running`
- EndAt：`2026-07-14T15:28:09.453Z`

## Benchmark 结果

| Case | RC | Elapsed(s) | stdout bytes | stderr bytes |
|---|---:|---:|---:|---:|
| 00-versions | 0 | 0.202 | 1125 | 0 |
| 01-lmbench-mem | 0 | 22.096 | 52 | 30 |
| 02-sysbench-prime | 0 | 5.022 | 887 | 0 |
| 03-go-benchmark | 0 | 72.474 | 2102 | 620 |
| 04-php-benchmark | 0 | 1.355 | 4658 | 0 |
| 05-python-benchmark | 0 | 25.053 | 4963 | 0 |
| 06-node-octane | 0 | 31.412 | 3748 | 0 |
| 07-java-scimark | 0 | 32.528 | 366 | 0 |

## 输出样例

### versions

```text
[versions] go=go version go1.25.0 linux/arm64
[versions] php=PHP 8.1.2-1ubuntu2.24 (cli) (built: May 25 2026 15:08:06) (NTS)
[versions] python=Python 3.10.12
[versions] pyperformance=pyperformance 1.14.0
[versions] node=v12.22.9
[versions] java=openjdk version "11.0.31" 2026-04-21
[versions] lmbench_bw_mem=/opt/cube-bench/bin/lmbench-bw_mem
[versions] sysbench=sysbench 1.0.20
[versions] sources=/opt/cube-bench/SOURCES.md
[versions] source: # Benchmark Sources
```

### lmbench-mem

```text
[lmbench-mem] upstream=lmbench tool=bw_mem size=16m
```

### sysbench-prime

```text
[sysbench-prime] upstream=sysbench cpu-max-prime=5000 threads=8 time=5
sysbench 1.0.20 (using bundled LuaJIT 2.1.0-beta2)

Running the test with following options:
Number of threads: 8
Initializing random number generator from current time


Prime numbers limit: 5000

Initializing worker threads...

```

## 结果文件

- 结果目录：`/home/lyq/cube-bench-template-arm64-8c16g-probe49999-20260714-222551/benchmark-results-20260714-223058-envd`
- 压缩包：`/home/lyq/cube-bench-template-arm64-8c16g-probe49999-20260714-222551/benchmark-results-20260714-223058-envd.tar.gz`
- SHA256：`4c2d862897951daec3f5024b565c00480a069001b45e46d4adbee254ec067e91`
- 每个用例保存了：`.cmd`、`.stdout`、`.stderr`、`.rc`、`.events.json`、`.raw`。

## 后续建议

- 如果后续希望 SDK `sandbox.commands.run()` 走公网/域名代理，需要继续配置并验证 cube-proxy 的 DNS/TLS；本次验证已确认集群内 envd 命令通道可用。
- 对 benchmark 正式压测时，将当前 smoke 参数调整为 full 参数，并延长 Sandbox timeout。

## 清理状态

- Benchmark Sandbox 已通过 CubeAPI 删除，删除接口返回 HTTP 204。
- 历史 exited Sandbox 记录已删除。
- 最终 `GET /health` 返回 `{"status":"ok","sandboxes":0}`。
