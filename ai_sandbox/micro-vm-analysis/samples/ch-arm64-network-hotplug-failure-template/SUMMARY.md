# Cloud Hypervisor ARM64 Hotplug 样本模板

本目录用于记录：

`Cloud Hypervisor ARM64 runtime add-net / hotplug 真实失败样本`

目标文档：[ARM64 网络下一批真实样本目标图](../../arm64-network-next-target-map.md)。

关联准样本：[Cloud Hypervisor ARM64 网络准样本：Runtime `add-net` / Hotplug 失败](../../../cloud-hypervisor/analysis/arm64-network-sample-hotplug-failure.md)。

## 1. 场景

- 日期：
- 节点架构：
- 是否运行期 `add-net`：
- API socket：
- net 参数：
- pci_segment：

## 2. 预期目标

固定问题停在：

1. API / `vm_add_net()`
2. `InvalidIommuHotplug`
3. guest convergence

## 3. 最终结论

- API 返回：
- BDF：
- guest 接口数量：
- 首个失败点：
- 归类层级：
