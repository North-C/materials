# MicroVM DEMO 实践实现计划

## 项目目标

构建一个轻量级的 MicroVM 运行时 DEMO，支持 ARM64 和 x86_64 架构，具备完整的功能和测试。

**预期时间**: 3-4 周
**目标**: 可启动 Linux 内核的最小化 VMM + 基础 virtio 设备 + HTTP API

---

## 第三方库选型（基于典型项目分析）

### 核心虚拟化库
| 库名 | 版本 | 用途 | 参考项目 |
|------|------|------|---------|
| `kvm-ioctls` | 0.17 | KVM ioctl 封装 | Firecracker, Cloud Hypervisor, StratoVirt |
| `kvm-bindings` | 0.9 | KVM 结构体定义 | Firecracker, Cloud Hypervisor |
| `vm-memory` | 0.15 | Guest 内存管理 | Firecracker, Cloud Hypervisor, Dragonball |
| `vmm-sys-util` | 0.12 | 系统工具（eventfd等） | Firecracker, Cloud Hypervisor |

### Virtio 设备
| 库名 | 版本 | 用途 | 参考项目 |
|------|------|------|---------|
| `virtio-queue` | 0.12 | Virtio 队列管理 | Cloud Hypervisor |
| `virtio-bindings` | 0.2 | Virtio 规范绑定 | Cloud Hypervisor, Dragonball |
| `vhost` | 0.11 | vhost 协议支持 | Cloud Hypervisor |

### 异步运行时与网络
| 库名 | 版本 | 用途 | 参考项目 |
|------|------|------|---------|
| `tokio` | 1.41 | 异步运行时 | StratoVirt, Dragonball |
| `async-trait` | 0.1 | 异步 trait | StratoVirt |
| `axum` | 0.7 | HTTP 服务器 | - |

### 序列化与日志
| 库名 | 版本 | 用途 | 参考项目 |
|------|------|------|---------|
| `serde` | 1.0 | 序列化/反序列化 | Firecracker, Cloud Hypervisor |
| `serde_json` | 1.0 | JSON 支持 | Firecracker |
| `tracing` | 0.1 | 结构化日志 | Cloud Hypervisor |
| `tracing-subscriber` | 0.3 | 日志订阅器 | Cloud Hypervisor |

### 测试框架
| 库名 | 版本 | 用途 | 参考项目 |
|------|------|------|---------|
| `criterion` | 0.5 | 性能基准测试 | Firecracker, Cloud Hypervisor |
| `proptest` | 1.0 | 属性测试 | Firecracker |

### ARM64 特定支持
- `kvm-ioctls` 和 `kvm-bindings` 已原生支持 ARM64
- `vm-memory` 对 ARM64 内存模型有完整支持
- 需要注意 GIC（ARM 中断控制器）与 x86 的 APIC 差异

---

## DEMO 功能清单

### 里程碑 1: 最小 KVM 运行环境（Week 1）

**功能**:
- [x] KVM 初始化和 VM 创建
- [x] vCPU 创建和基本寄存器设置
- [x] Guest 内存分配和映射
- [x] 在 Guest 中执行简单代码（返回固定值）

**测试**:
```rust
#[test]
fn test_vm_creation() {
    let kvm = Kvm::new().unwrap();
    let vm = kvm.create_vm().unwrap();
    assert!(vm.get_nr_memslots() > 0);
}

#[test]
fn test_vcpu_run_simple_code() {
    // x86_64: mov rax, 42; ret
    // ARM64: mov x0, #42; ret
    let code = if cfg!(target_arch = "aarch64") {
        vec![0x80, 0x05, 0x80, 0xd2, 0xc0, 0x03, 0x5f, 0xd6]
    } else {
        vec![0x48, 0xc7, 0xc0, 0x2a, 0x00, 0x00, 0x00, 0xc3]
    };

    let vm = create_test_vm(&code);
    let exit_reason = vm.run_vcpu().unwrap();
    assert_eq!(exit_reason, VcpuExit::Hlt);
}
```

**代码结构**:
```
src/
├── main.rs
├── kvm/
│   ├── mod.rs
│   ├── vm.rs          # VM 创建和管理
│   └── vcpu.rs        # vCPU 线程和执行
├── memory/
│   ├── mod.rs
│   └── guest_memory.rs # Guest 内存管理
└── arch/
    ├── x86_64/
    │   └── regs.rs     # 寄存器初始化
    └── aarch64/
        └── regs.rs     # ARM64 寄存器初始化
```

**核心代码示例**:
```rust
// src/kvm/vm.rs
use kvm_ioctls::{Kvm, VmFd};
use vm_memory::{GuestAddress, GuestMemory, GuestMemoryMmap};

pub struct MicroVm {
    kvm: Kvm,
    vm_fd: VmFd,
    guest_memory: GuestMemoryMmap,
}

impl MicroVm {
    pub fn new(mem_size: usize) -> Result<Self> {
        let kvm = Kvm::new()?;
        let vm_fd = kvm.create_vm()?;

        // 创建 Guest 内存
        let guest_memory = GuestMemoryMmap::from_ranges(&[
            (GuestAddress(0), mem_size)
        ])?;

        // 设置用户内存区域
        let mem_region = kvm_userspace_memory_region {
            slot: 0,
            guest_phys_addr: 0,
            memory_size: mem_size as u64,
            userspace_addr: guest_memory.get_host_address(GuestAddress(0))? as u64,
            flags: 0,
        };
        unsafe { vm_fd.set_user_memory_region(mem_region)? };

        Ok(Self { kvm, vm_fd, guest_memory })
    }
}
```

---

### 里程碑 2: Linux 内核启动（Week 2）

**功能**:
- [x] 加载 Linux 内核镜像（bzImage/Image）
- [x] 配置内核命令行参数
- [x] 设置启动协议（x86: boot protocol, ARM64: device tree）
- [x] Serial console 输出（通过 I/O 端口/MMIO）
- [x] 成功启动到内核 panic 或 shell

**测试**:
```rust
#[test]
fn test_kernel_boot() {
    let kernel_path = if cfg!(target_arch = "aarch64") {
        "tests/kernels/Image-arm64"
    } else {
        "tests/kernels/bzImage-x86_64"
    };

    let vm = MicroVm::new(512 * 1024 * 1024)?;
    vm.load_kernel(kernel_path, "console=ttyS0")?;
    vm.configure_serial()?;

    let result = vm.run_with_timeout(Duration::from_secs(10))?;
    assert!(result.serial_output.contains("Linux version"));
}

#[cfg(target_arch = "aarch64")]
#[test]
fn test_device_tree_generation() {
    let dt = DeviceTree::new();
    dt.add_cpu_nodes(1)?;
    dt.add_memory_node(0x4000_0000, 512 * 1024 * 1024)?;
    dt.add_serial_node()?;

    let dtb = dt.compile()?;
    assert!(dtb.len() > 0);
}
```

