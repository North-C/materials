# Long Terminal-Bench Workloads

This toolkit includes four long-running Terminal-Bench workload groups:

| Task | Load Type | Recommended Mode | Image |
|---|---|---|---|
| `jsonl-aggregator` | JSONL scan/aggregation | `replay_trajectory` with `--workload-repeat` | `docker.io/library/golang:1.25.0` or long image |
| `large-scale-text-editing` | Vim over 1M-row CSV | `replay_trajectory`, `fixed_output` | `localhost/tbench-long:20260509` |
| `deterministic-tarball` | file tree normalization + tar + zstd | `replay_trajectory`, `fixed_output` | `localhost/tbench-long:20260509` |
| `sqlite-with-gcov` | SQLite source build with gcov | `replay_trajectory` | `localhost/tbench-long:20260509` |

Preferred path: build/import the long image on the ARM host:

```bash
cd /root/agent-cpu-sandbox-toolkit
docker build -t localhost/tbench-long:20260509 -f images/tbench-long/Dockerfile .
docker save localhost/tbench-long:20260509 | ctr -n default images import -
```

If Docker build is unavailable on the host, prepare a writable rootfs and pass it with `--rootfs`:

```bash
mkdir -p /root/tbench-rootfs-mount /root/tbench-long-rootfs
ctr -n default images mount docker.io/library/golang:1.25.0 /root/tbench-rootfs-mount
cp -a /root/tbench-rootfs-mount/. /root/tbench-long-rootfs/
ctr -n default images unmount /root/tbench-rootfs-mount
ctr -n default run --rm --rootfs --net-host /root/tbench-long-rootfs tbench-rootfs-apt \
  /bin/bash -lc 'apt-get update && apt-get install -y --no-install-recommends bc file fossil jimsh sqlite3 tclsh unzip vim zstd rustc && rm -rf /var/lib/apt/lists/*'
```

Example runs:

```bash
python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id jsonl-aggregator \
  --runtime runc \
  --mode replay_trajectory \
  --workload-repeat 5

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id large-scale-text-editing \
  --runtime runc \
  --mode fixed_output \
  --rootfs /root/tbench-long-rootfs

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id deterministic-tarball \
  --runtime runc \
  --mode fixed_output \
  --rootfs /root/tbench-long-rootfs

python3 tools/run_terminal_bench_task.py \
  --task-root terminal-bench-tasks \
  --task-id sqlite-with-gcov \
  --runtime runc \
  --mode replay_trajectory \
  --rootfs /root/tbench-long-rootfs
```

Use `--force-prepare` after changing task files, image contents, or scale labels.

## Validated On ARM Host

Host: `root@192.168.25.61`

Rootfs: `/root/tbench-long-rootfs`

Docker build is currently blocked by the host Docker/containerd mismatch:

```text
type with url containerd.linux.runc.CreateOptions: not found
```

The validated path is therefore `ctr --rootfs` with the prepared rootfs. Kata accepts the same rootfs path.

| Task | Runtime | Mode | Repeat | Wall Time | Status |
|---|---|---|---:|---:|---|
| `jsonl-aggregator` | runc | replay | 3 | 10.014705s | pass |
| `large-scale-text-editing` | runc | replay | 1 | 120.127073s | pass |
| `large-scale-text-editing` | runc | fixed | 1 | 120.324130s | pass |
| `deterministic-tarball` | runc | fixed | 5 | 14.338949s | pass |
| `deterministic-tarball` | kata | fixed | 2 | 23.052157s | pass |
| `sqlite-with-gcov` | runc | replay | 1 | 18.091837s | pass |

Notes:

- `jsonl-aggregator` is stretched by repeating the replayed solution scan over the same deterministic 1M-record input.
- `large-scale-text-editing` is naturally long because the verifier runs Vim over a 1M-row CSV.
- `deterministic-tarball` is stretched by repeating the fixed-output verifier; the verifier repeatedly executes `/app/build.sh`, so this remains real tar/zstd work.
- `sqlite-with-gcov` should be treated as replay-only for long-load purposes; fixed output mostly verifies compiled artifacts.
