# Fill Guide

1. 先读 `baseline.txt`，确认本 seed 已有的 translation / propagation / guest landing 基线片段。
2. 再在 `commands.txt` 写 host runtime、request、guest 检查命令。
3. 在 `host.txt` 记录 rootfs/volume 被翻译成哪类 storage，以及 `CreateContainerRequest.storages` 的证据。
4. 在 `logs.txt` 写 `add_storages()` / `mount_from()` / `mount_storage()` 的日志路径和关键输出。
5. 在 `guest.txt` 记录 rootfs / volume 是否真正可用。
6. 最后在 `classification.md` 判断问题更像：
   - storage translation incomplete
   - request propagation incomplete
   - guest add_storages incomplete
   - guest mount convergence incomplete
7. 如果准备把本 seed 升成 `real`，再对照：
   - `evidence-targets.txt`
   - `collection-runbook.md`
   确认已经同时覆盖 translation、request、guest landing、guest-visible result 四层证据。
8. 如果已经拿到一整包日志，先对照：
   - `minimum-log-bundle.txt`
   - `decision-table.txt`
   - `bundle-template.txt`
   - `bundle-skeleton.txt`
   再决定是继续留在 seed，还是升级成新的 `real`。
9. 如果当前还没有真实 request dump，先不要空着：
   - 优先用 `request-samples.txt`
   - 如果连对照样本都不适合当前场景，再从 `request.template.json` 起步