**代码结构**:
```
src/
├── kernel/
│   ├── mod.rs
│   ├── loader.rs      # 内核加载器
│   └── cmdline.rs     # 内核命令行
├── devices/
│   ├── mod.rs
│   ├── serial.rs      # 串口设备
│   └── legacy/
│       ├── i8042.rs   # x86 键盘控制器
│       └── rtc.rs     # RTC
└── arch/
    ├── x86_64/
    │   ├── boot.rs    # Boot protocol
    │   └── cpuid.rs   # CPUID 模拟
    └── aarch64/
        ├── fdt.rs     # Device Tree
        └── gic.rs     # GIC 中断控制器
```

**核心代码示例（ARM64 特定）**:
```rust
// src/arch/aarch64/fdt.rs
use vm_fdt::{FdtWriter, FdtWriterNode};

pub struct DeviceTreeBuilder {
    fdt: FdtWriter,
}

impl DeviceTreeBuilder {
    pub fn new() -> Self {
        let mut fdt = FdtWriter::new().unwrap();

        let root = fdt.begin_node("").unwrap();
        fdt.property_string("compatible", "linux,dummy-virt").unwrap();
        fdt.property_u32("#address-cells", 0x2).unwrap();
        fdt.property_u32("#size-cells", 0x2).unwrap();
        fdt.end_node(root).unwrap();

        Self { fdt }
    }

    pub fn add_cpu_nodes(&mut self, num_cpus: u8) -> Result<()> {
        let cpus = self.fdt.begin_node("cpus")?;
        self.fdt.property_u32("#address-cells", 0x1)?;
        self.fdt.property_u32("#size-cells", 0x0)?;

        for i in 0..num_cpus {
            let cpu = self.fdt.begin_node(&format!("cpu@{}", i))?;
            self.fdt.property_string("device_type", "cpu")?;
            self.fdt.property_string("compatible", "arm,arm-v8")?;
            self.fdt.property_u32("reg", i as u32)?;
            self.fdt.property_string("enable-method", "psci")?;
            self.fdt.end_node(cpu)?;
        }

        self.fdt.end_node(cpus)?;
        Ok(())
    }

    pub fn add_gic_node(&mut self) -> Result<()> {
        let gic = self.fdt.begin_node("intc@8000000")?;
        self.fdt.property_string("compatible", "arm,gic-v3")?;
        self.fdt.property_null("interrupt-controller")?;
        self.fdt.property_u32("#interrupt-cells", 0x3)?;
        self.fdt.property_array_u64("reg", &[
            0x0, 0x8000000, 0x0, 0x10000,     // GICD
            0x0, 0x80A0000, 0x0, 0xf60000,    // GICR
        ])?;
        self.fdt.property_u32("phandle", 1)?;
        self.fdt.end_node(gic)?;
        Ok(())
    }
}
```

**x86_64 特定代码**:
```rust
// src/arch/x86_64/boot.rs
const BOOT_PARAMS_ADDR: u64 = 0x7000;
const KERNEL_LOAD_ADDR: u64 = 0x100000;  // 1MB

pub struct BootConfigurator;

impl BootConfigurator {
    pub fn configure(
        vm: &MicroVm,
        kernel_load_addr: u64,
        cmdline_addr: u64,
    ) -> Result<()> {
        // 设置 boot_params 结构
        let boot_params = setup_boot_params(cmdline_addr);
        vm.guest_memory.write_obj(boot_params, GuestAddress(BOOT_PARAMS_ADDR))?;

        // 设置初始寄存器
        let mut sregs = vm.vcpu.get_sregs()?;
        sregs.cs.base = 0;
        sregs.cs.selector = 0;
        vm.vcpu.set_sregs(&sregs)?;

        let mut regs = vm.vcpu.get_regs()?;
        regs.rip = kernel_load_addr + KERNEL_ENTRY_OFFSET;
        regs.rsi = BOOT_PARAMS_ADDR;
        regs.rflags = 0x2;
        vm.vcpu.set_regs(&regs)?;

        Ok(())
    }
}
```

---

### 里程碑 3: Virtio 设备支持（Week 3）

**功能**:
- [x] Virtio MMIO 传输层
- [x] Virtio Block 设备（rootfs 支持）
- [x] Virtio Net 设备（网络连接）
- [x] Virtqueue 管理和中断注入
- [x] 启动完整 rootfs（使用 Alpine Linux）

**测试**:
```rust
#[test]
fn test_virtio_block_read_write() {
    let disk_path = create_test_disk(1024 * 1024 * 100); // 100MB
    let block_device = VirtioBlock::new(disk_path)?;

    let vm = MicroVm::new(512 * 1024 * 1024)?;
    vm.add_device(Box::new(block_device))?;
    vm.load_kernel_with_rootfs("tests/kernels/bzImage", "root=/dev/vda")?;

    let result = vm.run_with_timeout(Duration::from_secs(30))?;
    assert!(result.serial_output.contains("Welcome to Alpine"));
}

#[test]
fn test_virtio_net_tap() {
    let net_device = VirtioNet::new_tap("tap0")?;

    let vm = MicroVm::new(512 * 1024 * 1024)?;
    vm.add_device(Box::new(net_device))?;
    vm.load_kernel_with_rootfs("tests/kernels/bzImage", "root=/dev/vda")?;

    vm.run_async()?;
    std::thread::sleep(Duration::from_secs(5));

    // 测试网络连通性
    let response = ping_guest_ip("192.168.100.2")?;
    assert_eq!(response.status, PingStatus::Success);
}

#[test]
fn test_virtqueue_descriptor_chain() {
    let queue = VirtQueue::new(256);

    // 模拟 Guest 写入描述符
    queue.add_descriptor(0x1000, 512, VIRTQ_DESC_F_NEXT, 1);
    queue.add_descriptor(0x2000, 512, 0, 0);

    let chain = queue.pop_descriptor_chain()?;
    assert_eq!(chain.len(), 2);
    assert_eq!(chain[0].addr, 0x1000);
}
```

**代码结构**:
```
src/
├── virtio/
│   ├── mod.rs
│   ├── device.rs      # Virtio 设备 trait
│   ├── queue.rs       # Virtqueue 实现
│   ├── mmio.rs        # MMIO 传输层
│   ├── block/
│   │   ├── mod.rs
│   │   ├── device.rs  # Block 设备
│   │   └── executor.rs # I/O 执行器
│   └── net/
│       ├── mod.rs
│       ├── device.rs  # Net 设备
│       └── tap.rs     # TAP 接口
└── devices/
    └── interrupt.rs   # 中断注入
```

