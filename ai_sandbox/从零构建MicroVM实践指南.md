# 从零构建 MicroVM/Serverless 平台实践指南

## 项目概述

基于对 Firecracker、StratoVirt、Cloud Hypervisor 等项目的深度分析，本指南提供了一个使用 Rust 从零构建 MicroVM 平台的完整路线图。

**项目目标:**
- 构建一个轻量级的虚拟机监控器(VMM)
- 支持快速启动(目标 <500ms)
- 内存占用小(目标 <50MB)
- 安全隔离(基于 KVM 硬件虚拟化)
- 可扩展为 Serverless 平台

**技术栈:**
- 语言: Rust 1.70+
- 虚拟化: KVM (Linux Kernel-based Virtual Machine)
- 网络: TAP/veth
- 存储: virtio-blk
- 构建工具: Cargo

---

## 第一阶段: 前置知识准备 (2-4周)

### 1.1 必备知识清单

#### A. Rust 语言能力

**基础要求:**
```rust
// 1. 所有权和借用
fn ownership_example() {
    let s1 = String::from("hello");
    let s2 = s1;  // s1 moved
    // println!("{}", s1);  // Error: value borrowed after move
}

// 2. 生命周期
struct VM<'a> {
    name: &'a str,
    memory: Vec<u8>,
}

// 3. Trait 和泛型
trait Hypervisor {
    fn start(&mut self) -> Result<(), Error>;
    fn stop(&mut self) -> Result<(), Error>;
}

// 4. 错误处理
use anyhow::{Context, Result};
fn create_vm() -> Result<VM> {
    let vm = VM::new()
        .context("Failed to create VM")?;
    Ok(vm)
}

// 5. 异步编程 (可选,后期优化用)
use tokio::runtime::Runtime;
async fn async_operation() {
    // async code
}
```

**推荐学习资源:**
- 《The Rust Programming Language》(官方书)
- 《Rust for Rustaceans》(进阶)
- `std::os::unix` 模块文档 (Unix 系统调用)

#### B. 操作系统和虚拟化知识

**关键概念:**

1. **KVM 基础:**
```bash
# KVM 设备节点
/dev/kvm

# 检查 KVM 是否可用
lsmod | grep kvm
# 应该看到: kvm_intel 或 kvm_amd
```

2. **虚拟化核心概念:**
```
┌─────────────────────────────────────┐
│         User Space                  │
│  ┌──────────────────────────────┐  │
│  │    Your VMM (Rust Program)    │  │
│  │                               │  │
│  │  - VM Management              │  │
│  │  - vCPU Control               │  │
│  │  - Memory Mapping             │  │
│  │  - Device Emulation           │  │
│  └───────────┬──────────────────┘  │
└──────────────┼─────────────────────┘
               │ ioctl() syscalls
┌──────────────▼─────────────────────┐
│      Kernel Space (KVM Module)     │
│  - Hardware-assisted virtualization│
│  - VM Exits handling               │
│  - Memory virtualization (EPT/NPT) │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│       Hardware (CPU + RAM)         │
│  - Intel VT-x / AMD-V              │
│  - Extended Page Tables            │
└────────────────────────────────────┘
```

3. **关键 KVM ioctl 命令:**
```rust
// KVM ioctl 常量 (需要从 Linux headers 获取)
const KVM_CREATE_VM: u64 = 0xAE01;
const KVM_CREATE_VCPU: u64 = 0xAE41;
const KVM_RUN: u64 = 0xAE80;
const KVM_SET_USER_MEMORY_REGION: u64 = 0x4020AE46;
const KVM_GET_VCPU_MMAP_SIZE: u64 = 0xAE04;
```

**推荐学习资源:**
- 《Using the KVM API》(LWN.net 文章)
- 《深入理解 Linux 虚拟内存管理》
- QEMU 和 Firecracker 源码阅读

#### C. Linux 系统编程

**必备技能:**

```rust
// 1. 文件描述符操作
use std::os::unix::io::RawFd;
use nix::sys::stat::Mode;
use nix::fcntl::{open, OFlag};

fn open_kvm_device() -> Result<RawFd> {
    let fd = open(
        "/dev/kvm",
        OFlag::O_RDWR | OFlag::O_CLOEXEC,
        Mode::empty()
    )?;
    Ok(fd)
}

// 2. ioctl 调用
use nix::ioctl_write_int;
ioctl_write_int!(kvm_create_vm, 0xAE, 0x01);

// 3. mmap 内存映射
use nix::sys::mman::{mmap, MapFlags, ProtFlags};
use std::ptr;

fn map_guest_memory(size: usize) -> Result<*mut u8> {
    let addr = unsafe {
        mmap(
            ptr::null_mut(),
            size,
            ProtFlags::PROT_READ | ProtFlags::PROT_WRITE,
            MapFlags::MAP_PRIVATE | MapFlags::MAP_ANONYMOUS,
            -1,
            0
        )?
    };
    Ok(addr as *mut u8)
}

// 4. eventfd 和 epoll
use nix::sys::eventfd::{eventfd, EfdFlags};
use nix::sys::epoll::{epoll_create1, epoll_ctl, EpollEvent, EpollFlags, EpollOp};
```

