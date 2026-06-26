# ARM64 面向 KVM 学习的阅读地图

## 1. 先定目标

这份地图默认你的目标不是“泛泛了解虚拟化”，而是：

- 能看懂 ARM64 KVM 的核心机制
- 能把 `EL2 / stage-2 / trap / vgic / timer / vCPU` 串起来
- 后续看到 KVM 代码或设计文档时，知道每块在解决什么问题

如果按这个目标学，阅读顺序不能按“大而全”，而要按 `KVM 运行路径` 来读。

## 2. KVM 视角下，先建立一条主线

先记住这条主线：

1. 用户态 VMM 创建 VM 和 vCPU。
2. KVM 把 guest 放进 EL1/EL0 运行，hypervisor/KVM 自己在 EL2。
3. guest 访问内存时，经过 `stage-1 + stage-2` 翻译。
4. guest 做了受限操作，会 `trap` 到 EL2。
5. KVM 在 EL2 处理异常、模拟行为、注入虚拟中断或异常。
6. 然后再 `ERET` 回 guest。

你后面看的每一章，最好都回到这条主线上。

## 3. 分阶段阅读路线

## Phase 0：最小前置知识

目标：
- 先搞清楚 ARM64 上 KVM 站在什么特权级上运行
- 明白 guest 为什么“看起来像在独占机器”，但实际上被 EL2 控制

必读：
- [learn_the_architecture_aarch64_virtualization_guide_102142_0100_06_en.pdf](/home/lyq/Projects/materials/virtualization/learn_the_architecture_aarch64_virtualization_guide_102142_0100_06_en.pdf)
  - `2. Introduction to virtualization`
  - `3. Virtualization in AArch64`

辅助查阅：
- [DDI_0487_M.b_a-profile_architecture_reference_manual.pdf](/home/lyq/Projects/materials/virtualization/DDI_0487_M.b_a-profile_architecture_reference_manual.pdf)
  - `The Exception model`
  - `The AArch64 System Level Architecture`

读完后你应该能回答：
- KVM 在 ARM64 上为什么依赖 `EL2`
- Type-1 / Type-2 的区别，KVM 更接近哪一种
- VM、vCPU、PE 之间是什么关系
- guest OS 为什么通常跑在 `EL1`

## Phase 1：先吃透 KVM 的核心，stage-2

目标：
- 搞清楚 ARM64 KVM 最关键的一件事：`stage-2 translation`
- 明白 KVM 为什么能隔离 guest memory、拦截 MMIO、控制 IPA

必读：
- virtualization guide
  - `4. Stage 2 translation`

必须回查的 ARM ARM 章节：
- `Translation process` - 7686
- `Translation table descriptor formats` - 7724
- `Memory aborts` - 7829
- `Translation Lookaside Buffers` - 7842
- `TLB maintenance` - 7847

重点关键词：
- `IPA`
- `PA`
- `VTTBR_EL2`
- `VTCR_EL2`
- `HPFAR_EL2`
- `VMID`
- `stage 2`

KVM 视角怎么理解：
- KVM 维护 guest 的 stage-2 页表
- guest 自己维护 stage-1 页表
- MMIO 一般靠 stage-2 fault 触发 trap
- guest 的“物理地址”其实常常是 `IPA`

读完后你应该能回答：
- guest VA 到真正 PA 为什么是两段翻译
- 为什么 KVM 可以通过 stage-2 把某些地址标成 fault
- 为什么 MMIO 模拟常常从 stage-2 abort 开始
- `VMID` 为什么重要

## Phase 2：KVM 的退出路径，trap-and-emulate

目标：
- 理解 guest 为什么会退出到 KVM
- 理解 KVM 如何模拟 guest 不能直接做的操作

必读：
- virtualization guide
  - `5. Trapping and emulation of instructions`
  - `6. Virtualizing exceptions`

