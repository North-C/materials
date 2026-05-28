# E2B Runtime 任务镜像说明

本文档总结三个已经转换为 E2B runtime 形态的 Terminal-Bench 任务镜像。三者均面向 ARM64，基于 `e2bdev/base:latest` 构建，保留 E2B sandbox 所需的基础运行环境，并安装 `systemd`、`systemd-sysv`、`openssh-server`、`sudo`、`chrony`、`linuxptp`、`socat`、`curl`、`passwd` 等包。

这些镜像与早期 Docker 自运行版不同：镜像默认不自动执行 benchmark 任务，任务需要在 E2B sandbox 创建后，通过 CLI `e2b sandbox exec` 或 SDK 的 `commands.run()` 显式触发。这样可以避免 Dockerfile 中的 `ENTRYPOINT`/`CMD` 被 E2B template build 解释为 template start command。

## 镜像清单

| 任务 | Docker Hub 镜像 | 推荐标签 | 任务入口 |
| --- | --- | --- | --- |
| analyze-access-logs | `xdlyqdocker/tbench-analyze-access-logs-e2b-runtime` | `20260518-arm64` | `/usr/local/bin/tbench-analyze-access-logs` |
| train-bpe-tokenizer | `xdlyqdocker/tbench-train-bpe-tokenizer-e2b-runtime` | `20260518-arm64` | `/usr/local/bin/tbench-train-bpe-tokenizer` |
| large-scale-text-editing | `xdlyqdocker/tbench-large-scale-text-editing-e2b-runtime` | `20260528-arm64` | `/usr/local/bin/tbench-large-scale-text-editing` |

## 任务内容

### analyze-access-logs

该任务处理 Apache/Nginx 风格的访问日志，执行内容包括：

- 读取 `/app/access_log`。
- 统计总请求数、唯一 IP 数、404 错误数。
- 统计 Top 3 URL。
- 生成 `/app/report.txt`。
- 运行内置测试校验报告格式与统计结果。

该任务主要是文本扫描、排序、聚合和文件写入，CPU 占用较低，适合作为短时 I/O 与文本处理任务。

### train-bpe-tokenizer

该任务训练一个简化 BPE tokenizer，执行内容包括：

- 准备 `/app/doc` 下的英文语料。
- 生成 `/app/eng_docs.txt`。
- 训练 BPE merge 规则。
- 输出 `/app/tokens.txt`、`/app/merges.txt` 和 `/app/train.py`。
- 运行 tokenizer 正确性与输出文件测试。

该任务包含 Python 代码生成、文本读取、词频统计、BPE merge 训练和文件写入，属于短时但具备代码执行特征的任务。

### large-scale-text-editing

该任务生成大规模 CSV 文本并用 Vim macro 完成批量编辑，执行内容包括：

- 根据 `--rows` 生成 `/app/input.csv`。
- 生成 `/app/apply_macros.vim`。
- 使用 headless Vim 执行宏，将 CSV 字段清理、重排、大小写转换并追加标记。
- 在测试阶段生成 `/app/expected.csv`。
- 对 `/app/input.csv` 与 `/app/expected.csv` 做哈希比较。

该任务包含大文件生成、脚本生成、Vim 批处理、文件读写和结果校验。可通过 `--rows` 控制任务时长。

## 启动方式

### Docker 直接验证

E2B runtime 镜像默认不自动执行任务。直接用 Docker 验证时，应显式指定任务入口。

```bash
docker run --rm \
  --entrypoint /usr/local/bin/tbench-analyze-access-logs \
  xdlyqdocker/tbench-analyze-access-logs-e2b-runtime:20260518-arm64 \
  --mode run
```

```bash
docker run --rm \
  --entrypoint /usr/local/bin/tbench-train-bpe-tokenizer \
  xdlyqdocker/tbench-train-bpe-tokenizer-e2b-runtime:20260518-arm64 \
  --mode run
```

```bash
docker run --rm \
  --entrypoint /usr/local/bin/tbench-large-scale-text-editing \
  xdlyqdocker/tbench-large-scale-text-editing-e2b-runtime:20260528-arm64 \
  --mode run --rows 1000000
```

### E2B CLI 执行

将镜像转换为 E2B template 并创建 sandbox 后，通过 `sandbox exec` 后置执行任务：

```bash
e2b sandbox exec <SANDBOX-ID> \
  "bash -lc '/usr/local/bin/tbench-analyze-access-logs --mode run'"
```

```bash
e2b sandbox exec <SANDBOX-ID> \
  "bash -lc '/usr/local/bin/tbench-train-bpe-tokenizer --mode run'"
```

```bash
e2b sandbox exec <SANDBOX-ID> \
  "bash -lc '/usr/local/bin/tbench-large-scale-text-editing --mode run --rows 1000000'"
```

如果在 sandbox 内部已经进入 shell，也可以直接执行：

```bash
/usr/local/bin/tbench-analyze-access-logs --mode run
/usr/local/bin/tbench-train-bpe-tokenizer --mode run
/usr/local/bin/tbench-large-scale-text-editing --mode run --rows 1000000
```