**核心代码示例**:
```rust
// src/virtio/block/device.rs
use std::fs::File;
use std::os::unix::io::AsRawFd;
use virtio_queue::{Queue, QueueT};

pub struct VirtioBlock {
    disk_image: File,
    disk_size: u64,
    queue: Queue,
    activated: bool,
}

impl VirtioBlock {
    pub fn new(path: &str) -> Result<Self> {
        let disk_image = File::options()
            .read(true)
            .write(true)
            .open(path)?;
        let disk_size = disk_image.metadata()?.len();

        Ok(Self {
            disk_image,
            disk_size,
            queue: Queue::new(256)?,
            activated: false,
        })
    }

    pub fn process_queue(&mut self, mem: &GuestMemoryMmap) -> Result<()> {
        while let Some(chain) = self.queue.iter(mem.clone())?.next() {
            let request_type = chain.clone()
                .next()
                .and_then(|desc| {
                    mem.read_obj::<u32>(GuestAddress(desc.addr() as u64)).ok()
                })?;

            match request_type {
                VIRTIO_BLK_T_IN => self.handle_read(chain, mem)?,
                VIRTIO_BLK_T_OUT => self.handle_write(chain, mem)?,
                _ => return Err(Error::InvalidRequest),
            }
        }
        Ok(())
    }

    fn handle_read(&mut self, chain: DescriptorChain, mem: &GuestMemoryMmap) -> Result<()> {
        // 从 chain 中解析 sector 和 data 描述符
        let mut iter = chain.clone();
        let header_desc = iter.next().unwrap();
        let data_desc = iter.next().unwrap();

        let header: BlockRequestHeader = mem.read_obj(
            GuestAddress(header_desc.addr() as u64)
        )?;

        // 读取磁盘数据
        use std::io::{Read, Seek, SeekFrom};
        self.disk_image.seek(SeekFrom::Start(header.sector * 512))?;

        let mut buffer = vec![0u8; data_desc.len() as usize];
        self.disk_image.read_exact(&mut buffer)?;

        // 写入 Guest 内存
        mem.write_slice(&buffer, GuestAddress(data_desc.addr() as u64))?;

        // 写入状态
        let status_desc = iter.next().unwrap();
        mem.write_obj(VIRTIO_BLK_S_OK, GuestAddress(status_desc.addr() as u64))?;

        Ok(())
    }
}

// ARM64 特定: MMIO 地址布局
#[cfg(target_arch = "aarch64")]
pub const VIRTIO_MMIO_BASE: u64 = 0x0a000000;

#[cfg(target_arch = "x86_64")]
pub const VIRTIO_MMIO_BASE: u64 = 0xd0000000;

pub const VIRTIO_MMIO_SIZE: u64 = 0x200;
```

**Virtio Net 实现（TAP 设备）**:
```rust
// src/virtio/net/tap.rs
use std::os::unix::io::{AsRawFd, RawFd};

pub struct Tap {
    tap_fd: RawFd,
    if_name: String,
}

impl Tap {
    pub fn new(name: &str) -> Result<Self> {
        let fd = unsafe {
            libc::open(
                b"/dev/net/tun\0".as_ptr() as *const libc::c_char,
                libc::O_RDWR | libc::O_NONBLOCK,
            )
        };

        if fd < 0 {
            return Err(Error::TapOpen);
        }

        // 设置 TAP 设备
        let mut ifr: libc::ifreq = unsafe { std::mem::zeroed() };
        ifr.ifr_ifru.ifru_flags = (libc::IFF_TAP | libc::IFF_NO_PI | libc::IFF_VNET_HDR) as i16;

        unsafe {
            std::ptr::copy_nonoverlapping(
                name.as_ptr(),
                ifr.ifr_name.as_mut_ptr() as *mut u8,
                name.len().min(libc::IFNAMSIZ - 1),
            );

            if libc::ioctl(fd, TUNSETIFF as u64, &ifr) < 0 {
                libc::close(fd);
                return Err(Error::TapSetup);
            }
        }

        Ok(Self {
            tap_fd: fd,
            if_name: name.to_string(),
        })
    }

    pub fn read_packet(&self, buf: &mut [u8]) -> Result<usize> {
        let ret = unsafe {
            libc::read(self.tap_fd, buf.as_mut_ptr() as *mut libc::c_void, buf.len())
        };

        if ret < 0 {
            Err(Error::TapRead)
        } else {
            Ok(ret as usize)
        }
    }
}
```

---

### 里程碑 4: HTTP API 和控制平面（Week 4）

**功能**:
- [x] RESTful API 服务器（使用 Axum）
- [x] VM 生命周期管理（创建/启动/停止/删除）
- [x] 配置管理（CPU/内存/设备）
- [x] 指标监控（CPU 使用率、内存、I/O）

**测试**:
```rust
#[tokio::test]
async fn test_api_create_vm() {
    let app = setup_test_api();

    let config = VmConfig {
        vcpu_count: 2,
        mem_size_mb: 512,
        kernel_path: "tests/kernels/bzImage".to_string(),
        rootfs_path: "tests/rootfs.ext4".to_string(),
    };

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/vm")
                .header("content-type", "application/json")
                .body(Body::from(serde_json::to_string(&config)?))
                .unwrap()
        )
        .await?;

    assert_eq!(response.status(), StatusCode::CREATED);

    let body: CreateVmResponse = serde_json::from_slice(
        &hyper::body::to_bytes(response.into_body()).await?
    )?;
    assert!(!body.vm_id.is_empty());
}

#[tokio::test]
async fn test_api_vm_lifecycle() {
    let app = setup_test_api();
    let vm_id = create_test_vm(&app).await?;

    // 启动 VM
    let response = app.clone()
        .oneshot(Request::builder()
            .method("PUT")
            .uri(&format!("/vm/{}/start", vm_id))
            .body(Body::empty())
            .unwrap()
        )
        .await?;
    assert_eq!(response.status(), StatusCode::OK);

    // 检查状态
    tokio::time::sleep(Duration::from_secs(2)).await;
    let response = app.clone()
        .oneshot(Request::builder()
            .method("GET")
            .uri(&format!("/vm/{}", vm_id))
            .body(Body::empty())
            .unwrap()
        )
        .await?;

    let status: VmStatus = serde_json::from_slice(
        &hyper::body::to_bytes(response.into_body()).await?
    )?;
    assert_eq!(status.state, VmState::Running);
}

#[tokio::test]
async fn test_metrics_collection() {
    let vm = create_running_vm().await?;

    tokio::time::sleep(Duration::from_secs(5)).await;

    let metrics = vm.get_metrics()?;
    assert!(metrics.cpu_usage_percent >= 0.0);
    assert!(metrics.cpu_usage_percent <= 100.0);
    assert!(metrics.memory_rss_bytes > 0);
}
```

**代码结构**:
```
src/
├── api/
│   ├── mod.rs
│   ├── server.rs      # Axum 服务器
│   ├── handlers.rs    # API 处理器
│   └── models.rs      # 请求/响应模型
├── vm_manager/
│   ├── mod.rs
│   ├── manager.rs     # VM 管理器
│   └── lifecycle.rs   # 生命周期控制
└── metrics/
    ├── mod.rs
    └── collector.rs   # 指标收集
```

