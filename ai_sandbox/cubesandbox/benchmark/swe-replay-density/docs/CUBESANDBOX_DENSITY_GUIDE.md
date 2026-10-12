# CubeSandbox 通用密度测试指南

先按 [部署依赖](../README.md#部署依赖)取得驱动与轨迹，再从本发布目录执行下面的步骤。

本文从已有 envd 适配镜像开始，串联镜像导入、模板构建、单条回放、密度阶梯、指标验收与清理。
主线为 **`bench-core + cubesandbox + exec_only`**：先创建沙箱，在持续 RUNNING 的沙箱内
回放命令，最后清理本轮沙箱。测试参数来自目标环境和本次实验计划，不预设机器容量或服务端口。
项目依赖、各项目提供的文件及部署边界见 [项目依赖与所用文件](../CUBESANDBOX.md#项目依赖与所用文件)。

阅读顺序：环境 → 选择集合 → 导入一条适配镜像 → 创建模板 → 单条预检 → 批量导入与模板 → 密度阶梯 → 验收与清理。
原始 OCI 镜像注入 envd 已完成，不是常规测试前置步骤；新增或重做镜像时才使用文末可选附录。

## 快速入口：镜像已在 registry

**适配镜像已推送到目标 registry 时，从这里开始。** 此路径不需要 tar、归档 manifest 或
`SHA256SUMS`，也不重新适配镜像。仍需本项目脚本、驱动、数据集 CSV 和所选轨迹文件。

### 第一步：选择 registry 模式并准备环境

在项目根目录打开 Bash，先设置来源：

```bash
export IMAGE_SOURCE=registry
export ARCHIVE_DIR=""
```

接着按 [2.2–2.8 节](#22-配置工作目录)完成目录、平台入口、规格、驱动安装与检查。
2.2 会保留上面设置的来源。重点确认：

| 参数 | 填写内容 |
|---|---|
| `REGISTRY` | 已推送镜像的 `host[:port]/namespace`，不带 `http://` 或 `https://` |
| `ARCH` | 镜像实际架构：`x86` 或 `arm64` |
| `IMAGE_SUFFIX` | 已有适配 tag 中的版本后缀，不包含末尾的 `-x86` / `-arm64` |
| `CUBE_MASTER_URL` | 用于创建模板的 CubeMaster 入口 |
| `CUBE_API_URL`、`CUBE_SANDBOX_DOMAIN` | 后续创建沙箱与执行命令所需入口 |
| `CPU_MILLICORES`、`MEMORY_MIB`、`WRITABLE_LAYER_SIZE` | 本轮模板规格，示例为 2 vCPU / 4 GiB / `10G` |

例如 tag 以 `-cube-envd-2026.16-testbed-x86` 结尾时，
`IMAGE_SUFFIX=cube-envd-2026.16-testbed`、`ARCH=x86`。
当前脚本按数据集中的镜像名称生成目标引用；仓库路径或 tag 改过名时，先核对并统一命名。
HTTP registry 需在第 3.7 节模板参数中增加 `--registry-http`，并预先配置对应的访问策略。

### 第二步：直接创建一条模板

按下面三步执行，**跳过第 3.2–3.6 节的归档校验、load、tag 和 push**：

1. [2.9 生成镜像清单](#29-确定测试案例并生成镜像清单)：registry 模式只读取数据集 CSV，生成目标镜像引用，不读取归档。
2. [3.1 选择实例并拉取适配镜像](#31-选择预检实例)：执行该节的选择命令和 `docker image pull`，让本地 Docker 具备目标镜像及 RepoDigests。
3. [3.7–3.9 配置、预览并创建模板](#37-配置模板参数)：始终使用 `--phase cube`，等待 READY 并得到 `SINGLE_MANIFEST`。

这里的 Docker 拉取供模板脚本查询镜像身份使用；无需重新构建或推送镜像。
`build_template.py --phase pull` 拉取的是原始镜像，不用于此入口。

### 第三步：运行后续测试

| 顺序 | 执行入口 | 完成后得到 |
|---|---|---|
| 单条验证 | [第 4 节](#4-单条功能预检)：生成配置、记录清单、执行回放、验收 | 可用的单模板/单沙箱回放结果 |
| 其余模板 | [5.1 的 registry 拉取命令](#51-加载其余适配镜像)，随后直接进入 [5.4–5.5](#54-创建其余模板)；跳过 5.2–5.3 | 全集模板映射 `FULL_MANIFEST` |
| 密度测试 | [第 6 节](#6-运行密度阶梯)：设置 N、创建批量、时长、超时和延迟倍率，再运行 | 各轮回放结果及主机/VM 指标 |
| 验收与清理 | 每轮结束执行 [第 7 节](#7-结果验收与清理) | 完整性、性能门槛及资源回收核对结果 |

请在同一 Bash 会话中继续上述步骤；更换 shell 时需要恢复本次参数和 `BUILD_ARGS` 数组。

## 1. 测试对象与成功标准

```text
已有 envd 适配镜像归档 → load / tag / push 到目标 registry
                     → 目标集群 Template → 轨迹文件与 Template ID 映射 → 回放报告
```

源清单为 `swerebench-offline-replays-master/verified-135/manifest.csv`，其中记录镜像、架构、
工作目录与轨迹。测试集合由显式筛选参数确定，最终运行集由本次生成的模板映射限定。
镜像归档不包含轨迹、驱动源码或 Python 依赖，必须单独准备这些输入。
模板 ID 属于目标集群；迁移镜像后须在目标环境重新构建模板，不能复制其他集群的 ID 作为验收结果。

### 1.1 模式与超分口径

| 模式 | 行为 | 使用范围 |
|---|---|---|
| `exec_only` | 预创建 VM；逐条执行命令；没有 pause/resume | 本文主线，观察驻留 VM 密度 |
| `lifecycle` | 命令之间暂停/恢复，运行槽参与限流 | 需另行验证快照、内存回收和恢复语义 |
| `trajectory` | 每条轨迹独立创建/删除 VM，持有轨迹级运行槽，仍涉及逐步生命周期动作 | 另一种负载模型，总数不能直接视为同时 RUNNING 数 |

设沙箱数为 `N`、每沙箱 vCPU 数为 `v`、宿主 CPU 预算为 `C`：

```text
CPU 配置超分比 = N × v / C
内存配置超分比 = N × 每 VM 配置内存 / 宿主可用于测试的内存预算
```

明确 `C` 是逻辑 CPU、物理核还是预留后的预算，并在轮次间保持一致。
多节点测试同时记录每个节点的预算、实际放置数与集群总量，避免总量掩盖单节点瓶颈。
配置内存、RSS/PSS 和物理占用是不同指标。

在 `exec_only` 下，`replay.running_concurrency` 不能限制 VM 创建总数；
`sandbox.total_count`、`create_batch` 和 `test.round_size` 分别影响总量、创建节奏和执行批次。
原生 `run_summary.overcommit_ratio` 是运行槽口径，不能替代上述 CPU 配置超分比。

### 1.2 分层验收

1. 镜像：架构匹配，envd 可用，工作目录正确，平台能从 registry 取到指定 digest。
2. 模板：job READY 后再次确认模板 READY，再真实创建沙箱并执行命令。
3. 回放：预期案例与可执行步骤完整；普通非零返回码与原始基线比较；超时、执行异常单列。
4. 密度：实际达到目标驻留数，指标覆盖完整，时延和超时率满足事先约定的门槛。
5. 清理：本轮资源已经回收，既有资源的变化得到核对。

Docker `/health=204`、模板 READY、SDK 命令成功和整轮回放完成是不同检查点。
轨迹中可能本来就有非零返回码；不要为得到全零结果而改写工具链或轨迹。

## 2. 准备环境与固定输入

### 2.1 环境角色

目标需要已经部署可用的 CubeSandbox。镜像导入与模板脚本需要 Docker；驱动需要 Python 3.10+ 和真实 SDK。
本文不负责平台安装或升级。先从部署配置确认以下入口：

| 入口或资源 | 用途 |
|---|---|
| CubeMaster URL | 镜像转模板任务 |
| CubeAPI URL | SDK 创建、列举、删除沙箱 |
| 沙箱域名与数据面路由 | 沙箱内命令执行 |
| 目标 registry | Docker 推送与平台拉取镜像 |
| 节点 ID、架构与存储位置 | 模板放置与容量核对 |

构建机、驱动机和 Cube 节点可以分离。`localhost` 只指访问进程所在主机或网络命名空间。
数据面域名解析、证书、鉴权和代理排除项按实际部署配置，不从端口号推测服务身份。
主机监控必须采集**实际承载 VM 的节点**；只在工作站采集 `/proc` 得到的是工作站指标。
本文监控示例适用于驱动与 VM 同节点的 Linux 环境；多节点时逐节点部署并关联监控数据。

### 2.2 配置工作目录

以下命令在项目根目录的同一个 Bash 会话按顺序执行。新 shell 需要恢复环境变量和后续的 Bash 数组。
`IMAGE_SOURCE=archive` 表示导入归档，`registry` 表示镜像已在目标 registry。
归档方式需将 `ARCHIVE_DIR` 改为实际目录，包含 `manifest.csv`、`SHA256SUMS` 和 tar；
registry 方式不读取归档文件。
配套原项目的 `exports/cubesandbox-x86-55-20261010/` 记录了 55 条 x86 镜像；
本发布包不附带归档元数据或 tar，归档模式下需单独取得完整镜像包。元数据中的原始 tag 只用于
定位 `docker load` 后的本地镜像，不要求连接或复用其原 registry。

```bash
set -euo pipefail
export SUITE_ROOT="$PWD"
export DENSITY_ROOT="$HOME/density-lab"
export BENCH_SRC="$SUITE_ROOT/agent_vm_bench"
export IMAGE_SOURCE="${IMAGE_SOURCE:-archive}"  # 快速入口已设 registry 时保留该值
export ARCHIVE_DIR="${ARCHIVE_DIR-/path/to/adapted-image-archives}"
export EXPERIMENT_ID="$(date -u +%Y%m%dT%H%M%SZ)"
export SOURCE_MANIFEST="$SUITE_ROOT/swerebench-offline-replays-master/verified-135/manifest.csv"
export TRAJECTORY_DIR="$SUITE_ROOT/swerebench-offline-replays-master/verified-135/replays"
export BUILD_DIR="$DENSITY_ROOT/build/$EXPERIMENT_ID"
export PARTS_DIR="$DENSITY_ROOT/template-parts/$EXPERIMENT_ID"
export FULL_MANIFEST="$DENSITY_ROOT/templates-$EXPERIMENT_ID.json"
export SELECTED_CASES="$DENSITY_ROOT/inventory/$EXPERIMENT_ID-cases.json"
export IMPORT_PLAN="$DENSITY_ROOT/inventory/$EXPERIMENT_ID-import.tsv"
mkdir -p "$DENSITY_ROOT"/{configs,inventory,logs,results,runtime} "$PARTS_DIR"
```

### 2.3 配置平台入口

将 `example.com` 替换为目标环境入口。registry 应提前完成 TLS、鉴权和平台拉取配置。
需要登录时，在导入镜像前使用本环境的凭据执行 `docker login`。

```bash
export CUBE_MASTER_URL=https://master.example.com
export CUBE_API_URL=https://api.example.com
export CUBE_SANDBOX_DOMAIN=sandbox.example.com
export REGISTRY=registry.example.com/density-bench
```

开启鉴权时，在调用配置生成器和 ID 快照工具前安全注入 `CUBE_API_KEY`，不要写入公开脚本。
这些入口分别属于 CubeMaster、CubeAPI 和沙箱数据面，不能互换。

### 2.4 配置选择范围与模板规格

资源数值仅是示例，容量、并发和停止线按目标预算确定。
当前 55 条归档为 x86；测试 ARM64 时须提供对应 ARM64 适配归档或 registry 镜像，不能只修改架构变量。
`IMAGE_SUFFIX` 与当前归档 tag 对应，归档方式下一步会逐条校验。其他归档或 registry
镜像须填写实际后缀；registry 方式由使用者核对 tag 对应的内容、适配版本和来源。

```bash
export ARCH=x86
case "$ARCH" in
  x86) export PLATFORM=linux/amd64 ;;
  arm64) export PLATFORM=linux/arm64 ;;
  *) echo '不支持的目标架构' >&2; exit 1 ;;
esac
export IMAGE_SUFFIX=cube-envd-2026.16-testbed
export LANGS=go,ts,java
export MAX_WALL=2100
export CPU_MILLICORES=2000
export MEMORY_MIB=4096
export WRITABLE_LAYER_SIZE=10G
```

#### 沙箱配置一览

**本指南的单沙箱示例规格为 2 vCPU / 4 GiB 内存 / `10G` 可写层。**
下表区分模板规格与回放配置；平台实际创建结果还需与模板详情核对。

| 模板配置项 | 示例值 / 行为 | 配置位置 |
|---|---|---|
| 目标架构 | `x86` → `linux/amd64`；可改为 `arm64` → `linux/arm64` | `ARCH`，并使用匹配架构的适配镜像 |
| CPU | `2000m` = 2 vCPU | `CPU_MILLICORES` → `--cpu` |
| 内存 | `4096Mi` = 4 GiB | `MEMORY_MIB` → `--memory` |
| 可写层 | `10G`，不含只读基础镜像的总存储占用 | `WRITABLE_LAYER_SIZE` → `--writable-layer-size` |
| 实例类型 | `cubebox` | `build_template.py` 的 `instance_type`，当前固定 |
| 网络类型 | `tap` | `build_template.py` 的 `network_type`，当前固定 |
| envd 服务端口 | `49983` | 模板请求的 `exposed_ports` 与探针端口，当前固定 |
| 健康探针 | HTTP `/health`；超时 30000 ms，间隔 500 ms，失败阈值 60，成功阈值 1 | 模板请求的 `container_overrides.probe` |
| 放置节点 | 默认不指定，由平台决定 | 需要限定时在 `BUILD_ARGS` 中增加 `--cube-node` |
| 镜像 / 模板身份 | 目标 registry 的适配镜像 digest / 本集群 READY 的 `tpl-*` | `request.json` 与本次模板映射 |

镜像导入不改变这些资源规格；`--phase cube` 根据上述参数创建模板。
修改 CPU、内存、可写层或节点范围时，使用新的 `BUILD_DIR` 创建模板并更新映射。
模板预览后可在 `BUILD_DIR/<arch>/<swb-name>/request.json` 核对请求值；正式创建后再核对平台返回的模板详情。

| 回放配置项 | 单条预检 | 密度测试 | 配置来源 |
|---|---|---|---|
| 沙箱总数 | 1 | `N` | `--count` → `sandbox.total_count` |
| 沙箱来源 | 新建，不复用既有沙箱 | 同左 | `sandbox.detect_existing: false`、`create_only: false` |
| 每批创建数 / 间隔 | 1 / 1 秒 | `min(N, CREATE_BATCH)` / 1 秒 | `--create-batch`；间隔由生成器固定 |
| 空闲 TTL | 86400 秒 | 86400 秒 | 生成器写入 `cubesandbox.timeout`，修改时编辑生成的 YAML |
| 执行模式 | `exec_only` | `exec_only` | `replay.mode`，生成器固定 |
| 命令用户 / 工作目录 | `root` / `/testbed` | 同左 | provider 固定用户；生成器设置 `replay.workdir` |
| 单步超时 | 300 秒 | `ACTION_TIMEOUT` 秒 | `--action-timeout` → `replay.action_timeout` |
| 思考时间倍率 | 0（不等待记录的思考时间） | `DELAY_SCALE`，保真使用 1.0 | `--delay-scale` → `replay.delay_scale` |
| 每组执行数 / 轮数 | 1 / 1 | `N` / 1 | `test.round_size` / `test.round_count` |
| 整轮时长上限 | 900 秒 | `RUN_DURATION` 秒 | `--duration` → `test.duration` |
| 主机/VM 监控 | 关闭 | 开启，采样间隔 2 秒 | 生成器 `--monitor` 与 CLI `--vm-monitor` |

`cubesandbox.timeout` 是沙箱空闲到期时间，`action_timeout` 是单条命令的超时，
`test.duration` 是测试运行的时间上限，三者不能混用。
回放配置生成后，在 `DENSITY_ROOT/configs/<NAME>.yaml` 核对本轮取值，模板 ID 在同名
`<NAME>.templates.json` 中。含凭据的 YAML 不直接公开，报告中单独记录以上配置字段。

### 2.5 检查节点资源与 Docker

在实际承载 VM 的 Linux 节点核对 CPU、内存以及模板、快照、可写层所在分区：

```bash
uname -m
nproc
free -h
df -h
```

在执行镜像导入和模板命令的机器核对 Docker 与镜像存储：

```bash
docker version
docker info --format 'data-root={{.DockerRootDir}} driver={{.Driver}}'
```

记录 CPU 和内存预算，考虑平台进程、其他用户 VM、调度额度、TAP/IP 地址池及 registry 容量。
稀疏文件逻辑大小、`du` 实占和 `df` 剩余空间含义不同；loop 文件系统还要核对 backing 文件分区。
OCI 镜像压缩体积不能代表模板与运行时总空间需求。

### 2.6 安装驱动

使用按 [部署依赖](../README.md#部署依赖)取得的 `agent_vm_bench/` 源码，跨机器时保留项目相对目录结构。

```bash
python3 -m venv "$DENSITY_ROOT/.venv"
export PATH="$DENSITY_ROOT/.venv/bin:$PATH"
python -m pip install -e "$BENCH_SRC[cubesandbox]"
```

### 2.7 验证 CLI 与真实 SDK

```bash
bench-core --help
vm-monitor --help
python - <<'PY'
import importlib.metadata
from cubesandbox import Sandbox
from env_provider.cubesandbox import manager
assert manager.Sandbox is Sandbox, 'provider 未使用真实 SDK'
print('cubesandbox', importlib.metadata.version('cubesandbox'))
PY
```

辅助工具针对上述兼容驱动的单轮 `exec_only` 格式；升级驱动或 SDK 后重新检查接口。
ID 快照工具要求 `Sandbox.list()` 返回含 `sandboxID` 的字典列表，曾在 SDK 0.7.0 核验；
版本号不是通用安装要求，接口变化应先适配工具，不能用空列表代替检查。

### 2.8 记录版本

先记录 Python 依赖：

```bash
python -m pip freeze > "$DENSITY_ROOT/inventory/$EXPERIMENT_ID-pip-freeze.txt"
```

再记录源码版本和工作区状态：

```bash
for component in suite bench; do
  source_dir="$SUITE_ROOT"
  [ "$component" = bench ] && source_dir="$BENCH_SRC"
  if git -C "$source_dir" rev-parse --verify HEAD >/dev/null 2>&1; then
    git -C "$source_dir" rev-parse HEAD > "$DENSITY_ROOT/inventory/$EXPERIMENT_ID-$component-commit.txt"
    git -C "$source_dir" status --short > "$DENSITY_ROOT/inventory/$EXPERIMENT_ID-$component-dirty.txt"
  else
    printf '%s\n' '源码副本无 Git 身份，请另附来源版本并保留源码快照。' \
      > "$DENSITY_ROOT/inventory/$EXPERIMENT_ID-$component-source.txt"
  fi
done
```

最后记录实际使用文件的哈希：

```bash
python - "$SUITE_ROOT" "$BENCH_SRC" > "$DENSITY_ROOT/inventory/$EXPERIMENT_ID-source-hashes.txt" <<'PY'
import hashlib, pathlib, sys
suite, bench = map(pathlib.Path, sys.argv[1:])
paths = [suite / 'build_template.py', bench / 'pyproject.toml']
paths += sorted((suite / 'docs/tools').rglob('*.py'))
paths += sorted((bench / 'src').rglob('*.py'))
paths += sorted((bench / 'vm_monitor').rglob('*.py'))
for p in paths:
    print(hashlib.sha256(p.read_bytes()).hexdigest(), p)
PY
```

同时保存未提交改动或源码快照，并记录平台镜像 digest / 二进制哈希；单个 CLI 版本不足以标识部署。
离线环境需另外准备 Python wheels、源码和工具镜像；workload tar 不是完整离线安装介质。

### 2.9 确定测试案例并生成镜像清单

本节确定本次测试包含哪些案例、每个案例使用哪个镜像，并保存清单供后续导入、模板创建和验收共用。
使用构建脚本同一筛选函数；归档方式再与 `manifest.csv` 按 `instance_id` 对齐。
该步骤只写清单，不加载或构建镜像；归档缺少任何选中镜像、架构不符或 tag 后缀不一致都会停止。
registry 方式仅生成目标引用，后续 `docker pull` 时才验证镜像存在及架构。
清单长度记为 K，不把当前归档的 55 条写死为运行要求。

```bash
python - "$SUITE_ROOT" "$SOURCE_MANIFEST" "$LANGS" "$MAX_WALL" "$ARCH" "$REGISTRY" \
  "$IMAGE_SUFFIX" "$ARCHIVE_DIR" "$PLATFORM" "$SELECTED_CASES" "$IMPORT_PLAN" "$IMAGE_SOURCE" <<'PY'
import csv, json, pathlib, sys
root, source, langs, wall, arch, registry, suffix, archive, platform, selected, plan, mode = sys.argv[1:]
assert mode in ("archive", "registry"), mode
sys.path.insert(0, root)
import build_template as b
cases = b.load_cases(source, set(langs.split(',')), float(wall), arch, registry)
assert cases, '筛选结果为空'
images = {}
if mode == 'archive':
    with (pathlib.Path(archive) / 'manifest.csv').open() as f:
        rows = list(csv.DictReader(f))
    images = {r['instance_id']: r for r in rows}
    assert len(images) == len(rows), '归档清单 instance_id 重复'
for c in cases:
    c['local_ref'] += f'-{suffix}-{arch}'
    c.update(source_ref='-', archive_filename='-', archive_sha256='-')
    if mode == 'archive':
        r = images[c['instance_id']]
        assert f"{r['os']}/{r['architecture']}" == platform, c['instance_id']
        assert r['original_tag'].rsplit('/', 1)[-1] == c['local_ref'].rsplit('/', 1)[-1], c['instance_id']
        assert pathlib.Path(r['archive_filename']).name == r['archive_filename']
        assert r['validation_status'] == 'verified', c['instance_id']
        c.update(source_ref=r['original_tag'], archive_filename=r['archive_filename'], archive_sha256=r['archive_sha256'])
with pathlib.Path(selected).open('x') as f:
    json.dump(cases, f, ensure_ascii=False, indent=2)
    f.write('\n')
with pathlib.Path(plan).open('x') as f:
    for c in cases:
        f.write('\t'.join(c[k] for k in ('instance_id', 'archive_filename', 'source_ref', 'local_ref')) + '\n')
print('selected cases:', len(cases))
PY
```

`IMPORT_PLAN` 四列依次为实例 ID、tar 文件名、归档原 tag、目标 tag；registry 方式的中间两列为 `-`。
后续导入和批量模板使用同一份清单。
镜像归档没有轨迹；测试仍会读取 `TRAJECTORY_DIR` 下相应的 replay 文件。

## 3. 导入一条适配镜像并创建模板

### 3.1 选择预检实例

以下默认选择清单第一条；也可以从 `IMPORT_PLAN` 选择另一条，并同步设置这四个变量。

```bash
IFS=$'\t' read -r INSTANCE ARCHIVE_FILE SOURCE_REF TARGET_REF < "$IMPORT_PLAN"
export INSTANCE ARCHIVE_FILE SOURCE_REF TARGET_REF
export SINGLE_MANIFEST="$PARTS_DIR/$INSTANCE.json"
```

镜像已在目标 registry 时，跳过 3.2–3.6。在当前 Docker 中拉取适配镜像并检查架构，然后进入 3.7：

```bash
docker image pull --platform "$PLATFORM" "$TARGET_REF"
test "$(docker image inspect "$TARGET_REF" --format '{{.Os}}/{{.Architecture}}')" = "$PLATFORM"
```

这里使用 Docker 拉取适配 tag；`build_template.py --phase pull` 拉取的是原始镜像，不能替代。

### 3.2 校验镜像归档

导入前校验整个归档包的传输完整性；GNU `sha256sum` 不可用时使用 `shasum -a 256 -c SHA256SUMS`。
元数据与 tar 应来自同一归档包。

```bash
(cd "$ARCHIVE_DIR" && sha256sum -c SHA256SUMS)
```

### 3.3 加载单条镜像

`docker load` 会恢复归档的原始 tag；先确认该 tag 不会覆盖其他任务的本地镜像。

```bash
docker image load --input "$ARCHIVE_DIR/$ARCHIVE_FILE"
```

### 3.4 检查加载后的架构

```bash
test "$(docker image inspect "$SOURCE_REF" --format '{{.Os}}/{{.Architecture}}')" = "$PLATFORM"
```

### 3.5 设置目标 tag

目标 tag 已由第 2.9 节根据归档和目标 registry 生成，先确认目标命名空间属于本次实验。

```bash
docker image tag "$SOURCE_REF" "$TARGET_REF"
```

### 3.6 推送至目标 registry

```bash
docker image push "$TARGET_REF"
```

记录推送后的目标分发摘要：

```bash
docker image inspect "$TARGET_REF" --format '{{json .RepoDigests}}' \
  > "$DENSITY_ROOT/inventory/$EXPERIMENT_ID-$INSTANCE-repodigests.json"
```

tar SHA256 校验传输；config/layer digest 标识内容；registry manifest/index digest 标识分发对象。
现有归档是单平台导出，`load/push` 后顶层 index digest 可变化，不能以源顶层 digest 不同判定导入失败。
原 registry 已停用也不影响上述离线导入。

### 3.7 配置模板参数

仅运行 `cube` 阶段，不再执行 `pull,build,smoke,push` 适配流水线。
使用 HTTP registry 时才在数组中增加 `--registry-http`；该选项不修改 Docker 或平台信任配置。
模板需要限定节点时增加 `--cube-node <目标节点 ID>`。

```bash
BUILD_ARGS=(
  --provider cubesandbox --arch "$ARCH"
  --manifest "$SOURCE_MANIFEST" --langs "$LANGS" --max-wall "$MAX_WALL"
  --registry "$REGISTRY" --image-suffix "$IMAGE_SUFFIX"
  --cube-url "$CUBE_MASTER_URL"
  --cpu "$CPU_MILLICORES" --memory "$MEMORY_MIB"
  --writable-layer-size "$WRITABLE_LAYER_SIZE"
  --build-dir "$BUILD_DIR" --template-timeout 3600 --jobs 1 --verbose
)
```

### 3.8 预览模板请求

```bash
python "$SUITE_ROOT/build_template.py" "${BUILD_ARGS[@]}" \
  --instance "$INSTANCE" --phase cube --json-out "$SINGLE_MANIFEST" --dry-run
```

### 3.9 创建并等待模板 READY

核对预览中的地址、架构、镜像和资源后执行：

```bash
python "$SUITE_ROOT/build_template.py" "${BUILD_ARGS[@]}" \
  --instance "$INSTANCE" --phase cube --json-out "$SINGLE_MANIFEST" \
  2>&1 | tee "$DENSITY_ROOT/logs/$EXPERIMENT_ID-template-$INSTANCE.log"
```

`cube` 阶段使用本机目标镜像的 RepoDigests 并检查远端 manifest，因此本机镜像也必须存在。
镜像若已经在目标 registry，可跳过 3.2–3.6，先对 `TARGET_REF` 执行
`docker image pull --platform "$PLATFORM" "$TARGET_REF"`，再核对其架构、来源和 digest。

脚本的 envd 探针为 `49983/health`，`timeout_ms=30000`、`period_ms=500`、`failure_threshold=60`；
这是软件契约，不是宿主服务端口设置。job READY 后脚本再次确认模板 READY，再写入真实 `tpl-*` 映射。
目标、digest 或规格变化时使用新 `BUILD_DIR`；CLI 等待超时不代表服务端任务取消，
同样参数重跑会继续查询已有 job。失败 job 和日志需保留。

## 4. 单条功能预检

先完成一条预检，再扩大模板集合。配置生成器**只写 YAML/映射，不启动负载**；
它设置 `exec_only`、`/testbed`、单轮回放、绝对路径和唯一 marker。
开启鉴权时，生成配置前安全注入 `CUBE_API_KEY`。生成的 YAML 权限为 0600，含凭据时不要提交或公开。
provider 的空 key 配置会清除 SDK 环境 key，不能在 YAML 生成后只 export key 就认为配置已经更新。

### 4.1 生成预检配置

下面关闭主机监控，适合先验证远程功能；密度测试的监控见第 6 节。

```bash
export NAME="preflight-$EXPERIMENT_ID"
python "$SUITE_ROOT/docs/tools/make_density_config.py" \
  --lab "$DENSITY_ROOT" --trajectory-dir "$TRAJECTORY_DIR" \
  --manifest "$SINGLE_MANIFEST" --name "$NAME" --count 1 \
  --api-url "$CUBE_API_URL" --domain "$CUBE_SANDBOX_DOMAIN" \
  --duration 900 --action-timeout 300 --delay-scale 0 --create-batch 1
```

### 4.2 保存运行前的沙箱清单

```bash
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.before.json"
```

### 4.3 执行单条回放

```bash
bench-core --provider cubesandbox --config "$DENSITY_ROOT/configs/$NAME.yaml" \
  --vm-monitor false 2>&1 | tee "$DENSITY_ROOT/logs/$NAME.log"
```

### 4.4 核对沙箱变化

```bash
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.after.json" \
  --compare "$DENSITY_ROOT/inventory/$NAME.before.json"
```

### 4.5 定位并验收预检报告

先列出报告位置，并结合日志确定本次确切结果目录：

```bash
find "$DENSITY_ROOT/results/$NAME" -maxdepth 2 -name '*_run_summary.json'
```

将 `RUN_DIR` 设置为含报告的目录后验收：

```bash
: "${RUN_DIR:?设置本次预检含run_summary的确切目录}"
python "$SUITE_ROOT/docs/tools/verify_density_run.py" "$RUN_DIR" \
  --expected-count 1 --expected-distinct 1 --trajectories "$TRAJECTORY_DIR"
```

核对可执行步骤数、已准备的基线返回码、没有新增超时或执行异常、结果完整、该沙箱已清理。
本发布包没有配套数据项目的 `profiles/` 基线数据，replay 动作文件也不提供返回码基线；需另行取得
匹配数据或建立低负载基线，缺少时应标注“未做基线一致性比较”，不能声称通过该项验收。
校验器不验证返回码基线和清理归属，这两项需结合匹配的基线结果与创建记录核对。
`submit` / `finish` / `done` 终止标记不作为命令执行，不能简单用 JSON 数组长度验收。

工作目录应为 `/testbed` 并指向 manifest.workdir。相对路径命令额外失败时先检查工作目录，
不要直接改变轨迹或补装工具来掩盖差异。预检时长应足够覆盖所选轨迹；示例时间预算不足时，
先调整测试计划再重新执行，不能把被截断的回放当作通过。

## 5. 批量模板与完整集合

单条预检通过后处理剩余选择集。下面将导入、改 tag、推送、模板创建分别执行，方便定位失败阶段。
示例会暂存整组选中镜像；空间不足时按第 3 节逐镜像完成导入、推送和模板创建，记录完成情况后再推进。

### 5.1 加载其余适配镜像

已在目标 registry 时跳过归档操作，使用下面的拉取命令，然后进入 5.4：

```bash
while IFS=$'\t' read -r iid archive_file source_ref target_ref; do
  [ "$iid" = "$INSTANCE" ] && continue
  docker image pull --platform "$PLATFORM" "$target_ref"
  test "$(docker image inspect "$target_ref" --format '{{.Os}}/{{.Architecture}}')" = "$PLATFORM"
done < "$IMPORT_PLAN"
```

导入归档时先完成 3.2 的校验，再执行下面的加载与架构检查，然后继续 5.2–5.3：

```bash
while IFS=$'\t' read -r iid archive_file source_ref target_ref; do
  [ "$iid" = "$INSTANCE" ] && continue
  docker image load --input "$ARCHIVE_DIR/$archive_file"
  test "$(docker image inspect "$source_ref" --format '{{.Os}}/{{.Architecture}}')" = "$PLATFORM"
done < "$IMPORT_PLAN"
```

### 5.2 设置其余镜像的目标 tag

```bash
while IFS=$'\t' read -r iid archive_file source_ref target_ref; do
  [ "$iid" = "$INSTANCE" ] && continue
  docker image tag "$source_ref" "$target_ref"
done < "$IMPORT_PLAN"
```

### 5.3 推送其余镜像

```bash
while IFS=$'\t' read -r iid archive_file source_ref target_ref; do
  [ "$iid" = "$INSTANCE" ] && continue
  docker image push "$target_ref"
done < "$IMPORT_PLAN"
```

单独保存整组目标镜像的 RepoDigests：

```bash
while IFS=$'\t' read -r iid archive_file source_ref target_ref; do
  docker image inspect "$target_ref" --format '{{json .RepoDigests}}' \
    > "$DENSITY_ROOT/inventory/$EXPERIMENT_ID-$iid-repodigests.json"
done < "$IMPORT_PLAN"
```

### 5.4 创建其余模板

```bash
while IFS=$'\t' read -r iid archive_file source_ref target_ref; do
  [ "$iid" = "$INSTANCE" ] && continue
  python "$SUITE_ROOT/build_template.py" "${BUILD_ARGS[@]}" \
    --instance "$iid" --phase cube --json-out "$PARTS_DIR/$iid.json" \
    2>&1 | tee "$DENSITY_ROOT/logs/$EXPERIMENT_ID-template-$iid.log"
done < "$IMPORT_PLAN"
```

### 5.5 合并并核对模板映射

```bash
python - "$SELECTED_CASES" "$PARTS_DIR" "$FULL_MANIFEST" <<'PY'
import json, pathlib, sys
cases = json.load(open(sys.argv[1]))
parts = pathlib.Path(sys.argv[2])
merged = {}
for c in cases:
    part = json.loads((parts / f"{c['instance_id']}.json").read_text())
    assert set(part) == {c['replay_file']}
    value = part[c['replay_file']]
    assert isinstance(value, str) and value.startswith('tpl-')
    assert c['replay_file'] not in merged
    merged.update(part)
assert len(merged) == len(cases)
assert len(set(merged.values())) == len(cases)
with pathlib.Path(sys.argv[3]).open('x') as f:
    json.dump(dict(sorted(merged.items())), f, indent=2)
    f.write('\n')
print('templates:', len(merged))
PY
```

结构校验不替代模板当前 READY/节点兼容状态检查；运行前还需确认目标模板可用。
失败时保留当前镜像、job 和日志，按完成记录续跑，不合入空映射。
仅移除确认本次新增且不再被引用的 staging tag；先确认已推送、模板 READY，并保留身份记录。
不使用 prune、强制删除或直接删除 registry blob 作为批次收尾。

## 6. 运行密度阶梯

每轮只改变实验计划中的变量，固定源码、镜像 digest、集合、模板规格、模式、超时、delay_scale、
创建节奏、监控采样、日志和预热条件。预先约定超时率、尾时延与资源停止线，逐轮验收后再增加 N。
`delay_scale=0` 压缩思考时间；保真延迟用 1.0，须作为不同负载口径比较。

N 不是集合大小 K 的倍数时，各轨迹重复次数可能不同，按每条轨迹 `n_runs` 分层比较。
N<K 时只覆盖部分集合；验收的 `EXPECTED_DISTINCT` 按实际分配计划填写，不能宣称覆盖完整集合。
从单条开始，选择小规模基线后逐步增加；CPU 比例不是容量许可，准入、内存、磁盘和背景负载均可能先成为限制。

### 6.1 设置本轮参数

下列参数由实验计划填写；`CPU_BUDGET` 是目标节点或参与节点合计预算，不能无条件取驱动机的 CPU 数。
`CREATE_BATCH` 显式提供，避免继承配置生成器的默认批量大小。

```bash
: "${N:?设置本轮沙箱数}" "${CPU_BUDGET:?设置宿主CPU预算}"
: "${CREATE_BATCH:?设置每批创建数}" "${EXPECTED_DISTINCT:?设置预计覆盖轨迹数}"
: "${RUN_DURATION:?设置轮次时长秒数}" "${ACTION_TIMEOUT:?设置单步超时秒数}"
: "${DELAY_SCALE:?设置思考时间倍率}"
export VCPUS="$(python -c 'import sys; print(int(sys.argv[1])/1000)' "$CPU_MILLICORES")"
export NAME="density-n${N}-$(date -u +%Y%m%dT%H%M%SZ)"
```

### 6.2 保存运行前的沙箱清单

```bash
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.before.json"
```

### 6.3 生成密度测试配置

```bash
python "$SUITE_ROOT/docs/tools/make_density_config.py" \
  --lab "$DENSITY_ROOT" --trajectory-dir "$TRAJECTORY_DIR" \
  --manifest "$FULL_MANIFEST" --name "$NAME" --count "$N" \
  --api-url "$CUBE_API_URL" --domain "$CUBE_SANDBOX_DOMAIN" \
  --duration "$RUN_DURATION" --action-timeout "$ACTION_TIMEOUT" \
  --delay-scale "$DELAY_SCALE" --create-batch "$CREATE_BATCH" --monitor
```

### 6.4 核对 CPU 配置超分比

```bash
python - "$N" "$VCPUS" "$CPU_BUDGET" <<'PY'
import sys
print('configured CPU oversubscription:', int(sys.argv[1])*float(sys.argv[2])/float(sys.argv[3]))
PY
```

### 6.5 执行本轮回放

```bash
bench-core --provider cubesandbox --config "$DENSITY_ROOT/configs/$NAME.yaml" \
  --vm-monitor true 2>&1 | tee "$DENSITY_ROOT/logs/$NAME.log"
```

生成器设置 `round_size=N`，表示一组并发执行；`create_batch` 是创建阶段节奏，两者不能混用。
使用唯一 NAME 保存输入和 marker，不要让多个轮次共享文件。
长批次可以放在任务系统中执行，但需保留 PID、命令、退出码和终态，启动回执不能证明完成。

本文使用显式配置的 `bench-core`。其他入口如 `oversub-bench` 的默认 provider、模式和清理策略
可能不同，使用前须核对；不要直接套用会枚举清理既有沙箱的默认行为。

## 7. 结果验收与清理

### 7.1 完整性与性能门槛

CLI 会在 `results/$NAME/` 下生成带时间戳的目录。从日志确认本轮的确切目录，
不要在混合多个批次的目录树中直接取最新报告。

```bash
find "$DENSITY_ROOT/results/$NAME" -maxdepth 2 -name '*_run_summary.json'
```

设置确切的 `RUN_DIR` 后执行只读验收：

```bash
: "${RUN_DIR:?设置本轮含run_summary的确切目录}"
python "$SUITE_ROOT/docs/tools/verify_density_run.py" "$RUN_DIR" \
  --expected-count "$N" --expected-distinct "$EXPECTED_DISTINCT" \
  --trajectories "$TRAJECTORY_DIR" --require-monitor \
  --cpu-budget "$CPU_BUDGET" --vcpus "$VCPUS"
```

只读校验器面向单轮 `exec_only`，检查最终报告、轨迹/步骤完整性、series/export 一致性与监控样本，
输出超时和非超时执行异常。默认超时 run 比例门槛为 0；有预定 SLO 时显式传
`--max-timeout-run-fraction`，不得为了让已完成的结果通过再放宽门槛。

`data_complete` 表示记录完整，`quality_gate_passed` 表示满足该校验器的超时/执行异常门槛。
时延 SLO 和普通非零返回码的基线比较仍需另行检查。
校验器不连接 API，不验证实际 VM 并发或清理，故输出 `cleanup_verified=false`。
将本轮创建 ID 与监控中的 `vm_name`、时间窗口关联，确认实际峰值和覆盖时长；配置 N 或
`peak_active <= N` 都不能证明实际达到 N。CLI 退出 0、`throughput.succeeded=N` 也不能替代步骤验收。

### 7.2 清理与归属

常规新建沙箱的完整 bench-core 流程会清理其管理的实例；`--detect`、`--create-only`、
`--warmup-only` 和中断后的行为不同。不要使用共享平台上的 `bench-core --cleanup` 或
其他枚举全平台沙箱的清理命令作为本轮收尾。

```bash
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.after.json" \
  --compare "$DENSITY_ROOT/inventory/$NAME.before.json"
```

差集只表示变化，不证明归属：其他任务也可能在同一时间创建或删除资源。
交叉核对 baseline、本轮创建日志、控制面审计和实验 metadata，只删除确认属于本轮的残留 ID。
当前驱动的正常完整运行不保证调用 `save_ids`；设置 `sandbox_ids_file` 不代表一定生成清单。
需要中断恢复时，提前安排创建审计或受控创建阶段的 ID 保存，不依赖事后猜测。

精确删除使用目标版本支持的 SDK `kill()` 或 API，按环境注入鉴权，删除后再次查询并检查运行时回收。
既有沙箱不要求清零；其变化需要记录并解释。模板和 registry 镜像通常保留供后续复用，
临时沙箱、采样进程和本轮 marker 需核对收尾。

## 8. 指标与计时口径

| 指标或文件 | 含义与限制 |
|---|---|
| `run_summary.throughput.succeeded` | 完整回放到结束的轨迹次数，不表示每条命令返回 0 |
| `replay_result.n_failed` | 执行层失败的 run 数；run 为轨迹 × sandbox × round |
| `steps[].return_code` / series `exit_code` | 与原始轨迹基线比较，普通非零不自动归因于平台 |
| `timed_out` | 单步超时，单列统计 |
| `slice_failed` | 执行层失败；超时也可能置位，统计非超时异常时排除 `timed_out` |
| 创建/删除错误及实际 created/ready 数 | 控制面成功率与目标负载是否达成 |
| `*_run_summary.json` | wall、完成数、步数、steps/s、错误及其他产物位置 |
| `*_lifecycle_series.jsonl` | 每步原始时序，exec_only 的 step 事件不代表存在 pause/resume 负载 |
| `trajectories/index.json`、`*/replay_result.json` | 按轨迹、sandbox、round 定位慢步和失败 |
| `*_obs.xlsx`、`*_gantt.png`、文本报告 | 检查与展示；回溯原始口径以 JSONL/JSON 为准 |
| `vm_monitor/cubesandbox_monitor.csv` | VM 名称、PID、CPU、RSS/PSS 等；需与本轮 ID 对齐 |
| `vm_monitor/resource_report.xlsx`、`*.svg` | 主机与 VM 资源曲线，具体列以实际采集能力为准 |

原生 series 不保留完整 stdout/stderr，动作文本也可能截短。`stderr:null` 不表示没有错误；
需要按步骤索引回查原始轨迹与诊断日志，不能据此宣称输出逐字节一致。

计时与比较遵循以下边界：

- 当前驱动中 exec_only 的 VM 创建发生在 stats collector 启动前。`wall_sec` 是 collector 到报告
  读取时的窗口，不能称为创建加回放总耗时。跨轮使用同类文件，推荐 run_summary。
- shell 全流程计时还含创建、清理、导出；单步 `exec_sec` 为调用级边界，不能将不同口径相减后
  自动称为 VMM 开销。Docker smoke 时间也不是沙箱启动时延。
- 不合并不同轮次的 P95/P99；需要总体分位数时从同口径样本重算。不同轨迹长度不同，需按案例与步骤比较。
- RSS 求和可能重复计算共享页；结合 PSS、宿主 MemAvailable、页缓存、PSI 和 swap 分析内存压力。
- 宿主曲线包含平台进程和背景 VM；通过 ID、节点和时间窗口关联实验对象，不能直接减去固定背景数量。

监控采用 `monitor.enabled: "true"` 字符串、`vmm: cubesandbox`，并确保 `.venv/bin` 在 PATH。
生成器已经处理这些字段；当前驱动对开关大小写敏感，布尔 `true` 可能转换为不匹配的 `"True"`。
日志应显示 vm-monitor 已启动、marker 已识别、CSV 有数据、`vm_monitor_dir` 非空。
未配置的外部采集器会跳过，空值或默认零不代表无资源消耗。
`skip_charts: true` 省去 XLSX 图表阶段，保留数据表和常规 SVG。

相关语义以本地驱动源码为准：`agent_vm_bench/src/bench_core/observability/run_summary.py`、
`agent_vm_bench/src/bench_core/observability/stats_collector.py`、
`agent_vm_bench/src/bench_core/observability/monitor.py`。升级后重新核对输出与计时边界。

## 9. 记录与发布结果

每轮报告至少包含以下内容，不将其他主机或旧版本的结果直接作为当前环境的验收基线：

| 类别 | 必填内容 |
|---|---|
| 环境 | 节点/架构、CPU 与内存预算、组件版本/digest、背景负载与调度限制 |
| 输入 | 选择集、轨迹/镜像哈希、目标模板 ID、规格、驱动源码和依赖版本 |
| 配置 | N、实际 created/ready/驻留峰值、创建批量、模式、超时、delay_scale、轮次与预热 |
| 结果 | 完成轨迹/步骤、普通非零数、超时步/run、非超时异常、吞吐、逐案例尾时延 |
| 观测 | 主机/VM 采样范围、间隔、缺失项、资源峰值、实际并发覆盖时间 |
| 验收 | 数据完整性、预定 SLO 是否满足、残留资源、未完成原因 |

将配置超分比、实际负载和性能质量分别报告。所有轨迹完成不代表没有超时或尾时延退化。
create-only 仅验证创建准入，不等同于真实轨迹密度测试。
预热、缓存、版本和背景负载同时变化的批次不能直接作单变量因果结论。
中断或缺少关键指标的轮次单独标记，不与完整数据混为一组。

## 10. 排错与归档清单

| 现象 | 检查与处理 |
|---|---|
| 模板接口 404 | 核对 CubeMaster URL、监听服务身份和目标版本路由 |
| 模板启动探针失败 | 核对 envd、镜像架构、探针参数与启动日志；保留首个失败证据 |
| Docker smoke 正常、VM 命令失败 | 核对 guest 网络、数据面路由、平台日志和目标模板可执行性 |
| API 正常、SDK 502/504 | 检查域名解析、证书、代理排除项及数据面入口；控制面健康不等于数据面可用 |
| 相对路径命令额外失败 | 检查 `/testbed`、manifest.workdir 和 replay cwd |
| 创建数低于 N | 检查调度额度、既有用量、TAP/IP/cgroup 池和物理资源；保留首个错误 |
| 完成数正常但性能退化 | 按轨迹/步骤检查超时、执行异常和尾时延，不用放宽超时隐藏问题 |
| 监控为空 | 检查 enabled 字符串、vmm、PATH、marker、采集位置和日志 |
| 存储不足 | 分别检查 Docker、registry、模板、快照、loop backing 分区，按精确归属清理 |

归档输入与映射、镜像 digest、源码身份、依赖 freeze、脱敏配置、命令与退出码、UTC 起止、
创建/清理记录、原生结果、监控和既有资源基线。服务日志可能含下载令牌，分享前脱敏。
平台修复、配额调整和服务重启应作为独立变更记录，完成后重新预检，不能夹在不同密度轮次中而不说明。

辅助工具：[配置生成器](tools/make_density_config.py)、[只读结果校验器](tools/verify_density_run.py)、
[只读沙箱 ID 快照](tools/snapshot_cube_ids.py)。它们用于生成输入或验收，不替代原生 benchmark 执行器。


## 附录 A：可选——新增或重新适配 OCI 镜像

**已有适配镜像不执行本附录。** 仅新增 workload、更新 envd 或重做镜像时，需要原始 OCI 镜像
和 envd donor。来源、代码及模板文件见 [项目依赖与所用文件](../CUBESANDBOX.md#项目依赖与所用文件)。
当前生成 Dockerfile 支持 Debian/Ubuntu，会注入 envd/tini，并按 manifest.workdir 准备 `/testbed`。
其他发行版需另行适配。

使用第 3.7 节的 `BUILD_ARGS`，为此次适配另选 `--image-suffix`、`--build-dir`，固定 donor digest。
以下只准备并推送适配镜像，不创建模板；完成后更新镜像清单，再回到常规模板与预检流程。

```bash
: "${ENVD_IMAGE:?设置envd donor的repo@sha256摘要}"
: "${NEW_IMAGE_SUFFIX:?设置新适配版本后缀}" "${NEW_BUILD_DIR:?设置新构建目录}"
python "$SUITE_ROOT/build_template.py" "${BUILD_ARGS[@]}" \
  --instance "$INSTANCE" --phase pull,build,smoke,push \
  --envd-image "$ENVD_IMAGE" --image-suffix "$NEW_IMAGE_SUFFIX" --build-dir "$NEW_BUILD_DIR" \
  --dry-run
```

确认预览后去掉 `--dry-run` 执行。代理仅在需要时通过 `--build-network` / `--build-proxy` 配置。
适配与平台部署不是同一步骤；不要把平台升级或修复夹入密度测试轮次。
