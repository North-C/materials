# CubeSandbox ARM64 Pause / Snapshot / Resume / Restore 关联链路分析

## 1. 文档范围

- 日期：2026-07-21
- 设计目标版本：CubeSandbox v0.5.1，社区基线 commit `a164417f497234a0d787cb328b0ae96480b1569b`
- 实际取证源码树：`source_code/CubeSandbox`，当前 HEAD `30b4e25ab16891187c775e002816274427f541f1`
- 上游设计文档：`CUBESANDBOX_ARM64_PAUSE_RESUME_DETAIL_AND_INSTRUMENTATION_20260721.md`
- 关联实验报告：`CUBESANDBOX_ARM64_MULTIVCPU_COMPLETE_EXPERIMENT_REPORT_20260718.md`

本文只抽取并重组 Pause、Snapshot、Resume、Restore 的调用链与状态顺序，不重复插桩设计和实验数据。链路通过 CodeGraph AST 索引与实际函数体核对。

实际取证 HEAD 是目标基线的祖先。两者在本文覆盖文件中的差异仅位于 `hypervisor/vmm/src/cpu.rs` 的 ARM64 PMU 初始化回退与测试，不改变本文分析的 pause、snapshot、resume、restore 主链。

CodeGraph 能确定同一语言内的静态调用边。进程启动、Unix HTTP、请求通道和 trait 动态分派不表现为普通直接调用，本文将这些边明确标为“边界跳转”。

下文代码块取自上述源码树，仅按版面换行。为控制篇幅，非关键分支用 `// 省略 ...` 标明；除这些显式省略外，不用自造 helper 名称替代真实调用。

## 2. 全局边界与组件关系

![Pause、Snapshot、Resume、Restore 的进程与内核边界](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ASSETS_20260721/01-process-boundaries.svg)

链路跨越四个执行域：

| 执行域 | 关键组件 | 与下一层的接口 |
| --- | --- | --- |
| Cubelet 进程 | `AppSnapshot`、`executeCubeRuntimeSnapshot` | 启动并同步等待 `cube-runtime` 子进程 |
| `cube-runtime` 进程 | snapshot CLI、`Snapshot::do_app_snapshot` | HTTP/1.1 over Unix socket `chapi` |
| `containerd-shim-cube-rs` 进程 | HTTP API、VMM control loop、`Vm`、`CpuManager` | Rust 请求通道、trait 动态分派 |
| Linux/KVM | `KVM_RUN`、one-reg、vGIC device attributes | ioctl 与线程信号 |

`CubeShim` 目录中存在两个不同的二进制。`containerd-shim-cube-rs` 常驻并托管 VMM；`cube-runtime` 是短命 CLI。修改 app snapshot 流程时，两者的构建和部署不能混为一谈。

### 2.1 必须排除的同名死链路

`CubeShim/shim/src/sandbox/sb.rs` 中的 `SandBox::create_snapshot` 看似符合“pause → snapshot → resume”，但仓库内没有调用者，不是 Template 构建入口。

```rust
pub async fn create_snapshot(
    &self,
    snapshot_path: &str,
    snapshot_type: SnapshotType,
) -> CResult<()> {
    let ch = self.ch.as_ref().unwrap().lock().await;
    ch.pause_vm().await?;
    ch.snapshot_vm(format!("file://{}", snapshot_path).as_str(), snapshot_type)
        .await?;
    ch.resume_vm().await
}
```

因此，针对该函数的修改不会影响 Cubelet 的 app snapshot。真实入口位于 `Cubelet/services/cubebox/appsnapshot.go`，并跨进程进入 `cube-runtime`。

## 3. Template 构建：App Snapshot 调用链

![Template app snapshot 时序](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ASSETS_20260721/02-template-app-snapshot-sequence.svg)

完整逻辑链如下：

```text
Cubelet AppSnapshot Step 4
  -> executeCubeRuntimeSnapshot
  == 启动子进程 ==>
cube-runtime snapshot --app-snapshot
  -> snapshot::cmd::execute
  -> Snapshot::handle
  -> Snapshot::do_app_snapshot
  == HTTP/1.1 over Unix socket ==>
containerd-shim-cube-rs chapi
  -> VMM ApiRequest::VmPause
  -> VMM ApiRequest::VmSnapshot
  -> VMM ApiRequest::VmResume
```

### 3.1 Cubelet 启动独立 CLI 进程

`executeCubeRuntimeSnapshot` 组装 snapshot 参数，用 `exec.CommandContext` 启动 `DefaultCubeRuntimePath`，并通过 `CombinedOutput` 同步等待子进程退出。

```go
func (s *service) executeCubeRuntimeSnapshot(ctx context.Context, sandboxID string,
    spec *CubeboxSnapshotSpec, snapshotPath, memoryVol, snapshotType string) error {
    snapshotType = normalizeSnapshotType(snapshotType)
    stepLog := log.G(ctx).WithFields(CubeLog.Fields{
        "sandboxID": sandboxID, "snapshotPath": snapshotPath,
        "snapshotType": snapshotType,
    })
    args := buildCubeRuntimeSnapshotArgs(sandboxID, spec, snapshotPath,
        memoryVol, snapshotType)

    stepLog.Infof("Executing: %s %v", DefaultCubeRuntimePath, args)
    cmd := exec.CommandContext(ctx, DefaultCubeRuntimePath, args...)
    output, err := cmd.CombinedOutput()
    if err != nil {
        stepLog.Errorf("cube-runtime snapshot failed: %v, output: %s",
            err, string(output))
        return fmt.Errorf("cube-runtime snapshot failed: %w, output: %s",
            err, string(output))
    }
    stepLog.Infof("cube-runtime snapshot output: %s", string(output))
    return nil
}
```

参数构造的关键结果是：

```text
snapshot --app-snapshot --vm-id <sandbox-id> --path <snapshot-path>
         --force --snapshot-type full --memory-vol <memory-volume>
```

