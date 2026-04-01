# Kata Containers 性能优化技术分析报告

## 项目范围与分析口径

本文基于当前仓库主线代码现状，对 Kata Containers 中三类性能优化技术进行分析：

1. `VM Cache`
2. `VM Templating`
3. `Nydus` 镜像加速

重点分析以下问题：

- 这些能力在当前代码中的实现入口在哪里
- 它们各自优化的性能瓶颈是什么
- 在 `Cloud Hypervisor` 作为 VMM 的场景下，哪些能力真正可用，哪些只是框架存在但能力未闭合
- Go runtime 与 runtime-rs 在这些能力上的现状差异

本文以仓库实现为主，必要时补充“文档/设计意图”和“当前实现状态”之间的差距。

---

## 一、结论摘要

如果当前主要关注 `Cloud Hypervisor` 场景，那么这三项能力的优先级应当这样理解：

### 1.1 当前最值得重点研究的是 Nydus

原因不是概念上更先进，而是因为从主线代码来看，`Nydus + Cloud Hypervisor` 已经具备比较明确的实现路径：

- 配置层支持 `shared_fs = "virtio-fs-nydus"`
- Go runtime 中存在 `nydusd` 生命周期管理和 rootfs 处理逻辑
- runtime-rs 中也存在 Nydus rootfs 的资源层实现
- `Cloud Hypervisor` 的共享文件系统接入路径允许 `virtio-fs-nydus`

因此，Nydus 是当前最适合在 `Cloud Hypervisor` 场景下继续深入研究的性能优化能力。

### 1.2 VM Templating 目前本质上仍偏向 QEMU

仓库中同时存在 Go runtime 和 runtime-rs 的模板工厂代码，但真正完整打通“模板保存 + 模板恢复 + 启动克隆 VM”路径的，是 QEMU。

对于 `Cloud Hypervisor`：

- 配置框架和通用模板框架并不等于能力已落地
- Go runtime 中 `cloudHypervisor` 的 `PauseVM()` / `SaveVM()` / `ResumeVM()` 当前只是空实现
- runtime-rs 的模板框架存在，但 `TemplateVm` 当前明确只支持 QEMU

因此，从主线代码现状看，`Cloud Hypervisor` 并不具备成熟可用的 VM Templating 实现。

### 1.3 VM Cache 的工厂框架存在，但在 Cloud Hypervisor 上不能等价理解为“成熟能力”

VM Cache 的本质是“预先创建好一批 blank VM，运行时直接取用”。这套机制在工厂层是通用的，但它依赖底层 VM 的暂停/恢复语义是可靠的。

在 `Cloud Hypervisor` 上：

- 工厂和缓存框架代码可以复用
- 但 `PauseVM()` / `ResumeVM()` 当前为空实现
- 因此缓存层对 CH 来说更像“接口路径存在”，而不是“能力闭环完成”

所以，如果目标是研究 `Cloud Hypervisor` 的现实可用优化技术，VM Cache 应排在 Nydus 之后，并且要特别谨慎地区分“框架存在”和“优化效果真实成立”。

---

## 二、三项技术的目标与优化对象

### 2.1 VM Cache 优化的是什么

VM Cache 优化的是 **新建沙箱 VM 的准备延迟**。

它的思路不是共享已有 VM 的内存，也不是从快照恢复，而是：

- 事先创建一批“可直接交付”的基础 VM
- 把这些 VM 缓存在一个工厂或缓存服务中
- 真正创建 sandbox 时直接取一个现成 VM

它减少的是“临时从零启动一个基础 VM”的等待时间。

### 2.2 VM Templating 优化的是什么

VM Templating 同时优化两个维度：

- **启动时间**
- **内存占用**

它的核心思想是先构建一个模板 VM，再让后续 VM 从该模板克隆出来。这样新 VM 不需要完整经历一遍普通启动流程，并且模板相关的内存页可以按共享只读方式复用。

因此，VM Templating 相比 VM Cache 更激进，收益也通常更大，但代价是：

- 对底层 VMM 的模板/迁移/保存恢复机制依赖更强
- 与共享内存相关的安全与兼容性约束更多

### 2.3 Nydus 优化的是什么

Nydus 优化的是 **镜像拉取、镜像解压、容器 rootfs 准备** 这一段链路。

它不是 VM 启动层优化，而是镜像和文件系统层优化。

其核心收益来自：

