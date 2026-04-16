#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


KLOG_TS_RE = re.compile(
    r'^[IWEF](?P<month>\d{2})(?P<day>\d{2}) (?P<clock>\d{2}:\d{2}:\d{2}\.\d+)'
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_timestamp(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    value = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", value)
    value = re.sub(r"\.(\d{6})\d+([+-]\d{2}:\d{2})$", r".\1\2", value)
    return datetime.fromisoformat(value)


def _format_timestamp(value: str | datetime) -> str:
    if isinstance(value, str):
        value = _parse_timestamp(value)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f%z")


def _seconds_between(start: str, end: str) -> float:
    return (_parse_timestamp(end) - _parse_timestamp(start)).total_seconds()


def _container_id(value: str) -> str:
    prefix = "containerd://"
    return value[len(prefix) :] if value.startswith(prefix) else value


def _event_timestamp(events: dict[str, Any], reason: str) -> str:
    for item in events.get("items", []):
        if item.get("reason") == reason:
            ts = (
                item.get("eventTime")
                or item.get("firstTimestamp")
                or item.get("lastTimestamp")
                or item.get("metadata", {}).get("creationTimestamp", "")
            )
            if ts:
                return _format_timestamp(ts)
    return ""


def _line_timestamp(line: str) -> str:
    full_ts = re.match(
        r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{4})", line
    )
    if full_ts:
        return _format_timestamp(full_ts.group("ts"))

    klog_ts = KLOG_TS_RE.match(line)
    if klog_ts:
        year = datetime.now().year
        offset = datetime.now().astimezone().strftime("%z")
        raw = (
            f"{year}-{klog_ts.group('month')}-{klog_ts.group('day')}"
            f"T{klog_ts.group('clock')}{offset}"
        )
        return _format_timestamp(raw)

    return ""


def _parse_kubelet_syncpod_enter(log_text: str, pod_name: str, pod_uid: str) -> str:
    for line in log_text.splitlines():
        if (
            '"SyncPod enter"' in line
            and f'pod="default/{pod_name}"' in line
            and f'podUID="{pod_uid}"' in line
        ):
            return _line_timestamp(line)
    return ""


def _parse_scheduler_bound(log_text: str, pod_name: str) -> str:
    for line in log_text.splitlines():
        if (
            "Successfully bound pod to node" in line
            and f'pod="default/{pod_name}"' in line
        ):
            return _line_timestamp(line)
    return ""


def _parse_containerd_points(
    log_text: str, pod_name: str, pod_uid: str, container_id: str
) -> dict[str, str]:
    parsed = {
        "t_run_pod_sandbox_request": "",
        "t_vm_started": "",
        "t_agent_started": "",
        "t_container_started": "",
        "sandbox_id": "",
    }

    request_pattern = (
        f"RunPodSandbox for &PodSandboxMetadata{{Name:{pod_name},Uid:{pod_uid},Namespace:default"
    )
    return_pattern = (
        f"RunPodSandbox for &PodSandboxMetadata{{Name:{pod_name},Uid:{pod_uid},Namespace:default"
    )

    for line in log_text.splitlines():
        ts = _line_timestamp(line)
        if not ts:
            continue

        if not parsed["t_run_pod_sandbox_request"] and request_pattern in line:
            parsed["t_run_pod_sandbox_request"] = ts

        if not parsed["t_vm_started"] and 'msg="VM started"' in line:
            parsed["t_vm_started"] = ts

        if (
            not parsed["t_agent_started"]
            and 'msg="Agent started in the sandbox"' in line
        ):
            parsed["t_agent_started"] = ts

        if (
            not parsed["sandbox_id"]
            and return_pattern in line
            and "returns sandbox id" in line
        ):
            match = re.search(r'returns sandbox id \\"([^"]+)\\"', line)
            if not match:
                match = re.search(r'returns sandbox id "([^"]+)"', line)
            if match:
                parsed["sandbox_id"] = match.group(1)

        if (
            not parsed["t_container_started"]
            and 'msg="Container is started"' in line
            and f"container={container_id}" in line
        ):
            parsed["t_container_started"] = ts

    return parsed


def parse_run_dir(run_dir: str | Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    request = _load_json(run_dir / "raw" / "request.json")
    pod = _load_json(run_dir / "raw" / "pod.json")
    events_path = run_dir / "raw" / "events.json"
    events = _load_json(events_path) if events_path.is_file() else {"items": []}

    metadata = pod["metadata"]
    container_status = pod["status"]["containerStatuses"][0]
    pod_name = metadata["name"]
    pod_uid = metadata["uid"]
    container_id = _container_id(container_status.get("containerID", ""))

    kubelet_log = (run_dir / "logs" / "kubelet.log").read_text(encoding="utf-8")
    scheduler_path = run_dir / "logs" / "kube-scheduler.log"
    scheduler_log = (
        scheduler_path.read_text(encoding="utf-8") if scheduler_path.is_file() else ""
    )
    containerd_log = (run_dir / "logs" / "containerd.log").read_text(encoding="utf-8")

    runtime_points = _parse_containerd_points(
        containerd_log, pod_name, pod_uid, container_id
    )
    t_request_sent = _format_timestamp(request["t_request_sent"])
    t_object_created = _format_timestamp(metadata["creationTimestamp"])
    t_scheduled = _event_timestamp(events, "Scheduled") or _parse_scheduler_bound(
        scheduler_log, pod_name
    )
    t_kubelet_syncpod_enter = _parse_kubelet_syncpod_enter(
        kubelet_log, pod_name, pod_uid
    )
    t_running = _format_timestamp(
        container_status["state"]["running"]["startedAt"]
    )
    t_container_started = runtime_points["t_container_started"] or t_running

    parsed = {
        "run_id": request.get("run_id", ""),
        "workload_type": "k8s_pod",
        "namespace": metadata["namespace"],
        "pod_name": pod_name,
        "pod_uid": pod_uid,
        "sandbox_id": runtime_points["sandbox_id"],
        "container_id": container_id,
        "runtime_handler": request.get("runtime_handler", ""),
        "hypervisor": request.get("hypervisor", ""),
        "t_request_sent": t_request_sent,
        "t_object_created": t_object_created,
        "t_scheduled": t_scheduled,
        "t_kubelet_syncpod_enter": t_kubelet_syncpod_enter,
        "t_run_pod_sandbox_request": runtime_points["t_run_pod_sandbox_request"],
        "t_vm_started": runtime_points["t_vm_started"],
        "t_agent_started": runtime_points["t_agent_started"],
        "t_container_started": t_container_started,
        "t_running": t_running,
        "request_to_running_seconds": _seconds_between(t_request_sent, t_running),
        "object_create_to_running_seconds": _seconds_between(
            t_object_created, t_running
        ),
    }

    if t_scheduled:
        parsed["schedule_latency_seconds"] = _seconds_between(
            t_object_created, t_scheduled
        )
    if t_kubelet_syncpod_enter and runtime_points["t_run_pod_sandbox_request"]:
        parsed["kubelet_to_runtime_seconds"] = _seconds_between(
            t_kubelet_syncpod_enter, runtime_points["t_run_pod_sandbox_request"]
        )
    if runtime_points["t_run_pod_sandbox_request"] and runtime_points["t_vm_started"]:
        parsed["vm_boot_seconds"] = _seconds_between(
            runtime_points["t_run_pod_sandbox_request"], runtime_points["t_vm_started"]
        )
    if runtime_points["t_vm_started"] and runtime_points["t_agent_started"]:
        parsed["vm_to_agent_seconds"] = _seconds_between(
            runtime_points["t_vm_started"], runtime_points["t_agent_started"]
        )
    if runtime_points["t_run_pod_sandbox_request"]:
        parsed["runtime_to_running_seconds"] = _seconds_between(
            runtime_points["t_run_pod_sandbox_request"], t_running
        )

    return parsed


def write_outputs(result: dict[str, Any], run_dir: str | Path) -> None:
    run_dir = Path(run_dir)
    summary_dir = run_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    csv_path = summary_dir / "result.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(result.keys()))
        writer.writeheader()
        writer.writerow(result)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse Kubernetes Kata Pod latency from pod artifacts and logs."
    )
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    result = parse_run_dir(args.run_dir)
    write_outputs(result, args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
