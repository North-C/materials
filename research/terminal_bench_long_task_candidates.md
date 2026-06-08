# Terminal-Bench Long-Running Task Candidates

## Objective

当前 v0-ready 任务多数在数秒内完成，适合 smoke、runc/Kata 对比和工具链验证，但不适合形成稳定的中长时 CPU 负载。本文在已有 Terminal-Bench 本地仓库 `original-tasks/` 上继续筛选相对长时任务，用于后续在 AI 沙箱中做 CPU 负载和性能表现分析。

筛选仍遵循当前约束：

1. 不直接依赖大模型 API。
2. 尽量离线运行，避免运行时 `apt/pip/npm/cargo` 在线下载。
3. 使用确定性 verifier。
4. 适合 Replay Trajectory 或 Fixed Output。
5. 负载主要来自沙箱内本地执行，而不是网络、模型推理或外部服务。

## Additional Long-Task Filter

为了避免“看似复杂但运行很短”的任务，长时任务额外按以下标准筛选：

1. replay 后仍有真实执行负载：官方 `solution.sh` 不能只是硬编码答案。
2. fixed 后仍有验证负载：如果 fixed 只校验一个已有小文件，则不作为主要长时模式。
3. 可扩展：输入规模、迭代次数、压缩等级、文件数量或编译并发度可以稳定放大。
4. CPU 侧可解释：能归类为文本处理、压缩归档、编译构建、查询执行、算法搜索或解释型语言执行。
5. 镜像依赖可收敛：即使当前镜像不满足，也能通过一个离线长任务镜像解决。

当前远端 `golang:1.25.0` 容器内已确认有 `python3/gcc/g++/make/tar/gzip/sha256sum`，缺少 `vim/zstd/file/unzip/sqlite3/rustc/bc`。宿主机工具更完整，但不能代表沙箱镜像能力。

## Recommended Long Task Set

| Priority | Task | Main Load | Replay Suitability | Fixed Output Suitability | Environment Delta | Rationale |
|---|---|---|---|---|---|---|
| P0 | `jsonl-aggregator` scaled variant | JSONL 生成、扫描、聚合、排序 | 高，已跑通；放大记录数即可 | 中，高负载主要在 verifier 聚合时可保留 | 当前 runner 已支持，需加入规模参数 | 已是 v0-ready，最小改动即可从秒级扩展到十秒/分钟级 |
| P0 | `large-scale-text-editing` | 100 万行 CSV 上执行 Vim 宏，多轮文本替换 | 高，solution 生成宏并由测试执行 Vim | 高，但需要 artifact-only fixed：保留 `apply_macros.vim`，重置原始 `input.csv` | 需要 `vim`，runner 需执行 `gen_large_csv.py both` 并挂载 `/tests` | 真实终端编辑任务，CPU/内存/文件 IO 都明显，且测试 timeout 已给到 600s |
| P0 | `deterministic-tarball` | 文件树扫描、权限/换行归一化、tar、`zstd -19 --long` | 高，solution 生成 `build.sh` | 高，fixed verifier 会多次重新执行 `build.sh` | 需要 `zstd/file/zstdcat`，runner 需执行 `setup_source_tree.sh` | 归档压缩负载稳定，适合观察单线程压缩、文件元数据访问和 page cache 行为 |
| P1 | `sqlite-with-gcov` | SQLite 源码解包、configure、gcov 编译、并行 make | 高，replay 是真实编译 | 低，fixed 后测试只验证已编译产物，编译负载消失 | 需要 `fossil/jimsh/tclsh/sqlite3/gcov` 等离线镜像依赖 | 适合作为多核编译构建型长任务，CPU 饱和度高，和 Agent 终端修复类任务接近 |
| P1 | `write-compressor` | Rust 编译 + 动态规划压缩器执行 | 高，replay 会编译并压缩 | 低，fixed 主要解压校验，压缩负载消失 | 需要 `rustc/bc`，并预编译或构建 `decomp` | 算法型 CPU 任务，适合补充单进程计算负载，但 fixed 不应作为主模式 |
| P1 | `query-optimize` | SQLite 大库查询、golden/solution 多轮 runtime 对比 | 中，solution 只写 SQL，重负载在 tests | 高，fixed verifier 仍会执行 5 轮查询 | 需要离线提供 `oewn.sqlite` 和 `sqlite3`/Python sqlite | 非编译型、非文本型的数据库查询负载，适合观察 cache/memory/branch 行为 |
| P2 | `train-bpe-tokenizer` | 纯 Python BPE 训练、排序、Counter、正则替换 | 中，当前数据偏小，需要扩展语料或 vocab | 中，fixed 后主要 tokenization 校验，不一定重训 | 当前镜像有 Python；runner 需处理 Dockerfile COPY 到 `/app/tokenize.py` | 依赖最轻，适合作为解释型语言 CPU 负载，但要做 scaled variant 才够长 |
| P2 | `count-call-stack` scaled variant | 解压 stack log、正则解析、top-N 聚合 | 中，官方数据偏小，需要扩展日志 | 中，fixed 校验可保持解析负载但默认很短 | 需要 `unzip` 或 runner 用 Python zipfile 初始化 | 作为日志分析类长任务补充可行，但优先级低于 `large-scale-text-editing` |

## Recommended First Batch

第一批建议只引入 4 个长任务，覆盖不同 CPU 行为，避免一次性扩大太多适配面：

