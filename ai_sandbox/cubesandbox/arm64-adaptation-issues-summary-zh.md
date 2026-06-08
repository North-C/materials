# CubeSandbox ARM64 适配问题汇总

日期：2026-05-06

## 范围

本文汇总截至目前在 Trellis 任务 `05-06-arm64-port` 中发现的 ARM64 适配问题，重点来自子任务 `05-06-arm64-build-toolchain` 的第一轮组件构建验证。

远程验证环境：

```text
host: k8s-master
ssh: root@192.168.25.61
arch: aarch64
os: openEuler 24.03 (LTS-SP3)
kernel: 6.6.0-132.0.0.111.oe2403sp3.aarch64
kvm: available
```

远程构建日志目录：

```text
/tmp/cubesandbox-arm64-build-logs
```

## 总体结论

ARM64 主机基础条件已经具备：KVM 可用，Rustup 工具链已修复，基础构建工具已安装。但是 CubeSandbox 当前还不能作为完整系统声明支持 ARM64。第一轮组件构建结果如下：

可在 ARM64 上构建：

* `CubeAPI`
* `Cubelet` / `cubecli`，但需要显式指定 protobuf include 目录

ARM64 上仍阻塞：

* `CubeShim`
* `hypervisor`
* `agent`
* `CubeMaster`
* `network-agent`

尚未完成验证：

* ARM64 builder image
* ARM64 guest kernel/image 资产
* ARM64 CubeNet 运行期和 eBPF 加载行为
* ARM64 端到端 sandbox 生命周期
* ARM64 CI/release 打包

当前最高优先级阻塞项：

1. Hypervisor ARM64 KVM 代码无法编译。
2. `cube-agent` 引入了 x86-only Rust crate 和 x86 汇编路径。
3. CubeNet BPF 生成物只有 x86 版本。
4. CubeMaster 生产构建路径引入旧版 x86/amd64-only `gomonkey`。
5. 构建和发布脚本仍包含 x86_64/amd64 产物假设。

## 构建矩阵

| 组件 | 结果 | 证据 | 分类 |
|---|---|---|---|
| CubeAPI | 成功 | 已生成 ARM64 `cube-api` | 构建层面可用 |
| Cubelet | workaround 后成功 | 设置 `PROTOBUF_INCLUDE_DIR` 后已生成 ARM64 `cubelet` 和 `cubecli` | 环境/构建脚本问题 |
| CubeShim | 失败 | hypervisor ARM64 KVM 编译错误 | 代码适配阻塞 |
| hypervisor | 失败 | 同 ARM64 KVM 编译错误 | 代码适配阻塞 |
| agent | 失败 | x86_64 crate / x86 inline asm 错误 | 代码适配阻塞 |
| CubeMaster | 失败 | 生产路径引入旧版 `gomonkey` | 依赖/构建架构阻塞 |
| network-agent | 失败 | CubeNet x86-only BPF binding 缺少 ARM64 函数 | 生成代码/eBPF 阻塞 |

详细构建结果记录在：

* `05-06-arm64-build-toolchain/research/arm64-component-build-results.md`

## 问题 1：Hypervisor 和 CubeShim 的 ARM64 KVM 代码无法编译

### 状态

未修复。

### 影响组件

* `hypervisor`
* `CubeShim`
* 后续运行期验证和 sandbox 生命周期

### 错误信息

```text
error: cannot find macro `offset_of` in this scope
error[E0061]: this method takes 2 arguments but 1 argument was supplied
    --> hypervisor/src/kvm/mod.rs:1223:14
     |
1223 |             .get_one_reg(arm64_core_reg_id!(KVM_REG_SIZE_U64, off))
     |              ^^^^^^^^^^^ an argument of type `&mut [u8]` is missing

error: could not compile `hypervisor` (lib) due to 30 previous errors
```

### 证据

* `/tmp/cubesandbox-arm64-build-logs/CubeShim.log`
* `/tmp/cubesandbox-arm64-build-logs/hypervisor.log`
* `reports/issue-arm64-hypervisor-kvm-build.md`

### 原因判断

ARM64 KVM 代码路径与当前锁定的 `kvm-ioctls` API 不匹配。在 `kvm-ioctls 0.17.0` 中，`get_one_reg` 需要传入寄存器 id 和可变字节缓冲区，而现有代码看起来仍按“返回寄存器值”的旧接口使用。同时，ARM64 代码使用了 `offset_of!`，但当前作用域内没有可用的宏导入。

### 可能修复方案

