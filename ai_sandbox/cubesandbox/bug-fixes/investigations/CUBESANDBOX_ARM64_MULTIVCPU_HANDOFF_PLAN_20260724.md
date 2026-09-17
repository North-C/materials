# CubeSandbox ARM64 多 vCPU Template 故障交接与后续执行计划

> 交接日期：2026-07-24
>
> 主测试节点：`root@192.168.25.90`
>
> 对照节点：`root@192.168.25.65`
>
> 社区源码基线：CubeSandbox v0.5.1，commit `a164417f497234a0d787cb328b0ae96480b1569b`

## 1. 文档用途

本文供下一位执行者直接接手。它记录当前结论、远端状态、实验资产、操作门禁、下一轮矩阵和结果决策树。

原始报告和证据不在本文重复展开。若本文与 2026-07-22 以前的机制判断冲突，以本文及综合复盘的最新证据边界为准。

## 2. 当前结论

故障可在纯社区 v0.5.1 全栈、stock 宿主内核和全新 2 vCPU Template 上复现。它不是仅由 v0.3/v0.5 guest cmdline 差异造成。

2 vCPU 是高概率故障组，3/4 vCPU 是稳定 control。两套 20 次协议均得到 2 vCPU 大量失败、3/4 vCPU `20/20`。

主要失败链为 `reset guest time` ttrpc timeout，随后出现 guest RCU stall、RCU starvation 和 timer handling issue。失败后常遗留高 CPU Shim。

高置信度故障点位于 ARM64 多 vCPU restore 后、guest 首次有效运行边界。精确责任仍可能在 VMM、KVM timer/vGIC 激活、guest timer/RCU 或它们的交互。

增加日志能显著改变结果，说明存在明显观察效应。现有证据支持“时序敏感”，但不能直接证明 Rust 用户态存在 ARM64 弱内存序错误。

pause/resume 路径已有 `SeqCst`、mutex、signal 和 KVM ioctl 边界。logger 还能引入锁、调度、I/O、代码布局和 cache 效应，因此“加日志成功”不是内存屏障修复证明。

## 3. 已关闭或降级的假设

| 假设 | 当前判断 | 直接依据 |
|---|---|---|
| v0.3 ARM64 cmdline 保护缺失 | 非充分根因 | 对齐后仍同型失败 |
| 单纯缺少 memory volume flush | 非充分根因 | sync、reopen、readback 后仍失败 |
| KVM timer GET 具有必要状态物化作用 | 不成立 | GET-only 为 `1/20` |
| `set_state` 后增加固定 8 us 即可修复 | 不成立 | delay-only 为 `1/20` |
| irqbypass custom kernel 决定有无故障 | 不成立 | stock 内核和社区栈仍复现 |
| 单个负 timer deadline 或 `CTL=1` | 非充分判据 | 成功 3/4 vCPU Template 也存在 |
| 普通 API、网络或删除逻辑是首因 | 低优先级 | guest timer/RCU 先失去进展 |

dirty bitmap 是否遗漏 restore 必需页尚未被全量关闭。现有 C1 只验证写入区间抽样页，未扫描 bitmap omitted pages。

## 4. 社区全栈与 2/3/4 vCPU 基线

社区版测试部署了 11 个从同一 v0.5.1 commit 构建的组件。guest kernel、rootfs、envd、Cloud Hypervisor、MySQL 和 Redis 是外部依赖，不能写成“本轮社区源码构建”。

| 协议 | 2 vCPU | 3 vCPU | 4 vCPU |
|---|---:|---:|---:|
| 每次尝试后隔离清理 | 3/20 | 20/20 | 20/20 |
| 连续 20 次、组末清理 | 2/20 | 20/20 | 20/20 |

每个 CPU 组均新建 Template。旧 baseline 仅提供请求结构，没有复用其 snapshot。

社区来源和组件边界见 [component-provenance.json](remote-results/community-stack-vcpu-matrix-20260723-161000/evidence/component-provenance.json)。

## 5. v16 拆分实验结果

本轮先用纯社区 Shim 新建一个 2 vCPU Template，再让全部恢复侧变体使用同一新 Template。每组 20 次完整生命周期，组末统一清理。

该设计隔离恢复侧变量。Template `tpl-cb9152bb76f54e35a754b7dc` 是本轮新建产物，不是 baseline；截至交接时仍为 `READY`，但下一轮不得继续使用。