**推荐学习资源:**
- 《The Linux Programming Interface》
- `nix` crate 文档 (Rust 的 Unix API 绑定)
- `libc` crate 文档

### 1.2 开发环境搭建

```bash
# 1. 安装 Rust 工具链
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup default stable

# 2. 安装必要的开发工具
sudo apt-get install -y \
    build-essential \
    libcap-dev \
    linux-headers-$(uname -r) \
    qemu-system-x86

# 3. 验证 KVM 可用
sudo apt-get install -y cpu-checker
kvm-ok
# 输出: INFO: /dev/kvm exists
#       KVM acceleration can be used

# 4. 创建项目
cargo new micro-vm --bin
cd micro-vm

# 5. 添加依赖 (Cargo.toml)
```

**初始 `Cargo.toml`:**
```toml
[package]
name = "micro-vm"
version = "0.1.0"
edition = "2021"

[dependencies]
# 错误处理
anyhow = "1.0"
thiserror = "1.0"

# Unix 系统调用
nix = { version = "0.27", features = ["ioctl", "mman", "event"] }
libc = "0.2"

# 日志
log = "0.4"
env_logger = "0.10"

# 序列化 (配置文件)
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"

# 命令行参数解析
clap = { version = "4.0", features = ["derive"] }

# 虚拟化相关 (可选,后期添加)
# kvm-bindings = "0.6"
# kvm-ioctls = "0.15"
# vm-memory = "0.12"

[dev-dependencies]
tempfile = "3.0"
```

---

## 第二阶段: 最小可行 VMM (4-6周)

### 2.1 第一个里程碑: Hello World VM

**目标:** 创建一个 VM,执行一段机器码,打印 "Hello World"

#### Step 1: KVM 设备打开和 VM 创建

**文件:** `src/kvm/mod.rs`

```rust
use anyhow::{Context, Result};
use nix::fcntl::{open, OFlag};
use nix::sys::stat::Mode;
use std::os::unix::io::RawFd;

pub struct Kvm {
    fd: RawFd,
}

impl Kvm {
    /// 打开 /dev/kvm 设备
    pub fn new() -> Result<Self> {
        let fd = open(
            "/dev/kvm",
            OFlag::O_RDWR | OFlag::O_CLOEXEC,
            Mode::empty()
        ).context("Failed to open /dev/kvm")?;

        log::info!("Opened /dev/kvm, fd={}", fd);
        Ok(Kvm { fd })
    }

    /// 创建虚拟机
    pub fn create_vm(&self) -> Result<Vm> {
        // KVM_CREATE_VM ioctl
        let vm_fd = unsafe {
            libc::ioctl(self.fd, KVM_CREATE_VM, 0)
        };

        if vm_fd < 0 {
            anyhow::bail!("Failed to create VM");
        }

        log::info!("Created VM, fd={}", vm_fd);
        Ok(Vm { fd: vm_fd })
    }

    /// 获取 KVM API 版本
    pub fn get_api_version(&self) -> Result<i32> {
        let version = unsafe {
            libc::ioctl(self.fd, KVM_GET_API_VERSION, 0)
        };

        if version < 0 {
            anyhow::bail!("Failed to get KVM API version");
        }

        Ok(version)
    }
}

impl Drop for Kvm {
    fn drop(&mut self) {
        unsafe { libc::close(self.fd) };
    }
}

pub struct Vm {
    fd: RawFd,
}

impl Vm {
    /// 创建 vCPU
    pub fn create_vcpu(&self, id: u32) -> Result<Vcpu> {
        let vcpu_fd = unsafe {
            libc::ioctl(self.fd, KVM_CREATE_VCPU, id as libc::c_ulong)
        };

        if vcpu_fd < 0 {
            anyhow::bail!("Failed to create vCPU");
        }

        log::info!("Created vCPU {}, fd={}", id, vcpu_fd);
        Ok(Vcpu {
            fd: vcpu_fd,
            id,
            run_mmap: None,
        })
    }

    /// 设置用户内存区域
    pub fn set_user_memory_region(
        &self,
        slot: u32,
        guest_phys_addr: u64,
        memory_size: u64,
        userspace_addr: u64,
    ) -> Result<()> {
        let region = kvm_userspace_memory_region {
            slot,
            flags: 0,
            guest_phys_addr,
            memory_size,
            userspace_addr,
        };

        let ret = unsafe {
            libc::ioctl(
                self.fd,
                KVM_SET_USER_MEMORY_REGION,
                &region as *const _ as libc::c_ulong
            )
        };

        if ret < 0 {
            anyhow::bail!("Failed to set user memory region");
        }

        log::info!(
            "Set memory region: slot={}, guest_phys={:#x}, size={:#x}",
            slot, guest_phys_addr, memory_size
        );
        Ok(())
    }
}

impl Drop for Vm {
    fn drop(&mut self) {
        unsafe { libc::close(self.fd) };
    }
}

// KVM ioctl 常量
const KVM_GET_API_VERSION: libc::c_ulong = 0xAE00;
const KVM_CREATE_VM: libc::c_ulong = 0xAE01;
const KVM_CREATE_VCPU: libc::c_ulong = 0xAE41;
const KVM_SET_USER_MEMORY_REGION: libc::c_ulong = 0x4020AE46;

#[repr(C)]
struct kvm_userspace_memory_region {
    slot: u32,
    flags: u32,
    guest_phys_addr: u64,
    memory_size: u64,
    userspace_addr: u64,
}
```

