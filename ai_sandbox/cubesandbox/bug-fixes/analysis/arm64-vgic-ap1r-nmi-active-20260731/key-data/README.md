# key-data 说明：验证矩阵单元格 → 数据文件映射

2×2 析因矩阵（串行 20 次创建，模板 tpl-42e1ad04f7354b1295e05b78）的归档对应关系：

| 内核 \ VMM | 原版 VMM (7630247b) | icc 修复 VMM (a68d64cd) |
|---|---|---|
| 未打补丁内核（sbench） | 5/20（2026-07-31 11:10 前的基线轮，记录在主报告；另 2026-08-03 复跑前 5 次仍复现 reset guest time/reseed，中途清理未归档） | `serial-fixedvmm-unpatched-kernel-deploy-test.log`（5/20） |
| aprmask 内核 | `serial-origvmm-aprmask.log`（5/20） | **20/20**（2026-07-31 14:56 直播观察；归档见下注） |

注：`serial-aprmask-fixedvmm-deploy-test.log`（14/6）是 aprmask 内核首轮，6 个失败全部为重启后资源未就绪的 `130597 no more resource`（约 1 秒内返回的基建错误，非目标签名），随后同配置干净重跑 20/20 pass、探针 bit63=0（`ap1r-after-aprmask-kernel.log`）。20/20 该轮输出当时经会话终端展示，未落盘归档；如需归档副本，可在 aprmask 内核下重跑 `serial_create_test.sh`（.90 当前默认启动为未打补丁内核，需 `grub2-reboot` 到 `6.6.0-sbench-irqbypass-xarray-v2-aprmask`）。

并发矩阵摘要见 `concurrent-bench-summary.jsonl`（A 模板 c10/200、c20/300、c50/500）及 `remote-results/arm64-aprmask-validation-20260731/`（B/C 模板 c20/300、原版 VMM 对照 c10/200）。并发残余失败均为 `Create container failed: ttrpc timeout`（与目标 bug 不同签名不同阶段，原版 VMM 对照失败率相同）。
