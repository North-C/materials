# 大文件与生成物

状态：`mat-01-phase-1`。本页记录存储决策入口；当前已允许大对象在通过 manifest 审阅后使用 Git LFS，但本轮没有复制、移动、删除、上传、暂存或提交大对象，也没有历史改写。

## 分类矩阵

| 对象 | 当前事实 | 分类 | Wiki/仓库策略 | 待确认 |
|---|---|---|---|---|
| `tbench-large-scale-text-editing-profile-perf-amd6.tar` | 主检出区未跟踪，598,772,736 B；`amd6` 已确认为笔误 | `unclassified evidence candidate` | 暂时不纳入；未来若纳入应使用 `amd64` canonical 名称，并重新校验 hash | owner、来源、可重建性、敏感级别、保留期 |
| `virtualization/DDI_0487_M.b_a-profile_architecture_reference_manual.pdf` | 已跟踪，161,102,669 B，命中现有 PDF LFS 规则 | `external reference` | 现有 virtualization PDFs 允许作为 LFS 对象上传；不改历史 | 后续可单独核对授权和长期 LFS 成本 |
| `research/.../vendor/sqlite-fossil-release.tar.gz` | 主检出区未跟踪，12,640,606 B，旁有 SHA-256 | `third-party input` | 本 Workspace 不处理 | 后续若重启，再确认上游 URL、版本、许可证、离线要求 |
| 根级与 KVM Excalidraw | 多个已跟踪/未跟踪图源，约 0.9–6.5 MiB | `canonical source candidate` | 图源可版本化，导出图为 derived asset；先建立关联文档 | owner、所属主题、canonical 图源 |
| CubeSandbox trace/log/TSV/CSV | 小型到约 3.6 MiB，部分已有 README/SHA256SUMS | `raw/derived evidence` | 小型文本可保留；由 manifest 区分 raw/derived/report | 缺失 revision、采集配置或生成命令的目录 |
| `__pycache__/`、`*.pyc` | 9 个 bytecode 已跟踪，另有未跟踪/忽略对象 | `generated/ephemeral` | 新对象由最小 `.gitignore` 排除；取消既有跟踪需单独批准 | benchmark 离线包是否依赖 bytecode |
| `.marscode/deviceInfo.json`、`tmp/.../dconf/user` | 主检出区未跟踪 | `machine-local candidate` | 不进入 Wiki；先确认是否有审计价值 | 是否包含环境证据或敏感设备信息 |

## 决策顺序

1. 先判断 artifact 是否支撑唯一结论；无法判断时按 evidence candidate 保护。
2. 记录字节数、SHA-256、owner、来源、采集时间、source revision 和敏感级别。
3. 判断能否从保存的输入和脚本稳定重建。
4. 再选择普通 Git、Git LFS、对象存储/release、稳定上游 URL 或不版本化。
5. manifest 必须从所属主题页和结论文档可达。

当前 manifest：[Large Object Manifest](../meta/LARGE_OBJECT_MANIFEST.md)。

当前根 `.gitattributes` 使 `*.tar`、`*.tar.gz`、`*.tgz`、`*.zip`、`*.pdf` 在获批版本化时走 Git LFS。该规则不是“所有匹配文件都应该提交”的授权；它只防止获批的大归档/PDF 误进普通 Git。

## 未来网页发布 allowlist

默认只发布脱敏 Markdown 索引和 manifest。以下内容默认不进入网页构建：

- tar/zip/gz 等归档；
- PDF 和其他第三方二进制正文；
- raw logs/results/trajectory；
- 机器状态、设备信息、绝对内部路径；
- 任何尚未完成敏感审计的对象。

## 下一 Workspace

MAT-01 只做元数据、hash、provenance 和存储决策；MAT-07 单独处理已跟踪 bytecode。两个任务都不得删除原件或改写历史。

相关治理：[信息架构的大文件策略](../meta/INFORMATION_ARCHITECTURE.md#large-file-policy) · [事实清单](../meta/INVENTORY.md#large-file-candidates) · [Large Object Manifest](../meta/LARGE_OBJECT_MANIFEST.md)
