# Nydus 项目架构设计分析

## 一、项目概述

Nydus 是 Dragonfly 开源的容器镜像服务，实现了基于 **RAFS (Reduced Advanced File System)** 格式的内容寻址文件系统。它通过**按需加载**、**块级去重**等技术，显著提升容器启动速度和资源利用效率。

**核心价值：**
- 秒级容器冷启动
- 毫秒级函数计算代码包加载
- 端到端数据完整性验证
- 节省存储、网络、内存资源

---

## 二、整体架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                   应用层 (Container/VM)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  文件系统接口层                               │
│            FUSE / Virtio-fs / EROFS-fscache                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   nydusd 守护进程层                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      服务管理层 (nydus-service)                       │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      RAFS 文件系统层 (nydus-rafs)                     │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │      存储抽象层 (nydus-storage)                       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│               存储后端 (Backends)                            │
│    Registry / OSS / S3 / Local Disk / HTTP Proxy            │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、核心模块设计

### 1. RAFS 模块 (`/rafs`)

**职责：** 实现 RAFS 文件系统格式

**关键组件：**
- **元数据管理** (`metadata/`)
  - `direct_v5.rs` - RAFS v5 直接映射（FUSE）
  - `direct_v6.rs` - RAFS v6 直接映射（EROFS 兼容）
  - `cached_v5.rs` - v5 缓存元数据实现
  - `inode.rs` - Inode 管理
  - `chunk.rs` - 数据块信息处理

- **磁盘格式** (`metadata/layout/`)
  - `v5.rs` - RAFS v5 布局结构
  - `v6.rs` - RAFS v6 布局（EROFS 兼容）

**RAFS 镜像结构：**
```
Bootstrap (元数据 Blob)
├── SuperBlock (前 8K)
├── Inode 表
├── Prefetch 表（可选）
├── Blob 表
├── Inode 节点（目录/文件元数据）
└── Chunk 信息（文件数据块）

Data Blob (数据 Blob)
└── 压缩的数据块
```

### 2. Storage 模块 (`/storage`)

**职责：** 核心存储子系统，处理从各后端获取 Blob 对象

**关键组件：**
- **设备管理** - `device.rs`, `factory.rs`
- **后端实现** (`backend/`)
  - `registry.rs` - 容器镜像仓库
  - `oss.rs` - 阿里云 OSS
  - `s3.rs` - AWS S3 兼容存储
  - `localfs.rs` - 本地文件系统
  - `localdisk.rs` - 本地磁盘（支持 GPT）
  - `http_proxy.rs` - HTTP 代理

- **缓存实现** (`cache/`)
  - `fscache/` - Linux fscache 后端
  - `filecache/` - 文件缓存
  - `dedup/` - 块级去重支持

**核心特性：**
- 按需块获取
- 多策略缓存
- 跨层/跨镜像块去重
- 压缩/非压缩块支持
- 完整性验证（SHA256, BLAKE3）

### 3. Service 模块 (`/service`)

**职责：** 服务管理器，创建和管理 Nydus 守护进程

**关键组件：**
- `daemon.rs` - 守护进程控制器
- `fusedev.rs` - FUSE 设备服务
- `fs_service.rs` - 文件系统服务抽象
- `blob_cache.rs` - Blob 缓存管理
- `block_device.rs` - 块设备支持
- `block_nbd.rs` - NBD（网络块设备）支持
- `upgrade.rs` - 热升级机制

**服务类型：**
- FUSE 服务
- Virtio-fs 服务（VM 容器）
- Fscache 服务（内核 EROFS）
- Blobcache 服务

### 4. Builder 模块 (`/builder`)

**职责：** 从各种源构建 RAFS 文件系统

**关键组件：**
- `core/` - 核心构建功能
  - `context.rs` - 构建上下文
  - `tree.rs` - 文件树表示
  - `node.rs` - 文件/目录节点
- `tarball.rs` - Tarball 转换
- `stargz.rs` - Stargz 镜像支持
- `merge.rs` - 合并多层 RAFS
- `compact.rs` - Blob 压缩

**支持格式：**
- Native 模式 - 完整 RAFS 格式
- Zran 模式 - OCIv1 兼容懒加载
- Tarfs 模式 - 简单 tar.gz/tar.zst 格式

### 5. API 模块 (`/api`)

**职责：** 配置和 API 定义

**关键组件：**
- `config.rs` - 配置结构定义
- `http_endpoint_v1.rs` / `v2.rs` - HTTP API 端点
- `http_handler.rs` - HTTP 请求处理

---

## 四、主要可执行程序

### 1. nydusd (`/src/bin/nydusd`)

**职责：** 主守护进程，处理文件系统请求

