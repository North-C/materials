# 三状态十五轮独立数据审计

最终补充审计范围：baseline / go / combined各5轮、最终comparison、task-composition及all-final运行约束。仅只读证据，只修改本审计文件。下文先给十五轮最终核验，再保留十轮时的阶段审计；其中关于partial/Cubelet恢复中的措辞为历史检查点，已由最终补充结论更新。

## 十五轮最终核验

`comparison.json`为complete，三个状态各5轮accepted。已重新逐轮检查正式c100/n100/w0/create-only、100条唯一seq 1–100、100成功/0错误；独立预热c1/n3/w0、3成功；清理complete、103个逐项confirmed_absent、无owned/unexpected残留。十五轮共1500正式+45预热全部成功；1545个清理ID跨轮互异，逐轮CLI正式100+预热3的并集等于清理集合。固定模板、资源及客户端hash一致。未发现数据验收阻碍最终交付的问题。

| 指标（各轮统计的中位数） | baseline | go | combined | combined 对 baseline | combined 对 go |
|---|---:|---:|---:|---:|---:|
| 整轮ms | 508.00235 | 477.62641 | 374.92959 | −133.07276 / −26.1953% | −102.69682 / −21.5015% |
| 请求平均ms | 355.94335 | 340.19908 | 278.67223 | −77.27112 / −21.7088% | −61.52685 / −18.0855% |
| P50ms | 381.851 | 361.112 | 293.911 | −23.0299% | −18.6095% |
| P95ms | 502.879 | 472.615 | 372.723 | −25.8822% | −21.1360% |
| P99ms | 505.426 | 473.240 | 373.451 | −26.1116% | −21.0863% |
| QPS | 196.84948 | 209.36866 | 266.71675 | +69.86726 / +35.4927% | +57.34809 / +27.3910% |

上述百分比与comparison一致。Go-only对baseline整轮−5.9795%，请求均值−4.4233%；仍只接受描述性变化。

### combined轮内漂移与阶段支持

| combined轮 | 整轮ms | 请求均值ms | P99ms | Cubelet cubebox-service均值ms | CubeMaster cube-e2e均值ms | before load1/总调度实体 |
|---|---:|---:|---:|---:|---:|---|
| 01 | 414.63742 | 293.12947 | 412.211 | 206.09854 | 215.08 | 0.37 / 5956 |
| 02 | 374.92959 | 278.67223 | 373.451 | 195.35433 | 202.79 | 0.72 / 9982 |
| 03 | 387.60490 | 289.58766 | 384.049 | 205.69411 | 214.80 | 5.65 / 11216 |
| 04 | 296.70435 | 210.72157 | 295.422 | 161.91856 | 169.92 | 4.93 / 11815 |
| 05 | 305.34520 | 217.17684 | 304.236 | 148.47966 | 155.49 | 4.30 / 11926 |

前3轮375–415ms、后2轮297–305ms是明显轮次分组，不应选择后两轮宣称“稳定300ms”，也不能仅用一个中位数隐去296.704–414.637ms范围。两个全覆盖主路径阶段也在后两轮下降，方向与客户端相符，说明下降不只是客户端单一计时字段的偶然变化；仍未控制重启后热度、历史网络恢复、CPU/内核工作队列状态，不能证明由NUMA单独造成。

跨状态全覆盖阶段的各轮均值中位数：Cubelet cubebox-service 278.898→287.916→195.354ms；CubeMaster cube-e2e287.070→294.820→202.790ms；sandbox-create138.054→143.134→89.913ms；CubeShim CreatePodSandbox61.270→65.140→46.980ms，均支持combined存在广泛路径加速的描述。不是每个子阶段逐轮单调下降，例如combined首轮CreatePodSandbox42.34ms比后两轮46.98/44.74ms还低。cgroup的combined均值中位数22.644ms但覆盖仅61–76%；network均值9.338ms但覆盖18–64%，不能把这些受阈值筛选阶段与完整100请求总体无条件比较。

十五轮capture gap均为master_stat缺失，precision batch均0/100；未新增可证明GC、调度或跨NUMA访问机制的连续采样证据。combined的数据文件与profile示例：[首轮raw](combined/round-01/runs/20261016T074751Z-bea5ecc6/capture/startup-latency/benchmark.raw.json)、[末轮清理](combined/round-05/evidence/cleanup.json)、[阶段比较](stage-comparison.json)。

### 最终任务构成与运行约束补充

