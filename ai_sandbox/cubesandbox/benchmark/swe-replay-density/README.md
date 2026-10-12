# SWE 轨迹回放密度测试材料

本目录发布 `density-bench` 的 CubeSandbox 测试版构建脚本与操作指南。
负载执行由上游原生 `agent_vm_bench/bench-core` 完成；随包小工具负责配置、采样和验收。

- [完整用户指南](docs/CUBESANDBOX_DENSITY_GUIDE.md)：从镜像导入到模板、预检、密度阶梯和指标验收。
- [测试数据、Excel 与图表](results/README.md)：.95 功能验证、.90 两批密度结果、准入与中断记录，以及图表修正说明。
- [镜像筛选与构建脚本说明](CUBESANDBOX.md)：55 条来源、原始镜像拉取、envd 适配与任务恢复。
- [源码改动清单](SOURCE_CHANGES.md)：修改、新增、既有未提交改动和历史验证边界。
- [测试版 build_template.py](build_template.py)：与已验证版本逐字节一致。
- [发布文件 SHA256](SHA256SUMS)：在本目录运行 `sha256sum -c SHA256SUMS`。

## 文件与外部输入

```text
swe-replay-density/
├── build_template.py
├── CUBESANDBOX.md
├── SOURCE_CHANGES.md
├── SHA256SUMS
├── results/                       # 脱敏结果、图表、配置与来源清单
└── docs/
    ├── CUBESANDBOX_DENSITY_GUIDE.md
    └── tools/
        ├── make_density_config.py
        ├── verify_density_run.py
        ├── snapshot_cube_ids.py
        └── host_sampler.py
```

运行前还需要单独取得原项目的 `swerebench-offline-replays-master/verified-135/manifest.csv`
和 `replays/`，以及目标架构的适配镜像。这里不包含轨迹、镜像 tar、registry 数据、实验凭据、
集群模板 ID 或原始运行日志。指南第 2.3 节给出分别部署发布文件与数据的命令。

55 个已导出 tar 是 `linux/amd64`，历史 `.95/.90` 测试节点是 ARM64；二者不能直接混用。
需要 x86 镜像包时，从原项目 `exports/cubesandbox-x86-55-20261010/` 取得全部 tar 和校验清单。
目标集群必须重新创建模板并完成单条端到端预检。

## 固定身份与发布处理

- 构建脚本 SHA256：`ed82005f199101fb0c532a4660fe3c6f4dda67ea130a78d3cd0d33d568a1658a`。
- 原指南 SHA256：`33d13f07c2f1066026804104010e8be614e30dc99219ca818c59f63b74910fba`。
- 密度驱动：`JackWeiw/agent_vm_bench@93f978f7ec27d9bc519dca2efdc809ada09acbaa`；SDK `cubesandbox==0.7.0`。
- 发布版指南将本机目录替换为 `/srv/density-lab` 或待填写参数，将节点地址替换为文档示例地址；
  `.95/.90` 仅为历史环境简称。失效的本地证据链接改为目录说明，原证据仍保留在原项目。
- 三个指南辅助工具和宿主采样器均按已验证文件原样复制；`CUBESANDBOX.md` 摘录清单与适配说明。

本次是材料发布，不重新执行 Docker load、模板创建或压力测试。发布副本经 19 项既有离线单元测试、
20 个 Bash 代码块及 27 次指南子进程检查；归档结果验证覆盖普通非零、超时门槛和残次报告拒绝。
精确命令、工具版本、UTC 时间和原始输出保存在原项目 `validation/20261012-materials-publication/`。

`materials` 中这是发布快照；后续修改应回到原项目验证，再同步本目录并更新哈希。
