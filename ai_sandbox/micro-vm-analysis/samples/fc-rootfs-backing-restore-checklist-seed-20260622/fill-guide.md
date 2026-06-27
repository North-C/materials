# Fill Guide

1. 先读 `baseline.txt`，确认本 seed 已有的 root expression / backing / restore 基线片段。
2. 再在 `commands.txt` 写 snapshot / restore / guest 检查命令。
3. 在 `host.txt` 写 root block/pmem 与 cmdline 对应关系，以及 backing file 是否仍然语义一致。
4. 在 `api.txt` 或 `commands.txt` 旁注 restore 输入、snapshot 来源、disk/pmem 配置。
5. 在 `guest.txt` 记录 guest 是否真正看到设备，以及 rootfs 是否真正可用。
6. 最后在 `classification.md` 判断问题更像：
   - root expression mismatch
   - backing file inconsistency
   - restore succeeded but guest device invisible
   - guest rootfs not usable
7. 如果准备把本 seed 升成 `real`，再对照：
   - `evidence-targets.txt`
   - `collection-runbook.md`
   确认已经同时覆盖 restore success、root expression、backing consistency、guest visibility、rootfs usability 五层证据。
8. 如果已经拿到一整包日志，先对照：
   - `minimum-log-bundle.txt`
   - `decision-table.txt`
   - `bundle-template.txt`
   - `bundle-skeleton.txt`
   再决定是继续留在 seed，还是升级成新的 `real`。
9. 如果当前还没有真实 request dump，先用：
   - `create-snapshot-request.template.json`
   - `load-snapshot-request.template.json`
   固定字段结构，但不要把它们当成真实证据。