#### Step 2: vCPU 管理和运行

**文件:** `src/kvm/vcpu.rs`

```rust
use anyhow::{Context, Result};
use nix::sys::mman::{mmap, munmap, MapFlags, ProtFlags};
use std::os::unix::io::RawFd;
use std::ptr;

pub struct Vcpu {
    pub fd: RawFd,
    pub id: u32,
    pub run_mmap: Option<*mut kvm_run>,
}

impl Vcpu {
    /// 初始化 vCPU (mmap kvm_run 结构)
    pub fn init(&mut self, kvm_fd: RawFd) -> Result<()> {
        // 获取 kvm_run 结构的大小
        let mmap_size = unsafe {
            libc::ioctl(kvm_fd, KVM_GET_VCPU_MMAP_SIZE, 0)
        };

        if mmap_size < 0 {
            anyhow::bail!("Failed to get VCPU mmap size");
        }

        // mmap kvm_run 结构
        let run_mmap = unsafe {
            mmap(
                ptr::null_mut(),
                mmap_size as usize,
                ProtFlags::PROT_READ | ProtFlags::PROT_WRITE,
                MapFlags::MAP_SHARED,
                self.fd,
                0
            )?
        };

        self.run_mmap = Some(run_mmap as *mut kvm_run);
        log::info!("vCPU {} initialized, run_mmap={:p}", self.id, run_mmap);
        Ok(())
    }

    /// 设置寄存器 (x86_64)
    pub fn set_regs(&self, regs: &kvm_regs) -> Result<()> {
        let ret = unsafe {
            libc::ioctl(
                self.fd,
                KVM_SET_REGS,
                regs as *const _ as libc::c_ulong
            )
        };

        if ret < 0 {
            anyhow::bail!("Failed to set registers");
        }

        Ok(())
    }

    /// 设置特殊寄存器 (段寄存器等)
    pub fn set_sregs(&self, sregs: &kvm_sregs) -> Result<()> {
        let ret = unsafe {
            libc::ioctl(
                self.fd,
                KVM_SET_SREGS,
                sregs as *const _ as libc::c_ulong
            )
        };

        if ret < 0 {
            anyhow::bail!("Failed to set special registers");
        }

        Ok(())
    }

    /// 运行 vCPU
    pub fn run(&self) -> Result<VmExit> {
        let ret = unsafe {
            libc::ioctl(self.fd, KVM_RUN, 0)
        };

        if ret < 0 {
            anyhow::bail!("KVM_RUN failed");
        }

        // 读取 kvm_run 结构,判断退出原因
        let run = unsafe { &*self.run_mmap.unwrap() };
        let exit_reason = run.exit_reason;

        match exit_reason {
            KVM_EXIT_HLT => Ok(VmExit::Halt),
            KVM_EXIT_IO => {
                let io = unsafe { &run.__bindgen_anon_1.io };
                Ok(VmExit::IoOut {
                    port: io.port,
                    size: io.size,
                })
            }
            KVM_EXIT_MMIO => Ok(VmExit::Mmio),
            KVM_EXIT_SHUTDOWN => Ok(VmExit::Shutdown),
            _ => Ok(VmExit::Unknown(exit_reason)),
        }
    }
}

impl Drop for Vcpu {
    fn drop(&mut self) {
        if let Some(run_mmap) = self.run_mmap {
            unsafe {
                munmap(run_mmap as *mut _, 4096).ok();
            }
        }
        unsafe { libc::close(self.fd) };
    }
}

#[derive(Debug)]
pub enum VmExit {
    Halt,
    IoOut { port: u16, size: u8 },
    Mmio,
    Shutdown,
    Unknown(u32),
}

// KVM 常量和结构体
const KVM_GET_VCPU_MMAP_SIZE: libc::c_ulong = 0xAE04;
const KVM_RUN: libc::c_ulong = 0xAE80;
const KVM_SET_REGS: libc::c_ulong = 0x4090AE82;
const KVM_SET_SREGS: libc::c_ulong = 0x4138AE84;

const KVM_EXIT_HLT: u32 = 5;
const KVM_EXIT_IO: u32 = 2;
const KVM_EXIT_MMIO: u32 = 6;
const KVM_EXIT_SHUTDOWN: u32 = 8;

#[repr(C)]
pub struct kvm_run {
    pub exit_reason: u32,
    // ... 其他字段 (使用 bindgen 生成完整定义)
    pub __bindgen_anon_1: kvm_run__bindgen_ty_1,
}

#[repr(C)]
pub union kvm_run__bindgen_ty_1 {
    pub io: kvm_run_io,
    // ... 其他联合体成员
}

#[repr(C)]
pub struct kvm_run_io {
    pub direction: u8,
    pub size: u8,
    pub port: u16,
    pub count: u32,
    pub data_offset: u64,
}

#[repr(C)]
pub struct kvm_regs {
    pub rax: u64,
    pub rbx: u64,
    pub rcx: u64,
    pub rdx: u64,
    pub rsi: u64,
    pub rdi: u64,
    pub rsp: u64,
    pub rbp: u64,
    pub r8: u64,
    pub r9: u64,
    pub r10: u64,
    pub r11: u64,
    pub r12: u64,
    pub r13: u64,
    pub r14: u64,
    pub r15: u64,
    pub rip: u64,
    pub rflags: u64,
}

#[repr(C)]
pub struct kvm_sregs {
    // 段寄存器等 (使用 bindgen 生成)
    // ...
}
```

