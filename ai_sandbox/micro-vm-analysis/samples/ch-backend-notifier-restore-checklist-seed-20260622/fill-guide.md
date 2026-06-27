# Fill Guide

1. 先读 `baseline.txt`、`event.json.sample`、`snapshot-layout.txt`，确认本 seed 目前已有的 doc/test-derived 基线片段。
2. 再在 `commands.txt` 写实际使用的 snapshot / restore 命令，并在 `api.txt` 补 request / response / source_url / destination_url。
3. 在 `logs.txt` 先登记事件日志、VMM 日志、backend 日志、controller 日志的真实路径；如果真实输出结构和 `event.json.sample` 不一致，要显式记下来。
4. 再在 `host.txt` 写 restore 是否成功、是否出现 `restored` 信号，以及 backend/socket/fd 是否重连。
5. 然后在 `host.txt` 或 `logs.txt` 中写 `set_vring_call` / `set_vring_kick` / `set_config_call`、MSI-X、GIC/IOAPIC 的关键证据。
6. 在 `guest.txt` 记录 guest 是否重新看到 disk/fs/net/pmem，以及是否真正可访问。
7. 最后在 `classification.md` 判断问题更像：
   - transport restore incomplete
   - backend reconnect incomplete
   - route/controller restore incomplete
   - guest-visible state not yet proven
8. 如果准备把本 seed 升成 `real`，再对照：
   - `evidence-targets.txt`
   - `collection-runbook.md`
   确认已经同时覆盖 restore success、transport/notifier、controller restore、guest result 四层证据。
9. 如果已经拿到一整包日志，先对照：
   - `minimum-log-bundle.txt`
   - `decision-table.txt`
   - `bundle-template.txt`
   - `bundle-skeleton.txt`
   再决定是继续留在 seed，还是升级成新的 `real`。
10. 如果当前还没有真实 request dump，先用：
    - `snapshot-request.template.json`
    - `restore-request.template.json`
    固定字段结构，但不要把它们当成真实证据。