| 组 | 单一变量 | 完整生命周期 | 组末清理后 |
|---|---|---:|---:|
| V0 community | 无插桩 | 1/20 | 0/0/0 |
| V1 log-only | v15 restore/resume 日志 | 20/20 | 0/0/0 |
| V2 GET-only | 3 个 KVM timer GET | 1/20 | 0/0/0 |
| V3 delay-only | `set_state` 后 busy-spin 8 us | 1/20 | 0/0/0 |
| V4 full-v16 | V1 日志加 timer GET/readback | 19/20 | 0/0/0 |

V0、V2、V3 各有 19 次 `reset guest time` ttrpc timeout。V1 没有目标错误；V4 仍有 1 次同型失败。

因此，V1 的日志扰动比 timer GET 或固定延迟更关键。V4 不是确定性修复，V2 已排除“GET readback 本身足够修复”。

完整结构化结果见 [matrix-summary.json](remote-results/arm64-v16-decomposition-v24-20260723-222458/matrix-summary.json)。

## 6. 宿主 GIC、ITS 与平台差异

两台机器当前均运行同一 stock 内核 `6.6.0-132.0.0.111.oe2403sp3.aarch64`，均使用 GICv3 基础接口，并启用 GICv4/GICv4.1 ITS 虚拟化支持。

| 项目 | `.65` | `.90` |
|---|---|---|
| GIC | GICv3 | GICv3 |
| GICv4 | GICv4.1，RVPEID Valid+Dirty | GICv4，DirectLPI Valid+Dirty |
| ITS mode | GICv4.1 mode | 未打印同型 mode 行 |
| ITS Virtual CPUs | 65536 | 32768 |
| vCPU table page size | 16K | 4K |
| table pages 缩减 | 无 | 每个 ITS `512 -> 256` |
| ITS 数量 | 8 | 8 |

`.90` 的缩减是 ITS vCPU table 在 4K page 条件下无法按初始规模分配后的容量回退。它影响宿主 ITS/VPE 容量，不等同于 guest snapshot 文件页大小。

该差异可能调制 KVM vITS 分配、恢复或首次注入时序，因此保留为跨宿主 P1。但 2 至 4 vCPU 远低于 32768，且 `.90` 的上游 Cloud Hypervisor 对照曾 `100/100`。

所以 ITS 缩减目前不是充分根因。要确认因果，必须在相同 v0.5 组件、相同新 Template 协议下做跨宿主或固件/页表条件 A/B。

`.90` 曾发生 mlx5 高温和 GHES PCIe root-port fatal error。当前 boot 日志干净，但高压测试前必须重新检查硬件告警。

## 7. 交接时远端状态

2026-07-24 复核结果：

```text
node=192.168.25.90
kernel=6.6.0-132.0.0.111.oe2403sp3.aarch64
required_services=6/6 active
api={"status":"ok","sandboxes":0}
shim/vmm=0/0
live_shim_sha256=4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d
```

正确 unit 是 `cube-sandbox-cube-lifecycle-manager`。不要误写为不存在的 `cube-sandbox-lifecycle-manager`。

systemd postcheck 使用 `http://127.0.0.1:3000/health`。矩阵脚本的细粒度门禁使用 `/cubeapi/v1/health` 和 `/sandboxes`。

当前运行的是纯社区 Shim。V25 变体只完成构建准备，未部署，不存在未恢复的实验二进制。

## 8. V25 实验资产状态

| 变体 | 本地 worktree | 远端 worktree | 状态 |
|---|---|---|---|
| state-log-only | `source_code/CubeSandbox-v0.5.1-arm64-state-log-only-v25` | `/home/lyq/CubeSandbox-v0.5.1-arm64-state-log-only-v25` | 已格式化、编译、未部署 |
| resume-log-only | `source_code/CubeSandbox-v0.5.1-arm64-resume-log-only-v25` | `/home/lyq/CubeSandbox-v0.5.1-arm64-resume-log-only-v25` | 已格式化、未重新编译 |

`state-log-only` 只在每个 vCPU `set_state` 前记录保存的 timer/core 状态。其 ARM64 二进制 SHA256 为：

```text
09a47cd66c61f4ee18491397a280961a54636580f53c0136dfc4608ff628ee5a
```

`resume-log-only` 只在 `CpuManager::resume` 前后各记录一行。远端现有 target 二进制是硬链接缓存中的 V3 陈旧产物，SHA256 为 `5822c6fe6d8b562655e2bcbcaa6f43daf60a43e5faa18ca5e49ccadf38cdaff0`。

