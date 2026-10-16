# cube-bench 计时分析报告：TUI 计时偏差与 `-no-tui` 运行时间轴

- 代码版本：`examples/cube-bench`（分支 `North-C/v071-c100n100-bottleneck`，未改动；最近一次相关提交 `725b7660`）
- 依赖：`github.com/charmbracelet/bubbletea v1.3.10`
- 关注场景：`-m create-only -c 100 -n 100`
- 日期：2026-10-15
- 适用版本：v0.7.1、v0.7.2、v0.7.3 与 master（截至 `origin/master` `5741deb4`，2026-10-15）的 cube-bench 源码完全相同，本报告的结论和行号对它们都适用。v0.5.1 到 v0.7.1 之间与计时相关的逻辑也没有变化（`-w > 0` 时除外）。详见第三部分。

---

## 第一部分：TUI 模式下的计时偏差

### 1.1 现象

在 c100 n100 create-only 的测试中：

| 运行方式 | Total Time | CREATE max |
|---|---|---|
| 默认 TUI，多数情况 | 约 0.30s | 约 153ms |
| 默认 TUI，偶尔 | 约 0.16s | 约 153ms |
| 加 `-no-tui` | 稳定在约 0.16s | 约 153ms |

单个请求的最大耗时只有约 153ms，但 TUI 模式下总时长常常接近它的两倍，并且呈现双峰。

### 1.2 结论

TUI 模式下，Total Time 的停表点在 **Bubble Tea 程序退出之后**（`main.go:444`）。所以它测的是「所有请求完成 + TUI 把 100 个结果逐个处理完 + TUI 退出」的总时间，不是请求本身的完成时间。TUI 处理结果的开销和终端写入的阻塞全部被计进了 Total Time 和 Throughput。

**CREATE 的单请求延迟（min/avg/P99/max）不受 TUI 影响**。它们在 worker goroutine 里围绕 `client.Do` 单独计时（`runner.go:30-42`），与结果什么时候被 UI 消费无关。受影响的只有 `Total Time` 和 `Throughput`（= 成功数 / Total Time）。

### 1.3 计时窗口对比

```
main.go:424  startTime = now ─────────────────────────────────────────┐
                                                                      │  Total Time
  [ 请求阶段：100 个 worker 并发 create，约 150ms ]                    │
  [ 结果消费：TUI 串行处理 100 条 resultMsg（Update + View + 锁）]     │  ← TUI 额外开销
  [ TUI 退出：doneMsg → Quit → shutdown → 最后一次 flush → 还原终端 ]   │  ← TUI 额外开销
                                                                      │
main.go:444  elapsed = since(startTime) ──────────────────────────────┘
```

`-no-tui` 时，「结果消费」只是一个 `for range` 往切片里 append，也没有退出流程，所以 Total Time ≈ 最慢那个请求的完成时间。

### 1.4 TUI 的结果消费路径（为什么慢）

Bubble Tea 的结果消费是**严格串行**的，每一条结果都要走下面这一整圈：

```
handleCommands goroutine 收到 cmd
  └─ go func(){ msg := cmd(); p.Send(msg) }()        tea.go:354-365   每条结果新起一个 goroutine
       └─ waitForResult: <-resultCh 取 1 条           ui.go:54-61
       └─ p.Send → p.msgs（无缓冲）
eventLoop
  └─ model.Update(resultMsg)                          ui.go:86-101    append 并返回下一个 waitForResult
  └─ cmds <- cmd（无缓冲，交还给 handleCommands）     tea.go:496-499
  └─ p.renderer.write(model.View())                  tea.go:502      每条消息都完整渲染一次
       └─ View(): lipgloss 边框、渐变进度条、
          renderStats 遍历全部已收结果                ui.go:122-231
       └─ write() 要拿 renderer.mtx                  standard_renderer.go:303-304
```

这条路径上有三处成本：

