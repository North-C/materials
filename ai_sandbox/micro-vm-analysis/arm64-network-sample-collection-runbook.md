# ARM64 网络样本采集 Runbook

本文承接 [ARM64 网络下一批样本优先级](./arm64-network-next-sample-priority.md) 和 [ARM64 网络测试与取证命令总表](./arm64-network-test-observation-command-matrix.md)。

前一篇已经回答：

下一批样本该先补哪家。

后一篇已经回答：

各项目先跑哪些命令最值。

本文继续把它们落成一份更直接的执行 runbook。

目标不是再解释框架。

目标是让后续真的去采集样本时，有一套统一的动作顺序和留档要求。

源码基线：当前工作树。

## 1. 核心结论

下一批 ARM64 网络样本采集，建议按下面顺序执行：

1. Kata Containers ARM64 失败样本
2. Cloud Hypervisor ARM64 失败样本
3. Firecracker ARM64 失败样本
4. CubeSandbox ARM64 中间层日志样本

每一家都遵循同一原则：

1. 先固定触发配置
2. 再固定最小命令组
3. 再保存最小日志与结果
4. 最后按失败原型归档

如果不按这个顺序，最后很容易只剩一段孤立日志，无法对回项目级文档。

## 2. 通用采集规则

每份样本，至少固定这四项。

1. 触发配置
   说明是普通启动、hotplug、restore、rollback 还是并发创建。
2. 最小命令输出
   来自项目对应的命令总表。
3. 原始错误文本
   不要只写概括语。
4. 所属层级与回看文档
   例如 host backend、guest 枚举、guest 收敛、restore 等。

如果缺这四项，后续很难把样本并入已有的矩阵和失败签名体系。

## 3. 第一优先：Kata ARM64 网络失败样本

Kata 当前最缺真实失败样本。

推荐最先采的不是“随机故障”。

而是最容易和现有失败原型对上的三类：

1. `unrecognised machinetype`
2. `Arm64 architecture does not support vIOMMU`
3. `interface not available` / `update interface request failed`

建议最小动作：

1. 固定 `HypervisorMachineType` 或 IOMMU 相关配置。
2. 保存 host runtime 日志。
3. 保存 guest `ip link`、`ip route`。
4. 保存完整错误文本。

最少应对齐到：

1. [ARM64 网络能力边界矩阵](../kata-containers/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../kata-containers/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../kata-containers/analysis/arm64-network-failure-prototypes.md)

## 4. 第二优先：Cloud Hypervisor ARM64 网络失败样本

Cloud Hypervisor 已经有比较成熟的命令锚点。

建议最先采的三类样本是：

1. `InvalidIommuHotplug`
2. `TapOpen/TapEnable/MultiQueueNoTapSupport`
3. `add_net()` 成功但 guest 没有真正激活设备

建议最小动作：

1. 保存 `NetConfig` 或 hotplug 参数。
2. 记录 host `ip link` / tap 检查。
3. 记录 guest `/proc/interrupts`、guest 设备可见性。
4. 保存错误文本或 `virtio-device activated` 缺失现象。

最少应对齐到：

1. [ARM64 网络能力边界矩阵](../cloud-hypervisor/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../cloud-hypervisor/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../cloud-hypervisor/analysis/arm64-network-failure-prototypes.md)

## 5. 第三优先：Firecracker ARM64 网络失败样本

Firecracker 目前的困难不是原型不清楚。

而是现成的 guest 观测和项目内样本锚点相对更少。

因此建议最先采的失败样本不要太复杂。

优先考虑：

1. `TapOpen`
2. `TapSetVnetHdrSize`
3. `VnetHeaderMissing`
4. restore 后网络异常

建议最小动作：

1. 固定 `host_dev_name` 与 net 配置。
2. 保存 Firecracker logger/metrics 输出。
3. 记录 host `ip link`。
4. 若场景涉及 MMDS，额外记录 metadata 访问结果。

最少应对齐到：

1. [ARM64 网络能力边界矩阵](../firecracker/analysis/arm64-network-capability-matrix.md)
2. [ARM64 网络观测指南](../firecracker/analysis/arm64-network-observation-guide.md)
3. [ARM64 网络失败原型](../firecracker/analysis/arm64-network-failure-prototypes.md)

## 6. 第四优先：CubeSandbox ARM64 中间层日志样本

CubeSandbox 不是没有样本。

它已经有：

1. 平台级成功样本
2. `tap fd unavailable` 真实故障线索
3. `quickcheck`、`check-procs`、`collect-logs` 三类现成入口

因此它现在最值得采的，不是“再来一份平台成功样本”。

而是补一份带 `collect-logs.sh` 产物的中间层日志样本。

建议优先覆盖：

1. `tap fd unavailable`
2. `newTap attach filter failed`
3. `wait a pci`
4. `Missing GicV3Its snapshot`

建议最小动作：

1. 跑一轮最小 ARM64 场景或并发场景。
2. 执行 `quickcheck.sh`。
3. 执行 `cube-diag/check-procs.sh`。
4. 执行 `collect-logs.sh --module network-agent --module cubeshim --module cubevmm --module runtime --module dmesg --module env`。

最少应对齐到：

1. [ARM64 网络观测与取证指南](../CubeSandbox-sandbox-clone/analysis/arm64-network-observation-guide.md)
2. [ARM64 日志采集缺口与补齐路径](../CubeSandbox-sandbox-clone/analysis/arm64-log-collection-gap.md)
3. [ARM64 日志源映射](../CubeSandbox-sandbox-clone/analysis/arm64-log-source-map.md)
4. [ARM64 网络失败原型](../CubeSandbox-sandbox-clone/analysis/arm64-network-failure-prototypes.md)

## 7. 每份样本建议产物

建议每份样本都至少保留这几个文件：

1. `README.md` 或 `SUMMARY.md`
   说明场景、配置、结论。
2. `commands.txt`
   记录实际执行命令。
3. `stdout-stderr.log`
   保留主要错误文本。
4. `guest-observation.txt`
   记录 guest 侧 `ip link` / `ip route` / `/proc/interrupts` 等输出。
5. `classification.md`
   用现有失败原型给出归类结果。

没有 `classification.md` 的样本，后续通常还要重看一遍源码，成本很高。

## 8. 建议目录命名

为了后续归档一致，建议统一命名为：

```text
analysis/samples/<project>-arm64-network-<scenario>-<date>/
```

例如：

```text
analysis/samples/kata-arm64-network-viommu-20260618/
analysis/samples/ch-arm64-network-iommu-hotplug-20260618/
analysis/samples/fc-arm64-network-tapopen-20260618/
analysis/samples/cubesandbox-arm64-network-tap-fd-unavailable-20260618/
```

这种命名方式足够短，也方便后面继续做总索引。

## 9. 结论

现在这条 ARM64 网络研究线已经具备：

1. 边界矩阵
2. 观测指南
3. 失败原型
4. 命令总表
5. 样本优先级

后续真正要做的，不再是加第六层抽象。

而是严格按这份 runbook 去补真实样本。 
