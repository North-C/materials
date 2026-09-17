# CubeSandbox Pause / Resume / Restore 阶段细化与低扰动插桩设计

## 1. 文档信息

- 日期：2026-07-21
- 适用版本：CubeSandbox v0.5.1，社区基线 commit `a164417f497234a0d787cb328b0ae96480b1569b`
- 分析源码树：`source_code/CubeSandbox`（行号均以此树为基准）
- 关联文档：
  - `CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md`（主报告，实验矩阵）
  - `CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_20260720.md`（机制与规范语义）
  - `CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ANALYSIS_20260721.md`（独立调用链与真实代码摘录）
- 本文目标：
  1. 把 Pause / Resume / Restore 三个阶段拆解到函数与行号级别；
  2. 指出机制文档和主报告中已被源码证据修正的两处偏差；
  3. 给出每条链路上建议的日志/插桩点，并按扰动等级分类，说明如何在减少对实验结果扰动的前提下完成观测。

## 2. 重要勘误：Template 构建的真实调用链

### 2.1 主报告 §10.4 的结论需要修正

主报告 §10.4 写道：

```text
CubeShim/shim/src/sandbox/sb.rs
SandBox::create_snapshot
  -> CubeHypervisor::pause_vm
  -> CubeHypervisor::snapshot_vm
  -> CubeHypervisor::resume_vm
```

源码证据表明这一结论不成立：

1. `SandBox::create_snapshot`（`CubeShim/shim/src/sandbox/sb.rs:1172-1182`）在整个仓库内
   **没有任何调用者**。对 `create_snapshot` 的全仓库 grep 只命中该定义本身、
   `snapshot/mod.rs:359` 的冷启动同名函数、CubeAPI/Cubelet/SDK 的同名无关函数。
2. v15 在该函数内加入的 `template_snapshot_begin/paused/saved/resumed` 四条日志，
   在 v15 Template 构建证据中 **0 次命中**（已核对
   `remote-results/arm64-vcpu-sync-v10-20260720/v15-timer-state-trace/template/` 下
   `timer-trace.log`、`vmm-template.log`、`cubelet-journal.log`）。
   v15 实际捕获到的 Template 阶段数据全部来自 `cpu.rs` 中 VMM 侧的
   `ARM64_TIMER_TRACE` 日志。

### 2.2 真实调用链（已用源码和日志双重确认）

```text
Cubelet services/cubebox/appsnapshot.go
  Step 1-3: 创建临时可写层、Template 内存卷、collectEnvdVersion
  Step 4 (appsnapshot.go:283-297)
    -> executeCubeRuntimeSnapshot (appsnapshot.go:630-651)
       exec.CommandContext(DefaultCubeRuntimePath,
         "snapshot", "--app-snapshot", "--vm-id", <sandboxID>, "--path", ...,
         "--snapshot-type", "full", "--memory-vol", ...)   // 独立子进程
  -> cube-runtime CLI 进程（独立二进制，见 2.3）
       cube-runtime/src/main.rs:34-36 分派 snapshot 子命令
       -> shim/src/snapshot/cmd.rs:118-128 execute()
       -> shim/src/snapshot/mod.rs:101-109 Snapshot::handle
       -> do_app_snapshot (mod.rs:119-138)
          PUT /api/v1/vm.pause    (api_pause_vm,    mod.rs:140-152)
          PUT /api/v1/vm.snapshot (api_snapshot_vm, mod.rs:154-179)
          PUT /api/v1/vm.resume   (api_resume_vm,   mod.rs:147 附近)
          // HTTP/1.1 over unix socket /run/vc/vm/<id>/chapi
          // (request_ch, mod.rs:181-228；chapi 路径 common/utils.rs:280-282)
  -> 目标 Sandbox 的 shim 进程（containerd-shim-cube-rs）内的 VMM 线程处理
       hypervisor/vmm/src/lib.rs:1898 "API request event: VmPause/VmSnapshot/VmResume"
```

即：**触发方是 Cubelet 拉起的短命 `cube-runtime` CLI 进程，通过 HTTP over unix socket
驱动 Sandbox 自己 shim 进程内的 VMM**。v15 Template 日志（`vmm-template.log:122-153`）
与此完全一致：`API request event: VmPause` → `VmSnapshot(...)` → `VmResume`，中间夹着的
`cpu_manager_pause/snapshot/resume` 日志来自 shim 进程内的 VMM 线程。

### 2.3 v13/v14 未命中真实路径的真正原因

`CubeShim` 下存在两个独立二进制：

| 二进制 | crate | 作用 |
| --- | --- | --- |
| `containerd-shim-cube-rs` | `CubeShim/shim`（`shim/Cargo.toml:7-9` `[[bin]]`） | 常驻 shim 进程，托管 VMM 线程 |
| `cube-runtime` | `CubeShim/cube-runtime`（独立 package） | CLI，`snapshot` 子命令执行 `do_app_snapshot` |

- v13 修改的是 `snapshot/mod.rs::create_snapshot`（冷启动路径 `do_snapshot` 用，
  `mod.rs:359`），app snapshot 根本不经过它——改错了函数。
- v14 修改的是 `do_app_snapshot`，函数选对了，但等待逻辑编译进的是
  **`cube-runtime` 二进制**。实验部署流程只替换 `containerd-shim-cube-rs`
  （见主报告 §4.3 的部署路径与二进制 SHA256 管理），`cube-runtime` 未重新部署，
  因此 50 ms 等待不可能生效。

