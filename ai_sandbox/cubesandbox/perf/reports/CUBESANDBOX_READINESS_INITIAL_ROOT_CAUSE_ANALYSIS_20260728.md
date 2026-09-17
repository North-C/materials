# CubeSandbox Template 并发创建就绪阶段初步原因分析

## 1. 文档目的

本文记录 2U2G Template 在 `c50n500` 并发创建场景中，就绪确认阶段耗时偏高的初步定位结果。

当前分析已经区分以下两类时间：

1. Cubelet HTTP probe 的轮询、连接和重试开销。
2. guest 恢复后，`envd` 实际尚未达到可响应状态的等待时间。

当前证据能够将主要等待收敛到 guest 恢复后的运行与就绪路径，但尚未取得 guest 内每个关键事件的统一时钟时间戳。因此，本文结论属于有数据支持的初步原因定位，不声明已经证明唯一根因。

## 2. 就绪逻辑链路

```text
创建请求
  -> Cubelet 启动 early HTTP probe
  -> CubeShim CreatePodSandbox
  -> LaunchVmm / RestoreVm / ResetVm
  -> guest vCPU 恢复运行
  -> CreateContainer / runContainer
  -> guest envd 调度并监听 :49999
  -> TAP TCP 建连
  -> GET /health 返回
  -> Cubelet/CubeMaster 返回创建成功
```

early probe 实验将 HTTP probe 提前到 `runContainer` 之前启动，并在容器启动后等待 probe 结果，使 VM 恢复、容器启动与就绪探测尽量重叠。该实验用于判断原实现中的串行等待是否是主要耗时来源。

## 3. 分阶段性能数据

最新 early probe v2、delay=75ms、period=20ms 的 c50 profile 完成 500/500 次创建，无失败请求：

| 阶段 | avg (ms) | p95 (ms) |
|---|---:|---:|
| API 创建总延迟 | 199.38 | 308.12 |
| CubeMaster `sandbox-probe` | 178.84 | 290.00 |
| Cubelet `cubebox-service` | 185.57 | 294.81 |
| Cubelet `sandbox-probe` | 179.34 | 290.13 |
| Cubelet `sandbox-start` | 38.27 | 43.93 |
| Shim `CreatePodSandbox` | 28.25 | 33.00 |
| Shim `RestoreVm` | 8.49 | 10.00 |
| Shim `ResetVm` | 8.43 | 11.00 |
| Shim `CreateContainer` | 1.83 | 4.00 |

这里的 `sandbox-probe` 约 179ms 是从提前启动 probe 到首次收到健康响应的绝对就绪时间，其中包含 VM 恢复和容器启动。它与 `sandbox-start`、`CreatePodSandbox`、`RestoreVm` 等阶段相互重叠，不能直接相加。

数据说明：

- VMM 启动、RestoreVm 和 ResetVm 本身不是百毫秒级热点。
- 容器启动主路径通常在约 38ms 内完成。
- 容器启动完成后，仍有约百毫秒等待 guest/envd 真正可以响应健康检查。
- 提前并行 probe 明显改善了尾延迟，但没有把平均延迟降到 170ms 以下。

early probe v2 在 delay=75ms、period=20ms 下两轮 c50n500 的 avg 分别为 193.05ms 和 199.38ms，均值约 196.21ms。该结果说明串行调用顺序存在优化价值，但不是剩余延迟的主要根因。

## 4. TAP/HTTP 探针观测

对 503 个 TAP 的 HTTP readiness 流量抓包并关联实例后得到：

| 指标 | avg (ms) | p95 (ms) |
|---|---:|---:|
| TCP connect | 69.30 | 100.89 |
| HTTP request-to-response | 35.43 | 192.93 |
| 首个 SYN 到首个响应 | 92.85 | 295.39 |
| 首个 SYN 到客户端最终接受的响应 | 172.13 | 678.73 |

每个 TAP 平均发出 1.423 次请求。该结果说明 100ms client timeout 会取消部分最终能够成功返回的请求，但它不是唯一耗时来源。简单缩短或延长 timeout 会改变并发负载和重试行为，实际 A/B 均未改善平均延迟。

## 5. 已验证方案