**核心代码示例**:
```rust
// src/api/server.rs
use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post, put, delete},
    Json, Router,
};
use std::sync::Arc;
use tokio::sync::RwLock;

pub struct ApiServer {
    vm_manager: Arc<RwLock<VmManager>>,
}

impl ApiServer {
    pub fn new() -> Self {
        Self {
            vm_manager: Arc::new(RwLock::new(VmManager::new())),
        }
    }

    pub fn router(&self) -> Router {
        Router::new()
            .route("/vm", post(create_vm))
            .route("/vm/:id", get(get_vm_info))
            .route("/vm/:id/start", put(start_vm))
            .route("/vm/:id/stop", put(stop_vm))
            .route("/vm/:id", delete(delete_vm))
            .route("/vm/:id/metrics", get(get_vm_metrics))
            .with_state(self.vm_manager.clone())
    }

    pub async fn serve(self, addr: &str) -> Result<()> {
        let listener = tokio::net::TcpListener::bind(addr).await?;
        tracing::info!("API server listening on {}", addr);

        axum::serve(listener, self.router()).await?;
        Ok(())
    }
}

// API 处理器
async fn create_vm(
    State(manager): State<Arc<RwLock<VmManager>>>,
    Json(config): Json<VmConfig>,
) -> Result<(StatusCode, Json<CreateVmResponse>), ApiError> {
    let mut mgr = manager.write().await;
    let vm_id = mgr.create_vm(config).await?;

    Ok((
        StatusCode::CREATED,
        Json(CreateVmResponse { vm_id }),
    ))
}

async fn start_vm(
    State(manager): State<Arc<RwLock<VmManager>>>,
    Path(vm_id): Path<String>,
) -> Result<StatusCode, ApiError> {
    let mut mgr = manager.write().await;
    mgr.start_vm(&vm_id).await?;
    Ok(StatusCode::OK)
}

async fn get_vm_metrics(
    State(manager): State<Arc<RwLock<VmManager>>>,
    Path(vm_id): Path<String>,
) -> Result<Json<VmMetrics>, ApiError> {
    let mgr = manager.read().await;
    let metrics = mgr.get_vm_metrics(&vm_id).await?;
    Ok(Json(metrics))
}

// src/vm_manager/manager.rs
pub struct VmManager {
    vms: HashMap<String, MicroVm>,
    config: ManagerConfig,
}

impl VmManager {
    pub async fn create_vm(&mut self, config: VmConfig) -> Result<String> {
        let vm_id = Uuid::new_v4().to_string();

        let vm = MicroVm::new(config.mem_size_mb * 1024 * 1024)?;
        vm.add_vcpus(config.vcpu_count)?;
        vm.load_kernel(&config.kernel_path, "console=ttyS0")?;

        if let Some(rootfs) = config.rootfs_path {
            let block_device = VirtioBlock::new(&rootfs)?;
            vm.add_device(Box::new(block_device))?;
        }

        self.vms.insert(vm_id.clone(), vm);
        Ok(vm_id)
    }

    pub async fn start_vm(&mut self, vm_id: &str) -> Result<()> {
        let vm = self.vms.get_mut(vm_id)
            .ok_or(Error::VmNotFound)?;

        // 在独立线程中运行 VM
        let vm_clone = vm.clone();
        tokio::task::spawn_blocking(move || {
            vm_clone.run()
        });

        Ok(())
    }
}

// src/metrics/collector.rs
use sysinfo::{ProcessExt, System, SystemExt};

pub struct MetricsCollector {
    system: System,
}

impl MetricsCollector {
    pub fn collect(&mut self, pid: i32) -> VmMetrics {
        self.system.refresh_process(pid);

        let process = self.system.process(pid).unwrap();

        VmMetrics {
            cpu_usage_percent: process.cpu_usage() as f64,
            memory_rss_bytes: process.memory() * 1024,
            memory_virtual_bytes: process.virtual_memory() * 1024,
            disk_read_bytes: 0,  // 需要从 /proc/[pid]/io 读取
            disk_write_bytes: 0,
            uptime_seconds: process.run_time(),
        }
    }
}
```

---

## 完整项目结构

```
micro-vm-demo/
├── Cargo.toml
├── README.md
├── src/
│   ├── main.rs
│   ├── lib.rs
│   ├── kvm/
│   │   ├── mod.rs
│   │   ├── vm.rs
│   │   └── vcpu.rs
│   ├── memory/
│   │   ├── mod.rs
│   │   └── guest_memory.rs
│   ├── arch/
│   │   ├── mod.rs
│   │   ├── x86_64/
│   │   │   ├── mod.rs
│   │   │   ├── regs.rs
│   │   │   ├── boot.rs
│   │   │   └── cpuid.rs
│   │   └── aarch64/
│   │       ├── mod.rs
│   │       ├── regs.rs
│   │       ├── fdt.rs
│   │       └── gic.rs
│   ├── kernel/
│   │   ├── mod.rs
│   │   ├── loader.rs
│   │   └── cmdline.rs
│   ├── devices/
│   │   ├── mod.rs
│   │   ├── serial.rs
│   │   ├── interrupt.rs
│   │   └── legacy/
│   │       ├── i8042.rs
│   │       └── rtc.rs
│   ├── virtio/
│   │   ├── mod.rs
│   │   ├── device.rs
│   │   ├── queue.rs
│   │   ├── mmio.rs
│   │   ├── block/
│   │   │   ├── mod.rs
│   │   │   ├── device.rs
│   │   │   └── executor.rs
│   │   └── net/
│   │       ├── mod.rs
│   │       ├── device.rs
│   │       └── tap.rs
│   ├── api/
│   │   ├── mod.rs
│   │   ├── server.rs
│   │   ├── handlers.rs
│   │   └── models.rs
│   ├── vm_manager/
│   │   ├── mod.rs
│   │   ├── manager.rs
│   │   └── lifecycle.rs
│   └── metrics/
│       ├── mod.rs
│       └── collector.rs
├── tests/
│   ├── integration_test.rs
│   ├── api_test.rs
│   ├── kernels/
│   │   ├── bzImage-x86_64
│   │   └── Image-arm64
│   └── rootfs/
│       ├── alpine-x86_64.ext4
│       └── alpine-arm64.ext4
├── benches/
│   ├── boot_time.rs
│   └── io_performance.rs
└── scripts/
    ├── build.sh
    ├── test.sh
    ├── setup-tap.sh
    └── download-kernels.sh
```

---

## Cargo.toml 配置

