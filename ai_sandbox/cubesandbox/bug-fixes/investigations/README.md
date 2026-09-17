# investigations

ARM64 snapshot-restore / multi-vCPU 故障的历史调查链：AP1R/NMI 最终根因报告之前的完整调查过程。按 CONTENT_CONVERGENCE 的 AP1R Supersede Chain，这些文档是 historical investigation chain——保留它们是为了说明早期假设如何被逐一排除、结论如何演进，**当前结论以 canonical 报告为准**：

- Canonical（最终根因）：[CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md](../CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md)
- Evidence bundle：[debug/arm64-vgic-ap1r-nmi-active-20260806/](../../debug/arm64-vgic-ap1r-nmi-active-20260806/README.md)
- 收敛关系总图：[CONTENT_CONVERGENCE.md](../../CONTENT_CONVERGENCE.md)

## 内容概览

- 2026-07-17~24 multi-vCPU snapshot-restore 系列（分析、实验、brief、重评、handoff）
- WFI/timer delivery、KVM vtimer、RCU stall、GIC/CPU1 tick 链等专项定位
- pause/resume 调用链分析与 quiescence/KVM 分析
- v0.3.0/v0.5.0 源码 diff、trace stripped 实验、first-entry trace 指南
- Cloud Hypervisor 社区先例检索、ISSUE6966 UB 对照
- ARM64 适配问题总结（中英对，historical language pair）

## 已知链接边界

部分报告链接 `remote-results/`、`scripts/`、`*_ASSETS_*/` 等仓库外或从未入库的路径——迁移前即不可解析，按 external evidence / unavailable 处理，详见 [EVIDENCE_AVAILABILITY.md](../../EVIDENCE_AVAILABILITY.md)。

## Provenance

本目录 21 份文档原位于 `ai_sandbox/cubesandbox/` 顶层，2026-09-17 迁入（MAT-02 批次 C1）；纯 Git rename，内容零改动，仓库内入链已全部重写。