这条边是操作系统进程创建，不是 Go 到 Rust 的直接调用。`cube-runtime` 的 stdout/stderr 由 Cubelet 回收，因此 CLI 侧失败会沿 `CombinedOutput` 返回。

### 3.2 `cube-runtime` 分派 snapshot 子命令

`CubeShim/cube-runtime/src/main.rs` 将 snapshot 子命令交给 shim crate 暴露的命令实现：

```rust
match cli.command {
    SubCommands::Snapshot(snapshot_args) => {
        snapshot::cmd::execute(snapshot_args).await?;
    }
    // 其他子命令省略
}
```

`CubeShim/shim/src/snapshot/cmd.rs` 创建 `Snapshot`，app snapshot 模式下用 `--vm-id` 覆盖临时生成的 ID，然后调用 `handle()`。

```rust
pub async fn execute(args: SnapshotArgs) -> Result<()> {
    let mut snapshot =
        Snapshot::try_from(args).map_err(|e| anyhow!("failed to create snapshot: {}", e))?;
    println!("debuginfo force:{}, tap:{}", snapshot.force, snapshot.tap);
    snapshot
        .handle()
        .await
        .map_err(|e| anyhow!("failed to handle snapshot: {}", e))?;
    println!("snapshot success");
    Ok(())
}
```

### 3.3 `Snapshot::handle` 选择真实 app snapshot 分支

`CubeShim/shim/src/snapshot/mod.rs`：

```rust
pub(self) async fn handle(&mut self) -> CResult<()> {
    self.check_path()?;

    if self.app_snapshot {
        self.do_app_snapshot().await?;
        return Ok(());
    }
    self.do_snapshot()
}
```

`do_app_snapshot` 执行严格的 pause → snapshot/metadata → resume。snapshot 失败后仍会尝试 resume；pause 失败则直接返回。

```rust
async fn do_app_snapshot(&mut self) -> CResult<()> {
    self.api_pause_vm().await?;
    let snapshot_result = async {
        self.api_snapshot_vm().await?;
        self.store_metadata()
    }
    .await;
    let resume_result = self.api_resume_vm().await;

    match (snapshot_result, resume_result) {
        (Ok(()), Ok(())) => Ok(()),
        (Err(snapshot_err), Ok(())) => Err(snapshot_err),
        (Ok(()), Err(resume_err)) => Err(resume_err),
        (Err(snapshot_err), Err(resume_err)) => Err(format!(
            "{}; additionally resume vm failed:{}",
            snapshot_err, resume_err
        )
        .into()),
    }
}
```

三个 API 方法只负责构造路径和 snapshot 配置：

```rust
async fn api_pause_vm(&self) -> CResult<()> {
    self.request_ch("/api/v1/vm.pause", "".to_string())
        .await
        .map_err(|e| format!("pause vm failed:{}", e))?;
    Ok(())
}

async fn api_resume_vm(&self) -> CResult<()> {
    self.request_ch("/api/v1/vm.resume", "".to_string())
        .await
        .map_err(|e| format!("resume vm failed:{}", e))?;
    Ok(())
}

async fn api_snapshot_vm(&self) -> CResult<()> {
    let mut snapshot_path = PathBuf::from(self.path.clone());
    snapshot_path.push("snapshot");
    fs::create_dir_all(snapshot_path.as_path()).map_err(|e| {
        format!(
            "Failed to create path:{}, err:{}",
            snapshot_path.display(),
            e
        )
    })?;
    let config = SnapshotConfig {
        destination_url: format!("file://{}", snapshot_path.to_str().unwrap()),
        snapshot_type: self.snapshot_type,
        memory_vol_url: self.memory_vol_url.clone(),
        ..Default::default()
    };
    let data =
        serde_json::to_string(&config).map_err(|e| format!("serialize config failed:{}", e))?;
    self.request_ch("/api/v1/vm.snapshot", data)
        .await
        .map_err(|e| format!("snapshot vm failed:{}", e))?;
    Ok(())
}
```

### 3.4 Unix HTTP 是第二个关键边界

`request_ch` 连接 `/run/vc/vm/<id>/chapi`，建立 HTTP/1.1 连接并发送 PUT。代码只以 HTTP 2xx 判断成功，没有额外的 VM 状态确认，也没有显式 timeout 或 retry。

```rust
async fn request_ch(&self, path: &str, data: String) -> CResult<Bytes> {
    let address = Utils::chapi_path(self.id.as_str());
    let stream = tokio::net::UnixStream::connect(address.as_str())
        .await
        .map_err(|e| format!("connect {} failed:{:?}", address, e))?;
    let io = TokioIo::new(stream);
    let (mut sender, conn) = client::conn::http1::Builder::new()
        .preserve_header_case(true)
        .title_case_headers(true)
        .handshake(io)
        .await
        .map_err(|e| format!("handshake failed:{}", e.to_string()))?;
    tokio::task::spawn(async move {
        if let Err(err) = conn.await {
            println!("Connection failed: {:?}", err);
        }
    });

    let request = hyper::Request::builder()
        .method("PUT")
        .uri(path)
        .header("Host", "localhost")
        .header("Accept", "*/*")
        .header("Content-Type", "application/json")
        .body(Full::new(Bytes::from(data)))
        .map_err(|e| format!("build request failed:{}", e.to_string()))?;
    let response = sender
        .send_request(request)
        .await
        .map_err(|e| format!("send request failed:{}", e.to_string()))?;
    let status = response.status();
    let body_bytes = response
        .into_body()
        .collect()
        .await
        .map_err(|e| format!("collect body failed:{}", e.to_string()))?
        .to_bytes();

    if !status.is_success() {
        let body = String::from_utf8_lossy(&body_bytes);
        return Err(format!(
            "HTTP request failed with status: {}, body: {}",
            status, body
        )
        .into());
    }
    Ok(body_bytes)
}
```

`Utils::chapi_path` 给出目标 shim 的控制 socket：

