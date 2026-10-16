# 配置快照与 Go + NUMA 操作方法

本目录配套 2026-10-16 的 CubeSandbox 社区 v0.7.1 c100n100 报告。实验服务器已保留最终组合配置，**此次整理和发布没有重新配置、重启或压测服务器**。下面的脚本是从实验步骤整理的可复用操作方法，仅完成离线测试，未在生产主机再次执行 apply/restore。现有服务器不必再执行 apply。

## 适用范围与参数

在目标主机本地以 root 运行 Python 3 标准库脚本，要求 systemd、Docker、Linux cgroup v1，以及 node1 的 CPU 列表严格为 `96-191`。脚本不会通过 SSH 连接，不包含 IP、API key、模板凭据或远端实验目录。

| 范围 | systemd 配置 | 实际验收依据 |
|---|---|---|
| CubeMaster | `GOGC=800`、`GOMAXPROCS=32`、`GOMEMLIMIT=8GiB` | `/proc/MainPID/environ` 的三个白名单变量 |
| 5 个原生组件 | `CPUAffinity=96-191`、`NUMAPolicy=bind`、`NUMAMask=1` | 所有枚举线程的 CPU 集合；主线程 `numa_maps` 的 `bind:1` |
| 8 个容器组件 | unit 同上，附加持久 `ExecStartPost` helper；Docker `--cpuset-cpus 96-191 --cpuset-mems 1` | 容器全部进程和线程、Docker HostConfig、实际叶 cpuset 及祖先 |
| 全部 13 个上述 unit | `AllowedCPUs=96-191`、`AllowedMemoryNodes=1` 声明 | 不以这两个属性单独判定 cgroup v1 已隔离 |

五个原生组件：`cubemaster`、`cube-templatecenter`、`cube-api`、`cubeops`、`cubelet`。unit 名称统一为 `cube-sandbox-<组件>.service`。

| 容器组件 | Docker 容器名 |
|---|---|
| coredns | cube-proxy-coredns |
| cube-egress | cube-egress |
| cube-lifecycle-manager | cube-lifecycle-manager |
| cube-proxy | cube-proxy |
| minio | cube-sandbox-minio |
| mysql | cube-sandbox-mysql |
| redis | cube-sandbox-redis |
| webui | cube-webui |

CPU 96–191 / node1 来自本次机器的历史映射，不是面向任意机器的默认推荐。DNS、egress-net 的 oneshot unit 无常驻进程；未启用的 s3lvol、targets、未存在的独立服务不新增映射。Docker daemon 及无关监控服务不调整。Shim/VMM 随 Cubelet 启动继承约束，脚本不创建沙箱验证继承；实验报告另有实际沙箱样本。

三个 Go 值是此次实验候选。v0.7.1 的 `debug.SetGCPercent(90)` 会覆盖初始 GOGC，因此进程环境 `GOGC=800` **不代表运行时 GC 百分比为 800**。GOMEMLIMIT 是 Go 软限制，不是 RSS/cgroup 硬限制。不同部署版本、配额、内存余量、EnvironmentFile 覆盖以及启动脚本行为需要操作人先复核。

## 快照、预览、配置、验收

将整个 `scripts/` 目录复制到目标主机的独立工具目录；不要只复制主入口文件。选择已存在、持久、空间充足的数据盘父目录。以下 `/data/cube-go-numa-state-*` 是示例，替换为自己的新目录；目录路径只允许字母、数字、`_`、`.`、`-`、`/`，不允许空格或 `..`。

```sh
# 在目标 Linux 主机本地运行；/data 必须已存在。
STATE="/data/cube-go-numa-state-$(date -u +%Y%m%dT%H%M%SZ)"
sudo python3 scripts/go_numa.py snapshot --state-dir "$STATE"
sudo python3 scripts/go_numa.py plan --state-dir "$STATE"
sudo cat "$STATE/plan.json"
sudo cat "$STATE/plan.private.diff"
```

`snapshot`、`plan`、`verify` 只读取服务，写入指定的私有证据目录，不 reload/restart、不更新 Docker。快照要求 13 个服务与 8 个容器当前运行；不接受同名目录，即使目录为空或上一份快照中断，也不覆盖。`state.json` 记录 UTC 时间、主机名、文件 SHA256、权限/所有者、每条原文件路径与恢复状态；`backup/` 保存当前加载的原 unit、drop-in，以及将修改的 systemd.control 文件。`runtime-before.json` 保存 Docker 原 cpuset、镜像/容器身份、实际进程/线程约束、白名单 Go 环境和 NUMA 映射证据。

**私有目录权限为 0700。原始 unit、diff、异常命令输出可能含配置秘密，不能把实际新采集的整个 state 目录直接上传公共仓库。** 环境文件只在 unit 中保留引用，脚本不读取/备份 EnvironmentFile 的内容，也不打印全部进程环境。它不是虚拟机、数据卷、数据库或应用数据备份。

操作人确认没有并行部署/压测、沙箱库存为空且拥有维护窗口后，执行：

```sh
sudo python3 scripts/go_numa.py apply --state-dir "$STATE" --maintenance-window
sudo python3 scripts/go_numa.py verify --state-dir "$STATE"
sudo cat "$STATE/state.json"
sudo cat "$STATE/verification.json"
```

