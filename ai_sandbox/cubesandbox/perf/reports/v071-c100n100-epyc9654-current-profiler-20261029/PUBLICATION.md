# 公开范围与复核方法

日期：2026-10-29。类型：已完成实验的材料发布；本次发布未执行新的远端压测、部署或重启。

公开主报告、完整阶段目录、15轮计时、五轮正式/预热阶段统计、匿名尾部请求摘要、F5阶段变化、运行组件SHA和原始验收摘要。模板名替换为template-A；数据保留阶段数值、分母和缺失状态。原件与副本哈希分别见[data投影说明](data/DATA-PROJECTION.zh-CN.md)及[证据原件哈希](evidence/source-hashes.json)。

原始服务日志、完整配置、机器地址和路径、真实SID/request ID、库存及清理明细、原始HTTP输出、源码补丁、源码bundle、二进制和私有归档未公开。主体报告按公开附件重新编排链接；阶段结论和数值不变，门禁与统计边界补充说明。

公开数值可复核轮次均值/中位数/范围、五对差值、阶段跨轮统计及列示的匿名尾部数据；不能从聚合值重建逐请求分布、从轮P95推导总体P95，或独立重放原始日志归属、清理和运行身份审计。原始审计通过的声明与公开副本校验是两个层次；SHA只标识对应文件字节。

在本专题目录可校验文件：

```sh
shasum -a 256 -c SHA256SUMS
python3 -I data/verify_public_data.py
```

每个计时组有五轮，主指标是正式100请求的summary.total_time_s乘1000，预热排除；F−D按轮次编号配对。stage-rounds.csv保留formal/warmup及计时轴，不相加父子/重叠阶段，storage等低覆盖stat只代表已记录子集。数据投影说明记录离线数值核对结果。

通用采集工具继续由[GitCode profiler仓库](https://gitcode.com/yuncongyue/cubesandbox-startup-profiler)维护（需要成员权限）；本材料包没有复制或分叉该工具。