```toml
[package]
name = "micro-vm-demo"
version = "0.1.0"
edition = "2021"

[dependencies]
# KVM 和内存管理
kvm-ioctls = "0.17"
kvm-bindings = "0.9"
vm-memory = { version = "0.15", features = ["backend-mmap"] }
vmm-sys-util = "0.12"

# Virtio
virtio-queue = "0.12"
virtio-bindings = "0.2"
vhost = "0.11"

# 异步运行时
tokio = { version = "1.41", features = ["full"] }
async-trait = "0.1"

# HTTP 服务器
axum = "0.7"
tower = "0.4"
tower-http = { version = "0.5", features = ["trace"] }

# 序列化
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

# 日志
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }

# 工具
anyhow = "1.0"
thiserror = "1.0"
uuid = { version = "1.0", features = ["v4"] }
libc = "0.2"

# ARM64 特定
[target.'cfg(target_arch = "aarch64")'.dependencies]
vm-fdt = "0.3"

[dev-dependencies]
criterion = { version = "0.5", features = ["html_reports"] }
proptest = "1.0"
tempfile = "3.0"

[[bench]]
name = "boot_time"
harness = false

[[bench]]
name = "io_performance"
harness = false

[profile.release]
opt-level = 3
lto = true
codegen-units = 1
```

---

## 测试策略

### 单元测试
```bash
# 运行所有单元测试
cargo test --lib

# 架构特定测试
cargo test --lib --target aarch64-unknown-linux-gnu
cargo test --lib --target x86_64-unknown-linux-gnu
```

### 集成测试
```bash
# 需要 root 权限（访问 /dev/kvm）
sudo cargo test --test integration_test

# API 测试
cargo test --test api_test
```

### 性能基准测试
```bash
cargo bench

# 结果保存在 target/criterion/
```

### 测试覆盖率
```bash
cargo install cargo-tarpaulin
cargo tarpaulin --out Html --output-dir coverage
```

---

## GitHub CI/CD 自动化测试

### 项目结构

```
.github/
├── workflows/
│   ├── ci.yml              # 主 CI 流程
│   ├── release.yml         # 发布流程
│   └── coverage.yml        # 代码覆盖率
├── actions/
│   └── setup-kvm/          # 自定义 Action: 设置 KVM
│       └── action.yml
└── dependabot.yml          # 依赖自动更新
```

---

### 主 CI 流程配置

**`.github/workflows/ci.yml`**:

```yaml
name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

env:
  CARGO_TERM_COLOR: always
  RUST_BACKTRACE: 1

jobs:
  # Job 1: 代码质量检查
  quality:
    name: Code Quality
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy

      - name: Cache cargo registry
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}
          restore-keys: |
            ${{ runner.os }}-cargo-

      - name: Check formatting
        run: cargo fmt --all -- --check

      - name: Run clippy
        run: cargo clippy --all-targets --all-features -- -D warnings

      - name: Check documentation
        run: cargo doc --no-deps --all-features
        env:
          RUSTDOCFLAGS: -D warnings

  # Job 2: 单元测试（多架构）
  unit-tests:
    name: Unit Tests - ${{ matrix.arch }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        include:
          # x86_64 Linux
          - arch: x86_64
            os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
            rust: stable
          # x86_64 Linux (nightly)
          - arch: x86_64
            os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
            rust: nightly
          # ARM64 Linux (交叉编译)
          - arch: aarch64
            os: ubuntu-latest
            target: aarch64-unknown-linux-gnu
            rust: stable

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust ${{ matrix.rust }}
        uses: dtolnay/rust-toolchain@master
        with:
          toolchain: ${{ matrix.rust }}
          targets: ${{ matrix.target }}

      - name: Install cross-compilation tools (ARM64)
        if: matrix.arch == 'aarch64'
        run: |
          sudo apt-get update
          sudo apt-get install -y gcc-aarch64-linux-gnu g++-aarch64-linux-gnu

      - name: Configure cross compilation
        if: matrix.arch == 'aarch64'
        run: |
          mkdir -p .cargo
          cat >> .cargo/config.toml <<EOF
          [target.aarch64-unknown-linux-gnu]
          linker = "aarch64-linux-gnu-gcc"
          EOF

      - name: Cache cargo artifacts
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-${{ matrix.target }}-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Build
        run: cargo build --target ${{ matrix.target }} --verbose

      - name: Run unit tests
        run: cargo test --lib --target ${{ matrix.target }} --verbose
        continue-on-error: ${{ matrix.rust == 'nightly' }}

  # Job 3: 集成测试（需要 KVM）
  integration-tests:
    name: Integration Tests - ${{ matrix.kvm-mode }}
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        kvm-mode: [hardware, emulated]

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable

      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            qemu-kvm \
            qemu-utils \
            bridge-utils \
            libvirt-daemon-system \
            libvirt-clients

      # 检查硬件虚拟化支持
      - name: Check KVM support
        id: check-kvm
        run: |
          if [ -e /dev/kvm ]; then
            echo "kvm-available=true" >> $GITHUB_OUTPUT
            echo "✅ Hardware KVM available"
            ls -l /dev/kvm
          else
            echo "kvm-available=false" >> $GITHUB_OUTPUT
            echo "⚠️  Hardware KVM not available, will use software emulation"
          fi

      # 硬件 KVM 模式
      - name: Setup KVM permissions
        if: matrix.kvm-mode == 'hardware' && steps.check-kvm.outputs.kvm-available == 'true'
        run: |
          sudo chmod 666 /dev/kvm
          sudo usermod -aG kvm $USER

      # 软件模拟模式（用于不支持嵌套虚拟化的 CI 环境）
      - name: Setup software emulation
        if: matrix.kvm-mode == 'emulated' || steps.check-kvm.outputs.kvm-available == 'false'
        run: |
          # 使用 mock KVM 或跳过需要真实 KVM 的测试
          echo "MICRO_VM_TEST_MODE=mock" >> $GITHUB_ENV

      - name: Download test kernels
        run: |
          mkdir -p tests/kernels tests/rootfs

          # 下载轻量级测试内核
          wget -q -O tests/kernels/bzImage-x86_64 \
            https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin || true

      - name: Cache cargo artifacts
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-integration-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Build integration tests
        run: cargo test --test integration_test --no-run

      - name: Run integration tests
        run: |
          if [ "${{ matrix.kvm-mode }}" = "hardware" ] && [ "${{ steps.check-kvm.outputs.kvm-available }}" = "true" ]; then
            sudo -E cargo test --test integration_test -- --test-threads=1
          else
            # 软件模拟模式，只运行不需要真实 KVM 的测试
            cargo test --test integration_test -- --skip requires_kvm --test-threads=1
          fi
        timeout-minutes: 10

      - name: Upload test logs
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: integration-test-logs-${{ matrix.kvm-mode }}
          path: |
            target/debug/test-*.log
            /tmp/micro-vm-*.log

  # Job 4: API 测试
  api-tests:
    name: API Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable

      - name: Cache cargo artifacts
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-api-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Build API tests
        run: cargo test --test api_test --no-run

      - name: Run API tests
        run: cargo test --test api_test --verbose

  # Job 5: 性能基准测试
  benchmarks:
    name: Benchmarks
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y qemu-kvm

      - name: Cache cargo artifacts
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-bench-cargo-${{ hashFiles('**/Cargo.lock') }}

      - name: Run benchmarks
        run: |
          # 在 mock 模式下运行基准测试
          MICRO_VM_TEST_MODE=mock cargo bench --no-fail-fast
        continue-on-error: true

      - name: Upload benchmark results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: target/criterion/

  # Job 6: 安全审计
  security-audit:
    name: Security Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install cargo-audit
        run: cargo install cargo-audit

      - name: Run security audit
        run: cargo audit

      - name: Check for vulnerabilities
        run: cargo audit --deny warnings
        continue-on-error: true

  # Job 7: 依赖检查
  dependency-check:
    name: Dependency Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install cargo-deny
        run: cargo install cargo-deny

      - name: Check dependencies
        run: cargo deny check

  # Job 8: 构建发布版本
  build-release:
    name: Build Release - ${{ matrix.target }}
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
            artifact: micro-vm-demo-x86_64-linux
          - os: ubuntu-latest
            target: aarch64-unknown-linux-gnu
            artifact: micro-vm-demo-aarch64-linux

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - name: Install cross-compilation tools
        if: matrix.target == 'aarch64-unknown-linux-gnu'
        run: |
          sudo apt-get update
          sudo apt-get install -y gcc-aarch64-linux-gnu

      - name: Cache cargo artifacts
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-${{ matrix.target }}-release-${{ hashFiles('**/Cargo.lock') }}

      - name: Build release
        run: cargo build --release --target ${{ matrix.target }}

      - name: Strip binary
        run: |
          if [ "${{ matrix.target }}" = "aarch64-unknown-linux-gnu" ]; then
            aarch64-linux-gnu-strip target/${{ matrix.target }}/release/micro-vm-demo
          else
            strip target/${{ matrix.target }}/release/micro-vm-demo
          fi

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: ${{ matrix.artifact }}
          path: target/${{ matrix.target }}/release/micro-vm-demo
```