#### Step 3: 内存管理

**文件:** `src/memory.rs`

```rust
use anyhow::Result;
use nix::sys::mman::{mmap, munmap, MapFlags, ProtFlags};
use std::ptr;

pub struct GuestMemory {
    pub addr: *mut u8,
    pub size: usize,
}

impl GuestMemory {
    /// 分配 Guest 物理内存
    pub fn new(size: usize) -> Result<Self> {
        let addr = unsafe {
            mmap(
                ptr::null_mut(),
                size,
                ProtFlags::PROT_READ | ProtFlags::PROT_WRITE,
                MapFlags::MAP_PRIVATE | MapFlags::MAP_ANONYMOUS | MapFlags::MAP_NORESERVE,
                -1,
                0
            )?
        };

        log::info!("Allocated guest memory: addr={:p}, size={:#x}", addr, size);

        Ok(GuestMemory {
            addr: addr as *mut u8,
            size,
        })
    }

    /// 写入数据到 Guest 内存
    pub fn write(&self, offset: usize, data: &[u8]) -> Result<()> {
        if offset + data.len() > self.size {
            anyhow::bail!("Write beyond guest memory bounds");
        }

        unsafe {
            ptr::copy_nonoverlapping(
                data.as_ptr(),
                self.addr.add(offset),
                data.len()
            );
        }

        Ok(())
    }

    /// 从 Guest 内存读取数据
    pub fn read(&self, offset: usize, len: usize) -> Result<Vec<u8>> {
        if offset + len > self.size {
            anyhow::bail!("Read beyond guest memory bounds");
        }

        let mut buf = vec![0u8; len];
        unsafe {
            ptr::copy_nonoverlapping(
                self.addr.add(offset),
                buf.as_mut_ptr(),
                len
            );
        }

        Ok(buf)
    }

    /// 获取 Host 虚拟地址 (用于 KVM_SET_USER_MEMORY_REGION)
    pub fn as_ptr(&self) -> u64 {
        self.addr as u64
    }
}

impl Drop for GuestMemory {
    fn drop(&mut self) {
        unsafe {
            munmap(self.addr as *mut _, self.size).ok();
        }
    }
}
```

#### Step 4: Hello World 示例

**文件:** `src/main.rs`

```rust
mod kvm;
mod memory;

use anyhow::Result;
use kvm::{Kvm, VmExit};
use memory::GuestMemory;

fn main() -> Result<()> {
    env_logger::init();

    // 1. 打开 KVM
    let kvm = Kvm::new()?;
    println!("KVM API version: {}", kvm.get_api_version()?);

    // 2. 创建 VM
    let vm = kvm.create_vm()?;

    // 3. 分配 Guest 内存 (1MB)
    let mem_size = 1024 * 1024;
    let guest_mem = GuestMemory::new(mem_size)?;

    // 4. 设置内存映射
    vm.set_user_memory_region(
        0,                      // slot
        0x0,                    // guest_phys_addr
        mem_size as u64,        // memory_size
        guest_mem.as_ptr(),     // userspace_addr
    )?;

    // 5. 写入机器码到内存
    // x86_64 Real Mode 代码: 打印 'H' 然后 HLT
    let code: &[u8] = &[
        0xba, 0xf8, 0x03,  // mov dx, 0x3f8 (串口端口)
        0xb0, 0x48,        // mov al, 'H'
        0xee,              // out dx, al
        0xf4,              // hlt
    ];
    guest_mem.write(0x0, code)?;

    // 6. 创建 vCPU
    let mut vcpu = vm.create_vcpu(0)?;
    vcpu.init(kvm.fd)?;

    // 7. 设置寄存器 (从 0x0 开始执行)
    let mut regs = kvm::vcpu::kvm_regs {
        rip: 0x0,
        rflags: 0x2,  // 默认标志位
        ..Default::default()
    };
    vcpu.set_regs(&regs)?;

    // 8. 运行 vCPU
    println!("Running VM...");
    loop {
        match vcpu.run()? {
            VmExit::Halt => {
                println!("VM halted");
                break;
            }
            VmExit::IoOut { port, size } => {
                println!("I/O OUT: port={:#x}, size={}", port, size);
                // 读取输出数据 (从 kvm_run 结构)
            }
            VmExit::Shutdown => {
                println!("VM shutdown");
                break;
            }
            other => {
                println!("Unexpected VM exit: {:?}", other);
                break;
            }
        }
    }

    Ok(())
}
```

