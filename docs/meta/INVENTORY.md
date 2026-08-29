# Materials 事实清单与风险

- 盘点日期：2026-08-20
- 当前独立 worktree 基线：`f036fd2`
- 主检出区：`/home/lyq/Projects/materials`，全程只读

状态复核：2026-08-27 主检出区仍为 HEAD `f036fd2`、2 个 modified、70 个 untracked 文件级条目、0 staged；普通 `git status --short` 会把部分未跟踪目录折叠为 48 条显示项。当前本地 `main` 相对已知 `origin/main` 落后 3 个提交，后续 Workspace 开始前必须重新确认目标基线；原始 baseline 统计未重新解释为新盘点。

本文件把“已提交基线”“主检出区已修改内容”“主检出区未跟踪/忽略内容”分开记录。统计按路径和扩展名完成，不代表对每个文件内容质量的判断。`github-tokens.md` 只检查了 Git 跟踪状态，没有读取或复制其内容。

## 已验证事实

### Git 与已提交结构

- 当前独立 worktree 位于分支 `North-C/materials-information-architecture`，开始盘点时状态干净，HEAD 为 `f036fd2`。
- HEAD 有 708 个已跟踪文件。根目录原先没有 `README.md`、`.gitignore`、根级 `.gitattributes` 或 `docs/meta/`。
- 最近历史主要增加 CubeSandbox 分析、benchmark、调试证据、AgentENV 和内存容量报告；对根 README、根 `.gitignore` 与 `docs/meta/` 的历史查询无结果。
- 已有 14 个 README/INDEX 类入口，但分布在子目录；CubeSandbox 项目根 `ai_sandbox/cubesandbox/` 没有总 README。
- `virtualization/.gitattributes` 对 `*.pdf` 启用 Git LFS；当前有 6 份 PDF 由 LFS 管理。

已提交文件按互斥扩展名规则统计如下：

| 类别 | 数量 | 统计口径 |
|---|---:|---|
| Markdown | 346 | `*.md`，其中包含 1 个未读取的高风险命名文件 |
| 图片 | 64 | png/jpg/jpeg/gif/svg/webp |
| 日志/trace | 13 | log/jsonl/trace 或位于 `logs/` |
| 脚本/源码 | 65 | sh/py/mjs/js/bt/c |
| 归档 | 0 | tar/tar.gz/tgz/zip/gz/xz/bz2/7z |
| PDF | 6 | 全部命中现有 LFS 规则 |
| Excalidraw | 2 | 可编辑图源 |
| 其他 | 212 | CSV、JSON、TSV、配置、patch、LFS pointer 对应工作区文件等 |
| 合计 | 708 | `git ls-files` |

### 主检出区状态

主检出区相对 `main`/`origin/main` 的只读状态为：

- 已修改、未暂存：2 个。
- 已暂存：0 个。
- 未跟踪：70 个。
- 被当前 ignore 规则忽略且仍存在：6 个。

已修改路径（未读取 diff）：

- `research/agent_cpu_sandbox_toolkit/terminal-bench-tasks/large-scale-text-editing/Dockerfile.e2b`
- `research/agent_cpu_sandbox_toolkit/terminal-bench-tasks/large-scale-text-editing/Dockerfile.e2b-perf`

主检出区全部 784 个非 `.git` 文件按同一规则统计：

| 类别 | 全部 | 其中未跟踪 |
|---|---:|---:|
| Markdown | 355 | 9 |
| 图片 | 65 | 1 |
| 日志/trace | 15 | 2 |
| 脚本/源码 | 86 | 21 |
| 归档 | 3 | 3 |
| PDF | 6 | 0 |
| Excalidraw | 5 | 3 |
| 其他 | 249 | 31 |
| 合计 | 784 | 70 |

未跟踪内容主要集中在：

