# CubeSandbox ARM64 Adaptation Issues Summary

Date: 2026-05-06

## Scope

This report summarizes ARM64 adaptation issues discovered so far through Trellis task `05-06-arm64-port`, especially the first build pass in `05-06-arm64-build-toolchain`.

Remote validation host:

```text
host: k8s-master
ssh: root@192.168.25.61
arch: aarch64
os: openEuler 24.03 (LTS-SP3)
kernel: 6.6.0-132.0.0.111.oe2403sp3.aarch64
kvm: available
```

Remote build logs:

```text
/tmp/cubesandbox-arm64-build-logs
```

## Executive Summary

ARM64 host readiness is good after toolchain repair: KVM is available, Rustup toolchains are usable, and basic build tools are installed. However, CubeSandbox is not yet ARM64-compatible as a system. The first component build pass shows:

* Buildable on ARM64:
  * `CubeAPI`
  * `Cubelet` / `cubecli` with protobuf include workaround
* Blocked on ARM64:
  * `CubeShim`
  * `hypervisor`
  * `agent`
  * `CubeMaster`
  * `network-agent`
* Not yet validated:
  * ARM64 builder image
  * ARM64 guest kernel/image assets
  * ARM64 CubeNet runtime/eBPF load behavior
  * ARM64 end-to-end sandbox lifecycle
  * ARM64 CI/release packaging

The highest-priority blockers are:

1. Hypervisor ARM64 KVM code does not compile.
2. `cube-agent` pulls x86-only Rust crate/code paths.
3. CubeNet BPF generated bindings are x86-only.
4. CubeMaster production command imports old x86/amd64-only `gomonkey`.
5. Build/release scripts still hardcode x86_64/amd64 artifact assumptions.

## Build Matrix

| Component | Result | Evidence | Classification |
|---|---|---|---|
| CubeAPI | success | ARM64 `cube-api` built | compatible at build level |
| Cubelet | success with workaround | ARM64 `cubelet` and `cubecli` built after `PROTOBUF_INCLUDE_DIR` override | environment/build-script issue |
| CubeShim | failed | hypervisor ARM64 KVM compile errors | code adaptation blocker |
| hypervisor | failed | same ARM64 KVM compile errors | code adaptation blocker |
| agent | failed | x86_64 crate / x86 inline asm errors | code adaptation blocker |
| CubeMaster | failed | old `gomonkey` imported by production path | dependency/build-architecture blocker |
| network-agent | failed | CubeNet x86-only BPF bindings missing ARM64 functions | generated-code/eBPF blocker |

Detailed build results are recorded in:

* `05-06-arm64-build-toolchain/research/arm64-component-build-results.md`

## Issue 1: Hypervisor And CubeShim ARM64 KVM Code Fails To Compile

### Status

Open.

### Affected Components

* `hypervisor`
* `CubeShim`
* later runtime validation and sandbox lifecycle

### Error

```text
error: cannot find macro `offset_of` in this scope
error[E0061]: this method takes 2 arguments but 1 argument was supplied
    --> hypervisor/src/kvm/mod.rs:1223:14
     |
1223 |             .get_one_reg(arm64_core_reg_id!(KVM_REG_SIZE_U64, off))
     |              ^^^^^^^^^^^ an argument of type `&mut [u8]` is missing

error: could not compile `hypervisor` (lib) due to 30 previous errors
```

### Evidence

* `/tmp/cubesandbox-arm64-build-logs/CubeShim.log`
* `/tmp/cubesandbox-arm64-build-logs/hypervisor.log`
* `reports/issue-arm64-hypervisor-kvm-build.md`

### Root Cause Assessment

The ARM64 KVM code path does not match the currently locked `kvm-ioctls` API. In `kvm-ioctls 0.17.0`, `get_one_reg` takes a register id plus a mutable byte buffer, while the current code appears to expect a returned register value. The ARM64 code also uses `offset_of!` without a valid macro import in scope.

### Possible Fix

