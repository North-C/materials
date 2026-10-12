# CubeSandbox 超分密度测试用户指南

> Materials 发布版（2026-10-12）：命令流程沿用已验证指南；机器地址和实验目录使用示例值。
> `.95`、`.90` 是历史环境简称。轨迹、55 个镜像 tar 和原始结果需单独取得，见[交付说明](../README.md)。

本文把镜像归档、跨机导入、模板构建、轨迹回放和结果验收串成一条可迁移的流程。
主线采用已经在 `.90` 执行过的 **`bench-core + cubesandbox + exec_only`**：先创建沙箱，
在持续 RUNNING 的沙箱内回放命令，最后清理本轮沙箱。它用于测量实际驻留 VM 的密度。

**先确认架构：本次导出的 55 个 tar 都是 `linux/amd64`。`.95` 和 `.90` 是 ARM64，
不能直接拿这些 x86 镜像在它们上面构建可运行的模板。** 在 x86 CubeSandbox 节点上使用这些 tar；
在 ARM64 节点上使用已验证的 ARM64 镜像。两种架构共用轨迹，镜像内容和模板 ID 分别管理。

验证边界：x86 镜像的构建、Docker smoke 和本次归档完整性已验证，但本次没有向共享 Docker
执行 `docker load` 回环验证，也没有在新的 x86 CubeSandbox 节点跑端到端测试。迁移时必须完成
下面的单包导入与单沙箱预检，不能把 ARM64 实测直接当作 x86 运行验收。

建议阅读路径：环境 → 镜像传输 → **单条模板 → 单条预检** → 其余模板 → 密度阶梯 → 结果/清理。
第 4.3 节的批量操作在第 5 节单条预检通过后执行。

## 导航

