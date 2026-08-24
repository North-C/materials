# CubeSandbox Runtime Snapshot / Pause / Resume / Clone 基线报告

## 0. 状态

**CORE COMMUNITY BASELINE COMPLETE / EXTENDED MATRIX PARTIAL（COOLDOWN STOP）**。

- 早期 REST 预检 attempt 与残留问题保留在第 1–7 节，作为失败历史，不从报告中删除。
- .90 重启并恢复 SSH 后，已获授权清理唯一 worker pausevm orphan；当前物理/逻辑资源归零。
- 直接使用未修改的社区原脚本完成 Snapshot c1/c5/c10、Pause/Resume c1/c5/c10、Clone n1/c1 与 n100/c10/c20/c50。
- dirty、从 Snapshot 创建、Rollback 尚未执行；尚未进入任何优化或二进制替换。

## 1. 批次与版本

### Attempt 1

- run label：`spc90-20260821T150133Z-1ffd0f47`
- 结果：preflight PASS；Snapshot warm-up 功能 PASS；三个 DELETE 均一次返回 204。
- runner 在 DELETE 后立即采样到 TAP-in-use=2，误判 cleanup 失败；随后无额外操作自然回到 TAP-in-use=0。
- 该 attempt 不含 formal 样本，完整保留为失败 attempt。

### Attempt 2

- run label：`spc90-20260821T151035Z-e0063a6a`
- runner SHA-256：`5eee456600c77d656f1f88cb18d5d7e61b5144d1a979b2b504370aff563b7856`
- 复用 Attempt 1 成功 warm-up，文件 SHA-256：`0ca79411c17bb5bb76b9d7f57c2b074552393620754f4b10e4b91f3cf341f4d2`
- DELETE 后只读等待资源收敛，不重复 DELETE。
- preflight 身份与接受起点一致：kernel、NUMA/THP/HugePages、XFS、quota、Template/image/fingerprint、六组件 SHA-256、CPU affinity、quickcheck、服务和空闲资源全部通过。

## 2. Runtime Snapshot c1 preliminary baseline（非社区脚本主表）

本节由标准库 REST 预检 runner 形成，用于验证 API、marker、Snapshot mode 和 cleanup 链路。它没有直接执行社区 `bench_snapshot_concurrency.py`，因此保留为 preliminary evidence；后续社区对照主表必须重新使用固定 SHA-256 的社区脚本及相同 timer/round 定义。本节数据不会与社区历史值直接计算提升或回归百分比。

### 2.1 功能断言

三轮均通过：

- source rootfs marker 与 `/dev/shm` memory marker 在 Snapshot restore 后保持 snapshot 时刻值；
- Snapshot 后修改 source 的两类 marker，不影响从原 Snapshot 创建的 restore Sandbox；
- Runtime Snapshot 前后 source shim PID/start ticks 不变，源 Sandbox 继续运行；
- 每轮 source、restore、Runtime Snapshot 的精确 ID 均一次 cleanup 成功；
- Sandbox/API Snapshot/CubeCow/shim/task/VMM/TAP 最终回到 before baseline，但 4 个 worker `snap-*` metadata 空目录仍存在；因此严格物理清理门禁未完全通过。

### 2.2 请求时延

单位为 ms；分位数为 nearest-rank。3 个样本时 P95/P99 都等于 max。

| 指标 | Raw | Avg | Min | P50 | P95/P99/Max | CV |
|---|---|---:|---:|---:|---:|---:|
| Runtime Snapshot create | 82.578 / 75.761 / 87.758 | 82.032 | 75.761 | 82.578 | 87.758 | 7.335% |
| 从 Runtime Snapshot 创建 | 93.138 / 93.045 / 94.346 | 93.510 | 93.045 | 93.138 | 94.346 | 0.776% |
| source Template create（preparation） | 51.510 / 50.102 / 50.231 | 50.614 | 50.102 | 50.231 | 51.510 | 1.538% |