`large-scale-text-editing` 的修复版已确保即使当前目录不是 `/app`，也会在 `/app` 下生成输入、预期文件和测试结果。

### Python SDK 执行

```python
from e2b import Sandbox

sbx = Sandbox.create(template="your-template-id-or-alias")

try:
    result = sbx.commands.run(
        "/usr/local/bin/tbench-large-scale-text-editing --mode run --rows 1000000",
        timeout=300,
    )
    print(result.stdout)
    print(result.stderr)
finally:
    sbx.kill()
```

## 预估执行时间

以下时间来自 ARM64 远程服务器上的实际验证，镜像层已在本地存在时计时。E2B 平台上的时间会受到 sandbox 冷启动、资源规格、镜像/template 缓存和网络状态影响。

| 任务 | 参数 | 远端 ARM64 实测耗时 | 用途 |
| --- | --- | ---: | --- |
| analyze-access-logs | `--mode run` | 约 1.2 秒 | 短时日志分析任务 |
| train-bpe-tokenizer | `--mode run` | 约 5.8 秒 | 短时文本训练与代码任务 |
| large-scale-text-editing | `--mode run --rows 10000` | 约 2.2 秒 | 短时 smoke test |
| large-scale-text-editing | `--mode run --rows 1000000` | 约 1 分 46 秒 | 长时大文件文本处理任务 |

## 吞吐量指标

`large-scale-text-editing` 支持把每次任务完成事件写入宿主机可读的 metrics 目录。每次 `run` 或 `verify` 完成后都会写入一个独立 JSON 文件，文件名包含完成时间、任务名、run id 和 iteration。该设计适合多个容器并发写入同一个宿主机目录，宿主机可按时间窗口统计完成数和吞吐量。

容器侧启动示例：

```bash
mkdir -p /var/lib/tbench-metrics

docker run --rm \
  -v /var/lib/tbench-metrics:/metrics \
  --entrypoint /usr/local/bin/tbench-large-scale-text-editing \
  xdlyqdocker/tbench-large-scale-text-editing-e2b-runtime:20260528-arm64 \
  --mode run --rows 1000000 \
  --metrics-dir /metrics \
  --run-id worker-001
```

也可以使用环境变量：

```bash
docker run --rm \
  -v /var/lib/tbench-metrics:/metrics \
  -e TBENCH_METRICS_DIR=/metrics \
  -e TBENCH_RUN_ID=worker-001 \
  --entrypoint /usr/local/bin/tbench-large-scale-text-editing \
  xdlyqdocker/tbench-large-scale-text-editing-e2b-runtime:20260528-arm64 \
  --mode run --rows 1000000
```

每个完成事件的 JSON 结构类似：

```json
{
  "schema_version": 1,
  "event": "task_completion",
  "task_id": "large-scale-text-editing",
  "mode": "run",
  "rows": 1000000,
  "run_id": "worker-001",
  "iteration": 1,
  "status": "pass",
  "exit_code": 0,
  "started_at": "2026-05-28T10:00:00.000000Z",
  "finished_at": "2026-05-28T10:01:46.000000Z",
  "started_at_ms": 1780000000000,
  "finished_at_ms": 1780000106000,
  "duration_ms": 106000,
  "hostname": "container-id",
  "pid": 1,
  "output": "/app/score.json"
}
```

宿主机统计最近 10 分钟吞吐量：

```bash
python3 research/agent_cpu_sandbox_toolkit/tools/summarize_tbench_metrics.py \
  /var/lib/tbench-metrics \
  --task-id large-scale-text-editing \
  --window-seconds 600
```

按 60 秒分桶统计：

```bash
python3 research/agent_cpu_sandbox_toolkit/tools/summarize_tbench_metrics.py \
  /var/lib/tbench-metrics \
  --task-id large-scale-text-editing \
  --window-seconds 600 \
  --bucket-seconds 60
```

输出 JSON 便于进一步整理：

```bash
python3 research/agent_cpu_sandbox_toolkit/tools/summarize_tbench_metrics.py \
  /var/lib/tbench-metrics \
  --task-id large-scale-text-editing \
  --window-seconds 600 \
  --json
```

## 使用建议

- 若用于 E2B template，优先使用 `*-e2b-runtime` 镜像，不要使用早期 `*-self-contained` 或不带 `runtime` 的自运行镜像。
- E2B template 构建后，不需要在 sandbox 内再次 `docker run`，直接调用 `/usr/local/bin/tbench-*` 即可。
- `large-scale-text-editing` 可通过 `--rows` 调节运行时间；建议用 `--rows 10000` 做连通性验证，用 `--rows 1000000` 做长时文本处理测试。
- 需要宿主机统计吞吐量时，为多个容器挂载同一个 metrics 目录，并通过 `--metrics-dir` 或 `TBENCH_METRICS_DIR` 打开完成事件输出。
- 如果通过 E2B CLI 执行，建议使用 `bash -lc '...'` 包裹命令，以避免参数解析和工作目录差异。