**结论**：v13/v14 均未构成对静止窗口假设的有效检验，且原因不同。后续任何命中
Template 构建路径的实验必须同时满足：

1. 修改点位于 `do_app_snapshot`（cube-runtime 侧）或 VMM/CpuManager 层（shim 侧）；
2. **两个二进制都重新构建并部署**，部署后用 `cube-runtime snapshot --help` 或版本
   横幅确认新二进制生效；
3. 用 VMM 日志中 `VmPause` 与 `VmSnapshot` 的 `API request event` 时间差证明等待
   实际生效（该日志每个请求必打，`lib.rs:1898`）。

### 2.4 机制文档的两处小修正

对 `CUBESANDBOX_ARM64_TEMPLATE_QUIESCENCE_KVM_ANALYSIS_20260720.md`：

1. §4.2 描述“等待该 vCPU 的 `vcpu_run_interrupted = true` -> 依次调用 `Vcpu::pause()`”。
   实际 ACK 等待**内嵌在 `signal_thread()` 的 1 ms 重试循环里**
   （`cpu.rs:594-609`：发 SIGRTMIN → 检查 `vcpu_run_interrupted` → 未置位 sleep 1ms 重试）；
   `CpuManager::pause()`（`cpu.rs:2051-2078`）在 signal 全部完成后才逐 vCPU 调
   `Vcpu::pause()`，且 aarch64 下 `Vcpu::pause` 是 `Pausable` trait 的空默认实现
   （`cpu.rs:413`）。真正的暂停动作全部发生在 vCPU 线程自己的 pause 分支里。
2. §4.3/4.4 的语义不变，但注意 vCPU 线程 pause 分支位于主循环**最顶部**
   （`cpu.rs:968-999`），是先检查 pause flag 再进入正常 `KVM_RUN` 的结构。

## 3. Pause 阶段逐层细化（Template 构建侧）

以下按调用层次展开，每层给出代码位置、动作、同步语义和已有观测点。v15 实测耗时
取自 `v15-timer-state-trace/template/vmm-template.log`（2 vCPU / 2000Mi Template
`tpl-687c...`）。

### 3.1 L0：Cubelet（Go）

`Cubelet/services/cubebox/appsnapshot.go`：

- Step 1-3：临时可写层、内存卷（`CreateTemplateMemoryVolume`）、`collectEnvdVersion`
  （必须在 Step 4 前完成，因为之后 guest 被标记为 app-snapshotting、exec 被禁用，
  对应 shim 侧 `task_srv.rs:514-516`）。
- Step 4（`appsnapshot.go:283-297`）：`executeCubeRuntimeSnapshot`，同步等待
  `cube-runtime` 子进程退出（`exec.CommandContext ... CombinedOutput`，
  `appsnapshot.go:642-643`）。子进程 stdout/stderr 打入 cubelet 日志
  （`appsnapshot.go:649`），这是 cube-runtime 侧插桩输出的天然回收通道。

### 3.2 L1：cube-runtime CLI 进程

- `snapshot/cmd.rs:118-128`：`execute()` 构造 `Snapshot`，app 模式下 `id` 被覆盖为
  `--vm-id`（`cmd.rs:154-159`）。
- `snapshot/mod.rs:101-109`：`handle()` 先 `check_path()`（`:421-441`）再分派。
- `do_app_snapshot`（`mod.rs:119-138`）：

```rust
self.api_pause_vm().await?;                  // 失败直接返回，不 resume
let snapshot_result = async {
    self.api_snapshot_vm().await?;
    self.store_metadata()                    // 写 metadata.json
}.await;
let resume_result = self.api_resume_vm().await;  // 即使 snapshot 失败也尝试 resume
```

- 通信（`request_ch`，`mod.rs:181-228`）：hyper HTTP/1.1 over unix socket
  `/run/vc/vm/<id>/chapi`，**仅以 HTTP 2xx 判定成功，无显式超时、无重试**。
  pause 返回 200 后**不再确认 VM 已进入 Paused**就直接发 snapshot。
- 现有观测：只有 `println!`（`cmd.rs:121,126,136,160`）和错误包装
  （`"pause vm failed:{}"` `:143`），**全程零结构化日志**。

### 3.3 L2：VMM API 事件线程（shim 进程内）

- `hypervisor/vmm/src/lib.rs:275-374`：`start_vmm_thread()` spawn 名为 `vmm` 的线程，
  应用 `Thread::Vmm` seccomp（`:320-323`），所有 API 请求都在此线程串行处理。
- `control_loop`（`lib.rs:1818` 起）：epoll → `EpollDispatch::Api` → 收 `ApiRequest`。
- **每个请求必打** `info!("API request event: {:?}", api_request)`（`lib.rs:1898`，
  `VmmPing` 除外），这是 Shim↔VMM 边界上现成、零成本的阶段时间戳。
- 分发（`lib.rs:1958-2003`）：`VmPause`→`vm_pause()`（`:608-614`）、
  `VmSnapshot`→`vm_snapshot()`（`:640-651`，snapshot 后 `vm.send()` 写盘）、
  `VmResume`→`vm_resume()`（`:625-631`）。
- fork 特有的合并请求：`VmPauseToSnapshot`（`:616-623`，pause→snapshot→delete）和
  `VmResumeFromSnapshot`（`:633-638`，= 仅 `vm_restore`），用于运行时 Pause/Resume，
  见第 6 节。

### 3.4 L3：`Vm::pause()`（`hypervisor/vmm/src/vm.rs:2580-2616`）