三轮 formal 请求全部成功，无重试。c1 中 whole-round wall 等于单请求 latency；尚无并发吞吐结论。

### 2.3 Snapshot type、base 与实际写入

三轮 source 都是 fresh Template restore：

| Round | Cubelet/VMM 请求 type | VMM 实际 mode | actual written bytes |
|---:|---|---|---:|
| 1 | `SoftDirty` | tracker 未 arm，实际 `PagemapAnon` | 10,932,224 |
| 2 | `SoftDirty` | tracker 未 arm，实际 `PagemapAnon` | 10,866,688 |
| 3 | `SoftDirty` | tracker 未 arm，实际 `PagemapAnon` | 10,768,384 |

**已验证事实**：当前 fresh source 的首次 Runtime Snapshot 虽请求 `SoftDirty`，但 VMM 明确记录 tracker 尚未 arm，因此用 pagemap_anon 写完整 anon-page 集合，然后 `clear_refs(4)` 为下一周期 arm。不能把该三轮称为稳态 SoftDirty delta。

### 2.4 cleanup 收敛

- 三轮 DELETE 后首次采样均见 TAP-in-use=2；只读等待后分别约 1.349 / 1.373 / 1.388 秒回到 0。
- 未重发 DELETE。
- 冷却结束 `kvm-irqfd-cleanup=0`；final threads 分别约 5,768 / 5,885 / 6,007。
- Round 1 冷却用了 11 个 2 秒样本，其余为 5 个；门禁未放宽。
- API Snapshot 列表和 CubeCow memory/rootfs 对象已归零，但以下 worker metadata 目录为空且仍存在，均为 mode 0755、size 6、blocks 0：
  - `snap-01e53a9375b54ca4879526b8`（Attempt 1 warm-up）；
  - `snap-dfdf9b8dd2404ba7a888d628`；
  - `snap-0a7156b300944094bc9a745d`；
  - `snap-fa8930118c294ed09b2b9635`。
- 未直接删除这些目录。按严格“物理对象回到 before baseline”定义，Runtime Snapshot suite 的 cleanup 只能标记为 **PARTIAL**，不能标记完全通过。

## 3. Pause warm-up：部署路径与 current HEAD 不同

worker-owned Sandbox：`f970cb7d612e41b4b0dc83b175c2d0b4`。

### 3.1 已验证事实

- CubeAPI Pause 请求成功；API journal 起止约为 23:09:56.164 至 23:09:56.918，日志差约 753.5 ms。该值是单次 warm-up 日志差，不是 formal baseline。
- Pause 后 API state=`paused`，VMM=0、containerd task=0，但 shim=1、TAP-in-use=1。
- VMM 日志明确为：

```text
VmPauseToSnapshot(SnapshotConfig {
  destination_url: file:///data/cubelet/root/pausevm/f970cb7d612e41b4b0dc83b175c2d0b4,
  snapshot_type: Full,
  memory_vol_url: None
})
Saving full guest memory to snapshot image file.
```

- 实体：

| 文件 | apparent bytes | allocated bytes |
|---|---:|---:|
| `config.json` | 3,533 | 4,096 |
| `state.json` | 93,988 | 94,208 |
| `memory-ranges` | 2,097,152,000 | 2,097,152,000 |

- 没有新 `cube-snapshot/cubebox/snap-*` Pause catalog。
- 部署 Cubelet/Shim 不含 current HEAD PauseCow 的关键标识，说明 .90 当前二进制走 legacy pausevm 路径。

### 3.2 cleanup 失败与当前残留

runner 只对精确 worker ID 调用一次 DELETE，返回：

```text
HTTP 500
CubeMaster error 130593:
delete sandbox by binary failed: ... sandbox not in normal state
```

当前保留：