* Update ARM64 register access helpers to use `get_one_reg(reg_id, &mut bytes)` and decode bytes into the target register type.
* Import or replace `offset_of!` consistently. For Rust `1.77.2`, verify whether `std::mem::offset_of` is stable enough for this code path; otherwise use a local macro/helper or the existing project helper if available.
* Add an ARM64 compile check for `hypervisor` and `CubeShim`.
* Keep the fix isolated to ARM64 KVM code paths so existing x86_64 behavior is not changed.

### Suggested Verification

```bash
cd /root/CubeSandbox/hypervisor
RUSTUP_TOOLCHAIN=1.77.2 cargo build --release --locked

cd /root/CubeSandbox/CubeShim
cargo build --release --locked
```

## Issue 2: cube-agent Depends On x86_64 Crate And x86 Inline Assembly

### Status

Open.

### Affected Components

* `agent`
* guest image build
* runtime sandbox startup

### Error

```text
error[E0433]: failed to resolve: could not find `x86_64` in `arch`
error: invalid register `al`: unknown register
error: invalid register `dx`: unknown register
error: invalid register `rax`: unknown register
error: invalid register `rdx`: unknown register
error: could not compile `x86_64` (lib) due to 33 previous errors
```

### Evidence

* `/tmp/cubesandbox-arm64-build-logs/agent.log`
* `reports/issue-agent-x86-crate-arm64-build.md`

### Root Cause Assessment

`agent/Cargo.toml` depends on the x86-only `x86_64` crate. The code path using it is compiled on ARM64 and triggers x86 register/inline assembly errors. Earlier code inventory also identified x86 I/O port usage in `agent/src/rpc.rs`.

### Possible Fix

* Move `x86_64` dependency under a target-specific Cargo dependency:
  ```toml
  [target.'cfg(target_arch = "x86_64")'.dependencies]
  x86_64 = "..."
  ```
* Gate x86-only Rust code with:
  ```rust
  #[cfg(target_arch = "x86_64")]
  ```
* Define ARM64 behavior explicitly:
  * no-op if the operation is only relevant to x86 port I/O,
  * ARM64-specific implementation if equivalent functionality is required,
  * or a clear runtime error for unsupported sub-feature if the feature is optional.
* Add at least a compile-only ARM64 CI check for `agent`.

### Suggested Verification

```bash
cd /root/CubeSandbox/agent
cargo build --release
```

## Issue 3: CubeNet BPF Bindings Are Generated Only For x86

### Status

Open.

### Affected Components

* `CubeNet/cubevs`
* `network-agent`
* CubeVS/eBPF networking
* later runtime network validation

### Error

```text
# github.com/tencentcloud/CubeSandbox/CubeNet/cubevs
../CubeNet/cubevs/miscs.go:96:28: undefined: loadLocalgw
../CubeNet/cubevs/miscs.go:101:27: undefined: loadMvmtap
../CubeNet/cubevs/miscs.go:106:27: undefined: loadNodenic
```

### Evidence

* `/tmp/cubesandbox-arm64-build-logs/network-agent.log`
* `reports/issue-network-agent-cubenet-bpf-arm64-build.md`

### Root Cause Assessment

Generated files such as `localgw_x86_bpfel.go`, `mvmtap_x86_bpfel.go`, and `nodenic_x86_bpfel.go` are guarded by x86 build tags. On ARM64 they are excluded, so functions such as `loadLocalgw`, `loadMvmtap`, and `loadNodenic` are undefined.

The repository also currently has only `CubeNet/vmlinux/x86/vmlinux.h`; ARM64 CO-RE headers are missing.

### Possible Fix

* Generate ARM64 `vmlinux.h`:
  ```bash
  cd CubeNet/vmlinux
  make
  ```
  or use `bpftool btf dump file /sys/kernel/btf/vmlinux format c`.
* Update `CubeNet/cubevs/cubevs.go` `go:generate` directives to generate both amd64 and arm64:
  ```go
  //go:generate go run github.com/cilium/ebpf/cmd/bpf2go -target amd64 ...
  //go:generate go run github.com/cilium/ebpf/cmd/bpf2go -target arm64 ...
  ```
* Commit generated ARM64 Go/object files with correct build tags.
* Rebuild `network-agent` on ARM64.
* Later, validate BPF verifier/load behavior on the ARM64 kernel, not just compilation.

### Suggested Verification

