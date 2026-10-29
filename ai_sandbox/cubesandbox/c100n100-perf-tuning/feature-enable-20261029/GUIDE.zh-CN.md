# CubeSandbox dirty_log 与 Cubelet NUMA 绑定指南

日期：2026-10-29。dirty_log 按 BoostKit 固定提交 `2babb6f7405677c04b7fed1563c6a5d53a8e771b` 的 [PR32](https://gitcode.com/boostkit/CubeSandbox/pull/32) 核对。NUMA 部分针对 **Cubelet 服务进程本身**，通过 systemd 设置 CPU affinity 和内存分配策略，无需 PR20 或修改 Cubelet 源码。

| 功能 | 如何使能 | 默认状态 |
|---|---|---|
| PR32 的 pause dirty-log 写出 | Cubelet 动态 YAML 设置 `host.memory.dirty_log: true` | 关闭 |
| Cubelet 进程 NUMA 绑定 | systemd `[Service]` 设置 `CPUAffinity`、`NUMAPolicy=bind`、`NUMAMask`，重启服务 | 以现有 unit 与 drop-in 为准 |

## 共同前提

启用 dirty_log 时，部署包含 PR32 的配套组件，核对**实际运行**的 `cubelet`、`containerd-shim-cube-rs`、`cube-runtime` 版本与 SHA256。VMM 链接在 Shim 中，不能只替换一个独立 hypervisor 文件。模板目录或运行命名空间内存在组件副本时，也要核对真正使用的副本。

本指南只整理使能步骤；没有修改运行环境、构建新组件或新增性能测试。

## dirty_log

### 配置

编辑 Cubelet 实际加载的动态配置，默认路径：

```text
/usr/local/services/cubetoolbox/Cubelet/dynamicconf/conf.yaml
```

实际路径以进程的 `--dynamic-conf-path` 或静态 `config.toml` 的 `dynamic_config_path` 为准。将下面配置合并进**已有** `host:`，保留其他字段：

```yaml
host:
  memory:
    dirty_log: true
```

这是 YAML 配置，不是静态 TOML 中的 `[host]` 配置，也不应由业务请求自行设置 `cube.memory.dirty_log` 注解。Cubelet 会清理外部传入的该注解，再按宿主配置生成它。

动态配置支持文件事件热加载，并有 10 秒轮询兜底。确认配置成功重载后，再从模板/快照新建沙箱，或正常 resume/rollback。**通常无需重启 Cubelet，也无需重建模板；已经运行的 VM 不会立即切换。** 恢复时会用当前宿主策略覆盖快照中旧的 `memory.dirty_log`。

### 确认生效

1. 对此次新建沙箱，在 VMM restore 配置日志中确认 `dirty_log: true`。默认日志文件为 `/data/log/CubeVmm/vmm.log`，按沙箱 ID 和本次时间窗口定位。
2. 在沙箱 `/dev/shm` 写入已知内容，记录校验和，执行 pause/resume 后再次核对内容。
3. 检查该次 pause 是否出现以下日志，确认实际采用 dirty-log 写出路径：

   ```text
   Saving dirty guest memory to snapshot image file.
   ```

只有 YAML 为 true，尚不能说明实际写出路径已生效。不要用全局历史日志判断：模板构建路径本来就可能单独启用 dirty logging。

该开关主要作用于**从快照恢复的 VM**：通过 KVM 与 VMM 的脏页位图，用于减少后续 pause 的内存扫描和写出。正常流程保留正确的基础内存镜像；不要自行把增量结果当成完整内存镜像。恢复 VM 请求 `full` 快照时仍完整写出，这是预期行为。普通冷启动路径不由该宿主开关开启 dirty logging；它也不等同于 Linux `soft-dirty` 开关。

关闭时设置 `dirty_log: false`，等待重载，再用新建或重新恢复的实例回读验证。

## 为 Cubelet 服务绑定 NUMA

以下示例将 `cube-sandbox-cubelet.service` 绑定到 **NUMA node 0**，CPU 列表从目标主机读取；改成其他节点时调整 `cubelet_node`。服务名不同则替换命令中的 unit 名。

### 1 核对节点和现有配置

```sh
systemctl --version
lscpu -e=CPU,NODE,SOCKET,ONLINE
numactl --hardware
systemctl cat cube-sandbox-cubelet.service
```

确认节点在线、有可用内存，且其 CPU 与父 cgroup 的限制相容。`NUMAPolicy`/`NUMAMask` 需要 systemd 243 或更新版本。`CPUAffinity` 指定 CPU 编号，`NUMAMask` 指定 NUMA 节点编号，两者不能混用。[systemd.exec 官方说明](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html#CPUAffinity=)

### 2 写入 service 的 drop-in

使用 `/etc/systemd/system/cube-sandbox-cubelet.service.d/zzzz-cubelet-numa.conf`，与原 service 合并生效；不需要复制整个 unit 或改动 `ExecStart`。若同名文件已存在，编辑前先备份。

```sh
cubelet_node=0
cubelet_cpus=$(cat "/sys/devices/system/node/node${cubelet_node}/cpulist")
test -n "$cubelet_cpus" || exit 1

sudo install -d -m 0755 /etc/systemd/system/cube-sandbox-cubelet.service.d
sudo tee /etc/systemd/system/cube-sandbox-cubelet.service.d/zzzz-cubelet-numa.conf >/dev/null <<EOF
[Service]
CPUAffinity=
CPUAffinity=${cubelet_cpus}
NUMAPolicy=bind
NUMAMask=
NUMAMask=${cubelet_node}
EOF
```

例如目标主机 node 0 的 CPU 为 `0-95`，写出的内容就是：

```ini
[Service]
CPUAffinity=
CPUAffinity=0-95
NUMAPolicy=bind
NUMAMask=
NUMAMask=0
```

空赋值先清除此前列表，避免旧配置与本次值累加。检查已有其他 drop-in，排除后加载的冲突项；最后以 `systemctl show` 的合并值为准。`bind` 将受该策略管理的新内存分配限制在指定节点，需留足该节点内存；不要仅凭 CPU 数量选节点。

如果希望绑定多个节点，例如 `0-1`，把 `NUMAMask` 改为 `0-1`，`CPUAffinity` 改为这些节点实际 CPU 的并集。节点不一定与 socket 一一对应。历史 .90 曾使用 `CPUAffinity=0-191`、`NUMAMask=0-1`，这是历史机器拓扑下的示例，不应直接套用到其他主机。

### 3 重载并重启 Cubelet

在可重启 Cubelet 的维护窗口执行。只运行 `daemon-reload` 不会改变既有进程的绑定，必须重启进程。[systemctl 官方说明](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html#daemon-reload)

```sh
sudo systemctl daemon-reload
systemctl show cube-sandbox-cubelet.service \
  -p CPUAffinity -p NUMAPolicy -p NUMAMask -p DropInPaths
sudo systemctl restart cube-sandbox-cubelet.service
systemctl status cube-sandbox-cubelet.service --no-pager
```

等待 Cubelet 初始化完成。一键部署的 `cube-sandbox-cube-egress` 与 `cube-sandbox-cube-egress-net` 依赖 Cubelet；若此前启用而重启后未恢复，待 Cubelet 就绪后启动它们：

```sh
sudo systemctl start cube-sandbox-cube-egress-net.service cube-sandbox-cube-egress.service
```

### 4 验证实际进程

```sh
cubelet_pid=$(systemctl show cube-sandbox-cubelet.service -p MainPID --value)
test "$cubelet_pid" -gt 0 || exit 1
ps -p "$cubelet_pid" -o pid,comm,args
sudo taskset -apc "$cubelet_pid"
sudo head -n 20 "/proc/$cubelet_pid/numa_maps"
sudo numastat -p "$cubelet_pid"
```

`taskset -apc` 检查 Cubelet 所有线程，其 CPU affinity 应在目标 CPU 集合内；`numa_maps` 检查映射策略，node 0 示例应能看到 `bind:0`，并结合 `numastat` 查看实际页分布。`NUMAPolicy` 不是 cpuset：`/proc/<pid>/status` 的 `Mems_allowed_list` 仍可能列出全部节点，不能据此判定绑定失败；也不要用另起进程的 `numactl --show` 代替检查 Cubelet。

已存在的共享页缓存可能位于其他节点，不能要求每一页都在 node 0。内存策略按进程/线程继承，改变策略也不会自动搬迁此前分配的页。[Linux NUMA 策略说明](https://docs.kernel.org/admin-guide/mm/numa_memory_policy.html)

### 5 撤销本次设置

若此 drop-in 是本次新建，移走该文件并重启；若原本存在，则恢复备份内容。不要使用 `systemctl revert` 清除该服务的其他配置。

```sh
sudo mv /etc/systemd/system/cube-sandbox-cubelet.service.d/zzzz-cubelet-numa.conf \
  /etc/systemd/system/cube-sandbox-cubelet.service.d/zzzz-cubelet-numa.conf.disabled
sudo systemctl daemon-reload
sudo systemctl restart cube-sandbox-cubelet.service
```

恢复后重新检查合并配置、实际 PID 和前述 egress 服务；如果此前还有别的 NUMA drop-in，它会重新生效。

这套配置绑定 Cubelet 自身，不依赖 PR20，也无需改 `usePoolV2` 或 `kernel.numa_balancing`。派生子进程可能继承策略；PR20 会重置 Shim 的 CPU affinity，但不等同于清除其继承的 NUMA 内存策略，因此不能由 Cubelet 的绑定推断所有沙箱的最终绑定状态。

## 核对依据

- PR32 合并提交：`86f6d9b9e20015706c2da0f2604b5731015bfc2f`。
- PR20 合并提交：`53acc6f04fe4a984480b2653d00d0363b3434de0`。
- 固定审查版本 tree：`608397465872e2050e823fd4ebf1207d3d1208f0`。
- dirty_log 配置与恢复路径：[动态配置](https://gitcode.com/boostkit/CubeSandbox/blob/2babb6f7405677c04b7fed1563c6a5d53a8e771b/Cubelet/dynamicconf/conf.yaml)、[配置加载](https://gitcode.com/boostkit/CubeSandbox/blob/2babb6f7405677c04b7fed1563c6a5d53a8e771b/Cubelet/pkg/config/config.go)、[VMM 恢复配置](https://gitcode.com/boostkit/CubeSandbox/blob/2babb6f7405677c04b7fed1563c6a5d53a8e771b/hypervisor/vmm/src/lib.rs)、[快照内存写出](https://gitcode.com/boostkit/CubeSandbox/blob/2babb6f7405677c04b7fed1563c6a5d53a8e771b/hypervisor/vmm/src/memory_manager.rs)。
- Cubelet 服务与子进程边界：[systemd unit](https://gitcode.com/boostkit/CubeSandbox/blob/2babb6f7405677c04b7fed1563c6a5d53a8e771b/deploy/one-click/systemd/cube-sandbox-cubelet.service)、[启动脚本](https://gitcode.com/boostkit/CubeSandbox/blob/2babb6f7405677c04b7fed1563c6a5d53a8e771b/deploy/one-click/scripts/systemd/cubelet-start.sh)、[PR20 的 Shim affinity 重置](https://gitcode.com/boostkit/CubeSandbox/blob/2babb6f7405677c04b7fed1563c6a5d53a8e771b/CubeShim/shim/src/main.rs)。

配置开启、运行路径生效与性能改善应分别记录；本指南不作性能收益承诺。
