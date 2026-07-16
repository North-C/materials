# `run_cube_bench_envd.py` 使用指南

`run_cube_bench_envd.py` 是本项目最早用于通过 envd 直接执行 `cube-bench-suite` 的脚本。它直接调用 CubeAPI 创建/查询/删除 Sandbox，再通过 Sandbox 内网 IP 访问 envd `49983` 的 Connect Process API 执行 `run-benchmark` 命令。

它和 `cube_bench_reusable.py` 使用同一类底层通道：都是 **CubeAPI + Sandbox 内网 envd**，都不依赖 E2B SDK。区别是：

| 脚本 | 定位 | 推荐程度 |
|---|---|---|
| `run_cube_bench_envd.py` | 早期/兼容版 envd runner，逻辑更简单。 | 可用，但不建议作为新环境首选。 |
| `cube_bench_reusable.py` | 在前者基础上整理出的复用版，增加逐 case 隔离、报告生成、HTTPS `--insecure`、更完整上下文记录和更稳健参数校验。 | 推荐用于新测试和跨环境复用。 |

若没有历史兼容需求，优先使用 `cube_bench_reusable.py`；若要复现早期测试方法或只需要一个轻量直接 runner，可以使用 `run_cube_bench_envd.py`。

## 1. 远端验证状态

已在远程服务器 `root@192.168.25.90` 上补做 smoke 验证。

验证命令：

```bash
python3 scripts/run_cube_bench_envd.py \
  --cube-api http://127.0.0.1:3000 \
  --template-id tpl-bca9467038864260a79d908c \
  --suite smoke \
  --case 00-versions \
  --case sysbench-prime \
  --delete \
  --results-dir /home/lyq/cube-bench-script-smoke-20260715-170918/run-envd-smoke
```

验证结果：

| case | rc | elapsed_sec | stdout_bytes |
|---|---:|---:|---:|
| `00-versions` | 0 | 0.263 | 993 |
| `02-sysbench-prime` | 0 | 5.014 | 886 |

远端结果目录：

```bash
/home/lyq/cube-bench-script-smoke-20260715-170918/run-envd-smoke
```

远端结果归档：

```bash
/home/lyq/cube-bench-script-smoke-20260715-170918/run-envd-smoke.tar.gz
```

测试结束后已确认远端没有残留 Sandbox：

```text
SANDBOX_COUNT    0
```

## 2. 运行前提

运行机需要满足：

- Python 3.10 或更高版本。
- 能访问 CubeAPI，默认 `http://127.0.0.1:3000`。
- 能直接访问 Sandbox 内网 IP 的 `49983` 和 `49999` 端口。
- `cubemastercli` 在 `PATH` 中，除非复用已有 Sandbox 且显式传入 `--sandbox-ip`。
- Template 来自 `cube-bench-suite` 镜像，并已暴露 envd `49983`。

该脚本不走 CubeProxy，也不走 E2B SDK。如果运行机无法访问 Sandbox 内网 IP，应使用 `cube_bench_sdk.py`。

## 3. 基本命令

查看参数：

```bash
python3 scripts/run_cube_bench_envd.py --help
```

运行 smoke 套件：

```bash
python3 scripts/run_cube_bench_envd.py \
  --cube-api http://127.0.0.1:3000 \
  --template-id <template_id> \
  --suite smoke \
  --delete \
  --results-dir ./results/run-envd-smoke
```

运行正式套件：

```bash
python3 scripts/run_cube_bench_envd.py \
  --cube-api http://127.0.0.1:3000 \
  --template-id <template_id> \
  --suite formal \
  --delete \
  --results-dir ./results/run-envd-formal
```

只运行指定 case：

```bash
python3 scripts/run_cube_bench_envd.py \
  --template-id <template_id> \
  --suite smoke \
  --case 00-versions \
  --case sysbench-prime \
  --delete
```

复用已有 Sandbox：

```bash
python3 scripts/run_cube_bench_envd.py \
  --sandbox-id <sandbox_id> \
  --sandbox-ip <sandbox_ip> \
  --suite smoke \
  --results-dir ./results/run-envd-existing
```

## 4. 参数说明

| 参数 | 说明 |
|---|---|
| `--cube-api` | CubeAPI 地址，默认读取 `CUBE_API`，否则为 `http://127.0.0.1:3000`。 |
| `--template-id` | 从 Template 创建新 Sandbox。未传 `--sandbox-id` 时必填。 |
| `--sandbox-id` | 复用已有 Sandbox。 |
| `--sandbox-ip` | 已有 Sandbox 的内网 IP。省略时使用 `cubemastercli cubebox info` 解析。 |
| `--sandbox-timeout` | 创建 Sandbox 时传给 CubeAPI 的 timeout，默认 `3600`。 |
| `--results-dir` | 宿主机结果目录。 |
| `--suite` | `smoke` 或 `formal`，默认 `smoke`。 |
| `--case` | 指定 case，可重复。支持完整 case 名或去掉数字前缀后的名称。 |
| `--cwd` | Sandbox 内执行命令的工作目录，默认 `/opt/cube-bench`。 |
| `--delete` | 测试结束后删除脚本创建或复用的 Sandbox。 |
| `--no-tar` | 不生成 `.tar.gz` 归档。 |

## 5. 输出文件

每个 case 会生成：

| 文件 | 内容 |
|---|---|
| `<case>.cmd` | 实际执行的 benchmark 命令。 |
| `<case>.stdout` | envd 返回的 stdout。 |
| `<case>.stderr` | envd 返回的 stderr。 |
| `<case>.rc` | 退出码。 |
| `<case>.events.json` | Connect frames 解码后的事件。 |
| `<case>.raw` | envd 原始响应。 |

结果目录还包含：

| 文件 | 内容 |
|---|---|
| `context.json` | CubeAPI、Template、Sandbox、Sandbox IP、envd URL 等上下文。 |
| `health.txt` | `49983 /health` 和 `49999 /health` 检查结果。 |
| `summary.json` | 每个 case 的退出码、耗时、输出大小和错误。 |
| `<results-dir>.tar.gz` | 结果目录归档，除非传入 `--no-tar`。 |

该脚本不会生成 Markdown 报告。若需要报告、逐 case 隔离或更完整 CSV/Markdown 输出，使用 `cube_bench_reusable.py`。

## 6. CSV 汇总

`run_cube_bench_envd.py` 的结果目录结构与 envd 汇总脚本兼容，可以用：

```bash
python3 scripts/summarize_cube_bench_envd_csv.py \
  --results-dir ./results/run-envd-smoke \
  --output ./results/run-envd-smoke-summary.csv
```

生成的 CSV 是长表格式，一行一个指标，适合后续用 Excel、pandas 或数据库汇总。

## 7. 与 `cube_bench_reusable.py` 的选择

优先选择 `cube_bench_reusable.py` 的情况：

- 要在其他 CubeSandbox 环境复用标准测试方法。
- 要正式跑 full/formal benchmark。
- 要每个 case 创建独立 Sandbox。
- 要自动生成 `benchmark-report.md`。
- 要使用 HTTPS CubeAPI 或临时诊断自签证书问题。

可以选择 `run_cube_bench_envd.py` 的情况：

- 要复现早期测试脚本行为。
- 只需要最小 envd 命令执行验证。
- 希望输出尽量接近 envd 原始响应。

二者不能替代 SDK 版脚本。如果运行机只能通过 CubeProxy/SDK 访问 Sandbox，应使用 `cube_bench_sdk.py`。
