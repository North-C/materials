# v0.7.1 与 master 的 cube-bench 一致性证据

核验范围是 `examples/cube-bench` 的全部跟踪文件，不表示整个 CubeSandbox 仓库相同。

| 版本 | commit | cube-bench tree |
| --- | --- | --- |
| v0.7.1 | `31d911e430fdf8a8879bd062b8e78066c1a8e89d` | `fa4895544c890a6204b5defbb1750e7217b7f980` |
| master | `5741deb433b7e2b9c9d2dcadb1c87214de74bd24` | `fa4895544c890a6204b5defbb1750e7217b7f980` |

官方远端 ref 已实时核验，见 [upstream-refs.txt](upstream-refs.txt)。两个目录包含相同的14个文件，逐文件字节及 SHA256 一致，包含 go.mod/go.sum。`git diff` 输出为0字节，见 [source.diff](source.diff)；完整哈希见 [comparison.json](comparison.json)。

复核命令：

```sh
git diff 31d911e430fdf8a8879bd062b8e78066c1a8e89d 5741deb433b7e2b9c9d2dcadb1c87214de74bd24 -- examples/cube-bench
git rev-parse 31d911e430fdf8a8879bd062b8e78066c1a8e89d:examples/cube-bench
git rev-parse 5741deb433b7e2b9c9d2dcadb1c87214de74bd24:examples/cube-bench
```

已有两份二进制 SHA256 不同，且构建参数有差异（master 使用 -trimpath，旧 v0.7.1 没有）。二进制差异不表示源码不同。本次合并为一个源码组，不重复运行 master。

本次补充验证：在 构建机 将未修改 v0.7.1 使用与 master 相同参数重新构建，两份二进制逐字节一致，SHA256 均为 `ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511`。本次压测采用这份统一构建的 v0.7.1，详见 [构建清单](../v0.7.1-build/build-manifest.json)。
