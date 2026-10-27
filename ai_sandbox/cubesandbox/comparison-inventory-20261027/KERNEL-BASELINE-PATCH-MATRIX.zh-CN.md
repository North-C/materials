# 对比测试内核清单：源码基线与附加补丁

> **公开发布副本 · 2026-10-27**：报告数值、身份与限制保留；测试机地址脱敏，原工作区证据链接改为来源登记。原始日志、配置、149 条导航完整快照及本地索引未公开，读者不能仅用本包重算全部性能结果。发布范围和原件哈希见 [PUBLICATION.md](PUBLICATION.md)，两份报告入口见 [README.md](README.md)。

整理日期：2026-10-27。范围：本工作区 .90 的 c100n100 / TLBi 主线及其前置 stage-2 flush 对照，补充近期相关内核与恢复启动项。仅整理本地证据，没有访问远端、修改内核或新增测试；新增性能样本数为 **0**，不计算跨批次收益。

“基线”指添加本轮实验补丁前的源码版本；“无附加补丁”只表示没有再加本实验的补丁，不表示发行分支本身没有下游修改。测试状态描述已有归档，不是目标机实时状态。

## 1. 核心清单

下表commit先写短名，完整值见第2节。D/K1/K2/N/H等是实验代号，不能脱离所属实验仅凭一个字母辨认内核。

| 内核/测试代号 | `uname -r` / kernelrelease | 源码基线 | 在该基线上附加的补丁 | 已有记录与边界 |
|---|---|---|---|---|
| **K0：with-softdirty历史默认核** | `6.6.0-with-softdirty+` | 报告记为SP3自编译内核；**精确commit未知** | **完整补丁栈未确认**；不能只根据softdirty后缀推断全部改动，更不能与D等同 | 历史测试及P1/K0有实际计时记录。[E10] |
| **D：历史153.7ms所关联内核** | `6.6.0-9999.sp3.vnmi.xarray.d383a36d` | 原始 `openEuler-24.03-LTS-SP3` release tag，`1cefaec0` | 历史五文件combined.patch：vNMI/AP1R处理 + irqbypass list→XArray；关联本地提交短ID `d383a36d` | 历史实测来源；不含本次V2。153.7ms身份由历史报告与host-config关联，不是s13每轮自带uname证明。[E1][E2] |
| **K1：OLK无实验补丁基线** | `6.6.0-olk66base` | OLK-6.6，`512d487c` | 无本轮TLBi附加补丁 | 有构建、启动及P2–P4测试记录；不是只存在于计划。[E3] |
| **B：10月26日无TLBi对照** | `6.6.0-olk66base` | 同为OLK-6.6，`512d487c` | 不应用旧TLBi combined-port补丁 | 与K1同release/源码基点/无TLBi身份；未对两批实际启动image做逐字节核验，不直接声称同一个二进制。[E4] |
| **K2：旧版TLBi实验内核** | `6.6.0-olk66tlbi` | OLK-6.6，`512d487c` | `0001-tlbi-ipi-olk66-combined-port.patch`：旧版KVM stage-2 targeted IPI + lazy、host stage-1 targeted IPI、`fault_retry_hva`及对应OLK移植；另应用selftest补丁（不属于运行时优化） | 主线实际使用的旧TLBi版本；**不是**新版三个V2原件，也没有另行叠加D的五文件vNMI/irqbypass补丁。[E3][E4] |
| **OLK新版V2候选**（本文不给它擅自增加K3代号） | `6.6.0-olk66tlbiv2` | OLK-6.6，`512d487c` | 新版V2三个原件的OLK移植；从干净基线出发，**不是K2旧组合补丁再叠V2** | 构建与selftests编译完成；对应性能任务停在预检，不能写成已完成该内核性能测试。[E5][E6] |
| **N / N-off / N-on** | `6.6.0-sp3orig-tlbiv2` | 原始SP3 release tag `1cefaec0`，先重建历史D的补丁基线 | 原历史五文件vNMI/irqbypass combined.patch，再加新版V2三补丁 | 后续已有实际N组运行记录。N-off/on是同一内核的开关状态；没有混入后期SP3 s2flush补丁。[E2][E7] |
| **H / H-off / H-on** | `6.6.0-145334-vnmi-tlbiv2` | source tag `6.6.0-145.3.34`，`dfd87b8f` | 保留该tag原生irqbypass/XArray及新API；仅移植历史vNMI三文件子集，再加新版V2三补丁 | 后续已有实际H组运行记录。**未重打历史irqbypass部分**；不是N仅更换版本字符串。[E7][E8] |