```text
event!("vm","pausing")                       :2582
state.try_write() 校验 Running->Paused        :2583-2591
[x86_64 only] 保存 clock                      :2593-2601 (aarch64 无)
activate_virtio_devices()                     :2605-2607
cpu_manager.lock().pause()                    :2609      <- L4
device_manager.lock().pause()                 :2610
*state = Paused                               :2612
event!("vm","paused")                         :2614
```

`event!` 宏定义于 `hypervisor/event_monitor/src/lib.rs:67-82`，JSON 输出，**仅在
`--event-monitor path=...|fd=...` 配置后生效**，未配置时为空操作（fd 设 O_NONBLOCK，
`event_monitor/src/lib.rs:19-35`）。这是天然的低扰动观测通道，见 §8.4。

### 3.5 L4：`CpuManager::pause()`（`cpu.rs:2051-2078`）

```text
vcpus_pause_signalled.store(true, SeqCst)     :2054
for each vcpu_state: signal_thread()          :2059-2061  <- L5（内含 ACK 等待）
for each vcpu: lock(); vcpu.pause()           :2063-2065  (aarch64 空实现)
[x86_64] notify_guest_clock_paused()          :2066-2074
```

v15 实测（2 vCPU）：`cpu_manager_pause_begin` → vcpu0 ACK 1064 µs → vcpu1 ACK 2126 µs
→ `cpu_manager_pause_complete elapsed_us=2129`。即整个 CpuManager pause 约 2.1 ms，
瓶颈是等待最后一个 vCPU 完成 immediate-exit 运行。

### 3.6 L5：`signal_thread()`（`cpu.rs:594-609`）

```rust
loop {
    pthread_kill(handle.as_pthread_t(), SIGRTMIN());   // :598
    if vcpu_run_interrupted.load(SeqCst) { break; }     // :600 ACK
    thread::sleep(1ms);                                 // :605 防优先级反转
}
```

ACK 语义 = “vCPU 线程已执行到 `vcpu_run_interrupted.store(true)`”
（`cpu.rs:994`），即已经完成 immediate-exit `KVM_RUN`，**但尚未进入 `park()`**。

### 3.7 L6：vCPU 线程 pause 分支（`cpu.rs:968-999`，主循环最顶部）

```text
if vcpu_pause_signalled (SeqCst) {
    vcpu.lock().set_immediate_exit(true)                :986
    vcpu.lock().run()  // 期望 Ok(VmExit::Ignore)        :987-990  否则 error + break
    vcpu.lock().set_immediate_exit(false)               :991
    vcpu_run_interrupted.store(true)                    :994   <- L5 等的 ACK
    while vcpu_pause_signalled { thread::park() }       :995-997 虚假唤醒防护
    vcpu_run_interrupted.store(false)                   :998
}
```

要点：

- immediate-exit 的再次 `KVM_RUN` 是 KVM 文档要求：PIO/MMIO 等退出只有 userspace
  重新进入 `KVM_RUN` 后才算完成，guest 状态才一致（注释 `cpu.rs:969-982`）。
- 三次 `vcpu.lock()` 与 snapshot 侧的 `vcpu.lock().snapshot()` 互斥，提供部分一致性。
- ACK（`:994`）与 `park()`（`:996`）之间存在指令窗口；`VmPause` 返回时 vCPU 线程
  可能还没睡着。这就是“静止窗口假设”关注的边界，但机制文档 §4.5 已说明：pause flag
  已置位 + mutex 串行化使可快照状态大概率已稳定，固定 sleep 不能替代寄存器级证据。

### 3.8 三个“已暂停”语义层级（修正版）

| 层级 | 判定 | 代码证据 | VmPause 返回时是否保证 |
| --- | --- | --- | --- |
| VM 逻辑状态 `Paused` | 状态机迁移完成 | `vm.rs:2612` | 是 |
| vCPU 已退出并完成 immediate-exit `KVM_RUN` | `vcpu_run_interrupted=true` | `cpu.rs:994`，ACK 于 `cpu.rs:600` | 是 |
| vCPU 线程已进入 `park()` | 无任何原语表示 | `cpu.rs:995-997` | **否** |

## 4. Snapshot 保存阶段（Pause 之后、Resume 之前）

### 4.1 `Vm::snapshot()`（`vm.rs:2663-2734`）

要求当前状态必须为 Paused（`:2678-2683`），然后依次：

```text
Snapshot::new_from_state(VM_SNAPSHOT_ID)     :2721
cpu_manager.snapshot()                       :2723   <- 4.2
memory_manager.snapshot()                    :2724
[aarch64] add_vgic_snapshot_section()        :2726-2728  <- 4.3
device_manager.snapshot()                    :2730
```

之后 `vm_snapshot()`（`lib.rs:640-651`）调 `vm.send()` 把快照写到
`destination_url`。v15 实测：`VmPause`（t=4815 ms）→ `VmSnapshot`（t=4818）→
`VmResume`（t=4941），即 Pause→Snapshot 约 1-3 ms，Snapshot→Resume 约 123 ms
（含 2 GiB 内存快照写卷）。

### 4.2 vCPU 状态保存（`cpu.rs:2099-2114` → `kvm/mod.rs:2037-2085`）

每个 vCPU：`vcpu.lock().snapshot()` → aarch64 `Vcpu::state()`：

