# v0.7.1 GICv3 核心性能数据：证据与发布清单

| 字段 | 值 |
|---|---|
| Task-ID | `materials-v071-gicv3-results-20261010` |
| 测试日期 | 2026-10-08–09，Asia/Shanghai |
| 归档日期 | 2026-10-10 |
| 汇总负责人 | Codex |
| 内容状态 | 已核对本地来源；远端归档以对应Task-ID提交与ref核验为准 |
| 被测版本 | 官方v0.7.1，`31d911e430fdf8a8879bd062b8e78066c1a8e89d` |
| 核心完成情况 | 32个非密度case完成；密度1500目标未达，最高完整健康档1000 |
| 允许写入 | 本次同名前缀4个归档文件及benchmark README导航；不改变旧报告、源raw或测试环境 |

## 归档文件

| 文件 | 内容 | bytes | SHA256 |
|---|---|---:|---|
| [测试结果报告](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.md) | 环境、条件、方法、逐项数据及适用范围的公开脱敏版 | 27245 | `9bd2560d94de843bc8af799c39de0745530c9e0291de4740b85253c8eca1a5b5` |
| [性能CSV](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.csv) | 53条指标记录，39列 | 24047 | `541e8d0475a5fb98b2e9175d6a60d3e537693e8306ec94291a519e82343310c2` |
| [环境CSV](CUBESANDBOX_V071_GICV3_CORE_PERFORMANCE_20261009.environment.csv) | 41条环境、条件及指标定义，4列 | 6221 | `4683a93a0b4f27ed6a24d20d779918d77076ac911bb82a5c963230a6a63d76af` |

这些是报告/派生数据，不冒充原始逐请求日志。源数据只读，未重新执行测试。原始JSON、运行日志、精确ID台账、数据库备份、组件二进制和源码压缩包未上传；本次没有新增大文件，不需要Git LFS。

## CSV 字段与行数

两个CSV使用UTF-8 BOM、逗号分隔，可由Excel或标准CSV解析器读取。

- 32个非密度case展开为43条指标记录：脏页8档各有Snapshot/热恢复，Pause/Resume 3档各有两个指标。按 `case_id` 去重还原32个case。
- 10条密度记录包括WFI=N/Y各4个健康采样点，以及各1条1500目标未达记录。累计1159/1196成功创建不等于完整健康验收容量。
- 延迟列单位ms；创建为逐请求HTTP返回，其余并发操作为整批wall。`per摊销_ms`不是逐请求平均值。
- `QPS_每秒`只来自原生创建统计；内存以GiB/MiB标注，差值摊销不是VM进程RSS。
- 空白表示未提供、不适用或未测得，不用0补数；Python工具没有P50/P99，不虚构这些字段。
- 展示精度沿用原报告：原生创建与密度按十进制ROUND_HALF_UP保留2位，Python汇总保留1位；未重新汇总分位数。
- `run_id`在公开版使用稳定的结果目录别名，不是原始运行UUID；`原始来源`是本地逻辑索引，不是公开下载地址。

## 原始证据

下列路径统一以 `<local-evidence-root>` 表示受控本地证据根。维护者保留原始位置与ID对应关系；公开仓库读者不能据此访问原始文件。

| 公开run别名 | 原始用途 / 本报告纳入范围 | 本地逻辑位置 |
|---|---|---|
| `results-core-create-a1` | 原生Template创建7档，1620正式请求及21次预热 | `<local-evidence-root>/results-core-create-a1/` |
| `results-core-lifecycle-a2-dbcompat` | 只纳入4.1的3档；该run后续旧脏页准备失败仍保留 | `<local-evidence-root>/results-core-lifecycle-a2-dbcompat/` |
| `results-core-dirty-a1-prepared` | 统一准备条件下8档脏页/恢复，24正式轮 | `<local-evidence-root>/results-core-dirty-a1-prepared/` |
| `results-core-restore-rollback-clone-a1` | 4.3/4.4/4.5共11档 | `<local-evidence-root>/results-core-restore-rollback-clone-a1/` |
| `results-core-pause-a1` | Pause/Resume 3档 | `<local-evidence-root>/results-core-pause-a1/` |
| `results-density-1500-a1` | WFI=N；健康点到1000，1500目标失败 | `<local-evidence-root>/results-density-1500-a1/` |
| `results-density-1500-a2-wfiy` | WFI=Y；健康点到1000，1500目标失败 | `<local-evidence-root>/results-density-1500-a2-wfiy/` |

