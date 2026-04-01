# Nydus Snapshotter 第十二层：故障恢复与 daemon 重建机制

## 本层回答的问题

前面几层已经把 Nydus 的启动链路、读路径、优化和完整性拆开了。  
但一个真正长期运行的镜像服务，还必须回答另一个工程问题:

> 如果 `nydus-snapshotter` 自己重启了，或者 `nydusd` 在容器运行过程中崩了，这条远程 rootfs 链路如何恢复？

因此第十二层要回答的不是“怎么正常启动一次”，而是:

1. snapshotter 重启后如何把既有 daemon / RAFS instance 重新接回来
2. nydusd 运行中死亡后，snapshotter 如何按策略处理
3. failover 和 restart 有什么本质区别
4. hot upgrade 为什么能在不中断 I/O 的前提下替换 nydusd

这一层的重点是:

> Nydus 不只是会“挂载”，它还实现了一套围绕 daemon 生命周期、状态持久化和接管恢复的运行时控制机制。

---

## 一、先给“恢复”一个准确定位

在 Nydus 体系里，恢复不是单一场景，而是至少有两类:

### 1.1 控制面恢复

也就是:

- `nydus-snapshotter` 进程退出或重启
- 但一部分 daemon、挂载点、RAFS instance 可能还存在

这类问题要解决的是:

> 如何把已经存在的运行态重新纳入 snapshotter 的管理视图。

### 1.2 数据面 / 服务面恢复

也就是:

- `nydusd` 本身崩溃、退出、被 kill
- 但容器还活着，rootfs 仍然需要继续提供服务

这类问题要解决的是:

> 如何把具体的文件系统服务重新拉起来，甚至尽量不中断已有 I/O。

因此“恢复”在 Nydus 里不是一个点，而是两层:

- snapshotter 对运行态对象的重新接管
- nydusd 对服务状态和底层句柄的重新接续

---

## 二、snapshotter 启动时先做的不是挂新实例，而是恢复旧状态

`nydus-snapshotter/pkg/filesystem/fs.go` 的 `NewFileSystem()` 很能说明这一点。

在正常初始化 manager 后，它做的第一件关键事不是直接新建 daemon，而是:

- 遍历已启用的 manager
- 调用 `fsManager.Recover(...)`

也就是说，snapshotter 启动时的默认思路是:

> 先看看历史状态里已经有什么，再决定需不需要补建新实例。

这和一次性脚本式的挂载器很不一样，说明 snapshotter 从设计上就是一个:

> 带持久状态的长期服务控制器

而不是无状态命令。

---

## 三、Manager.Recover 做了两件事：恢复 daemon 视图，恢复 RAFS instance 视图

`pkg/manager/manager.go` 里 `Recover()` 很直接:

1. `recoverDaemons()`
2. `recoverRafsInstances()`

这两步的职责边界非常清晰。

### 3.1 `recoverDaemons()`

它会:

- 从 store/DB 遍历 daemon 记录
- 重建内存里的 `Daemon` 对象
- 重新放回 `daemonCache`
- 必要时重新创建 supervisor
- 对 fusedev 重载 daemon config
- 尝试通过 API 查询 daemon 当前状态

如果查询成功且状态是 `RUNNING`，就把它归到 `liveDaemons`；  
如果查询失败，则把它放进 `recoveringDaemons`。

所以这一层恢复的本质不是“立刻启动进程”，而是:

> 基于持久化记录重新建立 snapshotter 的 daemon 管理视图，并区分哪些 daemon 还活着、哪些只是留下了持久状态。

### 3.2 `recoverRafsInstances()`

它会继续遍历持久化的 RAFS instance 记录，把它们重新挂回对应 daemon 对象:

- live daemon 就挂到 live daemon 上
- recovering daemon 也先挂回 recovering daemon
- 同时放入全局 RAFS cache

因此第二步恢复的是:

> snapshotter 对“哪个 daemon 托管哪些 RAFS instance”的关系视图。