**运行:**
```bash
# 需要 root 权限访问 /dev/kvm
sudo cargo run

# 预期输出:
# KVM API version: 12
# Opened /dev/kvm, fd=3
# Created VM, fd=4
# Allocated guest memory: addr=0x7f..., size=0x100000
# Set memory region: slot=0, guest_phys=0x0, size=0x100000
# Created vCPU 0, fd=5
# vCPU 0 initialized, run_mmap=0x7f...
# Running VM...
# I/O OUT: port=0x3f8, size=1
# VM halted
```

### 2.2 改进: 使用现有 Crate

为了加速开发,推荐使用成熟的 Rust crate:

```toml
[dependencies]
kvm-bindings = "0.6"     # KVM 结构体和常量
kvm-ioctls = "0.15"      # KVM ioctl 封装
vm-memory = "0.12"       # Guest 内存管理
```

**使用 kvm-ioctls 重写:**

```rust
use kvm_ioctls::{Kvm, VmFd, VcpuFd};
use kvm_bindings::{kvm_userspace_memory_region, KVM_MEM_LOG_DIRTY_PAGES};
use vm_memory::{GuestAddress, GuestMemoryMmap, GuestMemoryRegion};

fn main() -> Result<()> {
    // 1. 打开 KVM
    let kvm = Kvm::new()?;

    // 2. 创建 VM
    let vm = kvm.create_vm()?;

    // 3. 创建 Guest 内存
    let mem_size = 1024 * 1024;
    let guest_addr = GuestAddress(0x0);
    let guest_mem = GuestMemoryMmap::from_ranges(&[(guest_addr, mem_size)])?;

    // 4. 设置内存区域
    let region = kvm_userspace_memory_region {
        slot: 0,
        flags: 0,
        guest_phys_addr: 0,
        memory_size: mem_size as u64,
        userspace_addr: guest_mem.get_host_address(guest_addr)? as u64,
    };
    unsafe { vm.set_user_memory_region(region)? };

    // 5. 写入代码
    let code: &[u8] = &[0xb0, 0x48, 0xf4];  // mov al, 'H'; hlt
    guest_mem.write_slice(code, guest_addr)?;

    // 6. 创建 vCPU
    let vcpu = vm.create_vcpu(0)?;

    // 7. 设置寄存器
    let mut regs = vcpu.get_regs()?;
    regs.rip = 0x0;
    regs.rflags = 0x2;
    vcpu.set_regs(&regs)?;

    // 8. 运行
    loop {
        match vcpu.run()? {
            VcpuExit::Hlt => break,
            VcpuExit::IoOut(port, data) => {
                println!("OUT {:#x}: {:?}", port, data);
            }
            exit => {
                println!("Exit: {:?}", exit);
                break;
            }
        }
    }

    Ok(())
}
```

---

## 第三阶段: 功能扩展 (6-8周)

### 3.1 Boot Linux Kernel

**目标:** 加载并启动真实的 Linux Kernel

#### A. Kernel 加载器

**文件:** `src/boot/linux.rs`