`task-composition.json`时间为2026-10-16T07:50:32Z，总11944个任务，其中kworker7779（约65.1%）。这说明**该时刻**任务数主要由内核工作线程组成，不能倒推baseline/go阶段6040→21900的全部增量由kworker造成，更不能推出存在1545沙箱泄漏。需保留“宿主状态漂移，原因未完全辨识”，而非把任务总数增加等同清理失败。

`all-final.json`时间为07:52:59Z：五原生服务均active，全线程CPU96–191，numa_maps策略bind:1；其Mems_allowed仍0–3，与cgroup v1根cpuset限制未缩小一致，不能将NUMAPolicy绑定误写为原生服务硬cpuset mems=1。Master环境仍800/32/8GiB。八容器全部Running，docker cpuset CPU96–191/mems1；审计780个容器进程共1089线程，CPU集合均是96–191的子集且mems=1，采样完整，thread_errors/process_errors均空，exe解析成功。部分cube-proxy worker绑定到96–127内的单个CPU，是合法更窄集合，不是逃逸限制。systemd中的docker包装进程仍可能显示0–383，不抵消真实容器负载约束证据。

最终数据方面无final-blocker。最终报告应继续保留GOGC被应用覆盖、分块/重启和轮内漂移、profile缺失等限制，并结合owner独立采集的节点READY、应用健康、最终库存、本次沙箱约束和回滚证据完成全任务验收；本审计不代替这些运行状态检查。

## 以下为baseline/go十轮时的阶段审计记录

## 验收结果

十轮正式1000次、独立预热30次均成功。每轮正式raw配置为c100/n100/w0/create-only、100条唯一seq 1–100；每轮预热c1/n3/w0、3成功/0错误；invocation记录正式no_tui=true。每轮103个清理ID、全部confirmed_absent，remaining_owned_ids和unexpected_remaining_ids均空；正式100与预热3的CLI集合并集恰为清理集合。十轮ID互不重复，总计1030。没有发现raw与汇总数字不一致。

十轮 `evidence/template.json` 对象完全一致：模板tpl-cf2b04fdd4604b7c84e157fa、READY、单容器2000m/2048Mi、1G可写层、固定rootfs artifact template-anonymous。`template-current.json` 的image_info固定为arm64 sha256:e1cb43e12ba70b8453b45f0c063306faab8a6974aa3fd76982dc4d019d07c60d；`preflight.json` 本机image ID为sha256:79972015a4a2b48b18a2165af61606d87e7d859143165fcd33f104fbd8590bee。每轮context固定客户端SHA ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511。镜像digest采集是阶段前证据，逐轮模板证据核对rootfs与资源；不能说每轮独立重新计算完整镜像字节hash。

| 状态/轮 | 整轮ms | 请求均值ms | P99ms | 清理ID | before load1 / 总调度实体 |
|---|---:|---:|---:|---:|---|
| baseline/01 | 508.002 | 371.029 | 505.426 | 103 | 0.73 / 6040 |
| baseline/02 | 509.160 | 355.943 | 507.237 | 103 | 8.81 / 11455 |
| baseline/03 | 530.843 | 384.739 | 529.625 | 103 | 6.69 / 14516 |
| baseline/04 | 465.367 | 333.455 | 461.775 | 103 | 4.83 / 16729 |
| baseline/05 | 481.649 | 333.746 | 479.823 | 103 | 3.85 / 18043 |
| go/01 | 461.005 | 340.199 | 460.548 | 103 | 5.99 / 19463 |
| go/02 | 485.658 | 339.296 | 484.173 | 103 | 5.81 / 20607 |
| go/03 | 470.179 | 338.108 | 467.336 | 103 | 4.98 / 21237 |
| go/04 | 482.888 | 344.724 | 481.744 | 103 | 4.40 / 21722 |
| go/05 | 477.626 | 359.450 | 473.240 | 103 | 4.24 / 21620 |

核验路径：每轮`capture/startup-latency/benchmark.raw.json`、`warmup/benchmark.raw.json`、`evidence/{context,invocation,template,cleanup,before,after}.json`。例如[baseline首轮raw](baseline/round-01/runs/20261016T072437Z-ebbb3767/capture/startup-latency/benchmark.raw.json)、[go末轮清理](go/round-05/evidence/cleanup.json)。吞吐逐轮等于100/total_time_s；平均和nearest-rank P99均独立重算。状态中位数baseline508.00235ms、go477.62641ms，变化−30.37594ms/−5.97949%，与报告−5.98%一致。

## 需要保留的主要风险与报告修改建议

