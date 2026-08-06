# ARM64 vGIC AP1R NMI-active 故障修复包（2026-07-31）

根因与验证的完整分析见仓库根目录：
`CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md`

## 内容

| 文件 | 说明 |
|---|---|
| `kernel-vgic-v3-apr-readback-mask.patch` | 内核补丁：`__vgic_v3_save_aprs` 对 AP 寄存器硬件读回值屏蔽高 32 位（向量 B 修复）。适用于 sbench 树 `arch/arm64/kvm/hyp/vgic-v3-sr.c`（openEuler 6.6.0-132 oe2403sp3 基线） |
| `vmm-icc-regs-u64-access.patch` | VMM 补丁：`icc_regs.rs` 的 CPU_SYSREGS 访问改 8 字节缓冲（向量 A 修复）；快照序列化格式不变，旧模板兼容 |
| `artifacts/cube-runtime-iccfix-a68d64cd` | 修复版 cube-runtime（含 icc 修复与 snapshot 子命令；CubeShim workspace `cargo build --release --locked` 构建于 cube-community-builder:offline） |
| `artifacts/kernel-6.6.0_sbench_irqbypass_xarray_v2_aprmask-2.aarch64.rpm` | 修复版内核 rpm（aprmask） |
| `artifacts/icc_regs.rs.orig-reference` / `icc_regs.rs.patched-reference` | VMM 补丁前后参考源文件 |
| `artifacts/vgic-v3-sr.c.patched-reference` | 内核补丁后参考源文件（补丁前版本在 .90：`/home/lyq/kernel-build-irqbypass-v2-20260720/vgic-v3-sr.c.pre-aprmask`） |

## 部署与验证口径

- 两个补丁**各自单独都不够**（userspace 注入与硬件读回注入是两条独立向量），需同时生效。
- 验证基线（.90，社区 cubelet `88e5e224` / shim `4702fde1` / cubemaster `0b78e83c`，社区 TencentOS guest image，模板 `tpl-42e1ad04f7354b1295e05b78`）：未修复 5/20；单修任一 5/20；**双修 20/20，并发 1600 次 0 次 `reset guest time failed` / `reset reseed random dev failed`，探针 bit63=0**。

## 校验

见 `SHA256SUMS`（内核 rpm 与 .90 源文件逐字节一致：`9f340203…`）。