- 镜像按需加载，而不是完整预取
- 避免传统 OCI 层的解压与大规模小文件展开
- 通过 `rafs` / FUSE / virtio-fs 路径，把镜像访问转为按需页或按需文件读取

所以在容器启动总时延里，Nydus 优化的是“镜像就绪”这部分，而不是 VMM 自身的冷启动。

---

## 三、VM Cache：实现与原理

## 3.1 代码入口

VM Cache 在 Go runtime 中的主要实现路径如下：

- 工厂入口：`src/runtime/virtcontainers/factory/factory_linux.go`
- 缓存实现：`src/runtime/virtcontainers/factory/cache/cache.go`
- gRPC 客户端：`src/runtime/virtcontainers/factory/grpccache/grpccache.go`
- 协议定义：`src/runtime/protocols/cache/cache.proto`
- 相关说明文档：`docs/how-to/what-is-vm-cache-and-how-do-I-use-it.md`

其中最关键的入口在 `NewFactory()`：

- 如果启用了 `Template`，先构建模板工厂
- 如果启用了 `Cache > 0`，再在基础工厂外包一层 `cache.New(...)`
- 如果启用了 `VMCache` 且 `Cache == 0`，则走 `grpccache`，向 VMCache 服务端要一个基础 VM

这说明 VM Cache 在架构上本质是一个 **工厂增强层**，不是独立的 Hypervisor 能力。

## 3.2 工作原理

### 本地缓存模式

在 `cache.go` 中，缓存工厂会启动若干后台 goroutine，不断向底层工厂请求 `GetBaseVM()`，并把得到的 VM 放入 `cacheCh`。

也就是说：

1. 底层工厂先产出“基础 VM”
2. 缓存层把这些 VM 提前准备好
3. 上层真正要创建 sandbox 时，从 channel 里直接取一个 VM
4. 缓存层继续异步补货

这是典型的“生产者-消费者”预热池模型。

### 远程 VMCache 模式

在 `grpccache.go` 中，客户端通过 Unix socket + gRPC 请求缓存服务：

- `Config()` 获取 VM 配置
- `GetBaseVM()` 获取一个基础 VM

协议定义在 `cache.proto`。从协议结构看，服务端会把 hypervisor 状态、CPU、memory 等信息序列化为 `GrpcVM` 返回给客户端。

因此，VM Cache 的远程模式本质上是“一个专用 VM 池服务 + runtime 侧消费者”。

## 3.3 基础 VM 是什么状态

这是理解 VM Cache 的关键。

在 `src/runtime/virtcontainers/factory/direct/direct.go` 中，`GetBaseVM()` 的流程是：

1. `vc.NewVM(ctx, config)`
2. `vm.Pause(ctx)`
3. 返回该 VM

也就是说，工厂语义要求“基础 VM”是一个 **已创建并暂停的 VM**。

随后在 `factory_linux.go` 的 `GetVM()` 中，runtime 会：

1. 从基础工厂取出基础 VM
2. 调用 `vm.Resume(ctx)`
3. `vm.ReseedRNG(ctx)`
4. `vm.SyncTime(ctx)`
5. 必要时执行 CPU / 内存热插拔

这说明 VM Cache 的核心前提不是“缓存配置”，而是 **缓存一个可恢复的暂停态 VM**。

## 3.4 性能收益来自哪里

VM Cache 的收益主要来自：

- 避免在业务请求到达时同步执行 `NewVM()`
- 将 VM 创建耗时前移到后台预热阶段
- 把新 sandbox 的 VM 获取路径从“创建 VM”变成“领取已准备 VM”

它不依赖模板共享内存，因此：

- 不提供 VM Templating 那种显著的内存节省
- 但也不引入模板共享内存相关风险

这与仓库文档中的描述是一致的。

## 3.5 Cloud Hypervisor 场景分析

从代码语义看，VM Cache 想要在某个 VMM 上真正成立，至少需要：

- `NewVM()` 可靠
- `PauseVM()` 真实可用
- `ResumeVM()` 真实可用
- 恢复后 agent 通信、时间同步、随机数重播都能成立

这不是一个抽象上的推断，而是可以沿着调用链逐步落到代码上：

1. `src/runtime/virtcontainers/factory/direct/direct.go` 中，基础工厂 `GetBaseVM()` 明确执行：
   - `vc.NewVM(ctx, config)`
   - `vm.Pause(ctx)`
