# 历史 NUMA 映射与最小恢复方案（只读调查）

调查时间：2026-10-16 07:24–07:29 UTC。本调查未修改远端、未重启服务、未运行压测。读取了当前及 v071-c100n100-bottleneck 的 AGENTS.md；不提交代码。以下是恢复建议，实际执行/验收由主代理记录。

## 结论与证据优先级

找到了 10 月 14 日更晚且覆盖全部运行组件的历史备份，不能拿 10 月 13 日 Cubelet/CubeAPI 的 node0/local 实验替代它。

1. `测试机:private-path-redacted` 保存五个原生服务 `60-numa1.conf`，全部是 `CPUAffinity=96-191`、`NUMAPolicy=bind`、`NUMAMask=1`。同目录 `system.control/` 的五组文件均为 `AllowedCPUs=96-191`、`AllowedMemoryNodes=1`。逐文件内容和 SHA256 在 historical-numa-dropins.txt（原始私有证据未公开）。
2. `测试机:private-path-redacted` 行 606–610 记录同次原生服务配置和八个 Cube 容器执行 `docker update --cpuset-cpus 96-191 --cpuset-mems 1`。行 694–696 记录备份、删除上述 drop-in、清除容器限制及之后全范围 cpuset/reboot。选取证据在 history-selected.txt（原始私有证据未公开）。Shell history 是操作文本，不能单独证明当时成功；五个原生服务有实际备份交叉佐证。容器缺少当时 inspect 原始回执，但容器名单、CPU/内存节点映射清楚。
3. 较早 `tools/build-v071-137/deploy-90/numa-review.txt` 与 `rollback-20261014T023300Z/rollback.py` 仅涉及 Cubelet/CubeAPI 的 `0-95/local`，10 月 14 日上午已经撤销。该实验不是下午五原生加八容器的 node1/bind 策略。
4. 当前新采样在 current-properties.txt（原始私有证据未公开） 和 container-proc.txt（原始私有证据未公开），采集时间及文件 SHA256 见 manifest.json（原始私有证据未公开）。当前八个容器的实际 cgroup 都是 v1 `/docker/<id>`，不是 systemd wrapper 的 cgroup。

## 逐组件映射

所有 service 名均带前缀 `cube-sandbox-` 和后缀 `.service`。

| 组件 | 历史限制 | 当前采样 | 本次恢复/不适用 |
|---|---|---|---|
| cubemaster | CPU 96-191；mempolicy bind:1；AllowedMemoryNodes=1 | AllowedCPUs 96-191；CPUAffinity 空；NUMAPolicy n/a | 恢复原生进程 CPUAffinity + bind:1；Go 参数另行叠加 |
| cube-api | 同上 | 同上 | 同上 |
| cube-templatecenter | 同上 | 同上 | 同上 |
| cubeops | 同上 | 同上 | 同上 |
| cubelet | 同上 | AllowedCPUs 0-383；CPUAffinity 空；NUMAPolicy n/a | 恢复 96-191/bind:1，历史证据明确；检查 Shim/VMM 是否被运行时重新设 affinity |
| cube-egress | 容器 cube-egress：cpus 96-191/mems 1 | 容器 cpus/mems 均空，实际 0-383/0-3 | docker cpuset；unit 持久 hook |
| cube-proxy | 容器 cube-proxy：cpus 96-191/mems 1 | cpus 96-191，mems 空，实际 96-191/0-3 | 同上 |
| cube-lifecycle-manager | 容器 cube-lifecycle-manager：cpus 96-191/mems 1 | 同上 | 同上 |
| webui | 容器 cube-webui：cpus 96-191/mems 1 | 同上 | 同上 |
| redis | 容器 cube-sandbox-redis：cpus 96-191/mems 1 | 同上 | 同上 |
| mysql | 容器 cube-sandbox-mysql：cpus 96-191/mems 1 | 同上 | 同上 |
| minio | 容器 cube-sandbox-minio：cpus 96-191/mems 1 | 同上 | 同上 |
| coredns | 容器 cube-proxy-coredns：cpus 96-191/mems 1 | 同上 | 同上 |
| dns | 无历史 NUMA 文件 | oneshot，active/exited，MainPID=0 | 不适用：host routing 配置任务，无常驻 Cube 负载；不修改宿主 dnsmasq |
| cube-egress-net | 无历史 NUMA 文件 | oneshot，active/exited，MainPID=0 | 不适用：iptables/ip-rule 配置任务，无常驻进程 |
| s3lvol | 无历史 NUMA 文件 | inactive，MainPID=0 | 不适用：未启用数据面，不为本实验启动或改动 |
| control/compute target | 仅依赖编排 | target 无进程 | 不适用 |
| Shim/VMM | 无独立 cube-sandbox systemd unit | 压测前无本实验实例 | 按 Cubelet 后代实际 cpuset/affinity/policy验收；不能仅按继承假定 |

