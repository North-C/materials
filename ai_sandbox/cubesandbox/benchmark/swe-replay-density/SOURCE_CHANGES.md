# SWE 轨迹回放套件源码改动说明

核对日期：2026-10-12。本次适配修改了根目录 `build_template.py`，新增离线测试、操作指南和辅助工具；
没有修改 `agent_vm_bench` 的 `bench-core` 或 CubeSandbox provider 源码。

根目录不是 Git 仓库，因此构建脚本以开始适配前保存的原始文件为比较基线；
不能把整个目录中的文件都称为一个可追溯的 Git diff。嵌套驱动仓库的既有未提交改动单独列出。

## 1. 修改的生产脚本

| 文件 | 基线与规模 | 改动目的 |
|---|---|---|
| [build_template.py](build_template.py) | 424 → 717 行；增加 330 行、删除 37 行 | 在保留默认 AgentEnv 流程的基础上增加 CubeSandbox 镜像适配、模板构建与真实 ID 输出 |

文件身份：

```text
原始文件 SHA256：95f64f7f9a5fdee70adb6018be7b7354f44eb4f54ec29c8251ec48769237b73d
测试版   SHA256：ed82005f199101fb0c532a4660fe3c6f4dda67ea130a78d3cd0d33d568a1658a
```

| 改动 | 实现位置 | 具体行为 |
|---|---|---|
| 双 provider 与阶段选择 | `build_template.py:527`、`:673` | 默认仍为 `aenv`；CubeSandbox 使用 `pull,build,smoke,push,cube`，按固定顺序执行；支持单实例、独立构建目录、镜像清单导出 |
| OCI 预装依赖 | `build_template.py:177`、`:223` | 从官方 `2026.16` donor 复制 envd/entrypoint；安装 bash、CA、curl、sudo、tini、passwd；创建 user；以 tini+envd 常驻，替换原 ENTRYPOINT/CMD |
| 回放工作目录 | `build_template.py:195` | 根据 manifest.workdir 预建 `/testbed` 别名；若已有目录或链接指向别处则失败；保留源镜像工具链、ENV 与 WORKDIR |
| Docker 冒烟与清理 | `build_template.py:246` | 容器禁用外部网络；检查 49983/health=204、bash/user/workdir；记录 create 返回的 ID，start 失败也只清理该容器 |
| CubeMaster 请求 | `build_template.py:281`、`:300` | 显式区分 CubeMaster 与 CubeAPI；探针包含 30 秒预算、500 ms 周期、60 次失败阈值；鉴权 key 仅走请求头，错误信息脱敏 |
| 镜像及任务身份 | `build_template.py:323` | 读取 RepoDigests 后再次查询 registry manifest，使用不可变 digest；保存 request/job；重跑继续轮询原 job，拒绝复用不同目标/请求的任务 |
| 真实模板映射 | `build_template.py:369`、`:701` | job READY 后再次确认模板 READY，仅输出真实 `tpl-*`；list/dry-run 不伪造 ID；部分失败只输出成功项并返回非零 |
| 通用健壮性 | `build_template.py:388`、`:421`、`:581` | 修正跳过步骤的进度计数；拒绝无效 phase 和非正参数；失败案例不进入后续阶段；代理按变量名转发，不写镜像 ENV |

当前 Dockerfile 以 Debian/Ubuntu 的 apt 为前提；不承诺兼容所有 OCI 镜像发行版。
默认 donor 固定到 tag，严格复现应使用 `--envd-image repo@sha256:...`。
`--dry-run` 不调用 Docker/API，但会生成 Dockerfile 和请求预览文件。

## 2. 新增文件及职责