2. `src/runtime/virtcontainers/vm.go` 中，`VM.Pause()` 只是转调底层 `hypervisor.PauseVM(ctx)`。
3. `src/runtime/virtcontainers/factory/factory_linux.go` 中，真正交付 VM 给上层时，又会执行：
   - `vm.Resume(ctx)`
   - `vm.ReseedRNG(ctx)`
   - `vm.SyncTime(ctx)`
4. `src/runtime/virtcontainers/vm.go` 中，`VM.Resume()` 同样只是转调底层 `hypervisor.ResumeVM(ctx)`。

因此，VM Cache 在实现语义上依赖一个非常强的前提：

- “底层 hypervisor 必须真的支持 pause/resume”

但在 `src/runtime/virtcontainers/clh.go` 中：

- `PauseVM()` 只是打印日志后返回 `nil`
- `SaveVM()` 只是打印日志后返回 `nil`
- `ResumeVM()` 只是打印日志后返回 `nil`

也就是说：

- `factory/direct` 认为自己拿到了一个“已暂停 VM”
- 但 `cloudHypervisor` 实际上并没有执行真实 pause
- 后续 `factory.GetVM()` 再调 `Resume()` 时，CH 也没有执行真实 resume

这意味着对 `Cloud Hypervisor` 来说，工厂层虽然可以复用同一套 VM Cache 代码，但“缓存的是暂停态基础 VM”这一语义并没有被 CH 的主线实现真正支撑。

进一步说，QEMU 与 CH 在这里形成了鲜明对比：

- `src/runtime/virtcontainers/qemu.go` 中，`PauseVM()` 和 `ResumeVM()` 会走真实的 QMP pause/resume 逻辑
- 同一文件中，`SaveVM()` 也会通过 QMP `migrate` 将设备状态流写入 `DevicesStatePath`

而 CH 没有对应的保存/恢复实现闭环。

### 实际含义

因此在主线代码现状下，不能简单地说“Cloud Hypervisor 已支持 VM Cache”。

更准确的说法是：

- VM Cache 工厂框架是通用的
- 但 Cloud Hypervisor 缺少与该框架严密匹配的 pause/resume 实现闭环
- 所以在 CH 场景中，它更像“接口路径存在”，而不是一个已经成熟、可验证收益的优化能力

## 3.6 文档与实现的差距

仓库文档 `docs/how-to/what-is-vm-cache-and-how-do-I-use-it.md` 明确写了：

- VMCache 不能和 VM Templating 同时使用
- VMCache 只支持 QEMU

这个说法与主线代码现状是吻合的。也就是说：

- 工厂层代码表面上并非写死 QEMU
- 但从能力语义来看，文档的“Only supports the QEMU hypervisor”是合理结论
- 依据不是配置文件限制，而是 CH 当前缺少支撑 VM Cache 语义所需的真实 `pause/resume/save` 实现

---

## 四、VM Templating：实现与原理

## 4.1 代码入口

### Go runtime

- 工厂入口：`src/runtime/virtcontainers/factory/factory_linux.go`
- 模板实现：`src/runtime/virtcontainers/factory/template/template_linux.go`
- QEMU 模板约束：`src/runtime/virtcontainers/qemu.go`
- 说明文档：`docs/how-to/what-is-vm-templating-and-how-do-I-use-it.md`

### runtime-rs

- 模板工厂：`src/runtime-rs/crates/runtimes/virt_container/src/factory/template.rs`
- 模板 VM 抽象：`src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs`
- 模板启动流程：`src/runtime-rs/crates/runtimes/virt_container/src/sandbox.rs`
- 从模板构建 VM：`src/runtime-rs/crates/runtimes/virt_container/src/lib.rs`
- QEMU 侧模板恢复：`src/runtime-rs/crates/hypervisor/src/qemu/inner.rs`

## 4.2 工作原理

VM Templating 的核心流程可以概括为：

1. 准备模板状态目录
2. 在该目录上挂载 `tmpfs`
3. 创建模板 VM
4. 启动到 agent 可用
5. 断开 agent 连接
6. 暂停 VM
7. 保存设备状态和内存状态
8. 后续新 VM 直接从模板状态恢复

在 Go runtime 的 `template_linux.go` 中，这个流程很清楚：

- `prepareTemplateFiles()` 负责创建目录、挂载 `tmpfs`、创建 `memory` 文件
- `createTemplateVM()` 负责设置：
  - `BootToBeTemplate = true`
  - `MemoryPath = statePath + "/memory"`
  - `DevicesStatePath = statePath + "/state"`
- 然后执行：
  - `vc.NewVM()`
  - `vm.Disconnect()`
  - `time.Sleep(templateWaitForAgent)`
  - `vm.Pause()`
  - `vm.Save()`