```rust
pub fn chapi_path(sandbox_id: &str) -> String {
    format!("{}/{}/chapi", VM_PATH, sandbox_id)
}
```

### 3.5 VMM 请求分派

目标 shim 的 HTTP 服务将请求转为 `ApiRequest`，VMM control loop 串行处理。三个独立请求最终分别进入以下方法：

```rust
fn vm_pause(&mut self) -> result::Result<(), VmError> {
    if let Some(ref mut vm) = self.vm {
        vm.pause().map_err(VmError::Pause)
    } else {
        Err(VmError::VmNotRunning)
    }
}

fn vm_snapshot(&mut self, snapshot_config: &SnapshotConfig) -> result::Result<(), VmError> {
    if let Some(ref mut vm) = self.vm {
        vm.snapshot()
            .map_err(VmError::Snapshot)
            .and_then(|snapshot| {
                vm.send(&snapshot, snapshot_config)
                    .map_err(VmError::SnapshotSend)
            })
    } else {
        Err(VmError::VmNotRunning)
    }
}

fn vm_resume(&mut self) -> result::Result<(), VmError> {
    if let Some(ref mut vm) = self.vm {
        vm.resume().map_err(VmError::Resume)
    } else {
        Err(VmError::VmNotRunning)
    }
}
```

这里的 trait 调用依赖运行时对象，CodeGraph 不把 HTTP → request channel → trait object 还原为单条静态 Rust 调用。逻辑链由 API 枚举分派和实际方法体共同确定。

## 4. Pause 内部链路

![Pause 内部同步时序](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ASSETS_20260721/03-pause-internal-sequence.svg)

### 4.1 VM 状态机先进入过渡，再暂停 CPU 和设备

`hypervisor/vmm/src/vm.rs` 中 `Vm::pause` 的核心顺序是：校验状态迁移、激活待处理 virtio、暂停 CPU、暂停设备，最后发布 `Paused`。

```rust
impl Pausable for Vm {
    fn pause(&mut self) -> std::result::Result<(), MigratableError> {
        event!("vm", "pausing");
        let mut state = self
            .state
            .try_write()
            .map_err(|e| MigratableError::Pause(anyhow!("Could not get VM state: {}", e)))?;
        let new_state = VmState::Paused;
        state
            .valid_transition(new_state)
            .map_err(|e| MigratableError::Pause(anyhow!("Invalid transition: {:?}", e)))?;

        // 省略 x86_64 专有的 VM clock 保存分支。
        self.activate_virtio_devices().map_err(|e| {
            MigratableError::Pause(anyhow!(
                "Error activating pending virtio devices: {:?}", e
            ))
        })?;
        self.cpu_manager.lock().unwrap().pause()?;
        self.device_manager.lock().unwrap().pause()?;
        *state = new_state;
        event!("vm", "paused");
        Ok(())
    }
}
```

ARM64 不执行 x86_64 的 guest clock 保存分支。VM 逻辑状态在 CPU 和设备 pause 返回后才正式写为 `Paused`。

### 4.2 `CpuManager::pause` 等待每个 vCPU 的 immediate-exit ACK

`hypervisor/vmm/src/cpu.rs`：

```rust
impl Pausable for CpuManager {
    fn pause(&mut self) -> std::result::Result<(), MigratableError> {
        self.vcpus_pause_signalled.store(true, Ordering::SeqCst);

        for state in self.vcpu_states.iter() {
            state.signal_thread();
        }
        for vcpu in self.vcpus.iter() {
            let mut vcpu = vcpu.lock().unwrap();
            vcpu.pause()?;
            // 省略 x86_64 专有的 notify_guest_clock_paused 分支。
        }
        Ok(())
    }
}
```

ARM64 上 `Vcpu` 使用 `Pausable` 的空默认实现，因此第二个循环不是实际停机点。同步保证来自 `VcpuState::signal_thread` 和 vCPU 线程的 pause 分支。

```rust
fn signal_thread(&self) {
    if let Some(handle) = self.handle.as_ref() {
        loop {
            unsafe {
                libc::pthread_kill(handle.as_pthread_t() as _, SIGRTMIN());
            }
            if self.vcpu_run_interrupted.load(Ordering::SeqCst) {
                break;
            } else {
                thread::sleep(std::time::Duration::from_millis(1));
            }
        }
    }
}
```

### 4.3 ACK 表示 KVM 状态一致，不表示线程已经 park

vCPU 主循环顶部先检查 pause flag，再执行一次 immediate-exit `KVM_RUN`。这样可完成先前未完成的 PIO/MMIO 退出，然后才设置 ACK 并 park。

```rust
if vcpu_pause_signalled.load(Ordering::SeqCst) {
    #[cfg(feature = "kvm")]
    {
        vcpu.lock().as_ref().unwrap().vcpu.set_immediate_exit(true);
        if !matches!(vcpu.lock().unwrap().run(), Ok(VmExit::Ignore)) {
            error!("Unexpected VM exit on \"immediate_exit\" run");
            break;
        }
        vcpu.lock().as_ref().unwrap().vcpu.set_immediate_exit(false);
    }
    vcpu_run_interrupted.store(true, Ordering::SeqCst);

    while vcpu_pause_signalled.load(Ordering::SeqCst) {
        thread::park();
    }
    vcpu_run_interrupted.store(false, Ordering::SeqCst);
}
```

`signal_thread()` 等到的是 `vcpu_run_interrupted=true`。该 store 位于 `park()` 之前，因此 `VmPause` 返回时不能证明线程已执行到 park，只能证明 immediate-exit `KVM_RUN` 已完成。

| “已暂停”语义 | 判定原语 | `VmPause` 返回时是否保证 |
| --- | --- | --- |
| VM 逻辑状态为 `Paused` | `Vm.state = VmState::Paused` | 是 |
| vCPU 完成 immediate-exit `KVM_RUN` | `vcpu_run_interrupted=true` | 是 |
| vCPU 线程已经进入 `thread::park()` | 无独立 ACK | 否 |