```text
get_mp_state()          KVM_GET_MP_STATE            :2040
get_regs()              core regs（逐 KVM_GET_ONE_REG）:2044
RegList::new(500) + KVM_GET_REG_LIST                :2050-2055
retain(is_system_register)                          :2064  (定义 aarch64/mod.rs:91-105)
逐 id KVM_GET_ONE_REG，按内核列表原顺序 push         :2068-2080
```

**关键事实**：代码不排序、不感知 timer。保存向量的顺序完全继承内核
`KVM_GET_REG_LIST` 输出，其中 arch timer 固定为 index 8=`KVM_REG_ARM_TIMER_CTL`、
9=`KVM_REG_ARM_TIMER_CNT`、10=`KVM_REG_ARM_TIMER_CVAL`。v15 实测每 vCPU
`sys_regs=259`。

### 4.3 vGIC 保存（`vm.rs:2256-2284` → `hypervisor/src/kvm/aarch64/gic/mod.rs:316-395`）

- 先 `set_gicr_typers(&saved_vcpu_states)`（`vm.rs:2270`），再 `gic.snapshot()`。
- 保存内容（`Gicv3ItsState`，`gic/mod.rs:109-120`）：`gicd_ctlr` → dist
  （GICD_CTLR/STATUSR/IGROUPR/ISENABLER/ICENABLER/ISPENDR/ICPENDR/ISACTIVER/
  ICACTIVER/IPRIORITYR/ICFGR/IROUTER，约 568 项）→ redist → icc
  （ICC_SRE/CTLR/IGRPEN0/1/PMR/BPR0/1/AP0R0-3/AP1R0-3）→ ITS 表。
- **注意**：`GICR_ISPENDR0` 读的是 software-latched pending；level-sensitive 的
  timer PPI 真实电平要由 `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO` 单独读，当前快照
  不保存 line level（机制文档 §9.4）。

## 5. Resume 阶段逐层细化（Template 构建侧）

```text
cube-runtime: api_resume_vm (mod.rs:147)  PUT /api/v1/vm.resume
  -> VMM: vm_resume (lib.rs:625-631)
  -> Vm::resume (vm.rs:2618-2646)
       cpu_manager.resume()                 :2630   <- 下文
       [x86_64] 恢复 clock                   :2631-2638
       device_manager.resume()               :2639
       state = Running; event!("vm","resumed") :2644
  -> CpuManager::resume (cpu.rs:2080-2096)
       逐 vCPU lock().resume()（空实现）      :2081-2083
       vcpus_pause_signalled.store(false)     :2086
       逐 unpark_thread()                     :2092-2094
```

vCPU 线程被 unpark 后从 `cpu.rs:995-997` 的 park 循环退出，`:998` 清
`vcpu_run_interrupted`，回到主循环 `:1012` 正常 `KVM_RUN`。v15 实测
`cpu_manager_resume_complete elapsed_us=6`——resume 本身几乎零成本，所有代价在
guest 重新运行之后。

## 6. 运行时 Pause/Resume 与 Restore：另外三条链路

### 6.1 运行时 Sandbox Pause（`VmPauseToSnapshot`）

```text
ttrpc Task/Pause (task_srv.rs:582-602)
  -> SandBox::pause_vm (sb.rs:1193-1222)
       状态校验/置 Paused；disconnect_agent(false)   :1196-1206
       ch.pause_vm_cube("file:///data/cubelet/root/pausevm/<id>")
           (cube_hypervisor.rs:289-301 -> ApiRequest::VmPauseToSnapshot)
       wait_notify(3s) 等事件                          :1217-1219
  -> VMM: vm_pause_to_snapshot (lib.rs:616-623) = pause + snapshot + delete
```

注意这是 **pause+落盘+删除 VM 一体**，VMM 内 Vm 对象随后被删除。

### 6.2 运行时 Sandbox Resume（`VmResumeFromSnapshot`）

```text
ttrpc Task/Resume (task_srv.rs:604-626)
  -> SandBox::resume_vm (sb.rs:1224-1226) -> resume_vm_with_config(None) (sb.rs:1293-1346)
       ch.resume_vm_cube(file://...)  (cube_hypervisor.rs:303-315 -> VmResumeFromSnapshot)
       connect_agent()                 :1315  (无重试无超时, common/utils.rs:335-369)
       reset_guest()                   :1322  (set_guest_date_time + reseed_random,
                                              ttrpc 超时 3s, sb.rs:105)
```

### 6.3 从 Template 创建 Sandbox（故障所在链路）

Shim 侧（`sb.rs`）：

```text
create_sandbox (:436-517)
  -> start_vm (:781-828)
       ch.launch_vmm()
       if by_snapshot(): restore_vm() (:838-909)
           校验 metadata.json 与请求规格          :839-856
           RestoreConfig{source_url, fs, net, disks, vsock(cid=3), memory_vol_url} :877-886
           ch.restore_vm(config) -> ApiRequest::VmRestore (cube_hypervisor.rs:173-183)
           // :889-899 等待 NotifyEvent::RestoreReady 的代码被整块注释
           //   —— VmRestore API 同步返回即视为成功
           if app_snapshot_restore: return Ok    :793-795  ★跳过 VsockServerReady 等待
       else: 等 NotifyEvent::VsockServerReady, 超时 10s :810-826
  -> connect_agent (:446; 单次尝试，无重试)
  -> reset_guest (:450-452 -> :402-434)
       set_guest_date_time + reseed_random_dev，ttrpc 超时仅 3s (sb.rs:105)
       // 故障时的 "reset guest time failed" 就发生在这里
  -> agent CreateSandbox RPC, timeout 25s (:462-502)
```