```rust
use anyhow::{Context, Result};
use std::fs::File;
use std::io::Read;
use vm_memory::{GuestAddress, GuestMemoryMmap};

const KERNEL_START: u64 = 0x100000;  // 1MB
const CMDLINE_START: u64 = 0x20000;  // 128KB

pub struct LinuxBootParams {
    pub kernel_path: String,
    pub initrd_path: Option<String>,
    pub cmdline: String,
}

pub fn load_kernel(
    guest_mem: &GuestMemoryMmap,
    params: &LinuxBootParams
) -> Result<u64> {
    // 1. 读取 Kernel 文件
    let mut kernel_file = File::open(&params.kernel_path)
        .context("Failed to open kernel")?;

    let mut kernel_data = Vec::new();
    kernel_file.read_to_end(&mut kernel_data)?;

    // 2. 写入 Kernel 到 Guest 内存
    guest_mem.write_slice(
        &kernel_data,
        GuestAddress(KERNEL_START)
    )?;

    log::info!("Loaded kernel: {} bytes at {:#x}",
        kernel_data.len(), KERNEL_START);

    // 3. 写入 Kernel 命令行
    let cmdline_bytes = params.cmdline.as_bytes();
    guest_mem.write_slice(
        cmdline_bytes,
        GuestAddress(CMDLINE_START)
    )?;

    // 4. 设置 Boot Params (x86_64 boot protocol)
    setup_boot_params(guest_mem, &params)?;

    Ok(KERNEL_START)
}

fn setup_boot_params(
    guest_mem: &GuestMemoryMmap,
    params: &LinuxBootParams
) -> Result<()> {
    // x86_64 boot protocol 需要设置 boot_params 结构
    // 参考: https://www.kernel.org/doc/html/latest/x86/boot.html

    const BOOT_PARAMS_START: u64 = 0x10000;  // 64KB

    // 简化版本: 仅设置必要字段
    // 完整实现需要参考 Linux boot protocol

    Ok(())
}
```

#### B. 支持 virtio 设备

**文件:** `src/devices/virtio/mod.rs`

```rust
// virtio 设备框架
pub trait VirtioDevice {
    fn device_type(&self) -> u32;
    fn queue_max_sizes(&self) -> &[u16];
    fn activate(&mut self, queues: Vec<Queue>) -> Result<()>;
    fn reset(&mut self);
}

// virtio-blk 实现
pub struct BlockDevice {
    disk_path: String,
    file: File,
}

impl VirtioDevice for BlockDevice {
    fn device_type(&self) -> u32 {
        VIRTIO_ID_BLOCK  // 2
    }

    fn queue_max_sizes(&self) -> &[u16] {
        &[256]  // 单队列,最多 256 个请求
    }

    fn activate(&mut self, queues: Vec<Queue>) -> Result<()> {
        // 启动 I/O 线程
        std::thread::spawn(move || {
            // 处理队列中的请求
        });
        Ok(())
    }

    fn reset(&mut self) {
        // 重置设备状态
    }
}
```

### 3.2 网络支持 (TAP 设备)

**文件:** `src/devices/net/tap.rs`

```rust
use nix::fcntl::{open, OFlag};
use nix::sys::stat::Mode;
use std::os::unix::io::RawFd;

pub struct Tap {
    fd: RawFd,
    if_name: String,
}

impl Tap {
    pub fn new(if_name: &str) -> Result<Self> {
        // 1. 打开 /dev/net/tun
        let fd = open(
            "/dev/net/tun",
            OFlag::O_RDWR | OFlag::O_NONBLOCK,
            Mode::empty()
        )?;

        // 2. 配置 TAP 设备
        let mut ifr = ifreq {
            ifr_name: [0; IFNAMSIZ],
            ifr_flags: IFF_TAP | IFF_NO_PI | IFF_VNET_HDR,
        };

        // 复制接口名
        for (i, byte) in if_name.as_bytes().iter().enumerate() {
            ifr.ifr_name[i] = *byte as i8;
        }

        // 3. TUNSETIFF ioctl
        unsafe {
            libc::ioctl(fd, TUNSETIFF, &ifr as *const _ as libc::c_ulong);
        }

        log::info!("Created TAP device: {}", if_name);

        Ok(Tap {
            fd,
            if_name: if_name.to_string(),
        })
    }

    pub fn read(&self, buf: &mut [u8]) -> Result<usize> {
        let n = nix::unistd::read(self.fd, buf)?;
        Ok(n)
    }

    pub fn write(&self, buf: &[u8]) -> Result<usize> {
        let n = nix::unistd::write(self.fd, buf)?;
        Ok(n)
    }
}

const TUNSETIFF: libc::c_ulong = 0x400454ca;
const IFF_TAP: i16 = 0x0002;
const IFF_NO_PI: i16 = 0x1000;
const IFF_VNET_HDR: i16 = 0x4000;
const IFNAMSIZ: usize = 16;

#[repr(C)]
struct ifreq {
    ifr_name: [i8; IFNAMSIZ],
    ifr_flags: i16,
}
```

### 3.3 API Server (HTTP/gRPC)

**文件:** `src/api/http.rs`

