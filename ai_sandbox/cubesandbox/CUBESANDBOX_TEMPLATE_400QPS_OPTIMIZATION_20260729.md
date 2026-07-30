# CubeSandbox Template c50n500 吞吐优化报告

## 测试条件

- 节点：`root@192.168.25.90`
- Template：`tpl-124b2a544a564576bc5c1c1b`
- OCI rootfs：`rfs-697ade2113e1f97ffe5d63e4`
- OCI 镜像：`127.0.0.1:5000/cubesandbox-bench/sandbox-code-envd-ci:arm64-slim-mmds-prime-native-code-v3`
- 规格：2U2G，writable layer 1G
- 压测：Template create-only，`c50n500`，每轮 3 次 warmup
- 资源门禁：每轮前后均要求 0 sandbox、0 shim、0 task、1000 TAP 且 0 TAP in-use
- Cubelet：原始 SHA256 `486688ed1da44d3d9ee861a3734c106e65719d41bfd30ea3f649f0cbfdc4ebc1`
- 最终 CubeShim：SHA256 `d817464d334bc174a9a804016ef0d2c4eff199292ef7c3bcd40feb71ee3a98a0`

## 瓶颈与改动

Snapshot restore 已经建立 guest-agent 控制连接，但原路径仍在 `task.Start` 中同步建立第二条 vsock 连接用于 init 日志转发。最终实现仅在 Snapshot restore 时复用已有连接；冷启动仍保留独立日志连接。

此外，restore 的 `CreateContainer` RPC 会启动 guest 子进程进入容器 mount namespace。当 OCI spec 同时缺少 `cube.propagation.exec.mounts` 和 `cube.propagation.container.umounts` 时，该子进程不执行任何挂载或卸载。最终实现只在这个严格条件下省略空 RPC；任一传播配置存在时仍执行原路径。

关键阶段变化：

| 阶段 | 优化前 | 优化后 |
|---|---:|---:|
| `task.Start - sandbox-create` avg | 35.28 ms | 0.95 ms |
| `task.Start - sandbox-create` p95 | 196.23 ms | 2.57 ms |
| CubeShim `CreateContainer` avg | 19.09 ms | 0.08 ms |
| CubeShim `CreateContainer` p95 | 152 ms | 1 ms |

## c50n500 结果

| 轮次 | 成功/总数 | Avg latency | P95 | Max | Total time | Throughput |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 500/500 | 76.510 ms | 129.528 ms | 187.847 ms | 0.9816 s | 509.37/s |
| 2 | 500/500 | 78.922 ms | 145.344 ms | 181.057 ms | 0.9987 s | 500.63/s |
| 3 | 500/500 | 80.366 ms | 135.301 ms | 187.221 ms | 1.0064 s | 496.80/s |
| 平均 | 1500/1500 | 78.599 ms | 136.724 ms | - | 0.9956 s | 502.93/s |

三轮最低吞吐为 496.80/s，均超过 400/s 目标。

## 功能与清理验证

- c1n20：20/20，avg 29.184 ms，p95 30.077 ms。
- 串行创建后立即执行代码：10/10 正确，10/10 删除成功。
- c20n100 创建后立即执行代码：100/100 正确，100/100 删除成功。
- 三轮 c50n500 均无创建错误、无 reset/guest timeout。
- 最终状态：0 sandbox、0 shim、0 task、1000 TAP、0 TAP in-use；Cubelet 和 network-agent active。

并发 `run_code` 的执行耗时仍有约 0.1-6.1 秒波动，但所有结果正确。该指标不计入 create-only 吞吐，可作为后续独立优化项。

## 归档与回退

远端完整归档目录：

`/home/lyq/cubesandbox-template-400qps-20260729/shim-reuse-log-conn-candidate`

原始 CubeShim：

`containerd-shim-cube-rs.original-deployed`

最终 CubeShim：

`containerd-shim-cube-rs.reuse-log-skip-empty-restore`

最终源码和补丁：

- `container.mod.rs.reuse-log-skip-empty-restore`
- `container-reuse-log-skip-empty-restore.patch`

在无活动 sandbox/shim 时，可将原始 CubeShim 安装回：

`/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs`
