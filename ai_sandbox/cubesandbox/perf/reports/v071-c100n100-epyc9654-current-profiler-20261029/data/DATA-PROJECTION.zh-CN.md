# EPYC9654 当前服务 c100：公开数据投影说明

日期：2026-10-29。状态：离线公开副本生成及数值、匿名化校验完成；本步骤未访问测试机、未新增测试，未提交或推送。

对应实验为北京时间2026-10-29 17:27–17:34。所有计时单位均为ms；对照统计单位是轮次，不把同轮100请求当作100个独立实验轮次。公开时间字段保留原记录的时区表示。

## 文件与允许字段

| 文件 | 公开内容 | 删除或转换 |
| --- | --- | --- |
| comparison.json / rounds.csv | B、D、F各5轮的组别、轮次、配对顺序、时间、整轮耗时、请求均值/P95/max、成功/错误计数及组统计 | 删除每轮evidence字段；不包含原始日志、机器地址、运行进程编号或请求身份 |
| stage-summary.json / stage-rounds.csv | 正式、预热、unknown_phase分别保留阶段定义、时钟口径、覆盖、缺失原因、逐轮统计及轮间聚合 | 逐字段重建；仅白名单统计及说明字段，未附逐请求原始记录 |
| tail-summary.json | 每轮客户端最慢正式请求的客户端、模板、Master业务、Cubelet早期与storage耗时 | 保留轮内seq并使用F-rN-formal-rank-1匿名别名；seq只表示负载内序号，不是真实SID或RequestID。rank=1是该轮客户端延迟最高请求，同一行所有阶段仍属于同一原始请求；不公开运行身份反查映射 |
| f5-stage-variation.json | F5与前四轮均值平均的阶段差值、F5均值/P95 | 只保留阶段名与数值，不附原始请求或路径 |

全部JSON均按字段白名单递归重建，CSV按列白名单重建；没有复制原始请求文件或日志。保留的数值与输入完全一致，不重新舍入。阶段名称、时钟口径和缺失原因是分析定义，不是运行身份标识。

## 样本、覆盖与可重算范围

- comparison有15轮、1500个正式成功请求；每轮3次预热不进入整轮耗时。公开逐轮汇总足以重算各组均值/中位数/范围及F−D配对差。请求P95/max仍是原轮统计，不能由15个轮汇总重新计算1500请求的分位数。
- F阶段表对应5轮、500个正式请求和15个预热请求；formal与warmup始终分列。unknown_phase为保留的空定义行，没有将未知样本改为正式或预热。990行阶段表包含每轮52个startup定义的三个phase，以及客户端旧计时和20个frontdoor定义的formal/warmup两类。
- 客户端旧计时、Host核心日志链及主要Master阶段各覆盖500/500正式请求，并非每个阶段都有500条测量。storage各轮仅74/73/86/82/73条，共388/500，缺112条。成功且小于5ms的Cubelet stat可能不输出，因此有日志子集的均值/P95不能当作全部500请求统计；缺失保持缺失，不补零。
- 20个frontdoor事件区间仍全部未观测；Client→API、API→Master、Master HTTP middleware及回传边界不能由其他阶段相减恢复。Host wall、组件单调时长、Shim累计时长及客户端duration分别保留，父子重叠阶段不能相加。
- stage-rounds可重算stage-summary的轮均值中位/范围和轮P95中位；各轮P95为nearest-rank。没有公开500条请求的完整分布，不能独立重算每轮分位数或原始端点时间。
- 五个匿名最慢请求保留同请求阶段对应关系，能够复核报告的选定尾部数值；原始SID、RequestID及其反查映射未发布；seq仅保留为轮内非运行身份序号，无法从公开材料恢复其他请求或验证原始日志关联。
- 未公开原始capture、journal、运行配置和逐请求日志；本数据投影不独立证明运行环境、源码编入tree、日志完整性或因果归属。原件SHA标识本地分析输入，公开SHA标识公开副本字节；两者不能互相替代。