**功能：**
- 处理来自内核的 FUSE/fscache 消息
- 解析 Nydus 镜像满足请求
- 管理多个文件系统实例
- 提供 HTTP API 用于控制和监控
- 支持热升级

**支持协议：**
- FUSE（用户态）
- Virtio-fs（VM 容器）
- EROFS/fscache（内核态）

### 2. nydus-image (`/src/bin/nydus-image`)

**职责：** 构建 RAFS 文件系统的 CLI 工具

**主要命令：**
- `create` - 从 tarball 或目录构建 RAFS
- `check` - 验证 RAFS 文件系统
- `inspect` - 检查 RAFS 元数据
- `export` - 导出 RAFS 到目录
- `merge` - 合并多个 RAFS 层
- `compact` - 压缩 Blob 数据

### 3. nydusctl (`/src/bin/nydusctl`)

**职责：** 控制 nydusd 守护进程的 CLI 客户端

**命令：**
- `info` - 获取守护进程信息
- `metrics` - 获取运行时指标
- `mount/umount` - 挂载/卸载文件系统
- `set` - 配置守护进程参数

---

## 五、关键技术特性

### 1. 按需加载

```
容器启动
    │
    ▼
┌──────────────┐
│  应用访问文件  │
└──────────────┘
    │
    ▼
┌──────────────┐
│ 内核发送请求  │
│ (FUSE/fscache)│
└──────────────┘
    │
    ▼
┌──────────────┐
│ nydusd 查找  │
│ 块信息       │
└──────────────┘
    │
    ▼
┌──────────────┐
│ 检查缓存     │
│ (命中/未命中) │
└──────────────┘
    │
    ├─ 命中 → 直接返回
    │
    ▼ 未命中
┌──────────────┐
│ 从后端获取   │
│ 仅请求的块   │
└──────────────┘
    │
    ▼
┌──────────────┐
│ 返回给应用   │
└──────────────┘
```

**优势：**
- 块级粒度（默认 1MB）
- 仅下载访问的数据
- 对应用透明

### 2. 块级去重

```
Layer 1: [Chunk A][Chunk B][Chunk C]
Layer 2: [Chunk B][Chunk D][Chunk E]  ← Chunk B 不重复存储
Layer 3: [Chunk A][Chunk C][Chunk F]  ← Chunk A/C 不重复存储

存储后：
Blob: [Chunk A][Chunk B][Chunk C][Chunk D][Chunk E][Chunk F]
索引数据库：记录每个块的引用关系
```

**实现：**
- 内容寻址存储（哈希标识）
- 跨层/跨镜像去重
- SQLite 数据库跟踪重复块

### 3. 完整性验证

```
┌──────────────┐
│  Bootstrap   │
│  (元数据)     │
└──────────────┘
      │
      │ 包含
      ▼
┌──────────────┐
│ Inode Digest │ ← 文件元数据哈希
│ Chunk Digest │ ← 每个块的哈希
└──────────────┘
      │
      │ 验证
      ▼
┌──────────────┐
│  Data Blob   │
│  (实际数据)   │
└──────────────┘
```

**支持算法：**
- SHA256
- BLAKE3（更高性能）

### 4. 预取优化

```
Bootstrap 中包含预取提示
    │
    ▼
┌──────────────┐
│ 容器启动时   │
│ 后台预取     │
│ 关键文件     │
└──────────────┘
    │
    ▼
减少启动时的按需获取延迟
```

### 5. 压缩支持

**算法：**
- LZ4（快速解压）
- ZSTD（高压缩比）
- GZIP（兼容性）

**策略：**
- 逐块压缩
- 透明解压

---

## 六、文件系统实现对比

| 特性 | FUSE | EROFS/fscache | Virtio-fs |
|------|------|---------------|-----------|
| **内核版本要求** | 通用 | Linux 5.16+ (v6)<br>Linux 5.19+ (fscache) | 通用 |
| **性能** | 中等 | 高（内核态） | 高（共享内存） |
| **使用场景** | runC 容器 | 高性能容器 | Kata Containers |
| **RAFS 版本** | v5, v6 | v6 | v5, v6 |
| **实现位置** | `/service/fusedev.rs` | `/docs/nydus-fscache.md` | `/service/` |

---

## 七、存储后端架构

### 后端抽象

```rust
trait BlobBackend {
    fn read(&self, blob_id: &str) -> Result<BlobReader>;
    fn read_offset(&self, blob_id: &str, offset: u64, size: u64) -> Result<Vec<u8>>;
}
```

### 支持的后端

