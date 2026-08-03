# CubeSandbox 2U2G Template 核心性能测试报告

测试日期：2026-08-03

测试节点：`192.168.25.90`

最终状态：因连续错误达到阈值提前终止，无可纳入统计的核心性能样本

## 1. 结论摘要

1. 本轮新建了 `tpl-a72fa239e2fe4f22922f1f7f`，服务端保存的创建请求确认其配置为 2U2G、1GiB writable layer，状态为 `READY`。
2. 使用该 Template 的 Hello World 与 `run_code` 功能门禁通过，返回结果 `42`。
3. 正式矩阵从 Snapshot c1 开始。`snapshot-c1` 与 `snapshot-c5` 各重试 3 次，6 次均在首个 `Sandbox.create` 阶段失败，Snapshot 操作尚未开始。
4. 6 次失败中，5 次为 `reset reseed random dev failed`，1 次为 `reset guest time failed`；底层共同错误均为 guest-agent ttrpc `Receive packet timeout`。
5. 按“单项最多重试 3 次，累计 2 个测试项失败即停止”的预设门禁，其余 23 项没有继续施压。本轮不能给出 avg、p95、p99 或吞吐数据，相关字段统一标记为 `N/A`。
6. 测试结束后四个 CubeSandbox 服务均为 `active`，Sandbox、shim、task、占用中的 TAP 均为 0；测试前已有的 8 个 Snapshot ID 与测试后逐项一致。

这次结果说明当前运行栈未通过核心性能测试的可靠性前置条件，不能据此评价 Snapshot、Rollback、Clone 或 Pause/Resume 本身的性能。

## 2. 测试环境

| 项目 | 配置 |
|---|---|
| Host | `root@192.168.25.90`，ARM64 |
| Host kernel | `6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray-v2` |
| Guest rootfs OS | `TencentOS Server 4`，只读读取 `usr/lib/os-release` 确认 |
| Template | `tpl-a72fa239e2fe4f22922f1f7f`，`READY` |
| OCI image | `127.0.0.1:5000/cubesandbox-bench/sandbox-code-envd-ci@sha256:b741fde1de3dd4cc4f4cc82c089e861e5d53f1d5f0b4492be6f9f98f4652af3a` |
| Template resources | CPU `2000m`，内存 `2000Mi` |
| Writable layer | `1G` |
| Probe | HTTP `49999/health`，构建请求中 `period_ms=500`、`timeout_ms=30000` |
| Exposed ports | `49983`、`49999` |
| Python / SDK | Python `3.11.6`，CubeSandbox SDK `0.5.0` |
| TAP | 预创建 1000 个；每项前后要求占用数为 0 |
| API | `http://127.0.0.1:3000` |

### 2.1 运行组件校验值

| 组件 | SHA-256 |
|---|---|
| CubeMaster | `0b78e83c218a7d62c6418def13b50cc2e7c0a0e86115d3ff4006d538951014ae` |
| Cubelet | `88e5e224fdfb9b1fca5d4722cfa273c49aa7048dffdb28fb88adbc44ddee4c96` |
| CubeShim | `4702fde1390fc8ec11927ff2375096749adc4f4f72255bdede4b36e7c47bb15d` |
| Guest kernel `vmlinux-bm` | `c55157198ca74933526d1ed5d08a5a3786fd2323d5fc00c65ade19635a3b976e` |
| Guest image | `05890a04f1aab258abda1c400bf00fe7a2f217d21f27b7a807c2d07920cdfd67` |

## 3. 测试方法与中止条件

本轮沿用既有核心测试套件，计划依次运行 Snapshot、dirty-memory Snapshot、基于 Snapshot 创建 Sandbox、Rollback、Clone 和 Pause/Resume。每个测试项开始前和结束后均执行以下门禁：

- CubeMaster、Cubelet、network-agent、CubeAPI 及健康检查正常；
- Sandbox、测试新增 Snapshot、CubeShim task 均为 0；
- TAP 总量不少于 1000，且占用中的 TAP 为 0；
- 每项失败后清理本轮资源，再重新尝试；
- 单项最多尝试 3 次；累计 2 个测试项耗尽重试后停止后续矩阵；
- 只删除本轮测试新建的 Snapshot，保留测试前已有的 8 个 Snapshot。

正式测试从 `2026-08-03T22:09:25+08:00` 运行至 `2026-08-03T22:14:06+08:00`。在正式矩阵前，隔离清理逻辑完成了一次空矩阵演练，8 个原 Snapshot ID 的前后比较结果为一致。

## 4. 计划矩阵与执行状态

| 类别 | 计划场景 | 数量 | 执行结果 |
|---|---|---:|---|
| Snapshot 并发 | c1、c5、c10，各 5 轮 | 3 | c1/c5 各 3 次失败；c10 未执行 |
| Dirty-memory Snapshot | 0、10、50、100、200、500、800、1024MiB，各 3 轮 | 8 | 达到错误阈值，未执行 |
| 基于 Snapshot 创建 | c1、c10、c20、c50，各 3 轮 | 4 | 达到错误阈值，未执行 |
| Rollback | c1、c5、c10，各 5 轮 | 3 | 达到错误阈值，未执行 |
| Clone | n1/c1；n100/c10、c20、c50 | 4 | 达到错误阈值，未执行 |
| Pause/Resume | c1、c5、c10，各 5 轮 | 3 | 达到错误阈值，未执行 |
| 合计 | 25 个测试项 | 25 | 2 项失败，23 项按门禁跳过 |

