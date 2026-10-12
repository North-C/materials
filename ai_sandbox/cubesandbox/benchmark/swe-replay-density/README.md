# SWE 轨迹回放密度测试材料

本目录提供 CubeSandbox 模板脚本、通用测试指南和配置/验收工具。
负载由 `agent_vm_bench/bench-core` 执行，驱动与轨迹数据需要另外准备。

**适配镜像已经推送到 registry：直接进入 [registry 快速入口](docs/CUBESANDBOX_DENSITY_GUIDE.md#快速入口镜像已在-registry)。**
路径为：准备依赖 → 生成镜像清单 → 拉取适配镜像 → `--phase cube` 创建模板 → 单条回放 → 批量模板 → 密度测试与验收。
不需要归档 tar，不重复注入 envd。

- [通用测试入口与依赖清单](CUBESANDBOX.md)：依赖项目、实际使用文件、沙箱规格和操作顺序。
- [完整操作指南](docs/CUBESANDBOX_DENSITY_GUIDE.md)：按功能拆分的命令，支持归档导入或已有 registry 镜像。
- [沙箱配置一览](docs/CUBESANDBOX_DENSITY_GUIDE.md#沙箱配置一览)：示例 2 vCPU / 4 GiB / `10G` 可写层，以及网络、TTL、回放和监控参数。
- [历史测试数据、Excel 与图表](results/README.md)：独立保留原实验结果，不作为目标环境的默认参数或验收结果。
- [源码改动清单](SOURCE_CHANGES.md)：最初脚本适配、既有源码差异和历史验证记录。
- [模板脚本](build_template.py)及[发布文件 SHA256](SHA256SUMS)：在本目录运行 `sha256sum -c SHA256SUMS`。

## 部署依赖

以下操作在运行测试的机器执行。先进入本发布目录；后续指南的 `SUITE_ROOT` 就是该目录。
也可以将本目录的脚本和文档复制到独立实验目录后再补齐外部依赖。

### 1. 指定运行目录

```bash
cd /path/to/materials/ai_sandbox/cubesandbox/benchmark/swe-replay-density
export SUITE_ROOT="$PWD"
```

### 2. 获取测试驱动

驱动来源为 `JackWeiw/agent_vm_bench`。下列命令用于新的源码目录；如果已有匹配版本，直接复用并记录版本。
`93f978f7ec27d9bc519dca2efdc809ada09acbaa` 是既有发布记录使用的兼容基线，
不是任意平台必须采用的版本；更换版本后重新做 SDK、单条回放和报告格式检查。

```bash
git clone https://github.com/JackWeiw/agent_vm_bench.git "$SUITE_ROOT/agent_vm_bench"
git -C "$SUITE_ROOT/agent_vm_bench" checkout --detach 93f978f7ec27d9bc519dca2efdc809ada09acbaa
```

Python 环境、依赖安装和真实 SDK 核验在详细指南第 2.6–2.7 节执行。
本目录的辅助脚本不替代驱动项目，也不需要单独启动上游 replay server。

### 3. 准备数据集

从原 `density-bench` 数据包或数据提供者取得对应版本的
`swerebench-offline-replays-master/verified-135/manifest.csv` 和 `replays/`。
本发布包不包含这些文件；这里不提供未经核实的数据仓库地址。

下面的 `DATASET_ROOT` 指向已取得的 `swerebench-offline-replays-master` 目录；首次部署时复制到运行目录：

```bash
export DATASET_ROOT=/path/to/swerebench-offline-replays-master
mkdir -p "$SUITE_ROOT/swerebench-offline-replays-master/verified-135/replays"
cp "$DATASET_ROOT/verified-135/manifest.csv" \
  "$SUITE_ROOT/swerebench-offline-replays-master/verified-135/manifest.csv"
rsync -a "$DATASET_ROOT/verified-135/replays/" \
  "$SUITE_ROOT/swerebench-offline-replays-master/verified-135/replays/"
```

如需逐步比较历史返回码，还需取得匹配案例的 `profiles/.../replay/replay-result.json`，
或建立低负载基线。轨迹动作文件本身不提供返回码基线。

### 4. 选择镜像来源并开始测试

- **镜像已在目标 registry**：使用 [registry 快速入口](docs/CUBESANDBOX_DENSITY_GUIDE.md#快速入口镜像已在-registry)，设置 `IMAGE_SOURCE=registry`，无需取得任何归档文件。
- **收到适配镜像归档**：按详细指南第 2 节设置 `IMAGE_SOURCE=archive`，将实际包目录填入 `ARCHIVE_DIR`；包中应有 `manifest.csv`、`SHA256SUMS` 和对应 tar。

x86 镜像仅用于匹配的 x86 节点，ARM64 测试需对应 ARM64 镜像。模板 ID 在目标集群重新生成。
本目录不包含镜像 tar、归档元数据、registry 数据、实验凭据或可直接复用的集群模板 ID。

## 发布内容与验证边界

本次更新的是两份指南、此导航页、源码改动说明中的更新记录及其 SHA256；测试脚本、辅助工具和历史结果保持原有内容。
构建脚本 SHA256 为 `ed82005f199101fb0c532a4660fe3c6f4dda67ea130a78d3cd0d33d568a1658a`。

本次文档检查覆盖 Bash/Python 示例语法、链接和章节跳转、registry 模式参数、镜像清单生成及
模板 dry-run；没有执行镜像推送、模板创建或压力测试。最新文件身份以 `SHA256SUMS` 为准。
历史实验的版本、环境、验证结果和限制分别保存在 `SOURCE_CHANGES.md` 与 `results/`，不混入通用操作步骤。

后续修改应同步指南并更新 `SHA256SUMS`。依赖版本变化后先做单条验证，再执行密度阶梯。
