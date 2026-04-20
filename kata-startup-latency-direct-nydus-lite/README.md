# Kata Direct Nydus Lite

`kata-startup-latency-direct-nydus-lite` is a log-first helper for measuring the
`containerd + kata + cloud-hypervisor + nydus` direct CRI startup path without
Kubernetes.

It runs a direct `crictl runp/create/start` sample, temporarily switches the
CRI snapshotter to `nydus`, converts both the application image and the CRI
pause image into Nydus images, then parses `containerd` and
`nydus-snapshotter` logs into `summary/result.json` and `summary/result.csv`.

Image publication strategy:

- first try local `ctr images import --no-unpack`
- if CRI cannot resolve that local image, automatically fallback to
  `nerdctl tag/push` into the host-local registry and `crictl pull`

Batch support:

- `run-sample-series.sh` repeats the single-run measurement with warmup/sample counts
- `aggregate_batch_results.py` writes batch-level JSON and CSV summaries
- [MIGRATION.md](/home/test/lyq/Micro-VM/kata-containers/.worktrees/kata-startup-latency-phase01/tools/testing/kata-startup-latency-direct-nydus-lite/MIGRATION.md) records the standalone migration checklist

## Requirements

- `crictl`
- `ctr`
- `journalctl`
- `nydusify`
- `python3`
- `sudo`
- `containerd`, `kata`, `cloud-hypervisor`, `nydus-snapshotter`

## What It Validates

- the effective snapshotter is `nydus`
- the effective Kata config path is the generated `configuration-clh-nydus.toml`
- the requested Nydus image actually reaches the container runtime config
- Nydus evidence exists in the sample window
  - prefer `nydus-snapshotter` service logs
  - fallback to `containerd` log lines such as `starting nydusd` / `nydusd started`

## Usage

```bash
bash tools/testing/kata-startup-latency-direct-nydus-lite/run-direct-cri-nydus-lite.sh
```

Useful environment variables:

- `DIRECT_NYDUS_SOURCE_IMAGE`
- `DIRECT_NYDUS_RUNTIME_HANDLER`
- `DIRECT_NYDUS_NAMESPACE`
- `DIRECT_NYDUS_CONTAINER_TEMPLATE`
- `DIRECT_NYDUS_SANDBOX_TEMPLATE`
- `DIRECT_NYDUS_CLEANUP`
- `DIRECT_NYDUS_REGISTRY`
- `DIRECT_NYDUS_REGISTRY_USER`
- `DIRECT_NYDUS_REGISTRY_PASSWORD`

Run repeated sampling:

```bash
WARMUP_COUNT=1 \
SAMPLE_COUNT=5 \
bash tools/testing/kata-startup-latency-direct-nydus-lite/run-sample-series.sh
```

## Output

Each run writes to:

```text
results-direct-nydus-lite/<date>/<run_id>/
```

Main artifacts:

- `raw/request.json`
- `raw/inspectp.json`
- `raw/inspect.json`
- `raw/crictl-info.before.json`
- `raw/crictl-info.after.json`
- `raw/*nydus-convert.json`
- `logs/containerd.log`
- `logs/nydus-snapshotter.log`
- `summary/result.json`
- `summary/result.csv`

Batch mode writes to:

```text
results-direct-nydus-lite/<date>/<batch_id>/
```

Batch artifacts:

- `summary/batch-meta.json`
- `summary/batch-results.json`
- `summary/batch-sample-results.csv`
- `summary/batch-summary.csv`

Latest verified live sample on this host:

- [run-20260420T092816Z](/home/test/lyq/Micro-VM/kata-containers/.worktrees/kata-startup-latency-phase01/results-direct-nydus-lite/2026-04-20/run-20260420T092816Z)
- `request_to_running_seconds = 1.007403`
- `sandbox_create_seconds = 0.772431`
- `vm_boot_seconds = 0.05811`
- `vm_to_agent_seconds = 0.482173`
- `create_container_seconds = 0.0981`
- `start_container_seconds = 0.046912`

Latest verified live batch sample on this host:

- [batch-20260420T173500Z](/home/test/lyq/Micro-VM/kata-containers/.worktrees/kata-startup-latency-phase01/results-direct-nydus-lite/2026-04-20/batch-20260420T173500Z)
- `sample_count = 1`
- `validation_success_rate = 1.0`
- `request_to_running_seconds_mean = 1.032338`

## Notes

- The runner restores `/etc/containerd/config.toml` on exit.
- The runner also restores `/etc/nydus-snapshotter/config.toml` on exit.
- The converted Nydus images stay in the local containerd image store. When
  CRI cannot see them directly, the runner republishes them to the configured
  local registry for CRI consumption.
- On this host the live sample succeeded through that registry fallback path,
  using `nerdctl tag/push` and `crictl pull`.
- The default direct sample uses `/pause`. Override the container template if
  you want to test another application image/command.

## Troubleshooting

- `no such image "...nydus-lite" present`
  The converted image was imported into containerd, but CRI could not resolve
  it as a managed image. The runner should then fallback to the registry path.
- `failed to extract layer ... application/vnd.oci.image.layer.nydus.blob.v1`
  The environment is still consuming the image as a regular OCI image instead
  of through the Nydus snapshotter path. Recheck the temporary containerd and
  Kata config patches in the run directory.
- `logs/nydus-snapshotter.log` contains `-- No entries --`
  This can still be a valid run on this host. Check `logs/containerd.log` for
  `starting nydusd`, `nydusd started`, and the runtime block showing
  `Snapshotter:nydus`.
