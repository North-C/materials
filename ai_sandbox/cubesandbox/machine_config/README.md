# CubeSandbox 机器配置快照

[返回 CubeSandbox 导航](../README.md)

日期：2026-10-20。类型与状态：机器环境快照；已完成 `.90` 全模块只读采集及发布副本一致性检查。本次归档不重新采集、不修改机器配置。

## .90 对比基线

机器：`192.168.25.90`；采集时间：**2026-10-20 14:36:18（Asia/Shanghai）**；运行标识：`machine-90-20261020T143618`。

包含硬件、BIOS、OS、NUMA、RCU、KVM ARM、Cube 组件、Cube 运行资源共 **8 个模块、188 项**，可用于和其他机器的 machconf JSON 快照离线对比。

| 文件 | 用途 |
| --- | --- |
| [machine-90-20261020T143618.json](machine-90-20261020T143618.json) | 单机原始结构化快照，保留 key、value、note，作为 `--compare-files` 的左侧输入 |
| [machine-90-20261020T143618.md](machine-90-20261020T143618.md) | 同批采集结果的完整可读表格，含诊断说明，硬件、BIOS、OS 优先 |
| [SHA256SUMS](SHA256SUMS) | 上述两个文件的 SHA256 校验值 |

## 来源与完整性

采集工具为自维护的 [North-C/machconf](https://github.com/North-C/machconf)，版本为 [dc7e373965cfc70b29f3b092fef137ec5659af6f](https://github.com/North-C/machconf/commit/dc7e373965cfc70b29f3b092fef137ec5659af6f)。历史本地来源是 CubeSandbox `v071-c100n100-bottleneck` 工作区的 `tools/machconf/artifacts/machine-90-20261020T143618/`；本目录中的附件是其他机器可直接使用的发布副本。

实际采集使用 Python API `collect("192.168.25.90", MODULE_ORDER)`，通过默认 root SSH 执行只读探测；JSON 由 `render_json` 输出，Markdown 按同一批结果分模块生成，采用行内代码保留方括号、下划线等原文。采集脚本退出状态为 0；等价的 JSON 采集 CLI 为：

```bash
python3 machconf.py -H 192.168.25.90 -m all -f json > machine-90.json
```

两个附件与历史来源逐字节一致，未增加额外脱敏替换；保留内网 IP、路径、进程信息和资源配置，未发现凭据字段。采集器本身的资源项白名单与脱敏行为仍适用。仅归档工具输出，没有附带完整原始 SSH 输出或系统日志；未采集项不能据此推断为关闭或不存在。

在本目录校验附件（Linux）：

```bash
sha256sum -c SHA256SUMS
```

macOS 可使用 `shasum -a 256 -c SHA256SUMS`。校验值验证文件字节一致性，不证明机器当前仍处于该配置。

## 在另一台机器上对比

以下命令在放置仓库的同一父目录执行；若仓库已存在，使用相应路径即可。依赖 Python 3、Git 和 machconf 支持的 Linux 探测环境，完整本机查询建议使用 root。

```bash
# 获取工具和基线材料
git clone https://github.com/North-C/machconf.git
git clone https://github.com/North-C/materials.git

# 在目标机器上只读采集全部模块
sudo python3 machconf/machconf.py --local -m all -f json > machine-current.json

# .90 在左侧，目标机器在右侧；默认保留相同项
python3 machconf/machconf.py --compare-files \
  materials/ai_sandbox/cubesandbox/machine_config/machine-90-20261020T143618.json \
  machine-current.json -f markdown > comparison-with-90.md
```

需要只看差异时，在对比命令中添加 `--diff-only`；需要表格软件格式时，将 `-f markdown` 改为 `-f csv` 并输出到 `.csv`。已有另一台机器的单机 JSON 时，直接替换 `machine-current.json`，离线比较不连接 `.90`。

## 适用范围与局限

- 本快照描述上述采集时间的环境，不是持续更新的“当前状态”，也不是推荐配置或自动调优配方。
- BIOS 的 C-state 为 `N.A.`；其他 `unknown`、`not_observed`、缺项或诊断状态均保留原值和说明，不作成功或启用判断。
- 动态进程、线程数量、资源使用和组件状态可能随工作负载变化；比较结果应结合采集时间与负载解释。
- 机器配置只读采集成功不代表 CubeSandbox 部署、性能或端到端测试通过。本次发布未重新运行远端采集、部署或性能测试。
