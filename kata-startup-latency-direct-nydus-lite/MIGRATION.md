# Migration Guide

This note explains how to move `kata-startup-latency-direct-nydus-lite/` to another
`containerd + kata + cloud-hypervisor + nydus` environment with minimal changes.

## Goal

This tool answers one narrow question:

`How long does direct CRI startup take for a Nydus-backed Kata container?`

It uses:
- `crictl runp`
- `crictl create`
- `crictl start`
- `containerd` logs
- `nydus-snapshotter` logs when available
- `crictl inspectp`
- `crictl inspect`

It does not depend on:
- Kubernetes
- Jaeger
- Prometheus
- Grafana
- custom Kata instrumentation

## What To Copy

Copy the whole directory:

`tools/testing/kata-startup-latency-direct-nydus-lite/`

Required files:
- `run-direct-cri-nydus-lite.sh`
- `run-sample-series.sh`
- `aggregate_batch_results.py`
- `collect-logs-lite.sh`
- `parse_direct_nydus_kata_latency.py`
- `manifests/crictl-sandbox.json`
- `manifests/crictl-container.json`
- `README.md`
- `MIGRATION.md`

## Minimum Environment Checklist

Before first use, confirm:

1. `sudo crictl info` works.
2. `sudo journalctl -u containerd -n 5` works.
3. `sudo systemctl status nydus-snapshotter` shows `active`.
4. `/opt/kata/share/defaults/kata-containers/configuration-clh.toml` exists.
5. `/usr/local/bin/nydusd`, `nydusify`, `ctr`, `crictl`, and `nerdctl` exist.
6. The configured registry is reachable from the host.
7. The source image can be pulled or is already cached.

If any of these fail, fix them before trying the tool.

## What The Runner Changes Temporarily

Per sample run, the runner temporarily changes:

- `/etc/containerd/config.toml`
  - CRI `snapshotter = "nydus"`
  - CRI `sandbox_image`
  - Kata runtime `snapshotter = "nydus"`
  - Kata runtime `ConfigPath`
- `/etc/nydus-snapshotter/config.toml`
  - `enable_nydus_overlayfs = true`

Both files are backed up into the run directory and restored on exit.

## Minimum Variables To Adapt

The portable entrypoint is:

```bash
bash tools/testing/kata-startup-latency-direct-nydus-lite/run-direct-cri-nydus-lite.sh
```

The most common overrides are:

```bash
DIRECT_NYDUS_SOURCE_IMAGE=<your-source-image>
DIRECT_NYDUS_RUNTIME_HANDLER=<your-kata-runtime-handler>
DIRECT_NYDUS_BASE_KATA_CONFIG=<your-clh-kata-config>
DIRECT_NYDUS_REGISTRY=<your-registry>
DIRECT_NYDUS_REGISTRY_USER=<user>
DIRECT_NYDUS_REGISTRY_PASSWORD=<password>
```

Typical example:

```bash
DIRECT_NYDUS_SOURCE_IMAGE=registry.example.com/my-app:latest \
DIRECT_NYDUS_RUNTIME_HANDLER=kata \
DIRECT_NYDUS_BASE_KATA_CONFIG=/opt/kata/share/defaults/kata-containers/configuration-clh.toml \
DIRECT_NYDUS_REGISTRY=registry.example.com:5000 \
DIRECT_NYDUS_REGISTRY_USER=admin \
DIRECT_NYDUS_REGISTRY_PASSWORD=passw0rd \
bash tools/testing/kata-startup-latency-direct-nydus-lite/run-direct-cri-nydus-lite.sh
```

## Registry Fallback Behavior

This tool first tries:

- `ctr images export`
- `nydusify convert`
- `ctr images import --no-unpack`

If CRI cannot resolve the converted local image, it automatically falls back to:

- `nerdctl tag`
- `nerdctl push`
- `crictl pull`

On the current reference host, the successful path was the registry fallback path.

## First Migration Pass

Recommended first pass:

