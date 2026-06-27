# Checklist

## A. host 侧资源翻译

- [ ] 记录 `handler_rootfs()` 路径
- [ ] 记录 `handler_volumes()` 路径
- [ ] 记录生成的是 share-fs 还是 block storage

## B. request 传递

- [ ] 记录 `CreateContainerRequest.storages`
- [ ] 记录传入 guest 的 storage driver / source / mount_point
- [ ] 如果没有新的 request dump，至少记录是否已使用本目录 `request-samples.txt` 作为 request-side baseline
- [ ] 区分 device 已加进 VM 与 storage 已传给 agent

## C. guest 落地

- [ ] 记录 `add_storages()` 是否执行
- [ ] 记录 `mount_from()` 是否执行
- [ ] 记录最终 mount 是否成功

## D. guest-visible state

- [ ] 记录 rootfs / volume 是否真正可用
- [ ] 记录问题停在 hypervisor、agent storage，还是 guest mount 收敛
