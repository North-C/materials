# dirty_log 与 Cubelet NUMA 绑定使能指南

日期：2026-10-29。类型：配置指南。状态：源码与文档核对、命令语法检查完成；未在本次发布中部署、重启服务或执行性能测试。

[阅读指南](GUIDE.zh-CN.md) · [返回调优复现](../README.zh-CN.md) · [返回 CubeSandbox 导航](../../README.md)

- dirty_log：BoostKit PR32 的宿主动态 YAML 开关，涵盖热加载、恢复实例的生效验证与关闭方法。
- Cubelet NUMA：通过 systemd drop-in 配置 `CPUAffinity`、`NUMAPolicy=bind`、`NUMAMask`，包含拓扑选择、重启、egress 依赖检查和撤销步骤；不依赖 PR20，也无需修改沙箱 NUMA 池选择。
- 源码固定为 `2babb6f7405677c04b7fed1563c6a5d53a8e771b`；systemd 与 Linux 行为引用官方文档，访问日期为 2026-10-29。

发布副本保留原指南标题、配置与操作步骤；仅将末尾的本地源码审查记录、哈希清单链接改为固定版本的公开源码入口。本专题不附带原始日志、运行配置、补丁或二进制，也不继承父目录历史实验的性能收益。