## 5. Snapshot 保存链路

Snapshot 只有在 VM 当前状态为 `Paused` 时才允许执行。`Vm::snapshot` 的状态保存顺序固定为 CPU → memory → vGIC → devices。

```rust
impl Snapshottable for Vm {
    fn snapshot(&mut self) -> std::result::Result<Snapshot, MigratableError> {
        event!("vm", "snapshotting");
        let current_state = self.get_state().unwrap();
        if current_state != VmState::Paused {
            return Err(MigratableError::Snapshot(anyhow!(
                "Trying to snapshot while VM is running"
            )));
        }

        // 省略 x86_64 common CPUID 与 clock 字段的构造。
        let vm_snapshot_state = VmSnapshot {
            #[cfg(all(feature = "kvm", target_arch = "x86_64"))]
            clock: self.saved_clock,
            #[cfg(all(feature = "kvm", target_arch = "x86_64"))]
            common_cpuid,
        };
        let mut vm_snapshot =
            Snapshot::new_from_state(VM_SNAPSHOT_ID, &vm_snapshot_state)?;

        vm_snapshot.add_snapshot(self.cpu_manager.lock().unwrap().snapshot()?);
        vm_snapshot.add_snapshot(self.memory_manager.lock().unwrap().snapshot()?);
        #[cfg(target_arch = "aarch64")]
        self.add_vgic_snapshot_section(&mut vm_snapshot)
            .map_err(|e| MigratableError::Snapshot(e.into()))?;
        vm_snapshot.add_snapshot(self.device_manager.lock().unwrap().snapshot()?);

        event!("vm", "snapshotted");
        Ok(vm_snapshot)
    }
}
```

### 5.1 vCPU 保存进入 KVM one-reg 接口

每个 `Vcpu::snapshot` 调用 hypervisor vCPU 的 `state()`，并把返回的 `CpuState` 写入以 vCPU ID 命名的 snapshot 节点。

```rust
fn snapshot(&mut self) -> std::result::Result<Snapshot, MigratableError> {
    let saved_state = self
        .vcpu
        .state()
        .map_err(|e| MigratableError::Pause(anyhow!("Could not get vCPU state {:?}", e)))?;

    let mut vcpu_snapshot = Snapshot::new(&format!("{:03}", self.id));
    vcpu_snapshot.add_data_section(SnapshotDataSection::new_from_state(
        VCPU_SNAPSHOT_ID,
        &saved_state,
    )?);
    self.saved_state = Some(saved_state);
    Ok(vcpu_snapshot)
}
```

ARM64 KVM 实现读取 MP state、core registers 和 `KVM_GET_REG_LIST` 返回的 system registers。system register 向量保持内核返回顺序，不做 timer 感知排序。

```rust
fn state(&self) -> cpu::Result<CpuState> {
    let mut state = VcpuKvmState {
        mp_state: self.get_mp_state()?.into(),
        ..Default::default()
    };
    state.core_regs = self.get_regs()?;

    let mut sys_regs: Vec<Register> = Vec::new();
    let mut reg_list = RegList::new(500).unwrap();
    self.fd.lock().unwrap().get_reg_list(&mut reg_list)
        .map_err(|e| cpu::HypervisorCpuError::GetRegList(e.into()))?;
    reg_list.retain(|regid| is_system_register(*regid));

    for index in reg_list.as_slice().iter() {
        let mut bytes = [0_u8; 8];
        self.fd.lock().unwrap().get_one_reg(*index, &mut bytes)
            .map_err(|e| cpu::HypervisorCpuError::GetSysRegister(e.into()))?;
        sys_regs.push(kvm_bindings::kvm_one_reg {
            id: *index,
            addr: u64::from_le_bytes(bytes),
        });
    }
    state.sys_regs = sys_regs;
    Ok(state.into())
}
```

### 5.2 vGIC 保存发生在全部 vCPU 和内存状态之后

`add_vgic_snapshot_section` 先从 `CpuManager` 取得保存后的 vCPU state，用其设置 GICR typer，再调用 vGIC snapshot。

```rust
fn add_vgic_snapshot_section(
    &self,
    vm_snapshot: &mut Snapshot,
) -> std::result::Result<(), MigratableError> {
    let saved_vcpu_states = self.cpu_manager.lock().unwrap().get_saved_states();
    self.device_manager
        .lock().unwrap().get_interrupt_controller().unwrap()
        .lock().unwrap().set_gicr_typers(&saved_vcpu_states);

    vm_snapshot.add_snapshot(
        self.device_manager
            .lock().unwrap().get_interrupt_controller().unwrap()
            .lock().unwrap().snapshot()?,
    );
    Ok(())
}
```

vGIC state 包含 distributor、redistributor、ICC 和 ITS 状态。当前实现没有另存 `KVM_DEV_ARM_VGIC_GRP_LEVEL_INFO` 表示的 level-sensitive PPI line level。

## 6. Template 构建后的 Resume 链路

`Snapshot::do_app_snapshot` 发送 `/api/v1/vm.resume` 后，VMM 调用 `Vm::resume`。关键顺序是 CPU resume → ARM64 无 x86 clock 分支 → device resume → 发布 `Running`。

```rust
fn resume(&mut self) -> std::result::Result<(), MigratableError> {
    event!("vm", "resuming");
    let mut state = self
        .state
        .try_write()
        .map_err(|e| MigratableError::Resume(anyhow!("Could not get VM state: {}", e)))?;
    let new_state = VmState::Running;
    state
        .valid_transition(new_state)
        .map_err(|e| MigratableError::Resume(anyhow!("Invalid transition: {:?}", e)))?;

    self.cpu_manager.lock().unwrap().resume()?;
    // 省略 x86_64 专有的 VM clock 恢复分支。
    self.device_manager.lock().unwrap().resume()?;
    *state = new_state;
    info!("vm has been resumed");
    event!("vm", "resumed");
    Ok(())
}
```