- CubeSandbox 新问题文档、适配文档、一个 `temp.md` 和一个 Python bytecode。
- `research/agent_cpu_sandbox_toolkit/` 的 Terminal-Bench 任务、Dockerfile、测试、工具、trajectory、vendor 归档与版本 tar。
- `research/agent_ai_trend/research-notes/` 的研究过程文档。
- 三份 Excalidraw 图源、一份 PNG、两份日志、机器/应用状态文件及两个 `tmp/.../dconf/user`。
- 根目录的大型 perf tar。

当前 ignore 命中的 6 个文件包括 `.claude/settings.local.json` 和 5 个研究工具/任务目录下的 `__pycache__/*.pyc`。此外已有 9 个 `.pyc` 被 Git 跟踪，现有 ignore 规则不会自动取消其跟踪。

### 顶层目录与规模

下表是主检出区非 `.git` 文件按首级目录统计；`[root]` 表示直接散落在仓库根目录：

| 顶层 | 文件数 | 观察 |
|---|---:|---|
| `ai_sandbox/` | 507 | 最大内容域；混合项目文档、脚本、图、报告和证据 |
| `research/` | 108 | 研究总结、toolkit、任务、版本快照和过程材料 |
| `virtualization/` | 49 | ARM64/KVM/virtio 文档、图片及 LFS PDF |
| `[root]` | 22 | 主题跨度大，含 Markdown、图源、图片、风险文件和大型 tar |
| `results-direct-lite/` | 17 | 两次运行的 raw/logs/workloads/summary 与配置 |
| `kata-startup-latency-direct-nydus-lite/` | 17 | benchmark 项目包 |
| `kvm/` | 16 | KVM/QEMU 系列文档及未跟踪图源 |
| `kubelet源代码解析/` | 10 | 源码解读和图片 |
| `kata-startup-latency-lite/` | 9 | benchmark 项目包 |
| `kata-startup-latency-direct-lite/` | 9 | benchmark 项目包 |
| `scripts/` | 4 | 根级 benchmark 脚本 |
| `软件工程/` | 3 | 长期方法文档 |
| `Paperwork/` | 2 | 报告/文章 |
| `Ops_records/` | 2 | 操作记录与图片 |
| `bug-fix/` | 2 | 问题修复记录 |
| `每日项目简析/` | 2 | 日常分析 |
| `.claude/`、`katalyst分析/`、`mpam/`、`tracing/`、`unified_bus/` | 各 1 | 小型或单文档入口 |

### 大文件与二进制候选 {#large-file-candidates}

| 路径 | 大小 | Git 状态 | 当前判断 |
|---|---:|---|---|
| `tbench-large-scale-text-editing-profile-perf-amd6.tar` | 598,772,736 B | 未跟踪 | perf 归档/生成证据候选；超过普通 GitHub 100 MiB 上限，不提交、不迁移，先补 hash 与 manifest 并评估仓库外存储。文件名中的 `amd6` 也需确认是否笔误。 |
| `virtualization/DDI_0487_M.b_a-profile_architecture_reference_manual.pdf` | 161,102,669 B | 已跟踪，LFS | 外部参考资料；现状不改。后续核对授权、来源、版本与保留必要性，不迁移历史。 |
| `research/.../vendor/sqlite-fossil-release.tar.gz` | 12,640,606 B | 未跟踪，旁有 `.sha256` | 第三方输入候选；需要来源 URL/版本/许可证/哈希 manifest，优先考虑可重复下载而非直接版本化。 |
| `IO_stack_and_hypervisor.excalidraw` | 6,479,701 B | 未跟踪 | 可编辑图源，不等同于临时生成物；需指定所属主题、canonical 图源与导出图关系。 |
| `ai_sandbox/cubesandbox/.../v22-el2-first-entry-trace-full.txt` | 3,627,410 B | 已跟踪，普通 Git | 原始 trace 证据；有价值但与结论文档混放，适合在后续 Workspace 补 manifest 和索引。 |
| `kvm/GIC.excalidraw`、`kvm/kvm-arm64虚拟化.excalidraw` | 约 2.4 MiB、0.9 MiB | 未跟踪 | 项目图源候选；先确认 canonical 和关联文档。 |