必须回查的 ARM ARM 章节：
- `Memory aborts` - 7829
- `The Exception model`
- `About the AArch64 System registers` - 8464 附近

重点关键词：
- `ESR_EL2`
- `FAR_EL2`
- `HPFAR_EL2`
- `HCR_EL2`
- `trap`
- `exception routing`
- `virtual exception`

KVM 视角怎么理解：
- guest 执行某些指令、访问某些系统寄存器、触发某些异常时会退出
- KVM 要靠 syndrome 信息判断“guest 刚才想做什么”
- 然后决定：
  - 直接拒绝
  - 软件模拟
  - 注入虚拟异常
  - 修正状态后重新进入 guest

读完后你应该能回答：
- 一次 guest exit 常见原因有哪些
- KVM 处理 trap 时最依赖哪几类寄存器
- “注入虚拟异常” 和 “物理异常发生在宿主机上” 有什么区别

## Phase 3：KVM 的时间和中断模型

目标：
- 搞清楚 KVM 不只是管 CPU 和内存，还必须虚拟化中断和时间

必读：
- virtualization guide
  - `7. Virtualizing the generic timers`
  - `6. Virtualizing exceptions`

推荐同步查：
- ARM ARM 中与 timer trap、counter/timer virtual access 相关寄存器
- 如果后面要深入中断，再补 GIC System registers / GIC architecture 文档

重点关键词：
- `CNTHCTL_EL2`
- `virtual timer`
- `physical timer`
- `virtual interrupt`
- `vCPU timer context`

KVM 视角怎么理解：
- guest 看到的是它自己的 timer/counter 视图
- KVM 需要决定哪些计时资源让 guest 直接看，哪些必须 trap
- timer 到期后，KVM 需要把结果表现成“这个 vCPU 收到了自己的虚拟中断”

读完后你应该能回答：
- 为什么 timer 虚拟化是 vCPU 级问题
- 为什么 timer 通常和 virtual interrupt 紧密耦合
- KVM 为什么需要保存/恢复 timer 相关状态

## Phase 4：理解为什么 ARM64 KVM 常提到 VHE

目标：
- 明白 VHE 不是“另一个 hypervisor”，而是让 hosted hypervisor 更顺手
- 理解它对 KVM 的工程意义

必读：
- virtualization guide
  - `8. Virtualization host extensions`

必须回查的 ARM ARM 章节：
- `Virtualization Host Extensions` - 7814
- 搜索 `FEAT_VHE`

重点关键词：
- `FEAT_VHE`
- `E2H`
- `TGE`
- `EL2 host view`

KVM 视角怎么理解：
- VHE 让宿主机内核在使用 EL2 时更自然
- 目的是降低 hosted hypervisor 的切换和管理复杂度
- 学 KVM 时，你需要知道“有 VHE 和没 VHE，宿主侧运行模型会不同”

读完后你应该能回答：
- VHE 主要解决的是什么问题
- 为什么 KVM/arm64 实现里经常区分 VHE / nVHE
- VHE 对宿主内核和 guest 的运行边界有什么影响

## Phase 5：第二轮再碰 nested virtualization

目标：
- 在你已经吃透基本 KVM 路径后，再理解“guest 里再跑 hypervisor”这个更难的问题

必读：
- virtualization guide
  - `9. Nested virtualization`

必须回查的 ARM ARM 章节：
- `Nested virtualization` - 7821
- 搜索：
  - `FEAT_NV2`
  - `FEAT_NV2p1`

为什么不要太早读：
- 这块建立在你已经理解 `EL2 状态管理 / trap / stage-2 / guest hypervisor illusion`
- 太早读容易把一层虚拟化和两层虚拟化混在一起

读完后你应该能回答：
- 为什么 nested virtualization 的难点是“伪造一个 EL2 环境给 guest hypervisor”
- Host hypervisor 和 Guest hypervisor 分别各自控制什么

## Phase 6：最后再读 Secure virtualization