* 调整 ARM64 寄存器访问 helper，改为 `get_one_reg(reg_id, &mut bytes)`，再从字节数组解码目标寄存器类型。
* 统一处理 `offset_of!`。对于 Rust `1.77.2`，需要确认 `std::mem::offset_of` 在当前代码路径是否可用；如果不合适，应使用本地宏/helper 或项目已有 helper。
* 增加 `hypervisor` 和 `CubeShim` 的 ARM64 compile check。
* 修复应尽量限制在 ARM64 KVM 代码路径内，避免改变现有 x86_64 行为。

### 建议验证命令

```bash
cd /root/CubeSandbox/hypervisor
RUSTUP_TOOLCHAIN=1.77.2 cargo build --release --locked

cd /root/CubeSandbox/CubeShim
cargo build --release --locked
```

## 问题 2：cube-agent 依赖 x86_64 crate 和 x86 inline assembly

### 状态

未修复。

### 影响组件

* `agent`
* guest image 构建
* sandbox 启动运行期

### 错误信息

```text
error[E0433]: failed to resolve: could not find `x86_64` in `arch`
error: invalid register `al`: unknown register
error: invalid register `dx`: unknown register
error: invalid register `rax`: unknown register
error: invalid register `rdx`: unknown register
error: could not compile `x86_64` (lib) due to 33 previous errors
```

### 证据

* `/tmp/cubesandbox-arm64-build-logs/agent.log`
* `reports/issue-agent-x86-crate-arm64-build.md`

### 原因判断

`agent/Cargo.toml` 依赖 x86-only 的 `x86_64` crate。相关代码路径在 ARM64 上仍会参与编译，触发 x86 寄存器和 inline assembly 编译错误。前序代码盘点也发现 `agent/src/rpc.rs` 中存在 x86 I/O port 使用。

### 可能修复方案

* 将 `x86_64` 依赖移动到 target-specific Cargo dependency：

  ```toml
  [target.'cfg(target_arch = "x86_64")'.dependencies]
  x86_64 = "..."
  ```

* 使用 `cfg` 隔离 x86-only Rust 代码：

  ```rust
  #[cfg(target_arch = "x86_64")]
  ```

* 明确定义 ARM64 行为：
  * 如果该操作只对 x86 port I/O 有意义，ARM64 可实现为 no-op；
  * 如果 ARM64 有等价机制，应实现 ARM64-specific 路径；
  * 如果该功能是可选能力，应返回清晰的 runtime unsupported error。
* 至少为 `agent` 增加 ARM64 compile-only CI check。

### 建议验证命令

```bash
cd /root/CubeSandbox/agent
cargo build --release
```

## 问题 3：CubeNet BPF bindings 仅生成了 x86 版本

### 状态

未修复。

### 影响组件

* `CubeNet/cubevs`
* `network-agent`
* CubeVS/eBPF 网络能力
* 后续网络运行期验证

### 错误信息

```text
# github.com/tencentcloud/CubeSandbox/CubeNet/cubevs
../CubeNet/cubevs/miscs.go:96:28: undefined: loadLocalgw
../CubeNet/cubevs/miscs.go:101:27: undefined: loadMvmtap
../CubeNet/cubevs/miscs.go:106:27: undefined: loadNodenic
```

### 证据

* `/tmp/cubesandbox-arm64-build-logs/network-agent.log`
* `reports/issue-network-agent-cubenet-bpf-arm64-build.md`

### 原因判断

仓库中的 `localgw_x86_bpfel.go`、`mvmtap_x86_bpfel.go`、`nodenic_x86_bpfel.go` 等生成文件带有 x86 build tags。在 ARM64 上这些文件会被排除，导致 `loadLocalgw`、`loadMvmtap`、`loadNodenic` 等函数未定义。

仓库目前也只有 `CubeNet/vmlinux/x86/vmlinux.h`，缺少 ARM64 CO-RE 头文件。

### 可能修复方案

* 生成 ARM64 `vmlinux.h`：

  ```bash
  cd CubeNet/vmlinux
  make
  ```

  或使用：

  ```bash
  bpftool btf dump file /sys/kernel/btf/vmlinux format c
  ```

* 更新 `CubeNet/cubevs/cubevs.go` 的 `go:generate` 指令，同时生成 amd64 和 arm64：

  ```go
  //go:generate go run github.com/cilium/ebpf/cmd/bpf2go -target amd64 ...
  //go:generate go run github.com/cilium/ebpf/cmd/bpf2go -target arm64 ...
  ```

* 提交带正确 build tags 的 ARM64 Go/object 生成物。
* 在 ARM64 上重新构建 `network-agent`。
* 后续需要验证 ARM64 内核上的 BPF verifier/load 行为，不能只停留在编译通过。

