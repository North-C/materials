# Fill Guide

1. 先读 `baseline.txt`，确认本 seed 目前已有的 codepath-derived 基线片段。
2. 再在 `commands.txt` 写 restore / resume / set_fs / add_device 的实际入口命令，并在 `api.txt` 填 request / response。
3. 在 `logs.txt` 先登记 CubeShim、hypervisor VMM、backend、agent、Cubelet/network-agent 等日志位置。
4. 再在 `host.txt` 记录控制面返回、`VsockServerReady` / `VmShutdown` / probe 路径，以及 backend 是否重绑成功。
5. 然后在 `host.txt` 或 `logs.txt` 写 `FsEvent`、`back_state`、worker 唤醒、TAP/tap fd 重绑等关键证据。
6. 在 `guest.txt` 记录 agent 是否看到设备、uevent 等待是否通过、mount / net / ready 是否真正完成。
7. 最后在 `classification.md` 判断问题更像：
   - control plane reached VMM but worker not awakened
   - backend rebound incomplete
   - guest agent visibility incomplete
   - ready convergence incomplete
8. 如果准备把本 seed 升成 `real`，最后再核对：
   - 它不是纯控制面失败
   - 它不是纯成功基线
   - 它已经同时覆盖控制面成功、worker/backend 推进、guest-visible 收敛失败
9. 如果已经拿到一整包日志，先对照：
   - `minimum-log-bundle.txt`
   - `decision-table.txt`
   - `bundle-template.txt`
   - `bundle-skeleton.txt`
   再决定是继续留在 seed，还是升级成新的 failure `real`。
10. 如果当前还没有真实 request dump，先用：
    - `restore-request.template.json`
    - `resume-from-snapshot-request.template.json`
    - `set-fs-request.template.json`
    - `add-device-request.template.json`
    固定字段结构，但不要把它们当成真实证据。