禁止部署该陈旧文件。必须重新编译，并确认新哈希不等于 V3 和 community 后，才能进入矩阵。

源码补丁和已构建 V5 二进制位于 [evidence](remote-results/arm64-v16-decomposition-v24-20260723-222458/evidence)。

## 9. 测试不变量

后续所有矩阵必须遵守以下规则，否则结果不纳入主结论。

1. 开始前六个服务必须 active，API 健康，sandbox/shim/task 必须为 `0/0/0`。
2. 每轮先在纯社区 Shim 下新建 Template，不能沿用历史 baseline 或 `tpl-cb9152...`。
3. baseline Template 只能提供 `create_request`，不能作为实际 restore 对象。
4. 单变量拆分使用同一轮新 Template，避免 Template 个体差异污染恢复侧对照。
5. 每组 20 次 create、guest `nproc`/health、delete；只在组末清理。
6. 每次切换 Shim 前确认 sandbox/shim/task 为 `0/0/0`，记录 live SHA256。
7. 每组保留请求、Template JSON、snapshot JSON、日志 delta、逐次结果和清理前后状态。
8. 测试顺序随机化或至少交错，不要总让候选变体固定在热缓存后的最后一组。
9. 失败后先保存日志，再清理残留 Shim；不能先重启服务再取证。
10. 最后必须恢复纯社区 Shim，并再次通过六服务和 `0/0/0` 门禁。

## 10. P0：立即执行的 V25 两点拆分

目标是区分 V1 成功来自“逐 vCPU `set_state` 前日志”还是“resume 释放前后日志”。本阶段只做 2 vCPU，每组 20 次。

### 10.1 预检

在 `.90` 执行：

```bash
systemctl is-active \
  cube-sandbox-network-agent \
  cube-sandbox-cubemaster \
  cube-sandbox-cubelet \
  cube-sandbox-cube-api \
  cube-sandbox-cube-lifecycle-manager \
  cube-sandbox-cube-proxy

curl -fsS http://127.0.0.1:3000/health
curl -fsS -H 'Authorization: Bearer e2b_000000' \
  http://127.0.0.1:3000/sandboxes | jq length

pgrep -fc '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' || true
find /data/cubelet/root/io.containerd.runtime.v2.task \
  -mindepth 2 -maxdepth 2 -type d | wc -l

sha256sum /usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
uname -r
journalctl -k -b --no-pager | \
  grep -Ei 'GHES|hardware error|temperature|overheat|RCU stall|lockup|KVM.*error' | tail -100
```

任何服务非 active、API 非健康或计数非零时，先恢复环境，不得开始新组。

### 10.2 重新编译 resume-log-only

在 `.90` 执行：

```bash
V25_RESUME=/home/lyq/CubeSandbox-v0.5.1-arm64-resume-log-only-v25

git -C "$V25_RESUME" diff --check
cargo fmt --manifest-path "$V25_RESUME/CubeShim/Cargo.toml" --all -- --check

make -C "$V25_RESUME" builder-run \
  BUILDER_IMAGE=ghcr.io/tencentcloud/cubesandbox-builder:ubuntu2004-arm64 \
  BUILDER_CMD='mkdir -p /workspace/_output/bin && cd /workspace/CubeShim && cargo build --release --locked --offline && install -m 0755 target/release/containerd-shim-cube-rs /workspace/_output/bin/containerd-shim-cube-rs'

file "$V25_RESUME/_output/bin/containerd-shim-cube-rs"
sha256sum "$V25_RESUME/_output/bin/containerd-shim-cube-rs"
```

产物必须是 ARM aarch64 ELF。哈希不能是 community `4702fde...15d`，也不能是 V3 `5822c6fe...ff0`。

### 10.3 新建本轮 Template 并跑 community 基线

先确认 live Shim 是 community。然后运行 V0，不设置 `EXISTING_TEMPLATE_ID`，由脚本新建 2 vCPU Template。