这一步很重要，因为没有这层关系，后续即使 daemon 重启成功，也不知道该恢复哪些 mount。

---

## 四、snapshotter 重启后的恢复主线

把上面两步串起来，snapshotter 重启后的恢复逻辑可以压缩成:

```text
snapshotter 启动
-> 从 DB 读取 daemon 记录
-> 判断哪些 daemon 仍然存活，哪些需要恢复
-> 从 DB 读取 RAFS instance 记录
-> 把 instance 重新挂回对应 daemon 对象
-> 对需要恢复的 daemon 重新启动并恢复 mount
```

而 `fs.go` 后面的逻辑又把这一流程分成两类对象处理:

- shared daemon
- persisted but stopped daemon

这说明 snapshotter 对恢复不是“一刀切重启全部”，而是按 daemon 角色来恢复。

---

## 五、shared daemon 的恢复更偏“先确保公共底座存在”

在 `NewFileSystem()` 里，snapshotter 会先统计:

- 当前是否已经有 fscache shared daemon
- 当前是否已经有 fusedev shared daemon

如果应该存在但没找到，就会主动初始化新的 shared daemon。

这说明 shared daemon 在恢复中的地位不是普通实例，而是:

> 多个 RAFS instance 依赖的公共运行底座

因此它的恢复优先级更高。  
如果 shared daemon 没起来，后面很多基于共享模式的实例都无从附着。

---

## 六、persisted but stopped daemon 的恢复：重启进程，再恢复 RAFS mounts

对 `recoveringDaemons`，`fs.go` 会并发做几件事:

1. `d.ClearVestige()`
2. `fsManager.StartDaemon(d)`
3. `d.WaitUntilState(RUNNING)`
4. `d.RecoverRafsInstances()`

这条链路说明“恢复”不只是把进程重新拉起来。  
它至少包含两层动作:

- 恢复 daemon 进程本身
- 恢复 daemon 托管的 RAFS mount 实例

也就是说，真正的恢复完成条件不是“进程 PID 出现了”，而是:

> daemon 已经重新进入 Running，并重新托管了原先的 RAFS instances。

这和前面几层分析里强调的 `ready/running` 语义是一致的。

---

## 七、运行中 daemon 死亡时，snapshotter 不是轮询发现，而是靠 liveness monitor 订阅事件

`Manager` 初始化时会启动 monitor，并在后台跑:

- `mgr.monitor.Run()`
- `go mgr.handleDaemonDeathEvent()`

相关代码:

- `nydus-snapshotter/pkg/manager/manager.go`
- `nydus-snapshotter/pkg/manager/daemon_event.go`

同时，当一个 daemon 被纳入管理后，manager 会对它:

- `SubscribeDaemonEvent(d)`

一旦 monitor 检测到 daemon 死亡，`handleDaemonDeathEvent()` 就会收到事件。

所以运行中恢复的触发方式不是:

> 等用户发现容器卡住了再手动处理

而是:

> snapshotter 对受管 daemon 做存活订阅，并在死亡事件到达时自动进入恢复策略。

---

## 八、RecoverPolicy 决定 daemon 死亡后的处理方式

从 `daemon_event.go` 和文档 `docs/nydus-failover-upgrade.md` 可以看到，恢复策略至少有三种:

- `none`
- `restart`
- `failover`

`handleDaemonDeathEvent()` 收到死亡事件后，会按 `RecoverPolicy` 分流:

- `restart` -> `doDaemonRestart()`
- `failover` -> `doDaemonFailover()`
- 其他 -> 不处理

因此 `recover_policy` 不是外围运维参数，而是:

> 决定 nydusd 崩溃后服务恢复语义的核心运行时策略。

---

## 九、`restart`：重新拉起 daemon，再重新挂载实例

`doDaemonRestart()` 的动作相对直接:

1. 等旧 daemon 彻底退出
2. 取消旧订阅
3. `d.ClearVestige()`
4. `StartDaemon(d)`
5. 遍历 `d.RafsCache.List()`
6. 对 shared 场景重新 `SharedMount(r)`