`CpuManager::resume` 先清全局 pause flag，再 unpark 所有 vCPU 线程：

```rust
fn resume(&mut self) -> std::result::Result<(), MigratableError> {
    for vcpu in self.vcpus.iter() {
        vcpu.lock().unwrap().resume()?;
    }
    self.vcpus_pause_signalled.store(false, Ordering::SeqCst);
    for state in self.vcpu_states.iter() {
        state.unpark_thread();
    }
    Ok(())
}
```

线程离开 park 循环后清 `vcpu_run_interrupted`，回到主循环并执行正常 `KVM_RUN`。Resume API 返回不等待 guest 内部业务恢复，也不等待某个 guest RPC ready 条件。

## 7. 运行时 Sandbox Pause / Resume 链路

![运行时 Sandbox Pause 与 Resume 时序](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ASSETS_20260721/05-runtime-pause-resume-sequence.svg)

运行时 Pause/Resume 与 Template 构建的三个独立 API 不同。它们使用 fork 新增的合并请求：

```rust
pub async fn pause_vm_cube(&self, path: &str) -> CResult<()> {
    let snap_config = Arc::new(SnapshotConfig {
        destination_url: path.to_string(),
        ..Default::default()
    });
    let ch = self.ch.as_ref().unwrap().lock().await;
    let _ = ch
        .send_request(ApiRequest::VmPauseToSnapshot(snap_config))
        .map_err(|e| self.status_err(format!("pause vm to snapshot failed:{}", e)))?
        .map_err(|e| self.status_err(format!("pause vm to snapshot failed:{}", e)))?;
    Ok(())
}

pub async fn resume_vm_cube(&self, path: &str) -> CResult<()> {
    let restore_config = Arc::new(RestoreConfig {
        source_url: path.into(),
        ..Default::default()
    });
    let ch = self.ch.as_ref().unwrap().lock().await;
    let _ = ch
        .send_request(ApiRequest::VmResumeFromSnapshot(restore_config))
        .map_err(|e| self.status_err(format!("resume vm from snapshot failed:{}", e)))?
        .map_err(|e| self.status_err(format!("resume vm from snapshot failed:{}", e)))?;
    Ok(())
}
```

### 7.1 Pause 是 pause + snapshot + delete

`TaskService::pause` 校验 pod scope 后调用 `SandBox::pause_vm`。Sandbox 先断开 agent，再要求 VMM 把快照写到 pause 目录。

```rust
pub async fn pause_vm(&mut self) -> CResult<()> {
    {
        let mut state = self.state.lock().await;
        if *state != SandBoxState::Normal {
            return Err(format!("sandbox not running").into());
        }
        if self.pause_vm_forbidding().await {
            return Err(format!("sandbox pause forbidding, terminate exec tasks first").into());
        }
        *state = SandBoxState::Paused;
    }
    self.disconnect_agent(false).await?;

    let ch = self.ch.as_mut().unwrap().lock().await;
    let snapshot_path = format!("{}/{}", PAUSE_VM_SNAPSHOT_BASE, self.id);
    recreate_dir(&snapshot_path, "mkdir snapshot dir failed")?;
    ch.pause_vm_cube(format!("file://{}", snapshot_path).as_str()).await?;
    let _ = ch
        .wait_notify(Duration::from_nanos(self.ctx.timeout_nano as u64))
        .await?;
    Ok(())
}
```

VMM 的合并操作不会保留内存中的 `Vm` 对象：

```rust
fn vm_pause_to_snapshot(
    &mut self,
    snapshot_config: &SnapshotConfig,
) -> result::Result<(), VmError> {
    self.vm_pause()?;
    self.vm_snapshot(snapshot_config)?;
    self.vm_delete()
}
```

因此，运行时 Pause 的语义不是“线程停在内存中等待 resume”，而是“暂停并落盘，然后删除当前 VM”。

### 7.2 Resume 实际执行 restore

`TaskService::resume` 进入 `SandBox::resume_vm_with_config`。该函数恢复 VM 后重连 agent、重置 guest 时间与随机源，并重新绑定 container client 和监控任务。

```rust
pub async fn resume_vm(&mut self) -> CResult<()> {
    self.resume_vm_with_config(None).await
}

async fn resume_vm_with_config(&mut self, config: Option<RestoreConfig>) -> CResult<()> {
    {
        let state = self.state.lock().await;
        if *state != SandBoxState::Paused {
            return Err(format!("sandbox not paused").into());
        }
    }
    {
        let ch = self.ch.as_mut().unwrap().lock().await;
        match config {
            Some(restore_config) => {
                ch.resume_vm_cube_with_config(restore_config).await?;
            }
            None => {
                let resume_path = format!("{}/{}", PAUSE_VM_SNAPSHOT_BASE, self.id);
                ch.resume_vm_cube(format!("file://{}", resume_path).as_str()).await?;
            }
        }
    }

    self.connect_agent().await?;
    self.reset_guest().await?;

    let client = self.client.as_ref().unwrap();
    let mut containers = self.containers.lock().await;
    for (_, c) in containers.iter_mut() {
        c.set_client(client.clone()).await;
    }
    // 源码随后重建 OOM 与 VM monitor 任务。
    let mut state = self.state.lock().await;
    *state = SandBoxState::Normal;
    Ok(())
}
```

VMM 侧 `VmResumeFromSnapshot` 只调用 restore 入口；restore 内部会自动 resume：

```rust
fn vm_resume_from_snapshot(
    &mut self,
    restore_cfg: RestoreConfig,
) -> result::Result<(), VmError> {
    self.vm_restore(restore_cfg)
}
```

## 8. 从 Template 创建 Sandbox：Restore 链路

![ARM64 Restore 顺序与三个关键窗口](CUBESANDBOX_ARM64_PAUSE_RESUME_RESTORE_CALL_CHAIN_ASSETS_20260721/04-restore-order-windows.svg)

### 8.1 Shim 创建流程