```bash
RESULT_ROOT=/home/lyq/arm64-v25-log-split-$(date +%Y%m%d-%H%M%S)
BASE_REQUEST_TEMPLATE=tpl-52c8fddf838e4c10b19f3061
TIMELINE_ROOT=/home/lyq/cube-arm64-timeline-trace-v23-20260723

mkdir -p "$RESULT_ROOT/groups/v0-community"

env \
  WORKDIR="$RESULT_ROOT/groups/v0-community" \
  BASE_TEMPLATE_ID="$BASE_REQUEST_TEMPLATE" \
  RUNNER="$TIMELINE_ROOT/tools/cube_template_create_rate.py" \
  HELPERS="$TIMELINE_ROOT/tools/run_arm64_vcpu_template_matrix.sh" \
  COLLECTOR="$TIMELINE_ROOT/tools/collect_arm64_vcpu_timeline.sh" \
  ATTEMPTS=20 START_CPU=2 END_CPU=2 \
  KERNEL_TRACE_ATTEMPTS=0 ENABLE_VMM_TRACE=0 \
  bash "$TIMELINE_ROOT/tools/run_arm64_vcpu_timeline_matrix.sh"

CURRENT_TEMPLATE=$(cat "$RESULT_ROOT/groups/v0-community/cpu2/template-id.txt")
printf '%s\n' "$CURRENT_TEMPLATE"
```

`BASE_REQUEST_TEMPLATE` 只用于抽取请求。若该 ID 不再 `READY`，选择任意配置兼容的 READY Template，但仍必须由脚本生成新的 `CURRENT_TEMPLATE`。

V0 建议首先执行，因为它同时验证本轮新 Template 是否能复现问题。若 V0 为 `20/20`，换一个全新 Template 重做，不要直接用偶然 good Template 判断 V5/V6。

高失败组可能留下 19 个 Shim。脚本会在组末恢复，但 Cubelet 的 systemd retry 可能晚于 runner deadline，使 runner 返回 `2`。

此时先等服务恢复并核对 `0/0/0`，保存现有结果，不要直接重复该组。

### 10.4 安全切换 Shim

每次切换前先通过 `0/0/0` 门禁。将 community 备份和每个候选二进制复制到本轮 `binaries` 目录，并记录哈希。

```bash
RESULT_BIN="$RESULT_ROOT/binaries"
LIVE_SHIM=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
COMMUNITY_SHIM=/home/lyq/arm64-v16-decomposition-v24-20260723-222458/binaries/containerd-shim-cube-rs.v0-community
STATE_SHIM=/home/lyq/CubeSandbox-v0.5.1-arm64-state-log-only-v25/_output/bin/containerd-shim-cube-rs
RESUME_SHIM=/home/lyq/CubeSandbox-v0.5.1-arm64-resume-log-only-v25/_output/bin/containerd-shim-cube-rs

mkdir -p "$RESULT_BIN"
install -m 0755 "$LIVE_SHIM" "$RESULT_BIN/live-before"
install -m 0755 "$COMMUNITY_SHIM" "$RESULT_BIN/v0-community"
install -m 0755 "$STATE_SHIM" "$RESULT_BIN/v5-state-log-only"
install -m 0755 "$RESUME_SHIM" "$RESULT_BIN/v6-resume-log-only"
sha256sum "$RESULT_BIN"/* | tee "$RESULT_BIN/SHA256SUMS"
```

切换单个候选时：

```bash
CANDIDATE_SHIM="$RESULT_BIN/v5-state-log-only"  # V6 时替换为 v6 文件

systemctl stop cube-sandbox-cubelet
install -m 0755 "$CANDIDATE_SHIM" "$LIVE_SHIM"
sync
systemctl start cube-sandbox-cubelet

systemctl is-active cube-sandbox-cubelet
curl -fsS http://127.0.0.1:3000/cubeapi/v1/health
sha256sum "$LIVE_SHIM" "$CANDIDATE_SHIM"
```

两个 SHA256 必须相同。若 Cubelet 未恢复，不得运行矩阵；先查看 `journalctl -u cube-sandbox-cubelet -n 200`。

### 10.5 执行 V5 和 V6

V5、V6 都使用 V0 刚创建的 `CURRENT_TEMPLATE`。每组结束后脚本执行统一清理。