## 原始输入与公开副本SHA256

原始输入路径为实验包内相对路径，仅用于标识来源，不表示该原件已公开。原件与公开副本字节相同的条目表示其全部字段已通过白名单审核，不表示公开了原始请求日志。

| 公开文件 | 原始输入（实验包相对路径） | 原始输入SHA256 | 公开副本SHA256 |
| --- | --- | --- | --- |
| [comparison.json](comparison.json) | `analysis/comparison/comparison.json` | `b34f4e7d9e90547851f8f0b73159ddc73f133bf47d9e3d5b4b04075bda2262f3` | `0be8b472a07569892fae99ab1b86fe8aeceda62c90bcf2cb6806f35bc07c6051` |
| [rounds.csv](rounds.csv) | `analysis/comparison/rounds.csv` | `4f0a829394509d996f96d16290a41053d8398b29722de5f039c27f72d71f970a` | `d561d638c9d8666ba3c5acd1d3f6faa5eadb11601a340a59a63f703cf3a0fbe7` |
| [stage-summary.json](stage-summary.json) | `analysis/bottleneck/stage-summary.json` | `864f0e4462d05e0eef8ac79d127bbbbc85eced10cf3f5152f7fcce548f7dca31` | `864f0e4462d05e0eef8ac79d127bbbbc85eced10cf3f5152f7fcce548f7dca31` |
| [stage-rounds.csv](stage-rounds.csv) | `analysis/bottleneck/stage-rounds.csv` | `161b11a29c33e7d3528b7c860ef8fdd562a1b3dcb535c1871d0b7ec3b55009e6` | `161b11a29c33e7d3528b7c860ef8fdd562a1b3dcb535c1871d0b7ec3b55009e6` |
| [tail-summary.json](tail-summary.json) | `analysis/bottleneck/tail-summary.json` | `1e6812bcb99cd8072ae3225b13ad720b787d01a45c753d9224adf36d516ad77d` | `324b46a44b32efa53f008deb8a093f7ebe8d6cce8f87076ccc5576827124a219` |
| [f5-stage-variation.json](f5-stage-variation.json) | `analysis/bottleneck/f5-stage-variation.json` | `407b44933326e08c04cb4eb7acd08d0c2da0be419d1828b902f591983d2224ab` | `407b44933326e08c04cb4eb7acd08d0c2da0be419d1828b902f591983d2224ab` |
| [verify_public_data.py](verify_public_data.py) | 公开核验脚本（本次新增，无原件） | 不适用 | `d3f1e2ee1d74f5fcda88beb7634909331adf5daf6f91cc9825d161fbe45696f5` |

## 离线校验结果

- 6份数据文件保留字段逐项一致；15轮及全部组统计、5组配对差复算通过。
- 990条阶段行与阶段汇总逐轮数值、覆盖和排除原因一致；500 formal核心覆盖、15 warmup、388/500 storage覆盖及20个未观测入口区间均核对通过。
- 5条尾部记录的阶段数值与原件完全一致，保留轮内seq和延迟rank匿名关联，未保留真实SID或RequestID。
- 已对全部公开文件扫描地址、私有绝对路径、运行身份、凭据及原始日志字段，并与原始逐请求文件提取的实际SID/RequestID集合逐项比对；未发现泄露项。
- 本说明自身不作自指SHA；上层发布清单可统一收录全部公开文件。

## 离线复核命令

在本data目录执行：

```sh
python3 -I verify_public_data.py
```

脚本仅使用Python 3标准库读取同目录文件，不写文件、不联网。它核对15轮组统计、5组配对差、990条阶段行与汇总、formal/warmup覆盖、5个匿名尾部请求与各轮最大值、F5阶段差异，以及上表7个公开文件SHA；这不替代未公开原始请求或日志的核验。