1. Keep `DIRECT_NYDUS_CLEANUP=false` so the sandbox and container remain after measurement.
2. Run one sample.
3. Check the generated files under `results-direct-nydus-lite/<date>/<run_id>/`.
4. Inspect:
   - `raw/request.json`
   - `raw/inspectp.json`
   - `raw/inspect.json`
   - `logs/containerd.log`
   - `logs/nydus-snapshotter.log`
   - `summary/result.json`
5. Only after the first sample looks correct, switch `DIRECT_NYDUS_CLEANUP` back to `true`.

Suggested command:

```bash
DIRECT_NYDUS_CLEANUP=false \
bash tools/testing/kata-startup-latency-direct-nydus-lite/run-direct-cri-nydus-lite.sh
```

## Expected Successful Output

A successful run should produce:

- `summary/result.json`
- `summary/result.csv`

The JSON should usually contain at least:

- `snapshotter = "nydus"`
- `kata_config_path = ...configuration-clh-nydus.toml`
- `t_run_pod_sandbox_request`
- `t_vm_started`
- `t_agent_started`
- `t_container_started`
- `t_running`
- `request_to_running_seconds`

Reference successful sample:

- [run-20260420T092816Z](/home/test/lyq/Micro-VM/kata-containers/.worktrees/kata-startup-latency-phase01/results-direct-nydus-lite/2026-04-20/run-20260420T092816Z)

## Batch Sampling

Use the batch runner for repeated sampling:

```bash
WARMUP_COUNT=1 \
SAMPLE_COUNT=5 \
bash tools/testing/kata-startup-latency-direct-nydus-lite/run-sample-series.sh
```

Batch outputs are written under:

`results-direct-nydus-lite/<date>/<batch_id>/`

Main outputs:
- `summary/batch-results.json`
- `summary/batch-sample-results.csv`
- `summary/batch-summary.csv`
- `summary/batch-meta.json`

## What The Parser Assumes

The current parser matches stable log phrases already seen in this environment.

From `containerd` / Kata:
- `RunPodSandbox for &PodSandboxMetadata`
- `path=/opt/kata/bin/cloud-hypervisor`
- `VM started`
- `Agent started in the sandbox`
- `CreateContainer within sandbox`
- `StartContainer for`
- `Container is started`

Nydus evidence is accepted from either:
- `nydus-snapshotter` service logs
- `containerd.log` lines such as `starting nydusd` / `nydusd started`

## Common Porting Gaps

### 1. Different systemd unit names

Current scripts assume:
- `containerd`
- `nydus-snapshotter`

If your environment uses different units, update `collect-logs-lite.sh`.

### 2. Different Kata config paths

If the environment does not use:

`/opt/kata/share/defaults/kata-containers/configuration-clh.toml`

set:

`DIRECT_NYDUS_BASE_KATA_CONFIG=<path>`

### 3. Missing registry fallback tools

If `nerdctl` is unavailable, the current automatic fallback cannot work.
In that case either:

- install `nerdctl`, or
- pre-publish the converted Nydus image to a registry that `crictl pull` can access.

### 4. Empty `nydus-snapshotter.log`

This can still be a valid run.
Check `logs/containerd.log` for:

- `Snapshotter:nydus`
- `starting nydusd`
- `nydusd started`

### 5. Source image mismatch

If your target application is not `/pause`, do not edit the parser first.
Set:

- `DIRECT_NYDUS_SOURCE_IMAGE=<your-image>`
- `DIRECT_NYDUS_CONTAINER_TEMPLATE=<your-crictl-container-template>`

## How To Validate A New Environment

Use this order:

1. Run one sample.
2. Confirm the run exits successfully.
3. Confirm `summary/result.json` exists.
4. Confirm `snapshotter = "nydus"`.
5. Confirm all validation fields are `true`.
6. Confirm `request_to_running_seconds` is non-empty.
7. Only then move to batch sampling.

## Recommended Local Adjustments

Only change these files when porting:

- `run-direct-cri-nydus-lite.sh`
  for environment variables, registry behavior, or config patching
- `collect-logs-lite.sh`
  for systemd unit names
- `parse_direct_nydus_kata_latency.py`
  for log phrase matching
- `run-sample-series.sh`
  if batch directory or retry behavior needs adjustment

Avoid expanding scope during migration.
Keep the first migrated version limited to one successful direct CRI measurement.
