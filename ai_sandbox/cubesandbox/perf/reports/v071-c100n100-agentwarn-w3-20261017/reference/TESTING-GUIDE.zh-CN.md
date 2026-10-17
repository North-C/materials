# 性能测试指南（.90）

以下命令都以 root 身份在 .90 上执行。

## 0. 测试目录与公共前提

```sh
R=/data/cubelet/c100n100-perf-tuning-90/20261016T104049Z
cd $R
```

```text
$R/
  scripts/                     # run_series.py、run_round_w3.py、summarize.py、state_snapshot.py、change.sh
  tool/                        # profiler 与 capture_w3.py
  bin/cube-bench               # cube-bench v0.7.1 linux-arm64，SHA256 ae2f32cc…
  capture100.local.json        # 原模板配置（含密钥，不要外传）
  capture100.agentwarn.json    # 新模板配置
  snapshot-pause-resume-c10-20261017/    # pause/resume 测试目录（c10）
  snapshot-pause-resume-c100-20261017/   # pause/resume 测试目录（c100）
```

可用模板（均为 2 vCPU / 2048Mi / 1G 可写层）：

| 模板 ID | 配置文件 | 说明 |
|---|---|---|
| `tpl-cf2b04fdd4604b7c84e157fa` | `capture100.local.json` | 原模板 |
| `tpl-381852bfe518c30bb815e163` | `capture100.agentwarn.json` | `agent.log=warn` 新模板，需要已部署 Shim-A 或 Shim-C |

测试开始前：
- 确认沙箱库存为 0，并且没有其他人在用这台机器。
- 记录主机状态：

```sh
python3 scripts/state_snapshot.py <状态名>-state.json
```

---

## 1. 100 并发创建测试（c100n100）

### 1.1 变量

| 变量 | 说明 | 默认 |
|---|---|---|
| `CAPTURE_CONFIG` | 配置文件；使用新模板时设为 `$R/capture100.agentwarn.json` | `$R/capture100.local.json` |
| `E2B_API_KEY` | API 密钥；配置里已写 `api_key` 时不需要设置 | 读取配置中的 `api_key` |

`run_series.py` 的参数为 `SESSION STATE ROUNDS`：

| 参数 | 含义 |
|---|---|
| `SESSION` | 测试目录 `$R` |
| `STATE` | 状态名，也是输出子目录，如 `s14-xxx` |
| `ROUNDS` | 轮数。正式测试用 5 轮；试跑（pilot）用 1 轮 |

配置文件中的固定要求（已满足，修改时注意）：
- `warmup` 必须为 `0`，3 次预热由 cube-bench 进程内的 `-w 3` 完成；
- `cubemastercli.exclusive_template` 必须为 `true`；
- 模板规格必须是 `2000m / 2048Mi / 1G`。

### 1.2 执行

```sh
cd $R
export CAPTURE_CONFIG=$R/capture100.agentwarn.json     # 用原模板时不设置

python3 scripts/state_snapshot.py s14-state.json
python3 scripts/run_series.py $R s14-pilot 1           # 试跑 1 轮，不计入结果
python3 scripts/run_series.py $R s14-xxx 5             # 正式 5 轮
```

- 每轮开始前，脚本会等待机器空闲：库存为 0、没有 cube-bench/Shim 进程、load1 < 4。
- 每轮结束后，脚本按 ID 删除本轮创建的 103 个实例。任一轮失败即停止。
- 一次 pilot 加 5 轮正式测试约 3–5 分钟。

如果某个状态需要修改主机参数，在 `state_snapshot.py` 之前执行。修改会记录到 `changes.jsonl`，回退命令追加到 `restore-host.sh`：

```sh
bash scripts/change.sh $R rcu_expedited /sys/kernel/rcu_expedited 1
```

### 1.3 结果

```sh
cat s14-xxx/progress.log                                    # 每轮一行 JSON
python3 scripts/summarize.py $R s13-madvrandom s14-xxx > comparison-s14.json   # 多状态对比
```

- 主指标：每轮的 `total_ms`，即 cube-bench 的 `summary.total_time_s`，取 5 轮中位数。
- 合格标准：每轮 `ok` 为 100、`errors` 为 0、`cleanup` 为 `complete`、`deleted` 为 103。
- 每轮的明细在 `s14-xxx/round-NN/`：
  - 原始结果：`runs/*/capture/startup-latency/benchmark.raw.json`
  - 报告：`runs/*/analysis/report.html`

参考值（5 轮中位数）：s00 基线 283.6ms，s13 全部优化后 153.7ms。

### 1.4 异常处理

- **中断后有残留实例**：对中断的那一轮执行以下命令，只清理、不压测：

```sh
python3 scripts/run_round_w3.py --config ${CAPTURE_CONFIG:-$R/capture100.local.json} --tool-dir $R/tool \
  --binary $R/bin/cube-bench --expected-sha256 ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511 \
  --output $R/<STATE>/round-NN --cleanup-only
```

- **门禁超时（退出码 4）**：查看 `progress.log` 最后一行 `gate_timeout`，判断是库存、进程还是负载不满足。
- **换 cube-bench 二进制**：必须同步修改 `scripts/run_series.py` 中的 `BIN_SHA`。
- **恢复到调优前状态**：执行 `bash restore-to-start.sh`。要求库存为 0，会重启一次 Cubelet。

---

## 2. pause/resume 并发测试

### 2.1 变量

`run_once.py` 不读取环境变量，下列取值直接写在脚本里：

| 项目 | 当前值 | 修改位置 |
|---|---|---|
| API 地址、模板、密钥 | 读取 `$R/capture100.agentwarn.json` | `SESSION` 常量 |
| 模板断言 | `tpl-381852bfe518c30bb815e163` | `assert config['template_id'] == …` |
| 并发数 | c10 目录为 10，c100 目录为 100 | 共 4 处：docstring、`'concurrency'`、`run_round(N)`、`len(values) == N` |
| 预热 | 3 次 c1 的 create → pause → resume → 清理 | — |

依赖 `cubesandbox` SDK（`pip install "cubesandbox>=0.2.0"`）。

### 2.2 执行

```sh
D=$R/snapshot-pause-resume-c100-20261017      # c10 用 snapshot-pause-resume-c10-20261017
cd $D
python3 $R/scripts/state_snapshot.py state-before.json
python3 -u run_once.py > run.log 2>&1; echo rc=$?
```

要测其他并发档位时，复制 c10 目录，按 2.1 修改 4 处并发数。

### 2.3 结果

| 文件 | 内容 |
|---|---|
| `result.json` | `formal`：pause、resume 的墙钟时间和均摊时间；`statistics`：单请求 mean/p50/p95/max；`cleanup`：清理情况 |
| `owned.json` | 本次创建的全部沙箱 ID |
| `inventory-before.json` / `inventory-after.json` | 前后库存，都应为 `[]` |
| `run.log` | 控制台输出 |

合格标准：`status` 为 `success`，`cleanup.remaining_owned` 为空，`total_inventory_after` 为 0。

参考值（2026-10-17，新模板）：

| 并发 | pause 墙钟 | pause p50 | resume 墙钟 | resume p50 |
|---|---|---|---|---|
| c10 | 144ms | 124ms | 151ms | 142ms |
| c100 | 1542ms | 939ms | 368ms | 271ms |