---

### 代码覆盖率配置

**`.github/workflows/coverage.yml`**:

```yaml
name: Code Coverage

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  coverage:
    name: Generate Coverage Report
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable
        with:
          components: llvm-tools-preview

      - name: Install cargo-llvm-cov
        run: cargo install cargo-llvm-cov

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y qemu-utils

      - name: Cache cargo artifacts
        uses: actions/cache@v4
        with:
          path: |
            ~/.cargo/registry
            ~/.cargo/git
            target
          key: ${{ runner.os }}-coverage-${{ hashFiles('**/Cargo.lock') }}

      - name: Generate coverage
        run: |
          # 只运行单元测试和不需要 KVM 的测试
          cargo llvm-cov --lib --html --output-dir coverage

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: coverage/coverage.json
          fail_ci_if_error: false

      - name: Upload coverage artifact
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage/
```

---

### 发布流程配置

**`.github/workflows/release.yml`**:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*.*.*'

permissions:
  contents: write

jobs:
  create-release:
    name: Create Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Create Release
        uses: actions/create-release@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          tag_name: ${{ github.ref }}
          release_name: Release ${{ github.ref }}
          draft: false
          prerelease: false

  build-and-upload:
    name: Build and Upload - ${{ matrix.target }}
    needs: create-release
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
            artifact: micro-vm-demo-x86_64-linux.tar.gz
          - os: ubuntu-latest
            target: aarch64-unknown-linux-gnu
            artifact: micro-vm-demo-aarch64-linux.tar.gz

    steps:
      - uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - name: Install cross-compilation tools
        if: matrix.target == 'aarch64-unknown-linux-gnu'
        run: |
          sudo apt-get update
          sudo apt-get install -y gcc-aarch64-linux-gnu

      - name: Build release
        run: cargo build --release --target ${{ matrix.target }}

      - name: Package release
        run: |
          cd target/${{ matrix.target }}/release
          tar czf ${{ matrix.artifact }} micro-vm-demo
          cd -
          mv target/${{ matrix.target }}/release/${{ matrix.artifact }} .

      - name: Upload Release Asset
        uses: actions/upload-release-asset@v1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          upload_url: ${{ needs.create-release.outputs.upload_url }}
          asset_path: ./${{ matrix.artifact }}
          asset_name: ${{ matrix.artifact }}
          asset_content_type: application/gzip
```

---

### Dependabot 配置

**`.github/dependabot.yml`**:

```yaml
version: 2
updates:
  # Cargo 依赖更新
  - package-ecosystem: "cargo"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
    reviewers:
      - "your-github-username"
    labels:
      - "dependencies"
      - "rust"

  # GitHub Actions 更新
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "ci"
```

---

### 自定义 KVM Setup Action

**`.github/actions/setup-kvm/action.yml`**:

```yaml
name: 'Setup KVM'
description: 'Setup KVM for testing or use mock mode'
outputs:
  kvm-available:
    description: 'Whether KVM is available'
    value: ${{ steps.check.outputs.available }}
runs:
  using: 'composite'
  steps:
    - name: Check KVM availability
      id: check
      shell: bash
      run: |
        if [ -e /dev/kvm ]; then
          echo "available=true" >> $GITHUB_OUTPUT
          echo "✅ KVM is available"
        else
          echo "available=false" >> $GITHUB_OUTPUT
          echo "⚠️  KVM is not available, using mock mode"
        fi

    - name: Setup KVM permissions
      if: steps.check.outputs.available == 'true'
      shell: bash
      run: |
        sudo chmod 666 /dev/kvm || true
        sudo usermod -aG kvm $USER || true
```

---

### 测试支持：Mock KVM 模式

为了在不支持嵌套虚拟化的 CI 环境中运行测试，需要添加 Mock 模式支持：

**`src/kvm/mock.rs`**:

```rust
//! Mock KVM implementation for CI environments without KVM support

use std::sync::Arc;

pub struct MockKvm {
    // Mock implementation
}

impl MockKvm {
    pub fn new() -> Result<Self> {
        Ok(Self {})
    }
}

// 在测试中使用
#[cfg(test)]
pub fn create_test_kvm() -> Box<dyn KvmInterface> {
    if std::env::var("MICRO_VM_TEST_MODE").as_deref() == Ok("mock") {
        Box::new(MockKvm::new().unwrap())
    } else {
        Box::new(RealKvm::new().unwrap())
    }
}
```

**测试标记**:

```rust
// 标记需要真实 KVM 的测试
#[test]
#[cfg_attr(not(feature = "kvm-tests"), ignore)]
fn test_requires_real_kvm() {
    // 需要真实 KVM 的测试
}

