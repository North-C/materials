# SWE 回放镜像与 CubeSandbox 模板准备

完整实验流程见 [CubeSandbox 超分密度测试用户指南](docs/CUBESANDBOX_DENSITY_GUIDE.md)，
覆盖镜像导入、模板、预检、密度阶梯、指标和结果验收。
已导出的 55 个 x86 tar 和轨迹需单独取得，文件边界及来源见[交付说明](README.md)。
本页摘录原项目的清单筛选与适配说明；历史部署详情见[源码改动说明](SOURCE_CHANGES.md)。

## 55 条清单的来源

源清单为 `swerebench-offline-replays-master/verified-135/manifest.csv`，共 135 条。
`build_template.py` 的默认过滤为 `language ∈ {go,ts,java}` 且目标架构的
`wall_sec_arm` / `wall_sec_x86 < 2100`。当前数据两架构筛出**同一组 55 条**：
Go 31、TS 15、Java 9。wall 列是上游按 token delay 重算的投影墙钟，不是本次测试结果。
轨迹在 `swerebench-offline-replays-master/verified-135/replays/`。

在原项目中已生成以下列表（本 Materials 包不附数据，可使用下方命令重新生成）：

- `images/verified-55-x86.txt`：55 个 x86 镜像引用。
- `images/verified-55-arm64.txt`：对应的 55 个 ARM64 镜像引用。

这些列表由 CSV 生成；CSV 更新后重新生成，不手动维护第二套筛选逻辑。
上游仓库为 `swr.cn-north-4.myhuaweicloud.com/kunpeng-ai`，数据集说明镜像公开，
无需登录。原 `verified-135/download-images.sh` 会拉 **270 个**镜像，不用于这里的 55 条子集。

在本项目根目录执行，明确指定**目标机器**架构（`x86` 对应 `linux/amd64`）：

```bash
python3 build_template.py --provider cubesandbox --arch x86 --list \
  --images-out images/verified-55-x86.txt

# 只拉这 55 个源镜像，不构建、不推送、不创建模板。
python3 build_template.py --provider cubesandbox --arch x86 --phase pull --jobs 3

# 单独拉一个源镜像。
docker pull --platform linux/amd64 \
  swr.cn-north-4.myhuaweicloud.com/kunpeng-ai/swerebench-x86-aftership-clickhouse-sql-parser:128-8bea76f
```

ARM64 将 `--arch x86` 改为 `--arch arm64`；单独拉取时用 ARM64 清单和 `linux/arm64`。
源镜像与添加 envd 后的镜像是两种产物。Docker 拉到构建机也不等于 Cube 节点已能访问镜像。

## 适配行为

原脚本默认的 AgentEnv 流程保留为 `--provider aenv`。CubeSandbox 使用：

```text
pull → build → smoke → push → cube
```

- `build`：以 SWE 镜像为最终基础，从 `ghcr.io/tencentcloud/cubesandbox-base:2026.16`
  复制 `/usr/bin/envd` 和官方 `cube-entrypoint.sh`；安装 bash、CA、curl、sudo、tini、passwd，
  保证 `user` 账户存在。当前生成的 Dockerfile 支持 Debian/Ubuntu；
  其他发行版会明确失败，需要另行适配。
- 保留源镜像文件系统、工具链、ENV、WORKDIR；替换 ENTRYPOINT/CMD 为 tini + envd 常驻服务。
  不执行原交互式 shell CMD；原 ENTRYPOINT 若承担必要初始化，须单独审查。
  设置 `ENVD_EXTRA_ARGS=-isnotfc`，不向原环境添加 Jupyter/code-interpreter 等无关服务。
- 按 manifest 的 `workdir` 提前准备 `/testbed` 别名，供多模板共用 `replay.workdir: /testbed`。
  已有 `/testbed` 必须解析到该工作目录，否则构建失败，不覆盖已有目录或其他链接。
- 改造镜像标签附加 `-cube-envd-2026.16-x86` 或 `-cube-envd-2026.16-arm64`，避免覆盖原镜像。
  更换 donor 时同时设置有区分度的 `--image-suffix`；可通过 `--envd-image repo@sha256:...` 固定 donor。
- `smoke`：用该镜像创建独立 Docker 容器，关闭容器外部网络，检查 envd `/health == 204`、
  bash、user、轨迹工作目录；结束时只删除本次创建的容器。此检查不证明 VM 恢复或回放成功。
- `push`：推送到显式指定的仓库。`cube` 从 Docker `RepoDigests` 取不可变 digest，
  再用 `docker manifest inspect` 确认仓库已有该 digest，之后发给 CubeMaster，
  使用 `/cube/template/from-image`，配置 `49983/health` 探针，默认 2000m CPU / 4096Mi 内存 / 10G 可写层。
  探针与官方 CLI 对齐：`timeout_ms=30000`、`period_ms=500`、`failure_threshold=60`。
  不能省略失败阈值：Cubelet 会将缺省值设为 1，第一次启动探测失败便立即终止。
- 保存每条的 `Dockerfile`、`request.json`、`job.json` 至 `--build-dir/<arch>/<swb-name>/`。
  超时保留服务器任务，下次继续查询同一 job。目标、镜像 digest、资源等变化时拒绝复用旧 job；
  使用新的 `--build-dir` 创建新一轮。失败 job 不会被自动重新提交。
- job 达到 READY 后再次查询模板状态，只把确认 READY 的 `tpl-*` 写入
  `trajectory-templates-cubesandbox.json`。阶段失败返回非零退出码；部分成功只输出成功条目。
  `--list`、`--dry-run` 和只构建镜像不会生成假模板 ID，也不会覆盖已有模板映射。

`--dry-run` 不调用 Docker/API，但会写生成的 Dockerfile 和请求预览文件。
阶段按上面固定顺序运行。可用 `--phase pull,build,smoke` 分步准备；单独 `cube` 要求对应改造镜像已推送，
且本机 Docker 中有对应 `RepoDigests`。Docker 29 的本地构建也可能生成 RepoDigests，
因此脚本另做远程 manifest 校验；这仍不能证明 CubeMaster 节点到 registry 的网络可达。
保留 `--verbose --jobs 1` 可显示完整 Docker 错误。

构建阶段需要访问源镜像的 apt 软件源。若构建机依赖宿主机本地 HTTP 代理，可显式使用
`--build-network host --build-proxy`；仅按变量名转交当前环境的 HTTP(S)_PROXY/NO_PROXY，
不把代理写入镜像 ENV。此选项只影响构建阶段；smoke 仍使用隔离网络。
第一条 Go 源镜像不含 python3，而本项目 replay runner 原样执行 action，不要求额外 Python shim；
适配不会仅为了 smoke 测试给所有轨迹镜像安装 Python。