VMM 侧（`vm_restore`，`lib.rs:653-733`）：读 config/state → `Vm::new_from_snapshot`
→ `vm.restore(snapshot)` → **`vm.resume()` 紧随其后（`lib.rs:726-727`），restore 与
resume 在同一个 API 请求内完成**。

`Vm::restore`（`vm.rs:2736-2811`）内部顺序：

```text
event!("vm","restoring")                          :2737
校验可转到 Paused                                  :2739-2745
device_manager.restore()                          :2751-2760
cpu_manager.restore()                             :2762-2771
    逐 vCPU create_vcpu (cpu.rs:795-829)
      -> vcpu.init(&vm)                           :807-808
      -> vcpu.restore(snapshot) -> set_state()    :810
aarch64: restore_vgic_and_enable_interrupt()      :2773-2774  <- 见下
device_manager.restore_devices()                  :2776-2785
cpu_manager.start_restored_vcpus()                :2787-2794
    -> activate_vcpus(n, false, Some(true)) (cpu.rs:1178-1185, 1107-1144)
       vcpus_pause_signalled.store(true)          :1121-1123
       start_vcpu 逐线程启动 (cpu.rs:872-1104)
       // 新线程第一圈即命中 pause 分支 -> immediate-exit KVM_RUN -> park
state = Paused; event!("vm","restored")           :2808-2809
```

`restore_vgic_and_enable_interrupt`（`vm.rs:2286-2359`）：

```text
create_vgic(Gic::create_default_config(vcpu_count))  :2300-2308
cpu_manager.init_pmu(AARCH64_PMU_IRQ + 16)           :2311-2315
set_gicr_typers(saved_states)                        :2318-2325
按 GIC_V3_ITS_SNAPSHOT_ID 恢复 GIC 状态               :2328-2341
    gic set_state (gic/mod.rs:398-462):
      gicd_ctlr -> dist -> redist -> icc -> ITS -> RESTORE_TABLES -> ITS CTLR
enable() 开启 legacy irq 路由                          :2343-2357
```

### 6.4 Restore 阶段的三个关键时序窗口

**窗口 W1：timer 提前启用（vCPU set_state 内部）**
`set_state()`（`kvm/mod.rs:2176-2192`）原样遍历 sys_regs：先写 `CTL`（idx 8）
再写 `CNT`（idx 9）/`CVAL`（idx 10），最后 `set_mp_state`（`:2189`）。对
`CTL=5`（ENABLE+ISTATUS）且 CVAL 已过期的快照，**timer 在 CNT/CVAL 写好之前就被
启用**，KVM 可在此时即按旧 counter 评估 timer line。

**窗口 W2：timer 已启用但 vGIC 未恢复**
CPU0、CPU1 的 set_state 在 `cpu_manager.restore()` 内先后完成（`vm.rs:2762-2771`），
而 vGIC 的 create/restore/enable 在 `:2773-2774`。两个 vCPU 的 timer 都处于
已恢复状态时，GIC redistributor 的 pending/active/enable 还是新建默认值。timer PPI
line 与 vGIC latch 的合并发生在这段时间内，是 P0 假设关注的竞态窗口。

**窗口 W3：unpark 到首次 KVM_RUN**
`start_restored_vcpus` 让新线程先 park（`cpu.rs:1121-1137`），`vm.resume()`
（`lib.rs:727` → `CpuManager::resume` `cpu.rs:2080-2096`）清 flag 并 unpark。
vCPU 线程离开 park 后进入首个正常 `KVM_RUN`（`cpu.rs:1012-1014`）。guest 首次
执行时 timer line、PPI pending、PSTATE.I、MP state 的组合决定 CPU1 是否拿到
第一个 tick。基线代码在 `set_state`（kvm 侧）到 `Starting vCPU`（`cpu.rs:912`）
之间**完全没有日志**，v16 的 readback 正是填在 W1/W2 之间。

### 6.5 seccomp 的一个现存缺口

`hypervisor/vmm/src/seccomp_filters.rs`：KVM ioctl 常量区 `:125-152`，VMM 线程
通用白名单 `:211-243`（含 `KVM_SET/GET_ONE_REG`、`KVM_SET_DEVICE_ATTR` 等），
aarch64 扩展 `:400-414` 只有三项。**全仓库不存在 `KVM_ARM_SET_COUNTER_OFFSET`
（VM 级 ioctl，编号 `0x4030aea5`）的定义和白名单项**。这与 v5 实验的 SIGSYS
拦截一致；任何走 VM offset 的修复都必须先补 seccomp 常量区和 aarch64 规则，
并核对 vCPU 线程规则（`vcpu_thread_rules`，同文件后半）。

## 7. 插桩设计：在哪条链路、哪个点、以什么扰动等级观测

### 7.1 v15/v16 的经验教训（先定量，再谈原则）

v15/v16 单次创建只产生约 6 条 trace 日志（恢复侧）+ 14 条（模板侧），格式为
`ARM64_TIMER_TRACE event=... key=value`，无 env 开关、半结构化、每阶段一次。
即便如此少量的日志，A/B 实验证明足以让确定性失败的 `tpl-3394...` 变为成功
（主报告 §12）。教训是：

> **扰动大小不由日志条数决定，而由日志点是否落在关键时序窗口内决定。**
> 一条位于 W1/W2 窗口内、带格式化 + 写日志（数百微秒）的 `info!`，就足以改变
> timer/vGIC 竞态的结果。反之，窗口外的等量日志几乎无影响。