Git HEAD 中最大的普通 Git blob 约 3.6 MB；上述 154 MiB PDF 的 Git 对象是 LFS pointer，不是普通 Git blob。

## 四类内容盘点

分类是职责判断，不是只看扩展名或目录名。图片、CSV、JSON、tar 和日志都可能属于证据，也可能是可重新生成的派生产物。

| 类别 | 当前例子 | 主要问题 |
|---|---|---|
| durable knowledge | `kvm/` 系列、`virtualization/` 学习地图、`软件工程/`、面向读者的 CubeSandbox 文章 | 根入口缺失；部分主题在根和项目目录各有版本；状态和 last verified 不统一 |
| project-local docs | `ai_sandbox/cubesandbox/`、`ai_sandbox/agentenv/`、`research/agent_cpu_sandbox_toolkit/`、三个 Kata latency 项目包 | 结论、操作、源码解读和执行脚本混在同一层；多数项目缺 scope/canonical/status 导航 |
| evidence | `results-direct-lite/`、CubeSandbox `debug/.../data` 与 `evidence`、benchmark CSV、memory_compress CSV/JSON、checksum | 有的证据包成熟，有的结果目录缺 manifest、来源 revision 或复现说明；解释文档与原始日志混放 |
| generated/ephemeral | `__pycache__/`、`*.pyc`、`.marscode/deviceInfo.json`、应用状态目录 | 已有 9 个 bytecode 被跟踪；`tmp`/`logs`/`results` 不能整体忽略，因为其中也存在证据 |

边界例子：

- Excalidraw 通常是可维护的图源，属于项目资产；由它导出的 PNG/SVG 才可能是生成物。
- benchmark summary CSV 是可重新生成的派生数据，但也是报告结论的审计证据。若保留，应由 manifest 指向原始输入和生成脚本。
- 598 MB perf tar 很可能由工具生成，但它可能含唯一原始 profile。在确认可重建性和保存位置前按证据候选保护。
- 第三方 PDF 是 reference，不是本仓库的结论；是否版本化还取决于授权、稳定 URL 与离线需求。

## 结构与内容风险

### 重复入口与孤儿候选

- 根目录原先没有 README，15 份根级 Markdown 没有统一导航入口，主题横跨容器、并发、设计、运维和硬件。
- 对 345 份已跟踪 Markdown（排除 `github-tokens.md`）做简单的 Markdown 内联相对链接入度扫描，发现 254 个“零入链”候选，其中 `ai_sandbox/` 163 个、`research/` 20 个、`virtualization/` 15 个、`kvm/` 14 个。该数字只用于发现候选：引用式链接、裸路径、生成站点导航等可能造成误报，不能据此删除文件。
- `ai_sandbox/micro-vm-analysis/README.md` 链接到当前仓库不存在的 `ai_sandbox/firecracker/analysis/deep-routes.md`、`ai_sandbox/cloud-hypervisor/analysis/deep-routes.md` 和 `ai_sandbox/CubeSandbox-sandbox-clone/analysis/deep-routes.md`，说明部分入口仍依赖仓库外或未同步项目树。
- 许多 CubeSandbox 报告引用未入库的 `remote-results/`、`source_code/` 或其他绝对本地路径。它们可能是 provenance 线索，但当前无法从仓库独立解析。

### 完全重复与重叠候选

已按 SHA-256 验证的完全相同文件包括：