`SandBox::create_sandbox` 先通过 `start_vm` 启动或恢复 VM，然后立即连接 agent。若 VM 来自 app snapshot，`start_vm` 在 restore 成功后直接返回，不等待冷启动路径使用的 `VsockServerReady`。

```rust
pub async fn create_sandbox(&mut self) -> CResult<()> {
    let snapshot = self.start_vm().await?;
    // 省略 notify_snapshot_ret 分支。
    self.connect_agent().await?;
    if snapshot {
        self.reset_guest().await?;
    }
    // 源码随后构造 agent::CreateSandboxRequest 并调用 client.create_sandbox。
    Ok(())
}

async fn start_vm(&mut self) -> CResult<bool> {
    {
        let mut ch = self.ch.as_mut().unwrap().lock().await;
        ch.launch_vmm().await?;
    }
    let mut snapshot = false;
    if self.by_snapshot() {
        match self.restore_vm().await {
            Ok(_) => {
                snapshot = true;
                if self.conf.app_snapshot_restore {
                    return Ok(snapshot);
                }
            }
            Err(e) => {
                if self.conf.app_snapshot_restore {
                    return Err(format!("app snapshot restore vm failed:{}", e));
                }
            }
        }
    }
    // 源码随后在非 app-snapshot 快返路径等待 VsockServerReady。
    Ok(snapshot)
}
```

`reset_guest` 是 restore 后第一个关键 guest RPC 组合：

```rust
async fn reset_guest(&mut self) -> CResult<()> {
    let client = self.client.as_ref().unwrap().lock().await;
    let tm = Utc::now();
    let req = agent::SetGuestDateTimeRequest {
        Sec: tm.timestamp(),
        Usec: tm.timestamp_subsec_micros() as i64,
        ..Default::default()
    };
    client.set_guest_date_time(self.ctx.clone(), &req).await
        .map_err(|e| format!("reset guest time failed:{}", e))?;

    let req = agent::ReseedRandomDevRequest {
        data: Utils::get_rng()?,
        ..Default::default()
    };
    client.reseed_random_dev(self.ctx.clone(), &req).await
        .map_err(|e| format!("reset reseed random dev failed:{}", e))?;
    Ok(())
}
```

### 8.2 `restore_vm` 同步等待 VMM API 返回，但不等待额外 ready 事件

`restore_vm` 校验 metadata，构造 `RestoreConfig` 并调用 `CubeHypervisor::restore_vm`。原本等待 `NotifyEvent::RestoreReady` 的代码被整段注释，因此 API 成功即视为恢复成功。

```rust
async fn restore_vm(&mut self) -> CResult<()> {
    let ss_file = SnapshotInfo::load(
        self.conf.snapshot_base.as_str(),
        self.conf.vm_res.cpu,
        self.conf.vm_res.snap_memory,
    )?;
    let mut ss_req = SnapshotInfo::new(self.conf.vm_res.cpu, self.conf.vm_res.snap_memory);
    ss_req.set_image_version()?;
    ss_req.set_kernel_version(self.conf.kernel.as_str())?;
    ss_req.set_disks(&self.conf.disk);
    let align_pmem = ss_file.align_pmems(&self.conf.pmem);
    ss_req.set_pmems(&align_pmem);
    ss_file.eq(&ss_req).map_err(|e| format!("snapshot metadata not match:{}", e))?;

    // 省略 snapshot 路径以及 fs/net/disk/pmem/vsock 配置的转换代码。
    let config = RestoreConfig {
        source_url: PathBuf::from(snapshot),
        fs: Some(fss),
        net: Some(nets),
        disks: Some(disks),
        pmem: Some(pmems),
        vsock: Some(vsock),
        memory_vol_url: restore_memory_vol_url,
        ..Default::default()
    };
    let ch = self.ch.as_mut().unwrap().lock().await;
    ch.restore_vm(config).await?;

    // RestoreReady 的等待逻辑在基线代码中被注释。
    self.conf.pmem = align_pmem;
    // 省略 pmem_path_map 重建代码。
    Ok(())
}
```

### 8.3 VMM 在同一个 `VmRestore` 请求中紧接着 resume

`hypervisor/vmm/src/lib.rs` 的恢复入口完成配置和 snapshot 读取，创建 `Vm` 后连续调用 `restore` 与 `resume`。

```rust
fn vm_restore(&mut self, restore_cfg: RestoreConfig) -> result::Result<(), VmError> {
    if self.vm.is_some() || self.vm_config.is_some() {
        return Err(VmError::VmAlreadyCreated);
    }
    let source_url = restore_cfg.source_url.as_path().to_str();
    if source_url.is_none() {
        return Err(VmError::InvalidRestoreSourceUrl);
    }
    let source_url = source_url.unwrap();
    let vm_config = Arc::new(Mutex::new({
        let mut vm_config = recv_vm_config(source_url).map_err(VmError::Restore)?;
        // 省略 disks/net/vsock/fs/pmem 等后端配置覆盖。
        vm_config.memory.dirty_log = restore_cfg.dirty_log;
        vm_config
    }));
    let snapshot = recv_vm_state(source_url).map_err(VmError::Restore)?;

    // 省略 eventfd clone 以及 x86_64 CPUID 兼容性检查。
    let mut vm = Vm::new_from_snapshot(
        &snapshot,
        vm_config.clone(),
        exit_evt,
        reset_evt,
        #[cfg(feature = "guest_debug")]
        debug_evt,
        Some(source_url),
        restore_cfg.prefault,
        &self.seccomp_action,
        self.hypervisor.clone(),
        activate_evt,
        self.sandbox_id.clone(),
        self.vcpu_started.clone(),
        restore_cfg.memory_vol_url.as_deref(),
    )?;

    vm.restore(snapshot).map_err(VmError::Restore)?;
    vm.resume().map_err(VmError::Resume)?;
    self.vm_config = Some(vm_config.clone());
    self.vm = Some(vm);
    Ok(())
}
```