因此下一轮插桩的核心策略是：**把“采集”和“输出”分离**——窗口内只做纳秒级的
时间戳与数值拷贝（写预分配内存），把格式化与日志写盘推迟到窗口关闭之后
（snapshot 完成后 / resume 完成后 / restore 完成后）。

### 7.2 扰动分级

| 级别 | 含义 | 例子 | 对竞态窗口的影响 |
| --- | --- | --- | --- |
| L0 零扰动 | 不改二进制，或只用已有日志 | `API request event` 时间戳、`event!` monitor、宿主侧 perf/bpftrace | 无（bpf 开销在宿主线程外） |
| L1 低扰动 | 窗口外的单条日志/计数 | resume 完成后批量输出采集缓冲；cube-runtime CLI 侧日志 | 可忽略 |
| L2 中扰动 | 窗口内的纯内存操作 | 窗口内 `Instant::now()` + 寄存器值拷贝到预分配 buffer | 纳秒级，一般可忽略 |
| L3 高扰动 | 窗口内的格式化/IO/额外 ioctl | v15 的逐 vCPU `info!`、v16 的 `KVM_GET_ONE_REG` 读回 | **已证明改变结果** |
| L4 禁止作为观测 | sleep、额外同步原语 | v10/v11 ACK、v13/v14 50ms | 直接改变被测对象 |

v16 的 `KVM_GET_ONE_REG` 读回要单独强调：它不只是打印——每次 GET 都进入 KVM，
可能触发 KVM 内部 timer 状态同步，属于 L3。读回数据有价值，但必须意识到
“读回成功 + 创建成功”是在扰动后的系统上取得的。

### 7.3 通用工程措施

1. **env 开关，默认关闭**：如 `CUBE_ARM64_TRACE=1`，启动时用 `OnceLock`/`lazy`
   读取一次，热路径只付一次原子 load。避免靠日志级别当开关（CubeShim 的
   级别由 shim debug flag 决定，`task_srv.rs:54-59`，无 env 控制）。
2. **采集/输出分离**：定义 per-VM 的 `TraceBuf`（固定大小数组 + 游标），窗口内
   `push(TraceEvent{mono_ns, event, vcpu, vals})`（L2），在以下“安全点”统一
   `info!` 批量输出（L1）：
   - Template 侧：`Vm::snapshot()` 返回后、`Vm::resume()` 完成后；
   - Restore 侧：`vm.resume()` 完成后（`lib.rs:727` 之后）、或首次 ttrpc 成功后。
3. **单行结构化**：沿用 `ARM64_TIMER_TRACE` 前缀 + `key=value`，但寄存器值不要
   用 `{:?}` 打印 `Option<(index, u64)>`，直接展开为整数字段，减少格式化和
   下游解析成本。
4. **绝不在热循环和持锁点打印**：vCPU 主循环（`cpu.rs:1012` 之后）禁止日志；
   `vcpu.lock()` 持有期间禁止格式化（v15 在 pause 分支的日志在锁外，保持这一
   约束）。
5. **时间戳语义统一**：统一用 `CLOCK_MONOTONIC` 纳秒（`Instant` 不行时就
   `libc::clock_gettime`），字段含 `pid/tid/host_cpu(sched_getcpu)/vcpu_id`，
   与主报告 §15.1 的字段表一致。
6. **timer 采样用包围法**：读 `CVAL/CTL` 前后各取一次 `CNTVCT` 样本，把真实
   采样时刻约束在 `[cntvct_before, cntvct_after]` 区间内，避免逐寄存器读取
   非原子带来的误判（机制文档 §7.3/§11.2）。
7. **判定字段预计算**：`enable/imask/istatus/condition_met/expired/expected_line`
   按无符号 64 位语义算好后随事件输出，不要用 `Signed64(CNTVCT-CVAL)` 替代
   规范判断。

### 7.4 分链路插桩点清单

#### A. Template 构建（app snapshot）链路

| # | 事件 | 位置 | 级别 | 说明 |
| --- | --- | --- | --- | --- |
| A1 | `cubelet_appsnapshot_step4_begin/end` | `appsnapshot.go:283/297` | L1 | cubelet 已有 stepLog，补耗时字段即可 |
| A2 | `cli_pause_req/resp` | `snapshot/mod.rs:140-152`（`api_pause_vm`） | L1 | cube-runtime 进程 stdout 会被 cubelet 回收（`appsnapshot.go:649`）；补单调时钟耗时 |
| A3 | `cli_snapshot_req/resp`、`cli_resume_req/resp` | `mod.rs:154-179`、`:147` | L1 | 同上；resp 里带 HTTP status 与服务端耗时（若 A4 增加 header 回传） |
| A4 | （已有）`API request event: VmPause/VmSnapshot/VmResume` | `lib.rs:1898` | L0 | 直接用相邻 `API request event` 时间差量化 Pause→Snapshot 间隔 |
| A5 | `vm_pause_state_enter/exit` | `vm.rs:2582/2614` | L0-L1 | `event!` 已有；开启 `--event-monitor fd` 即得，无需改代码 |
| A6 | `cpu_pause_begin / vcpu_pause_ack / cpu_pause_end` | `cpu.rs:2054/2060/2077` | L2 采集 + L1 输出 | v15 已有等价点；改为写 TraceBuf，`Vm::snapshot` 结束后输出 |
| A7 | `vcpu_immediate_exit_begin/end`、`vcpu_before_park` | `cpu.rs:986/991/995` | **L3，谨慎** | 位于 vCPU 线程关键路径；只在验证“静止窗口”假设时短期开启，且只写 TraceBuf 不打印 |
| A8 | `vcpu_snapshot_timer_state` | `cpu.rs:414-463`（`Vcpu::snapshot`） | L2 | 记录 PC/PSTATE/MP + timer 五元组（CTL/CNT/CVAL/CNTKCTL/CNTPCT），包围法采样 |
| A9 | `vgic_snapshot_begin/end` | `vm.rs:2270/2281` | L1 | 与 A8 对齐，确认 vGIC 保存发生在全部 vCPU 保存之后 |

