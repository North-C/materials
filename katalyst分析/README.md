# katalyst分析

容器混部（colocation）与资源隔离主题的资料目录：以 Katalyst 分析为主线，附同类混部引擎的对照资料。

## 文档导航

| 文档 | 类型 | 状态 |
|---|---|---|
| [metrics监控.md](metrics监控.md) | Katalyst metrics 监控分析 | 未复核 |
| [容器资源隔离.md](容器资源隔离.md) | openEuler rubik 混部引擎链接集（PSI 设计、部署、特性介绍） | 迁入待复核：纯外部链接占位，无自有正文 |

## 混部方案对照说明

Katalyst（本目录主线）与 rubik（openEuler，`容器资源隔离.md` 所指）同为容器混部/资源隔离方案：前者是字节跳动开源的混部系统，后者是 openEuler 社区的混部引擎（DaemonSet 部署、用户态运行）。两份资料作为同类方案对照保留，引用时注意区分引擎。

## Provenance

- `metrics监控.md` 自入库起位于本目录。
- `容器资源隔离.md` 于 2026-09-17 从仓库根目录迁入（MAT-04 Group R3）；纯 Git rename，内容零改动，迁移前入链为零（已验证）。

上级导航：[根目录散落文件主题](../docs/topics/root-files.md) · [内容目录](../docs/index.md)
