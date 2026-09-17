# guest-image

CubeSandbox 客户机镜像与内核操作文档集：镜像构建、版本决策与关联重测。

## 文档导航

| 文档 | 角色 | 状态 |
|---|---|---|
| [CUBESANDBOX_GUEST_IMAGE_OCI_VMLINUX_RELATIONSHIP.md](CUBESANDBOX_GUEST_IMAGE_OCI_VMLINUX_RELATIONSHIP.md) | OCI 镜像与 vmlinux 的关系说明 | 未复核 |
| [CUBESANDBOX_GUEST_IMAGE_REPLACEMENT.md](CUBESANDBOX_GUEST_IMAGE_REPLACEMENT.md) | 镜像更换决策 | 未复核 |
| [CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md](CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md) | openEuler 镜像构建指南 | operations；命令执行前需版本/环境复核 |
| [CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md](CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md) | vmlinux 裸机构建 | operations；同上 |
| [CUBESANDBOX_GUEST_IMAGE_AB_20260725.md](CUBESANDBOX_GUEST_IMAGE_AB_20260725.md) | 镜像 A/B 对比（2026-07-25） | dated report |
| [CUBESANDBOX_COMMUNITY_GUEST_IMAGE_ROLLBACK_RETEST_20260727.md](CUBESANDBOX_COMMUNITY_GUEST_IMAGE_ROLLBACK_RETEST_20260727.md) | 社区镜像回滚重测（2026-07-27） | dated report |

镜像构建产物的 checksum/manifest 边界见 [benchmark/checksums](../benchmark/checksums/)；镜像相关的性能报告在 [perf/reports](../perf/reports/)。

## Provenance

六份文档原位于 `ai_sandbox/cubesandbox/` 顶层，2026-09-17 迁入本目录（MAT-02 批次 C3）；纯 Git rename，内容零改动，迁移前入链均已重写。

上级导航：[CubeSandbox README](../README.md) · [内容收敛图](../CONTENT_CONVERGENCE.md)