- logical paused Sandbox：`f970cb7d612e41b4b0dc83b175c2d0b4`；
- shim：1；TAP-in-use：1；VMM/task：0；
- `/data/cubelet/root/pausevm/f970cb7d612e41b4b0dc83b175c2d0b4/`；
- 上一节列出的 4 个 worker Runtime Snapshot metadata 空目录；
- 服务均 active、failed units=0；未发现其他 Sandbox/Runtime Snapshot。

没有再次 Resume、DELETE、kill、目录清理或扩大 cleanup。

## 4. 尚未执行

- Pause formal 3/5 rounds；
- Resume 功能与性能；
- Clone 功能与性能；
- c5/c10 或更高并发；
- dirty sensitivity；
- 单变量优化与 A/B。
- 固定社区六脚本的正式对照主表。

这些项目必须等待 worker-owned paused Sandbox 的精确恢复/清理获得新授权，并在清理后重新执行 G0/G1/G2。

## 5. 证据目录

- Attempt 1：`/home/lyq/Projects/Verification/cubesandbox/remote-results/runtime-snapshot-pause-clone-90-spc90-20260821T150133Z-1ffd0f47`
- Attempt 2：`/home/lyq/Projects/Verification/cubesandbox/remote-results/runtime-snapshot-pause-clone-90-spc90-20260821T151035Z-e0063a6a`
- 两目录均含 runner、preflight、逐轮 JSON、owned-object ledger、cleanup/convergence/cooldown、filtered logs 和 `SHA256SUMS`。

## 6. 结论等级

- **已验证事实**：Runtime Snapshot c1 三轮功能/时延、首次 fresh Snapshot 的 PagemapAnon 实际 mode、逻辑/API/CubeCow 资源收敛、4 个 metadata 空目录残留、legacy Full Pause 实体和 cleanup 错误。
- **合理推断**：Pause 约 753.5 ms 的主导成本很可能包含 2,097,152,000-byte full memory 写入；缺内部独占阶段计时，尚不能给出精确占比。
- **尚未确认**：Resume 时延、Clone 时延、并发扩展、Page Cache 因果、Pause SoftDirty 候选收益。

时钟 caveat：operation latency 来自同机 monotonic；Pause 753.5 ms 仅由同机 CubeAPI journal 差得到。未用跨主机绝对时间计算时延。

## 7. 2026-08-22 重启后的残留状态

.90 发生外部重启，boot ID 变为 `da0959a5-e258-48be-82f9-3b1eac1e8093`。重启后重新核验：

- 六组件 hash、kernel、NUMA/THP/HugePages、XFS、quota、CPU affinity、Template/image/fingerprint 全部仍匹配接受起点；
- quickcheck OK、failed units=0；Sandbox/API Snapshot/shim/task/VMM/TAP-in-use 均为 0；
- 上轮 paused Sandbox `f970cb7d612e41b4b0dc83b175c2d0b4` 在 CubeAPI 和 CubeMaster 均为 NotFound，containerd/Cubelet state 无引用；
- `/data/cubelet/root/pausevm/f970cb7d612e41b4b0dc83b175c2d0b4` 仍保留 `config.json`、`state.json` 和 2,097,152,000-byte fully allocated `memory-ranges`，属于重启后的孤立物理产物；
- 4 个已确认 children=0 的 worker `snap-*` metadata 目录已使用精确 `rmdir` 删除；未使用递归删除；
- 未直接删除非空 pausevm orphan，等待明确授权。

社区脚本的新批次尚未启动。严格 before baseline 只有在该非空 orphan 获得处理后才可能通过。

## 8. 2026-08-22 社区原脚本核心基线

### 8.1 执行身份与边界

- run label：`spc90-community-20260822T091058Z-31b38a2d`。
- 直接执行仓库原脚本，未修改脚本内容：
  - `bench_snapshot_concurrency.py`：`b896937eabe210cfddfb63501f471b4e48c873b7149d20da886a1f502f152253`；
  - `bench_pause_resume_concurrency.py`：`2cba48bf409d26812cbea88a29d9987931a838f5bf6804f5da25652688134593`；
  - `bench_clone_concurrency.py`：`eda015c383c95bae92fe7608aa2f4824c4583cdc571062cf3f8577544ab9e67f`。