### 建议验证命令

```bash
cd /root/CubeSandbox/CubeNet/cubevs
go generate ./...

cd /root/CubeSandbox/network-agent
make proto
go build -o /tmp/cubesandbox-arm64-build-logs/network-agent ./cmd/network-agent
```

## 问题 4：CubeMaster 生产构建路径引入旧版 gomonkey

### 状态

未修复。

### 影响组件

* `CubeMaster/cmd/cubemaster`
* `CubeMaster/cmd/cubemastercli`

### 错误信息

```text
# github.com/agiledragon/gomonkey
/root/go/pkg/mod/github.com/agiledragon/gomonkey@v2.0.2+incompatible/patch.go:163:10: undefined: buildJmpDirective
```

### 证据

* `/tmp/cubesandbox-arm64-build-logs/CubeMaster.log`
* `reports/issue-cubemaster-gomonkey-arm64-build.md`

### 原因判断

`cmd/cubemaster/main.go` 引入 `CubeMaster/integration`；`cmd/cubemastercli/commands/cubebox/benchrun.go` 也引入 `integration`。`integration/mock_init.go` 引入旧版 `github.com/agiledragon/gomonkey` `v2.0.2+incompatible`，该版本缺少 ARM64 jump directive 实现。

本质问题是生产构建路径引入了 mock/monkey-patching 代码。

### 可能修复方案

* 将 integration/mock 代码放到 build tags 后面，例如：

  ```go
  //go:build integration || test
  ```

* 从普通 `cubemaster` 启动路径移除 `integration.MockInit()`，或将其挂到默认不启用的 build tag/config flag 后面，避免 mock 依赖进入生产构建。
* 将 `cubemastercli` 中仅 benchmark 使用、且依赖 `integration` 的代码移到单独 build tag 或仅显式启用的子命令包。
* 如果测试仍需要 monkey patching，应把 `github.com/agiledragon/gomonkey/v2` 限制在 `_test.go` 或 tagged test/integration 文件中。

### 建议验证命令

```bash
cd /root/CubeSandbox/CubeMaster
go build -o /tmp/cubesandbox-arm64-build-logs/cubemaster ./cmd/cubemaster
go build -o /tmp/cubesandbox-arm64-build-logs/cubemastercli ./cmd/cubemastercli
```

## 问题 5：Cubelet protobuf include 路径发现不适配 openEuler

### 状态

workaround 已验证。

### 影响组件

* `Cubelet/Makefile`
* ARM64/openEuler 构建环境

### 错误信息

```text
error: protobuf include directory not found
make: *** [Makefile:73: check-proto-tools] Error 1
```

### 证据

* `/tmp/cubesandbox-arm64-build-logs/Cubelet.log`
* `/tmp/cubesandbox-arm64-build-logs/Cubelet-retry-protobuf-include.log`
* `reports/issue-cubelet-protobuf-include-path.md`

### 原因判断

Makefile 只在少数目录中查找 `google/protobuf/empty.proto` 和 `google/protobuf/any.proto`。ARM64 openEuler 主机上已安装 `protoc`，但 protobuf include 文件不在 Makefile 预期路径中。

### 已验证 workaround

使用本地 Cargo registry 中的 protobuf include 目录后，`make proto` 和 ARM64 Go 构建均通过：

```bash
PROTOBUF_INCLUDE_DIR=/root/.cargo/registry/src/rsproxy.cn-0dccff568467c15b/prost-build-0.8.0/third-party/protobuf/include
```

生成结果：

```text
/tmp/cubesandbox-arm64-build-logs/cubelet: ELF 64-bit LSB executable, ARM aarch64
/tmp/cubesandbox-arm64-build-logs/cubecli: ELF 64-bit LSB executable, ARM aarch64
```

### 可能修复方案

* 将 `PROTOBUF_INCLUDE_DIR` 作为非 Ubuntu/非 builder 主机的显式文档化输入。
* 改进 Makefile 自动发现逻辑，纳入 openEuler `protobuf-devel` 可能安装路径。
* 优先安装稳定的 protobuf include 包，不依赖 Cargo registry 临时路径。
* 如果项目策略允许，可考虑 vendoring protobuf include，以提高 proto 生成的可复现性。

### 建议验证命令

```bash
cd /root/CubeSandbox/Cubelet
make proto PROTOBUF_INCLUDE_DIR=<stable protobuf include dir>
GOARCH=arm64 GOOS=linux go build -o /tmp/cubesandbox-arm64-build-logs/cubelet ./cmd/cubelet
GOARCH=arm64 GOOS=linux go build -o /tmp/cubesandbox-arm64-build-logs/cubecli ./cmd/cubecli
```

