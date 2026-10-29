# CubeSandbox v0.7.1 c100n100 创建时延优化：复现指南

来源：原调优 workspace 的 `artifacts/c100n100-perf-tuning-90/REPORT.zh-CN.md`，测试机为 .90，时间 2026-10-16。本指南只收录在 .90 上**测出了收益**的手段，并写明每一项的配置方法、验证方法和回退方法。

> 仓库发布说明（2026-10-17）：本目录收录复现指南、补丁、配置样例、辅助脚本、测试指南及 s13 状态快照。文中的 `../shim-builds/` 路径指原调优 workspace 的构建产物，本次未上传二进制；可按第 4.1 节从源码构建。远端 `$R` 下的测试脚本与含密钥配置仍需在原测试环境使用。发布时仅调整来源说明及文档链接，未执行本文配置或测试命令。


**已部署 Shim-C、需要在重启后恢复优化的 .90：直接看 [5.1 重启后恢复 s13 优化配置](#restore-s13)。** 从原版开始部署仍按第 3–5 节执行。2026-10-17 补充了恢复步骤；本文命令未在本次文档整理中执行。

在 .90 上，按本文顺序全部做完后，c100n100 `-w 3` 的整轮中位数从 **283.6ms 降到 153.7ms**。其他机器的收益幅度会随硬件和内核不同而变化，见第 6 节。

> 独立配置指南（2026-10-29）：[dirty_log 与 Cubelet NUMA 绑定](feature-enable-20261029/GUIDE.zh-CN.md)，介绍 BoostKit PR32 开关与 Cubelet 服务级 systemd 绑定、验证和撤销。源码及命令语法已核对，本次未部署或实测；不继承下文 2026-10-16 的性能收益，含 PR20 的 Shim 也可能重置继承的 CPU affinity。

## 1. 收益汇总

| # | 手段 | 类型 | .90 上的收益（整轮中位数） | 是否需要改代码 |
|---|---|---|---|---|
| ① | TAP 池 4000→500，并删除多余的空闲 TAP | 配置 | 283.6 → 242.3ms（−14.6%） | 否 |
| ② | Cubelet 绑定到单个 socket（CPU 0-191，内存 bind 0-1） | systemd drop-in | 242.3 → 227.5ms（−6.1%） | 否 |
| ③ | 新模板：guest 内核参数加 `agent.log=warn` | 模板 + Shim 补丁 A | 223.8 → 183.8ms（−17.9%） | 是（Shim 新增 9 行） |
| ④ | `rcu_expedited=1` | 内核运行时参数 | 183.8 → 178.0ms（−3.2%，轮间波动从 19ms 降到 4ms） | 否 |
| ⑤ | VMM 对快照内存和 pmem 映射设置 `MADV_RANDOM`，让共享文件的页缓存只用 4K folio | Shim 补丁 B2 + 开关文件 | 177.6 → 153.7ms（−13.5%） | 是 |

几点说明：
- ③ 的对照是 s08，即已换上 Shim-A 但仍用原模板；s08 与换 Shim 前的 s03（227.5ms）相当。
- ④ 单独看收益很小，而且在 ③ 之前单独开启时（s01）反而 **+13%**。它只在 ③ 之后才有正收益，最终 153.7ms 的组合里包含它。
- ⑤ 的对照是 s11，即默认的大 folio 页缓存。

**在 .90 上试过、测不出收益的手段，不要照搬**：
- 在 ③ 之前单独开 rcu_expedited：+13%。
- Cubelet 放开到全部 CPU（跨 socket）：+12%。
- THP 改为 madvise：无变化。
- 把页缓存迁到本地 NUMA 节点：无变化。
- 恢复时用 PMD 预映射快照内存（补丁 B1）：退出次数反而增加。

## 2. 前提与环境

### 2.1 测试时 .90 的环境

下面这些设置在调优开始前就已存在，本次调优没有单独测过它们各自的贡献：

| 项目 | .90 的取值 |
|---|---|
| 硬件 | 双路 Kunpeng 950，384 逻辑 CPU，4 个 NUMA 节点（每节点 96 CPU，node0/1 属于 socket0），DDR5-6400 |
| 系统 | openEuler 24.03 SP3，内核 6.6.0-9999.sp3.vnmi.xarray，cgroup v1 |
| CubeSandbox | 社区 v0.7.1 @31d911e，单节点（Master、Cubelet 都在本机） |
| 主机设置 | THP enabled/defrag=never，numa_balancing=0，未挂载 hugetlbfs，tuned=throughput-performance，governor=performance |
| CubeMaster 环境变量 | GOGC=800，GOMAXPROCS=32，GOMEMLIMIT=8GiB（注意 v0.7.1 的 `main.go` 会把 GOGC 强制设为 90） |
| 其余 12 个服务 | CPU 绑在 node1（96-191），内存 bind 1 |
| 模板 | 2 vCPU / 2048Mi / 1G 可写层，sandbox-code 镜像，探针为 /health:49999 |

### 2.2 测量方法

每个状态跑 5 轮，取 `summary.total_time_s` 的中位数。每轮之间按 ID 逐个删掉本轮创建的 103 个实例，再检查空闲门禁（沙箱库存为 0、没有 Shim 进程、load1 < 4）。命令如下：

```sh
cube-bench -c 100 -n 100 -w 3 -m create-only -no-tui -t <template-id> -o <out>.json
```

**建议在动手前，先按同样方法测一组基线**，之后每完成一步就复测一组，这样才能判断这台机器上每一项是否有效。

### 2.3 每次变更前的检查

确认沙箱库存为 0（`GET /sandboxes` 返回空列表），并且没有 `containerd-shim-cube-rs` 进程在跑。判断 Shim 进程时要看 `/proc/*/exe`，不要用 `pgrep -f`（它会匹配到你自己命令行里的路径）。确认机器上没有其他人正在做测试。

## 3. 只改配置的手段

### ① 缩小 TAP 池并删除多余的空闲 TAP

- **原理**：Cubelet 预建的每个 TAP 都会占用 1 个 tun fd 和约 3 个 bpf-map fd。池子为 4000 时，Cubelet 持有约 1.6 万个 fd。每次为 Shim 做 fork 时，内核要在锁内复制整张 fd 表（单次 1–2ms，争用时 8–32ms），Shim 只能串行拉起。
- **取值**：`tap_init_num` 不能小于预期同时存活的沙箱数，并留些余量。池子用尽后，Cubelet 会按需新建 TAP，每个多花约 63ms（见代码 `tap_lifecycle.go`）。c100n100 一轮最多存活 103 个实例，用 500 即可，这也是社区 `config.toml` 的默认值。
- **步骤**（以下设备名格式 `10.100.x.y` 对应默认 CIDR 10.100.0.0/18）：

```sh
CONF=/usr/local/services/cubetoolbox/Cubelet/config/config.toml
cp -a $CONF $CONF.bak.$(date +%Y%m%d%H%M%S)
sed -i -E 's/^(\s*tap_init_num\s*=\s*)[0-9]+\s*$/\1500/' $CONF && grep -n tap_init_num $CONF

# 下面两条只读检查用于确认没有在用的 TAP：taps 状态应全部为 Ready，库存为 0
/usr/local/services/cubetoolbox/Cubelet/bin/cubecli container taps | awk 'NR>1{print $1}' | sort | uniq -c

systemctl stop cube-sandbox-cubelet.service
ip -br link show type tun | awk '{print $1}' | grep -E '^10\.100\.' | sort -V | tail -n +501 \
  | sed 's/^/link del dev /' > /tmp/tap-del.batch
ip -force -batch /tmp/tap-del.batch        # .90 上删除 3502 个约需 260 秒
systemctl start cube-sandbox-cubelet.service
```

- **等待就绪**：以 `Cubelet-req.log` 中出现 `cubelet successfully booted` 为准。第一次启动时要清理被删 TAP 遗留的 eBPF 策略项（日志里会有 `stale policy map gc: keep=500 deleted=…`），.90 上用了约 615 秒；之后再重启只要 1–77 秒。Cubelet 就绪后，再依次启动 `cube-sandbox-cube-egress-net` 和 `cube-sandbox-cube-egress`。
- **验证**：

```sh
ip -br link show type tun | grep -c '^10\.100\.'                          # 期望 500
ls /proc/$(systemctl show -p MainPID --value cube-sandbox-cubelet)/fd | wc -l   # .90 上从 16130 降到约 2000
```

- **回退**：恢复 `config.toml` 的备份，然后重启 Cubelet。后台会把 TAP 池补回原数量。

### ② 把 Cubelet 绑定到单个 socket

- **原理**：Cubelet 拉起的 Shim、VMM 和 vCPU 线程会继承它的 CPU 亲和性和内存策略。在 .90 上，Cubelet 原本被绑在 node1 的 96 个 CPU 上，200 个 vCPU 都挤在这里。扩到同一 socket 的两个节点后，排队基本消失；但扩到全部 4 个节点（跨 socket）反而慢了 40%。
- **怎么为其他机器选值**：用 `numactl --hardware` 看节点之间的距离，选**同一个 socket** 内的节点（.90 上同 socket 距离为 15，跨 socket 为 20）。CPU 数量至少要容纳 2×并发 vCPU 再加控制面。.90 只测过 96、192、384 三档 CPU。
- **步骤**：把 `files/zzz-perf-tuning-numa.conf` 改成本机的 CPU 范围和节点，然后：

```sh
install -m 0644 zzz-perf-tuning-numa.conf /etc/systemd/system/cube-sandbox-cubelet.service.d/
systemctl daemon-reload && systemctl restart cube-sandbox-cubelet.service
# 等待 "cubelet successfully booted"，然后启动 egress-net 和 egress（同 ①）
```

- **验证**：在 cgroup v1 下，`AllowedCPUs` 不生效，所以必须看线程的实际状态：

```sh
P=$(systemctl show -p MainPID --value cube-sandbox-cubelet)
cat /proc/$P/task/*/status | awk '/Cpus_allowed_list/{print $2}' | sort | uniq -c   # 期望全部为 0-191
head -1 /proc/$P/numa_maps                                                          # 期望 bind:0-1
```

- **回退**：删除这个 drop-in，执行 `daemon-reload`，然后重启 Cubelet。

### ④ 开启 rcu_expedited（必须在 ③ 之后）

- **原理**：cube-bench 打开第 64 个 fd 时，内核扩展 fd 表需要等一次 RCU 宽限期。在 384 核、HZ=250 的机器上，这一次要 30–60ms，导致 100 个请求分成两波到达。开启 expedited RCU 后，100 个请求能在约 20ms 内全部到达。
- **为什么必须在 ③ 之后**：③ 之前，削峰效应反而在保护服务端，请求同时到达会让服务端更慢（s01 +13%）。
- **步骤**：`echo 1 > /sys/kernel/rcu_expedited`（运行时生效，重启后失效）。持久化可以用 `files/cube-perf-tmpfiles.conf` 里的 `w` 行，或者在内核启动参数里加 `rcupdate.rcu_expedited=1`。这两种持久化方式在 .90 上都没有验证过。
- **回退**：`echo 0 > /sys/kernel/rcu_expedited`。

## 4. 需要改代码的手段

### 4.1 构建 Shim

- **补丁**：
  - `patches/ABC-combined.patch`：包含补丁 A（cmdline 别名注解）、B1（PMD 预映射，默认关闭）和 B2（MADV_RANDOM），基于 v0.7.1 @31d911e，已确认能在干净源码上打上。
  - 这就是 s13 使用的 Shim-C（containerd-shim-cube-rs SHA256 67d8d06a6f264023df91d2f928f4205fcc33f3e02b8f2d0fe03a4d953614cbad）；2026-10-17 只读核查时，两处部署文件仍为此哈希。
  - 只需要 ③ 的话，可以只用 `patches/A-cmdline-alias.patch`，对应 Shim-A（6cf0887c…）。
  - 补丁文件的哈希见 `patches/SHA256SUMS`。
- **构建**：

```sh
git clone <CubeSandbox 仓库> src && cd src && git checkout 31d911e430fdf8a8879bd062b8e78066c1a8e89d
git apply /path/to/patches/ABC-combined.patch
cd CubeShim && cargo +1.77.2 build --release --locked
# 产物：target/release/containerd-shim-cube-rs（VMM 作为库一起编进去）
```

  .90 用的产物是在 .140 上用固定构建镜像 `sha256:0f7cdb96…` 和 `build-components.sh shim` 构建的，用时约 8 分钟。构建记录在 `../shim-builds/`。如果目标机也是 ARM64、v0.7.1，可以直接用 `../shim-builds/C/bin/containerd-shim-cube-rs`。
- **部署**：检查库存为 0、没有 Shim 进程后，替换**两处路径**并备份原版。Shim 是每个沙箱单独启动的，不需要重启任何服务。

```sh
for p in /usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs \
         /data/cubelet/root/component_versions/cube-shim/v0.7.1/bin/containerd-shim-cube-rs; do
  [ -e $p.orig ] || cp -a $p $p.orig     # 只在第一次备份，避免重复执行时覆盖原版
  install -m 0755 containerd-shim-cube-rs $p.new && mv -f $p.new $p
done
sha256sum /usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs \
          /data/cubelet/root/component_versions/cube-shim/v0.7.1/bin/containerd-shim-cube-rs
```

  社区原版 Shim 的哈希是 8d2b467e…，`cube-runtime` 不用替换。
- **回退**：把两处 `.orig` 改回原名。

### ③ 新模板：agent.log=warn（需要先部署补丁 A）

- **原理**：guest 里的 agent 是 PID 1，它的 INFO 日志经 PL011 串口逐字符输出，每个字符要 2 次 VM 退出，每创建一个沙箱约 1345 次。100 并发时，每次退出的成本放大了约 5 倍，这些日志就在创建路径上，把 guest 内的两步从约 5ms 拖到约 50ms。`agent.log=warn` 会在构建模板时写进快照，之后每次恢复都会继承。
- **为什么要改代码**：社区 v0.7.1 没有任何路径能把 guest 内核参数从模板传到 Shim。CubeMaster 会丢掉不以 `cube.master` 开头的 `cube.*` 注解，Cubelet 沙箱级注解也有白名单。补丁 A 让 Shim 额外接受一个不以 `cube.` 开头的别名注解 `io.cubesandbox.vm.kernel.cmdline.append`。
- **顺序**：**先部署 Shim-A 或 Shim-C，再创建模板**。构建模板时启动的 VM 由新 Shim 处理，参数才会写进快照。
- **步骤**：在目标机上，从现有的 READY 模板派生：

```sh
python3 make_template_request.py <原模板ID> /root/tpl-agentwarn.json --log-level warn
#   这一步只读；输出新模板 ID，以及资源、可写层、rootfs 供核对
#   请求文件里带制品下载 token，文件权限为 0600，不要外传
/usr/local/bin/cubemastercli tpl create -f /root/tpl-agentwarn.json --node <本机节点IP> --json
```

  脚本会**显式写入新的 template.id**。这是为了绕开 v0.7.1 CubeMaster 的一个 bug：不指定 ID 时，存下来的请求和快照会被分配两个不同的 ID，用这个模板创建沙箱会报 `130597 no more resource`。
- **验证**：

```sh
T=<新模板ID>
cubemastercli tpl info $T --include-request --json | grep -o 'tpl-[0-9a-f]\{24\}' | sort | uniq -c   # 只有一个 ID
grep "${T}_0" /data/log/CubeShim/cube-shim-req.log | grep -o 'agent.log=warn' | head -1           # 构建 VM 的 cmdline 里有该参数
# 用新模板创建一个 c1 沙箱，对比 /sys/kernel/debug/kvm/mmio_exit_user 的增量：原模板约 1345，新模板约 52
```

- **代价**：guest agent 的 INFO 日志不再出现在 Shim 日志里，WARN 及以上仍然保留。
- **回退**：测试改回使用原模板即可。原模板不受任何影响。

### ⑤ 共享页缓存只用 4K folio（需要部署 Shim-C）

- **原理**：100 个 VM 都映射同一个快照内存文件和同一份 pmem 镜像。每次 stage-2 缺页时，宿主侧都要对后备页缓存 folio 做引用计数。大 folio 的所有子页共用一个引用计数缓存行，100 个 VM 在少数几个缓存行上争用：每次缺页在 c1 下约 2.9µs，c100 下约 5.7µs，每个 VM 约 1.88 万次。`MADV_RANDOM` 会关闭 mmap 预读，冷缓存缺页时只分配 order-0 folio。
- **步骤**：

```sh
mkdir -p /run/cube-perf && touch /run/cube-perf/snap_madv_random     # 开关；snap_populate_read（B1）保持不存在
# 逐出共享文件里已经形成的大 folio，只丢弃干净缓存，不影响文件内容
python3 pagecache_nodes.py --evict \
  /usr/local/services/cubetoolbox/cubebox_os_image/<rfs-id>/<rfs-id>.ext4 \
  /data/cubelet/root/component_versions/cube-agent/v0.7.1/cube-agent.ext4 \
  /data/cubelet/root/component_versions/cube-image/<guest-image>/cube-guest-image-cpu.img \
  /data/cubelet/storage/xfs/objects/volumes/tpl-<新模板ID>-memory/tpl-<新模板ID>-memory
```

  文件列表要以本机为准。办法是建一个 c1 沙箱，查看它 VMM 进程的 `/proc/<pid>/maps` 里映射了哪些共享文件；记录路径后，先清理这个 c1 沙箱，再次确认零库存、无 Shim 后才执行 `--evict`。`pagecache_nodes.py <文件…>`（不加 `--evict`）检查缓存驻留，不修改文件内容。该脚本硬编码 ARM64 系统调用号和 4KiB 页大小，仅适用于相符环境。开关文件放在 `/run` 下，重启后会丢失，可以用 `files/cube-perf-tmpfiles.conf` 持久化（未在 .90 上验证）。
- **验证**：VMM 日志里要能看到 `snapshot memory: MADV_RANDOM applied … size 0x80000000` 和 `pmem: MADV_RANDOM applied`，而且没有 `MADV_RANDOM failed`。在 .90 上，从冷缓存开始的第一轮约 157ms（4K 随机读盘），之后稳定在约 154ms。
- **注意**：
  - 如果模板构建、备份或 `cat`、`cp` 之类的顺序读先把这些文件读进页缓存，又会形成大 folio。每次重建模板或机器重启之后，都要先 `--evict` 再测试。
  - 这一项依赖内核页缓存支持大 folio（XFS 在 6.x 内核上默认支持）。如果内核本来就只用 4K 页缓存，这一项预期没有收益。
- **回退**：删除开关文件，并保持 `snap_populate_read` 不存在，后续新建映射会跳过 B1/B2 优化。已有映射上的 advice 不会被撤销，已形成的 4K 页缓存也不会自动变回大 folio。

## 5. 推荐执行顺序与验收

1. 先测基线（第 2.2 节）。
2. 做 ①，复测。
3. 做 ②，复测。
4. 构建并部署 Shim-C（4.1），用原模板复测，结果应与上一步相当，以确认重编 Shim 本身没有影响。
5. 做 ③，建新模板，之后的测试改用新模板。
6. 做 ④，复测。
7. 做 ⑤：创建开关文件，逐出页缓存，复测。
8. 每一步都要确认 100/100 成功、实例全部清理干净。如果某一步没有收益，就回退这一步，不要把它带入下一步。

.90 上各步的参考值：283.6 → 242.3 → 227.5 →（换 Shim）223.8 → 183.8 → 178.0 → 153.7ms。

<a id="restore-s13"></a>

### 5.1 重启后恢复 s13 优化配置（.90）

适用范围：**192.168.25.90 已部署 Shim-C 和 agent.log=warn 模板，只需恢复运行时设置及缓存条件**。这套流程不重新构建模板、不替换二进制、不重启服务。TAP、绑核或模板不符时，先按前面的对应章节修复，再执行本节。

2026-10-17 18:12 左右的只读核查发现：两处 Shim-C 和 Master/Cubelet 配置哈希与 s13 相同，但机器在 15:23（北京时间）重启后，`rcu_expedited=0`、`/run/cube-perf` 不存在、THP defrag=madvise。当前内核为 `6.6.0-with-softdirty+`，原测试记录为 `6.6.0-9999.sp3.vnmi.xarray.d383a36d`。**恢复以下配置不代表内核和性能环境完全相同，必须重新测量。** 此流程不自动切换内核。

#### A. 目标配置与前置检查

| 项目 | s13 目标 | 恢复方式 |
|---|---|---|
| Shim | 两处均为 Shim-C，完整 SHA256 见下方断言 | 不符则停止，参见 4.1 |
| 模板 | `tpl-381852bfe518c30bb815e163`，agent.log=warn，2 vCPU / 2048Mi / 1G | 使用现有 `capture100.agentwarn.json`；换模板需重新核对共享文件 |
| TAP | `tap_init_num=500`，空闲时实际 TAP 500 | 已满足则保留；不符参见 ① |
| Cubelet | CPU 0-191，NUMA bind 0-1 | 不符参见 ② |
| Master/API/TemplateCenter | CPU 96-191，NUMA bind 1 | 与 s13 快照核对 |
| Master Go 环境 | GOGC=800、GOMAXPROCS=32、GOMEMLIMIT=8GiB | 仅环境记录；GOGC 仍受程序覆盖，见 2.1 |
| THP enabled / defrag | never / never | 下方按 s13 恢复；不是 MADV_RANDOM 的前提 |
| 自动 NUMA 平衡 | 0 | 下方恢复 |
| governor / tuned | performance / throughput-performance | 只读核对，避免切换 tuned 后覆盖手工设置 |
| RCU | expedited=1、normal=0 | 下方恢复；仅用于本优化组合 |
| B2 / B1 开关 | snap_madv_random 存在 / snap_populate_read 不存在 | 下方恢复 |
| 相关共享文件缓存 | 先清空，后由 VM 自然填充；驻留页应为 4K folio | 定向逐出 + 实测验证 |

以下命令在 **.90 的同一个 root Bash 会话**依次执行。测试目录与脚本已经存在，配置含密钥，不要直接打印。先确认机器由本次测试独占，暂停模板构建、备份和其他会读共享镜像的任务。

```bash
set -euo pipefail
export R=/data/cubelet/c100n100-perf-tuning-90/20261016T104049Z
export CAPTURE_CONFIG="$R/capture100.agentwarn.json"
export CHECK_DIR="$R/restore-check-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -m 0700 "$CHECK_DIR"
printf '保存此目录，失败后回退需要它：%s\n' "$CHECK_DIR"
test "$(uname -m)" = aarch64
test "$(getconf PAGESIZE)" = 4096
uname -r | tee "$CHECK_DIR/kernel.txt"
python3 "$R/scripts/state_snapshot.py" "$CHECK_DIR/before.json"

# 只读门禁函数：执行缓存处理前还会再调用一次。
check_idle() {
python3 - <<'PY'
import hashlib, json, os, sys
from pathlib import Path
root = Path(os.environ['R'])
sys.path.insert(0, str(root / 'scripts'))
from run_round_w3 import API, inventory
config = json.loads(Path(os.environ['CAPTURE_CONFIG']).read_text())
assert config['template_id'] == 'tpl-381852bfe518c30bb815e163'
assert config['warmup'] == 0 and config['cubemastercli']['exclusive_template'] is True
expected = '67d8d06a6f264023df91d2f928f4205fcc33f3e02b8f2d0fe03a4d953614cbad'
for name in ['/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs',
             '/data/cubelet/root/component_versions/cube-shim/v0.7.1/bin/containerd-shim-cube-rs']:
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected, name
assert not inventory(API(config)), 'sandbox inventory is not empty'
busy = []
for exe in Path('/proc').glob('[0-9]*/exe'):
    try:
        name = os.readlink(exe).removesuffix(' (deleted)').rsplit('/', 1)[-1]
    except FileNotFoundError:
        continue
    if name in ('containerd-shim-cube-rs', 'cube-runtime', 'cube-bench'):
        busy.append((exe.parent.name, name))
assert not busy, busy
print('idle gate passed; Shim-C hashes and capture configuration match')
PY
}
check_idle
```

核对 `before.json` 中的 CPU/NUMA、两份配置哈希和 Go 环境，与 [s13-state.json](reference/s13-state.json) 对照。快照不记录 RCU 和开关，下面单独保存。`tap_count=0` 是旧快照脚本按 `z` 前缀计数的限制；实际 TAP 请用第 ① 节命令核对。

#### B. 恢复运行时参数

```bash
# 记录原值，供回退；这些文件不含凭据。
cat /sys/kernel/rcu_expedited > "$CHECK_DIR/rcu_expedited.before"
cat /sys/kernel/rcu_normal > "$CHECK_DIR/rcu_normal.before"
cat /proc/sys/kernel/numa_balancing > "$CHECK_DIR/numa_balancing.before"
for key in enabled defrag; do
  sed -n 's/.*\[\([^]]*\)\].*/\1/p' "/sys/kernel/mm/transparent_hugepage/$key" > "$CHECK_DIR/thp-$key.before"
done
for flag in snap_madv_random snap_populate_read; do
  if test -e "/run/cube-perf/$flag"; then echo present; else echo absent; fi > "$CHECK_DIR/$flag.before"
done

mkdir -p /run/cube-perf
rm -f /run/cube-perf/snap_populate_read
touch /run/cube-perf/snap_madv_random
echo 0 > /sys/kernel/rcu_normal
echo 1 > /sys/kernel/rcu_expedited
echo 0 > /proc/sys/kernel/numa_balancing
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag

test "$(cat /sys/kernel/rcu_expedited)" = 1
test "$(cat /sys/kernel/rcu_normal)" = 0
test "$(cat /proc/sys/kernel/numa_balancing)" = 0
grep -F '[never]' /sys/kernel/mm/transparent_hugepage/{enabled,defrag}
test -e /run/cube-perf/snap_madv_random
test ! -e /run/cube-perf/snap_populate_read
```

`MADV_RANDOM` 是映射级 advice，与 THP 设置里的 `madvise` 不同。s13 的 THP 两项都是 never。开关只在新建映射时读取，添加或删除文件都不会追溯改变已有 VM 的映射。

#### C. 定向逐出已有大 folio 页缓存

以下四个文件是 .90 的目标模板实际使用的 rootfs、agent、guest image、快照内存文件，2026-10-17 已只读核实路径存在。原实验还逐出了旧模板的内存文件；只测新模板时不需要处理旧模板。换模板或镜像后，应通过 c1 的 `/proc/<VMM PID>/maps` 重新确认路径，清理 c1 后再执行。

```bash
SHARED_FILES=(
  /usr/local/services/cubetoolbox/cubebox_os_image/rfs-dd2b6baa7183b8077c714eb9-e5190241/rfs-dd2b6baa7183b8077c714eb9-e5190241.ext4
  /data/cubelet/root/component_versions/cube-agent/v0.7.1/cube-agent.ext4
  /data/cubelet/root/component_versions/cube-image/guest-image-260820-1/cube-guest-image-cpu.img
  /data/cubelet/storage/xfs/objects/volumes/tpl-tpl-381852bfe518c30bb815e163-memory/tpl-tpl-381852bfe518c30bb815e163-memory
)
for file in "${SHARED_FILES[@]}"; do test -f "$file"; done
check_idle
python3 "$R/scripts/pagecache_nodes.py" --evict "${SHARED_FILES[@]}" | tee "$CHECK_DIR/evict.jsonl"
python3 - <<'PY'
import json, os
from pathlib import Path
rows = [json.loads(s) for s in (Path(os.environ['CHECK_DIR']) / 'evict.jsonl').read_text().splitlines()]
assert len(rows) == 4
assert all(r.get('after_evict') == 0 for r in rows), 'cache remains resident; investigate before benchmarking'
print('all four files have zero resident pages after eviction')
PY
```

脚本使用 `POSIX_FADV_DONTNEED` 请求丢弃这些文件的干净页缓存，不删除文件、不改变文件内容，也不做全机 `drop_caches`。返回成功不保证全部缓存被逐出，因此必须检查 `after_evict=0`。若仍有驻留页，先检查是否有其他进程映射/读取这些文件、模板构建尚未结束或数据尚未写回，解决后重试；不要绕过检查。

此后不要对这些文件做 `cat`、`cp`、全文件哈希、手工顺序预热，也不要执行 `warm_hugefolio.py`。让 VM 在 B2 开启时自然填充缓存。逐出仅在本次测试序列前做一次，不要在每轮之间逐出，否则测量条件不同于原来的热缓存正式轮次。

#### D. 验证优化生效并重新测量

```bash
python3 "$R/scripts/state_snapshot.py" "$CHECK_DIR/after.json"
STATE="restore-s13-$(date -u +%Y%m%dT%H%M%SZ)"
python3 "$R/scripts/run_series.py" "$R" "$STATE-pilot" 1

# 只检查本次试跑产生的 VMM 日志，避免误读历史成功日志。
grep -hE 'snapshot memory: MADV_RANDOM applied|pmem: MADV_RANDOM applied|MADV_RANDOM failed' \
  "$R/$STATE-pilot"/round-01/runs/*/capture/evidence/vmm-delta.log \
  > "$CHECK_DIR/madv-random.log"
grep -q 'snapshot memory: MADV_RANDOM applied' "$CHECK_DIR/madv-random.log"
grep -q 'pmem: MADV_RANDOM applied' "$CHECK_DIR/madv-random.log"
if grep -q 'MADV_RANDOM failed' "$CHECK_DIR/madv-random.log"; then
  echo 'MADV_RANDOM failed; stop and inspect the log' >&2
  exit 1
fi

# VM 自然填充并完成清理后检查；冷缓存的 null/0 不是成功证据。
python3 "$R/scripts/folio_orders.py" "${SHARED_FILES[@]}" | tee "$CHECK_DIR/folios.jsonl"
python3 - <<'PY'
import json, os
from pathlib import Path
rows = [json.loads(s) for s in (Path(os.environ['CHECK_DIR']) / 'folios.jsonl').read_text().splitlines()]
assert len(rows) == 4
assert all(r['mapped_pages'] > 0 and set(r['pages_by_folio_kib']) == {'4'} for r in rows), 'not all resident pages are order-0'
print('folio diagnostic reports only 4KiB pages for all four files; corroborate with VMM logs')
PY

python3 "$R/scripts/run_series.py" "$R" "$STATE" 5
cat "$R/$STATE/progress.log"
```

验收：本轮日志同时包含 snapshot memory 和 pmem 的 `MADV_RANDOM applied`，没有失败；四个文件的 folio 脚本观测结果仅含 4KiB，作为辅助证据；正式 5 轮每轮 `ok=100`、`errors=0`、`cleanup=complete`、`deleted=103`。以 `total_ms` 的 5 轮中位数比较 s13 的 153.7ms，不把历史数值当作保证。更多采集和清理方法见 [测试指南](TESTING-GUIDE.zh-CN.md)。

`folio_orders.py` 是辅助诊断：需在宿主机 root 环境读取真实 PFN（不能使用屏蔽 PFN 的受限容器）。它通过 pagemap/kpageflags 和已观测的连续 compound 页段估算 folio 大小，未对 PFN 权限受限或部分驻留的 compound 页做完整错误检测。因此 `100%` 不能单独作为严格证明，应结合本次映射日志、冷缓存准备和性能结果判断。若某文件 `mapped_pages=0`，本次运行没有提供足够观测，应核对映射路径和实际访问情况，不要手工读文件来让检查通过。

#### E. 可选持久化与回退

已有 [files/cube-perf-tmpfiles.conf](files/cube-perf-tmpfiles.conf) 样例，只负责开机创建 B2 开关和设置 `rcu_expedited=1`。把它复制到 `/etc/tmpfiles.d/cube-perf.conf` 后，可用 `systemd-tmpfiles --create /etc/tmpfiles.d/cube-perf.conf` 应用。安装前备份同名文件，避免覆盖其他配置。

**该样例未在 .90 上完成重启验证，也不恢复 THP、NUMA、rcu_normal、B1 开关或页缓存状态。** 若要持久化全部设置，应在本机已有 tuned/systemd 配置中统一管理，并确保在接受沙箱创建请求前完成；不要依赖互相覆盖的多份配置。重启后再次核对本节目标表。缓存逐出不作为开机盲目执行的任务，仍需确认无沙箱及无其他读者；它不是一个可以持久化的缓存属性。

回退本节 B 的修改时，先恢复零库存、无 Shim，使用保存的 `CHECK_DIR`。命令失败可能因 `set -e` 退出 Bash；若已进入新会话，先执行以下初始化，再从 A 复制执行 `check_idle() { ... }` 的函数定义。**不要重跑 A 的目录创建或 B 的原值保存部分**，否则会丢失回退依据。

```bash
set -euo pipefail
export R=/data/cubelet/c100n100-perf-tuning-90/20261016T104049Z
export CAPTURE_CONFIG="$R/capture100.agentwarn.json"
# 替换成 A 中打印的原目录，不要新建目录。
export CHECK_DIR="$R/restore-check-<原时间戳>"
```

确认函数已定义、原值文件齐全后执行：

```bash
for key in rcu_expedited rcu_normal numa_balancing thp-enabled thp-defrag snap_madv_random snap_populate_read; do
  test -s "${CHECK_DIR:?需要设置原检查目录}/$key.before"
done
check_idle
cat "$CHECK_DIR/rcu_expedited.before" > /sys/kernel/rcu_expedited
cat "$CHECK_DIR/rcu_normal.before" > /sys/kernel/rcu_normal
cat "$CHECK_DIR/numa_balancing.before" > /proc/sys/kernel/numa_balancing
for key in enabled defrag; do
  cat "$CHECK_DIR/thp-$key.before" > "/sys/kernel/mm/transparent_hugepage/$key"
done
for flag in snap_madv_random snap_populate_read; do
  if test "$(cat "$CHECK_DIR/$flag.before")" = present; then
    mkdir -p /run/cube-perf
    touch "/run/cube-perf/$flag"
  else
    rm -f "/run/cube-perf/$flag"
  fi
done
```

若另外安装了持久化文件，还需恢复其备份或移除本次新增文件。已逐出的缓存无法按原驻留状态回滚，后续会自然重新填充；关闭 B2 也不会立即将已有 4K folio 合并成大 folio。

## 6. 其他机器上的适用性

| 手段 | 适用条件 | 预期 |
|---|---|---|
| ① | 历史上积累了大量 TAP，或 `tap_init_num` 设得很大 | Cubelet fd 越多收益越大；fd 本来就只有几千时收益很小 |
| ② | 多 NUMA 节点，且 Cubelet 原本被绑得过窄或跨 socket | 单 socket 的机器不适用；要按本机拓扑选范围 |
| ③ | 任何机器 | VM 退出成本越高（并发越高、核越多）收益越大 |
| ④ | CPU 核数多，且 `synchronize_rcu` 慢（HZ 低、PREEMPT_NONE） | 依赖 ③；核数少的机器可能没有收益 |
| ⑤ | 内核页缓存使用大 folio，并且多个 VM 共享同一份快照或镜像 | 并发越高收益越大 |

---

**本目录文件**：
- `patches/`：补丁 A、ABC 合并补丁，以及 SHA256SUMS。
- `files/zzz-perf-tuning-numa.conf`：② 的 systemd drop-in 样例（值为 .90 的拓扑）。
- `files/cube-perf-tmpfiles.conf`：④⑤ 的持久化样例（未验证）。
- `make_template_request.py`：生成 ③ 的模板请求。在 .90 上已验证，生成的请求与构建 tpl-381852bf 时用的完全一致（ID 除外）。
- `pagecache_nodes.py`：查看或逐出共享文件的页缓存。
- `folio_orders.py`：检查共享文件页缓存的 folio 大小（⑤ 生效后应为 100% 4K）；`--experiment <XFS 目录>` 可在新机器上先验证内核是否会生成大 folio，判断 ⑤ 是否适用。
- 构建好的二进制：`../shim-builds/{A,C}/bin/`。
