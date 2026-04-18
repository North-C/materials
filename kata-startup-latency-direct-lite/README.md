# Kata Startup Latency Direct Lite

This directory is the small, log-first toolset for measuring direct
`containerd + kata + cloud-hypervisor + application container` startup latency
without Kubernetes.

It uses:
- `crictl runp`
- `crictl create`
- `crictl start`
- `containerd` logs
- `crictl inspectp`
- `crictl inspect`

It does not require:
- Kubernetes
- Jaeger
- Prometheus
- Grafana
- custom Kata instrumentation

## Requirements

The target host should provide:
- `crictl`
- `python3`
- `sudo`
- `journalctl`
- `containerd`
- a usable Kata runtime handler in CRI

## Files

- `run-direct-cri-lite.sh`
  one-command direct CRI runner
- `collect-logs-lite.sh`
  captures `containerd` logs for the run window
- `parse_direct_kata_latency.py`
  parses raw artifacts and logs into `result.json` and `result.csv`
- `manifests/crictl-sandbox.json`
  sandbox template
- `manifests/crictl-container.json`
  container template

## Output

Each run is written under:

`results-direct-lite/<date>/<run_id>/`

Subdirectories:
- `raw/`
- `logs/`
- `summary/`
- `workloads/`

Main outputs:
- `summary/result.json`
- `summary/result.csv`

## Usage

Run one sample:

```bash
bash tools/testing/kata-startup-latency-direct-lite/run-direct-cri-lite.sh
```

Override the key environment variables when needed:

```bash
DIRECT_LITE_RUNTIME_HANDLER=kata \
DIRECT_LITE_NAMESPACE=default \
DIRECT_LITE_IMAGE=sealos.hub:5000/pause:3.9 \
DIRECT_LITE_HYPERVISOR=cloud-hypervisor \
bash tools/testing/kata-startup-latency-direct-lite/run-direct-cri-lite.sh
```

Keep sandbox and container after measurement:

```bash
DIRECT_LITE_CLEANUP=false \
bash tools/testing/kata-startup-latency-direct-lite/run-direct-cri-lite.sh
```

Increase the post-start log flush wait when the host is slow:

```bash
DIRECT_LITE_LOG_FLUSH_WAIT_SECS=4 \
bash tools/testing/kata-startup-latency-direct-lite/run-direct-cri-lite.sh
```

Use a custom container template when measuring a real application image with its own command:

```bash
DIRECT_LITE_IMAGE=my-registry.example.com/my-app:latest \
DIRECT_LITE_CONTAINER_TEMPLATE=/path/to/my-crictl-container.json \
bash tools/testing/kata-startup-latency-direct-lite/run-direct-cri-lite.sh
```

Re-parse an existing run:

```bash
python3 tools/testing/kata-startup-latency-direct-lite/parse_direct_kata_latency.py \
  --run-dir results-direct-lite/<date>/<run_id>
```

## Extracted Time Points

This direct-lite version focuses on the smallest stable direct runtime timeline:

- `t_request_sent`
- `t_run_pod_sandbox_request`
- `t_cloud_hypervisor_spawn`
- `t_vm_started`
- `t_agent_started`
- `t_run_pod_sandbox_return`
- `t_create_container_request`
- `t_create_container_return`
- `t_start_container_request`
- `t_container_started`
- `t_running`

## Derived Metrics

- `request_to_running_seconds`
- `sandbox_create_seconds`
- `vm_boot_seconds`
- `vm_to_agent_seconds`
- `create_container_seconds`
- `start_container_seconds`
- `runtime_to_running_seconds`

## Notes

The current definition of "application startup" in this small version is:
- the container has been started by Kata/containerd
- `crictl inspect` reports a `startedAt`

It does not attempt to infer application-level readiness inside the guest.
If you need to launch a real application instead of `/pause`, provide a custom
container template through `DIRECT_LITE_CONTAINER_TEMPLATE`.

## Limits

This version does not provide:
- Kubernetes path measurements
- guest agent sub-step timing
- runtime-rs `startup_stage` metrics
- batch sampling
- dashboards or traces