runtime-rs 的 `factory/template.rs` 基本沿用了同样设计：

- 仍然通过 `tmpfs + memory + state` 组织模板文件
- 仍然是“新建模板 VM -> disconnect -> pause -> save”

### 模板里到底包含什么

从当前 Kata 主线实现来看，模板至少由两部分“落盘状态”和一组“必须保持不变的外部条件”组成。

#### 1. 落盘状态

Go runtime 的 `template_linux.go` 和 runtime-rs 的 `factory/template.rs` 都明确创建了两个核心文件：

- `memory`
- `state`

其中：

- `memory` 是模板 VM 的内存后端文件，放在模板目录挂载出来的 `tmpfs` 中
- `state` 是设备状态和迁移状态流的落盘位置

这两个文件共同构成 Kata 所谓“模板”的核心物化结果。

#### 2. 模板恢复必须复用的不变条件

模板并不是一个包含一切内容的单文件快照。真正恢复时，还必须保证一组外部条件与保存模板时保持一致：

- 相同的 QEMU 命令行大体结构
- 相同的虚拟设备布局
- 相同的 kernel / initrd 或 image
- 相同的 vCPU / memory 拓扑
- 相同的 agent 通信方式

这一点可以从两类证据同时得到支持：

- Kata 本地代码在模板恢复时会继续复用同一套 hypervisor 配置，只是打开 `BootFromTemplate` 并指向同一个 `memory/state`
- QEMU 官方文档也明确说明：保存/恢复要成立，QEMU 必须以相同参数重新启动，恢复时主要差异是增加 `-incoming`

因此，更准确的理解是：

- 模板“文件”主要保存的是 **RAM + 设备/迁移状态**
- 模板“环境”则还依赖 **相同的启动工件和虚拟硬件配置**

#### 3. 从 Kata 文档看，哪些内容会被共享

仓库 how-to 文档对模板收益的描述是：

- 新 VM 会共享相同的 `initramfs`、`kernel` 和 `agent memory`，并以只读方式复用

这不是说 `kernel/initramfs` 被塞进 `state` 文件里，而是说：

- 新 VM 仍使用相同的启动工件
- 模板保存下来的内存态中已经包含 agent 初始化后的内存内容
- 从而使后续 VM 既能跳过完整启动，又能共享一部分只读内存页

### 为什么它能省掉后续启动流程

模板机制省掉的不是“VMM 进程创建”本身，而是 **guest 从冷启动到 agent 就绪这一大段路径**。

普通 VM 启动至少要经过：

1. QEMU 启动
2. 内核进入 guest
3. initrd / image 初始化
4. agent 进程启动
5. agent 通信端口准备完成
6. guest 进入可以接收后续容器操作的状态

而模板 VM 的做法是：

1. 先完整走完一次上述流程
2. 在 agent 已经 ready 的时刻断开连接
3. pause VM
4. 把 RAM 和设备状态保存下来
5. 后续新 VM 启动时，不再执行完整 guest 冷启动，而是直接从该保存态恢复

因此它省掉的主要是：

- 内核冷启动时间
- initrd / image 初始化时间
- agent 启动和准备时间
- 一部分设备初始化路径

而保留下来的则是：

- 启动一个新的 QEMU 进程
- 指向相同的模板文件和相同的启动工件
- 将 VM 恢复到模板保存点之后继续执行

## 4.3 性能收益来自哪里

VM Templating 的收益主要来自两个方面。

### 启动时间优化

普通 VM 启动要经历：

- VMM 启动
- 内核启动
- initrd / image 初始化
- agent 启动
- 设备与通信就绪

模板 VM 把这些步骤尽可能前移并固化，因此新 VM 可以从保存态恢复，而不是重新完整冷启动。

### 内存优化

模板技术的另一个关键收益是共享只读内存页：

- kernel
- initramfs / image 中一部分内容
- agent 相关内存

因此当同一主机上运行大量同构 Kata sandbox 时，模板方式通常比普通 VM 更节省内存。

这也是它与 VM Cache 的根本区别。

## 4.4 QEMU 中为什么是完整能力

QEMU 在主线代码中具备真实的模板恢复路径。

在 runtime-rs 的 `src/runtime-rs/crates/hypervisor/src/qemu/inner.rs` 中：

- 如果 `boot_from_template = true`，启动后会执行 `boot_from_template()`
- 该函数通过 QMP 设置共享内存能力并执行迁移恢复
- `save_vm()` 则通过 QMP 执行状态保存

