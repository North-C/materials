---
status: in-progress
scope: read-only manifest for research dirty and untracked inputs in the main checkout
last_verified: 2026-08-29
source_revision: f036fd2 (main checkout HEAD at observation time)
canonical: false
evidence_manifest: partial
---

# Research Dirty Input Manifest

本 manifest 记录 2026-08-29 在只读主检出区 `/home/lyq/Projects/materials` 观察到的 research dirty/untracked 输入。它不是导入清单，不授权删除、清理、暂存、提交或覆盖这些路径。

## Git Boundary

主检出区 `research/` 范围只读观测：

- modified tracked files: 2
- untracked file-level entries: 58
- staged files: 0
- observed HEAD: `f036fd2`
- local `main` was behind known `origin/main` by 3 commits in prior inventory

Modified tracked files:

- `research/agent_cpu_sandbox_toolkit/terminal-bench-tasks/large-scale-text-editing/Dockerfile.e2b`
- `research/agent_cpu_sandbox_toolkit/terminal-bench-tasks/large-scale-text-editing/Dockerfile.e2b-perf`

## Untracked Inputs by Role

| Role | Paths | Decision |
|---|---|---|
| Local machine/app state | `research/.marscode/deviceInfo.json`, `research/tmp/aha/dconf/user` | Treat as local/private candidate; do not import without review |
| Trend research notes | `research/agent_ai_trend/research-notes/*.md` | Candidate supporting notes; review source/publicness before import |
| Toolkit ignore rule | `research/agent_cpu_sandbox_toolkit/.gitignore` | Review against root minimal ignore policy before import |
| Toolkit scripts/tools | `scripts/terminal_cpu_io.sh`, `tools/mini_pytest.py`, `tools/run_terminal_bench_task.py`, `tools/run_workload.py`, `tools/summarize.py`, `tools/summarize_terminal_bench.py` | Candidate toolkit source; needs license/runtime review and README alignment |
| Raw trajectory | `trajectories/terminal_cpu_io.jsonl` | Raw evidence; import only with manifest or external evidence decision |
| Toolkit image build input | `images/tbench-long/Dockerfile` | Build fixture candidate; needs scope and reproducibility metadata |
| Terminal-Bench task fixtures | untracked task files under `analyze-access-logs`, `deterministic-tarball`, `jsonl-aggregator`, `large-scale-text-editing`, `sqlite-with-gcov`, `train-bpe-tokenizer` | Candidate task source/fixture; preserve task self-contained boundaries |
| Vendor archive | `sqlite-with-gcov/vendor/sqlite-fossil-release.tar.gz` and `.sha256` | User decision: vendor tar not handled in this phase |
| Version archive | `versions/v0/agent_cpu_sandbox_toolkit_v0.tar.gz` | Do not import now; use version manifest and storage decision |

## Task Fixture Inventory

| Task | Observed untracked paths | Notes |
|---|---|---|
| `analyze-access-logs` | `Dockerfile`, `Dockerfile.self-contained`, `docker-compose.yaml`, `run-tests.sh`, `task.yaml` | Existing tracked baseline also contains E2B/self-contained support files |
| `deterministic-tarball` | Dockerfile, compose, setup, solution, task, tests | New task candidate; no import yet |
| `jsonl-aggregator` | Dockerfile, compose, run-tests, solution, task deps, task, tests | New task candidate; likely source plus fixture |
| `large-scale-text-editing` | Dockerfile variants, compose, run-tests, task, test generator | Has two modified tracked Dockerfiles; canonical unresolved |
| `sqlite-with-gcov` | Dockerfile, compose, run-tests, solution, task, tests, vendor tar/hash | Vendor tar explicitly out of scope |
| `train-bpe-tokenizer` | Dockerfile variants, compose, run-tests, task | Existing tracked baseline contains app/doc/self-contained/test files |

## Import Preconditions

Before any dirty input is copied or recreated in the Orca worktree:

1. Record exact `git status --porcelain=v1 --untracked-files=all -- research`.
2. For source/scripts/tasks, inspect content for license, credentials, absolute paths and runtime assumptions.
3. For raw/derived evidence, record hash, generator, input, runtime, commit and reproducibility status.
4. For large archives, follow [Large Object Manifest](../docs/meta/LARGE_OBJECT_MANIFEST.md) and avoid ordinary Git objects over 100 MiB.
5. For local/private state paths, default to exclusion unless the user explicitly identifies them as evidence.

## Open Decisions

- Which of the six toolkit tool/script files should become tracked source in the canonical toolkit?
- Are the two modified `large-scale-text-editing` Dockerfiles the latest canonical, local experiments, or obsolete edits?
- Should trend research notes be public docs, private notes, or excluded working material?
- Should `versions/v0` be represented only by manifest/hash, or by an external artifact plus LFS pointer for smaller required files?
