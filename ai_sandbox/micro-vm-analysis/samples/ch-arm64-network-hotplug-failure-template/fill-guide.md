# Fill Guide

1. 先在 `api.txt` 填原始 `add-net` 参数和返回值。
2. 再在 `guest.txt` 填 guest 接口数量和新路径可达性。
3. 然后在 `host.txt` 写 host/VMM 错误。
4. 最后在 `classification.md` 判断问题停在：
   - API / `vm_add_net()`
   - `InvalidIommuHotplug`
   - guest convergence
