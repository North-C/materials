# 2026-10-19 PR4 / warn / Cubelet 不绑 NUMA：归档说明

本目录归档本次已有的 1 pilot、3 正式性能轮及 1 独立瓶颈抓取轮；没有运行新的性能测试。原始来源为工作区 `artifacts/shim-switch-bottleneck-20261019`，远端采集目录 `/data/cubelet/shim-switch-bottleneck-20261019T040949Z`。原目录和既有 materials 报告均不覆盖。

## 收录范围

- `results/`：本地已导出的逐轮 benchmark raw、cleanup/run-exit、配置与二进制身份、门槛检查、功能探针、完成/交付审计，及瓶颈轮全部外层/内层日志和原生 HTML 分析。
- `analysis/`：指定瓶颈 workspace 工具离线生成的阶段、网络细分、CreateContainer 明细和时间线。它与 `results/` 中原生报告共同保留，不替换原生报告。
- `reference/`：构建 VERSION、原总结、完成后的分析复核，以及采集前的工具准备记录。准备记录是历史过程材料，不覆盖最终审计结论。
- 新增 `REPORT.md`、逐轮 CSV、历史整体/阶段对比 CSV、发布说明、校验与来源清单。

132 个来源文件共 21,686,461 字节。清单逐文件记录来源相对路径、原始/公开 SHA256、字节数和脱敏次数。这里不是远端整个目录的完整镜像：没有收录二进制备份、私有 API 配置、两份重复中转 tgz，以及 analysis-copy 中重复的原始 capture。四轮参考性能数据提供 raw 和清理/审计，完整组件抓取仅对应独立瓶颈轮；不要理解为五轮都进行了完整组件日志采集。

## 脱敏边界

同一个 rootfs artifact 下载令牌在两份 Cubelet 请求日志中各出现 206 次（103 条 annotation＋103 条下载 URL），合计 **412 次**。公开副本将其替换为等长 36 字节占位符 `REDACTED_ARTIFACT_TOKEN_____________`。两份日志对应同次抓取的外层和内层证据，不是两次实验。

只修改上述令牌，保留所有记录、实例 ID、时戳、阶段耗时及文件字节长度。其余 130 个来源文件与源文件逐字节一致。未输出或收录原令牌；常见凭据字段/模式扫描未发现未脱敏候选。这是对所选本地发布文件的扫描，不声称完成对整台机器或全部历史目录的秘密审计；没有导出私有 API 配置。

`PUBLICATION-MANIFEST.json` 和 `SOURCE_SHA256SUMS` 记录脱敏前的来源哈希。原始 capture/analysis manifest 保持不变，所以其中两个日志的原始哈希不能用来校验公开日志。**校验分发字节请使用本目录 `SHA256SUMS` 或发布清单中的 `published_sha256`。** 发布校验见 `PUBLICATION-VALIDATION.json`。

## 查看与校验

从 [REPORT.md](REPORT.md) 进入 [原生 report.html](results/bottleneck-c100/capture/inner-round/runs/20261019T041508Z-ca010a49/analysis/report.html)。HTML 与其本地依赖一起归档，整目录下载后可离线打开。历史比较链接指向 materials 中同级旧报告；只解压单个数据包时，历史报告不在包内，需在仓库中查看。

本目录还提供 `result.tar.gz`，内容与本目录发布文件相同（排除压缩包自身和外部包校验文件），便于搬运；不会把未脱敏中转 tgz 套入其中。

```sh
# 在本目录校验所有公开文件
shasum -a 256 -c SHA256SUMS
# 校验数据包
shasum -a 256 -c result.tar.gz.sha256
```

归档保留原始执行异常：后处理 postcheck 的 TypeError 及恢复审计没有删掉。该异常发生在成功的 capture/runner 之后，不改变 100/100 API 成功结果；也不能据此声称编排全程没有错误。
