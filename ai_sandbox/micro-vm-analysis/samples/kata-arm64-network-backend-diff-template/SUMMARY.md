# Kata ARM64 Backend 差异样本模板

本目录用于记录：

`Kata ARM64 backend 差异真实样本`

目标文档：[ARM64 网络下一批真实样本目标图](../../arm64-network-next-target-map.md)。

关联准样本：[Kata ARM64 网络准样本：Backend 差异失败](../../../kata-containers/analysis/arm64-network-sample-backend-diff.md)。

## 1. 场景

- 日期：
- 节点架构：
- backend：`qemu` / `cloud-hypervisor` / `dragonball`
- 是否走 hotplug：
- host dev name：
- guest mac：
- queue 参数：

## 2. 预期目标

固定 backend-specific 错误，并排除：

1. machine / vIOMMU 更早失败
2. guest discovery 更后失败

## 3. 最终结论

- 首个失败点：
- 对应签名：
- 归类层级：
- 回看文档：
