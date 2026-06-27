# Checklist

## A. restore 调用

- [ ] 记录 restore 命令或 API 请求
- [ ] 记录 restore 返回成功/失败
- [ ] 记录 source_url / snapshot 目录信息
- [ ] 记录 restore 前 VM 是否已处于 paused / snapshot 已生成
- [ ] 记录是否出现 `event":"restored"` 或等价恢复成功信号

## B. transport / backend

- [ ] 记录 `VirtioPciDevice` / transport 相关日志
- [ ] 记录 vhost-user 或 vDPA backend 连接信息
- [ ] 记录 `set_vring_call` / `set_vring_kick` / `set_config_call` 相关证据
- [ ] 记录 backend/socket 与 `/dev/vhost-vdpa-*` 是否真的可用
- [ ] 记录 restore 后 queue / vring / notifier 是否重建

## C. controller / route

- [ ] 记录 MSI-X / route / mask 相关日志或观测
- [ ] ARM64：记录 GIC restore 相关信息
- [ ] x86_64：记录 IOAPIC restore 相关信息
- [ ] 明确 backend 正常但 guest 无中断时，问题是否落在 route/controller restore
- [ ] 区分 transport restore 不完整 与 controller restore 不完整

## D. guest 可见性

- [ ] 记录 guest 中是否重新看到设备
- [ ] 记录 guest 中断或数据面是否恢复
- [ ] 明确“问题停在 restore 层”还是“已进入 guest 配置层”
- [ ] 对 fs 路径，记录 guest 是否真的能访问共享目录
- [ ] 对 disk/pmem 路径，记录 guest 是否真的重新看到对应设备节点