## 5. 核心性能结果

### 5.1 有效结果表

| 场景 | 尝试次数 | 有效轮次 | 成功率 | avg | p95 | p99 | 吞吐 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Snapshot c1 | 3 | 0 | 0/3 | N/A | N/A | N/A | N/A |
| Snapshot c5 | 3 | 0 | 0/3 | N/A | N/A | N/A | N/A |

`bench_snapshot_concurrency.py` 每次都在首轮创建源 Sandbox 时抛出异常，尚未进入 Snapshot 计时与汇总阶段。失败进程只输出表头或 traceback，没有合法的延迟行，因此不能将进程存活时间或清理时间当作性能时延。

### 5.2 逐次失败

| 测试项 | 尝试 | 退出码 | 失败阶段 | 错误 |
|---|---:|---:|---|---|
| Snapshot c1 | 1 | 1 | `Sandbox.create` / guest reset | `reset reseed random dev failed`，ttrpc receive timeout |
| Snapshot c1 | 2 | 1 | `Sandbox.create` / guest reset | `reset reseed random dev failed`，ttrpc receive timeout |
| Snapshot c1 | 3 | 1 | `Sandbox.create` / guest reset | `reset guest time failed`，ttrpc receive timeout |
| Snapshot c5 | 1 | 1 | `Sandbox.create` / guest reset | `reset reseed random dev failed`，ttrpc receive timeout |
| Snapshot c5 | 2 | 1 | `Sandbox.create` / guest reset | `reset reseed random dev failed`，ttrpc receive timeout |
| Snapshot c5 | 3 | 1 | `Sandbox.create` / guest reset | `reset reseed random dev failed`，ttrpc receive timeout |

作为功能对照，正式矩阵前使用相同 Template 创建 Sandbox 并执行 `run_code` 成功，输出 `Hello from Cube Sandbox, safely isolated!` 和结果 `42`。这表明故障具有不稳定性，而不是 Template 永久不可用。

## 6. 错误分析

当前证据支持以下判断：

1. 失败发生在基于 Template 恢复 Sandbox 的 guest reset 阶段，早于 Snapshot API，因此不能归因于 Snapshot 写盘、dirty-memory 拷贝或并发 Snapshot 逻辑。
2. c1 也连续失败，且测试前资源充足，不能用高并发或 TAP 耗尽解释本轮错误。
3. 6 次错误共同指向 host CubeShim 与 guest-agent 之间的 ttrpc 响应超时；其中 reseed random device 是主要失败点，guest time reset 也出现一次。
4. c1 的第 1、3 次以及 c5 的第 2 次失败后观察到 1 个残留 CubeShim；隔离 runner 回收后资源门禁恢复正常。
5. 当前 guest rootfs 是 TencentOS Server 4。仅凭本轮数据不能证明 OS 发行版本身是根因，但在更换 guest image/kernel 或 guest-agent 后必须重新构建 Template，再做同口径可靠性门禁。

建议在再次运行完整矩阵前，先要求同一 2U2G/1G Template 连续完成至少 20 次 create/delete 且 20/20 成功，并重点检查 guest-agent 的 guest-time/reseed reset handler、vsock/ttrpc 接收超时及失败后的 shim 生命周期。可靠性门禁通过后再恢复 25 项矩阵，避免将系统错误混入性能统计。

## 7. 测试后资源核验

| 资源 | 测试前 | 测试后 | 结果 |
|---|---:|---:|---|
| CubeSandbox 服务 | 4 个 active | 4 个 active | 通过 |
| Sandbox | 0 | 0 | 通过 |
| Snapshot 总数 | 8 | 8 | 通过 |
| Snapshot ID 集合 | 8 个基线 ID | 与基线逐项一致 | 通过 |
| 测试新增 Snapshot | 0 | 0 | 通过 |
| CubeShim | 0 | 0 | 通过 |
| containerd task | 0 | 0 | 通过 |
| TAP 总数 | 1000 | 1000 | 通过 |
| TAP in-use | 0 | 0 | 通过 |

测试结束时 API 健康响应为 `{"status":"ok","sandboxes":0}`，未遗留测试资源。

## 8. 证据索引

完整原始证据保存在本地：

`/home/lyq/Projects/Verification/cubesandbox/artifacts/cubesandbox-core-perf-2u2g-20260803`

| 内容 | 相对路径 |
|---|---|
| Template 创建结果 | `evidence/template-create.json` |
| Template READY 信息与原始创建请求 | `evidence/template-info.ready.json` |
| Template render | `evidence/template-render.json` |
| 组件哈希 | `evidence/component-sha256.txt` |
| 测试配置 | `core-operations/evidence/test-context.txt` |
| 执行时间线与错误阈值 | `core-operations/run.log` |
| 六次失败原始日志 | `core-operations/snapshot-c1-attempt-*.log`、`snapshot-c5-attempt-*.log` |
| 测试前后 Snapshot ID | `core-operations/evidence/baseline-snapshot-ids.json`、`final-snapshot-ids.json` |
| 最终资源状态 | `core-operations/evidence/final-state.txt` |
| 完整性校验 | `core-operations/SHA256SUMS` |
| 测试状态 | `core-operations/status.txt` |