| 实验 | 结果 | 判断 |
|---|---|---|
| probe period=20ms、timeout=20ms | avg 约 279.88ms | 重试风暴，负优化 |
| probe period=20ms、timeout=100ms | avg 约 246ms | 无平均延迟收益 |
| 延长 timeout 至 200/600ms | avg 约 257-263ms | 负优化 |
| 并发 hedged HTTP probe | avg 269.22ms | 请求放大，负优化 |
| 建连/响应 timeout 分离 | avg 251.99ms | 慢连接竞争加重 |
| guest 内 containerd exec `curl` | 500/500，avg 438.42ms | exec/agent/进程创建开销过大 |
| early HTTP probe 并行容器启动 | 两轮均值约 196.21ms | 改善尾延迟，平均值仍不足 |
| KVM halt poll 1ms/2ms | 无稳定收益 | 拒绝 |
| ready VM CPU shares 下调 | 无稳定收益 | 拒绝 |
| Cubelet GOMAXPROCS=64 | avg 198.22ms | 无收益 |
| GICv4-only | 三轮均值 201.47ms，后续发生主机异常重启 | 收益不足且不稳定 |

## 6. 已确认的历史热点

基础 OCI image 中的 `envd 0.5.13` 会每 50ms 轮询 CubeSandbox 未提供的 Firecracker MMDS。该轮询在已经 ready 的 VM 中持续产生 guest WFI、arch timer 和 virtio-net 中断，高密度并发时会干扰新恢复 VM 的就绪过程。

通过保留 Template 构建/ResetVm 所需的 MMDS 初始化行为，并在 guest 时钟恢复后停止无效轮询，稳定 c50n500 三轮均值从约 241.47ms 降至 202.72ms，改善约 16.05%。这是目前已经确认并保留的最大单项收益。

该热点消除后，host 整体 CPU 仍有大量空闲，但并发波次中 guest readiness 会出现明显抖动。这进一步指向 vCPU 唤醒、调度、虚拟定时器或中断注入路径，而不是普通的 host CPU 饱和或 OCI 冷启动。

## 7. 初步原因判断

当前结论是：

1. 就绪确认接口主要是在观察 guest 未就绪，而不是自身制造全部 179ms 延迟。
2. RestoreVm、ResetVm 和 CreateContainer 的直接执行时间较短，无法解释剩余百毫秒级等待。
3. 提前并行 probe 已经消除了大部分串行等待，但 c50 avg 仍约 196-199ms。
4. 剩余热点更可能位于 guest 恢复后到 `envd` 首次可服务之间的 vCPU 唤醒、guest 调度、虚拟定时器/中断及网络响应链路。
5. 该判断有端到端 profile、TAP 抓包、MMDS 热点对照和多组 probe A/B 支持，但尚未通过 guest 内部事件时间戳证明唯一根因。

## 8. 尚待闭合的内部时间线

下一步需要在同一实例上记录以下关键事件，并建立可关联的统一时间线：

```text
host 发起 RestoreVm/ResetVm
  -> KVM vCPU 首次重新进入 guest
  -> guest clock/timer 恢复
  -> guest agent Reset 完成
  -> CreateContainer / StartContainer 到达 guest
  -> envd 首次获得调度
  -> envd 完成 listen(:49999)
  -> guest 收到首个 SYN
  -> accept()/GET /health
  -> 首个健康响应离开 guest
```

建议优先验证：

- 新恢复 VM 的 vCPU runnable-to-running 延迟和 CPU migration 情况。
- 并发波次中 vCPU 是否集中竞争部分物理核或 NUMA 节点。
- guest timer 恢复与首次 envd 调度之间是否存在固定或长尾等待。
- TAP 首个 SYN 到达 guest 与 `envd accept()` 之间的差值。
- 对 vCPU affinity/调度策略做完全可回滚的 c50 A/B，并以 500/500 成功作为有效门禁。

## 9. 证据位置

- 分阶段分析：`artifacts/c50-optimization-20260727/early-external-http-probe-overlap/v2-delay75-period20/profile-c50-run1/analysis.json`
- 总优化报告：`CUBESANDBOX_C50_OPTIMIZATION_REPORT_20260727.md`
- HTTP 抓包实验：`artifacts/c50-optimization-20260727/tcp-pcap-observation/run1`
- MMDS 稳定实验：`artifacts/c50-optimization-20260727/remote-experiments/envd-mmds-prime`