```bash
cd /root/CubeSandbox/CubeNet/cubevs
go generate ./...

cd /root/CubeSandbox/network-agent
make proto
go build -o /tmp/cubesandbox-arm64-build-logs/network-agent ./cmd/network-agent
```

## Issue 4: CubeMaster Production Build Imports Old gomonkey

### Status

Open.

### Affected Components

* `CubeMaster/cmd/cubemaster`
* `CubeMaster/cmd/cubemastercli`

### Error

```text
# github.com/agiledragon/gomonkey
/root/go/pkg/mod/github.com/agiledragon/gomonkey@v2.0.2+incompatible/patch.go:163:10: undefined: buildJmpDirective
```

### Evidence

* `/tmp/cubesandbox-arm64-build-logs/CubeMaster.log`
* `reports/issue-cubemaster-gomonkey-arm64-build.md`

### Root Cause Assessment

`cmd/cubemaster/main.go` imports `CubeMaster/integration`; `cmd/cubemastercli/commands/cubebox/benchrun.go` also imports `integration`. `integration/mock_init.go` imports old `github.com/agiledragon/gomonkey` `v2.0.2+incompatible`, which lacks ARM64 jump directive implementation.

This is a production build path importing mock/monkey-patching code.

### Possible Fix

* Split integration/mock code behind build tags, for example:
  ```go
  //go:build integration || test
  ```
* Remove `integration.MockInit()` from normal `cubemaster` startup, or gate it behind a build tag/config flag that does not compile mock dependencies into production.
* Move benchmark-only `cubemastercli` code that imports `integration` behind a separate build tag or subcommand package compiled only when explicitly requested.
* If monkey patching is still required for tests, use `github.com/agiledragon/gomonkey/v2` only in `_test.go` or tagged test/integration files.

### Suggested Verification

```bash
cd /root/CubeSandbox/CubeMaster
go build -o /tmp/cubesandbox-arm64-build-logs/cubemaster ./cmd/cubemaster
go build -o /tmp/cubesandbox-arm64-build-logs/cubemastercli ./cmd/cubemastercli
```

## Issue 5: Cubelet Protobuf Include Discovery Fails On openEuler

### Status

Workaround verified.

### Affected Components

* `Cubelet/Makefile`
* ARM64/openEuler build environment

### Error

```text
error: protobuf include directory not found
make: *** [Makefile:73: check-proto-tools] Error 1
```

### Evidence

* `/tmp/cubesandbox-arm64-build-logs/Cubelet.log`
* `/tmp/cubesandbox-arm64-build-logs/Cubelet-retry-protobuf-include.log`
* `reports/issue-cubelet-protobuf-include-path.md`

### Root Cause Assessment

The Makefile searches only a few include locations for `google/protobuf/empty.proto` and `google/protobuf/any.proto`. On the ARM64 openEuler host, `protoc` is installed, but the protobuf include files were not found in the Makefile's expected locations.

### Verified Workaround

Using a known include directory from the local Cargo registry allowed `make proto` and ARM64 Go builds to pass:

```bash
PROTOBUF_INCLUDE_DIR=/root/.cargo/registry/src/rsproxy.cn-0dccff568467c15b/prost-build-0.8.0/third-party/protobuf/include
```

This produced:

```text
/tmp/cubesandbox-arm64-build-logs/cubelet: ELF 64-bit LSB executable, ARM aarch64
/tmp/cubesandbox-arm64-build-logs/cubecli: ELF 64-bit LSB executable, ARM aarch64
```

### Possible Fix

* Make `PROTOBUF_INCLUDE_DIR` an explicit documented input for non-Ubuntu/non-builder hosts.
* Improve Makefile discovery to include openEuler protobuf-devel paths if available.
* Prefer installing a stable protobuf include package over depending on a Cargo registry path.
* Consider vendoring protobuf includes for reproducible proto generation if compatible with project policy.

### Suggested Verification

```bash
cd /root/CubeSandbox/Cubelet
make proto PROTOBUF_INCLUDE_DIR=<stable protobuf include dir>
GOARCH=arm64 GOOS=linux go build -o /tmp/cubesandbox-arm64-build-logs/cubelet ./cmd/cubelet
GOARCH=arm64 GOOS=linux go build -o /tmp/cubesandbox-arm64-build-logs/cubecli ./cmd/cubecli
```

