# Checklist

## 1. 采样前

- [ ] 确认节点是 `arm64`
- [ ] 确认本次场景是 runtime `add-net`
- [ ] 记录 `net` 参数和 `pci_segment`

## 2. 采样中

- [ ] 在 `commands.txt` 记录 `add-net` 请求命令
- [ ] 在 `api.txt` 保存请求参数和返回值
- [ ] 在 `guest.txt` 保留 `ip -o link | wc -l`
- [ ] 如可用，记录通过新网卡 IP 的 SSH 结果
- [ ] 在 `host.txt` 保留 API / tap / IOMMU 相关错误

## 3. 采样后

- [ ] 在 `classification.md` 判断失败停在 API、device-model 还是 guest convergence
- [ ] 如果命中 `InvalidIommuHotplug`，明确写出不是 guest 枚举问题
- [ ] 如果 API 成功但 guest 未收敛，明确写出 BDF 与 guest 侧症状
