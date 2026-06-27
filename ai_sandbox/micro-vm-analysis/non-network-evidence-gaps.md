# 非网络当前证据缺口总表

本文不是新的专题分析。

它只回答一个现实问题：

按当前工作树，non-network 三条横线里，哪些证据已经有，哪些还缺。

承接文档：

- [非网络横线样本资产矩阵](./non-network-sample-asset-matrix.md)
- [非网络下一批真实样本目标图](./non-network-next-target-map.md)
- [非网络样本采集 Runbook](./non-network-sample-collection-runbook.md)

## 1. 核心结论

当前 non-network 线已经不缺：

1. 分析结构
2. seed 目录骨架
3. request-side baseline
4. bundle / decision / upgrade 规则

当前真正缺的是：

- 新的、同一次 attempt 的 host/runtime/guest 运行证据

## 2. 当前缺口一览

| 项目 | 当前最强证据 | 当前最缺的真实证据 |
|---|---|---|
| CubeSandbox guest-visible | codepath + request sample + 完整升级护栏 | 同一 attempt 中的控制面成功、worker推进、guest-visible失败 |
| Kata storage | codepath + request-shaped JSON sample | guest `add_storages()` / `mount_from()` 运行证据 + final usability |
| Firecracker rootfs/backing | codepath + parser/test-derived request sample | 真实 restore 请求 + backing consistency + guest-visible/rootfs 结果 |
| Cloud Hypervisor backend/notifier | doc/test-derived baseline + documented request sample | failure-side runtime bundle，含 transport/notifier/controller + guest result |

## 3. 当前最接近新 `real` 的目标

按当前工作树状态：

1. CubeSandbox guest-visible failure `real`
2. Kata storage convergence `real`
3. Firecracker rootfs/backing `real`
4. Cloud Hypervisor backend/notifier failure `real`

这不是项目重要性排序。

它只表示：

谁离“只差一包新证据就能升级”最近。

## 4. 不建议重复做的事

除非有新的运行证据进入工作树，否则不建议继续重复：

1. 再次全仓搜索相同关键字
2. 再补同类框架说明
3. 再拆更多 seed 元数据

这些动作现在的边际收益已经很低。

## 5. 推荐下一步

如果下一轮有新证据：

1. 先用 [非网络证据包记录模板](./non-network-evidence-bundle-template.md) 记账
2. 再按 [非网络样本采集 Runbook](./non-network-sample-collection-runbook.md) 选 seed
3. 最后按对应 seed 的 `decision-table` 判断能否升级

如果下一轮没有新证据：

最合理的动作通常不是继续补分析，而是停止在此处，等待新的运行时证据进入工作树。
