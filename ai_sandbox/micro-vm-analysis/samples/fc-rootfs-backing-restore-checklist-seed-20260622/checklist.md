# Checklist

## A. restore 调用

- [ ] 记录 snapshot / restore 的命令或 API 请求
- [ ] 记录 restore 返回成功/失败
- [ ] 记录 snapshot 来源与 disk/pmem 相关配置

## B. rootfs 表达

- [ ] 记录 root 是否来自 block 还是 pmem
- [ ] 记录 `root=/dev/vda` / `root=PARTUUID=...` / `root=/dev/pmemX`
- [ ] 记录是否存在 block root 与 pmem root 的冲突风险

## C. backing file 一致性

- [ ] 记录 backing file / disk path / pmem path
- [ ] 记录 restore 后这些路径是否仍可用
- [ ] 区分“VMM state 恢复成功”与“host backing file 语义仍成立”

## D. guest 可见性

- [ ] 记录 guest 是否重新看到 block / pmem 设备
- [ ] 记录 rootfs 是否真的可用
- [ ] 明确问题停在 restore 层还是 guest rootfs 层
