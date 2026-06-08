# Agent CPU Sandbox Toolkit

This toolkit builds a no-LLM, Terminal-bench-style workload for measuring CPU and sandbox overhead on ARM servers.

The first workload is `terminal_cpu_io`: a deterministic replay trajectory that creates text artifacts, hashes files, sorts checksums, scans content, archives results, and emits a rule-based score. It is intended to model the local execution side of CLI coding/data-agent tasks without model API variance.

## Tools

1. `tools/run_workload.py`
   Runs the workload in Docker, containerd/runc, or Kata via containerd.

2. `scripts/terminal_cpu_io.sh`
   The fixed replay trajectory executed inside the sandbox.

3. `tools/summarize.py`
   Aggregates `run.json` and `time.txt` files into a CSV summary.

4. `trajectories/terminal_cpu_io.jsonl`
   Human-readable replay trajectory metadata.

5. `tools/run_terminal_bench_task.py`
   Runs selected real Terminal-Bench task packages with no model API by executing `solution.sh` and the task's own `tests/test_outputs.py`.

6. `LONG_TASKS.md`
   Documents the four longer Terminal-Bench workload groups and their runtime/image requirements.

## Quick Start

containerd/runc baseline:

```bash
python3 tools/run_workload.py --runtime runc --runs 1 --files 8 --lines 120
```

Fixed-output evaluator mode:

```bash
python3 tools/run_workload.py --runtime runc --mode fixed_output --runs 1 --files 8 --lines 120
```

Kata via containerd:

```bash
python3 tools/run_workload.py --runtime kata --runs 1 --files 8 --lines 120
```

Kata with cloud-hypervisor config:

```bash
python3 tools/run_workload.py --runtime kata --kata-config /opt/kata/share/defaults/kata-containers/configuration-clh.toml --runs 1 --files 8 --lines 120
```

Summarize:

```bash
python3 tools/summarize.py runs
```

## Recommended Test Matrix

Start with small smoke tests:

```bash
python3 tools/run_workload.py --runtime runc --runs 1 --files 8 --lines 120
python3 tools/run_workload.py --runtime kata --runs 1 --files 8 --lines 120
```

Then scale:

```bash
python3 tools/run_workload.py --runtime runc --runs 3 --files 32 --lines 400 --cpus 2 --memory 4g
python3 tools/run_workload.py --runtime kata --runs 3 --files 32 --lines 400 --cpus 2 --memory 4g
```

## Output

Each run writes:

```text
runs/<run_id>/
  run.json
  stdout.log
  stderr.log
  time.txt
  work/
    score.json
    processed/
    artifacts/
```

The Python runner captures host-side elapsed time, child user/system time, max RSS, context switches, and filesystem IO for the sandbox invocation.

## Real Terminal-Bench Tasks, No Model API

After copying selected official task directories under `terminal-bench-tasks/`, run:

```bash
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

Summarize:

```bash
python3 tools/summarize_terminal_bench.py runs-terminal-bench
```

## Long Terminal-Bench Workloads

The toolkit also includes longer no-LLM task packages:

- `jsonl-aggregator`
- `large-scale-text-editing`
- `deterministic-tarball`
- `sqlite-with-gcov`

Build the long-task image and run examples from `LONG_TASKS.md`. The runner supports:

```bash
python3 tools/run_terminal_bench_task.py --list-long-tasks
```

Use `--workload-repeat N` to stretch replay-heavy tasks without changing task outputs, and `--force-prepare` after changing task packages or images.
