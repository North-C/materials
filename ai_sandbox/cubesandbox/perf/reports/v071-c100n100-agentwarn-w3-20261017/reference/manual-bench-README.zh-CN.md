# 手动性能测试：cube-bench 100 并发与 pause/resume

测试目录：`/data/cubelet/c100n100-perf-tuning-90/manual-bench/`。所有命令都以 root 身份在 .90 上执行。

## 1. 目录内容

```text
manual-bench/
  env.sh                  # 导出 API、模板和 cube-bench 路径等变量
  sandboxes.py            # 沙箱库存检查与清理
  run_c100.sh             # 100 并发创建测试
  run_pause_resume.sh     # pause/resume 并发测试
  pause_resume/           # 仓库原版脚本，未修改
    bench_pause_resume_concurrency.py   # 来自 examples/snapshot-rollback-clone/
    env.py
  results/                # 每次运行生成一个子目录
```

## 2. 变量配置

`env.sh` 不另存任何配置。每次运行时，它直接读取调优会话的配置文件，所以 API 地址、密钥和模板 ID 始终与 `/data/cubelet/c100n100-perf-tuning-90/20261016T104049Z/scripts/run_series.py` 使用的一致。

用 `TPL` 选择模板，默认 `agentwarn`：

| `TPL` | 读取的配置文件 | 模板 ID |
|---|---|---|
| `agentwarn`（默认） | `20261016T104049Z/capture100.agentwarn.json` | `tpl-381852bfe518c30bb815e163`（`agent.log=warn` 新模板） |
| `local` | `20261016T104049Z/capture100.local.json` | `tpl-cf2b04fdd4604b7c84e157fa`（原模板） |

两个模板规格相同，都是 2 vCPU / 2048Mi / 1G 可写层。也可以用 `CONFIG=/path/to/xxx.json` 直接指定配置文件，格式与上面两个文件相同。

`env.sh` 导出的变量如下：

| 变量 | 来源字段 | 使用者 |
|---|---|---|
| `E2B_API_URL` / `E2B_API_KEY` | `api_url` / `api_key` | cube-bench |
| `CUBE_API_URL` / `CUBE_API_KEY` | `api_url` / `api_key` | cubesandbox Python SDK、`sandboxes.py` |
| `CUBE_TEMPLATE_ID` | `template_id` | 全部 |
| `CUBE_BENCH` | `benchmark_binary`；如果运行前已设置该变量，以已设置的值为准 | `run_c100.sh`，默认 `20261016T104049Z/bin/cube-bench`（v0.7.1） |

查看当前生效的值：

```sh
cd /data/cubelet/c100n100-perf-tuning-90/manual-bench
source env.sh && echo $CUBE_API_URL $CUBE_TEMPLATE_ID $CUBE_BENCH
TPL=local bash -c 'source env.sh && echo $CUBE_TEMPLATE_ID'
```

## 3. 运行前检查

```sh
cd /data/cubelet/c100n100-perf-tuning-90/manual-bench
bash -c 'source env.sh && python3 sandboxes.py count'   # 期望 inventory 0
cat /proc/loadavg                 # load1 建议 < 4
```

两个测试脚本启动时都会检查库存。只要库存不为 0，脚本就拒绝运行，因为结束时会删除该模板的全部沙箱。请确认测试期间没有其他人在用这台机器。

## 4. 100 并发创建测试

```sh
./run_c100.sh                     # 新模板，c100 n100 -w 3
TPL=local ./run_c100.sh           # 原模板
C=50 N=50 ./run_c100.sh           # 修改并发数和总数
DRY_RUN=1 ./run_c100.sh           # 不连服务端，只演练流程
```

| 变量 | 默认 | 含义 |
|---|---|---|
| `C` | 100 | 并发数，即 cube-bench 的 `-c` |
| `N` | 100 | 正式创建总数，即 `-n` |
| `W` | 3 | 进程内预热次数，即 `-w`。预热不计入 `total_time_s` |
| `DRY_RUN` | 空 | 设为 1 时加 `-dry-run`，跳过库存检查和清理 |

实际执行的命令：

```sh
$CUBE_BENCH -c 100 -n 100 -w 3 -m create-only -no-tui -t $CUBE_TEMPLATE_ID -o results/<目录>/benchmark.json
```

结束时，脚本会删除该模板的全部沙箱（N+W 个，默认 103 个）。即使测试失败或被 Ctrl-C 中断，也会执行清理。

结果在 `results/c100n100-<时间>/`：

| 文件 | 内容 |
|---|---|
| `summary.txt` | 整轮耗时 `total_time_ms`、成功数和错误数、QPS、单请求 create_ms 的 p50/p90/p95/p99/max |
| `benchmark.json` | cube-bench 原始结果，主指标是 `summary.total_time_s` |
| `console.log` | cube-bench 输出 |
| `state.json` | 运行前的主机状态（内核参数、服务二进制哈希等） |
| `cleanup.log` | 清理结果，`remaining of template` 应为 0 |

**参考值**：在 .90 当前状态下（新模板、所有优化都已生效），2026-10-16 测得整轮中位数约为 154ms。单轮会有波动，建议连续跑 5 次取中位数，每次之间等 load1 回落。

## 5. pause/resume 并发测试

```sh
./run_pause_resume.sh             # 新模板，c100，3 轮正式测试
C=10 N=5 ./run_pause_resume.sh    # c10，5 轮
```

| 变量 | 默认 | 含义 |
|---|---|---|
| `C` | 100 | 并发数：每轮创建 C 个沙箱，然后并发 pause，再并发 resume |
| `N` | 3 | 正式轮数，即脚本的 `-n` |
| `S` | 2 | 轮间等待秒数，即 `-s` |

脚本流程：
- 每轮先**逐个**创建 C 个沙箱，创建时间不计入结果。
- 只计时并发 pause 和并发 resume 两段。
- 每轮结束后由脚本自己删除本轮的沙箱。
- 正式轮之前，会先跑 1 轮相同并发的预热，结果丢弃。
- c100 每轮约 1 分钟。

结果在 `results/pause-resume-c100-<时间>/`：

| 文件 | 内容 |
|---|---|
| `output.txt` | 汇总表：pause 和 resume 各自的 avg/min/p95/max 墙钟时间（ms），以及均摊到每个沙箱的时间 `per_pause` / `per_resume` |
| `state.json` | 运行前的主机状态 |
| `cleanup.log` | 兜底清理结果。正常情况下显示 `no sandbox of …` |

**参考值**：2026-10-17 用新模板、1 轮正式测试，c100 的 pause 墙钟时间为 1542ms，resume 为 368ms；c10 分别为 144ms 和 151ms。那次测试的预热方式是 3 次 c1，与本脚本的预热方式不同，比较时注意这一点。

## 6. 异常处理

| 情况 | 处理 |
|---|---|
| 提示 `inventory is not empty` | 先 `bash -c 'source env.sh && python3 sandboxes.py count'` 查看。确认是自己之前测试残留的，再按模板清理：`TPL=local bash -c 'source env.sh && python3 sandboxes.py cleanup'` |
| 只清理不测试 | `bash -c 'source env.sh && python3 sandboxes.py cleanup'`。只删除当前 `TPL` 对应模板的沙箱 |
| 想换 cube-bench 版本 | 运行时指定：`CUBE_BENCH=/path/to/cube-bench ./run_c100.sh` |
| SDK 缺失 | `pip install "cubesandbox>=0.2.0"`（.90 已安装 0.7.0） |
