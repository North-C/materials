# 非网络证据包记录模板

本文不是专题分析。

它是一个最小记录模板，用于在拿到一包新的 non-network 证据后，先把事实落下来，再决定它应该回填到哪一份 seed 或升级到哪一类 `real`。

它适用于当前四份重点 seed：

1. `cubesandbox-guest-visible-restore-checklist-seed-20260622`
2. `kata-storage-convergence-checklist-seed-20260622`
3. `fc-rootfs-backing-restore-checklist-seed-20260622`
4. `ch-backend-notifier-restore-checklist-seed-20260622`

## 1. 基本信息

- bundle 名称：
- 采集时间：
- 项目：
- 对应 seed：
- attempt 唯一标识：
- 机器架构：
- 触发动作：

推荐命名约定：

- 目录名：
  `<project>-<topic>-attempt-<YYYYMMDD>-<shortid>/`
- `attempt` 标识：
  同一轮控制面请求、worker/backend 处理、guest-visible 结果必须共用同一个 `attempt` 标识

不要把：

- 不同时间点
- 不同 sandbox/container
- 不同恢复动作

混成同一个 bundle。

## 2. 目录内容

- `api.txt`:
- `host.txt`:
- `guest.txt`:
- `vmm.log` / `backend.log` / `agent.log` / `shim.log` / `event.log`:
- 其它补充文件：

## 3. 当前最强证据

### 控制面 / request

- 已有：
- 缺失：

### 中间层 / worker / backend / controller

- 已有：
- 缺失：

### guest-visible 结果

- 已有：
- 缺失：

## 4. 用 `decision-table` 的初判

- 当前更像：
  - success baseline
  - control-plane failure
  - guest-visible failure
  - 仍停在 seed

理由：

## 5. 仍缺哪一层

- 还缺：
  - request / control-plane success
  - worker / backend progression
  - controller restore
  - guest-visible convergence
  - final usability

## 6. 下一步动作

- 继续补哪些日志：
- 是否已经够资格升级为 `real`：
- 如果不够，最小还差什么：
