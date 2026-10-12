# CubeSandbox 通用测试指南

**镜像的 envd 适配已经完成，本指南从导入适配镜像开始。**
常规测试不需要重新拉取原始 OCI 镜像、构建 Dockerfile 或安装 envd。

主流程：**适配镜像归档 → 导入目标 registry → 创建目标模板 → 单条回放 → 批量模板 → 密度测试 → 验收与清理**。
若适配镜像已经在目标 registry，直接从确认镜像引用与创建模板开始。

本文说明依赖、文件用途和流程边界。逐步命令集中在
[详细操作指南](docs/CUBESANDBOX_DENSITY_GUIDE.md)，按配置、安装、镜像导入、模板、回放、验收分别执行。
镜像适配仅在缺少目标架构的适配镜像或需要更新运行环境时使用，见本文末尾的可选说明。

## 镜像已在 registry：从这里开始

直接进入 [registry 快速入口](docs/CUBESANDBOX_DENSITY_GUIDE.md#快速入口镜像已在-registry)。
该入口使用 `IMAGE_SOURCE=registry`，不需要归档文件，顺序为：

**配置目标环境 → 生成镜像清单 → 拉取已有适配镜像 → 仅执行 `--phase cube` → 单条回放 → 其余模板 → 密度测试与验收。**

快速入口标明了每一步的命令位置和可跳过的章节；模板默认规格为 **2 vCPU / 4 GiB / `10G` 可写层**，
可在创建前修改。后续回放仍需准备数据集 CSV、轨迹和驱动，具体依赖见下文。

## 项目依赖与所用文件

运行目录需要另外准备两个项目，本 Materials 发布包只包含模板脚本与指南工具。
先按 [部署依赖](README.md#部署依赖)准备文件，再执行指南。两个项目的分工为：`swerebench-offline-replays-master` 提供工作负载，
`agent_vm_bench` 提供回放执行器和监控；本项目脚本负责创建 CubeSandbox 模板、生成配置和验收结果。

### 数据依赖：swerebench-offline-replays-master

该项目作为文件数据源使用，本流程不安装或调用它自己的测试执行器。


| 文件或目录                                                                                                 | 谁读取                              | 用途                                                      | 是否必需                 |
| ----------------------------------------------------------------------------------------------------- | -------------------------------- | ------------------------------------------------------- | -------------------- |
| `swerebench-offline-replays-master/verified-135/manifest.csv`              | `build_template.py`、详细指南中的清单生成步骤 | 取得 instance、源镜像命名、架构、工作目录、轨迹文件名和筛选字段；即使跳过镜像适配，模板脚本仍读取此表 | 必需                   |
| `swerebench-offline-replays-master/verified-135/replays/` 下选中的 `*.replay.json` | `bench-core`、配置生成器和结果校验器         | 提供实际回放的动作、延迟和步骤信息                                       | 必需                   |
| `profiles/<案例>/replay/replay-result.json`                                                             | 人工或另行编写的对比程序                     | 核对历史命令返回码、解释原有非零结果；不由本指南结果校验器自动对比                       | 做返回码基线验收时使用，需与所选案例对应 |
| `verified-135/download-images.sh`、该项目的 runner / profiling 工具                                          | 本流程不调用                           | 原始镜像下载和上游自有测试流程                                         | 无需运行                 |


本发布包未附带 `profiles/`。需要逐步返回码对比时另行取得匹配版本的基线记录，
或先在低负载下建立并保存基线；仅凭轨迹动作文件无法证明返回码与历史一致。

配套数据集当前默认筛选为 `go,ts,java` 且目标架构 `wall_sec_* < 2100`，得到 55 条案例。
这些 wall 字段是数据集投影值，不是本次测试成绩。更换集合时以实际清单为准，并同时准备相应适配镜像。

### 执行依赖：agent_vm_bench

通过 `pip install -e "路径/agent_vm_bench[cubesandbox]"` 安装完整项目及 CubeSandbox SDK 扩展。
不要只复制 `bench.py`：执行器还依赖同项目内的 provider、回放与报告模块。


| 文件或目录                                                                                               | 作用                                                                |
| --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `agent_vm_bench/pyproject.toml`                                                     | 声明 Python 依赖、`cubesandbox` 可选扩展，以及 `bench-core`、`vm-monitor` 命令入口 |
| `agent_vm_bench/src/bench_core/bench.py`                                   | `bench-core` 入口，加载配置并组织测试                                         |
| `agent_vm_bench/src/bench_core/payload/replay_payload.py` | 读取轨迹与模板映射，形成运行集合                                                  |
| `agent_vm_bench/src/bench_core/task_runner/replay.py`         | 执行轨迹回放                                                            |
| `agent_vm_bench/src/env_provider/cubesandbox/`                       | 通过真实 CubeSandbox SDK 创建、执行、查询和清理沙箱                                |
| `agent_vm_bench/src/bench_core/observability/`                       | 生成 run summary、步骤时序及报告                                            |
| `agent_vm_bench/vm_monitor/`                                                           | 采集承载 VM 的 Linux 主机和虚拟机指标，密度测试使用                                   |
| `agent_vm_bench/config/common/replay-trajectory.yaml`         | 配置字段参考；主流程使用本项目生成的配置，不直接运行此示例                                     |


驱动要求 Python 3.10+。依赖包以 `pyproject.toml` 和本次安装后的 `pip freeze` 为准。
provider 在 SDK 缺失时有开发用 Mock，正式测试必须先确认使用真实 SDK。

### 本项目脚本与适配镜像包


| 文件或目录                                                                                                  | 输入 → 输出 / 用途                                                                                      |
| ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| [build_template.py](build_template.py)                                                                 | 数据清单 + 目标 registry 镜像 → CubeMaster job → READY 模板映射；主流程显式使用 `--provider cubesandbox --phase cube` |
| [docs/tools/make_density_config.py](docs/tools/make_density_config.py)                                 | 轨迹目录 + READY 模板映射 + 测试参数 → YAML 和本轮映射；只生成输入，不执行测试                                                 |
| [docs/tools/snapshot_cube_ids.py](docs/tools/snapshot_cube_ids.py)                                     | CubeAPI 中的 ID 列表 → 测试前后清单及差异；只读，不清理                                                               |
| [docs/tools/verify_density_run.py](docs/tools/verify_density_run.py)                                   | 本轮结果目录 + 原始轨迹 → 完整性与超时/执行异常检查；不连接 API，不证明实际并发或清理                                                  |
| 适配镜像包中的 `manifest.csv` / `manifest.json`                                                               | 同一组镜像的扁平清单与完整元数据；详细指南读取 CSV 中的 `instance_id`、`original_tag`、架构、`archive_filename` 和校验信息，生成导入清单    |
| 适配镜像包中的 `SHA256SUMS` 与 `*.tar`                                                                         | 校验后以 `docker load` 导入，随后 tag/push 至目标 registry                                                    |
| `exports/cubesandbox-x86-55-20261010/manifest.json` | 原项目中保留的 x86 适配包元数据示例，本发布包不附带；该包对应 `linux/amd64`，不能当作 ARM64 包使用                                              |
| `images/` 下的 `verified-55-*.txt`                                                              | 原始镜像引用清单，供可选的重新适配使用；不是适配镜像的导入清单                                                                   |


本 Materials 发布包**不包含导出清单、`*.tar` 或轨迹数据**，这些需要从配套数据包另行取得。
将实际适配镜像包放在详细指南的 `ARCHIVE_DIR` 中，或使用已经存放适配镜像的 registry。
包内旧 registry 地址只是归档 tag 的身份信息；导入后改为目标 registry 引用，不需要访问旧地址。

配置生成器使用 PyYAML，ID 快照工具使用 CubeSandbox SDK，这两项随驱动及其扩展安装。
模板脚本和结果校验器自身使用 Python 标准库；模板创建还调用 Docker CLI 并访问 CubeMaster。

### 外部服务与工具


| 依赖                  | 本流程用途                                                 |
| ------------------- | ----------------------------------------------------- |
| 已部署的 CubeSandbox    | CubeMaster 接收模板任务；CubeAPI 提供 SDK 控制面；沙箱域名和数据面路由承载命令执行 |
| 可达的 registry        | 存储适配镜像，供平台按 digest 拉取；提前配置 TLS 与鉴权                    |
| Docker CLI / daemon | load、tag、push，以及模板脚本所需的本地 RepoDigests 和远端 manifest 查询 |
| Python 3.10+、Bash   | 安装驱动、运行辅助脚本及指南命令                                      |
| Linux 主机采集环境        | 在实际承载 VM 的节点上运行 `vm-monitor`；仅远程功能预检可先关闭监控            |


主流程不需要 AgentEnv 服务、不运行 `--provider aenv`，也不需要重新获取 envd donor 或访问源镜像的 apt 软件源。

## 部署时需要准备什么

按 [部署依赖](README.md#部署依赖)组装运行目录后，应具有如下结构；路径由详细指南中的环境变量指定：

```text
swe-replay-density/                     # SUITE_ROOT，补齐外部输入后的运行目录
├── build_template.py
├── docs/tools/                         # 三个配置/验收辅助脚本
├── agent_vm_bench/                     # 完整驱动项目，用于安装
└── swerebench-offline-replays-master/
    ├── verified-135/manifest.csv
    ├── verified-135/replays/           # 至少包含所选轨迹
    └── profiles/                      # 可选，另行取得的返回码基线记录

<ARCHIVE_DIR>/                          # 单独准备的适配镜像包
├── manifest.csv
├── manifest.json
├── SHA256SUMS
└── <instance_id>.tar
```

`validation/` 和导出过程的日志是历史证据，不是新环境运行的依赖。
镜像 tar 不含测试驱动、轨迹、Python wheels 或模板 ID，不能只传镜像包就开始回放。
模板 ID 必须在目标环境生成；每轮 YAML、模板映射、日志和报告统一保存到独立实验目录。

## 测试使用的沙箱配置

以下为指南示例配置，实际资源由目标模板决定。镜像已完成适配，创建模板时仍需明确沙箱规格。


| 配置项           | 本指南配置                                             |
| ------------- | ------------------------------------------------- |
| 每沙箱 CPU       | **2 vCPU**（`2000m`）                               |
| 每沙箱内存         | **4 GiB**（`4096Mi`）                               |
| 可写层           | **`10G`**，传给平台的容量字符串，不代表包含只读镜像的总磁盘占用              |
| 架构            | 示例为 `x86` / `linux/amd64`；ARM64 测试使用对应适配镜像和模板     |
| 实例类型 / 网络     | `cubebox` / `tap`                                 |
| 命令执行用户 / 工作目录 | `root` / `/testbed`                               |
| 沙箱空闲 TTL      | `86400` 秒（24 小时），不是单步超时或整轮时长                      |
| 回放方式          | `exec_only`，预创建沙箱，回放期间不执行 pause/resume            |
| 单条预检          | 1 个沙箱、1 轮、单步超时 300 秒、测试时长上限 900 秒、`delay_scale=0` |
| 密度测试          | 沙箱数 `N`、创建批量、单步超时、轮次时长和思考延迟倍率由实验计划填写              |


完整字段、修改位置及生效方式见
[详细指南：沙箱配置一览](docs/CUBESANDBOX_DENSITY_GUIDE.md#沙箱配置一览)。
CPU、内存和可写层在模板创建时确定；调整这些规格需要用新构建目录重新创建模板，
并更新测试映射，不能只修改回放 YAML。

## 操作顺序与完成条件

具体命令见 [详细操作指南](docs/CUBESANDBOX_DENSITY_GUIDE.md)。每一阶段完成后再继续下一阶段：


| 阶段     | 操作                              | 完成条件                        |
| ------ | ------------------------------- | --------------------------- |
| 准备     | 配置路径/服务入口，安装驱动，确认真实 SDK         | 数据文件齐全，版本可追溯，控制面和数据面可达      |
| 导入一条镜像 | 校验归档 → load → 核对架构 → tag → push | 目标 registry 镜像可用，命名与模板脚本一致  |
| 创建一条模板 | `--phase cube` 预览与执行            | job 和模板均 READY，生成真实模板 ID 映射 |
| 单条预检   | 生成配置 → 记录资源基线 → 回放 → 验收/清理核对    | 步骤完整，返回码符合基线，无新增超时或执行异常     |
| 扩大集合   | 导入其余镜像 → 创建其余模板 → 合并映射          | 所选案例都有可用模板，集合不缺失            |
| 密度阶梯   | 确定资源预算与性能门槛，逐轮运行并采集指标           | 实际驻留数达到目标，数据完整，性能与清理通过验收    |


`cube` 阶段需要本地 Docker 中的目标镜像 RepoDigests。
如果镜像早已在 registry，先 `docker pull` 对应的适配镜像；无需重复 build。
不要用 `--phase pull` 代替这一步：该阶段拉取的是原始镜像。
脚本检查远端 manifest 后调用 `/cube/template/from-image`，只有确认 READY 的 ID 才写入映射。
资源或镜像变化时使用新的 `--build-dir`，以免复用旧 job；单条与全量映射使用不同文件。

## 可选：重新适配镜像

**已有适配镜像时跳过本节。** 只有新增案例、补齐目标架构或更新 envd 时，才需要
“原始 OCI 镜像 → 注入 envd 的适配镜像”。命令见详细指南的可选附录。

`build_template.py` 支持 `pull → build → smoke → push`：从源镜像构建，复制 envd 与入口脚本，
准备 `user` 和 `/testbed`，用独立 Docker 容器做本地探活后推送。
当前 Dockerfile 支持 Debian/Ubuntu，需要 envd donor（默认 `ghcr.io/tencentcloud/cubesandbox-base:2026.16`）
和 apt 软件源；这些只是重新适配时的依赖。

更换 donor 时固定版本或 digest，并使用可区分的 `--image-suffix`，保留原始镜像与工具链。
Docker smoke 不替代目标 VM 中的回放验收；新镜像仍须回到主流程完成模板创建和单条预检。
