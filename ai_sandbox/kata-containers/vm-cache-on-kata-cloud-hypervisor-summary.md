# VM Cache 在 Kata + Cloud Hypervisor 上的现状分析摘要

日期：2026-03-27

## 1. 核心结论

1. `VMCache` 在 Kata 中不是“缓存配置”，而是缓存一批 **已创建并暂停的基础 VM**。
2. 因此，`VMCache` 的成立前提是：底层 VMM 必须真正支持 `pause / resume`，最好还具备可靠的 `save` 语义。
3. 当前 `Kata + Cloud Hypervisor` 路径上，这个前提不成立：`CH` 在 Go runtime 里的 `PauseVM / SaveVM / ResumeVM` 只是空实现。
4. 所以从当前主线代码和官方文档看，`VMCache` 在 `Kata + Cloud Hypervisor` 上不能视为成熟可用能力，最多只能说“工厂框架路径存在”。

## 2. VMCache 的工作原理

`VMCache` 的基本思路是：

- 后台预先创建若干基础 VM
- 把这些 VM 缓存在本地 channel 或 gRPC cache server 中
- 真正创建 sandbox 时直接领取一个现成 VM

Kata 工厂层入口：

- [src/runtime/virtcontainers/factory/factory_linux.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/factory/factory_linux.go)

两种形式：

- 本地缓存：`factory/cache/cache.go`
- 远程缓存：`factory/grpccache/grpccache.go`

文档说明：

- [docs/how-to/what-is-vm-cache-and-how-do-I-use-it.md](/home/test/lyq/Micro-VM/kata-containers/docs/how-to/what-is-vm-cache-and-how-do-I-use-it.md)

## 3. 为什么 VMCache 依赖 Pause/Resume

关键点在 `direct` 工厂：

- `GetBaseVM()` 先调用 `vc.NewVM(ctx, config)`
- 然后立刻调用 `vm.Pause(ctx)`
- 最后返回这个 VM

代码位置：

- [src/runtime/virtcontainers/factory/direct/direct.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/factory/direct/direct.go)

这说明：

- “基础 VM” 的语义不是普通运行态 VM
- 而是 **已经创建完成并处于暂停态的 VM**

随后在 `factory.GetVM()` 中，运行时会：

- 从工厂或 cache 中拿到基础 VM
- 调用 `vm.Resume(ctx)`
- 调用 `vm.ReseedRNG(ctx)`
- 调用 `vm.SyncTime(ctx)`

代码位置：

- [src/runtime/virtcontainers/factory/factory_linux.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/factory/factory_linux.go)

因此，`VMCache` 依赖的不是抽象意义上的“预热”，而是非常具体的语义：

- `NewVM() -> Pause() -> Cache -> Resume()`

## 4. CH 在这条语义上为什么不成立

### Go runtime

`VM.Pause/Save/Resume` 只是简单转调到底层 hypervisor：

- [src/runtime/virtcontainers/vm.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/vm.go)

但 `cloudHypervisor` 的对应实现当前只是：

- 打日志
- 返回 `nil`

代码位置：

- [src/runtime/virtcontainers/clh.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/clh.go)

也就是说：

- `direct.GetBaseVM()` 认为自己拿到了一个“已暂停 VM”
- 但 `CH` 实际并没有执行真正的 pause
- 后续 `GetVM()` 再调 `Resume()` 时，也没有真实 resume

结果就是：

- `VMCache` 在 `CH` 上并没有被底层语义真正支撑

### 与 QEMU 的对比

QEMU 路径上：

- `PauseVM()` 走真实 pause
- `ResumeVM()` 走真实 resume
- `SaveVM()` 走真实 QMP migration/save

代码位置：

- [src/runtime/virtcontainers/qemu.go](/home/test/lyq/Micro-VM/kata-containers/src/runtime/virtcontainers/qemu.go)

这也是为什么主线文档最终明确写出：

- `VMCache` only supports the QEMU hypervisor

## 5. 文档、代码与 Cloud Hypervisor 的关系

从工厂代码看，`VMCache` 框架本身并没有在入口处写死只允许 `QEMU`。

但文档中明确写了两条限制：

- 不能和 `VM Templating` 一起使用
- 只支持 `QEMU`

文档位置：

- [docs/how-to/what-is-vm-cache-and-how-do-I-use-it.md](/home/test/lyq/Micro-VM/kata-containers/docs/how-to/what-is-vm-cache-and-how-do-I-use-it.md)

这说明官方结论不是来自“配置开关写死”，而是来自更深一层的实现语义：

- `CH` 虽然走得到工厂代码
- 但没有 `pause/resume/save` 的真实闭环
- 因而不能把它视为支持 `VMCache`

## 6. 对 Kata + Cloud Hypervisor 的实际意义

对 `Kata + Cloud Hypervisor` 场景，应该这样理解 `VMCache`：

- **不是**：当前可以直接拿来降低 CH 启动时延的成熟能力
- **而是**：Kata 工厂层已有一个预热池框架，但 CH 后端缺失关键语义支撑

所以如果目标是继续降低 `CH` 启动时延，现实路线不是直接开启 `VMCache`，而是：

### 短期可做

- 做运行态 `warm sandbox pool`
- 做 host 侧资源池化（网络/TAP/磁盘）

### 长期可做

- 在 Kata 中为 `CH` 补真实 `PauseVM / SaveVM / ResumeVM`
- 再评估是否能把现有 `VMCache` 工厂语义复用到 CH

## 7. 汇报用一句话结论

可以把这部分概括为：

> `VMCache` 在 Kata 中缓存的是“已创建并暂停的基础 VM”，而不是普通预热对象；由于当前 `Cloud Hypervisor` 后端没有实现真实的 `pause / resume / save` 语义，所以 `VMCache` 在 `Kata + Cloud Hypervisor` 上目前不能视为成熟可用能力。