1. **每条消息都同步渲染一次完整 `View()`。** 上一次分析在 M4 上做了 benchmark，单次 `View()` 约 0.1ms、963 次内存分配。tickMsg（150ms 一次）和 `progress.FrameMsg` 也会各触发一次 `View()`。`renderStats` 每次都遍历全部结果，总开销是 O(n²)，n=100 时可以忽略，n 到几千时会变得明显。
2. **写终端会卡住 event loop。** renderer 按 60fps（每 16.7ms）调用 `flush()`，`flush()` 在持有 `r.mtx` 的情况下调用 `r.out.Write` 写终端（`standard_renderer.go:161-163, 283`）。event loop 的 `renderer.write()` 要拿同一把锁。通过 SSH 手动运行时，如果 pty 缓冲已满或 SSH 链路慢，`Write` 会阻塞，event loop 也跟着停下，结果消费随之暂停。
3. **结果集中在尾部到达。** c=n=100 时 100 个请求同时发出，完成时间挤在很窄的窗口里。请求阶段 TUI 基本无事可做，请求一结束，100 条结果却要排队串行处理，这段时间全部加在 Total Time 的末尾。

另外，退出阶段也在计时窗口内：`doneMsg` → `tea.Quit` → `QuitMsg` → `eventLoop` 返回 → `shutdown()`。`shutdown()` 会等输入读循环退出（`waitForReadLoop`，最长等 500ms，`tty.go:109-117`），再执行 `renderer.stop()` 做最后一次 flush，最后还原终端状态（`tea.go:810-835`）。这些都完成后 `p.Run()` 才返回。

### 1.5 本地复现数据

用 dry-run 排除服务端因素（`--dry-latency 150,0 --dry-error-rate 0 -m create-only -c 100 -n 100`）。TUI 模式用 `script` 包一层 160 列的伪终端，输出丢弃到 `/dev/null`。2026-10-15 在 macOS / M4 上重跑：

| 运行 | `-no-tui` Total | TUI（160 列）Total | max |
|---|---|---|---|
| 1 | 0.152s | 0.185s | 150.0ms |
| 2 | 0.151s | 0.186s | 150.0ms |
| 3 | 0.151s | 0.185s | 150.0ms |
| 4 | 0.151s | 0.183s | 150.0ms |
| 5 | 0.151s | 0.185s | 150.0ms |

在本地 CPU 空闲、终端输出直接丢弃的理想条件下，TUI 已经稳定多出约 **33ms**。在压测节点上，CPU 同时在启动 100 个 VM，而且通过 SSH 输出到真实终端，这部分开销会被放大。

> 更正：上一轮分析一度认为「TUI 不是原因」。那次测试用的伪终端宽度为 0，`WindowSizeMsg` 把 `m.width` 设成了 0，`View()` 直接返回空串（`ui.go:123-125`），渲染开销全被跳过，结论有误。设置 160 列之后，差异就出现了。

### 1.6 关于 0.30s / 0.16s 双峰

- **已确认：** TUI 会把结果消费和退出时间计入 Total Time，`-no-tui` 消除了这部分，总时长稳定在约 160ms。
- **推断（尚未在节点上直接验证）：** 双峰中多出的约 150ms，最可能来自 1.4 第 2 点。某次 `flush()` 写终端被阻塞时就是 0.30s，没被阻塞时就是 0.16s。另一个可能是 cube-bench 进程本身被 CFS throttle 或抢不到 CPU。由于 `-no-tui` 下总时长已经稳定，后者即便存在，影响也很小。可以用 `-no-tui` 连跑多轮，同时记录 cgroup `cpu.stat` 里的 `nr_throttled` 和 `cpu.pressure`，彻底排除。

### 1.7 TUI 界面上 Elapsed 的另一个差异

TUI 面板上显示的 `Elapsed` 从**收到第一条结果**开始计（`ui.go:93-95, 138`），和最终报告里从 `startTime` 开始计的 Total Time 不是同一个值，两者不能直接对比。

### 1.8 修复建议

