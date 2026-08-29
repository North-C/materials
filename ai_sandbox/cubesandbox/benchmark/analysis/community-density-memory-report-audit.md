# CubeSandbox 社区单机密度内存表审计

## 结论

社区表中的“单 VM 均摊内存上升”不是 CoW 失效证据。

表格测量的是整机 `MemAvailable` 差值除以实例数，不是 Snapshot 共享页的 PSS，也不是 VMM RSS。

按页面显示值重算，新增实例的边际成本并未持续加速。第一批约为 21.5 MiB/实例，后续三段约为 25.1、26.6、26.6 MiB/实例。

更准确的描述是：第一批结果较低，累计平均值逐渐向约 26 MiB 的后续边际成本收敛。

## 1. 官方数据与公式

[官方报告 §3.3](https://docs.cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)给出的环境是 375 GiB BMI5 裸金属、2 vCPU/2 GiB Sandbox、XFS CoW reflink。

测试顺序是清空机器后累计创建 Sandbox，并在 100、300、500、1000 个存活实例时执行一次 `free -h`。

| 存活实例 N | `free available` | 报告均摊 |
|---:|---:|---:|
| 0 | 359.5 GiB | — |
| 100 | 357.4 GiB | ~21.5 MB |
| 300 | 352.5 GiB | ~23.8 MB |
| 500 | 347.3 GiB | ~25.0 MB |
| 1000 | 334.3 GiB | ~25.7 MB |

报告写出的公式是：

```text
单 VM 均摊开销 = (当前 used - 基线 used) / N
```

表内保存的是 `available`。当 `MemTotal` 不变时，等价公式是：

```text
A(N) = [MemAvailable(0) - MemAvailable(N)] / N
```

这个量应称为“整机 `MemAvailable` 摊销”，不能称为 Sandbox RSS。

## 2. 从累计平均改看边际成本

累计平均容易掩盖不同批次的真实斜率。相邻两点的边际成本为：

```text
M(N1,N2) = [MemAvailable(N1) - MemAvailable(N2)] / (N2-N1)
```

按页面显示值换算为 MiB：

| 区间 | Available 下降 | 新增实例 | 边际 MiB/实例 |
|---:|---:|---:|---:|
| 0→100 | 2.1 GiB | 100 | 21.504 |
| 100→300 | 4.9 GiB | 200 | 25.088 |
| 300→500 | 5.2 GiB | 200 | 26.624 |
| 500→1000 | 13.0 GiB | 500 | 26.624 |

后三段接近稳定。累计值继续上升，是因为较高的后续边际成本逐步提高了全体实例的累计平均。

因此，表格不支持“实例越多，单实例成本持续恶化”的强结论。

## 3. 显示精度限制

页面只保留一位小数 GiB。每个 `available` 显示值最多有约 ±0.05 GiB 舍入误差。

两个点相减时，最坏差值误差约为 ±0.1 GiB。折算到累计均摊：

| N | 最坏舍入误差 |
|---:|---:|
| 100 | ±1.024 MiB/实例 |
| 300 | ±0.341 MiB/实例 |
| 500 | ±0.205 MiB/实例 |
| 1000 | ±0.102 MiB/实例 |

页面显示值不能精确复算 23.8 和 25.7。原始 KiB 数据或未舍入值没有随报告公开。

报告列名使用 MB，但从 GiB 换算更接近 MiB。做跨报告比较时必须统一单位。

## 4. 这张表证明了什么

它证明了在该硬件、Template、时间和轻载条件下，2 GiB Guest 配置没有转化为 2 GiB Host 实占。

它还表明 1000 个轻载实例的整机可用内存下降仍处于约 25 GiB 量级。

这与 Snapshot 文件共享、按需触页和写时复制的总体设计一致。

## 5. 这张表没有证明什么

它没有保存以下证据：

- 固定 settle window 和多时间点样本；
- 同一密度的独立重复轮次；
- VMM/CubeShim PSS、USS、Private/Shared；
- Sandbox cgroup 的 anon/file/kernel；
- `Cached`、`Slab`、`PageTables`、`KernelStack`；
- page fault、磁盘 I/O、PSI、NUMA；
- 清理后的回收曲线；
- runtime commit、完整命令输出和原始 KiB。

因此，不能从四个整机单点判断增长来自私有脏页、内核对象、Page Cache、控制面，还是自然漂移。

也不能据此判断 CoW 是否生效。验证 CoW 需要观察共享 Snapshot mapping 的 PSS/USS，而不是只看 `free -h`。

## 6. 累计顺序带来的混杂

测试从 100 累计到 1000，没有在每个点重新回到 N=0。

较高密度点中的早期 Sandbox 已运行更久。Guest 后台活动可能继续 fault 页面，并将写入页转换为私有匿名页。

Page Cache、dentry/inode、服务 allocator 和控制面缓存也可能沿顺序保留高水位。

密度 N 与实验经过时间、实例年龄和缓存热度相关。单点 `MemAvailable` 无法分离这些变量。

## 7. 更可靠的结论写法

推荐将社区结果描述为：

> 在报告环境下，轻载 2 vCPU/2 GiB Sandbox 的整机 `MemAvailable` 累计摊销约为 21–26 MiB/实例。第一批较低，后续边际成本约为 25–27 MiB/实例。现有证据不足以解释分项来源。

不推荐写成：

> 每个 Sandbox RSS 是 25 MB。

也不推荐写成：

> 均摊上升证明 CoW 共享随密度失效。

## 8. 后续验证入口

对象与记账模型见 [CubeSandbox CoW 与宿主机内存记账模型](cubesandbox-cow-memory-accounting-model.md)。

可复现实验方法见 [CubeSandbox 单机密度内存测量指南](cubesandbox-memory-density-measurement-guide.md)。

## 参考资料

- [CubeSandbox 核心操作性能基准测试报告](https://docs.cubesandbox.com/zh/blog/posts/2026-06-01-cubesandbox-perf-benchmark.html)
- [CubeSandbox 沙箱资源指标](https://docs.cubesandbox.com/zh/guide/resource-metrics.html)
- [Linux 6.6 `/proc/meminfo`](https://docs.kernel.org/6.6/filesystems/proc.html#meminfo)
