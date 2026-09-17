# nri-resource-policy

容器资源调度 Policy 框架的项目文档集：通过 runtimeHook 对接 Proxy/NRI，对不同类型资源（cpu/memory/disk/network）做 Affinity 综合比较与调度调整；交付形态之一是 kata-cpuset-nri DaemonSet（约束 kata Pod 的 cpuset sibling）。

## 文档导航

| 文档 | 角色 | 状态 |
|---|---|---|
| [design.md](design.md) | 框架设计（runtimeHook/statesinformer/NRI/reconciler/cgroup reader 结构图） | canonical candidate |
| [Policy模块设计文档.md](Policy模块设计文档.md) | Policy 子模块细化：截获容器变更请求、按策略调整资源后返回 | draft（骨架，章节多为空） |
| [并发问题.md](并发问题.md) | NUMA-aware 调度的资源不一致 bug 记录与解决方向 | bug record |

## 待并入

- 根级 `日志.md` 中的 kata-cpuset-nri 开发计划正文：待凭据轮换完成后拆出并入本目录（该文件当前含明文 API key，见 [迁移映射](../docs/meta/ROOT_MIGRATION_MAP.md) 的凭据风险登记）。

## Provenance

- 三份文档于 2026-02-13 随仓库首批入库（各 1 个 commit，无逐文件演进历史）。
- 2026-09-17 从仓库根目录迁入本目录（MAT-04 Group R1）；移动前后内容零改动，入链为零（迁移前已验证）。

上级导航：[根目录散落文件主题](../docs/topics/root-files.md) · [内容目录](../docs/index.md)
