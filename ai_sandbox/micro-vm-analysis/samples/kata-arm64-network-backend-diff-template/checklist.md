# Checklist

## 1. 采样前

- [ ] 确认节点是 `arm64`
- [ ] 确认本次目标 backend：`qemu` / `cloud-hypervisor` / `dragonball`
- [ ] 确认是否走 hotplug
- [ ] 确认 machine / vIOMMU 不是本次目标

## 2. 采样中

- [ ] 在 `commands.txt` 记录触发命令
- [ ] 在 `SUMMARY.md` 填写 backend、host dev name、guest mac、queue 参数
- [ ] 在 `host.txt` 保留原始错误文本
- [ ] 若进入 guest，在 `guest.txt` 保留 `ip link` / `ip route`

## 3. 采样后

- [ ] 在 `classification.md` 写清 backend 名
- [ ] 判断是否命中 `QMP not initialized` / `open named tuntap` / `insert network device`
- [ ] 说明为什么不是 machine / vIOMMU 更早失败
- [ ] 说明为什么不是 guest discovery 更后失败