```bash
run_split_group()
{
  GROUP_NAME=$1
  GROUP_DIR="$RESULT_ROOT/groups/$GROUP_NAME"
  mkdir -p "$GROUP_DIR"

  env \
    WORKDIR="$GROUP_DIR" \
    BASE_TEMPLATE_ID="$BASE_REQUEST_TEMPLATE" \
    RUNNER="$TIMELINE_ROOT/tools/cube_template_create_rate.py" \
    HELPERS="$TIMELINE_ROOT/tools/run_arm64_vcpu_template_matrix.sh" \
    COLLECTOR="$TIMELINE_ROOT/tools/collect_arm64_vcpu_timeline.sh" \
    ATTEMPTS=20 START_CPU=2 END_CPU=2 \
    KERNEL_TRACE_ATTEMPTS=0 ENABLE_VMM_TRACE=0 \
    EXISTING_TEMPLATE_ID="$CURRENT_TEMPLATE" \
    bash "$TIMELINE_ROOT/tools/run_arm64_vcpu_timeline_matrix.sh"
}

run_split_group v5-state-log-only
# 切换到 V6 并再次通过门禁后执行：
run_split_group v6-resume-log-only
```

V5 有效样本应在日志中看到 40 条 `event=vcpu_restore_saved_state`。V6 应看到 20 条 begin 和 20 条 complete。

若日志数量不符，该组插桩未按预期命中，结果无效。先检查 log level 和日志提取起止行，不要继续解释通过率。

### 10.6 结果分支

| V5 state-only | V6 resume-only | 判断 | 下一变体 |
|---:|---:|---|---|
| 接近 20/20 | 接近 V0 | 关键扰动在逐 vCPU `set_state` 前 | 分离“寄存器扫描/格式化”与“logger 输出” |
| 接近 V0 | 接近 20/20 | 关键扰动在 resume 释放边界 | 对比无日志 `yield`、短自旋、fence 和串行 unpark |
| 都接近 20/20 | 都能关闭窗口 | 多个 restore 边界扰动均可抑制 | 做 no-output、logger-lock、yield 三分法 |
| 都接近 V0 | V1 需要组合扰动 | 单点不足 | 增加 restore begin/complete-only，再做组合最小化 |

“接近”不能只凭单次成功判断。先比较 20 次失败率和目标日志签名；候选有效后再扩大样本。

只有边界被定位后，才做 ARM64 memory-order 变体。建议顺序为 no-op/`black_box`、`yield_now`、短延迟、编译器 fence、Release/Acquire、SeqCst fence。

若只有 fence 稳定生效，而等时长 `yield`/delay 和 logger-lock 不生效，才有理由把弱内存序提升为高优先级。

## 11. P1：候选稳定后的 2/3/4 vCPU 矩阵

找到最小候选后，恢复 community，新建 2/3/4 vCPU Template。每个 CPU 组 20 次，不能复用 V25 诊断 Template。

使用 `run_arm64_vcpu_timeline_matrix.sh`，设置 `START_CPU=2`、`END_CPU=4`，不要设置 `EXISTING_TEMPLATE_ID`。

对每个 CPU 组分别记录 Template ID、snapshot JSON、20 次完整生命周期、日志签名和清理前后计数。

若候选使 2 vCPU 通过但令 3/4 vCPU 出现新失败，候选不能进入长压；先检查是否改变 vCPU release 顺序或引入全局 logger/锁竞争。

## 12. P1/P2 后续根因实验

| 优先级 | 实验 | 目的 |
|---|---|---|
| P1 | true Full 与 dirty-on-empty 使用同一 paused state | 关闭 dirty bitmap omitted-page 分支 |
| P1 | 低扰动 first-entry timer/vGIC/INTID 采集 | 找到 good/bad 首次分叉 |
| P1 | `.90` 与无 GHES 历史同型号节点 A/B | 隔离平台固件和硬件风险 |
| P1 | `.65`/`.90` ITS table 条件对照 | 检查 65536/32768 与 page-size 差异是否调制故障 |
| P1 | vCPU affinity/NUMA 固定与随机 A/B | 验证迁移和 NUMA 落点影响 |
| P2 | envd `set_guest_date_time` 到达/返回 trace | 区分 agent 未调度与请求链故障 |
| P2 | Template publish 全量逻辑 hash | 排除 cubecow 对象发布遗漏 |

ITS 对照必须记录宿主启动日志、KVM/vGIC 配置、Template `state.json`、guest RAM 中 ITS tables 和首次 IRQ 注入。仅比较 dmesg 数字不能证明快照因果。

## 13. 长压与修复验收

20 次矩阵只用于筛选，不足以证明修复。

候选修复必须同时满足：