1. **把停表点移到请求全部完成的时刻（推荐）。** 在 `RunBenchmark` 里，`wg.Wait()` 之后、`close(resultCh)` 之前记录结束时间，`main` 改为用这个值算 elapsed，不再在 UI 退出后自己停表。`main` 是在 channel 关闭之后才读这个值的，`close` 本身就提供了 happens-before 保证，不需要额外加锁。这样 TUI 渲染多慢都不会影响测量结果。只需改 `runner.go` 和 `main.go` 两处，再补一个单测。
2. **可选：TUI 批量消费结果。** `waitForResult` 取到一条后，把 channel 里已有的结果一次性取完，作为一条消息交给 Update，避免 100 次串行的 `View()`。
3. **当前的规避办法：** 测时延和吞吐时一律加 `-no-tui`。stdout 不是 TTY 时（例如重定向到文件或管道），cube-bench 会自动启用 no-tui（`main.go:129`）。

---

## 第二部分：`-no-tui` 模式的运行流程与计时

### 2.1 参与的 goroutine 和同步关系

| 角色 | 运行在哪个 goroutine | 同步 / 异步 | 会阻塞在哪里 |
|---|---|---|---|
| `main` | 主 goroutine | 全程同步、顺序执行 | `for r := range resultCh`，直到 channel 关闭 |
| `RunBenchmark`（生产者） | `go RunBenchmark(...)`，`main.go:426` | 相对 main 异步 | `sem <- struct{}{}`：在飞数达到 c 时等待；`wg.Wait()` |
| worker × n | 每次迭代一个 `go func(seq)`，`runner.go:163` | 相互之间并发；单个 worker 内部 create →（delete）→ 发送结果是同步的 | `client.Do` 等响应头；`io.ReadAll` 等 body |
| `net/http` Transport 内部 | 每条连接的 readLoop / writeLoop、拨号 goroutine | 对 worker 透明，`Do` 从调用方看是阻塞调用 | — |

几个关键的同步点：

- **`resultCh` 的缓冲区大小为 `cfg.Total`**（`main.go:422`），worker 执行 `resultCh <- r` 永远不会阻塞，main 消费得快慢不会反压到请求侧。
- **信号量 `sem` 的容量为 c**（`runner.go:153`）。它是闭环模型：一个槽位要等对应的 worker 把结果发进 channel 之后才释放（`defer func(){ <-sem }()`，`runner.go:165`）。c=n 时整个循环不会在信号量上阻塞，100 个 goroutine 几乎同时被放出去。
- **defer 的执行顺序：** `defer wg.Done()` 先注册，`defer <-sem` 后注册，所以是先释放槽位、再 `wg.Done()`。
- **channel 关闭时机：** `wg.Wait()` 等到最后一个 worker 执行完 `wg.Done()` 之后才 `close(resultCh)`（`runner.go:176-177`）。main 的 `range` 要等到 close 才退出，所以 main 停表一定在最后一个 worker 结束之后。

### 2.2 请求如何发送

**预先准备（不计时）**

- `parseConfig` 提前构造好请求体 `cfg.requestBody`（JSON：`templateID`，可选的 `metadata.host-mount` 和 `network` 规则）和请求头 `Authorization: Bearer <key>`（`main.go:183-196`）。每次请求直接复用，JSON 序列化不进计时。
- 预热 `RunWarmup`（`runner.go:134-150`）：串行执行 `-w` 次 `benchOne`，不计时。
  - **默认 `-w 0` 时直接返回 `nil`，`RunBenchmark` 会新建一个 client**（`runner.go:156-158`）。所以正式压测的 100 个请求全部要新建 TCP 连接，建连时间算在各自的 `CreateMs` 里。
  - `-w k` 时复用预热用过的 client，但预热是串行的，实际只预热了 1 条 keep-alive 连接，其余 c-1 条仍然要新建。

**HTTP client**（`runner.go:119-129`）

- `MaxConnsPerHost = MaxIdleConnsPerHost = c + 20`，连接数上限比并发度宽，请求不会在 Transport 里排队等连接。
- `Timeout: 120s`，单个请求（含读 body）最多 120 秒。
- 未关闭 Go 默认的 `Accept-Encoding: gzip`。

**单次迭代 `benchOne`**（`runner.go:25-90`）