在 Go runtime 的 `src/runtime/virtcontainers/qemu.go` 中，这条路径同样很具体：

- `SaveVM()` 会通过 QMP 设置迁移参数，并把迁移输出写到 `DevicesStatePath`
- `PauseVM()` / `ResumeVM()` 走真实的 pause/resume 逻辑

也就是说，QEMU 模板并不是“运行时把一个 Rust/Go 结构复制一份”，而是依赖 QEMU 自身的 migration/save/restore 机制。

这一点还可以从 QEMU 官方文档得到直接支持：

- `Migration framework` 文档说明，QEMU 保存/恢复 guest 时，本质是在保存设备状态并通过统一 migration 基础设施恢复
- 同一文档说明 migration 流可以通过 `exec` transport 传输
- QEMU 官方文档中的 save/restore 示例也给出了：
  - 保存：`migrate "exec:cat > testvm.bin"`
  - 恢复：QEMU 以 `-incoming "exec:cat < testvm.bin"` 重新启动

这与 Kata 当前代码中的：

- `exec:cat > state`
- `execute_migration_incoming("exec:cat state")`

在实现思路上是一致的。

这说明 QEMU 的模板机制并不是“配置位存在”，而是底层 Hypervisor 实现真的接住了：

- 模板保存
- 模板恢复
- 迁移完成等待
- 恢复后继续运行

Go runtime 中也有与之对应的 QEMU 约束和模板路径。

## 4.5 QEMU 模板的限制条件

`src/runtime/virtcontainers/qemu.go` 中有一个很关键的限制：

- VM templating 与 `virtio-fs`
- VM templating 与 `virtio-fs-nydus`
- VM templating 与 file-backed memory

在当前实现下不能共存。

代码中明确写到：

- 如果启用了 `virtio-fs` / `virtio-fs-nydus` / file-backed memory
- 且同时启用了模板
- 则该配置不会工作，并直接报错

这意味着模板技术虽然性能收益明显，但兼容性约束比 VM Cache 和 Nydus 都更强。

这里也能反向说明模板的工作方式：

- 模板恢复依赖模板 VM 和克隆 VM 之间的内存组织方式保持严格一致
- 而 `virtio-fs` 需要共享内存打开方式与模板路径冲突
- 所以模板不是一个完全独立于内存拓扑的高层功能，而是与底层内存后端和迁移机制强绑定

## 4.6 Cloud Hypervisor 场景分析

### Go runtime 现状

`cloudHypervisor` 在 `clh.go` 中当前的：

- `PauseVM()`
- `SaveVM()`
- `ResumeVM()`

都只是空实现。

这直接说明，CH 在 Go runtime 中并没有形成模板所需的保存/恢复闭环。

并且这个结论可以直接与模板工厂代码对照：

- 模板创建阶段必须执行 `vm.Pause()`
- 模板创建阶段必须执行 `vm.Save()`
- 模板交付阶段又必须执行 `vm.Resume()`

其中任意一环如果只有空实现，模板链路都不能算真正成立。CH 当前三环都缺。

### runtime-rs 现状

runtime-rs 中表面上存在更通用的模板框架：

- `build_vm_from_template()`
- `Template::create()`
- `Sandbox::start_template()`

而且 `new_hypervisor()` 也能根据配置选择 `cloud-hypervisor`。

但这里有一个更关键的实现事实：

在 `src/runtime-rs/crates/runtimes/virt_container/src/factory/vm.rs` 中，`TemplateVm::new_hypervisor()` 当前只支持：

- `QEMU`

对其他 Hypervisor 会直接返回 `Unsupported hypervisor`。

因此 runtime-rs 的模板工厂虽然具有通用框架外观，但它的模板 VM 核心实现当前仍然只落在 QEMU 上。

## 4.7 文档与实现的差距

仓库 how-to 文档对 VM Templating 的介绍是一个较高层能力描述，重点强调：

- 启动更快
- 内存占用更低
- 依赖 QEMU 和 initrd
- 不能与 `virtio-fs` 共用

从主线代码现状看，这些约束依然成立，甚至还可以进一步严格化：

- 不只是“偏向 QEMU”，而是当前完成度上本质属于 QEMU 能力
- 对 `Cloud Hypervisor` 来说，模板相关的框架代码存在，但主线实现并未闭环

### 补充的外部依据

除了仓库内文档和代码之外，QEMU 官方文档也支持这里的实现判断：

