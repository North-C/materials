# CubeShim 优化版本迁移文档

本文按“将当前优化版 CubeShim 迁移到其他服务器”编写。如果目标是将改动迁移到其他源码分支，参考“源码迁移”章节。

## 1. 当前制品

源服务器：`root@192.168.25.90`

```text
归档目录：
/home/lyq/cubesandbox-template-400qps-20260729/shim-reuse-log-conn-candidate

优化二进制：
containerd-shim-cube-rs.reuse-log-skip-empty-restore

目标安装路径：
/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs

优化版 SHA256：
d817464d334bc174a9a804016ef0d2c4eff199292ef7c3bcd40feb71ee3a98a0
```

该二进制为 ARM64 ELF，实际最高要求 `GLIBC_2.29`，依赖 `libcap-ng.so.0`。原始基线为 CubeSandbox v0.5.1，提交 `a164417f497234a0d787cb328b0ae96480b1569b`。

## 2. 优化内容

改动仅位于：

```text
CubeShim/shim/src/container/mod.rs
```

包含两项优化：

1. Snapshot restore 时复用已经建立的 guest-agent 连接进行 init 日志转发，避免同步建立第二条 vsock 连接。
2. Snapshot restore 且 OCI spec 同时不存在以下 annotation 时，省略无实际工作的 `CreateContainer` RPC：

```text
cube.propagation.exec.mounts
cube.propagation.container.umounts
```

冷启动路径，以及包含任一传播 annotation 的 restore 路径保持原行为。

## 3. 迁移前提

直接复制二进制仅适用于：

- 目标节点为 `aarch64`。
- 目标节点 GLIBC 不低于 2.29。
- 存在 `libcap-ng.so.0`。
- CubeSandbox/CubeShim 基线与 v0.5.1 `a164417f` 相同或已经验证协议兼容。
- CubeShim 与 guest `cube-agent` 使用兼容的 ttrpc/protobuf 定义。

检查命令：

```bash
uname -m
getconf GNU_LIBC_VERSION
ldconfig -p | grep 'libcap-ng.so.0'
/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs --version
```

如果版本不同，建议使用第 8 节的源码迁移方式重新编译。

## 4. 复制制品

在目标服务器执行：

```bash
install -d -m 0755 /var/tmp/cubeshim-migration-20260729

scp root@192.168.25.90:/home/lyq/cubesandbox-template-400qps-20260729/shim-reuse-log-conn-candidate/containerd-shim-cube-rs.reuse-log-skip-empty-restore \
  /var/tmp/cubeshim-migration-20260729/containerd-shim-cube-rs.optimized

sha256sum /var/tmp/cubeshim-migration-20260729/containerd-shim-cube-rs.optimized
file /var/tmp/cubeshim-migration-20260729/containerd-shim-cube-rs.optimized
ldd /var/tmp/cubeshim-migration-20260729/containerd-shim-cube-rs.optimized
```

必须确认 SHA256 为：

```text
d817464d334bc174a9a804016ef0d2c4eff199292ef7c3bcd40feb71ee3a98a0
```

`ldd` 输出中不能出现 `not found`。

## 5. 排空节点

先从调度侧禁止新请求进入该计算节点，然后确认：

```bash
curl -fsS -H 'Authorization: Bearer e2b_000000' \
  http://127.0.0.1:3000/sandboxes | jq 'length'

ps -eo pid=,args= |
  awk '$2 == "/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs"'

find /data/cubelet/root/io.containerd.runtime.v2.task \
  -mindepth 2 -maxdepth 2 -type d 2>/dev/null | wc -l
```

三项必须分别为：

```text
sandbox = 0
CubeShim 进程 = 0
task 目录 = 0
```

不要在仍有活动沙箱时替换 CubeShim。Template/Snapshot 本身不包含宿主机 CubeShim，因此无需重建 Template；替换只影响之后新启动的 shim。

## 6. 安装