- `ai_sandbox/04-Kata-Containers-架构分析报告.md` 与 `ai_sandbox/kata-containers/04-Kata-Containers-架构分析报告.md`。
- `ai_sandbox/cubesandbox/perf/sample_c50_host.sh` 与 `ai_sandbox/cubesandbox/perf/scripts_v2/sample_c50_host.sh`。
- `ai_sandbox/cubesandbox/perf/run_cubesandbox_openeuler_template_perf.sh` 与 `ai_sandbox/cubesandbox/perf/scripts_v2/run_cubesandbox_openeuler_template_perf.sh`。
- `virtualization/virtio/as_title_vdevice.md` 与 `virtualization/virtio/as_title_virtnet.md`。
- 三个 Terminal-Bench task 内各自携带相同的 `mini_pytest.py`；这可能是自包含任务设计，不应在不了解打包边界时贸然合并。

另有 6 份空 Markdown：`BDD与cucumber.md`、`golang_under_the_hood.md`、`katalyst分析/metrics监控.md`、`每日项目简析/archGW.md`、`ai_sandbox/build_from_scratch-Doing.md`、`ai_sandbox/firecracker分析-TODO.md`。它们是占位/孤儿候选，不是删除授权。

以下是内容重叠候选，尚未完成逐段语义审阅：

- 根级与项目内同时存在的 Kata、E2B、Nydus 架构报告。
- `arm64-adaptation-issues-summary.md` 与 `arm64-adaptation-issues-summary-zh.md` 可能是语言变体，需要明确主版本和同步关系。
- `architecture.md`、`architecture-analysis.md`、`summary.md` 等通用名称在多个项目中出现；目录上下文可区分，但跨目录检索时难判断 canonical。
- CubeSandbox 同一问题存在 `analysis`、`debug`、`perf`、顶层日期报告和面向公众文章等多种表达，应区分原始分析、验证报告、最终结论与历史版本。

### 命名与状态不一致

- 中文、英文、下划线、连字符、空格和全大写标题并存。
- 日期同时作为文档版本、实验时间和文件名后缀，语义不统一。
- `TODO`、`Doing`、`v0`、`scripts_v2`、`temp.md` 等名称承担状态，但没有统一索引解释。
- 同一系列中编号重复，例如 `08-Nydus` 与 `08-faasd`；编号不是稳定的全仓库标识。

本轮不统一语言和文件名。先通过 README、状态元数据与迁移映射建立稳定入口，避免破坏已有链接。

### 文档与证据混放、provenance 不均衡

- CubeSandbox `debug/arm64-vgic-ap1r-nmi-active-20260806/` 已有 README、环境 TSV、结果 TSV、证据日志、修复、脚本和 `SHA256SUMS`，是较成熟的证据包。
- `results-direct-lite/` 有配置和两次 timestamped run，run 内有 raw/logs/workloads/summary，但目录级没有 README/manifest，无法从入口快速确认采集主机、源码 revision、命令、工具版本和复现状态。
- CubeSandbox benchmark `reports/` 混合解释报告和 CSV 汇总；目录没有独立 manifest 说明 CSV 的原始输入、生成命令与 hash。
- 未跟踪的大型 tar、Excalidraw 和根级 PNG 没有同路径可见的 provenance manifest；在确认来源前不得提交或删除。

## 敏感信息风险

- `github-tokens.md` 已被 Git 跟踪。仅凭文件名无法确认内容是否仍含有效凭据；本次按安全边界没有读取内容。
- 建议在单独、私密且不输出内容的 Workspace 中审计其当前内容和 Git 历史。若确认含凭据，应先轮换/吊销，再经明确批准制定历史清理和协作者同步方案。
- 在审计完成前，不应在 README、issue、diff、终端输出或迁移 manifest 中复制该文件内容。

## 本次没有执行

- 没有修改、移动、删除、清理、暂存或提交主检出区文件。
- 没有打开大型 tar/PDF/日志内容，也没有读取 `github-tokens.md`。
- 没有运行 `git clean`、`git reset`、`git checkout`、历史改写、push 或发布。
- 没有把 `tmp/`、`logs/`、`results/`、`images/` 整体加入 ignore。