这意味着 shim 收到 `VmRestore` 成功时，VMM 不只是恢复出 Paused VM，而是已经清 pause flag 并 unpark vCPU。

### 8.4 `Vm::restore` 的真实顺序

核心函数依次恢复设备骨架、vCPU、vGIC、设备状态，再以 paused 模式启动 vCPU 线程，最后发布 `Paused`。

```rust
fn restore(&mut self, snapshot: Snapshot) -> std::result::Result<(), MigratableError> {
    event!("vm", "restoring");
    let current_state = self.get_state().map_err(|e| {
        MigratableError::Restore(anyhow!("Could not get VM state: {:#?}", e))
    })?;
    let new_state = VmState::Paused;
    current_state.valid_transition(new_state).map_err(|e| {
        MigratableError::Restore(anyhow!("Could not restore VM state: {:#?}", e))
    })?;

    if let Some(device_manager_snapshot) = snapshot.snapshots.get(DEVICE_MANAGER_SNAPSHOT_ID) {
        self.device_manager
            .lock().unwrap().restore(*device_manager_snapshot.clone())?;
    } else {
        return Err(MigratableError::Restore(anyhow!(
            "Missing device manager snapshot"
        )));
    }
    if let Some(cpu_manager_snapshot) = snapshot.snapshots.get(CPU_MANAGER_SNAPSHOT_ID) {
        self.cpu_manager
            .lock().unwrap().restore(*cpu_manager_snapshot.clone())?;
    } else {
        return Err(MigratableError::Restore(anyhow!(
            "Missing CPU manager snapshot"
        )));
    }
    #[cfg(target_arch = "aarch64")]
    self.restore_vgic_and_enable_interrupt(&snapshot)?;
    if let Some(device_manager_snapshot) = snapshot.snapshots.get(DEVICE_MANAGER_SNAPSHOT_ID) {
        self.device_manager
            .lock().unwrap().restore_devices(*device_manager_snapshot.clone())?;
    } else {
        return Err(MigratableError::Restore(anyhow!(
            "Missing device manager snapshot"
        )));
    }
    self.cpu_manager.lock().unwrap().start_restored_vcpus()
        .map_err(|e| MigratableError::Restore(anyhow!(
            "Cannot start restored vCPUs: {:#?}", e
        )))?;

    // 省略 signal handler 与 TTY 初始化。
    let mut state = self.state.try_write().map_err(|e| {
        MigratableError::Restore(anyhow!("Could not set VM state: {:#?}", e))
    })?;
    *state = new_state;
    info!("vm has been restored");
    event!("vm", "restored");
    Ok(())
}
```

`CpuManager::restore` 为每个 snapshot vCPU 创建新对象，并立即将保存状态写回 KVM：

```rust
fn restore(&mut self, snapshot: Snapshot) -> std::result::Result<(), MigratableError> {
    for (cpu_id, snapshot) in snapshot.snapshots.iter() {
        info!("Restoring VCPU {}", cpu_id);
        self.create_vcpu(cpu_id.parse::<u8>().unwrap(), None, Some(*snapshot.clone()))
            .map_err(|e| MigratableError::Restore(anyhow!(
                "Could not create vCPU {:?}", e
            )))?;
    }
    // 省略 x86_64 专有的 TSC MSR 同步分支。
    Ok(())
}
```

### 8.5 ARM64 `set_state` 保持 snapshot 中的 system register 顺序

KVM ARM64 实现先写 core registers，然后按 `sys_regs` 向量原顺序执行 `KVM_SET_ONE_REG`，最后设置 MP state。

```rust
fn set_state(&self, state: &CpuState) -> cpu::Result<()> {
    let state: VcpuKvmState = state.clone().into();
    self.set_regs(&state.core_regs)?;

    for reg in &state.sys_regs {
        self.fd
            .lock()
            .unwrap()
            .set_one_reg(reg.id, &reg.addr.to_le_bytes())
            .map_err(|e| cpu::HypervisorCpuError::SetSysRegister(e.into()))?;
    }
    self.set_mp_state(state.mp_state.into())?;
    Ok(())
}
```

代码不识别 timer 寄存器的依赖关系。若 snapshot 中顺序为 `TIMER_CTL`、`TIMER_CNT`、`TIMER_CVAL`，恢复就会先写使能位，再写 counter/deadline。

### 8.6 vGIC 恢复与 vCPU 启动

`restore_vgic_and_enable_interrupt` 在所有 vCPU `set_state` 之后创建 vGIC、初始化 PMU、设置 GICR typer、恢复 vGIC snapshot，并启用中断路由。

```rust
fn restore_vgic_and_enable_interrupt(
    &self,
    vm_snapshot: &Snapshot,
) -> std::result::Result<(), MigratableError> {
    let saved_vcpu_states = self.cpu_manager.lock().unwrap().get_saved_states();
    let vcpu_count = saved_vcpu_states.len().try_into().unwrap();

    self.device_manager
        .lock().unwrap().get_interrupt_controller().unwrap()
        .lock().unwrap().create_vgic(&self.vm, Gic::create_default_config(vcpu_count))
        .map_err(|e| MigratableError::Restore(anyhow!("Could not create GIC: {:#?}", e)))?;
    self.cpu_manager
        .lock().unwrap().init_pmu(arch::aarch64::fdt::AARCH64_PMU_IRQ + 16)
        .map_err(|e| MigratableError::Restore(anyhow!("Error init PMU: {:?}", e)))?;
    self.device_manager
        .lock().unwrap().get_interrupt_controller().unwrap()
        .lock().unwrap().set_gicr_typers(&saved_vcpu_states);

    if let Some(gicv3_its_snapshot) = vm_snapshot.snapshots.get(GIC_V3_ITS_SNAPSHOT_ID) {
        self.device_manager
            .lock().unwrap().get_interrupt_controller().unwrap()
            .lock().unwrap().restore(*gicv3_its_snapshot.clone())?;
    } else {
        return Err(MigratableError::Restore(anyhow!("Missing GicV3Its snapshot")));
    }
    self.device_manager
        .lock().unwrap().get_interrupt_controller().unwrap()
        .lock().unwrap().enable()
        .map_err(|e| MigratableError::Restore(anyhow!(
            "Could not enable interrupt controller routing: {:#?}", e
        )))?;
    Ok(())
}
```