### 1.1 前置SP3 / stage-2 flush对照与近期其他实测核

| 内核身份 | release | 源码基线及附加补丁 | 状态 |
|---|---|---|---|
| 后期SP3 vNMI基线，历史base | `6.6.0-sp3vnmibase` | 后期SP3分支头 `09859d13` + vNMI/irqbypass移植提交 `f28f9b347d72f4763dcd9b27e0d58a437f6d43fa` | 10月21日已测试；**不是原D/N基线**。[E1][E11] |
| 后期SP3 stage-2 flush候选 | `6.6.0-sp3vnmis2flush` | 上一行基线 + 修复提交 `3ff412747b34c7745fe895db7fbf15b0b081fa9d` + selftest提交 `fed469f1895e8282dbce1ed8e16ae5d82d4914a8` | 10月21日已测试。修复是解除实际有效叶子映射时才要求deferred TLBI，**不是V2定向IPI系列**。[E1][E11] |
| sbench / aprmask，无可靠统一短代号 | `6.6.0-sbench-irqbypass-xarray-v2-aprmask` | **源码commit与完整补丁栈未知**。名字中的 `xarray-v2` 不能当成已证实叠加了本文TLBi V2三补丁 | 10月26日热集/预读/预COW对照实际使用过；不并入D、N、H或PVM。[E12] |

### 1.2 已作废、仅启动项或未执行的候选

| 身份 | release/标识 | 已确认的基线/附加内容 | 为什么单列 |
|---|---|---|---|
| 首次SP3 base构建 | `6.6.0-sp3base+` | `09859d1307af3b7351ae32c27d99b5805f6b6ba0`；未加vNMI/irqbypass | 报告明确作废、仅留档、不用于测试，不能混入实测sp3vnmibase。[E1][E13] |
| 首次SP3 s2flush构建 | `6.6.0-sp3s2flush+` | 上述SP3分支基点 + deferred stage-2 flush修复；记录build commit `1aa28d03b31a05ec77424e554c82f93dcbd8b5dd` | 同样作废，不是后来实测的sp3vnmis2flush。[E1][E13] |
| PVM永久默认启动核 | `6.6.0-lw-pvm-defconfig-1023+` | **源码commit/完整补丁未知**；grubby与grubenv确认精确启动项 | 测试时保护的默认恢复目标，没有把它作为本表正式内核性能组的充分证据。[E6] |
| 早期PVM拓扑诊断核 | `6.6.0-lw-pvm-noconfigkvmpvm-l1++` | **源码commit/完整补丁未知** | 配置/CPU数量诊断身份，不与上一行默认PVM核混同；也不据拓扑快照生成性能样本。[E14] |
| .61原内核复现候选 | `6.6.0+` | **源码commit/完整补丁未知**；GRUB中的LTS-SP1标题不足以确认源码 | 原内核/K2跨机复现计划受阻，原内核benchmark为0轮。[E15] |
| 145.3.34.165映射核对 | source tag `6.6.0-145.3.34`，无本次构建uname | `dfd87b8f` + 三个V2原件；独立index检查 | 仅静态应用核对，没有为该纯tag组合另建包或运行；不要与另加vNMI的H混同。[E9] |

`.140` 的 `6.6.0-132.0.0.111.oe2403sp3.aarch64` 是构建/自测宿主环境身份；其他主机的裸 `6.6.0` 记录也不能仅凭字符串提升为新的内核对照处理组。guest内核、PVM虚拟机名与本表host内核另行区分。

### 不能从名称得出的结论