以上的 node1 集中不是随意将所有服务绑同节点，而是具体备份和历史操作所记录。CPU 96-191 对应 node1；这会把 100×2 vCPU 及服务竞争集中在 96 个逻辑 CPU 上，可能降低性能，但仍是用户要求验证的历史组合，不应改为“看起来更合理”的分散映射。

监控 grafana/prometheus/node-exporter/cube-perf-exporter 曾有独立 node2 历史策略，但不属于 CubeSandbox 组件，本次不恢复，不改 Docker daemon、系统服务或全局 NUMA/THP。

## 最小可回滚实现建议

### 五个原生服务

备份当前 unit/drop-in 后新增本实验专属 drop-in，复原 `CPUAffinity=` 清空后 `CPUAffinity=96-191`，`NUMAPolicy=bind`，`NUMAMask=1`。可以用 `systemctl set-property` 恢复历史 AllowedCPUs/AllowedMemoryNodes 的声明，但 cgroup v1 上这些声明本身并非有效 cpuset；不应把 systemctl show 当成实际隔离证据。原生进程使用 CPUAffinity 与 mempolicy 即可在 v1 生效，Mems_allowed_list 可能仍为 0-3，此时实际 `numa_maps bind:1` 才是内存策略证据。无需为得到漂亮的 Mems_allowed_list 自建 cpuset 层级。

### 八个容器

只修改 systemd 的 CPUAffinity/NUMAPolicy 不会传递给由 dockerd 创建的容器。对八个已运行容器实时 `docker update --cpuset-cpus 96-191 --cpuset-mems 1`，同时在各自 systemd drop-in 追加 ExecStartPost，调用本实验独立 helper 以在该单位未来重建容器后重新应用限制。无需编辑原脚本或镜像。

- 各容器单位当前均为 `Type=simple`，阻塞的 docker attach/compose up 是 ExecStart 的主进程，**不阻止 ExecStartPost 执行**。
- 保留原 ExecStartPost，不用空赋值清除原健康检查。追加 helper 后执行顺序是原 postcheck、限制 helper；LCM 无原 postcheck，因此 helper 必须有限轮询直到容器存在且 Running，再更新。
- helper 应绑定固定白名单容器名，读取 container ID → Running → docker update → 复查 ID/Running/HostConfig/实际 cpuset，若容器在过程中重建则重试；超时应返回失败。不能只见容器名称存在便处理旧实例。
- 初次应用时手动调用同一个 helper，不必为了执行 hook 额外重启所有容器。可保留 wrapper 的 AllowedCPUs 声明；wrapper 不是实际负载，不必为了它的 affinity 增加一次容器重建。
- **不要直接重启 CubeProxy/LCM 原 unit**：当前 `up-cube-proxy.sh:275–276` 和 `up-cube-lifecycle-manager.sh:129–130` 无条件 `docker pull` 镜像标签。新证据 container-startup-evidence.txt（原始私有证据未公开）。这会引入镜像漂移风险。本实验只做 docker update 就没有 pull。若必须验证它们重启，应先将启动镜像显式固定为当前完整 digest 并保存回退，此举比实时 update 更复杂。
- CoreDNS、Egress 的现有脚本重建容器；Egress 只在本地镜像不存在时 pull。Cubelet 重启会停 Egress 与 egress-net，因此 Egress 本轮可实际验证 hook；其镜像仍要验证重建前后 image ID 完全一致。
- `ExecStartPost` 是启动后限制，存在启动短窗口；历史 docker update 本来也如此。限制已运行容器不保证已有匿名页全部搬到 node1，不能宣称完全本地内存。报告应分开列 cpuset mems 与 numa_maps 物理分布；容器 numa_maps 的 `default` 策略在 cpuset.mems=1 下是合理结果，不要求伪造 bind:1。
- 回退恢复旧 drop-in、对精确八容器恢复采样到的 cpus/mems，然后检查实际 cgroup。旧 mems 空值需验证 Docker update 能否恢复为空；如 Docker 不接受清空，恢复全可用 0-3 并明确记录差异，不能误报逐字相同。