- SDK 使用冻结的当前源码 `0.6.0`，通过 `PYTHONPATH` 直接导入；隔离 venv 固定 `httpx 0.28.1`、`requests 2.34.2` 等依赖。第一次在线安装超时、第二次 SDK wheel build 缺 `bdist_wheel` 均保留为 setup failure；最终依赖来自 SHA-256 已记录的 ARM64 offline wheelhouse。
- 外层 harness 只记录 before/after、host samples、组件日志窗口、ID、空 metadata 目录清理和冷却，不修改社区 timer/aggregate。
- 社区脚本只输出 aggregate，缺逐轮 raw；P95 在 2 或 5 轮时等于 max。这一限制原样保留。

### 8.2 Runtime Snapshot concurrency

| c | rounds | wall avg | min | P95/max | wall/N |
|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 84.9 ms | 80.5 | 88.8 | 84.9 ms |
| 5 | 5 | 103.5 ms | 100.3 | 112.3 | 20.7 ms |
| 10 | 5 | 125.6 ms | 117.2 | 138.7 | 12.6 ms |

所有脚本返回 0。c1/c5/c10 分别登记 6/60/120 个对象 ID；API/CubeCow/runtime 资源归零，社区删除留下的空 `snap-*` 目录按精确 ID 使用 `rmdir` 清理。

### 8.3 Pause / Resume

| c | rounds | Pause avg | Pause min | Pause P95/max | Pause wall/N | Resume avg | Resume min | Resume P95/max | Resume wall/N |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 514.2 | 486.1 | 550.5 | 514.2 | 14.5 | 14.1 | 14.8 | 14.5 |
| 5 | 5 | 590.8 | 562.0 | 630.2 | 118.2 | 18.7 | 18.1 | 19.2 | 3.7 |
| 10 | 5 | 572.9 | 553.4 | 597.3 | 57.3 | 24.2 | 23.4 | 25.0 | 2.4 |

单位均为 ms。三档分别登记 6/30/60 个 Sandbox ID；最终 pausevm/shim/task/VMM/TAP/API 全部归零。

### 8.4 Clone

| n | c | rounds | wall avg | min | P95/max | wall/N |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 5 | 189.4 ms | 187.3 | 193.9 | 189.4 ms |
| 100 | 10 | 2 | 720.5 ms | 718.5 | 722.5 | 7.2 ms |
| 100 | 20 | 2 | 492.8 ms | 489.2 | 496.5 | 4.9 ms |
| 100 | 50 | 2 | 396.2 ms | 395.8 | 396.6 | 4.0 ms |

n100 各档均登记 303 个 Sandbox/Snapshot ID，最终资源归零。`wall/N` 是吞吐摊销，不是单 clone request latency。

### 8.5 冷却与 gate-only attempts

- Snapshot c5/c10 分别需要 48/96 个 2 秒冷却样本；c10 threads 从 9,142 回落到 5,466。
- Pause c10 需要 88 个样本；threads 从 10,658 回落到 5,587。
- Clone n100 c10/c20/c50 分别需要 92/85/80 个样本；threads 峰值约 12,277/12,518/13,264，随后批量回落。
- 本轮 `kvm-irqfd-cleanup` 采样均为 0，但总 threads 明显累积并批量回落。该现象与旧 boot 上的命名 kworker 不同，原因尚未确认。
- Snapshot c10、Pause c5、Clone c50 各有一次 `Writeback>0` 的 before gate-only failure；均未启动社区脚本、未创建对象，随后在新 evidence 目录执行。
- 未提高 threads/Writeback 门禁，未 kill 线程，未重启服务或主机。

### 8.6 与社区历史表的解释边界