- `olk66tlbi` 与 `olk66tlbiv2` 是不同补丁实现，不是同一个包的开关名。
- K1/B与K2同基点，但D/N与K2不是同基点。H又属于另一个tag。
- **H与N同时改变了源码基线和irqbypass实现，差异不能单独归因于V2。**
- 构建metadata中的 `kernel_booted=false` 只记录构建交付时；不能据此否定后来N/H的运行归档。
- K1/K2使用过从 `config-6.6.0-sp3vnmibase` 派生的配置，不代表它们的源码基线也是SP3；其源码仍是OLK `512d487c`。配置来源和源码来源应分两列理解。
- 某组曾完成100/100请求不等于该内核通过所有正确性门禁；中止、模板问题和不同测试条件仍以原报告为准。

## 2. 四组必须区分的源码身份

| 源码身份 | 完整commit | 用途 |
|---|---|---|
| 原SP3 release tag `openEuler-24.03-LTS-SP3` | `1cefaec0de176ec513c09153d3bd3dd5d60e10a0` | D的基础，以及N重建的起点 |
| 后期SP3分支头 | `09859d1307af3b7351ae32c27d99b5805f6b6ba0` | 后述sp3vnmibase / sp3vnmis2flush；**不能替代原153.7ms基点** |
| 本批OLK-6.6基点 | `512d487ca736f24c8167b297c62fd1f65406e114` | K1/B、K2、OLK新版V2候选 |
| source tag `6.6.0-145.3.34` | `dfd87b8f89d1007136786ea633e421c37131afc4` | H及V2原件干净应用核对 |

发行版本 `6.6.0-145.3.34.165` 的映射是：src-openeuler/kernel打包commit `b9a808ba4c9891f69c5dce6d7fb0fda8cb75f9ed` → `SOURCE=6.6.0-145.3.34`；`.165` 是 `pkg_release`，不是另一个kernel source tag。[E9]

N的历史重建保真边界：未取得原 `d383a36d` 完整提交对象，采用准确release tag + 原combined.patch + 历史config重建；五个改动文件的前后blob前缀全部匹配，重建tree为 `d800cb5e76e42c359fc7f233bc5c444f6b6e15ef`。这是有证据的源码重建，不是原历史完整tree或二进制可复现认证。[E2]

## 3. 附加补丁究竟是什么

### 3.1 历史vNMI / irqbypass五文件combined.patch

文件：`sp3-vnmi-irqbypass-xarray-combined.patch`。

SHA256：`6dbf5fd71dff0bbfa1424e6457ccb40a881c025024a530abf42e70b565ed2473`。

- vNMI三文件：`arch/arm64/include/asm/kvm_hyp.h`、`arch/arm64/kvm/arm.c`、`arch/arm64/kvm/hyp/vgic-v3-sr.c`。
- 内容：按guest是否选择vNMI决定AP1R保存/恢复宽度，移除过早的VM `pfr1_nmi` 初始化。
- irqbypass两文件：`include/linux/irqbypass.h`、`virt/lib/irqbypass.c`，历史list→XArray转换。
- **D、N使用五文件；H仅取三文件vNMI部分。** H基线已包含演进后的XArray、typed eventfd API及双向配对状态，不能用历史实现覆盖。

H子集原始SHA：`1f6e371c2d2ccdd292d44f07deb7f6fadccc53423b4f0cec1b06c0424ea3b0ee`；上下文适配后SHA：`1d0f970c9512fd96ef1d622b6f4023d5b4323204d55234a807cd60f5f0d96096`。增删内容保持原样，arm.c保留Realm timer初始化。[E8]

### 3.2 K2旧TLBi组合与附件

实际内核补丁是 `0001-tlbi-ipi-olk66-combined-port.patch`。

归档中的其他patch不能一概写成“都编进内核”：

- `0007-port-tlbflush-to-olk66.patch`：审阅用，**不是本次构建叠加项**。
- `0003-KVM-selftests-arm64-Add-s2_unmap_tlbi_test.patch`：K2源码树另行应用的测试程序补丁，不包含于0001生产补丁；必须与运行内核补丁区分，不能算成新增运行时优化。
- 旧TLBi相关功能开关或 `fault_retry_hva` 的开/关是运行条件，不能替代实际patch记录。

具体来源以K2构建元数据和归档说明为准；不因目录里存在一个patch就认定它已应用。[E3][E4]

