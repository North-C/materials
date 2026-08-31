# Cubelet cgroup v1 采集纠错

## 结论

正式累计run中的Cubelet PSS/USS有效；原组件表中的Cubelet `cgroup current=69.648 MiB`无效。采集器错误地读取了systemd `ControlGroup`，没有读取Cubelet进程在cgroup v1 memory controller中的真实路径。

## 正式raw证据

`community-cumulative-r5/deep-samples.jsonl`首个N=0样本：

```text
utc=2026-08-30T14:40:59.296342+00:00
boot_id=<formal-run-boot-id>
systemd ControlGroup=/system.slice/cube-sandbox-cubelet.service
collector cgroup.path=/system.slice/cube-sandbox-cubelet.service
collector cgroup.memory_current=73031680
/proc/PID/cgroup memory path=/cube_sandbox/cubelet
```

同一正式raw中的`process.cgroups`已经保存真实memory controller路径，所以能够确认归因错误；但没有保存`/cube_sandbox/cubelet/memory.usage_in_bytes`，无法事后补算各density真实Cubelet cgroup charge。

## 2026-08-31只读复核

`2026-08-31T00:33:30Z`只读SSH复核仍显示：

```text
/proc/PID/cgroup: memory:/cube_sandbox/cubelet
actual memory.usage_in_bytes=111816704
systemd-path memory.usage_in_bytes=69591040
Cubelet Pss=156010 KiB
Sandbox count=0
```

该复核boot ID为`<verification-boot-id>`，与正式run不同，说明中间发生过重启。因此它只用于再次验证“两个cgroup路径及charge不同”，不得用来声称正式run在同一boot、同一Cubelet进程内完成了PSS回收。

## 修复

`tools/sandbox_memory_footprint/measure.py`现优先从`/proc/PID/cgroup`解析memory controller路径，只有进程路径不可用时才回退到systemd `ControlGroup`；对应单元测试覆盖cgroup v1分离路径。

Evidence内的`scripts/measure.py`是正式run所用采集器快照，为保持raw lineage而保留原样；复测应使用worktree中已修复的`tools/sandbox_memory_footprint/measure.py`。

Raw evidence与采集器快照保留在受控本地，没有发布到Materials。