```rust
use axum::{
    extract::State,
    http::StatusCode,
    routing::{post, get},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::Mutex;

#[derive(Clone)]
struct AppState {
    vms: Arc<Mutex<HashMap<String, VmHandle>>>,
}

#[derive(Deserialize)]
struct CreateVmRequest {
    vm_id: String,
    vcpu_count: u32,
    memory_mb: u64,
    kernel_path: String,
    rootfs_path: String,
}

#[derive(Serialize)]
struct CreateVmResponse {
    vm_id: String,
    status: String,
}

async fn create_vm(
    State(state): State<AppState>,
    Json(req): Json<CreateVmRequest>,
) -> Result<Json<CreateVmResponse>, StatusCode> {
    // 创建 VM
    let vm = Vm::new(VmConfig {
        vcpu_count: req.vcpu_count,
        memory_mb: req.memory_mb,
        kernel_path: req.kernel_path,
        rootfs_path: req.rootfs_path,
    }).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;

    // 存储 VM Handle
    let mut vms = state.vms.lock().await;
    vms.insert(req.vm_id.clone(), vm);

    Ok(Json(CreateVmResponse {
        vm_id: req.vm_id,
        status: "created".to_string(),
    }))
}

#[tokio::main]
async fn main() {
    let state = AppState {
        vms: Arc::new(Mutex::new(HashMap::new())),
    };

    let app = Router::new()
        .route("/vms", post(create_vm))
        .route("/vms/:id", get(get_vm))
        .route("/vms/:id/start", post(start_vm))
        .route("/vms/:id/stop", post(stop_vm))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

---

## 第四阶段: 性能优化 (4-6周)

### 4.1 快照和恢复

```rust
pub struct Snapshot {
    pub memory: Vec<u8>,
    pub vcpu_states: Vec<VcpuState>,
    pub device_states: Vec<DeviceState>,
}

impl Vm {
    pub fn create_snapshot(&self) -> Result<Snapshot> {
        // 1. 暂停 VM
        self.pause()?;

        // 2. 保存内存
        let memory = self.guest_mem.as_slice().to_vec();

        // 3. 保存 vCPU 状态
        let vcpu_states = self.vcpus.iter()
            .map(|vcpu| vcpu.save_state())
            .collect::<Result<Vec<_>>>()?;

        // 4. 保存设备状态
        let device_states = self.devices.iter()
            .map(|dev| dev.save_state())
            .collect::<Result<Vec<_>>>()?;

        Ok(Snapshot {
            memory,
            vcpu_states,
            device_states,
        })
    }

    pub fn restore_from_snapshot(&mut self, snapshot: Snapshot) -> Result<()> {
        // 1. 恢复内存
        self.guest_mem.write_slice(&snapshot.memory, GuestAddress(0))?;

        // 2. 恢复 vCPU 状态
        for (vcpu, state) in self.vcpus.iter_mut().zip(snapshot.vcpu_states) {
            vcpu.restore_state(state)?;
        }

        // 3. 恢复设备状态
        for (device, state) in self.devices.iter_mut().zip(snapshot.device_states) {
            device.restore_state(state)?;
        }

        Ok(())
    }
}
```

### 4.2 多线程优化

```rust
use std::sync::Arc;
use std::thread;

pub struct VmRunner {
    vm: Arc<Vm>,
}

impl VmRunner {
    pub fn run_vcpu(vm: Arc<Vm>, vcpu_id: u32) {
        thread::spawn(move || {
            let vcpu = &vm.vcpus[vcpu_id as usize];

            loop {
                match vcpu.run() {
                    Ok(VmExit::Halt) => break,
                    Ok(VmExit::Io(io)) => {
                        vm.handle_io(&io);
                    }
                    Ok(VmExit::Mmio(mmio)) => {
                        vm.handle_mmio(&mmio);
                    }
                    Err(e) => {
                        log::error!("vCPU {} error: {}", vcpu_id, e);
                        break;
                    }
                }
            }
        });
    }

    pub fn run(&self) {
        for vcpu_id in 0..self.vm.config.vcpu_count {
            Self::run_vcpu(self.vm.clone(), vcpu_id);
        }
    }
}
```

---

## 第五阶段: Serverless 层 (6-8周)

### 5.1 函数运行时

```rust
pub struct FunctionRuntime {
    language: Language,
    handler: String,
}

pub enum Language {
    Python,
    JavaScript,
    Binary,
}

impl FunctionRuntime {
    pub fn prepare_vm(&self, function: &Function) -> Result<VmConfig> {
        let mut config = VmConfig::default();

        // 根据语言配置运行时
        match self.language {
            Language::Python => {
                config.rootfs_path = "/path/to/python-rootfs.ext4";
                config.cmdline = format!(
                    "console=ttyS0 init=/sbin/init function_handler={}",
                    self.handler
                );
            }
            Language::JavaScript => {
                config.rootfs_path = "/path/to/node-rootfs.ext4";
                // ...
            }
            Language::Binary => {
                // 直接运行二进制
            }
        }

        Ok(config)
    }
}
```

### 5.2 函数调度器

```rust
use tokio::sync::Semaphore;
use std::collections::HashMap;

pub struct Scheduler {
    // VM 池
    vm_pool: Arc<Mutex<VmPool>>,

    // 并发限制
    concurrency_limit: Arc<Semaphore>,

    // 函数到 VM 的映射
    function_vms: Arc<Mutex<HashMap<String, String>>>,
}