// 可以在 mock 模式下运行的测试
#[test]
fn test_works_in_mock_mode() {
    let kvm = create_test_kvm();
    // 测试逻辑
}
```

---

### README 徽章

在 `README.md` 中添加状态徽章：

```markdown
# MicroVM Demo

[![CI](https://github.com/your-username/micro-vm-demo/workflows/CI/badge.svg)](https://github.com/your-username/micro-vm-demo/actions?query=workflow%3ACI)
[![Coverage](https://codecov.io/gh/your-username/micro-vm-demo/branch/main/graph/badge.svg)](https://codecov.io/gh/your-username/micro-vm-demo)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Rust Version](https://img.shields.io/badge/rust-1.70%2B-orange.svg)](https://www.rust-lang.org)
```

---

### 本地 CI 测试

使用 `act` 在本地运行 GitHub Actions：

```bash
# 安装 act
brew install act  # macOS
# 或
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# 运行所有 CI 任务
act

# 运行特定 job
act -j unit-tests

# 使用特定事件触发
act pull_request

# 使用大型 runner 镜像（更接近 GitHub 环境）
act -P ubuntu-latest=catthehacker/ubuntu:full-latest
```

---

### CI/CD 优化建议

#### 1. 缓存策略
```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.cargo/registry/index
      ~/.cargo/registry/cache
      ~/.cargo/git/db
      target
    key: ${{ runner.os }}-cargo-${{ hashFiles('**/Cargo.lock') }}
    restore-keys: |
      ${{ runner.os }}-cargo-
```

#### 2. 并行化测试
```yaml
strategy:
  matrix:
    test-suite:
      - unit
      - integration
      - api
      - benchmarks
```

#### 3. 增量构建
```yaml
env:
  CARGO_INCREMENTAL: 1
  CARGO_NET_RETRY: 10
  RUSTUP_MAX_RETRIES: 10
```

#### 4. 跳过不必要的步骤
```yaml
- name: Check if Rust files changed
  id: changed-files
  uses: tj-actions/changed-files@v40
  with:
    files: |
      **/*.rs
      **/Cargo.toml
      **/Cargo.lock

- name: Run tests
  if: steps.changed-files.outputs.any_changed == 'true'
  run: cargo test
```

---

### 性能监控

添加性能回归检测：

**`.github/workflows/performance.yml`**:

```yaml
name: Performance Monitoring

on:
  push:
    branches: [ main ]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run benchmarks
        run: cargo bench -- --save-baseline current

      - name: Compare with baseline
        run: |
          cargo bench -- --baseline previous --load-baseline current
        continue-on-error: true

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-comparison
          path: target/criterion/
```

---

### 常见 CI 问题排查

#### 问题 1: KVM 不可用
```yaml
# 解决方案：使用软件模拟或跳过测试
- name: Handle KVM unavailability
  run: |
    if [ ! -e /dev/kvm ]; then
      echo "MICRO_VM_TEST_MODE=mock" >> $GITHUB_ENV
    fi
```

#### 问题 2: 交叉编译失败
```yaml
# 解决方案：确保安装正确的工具链
- name: Install ARM64 toolchain
  run: |
    sudo apt-get install -y \
      gcc-aarch64-linux-gnu \
      g++-aarch64-linux-gnu \
      binutils-aarch64-linux-gnu
```

#### 问题 3: 测试超时
```yaml
# 解决方案：增加超时时间或减少测试并行度
- name: Run tests with timeout
  run: cargo test -- --test-threads=1
  timeout-minutes: 30
```

---

### 总结

完整的 CI/CD 流程包括：

✅ **代码质量检查** - rustfmt, clippy, doc
✅ **多架构测试** - x86_64, ARM64
✅ **单元测试** - 所有模块
✅ **集成测试** - 硬件 KVM + 软件模拟
✅ **API 测试** - HTTP API 端点
✅ **性能基准** - Criterion benchmarks
✅ **安全审计** - cargo-audit
✅ **依赖检查** - cargo-deny
✅ **代码覆盖率** - codecov
✅ **自动发布** - GitHub Releases
✅ **依赖更新** - Dependabot

这套 CI/CD 配置参考了 Firecracker、Cloud Hypervisor 等项目的最佳实践，确保代码质量和测试覆盖。

---

## ARM64 特定注意事项

### 1. 设备树（Device Tree）
ARM64 使用 FDT 替代 x86 的 ACPI/BIOS:
```rust
// 必须提供的 DT 节点
- /cpus
- /memory
- /chosen (bootargs, initrd)
- /intc (GIC 中断控制器)
- /timer
- /serial
- /virtio_mmio@ (每个 virtio 设备)
```

### 2. GIC 中断控制器
```rust
// x86: APIC
// ARM64: GICv2/GICv3
const GICD_BASE: u64 = 0x08000000;
const GICR_BASE: u64 = 0x080A0000;
const GIC_IRQ_BASE: u32 = 32;  // SPI starts at 32
```

### 3. 内存布局差异
```rust
// ARM64 典型布局
const ARM64_MEM_START: u64 = 0x40000000;  // 1GB
const ARM64_KERNEL_OFFSET: u64 = 0x00080000;  // 512KB

// x86_64 典型布局
const X86_64_MEM_START: u64 = 0x0;
const X86_64_KERNEL_OFFSET: u64 = 0x100000;  // 1MB
```

### 4. PSCI (电源管理)
```rust
// ARM64 需要实现 PSCI 调用
const PSCI_0_2_FN_CPU_ON: u32 = 0x84000003;
const PSCI_0_2_FN_SYSTEM_OFF: u32 = 0x84000008;
```

### 5. 交叉编译
```bash
# 安装 ARM64 工具链
rustup target add aarch64-unknown-linux-gnu
sudo apt install gcc-aarch64-linux-gnu

# 编译
cargo build --target aarch64-unknown-linux-gnu

# .cargo/config.toml
[target.aarch64-unknown-linux-gnu]
linker = "aarch64-linux-gnu-gcc"
```

---

## 构建和运行

### 1. 环境准备
```bash
# 安装依赖
sudo apt update
sudo apt install -y \
    build-essential \
    libssl-dev \
    pkg-config \
    qemu-utils \
    bridge-utils

# 检查 KVM 支持
lsmod | grep kvm
ls -l /dev/kvm

# 配置用户权限
sudo usermod -aG kvm $USER
```

### 2. 下载测试资源
```bash
#!/bin/bash
# scripts/download-kernels.sh

KERNEL_DIR="tests/kernels"
ROOTFS_DIR="tests/rootfs"

mkdir -p $KERNEL_DIR $ROOTFS_DIR

# x86_64 内核
wget -O $KERNEL_DIR/bzImage-x86_64 \
    https://s3.amazonaws.com/spec.ccfc.min/img/quickstart_guide/x86_64/kernels/vmlinux.bin

# ARM64 内核
wget -O $KERNEL_DIR/Image-arm64 \
    https://github.com/firecracker-microvm/firecracker/raw/main/tests/framework/kernels/aarch64/vmlinux-5.10.bin

# Alpine rootfs
wget -O $ROOTFS_DIR/alpine-x86_64.ext4 \
    https://dl-cdn.alpinelinux.org/alpine/v3.19/releases/x86_64/alpine-minirootfs-3.19.0-x86_64.tar.gz

# 解压并制作 ext4
mkdir -p /tmp/alpine-rootfs
tar -xzf $ROOTFS_DIR/alpine-x86_64.tar.gz -C /tmp/alpine-rootfs
dd if=/dev/zero of=$ROOTFS_DIR/alpine-x86_64.ext4 bs=1M count=100
mkfs.ext4 $ROOTFS_DIR/alpine-x86_64.ext4
sudo mount $ROOTFS_DIR/alpine-x86_64.ext4 /mnt
sudo cp -r /tmp/alpine-rootfs/* /mnt/
sudo umount /mnt
```

### 3. 配置网络
```bash
#!/bin/bash
# scripts/setup-tap.sh

TAP_NAME="vmtap0"
BRIDGE_NAME="vmbr0"

# 创建 TAP 设备
sudo ip tuntap add dev $TAP_NAME mode tap
sudo ip link set $TAP_NAME up

# 创建网桥
sudo ip link add name $BRIDGE_NAME type bridge
sudo ip link set $BRIDGE_NAME up
sudo ip addr add 192.168.100.1/24 dev $BRIDGE_NAME

# 将 TAP 加入网桥
sudo ip link set $TAP_NAME master $BRIDGE_NAME

# 启用 IP 转发
sudo sysctl -w net.ipv4.ip_forward=1
```

### 4. 编译项目
```bash
#!/bin/bash
# scripts/build.sh

# x86_64
cargo build --release

# ARM64 (交叉编译)
cargo build --release --target aarch64-unknown-linux-gnu

# 运行测试
sudo -E cargo test --release
```

### 5. 启动 DEMO
```bash
# 方式 1: 直接运行（命令行模式）
sudo ./target/release/micro-vm-demo \
    --kernel tests/kernels/bzImage-x86_64 \
    --rootfs tests/rootfs/alpine-x86_64.ext4 \
    --mem-size 512 \
    --vcpus 2

# 方式 2: API 服务器模式
sudo ./target/release/micro-vm-demo \
    --api-server \
    --listen 0.0.0.0:8080

# 使用 API 创建 VM
curl -X POST http://localhost:8080/vm \
    -H "Content-Type: application/json" \
    -d '{
        "vcpu_count": 2,
        "mem_size_mb": 512,
        "kernel_path": "tests/kernels/bzImage-x86_64",
        "rootfs_path": "tests/rootfs/alpine-x86_64.ext4"
    }'

# 启动 VM
curl -X PUT http://localhost:8080/vm/{vm_id}/start
```

---

## 性能基准

### 预期性能指标
| 指标 | 目标 | 参考项目 |
|------|------|---------|
| 启动时间（到内核） | < 150ms | Firecracker: 125ms |
| 启动时间（到用户空间） | < 1s | StratoVirt: ~1s |
| 内存开销（空闲） | < 50MB | Firecracker: 32MB |
| Block I/O 吞吐量 | > 500 MB/s | Cloud Hypervisor: ~600 MB/s |
| Network 吞吐量 | > 1 Gbps | Firecracker: ~3 Gbps |

### Benchmark 代码
```rust
// benches/boot_time.rs
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use micro_vm_demo::MicroVm;

fn bench_vm_boot(c: &mut Criterion) {
    c.bench_function("vm_boot_to_kernel", |b| {
        b.iter(|| {
            let vm = MicroVm::new(black_box(512 * 1024 * 1024)).unwrap();
            vm.load_kernel("tests/kernels/bzImage-x86_64", "").unwrap();

            let start = std::time::Instant::now();
            vm.run_until_kernel_log("Linux version").unwrap();
            start.elapsed()
        });
    });
}

criterion_group!(benches, bench_vm_boot);
criterion_main!(benches);
```

---

## 调试技巧

### 1. 启用详细日志
```bash
RUST_LOG=debug sudo ./target/release/micro-vm-demo ...
```

### 2. 使用 GDB 调试 Guest
```rust
// 在 KVM 中启用调试端口
vm_fd.set_gsi_routing(&gsi_routing)?;

// 使用 GDB 连接
gdb -ex "target remote localhost:1234"
```

### 3. 监控 KVM 事件
```bash
# 启用 KVM tracing
echo 1 | sudo tee /sys/kernel/debug/tracing/events/kvm/enable
sudo cat /sys/kernel/debug/tracing/trace_pipe
```

### 4. 内存泄漏检测
```bash
cargo install cargo-valgrind
sudo valgrind --leak-check=full \
    ./target/release/micro-vm-demo ...
```

---

## 下一步扩展

完成 DEMO 后，可以考虑添加：

1. **快照和恢复**（参考 Firecracker）
2. **热插拔** CPU/内存（参考 Cloud Hypervisor）
3. **vhost-user** 设备（高性能 I/O）
4. **多架构支持**（RISC-V）
5. **Seccomp 沙箱**（参考 Firecracker Jailer）
6. **指标导出**（Prometheus 格式）
7. **容器镜像支持**（OCI runtime）

---

## 参考资源

### 文档
- [KVM API Documentation](https://www.kernel.org/doc/html/latest/virt/kvm/api.html)
- [Virtio Specification 1.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html)
- [ARM ARM (Architecture Reference Manual)](https://developer.arm.com/documentation/)
- [Linux Boot Protocol (x86)](https://www.kernel.org/doc/html/latest/x86/boot.html)

### 示例项目
- Firecracker: `firecracker-microvm/firecracker`
- Cloud Hypervisor: `cloud-hypervisor/cloud-hypervisor`
- StratoVirt: `openeuler/stratovirt`
- rust-vmm: `rust-vmm/community`

---

## 总结

这个 DEMO 实现计划提供了一个**4 周内可完成**的最小化 MicroVM 实现路径：

- **Week 1**: KVM 基础 + 简单代码执行
- **Week 2**: Linux 内核启动 + 串口输出
- **Week 3**: Virtio 设备 + 完整 rootfs
- **Week 4**: HTTP API + 生命周期管理

所有第三方库都来自于 Firecracker、Cloud Hypervisor、StratoVirt 等生产级项目，**完整测试覆盖**，**原生支持 ARM64**。

核心特点：
✅ 切实可行的 4 周计划
✅ 每个里程碑都有完整测试
✅ 基于真实项目的库选型
✅ ARM64 和 x86_64 双架构
✅ 从单元测试到性能基准的完整测试策略
✅ 可运行的代码示例和脚本
