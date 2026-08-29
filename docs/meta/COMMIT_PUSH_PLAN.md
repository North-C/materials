---
status: proposed
scope: domain-batched commit and push plan for the current materials organization workspace
last_verified: 2026-08-29
canonical: false
---

# Domain-batched Commit and Push Plan

本计划把当前 Workspace 的文档治理成果拆成可审阅、可回滚的领域提交。它不等于立即提交或 push；执行前仍需逐批检查 `git status`、`git diff --check`、链接、敏感字符串和 LFS 状态。

## 执行护栏

- 只在当前 Orca worktree `/home/lyq/orca/workspaces/materials/materials-information-architecture` 提交。
- 不在主检出区 `/home/lyq/Projects/materials` 执行写操作、暂存、提交或清理。
- 每批只 `git add` 明确列出的路径；不用 `git add .`。
- push 仅限当前 workspace 分支 `North-C/materials-information-architecture`；不 push `main`，不打 tag，不发布网页。
- 598 MB perf tar、vendor tar、主检出区 dirty/untracked 文件不纳入本轮提交。
- 现有 virtualization PDFs 已按获批对象 ID 上传至 LFS；本计划只提交 LFS 规则和 manifest，不重写历史。

## 建议提交顺序

### Commit 1：governance baseline

目的：先固定仓库入口、治理规则和最小 ignore。

路径：

- `README.md`
- `.gitignore`
- `docs/index.md`
- `docs/CONTENT_CATALOG.md`
- `docs/meta/INVENTORY.md`
- `docs/meta/INFORMATION_ARCHITECTURE.md`
- `docs/meta/MIGRATION_PLAN.md`
- `docs/meta/TASK_BACKLOG.md`
- `docs/meta/CONTENT_ORGANIZATION_REPORT.md`
- `docs/meta/decisions/0001-materials-information-architecture.md`
- `docs/meta/decisions/0002-repository-native-web-wiki.md`

示例提交信息：`docs: establish materials governance baseline`

### Commit 2：large object governance

目的：记录大对象策略和获批 LFS 规则，不纳入未获批大对象。

路径：

- `.gitattributes`
- `docs/topics/large-files.md`
- `docs/meta/LARGE_OBJECT_MANIFEST.md`

示例提交信息：`docs: document large object governance`

### Commit 3：CubeSandbox convergence

目的：提交 CubeSandbox 项目入口、收敛图和第一批证据 manifest。

路径：

- `docs/topics/cubesandbox.md`
- `ai_sandbox/cubesandbox/README.md`
- `ai_sandbox/cubesandbox/CONTENT_CONVERGENCE.md`
- `ai_sandbox/cubesandbox/EVIDENCE_AVAILABILITY.md`
- `ai_sandbox/cubesandbox/benchmark/reports/README.md`
- `ai_sandbox/cubesandbox/perf/MANIFEST.md`
- `ai_sandbox/cubesandbox/debug/arm64-vgic-ap1r-nmi-active-20260806/MANIFEST.md`

示例提交信息：`docs: converge cubesandbox navigation and evidence`

### Commit 4：research convergence

目的：提交 research 项目入口、dirty input 保护清单和收敛图。

路径：

- `docs/topics/research.md`
- `research/README.md`
- `research/agent_cpu_sandbox_toolkit/README.md`
- `research/CONTENT_CONVERGENCE.md`
- `research/DIRTY_INPUT_MANIFEST.md`

示例提交信息：`docs: map research toolkit inputs and provenance`

### Commit 5：root file mapping

目的：提交根目录散落文件的分类地图，作为后续 rename/move 前置条件。

路径：

- `docs/topics/root-files.md`

示例提交信息：`docs: map root-level document candidates`

## 每批提交前检查

对每个 commit 执行：

1. `git status --short --branch`
2. `git diff --check -- <paths>`
3. 针对该批 Markdown 跑相对链接检查；仓库外 evidence 路径只记录为 external-local-evidence，不作为 repo link 失败。
4. 对该批文本跑敏感模式检查，不读取或输出 `github-tokens.md` 内容。
5. `git diff --cached --name-status` 确认只包含该批路径。
6. `git diff --cached --diff-filter=D --name-only` 必须为空。
7. `git lfs status` 确认没有意外 staged LFS 对象。

## Push 前检查

- `git log --oneline --decorate -n 8` 能清楚显示按领域拆分的提交。
- `git status --short --branch` 没有未预期 staged 内容；若保留未跟踪后续文件，必须说明原因。
- `git rev-parse --abbrev-ref HEAD` 输出 `North-C/materials-information-architecture`。
- `git remote -v` 指向预期远端。
- 执行 `git push origin North-C/materials-information-architecture` 前再次确认不包含大 tar、vendor tar、凭据或网页发布配置。

## 回滚策略

- 每个领域提交可独立 `git revert`。
- 如果 push 后发现某批文档需要重做，优先追加修正提交，不改写历史。
- 若误纳入凭据或不应公开对象，停止继续 push，先走 MAT-05 私密敏感审计和用户确认流程。
