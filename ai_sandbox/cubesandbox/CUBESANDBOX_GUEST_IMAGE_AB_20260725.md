# CubeSandbox guest 镜像 A/B 测试报告

> 后续修正（2026-07-27）：历史镜像在串行 20 次测试中未命中故障，但在并发 10 的创建压力测试中累计出现 3/700 次 `reset guest time failed`。因此，历史镜像没有消除问题；本报告的原始结果只能说明镜像会显著影响故障窗口，不能证明镜像替换已经解决问题。详见 [历史镜像创建压力复测](CUBESANDBOX_HISTORICAL_IMAGE_PRESSURE_20260727.md)。

日期：2026-07-25（Asia/Shanghai）  
目标机：`root@192.168.25.90`  
目标问题：判断 `reset guest time failed` 是否由 guest 镜像及其快照初态触发。

## 结论

在 `.90` 上保持 Cubelet、cube-shim 和 guest kernel 不变，仅将社区 guest 镜像替换为 `.61` 的历史自编译镜像并重新创建 Template 后：

| 镜像 | 有效完整生命周期 | `reset guest time failed` |
|---|---:|---:|
| `.90` 原社区镜像 | 5/11（45.5%） | 6/11（54.5%） |
| `.61` 历史自编译镜像 | 20/20（100%） | 0/20 |
| 历史镜像恢复后的独立冒烟 | 1/1（100%） | 0/1 |

这构成了较强的因果证据：故障窗口由 guest 镜像包或该镜像生成的快照初态显著影响；问题不是当前 host Cubelet、cube-shim 或 guest kernel 二进制单独造成的。

本次实验尚不能把根因进一步缩小到发行版、cube-agent、启动通知、镜像布局或某个具体 guest 状态。两个镜像同时改变了 rootfs/userland、内嵌 `/sbin/init`、镜像尺寸与布局，以及生成快照时的 guest 状态。

## 镜像身份

### `.90` 原社区镜像

- 备份路径：`/home/lyq/guest-image-ab-20260725-191753/pre/community-cube-image`
- 版本：`v0.5.1`
- 大小：`239075328` bytes
- SHA-256：`05890a04f1aab258abda1c400bf00fe7a2f217d21f27b7a807c2d07920cdfd67`
- rootfs：TencentOS Server 4，实测不是 Ubuntu
- ext4 UUID：`60ed6038-84cf-42a7-9eb5-1f887c109ecc`
- `/sbin/init` SHA-256：`27e7e00f2708048757d6e11363ce3c307c6147fcabc694c7dc202c6fa19f75fc`

### `.61` 历史自编译镜像

- 来源路径：`/usr/local/services/cubetoolbox.before-network-opt-rc1-20260622170352/cube-image-linux-arm64/cube-guest-image-cpu.img`
- 版本：`20260609-222734`
- 大小：`805306368` bytes
- SHA-256：`1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da`
- rootfs：openEuler 24.03 LTS-SP3
- ext4 UUID：`10366a2a-c8df-4cb3-9454-52d0278068c9`
- `/sbin/init` SHA-256：`b65c253b27c683fa7e32c282718718228f68a060a95ec03e40930b6e9d91652e`
- `/sbin/init` 包含 ARM64 `sys_ctrl` startup-ready 通知实现和 `/dev/mem` MMIO 访问字符串。

两个镜像均通过只读 `e2fsck` 检查，文件系统状态为 clean。

`.61` 当前在线部署中的 `d86a97f` 镜像不是上述历史适配镜像。它缺少 ARM64 startup-ready 通知，冷启动虽到达 `ttRPC server started`，但 Shim 等待 ready event 10 秒后超时。该候选已回滚，没有纳入有效 A/B 统计。

## 不变量

替换前后以下 `.90` host 组件保持不变：

| 组件 | SHA-256 |
|---|---|
| Cubelet | `88e5e224fdfb9b1fca5d4722cfa273c49aa7048dffdb28fb88adbc44ddee4c96` |
| cube-shim | `4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d` |
| guest kernel `vmlinux` | `7c227b2ba09988bb4380a95658d1ebe6e17e2f95fac60ed6eb6e42f4a676d8e5` |

Host kernel 为 `6.6.0-132.0.0.111.oe2403sp3.aarch64`。历史镜像对应的新 Template 为 `tpl-abold-83570639543444b0`，状态 `READY`，兼容策略 `STRICT`、结果 `OK`，规格为 2 vCPU / 2000 MiB。

Template API 中的 `agent_version=v0.5.1` 来自版本元数据，不能证明两个镜像内嵌 agent 相同；两者 `/sbin/init` 哈希明确不同。

参考代码版本：

