# CubeSandbox 测试二进制—生效补丁—内核—性能清单

> **公开发布副本 · 2026-10-27**：报告数值、身份与限制保留；测试机地址脱敏，原工作区证据链接改为来源登记。原始日志、配置、149 条导航完整快照及本地索引未公开，读者不能仅用本包重算全部性能结果。发布范围和原件哈希见 [PUBLICATION.md](PUBLICATION.md)，两份报告入口见 [README.md](README.md)。

- 整理日期：**2026-10-27**。范围：本 workspace 截至整理时已归档的 10-16～10-27 材料，以 .90 ARM64 创建性能主线为主，兼列暂停/恢复、历史诊断、构建交付及 x86 边界。
- 原工作区完成状态：**清单整理及两级索引同步完成**；来源不明、仅构建、受干扰和中止项仍保留原限制，不因本次归档变为已验证。
- 性质：**本地证据汇编，不是新实验**；本次新增性能样本数 **0**，没有登录目标机、替换组件或发起负载。不将历史部署记录当作远端当前状态。
- 目的：回答“测的是哪一份二进制，哪些 CubeSandbox 补丁编进去了、哪些在该轮真正用上了，配合哪一个内核，结果如何”。不是把每次最小耗时串成累计优化收益。
- 未公开的原工作区导航快照登记：[source-records.json（来源登记，原件未公开）](PUBLICATION.md#source-002)；未公开的逐项检索表登记：[CATALOG-ROWS.zh-CN.md（来源登记，原件未公开）](PUBLICATION.md#source-003)。附表包含诊断/构建/失败记录，**不代表其中每条都已测出性能**。
- 内核源码与附加补丁的完整展开请并读：[内核基线与补丁清单](KERNEL-BASELINE-PATCH-MATRIX.zh-CN.md)。本篇重点是用户态二进制及其实际运行组合。

## 1. 怎样读这份清单

### 1.1 四层证据不能混为一谈

| 层级 | 能证明什么 | 不能证明什么 |
|---|---|---|
| 源码 commit / diff | 候选源码含某补丁 | 已构建、已部署、已执行 |
| 构建 manifest + 二进制 SHA256 | 某次构建产物的身份 | 模板恢复时实际选中了这一份 |
| 部署回读 + VMM 版本日志 | 对应路径/实例实际跑了该版本 | 该补丁的条件分支必然执行 |
| 开关回读、profile/页列表、运行日志或内核计数器 | 特定机制在该次实验确实进入 | 单个补丁的独立因果收益，或其他内核/模板也有收益 |

**同一二进制可以有 off/on 两种有效配置；不同二进制也可能沿用相同版本字符串。** 本文优先用 SHA256 识别文件，用 commit 解释来源，用运行证据判断生效。

`.90` 模板恢复还受 `component_versions` 钉版本影响：要核对 `cube-shim/bin`、`/usr/local/bin/containerd-shim-cube-rs` 的实际目标、`component_versions/cube-shim/v0.7.1/bin`。只替换服务默认位置不能证明模板用了新 shim。cube-runtime 同样要配套核对。

### 1.2 统一的指标及比较边界

- 下文未另标时，指标为 **c100n100 create-only 整轮耗时中位数，单位 ms**，来自 `summary.total_time_s × 1000`；不是单实例平均、P50，也不是除以 100 后的时间。
- 10-25 起主线通常每组五轮、同进程 `-w 3`、Bash 直接启动 cube-bench。更早三轮、独立进程预热、profiler、诊断挂载均单独标记。
- 热缓存、冷缓存、大 folio 历史、模板 ID、CPU 数/内核、THP/NUMA/HugeTLB/swap、dirty_log、数据盘和并发规格都会影响结果。**“同为 v0.7.1”或“同为 K2”不是可比较的充分条件。**
- “五轮区间分离”沿用实验记录的描述性判据，不等同于正式显著性检验；区间重叠时可以报中位数，但不能写成已证实的稳定收益。
- 用于 profile、自动学习、warmup 的实例不计入正式性能轮数。失败、中断、污染轮保留证据，但不作为合格的五轮组。
- 未找到逐文件完整 SHA 的历史组，保留“未归档/未核实”，不拿同名文件的新构建 SHA 补填。

## 2. 先区分源码家族：original 也已经有补丁

`86f6d9b9` 是 Boostkit v0.7.1 的实验基线，不是“未优化的社区最初版本”。本地 Git first-parent 记录可见：

| 基线中已有提交 | 内容 | 生效判断 |
|---|---|---|
| `53acc6f0` / !20 | NUMA 修正 | 部分后续实验专门回退它；不能把回退 B 与 original 混为一个版本 |
| `03f99689` / !21 | aarch64 virtio-console / hvc0 | 代码存在；模板/guest 启动配置及 VMM 日志仍要匹配，不是 x86 收益证据 |
| `1920a049` / !27 | AppSnapshot 内存冻结前 settle gate | 主要在建模板/快照路径，不是每次 create 都执行 |
| `366dd0a5` / !28 | 把 pause VM teardown 移出暂停关键路径 | 暂停路径优化；create-only 不直接衡量它的收益 |
| `32004501` / !29 | freeze 时保留 agent 连接，restore 时重连 | 暂停/恢复路径，不应把其收益归给内存预热 |
| `86f6d9b9` / !32 | 基于 KVM dirty log 写暂停快照，host opt-in | 需要 dirty-log 开关和基镜像前提；“编进来了”不等于所有测试都开着 |

`2babb6f7` 在这个基线上再包含 `319ca90d` 的测试串行化修正；hotset 和自动学习 prewrite 都基于它，但彼此是**不同候选分支**，不是一个连续累加的优化包。

> 基线谱系仅列与本轮性能解释相关的补丁，不声称列出仓库全部功能提交；具体构建与实际开关见后续表格。源码谱系证据保存在本目录 `base-lineage.txt`。

## 3. 10-16～24 历史二进制家族和对比结果

本节 S/R/L 分别指 shim / cube-runtime / cubelet；SHA 表示 **二进制 SHA256 前缀**，不是源码 commit。旧 SP3=`6.6.0-9999.sp3.vnmi.xarray.d383a36d`；K0=`6.6.0-with-softdirty+`；K1/K2=`6.6.0-olk66base` / `6.6.0-olk66tlbi`。旧 SP3/K0 的完整源码身份未在这些历史组中闭合，不按名字推断。

### 3.1 组件身份与生效证据

| ID / 日期 | 源码与实际二进制 | 包含且实际有效的部分 | 内核 / 证据 |
|---|---|---|---|
| E0：10-16 原版→本地 Shim A/B/C | 基线 `31d911e4`；原 S `8d2b467e19c1`，A `6cf0887c3a2c`，B `15ed01bc10af`，C `67d8d06a6f26`；A/B/C 为未提交补丁；实际 R 一直 `10dced40e92c` | A cmdline alias，新 warn 模板验证日志改变；B 加 HUGEPAGE/POPULATE_READ，但 s11/s12 的 populate **关闭**；C 加 MADV_RANDOM，`snap_madv_random` 文件开、populate 关，日志确认 applied/失败0 | 旧 SP3；[报告（来源登记，原件未公开）](PUBLICATION.md#source-004)、[构建与部署身份（来源登记，原件未公开）](PUBLICATION.md#source-005) |
| E1：10-18 独立 alias PR3 | `31d911e4`→`6d46a781`；S `993f9213c002`、R `14ec82f2060f`；对照原 S `8d2b467e19c1`、L `6814fadeec55` | 只加 cmdline alias，不含 MADV；新 Tw 实读 `agent.log=warn`，旧模板不会自动改变冻结的 guest 行为 | K0；[构建（来源登记，原件未公开）](PUBLICATION.md#source-006)、[报告（来源登记，原件未公开）](PUBLICATION.md#source-007) |
| E2：10-18/19 独立 MADV PR4 | `999e115a`，基于 `31d911e4`；S `c887a2ebcae5`、R `76803184bd80`；**不是 E0 Shim C，也未叠加 PR3** | 环境 `CUBE_FILE_BACKED_MEMORY_MADV_RANDOM=0/1`，四类 VMA `rr` 0/4→4/4；Tw 的 warn 来自此前冻结模板，而非此 shim 含 alias | K0；[构建（来源登记，原件未公开）](PUBLICATION.md#source-008)、[MADV×RCU（来源登记，原件未公开）](PUBLICATION.md#source-009)、[shim-switch（来源登记，原件未公开）](PUBLICATION.md#source-010) |
| E3：10-19 UTC / 10-20 本地，PR4+hvc0 | `b71b796c` = `999e115a` + console；S `8c375e9cd232`；R **仍为 `76803184bd80`**，新构建 `dd488054e059` 未部署；L `05fd2f62c8e0` | 新模板 hvc0 生效，保留 earlycon/INFO；正式 U/H/W **都用新 shim 恢复**。c1 user-MMIO 1811→2、PL011 1651→0；不能称旧/新 shim 纯二进制 A/B | K0；[报告与运行哈希（来源登记，原件未公开）](PUBLICATION.md#source-011) |
| E4：10-20 独立 PR14 vsock | S0=`e8b9897a`，S14=`6db89302`；S `56859c92acf6`→`6f430bd47445`，固定 L `05fd2f62c8e0` | epoll 无限等待→20 ms 超时重扫。部署 SHA 已验证；模板 EVENT_IDX bit29=0。动态 timeout 命中探针未执行，只有静态调用链证据 | 该批独立 uname **未核实**，不从相邻日期推断 K0；[报告（来源登记，原件未公开）](PUBLICATION.md#source-012)、[入场身份（来源登记，原件未公开）](PUBLICATION.md#source-013) |
| E5：10-23 P6-61 PR18 hvc0 | 基线 `31d911e4`，head `43687e09`，tree `efea7827d7ee`；S/R `09ee1e883b9d` / `c6b4d426e7fd` | tty 模板构建借 PR15 包的未修改 S/R `30b3ee55162e` / `196f61738674`，**未部署 PR15 Cubelet**；正式统一 PR18 S/R。`/proc/consoles` 确认；c1 MMIO 1748→2 | .61 `6.6.0+`；[报告（来源登记，原件未公开）](PUBLICATION.md#source-014) |
| E6：10-22～24 原版 O | `86f6d9b`，S/R/L `4bd6b073…` / `29149efc…` / `aeddef5d…`，完整 SHA 见 §4 | 已有 hvc0/NUMA 等基线补丁；T0/T1 的 envd `-isnotfc` 是启动方式差异，不是另换 envd 程序；TLBi 独立诊断轮有实际计数增量 | K0、K1、K2 多组；[早期白名单结果（来源登记，原件未公开）](PUBLICATION.md#source-015)、[正确性审查（来源登记，原件未公开）](PUBLICATION.md#source-016) |
| E7：10-23 P8 四 PR 合包 | `31d911e4` + PR14/15/17/18；无新 merge commit，tree `6263e2d5f119`；S `ea8ec21caed6`、R `fffb9df865ac`、L `a17ab02cdb01` | vsock20ms + AppSnapshot settle + MADV + hvc0。MADV env=1、rr；T1p hvc0/isnotfc。settle 默认开，无覆盖，但未测实际等待时长。其余组件/guest 保留86f6d9b，属**混合部署** | K2/S3，THP always、NUMA1；[报告（来源登记，原件未公开）](PUBLICATION.md#source-017)、[合包 manifest（来源登记，原件未公开）](PUBLICATION.md#source-018) |
| E8：10-24 PR20 全量回退 B | `86f6d9b` 回退 merge `53acc6f0`；tree `b8822f82fe3c`；S `26fa02610c96`、L `c30538e42d22`，R `29149efc…` | 完整撤销 early host-cgroup join、affinity reset、Cubelet annotation 等，**不只是删一个 join 函数**。六路径哈希验收 | K2/S3，THP never、NUMA0、dirty_log true、swap off；[回退范围（来源登记，原件未公开）](PUBLICATION.md#source-019)、[接受轮次（来源登记，原件未公开）](PUBLICATION.md#source-020) |
| E9：10-24 精确 B+FD-only | E8 + PR37 `8536a7dd`，tree `0bf5fd27282b`；**只换 L=`44cb40fa5ad9`**，S/R/CLI 保持 B | `parentExit()` 后 `App()` 前 `ReserveFDTable(8192)`；实际 FDSize **4096→8192→4096**。无 PR36，未使用 PR36+37 混合包 cubelet | K2/S3，TAP525；[FD 报告（来源登记，原件未公开）](PUBLICATION.md#source-021) |

### 3.2 对应性能与有效结论

| 家族 / 对照 | 样本数与结果（ms） | 能说明什么 / 不能说明什么 |
|---|---|---|
| E0 顺序调优 | 每状态5轮：原版 s00 283.6→宿主调优 s03 227.5；A原模板223.8→warn183.8；B PMD/4K缓存177.6/153.8；C s13 **153.7** | 绑核、RCU、缓存与模板均变；不能把283.6→153.7全部归因MADV_RANDOM |
| E1 alias | 各5轮：原版T0 **308.710**，PR3 T0 **308.387**，PR3 Tw **195.059**、复测187.681；重建默认模板529.138/529.678 | 默认行为无明显改善；warn模板较快但冻结状态影响大，不是alias单独代码收益 |
| E2 MADV off/on | 各5轮：T0 **313.292/301.583**，回切310.331/310.483；Tw **192.234/182.633**，回切195.585/186.930 | NUMA缓存落点/长尾波动明显，未确认稳定通用收益 |
| E2 MADV×RCU 受控复测 | 每状态12轮、4区组；M0R0/M1R0/M0R1/M1R1 **197.707/192.134/187.061/176.700** | 后置锚点有反转；不能与上行混合计算。另 shim-switch 三轮中位189.823，诊断抓取轮198.052单列 |
| E3 hvc0 模板 | U/H各3轮 **307.238→188.300**；W另3轮405.750，正式900请求全成功 | 机制上 PL011/MMIO 大幅下降有证据；所谓旧warn模板实际无warn、仍INFO，不能作为warn对照 |
| E4 PR14 | 各5轮整轮**均值**（不是中位）：**190.724→187.898**；差−2.826，95% CI [−15.074,9.422] | 无可信提速证据；未复现目标vsock长停顿。100 VM idle/c1/T-U性能未测，共享机器变更后中止 |
| E5 P6-61 | tty有效2轮 / hvc有效3轮，中位 **929.991→813.069**；第六轮干扰排除 | 计划5×5未完成，模板构建有外来活动，不能称严格控制台单因素收益；c1机制样本各1次 |
| E6 早期内核矩阵 T1 | 各5轮：K0 **247.793**；K1 **298.403**；K2 S0 **277.975**、S1(stage2+lazy) **209.235**、S1e(nonlazy) **220.067**、S2(host31) **271.313**、S3两侧 **182.922** | attempt2白名单预览，非最终完整导出验收；attempt1正确性失败独立保留；这些是内核/开关比较，不是换了CubeSandbox二进制 |
| E7 P8 四PR合包 | 3轮 **224.524 / 223.459 / 177.198**，中位 **223.459**，300/0 | 组件基点、模板、背景不同，不能对历史182.922算某一PR回退或收益 |
| E6 后续磁盘/策略变化 | 各3轮：旧盘T1 **155.876**，新盘P11 **249.632**，后续swapoff **176.054** | 仍是O家族；盘、时间、内存策略改变，不作二进制或磁盘单因素收益；[旧盘（来源登记，原件未公开）](PUBLICATION.md#source-022)、[新盘（来源登记，原件未公开）](PUBLICATION.md#source-023) |
| E8 PR20回退 A1→B | 普通各3轮 **205.077→194.479**；profiler另各3轮 **239.773→202.019** | A2回转部署门禁受干扰，**没有A2成绩**；A1是保留stdout，非完整raw JSON；不能宣称可逆单PR收益 |
| E9 FD-only B→FD→B | 各3轮 **174.702→203.044→188.746**，900/0 | FD比前/后B分别慢16.22%/7.58%，**未观察到提速**；B本身漂移8.04%。这不是PR36+37混合包效果 |

10-25 白天旧 Python runner 组与后续 Bash 修正组须分开；父进程启动方式关联的40–85ms Go STW曾被诊断捕获，不能据此把所有历史差值自动“校正”成某个补丁收益。Profiler 也不能与普通计时混池。

### 3.3 构建了但不能冒领实测成绩的包

| 包 | 确认身份 | 限制 |
|---|---|---|
| 10-20 PR14/15/17/18 单包 | 基线31d911e4；head `6db89302/11099327/999e115a/43687e09`；各shim `f239895430c2/30b3ee55162e/6052faed35db/09ee1e883b9d` | `f239…`不是E4的`6f430…`；`6052…`不是E2的`c887…`。仅后续确有使用证据的组件在E5/E7列出；[构建说明（来源登记，原件未公开）](PUBLICATION.md#source-024) |
| 86f6d9b hvc0-base / ttyAMA0-revert | 逆向`d700ed39`；base S/R `4bd6…/2914…`，revert `9ea40ae0d80c/1a1fb277e5e8` | 构建/单测通过，无该构建对的guest性能验证，不能挂E5成绩；[报告（来源登记，原件未公开）](PUBLICATION.md#source-025) |
| PR36+PR37 TAP/FD混合包 | 与E9精确B+FD不同的构建 | 不得将FD-only三阶段结果套给混合包；[构建记录（来源登记，原件未公开）](PUBLICATION.md#source-026) |
| 10-22上午 isnotfc 单轮 | 整轮794.201ms，100/0；Cubelet `6814fadeec55`，运行shim身份未闭合 | 不能按日期套上稍后发布的86f6d9b；没有同期旧模板A/B；[记录（来源登记，原件未公开）](PUBLICATION.md#source-027) |

PR编号必须连同仓库/分支解释：早期 fork PR4 MADV 与后来的 Boostkit PR17 可能是同一功能提交，但不同构建 SHA 不能互换；早期本地 Shim A/B/C 的文件开关也不等于环境变量版 MADV。


## 4. 10-25～26 旧盘主线：original / stack / kit 与内核组合

### 4.1 真正运行过的三套组件

| ID | 源码身份 | 实际组件（SHA256 前缀） | 补丁和生效条件 |
|---|---|---|---|
| O：original | `86f6d9b9e20015706c2da0f2604b5731015bfc2f`，tree `e7b0a97b8b00922885a7a6c3ae1ae9d935757b0f` | cubelet `aeddef5d…`、master `167a966b…`、shim `4bd6b073…`、runtime `29149efc…` | 已含 §2 的补丁。该批 T1 已为 hvc0，settle 在建模板时执行；默认组 dirty_log=true，150cfg=false。没有下述 stack 四个增量 |
| S：stack | `86f6d9b` + staged tree **`e74d49d6d2b7277f6342cf4c3aebbdd9debc70ba`**；无新 commit 对象 | shim `46aa8dc5…`、runtime `2cffdc60…`；cubelet/master 仍为 O | 叠加下表四项。MADV_RANDOM 和 prewrite 默认关，必须逐项记录开关；不能称每轮“四项全开” |
| P：kit | 版本字符串 `v0.7.1-v2-gicfix`，基点 `31d911e4` 的预编译 shim + `0007` 实验预写入补丁 | shim **`13970933…`**；runtime 仍是 O 的 **`29149efc…`**，cubelet/master 仍是 O | **混合组件部署**，不是整个系统切到 31d911e4。可核实预写开关和运行日志；kit 完整 final tree/全部历史 gicfix 附加改动未被现有 manifest 完整证明，不把 stack 四项或 O 的全部 Shim 补丁自动套给它 |

**Stack 的四个增量：**

| 补丁 | 源码提交 | 编入后何时有效 / 证据边界 |
|---|---|---|
| 跳过 aarch64 vGIC 恢复限定零值 SET ioctl | `89a9c812` | 无开关，限 fresh-vGIC 和 allowlist 零值；非零及部分寄存器仍执行。对 v0.7.1 接口做最小适配，**未加入 `14a5a6f8` GET/ICC 修正** |
| PR14 vsock epoll idle timeout 20 ms 重扫 | `6db89302` | 无开关；不是保证所有 RPC 延迟小于 20 ms |
| PR17 文件内存映射 MADV_RANDOM | `999e115a` | 实际 shim 环境须有 `CUBE_FILE_BACKED_MEMORY_MADV_RANDOM=1`；默认 stack 行不启用 |
| 实验静态页列表预写入 | `3040594f` | `/run/cube-prewrite/enabled` 为 `1` 且 pages 可读；该主线 T1 列表 **1361 页 / 950 段**。这不是后来的 `conf/prewrite=auto` 自动学习方案 |

无开关项有“源码→构建树→运行 SHA”链条，但没有每轮专门统计 ioctl 跳过数或重扫次数，所以只写“包含且适用路径默认启用”，不伪称每个分支都被逐事件计数验证。Kit on 日志明确出现 `prewrite: 1361 pages in 950 ranges (0 failed)`；off 无此日志。页表绑定 T1，换模板必须重采，`/run` 下文件重启后须重建。

来源：[补丁栈报告（来源登记，原件未公开）](PUBLICATION.md#source-028)、[stack 构建 manifest（来源登记，原件未公开）](PUBLICATION.md#source-029)、[原版运行身份（来源登记，原件未公开）](PUBLICATION.md#source-030)、[stack MADV=1 身份（来源登记，原件未公开）](PUBLICATION.md#source-031)、[kit 开关对照（来源登记，原件未公开）](PUBLICATION.md#source-032)。

注意：stack manifest 的 `runtime_tested=false` 是**构建交付当时**的状态；后来上述运行记录证明 stack 已部署测试。不能仅看旧 manifest 就否认后续实测，也不能反过来修改历史构建状态。

### 4.2 配合的是哪个内核

| 本批代号 | 完整 uname / 基点 | 本批运行方式 |
|---|---|---|
| K2 / K2r / K2r2 | **`6.6.0-olk66tlbi`**；OLK `512d487c` + 旧 combined TLBi 移植 | S3：IPI Y、lazy Y、host flags31；retry/fixed/stats 关。r/r2 是重启/回测标签，**不是 V2 新补丁** |
| B（无 TLBi） | **`6.6.0-olk66base`**；同 `512d487c` 基点，不打上述 TLBi | 无旧 TLBi 开关；用作同 boot 原版/kit 对照。不能与别的 uname 缩写 B 混淆 |
| N / N2 | **`6.6.0-sp3orig-tlbiv2`**；SP3 tag `1cefaec0` | 重建历史 vNMI/irqbypass 五文件再加 V2 三项；off=N/N/0，S2lazy=Y/Y/0，full=Y/Y/3 |
| H / H2 | **`6.6.0-145334-vnmi-tlbiv2`**；145.3.34 `dfd87b8f` | 保留 tag 原生 irqbypass，移入 vNMI 三文件，再加 V2 三项；开关同 N |

N/H 的 V2 三项是 stage-2 targeted IPI、stage-2 lazy tracking、host stage-1 targeted IPI。`off` 关闭功能不等于移除 hooks/tracking；N/H 也不是只相差一个开关的内核。另有 `olk66tlbiv2` 构建候选，但其性能任务停在预检，**不得把旧 K2 或 N/H 的成绩挂给它**。详见 [内核总清单](KERNEL-BASELINE-PATCH-MATRIX.zh-CN.md)。

### 4.3 固定原版 O，改变内核/开关：各五轮

均旧盘 T1、500 TAP、Bash、同进程 `-w 3`，每 boot 另预热一次。默认策略为 THP never、NUMA balancing 0、HugeTLB 0、swap off、dirty_log true。150cfg 则是 THP always、NUMA balancing/swap on、dirty_log false，**不是默认组的重复样本**。

| 内核 / 模式 | 默认组中位 ms | 150cfg 中位 ms |
|---|---:|---:|
| K2r S3 | 156.0（149.0–161.8） | 158.8 |
| N2 off | 697.8 | 701.6 |
| N2 S2lazy | 185.6（178.8–197.5） | 199.0 |
| N2 full | 802.0 | 933.1 |
| H2 off | 244.0 | 685.2 |
| H2 S2lazy | 195.3（189.4–199.1） | 201.5 |
| H2 full | 730.7 | 836.0 |
| 返回 K2r2 S3 | 168.9 | 183.2 |

本批原版配旧 K2/S3 表现较好；N/H 的 full 并非更快。但跨内核必然跨 boot、执行顺序固定，K2 回测也有漂移，**不能把表中差值完全归因于某一个内核补丁**。来源：[delivery-01（来源登记，原件未公开）](PUBLICATION.md#source-033)。

### 4.4 固定 K2/S3，改变用户态组件或开关

| 实验 | 样本 | 整轮中位 ms | 判断 |
|---|---|---|---|
| K2r 同 boot：O / S 默认 / S+MADV_RANDOM | 各 5 | **156.0 / 151.2 / 164.5** | 区间重叠；没有证明 stack 的独立收益，也不能拆出 GIC/vsock 单项收益。MADV 本批没有改善 |
| 同 kit P：off1 / on2 / off3 / on4 | c100 各 5 | **159.6 / 145.0 / 159.8 / 150.2** | 确有 on/off 功能日志；on4 有 181.7 ms 轮，整体存在区间重叠，不写成稳定显著 c100 收益。配套 c1 每格 10 轮×c1n10 的单实例均值为 44.6 / 36.8 / 44.5 / 37.4 ms，不能混入整轮 c100 |
| K2r2 交替 a / b：O | 各 5 | **169.3 / 156.4** | 原报告同配置合计 10 轮中位 165.2（145.6–174.6） |
| K2r2 交替 a / b：P+prewrite | 各 5 | **157.6 / 145.9** | 原报告同配置合计 10 轮中位 147.8（142.5–158.6） |
| K2r2 交替 a / b：S+prewrite | 各 5 | **156.5 / 150.9** | 原报告同配置合计 10 轮中位 153.8（143.9–176.4） |
| K2r2：S、prewrite off | 5 | **166.3**（158.4–181.4） | 与 O 区间重叠 |

10 轮汇总仅引用原报告中**同一 boot、同一配置的 a/b**，没有合并不同组件/内核。原版、kit+prewrite、stack+prewrite 范围仍重叠；147.8 ms 是观测配置成绩，不是已证明 kit 胜过 stack 的结论。“预写入是主要关联因素”有依据，**“与 shim 版本完全无关”超出证据**。

来源：[delivery-01（来源登记，原件未公开）](PUBLICATION.md#source-033)、[delivery-02 §2（来源登记，原件未公开）](PUBLICATION.md#source-034)。同套件另一次五轮 c100 中位 141.1 ms 是另一组，不并入上表挑最低值。

### 4.5 无 TLBi、数据盘与暂停恢复

| 条件 | 样本 / 指标 | 结果与限制 |
|---|---|---|
| B=`olk66base` 同 boot，O vs P+prewrite | 各 10 轮，c100 整轮 | **692.8（242.3–737.7） vs 160.2（151.6–167.5）ms**，区间分离；但同时改变 shim 家族和预写开关，不是纯单补丁差异；也不能与 K2 跨 boot 直接算内核收益 |
| K2 + PCIe 5.0 新盘，O vs P+prewrite | 各 10 轮，c100 整轮 | **169.8 vs 158.5 ms**；与旧盘之间同时有盘/boot变化，不能当只换盘的纯收益 |
| K2、旧盘 P+prewrite 暂停/恢复 | 每档各 5 轮；pause/resume 整轮 | c1 **142 / 84 ms**；c100 **835 / 3454 ms**。c100 恢复读盘约 20.5 GiB；与 create-only 是不同操作 |
| 旧盘同配置 read-ahead 对照 | 三轮交替，c100 resume | read_ahead_kb 128：**1206–1294 ms**；4096：**3411–3474 ms**；c1 反而变慢。不是更换 CubeSandbox 二进制所得收益 |
| 新盘同配置 resume | 五轮；另有三轮 read-ahead 对照 | c100 中位 **1876 ms**；128 read-ahead 的三轮中位 **1006 ms**；不同盘/boot单列 |

来源同 [delivery-02（来源登记，原件未公开）](PUBLICATION.md#source-034)。这些结果不能证明预写入让 pause/resume 普遍变快；读盘、reflink 文件页缓存与 read-ahead 是额外变量。

### 4.6 主线完整 SHA256 与保存边界

| 组件 | SHA256 |
|---|---|
| O cubelet | `aeddef5dd88a54805397c89e42284e8e8f1565225e55963edd2b7647346feb08` |
| O CubeMaster | `167a966b157ed6cf8d65884bfc92c6bc4734039916213b40682cc8e015b01139` |
| O shim | `4bd6b07394f89b5cab2ee0f432e233b513ce3d78b5267a044cff1db1a5c43116` |
| O / kit 配套 runtime | `29149efcbf0ed8833d5045f625fbc4a2913df58bdb99eec5debfbc6731d4c47b` |
| S shim | `46aa8dc5e56a22aa6f2558354548a78fc7747d6fb81c1312178ec2559e08142c` |
| S runtime | `2cffdc60ea43ea6deac37d27eb384341430918d661c1b5bc6637a3e497bf3a75` |
| P kit shim | `13970933568a059dd15b65673c5b00d49fd4da251d01be299fcf25cd1ddfd282` |

原版发行信息：[arm64 manifest（来源登记，原件未公开）](PUBLICATION.md#source-035)；kit/stack 文件来源：[跨机包 source-manifest（来源登记，原件未公开）](PUBLICATION.md#source-036)。

部署证据支持“旧盘为服务实际使用盘、运行组件身份已回读”；未用这些记录进一步宣称“全部组件/模板清空后全新部署”。[best archive README（来源登记，原件未公开）](PUBLICATION.md#source-037) 所述完整归档位于历史远端路径，本地该目录只有 README，不宣称本次已验证远端全套文件。


## 5. 10-26 新的两条预热/预写路线

### 5.1 二进制身份和真正生效的功能

| ID | 源码 / 二进制 SHA256 前缀 | 包含什么 | 哪些在实验中生效 |
|---|---|---|---|
| W0：master hotset 初版 | master 移植构建；cubelet `ba36d376…`、shim `5a19e094…`、runtime `27b5b011…` | youhangwang 热页预读、建模板 profile、写集预 COW 三提交 | 建成 `tpl-a663…`；不能把其性能当作 v0.7.1 同基线对照。已被 W1 替换，独立收益未证实 |
| W1：v0.7.1 hotset | 基线 `2babb6f7`；实测构建 `737a2c5d`，重记提交的分支 HEAD `1e2b5f96`；cubelet `269ea219…`、shim `13257466…`、runtime `7c69c9ed…` | VMM `pread` 预读 + cubelet 两轮 profile + `written_extents` 预 COW | 当前实验内核无 soft-dirty、swap off，`tpl-e039…` 的写集为 0：**只预读有效，预 COW 没有执行页集合**。T1 无 profile 时两项均不消费；clear_refs 仍可能执行 |
| W2：hotset + bit 61 回退 | v0.7.1 提交 `376acf55`；给 youhangwang 的同改动提交 `00be3f8c`；cubelet **`a6bbc5a9…`**，shim/runtime 沿用 W1 | 只改 cubelet 写集判断及测试，**没有新 VMM 二进制** | 新模板 `tpl-6ddf…` 热集 155 段/73,175,040 B，写集 292 段/20,570,112 B；VMM 5022 页预 COW，0 failed，单实例 8.12859 ms。旧模板不会因换 cubelet 自动生成新写集 |
| L1：按快照自动学习 prewrite | 基线 `2babb6f7` + 原补丁 `159d2133`；本地 `dd5baee8` / 编译 `99a3494a`，同树 `12e85e92`；shim **`630d91c4…`**、runtime **`d288b6ca…`**；cubelet 保持 `a6bbc5a9…` | 恢复后采样、按快照身份缓存写集、下一次恢复前 `MADV_POPULATE_WRITE`；**此 shim 不含 W1/W2 的 hotset 实现** | `conf/prewrite=auto`、八次学习后启用；1481 页/1006 段，单实例 0 failed、2.66644 ms。T1 无 profile；cubelet 含 W2 不代表本组用了 W2 的预 COW |

W1 原始三提交为 `d0dc535e` / `0bf60695` / `c117e903`；v0.7.1 重记提交为 `cac3fa5b` / `ecfaf263` / `1e2b5f96`。源码分析和使用指南见 [hotset 分析（来源登记，原件未公开）](PUBLICATION.md#source-038)、[指南（来源登记，原件未公开）](PUBLICATION.md#source-039)。L1 见 [构建与实验报告（来源登记，原件未公开）](PUBLICATION.md#source-040)、[构建 manifest（来源登记，原件未公开）](PUBLICATION.md#source-041)。

**W2 的能力判断边界：** 当前代码是在一轮采样中未观察到 present 页的 bit 55 时回退，并非独立探针已经证明内核不支持 soft-dirty。在支持 soft-dirty 但本轮没有相应标记时也可能回退。`present && !bit61` 在新建 MAP_PRIVATE 快照映射中是私有化页的代理，不是精确的“仅 guest、仅 ready 以前写过”证明；还可能包含恢复阶段宿主写页。不能把回退称为精确写集检测。

### 5.2 对应内核与性能

以下全部为 `.90` 的 **`6.6.0-sbench-irqbypass-xarray-v2-aprmask`** 实验；不是旧 OLK K2/S3，也不是 10-26 深夜后来启动的其他内核。默认内存策略记录为 THP never、NUMA balancing 0、HugeTLB 0、swap off，dirty_log true；L1 的 TAP 数未单独核验，不能从 W2 的 500 Ready 记录推给 L1。

| 对照 | n | 整轮中位 ms（范围） | 可以支持的结论 / 限制 |
|---|---:|---|---|
| 原基线 A → W1、同一个无 profile T1（B） | 各 5 | 184.849 → 182.662 | 区间重叠，没有观察到明显回退；不等于证明零开销 |
| W1，新模板只预读 F / 无 profile G | 各 5 | 191.919 / 179.109 | 每组先逐出一次，再 `-w 3`；热缓存预读未证实收益，区间重叠 |
| W2 新模板 H / 同期无 profile G2 / 旧 profile F2 | 各 5 | **160.868**（150.484–170.621） / **178.150**（172.593–196.354） / **190.554**（180.235–195.375） | H 与两对照区间分离；相对 G2 中位低约 **9.7%**。**模板不同**，只能支持此配置组合改善，不是同模板、同二进制纯开关归因 |
| W2 重复 H2 | 5 | 151.856（150.519–180.353） | load1 约 10–17，有其他负载；与对照区间重叠，不作为第二次干净复现 |
| L1，同二进制同 T1，retry-01 C2 off → D2 auto | 各 5 | **185.166**（182.494–195.184） → **151.534**（141.473–168.508） | **降低 18.16%，范围分离**；这是该补丁本地归档中有效完整的 off/on 对照，不与 W2 合并 |
| L1，retry-01 A2/B2 | 原各 5，但 A2-r1 不合格 | A2 184.661 仅观测值；B2 157.529 | A2-r1 前后有高 CPU git；撤回“14.69%正式收益/两次有效复现”表述 |
| L1，retry-02 A3 off / B3 auto | A3 5；B3 2 合格 + 1 中断 | A3 **186.703**；B3 不报告组中位 | 用户中止，C3/D3 未跑；**不计算收益**，不与 retry-01 拼成完整组 |

热页新模板未逐出时曾有 C/D/E **705.153 / 683.351 / 242.779 ms** 的五轮中位；关闭预读或不带 profile 也有慢轮。逐出内存文件缓存后大幅改善，不能用约 700→160 ms 宣称回退补丁收益。大 folio/cache 历史改变是独立条件；实际内核锁/COW/TLBi 的逐事件因果尚未由该组 trace 证明。

W2 的组前逐出一次加每轮 `-w 3` **不是冷缓存基准**。L1 也只验证热缓存、单一 T1、单一 ARM64 内核。两个新方案都没有建立跨内核/跨模板普适收益结论。

来源：[hotset A–G/H–H2 原始目录（来源登记，原件未公开）](PUBLICATION.md#source-042)、[自动学习有效组报告（来源登记，原件未公开）](PUBLICATION.md#source-043)、[第三批中止报告（来源登记，原件未公开）](PUBLICATION.md#source-044)。

### 5.3 性能改善落在哪，不应误称“VMM 恢复全程加速”

L1 的离线分析：C2→D2，VMM resumed→API created 的实例级 P50 **72.658→25.617 ms**，而 VMM 恢复本身 **12→15 ms**。预 COW 是把工作前移，并不保证恢复线程耗时减少。同规模 103 个 shim 的匿名内存合计中位增加 **13,980 KiB（1.11%，约 136 KiB/VM）**，不是内存节省。

另外，`MADV_POPULATE_WRITE` 建立宿主私有页，不负责预建 KVM stage-2；有 soft-dirty 内核中后续 `clear_refs(4)` 会重新写保护宿主 PTE。W2/L1 的样本不能证明所有 stage-2 fault/TLBi 被消除。来源：[L1 分段分析（来源登记，原件未公开）](PUBLICATION.md#source-045)、[hotset 机制边界（来源登记，原件未公开）](PUBLICATION.md#source-038)。

### 5.4 可复核的完整 SHA256

| 二进制 | SHA256 |
|---|---|
| W2 cubelet | `a6bbc5a957723e55b1a6ee28b47db79b7998c53cf0ffa4ec050d07b243570c0a` |
| W1/W2 shim | `13257466d49f88bd76749c69d725f8e2dc4221b5ce06018ef94fa8491f96de5a` |
| W1/W2 cube-runtime | `7c69c9edda37b537dfa972299610cd1f9cfe6c2064a063c9ed7e15ab89598048` |
| L1 shim | `630d91c4b910328bb0ac97edafa20b2626f9b4414a6a66c890098c001d10070a` |
| L1 cube-runtime | `d288b6cacf2d62dbb63258ee9eed2819d7b31531ecce9eafec7c1b82128bc015` |

来源：[19:07 恢复回读（来源登记，原件未公开）](PUBLICATION.md#source-046)、[L1 构建 SHA256SUMS（来源登记，原件未公开）](PUBLICATION.md#source-047)。hash 是相应归档的身份记录，不是本次新算的目标机文件 hash。

## 6. 跨架构、仅构建和不可作为收益的项

| 材料 | 二进制 / 内核信息 | 清单中的地位 |
|---|---|---|
| 10-20 pause/resume 全栈双架构包 | Eulogizethesun `0.7.1test`，commit `e88bad53e28de5247ed3262f69a88f603c57b45d`，tree `0759d6e9702b3c77a1a0b8afb72d91bca19f8f12`；每架构 shim/runtime/cubelet/cubecli | 未叠加 PR14/15/17/18；dirtylog 默认关，动态配置 `host.memory.dirty_log`；只构建/版本验证，无实机 pause/resume 性能，QEMU 用户态启动不是 x86/KVM 验证；[构建说明（来源登记，原件未公开）](PUBLICATION.md#source-048) |
| v0.7.1 双架构交付 | `86f6d9b` 的 ARM64 + AMD64 包 | 构建成功不等于两架构都完成同条件性能 A/B；[交付目录（来源登记，原件未公开）](PUBLICATION.md#source-049) |
| Cube v0.7.1 + TLBI 迁移包 | ARM64 baseline + kit + stack + 旧 K2/base RPM；不含 W1/W2 新 hotset | 本次打包性能样本数 0；不是完整一键离线部署包，不自动使能优化；[报告（来源登记，原件未公开）](PUBLICATION.md#source-050) |
| x86 `.28` 启动 profiler | 报告版本 `31d911e4`，v0.7.1-amd64；openEuler 24.03 SP3 / `6.6.0-145`；精确逐组件 SHA 未在该报告列出 | 10-27 五轮整轮 **152.0 / 169.8 / 162.2 / 147.6 / 208.0 ms**（报告精度）；不是补丁 A/B。THP always、NUMA balancing 1、预留约 294 GB HugePages；独立三次 warmup 后正式 `-w 0`，不能与 .90 `-w 3` 主线比较收益；[报告（来源登记，原件未公开）](PUBLICATION.md#source-051) |
| AMD `.230.231` PCIe 4.0 巡检 | 内核报告为 `6.6.0`；看到历史 cube-bench 命令 | 只是主机活动/历史巡检，样本数 0；历史命令不是成功结果；[报告（来源登记，原件未公开）](PUBLICATION.md#source-052) |
| L1 合并门禁 | ARM64 六项带权限单测通过 | 尚有 x86_64 seccomp 与无特权测试问题，**性能有效不等于 PR-ready**；[审查（来源登记，原件未公开）](PUBLICATION.md#source-053) |

## 7. 总结：可以复用什么结论

1. **身份先于数字。** 原版、PR20 回退、kit、stack、hotset、自动学习 prewrite 是不同的组件家族，不能只写“v0.7.1”。同名 K2 也须加完整 uname 和 flags。
2. **预写入最清楚的单开关证据**是 L1 的同二进制、同 T1、同内核 C2→D2：185.166→151.534 ms，18.16%，各五轮区间分离；只有一次完整无已知污染的配对，不是两次。
3. **W2 支持配置级改善**：无 soft-dirty 时生成有效写集后，H 160.868 ms 对同期 G2 178.150 ms；但模板不同、H2 有负载，不能据此声称与 L1 等价或某个单独 bit 判断带来全部收益。
4. **已有暂停优化与创建预 COW 不同。** dirty-log 增量快照、保连接、延迟 teardown 不能从 create-only 的结果判断是否有用；应看暂停/恢复指标。
5. **kit、stack、W2、L1 之间没有本清单可确认的同条件四路 A/B**。不要用 147.8、153.8、160.9、151.5 排一个“最佳补丁排行榜”，也不要叠加各组百分比。
6. 复现实验应固定：组件 SHA、guest/template 身份、三处 shim、完整内核/flags、dirty_log、页列表/profile、内存策略、磁盘/页缓存和启动器。先验证实际使用版本与分支，再谈收益。

## 8. 覆盖与未决项

- 本文按二进制家族和有效对照组织，附表保存导航的逐条记录；不是对所有目录中每个 ELF 或 55 个测试镜像的穷举。只有构建物而无部署/计时证据的项保留为 build-only。
- 历史组存在只有报告值、源码/二进制对应不完整、同名版本跨日期变化等问题，已在各行标明。没有额外远端回读来“补全”历史证据。
- `.90` 20:03 恢复记录以及随后深夜变更是不同时间快照。本清单不声称目前目标机还运行任一历史内核或组件。
- 新增/修正结论以原始报告最新审查为准；本目录的 `source-records.json` 是整理时快照。重做汇编需重新核对源报告，而不只是运行脚本更新数值。
