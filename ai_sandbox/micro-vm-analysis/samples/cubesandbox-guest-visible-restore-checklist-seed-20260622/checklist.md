# Checklist

## A. 控制面

- [ ] 记录 `VmRestore` / `VmResumeFromSnapshot` / `VmSetFs` / `VmAddDevice` 请求
- [ ] 记录请求返回结果
- [ ] 记录是否有 `NotifyEvent` / ready 相关异常
- [ ] 记录是否出现 `VsockServerReady`、`VmShutdown` 或 fallback 到 vsock probe
- [ ] 区分是 restore 调用失败，还是 restore 成功后 guest-visible state 未收敛

## B. 后端重绑

- [ ] 记录 TAP / tap fd 是否重新取得
- [ ] 记录 fs backend / `back_state` 是否重新应用
- [ ] 记录 pending message / worker 唤醒证据
- [ ] 记录当前节点资源是否真的重绑成功，而不是只在控制面返回成功
- [ ] 记录 `VmSetFs` 后是否看到 `FsEvent` / worker 处理痕迹

## C. worker / interrupt

- [ ] 记录 net/fs worker 是否启动
- [ ] 记录 queue/irq/notifier 是否至少看起来正常
- [ ] 区分“VMM 层失败”与“平台闭环失败”
- [ ] 区分“worker 未唤醒”与“worker 已唤醒但 guest 不可见”

## D. guest-visible state

- [ ] 记录 guest agent 是否看到设备
- [ ] 记录 mount / 网络 / ready 是否完成
- [ ] 明确最终问题是否停在 guest-visible state 收敛
- [ ] 记录 block/pmem/pci 设备的 uevent 等待是否通过
- [ ] 记录共享目录或 rootfs 是否真的 mount 成功
