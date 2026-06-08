# Agent CPU Sandbox Toolkit v0

## Version

Version: `v0`
Date: 2026-05-08
Host used for validation: `root@192.168.25.61`
Architecture: `aarch64`
Primary sandbox runtimes: `ctr + runc`, `ctr + kata`

## Scope

`v0` freezes the initial working state for no-LLM Agent benchmark execution in AI sandboxes.

It includes:

- synthetic Terminal-bench-style workload tooling,
- real Terminal-Bench task runner,
- offline mini test runner,
- initial real Terminal-Bench task subset,
- runc/Kata smoke and validation results,
- task filtering rationale.

It intentionally does not focus on detailed CPU metric collection yet. The goal is to build reusable, real benchmark workloads that can later support deeper CPU analysis.

## Archive

Snapshot archive:

```text
versions/v0/agent_cpu_sandbox_toolkit_v0.tar.gz
```

The archive excludes generated run outputs and fixtures.

## Current Remote Layout

On the ARM server:

```text
/root/agent-cpu-sandbox-toolkit/
  tools/
    run_workload.py
    run_terminal_bench_task.py
    mini_pytest.py
    summarize.py
    summarize_terminal_bench.py
  scripts/
    terminal_cpu_io.sh
  trajectories/
    terminal_cpu_io.jsonl
  terminal-bench-tasks/
    log-summary/
    constraints-scheduling/
    jsonl-aggregator/
    analyze-access-logs/
    bank-trans-filter/
    assign-seats/
    schedule-vacation/
    recover-accuracy-log/
```

## v0 Ready Tasks

| Task | Validation Status | Runtime / Mode |
|---|---|---|
| log-summary | pass | runc/kata, replay/fixed |
| constraints-scheduling | pass | runc/kata, replay/fixed |
| jsonl-aggregator | pass | runc/kata, replay/fixed |
| analyze-access-logs | pass | runc, replay |
| bank-trans-filter | pass | runc, replay |
| assign-seats | pass | runc, replay |
| schedule-vacation | pass | runc, replay |
| recover-accuracy-log | pass | runc, replay |

## Core Commands

Replay:

```bash
cd /root/agent-cpu-sandbox-toolkit

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id log-summary \
  --runtime runc \
  --mode replay_trajectory
```

Fixed output:

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id log-summary \
  --runtime kata \
  --mode fixed_output
```

Summary:

```bash
python3 tools/summarize_terminal_bench.py runs-terminal-bench \
  | tee runs-terminal-bench/summary.csv
```

## Known Constraints

- Current runner bypasses official `run-tests.sh` online dependency installation and uses `mini_pytest.py`.
- Current selected tasks are constrained to Python stdlib / shell-compatible workloads.
- Docker regular `docker run` is not usable on the ARM host, so `ctr + runc` is used as the lightweight container baseline.
- Detailed CPU/cgroup/guest metrics are intentionally deferred to the next phase.
