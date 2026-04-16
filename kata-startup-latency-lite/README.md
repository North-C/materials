# Kata Startup Latency Lite

This directory is the portable, log-first subset of the full Kata startup latency toolchain.

Use it when you only need one thing:
- create one Kubernetes Pod with a Kata `RuntimeClass`
- collect the minimal host logs
- compute end-to-end startup latency from object timestamps and logs

It does not require:
- Jaeger
- Prometheus
- Grafana
- `kata-monitor`
- runtime-rs custom instrumentation
- direct CRI test flows

Migration notes:
- `MIGRATION.md`
  cross-environment migration checklist and adaptation notes

## Requirements

The target host should provide:
- `kubectl`
- `python3`
- `sudo`
- `journalctl`
- `containerd`
- `kubelet`

Optional:
- `crictl`
  used to collect `kube-scheduler` logs when the scheduler runs as a static Pod

The cluster should already have:
- a working Kubernetes control plane
- a usable Kata `RuntimeClass`
- a cached or reachable test image

## Files

- `run-k8s-pod-lite.sh`
  one-command runner for a Kubernetes Kata Pod
- `collect-logs-lite.sh`
  captures `kubelet`, `containerd`, and optional `kube-scheduler` logs
- `parse_kata_pod_latency.py`
  parses Pod artifacts and logs into `result.json` and `result.csv`
- `manifests/kata-latency-pod.yaml`
  minimal Pod template
- `MIGRATION.md`
  explains what usually needs changing in a different Kubernetes + Kata environment

## Output

Each run is written under:

`results-lite/<date>/<run_id>/`

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
bash tools/testing/kata-startup-latency-lite/run-k8s-pod-lite.sh
```

Override the key environment variables when needed:

```bash
LITE_RUNTIME_CLASS=kata \
LITE_NAMESPACE=default \
LITE_IMAGE=sealos.hub:5000/pause:3.9 \
LITE_HYPERVISOR=cloud-hypervisor \
bash tools/testing/kata-startup-latency-lite/run-k8s-pod-lite.sh
```

Keep the Pod after measurement:

```bash
LITE_DELETE_POD=false \
bash tools/testing/kata-startup-latency-lite/run-k8s-pod-lite.sh
```

Re-parse an existing run:

```bash
python3 tools/testing/kata-startup-latency-lite/parse_kata_pod_latency.py \
  --run-dir results-lite/<date>/<run_id>
```

## Extracted Time Points

This lite version focuses on the smallest stable timeline that is broadly portable:

- `t_request_sent`
- `t_object_created`
- `t_scheduled`
- `t_kubelet_syncpod_enter`
- `t_run_pod_sandbox_request`
- `t_vm_started`
- `t_agent_started`
- `t_container_started`
- `t_running`

## Derived Metrics

- `request_to_running_seconds`
- `object_create_to_running_seconds`
- `schedule_latency_seconds`
- `kubelet_to_runtime_seconds`
- `vm_boot_seconds`
- `vm_to_agent_seconds`
- `runtime_to_running_seconds`

## Portability Notes

This subset intentionally avoids host-specific integrations from the full toolchain.

If the target environment differs:
- change `LITE_RUNTIME_CLASS`
- change `LITE_IMAGE`
- change `LITE_HYPERVISOR`
- update `K8S_APISERVER_NO_PROXY` if your API server endpoint differs

If `kube-scheduler` logs are not available, the parser still works.
In that case:
- `t_scheduled` comes from Kubernetes events
- scheduler log-derived timing is not required

## Limits

This lite version does not provide:
- batch sampling
- direct CRI measurements
- Grafana dashboards
- Jaeger traces
- runtime-rs `startup_stage` metrics
- guest agent internal sub-step timing

Use the full `tools/testing/kata-startup-latency/` toolset when those are needed.
