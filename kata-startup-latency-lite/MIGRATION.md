# Migration Guide

This note explains how to move `kata-startup-latency-lite/` to another Kubernetes + Kata environment with minimal changes.

## Goal

The lite tool is designed to answer one question:

`How long does it take from sending a Kubernetes Pod request to a Kata container reaching Running?`

It uses:
- Kubernetes object timestamps
- `kubelet` logs
- `containerd` logs
- optional `kube-scheduler` logs

It does not depend on:
- Jaeger
- Prometheus
- Grafana
- custom Kata instrumentation

## What To Copy

Copy the whole directory:

`tools/testing/kata-startup-latency-lite/`

Required files:
- `run-k8s-pod-lite.sh`
- `collect-logs-lite.sh`
- `parse_kata_pod_latency.py`
- `manifests/kata-latency-pod.yaml`
- `README.md`
- `MIGRATION.md`

## Minimum Environment Checklist

Before first use, confirm:

1. `kubectl get nodes` works from the machine where the tool runs.
2. `sudo journalctl -u kubelet -n 5` works.
3. `sudo journalctl -u containerd -n 5` works.
4. `kubectl get runtimeclass` shows the Kata runtime class you intend to use.
5. The test image can be pulled or is already cached.

If any of these fail, fix them before trying the tool.

## Minimum Variables To Adapt

The portable entrypoint is:

```bash
bash tools/testing/kata-startup-latency-lite/run-k8s-pod-lite.sh
```

The most common overrides are:

```bash
LITE_RUNTIME_CLASS=<your-runtimeclass>
LITE_NAMESPACE=<your-namespace>
LITE_IMAGE=<your-image>
LITE_HYPERVISOR=<cloud-hypervisor|qemu|...>
K8S_APISERVER_NO_PROXY=<api-server,ip,localhost,127.0.0.1>
```

Typical example:

```bash
LITE_RUNTIME_CLASS=kata \
LITE_NAMESPACE=default \
LITE_IMAGE=registry.k8s.io/pause:3.9 \
LITE_HYPERVISOR=cloud-hypervisor \
K8S_APISERVER_NO_PROXY=apiserver.cluster.local,10.96.0.1,127.0.0.1,localhost \
bash tools/testing/kata-startup-latency-lite/run-k8s-pod-lite.sh
```

## First Migration Pass

Recommended first pass:

1. Keep `LITE_DELETE_POD=false` so the Pod remains after measurement.
2. Run one sample.
3. Check the generated files under `results-lite/<date>/<run_id>/`.
4. Inspect:
   - `raw/pod.json`
   - `logs/kubelet.log`
   - `logs/containerd.log`
   - `summary/result.json`
5. Only after the first sample looks correct, switch `LITE_DELETE_POD` back to `true`.

Suggested command:

```bash
LITE_DELETE_POD=false \
LITE_RUNTIME_CLASS=kata \
LITE_IMAGE=registry.k8s.io/pause:3.9 \
bash tools/testing/kata-startup-latency-lite/run-k8s-pod-lite.sh
```

## Expected Successful Output

A successful run should produce:

- `summary/result.json`
- `summary/result.csv`

The JSON should usually contain at least:

- `t_request_sent`
- `t_object_created`
- `t_scheduled`
- `t_kubelet_syncpod_enter`
- `t_run_pod_sandbox_request`
- `t_vm_started`
- `t_agent_started`
- `t_running`
- `request_to_running_seconds`

On the current reference machine, one real sample produced:

- `request_to_running_seconds = 1.09717`
- `object_create_to_running_seconds = 1.0`
- `vm_boot_seconds = 0.123233`
- `vm_to_agent_seconds = 0.488807`

Reference run:
- [result.json](/home/test/lyq/Micro-VM/kata-containers/.worktrees/kata-startup-latency-phase01/results-lite/2026-04-16/run-20260416T134601Z/summary/result.json)

## What The Parser Assumes

The current parser matches stable log phrases already seen in this environment.

From `kubelet`:
- `"SyncPod enter"`

From `containerd` / Kata:
- `RunPodSandbox for &PodSandboxMetadata`
- `VM started`
- `Agent started in the sandbox`
- `Container is started`

From Kubernetes events:
- `Scheduled`

If a target environment uses different wording, the parser may still run but some fields will be empty.

## Common Porting Gaps

### 1. Different systemd unit names

Current scripts assume:
- `kubelet`
- `containerd`

If your environment uses different units, update `collect-logs-lite.sh`.

### 2. Different runtime log strings

If `containerd.log` does not contain:
- `VM started`
- `Agent started in the sandbox`
- `Container is started`

then update the regex or string checks in `parse_kata_pod_latency.py`.

### 3. Scheduler logs unavailable

That is acceptable.
The lite parser can still use Kubernetes events for `t_scheduled`.

### 4. API server proxy interference

If `kubectl` works only when proxy variables are cleared, update:

`K8S_APISERVER_NO_PROXY`

The runner already forces `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` empty for `kubectl`.

### 5. RuntimeClass name mismatch

Do not edit the manifest directly first.
Set:

`LITE_RUNTIME_CLASS=<your-runtimeclass>`

## How To Validate A New Environment

Use this order:

1. Run one sample.
2. Confirm Pod really reached `Running`.
3. Confirm `summary/result.json` exists.
4. Confirm `request_to_running_seconds` is non-empty.
5. Confirm at least one runtime stage exists:
   - `t_run_pod_sandbox_request`
   - `t_vm_started`
   - `t_agent_started`
6. Inspect missing fields and adapt log matching only where necessary.

## Recommended Local Adjustments

Only change these files when porting:

- `run-k8s-pod-lite.sh`
  for environment variables and access behavior
- `collect-logs-lite.sh`
  for systemd unit names or scheduler log collection
- `parse_kata_pod_latency.py`
  for log phrase matching

Avoid expanding scope during migration.
Keep the first migrated version limited to one successful `k8s_pod` measurement.

## When To Switch Back To The Full Toolchain

Use the full `tools/testing/kata-startup-latency/` directory when you need:

- batch sampling
- `direct_kata_container`
- trace export
- dashboard provisioning
- runtime-rs startup-stage details
- guest agent sub-step analysis
