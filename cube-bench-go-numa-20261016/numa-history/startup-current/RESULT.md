# NUMA 阶段 Cubelet 启动观察结论

只读观察，未操作服务、未 kill/restart、未改参数。2026-10-16 07:45:53 UTC 最终采样：Cubelet pid 1576240 active/running，NRestarts=1，Result=success；Egress pid 1597696 active/running，NRestarts=10，Result=success；9998、9999、9091 均监听；Cubelet D-state 线程为 0，无本次时间窗 OOM/RCU-stall/blocked-task/soft-lockup 等内核告警。服务级/API/node/template健康验收由主代理继续负责。

关键时序（UTC）：

- 07:34:17 开始启动，initial pid1575615；07:34:38 shell记录它为stable/MainPID。
- 07:35:02 parent被SIGKILL，child1576240继续存活；systemd重启一次；另一次spawn因mainMutexLock 1秒timeout退出，stable PID最终指向1576240。
- 07:40:22 共3920个不同no-state TAP清理记录；07:40:29完成4002个。由于Egress尚未ready，清理的DELETE拒绝连接，记录保持Cleaning；没有删除他人沙箱或全局清空。
- 07:40:29–07:45:43 日志静默。每分钟采到不同线程在BPF map_lookup_elem→bpf_map_copy_value→synchronize_rcu等待；期间旧D线程context-switches继续增长，不能解释为同一次永久等待。
- 07:45:43.310772 日志明确 `network runtime stale policy map gc: keep=4002 deleted=0`。
- 07:45:43.464740 日志 `cubelet successfully booted in 640.788864s`。同文另有ERROR级重复记录，内容是成功，不能仅按level判启动失败。
- 07:45:53 采到三个端口均ready，D-state为0，Egress已自动恢复active。

基线 commit 31d911e 的源码证据见 baseline-source-excerpts.txt：main.go通过NEED_SET_MNT启动自身子进程，child明确调用parentExit()->pp.Kill()；startup shell只等initial最多20秒。当前父子切换与单次systemd重启符合这个既有生命周期竞争；没有OOM证据。mainMutexLock为bbolt 1秒锁超时，可解释重复child退出。

Egress prepare脚本显式只等待Cubelet bootstrap 60秒。Cubelet恢复实际耗时640.79秒，超出这个依赖检查窗口，故Egress曾多次启动失败；该暂态有真实失败证据，不应抹除。同步stale policy map扫描直到完成才写日志，最终keep=4002/deleted=0与观察的中间静默相符。

决定继续等候而不立即再重启的依据是扫描记录持续推进、进程/重启数稳定、内核无错误、已知历史启动901秒、当前同步恢复结构明确。该结果证明本轮配置下最终可恢复到监听状态；不证明NUMA对启动耗时毫无影响，也不将NRestarts/Egress短时失败伪称从未发生。正式压测必须在主代理全部健康门禁及NUMA实际生效验收后开始。

证据：每次观察JSON、gc-and-boot-completion.jsonl、基线源码摘录、现有启动脚本摘录。manifest.json保存文件SHA256。