```bash
systemctl stop cube-sandbox-cubelet.service

LIVE=/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
BACKUP="${LIVE}.pre-optimized-$(date +%Y%m%d-%H%M%S)"

cp -a "$LIVE" "$BACKUP"
sha256sum "$LIVE" "$BACKUP"

install -o root -g root -m 0755 \
  /var/tmp/cubeshim-migration-20260729/containerd-shim-cube-rs.optimized \
  "${LIVE}.new"

sha256sum "${LIVE}.new"
mv "${LIVE}.new" "$LIVE"
sync

systemctl start cube-sandbox-cubelet.service
systemctl is-active cube-sandbox-cubelet.service
sha256sum "$LIVE"
curl -fsS http://127.0.0.1:3000/cubeapi/v1/health
```

优化版通过直接构建生成，`--version` 可能显示 `0.0.0-dev`；迁移验收应以 SHA256 为准。

## 7. 验证

先进行功能门禁：

```bash
export E2B_API_URL=http://127.0.0.1:3000
export E2B_API_KEY=e2b_000000
export CUBE_TEMPLATE_ID=<目标节点Template-ID>

./bin/cube-bench -c 1 -n 20 -w 3 -m create-only -o cubeshim-c1n20.json
```

验收条件：

- `20/20` 创建成功。
- 创建后能够正常执行代码。
- 删除后 sandbox、shim、task 均为 0。
- 日志不存在 `guest timeout`、`Receive packet timeout`、`reset guest failed`。
- 带有上述传播 annotation 的场景也能正常创建。

相关日志：

```text
/data/log/CubeShim/cube-shim-req.log
/data/log/CubeShim/cube-shim-stat.log
/data/log/Cubelet/
```

功能验证后再进行 `c50n500`，不要直接以高并发作为第一轮验证。

## 8. 源码迁移

补丁位于：

```text
/home/lyq/cubesandbox-template-400qps-20260729/shim-reuse-log-conn-candidate/container-reuse-log-skip-empty-restore.patch
```

其 SHA256 为：

```text
ac7280b2ea715a7b884b3e94d031740170f9770d34842cae2473071bd211a848
```

在目标源码仓库执行：

```bash
git apply --check container-reuse-log-skip-empty-restore.patch
git apply container-reuse-log-skip-empty-restore.patch

cd CubeShim
cargo fmt --check
cargo test --workspace --locked
cargo build --release --locked
```

产物为：

```text
CubeShim/target/release/containerd-shim-cube-rs
```

如果补丁不能直接应用，应手工移植两处逻辑，不能简单删除所有 restore `CreateContainer` 调用。必须保留“存在任一 propagation annotation 时继续调用 RPC”的保护条件。

## 9. 回滚

出现功能异常时，重新排空节点，然后执行：

```bash
systemctl stop cube-sandbox-cubelet.service
install -o root -g root -m 0755 <第6节生成的BACKUP文件> \
  /usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs
sync
systemctl start cube-sandbox-cubelet.service
```

随后重新检查服务健康、二进制 SHA、沙箱创建和代码执行。

## 10. 完整性能环境

要复现 `.90` 上约 `502.93 sandbox/s` 的整体性能，仅迁移 CubeShim 不够，还需要对齐：

- v3 OCI 镜像和 MMDS-prime。
- Cubelet early probe。
- 2U2G Template 和 1G writable layer。
- 1000 个 TAP 资源。
- guest kernel、guest image 和宿主机硬件条件。

当前性能测试使用：

```text
Template：tpl-124b2a544a564576bc5c1c1b
OCI rootfs：rfs-697ade2113e1f97ffe5d63e4
OCI 镜像：127.0.0.1:5000/cubesandbox-bench/sandbox-code-envd-ci:arm64-slim-mmds-prime-native-code-v3
```

详细性能数据参见仓库根目录的 `CUBESANDBOX_TEMPLATE_400QPS_OPTIMIZATION_20260729.md`。