随后 `start_restored_vcpus` 以 `paused=true` 启动线程：

```rust
pub fn start_restored_vcpus(&mut self) -> Result<()> {
    self.activate_vcpus(self.vcpus.len() as u8, false, Some(true))
        .map_err(|e| {
            Error::StartRestoreVcpu(anyhow!(
                "Failed to start restored vCPUs: {:#?}", e
            ))
        })?;
    Ok(())
}
```

新线程第一轮进入 Pause 分支，执行 immediate-exit `KVM_RUN` 并 park。紧接着外层 `vm_restore` 调用 `Vm::resume`，清 flag、unpark，然后进入第一个正常 `KVM_RUN`。

## 9. 三个关键时序窗口

| 窗口 | 起点 | 终点 | 机制风险 |
| --- | --- | --- | --- |
| W1：timer 寄存器写入窗口 | 写 `TIMER_CTL` | `TIMER_CNT/CVAL` 写完 | timer 可能在 counter/deadline 完整恢复前被启用 |
| W2：timer 与 vGIC 窗口 | 全部 vCPU `set_state` 完成 | vGIC state 与路由恢复完成 | timer line 与新建/恢复中的 redistributor 状态相遇 |
| W3：首次运行窗口 | `CpuManager::resume` unpark | 首个正常 `KVM_RUN` | timer line、PPI pending、PSTATE.I 和 MP state 的组合决定首个 tick |

### 9.1 必须保持区分的状态不变量

1. `VmPause` 的 CPU ACK 证明 immediate-exit `KVM_RUN` 完成，不证明 vCPU 已 park。
2. `Vm::snapshot` 要求 VM 逻辑状态为 `Paused`，保存顺序为 CPU → memory → vGIC → devices。
3. `Vm::restore` 返回时内部状态为 `Paused`，但 VMM `vm_restore` 会立即调用 `Vm::resume`。
4. app snapshot restore 分支不等待 `VsockServerReady`，shim 紧接着执行 `connect_agent` 和 `reset_guest`。
5. 运行时 `Pause` 会删除 VM；运行时 `Resume` 是完整 restore，不是原线程的简单 unpark。

## 10. 关键函数索引

本索引使用“源码文件 + 函数/方法”定位，不依赖易漂移的行号。

| 模块 | 源码文件 | 关键函数或方法 |
| --- | --- | --- |
| Cubelet app snapshot | `Cubelet/services/cubebox/appsnapshot.go` | `AppSnapshot`、`executeCubeRuntimeSnapshot`、`buildCubeRuntimeSnapshotArgs` |
| cube-runtime CLI | `CubeShim/cube-runtime/src/main.rs` | `execute` 中的 `SubCommands::Snapshot` 分支 |
| snapshot 命令 | `CubeShim/shim/src/snapshot/cmd.rs` | `execute`、`TryFrom<SnapshotArgs> for Snapshot` |
| app snapshot 流程 | `CubeShim/shim/src/snapshot/mod.rs` | `Snapshot::handle`、`do_app_snapshot`、`request_ch` |
| Sandbox 生命周期 | `CubeShim/shim/src/sandbox/sb.rs` | `create_sandbox`、`start_vm`、`restore_vm`、`pause_vm`、`resume_vm_with_config`、`reset_guest` |
| Shim 到 VMM | `CubeShim/shim/src/hypervisor/cube_hypervisor.rs` | `pause_vm`、`snapshot_vm`、`resume_vm`、`restore_vm`、`pause_vm_cube`、`resume_vm_cube` |
| VMM API | `hypervisor/vmm/src/lib.rs` | `control_loop`、`vm_pause`、`vm_snapshot`、`vm_resume`、`vm_pause_to_snapshot`、`vm_resume_from_snapshot`、`vm_restore` |
| VM 状态机 | `hypervisor/vmm/src/vm.rs` | `Vm::pause`、`Vm::resume`、`Vm::snapshot`、`Vm::restore`、`add_vgic_snapshot_section`、`restore_vgic_and_enable_interrupt` |
| vCPU 生命周期 | `hypervisor/vmm/src/cpu.rs` | `VcpuState::signal_thread`、vCPU 线程 pause 分支、`CpuManager::pause`、`resume`、`snapshot`、`restore`、`start_restored_vcpus` |
| KVM ARM64 vCPU | `hypervisor/hypervisor/src/kvm/mod.rs` | ARM64 `Vcpu::state`、`Vcpu::set_state` |
| KVM ARM64 vGIC | `hypervisor/hypervisor/src/kvm/aarch64/gic/mod.rs` | `GicV3Its::state`、`GicV3Its::set_state` |

## 11. 结论

1. Template 构建的真实入口是 Cubelet 启动 `cube-runtime`，再通过 Unix HTTP 驱动目标 shim 内的 VMM；`SandBox::create_snapshot` 不在这条链上。
2. Pause 的可依赖完成条件是每个 vCPU 完成 immediate-exit `KVM_RUN` 并置 ACK，而不是线程已经进入 park。
3. Snapshot 保存顺序与 Restore 恢复顺序不对称。ARM64 timer state 早于 vGIC state 恢复，形成 W1/W2；resume unpark 到首次正常 `KVM_RUN` 形成 W3。
4. Template restore 与 resume 位于同一个 VMM API 内。shim 的 app snapshot 分支不额外等待 vsock ready，因此恢复后的首个 agent/reset RPC 紧邻 W3。
5. 运行时 Pause/Resume 是“pause + snapshot + delete”与“restore + resume”，不能套用常驻 VM 的原地暂停模型。