1. 全新 2 vCPU Template 串行完整生命周期至少 `100/100`。
2. 四档压力合计 `1020/1020`，并保留每档并发参数。
3. 3/4 vCPU 各至少 100 次，无新增回归。
4. guest health、`nproc` 和 delete 均成功，不能只统计 create 返回。
5. 无 RCU stall、timer handling issue、ttrpc timeout 和残留 Shim。
6. good/bad Template 与 community/candidate 顺序随机化或交错。
7. 二进制、commit、内核、镜像 digest、Template 和请求全部留证。
8. 扩展到 2/4/8 GiB，再覆盖 pause/resume/commit。

任何单批 `100/100` 都只能说明该批未命中。必须结合 community 同期坏对照和错误签名判断。

## 14. 最终恢复

无论实验成功或失败，最后都恢复纯社区 Shim。

```bash
LIVE_SHIM=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
COMMUNITY_SHIM=/home/lyq/arm64-v16-decomposition-v24-20260723-222458/binaries/containerd-shim-cube-rs.v0-community

systemctl stop cube-sandbox-cubelet
install -m 0755 "$COMMUNITY_SHIM" "$LIVE_SHIM"
sync
systemctl start cube-sandbox-cubelet

sha256sum "$LIVE_SHIM"
systemctl is-active \
  cube-sandbox-network-agent \
  cube-sandbox-cubemaster \
  cube-sandbox-cubelet \
  cube-sandbox-cube-api \
  cube-sandbox-cube-lifecycle-manager \
  cube-sandbox-cube-proxy
curl -fsS http://127.0.0.1:3000/health
curl -fsS -H 'Authorization: Bearer e2b_000000' \
  http://127.0.0.1:3000/sandboxes | jq length
```

最终 Shim SHA256 必须为 `4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d`。

还必须确认 shim/task 为 `0/0`，没有 trace flag 或私有 tracefs instance 遗留，并记录六个 unit 的最终状态。

不要删除诊断 Template、memory volume 或结果目录，除非已完成本地同步、SHA256 校验，并得到明确清理授权。

## 15. 结果归档要求

每轮远端结果目录至少包含：

- `context.txt`：时间、节点、内核、commit、执行顺序。
- `binaries/SHA256SUMS`：community 和全部候选。
- `groups/*/case-summary.json`：20 次通过率和清理计数。
- `groups/*/results.jsonl`：逐次完整生命周期。
- `groups/*/cube-shim.log`、`vmm.log`、`cubelet.log`。
- Template request/info 和 snapshot `config/state/catalog/metadata`。
- 最终服务、API、sandbox/shim/task、live SHA256。
- 源码补丁和 `git status --short`。

同步到本地 `remote-results/` 后生成全目录 SHA256，并执行校验。2 GiB payload 可只保留远端路径、stat、allocated blocks 和完整 SHA256。

## 16. 主要证据入口

- [综合根因复盘](CUBESANDBOX_ARM64_MULTIVCPU_ROOT_CAUSE_REASSESSMENT_20260722.md)
- [2/3/4 vCPU 新模板矩阵](CUBESANDBOX_ARM64_VCPU_COUNT_TEMPLATE_MATRIX_REPORT_20260723.md)
- [v0.3/v0.5 源码差异](CUBESANDBOX_ARM64_V030_V050_TEMPLATE_SOURCE_DIFF_ANALYSIS_20260722.md)
- [社区全栈矩阵结果](remote-results/community-stack-vcpu-matrix-20260723-161000)
- [v16 拆分矩阵结果](remote-results/arm64-v16-decomposition-v24-20260723-222458)
- [宿主条件对比](remote-results/cmdline-rerun-ab-20260723-103303/host-condition-review-20260723.md)
- [Cloud Hypervisor 原生正向对照](CLOUD_HYPERVISOR_ARM64_NATIVE_SNAPSHOT_RESTORE_CONTROL_20260722.md)
- [统一时间线脚本](scripts/run_arm64_vcpu_timeline_matrix.sh)
- [逐次生命周期 runner](scripts/cube_template_create_rate.py)

## 17. 交接完成条件

接手人开始操作前，应能回答以下问题：

1. 当前 live Shim 是否为 community，SHA256 是否正确？
2. 六服务、API、sandbox/shim/task 是否通过门禁？
3. 本轮 Template 是否新建，而不是 baseline 或历史诊断 Template？
4. 当前只改变了哪一个变量，插桩是否实际命中？
5. 失败日志是否在清理前保存？
6. 结束后是否恢复 community 并完成本地归档校验？

任一答案不明确时，先补证据，不进入下一组。