### 3.3 新版V2三个原件

| 顺序 | 原件 | 功能 | SHA256 |
|---|---|---|---|
| 1 | `0001-KVM-arm64-targeted-stage-2-range-invalidation-by-IPI.patch` | KVM stage-2定向范围失效，同步IPI及本地失效路径 | `9375c0a60a7f1edf75ac06ee3b614e9f7f1e8ff94c43759a8e7c125060de5374` |
| 2 | `0002-KVM-arm64-tlbi_ipi-lazy-mode-only-IPI-CPUs-with-a-lo.patch` | stage-2 lazy tracking / generation及load、put、entry协作 | `2b4ccec6fce4b30165a13eadafa951f7e333218a6bf4caffe29f112208d45516` |
| 3 | `0003-arm64-targeted-host-stage-1-TLB-invalidation-by-IPI.patch` | host stage-1定向失效、CPU tracking、操作位与统计 | `f9266437ad3c8c930ad1a875d5f6a49f5702876e5bcb09e3e397e9f811ce154b` |

三个交付都源自同一组原件，但移植差别必须记录：

| 交付 | 适配说明 |
|---|---|
| OLK V2 | 保留OLK PVM对象、LOCAL/DOMAIN/BROADCAST scope、flush尾部和notifier；`tlbflush.h`存在OLK scope适配，不宜声称所有新增/删除行都与原件逐字相同。 |
| N | patch1的 `pgtable.c` 仅做上下文适配，保留旧分块与广播回退；三补丁全部增删代码行与原件一致。 |
| H | vNMI的arm.c只适配上下文。V2原件未修改；因前置删除375–377行，patch1/2的四个arm.c hunk有可证明的-3行偏移，其他文件无偏移；混合arm.c与V2-only相比恰好只少那三行。 |

“V2三补丁在145.3.34纯tag上无冲突”与“H先叠vNMI后出现-3行偏移”并不矛盾。前者是纯tag验证，后者已有前置源码删除。[E5][E8][E9]

## 4. 运行组不是另一套内核补丁

- K2的S0/S1/S2/S3描述同一 `olk66tlbi` 的不同开关组合；记录中S3使用stage-2 IPI与lazy开启、host flags=31。不能据此把K2称为V2。
- N-off/N-on、H-off/H-on（以及后续N2/H2等阶段标签）仍分别是N/H内核；数字和后缀也可能表示重复批次，不是新源码commit。
- 新V2开关默认关闭仍可能有CPU tracking/hooks成本，所以V2-off不是严格的未打补丁基线。
- 旧K2用过flags31不代表可以对新版V2照搬。新版交付限制保留：host初步评估只取0或3；SWITCH/MM/host-LAZY/BROKEN不纳入普通测试。stage-2 lazy与host LAZY不是一个开关。
- `B` 也用于用户态组件版本，热集实验的 `H` 也可能代表预热组；必须同时看release、报告路径及测试条件，不能把字母机械关联为内核。
- MADV_RANDOM、dirty_log、THP、NUMA balancing、HugePages、模板T1/T2、磁盘、Shim/Hypervisor补丁及profile/预写入都是额外对照条件；它们不自动等于附加Linux内核补丁。

## 5. 新版交付包的身份辅助核验

| 内核 | 主RPM SHA256 |
|---|---|
| OLK V2 | `0e267348618e506e761e95c32aeab4109ca51da31b2e12c82461dfe9ed1ffeef` |
| N | `947298975b21a5874c43b85edc9d37cb663097a00dcc811836e88adda0031911` |
| H | `4efdebfd6991891c4e5347964538dd204c03b1252159ecb919d34154d9d56f49` |

这些是已交付RPM的哈希，不自动证明每个后续测试轮次实际启动的vmlinuz相同。追溯具体轮次仍需其启动回读、boot ID、image或包身份记录。

## 6. 主要证据入口