- QEMU 的 migration/save/restore 机制要求恢复端使用相同设备配置重新启动
- migration 流本身保存的是 guest/device state
- `exec` transport 可以直接把状态流写入文件并再从文件读回

这正是 Kata 当前模板实现依赖 QEMU、且不容易平移到 Cloud Hypervisor 的根本原因。

可直接参考的外部资料：

- QEMU Migration framework: https://www.qemu.org/docs/master/devel/migration/main.html
- QEMU 文档中基于 `exec:cat` 的 save/restore 示例: https://www.qemu.org/docs/master/specs/tpm.html#migration-with-the-tpm-emulator

---

## 五、Nydus：实现与原理

## 5.1 代码入口

Nydus 在当前仓库中同时出现在 Go runtime 和 runtime-rs 中。

### Go runtime

- `src/runtime/virtcontainers/nydusd.go`
- `src/runtime/virtcontainers/nydusd_linux.go`
- `src/runtime/pkg/containerd-shim-v2/create.go`
- `src/runtime/virtcontainers/fs_share_linux.go`
- `src/runtime/virtcontainers/container.go`
- `src/runtime/virtcontainers/qemu.go`
- `src/runtime/virtcontainers/clh.go`
- `src/runtime/config/configuration-clh.toml.in`

### runtime-rs

- `src/runtime-rs/crates/resource/src/rootfs/mod.rs`
- `src/runtime-rs/crates/resource/src/rootfs/nydus_rootfs.rs`
- `src/runtime-rs/config/configuration-cloud-hypervisor.toml.in`

### 通用数据结构

- `src/libs/kata-types/src/mount.rs`

这个文件定义了：

- Nydus volume 类型
- Nydus 额外配置解析
- `source` / `config` / `snapshot_dir` 等数据结构

## 5.2 Nydus 优化对象

Nydus 优化的是镜像分发和 rootfs 准备。

传统 OCI rootfs 准备通常包含：

1. 拉取镜像层
2. 解压层
3. 组装 overlay 层
4. 将 rootfs 暴露给容器

Nydus 通过 `rafs` 文件系统格式，把镜像访问转成更细粒度的按需加载，减少：

- 启动时完整下载等待
- 大量层解压开销
- 海量文件落盘与展开开销

因此它主要提升的是：

- 冷启动时的镜像就绪时间
- 镜像远端拉取和本地展开成本
- 大镜像、深层镜像、多小文件镜像场景下的效率

## 5.3 Go runtime 中的实现链路

### 第一步：shim 识别 Nydus rootfs

在 `src/runtime/pkg/containerd-shim-v2/create.go` 中，`checkAndMount()` 会检查 rootfs 类型。

如果 `vc.IsNydusRootFSType(m.Type)` 成立，则：

- 不在宿主机上执行普通 rootfs mount
- 直接返回 `false`

这说明 Nydus rootfs 不走常规 OCI 挂载路径，而是交给后续专门逻辑处理。

### 第二步：启动 nydusd

`src/runtime/virtcontainers/nydusd.go` 中定义了 `nydusd` 生命周期管理逻辑。

`Start()` 的主要动作包括：

1. 校验 daemon/socket/sourcePath
2. 构造参数并启动 `nydusd`
3. 等待其 API server ready
4. 调用 `setupShareDirFn()` 建立共享目录

其中 Nydus daemon 使用：

- `virtiofs` 模式运行
- `apisock` 暴露控制接口
- `sock` 提供共享文件系统接入

它既承担 Nydus 文件系统挂载控制，又承担 host/guest 共享目录桥接。

### 第三步：准备 passthrough_fs

`setupPassthroughFS()` 会通过 Nydus API 建立：

- `passthrough_fs`

其目标是把共享目录暴露到 guest 中的 `/containers`。

这一步的作用是：

- 让 guest 能通过 Nydus/virtio-fs 机制访问宿主机提供的目录
- 为后续 rootfs 组合提供底座

### 第四步：挂载 RAFS

`Mount()` 中会使用：

- `rafs`

作为挂载类型，通过 Nydus API 完成真实镜像元数据挂载。

也就是说，Nydus 的镜像访问并不是普通 overlay lowerdir 直接来自宿主机目录，而是来自 RAFS 挂载点。

### 第五步：构造 overlay rootfs

在 `nydusd.go` 末尾的注释和额外选项解析中，可以看到 Nydus rootfs 挂载格式形如：