预期新增输出量：每次 Template 构建 ≤ 20 条（批量输出后），且全部在窗口外落盘。

#### B. Template 恢复（创建 Sandbox）链路

| # | 事件 | 位置 | 级别 | 说明 |
| --- | --- | --- | --- | --- |
| B1 | `shim_restore_begin/end` | `sb.rs:838/907` | L1 | 顺手补上 `RestoreVm` 的 StatDefer 已覆盖部分（`cube_hypervisor.rs:175,181`） |
| B2 | `vcpu_restore_saved_state` | `cpu.rs:490` 附近（set_state **之前**，纯内存读快照数据） | L2 | v15 已有等价点；此点不与 KVM 交互，是唯一零 KVM 副作用的 timer 状态来源 |
| B3 | `kvm_set_state_timer_order` | `kvm/mod.rs:2181-2187` 循环内，仅对 timer 三个 id 写 TraceBuf | L2 | 记录每个 timer one-reg 的 id/值/SET 返回码/单调时间；**不在此处打印** |
| B4 | `kvm_timer_readback` | `kvm/mod.rs:2189` 之前（v16 位置） | **L3** | 保留为可选 env 子开关 `CUBE_ARM64_TRACE_READBACK=1`，默认关；明确标注其 KVM 副作用 |
| B5 | `vgic_restore_begin/end`、`gic_set_state_stage` | `vm.rs:2328-2341`、`gic/mod.rs:398-462` | L1/L2 | 标记 dist/redist/icc 各阶段完成时间，与 B3 的 timer 时间戳对齐 |
| B6 | `restored_vcpu_thread_started_paused` | `cpu.rs:912`（`Starting vCPU`）附近 | L1 | 基线已有 `info!`，补 `paused=true` 与 tid |
| B7 | `cpu_resume_begin/end`、`vcpu_unpark` | `cpu.rs:2086/2092` | L2 | 记录每个 vCPU unpark 的单调时间 |
| B8 | `vcpu_first_kvm_run_enter/exit` | `cpu.rs:1012-1014`，仅首次（per-vCPU once flag） | **L3** | 记录进入时刻、exit reason、是否 WFI wakeup；这是 P1 假设“首次 KVM_RUN 与 GIC ready 顺序”的直接证据，但位于最敏感点，用 once flag + TraceBuf 把成本压到最低 |
| B9 | `vm_restore_done`、`vm_resumed` | `lib.rs:726/727`、`vm.rs:2644` | L1 | 窗口关闭点；在此批量输出 B2-B8 的 TraceBuf |
| B10 | `reset_guest_begin/end`、`agent_connect_begin/end` | `sb.rs:402-434`、`utils.rs:335-369` | L1 | 3 s ttrpc 超时的上下文；失败时把 B 系列缓冲一并 dump，便于失败/成功对齐 |
| B11 | `vsock_ready` | `sb.rs:810-826` 等待处 | L1 | 注意 `app_snapshot_restore` 跳过该等待（`sb.rs:793-795`），日志要体现走了哪条分支 |

#### C. 运行时 Pause/Resume（`VmPauseToSnapshot`/`VmResumeFromSnapshot`）

复用 A 系列的 VMM 层点（A4-A9）与 B 系列的 restore 点（B2-B9），Shim 侧补：
`task_srv.rs:583/600`（已有 `"pause req start/finish"`）、`sb.rs:1210-1219`
（`pause_vm_cube` + `wait_notify` 3s）、`sb.rs:1293-1346`（`resume_vm_with_config`
各子步骤）。全部为 L1，用于后续 Pause/Resume 矩阵回归。

### 7.5 不改二进制的免侵入观测（优先于新增插桩）

在新增任何 L3 点之前，先用宿主侧手段拿到独立证据，这些手段对 shim/VMM 二进制的
观察效应为零：

1. **`event!` monitor**：以 `--event-monitor fd=N`（O_NONBLOCK）启动 VMM，
   直接得到 `vm pausing/paused/snapshotting/snapshotted/restoring/restored`
   的 JSON 时间线（定义 `event_monitor/src/lib.rs:67-82`）。
2. **`API request event` 日志**：`lib.rs:1898` 每请求必打，Pause→Snapshot、
   Snapshot→Resume 间隔直接可算。
3. **宿主线程级观测**：vCPU 线程名为 `vcpu{id}`（`cpu.rs:916`），可用
   `perf sched`/`/proc/<pid>/task/<tid>/schedstat` 观察 ACK 前后线程何时真正
   睡眠/被唤醒，不依赖任何代码内 ACK。
4. **bpftrace/kprobe（宿主）**：跟踪 `KVM_RUN`、`KVM_SET_ONE_REG`、
   `KVM_SET_DEVICE_ATTR` 的进入/返回，重构出 set_state→vGIC→首次 KVM_RUN 的
   完整 ioctl 时间线。开销在宿主导出路径，不进入 guest 竞态窗口。