本轮命令和脚本与社区表对齐，可做同口径描述性比较；但 host/kernel/Template/image/SDK/API、缓存和时间均不同，不是 fresh paired A/B，不能把差值归因到 opt235、MMDS-prime、HZ=1000 或任何单一优化。

## 9. 新批次证据

`/home/lyq/Projects/Verification/cubesandbox/remote-results/spc90-community-20260822T091058Z-31b38a2d`

每个 case 保存 command、stdout/stderr、before/after、host samples、组件日志窗口、观测 ID、空 metadata cleanup、convergence/cooldown 和 exit。环境、组件/脚本/wheel hashes 与最终状态见 `environment-and-final-state.txt`。

## 10. 2026-08-24 扩展矩阵启动前阻塞

计划执行从 Snapshot 创建、Rollback 和 dirty sensitivity，但 G0/G1 预检发现 CubeAPI 正在被其他操作者替换并处于重启异常，测试在创建任何对象前停止：

- 接受的 CubeAPI hash：`92b81197815823b23ec91906fbeaa7321d69da2c6136d9c757a5446684244bc1`；
- 当前磁盘文件 hash：`a412316d5b98aff4176a56885707725697e02e4544303f0e2c618b3e1f5f4941`；
- 当前磁盘文件 mtime/ctime：`2026-08-24 10:14:07 +08:00`，inode `539853007`；
- 仍提供 `GET /health` 200 的旧进程 PID `2403428`，启动于 `2026-08-24 10:13:47`，`/proc/2403428/exe` 标记 `(deleted)`，runtime SHA-256 仍为接受值 `92b81197...`；
- `cube-sandbox-cube-api.service` 处于 `activating (auto-restart)`，`ExecMainStatus=1`，10:39 后持续尝试启动磁盘上的新文件；
- 预检时 Sandbox/Snapshot/shim/task/VMM/TAP 均为 0；未启动 `bench_create_concurrency.py`、`bench_rollback_concurrency.py` 或 `bench_snapshot_dirty.py`；
- 三个社区原脚本 SHA-256 已重新验证，但没有产生性能样本。

因此第 8 节核心基线仍有效且保持原始证据；扩展测试没有结果，不能伪造或沿用旧值。恢复扩展测试需要用户先确认最终接受的 CubeAPI 身份，并使 systemd/runtime identity 收敛到同一个 hash。本文未停止服务、未恢复旧二进制、未替换新二进制。

阻塞证据目录：`/home/lyq/Projects/Verification/cubesandbox/remote-results/spc90-community-ext-20260824T024052Z-b4621d70`。

## 11. CubeAPI 恢复与扩展测试结果

### 11.1 CubeAPI 恢复到接受身份

经用户明确授权，CubeAPI 已恢复为接受的 `92b81197815823b23ec91906fbeaa7321d69da2c6136d9c757a5446684244bc1`：

- 可信源：`/usr/local/services/cubetoolbox/CubeAPI/bin/cube-api.baseline-`；
- 恢复前 `a412316d...` 已归档到 `/home/lyq/cube/backups/cubeapi-restore92b-before-20260824T025335Z/cube-api.a412.pre`；
- candidate、pre-image、mode/owner/mtime、ELF/readelf 和 SHA256SUMS 均已保存；
- 停止 systemd auto-restart，原子替换磁盘文件，向旧 deleted-inode PID 2403428 发送一次 TERM；
- 新 systemd MainPID 2505459 启动成功；磁盘和 `/proc/2505459/exe` SHA 均为 `92b81197...`；health OK；
- 自动回滚脚本保存在同一备份目录，可恢复归档的 `a412` 磁盘文件；本次未触发回滚。

恢复后六组件 hash、quickcheck、Template、Sandbox/Snapshot/shim/task/VMM/TAP 和 failed units 再次通过。

### 11.2 从 Snapshot 创建 c1

直接执行未修改社区原脚本：

```text
python bench_create_concurrency.py -c 1 -n 3
```