## Issue 6: Rustup Toolchains Were Incomplete

### Status

Fixed.

### Affected Components

* `CubeAPI`
* `CubeShim`
* `agent`
* `hypervisor`

### Error

```text
error: Missing manifest in toolchain '1.77.2-aarch64-unknown-linux-gnu'
error: Missing manifest in toolchain '1.85-aarch64-unknown-linux-gnu'
error: Missing manifest in toolchain '1.89-aarch64-unknown-linux-gnu'
```

### Evidence

* `reports/issue-rustup-incomplete-toolchains.md`
* `reports/adaptation-success-rustup-toolchains.md`

### Root Cause Assessment

Multiple `rustup install` and `cargo build` processes were running concurrently against the same `/root/.rustup`, while downloads were slow. Toolchain directories became visible before complete `rustc`/std manifests were installed.

### Fix Applied

* Stopped stuck Rustup/Cargo processes.
* Configured `rsproxy.cn`.
* Removed incomplete `1.77.2`, `1.85`, `1.89` toolchains.
* Reinstalled toolchains serially.
* Verified project-level toolchain selection and `cargo metadata`.

### Follow-Up

Keep Rustup installation serialized in automation. Avoid running multiple `rustup toolchain install` jobs in the same `RUSTUP_HOME`.

## Issue 7: Builder Image And Release Build Scripts Still Encode x86_64/amd64

### Status

Identified by code inventory; not yet fully build-tested in Docker on ARM64.

### Affected Components

* `docker/Dockerfile.builder`
* root `Makefile`
* `.github/workflows/build-check.yml`
* `deploy/one-click/build-release-bundle-builder.sh`
* `agent/Makefile`
* `CubeMaster/Makefile`
* `Cubelet/Makefile`
* `docker/Dockerfile.cube-base`

### Evidence

* `research/arm64-code-inventory.md`

### Observed x86_64/amd64 Assumptions

* Builder downloads Go `linux-amd64`.
* Builder downloads `protoc-*-linux-x86_64.zip`.
* Builder installs only `x86_64-unknown-linux-musl` Rust target.
* Static libseccomp build uses `--host=x86_64-linux-musl`.
* Root Makefile and CI expect `agent/target/x86_64-unknown-linux-musl/release/cube-agent`.
* `CubeMaster/Makefile` and `Cubelet/Makefile` export `GOARCH=amd64`.
* `docker/Dockerfile.cube-base` builds envd with `GOARCH=amd64`.

### Possible Fix

* Introduce a single architecture variable:
  ```make
  TARGET_ARCH ?= $(shell uname -m)
  GOARCH ?= arm64|amd64
  RUST_TARGET ?= aarch64-unknown-linux-gnu|x86_64-unknown-linux-musl
  ```
* Map Docker platform architecture to toolchain downloads:
  ```text
  amd64 -> go linux-amd64, protoc linux-x86_64, x86_64 Rust targets
  arm64 -> go linux-arm64, protoc linux-aarch_64 if available, aarch64 Rust targets
  ```
* Build libseccomp for the current architecture instead of hardcoding x86_64 musl.
* Make CI matrix explicit:
  ```yaml
  strategy:
    matrix:
      arch: [amd64, arm64]
  ```
* Ensure artifact paths and names include architecture.

### Suggested Verification

```bash
docker build -t cube-sandbox-builder:arm64 -f docker/Dockerfile.builder .
make builder-run BUILDER_IMAGE=cube-sandbox-builder:arm64 BUILDER_CMD='<component build>'
```

## Issue 8: Guest Kernel/Image Assets Are Still x86-Oriented

### Status

Identified by code inventory; not yet runtime-tested.

### Affected Components

* `configs/kernel-oc9.config`
* `.github/workflows/build-vmlinux.yml`
* `deploy/one-click/build-vm-assets.sh`
* `dev-env/prepare_image.sh`
* `dev-env/run_vm.sh`

### Evidence

* `research/arm64-code-inventory.md`

### Root Cause Assessment