1. **宿主背景状态明显漂移，不能把−5.98%写成已证实参数收益。** `/proc/loadavg`第四字段分母从baseline首轮before的6040升至go末轮after的21900；baseline首轮after已有11454。该字段是系统现存调度实体总数（含线程），不是沙箱数，也不能直接叫僵尸进程数。它证明空API库存不等于宿主回到相同状态，但仅凭此无法区分池化、异步回收、外部任务或泄漏。证据：baseline首轮before（原始私有证据未公开）、baseline首轮after（原始私有证据未公开）、go末轮after（原始私有证据未公开）。`run_stage.py`固定sleep(5)，没有load稳定门禁；报告当前“每轮空库存门禁、轮间5秒”准确，应补充上述具体漂移，而不是写稳定静默。建议完成当前健康恢复后采只读进程/线程分类解释该现象，不能因此无归属杀进程。baseline整轮465–531ms与go461–486ms重叠明显。

2. **主路径均值没有一致改善，禁止把客户端变化归因于某个阶段。** 全覆盖的Cubelet cubebox-service各轮均值中位数278.898→287.916ms（变慢），CubeMaster cube-e2e287.070→294.820ms（变慢），而客户端355.943→340.199ms（变快）；两者并非矛盾，因为边界、并发、排队及统计不同。cgroup均值66.347→56.425ms，但覆盖baseline78–94%、go67–95%，且其P95中位数122.972→142.533ms；不能据均值就下“cgroup瓶颈改善”结论。证据：`stage-comparison.json`对应formal组，及各轮`analysis/stage-latency.csv`。

3. **profile“limited”不是创建失败，但要说明缺失。** 十轮runner-validation均status=limited、problems=[]，因官方客户端无seq→sandbox ID映射，仅基于独占声明与CLI差集推定正式100集合；analysis formal owned=100，warmup owned=0（独立预热在正式采集外，不等于没做预热）。十轮唯一manifest gap均为`master_stat:no_readable_start_offset`；Cubelet metrics前后均captured且无gaps。十轮precision.json的formal cubelet_batch_coverage observed_instances均0/100，精细补丁数据不可用；不是全阶段都获得精确profile。总报告已经说明Master trace缺失和无连续MasterGC数据，建议再提precision覆盖0。证据示例：capture manifest（原始私有证据未公开）、[runner validation](baseline/round-01/runs/20261016T072437Z-ebbb3767/capture/startup-latency/runner-validation.json)、[precision](baseline/round-01/runs/20261016T072437Z-ebbb3767/analysis/precision.json)。

4. **当前总报告必须保持partial，最终态部分待实际验收。** 草稿已清楚列combined0轮/N/A，没有虚构性能结果。正文“原生服务用…恢复”“八容器通过…真实约束”目前是方案/执行过程说明，待全组件实际验证后才能当最终成功陈述；Cubelet尚在恢复历史TAP/eBPF时应加当前状态限定。最终还需逐组件配置/生效矩阵、全线程/cgroup/NUMA policy实际证据、容器工作负载和本次沙箱实际限制、最终健康/库存及恢复耗时。`write_report.py`末尾也提示owner补最终态，不应把当前脚本输出当已完成报告。

5. **目前身份/GC语义说明基本审慎。** `version-before.json`支持社区服务身份；`all-before.json` Master环境400/16/4GiB、全线程0–383/mems0–3；`all-go.json`环境800/32/8GiB、全线程仍0–383/mems0–3、NUMA policy default，符合Go-only状态。源码SetGCPercent(90)覆盖GOGC的说明限定“按源码应为90、未直接读运行时值”，没有把环境800当GC实际800。正文CGO_DISABLED建议统一写准确构建环境`CGO_ENABLED=0`（表述小问题，不影响实测）。

## 其余计时与归属检查

正式整轮必须取summary.total_time_s；采集命令窗口包含两次CLI与外围操作，不是创建总耗时。raw.create_ms至HTTP响应头，不独立证明应用就绪。阶段父子包含和paired residual不可求和，分位数不相减。部分成功短阶段低于5ms不输出；CreateContainer load_spec_cumulative的表中0是源profile记录值（计时粒度/路径语义），不证明该操作没有成本，也不是缺失填0。当前汇总正确保留Master trace和normal-path不存在项N/A，阶段聚合是各轮摘要的中位数，不是池化阶段原始分位数。

清理证据证明1030个API实例在检查窗口内消失；不能从此扩展成宿主所有TAP/eBPF/线程/缓存资源已完全释放。未发现需要否定当前正式请求延迟数据的格式、计数、模板或清理错误，但因背景漂移与仅5轮分块设计，本审计只接受描述性比较，不接受强因果或单变量贡献结论。