impl Scheduler {
    pub async fn invoke_function(
        &self,
        function_id: &str,
        payload: Vec<u8>
    ) -> Result<Vec<u8>> {
        // 1. 获取许可
        let _permit = self.concurrency_limit.acquire().await?;

        // 2. 查找或创建 VM
        let vm_id = self.get_or_create_vm(function_id).await?;

        // 3. 调用函数
        let result = self.invoke_in_vm(&vm_id, payload).await?;

        // 4. 如果空闲,scale to zero
        self.maybe_scale_to_zero(function_id).await?;

        Ok(result)
    }

    async fn get_or_create_vm(&self, function_id: &str) -> Result<String> {
        let mut function_vms = self.function_vms.lock().await;

        if let Some(vm_id) = function_vms.get(function_id) {
            // VM 已存在,唤醒
            self.vm_pool.lock().await.resume(vm_id)?;
            return Ok(vm_id.clone());
        }

        // 创建新 VM
        let vm_id = self.vm_pool.lock().await.create_vm(function_id)?;
        function_vms.insert(function_id.to_string(), vm_id.clone());

        Ok(vm_id)
    }
}
```

---

## 关键技术难点与解决方案

### 难点 1: KVM ioctl 绑定

**问题:** Rust 需要调用大量 KVM ioctl,手写绑定繁琐且易错

**解决方案:**
```bash
# 使用 bindgen 自动生成
cargo install bindgen-cli

# 生成 KVM 绑定
bindgen /usr/include/linux/kvm.h \
    --allowlist-type "kvm_.*" \
    --allowlist-var "KVM_.*" \
    --allowlist-function "kvm_.*" \
    > src/kvm_bindings.rs

# 或直接使用 kvm-bindings crate
```

### 难点 2: 内存安全

**问题:** 操作 Guest 内存涉及大量 unsafe 代码

**解决方案:**
```rust
// 使用 vm-memory crate 提供的安全抽象
use vm_memory::{GuestMemory, GuestAddress, Bytes};

// 安全的内存读写
guest_mem.read_obj::<u64>(GuestAddress(0x1000))?;
guest_mem.write_obj(value, GuestAddress(0x2000))?;

// 自动边界检查
```

### 难点 3: 设备模拟性能

**问题:** 每次 VM Exit 处理设备 I/O 开销大

**解决方案:**
```rust
// 1. 使用 vhost 卸载到内核
// 2. 使用 ioeventfd/irqfd 减少 Exit
use kvm_ioctls::IoEventAddress;

let ioeventfd = EventFd::new()?;
vm.register_ioevent(&ioeventfd, &IoEventAddress::Mmio(0x1000), 0)?;

// 3. 批量处理 I/O 请求
```

---

## 参考学习资源

### 开源项目
1. **Firecracker** - 学习极简设计
   - `src/vmm/src/builder.rs` - VM 构建流程
   - `src/vmm/src/device_manager` - 设备管理

2. **Cloud Hypervisor** - 学习完整功能
   - `vmm/src/vm.rs` - VM 生命周期
   - `vmm/src/cpu.rs` - vCPU 管理

3. **crosvm** (Google) - 学习 Rust 最佳实践
   - 代码质量高,注释完善

### 文档
- [Using the KVM API](https://lwn.net/Articles/658511/)
- [Linux KVM Documentation](https://www.kernel.org/doc/html/latest/virt/kvm/index.html)
- [x86 Boot Protocol](https://www.kernel.org/doc/html/latest/x86/boot.html)

### Crates
- `kvm-ioctls` - KVM 封装
- `vm-memory` - Guest 内存管理
- `virtio-queue` - virtio 队列实现
- `vm-device` - 设备模型抽象

---

## 项目时间线

| 阶段 | 时间 | 里程碑 | 验收标准 |
|-----|------|--------|---------|
| **阶段 1** | 2-4周 | 知识准备 | 能读懂 Firecracker 核心代码 |
| **阶段 2** | 4-6周 | 最小 VMM | 能运行简单机器码 |
| **阶段 3** | 6-8周 | Boot Linux | 能启动 Linux Kernel |
| **阶段 4** | 4-6周 | 性能优化 | 启动时间 <500ms |
| **阶段 5** | 6-8周 | Serverless | 能运行函数并 scale to zero |

**总计: 22-32 周 (5-8 个月)**

---

## 下一步行动

1. **立即开始:**
   ```bash
   # 克隆参考项目
   git clone https://github.com/firecracker-microvm/firecracker
   git clone https://github.com/cloud-hypervisor/cloud-hypervisor

   # 阅读核心代码
   cd firecracker/src/vmm
   ```

2. **建立学习笔记:**
   - 记录 KVM API 使用方法
   - 整理 Firecracker 架构图
   - 总结常见坑点

3. **循序渐进:**
   - 不要跳过阶段 1 (知识准备)
   - 从最小示例开始,逐步添加功能
   - 每个阶段都要有可运行的 demo

祝您开发顺利！🚀