### 顺序与健康门禁

1. 正式 NUMA 阶段前确保上一轮拥有沙箱全部清理，保存服务与镜像身份、各 cpuset 快照。五原生服务及八容器配置一次准备好，daemon-reload。
2. 先对基础容器 mysql/redis/minio/coredns 运行 helper，服务不必停；再 proxy/lcm/webui。保持依赖与镜像不变。
3. Cubelet 重启仅执行一次并等待真正 ready。它 `Requires=` 关联 Egress，所以要在 Cubelet 的 9998/9999 端口和 inventory 恢复后启动 egress-net/Egress，检查其实际容器 cpuset、健康及镜像。
4. CubeMaster、TemplateCenter、API、CubeOps 按 Master→TemplateCenter→API→CubeOps 逐个重启并检查；不存在“active 等于 ready”的捷径。也可以按主实验既定顺序，在 Cubelet 启动等待期间完成其他原生服务重启，但不要正式压测。
5. 所有长期原生进程每线程 affinity、mempolicy，以及八容器所有进程/线程 cpuset 全部合格后做同规格预热及正式轮。每轮留运行中至少一个 Shim/VMM 的线程及 cgroup 证据。

## Cubelet 历史启动风险的准确表述

- 10/13 deploy-90/README.txt 有明确结果：Cubelet 遍历 4002 historical no-state TAP 并同步扫描 stale eBPF maps，启动 901.340913 秒；早期两个 smoke 返回 HTTP 400，active 并不足以证明可创建。这是实际历史结果。
- 10/14 `.bash_history` 行 664、669、683–691 记录多次端口等待、日志大小观察、D-state/RCU 栈检查、删除 binding/restart、短暂 unpin/repin 的排查行为；historical-startup-investigation.txt（原始私有证据未公开） 保存精确命令。这些是调查命令，**不是 RCU stall 输出，也不是 NUMA 导致挂死的证明**。
- 当前 journal 查询只保留 16:39:37 reboot 后启动日志，未获得 15:40–16:30 的原始内核异常输出。本次应把风险描述为“曾有长恢复和卡启动排查”，不能写成已证实 bind 导致 RCU 死锁。
- 观察时要同时看 9998/9999、node inventory/READY、Cubelet 近期日志进度、D-state；如果恢复进度持续推进可等历史同等级分钟数；若异常按用户 E 条恢复该阶段配置。不要从历史 shell 命令照搬 pkill 全进程或主机 reboot。

## 验收最低证据

- 五原生：MainPID/exe/hash；所有 `/proc/PID/task/TID/status` 的 `Cpus_allowed_list=96-191`；各线程 numa_maps（可读时）策略 bind:1；实际 cgroup 路径/祖先 cpuset。Mems_allowed_list=0-3 不独自判失败。
- 八容器：inspect 的 ID/image/Pid/cpuset；读取实际 `/proc/PID/cgroup` 对应 cpuset.cpus、cpuset.mems（与 ancestors）；枚举该 cpuset 中每个进程和所有线程，不只 inspect 主 PID，特别 nginx worker；预计 `96-191`/`1`。记录 default mempolicy 与既存页面分布。
- 本实验 Shim/VMM：匹配精确 owned sandbox ID，检查全线程以及 cpuset；若运行时覆盖 CPUAffinity 要如实记录，不可宣布完整沙箱绑定已生效。
- 系统 globals：THP、NUMA balancing、静态大页、镜像、模板、二进制哈希前后相同。