- `Type: fuse.nydus-overlayfs`
- `Source: overlay`
- `Options: lowerdir=..., upperdir=..., workdir=..., extraoption=...`

其中 `extraoption` 里会携带：

- `source`
- `config`
- `snapshotdir`

这些信息会被 runtime 用来构造真正的 rootfs。

### 第六步：容器退出时清理

`container.go` 和 `fs_share_linux.go` 中多处调用 `nydusContainerCleanup(...)`，说明 Nydus 相关挂载不是一次性静态资源，而是容器生命周期中的动态状态，需要在失败回滚和容器销毁时清理。

## 5.4 runtime-rs 中的实现链路

runtime-rs 的 Nydus 路径更直接体现在资源层。

在 `src/runtime-rs/crates/resource/src/rootfs/mod.rs` 中：

- 如果 layer 的 `fs_type == "fuse.nydus-overlayfs"`
- 则构造 `NydusRootfs`

`src/runtime-rs/crates/resource/src/rootfs/nydus_rootfs.rs` 展示了它的主要流程：

1. 解析 `NydusExtraOptions`
2. 获取 RAFS meta 路径和配置
3. 调用 `rafs_mount(...)`
4. 在共享目录下创建容器 rootfs
5. 共享 snapshot dir
6. 组织 overlay：
   - `lowerdir` 指向 RAFS lower 层
   - `upperdir` 指向 snapshot `fs`
   - `workdir` 指向 snapshot `work`
7. 最终将其作为 `Storage` 返回给 agent

这表明 runtime-rs 中 Nydus 的模型是：

- 下层只读镜像内容来自 RAFS
- 上层可写层来自 snapshot dir
- 最终通过 overlay 组合成容器 rootfs

这是一个非常典型的“只读镜像层按需加载 + 可写层本地 overlay”的设计。

## 5.5 性能收益来自哪里

Nydus 的性能收益主要来自以下几个方面。

### 镜像按需访问

容器启动时不需要把整个镜像层全部解压并准备好，而是只在访问到某个文件或页时，才去读取对应数据。

这对大镜像尤其重要。

### 减少解压与文件展开成本

传统 OCI 层需要：

- 拉层
- 解包 tar
- 建立 overlay lowerdir

Nydus 则把大量“启动前必须完成”的工作转为“运行时按需读取”，显著降低冷启动前置成本。

### 更适合远端镜像和懒加载场景

当镜像位于远端仓库，且容器启动初期只会访问其中一小部分文件时，Nydus 的收益通常更明显。

### 可结合预取

runtime-rs 的 `nydus_rootfs.rs` 中还存在 `prefetch_file.list` 逻辑，表明当前代码也考虑了：

- 对热点文件做预取
- 避免完全被动懒加载造成首访抖动

这属于“懒加载 + 定向预热”的折中策略。

## 5.6 Cloud Hypervisor 场景分析

这是当前最重要的部分。

### 配置层已明确支持

在以下配置模板中，`shared_fs` 都允许：

- `virtio-fs-nydus`

对应文件：

- `src/runtime/config/configuration-clh.toml.in`
- `src/runtime-rs/config/configuration-cloud-hypervisor.toml.in`

因此至少在配置模型上，主线代码明确承认 `Cloud Hypervisor + Nydus` 是一个支持目标。

### Go runtime 中 CH 接住了共享卷接入

在 `src/runtime/virtcontainers/clh.go` 中：

- `Capabilities()` 会在启用共享文件系统时声明文件共享能力
- `addVolume()` 明确接受 `VirtioFS` 和 `VirtioFSNydus`
- 然后通过 `FsConfig` 把共享卷接入 Cloud Hypervisor VM

这说明 CH 并不是被动绕过 Nydus，而是明确参与了其共享文件系统接入路径。

### Nydusd 也明确标注支持 QEMU/CLH

在 `src/runtime/virtcontainers/nydusd.go` 中，错误常量 `errNydusdNotSupport` 明确写道：

- `nydusd only supports the QEMU/CLH hypervisor currently`

从这个表述看，代码设计层已经把 CH 视为 Nydus 的正式支持对象之一。

### 因此对 CH 来说，Nydus 是真实能力，而不是仅有框架

综合配置、共享文件系统、nydusd、rootfs 处理路径来看，Nydus 在 CH 场景下是三项技术里最接近“能力闭环”的一项。

这也是为什么从当前代码现状出发，研究 Cloud Hypervisor 场景时应该优先研究 Nydus。

## 5.7 与 VM Templating 的关系