脚本 SHA-256：`332d5cd147dd654ac141d7598028c93756997b1c72ef2deaee80229c28f5d513`。

| c | n_total | rounds | wall avg | min | P95/max | wall/N |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 3 | 48.4 ms | 47.3 | 49.9 | 48.4 ms |

脚本 return code=0；共从日志窗口登记 6 个对象 ID，Runtime Snapshot/API/CubeCow/runtime 资源归零，1 个空 Snapshot metadata 目录按精确 ID `rmdir`。

### 11.3 600 秒冷却门禁失败

尽管 create-c1 请求与 cleanup 成功，host 冷却没有在 600 秒硬上限内完成：

- 139 个两秒采样；
- 首个样本 threads=6,160；
- 观察峰值 threads=25,963；
- 600 秒末最后样本 threads=10,703，`gate_ok=false`；
- API Sandbox/Snapshot、shim、task、VMM、TAP、failed units 均为 0；
- `kvm-irqfd-cleanup` 命名计数为 0；
- wrapper 返回 22，明确表示 cooldown timeout，而不是社区脚本失败；
- wrapper 退出后才观察到 threads 批量降至约 5,816。

按照 TEST_PLAN 的 `cooldown_timeout_seconds=600` 和“不提高门禁、不在失败后进入下一档”，扩展 suite 在此停止。因此以下项目**没有结果**：

- 从 Snapshot 创建 c10/c20/c50；
- Rollback c1/c5/c10；
- dirty sensitivity 0/10/50/100/200/500/800/1024 MiB。

不得用社区历史值、早期其他主机结果或推算值填充这些空项。

### 11.4 最终社区对齐覆盖矩阵

| 社区测试项 | 本轮状态 |
|---|---|
| Runtime Snapshot concurrency c1/c5/c10 | COMPLETE |
| Pause/Resume c1/c5/c10 | COMPLETE |
| Clone n1/c1、n100/c10/c20/c50 | COMPLETE |
| 从 Snapshot 创建 c1 | COMPLETE，但 suite 冷却超时 |
| 从 Snapshot 创建 c10/c20/c50 | NOT RUN |
| Rollback c1/c5/c10 | NOT RUN |
| dirty sensitivity 0–1024 MiB | NOT RUN |

本报告已按社区脚本、参数、timer 和 aggregate 字段对齐；同时保留 setup failure、身份阻塞、gate-only attempt、物理 cleanup 和冷却失败，未以“只保留成功表格”的方式掩盖失败分母。

## 12. 2026-08-24 第二次扩展 suite 预检阻塞

用户授权在重新校验正常后以新 run label `spc90-community-ext2-20260824T105834Z-c2baad89` 继续未完成矩阵，但 G0 再次发现外部重启与 CubeAPI 身份变化，因此没有启动任何社区脚本：

- boot ID 从此前 `da0959a5-e258-48be-82f9-3b1eac1e8093` 变为 `34fd59b0-6cb6-4301-9a98-41194e868b33`；
- 当前 CubeAPI 磁盘/runtime SHA-256 均为 `3bc9d08b2b3fc56bf27ef719ae95feaf64012c8397406d07ecab1711eba85d66`；
- 该文件 mtime/ctime 为 `2026-08-24 14:19:31 +08:00`，inode `539853008`；
- systemd MainPID `10473`，17:49:43 启动，active/running、NRestarts=0、health 200；
- 接受的 `92b81197...` backup 仍存在，但本 worker 未再次覆盖当前 `3bc9...`；
- 其余五组件、kernel、Template/image/fingerprint 与资源空闲状态均匹配；
- 从 Snapshot 创建 c10/c20/c50、Rollback 和 dirty sensitivity 均未启动，也没有创建对象。

这不是性能失败，而是测试身份不再满足固定变量。继续前必须明确选择接受 `3bc9...` 作为新基线，或再次授权恢复 `92b...`，并确保没有并发部署/重启窗口。