1. `POST {api}/sandboxes`，状态码必须是 200 或 201。
2. `io.ReadAll` 读完响应体，再 `json.Unmarshal` 解析出 `sandboxID`。
3. `create-delete` 模式下接着发 `DELETE {api}/sandboxes/{id}`，状态码必须是 200 或 204。`create-only` 模式到此结束，创建的 sandbox 会一直保留。

### 2.3 时长如何计算

| 指标 | 开始 | 结束 | 包含 | 不包含 |
|---|---|---|---|---|
| `CreateMs` | `t0 := time.Now()`，`runner.go:30` | `client.Do` 返回，`runner.go:42` | 构造 request、获取连接（含 TCP 建连）、发送请求、服务端处理、收到**响应头** | 读 body、JSON 解码、发送到 channel |
| `DeleteMs` | `runner.go:67` | `runner.go:77` | 同上 | 同上 |
| Total Time（`cfg.elapsed`） | `startTime`，`main.go:424`，预热之后 | `main.go:444`，main 收完所有结果之后 | 见 2.5 的公式 | 预热、报告渲染、写 JSON 文件 |
| Throughput | — | — | 成功数 / Total Time（`report.go:26-29`、`main.go:315-318`） | — |

- `CreateMs` 精度为微秒，换算成毫秒浮点数。
- 分位数等统计只用 `Err == ""` 的结果（`report.go:11-16`）。失败请求的耗时会计入 Total Time，但不会计入 max/P99。
- 分位数用 nearest-rank 方法，不做插值（`stats.go`）。n=100 时 P99 就是第 99 小的值。

### 2.4 代码逻辑时间轴（c=100，n=100，create-only，`-no-tui`）

以 `startTime` 为 0 点。下面的时间是以服务端约 150ms 为例的示意值，量级来自本地 dry-run 和节点上的实测（Total ≈ 160ms）。

```
时间        main goroutine                RunBenchmark goroutine           worker #i（共 100 个，并发）
──────────  ────────────────────────────  ───────────────────────────────  ─────────────────────────────────────────
(计时前)    parseConfig: 构造 body/header
            renderBanner / renderConfig
            RunWarmup（-w 0 时直接返回 nil）
            make(resultCh, 100)

 0 ms   ●  startTime = time.Now()          main.go:424
            go RunBenchmark(...) ─────────▶ 新建 http.Client（client 为 nil 时）
            collectWithSimpleProgress:      for i in 1..100:
              lastPrint = now                 wg.Add(1)
              range resultCh ⏸ 阻塞            sem <- {}   (c=n，不阻塞)
                                              go worker(i) ──────────────▶ t0_i = time.Now()           ┐
~0–1 ms                                     循环结束（100 个 goroutine     NewRequest + 设置 header     │
                                            在 1ms 内全部放出）            client.Do:                    │
                                            wg.Wait() ⏸ 阻塞                 拨号新建 TCP 连接           │ CreateMs_i
                                                                             写请求                      │
                                                                             ⏸ 等响应头（服务端处理）     │
                                                                             ……                          │
~150 ms                                                                    Do 返回                      ┘
                                                                           CreateMs_i = since(t0_i)
                                                                           io.ReadAll(body)    ┐ 不进 CreateMs，
                                                                           json.Unmarshal      ┘ 但进 Total
                                                                           resultCh <- r  (有缓冲，不阻塞)
              ◀── 收到 r，append ────────────────────────────────────────  <-sem；wg.Done()
              (距 lastPrint 超过 200ms
               才打印一次进度)
  ……          ……（陆续收到其余结果）
~155 ms                                                                    最后一个 worker：wg.Done()
                                            wg.Wait() 返回
              ◀──────────────── close ───── close(resultCh)
              len==100 → 打印 100%
              range 结束，返回 results
~160 ms ●  elapsed = since(startTime)      main.go:444   ← Total Time 停表
(计时后)    RenderReport（统计、直方图、sparkline）
            exportJSON（-o）
            有失败且非 dry-run 时 exit(1)
```

### 2.5 Total Time 的构成