1. [测试对象、模式和成功标准](#1-测试对象模式和成功标准)
2. [准备环境与固定版本](#2-准备环境与固定版本)
3. [镜像包传输与校验](#3-镜像包传输与校验)
4. [导入镜像并构建模板](#4-导入镜像并构建模板)
5. [单条功能预检](#5-单条功能预检)
6. [运行密度阶梯](#6-运行密度阶梯)
7. [结果验收与清理](#7-结果验收与清理)
8. [指标、图表与计时口径](#8-指标图表与计时口径)
9. [实测结果如何引用](#9-实测结果如何引用)
10. [排错与复现清单](#10-排错与复现清单)

## 1. 测试对象、模式和成功标准

### 1.1 五种产物不要混用

```text
原始 OCI 镜像 → 已注入 envd 的适配镜像 → docker save tar / registry
             → 目标集群新建 Template → 轨迹文件与 Template ID 映射 → 回放报告
```

| 产物 | 本项目位置或例子 | 用途 |
|---|---|---|
| 源数据清单 | `swerebench-offline-replays-master/verified-135/manifest.csv` | 镜像、工作目录、轨迹之间的对应关系 |
| 所选 55 条 | `go,ts,java` 且目标架构 `wall_sec_* < 2100` | 当前两架构得到同一组案例；不是直接执行全部 135 条 |
| 适配镜像 | tag 后缀 `-cube-envd-2026.16-testbed-x86` 或 `-arm64` | 预装 envd/tini 等运行依赖和 `/testbed` 别名 |
| 本次 x86 导出包 | `exports/cubesandbox-x86-55-20261010/` | 每个 instance 一个 tar，另有 manifest、SHA256SUMS |
| 模板映射 | `{"aftership__clickhouse-sql-parser-128.replay.json":"tpl-..."}` | 运行集的唯一来源；只写目标集群实际 READY 的 ID |

Tar **不包含轨迹、驱动源码或 Python 依赖**，这些要单独部署。也不要把 `.95` 的模板 ID
直接复制到 `.90` 或新集群；模板是集群/节点运行环境的产物，需要在目标环境重新构建。

### 1.2 “超分”先约定分母

设本轮沙箱数为 `N`，每沙箱 vCPU 数为 `v`，用于比较的宿主 CPU 预算为 `C`：

```text
CPU 配置超分比 = N × v / C
内存配置超分比 = N × 每 VM 配置内存 / 宿主可用于测试的内存预算
```

`C` 应明确是在线逻辑 CPU、物理核还是经过预留后的 CPU 预算，并在所有轮次保持一致。
以 384 个 CPU、每 VM 2 vCPU 为例：384/768/1152/1536 个 VM 分别是 2/4/6/8 倍；
若只使用 383 个 CPU，就报告实际 `N×2/383`，不能仍称精确整数比。
配置内存是规格，不是 RSS/PSS；“配置了 6 TiB”不等于实际已消耗 6 TiB。

| 模式 | 行为 | 本指南覆盖 |
|---|---|---|
| `exec_only` | 预创建 VM；逐条命令执行；没有 pause/resume | `.95` 单条和 `.90` 密度阶梯实际验证过，本文主线 |
| `lifecycle` | 命令之间真实暂停/恢复，运行槽参与限流 | 需要额外验证快照、内存回收和恢复正确性 |
| `trajectory` | 每条轨迹独立创建/删除 VM，持有轨迹级运行槽；仍包含逐步生命周期动作 | 是另一种负载模型，不能拿它的总数等同于同时 RUNNING 数 |

在 `exec_only` 下，`replay.running_concurrency` **不能限制 VM 创建总数**；主要由
`sandbox.total_count`、`create_batch` 和 `test.round_size` 决定创建/执行形态。
原生 `run_summary.overcommit_ratio` 是运行槽口径，历史 exec_only 轮次都为 1.0，
它不是上面的 CPU 超分比。

### 1.3 分层验收

1. 镜像：架构正确、envd 可用、工作目录正确、目标 registry 能取到 manifest。
2. 模板：job READY 后再次确认模板 READY；随后真实创建沙箱并执行命令。
3. 回放：预期案例和步骤均执行；普通非零退出码与历史轨迹比较；超时和执行异常单列。
4. 密度：实际达到目标数量；完整采集指标；按事先约定的时延/超时率阈值评估退化。
5. 清理：只清理本次创建的 ID；平台既有沙箱保持原状。

Docker `/health=204`、Template READY、SDK 命令成功、整轮回放完成是不同检查点。
本项目 aftership 轨迹有 119 条记录，其中末尾 `submit` 不执行，实际为 118 步；
历史基线本来就有 6 条非零退出码，包括 Python 不存在。不要为了得到“全绿”改写镜像工具链或轨迹。

## 2. 准备环境与固定版本

### 2.1 角色与已验证环境

目标必须已经部署可用的 CubeSandbox，并准备好 Docker、Python 3.10+、git/rsync 及足够空间。
本文不安装/升级平台。记录各组件的实际镜像 digest 或运行二进制哈希；只查看 cubemastercli 版本
不足以标识整个部署，历史环境也含有带本地修改的构建。

推荐在 **承载这些 VM 的 Cubelet 主机**运行驱动和主机指标采集器。只在工作站运行 `/proc`
采集，得到的是工作站的数据。本文命令使用 Bash，路径参数统一由环境变量提供。

| 项目 | `.95` 历史验证 | `.90` 历史验证 |
|---|---|---|
| 架构 | ARM64/openEuler | ARM64/openEuler，在线 CPU 384，内存约 2.2 TiB；以实际预算为准 |
| CubeMaster | `127.0.0.1:8089` | `127.0.0.1:8089` |
| CubeAPI | `127.0.0.1:3000` | `127.0.0.1:3000` |
| 数据面代理 | 节点地址的 HTTP 80 | `127.0.0.1:18080`；80 被 Harbor 占用 |
| registry | 本机 5500 | 任务专用本机 5501 |
| 验证范围 | 一条 ARM64 模板/回放 + 55 镜像准备 | 55 模板、exec_only 密度阶梯、主机/VM 指标 |

这是历史配置，不是任意机器的默认值。**9966 在这两台机器上是 Cubelet，不能当成 CubeMaster。**
先检查进程、服务监听、SDK API 和数据面入口，再填写下面的参数。`localhost` 只指调用进程所在主机；
若 TemplateCenter 与 registry 不同机/不同网络命名空间，镜像 URL 必须使用它实际可达的地址。

### 2.2 统一实验目录与参数

在目标主机建立大盘上的独立目录；下面使用 `/srv/density-lab`，可统一替换。
填写参数后保存在你自己的 `experiment.env`，每个新 shell 都先 `source`。

```bash
set -euo pipefail
export DENSITY_ROOT=/srv/density-lab
export SUITE_ROOT="$DENSITY_ROOT/suite"
export BENCH_SRC="$DENSITY_ROOT/agent_vm_bench"
export ARCHIVE_DIR="$DENSITY_ROOT/archives/x86-55"
export ARCH=x86                       # .90/.95 改为 arm64，并改用 ARM64 镜像
export PLATFORM=linux/amd64           # ARM64 为 linux/arm64
export REGISTRY_ADDR=127.0.0.1:5501    # 本节示例采用同机 HTTP registry
export REGISTRY_PREFIX="$REGISTRY_ADDR/density-bench-20261009"
export IMAGE_SUFFIX=cube-envd-2026.16-testbed
export CUBE_MASTER_URL=http://127.0.0.1:8089
export CUBE_API_URL=http://127.0.0.1:3000
export CUBE_PROXY_NODE_IP=127.0.0.1
export CUBE_PROXY_PORT_HTTP=18080     # 这是 .90 的值；其他机器填实际数据面端口
export CUBE_SANDBOX_DOMAIN=cube.app
export CUBE_NODE=192.0.2.90         # 文档示例地址；必须改为目标节点 IP/ID
export CPU_BUDGET="$(nproc)"         # 如需预留 CPU，显式改小并记录
mkdir -p "$DENSITY_ROOT"/{archives,configs,inventory,logs,results,runtime,template-parts}
```

对使用 IP 的本地 API/代理，至少排除环回与节点地址的上游代理；保留企业环境已有的其他排除项：

```bash
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost,$CUBE_NODE,.cube.app"
export no_proxy="$NO_PROXY"
uname -m
case "$(uname -m)" in
  x86_64) ACTUAL_PLATFORM=linux/amd64 ;;
  aarch64|arm64) ACTUAL_PLATFORM=linux/arm64 ;;
  *) echo '未覆盖的宿主架构'; exit 1 ;;
esac
test "$PLATFORM" = "$ACTUAL_PLATFORM" || { echo '镜像与宿主架构不一致'; exit 1; }
docker version
docker info --format 'data-root={{.DockerRootDir}} driver={{.Driver}}'
df -h / "$DENSITY_ROOT" /data/cubelet
free -h
curl --noproxy '*' -fsS "$CUBE_API_URL/health"
```

不要仅依据 CPU 比例直接启动几百个 VM。同时核对物理内存、磁盘实占、模板快照/可写层、
调度配额、TAP/地址池和既有资源。`ls -lh` 的稀疏文件逻辑大小、`du` 的实占和 `df` 的剩余含义不同；
loop 文件系统还要核对其 backing 文件所在分区。OCI 压缩体积不是模板和运行时的总空间预算。

### 2.3 部署工具与轨迹

从两个来源部署内容到目标的 `$SUITE_ROOT`，保留相对路径：

- 本 Materials 子目录提供 `build_template.py`、`docs/tools/`；
- 原始数据包提供 `swerebench-offline-replays-master/verified-135/manifest.csv` 与 `replays/`；
- 镜像导出包提供 tar、归档清单和镜像 digest 清单。数据目录可包含 135 条，运行集仍由模板映射限定为所选 55 条。

示例在导出工作站执行；目标目录应预先创建。替换下面四个参数，`TARGET_ROOT` 与目标的
`DENSITY_ROOT` 一致。ARM64 路径不执行最后一条 x86 tar 传输：

```bash
export DELIVERY_ROOT=/absolute/path/to/materials/ai_sandbox/cubesandbox/benchmark/swe-replay-density
export INPUT_ROOT=/absolute/path/to/density-bench
export TARGET_SSH=root@TARGET
export TARGET_ROOT=/srv/density-lab
(
  cd "$DELIVERY_ROOT"
  rsync -aR build_template.py docs/tools "$TARGET_SSH:$TARGET_ROOT/suite/"
)
(
  cd "$INPUT_ROOT"
  rsync -aR swerebench-offline-replays-master/verified-135/manifest.csv \
    swerebench-offline-replays-master/verified-135/replays "$TARGET_SSH:$TARGET_ROOT/suite/"
)
rsync -a --partial --info=progress2 "$INPUT_ROOT/exports/cubesandbox-x86-55-20261010/" \
  "$TARGET_SSH:$TARGET_ROOT/archives/x86-55/"
```

`.95` 初次使用的驱动为 `262a0534...`；`.90` 密度批次来自
`93f978f7ec27d9bc519dca2efdc809ada09acbaa`。为了复现本文，使用后一个固定 commit，
不要运行一次 `git pull` 就把不同版本的数据混在一起。以下命令只用于**新的源码目录**：

```bash
git clone https://github.com/JackWeiw/agent_vm_bench.git "$BENCH_SRC"
git -C "$BENCH_SRC" checkout --detach 93f978f7ec27d9bc519dca2efdc809ada09acbaa
python3 -m venv "$DENSITY_ROOT/.venv"
export PATH="$DENSITY_ROOT/.venv/bin:$PATH"
python -m pip install -e "$BENCH_SRC[cubesandbox]" 'cubesandbox==0.7.0'
python -m pip freeze > "$DENSITY_ROOT/inventory/pip-freeze.txt"
git -C "$BENCH_SRC" rev-parse HEAD > "$DENSITY_ROOT/inventory/bench-commit.txt"
git -C "$BENCH_SRC" status --short > "$DENSITY_ROOT/inventory/bench-dirty.txt"
sha256sum "$SUITE_ROOT/build_template.py" > "$DENSITY_ROOT/inventory/builder.sha256"
bench-core --help
vm-monitor --help
```

离线目标还需提前准备 Python wheels、固定源码快照和 registry 工具镜像；这 55 个 workload tar
不是完整离线安装介质。没有 `.git` 的源码副本，要保存来源 commit 和文件哈希，不能仅凭包版本判断身份。
本指南编写时再次只读核对了 `.90` 的原生 CLI 和核心文件哈希，与本地 `93f978f` 源码对应。

确认加载真实 SDK，而不是 provider 的开发用 Mock：

```bash
python - <<'PY'
import importlib.metadata
from cubesandbox import Sandbox
from env_provider.cubesandbox import manager
assert manager.Sandbox is Sandbox
print('cubesandbox', importlib.metadata.version('cubesandbox'))
PY
```

## 3. 镜像包传输与校验

### 3.1 本次 x86 tar 的使用方式

Pi 的输出位于 `exports/cubesandbox-x86-55-20261010/`：每镜像一个 `<instance_id>.tar`，
另有 `manifest.json`（记录在 `images` 数组）、`manifest.csv`、`image-refs.txt`、`SHA256SUMS`、
工具版本和日志。目标上先做：

选择 ARM64 registry 迁移的读者跳到 3.2，不导入此 x86 包。

```bash
cd "$ARCHIVE_DIR"
sha256sum -c SHA256SUMS
python - "$ARCHIVE_DIR/manifest.json" "$PLATFORM" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); rows = d['images']
assert len(rows) == 55 and len({r['instance_id'] for r in rows}) == 55
assert all(f"{r['os']}/{r['architecture']}" == sys.argv[2] for r in rows)
print('55 archives, target platform matched')
PY
```

三个哈希要分开记录：tar SHA256 校验传输；config/layer digest 标识镜像内容；registry
manifest/index digest 标识仓库分发对象。本次 Docker 29/BuildKit 源镜像带 provenance attestation，
按 `linux/amd64` save 后的归档不包含 `unknown/unknown` 的证明项，load/重新 push 的顶层 index digest
可能改变。不要要求它与源 index digest 必然相等；使用归档里的 config、layer 信息核对内容，
并记录目标仓库新产生的 digest。工具行为参考 [Docker save](https://docs.docker.com/reference/cli/docker/image/save/)
与 [Docker load](https://docs.docker.com/reference/cli/docker/image/load/)。

### 3.2 ARM64 或 registry→registry 迁移

`.95 → .90` 使用的是 **ARM64 registry→registry** 路径，不经过本次 x86 tar。
在目标 host 使用固定版本的 skopeo，将每个已经冻结的源 digest 复制到独立目标 registry，
复制后用 `skopeo inspect` 顶层 `Digest` 验证。不要把 `--raw` 中的 `config.digest` 当成 manifest digest。

历史工具与逐条记录在原项目的 `validation/20261009-cube90/remote-cube90/transfer55/`，
不随本次发布上传；所需镜像冻结清单须从实验归档取得。
若要严格保留多架构 index 和证明项，使用支持该格式的 skopeo `copy --all --preserve-digests`；
只有实际目标摘要核对通过，才可称为 digest-preserving 迁移。使用 HTTP 私有 registry 时需要
对应的 `--src-tls-verify=false` / `--dest-tls-verify=false`，不能把关闭校验泛化到其他仓库。

ARM64 的单镜像示例（先完成 4.1 的目标 registry 准备）：

```bash
export SKOPEO_IMAGE=quay.io/skopeo/stable@sha256:e5d5d2815b94d74767d40be7111647c3e9cdc84406a638ffe1c7ea1f286f52a3
docker run --rm --network none "$SKOPEO_IMAGE" --version
# 192.0.2.95 为示例地址，替换为实际保存 ARM64 镜像的源 registry
export SRC_REF=192.0.2.95:5500/density-bench-20261009/aftership-clickhouse-sql-parser:128-8bea76f-cube-envd-2026.16-testbed-arm64
export DST_REF="$REGISTRY_PREFIX/${SRC_REF##*/}"
export EXPECTED_DIGEST=sha256:82e3e7811948174c0755d52e61d8cebeecd261c8ff9366711d1356df0297d433
docker run --rm --network host "$SKOPEO_IMAGE" copy --all --preserve-digests \
  --src-tls-verify=false --dest-tls-verify=false \
  "docker://${SRC_REF%:*}@$EXPECTED_DIGEST" "docker://$DST_REF"
GOT_DIGEST=$(docker run --rm --network host "$SKOPEO_IMAGE" inspect --tls-verify=false \
  --format '{{.Digest}}' "docker://$DST_REF")
test "$GOT_DIGEST" = "$EXPECTED_DIGEST"
```

上面的工具镜像 digest 从 `.90` 当前已安装镜像读取，作为这条 ARM64 路径的固定工具身份；
迁移到另一架构时先核验工具镜像平台。55 条批量源引用来自冻结清单，逐条比较源/目标顶层 digest，
失败就保留记录，不继续声称整批成功。命令语义见 [skopeo copy](https://github.com/containers/skopeo/blob/main/docs/skopeo-copy.1.md)。

## 4. 导入镜像并构建模板

### 4.1 准备目标可达的 registry

优先复用已经确认可用的 registry。若需要新建，选择空闲端口、独立容器名和大盘数据目录；
以下是 `.90` 同机 HTTP 布局的示例，不修改现有 Docker daemon 或已有容器：

```bash
ss -H -lnt 'sport = :5501'             # 创建前应为空；否则改端口或复用现有服务
mkdir -p "$DENSITY_ROOT/registry"
docker run -d --name density-registry-5501 --restart unless-stopped \
  -p 127.0.0.1:5501:5000 \
  -v "$DENSITY_ROOT/registry:/var/lib/registry" registry:2
docker image inspect registry:2 --format '{{json .RepoDigests}}'
curl --noproxy '*' -fsS "http://$REGISTRY_ADDR/v2/"
```

`registry:2` 也需是目标架构可运行的镜像；离线机器应事先导入它，并记录实际 digest。
同机环回 HTTP 避免改全局 daemon 配置；远程 HTTP 仓库需要目标 Docker 已允许访问。
远程/TLS/鉴权仓库应采用实际证书和登录配置，并让 CubeMaster/TemplateCenter 能访问同一仓库。
本节的 `--registry-http` 只给 Cube 模板请求增加 `http://`，不会修改 Docker 的信任设置。

### 4.2 先完成一条：load → tag → push → cube

这一步导入的是**已适配的镜像**。不要对 tar 再运行默认完整构建流程，也不要用 builder 的
`pull` 阶段代替导入：那个阶段拉取的是 SWR 原始镜像。

下面在新目标上选 aftership。先确认同名 source/destination tag 没有指向其他用户镜像；
已有镜像时先按归档身份核对，不盲目 load 覆盖标签。

**x86 tar 路径**：

```bash
cd "$DENSITY_ROOT"
test "$ARCH" = x86
export INSTANCE=aftership__clickhouse-sql-parser-128
export SOURCE_REF="127.0.0.1:5500/density-bench-20261009/aftership-clickhouse-sql-parser:128-8bea76f-cube-envd-2026.16-testbed-x86"
export TARGET_REF="$REGISTRY_PREFIX/${SOURCE_REF##*/}"
docker image load --input "$ARCHIVE_DIR/$INSTANCE.tar"
docker image inspect "$SOURCE_REF" --format '{{.Os}}/{{.Architecture}}'
docker image tag "$SOURCE_REF" "$TARGET_REF"
docker image push "$TARGET_REF"
docker manifest inspect --insecure "$TARGET_REF"
```

**ARM64 registry 路径**：先完成 3.2 的复制，然后从目标 registry 拉到本机，供原脚本读取 RepoDigests：

```bash
cd "$DENSITY_ROOT"
test "$ARCH" = arm64
export INSTANCE=aftership__clickhouse-sql-parser-128
export TARGET_REF="$REGISTRY_PREFIX/aftership-clickhouse-sql-parser:128-8bea76f-cube-envd-2026.16-testbed-arm64"
docker image pull --platform "$PLATFORM" "$TARGET_REF"
docker image inspect "$TARGET_REF" --format '{{.Os}}/{{.Architecture}}'
```

**两架构通用的模板阶段**：

```bash
python "$SUITE_ROOT/build_template.py" --provider cubesandbox --arch "$ARCH" \
  --instance "$INSTANCE" --phase cube \
  --registry "$REGISTRY_PREFIX" --registry-http \
  --image-suffix "$IMAGE_SUFFIX" \
  --cube-url "$CUBE_MASTER_URL" --cube-node "$CUBE_NODE" \
  --cpu 2000 --memory 4096 --writable-layer-size 10G \
  --build-dir "$DENSITY_ROOT/template-jobs" \
  --json-out "$DENSITY_ROOT/template-parts/$INSTANCE.json" \
  --template-timeout 3600 --jobs 1 --verbose
```

已经有目录时不要换目标 URL/镜像 digest 去复用同一个 job 目录。READY 或仍在构建的 job 可以
通过相同参数继续查询；FAILED 要保留首个失败证据，修正原因后用新 `--build-dir` 提交。

脚本请求包含 `49983/health`、`timeout_ms=30000`、`period_ms=500`、`failure_threshold=60`。
成功后保存的是 API 返回且再次确认 READY 的 `tpl-*`。请求、job ID、镜像 digest 都在对应
`template-jobs/<arch>/<swb-name>/`。官方契约见 [自定义镜像](https://docs.cubesandbox.com/zh/guide/tutorials/bring-your-own-image)
及 [OCI 模板创建](https://docs.cubesandbox.com/zh/guide/tutorials/template-from-image)。

### 4.3 批量准备 55 条与磁盘较小的目标

容量不足以同时 load 55 个镜像时，采用 `.90` 实测的逐镜像方式：

```text
校验一个 tar → load（或从 registry pull）→ push/确认目标仓库
→ 原脚本 cube 阶段 → 保存该实例映射和日志
→ 确认无容器引用后，仅移除本次新增的 staging tags → 下一个镜像
```

批量实例以 tar 的 `manifest.csv` 或原 manifest 的 55 条筛选结果为准，按 `instance_id` 串行执行
4.2。每条使用独立日志和 `template-parts/<instance_id>.json`。源 tag、目标 tag 与 tar 文件名
必须来自清单，不能只按 registry 的 repository 数量计数（多个案例可能共用 repository 的不同 tag）。
某条失败就暂停该流程核对，不把空 JSON 合入成功清单。

下面把 x86 tar 的逐条过程合成一个 Bash 批次。先完成单条预检；示例显式跳过已经准备好的
aftership。采用专用导入节点/独立标签，并对每条检查 tag 不存在，避免覆盖用户原镜像。
`RELEASE_STAGING=1` 仅移除这个循环当次新增的两个 tag，默认保留；磁盘紧张的目标应在核实
该 ownership 规则后启用。模板失败时脚本停止，保留当前镜像和日志供排查。

```bash
test "$ARCH" = x86
test "$PLATFORM" = linux/amd64
python - "$ARCHIVE_DIR/manifest.csv" "$REGISTRY_PREFIX" > "$DENSITY_ROOT/import-plan.tsv" <<'PY'
import csv, pathlib, sys
rows = list(csv.DictReader(open(sys.argv[1], newline='')))
assert len(rows) == 55
for r in rows:
    assert r['os'] == 'linux' and r['architecture'] == 'amd64'
    assert pathlib.Path(r['archive_filename']).name == r['archive_filename']
    src = r['original_tag']
    print(r['instance_id'], r['archive_filename'], src,
          sys.argv[2].rstrip('/') + '/' + src.rsplit('/', 1)[1], sep='\t')
PY

set -euo pipefail
export RELEASE_STAGING=0
export DONE_INSTANCE=aftership__clickhouse-sql-parser-128
while IFS=$'\t' read -r iid archive src dst; do
  [ "$iid" = "$DONE_INSTANCE" ] && continue
  df -h / "$DENSITY_ROOT" /data/cubelet
  # 每条仍需依据容量预算判断；不要在空间已接近停止线时继续。
  if docker image inspect "$src" >/dev/null 2>&1; then
    echo "已有 source tag，先核对归属/身份再续跑：$src" >&2; exit 1
  fi
  if [ "$dst" != "$src" ] && docker image inspect "$dst" >/dev/null 2>&1; then
    echo "已有 target tag，先核对归属/身份再续跑：$dst" >&2; exit 1
  fi
  {
    docker image load --input "$ARCHIVE_DIR/$archive"
    test "$(docker image inspect "$src" --format '{{.Os}}/{{.Architecture}}')" = "$PLATFORM"
    [ "$dst" = "$src" ] || docker image tag "$src" "$dst"
    docker image push "$dst"
    python "$SUITE_ROOT/build_template.py" --provider cubesandbox --arch "$ARCH" \
      --instance "$iid" --phase cube --registry "$REGISTRY_PREFIX" --registry-http \
      --image-suffix "$IMAGE_SUFFIX" --cube-url "$CUBE_MASTER_URL" --cube-node "$CUBE_NODE" \
      --cpu 2000 --memory 4096 --writable-layer-size 10G \
      --build-dir "$DENSITY_ROOT/template-jobs" \
      --json-out "$DENSITY_ROOT/template-parts/$iid.json" \
      --template-timeout 3600 --jobs 1 --verbose
    if [ "$RELEASE_STAGING" = 1 ]; then
      docker image rm "$dst"
      [ "$dst" = "$src" ] || docker image rm "$src"
    fi
  } 2>&1 | tee "$DENSITY_ROOT/logs/import-template-$iid.log"
done < "$DENSITY_ROOT/import-plan.tsv"
```

这段批次是文档化的原生命令组织，未在本文编写时向新集群执行。ARM64 registry 路径则把 load/tag
替换为 3.2 的逐条复制和 `docker pull "$dst"`，其余 cube 参数不变；不要混用 x86 清单和 `--arch arm64`。
续跑时依据每条 job/映射及实时模板状态选取待处理项，不直接覆盖已有成功映射或删除失败 job。

若移除 staging tag，只对本次事先记录为“不存在”、且本次新增的精确 tag 使用
`docker image rm "$TARGET_REF"`；先确认已 push、模板 READY、无引用。不要使用 `-f`、prune、
删除 blob 文件，或删除此前就存在的 tag。源 tag 若也是本次 load 新增，可同样单独处理。
镜像已在 registry 中；移除本地 staging tag 不代表删除 registry 镜像。

55 条完成后合并映射，同时与源选择集严格比较：

```bash
python - "$SUITE_ROOT" "$DENSITY_ROOT" "$ARCH" <<'PY'
import json, pathlib, sys
suite, lab, arch = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(suite))
import build_template as b
cases = b.load_cases(b.MANIFEST_DEFAULT, {'go','ts','java'}, 2100, arch, 'unused')
assert len(cases) == 55
merged = {}
for c in cases:
    part = json.loads((lab/'template-parts'/f"{c['instance_id']}.json").read_text())
    assert set(part) == {c['replay_file']}
    value = part[c['replay_file']]
    assert isinstance(value, str) and value.startswith('tpl-')
    assert c['replay_file'] not in merged
    merged.update(part)
assert len(set(merged.values())) == 55
dst = lab/'trajectory-templates.json'
with dst.open('x') as f:
    json.dump(dict(sorted(merged.items())), f, indent=2)
    f.write('\n')
print(dst)
PY
```

此合并检查只验证映射结构；继续运行前仍需查询这些 ID 的当前 READY/副本兼容状态。
不要用手填 alias、旧集群 ID 或镜像 tag 充当模板 ID。

## 5. 单条功能预检

可以先用 4.2 生成的单实例映射做预检，再扩大到完整 55 模板集合。
本指南附带的 `make_density_config.py` **只生成 YAML/映射，不启动负载**，实际执行仍是原生 bench-core。
它为这个单轮 exec_only 场景生成绝对路径、统一 `/testbed`、唯一监控 marker 和带引号的 monitor 开关。

```bash
export PATH="$DENSITY_ROOT/.venv/bin:$PATH"
export TRAJECTORY_DIR="$SUITE_ROOT/swerebench-offline-replays-master/verified-135/replays"
export NAME="preflight-$(date -u +%Y%m%dT%H%M%SZ)"
python "$SUITE_ROOT/docs/tools/make_density_config.py" \
  --lab "$DENSITY_ROOT" --trajectory-dir "$TRAJECTORY_DIR" \
  --manifest "$DENSITY_ROOT/template-parts/aftership__clickhouse-sql-parser-128.json" \
  --name "$NAME" --count 1 --api-url "$CUBE_API_URL" --domain "$CUBE_SANDBOX_DOMAIN" \
  --duration 900 --action-timeout 300 --delay-scale 0 --monitor
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.before.json"
set -o pipefail
bench-core --provider cubesandbox --config "$DENSITY_ROOT/configs/$NAME.yaml" \
  --vm-monitor true 2>&1 | tee "$DENSITY_ROOT/logs/$NAME.log"
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.after.json" \
  --compare "$DENSITY_ROOT/inventory/$NAME.before.json"
```

不开启鉴权的 `.95/.90` 使用空 API key。开启鉴权时，从安全环境注入 `CUBE_API_KEY` 后再生成配置；
生成器会以 0600 权限保存 YAML，并且只打印文件名。不要把含密钥的 YAML 提交 Git 或直接放进公开报告。
原生 provider 的空 key 配置会清除 SDK 环境 key，所以不能以为只 export key 而 YAML 为空也会生效。

预检验收：aftership 为 118 步，112 个零返回码和 6 条原有失败，无超时；
其原始基线在 `profiles/*aftership*/replay/replay-result.json`。确认数据面命令可执行、归档输出完整、
`vm_monitor/cubesandbox_monitor.csv` 有数据、该测试沙箱已删除。`/health` 成功本身不够。

工作目录必须是 `/testbed`。`.95` 曾用 `/`，导致两条相对路径 `cat patch.txt` 额外失败；
修正后所有 118 个返回码才与历史基线匹配。不要把这类配置问题带入密度轮次。

## 6. 运行密度阶梯

### 6.1 每轮只改变计划中的变量

固定版本/镜像 digest/55 案例、2 vCPU/4096Mi 模板、模式、action_timeout、delay_scale、
创建节奏、轮数、监控采样、日志级别和预热条件。选择好超时率/尾时延 SLO 后再执行，不能跑完再放宽门槛。
N 不是 55 的倍数时，各轨迹的重复次数会略有差异，须按每条轨迹的 `n_runs` 分层比较；
小规模 N<55 时只覆盖部分运行集，验收的 expected-distinct 应对应实际覆盖计划，不能宣称全套已覆盖。
`delay_scale=0` 是压缩思考时间的负载模型，不能称为真实 agent 思考节奏；保真模式用 1.0 并单独比较。

本战役用 `bench-core` 显式配置逐轮执行。`oversub-bench` 虽存在，但其默认 provider、模式和清理策略
不同，不能直接套用默认值：默认可能执行生命周期模式及广泛清理既有沙箱。本文不以它替换已验证主线。

### 6.2 保留既有资源快照

在目标主机、正确 SDK 环境中，先只保存现有 sandbox ID。不要输出完整 metadata 或凭据。
每轮先确定 N 和唯一 NAME；下列 384 只对应已确认容量的 `.90` 示例，迁移时按资源预算改小。

```bash
export N=384
export NAME="density-n${N}-$(date -u +%Y%m%dT%H%M%SZ)"
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.before.json"
```

这是差异检查基线，不能把 `after - before` 无条件视为本任务资源；并行用户也可能创建沙箱。
调试时使用唯一 metadata；常规轮次以本轮保存的 IDs、原生日志和 provider 状态关联归属。

### 6.3 生成一轮完整并发配置并运行

下面的 N=384 对应 `.90` 的第一个密度轮，仅在容量和调度准入都已核对的目标使用。
小机器从更小 N 逐级增加，不直接照抄 384。`round_size=N` 表示一组并发执行，
`create_batch=96` 则是创建阶段的节奏，两者不是同一个并发参数。

```bash
: "${N:?先按6.2设置本轮N}" "${NAME:?先按6.2设置本轮NAME并记录baseline}"
python "$SUITE_ROOT/docs/tools/make_density_config.py" \
  --lab "$DENSITY_ROOT" --trajectory-dir "$TRAJECTORY_DIR" \
  --manifest "$DENSITY_ROOT/trajectory-templates.json" \
  --name "$NAME" --count "$N" --api-url "$CUBE_API_URL" --domain "$CUBE_SANDBOX_DOMAIN" \
  --duration 14400 --action-timeout 300 --delay-scale 0 --create-batch 96 --monitor
python - "$N" "$CPU_BUDGET" <<'PY'
import sys
print('configured CPU oversubscription:', int(sys.argv[1])*2/int(sys.argv[2]))
PY
set -o pipefail
bench-core --provider cubesandbox --config "$DENSITY_ROOT/configs/$NAME.yaml" \
  --vm-monitor true 2>&1 | tee "$DENSITY_ROOT/logs/$NAME.log"
```

逐轮验收后才继续下一 N。`.90` 的历史阶梯为 384→768→1152→1536；第一次超过 768 时被配额拒绝。
后续是经授权调整准入、验证 900 个 create-only、保留既有沙箱后再跑，不能把 1536 当作开箱默认容量。

如果复现实测的额外宿主采样，使用随包提供的 `docs/tools/host_sampler.py`，
使用下列块**替代**上面的 bench-core 执行命令，不要重复跑一遍。它是自定义辅助采样器，
不是替代 benchmark 的执行器；子 shell 退出时只结束本次 sampler PID：

```bash
(
  set -euo pipefail
  python "$SUITE_ROOT/docs/tools/host_sampler.py" "$DENSITY_ROOT/logs/host-$NAME.csv" 5 &
  SAMPLER_PID=$!
  trap 'kill -TERM "$SAMPLER_PID" 2>/dev/null || true; wait "$SAMPLER_PID" 2>/dev/null || true' EXIT
  bench-core --provider cubesandbox --config "$DENSITY_ROOT/configs/$NAME.yaml" \
    --vm-monitor true 2>&1 | tee "$DENSITY_ROOT/logs/$NAME.log"
)
```

对长批次可在已有 tmux/任务系统中执行，但始终保留命令、PID、日志和终态；不要把 nohup 启动回执当成完成。
不要让多个轮次共用同一个 stress marker；本生成器按 NAME 生成独立 marker。

## 7. 结果验收与清理

### 7.1 检查完整性，再讨论性能

原生 CLI 会在 `results/$NAME/` 下再生成一个带时间戳的目录。从日志取得这个**确切目录**，
不要在混杂多个批次的树上直接取“最新一个 run_summary”。

```bash
find "$DENSITY_ROOT/results/$NAME" -maxdepth 2 -name '*_run_summary.json'
export RUN_DIR=/absolute/path/from/the/command/above
python "$SUITE_ROOT/docs/tools/verify_density_run.py" "$RUN_DIR" \
  --expected-count "$N" --expected-distinct 55 --trajectories "$TRAJECTORY_DIR" \
  --require-monitor --cpu-budget "$CPU_BUDGET" --vcpus 2
```

单条预检用 `--expected-count 1 --expected-distinct 1`。此只读校验器适用于本文单轮 exec_only，
检查最终报告、轨迹/步骤完整性、原生 series/export 一致性、监控样本，输出实际超时和异常计数。
默认允许的超时 run 比例为 0；有事先约定的 SLO 时传 `--max-timeout-run-fraction`。
`data_complete` 与 `quality_gate_passed` 分别表示记录是否完整和质量门槛是否满足：
超时退化轮可以有完整可用的数据，同时不满足零超时 SLO。
它不连 API，也不验证清理和实际 VM 并发，输出会明确 `cleanup_verified=false`。
要证明实际并发达标，还应将本轮创建 ID 与采样中的 `vm_name`、时间窗口关联，检查预期峰值及覆盖时长；
不要从配置的 N 或 `peak_active <= N` 推出已经达到 N。
历史数据复核可把超时阈值设为 1 来仅审计结构，但这不意味着高超时率满足性能要求。

CLI 退出 0 或 `throughput.succeeded=N` 都不能替代步骤级验收。固定测试持续时间、外层 timeout、
人工中断都可能留下部分报告；`.90` 的 `quarantine/aborted-manual-20s-run` 就是无效残次数据。

### 7.2 清理边界

常规新建沙箱的完整 bench-core 流程会清理自己管理的实例；`--detect`、`--create-only`、
`--warmup-only`、SIGTERM/强杀后的行为不同。尤其 **不要在共享平台上用 `bench-core --cleanup`
或 oversub-bench 默认 cleanup 当作本轮清理**，该路径会枚举既有沙箱。

轮末重新采集 ID，与 baseline、本轮创建记录交叉核对。只对确认属于本轮的残留 ID 执行删除；
该版本正常完整运行不保证调用 `save_ids`，配置 `sandbox_ids_file` 不代表一定生成了 ID 清单；
`--create-only/--warmup-only` 才有明确保存路径。需要中断恢复能力时，应在受控创建阶段保存 ID 或
记录控制面创建审计，配合专用实验模板关联归属。无法证明归属时不自动删除。
现有平台沙箱允许继续存在。`.90` 第二批运行时有 100 个既有沙箱共存，结束时 99 个，
这既影响宿主指标，也说明“总列表必须清零”不是正确验收条件。

```bash
python "$SUITE_ROOT/docs/tools/snapshot_cube_ids.py" "$DENSITY_ROOT/inventory/$NAME.after.json" \
  --compare "$DENSITY_ROOT/inventory/$NAME.before.json"
```

模板和 registry 镜像是后续可复用资产，通常保留；临时 sandbox、采样进程和本轮 marker 要核对收尾。
重启服务可能自动恢复既有 paused 沙箱，不能假设重启后原有资源仍静止。

在本战役的无鉴权 API 环境中，对一个**已确认属于本轮**的残留 ID，可使用精确删除：

```bash
export OWNED_SANDBOX_ID=替换为已确认属于本轮的真实ID
curl --noproxy '*' -fsS -X DELETE "$CUBE_API_URL/sandboxes/$OWNED_SANDBOX_ID"
```

启用鉴权时使用安全凭据注入或持有该实例的 SDK `kill()`；不要把密钥粘贴进命令历史。
删除后再次查询并核对运行时资源回收，不能只凭 DELETE 请求已发送断言清理完成。

## 8. 指标、图表与计时口径

### 8.1 三层成功率

| 指标/文件 | 正确含义 | 常见误读 |
|---|---|---|
| `run_summary.throughput.succeeded` | 完整回放到结束的轨迹次数 | 不能解释成所有命令退出码为 0 |
| `replay_result.n_failed` | 发生执行层失败的 run 数，run 是轨迹×sandbox×round | 不等于普通非零命令数 |
| `steps[].return_code` / series `exit_code` | 命令返回值，应与原始轨迹基线比较 | 原有 `grep` 无匹配、编译错误不能自动归因平台 |
| `timed_out` | 单步超时 | 不得归并到普通非零退出码 |
| `slice_failed` | 执行层失败；历史超时也置此标记 | 统计非超时异常时要排除 `timed_out`，不能重复计数 |
| 创建/删除错误、实际 created/ready 数 | 控制面/生命周期和目标负载是否达成 | 配置 N 不等于实际 N |

### 8.2 主要产物

| 文件 | 主要用途 |
|---|---|
| `*_run_summary.json` | 统一轮次 wall、轨迹完成数、步数、steps/s、错误及其他产物位置 |
| `*_lifecycle_series.jsonl` | 每步原始时序；exec_only 也有真实 step 事件，但无 pause/resume 负载 |
| `trajectories/index.json`、`*/replay_result.json` | 按轨迹、sandbox、round 定位慢步/失败；不要把多 run 汇总误当一条 |
| `*_obs.xlsx`、`*_gantt.png`、文本报告 | 交互检查与展示，回溯时以 JSONL/JSON 为准 |
| `vm_monitor/cubesandbox_monitor.csv` | `vm_name`、pid、CPU、RSS/PSS、NUMA、swapcache；核对与本轮 ID 的映射 |
| `vm_monitor/resource_report.xlsx`、`*.svg` | 宿主 CPU/内存/压力/NUMA/磁盘/VM 曲线 |
| `host-$NAME.csv`（可选） | 自定义全机 5s 采样，补充 CPU、MemAvailable、load、shim 数 |

原生 series 不保留完整 stdout/stderr，动作文本也会截短。`stderr:null` 不表示没有错误；
需要按 step index 回查原始轨迹与受控诊断日志。不要声称已做输出逐字节对拍。

### 8.3 计时与观察边界

- exec_only 的 VM 创建发生在 stats collector 启动前。`wall_sec` 是从 collector 启动到渲染时读取的
  窗口，不能称为创建+回放总耗时；源码在 `StatsCollector._resolved_wall_sec`，读取时仍使用当前时间。
  文本、XLSX、JSON 渲染时刻不同，数值可能略异。跨轮统一使用同一类文件，推荐 run_summary。
- shell 全流程计时还包含创建、清理和导出；单步 `exec_sec` 是调用级执行边界。
  不把三者相减后自动称为 VMM 开销，也不把 Docker smoke 时间当成沙箱启动时延。
- 不合并不同轮的 P95/P99；需要总体分位数时从同口径原始样本重算。
  55 条轨迹长短不同，要按案例和步骤比较，不能只看全局吞吐。
- CPU 配置超分、内存配置超分、实际 RSS/PSS、执行并行度是不同轴。
  一次跑完不代表吞吐、尾时延或用户体验满足 SLO。
- 多 VM 的 RSS 求和可能重复计算共享页；结合 PSS、宿主 MemAvailable、匿名页/页缓存、PSI 和 swap
  分析真实内存压力，不能将配置内存、RSS 与物理占用混作同一指标。
- 宿主曲线包含平台进程和既有 VM；`vm_name` 与本轮 ID 对齐后才分析本轮 VM。
  不要简单减去一个固定的“100 台”就声称隔离了背景负载。

### 8.4 监控生效检查

在已验证的驱动版本中必须使用 `monitor.enabled: "true"`（字符串）、`vmm: cubesandbox`，
且 `.venv/bin` 在 PATH 中。`true` 布尔会被转成 `"True"` 而不等于 `"true"`；
`vmm: firecracker` 也不对应 CubeSandbox。生成器已处理这些字段，CLI `--vm-monitor true` 还会显式覆盖开关。

确认日志里启动了 vm-monitor，stress marker 被识别，CSV 不是仅有表头，`vm_monitor_dir` 非空。
外部 devkit/ksys 没配置时会跳过，它们的缺失不能被写成指标为零。
同样要核对后端是否实际填充某列；空值或默认零不是“该资源无消耗”的证据。
`skip_charts: true` 省去 xlsx 图表阶段，仍保留数据表和常规 SVG，避免大规模导出超时。

## 9. 实测结果如何引用

下表来自 `.90` **第二批、有完整指标链**的归档。参数为 2U4G、exec_only、delay_scale=0、
action_timeout=300s、1 轮，背景有约 100 个平台既有 VM；CPU 比例按 384 个 CPU 计算。

| VM 数 | 配置 CPU 比例 | run_summary wall(s) | 步数 | steps/s | 完成轨迹 | 含超时的 run |
|---:|---:|---:|---:|---:|---:|---:|
| 384 | 2.0 | 1026.827 | 31701 | 30.873 | 384 | 9 |
| 768 | 4.0 | 860.775 | 63470 | 73.736 | 768 | 15 |
| 1152 | 6.0 | 1336.151 | 95229 | 71.271 | 1152 | 51 |
| 1536 | 8.0 | 1514.433 | 126986 | 83.851 | 1536 | 194 |

不能仅凭“1536 条轨迹均完成”称 8:1 无退化：194/1536 个 run 含超时。
第一批没有完整主机/VM 指标，且较高轮次曾实际只创建 768 个沙箱，不与此表混合。
不同批次的缓存、既有资源、准入参数有差异；关于预热改善的描述只是观察，未做单变量归因。

曾经的 768 准入墙与物理内存耗尽不是一回事。后续经授权更改了 Cubelet/CubeOps 注册额度和
TAP 预创建数量，并验证 900 个空闲 VM 可创建。那是控制面准入检查，不是 900 个真实轨迹的密度结果。
不要照抄历史的 12,000,000m/10,000,000Mi 等账面配额；按目标版本、资源归属、备份和维护窗口处理。

## 10. 排错与复现清单

| 现象 | 先检查 | 处理边界 |
|---|---|---|
| CubeMaster URL 返回 404 | 实际监听进程与端口；勿用 Cubelet 9966 | 修正客户端 URL |
| 模板第一下探活就失败 | failure_threshold 是否省略为默认 1 | 与验证脚本/官方 CLI 的 60 对齐 |
| Docker 204、VM 探针超时，既有模板命令也 504 | guest 路由、CubeNet 挂载、节点与代理入口 | `.95` 曾缺 cube-dev egress/from_envoy；不能自动重放宿主修复命令 |
| API 正常、SDK 命令 502/504 | NO_PROXY、实际 proxy HTTP 端口、Host 路由 | `.90` 是 18080；控制面健康不等于数据面可用 |
| 相对路径命令额外失败 | `/testbed` 是否预先指向 manifest.workdir；replay cwd | 保留原工具链，以历史退出码为基线 |
| `no more resource` / 创建数低于 N | 调度额度、已用额度、TAP/IP/cgroup 池、真实创建数 | 保留首个错误；配额修改与重启需要单独授权 |
| 所有“任务成功”，但 Java 回放退化 | timed_out、failed run、每轨迹/步骤尾时延 | 改 action_timeout 是换实验口径，不能事后隐藏超时 |
| 监控目录为空 | enabled 字符串、vmm 类型、PATH、marker、日志 | 未采集不是零消耗；指标不全不进入下一阶梯 |
| 根分区或模板存储不足 | DockerRootDir、registry、rootfs、快照、loop backing 的各自磁盘 | 按 ID/精确 tag 清理本次资产；不删共享 blob/数据库日志 |

每轮归档：输入/模板/镜像清单及哈希、builder 和驱动身份、依赖 freeze、配置的脱敏副本、
完整命令与退出码、UTC 起止、创建/清理 ID、原生结果、监控输出和既有资源基线。
服务日志可能含 artifact 下载令牌，采集/分享前脱敏；不要把完整环境或原始鉴权请求写入公开报告。

### 证据与辅助工具索引

- [镜像与模板脚本说明](../CUBESANDBOX.md)
- [源码改动、历史验证边界与证据位置](../SOURCE_CHANGES.md)
- 原项目的证据目录（本仓库不包含原始结果或大文件）：
  `.95` 为 `validation/20261009-cube95/`，`.90` 为 `validation/20261009-cube90/`，
  x86 构建为 `validation/20261009-x86-local/rebuild-55/`，
  tar 导出为 `exports/cubesandbox-x86-55-20261010/`。
- [可选宿主采样器](tools/host_sampler.py)：读取主机总量，含既有 VM；不证明本轮归属或并发达标。
- [配置生成器](tools/make_density_config.py)；[只读结果校验器](tools/verify_density_run.py)；
  [只读沙箱 ID 清单工具](tools/snapshot_cube_ids.py)
- 固定驱动源码：[`run_summary.py:74` 的完成数](https://github.com/JackWeiw/agent_vm_bench/blob/93f978f7ec27d9bc519dca2efdc809ada09acbaa/src/bench_core/observability/run_summary.py#L74)、
  [`trajectory_summary.py:170` 的失败标记](https://github.com/JackWeiw/agent_vm_bench/blob/93f978f7ec27d9bc519dca2efdc809ada09acbaa/src/bench_core/observability/trajectory_summary.py#L170)、
  [`stats_collector.py:616` 的 wall 边界](https://github.com/JackWeiw/agent_vm_bench/blob/93f978f7ec27d9bc519dca2efdc809ada09acbaa/src/bench_core/observability/stats_collector.py#L616)、
  [`monitor.py:90/114` 的开关解析](https://github.com/JackWeiw/agent_vm_bench/blob/93f978f7ec27d9bc519dca2efdc809ada09acbaa/src/bench_core/observability/monitor.py#L90)。

辅助工具是本次指南新增的本地工具，不是上游 benchmark 执行器。其验证范围和命令检查记录见
原项目的 `validation/20261010-export-guide/`，发布复核见[交付说明](../README.md)；本文编写没有重新执行 `.95/.90` 的压力测试，也没有改动平台资源。