`--maintenance-window` 是操作人的明确声明；脚本不内置访问令牌，也不会自行清空沙箱。它不会从一次 `list` 成功就推断库存为空。若已有其他同类操作，请先完成协调。

apply 会拒绝已使用的快照、配置文件或容器相对快照发生漂移的情况。它新增独立 `zzzz-materials-go-numa.conf`，备份并写入两个既有高优先级 systemd.control 属性文件，reload 后更新八容器 cpuset；停止 Egress，按顺序重启五个原生服务。Cubelet 重启后最多等待 20 分钟，轮询 `9998/v1/metrics`、`9998/v1/policies/dump` 与 TCP 9999，然后启动 Egress，再次施加容器约束、检查运行态及镜像身份。Proxy/LCM 等七个容器 wrapper 不重启，规避既有启动脚本自动 pull 的路径；因此它们的 wrapper 内存策略声明可能尚未加载，实际负载以容器 cpuset 验收。

**持久 helper 位于 `$STATE/container_cpuset.py`，在容器 unit 的 ExecStartPost 中引用。配置保留期间不可删除、移动 state 目录；它必须能在服务启动时挂载。** helper 不创建/拉取容器，等待既有容器运行后更新实际 cpuset；存在从容器启动到 post hook 完成的短窗口。它不替换现有部署脚本；本方法适用于已审阅启动链的本次 v0.7.1 安装。应用前还应审阅快照里的 unit 与引用的启动脚本，不承诺任意同名服务或那些原有脚本将来主动重启时不会拉取镜像。

verify 会保存 `runtime-verified.json` 与 `verification.json`。全线程采集不完整、集合发生变化、镜像改变、环境不符、约束未生效均不返回成功；瞬时线程变化最多重试三次。合法的单 CPU/nginx worker 亲和性只要是 96–191 的非空子集即通过。原生实际 cpuset 在此 cgroup v1 机器仍可能是根 0–383/0–3，限制通过 sched affinity 和 NUMA bind 策略生效；容器必须实测叶 cpuset 为 96–191/1。主线程 `numa_maps` 不是逐线程 `get_mempolicy` 检测；bind 策略及 cpuset 不证明所有已有/共享物理页已迁移至 node1。

## 恢复与失败处理

```sh
sudo python3 scripts/go_numa.py restore --state-dir "$STATE"
sudo cat "$STATE/state.json"
# 检查 runtime-restored.json、restore-readiness.json，并复核节点覆盖与业务健康。
```

恢复到**此次 snapshot 时刻**，而不是自动恢复到本报告实验基线。如果在已配置的服务器上创建快照，restore 会恢复该时刻已经存在的 Go + NUMA 配置。

恢复不依赖 CubeAPI 可用，不删除任何沙箱；即使 CPU 拓扑或 cgroup 挂载后来改变，restore 仍尝试独立恢复步骤并记录错误，不受 apply 的拓扑门禁阻塞。脚本只恢复/删除本次记录已开始写入的文件；校验原备份 SHA256，确认目标仍是本次写入的内容后才覆盖，保留其他文件。若别人后来修改了受管理文件，拒绝覆盖该文件、继续独立恢复步骤并报告失败。Docker 八容器按快照的原 CPU/内存节点值恢复，包括原本为空的值；不重启 Proxy/LCM。恢复原生服务时也等 Cubelet 有限就绪后才启动 Egress。

apply 内的异常和键盘中断会自动尝试恢复，调用最终仍以非零退出，不能把失败配置当成功。强制断电、SIGKILL、默认 SIGTERM 等进程终止可能来不及恢复；再次运行上述 restore，状态文件的 `writes_started` 会帮助识别已涉及文件。不提供 `--force` 覆盖他人改动。恢复失败时 `restore_errors` 给出未解决项，应保留私有目录排查。

状态含义：

- `snapshot_complete`：快照完成，尚未应用。
- `applied_and_runtime_verified`：组合配置和上述运行态检查完成。
- `restored_config_and_basic_health`：受管理配置、原 Docker cpuset/镜像及服务 active/Cubelet 端点检查通过。已保存恢复后的进程证据，但未自动逐项比较原生进程启动前后的所有策略，也未创建沙箱做业务验证。
- `apply_in_progress`、`restore_in_progress`：未完成，不能视为成功。
- `restore_failed`：存在未解决恢复步骤，不应删除 state 目录。

脚本不会跑压测、不改变 THP/numa_balancing/静态大页、不替换二进制、镜像或模板。CLI 成功并不代替业务创建可用性、1/1 节点覆盖和实际库存的验收。

## 离线验证

```sh
python3 -m unittest discover -s scripts -p test_go_numa.py -v
python3 -m py_compile scripts/go_numa.py scripts/runtime_snapshot.py scripts/container_cpuset.py
```

8 项测试覆盖 CPU 子集、固定映射、无镜像拉取/无 Proxy/LCM 重启的命令计划、先等待 Cubelet 后启动 Egress、部分写入失败与已更新容器后的就绪失败自动恢复（包括空 cpuset 值）、拒绝覆盖外部改动、拒绝重复快照和应用前配置漂移。测试使用临时文件与替代命令执行器，不访问 systemd/Docker；不构成在真实目标主机重新部署后的验收。