```
Total Time ≈ max_i ( 派发偏移_i + 调度延迟_i + CreateMs_i + 读body与解码_i + 发送到channel_i )
             + close 后唤醒 main 的延迟
             + 收集循环里的少量开销（append、偶尔打印进度）
```

- **派发偏移**：第 i 个 goroutine 被 `go` 出来的时间点。c=n 时 100 个都在 1ms 内放出。c<n 时，后面的迭代要等前面的槽位释放，这是闭环压测本来的语义。
- **调度延迟**：goroutine 被创建到真正执行 `t0` 之间的时间。CPU 紧张时这一段会变长，但它不进 `CreateMs`。
- **读 body 与解码**：CubeAPI 有 `CompressionLayer`，Go client 默认带 gzip。如果响应头先到、body 后到，晚到的部分只算进 Total Time，不算进 `CreateMs`。
- 节点上实测 Total ≈ 160ms、max ≈ 153ms，差出的约 7ms 就是上面这几项的总和，客户端开销很小。

### 2.6 解读 `-no-tui` 数据时的注意点

1. **Total Time 不完全等于 max。** 它还包含 `CreateMs` 窗口之外的 body 读取、调度等开销，正常情况下比 max 多几 ms。如果差值明显变大，先看有没有失败请求（失败不进 max）、body 有没有晚到。
2. **默认 `-w 0` 不复用连接。** 每个请求的 `CreateMs` 都包含一次 TCP 建连（如果是 https，还包括 TLS 握手）。要排除建连开销，需要至少预热 c 条连接。现有的串行预热做不到这一点。
3. **c=n 测的是突发并发。** 100 个请求同时打到服务端，分位数主要反映服务端的排队情况，不是稳态吞吐。
4. **create-delete 模式下槽位要等 delete 做完才释放。** 吞吐是「完成的 create+delete 迭代数/秒」，create 的实际并发度低于 c。delete 失败会把整条迭代判为失败，这条迭代的 `CreateMs` 也会被排除在统计之外。
5. **Sparkline 的横轴是完成顺序**（结果进入 channel 的顺序），不是 seq 顺序。

### 2.7 如果要进一步拆分时间

可以给 `IterResult` 加三个相对 `startTime` 的时间戳：`StartOff`（t0）、`HdrOff`（`Do` 返回）、`DoneOff`（读完 body 并解码），并写进 JSON 报告的 `raw`。这样就能直接看出最慢的那条请求，时间是花在派发调度、服务端处理还是 body 传输上，也能和 Cubelet / CubeShim 侧的 perftrace 按时间对齐。

---

## 第三部分：版本核对（v0.5.1 → v0.7.1，以及 master）

核对时间 2026-10-16，先执行 `git fetch origin --tags`，再比较。文中日期均为 git 提交日期。

### 3.1 v0.7.1 之后：cube-bench 源码无变化

| 比较对象 | 结果 |
|---|---|
| v0.7.1 tag | 就打在本分支 HEAD（`31d911e4`）上，本报告分析的就是 v0.7.1 的代码 |
| v0.7.2（2026-09-24）、v0.7.3（2026-10-12） | `examples/cube-bench` 目录树与 v0.7.1 完全相同 |
| `origin/master`（`5741deb4`，比 HEAD 多 113 个提交，HEAD 是其祖先） | `git diff HEAD origin/master -- examples/cube-bench` 为空，目录也没有被移动或改名 |

GitHub 上没有进行中的 cube-bench PR。唯一相关的 #1623（种子化负载生成器和 A/B 对比报告）已关闭，没有合入。

本地另有两个早期个人分支也改过这个目录：`north-c/feature/arm64-upstream-pr256`（2026-06）和 `north-c/snapshot/arm64-cubemaster-wip-20260522`（2026-05，删除了整个目录）。两者都不在 v0.7.1 和 master 的历史上，与本报告无关。

### 3.2 v0.5.1 → v0.7.1 期间 cube-bench 的修改

v0.5.1 是 v0.7.1 的祖先。`git log v0.5.1..v0.7.1 -- examples/cube-bench` 共 3 个提交，合计改动 7 个文件，+503 / −42 行。

