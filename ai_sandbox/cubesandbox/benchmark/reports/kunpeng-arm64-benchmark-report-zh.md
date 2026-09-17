# CubeSandbox ARM64 性能测试报告

本文记录 CubeSandbox 在 ARM64 单节点部署环境下的核心操作性能。测试覆盖模板准备、Sandbox 创建性能、常驻密度和内存增量统计；Snapshot、Rollback、Clone、Pause/Resume 等能力需在支持 v0.3.0 能力的部署版本上另行测试。

## 1. 测试概览

本次测试使用 ARM64 Ubuntu 22.04 模板，Sandbox 规格为 2 vCPU / 2 GiB，writable layer 为 1G。测试通过 CubeAPI 创建 Sandbox，并使用 `cube-bench` 执行并发创建和常驻密度验证。

主要结论：

| 项目 | 结果 |
|---|---:|
| 最高创建吞吐 | 154.12 sandboxes/s |
| 并发 50、500 次创建成功率 | 100.0% |
| 并发 50、500 次创建 P95 | 1322.3 ms |
| 100 常驻密度成功率 | 100.0% |
| 300 常驻密度成功率 | 100.0% |
| 300 常驻时单 Sandbox used 内存增量 | 6.58 MiB |
| 300 常驻时 Sandbox 总 used 内存占比 | 0.194% |

## 2. 测试环境

### 2.1 基础环境

| 项目 | 配置 |
|---|---|
| 部署形态 | CubeSandbox 单节点部署 |
| 架构 | ARM64 |
| CPU 资源 | 高规格多核 ARM64 服务器 |
| 内存资源 | 约 1 TiB |
| KVM | 已启用 |
| 容器运行时 | Docker / containerd |

### 2.2 存储条件

CubeSandbox 数据目录使用 XFS 文件系统。由于本次测试环境的数据盘容量有限，密度测试覆盖 100 和 300 常驻档位；更高规模的密度测试建议在大容量 XFS 数据盘环境下执行。

## 3. 模板准备和冒烟验证

正式测试模板使用 ARM64 Ubuntu 22.04 镜像构建，规格保持为 2 vCPU / 2 GiB / 1G writable layer。

模板规格：

| 项目 | 值 |
|---|---|
| 镜像 | Ubuntu 22.04 |
| 镜像架构 | arm64/linux |
| CPU | 2 vCPU |
| 内存 | 2 GiB |
| writable layer | 1G |
| 网络类型 | tap |

冒烟验证通过：创建 Sandbox 后，返回规格符合预期，Sandbox 可正常删除。

## 4. 基于模板创建 Sandbox

测试命令模板：

```bash
cube-bench \
  --api-url <cubeapi-url> \
  --api-key <api-key> \
  --template <template-id> \
  --concurrency <C> \
  --total <N> \
  --warmup 3 \
  --mode create-only \
  --no-tui \
  --output <result.json>
```

### 4.1 测试结果

| 并发 | 请求数 | 成功/失败 | 成功率 | 墙钟均摊 | 吞吐 | Avg | Min | P50 | P95 | P99 | Max |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 20/0 | 100.0% | 42.48 ms | 23.54/s | 38.3 ms | 22.0 ms | 27.0 ms | 40.6 ms | 227.5 ms | 227.5 ms |
| 10 | 200 | 200/0 | 100.0% | 6.49 ms | 154.12/s | 59.5 ms | 28.7 ms | 53.5 ms | 105.8 ms | 114.5 ms | 122.2 ms |
| 20 | 300 | 300/0 | 100.0% | 8.38 ms | 119.36/s | 155.9 ms | 30.9 ms | 148.9 ms | 299.2 ms | 317.8 ms | 325.4 ms |
| 50 | 500 | 500/0 | 100.0% | 14.74 ms | 67.84/s | 668.4 ms | 30.2 ms | 653.7 ms | 1322.3 ms | 1492.4 ms | 1578.6 ms |

### 4.2 结果分析

并发 10 是本轮最高吞吐点，达到 `154.12 sandboxes/s`。并发提高到 20 后，平均创建延迟升至 `155.9 ms`，吞吐下降到 `119.36/s`。并发 50 可以达到 `500/500` 成功，但 P95 为 `1322.3 ms`，尾延迟明显高于低并发档位。

## 5. Sandbox 密度验证

### 5.1 测试方法

密度测试使用 `create-only` 模式创建常驻 Sandbox。每轮测试前清空已有 Sandbox，创建后采集内存和存储指标，再清理全部 Sandbox。`cube-bench` 的 3 个 warmup Sandbox 在 `create-only` 模式下也会保留，因此常驻数为 `请求成功数 + 3`。

内存统计使用“创建后 - 创建前”的差分，测试前已有的系统服务和 CubeSandbox 控制面组件不会计入 Sandbox 增量。表中的“占整机内存”使用 `used_delta / MemTotal` 计算。

命令模板：

```bash
cube-bench \
  --api-url <cubeapi-url> \
  --api-key <api-key> \
  --template <template-id> \
  --concurrency 50 \
  --total <100|300> \
  --warmup 3 \
  --mode create-only \
  --no-tui \
  --output <result.json>
```

### 5.2 密度结果

| 请求数 | 成功/失败 | 成功率 | 常驻 Sandbox | 吞吐 | Avg | P95 | Max | used 增量 | 单 Sandbox used 增量 | 占整机内存 | 数据目录增量 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 100/0 | 100.0% | 103 | 259.86/s | 122.1 ms | 158.2 ms | 173.3 ms | 550.9 MiB | 5.35 MiB | 0.053% | 15.7 MiB |
| 300 | 300/0 | 100.0% | 303 | 115.44/s | 375.4 ms | 693.9 ms | 802.0 ms | 1993.8 MiB | 6.58 MiB | 0.194% | 46.2 MiB |

100 和 300 常驻档位均达到 100% 成功率。随着常驻数增加，单 Sandbox used 内存增量从 `5.35 MiB` 上升到 `6.58 MiB`，整体占 1.0 TiB 内存的比例仍低于 `0.2%`。

## 6. Snapshot / Rollback / Clone / Pause-Resume

Snapshot、Rollback、Clone、Pause/Resume 属于 CubeSandbox v0.3.0 相关能力。本次 ARM64 环境使用的部署版本未包含这些能力所需的完整实现，因此本报告不提供相关性能数据。待 ARM64 环境部署支持 v0.3.0 能力的版本后，可补充以下测试：

| 能力 | 建议测试内容 |
|---|---|
| Snapshot | Snapshot 创建延迟、并发 Snapshot、脏页量对 Snapshot 的影响 |
| 从 Snapshot 创建 | 不同并发下从 Snapshot 创建 Sandbox 的耗时 |
| Rollback | 并发 Rollback 延迟和成功率 |
| Clone | 单源多副本 Clone 的吞吐和延迟 |
| Pause/Resume | 并发 Pause/Resume 延迟和状态收敛 |