## 问题 6：Rustup 工具链曾处于不完整安装状态

### 状态

已修复。

### 影响组件

* `CubeAPI`
* `CubeShim`
* `agent`
* `hypervisor`

### 错误信息

```text
error: Missing manifest in toolchain '1.77.2-aarch64-unknown-linux-gnu'
error: Missing manifest in toolchain '1.85-aarch64-unknown-linux-gnu'
error: Missing manifest in toolchain '1.89-aarch64-unknown-linux-gnu'
```

### 证据

* `reports/issue-rustup-incomplete-toolchains.md`
* `reports/adaptation-success-rustup-toolchains.md`

### 原因判断

多个 `rustup install` 和 `cargo build` 进程并发操作同一个 `/root/.rustup`，同时下载速度较慢。toolchain 目录先可见，但 `rustc`/std manifest 尚未完整安装，造成工具链处于半安装状态。

### 已执行修复

* 停止卡住的 Rustup/Cargo 进程。
* 配置 `rsproxy.cn`。
* 移除不完整的 `1.77.2`、`1.85`、`1.89` toolchain。
* 串行重新安装 toolchain。
* 验证项目级 toolchain 选择和 `cargo metadata`。

### 后续要求

自动化中应串行安装 Rustup toolchain，避免多个作业同时写入同一个 `RUSTUP_HOME`。

## 问题 7：Builder image 和 release 构建脚本仍编码 x86_64/amd64

### 状态

代码盘点已发现，尚未在 ARM64 Docker 环境中完整构建验证。

### 影响组件

* `docker/Dockerfile.builder`
* 根目录 `Makefile`
* `.github/workflows/build-check.yml`
* `deploy/one-click/build-release-bundle-builder.sh`
* `agent/Makefile`
* `CubeMaster/Makefile`
* `Cubelet/Makefile`
* `docker/Dockerfile.cube-base`

### 证据

* `research/arm64-code-inventory.md`

### 已观察到的 x86_64/amd64 假设

* Builder 下载 Go `linux-amd64`。
* Builder 下载 `protoc-*-linux-x86_64.zip`。
* Builder 只安装 `x86_64-unknown-linux-musl` Rust target。
* 静态 libseccomp 构建使用 `--host=x86_64-linux-musl`。
* 根 Makefile 和 CI 期望 `agent/target/x86_64-unknown-linux-musl/release/cube-agent`。
* `CubeMaster/Makefile` 和 `Cubelet/Makefile` 导出 `GOARCH=amd64`。
* `docker/Dockerfile.cube-base` 构建 envd 时使用 `GOARCH=amd64`。

### 可能修复方案

* 引入统一架构变量：

  ```make
  TARGET_ARCH ?= $(shell uname -m)
  GOARCH ?= arm64|amd64
  RUST_TARGET ?= aarch64-unknown-linux-gnu|x86_64-unknown-linux-musl
  ```

* 将 Docker platform arch 映射到工具链下载：

  ```text
  amd64 -> go linux-amd64, protoc linux-x86_64, x86_64 Rust targets
  arm64 -> go linux-arm64, protoc linux-aarch_64 if available, aarch64 Rust targets
  ```

* 按当前架构构建 libseccomp，不能硬编码 x86_64 musl。
* 显式配置 CI matrix：

  ```yaml
  strategy:
    matrix:
      arch: [amd64, arm64]
  ```

* 产物路径和产物名称应包含架构信息。

### 建议验证命令

```bash
docker build -t cube-sandbox-builder:arm64 -f docker/Dockerfile.builder .
make builder-run BUILDER_IMAGE=cube-sandbox-builder:arm64 BUILDER_CMD='<component build>'
```

## 问题 8：Guest kernel/image 资产仍偏向 x86

### 状态

代码盘点已发现，尚未进行运行期验证。

### 影响组件

* `configs/kernel-oc9.config`
* `.github/workflows/build-vmlinux.yml`
* `deploy/one-click/build-vm-assets.sh`
* `dev-env/prepare_image.sh`
* `dev-env/run_vm.sh`

### 证据

* `research/arm64-code-inventory.md`

### 原因判断

当前 guest kernel config 是 x86 配置，one-click 打包使用通用 `cube-kernel-scf/vmlinux` 路径且没有架构校验。开发环境脚本使用 x86_64 OpenCloudOS qcow2 镜像和 `qemu-system-x86_64`。

