# CubeSandbox ARM64 Template 恢复失败问题与修复验证

本目录归档 CubeSandbox 在 ARM64 平台基于 Template 并发创建沙箱时，因虚拟 GIC AP1R 状态恢复异常导致 guest 卡死的问题说明、关键证据、修复补丁和修复后验证数据。

## 结论

- 测试机器：`.65` 远端 ARM64 环境。
- 修复组合：`aprmask` 内核 + 修复版 `cube-runtime`。
- 测试矩阵：`1U/2G` 至 `5U/2G`，每种资源规格 5 个 Template，共 25 个 Template。
- 每个 Template：6 轮，每轮并发创建 50 个沙箱，共 300 次。
- 总请求数：7500；成功 7500，失败 0。
- 清理检查：150 轮全部通过；每轮清理后等待 TAP 资源池恢复。
- TAP 配置：`tap_init_num=1000`；验证结束时 TAP link 数 1000、池内可用数 984。

## 文件说明

- `CUBESANDBOX_ARM64_TEMPLATE_RESTORE_FAILURE_PROBLEM_DESCRIPTION_20260806.md`：完整问题说明，包括环境、现象、关键日志、原因推断、修复依据和测试结果。
- `REPORT.zh-CN.md`：修复后多资源规格并发验证报告。
- `data/templates.tsv`：25 个 Template 及其资源规格。
- `data/totals.tsv`：全局请求、错误和清理统计。
- `data/summary.tsv`：按 Template 汇总的验证结果。
- `data/results.tsv`：7500 次沙箱创建请求的逐条结果。
- `data/cleanup-summary.tsv`：150 轮资源清理及 TAP 恢复检查结果。
- `data/environment.tsv`：测试环境、内核和 runtime 版本信息。
- `evidence/ap1r-pollution.log`：修复前 AP1R 状态污染的关键证据。
- `evidence/identity-attempt-1-shim.log`：修复前 Template 沙箱恢复失败的 CubeShim 关键日志。
- `fixes/`：内核 AP1R 读回掩码补丁、runtime 64 位 ICC 寄存器访问补丁及补丁说明。
- `scripts/validate_aprmask_multi_resource_templates_65.sh`：本轮并发验证脚本。
- `SHA256SUMS`：本目录全部归档文件的 SHA-256 校验和。

## 数据取舍

本归档保留可复核结论所需的逐请求结果、清理结果、关键故障日志和补丁。原始 `cube-shim-req.delta.log` 约 98 MB，包含大量重复运行日志，未纳入仓库；其错误计数和请求结果已分别固化在 `data/totals.tsv`、`data/summary.tsv` 与 `data/results.tsv` 中。

## 来源

数据与文档整理自：

```text
/home/lyq/Projects/Verification/cubesandbox
```

归档日期：2026-08-06。