| Task | Suggested Mode | Target Duration | Why First |
|---|---|---|---|
| `jsonl-aggregator` scaled | replay + fixed | 30s、2min 两档 | 已跑通，最容易形成可控长负载 |
| `large-scale-text-editing` | replay + artifact-only fixed | 1-5min | 真实终端编辑负载，和 Agent 使用 shell/editor 的场景高度贴近 |
| `deterministic-tarball` | replay + fixed | 30s-3min | 压缩归档负载稳定，fixed 也能重新执行重负载 |
| `sqlite-with-gcov` | replay only | 1-8min | 多核编译构建，能补足当前 v0 缺少的 build workload |

第二批再引入：

| Task | Suggested Mode | Reason |
|---|---|---|
| `write-compressor` | replay only | 算法计算 + Rust 编译，但 fixed 负载不足 |
| `query-optimize` | fixed + replay | 需要先离线准备数据库文件 |
| `train-bpe-tokenizer` scaled | replay | 轻依赖、纯 Python，可作为解释型 CPU 长负载 |

## Mode Notes

### Replay Trajectory

Replay 适合所有推荐任务，但要避免 oracle hardcode 任务。例如 `weighted-max-sat-solver` 静态看起来是优化求解任务，但当前 oracle 直接写出固定目标值，replay 几乎没有计算负载，因此不进入长任务主集。

### Fixed Output

Fixed Output 不能简单等同于保存 replay 后的整个 `/app` 快照。对会修改输入的任务，应保存 agent 产物并恢复初始输入：

| Task | Fixed Handling |
|---|---|
| `large-scale-text-editing` | 保存 `apply_macros.vim`，但重新生成原始 `input.csv`；否则测试会对已变换文件再次执行宏 |
| `deterministic-tarball` | 可保存 `build.sh` 和原始 `src`，verifier 会多次重新构建 archive |
| `query-optimize` | 保存 `sol.sql`、`my-sql-query.sql` 和只读 DB，verifier 仍执行多轮查询 |
| `sqlite-with-gcov` | fixed 只验证已编译产物，不适合作长负载 |
| `write-compressor` | fixed 只校验 `data.comp`，不适合作长负载 |

## Scaling Knobs

| Task | Scale Parameter | Implementation Direction |
|---|---|---|
| `jsonl-aggregator` | records/file、file count、重复 verifier 次数 | 修改或包装 `generate_records.py`，生成 1M/10M/50M 记录档位 |
| `large-scale-text-editing` | CSV 行数、字段长度、重复执行次数 | 给 `gen_large_csv.py` 增加环境变量，例如 `ROWS=1000000/3000000` |
| `deterministic-tarball` | source tree 文件数、文件大小、zstd level | 在 `setup_source_tree.sh` 后追加生成 `many/`、`deep/`、binary blobs |
| `sqlite-with-gcov` | make 并发、clean rebuild 次数、测试 SQL 轮数 | replay 阶段执行 `make clean && make -jN`，N 可绑定 vCPU 配置 |
| `write-compressor` | `data.txt` 大小、rustc 优化等级、重复压缩次数 | 保持 max compressed size 约束时谨慎放大，避免任务变成不可解 |
| `query-optimize` | DB 大小、`ITERATIONS`、cache pragma | 固定 DB hash，调整测试轮数形成稳定查询耗时 |
| `train-bpe-tokenizer` | corpus 行数、`vocab_size` | 重复官方 doc 或添加合成语料，保持 tokenization expected 稳定 |

## Excluded Long-Looking Tasks

| Task Type | Examples | Exclusion Reason |
|---|---|---|
| ML/GPU/科学计算依赖 | `pytorch-*`, `cartpole-rl-training`, `train-fasttext`, `fmri-encoding-r` | 依赖 torch/R/sklearn/gym/fasttext 等，不利于隔离 CPU 和沙箱开销 |
| OCR/video/图像处理 | `financial-document-processor`, `video-processing` | 依赖 PIL/OpenCV/PyMuPDF/tesseract，镜像重且负载容易偏离 Agent terminal 主场景 |
| 在线数据/包下载 | `build-pmars`, 部分 DB/apt source 任务 | 需要运行时联网；可以后续 vendor 化，但不进入第一批 |
| oracle hardcode | `weighted-max-sat-solver` | replay 不产生求解负载，只能在重写求解 trajectory 后考虑 |

## Runner Changes Needed

为了让这些长任务可复用，runner 需要从当前 v0 的“简单复制 + mini pytest”扩展为 per-task init/profile：

```json
{
  "task_id": "large-scale-text-editing",
  "init": [
    "copy_dockerfile_sources",
    "run_python /app/gen_large_csv.py both",
    "mount_tests_dir"
  ],
  "artifacts": ["apply_macros.vim"],
  "fixed_strategy": "artifact_only_reset_input",
  "runtime_deps": ["python3", "vim"],
  "scale": {
    "rows": 1000000
  }
}
```

建议新增一个 `task_profile.json` 层，不把每个任务的特殊初始化硬编码进 runner。这样后续可以把“Ready 短任务”和“Long 任务”放在同一个执行框架里，用 profile 控制初始化、artifact 保存、fixed 策略和规模档位。

## Conclusion

当前最值得推进的长任务不是一次性扩展很多 Terminal-Bench task，而是先形成一个小而稳定的长负载矩阵：

1. `jsonl-aggregator` scaled：数据扫描/聚合。
2. `large-scale-text-editing`：终端编辑 + 大文本处理。
3. `deterministic-tarball`：文件系统 + 压缩归档。
4. `sqlite-with-gcov`：多核编译构建。

这四类负载覆盖了 Agent 在 AI 沙箱中常见的本地执行模式，也能在不调用大模型 API 的前提下，把任务时长从当前秒级提升到十秒、分钟级。
