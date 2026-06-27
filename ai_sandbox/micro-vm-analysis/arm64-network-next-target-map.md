# ARM64 网络下一批真实样本目标图

本文承接 [ARM64 网络准样本覆盖矩阵](./arm64-network-sample-coverage-matrix.md)、[ARM64 网络下一批样本优先级](./arm64-network-next-sample-priority.md) 和 [ARM64 网络样本采集 Runbook](./arm64-network-sample-collection-runbook.md)。

前面三篇已经回答了：

1. 当前哪些层已有准样本
2. 四个项目下一批样本的总体优先级
3. 采集时的一般动作顺序

本文继续往前压一层。

它不再讨论“哪家更优先”这种泛化问题。

它直接回答：

下一批真实样本，具体该采哪几个场景。

源码基线：当前工作树。

## 1. 核心结论

当前四个项目里，下一批最值得采的不是任意 ARM64 网络失败。

而是四个已经被准样本或真实案例明确圈出来的具体场景：

1. Kata：backend 差异真实样本
2. Cloud Hypervisor：runtime `add-net` / hotplug 真实失败样本
3. Firecracker：guest visibility / interrupt visibility 真实失败样本
4. CubeSandbox：`collect-logs.sh` 中间层日志样本

这四个场景之所以值得优先采，不是因为它们听上去复杂。

而是因为它们正好分别补齐了当前矩阵里最有价值的空洞。

## 2. 目标一：Kata backend 差异真实样本

Kata 当前已经有三份准样本：

1. machine / vIOMMU 早失败
2. backend 差异失败
3. guest discovery 失败

其中真正最值得先落成真实样本的，是 backend 差异这一份。

因为它能把同样的 ARM64 失败，明确分到：

1. QEMU `QMP not initialized`
2. Cloud Hypervisor `open named tuntap`
3. Dragonball `insert network device`

源码依据：[Kata backend 差异失败](../kata-containers/analysis/arm64-network-sample-backend-diff.md)。

### 目标样本名

`kata-arm64-network-backend-diff-<date>`

### 最小成功标准

1. 明确 backend 名
2. 保留原始错误文本
3. 能排除 machine/vIOMMU 更早失败
4. 能排除 guest discovery 更后失败

### 为什么它排第一

因为它最能验证 Kata 这条线的三段式归类是否真的可用。

## 3. 目标二：Cloud Hypervisor `add-net` / hotplug 真实失败样本

Cloud Hypervisor 当前已经有：

1. 启动期多网卡准样本
2. PCI MSI 准样本
3. runtime `add-net` / hotplug 准样本
4. restore 后网络异常准样本

其中最值得先做成真实样本的，不是 restore。

而是 `add-net` / hotplug。

原因很直接：

它最容易把：

1. `vm_add_net()` API 层
2. `InvalidIommuHotplug`
3. guest convergence

这三层明确拆开。

源码依据：[Cloud Hypervisor hotplug 准样本](../cloud-hypervisor/analysis/arm64-network-sample-hotplug-failure.md)。

### 目标样本名

`ch-arm64-network-hotplug-failure-<date>`

### 最小成功标准

1. 保存 `add-net` 请求参数
2. 保存 API 返回值或错误文本
3. 保存 guest `ip -o link | wc -l`
4. 能判断问题停在 API、device-model 还是 guest convergence

### 为什么它排第二

因为它的测试包装已经很成熟，转成真实样本的成本最低。

## 4. 目标三：Firecracker guest visibility / interrupt visibility 真实失败样本

Firecracker 当前准样本已经补齐到四类：

1. TAP / vnet header 早失败
2. MMDS / rate limiter 伪失败
3. restore 后网络异常
4. guest visibility / interrupt visibility

下一份最值的真实样本，不该再回去做 `TapOpen`。

而应该做：

host 路径正常，但 guest 没真正跑起设备

也就是 `guest visibility / interrupt visibility` 这条线。

源码依据：[Firecracker guest visibility 准样本](../firecracker/analysis/arm64-network-sample-guest-visibility.md)。

### 目标样本名

`fc-arm64-network-guest-visibility-<date>`

### 最小成功标准

1. 证明 `TapOpen` / `TapSetVnetHdrSize` 没失败
2. 排除 MMDS / limiter 伪失败
3. 保留 guest 侧“不具备网络可用性”的证据
4. 最终归到 guest visibility / interrupt visibility

### 为什么它排第三

因为它最能补 Firecracker 当前从 host 数据面到 guest 可见性的真实证据缺口。

## 5. 目标四：CubeSandbox 中间层日志样本

CubeSandbox 的情况和前三家不一样。

它已经有：

1. 平台级真实样本
2. `tap fd unavailable` 真实案例

所以它下一份最值得做的，不是“再来一份成功样本”。

而是带 `collect-logs.sh` 产物的中间层日志样本。

最值得围绕的还是：

`tap fd unavailable`

因为这条线已经有真实案例，也最容易验证采集链是否完整。

源码依据：[CubeSandbox `tap fd unavailable` 故障案例](../CubeSandbox-sandbox-clone/analysis/tap-fd-unavailable-case-study.md)。

### 目标样本名

`cubesandbox-arm64-network-midlogs-<date>`

### 最小成功标准

1. 执行 `collect-logs.sh`
2. 保留 `network-agent`、`cubeshim`、`cubevmm`、`runtime`、`dmesg`、`env`
3. 让样本能直接对应到既有故障案例

### 为什么它排第四

因为它缺的是中间层取证，不是故障定义本身。

## 6. 四个目标的最小对照表

| 优先级 | 项目 | 目标场景 | 目标样本名模板 | 最小成功标准 |
|---|---|---|---|---|
| 1 | Kata | backend 差异失败 | `kata-arm64-network-backend-diff-<date>` | backend + 原始错误 + 正确归层 |
| 2 | Cloud Hypervisor | runtime `add-net` / hotplug 失败 | `ch-arm64-network-hotplug-failure-<date>` | API + BDF/错误 + guest convergence |
| 3 | Firecracker | guest visibility / interrupt visibility | `fc-arm64-network-guest-visibility-<date>` | 排除早失败/伪失败 + 保留 guest 症状 |
| 4 | CubeSandbox | 中间层日志样本 | `cubesandbox-arm64-network-midlogs-<date>` | `collect-logs.sh` 产物完整 |

## 7. 这张目标图应该怎么用

后续如果继续研究，不建议再从“哪个项目更重要”重新讨论。

而是直接从这四个目标里选一个执行。

使用顺序建议如下：

1. 先看当前能不能拿到对应环境
2. 再按这张图选一个目标
3. 最后回到对应项目的准样本和 runbook 去采

这样可以避免继续在优先级和抽象层打转。

## 8. 结论

现在这条 ARM64 网络研究线，已经不再缺“研究方向”。

它缺的是：

把下一批真实样本真正做出来。

这张目标图的作用，就是把“下一步”收敛到四个可执行场景。