**按版本汇总**

| 版本（tag 日期） | cube-bench 的变化 |
|---|---|
| v0.5.1（2026-07-11） | 基线 |
| v0.6.0（2026-07-24） | #1027：Makefile 新增 `fmt` 目标，无功能变化 |
| v0.7.0（2026-08-28） | #1306：预热移出计时窗口；#1318：新增 `--network-policy`，Makefile 按源码变化重新编译 |
| v0.7.1（2026-09-11） | 无变化（目录树与 v0.7.0 相同） |

**逐个提交**

1. **`76a3c7e0` fix(fmt): add formatting coverage …（#1027，2026-07-19，进入 v0.6.0）**
   - 只改了 `Makefile`：新增 `fmt` 目标（`go fmt ./...`），并接入根目录的 `make fmt` 和 CI 格式检查。
   - 对运行行为和计时没有影响。

2. **`2c326c7d` fix(cube-bench): fix warmup display error（#1306，2026-08-10，进入 v0.7.0）**
   - **修改前（v0.5.1 / v0.6.0）：** 预热在 `RunBenchmark` goroutine 内部执行，而这个 goroutine 是在 `startTime` 之后才启动的。所以：
     - 预热的串行耗时会被算进 `total_time_s` 和 `throughput_qps`；
     - 预热的 `fmt.Printf` 和 TUI 同时输出，导致界面错乱（PR 修的就是这个显示问题）。
   - **修改后（v0.7.0 起）：**
     - 新增 `RunWarmup`，在 `main` 里、`startTime` 之前同步执行，输出写在 TUI 启动之前；
     - `RunWarmup` 返回预热用过的 client，`RunBenchmark` 复用它；`-w 0` 时返回 `nil`，由 `RunBenchmark` 新建；
     - client 的创建抽成 `newHTTPClient`，参数不变（连接上限 c+20、超时 120s）；
     - 新增单测 `TestRunWarmupCompletesBeforeBenchmark`。
   - **对计时的影响：** 只在 `-w > 0` 时有区别。v0.5.1 / v0.6.0 用 `-w` 跑出的 Total Time 和吞吐包含预热时间，不能直接和 v0.7.0 之后的结果对比。`-w 0`（默认）时两边计时完全一致。

3. **`725b7660` perf/fix(network): cut policy apply latency …（#1318，2026-08-19，进入 v0.7.0）**
   - 这是一个以 Cubelet / CubeVS 网络优化为主的 PR，cube-bench 部分是配套改动：
     - 新增 `--network-policy` / `-np`，取值 `none`（默认）或 `rules`；
     - `rules` 会在 create 请求里带上 `allow_internet_access=false` 和一组内置的网络规则（新文件 `network_policy.go`，按 README 的说明是约 24 条 `allowOut` 加 6 条 L7 规则，其中 2 条带 inject）。请求体仍然只在 `parseConfig` 里构造一次；
     - 配置面板新增「Network Policy」一行，JSON 报告的 `config` 新增 `network_policy`、`network_allow_out`、`network_rules`、`network_inject_rules`；
     - `Makefile`：`bin/cube-bench` 改为依赖 `*.go`、`go.mod`、`go.sum`。在此之前，只要 `bin/cube-bench` 已经存在，`make` 就不会重新编译；
     - README 补充了网络策略的说明和 A/B 对比用法，`main_test.go` 补了 126 行测试。
   - **对计时的影响：** 没有。默认 `none` 时请求体与之前完全相同，计时代码也没有改动。

**这段时间没有变化的部分**

`ui.go`、`report.go`、`stats.go`、`theme.go`、`go.mod`、`go.sum` 在 v0.5.1 与 v0.7.1 之间完全相同。与计时相关的核心逻辑也都没变，包括：

- `benchOne` 的计时点（`t0` 到 `client.Do` 返回）；
- 信号量并发控制和结果 channel；
- `-no-tui` 的结果收集（`collectWithSimpleProgress`）和 TUI 的结果消费路径；
- `startTime` / `elapsed` 的位置（只是把预热挪到了 `startTime` 之前）。

