# Benchmark results CSV schema

`benchmark_results.csv` stores one formal benchmark run per row. New experiment IDs are
appended; regenerating an existing experiment replaces rows with the same stable
`experiment_id`, so rerunning an aggregator does not create duplicates.

- `capacity_compression_pct` is the percentage removed from the 4096 MiB baseline.
  For example, 80 means approximately 20% of the baseline remains available.
- `bandwidth_compression_pct` is reserved for the later bandwidth-throttling phase.
- Docker CPU uses the Docker stats convention: 100% is one logical CPU, so a 2U
  container reaches 200% at full allocation.
- DDR bandwidth is NUMA-node-wide uncore bandwidth, not cgroup-attributed bandwidth.
  It is derived from all NUMA-3 HiSilicon DDRC `flux_rd` and `flux_wr` counters.
- Empty cells mean that the metric was not collected for that historical run.
- Failed capacity conditions remain in the CSV with `exit_status` describing the
  failure; they are not silently discarded.
- `PASS` means the configured task count completed with no task failures.
  `TASK_FAILURES` means bench-core exited normally but one or more workload tasks
  failed or the configured round count was not completed.
- `oom_kill_delta` comes from the memory cgroup's `memory.oom_control` counter.
  Docker can report `OOMKilled=false` when a Chromium child was killed but the
  container init process survived.
