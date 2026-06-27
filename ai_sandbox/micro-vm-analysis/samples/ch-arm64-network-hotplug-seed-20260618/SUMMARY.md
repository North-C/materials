# Cloud Hypervisor ARM64 `add-net` / Hotplug 样本种子

本目录是一个准实样示范包。

它不是基于真实失败日志。

它直接把项目内 `_test_net_hotplug()` 的结构，落成一个可复用样本目录。

关联准样本：[Cloud Hypervisor ARM64 网络准样本：Runtime `add-net` / Hotplug 失败](../../../cloud-hypervisor/analysis/arm64-network-sample-hotplug-failure.md)。

## 1. 场景

- 日期：`2026-06-18`
- 节点架构：`arm64`
- 场景类型：runtime `add-net`
- API：`add-net`
- 目标：验证 API / BDF / guest convergence 三层拆分

## 2. 当前状态

这不是失败样本。

它是一个把测试包装直接转换成样本结构的种子包。

后续只要拿到真实失败输出，就可以直接把这份目录复制成真实样本。

## 3. 预期归类

- API 层失败：`Error when adding new network device to the VM`
- device-model 层失败：`InvalidIommuHotplug`
- guest 收敛失败：API 返回 BDF，但 guest 接口数未达预期