5. **guest 侧**：诊断内核限量记录 CPU1 的 arch_timer IRQ、clockevent deadline、
   scheduler tick（主报告 §15.5），与 VMM 侧 B8 对齐。

### 7.6 成功/失败对齐协议（沿用主报告 §15.6 并细化）

1. 同一插桩二进制、同一全新 Template，至少采：1 次完整成功、1 次
   `reset guest time` 失败、1 次 1 vCPU 成功对照。
2. 按 `event + vcpu_id` 对齐 B2-B10，找**第一个分歧点**；ttrpc timeout、RCU、
   shim 高 CPU 都是下游表现，不作定位依据。
3. 每个插桩版本先做“观察效应自检”：用确定性坏 Template `tpl-3394...` 做
   原版/插桩版 A/B。若插桩版把失败变成成功，说明插桩落在竞态窗口内——
   此时采到的状态数据仍可用于分析，但成功率数据必须作废，且下一轮要把
   该点改到窗口外（采集/输出分离）后重测。
4. 候选修复定稿前，必须去除 L3 点并复测全新 Template 100/100 + 坏 Template
   门禁（主报告 §20）。

## 8. 关键代码位置索引

| 模块 | 文件 | 关键行 |
| --- | --- | --- |
| Cubelet app snapshot | `Cubelet/services/cubebox/appsnapshot.go` | Step4 `:283-297`，exec `:630-651`，args `:598-628` |
| cube-runtime CLI | `CubeShim/cube-runtime/src/main.rs` | snapshot 子命令 `:34-36` |
| app snapshot 流程 | `CubeShim/shim/src/snapshot/mod.rs` | `handle` `:101-109`，`do_app_snapshot` `:119-138`，`request_ch` `:181-228`，冷路径 `create_snapshot` `:359-392` |
| Sandbox 创建/恢复 | `CubeShim/shim/src/sandbox/sb.rs` | `create_sandbox` `:436-517`，`start_vm` `:781-828`，`restore_vm` `:838-909`，`reset_guest` `:402-434`，`pause_vm` `:1193-1222`，`resume_vm_with_config` `:1293-1346`，**死代码 `create_snapshot` `:1172-1182`** |
| Shim↔VMM API | `CubeShim/shim/src/hypervisor/cube_hypervisor.rs` | `snapshot_vm/pause_vm/resume_vm` `:138-171`，`restore_vm` `:173-183`，`pause_vm_cube` `:289-301`，`resume_vm_cube` `:303-315` |
| VMM API 分发 | `hypervisor/vmm/src/lib.rs` | vmm 线程 `:275-374`，`API request event` `:1898`，分发 `:1958-2003`，`vm_restore`（内含 resume）`:653-733` |
| VM 状态机 | `hypervisor/vmm/src/vm.rs` | `pause` `:2580-2616`，`resume` `:2618-2646`，`snapshot` `:2663-2734`，`restore` `:2736-2811`，`add_vgic_snapshot_section` `:2256-2284`，`restore_vgic_and_enable_interrupt` `:2286-2359` |
| vCPU 生命周期 | `hypervisor/vmm/src/cpu.rs` | `signal_thread` `:594-609`，pause 分支 `:968-999`，`start_vcpu` `:872-1104`，`activate_vcpus` `:1107-1144`，`start_restored_vcpus` `:1178-1185`，`CpuManager::pause/resume/snapshot/restore` `:2051-2135` |
| KVM ARM64 状态 | `hypervisor/hypervisor/src/kvm/mod.rs` | `state()` `:2037-2085`，`set_state()` `:2176-2192` |
| vGIC | `hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs` | `state()` `:316-395`，`set_state()` `:398-462` |
| 事件监控 | `hypervisor/event_monitor/src/lib.rs` | `event!` `:67-82`，`set_monitor` `:19-35` |
| seccomp | `hypervisor/vmm/src/seccomp_filters.rs` | ioctl 常量 `:125-152`，vmm 通用 `:211-243`，aarch64 `:400-414`（缺 `KVM_ARM_SET_COUNTER_OFFSET`） |
| Shim 日志 | `CubeShim/shim/src/log/mod.rs` | 宏 `:27-57`，rotate `:254-259`；级别由 debug flag 决定（`task_srv.rs:54-59`） |

## 9. 结论

1. Template 构建的 Pause/Snapshot/Resume 由 Cubelet 拉起的独立 `cube-runtime`
   子进程通过 HTTP 驱动；`SandBox::create_snapshot` 是死代码。后续实验必须同时
   部署 `containerd-shim-cube-rs` 与 `cube-runtime` 两个二进制。
2. Pause 的真实完成点是 vCPU 线程完成 immediate-exit `KVM_RUN` 并置
   `vcpu_run_interrupted`（`cpu.rs:994`），而非 `park()`；三层“已暂停”语义
   不能混用。
3. Restore 与 resume 在同一 `VmRestore` API 内连续完成（`lib.rs:726-727`），
   关键窗口为 W1（CTL 先于 CNT/CVAL 写入）、W2（timer 已启用但 vGIC 未恢复）、
   W3（unpark 到首次 `KVM_RUN`）。
4. v15/v16 证明窗口内即使约 6 条日志也足以改变结果；下一轮插桩应以
   “L0 免侵入优先、L2 窗口内纯内存采集、L1 窗口外批量输出、L3 默认关闭”
   为原则，并用坏 Template A/B 对每个插桩版本做观察效应自检。