### 可能修复方案

* 增加独立 ARM64 kernel config 和产物命名约定：

  ```text
  cube-kernel-scf-linux-arm64/vmlinux
  cube-kernel-scf-linux-amd64/vmlinux
  ```

* 打包时用 `file` 校验 kernel artifact 架构。
* 打包 guest rootfs 前校验 rootfs 架构和 `cube-agent` 架构。
* 如果需要 dev-env ARM64 VM，补充 ARM64 guest image 路径和 QEMU machine 配置。

## 问题 9：运行期命令行包含 x86-specific 假设

### 状态

代码盘点已发现；当前仍被构建失败阻塞，尚未进入运行期测试。

### 影响组件

* `CubeShim/shim/src/hypervisor/config.rs`
* `CubeShim/shim/src/sandbox/sb.rs`
* `CubeShim/shim/src/snapshot/mod.rs`

### 证据

* `research/arm64-code-inventory.md`

### 已观察到的假设

* Kernel cmdline 包含 x86-oriented 参数，例如 `no_timer_check`、`noreplace-smp`、`earlyprintk=ttyS0`。
* Sandbox 启动追加 `clocksource=kvm-clock`。
* Snapshot boot 使用 `clocksource=tsc` 和 `tsc=reliable`。

### 可能修复方案

* 按架构拆分 kernel command line 默认值。
* 将 x86 TSC/kvm-clock 假设替换为 ARM64 适配的 clocksource/console 设置。
* 在 ARM64 hypervisor 和 agent 构建修复后，通过 guest serial logs 验证。

## 建议修复顺序

1. 修复 `hypervisor` ARM64 KVM 编译错误。这会同时解除 standalone hypervisor 和 CubeShim 的构建阻塞。
2. 修复 `agent` x86-only 依赖和代码路径。没有该修复，ARM64 guest image 即使构建出来也无法运行 CubeSandbox agent 逻辑。
3. 修复 CubeNet ARM64 BPF 生成流程。解除 `network-agent` 构建阻塞，并为后续网络验证做准备。
4. 修复 CubeMaster 生产路径对旧版 `gomonkey` 的引入。解除控制面二进制构建阻塞。
5. 修复 Cubelet protobuf include 自动发现。当前已有 workaround，但 CI/build automation 不应依赖 Cargo registry 路径。
6. 让 builder/release 脚本具备架构感知能力。建议在明确代码级编译阻塞后再做，以便自动化矩阵反映真实目标架构。
7. 增加 ARM64 guest kernel/image artifact contract。运行期和 E2E 验证前必须完成。
8. 按架构拆分并审查运行期 kernel cmdline。完成后才适合声明运行期兼容。

## 当前支持度分类

| 范围 | 分类 | 原因 |
|---|---|---|
| ARM64 host baseline | 可用 | 主机已验证 KVM 和构建工具。 |
| Rust toolchain | 可用 | 已修复并验证。 |
| CubeAPI build | 可用 | 已生成 ARM64 binary。 |
| Cubelet build | 带 caveat 可用 | 显式指定 protobuf include 后已生成 ARM64 binary。 |
| CubeShim build | 阻塞 | Hypervisor ARM64 KVM 编译错误。 |
| hypervisor build | 阻塞 | ARM64 KVM 编译错误。 |
| agent build | 阻塞 | x86-only crate/code path。 |
| CubeMaster build | 阻塞 | 生产 import path 中存在旧版 `gomonkey`。 |
| network-agent build | 阻塞 | CubeNet BPF 生成物只有 x86 binding。 |
| guest kernel/image | 未测试，预计阻塞 | 仍使用 x86 kernel config 和通用 artifact 路径。 |
| runtime sandbox lifecycle | 未测试，已被阻塞 | 依赖 hypervisor、CubeShim、agent、network-agent。 |
| CI/release | 未测试，预计阻塞 | 仍存在 x86_64/amd64 硬编码。 |

## 参考资料

* `05-06-arm64-build-toolchain/research/arm64-component-build-results.md`
* `reports/issue-arm64-hypervisor-kvm-build.md`
* `reports/issue-agent-x86-crate-arm64-build.md`
* `reports/issue-cubemaster-gomonkey-arm64-build.md`
* `reports/issue-network-agent-cubenet-bpf-arm64-build.md`
* `reports/issue-cubelet-protobuf-include-path.md`
* `reports/issue-rustup-incomplete-toolchains.md`
* `reports/adaptation-success-arm64-cubeapi-cubelet-build.md`
* `reports/adaptation-success-rustup-toolchains.md`
