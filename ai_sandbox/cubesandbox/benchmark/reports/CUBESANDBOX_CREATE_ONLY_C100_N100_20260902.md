# CubeSandbox create-only c100/n100 测试记录（2026-09-02）

## 结论

本次 `cube-bench` 单轮 `create-only` 测试完成 100/100 次创建，命令报告成功率
100.0%、吞吐 255.98 sandboxes/s，CREATE 平均延迟 164.1 ms、P95 228.5 ms、
P99 229.7 ms。

这是一次成功的高并发创建观测，但当前证据只有终端汇总输出，缺少原始 JSON、逐请求日志、
Template 资源与镜像身份、测试前后资源计数、清理和 cooldown 记录。因此该结果不能单独作为
跨版本性能对比、完整生命周期性能或可重复性验收结论。

## 测试身份

| 项目 | 值 |
|---|---|
| 命令 | `./cube-bench -c 100 -n 100 -w 3 -m create-only` |
| Template | `tpl-fb2c41599656413baa061a85` |
| API URL | `http://127.0.0.1:3000` |
| 并发数 | 100 |
| 正式请求数 | 100 |
| Warmup rounds | 3 |
| 模式 | `create-only` |
| 主机标识 | `localhost.localdomain` |
| `cube-bench` Go 运行时 | `go1.25.0` |
| 工具记录时间 | `2026-09-02 07:39:40 UTC` |
| Asia/Shanghai 时间 | `2026-09-02 15:39:40 +08:00` |
| 原始证据 | 用户提供的终端输出；未提供原始日志或 JSON 文件 |

尚未从本次输出确认的环境信息：

- CubeSandbox 版本与 commit；
- Host 架构、内核、CPU、NUMA、内存和存储；
- Template 的 CPU、内存、镜像 tag/digest、guest/agent 版本和 replica 状态；
- 测试前后 Sandbox、CubeShim 和 runtime task 计数；
- warmup 的逐轮结果及其是否完全排除在正式统计之外；
- 测试后的精确清理和 cooldown 状态。

## 汇总结果

| 指标 | 结果 |
|---|---:|
| 完成请求 | 100 / 100 |
| 成功请求 | 100 |
| 失败请求 | 0 |
| 成功率 | 100.0% |
| 总耗时 | 0.39 s |
| 吞吐 | 255.98 sandboxes/s |
| CREATE min | 75.8 ms |
| CREATE avg | 164.1 ms |
| CREATE std | 50.0 ms |
| CREATE P50 | 161.0 ms |
| CREATE P90 | 222.8 ms |
| CREATE P95 | 228.5 ms |
| CREATE P99 | 229.7 ms |
| CREATE max | 232.4 ms |
| DELETE avg | 0 ms |
| 工具评分 | `B`（显示口径：`P99=230ms, success=100.0%`） |

`100 / 0.39` 根据界面四舍五入后的总耗时计算约为 256.4/s，与工具报告的
255.98/s 接近；应以工具使用未取整时长计算出的 255.98/s 为记录值。`DELETE avg=0 ms`
来自 `create-only` 模式，不代表删除性能为零，也不构成删除路径验证。

## CREATE 延迟分布

下表逐项转录终端分布，样本数合计 100，与正式请求分母一致。

| 延迟区间 | 样本数 | 占比 |
|---:|---:|---:|
| 76–89 ms | 8 | 8.0% |
| 89–102 ms | 10 | 10.0% |
| 102–115 ms | 7 | 7.0% |
| 115–128 ms | 2 | 2.0% |
| 128–141 ms | 7 | 7.0% |
| 141–154 ms | 7 | 7.0% |
| 154–167 ms | 12 | 12.0% |
| 167–180 ms | 4 | 4.0% |
| 180–193 ms | 3 | 3.0% |
| 193–206 ms | 8 | 8.0% |
| 206–219 ms | 18 | 18.0% |
| 219–232 ms | 14 | 14.0% |
| **合计** | **100** | **100.0%** |

终端的 latency timeline 从约 76 ms 上升到约 232 ms。它说明按工具时间桶聚合后的延迟
随测试推进上升，但仅凭该可视化无法区分并发排队、服务端处理、客户端调度或其它原因，
不能据此给出根因结论。

## 结果边界

### 已验证事实

- `cube-bench` 报告 100 个正式请求全部完成且错误数为 0。
- 工具报告吞吐 255.98 sandboxes/s 和上述 CREATE 延迟统计。
- 终端分布的 12 个区间合计 100 个样本。

### 合理解读

- 在该 Template、该 API 端点和该次运行条件下，100 并发的创建请求没有出现工具可见失败。
- P90、P95、P99 和 max 相距较小，尾部成功样本集中在约 223–232 ms。

### 尚不能确认

- `create-only` 结果不证明 Sandbox 已完成业务 readiness、guest 内命令执行或网络可用。
- 本次没有 DELETE 样本，不能推导删除、Rollback、Clone、Pause/Resume 或完整生命周期性能。
- 没有独立复测、冷却和环境身份，不能与其它日期、机器、内核或 CubeSandbox 版本直接比较。
- 工具给出的 `B` 是内置评分，不应在缺少评分规则和验收阈值时替代正式结论。

## 后续正式取数所需证据

后续若将该档位升级为正式性能数据，至少应同步保存：

1. `cube-bench` 原始日志和机器可读 JSON，以及两者 SHA256；
2. Host、CubeSandbox、Template、镜像 digest、guest/agent 和资源规格身份；
3. 每个 warmup round 与正式请求的清晰边界；
4. 测试前、测试后、清理后和 cooldown 后的 Sandbox/CubeShim/task 计数；
5. 相同环境下至少 3 次独立正式运行，并报告中位数、离散度和完整成功率分母。
