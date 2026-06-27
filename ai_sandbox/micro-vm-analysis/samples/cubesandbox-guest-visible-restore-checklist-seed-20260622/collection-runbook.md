# Collection Runbook

目标：为
`cubesandbox-guest-visible-restore-checklist-seed-20260622`
补齐一组可以升级为失败类 `real` 的最小日志集合。

这份 runbook 不新增分析结论。

它只回答：

1. 下一轮应该抓哪些日志
2. 抓取顺序是什么
3. 抓到什么程度才值得升级 `real`

## 1. 最小目标

最小成功的失败样本，需要同一轮日志里同时出现：

1. 控制面 restore/update 请求成功
2. worker/backend 路径至少推进一段
3. guest-visible state 最终未收敛

如果缺任何一段，都不要升 `real`。

## 2. 推荐采集顺序

### A. 控制面请求

至少保留一组：

- CubeShim / cube-runtime 的 restore、resume、set_fs、add_device 请求输入
- 对应返回值或错误值

建议 grep：

```bash
rg -n "VmRestore|VmResumeFromSnapshot|VmSetFs|VmAddDevice|RollbackSnapshot|rollback_vm|resume_vm_with_config" <shim-or-cubelet-logs>
```

### B. Ready 路径

至少保留一组：

- `vm ready, vsock is listening (notify path)`
  或
- `vm ready, vsock is listening (probe path)`

并同时保留是否出现：

- `VmShutdown`
- `wait_notify VsockServerReady failed`
- `vsock not ready`

建议 grep：

```bash
rg -n "VsockServerReady|VmShutdown|wait_notify|vsock probe|vm ready, vsock is listening|vsock not ready" <shim-or-agent-logs>
```

### C. Worker / backend 推进

至少保留一组：

- `ApiRequest::VmSetFs`
- `ApiRequest::VmAddDevice`
- `FsEvent`
- `failed to update filter list`
- `back_state`
- `deserialize_and_apply_data`

建议 grep：

```bash
rg -n "ApiRequest::VmSetFs|ApiRequest::VmAddDevice|FsEvent|failed to update filter list|back_state|deserialize_and_apply_data" <vmm-or-virtiofs-logs>
```

### D. Guest-visible 收敛

至少保留一组成功推进信号：

- `wait a pci`
- `get_virtio_blk_pci_device_name`
- `create sandbox!, config net`
- `already mounted`
- `skip mount`

以及至少一组失败信号：

- `Failed to update interface`
- `Failed to update routes`
- `Failed to add ARP neighbours`

建议 grep：

```bash
rg -n "wait a pci|get_virtio_blk_pci_device_name|create sandbox!, config net|already mounted|skip mount|Failed to update interface|Failed to update routes|Failed to add ARP neighbours" <guest-or-agent-logs>
```

## 3. 最小目录回填顺序

拿到日志后，按下面顺序回填当前 seed：

1. `api.txt`
   写控制面请求、入口命令、返回值
2. `logs.txt`
   写每类日志文件实际路径
3. `host.txt`
   写控制面、ready、worker/backend 观察结果
4. `guest.txt`
   写 guest-visible 推进与失败结果
5. `classification.md`
   收敛 `final_bucket` 与 `confidence`

## 4. 升级门槛

满足下面条件后，才把这份 seed 升成 `real`：

1. 同一批日志里能证明控制面请求成功
2. 同一批日志里能证明 worker/backend 推进
3. 同一批日志里能证明 guest-visible 收敛失败

如果只有：

- 控制面失败
  归到 `cubesandbox-rollback-sandbox-not-running-real-20260622`

如果只有：

- 成功 create / snapshot / clone / rollback
  归到 `cubesandbox-guest-visible-restore-baseline-real-20260622`

## 5. 与现有资产的关系

这份 seed 的对照资产是：

- 成功基线：
  [cubesandbox-guest-visible-restore-baseline-real-20260622](../cubesandbox-guest-visible-restore-baseline-real-20260622/SUMMARY.md)
- 控制面失败：
  [cubesandbox-rollback-sandbox-not-running-real-20260622](../cubesandbox-rollback-sandbox-not-running-real-20260622/SUMMARY.md)

当前真正缺的是第三类：

- guest-visible convergence failure `real`
