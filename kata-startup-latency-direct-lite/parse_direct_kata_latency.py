#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


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


def _line_timestamp(line: str) -> str:
    match = re.match(
        r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{4})", line
    )
    if not match:
        return ""
    return _format_timestamp(match.group("ts"))


def _parse_containerd_points(
    log_text: str, sandbox_name: str, sandbox_uid: str, container_name: str, container_id: str
) -> dict[str, str]:
    parsed = {
        "t_run_pod_sandbox_request": "",
        "t_cloud_hypervisor_spawn": "",
        "t_vm_started": "",
        "t_agent_started": "",
        "t_run_pod_sandbox_return": "",
        "t_create_container_request": "",
        "t_create_container_return": "",
        "t_start_container_request": "",
        "t_container_started": "",
        "sandbox_id": "",
    }

    request_pattern = (
        f"RunPodSandbox for &PodSandboxMetadata{{Name:{sandbox_name},Uid:{sandbox_uid},Namespace:default"
    )
    create_request_pattern = f"CreateContainer within sandbox"
    create_request_name = f"Name:{container_name},Attempt:0"

    for line in log_text.splitlines():
        ts = _line_timestamp(line)
        if not ts:
            continue

        if (
            not parsed["t_run_pod_sandbox_request"]
            and request_pattern in line
            and "returns sandbox id" not in line
        ):
            parsed["t_run_pod_sandbox_request"] = ts

        if not parsed["t_cloud_hypervisor_spawn"] and "path=/opt/kata/bin/cloud-hypervisor" in line:
            parsed["t_cloud_hypervisor_spawn"] = ts

        if not parsed["t_vm_started"] and 'msg="VM started"' in line:
            parsed["t_vm_started"] = ts

        if not parsed["t_agent_started"] and 'msg="Agent started in the sandbox"' in line:
            parsed["t_agent_started"] = ts

        if (
            not parsed["t_run_pod_sandbox_return"]
            and request_pattern in line
            and "returns sandbox id" in line
        ):
            parsed["t_run_pod_sandbox_return"] = ts
            match = re.search(r'returns sandbox id \\"([^"]+)\\"', line)
            if not match:
                match = re.search(r'returns sandbox id "([^"]+)"', line)
            if match:
                parsed["sandbox_id"] = match.group(1)

        sandbox_id = parsed["sandbox_id"]
        if (
            not parsed["t_create_container_request"]
            and create_request_pattern in line
            and create_request_name in line
            and "returns container id" not in line
            and (not sandbox_id or sandbox_id in line)
        ):
            parsed["t_create_container_request"] = ts

        if (
            not parsed["t_create_container_return"]
            and create_request_pattern in line
            and create_request_name in line
            and "returns container id" in line
            and (not sandbox_id or sandbox_id in line)
        ):
            parsed["t_create_container_return"] = ts

        if (
            not parsed["t_start_container_request"]
            and "StartContainer for" in line
            and container_id in line
        ):
            parsed["t_start_container_request"] = ts

        if (
            not parsed["t_container_started"]
            and 'msg="Container is started"' in line
            and container_id in line
            and (not sandbox_id or sandbox_id in line)
        ):
            parsed["t_container_started"] = ts

    return parsed


def parse_run_dir(run_dir: str | Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    request = _load_json(run_dir / "raw" / "request.json")
    inspectp = _load_json(run_dir / "raw" / "inspectp.json")
    inspect = _load_json(run_dir / "raw" / "inspect.json")
    containerd_log = (run_dir / "logs" / "containerd.log").read_text(encoding="utf-8")

    inspectp_status = inspectp["status"]
    inspect_status = inspect["status"]
    sandbox_name = request["sandbox_name"]
    sandbox_uid = inspectp_status["metadata"].get("uid", "")
    container_name = request["container_name"]
    container_id = inspect_status["id"]
    runtime_points = _parse_containerd_points(
        containerd_log, sandbox_name, sandbox_uid, container_name, container_id
    )

    t_request_sent = _format_timestamp(request["t_request_sent"])
    t_object_created = _format_timestamp(inspectp_status["createdAt"])
    t_running = _format_timestamp(inspect_status["startedAt"])
    t_container_started = runtime_points["t_container_started"] or t_running

    parsed = {
        "run_id": request.get("run_id", ""),
        "workload_type": "direct_kata_container",
        "namespace": request.get("namespace", "default"),
        "sandbox_name": sandbox_name,
        "container_name": container_name,
        "sandbox_id": runtime_points["sandbox_id"] or inspectp_status["id"],
        "container_id": container_id,
        "runtime_handler": request.get("runtime_handler", ""),
        "hypervisor": request.get("hypervisor", ""),
        "t_request_sent": t_request_sent,
        "t_object_created": t_object_created,
        "t_cloud_hypervisor_spawn": runtime_points["t_cloud_hypervisor_spawn"],
        "t_run_pod_sandbox_request": runtime_points["t_run_pod_sandbox_request"],
        "t_vm_started": runtime_points["t_vm_started"],
        "t_agent_started": runtime_points["t_agent_started"],
        "t_run_pod_sandbox_return": runtime_points["t_run_pod_sandbox_return"],
        "t_create_container_request": runtime_points["t_create_container_request"],
        "t_create_container_return": runtime_points["t_create_container_return"],
        "t_start_container_request": runtime_points["t_start_container_request"],
        "t_container_started": t_container_started,
        "t_running": t_running,
        "request_to_running_seconds": _seconds_between(t_request_sent, t_running),
    }

    if runtime_points["t_run_pod_sandbox_request"] and runtime_points["t_run_pod_sandbox_return"]:
        parsed["sandbox_create_seconds"] = _seconds_between(
            runtime_points["t_run_pod_sandbox_request"],
            runtime_points["t_run_pod_sandbox_return"],
        )
    if runtime_points["t_cloud_hypervisor_spawn"] and runtime_points["t_vm_started"]:
        parsed["vm_boot_seconds"] = _seconds_between(
            runtime_points["t_cloud_hypervisor_spawn"], runtime_points["t_vm_started"]
        )
    if runtime_points["t_vm_started"] and runtime_points["t_agent_started"]:
        parsed["vm_to_agent_seconds"] = _seconds_between(
            runtime_points["t_vm_started"], runtime_points["t_agent_started"]
        )
    if runtime_points["t_create_container_request"] and runtime_points["t_create_container_return"]:
        parsed["create_container_seconds"] = _seconds_between(
            runtime_points["t_create_container_request"],
            runtime_points["t_create_container_return"],
        )
    if runtime_points["t_start_container_request"] and runtime_points["t_container_started"]:
        parsed["start_container_seconds"] = _seconds_between(
            runtime_points["t_start_container_request"], runtime_points["t_container_started"]
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
        description="Parse direct containerd+kata+cloud-hypervisor startup latency from logs."
    )
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    result = parse_run_dir(args.run_dir)
    write_outputs(result, args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