目标：
- 把 Secure EL2 当成高级专题，不要混入 KVM 主线入门

必读：
- virtualization guide
  - `10. Secure virtualization`

必须回查的 ARM ARM 章节：
- 搜索 `FEAT_SEL2`
- 搜索 `Secure EL2`

为什么放最后：
- 这不是你理解普通 ARM64 KVM 主路径的前置条件
- 它更适合放到“TrustZone / secure world / isolation model”专题里

## 4. 一轮、二轮、三轮怎么读

## 第一轮：只求打通主路径

按这个顺序读：

1. `3. Virtualization in AArch64`
2. `4. Stage 2 translation`
3. `5. Trapping and emulation of instructions`
4. `6. Virtualizing exceptions`
5. `7. Virtualizing the generic timers`
6. `8. Virtualization host extensions`

第一轮目标不是“记住所有寄存器”，而是打通：

- guest 怎么进来
- 为什么会退出
- KVM 怎么控内存
- KVM 怎么控异常
- KVM 怎么控 timer

## 第二轮：回 ARM ARM 查机制细节

按这个顺序查：

1. `Translation process`
2. `Translation table descriptor formats`
3. `Memory aborts`
4. `Translation Lookaside Buffers`
5. `TLB maintenance`
6. `Virtualization Host Extensions`
7. `Nested virtualization`
8. `About the AArch64 System registers`

第二轮目标：

- 把 guide 里的概念替换成真正的架构术语
- 知道每个机制背后由哪些寄存器控制

## 第三轮：带着问题去读 KVM 代码

到这一步再去看 KVM 代码或设计资料，重点盯这些问题：

1. KVM 在哪里建立或更新 stage-2 映射
2. guest exit 后，KVM 如何根据 syndrome 分类处理
3. timer 状态在哪里切换
4. virtual interrupt 何时注入到 vCPU
5. VHE 和 non-VHE 路径为什么不同

你这时看代码，脑子里要能对应回：

- `HCR_EL2`
- `VTCR_EL2`
- `VTTBR_EL2`
- `ESR_EL2`
- `HPFAR_EL2`
- `CNTHCTL_EL2`

## 5. 最值得建立的 KVM 心智模型

学 ARM64 KVM，建议优先形成这 5 个心智模型：

1. `KVM 本质上是在 EL2 管理 guest 的受限执行环境。`
2. `Stage-2 是 ARM64 KVM 的核心控制面。`
3. `Trap-and-emulate 是 guest exit 的基础处理模型。`
4. `中断和 timer 是 vCPU 语义，不只是设备语义。`
5. `VHE / nVHE / Nested / SEL2 都是在主路径之上的变体。`

## 6. 不建议一开始就钻的内容

- `Nested virtualization`
- `Secure virtualization`
- 过细的 feature matrix
- AArch32 虚拟化兼容细节
- 各种很新的 stage-2 扩展权限特性

原因：
- 这些内容会拉高复杂度，但不先贡献主路径理解

## 7. 如果你下一步要继续深入

建议按这个顺序继续扩展：

1. `ARM64 KVM 主执行路径`
2. `ARM64 KVM 内存虚拟化与 stage-2 页表`
3. `ARM64 KVM trap/exit 分类`
4. `ARM64 KVM timer 虚拟化`
5. `ARM64 KVM 中断虚拟化（尤其是 GIC/vGIC）`
6. `ARM64 KVM 的 VHE / nVHE 区别`
7. `ARM64 KVM nested virtualization`

## 8. 配套文件

基础章节清单见：

- [arm64_虚拟化相关章节整理.md](/home/lyq/Projects/materials/virtualization/arm64_虚拟化相关章节整理.md)

这份文件和上面的清单关系是：

- `arm64_虚拟化相关章节整理.md`：告诉你“读哪些章”
- `arm64_KVM学习阅读地图.md`：告诉你“为什么按这个顺序读，以及每章在 KVM 里对应什么”