| 文件/目录 | 类别 | 作用 |
|---|---|---|
| `tests/test_build_template.py` | 自定义离线测试，19 项 | Mock Docker/CubeMaster，覆盖双架构选择、失败/超时/恢复、真实 ID、digest 校验及清理；不等同于平台验收 |
| [docs/tools/make_density_config.py](docs/tools/make_density_config.py) | 配置工具 | 生成原生 bench-core 的单轮 exec_only 配置；固定 `/testbed`，监控开关用字符串，配置以 0600 创建，拒绝覆盖同名输入 |
| [docs/tools/verify_density_run.py](docs/tools/verify_density_run.py) | 只读结果校验 | 核对 summary、series、逐轨迹步骤与监控数据；区分普通非零、超时、非超时执行异常；分开判断数据完整和质量门槛 |
| [docs/tools/snapshot_cube_ids.py](docs/tools/snapshot_cube_ids.py) | 只读平台盘点 | 通过 SDK 保存前后 ID 集，提示需要核查归属的差异；不删除沙箱 |
| `validation/20261009-cube90/host_sampler.py` | 可选宿主采样 | 读取 CPU、内存、load 与 shim 总数；发布副本位于 `docs/tools/host_sampler.py`，不改变原生 benchmark 执行入口 |
| [CUBESANDBOX.md](CUBESANDBOX.md) | 适配说明 | 55 条筛选来源、拉取方法、镜像改造和脚本使用边界 |
| [docs/CUBESANDBOX_DENSITY_GUIDE.md](docs/CUBESANDBOX_DENSITY_GUIDE.md) | 完整用户指南 | 镜像传输/导入、模板构建、单条预检、密度阶梯、清理、指标及历史结果解释 |
| `validation/20261010-export-guide/pi-export/` | 导出与审计脚本 | `export_images.py`、`verify_exports.py`、`write_reports.py` 用于 55 个 tar 导出及归档校验 |
| `validation/20261009-*/`、`validation/20261010-export-guide/` | 实验编排与证据 | 保存逐实例命令、配置、脚本、日志和审计；不是上游 bench-core 的修改，不随 Materials 上传 |

指南辅助工具只准备输入、采样或校验结果；负载执行继续使用固定版本的原生 `bench-core`。
镜像内容、轨迹数据、模板 ID、运行配置和原始结果属于不同产物，不纳入生产源码修改统计。

## 3. 嵌套驱动仓库：既有改动与版本边界

`agent_vm_bench` 当前基线为 `262a0534cc76d138a38b42bc890c9bdd9b40922d`，开始本轮任务前已存在：

| 既有文件 | 当前差异 | 本次处理 |
|---|---|---|
| `config/common/coding-go.yaml` | 增加 coding-go 的 CubeSandbox 配置，9 行 | 保留，不归入本次适配或发布 |
| `dockerfile_build/coding/go/Dockerfile` | Hugo 源码从 git clone 改为本地 COPY，8 行增加、13 行删除 | 保留，不归入本次适配或发布 |
| `_smoke_cube.py`、`venv/` | 未跟踪的冒烟脚本与环境 | 保留，不提交 |

`.95` 的单条回放使用上述基线；`.90` 密度测试使用单独固定的
`93f978f7ec27d9bc519dca2efdc809ada09acbaa` 源码快照。两个版本不能混写成同一个测试身份。
`.90` 运行副本没有 `.git`，其来源通过核心文件哈希与固定 checkout 对照，而非凭包版本推断。

本次没有改写 SWE manifest 或轨迹以消除原有非零返回码，也没有修改 CubeSandbox 平台源码。
`.95` 经授权恢复 TC/BPF 挂载、`.90` 经授权调整配额/地址池，均属历史部署操作，不是 Python 源码补丁。

## 4. 已验证范围及证据位置

以下是已归档的历史验证，不代表发布当天重新运行了压力负载：

| 验证 | 结果与限制 | 原项目证据目录 |
|---|---|---|
| `.95` ARM64 单条端到端 | 118 个可执行步骤的返回码逐条匹配基线：112 成功、6 条原有非零，无超时；是功能验证 | `validation/20261009-cube95/` |
| ARM64 / x86 镜像准备 | 两架构各 55 个镜像完成构建、Docker smoke 和 registry 校验；Docker 成功不等于平台回放成功 | `.95` 目录下的 `rebuild-remaining54-20261009T0727Z/`；`validation/20261009-x86-local/rebuild-55/` |
| `.90` ARM64 密度第二批 | 55 模板；384/768/1152/1536 轨迹轮次均完成，含超时 run 分别为 9/15/51/194；不能称为零退化 | `validation/20261009-cube90/batch2-monladder-20261010/` |
| x86 tar 导出 | 55/55，39,506,298,368 bytes；归档 SHA256、平台和内容核对；未做共享 Docker load 回环或 x86 Cube 端到端 | `exports/cubesandbox-x86-55-20261010/`；`validation/20261010-export-guide/` |
| 指南及工具离线校验 | 20 个 Bash 代码块、内嵌 Python、链接及配置/历史结果门槛，共 27 个子进程检查；不执行指南中的平台变更命令 | `validation/20261010-export-guide/guide-validation.json` |

原始证据目录不随 Materials 发布。发布版保留已验证 `build_template.py` 的逐字节内容，
指南仅调整部署路径、示例地址、随包工具位置和证据索引；发布复核记录位于原项目的
`validation/20261012-materials-publication/`。本说明不把未执行的迁移步骤视为完成。