**结论：** 用默认的 `-w 0` 时，第一部分的 TUI 计时偏差和第二部分的 `-no-tui` 时间轴，在 v0.5.1 到 v0.7.3 / master 的所有版本上都成立。

**两点使用提醒**

- 用 v0.7.0 之前的 cube-bench 加 `-w` 得到的历史数据，Total Time 和吞吐里含有预热时间，和现在的数据对比前要先确认。
- 从旧版本切到新版本后，如果 `bin/cube-bench` 是在 #1318 之前编译的，单跑 `make` 不会重新编译。为保险起见，先 `make clean` 再 `make`。

**配套脚本（不属于 cube-bench 本身）**

同一时期新增了官方压测脚本 `tests/perf/cubebench.sh`：`da5743ab`（#1298，2026-08-06）新增，`9a3ffac2`（#1554，2026-08-28）改为用 `cubeopscli` 获取节点数。两者都进入了 v0.7.0。

### 3.3 v0.7.1 之后相关的改动：`tests/perf/cubebench.sh`

v0.7.1 之后只有提交 `79ba8f0d`（fix(cubebench): make CPU topology reports more compatible，2026-09-16，进入 v0.7.2，master 上也有）改了这个包装脚本：

- 环境信息里的 CPU 拓扑改为用 `LC_ALL=C lscpu` 解析，按去掉首尾空白后的字段名匹配，兼容本地化和带缩进的输出。
- 每个拓扑字段都做校验，缺失或不合法时输出 `unknown`。
- 新增 `tests/perf/cubebench_test.sh`，并接入 unit-test CI。

这个提交只影响测试报告里的环境描述，与压测流程和计时方式无关。

### 3.4 与本报告结论相关的两点

1. **官方脚本不受 TUI 计时问题影响。** `run_cube_bench` 把 cube-bench 的 stdout 重定向到日志文件（`tests/perf/cubebench.sh:1178`）。stdout 不是终端时，cube-bench 会自动启用 no-tui（`main.go:129`）。所以第一部分的偏差只出现在终端里手动运行的场景。
2. **脚本里的一条注释已过时。** `tests/perf/cubebench.sh:839` 写的是「预热时间会被算进 `total_time_s` / `throughput_qps`」。这在脚本写成时是对的：脚本是 #1298（2026-08-06）合入的，基于的还是 3.2 中 #1306 之前的代码。但四天后（2026-08-10）#1306 就把预热移出了计时窗口，所以这条理由不再成立。注释里不加 `-w` 的另外两条理由仍然成立：create-only 模式下预热创建的 sandbox 不会被删除，会让 sandbox 计数超过请求数；本节本来就要测冷启动。

---

## 附：代码位置索引

| 内容 | 位置 |
|---|---|
| 启用 no-tui（含非 TTY 时自动启用） | `main.go:121-129` |
| 主流程、`startTime` / `elapsed` | `main.go:420-444` |
| no-tui 结果收集 | `main.go:361-384` |
| 并发控制与关闭 channel | `runner.go:152-178` |
| 单次迭代与计时 | `runner.go:25-90` |
| HTTP client 配置 | `runner.go:119-129` |
| 预热 | `runner.go:134-150` |
| TUI Update / View | `ui.go:70-231` |
| 汇总报告与吞吐计算 | `report.go:10-96`、`main.go:270-359` |
| Bubble Tea 命令派发 | `bubbletea@v1.3.10/tea.go:333-370` |
| Bubble Tea 每条消息渲染 | `bubbletea@v1.3.10/tea.go:493-502` |
| 渲染器持锁写终端 | `bubbletea@v1.3.10/standard_renderer.go:161-163, 283, 303-304` |
| 退出流程 | `bubbletea@v1.3.10/tea.go:810-835`、`tty.go:109-117` |
| 官方压测脚本调用 cube-bench（输出重定向） | `tests/perf/cubebench.sh:1172-1184` |
| 官方脚本不加预热的说明（部分过时） | `tests/perf/cubebench.sh:839-843` |