Nydus 与 VM Templating 解决的是不同层面的启动开销：

- VM Templating 优化 VM 创建和内存共享
- Nydus 优化镜像分发与 rootfs 准备

但在当前 QEMU 实现中：

- `virtio-fs-nydus` 与 VM Templating 不能共用

这意味着在现实部署中往往需要做取舍：

- 如果更关注高密度和 VM 启动本身，模板更有吸引力
- 如果更关注镜像冷启动和大镜像加载，Nydus 更直接

而在 Cloud Hypervisor 现状下，由于模板能力未闭环，Nydus 的现实优先级就更高。

---

## 六、Go runtime 与 runtime-rs 的差异

## 6.1 VM Cache / VM Templating 仍以 Go runtime 和 QEMU 路径最成熟

Go runtime 的 `virtcontainers/factory` 是这两类能力最完整、最传统的实现位置。

runtime-rs 中已经有模板框架，但当前主线状态更像：

- 框架已经铺好
- QEMU 路径在继续承接
- 其他 Hypervisor 尤其是 Cloud Hypervisor，还没有把模板能力真正补齐

## 6.2 Nydus 在 runtime-rs 中的资源层表达更清晰

相比 Go runtime，runtime-rs 在 `resource/rootfs` 这一层把 Nydus 模型拆得更清楚：

- Nydus rootfs 是一种 rootfs 类型
- 通过 RAFS 和 overlay 组合成最终 rootfs
- 与 share-fs、device manager、agent storage 之间的边界更明确

如果后续要继续做架构级研究，runtime-rs 的 Nydus 路径更适合深入分析其资源组织模型。

---

## 七、面向 Cloud Hypervisor 的研究建议

如果后续研究以 `Cloud Hypervisor` 为主，建议按下面顺序推进。

## 7.1 第一优先级：Nydus

应优先研究：

- `nydusd` 启动参数与 API 交互
- `virtio-fs-nydus` 与 CH 的共享卷接入
- runtime-rs 中 RAFS + overlay 的 rootfs 组装
- prefetch 文件列表与首访延迟的关系

这是当前最可能产出真实优化结论的方向。

## 7.2 第二优先级：VM Cache 在 CH 上的语义真实性

建议重点验证：

- CH 当前空实现的 `PauseVM/ResumeVM` 是否只是占位
- 工厂缓存模式在 CH 上运行时到底缓存了什么
- 当前测试和运行路径是否真的能证明 CH 上 VM Cache 有效

也就是说，对 CH 场景研究 VM Cache，重点不是“怎么配置”，而是“这个能力现在到底有没有成立”。

## 7.3 第三优先级：VM Templating 在 CH 上的能力缺口

建议重点研究：

- CH 缺的到底是 pause/save/restore 能力，还是 Kata 侧没接
- runtime-rs 模板框架要扩展到 CH，需要打通哪些抽象层
- CH 若未来支持模板/快照恢复，Kata 现有工厂框架哪些部分可以直接复用

这部分更适合做“能力缺口分析”，不适合作为当前可落地优化路径。

---

## 八、最终结论

基于当前仓库主线代码现状，可以得出以下判断：

### 8.1 VM Cache

- 已有成熟工厂框架
- 语义上依赖“预创建并暂停基础 VM”
- 文档层明确定位为 QEMU 能力
- 在 Cloud Hypervisor 上由于 pause/resume 为空实现，不能视为成熟可用能力

### 8.2 VM Templating

- 主线实现核心仍然落在 QEMU
- Go runtime 和 runtime-rs 都有模板框架
- 但真正的保存/恢复链路在 QEMU 上最完整
- 在 Cloud Hypervisor 场景下，当前更像未闭环能力，而非可直接依赖的优化方案

### 8.3 Nydus

- 当前最适合在 Cloud Hypervisor 场景中深入研究
- 配置、共享文件系统、daemon、rootfs 组织路径都较明确
- Go runtime 和 runtime-rs 均有实现
- 它优化的是镜像和 rootfs 准备阶段，而不是 VMM 冷启动本身

### 8.4 总体判断

如果当前目标是研究 **Cloud Hypervisor 作为 VMM 时的 Kata Containers 性能优化技术**，那么最合理的技术主线应当是：

1. 先研究 `Nydus`
2. 再审视 `VM Cache` 在 CH 上是否真正成立
3. 最后把 `VM Templating` 作为“能力差距分析”而不是“现成可用优化项”

这也是当前主线代码能够支撑的最稳妥结论。
