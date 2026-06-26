# ARM64 虚拟化相关章节整理

## 1. 直接阅读：AArch64 Virtualization Guide

文件：
- [learn_the_architecture_aarch64_virtualization_guide_102142_0100_06_en.pdf](/home/lyq/Projects/materials/virtualization/learn_the_architecture_aarch64_virtualization_guide_102142_0100_06_en.pdf)

这本就是 ARM 官方的虚拟化学习指南，46 页，基本可以按顺序通读。

### 目录与页码

1. `Overview` - 第 6 页
2. `Introduction to virtualization` - 第 7 页
3. `Virtualization in AArch64` - 第 11 页
4. `Stage 2 translation` - 第 12 页
5. `Trapping and emulation of instructions` - 第 21 页
6. `Virtualizing exceptions` - 第 24 页
7. `Virtualizing the generic timers` - 第 28 页
8. `Virtualization host extensions` - 第 31 页
9. `Nested virtualization` - 第 37 页
10. `Secure virtualization` - 第 40 页
11. `Costs of virtualization` - 第 43 页
12. `Check your knowledge` - 第 44 页
13. `Related information` - 第 45 页
14. `Next steps` - 第 46 页

### 建议重点

- 必读主线：
  - `3. Virtualization in AArch64`
  - `4. Stage 2 translation`
  - `5. Trapping and emulation of instructions`
  - `6. Virtualizing exceptions`
  - `7. Virtualizing the generic timers`
- 进阶主线：
  - `8. Virtualization host extensions`
  - `9. Nested virtualization`
  - `10. Secure virtualization`

### 这本书覆盖的核心概念

- EL2 / Hypervisor 基本模型
- Stage-2 地址翻译
- VM / vCPU / IPA / PA
- Trap-and-emulate
- 虚拟异常与虚拟中断
- Generic Timer 虚拟化
- VHE
- Nested Virtualization
- Secure EL2 / Secure Virtualization

## 2. 查规范：A-profile Architecture Reference Manual

文件：
- [DDI_0487_M.b_a-profile_architecture_reference_manual.pdf](/home/lyq/Projects/materials/virtualization/DDI_0487_M.b_a-profile_architecture_reference_manual.pdf)

这本是 ARM ARM，154MB，17153 页。不要通读。查虚拟化时优先看下面这些章节。

### 虚拟化最相关章节

位于 `Part D, The AArch64 System Level Architecture`：

- `The AArch64 Virtual Memory System Architecture` - 从第 7686 页附近开始
  - `Translation process` - 7686
  - `Translation table descriptor formats` - 7724
  - `Virtualization Host Extensions` - 7814
  - `Nested virtualization` - 7821
  - `Memory aborts` - 7829
  - `Translation Lookaside Buffers` - 7842
  - `TLB maintenance` - 7847

### 相关但次一级的重要章节

- `The Exception model` - 这是理解 trap、异常路由、EL2 行为的基础入口
- `About the AArch64 System registers` - 8464 附近
  - 查 EL2 相关寄存器时很有用
- `Moves to and from non-debug System registers, Special-purpose registers` - 8446 附近
  - 查寄存器编码、访问规则时用

### AArch32 兼容视角

如果你还要看 32 位来宾或历史虚拟化模型：

- `G1.8 Virtualization` - 13469
- `The AArch32 Virtual Memory System Architecture` - 另一个独立入口

## 3. 推荐在 ARM ARM 里重点搜索的特性/术语

查 PDF 时，优先搜这些关键词：

- `FEAT_VHE`
- `FEAT_NV2`
- `FEAT_NV2p1`
- `FEAT_SEL2`
- `stage 2`
- `VMID`
- `ASID`
- `virtual interrupt`
- `memory abort`
- `trap`
- `HCR_EL2`
- `HCRX_EL2`
- `VTTBR_EL2`
- `VTCR_EL2`
- `HPFAR_EL2`
- `ESR_EL2`
- `CNTHCTL_EL2`

## 4. 建议阅读顺序

### 入门顺序

1. 先读虚拟化指南第 3 到第 10 章。
2. 再回 ARM ARM 查 `Translation process`、`Virtualization Host Extensions`、`Nested virtualization`。
3. 最后按寄存器回查 `HCR_EL2 / VTCR_EL2 / VTTBR_EL2 / ESR_EL2 / HPFAR_EL2 / CNTHCTL_EL2`。

### 如果你的目标是 KVM/Hypervisor 实战

优先读：

1. `Virtualization in AArch64`
2. `Stage 2 translation`
3. `Trapping and emulation of instructions`
4. `Virtualizing exceptions`
5. `Virtualizing the generic timers`
6. `Virtualization host extensions`

### 如果你的目标是高级主题

优先读：

1. `Nested virtualization`
2. `Secure virtualization`
3. ARM ARM 中的 `FEAT_NV2 / FEAT_NV2p1 / FEAT_SEL2`

## 5. 一句话索引

- 学概念：看 `102142` 这本 guide。
- 查规范：看 `DDI0487` 的 Part D。
- 查寄存器：回 `AArch64 System registers`。
- 查地址翻译：回 `Translation process` 和 `Translation table descriptor formats`。