- **E1**：[历史stage-2 flush记录与原SP3基点区分（来源登记，原件未公开）](PUBLICATION.md#source-055)；[历史调优主报告（来源登记，原件未公开）](PUBLICATION.md#source-004)。
- **E2**：[N构建报告（来源登记，原件未公开）](PUBLICATION.md#source-056) §2–3；[N元数据（来源登记，原件未公开）](PUBLICATION.md#source-057)。
- **E3**：[主线TEST-PLAN（来源登记，原件未公开）](PUBLICATION.md#source-058)；[P2–P4简报（来源登记，原件未公开）](PUBLICATION.md#source-059)；[K1/K2构建元数据（来源登记，原件未公开）](PUBLICATION.md#source-060)；[P2–P4第二次执行核对（来源登记，原件未公开）](PUBLICATION.md#source-061)。
- **E4**：[10月26日归档（来源登记，原件未公开）](PUBLICATION.md#source-037) §4；[旧盘主线delivery-02（来源登记，原件未公开）](PUBLICATION.md#source-034) §6。
- **E5**：[OLK新版V2构建报告（来源登记，原件未公开）](PUBLICATION.md#source-062) §原始来源与基点、移植与配置；[元数据（来源登记，原件未公开）](PUBLICATION.md#source-063)。
- **E6**：[OLK新版V2性能任务停止记录（来源登记，原件未公开）](PUBLICATION.md#source-064)。
- **E7**：[N/H后续旧盘运行记录（来源登记，原件未公开）](PUBLICATION.md#source-033)；[N内核对照首批报告（来源登记，原件未公开）](PUBLICATION.md#source-065)。
- **E8**：[H构建报告（来源登记，原件未公开）](PUBLICATION.md#source-066)；[H元数据（来源登记，原件未公开）](PUBLICATION.md#source-067)；[原冲突逐hunk说明（来源登记，原件未公开）](PUBLICATION.md#source-068)。
- **E9**：[145.3.34.165版本映射与纯V2干净应用核对（来源登记，原件未公开）](PUBLICATION.md#source-069)。
- **E10**：[SP3/with-softdirty分析（来源登记，原件未公开）](PUBLICATION.md#source-070) 第13–14行；[P1/K0与后续矩阵分析（来源登记，原件未公开）](PUBLICATION.md#source-071) 第9–12行；E3 TEST-PLAN第42行。
- **E11**：[后期SP3 vNMI/s2flush构建报告（来源登记，原件未公开）](PUBLICATION.md#source-072) 第7–20、34–47行；实际运行状态见E1第155–167行。
- **E12**：[10月26日热集预热分析（来源登记，原件未公开）](PUBLICATION.md#source-038) 第185行记录完整sbench release；其来源缺口保留。
- **E13**：[作废初版base commit（来源登记，原件未公开）](PUBLICATION.md#source-073)；[作废初版s2flush commit（来源登记，原件未公开）](PUBLICATION.md#source-074)；作废声明见E1第68–77行。
- **E14**：[CPU 256/384诊断（来源登记，原件未公开）](PUBLICATION.md#source-075) 第11–19行明确两次boot的release与配置差异，仅用于身份/拓扑，不作性能结论。
- **E15**：[P10 .61原内核/K2复现停止报告（来源登记，原件未公开）](PUBLICATION.md#source-076) 第30–34、48行。
- **K2补充**：[P0A构建报告（来源登记，原件未公开）](PUBLICATION.md#source-077) 第13–28行区分完整生产补丁、selftest、0007；[机制文档（来源登记，原件未公开）](PUBLICATION.md#source-078) 第108–122行区分K2与V2的fault_retry_hva。

## 7. 尚未关闭的来源缺口

1. K0/with-softdirty、PVM两种release、sbench、.61原核的完整source commit与补丁栈尚未由本次本地材料确认。名字中含某特性不构成应用证据。
2. D缺原完整提交对象及与N重建tree的全树独立比对；N采用的历史五文件blob匹配证据应与该限制一起引用。
3. K1与B虽然文档身份相符，本次没有核对跨批次启动镜像SHA；不擅自合并成同一二进制。
4. 此清单不是整个workspace所有主机、所有guest镜像的无限穷举。凡没有具体内核对照身份的构建宿主、普通配置快照和VM名字，不新增为实验内核。

本报告及导航记录只作来源清单，不修改各实验的判定、样本和成功/失败状态。