这条链路的特点是:

- 恢复方式偏“重建”
- 重点是把原先托管的 RAFS instance 重新 mount 回来

因此 restart 的语义更接近:

> 旧进程已经死了，清理遗留状态后重新起一个，并重新把 mount 补出来。

它解决的是“服务恢复”，但不承诺一定保留旧进程内部运行态。

---

## 十、`failover`：核心不是简单重启，而是接管旧 daemon 的状态与句柄

`doDaemonFailover()` 的关键动作和 restart 明显不同:

1. 等旧 daemon 退出
2. 取消旧订阅
3. 通过 supervisor `SendStatesTimeout(...)`
4. 重新启动新的 daemon
5. 等待新 daemon 到 `Init`
6. 调用 `d.TakeOver()`
7. 再调用 `d.Start()`

而 `docs/nydus-failover-upgrade.md` 对这个流程解释得更明确:

- 新 daemon 会带 `--upgrade` 参数启动
- 启动后停在 `Init`
- 外部控制器发 `Takeover`
- 新 daemon 收到旧 daemon 保存的状态并执行 `Restore`

文档还明确说，保存和恢复的信息包括:

- 文件句柄
- 后端文件系统状态

因此 failover 的本质不是:

> 重新 mount 一遍就算恢复

而是:

> 在尽量保留旧服务状态和关键句柄的前提下，让新进程接管旧服务。

这就是为什么它比 restart 更重，也更接近“平滑接管”。

---

## 十一、supervisor 是 failover / hot upgrade 的关键中介

从代码和文档看，failover 之所以成立，核心依赖的是 supervisor。

`Manager.NewManager()` 只有在 `RecoverPolicyFailover` 时才会创建:

- `SupervisorSet`

而 failover / upgrade 路径里都显式依赖:

- `d.Supervisor`
- `supervisor.SendStatesTimeout(...)`

文档也说明 snapshotter 会提供一个 unix domain socket 路径，  
nydusd 会把序列化后的状态和关键 fd 通过这条通道发回给 snapshotter / supervisor。

所以 supervisor 的准确角色不是“又一个 daemon”，而是:

> 旧 daemon 状态与文件句柄的保管和转运中介。

没有它，failover 就会退化成普通 restart。

---

## 十二、nydusd 自己也要配合恢复：它启动时会先判断是不是“前一个 daemon 崩了”

恢复不是 snapshotter 单方面完成的。  
`nydusd` 自己在启动时也会判断是否存在“残留现场”。

### 12.1 fusedev

`service/src/fusedev.rs` 里的 `is_crashed()` 会检查:

- mountpoint 是否仍然挂着
- API socket 是否残留但不可连接

如果满足这两点，就认为:

> 前一个 daemon 异常崩溃了，后续应该走 failover 恢复逻辑。

### 12.2 fscache / singleton

`service/src/singleton.rs` 里则会检查:

- `/dev/cachefiles` 是否还能正常打开
- API socket 是否残留但不可连接

如果 cachefiles 设备句柄被旧 daemon 或 supervisor 持有，就会进入类似的 crash / failover 判断。

这说明 `nydusd` 的恢复语义不是完全靠外部猜测，而是:

> 新进程启动时自己也会识别当前是不是在接手一个残留现场。

---

## 十三、fscache 恢复为什么尤其依赖“文件句柄接续”

`service/src/fs_cache.rs` 里 `FsCacheHandler::new()` 有一个很关键的分叉:

- 正常启动时，自己重新打开 `/dev/cachefiles` 并初始化 session
- 恢复路径下，使用 `restore_file`
- 然后向设备写入 `restore`

这段实现说明在 fscache 场景里，恢复不仅是“重新启动一个线程池”，而是:

> 把原来和内核 cachefiles 协作的那个关键文件句柄与会话继续接起来。

这也解释了为什么 failover 文档里把“file handler”列为必须保存和恢复的首要状态。

---

## 十四、hot upgrade 和 failover 共用同一套接管框架