- `~/Projects/Micro-VM/CubeSandbox`：`one-click-install@85ae0f99351b5ff6f880b2ac46c545660019168f`
- `~/Projects/Micro-VM/CubeSandbox-arm64-adaptation`：`feature/arm64-adaptation@28fe3900ba4c827e17618e49fbbe8eb568b3634f`，提交信息为 `Align ARM64 ready notification with x86`

## 测试方法与结果

1. 记录 `.90` 原镜像、host 组件哈希、服务健康和空闲状态，并完整备份社区镜像目录。
2. 从 `.61` 压缩传输历史镜像；在 `.90` 校验 SHA-256 和 ext4 文件系统。
3. 停止 Cubelet，原子替换 guest 镜像与版本文件，启动 Cubelet并检查 CubeAPI。
4. 基于新镜像创建独立 2-vCPU Template。
5. 串行运行 20 次 `create -> guest exec -> delete`；每次前后检查并清理 Sandbox、shim 和 task 目录。
6. 采集 Cubelet、Shim、VMM 与快照元数据，扫描 reset、RCU、timer 和通信错误特征。

有效隔离轮次结果：

- 20 个唯一 attempt，create/command/delete/lifecycle 均为 `20/20`。
- guest 命令输出全部为 `ready vcpus=2`。
- create 延迟：min `0.0572s`，median `0.0605s`，max `0.0754s`。
- `reset guest time failed`、`reset reseed random failed`、RCU stall/starved、timer handling issue 均为 0。
- 结束状态为 `sandboxes/shims/tasks=0/0/0`。

恢复完成后另做 1 次独立冒烟：create `0.0915s`，guest exec 成功，delete `0.3855s`，完整生命周期成功，六类扫描特征均为 0。

同日社区基线在相同 host 和相同三个组件哈希下共运行 11 次，5 次成功、6 次失败；6 次失败全部命中 `reset guest time failed`，并在下一次尝试前由 runner 清理遗留 shim。

## 有效性说明

- `historical-20260609/restore-run-isolated` 是唯一纳入 20 次统计的历史镜像目录。
- `historical-20260609/restore-run` 曾被两个 runner 重叠写入，整目录无效并已明确标记，未用于结论。
- 尝试切回社区镜像做即时反向 A2 控制时，Cubelet 连续五次命中已知的内部插件加载竞态：`io.cubelet.workflow.v1.workflow: NotFound`。脚本在 API 健康检查前自动回滚，因此没有产生 A2 工作负载样本。系统随后恢复正常；对照数据使用当日稍早的社区基线。
- 因未完成紧邻的 A2 反向控制，结论是“guest 镜像包显著触发或关闭故障窗口”，而不是“已经定位到某个 guest 文件或发行版”。

## 最终状态与回滚

截至 `2026-07-25T19:49:01+08:00`，`.90` 保留历史自编译镜像：

- 当前镜像 SHA-256：`1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da`
- 当前版本：`20260609-222734`
- `cube-sandbox-cubelet.service`：`active/running`
- CubeAPI：`{"status":"ok","sandboxes":0}`
- `sandboxes/shims/tasks=0/0/0`
- 当前有效 Template：`tpl-abold-83570639543444b0`

社区镜像完整备份仍在：

`/home/lyq/guest-image-ab-20260725-191753/pre/community-cube-image`

远端完整实验目录为：

`/home/lyq/guest-image-ab-20260725-191753`

## 本地证据

- [有效 20 次汇总](remote-results/guest-image-ab-20260725-191753/historical-20260609/restore-run-isolated/cpu2/case-summary.json)
- [有效 20 次逐条结果](remote-results/guest-image-ab-20260725-191753/historical-20260609/restore-run-isolated/cpu2/results/results.jsonl)
- [恢复后独立冒烟](remote-results/guest-image-ab-20260725-191753/historical-20260609/final-smoke-after-rollback/results/summary.json)
- [最终远端状态](remote-results/guest-image-ab-20260725-191753/final-state.txt)
- [社区镜像身份](remote-results/guest-image-ab-20260725-191753/source-90-community-image.txt)
- [历史镜像身份与 ARM ready 通知证据](remote-results/guest-image-ab-20260725-191753/source-61-historical-image.txt)
- [无效重叠轮次说明](remote-results/guest-image-ab-20260725-191753/INVALID_RESTORE_RUN_NOTE.txt)
- [未完成反向控制说明](remote-results/guest-image-ab-20260725-191753/COMMUNITY_REVERSE_CONTROL_NOTE.txt)
- [同日社区基线](remote-results/arm64-ebpf-wfi-lr-community-baseline-20260725-161653/README.md)

## 建议的下一步

以历史可通过镜像为基线，构建受控镜像矩阵：只替换 cube-agent/init，随后只替换 rootfs/userland；每个镜像重新生成 Template 并各跑至少 100 次串行生命周期。这样可以把当前“镜像整体”的因果证据继续缩小到 agent startup-ready 行为、rootfs 影响或快照时的 vCPU/IRQ 初态。