旧DB失败run、旧脏页ENOSPC/v4保护拒绝、功能canary、只读环境清单、原始文件SHA核验与收尾证据均在本地保留。它们没有被成功补测覆盖，也没有作为新的正式成绩加入公开CSV。

本地已有的原始文件核验记录说明八个结果目录352文件在当时远端/本地逐文件一致；这一历史验收不等于本次公开上传了这352个文件。此处只发布最终派生报告和CSV，并独立验证源/发布版的数据一致性。

## 工具身份

| 层次 | 固定来源 / SHA256 |
|---|---|
| 原生创建与密度 | 官方v0.7.1 Go `cube-bench`；`d7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d` |
| 社区生命周期脚本 | CubeSandbox源码 `cf571c65e41ca9f43012a1c3914575aef3cd6c21` |
| Snapshot并发 | `b896937eabe210cfddfb63501f471b4e48c873b7149d20da886a1f502f152253` |
| 从Snapshot创建 | `332d5cd147dd654ac141d7598028c93756997b1c72ef2deaee80229c28f5d513` |
| Rollback | `0f1d7720bc12192355943f30917e893f73d4e015a0007dcb2288f8490f765229` |
| Clone | `eda015c383c95bae92fe7608aa2f4824c4583cdc571062cf3f8577544ab9e67f` |
| Pause/Resume | `2cba48bf409d26812cbea88a29d9987931a838f5bf6804f5da25652688134593` |
| 脏页准备修正版 | `ef92e6d01b4e0ee7aaf62b6d791509f363189aa7071fd8a15f7069459872a2e2`；shm1536MiB、写入块1MiB；timer/预热/统计未改 |
| 编排v3 / v5 | `3722157f85303d7331f750150111b0393d92de069dc99fc9de8de6246578a60d` / `399815f259a072db79415a29496283da089308b95e66ba63494aeeb58ecfdd09` |

全套源码分发包只在本地保留，未随本次上传。读者复跑须取得对应工具、核对二进制/脚本身份、重新准备独立Template与资源门禁，不能复用本文的站点占位值。

## 环境条件

公开版保留CPU/NUMA/内存/内核、GICv3/WFI、TAP1500、调度超配额度、2vCPU/2GiB沙箱、固定镜像digest和SDK版本。主机、boot、Template身份已脱敏，不改变固定同机/同boot/同模板这一测量条件。

数据库并非全新初始化的纯v0.7.1结构：仍保留较新迁移，Snapshot测量在必要的单列默认值兼容调整后执行。依赖引擎为MySQL8.0.46/Redis7.4.9，不能把引擎版本混称CubeSandbox发布号；完整只读诊断仅本地留存。

本次只搬运与发布结果，没有修改数据库、Redis、配置或服务，也没有重新开启测试。创建与生命周期的样本量、非应用就绪/热恢复边界、密度未达目标均在报告中保留。

## 来源哈希与脱敏说明

| 脱敏前本地制品 | bytes | SHA256 |
|---|---:|---|
| `2026-10-09-v071-gicv3-performance-results.md` | 26906 | `b9620d0a87694d9cc45b8acb603dd481093755fd7cc986e69dd5178144cb86be` |
| `performance-results.csv` | 27004 | `39adc59dd0d4787adc441abb05323999fc8d84fc96a7eb0b8b966b13b1f101f6` |
| `environment-and-conditions.csv` | 7570 | `fb1867aad412539c2cde5db0f0606cf99acbbee7d702519fc3778b613e84a977` |

发布版不是源文件逐字节副本：报告只替换内部主机/资源身份、个人与部署路径及本地链接；新增公开版说明。性能CSV只改变 `主机`、`run_id`、`原始来源` 三列，其余36列逐单元格相同。环境CSV仅改变相应身份占位值和来源报告位置。

具体占位符为 `benchmark-host`、`tpl-redacted`、`boot-redacted`、`<suite-source-root>`、`<local-evidence-root>`；命令路径 `/opt/cube-perf-evidence`是公开示意，不是声称测量目录发生了变更。回环API地址和已公开端口保留，用于说明客户端与服务端同机条件。

发布前检查：CSV BOM/列数/53与41条记录、32个核心case/43条核心指标/10条密度记录、逐单元格数值一致性、Markdown本地链接、shell示例语法、内部地址/个人路径/资源ID与凭据扫描，以及精确文件暂存和Git差异检查。仅这组文件归本次提交；Materials主工作区既有dirty改动不纳入。

本清单不自含提交SHA；版本关联使用 `Task-ID: materials-v071-gicv3-results-20261010`。上传完成以实际远端分支指向该提交为验收，不以本地文件存在替代。
