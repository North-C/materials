# CubeSandbox Benchmark 前置健康检查报告

- 检查日期：2026-07-18
- 目标主机：`root@192.168.25.90`
- 架构：`aarch64`
- 主机内核：`6.6.0-132.0.0.111.oe2403sp3.aarch64-sbench-irqbypass-xarray`
- CubeSandbox：one-click standalone，v0.5.1 源码基线 `a164417f497234a0d787cb328b0ae96480b1569b`
- Benchmark Template：`tpl-59ebb6c88f6c41a9ad55da91`，2 vCPU / 4 GiB

## 结论

当前集群的基础服务、存储和网络预检通过，但 2 vCPU ARM64 Template 的重复创建可靠性未通过。因此，集群暂时不能判定为满足正式 benchmark 的正常状态，正式测试未继续执行。

## 基础服务检查

| 检查项 | 结果 | 状态 |
| --- | --- | --- |
| Cube API | `{"status":"ok","sandboxes":0}` | 通过 |
| Cubelet | `active` | 通过 |
| network-agent | `/healthz` 返回 `ok` | 通过 |
| CubeSandbox 核心 systemd 服务 | 全部 `active/running` | 通过 |
| systemd failed units | `0` | 通过 |
| 残留 `containerd-shim-cube-rs` | `0` | 通过 |
| TAP 池 | `500` 个持久 TAP | 通过 |
| Cubelet 数据盘 | `/dev/nvme3n1`，XFS，挂载于 `/data/cubelet` | 通过 |
| 数据盘可用空间 | 约 2.9 TiB | 通过 |
| 可用内存 | 约 2.13 TiB | 通过 |

## Kubernetes 隔离状态

- `kubelet.service`：`inactive`、`disabled`
- 未发现 kube-apiserver、kube-controller-manager、kube-scheduler、kube-proxy 或 kubelet 进程
- 未发现 `6443`、`10250`、`10257`、`10259` Kubernetes 监听端口

Kubernetes 服务已经关闭，不是当前故障的干扰源。

## 2 vCPU Template 可靠性门槛

当前部署的 CubeShim：

- 版本：`v0.5.1-arm-clock-vm-offset-cap1s-v7`
- SHA256：`2dd6f1a728e0ba1b78d86be85091bb0bd68f6d5f27617f4e4f37c08c9bec02b8`

全新 2 vCPU / 4 GiB Template 连续创建结果：

| 尝试 | 成功 | 失败 | 结果 |
| ---: | ---: | ---: | --- |
| 100 | 99 | 1 | 不通过 |

失败时的主要现象是 guest CPU1 卡在 timer softirq/RCU 路径，创建请求超时，并留下高 CPU 的 CubeShim。该问题具有间歇性，单次或少量冒烟成功不能证明集群正常。

## 已检查的因素

- CPU/内存规格：1 vCPU 稳定，2 vCPU 在 2 GiB、4 GiB、8 GiB 下均可能复现；内存容量不是根因。
- NUMA/CPU 亲和性：将 Cubelet 约束到单 NUMA 节点未解决问题。
- TAP：失败前 TAP 获取正常，接口为 `UP/LOWER_UP`，network-agent 无对应错误；TAP 参数不是根因。
- PMU：关闭 guest PMU 后，100 次创建仍有 2 次失败；PMU 不是根因。
- ARM64 timer snapshot：回移 Cloud Hypervisor 的 CNTVCT 修复并使用 VM 级 `KVM_ARM_SET_COUNTER_OFFSET` 后，失败率降低但未归零。
- v9 CVAL/CTL 重写实验：5 次仅 1 次成功，已回滚到 v7。

## 后续门槛

正式 benchmark 恢复前，应满足以下条件：

1. 全新 2 vCPU / 4 GiB Template 连续创建、执行简单命令并销毁 100 次，成功率为 100%。
2. 测试后 Cube API 中 sandbox 数量为 0，且不存在残留 CubeShim。
3. guest 日志不存在 timer handling、RCU stall 或相关 fatal 特征。
4. 基础服务、TAP 池和 XFS 数据盘继续保持健康。

当前建议继续处理 ARM64 多 vCPU snapshot/restore 的虚拟定时器兼容性，或升级到包含更完整 ARM64 timer/GIC snapshot 修复的 Cloud Hypervisor/CubeSandbox 版本。重试创建只能作为临时规避方式，不能用于正式性能测试。

## 远端证据

- 工作目录：`/home/lyq/cube-bench-formal-arm64-2c4g-retest-20260717-175203`
- v7 门槛结果：`diagnostics/clockfix-v7-fresh-template-gate-2c4g-100/summary.txt`
- v7 Template：`diagnostics/clockfix-v7-fresh-template-2c4g/template-id.txt`
- v8 PMU 隔离结果：`diagnostics/clockfix-v8-nopmu-fresh-gate-2c4g-100/summary.txt`
- v9 回归实验：`diagnostics/clockfix-v9-vtimer-refresh-gate-2c4g-5/results.txt`
