# Evidence manifest: CubeSandbox lifecycle community-aligned benchmark

| 字段 | 值 |
|---|---|
| 状态 | `verified` |
| last_verified | 2026-08-24 |
| 报告 | `CUBESANDBOX_RUNTIME_SNAPSHOT_PAUSE_CLONE_COMMUNITY_ALIGNED_20260824.md` |
| CSV | `CUBESANDBOX_RUNTIME_SNAPSHOT_PAUSE_CLONE_COMMUNITY_ALIGNED_20260824.csv` |
| source_revision | CubeSandbox `72af66c349301ec8f750f21796a08e65dbb85e73` |
| deployed host build | `6646d3837d28edb8a3e65f9a93da06994f7e83f4` |
| CubeAPI identity | `92b81197815823b23ec91906fbeaa7321d69da2c6136d9c757a5446684244bc1` |

## Source evidence sets

| Run label | 本机路径 | 内容 | SHA256SUMS entries |
|---|---|---|---:|
| `spc90-community-20260822T091058Z-31b38a2d` | `<local-evidence-root>/spc90-community-20260822T091058Z-31b38a2d` | Snapshot/Pause/Clone 核心矩阵 | 150 |
| `spc90-community-92b-full-20260824T125416Z-18811bfd` | `<local-evidence-root>/spc90-community-92b-full-20260824T125416Z-18811bfd` | Snapshot/dirty/create/Rollback、首次 c10 失败与 cleanup | 274 |
| `spc90-rollback-c10-retest-20260824T134119Z-c68c3d7b` | `<local-evidence-root>/spc90-rollback-c10-retest-20260824T134119Z-c68c3d7b` | Rollback c10 独立复测 | 17 |

这些本机绝对路径用于维护者追溯，不表示公开仓库读者可访问。Materials 只提交报告、CSV 和 manifest；原始日志、内部 IP 上的运行状态和大体积 evidence 不上传。

## Script provenance

| 脚本 | SHA-256 |
|---|---|
| `bench_snapshot_concurrency.py` | `b896937eabe210cfddfb63501f471b4e48c873b7149d20da886a1f502f152253` |
| `bench_snapshot_dirty.py` | `301b5276fe351956f8ed5ee1416d864ccbd7a45fa4e2a48f63c2908d8ffea72a` |
| `bench_create_concurrency.py` | `332d5cd147dd654ac141d7598028c93756997b1c72ef2deaee80229c28f5d513` |
| `bench_rollback_concurrency.py` | `0f1d7720bc12192355943f30917e893f73d4e015a0007dcb2288f8490f765229` |
| `bench_clone_concurrency.py` | `eda015c383c95bae92fe7608aa2f4824c4583cdc571062cf3f8577544ab9e67f` |
| `bench_pause_resume_concurrency.py` | `2cba48bf409d26812cbea88a29d9987931a838f5bf6804f5da25652688134593` |

社区脚本原件未修改。外层 harness 只负责身份/资源/冷却门禁、stdout/stderr、host samples、组件日志窗口、ID ledger 和精确清理，不进入社区 timer。

## Raw-to-derived lineage

```text
community script stdout
  -> report table aggregate
  -> CSV current metrics
  -> current-vs-community descriptive delta

component log window + before/after JSON
  -> exact Sandbox/Snapshot IDs
  -> cleanup/convergence/cooldown evidence
```

社区脚本没有输出逐轮 wall 数组；因此 CSV 保存的是 stdout aggregate，而不是伪造的逐轮 raw。失败 attempt 保存在对应 run 的 stderr、failure-state 和 failure-cleanup 中。

## Integrity and redaction

- 三个 evidence set 的 `SHA256SUMS` 已通过 `sha256sum -c`。
- 报告 SHA-256：`b4e5d0a6648610542c206d54e56494be44e8b0447b84620cadf4e2da5c28be81`。
- CSV SHA-256：`884f9d217929d1a1abfc30e7edcb87c8d4e3640fa7a41c5222eea33cb5ee7172`。
- 报告与 CSV 不包含 API key、token、Cookie、Authorization header、私钥或 artifact download token。
- Materials 未提交大文件，不需要 Git LFS。
- 主机绝对时间存在 NTP 未同步 caveat；请求 wall 使用同机 monotonic，绝对时间只用于日志关联。

## Reproducibility limits

- 社区历史表缺逐轮 raw 和完整 runtime/SDK 身份。
- 本报告合并同一 CubeAPI hash 下的多个日期/boot 批次；不能做 pooled A/B。
- Page Cache、Snapshot age、首次 restore 和后台 Guest 活动未被完全控制。
- Rollback c10 首次失败、独立复测成功；触发条件尚未确认。