Current guest kernel config is x86 and one-click packaging uses a generic `cube-kernel-scf/vmlinux` path without architecture validation. Dev environment scripts use x86_64 OpenCloudOS qcow2 images and `qemu-system-x86_64`.

### Possible Fix

* Add a separate ARM64 kernel config and artifact naming convention:
  ```text
  cube-kernel-scf-linux-arm64/vmlinux
  cube-kernel-scf-linux-amd64/vmlinux
  ```
* Validate artifact architecture with `file` during packaging.
* Validate guest rootfs architecture and `cube-agent` architecture before image packaging.
* Add ARM64 guest image path and QEMU machine config if dev-env ARM64 VM is required.

## Issue 9: Runtime Command Line Contains x86-Specific Assumptions

### Status

Identified by code inventory; blocked from runtime test by build failures.

### Affected Components

* `CubeShim/shim/src/hypervisor/config.rs`
* `CubeShim/shim/src/sandbox/sb.rs`
* `CubeShim/shim/src/snapshot/mod.rs`

### Evidence

* `research/arm64-code-inventory.md`

### Observed Assumptions

* Kernel cmdline includes x86-oriented params such as `no_timer_check`, `noreplace-smp`, `earlyprintk=ttyS0`.
* Sandbox startup appends `clocksource=kvm-clock`.
* Snapshot boot uses `clocksource=tsc` and `tsc=reliable`.

### Possible Fix

* Split kernel command line defaults by architecture.
* Replace x86 TSC/kvm-clock assumptions with ARM64-appropriate clocksource/console settings.
* Validate with guest serial logs after ARM64 hypervisor and agent builds are fixed.

## Recommended Fix Order

1. Fix `hypervisor` ARM64 KVM compile errors.
   This unblocks both standalone hypervisor and CubeShim builds.
2. Fix `agent` x86-only dependency/code paths.
   This is required before any ARM64 guest image can boot CubeSandbox agent logic.
3. Fix CubeNet ARM64 BPF generation.
   This unblocks `network-agent` and later network validation.
4. Fix CubeMaster production import of old `gomonkey`.
   This unblocks control-plane binary builds.
5. Make Cubelet protobuf include discovery portable.
   Workaround exists, but CI/build automation should not depend on Cargo registry paths.
6. Make builder/release scripts architecture-aware.
   Do this after code-level compile blockers are understood, so automation models the right target matrix.
7. Add ARM64 guest kernel/image artifact contract.
   Required before runtime/E2E validation.
8. Review and split runtime kernel cmdline by architecture.
   Required before declaring runtime compatibility.

## Current Support Classification

| Area | Classification | Reason |
|---|---|---|
| ARM64 host baseline | usable | Host validated with KVM and build tools. |
| Rust toolchain | usable | Repaired and verified. |
| CubeAPI build | usable | ARM64 binary produced. |
| Cubelet build | usable with caveat | ARM64 binaries produced with explicit protobuf include workaround. |
| CubeShim build | blocked | Hypervisor ARM64 KVM compile errors. |
| hypervisor build | blocked | ARM64 KVM compile errors. |
| agent build | blocked | x86-only crate/code paths. |
| CubeMaster build | blocked | old `gomonkey` in production import path. |
| network-agent build | blocked | x86-only CubeNet BPF generated bindings. |
| guest kernel/image | not tested, likely blocked | x86 kernel config and generic artifact path. |
| runtime sandbox lifecycle | not tested, blocked | Requires hypervisor, CubeShim, agent, network-agent. |
| CI/release | not tested, likely blocked | x86_64/amd64 hardcoding remains. |

## References

* `05-06-arm64-build-toolchain/research/arm64-component-build-results.md`
* `reports/issue-arm64-hypervisor-kvm-build.md`
* `reports/issue-agent-x86-crate-arm64-build.md`
* `reports/issue-cubemaster-gomonkey-arm64-build.md`
* `reports/issue-network-agent-cubenet-bpf-arm64-build.md`
* `reports/issue-cubelet-protobuf-include-path.md`
* `reports/issue-rustup-incomplete-toolchains.md`
* `reports/adaptation-success-arm64-cubeapi-cubelet-build.md`
* `reports/adaptation-success-rustup-toolchains.md`
