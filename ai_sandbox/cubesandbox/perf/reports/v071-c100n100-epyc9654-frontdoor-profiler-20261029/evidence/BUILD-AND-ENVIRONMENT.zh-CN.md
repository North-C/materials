# EPYC 9654 机器：构建、环境与验证证据

日期：2026-10-29。类型：公开环境与构建证据摘要。范围：Template create-only c100/n100、同进程串行预热 3 次的 profiler 对照实验；不涉及新的采集或部署。

**构建、目标机原生检查和 35 轮正式测试已完成；追加 Go runtime trace 未采集。** 本文保留可公开的身份与验证摘要，完整配置、服务日志、源码 bundle 和二进制不随本文公开。机器统一显示为“EPYC 9654 机器”，独立 ARM64 编译主机显示为“构建机”。机器 CPU 名称已有历史采集证据，不仅是显示名。

配套机器可读清单：[provenance.json](provenance.json)。其中 SHA256 区分构建产物、补丁与未公开原始证据；后者仅标识原件字节，不能替代公开原件的独立复核。

## 固定源码与补丁顺序

| 层次 | 固定身份 |
| --- | --- |
| 上游仓库 | [boostkit/CubeSandbox](https://gitcode.com/boostkit/CubeSandbox) |
| 基点 commit / tree | `2babb6f7405677c04b7fed1563c6a5d53a8e771b` / `608397465872e2050e823fd4ebf1207d3d1208f0` |
| 第 1 个补丁，U/P 共同包含 | `observed-working-tree.patch`；SHA256 `d10d4366db67aaeb0acfae63fe16058152ba829cd5dff25b8e5aae7cc3192c13`；保留原现场三文件修改，无运行开关 |
| U 最终 commit / tree | `9ddc0a6f4501d72c155bfbb4f0b1a7054b06aeb0` / `285f21316b8fbbe1b402a50ae94d660e4582c414` |
| 第 2 个补丁，仅 P 包含 | `frontdoor-server.patch`；SHA256 `c24254fc66a1d1e3d1536f0029d64eb8dd07bb475a6369a861860ddf58683eeb`；在第 1 个补丁之后应用 |
| P 最终 commit / tree | `747e5c1b71d992f780df4a1e7aa12b5bfa82b96a` / `a679b91d35a1a3cc317c21f0dbd566397dc8b446` |
| 客户端基点 | [TencentCloud/CubeSandbox](https://github.com/TencentCloud/CubeSandbox)，`31d911e430fdf8a8879bd062b8e78066c1a8e89d`；`examples/cube-bench` |
| 实际采集工具 commit | `f1f6b0156d7b0c53094326f04527bb45aaeca382` |
| 离线关联修复 commit / tree | `054e931ee1fe0ef63ae0a09f39fce534897a4111` / `7b90cd7fcbe3532b6c913d4ab5737d1ba5e17c67` |

U/P 是隔离构建快照提交，不宣称这些提交已可从公开远程检出。应用检查及实际应用通过，没有冲突适配；构建前后源码工作树均核对为 clean。共同现场补丁保持一致，不能用纯上游基点替代 U。

客户端按顺序加入 SID/独立 warmup 结果导出，再为 trace 版增加 HTTP 事件与请求关联头。两者是**独立二进制，没有同 binary 运行开关**。客户端修改由固定版本准备脚本生成，没有单独归档 patch 文件；`provenance.json` 给出脚本 SHA、各修改后文件 SHA 和 helper 文件 SHA，不虚构客户端最终 git tree。采集工具与后续离线关联修复分开记录；后者只补全 pre-SID Master 指标关联，没有改变本次运行二进制。

## 编译与分层验证

构建机为 aarch64，交叉目标为 x86_64；U/P 使用相同隔离环境与工具链。

| 项目 | 值 |
| --- | --- |
| Rust / Cargo | 1.89.0 / 1.89.0，显式选择 Rust 1.89，不修改源码工具链文件 |
| Go | 1.25.7 linux/arm64 |
| cross GCC / QEMU x86_64 | 9.4.0 / 4.2.1 |
| 构建镜像 ID | `sha256:6f2de1e0c80a9ca665477189cd05e7ecd5d35271a85f0ba8558deaf70f2e2be3` |
| 构建并发 | 容器 CPU 12；Cargo jobs 8；Go jobs 8 |
| 依赖约束 | Cargo locked；Go mod readonly |
| API release | opt-level=3、fat LTO、codegen-units=1、panic=abort；最高引用 glibc 2.29 |
| Master / 客户端 | Linux amd64，CGO_ENABLED=0，静态链接 |

构建阶段 18 项均退出 0。API ARM64 原生测试 150 通过；API amd64 QEMU 入口测试 7 通过；Master ARM64 race 测试 6 通过、1 项按 Linux 条件跳过；客户端 ARM64 race 23 通过、amd64 QEMU 10 通过。随后在 EPYC 9654 机器原生执行 API 依赖检查及 API/Master/客户端入口测试，四项检查均退出 0，二进制 SHA 核验通过。

这些验证分别证明构建与指定测试通过；正式性能结论另依据已归档的 35 轮结果，不以编译成功代替性能验证。离线 profiler 修复另有 395 项测试通过、0 跳过及远程版本回读记录。

## 实际二进制身份

运行前后核对真正执行的组件及客户端，不只核对安装副本。P/C/S/F 使用同一服务二进制；下表是本次实验的历史身份，不代表主机当前运行状态。

| 产物/组件 | SHA256 |
| --- | --- |
| U API | `d17fb1700509b2e590f997e0270590c29cfc74df42eea5a1df07262d87608f47` |
| U Master | `f3f0fd3afe2618c2ba01af5ac39d9249020db77daefdb8887eddbaf2235c7da3` |
| P API | `6d1b92f96b6f3daa06a4a04c3fd4473d884dcfc3d697f0e080f57f098c610f9b` |
| P Master | `be2c5163a602503723534ab30cad2f2f12cd6e49c4df27d0f74f434b073d37ea` |
| 基础客户端 | `baaeba5908c5734e6616039d1434cbda4634c726eda266e93b10a94bd1182675` |
| trace 客户端 | `8b4ff0ab9eb0500ee72de69f25ad732007e6f11626dd130a2ad0854fc54e5d1a` |
| 原部署 API（锚点） | `51542159b0732529a3bc3f489717122d2d2a9b015e912c4fb9773878aaea38b6` |
| 原部署 Master（锚点） | `cce1af8250cefdb4488a8cef62521dccebedc0faf231d20dc3590f273d15f3ea` |
| 原部署客户端（锚点） | `3614d21c38f1a50d261272c7fbb74f54dc1f80356a54ddb5986e55c2f3d89ba3` |
| 固定 Cubelet | `506b8a83d0859036e17a1cbda9e3392023f989af2162a3f9293a9a3e702afdf3` |
| 固定 active_component_version_Shim | `2153cb465d4069872ad3abcf88695380cbf786986fb16a4fcbacfaf303614bfa` |
| 固定 active_component_version_runtime | `c887554030a5be9e39b26e582abda56286c7248039898ec494c712ecf57003b2` |

固定 Shim/runtime 指向实际选用的组件版本副本；未将另一个安装副本的 SHA 误当作运行身份。原部署 API/Master 的精确编入源码树和工具链缺少原始完整构建清单，因此 A_before/A_after 仅作漂移锚点，不能用于 A→U/F 的单补丁成本归因。

## 开关矩阵与实际生效

| 组 | 轮数 | 服务端补丁状态 | 服务端 CUBE_FRONTDOOR_TRACE | 客户端 | 额外完整采集 |
| --- | ---: | --- | --- | --- | --- |
| A_before / A_after | 各 5 | 原部署漂移锚点，精确编入 tree 未知 | 未开启本次观测 | 原部署客户端 | 无 |
| U | 5 | 公共现场补丁已编入；frontdoor 未编入 | 不适用 | SID/warmup 导出基础版 | 无 |
| P | 5 | 公共补丁及 frontdoor 已编入 | 0 | 同 U | 无 |
| C | 5 | 同 P | 0 | HTTP trace 构建 | 无 |
| S | 5 | 同 P | 1 | 同 C | 无 |
| F | 5 | 同 P | 1 | 同 C | capture_100 |

公共现场补丁和客户端修改均无运行开关；服务端观测除环境开关外还要求有效关联头。同构建 C→S 回答服务端观测开启差异；U→P 回答补丁编入但关闭差异；U→F 只能回答整个组合差异。

实际生效通过进程二进制 SHA、环境回读与事件覆盖共同验收：S/F 每轮 API、Master 各 103 条与客户端唯一关联，五轮各为 515 条；C 只有客户端每轮 103 条；U/P 无本轮入口观测。F 五轮正式 500 请求的核心链路完整，15 条 warmup 独立列出。各组均有共同负载外身份与日志窗口记录，“无额外采集”不表示完全无观测。

## 环境与条件白名单

以下 CPU 片段来自既有只读归档，采集时间为 `2026-10-28T20:09:36.611098+00:00`（UTC；北京时间为 2026-10-29）。本次公开整理没有新增远程采集。

```text
Architecture:                         x86_64
CPU(s):                               384
Model name:                           AMD EPYC 9654 96-Core Processor
Thread(s) per core:                   2
Core(s) per socket:                   96
Socket(s):                            2
NUMA node(s):                         8
```

| 条件 | 已核实值或边界 |
| --- | --- |
| 主机内核 | 6.6.0；本任务未独立核实内核源码 commit，不据版本串推断补丁栈 |
| THP / NUMA balancing | madvise / 0 |
| 测试规格 | 同一固定 app-template；2000m CPU、2048 MiB、1G 可写层、XFS |
| 探针 | 端口 49999 的 health endpoint |
| 测试方式 | 原生 cube-bench；create-only；并发 100，正式 100，同进程串行 warmup 3 |
| 配置白名单 | log.level=info；enable_log_metric=true；MySQL；max_open_conns=20、max_idle_conns=5 |
| 时钟 | Linux monotonic；跨进程共同时钟域已验证，身份值不公开 |
| 每轮前置条件 | API/Master 重启后至少等 20 秒，再通过空库存、738 Ready TAP、无冲突工作、load1≤4 门禁 |
| 未改变项 | 未更换内核或 Cubelet；未清空页缓存、重建模板或修改探针 |

guest 内核源码、源镜像 digest、显式进程 CPU 绑定及完整存储/网络拓扑未在这份证据摘要中重新核实，不能从 CPU 型号或版本标签补推。门禁重试可能改变服务存活时间与缓存热度，不能声称每轮热状态完全相同，也不能将 w3 解释为已经预建 100 条连接或充分填满 SQL 池。

## 验收、清理与未完成边界

35 轮全部有效，正式请求 3500/3500 成功；7 组各完成 5 轮，关闭验收无错误。每轮 103 个本轮资源均清理，共 3605 个唯一资源，清理后库存均为空。原部署锚点的 10 轮客户端未直接导出 formal SID 和单独 warmup 结果，相关归属限制保留；独立库存和拥有资源对账不能冒充客户端 warmup 结果。

追加 Go runtime trace 在正式矩阵结束后的第一个 gate 因外部编译活动停止；随后只读发现另一会话部署新版本，因此未覆盖其部署继续采集。**真实 trace 样本数为 0，未改变诊断配置或服务，也未启动追加负载。** SQL 连接池、日志锁、调度等待的具体占比仍未证实。本机合成 trace 的脚本验证不属于远端性能样本。

本任务曾完成原部署恢复及 A_after 五轮回测，之后的另一会话部署被保留；这描述历史顺序，不宣称机器目前仍是原二进制。

公开副本排除访问地址、登录信息、绝对机器路径、时钟身份值、完整配置/日志、源码 bundle 与无关服务状态。可公开复核范围是本清单的身份、参数与验收摘要，以及公开报告另附的脱敏数据；缺失原件意味着读者不能仅靠此页重新执行全部远端日志、门禁与清理审计。