这也是 Nydus 设计里很值得注意的一点。

`docs/nydus-failover-upgrade.md` 明确说:

- failover 支持自动从 crash 恢复
- hot upgrade 支持替换 nydusd 而不中断容器 I/O

而 `nydus-snapshotter/pkg/manager/daemon_event.go` 里的 `DoDaemonUpgrade()` 可以看到，升级流程本质上也是:

1. 基于旧 daemon 状态构造一个新 daemon
2. 切换到新的 API socket
3. 通过 supervisor 发送旧状态
4. 启动新 daemon（带 upgrade 模式）
5. 等它到 `Init`
6. `TakeOver()`
7. 等它到 `Ready`
8. 让旧 daemon `Exit()`
9. 新 daemon `Start()`
10. `RecoverRafsInstances()`

所以 hot upgrade 并不是另一套完全不同的系统，而是:

> 把 failover 的接管机制从“被动故障恢复”扩展成“主动平滑替换”。

---

## 十五、snapshotter 启动时还会顺手做二进制版本对比和热升级

`fs.go` 里在恢复 live daemons 之后，还会:

- 读取当前 nydusd 二进制的 git commit
- 对 live daemons 查询 daemon info/version
- 如果 commit 不一致，就调用 `DoDaemonUpgrade(...)`

这意味着 snapshotter 启动时不只是恢复旧状态，它还会:

> 主动检查现有 daemon 是否需要切换到当前配置指向的新 nydusd 二进制。

这进一步说明 snapshotter 的角色已经不是简单 mount agent，而是:

> nydusd fleet 的生命周期编排器。

---

## 十六、从整体角度看，恢复机制保障了哪三件事

把上面的实现压缩一下，Nydus 的恢复机制本质上保障了三类连续性:

### 16.1 管理连续性

snapshotter 重启后，仍能从 DB 把 daemon 和 RAFS instance 关系恢复出来。

### 16.2 服务连续性

daemon 死亡后，可按 `restart` 或 `failover` 策略重新提供文件系统服务。

### 16.3 演进连续性

在不中断业务语义的前提下，支持把旧 nydusd 平滑切换到新版本。

这三者合起来，才让 Nydus 成为一个可长期运行的生产级镜像服务，而不只是一个“能按需读镜像”的实验性组件。

---

## 十七、把恢复机制放回整条运行链路里

最后把它放回之前已经拆开的主链路，可以得到这样一张恢复视角的流程:

```text
正常运行
-> snapshotter 管理 daemon 与 RAFS instance
-> monitor 订阅 daemon 存活状态

如果 snapshotter 重启
-> 从 DB 恢复 daemon / RAFS instance 关系
-> 对 stopped daemon 重启并恢复 mounts

如果 daemon 运行中死亡
-> monitor 触发 death event
-> 按 recover_policy 选择 none / restart / failover
-> restart: 重建 daemon 并重新挂载实例
-> failover: 经 supervisor 传递状态与 fd，新 daemon takeover 后继续服务

如果需要升级 daemon
-> snapshotter 比对二进制版本
-> 通过 failover 同一套 takeover 机制做 hot upgrade
```

因此恢复机制和主链路的关系是:

> 前面几层解决“怎样把远程镜像挂成可读 rootfs”，这一层解决“这条 rootfs 服务链路在异常和升级下怎样持续活着”。

---

## 十八、一句话总结这一层

第十二层的核心结论是:

> Nydus 的恢复体系分成两层：snapshotter 通过持久化 store 恢复 daemon 与 RAFS instance 的管理关系，nydusd 通过 restart / failover / takeover / hot upgrade 机制恢复或接管实际文件系统服务，其中 failover 的关键是借助 supervisor 保留和转交旧 daemon 的状态与关键文件句柄。

再压缩成一句更工程化的话就是:

> Nydus 不只解决“把镜像挂起来”，还解决“控制器重启、daemon 崩溃、版本升级之后，这个挂载服务如何继续活着”。 