| 后端类型 | 实现文件 | 特性 |
|---------|---------|------|
| **Registry** | `backend/registry.rs` | Docker/OCI 兼容仓库<br>Token 认证<br>Manifest 解析 |
| **OSS** | `backend/oss.rs` | 阿里云对象存储<br>密钥认证 |
| **S3** | `backend/s3.rs` | AWS S3 兼容存储<br>分段上传 |
| **LocalFS** | `backend/localfs.rs` | 本地文件系统 |
| **LocalDisk** | `backend/localdisk.rs` | 本地磁盘 + GPT 分区 |
| **HTTP Proxy** | `backend/http_proxy.rs` | HTTP 代理本地目录 |

---

## 八、缓存架构

### 1. BlobCache

```
┌──────────────────┐
│ 工作目录         │
└──────────────────┘
        │
        ├── /cache/blob1.data
        ├── /cache/blob2.data
        └── /cache/blob3.data

特点：
- 文件级缓存
- 无淘汰策略
- 元数据驱动
```

### 2. FsCache（内核集成）

```
┌──────────────────┐
│ Linux 内核       │
│ fscache 子系统   │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│ nydusd 提供数据  │
│ (按需)           │
└──────────────────┘

特点：
- 内核级缓存
- 性能更优
- EROFS 集成
```

### 3. Dedup Cache

```
┌──────────────────┐
│ SQLite 数据库    │
└──────────────────┘
        │
        ├── 块哈希 → Blob 位置
        ├── 引用计数
        └── 跨 Blob 去重映射

特点：
- 块级跟踪
- 跨 Blob 去重
- 共享缓存存储
```

---

## 九、容器运行时集成

### 1. Containerd

```
┌──────────────────┐
│   Containerd     │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│ nydus-snapshotter│ (远程快照器插件)
└──────────────────┘
        │
        ├── 管理 Nydus 镜像
        ├── 启动 nydusd
        └── 准备容器 rootfs
```

### 2. Kubernetes

```
┌──────────────────┐
│   Kubelet        │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│   CRI            │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│ Containerd +     │
│ nydus-snapshotter│
└──────────────────┘
        │
        ▼
┌──────────────────┐
│   Nydus 镜像      │
└──────────────────┘
```

### 3. Kata Containers

```
┌──────────────────┐
│   Kata Runtime   │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  Guest VM        │
│  ┌────────────┐  │
│  │ nydusd     │  │ ← Virtio-fs
│  │ (Virtio-fs)│  │
│  └────────────┘  │
└──────────────────┘
```

---

## 十、配置系统

### 配置结构（`/api/src/config.rs`）

```json
{
  "device": {
    "backend": {
      "type": "registry",
      "config": {
        "scheme": "https",
        "host": "registry.example.com",
        "repo": "library/nginx"
      }
    },
    "cache": {
      "type": "fscache",
      "compressed": true
    }
  },
  "mode": "direct",
  "digest_validate": true,
  "iostats_files": true,
  "enable_xattr": true,
  "fs_prefetch": {
    "enable": true,
    "prefetch_all": false,
    "threads_count": 4
  }
}
```

---

## 十一、生态集成

| 集成类型 | 项目 | 状态 | 说明 |
|---------|------|------|------|
| **构建** | Buildkit | ✅ | 直接从 Dockerfile 构建 Nydus 镜像 |
| **构建/运行** | Nerdctl | ✅ | Containerd 客户端，支持构建和运行 |
| **运行** | Docker/Moby | ✅ | 通过 containerd + nydus-snapshotter |
| **运行** | Kubernetes | ✅ | CRI 接口 |
| **运行** | Kata Containers | ✅ | 原生支持 |
| **分发** | Dragonfly | ✅ | P2P 分发，降低延迟 80%+ |
| **仓库** | Harbor | ✅ | 加速服务 |

---

## 十二、关键设计亮点

1. **分层清晰**：服务层 → RAFS 层 → 存储层，职责明确
2. **多协议支持**：FUSE、EROFS/fscache、Virtio-fs，适应不同场景
3. **存储抽象**：统一的 BlobBackend trait，支持多种后端
4. **性能优化**：按需加载、预取、缓存、去重多层优化
5. **安全保证**：端到端完整性验证，防供应链攻击
6. **灵活部署**：支持裸机、容器、VM 等多种环境
7. **生态兼容**：完全兼容 OCI 标准，无缝集成现有工具链

---

## 总结

Nydus 采用模块化的 Rust 工作区架构，通过 RAFS 格式实现了高性能的容器镜像服务。其核心优势在于：

- **按需加载**机制显著减少启动时间和资源消耗
- **块级去重**技术优化存储和网络传输
- **多后端支持**提供灵活的存储选择
- **内核级集成**（EROFS/fscache）提供极致性能
- **完整的生态系统**集成主流容器运行时和构建工具

代码组织清晰，文档完善，是一个设计优秀的云原生镜像服务实现。
