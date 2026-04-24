#!/usr/bin/env python3
"""Detailed CubeSandbox latency breakdown using server-side logs.

Creates sandboxes, then parses CubeMaster and Cubelet logs to extract
per-phase timing as measured by the server itself.

This script must run INSIDE the CubeSandbox environment (VM or server).

Usage:
  python3 measure_startup_detailed.py [TEMPLATE_ID] [ROUNDS]
"""

import base64
import json
import os
import sys
import time

import requests

API_URL = os.environ.get("E2B_API_URL", "http://127.0.0.1:3000")
API_KEY = os.environ.get("E2B_API_KEY", "dummy")
TEMPLATE_ID = os.environ.get("CUBE_TEMPLATE_ID") or (
    sys.argv[1] if len(sys.argv) > 1 else input("Enter template ID: ")
)
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 5

LOG_MASTER_REQ = "/data/log/CubeMaster/cubemaster-req.log"
LOG_CUBELET_STAT = "/data/log/Cubelet/Cubelet-stat.log"
LOG_CUBELET_REQ = "/data/log/Cubelet/Cubelet-req.log"
LOG_API = "/data/log/CubeAPI/cube-api.log"

LOG_FILES = [LOG_MASTER_REQ, LOG_CUBELET_STAT, LOG_CUBELET_REQ, LOG_API]

# Ordered sub-phase definitions for readable output.
# (log_key, display_name, description)
CREATE_PHASES = [
    ("client.create_ms",          "client API call",        "Client POST /sandboxes round-trip (incl. network)"),
    ("master.cube-e2e",           "CubeMaster E2E",         "CubeMaster total: schedule + Cubelet call + respond"),
    ("cubelet.create.sandbox-create", "  Cubelet create",   "  Restore MicroVM from snapshot + configure resources"),
    ("cubelet.create.sandbox-start",  "  Cubelet start",    "  Fire up the restored MicroVM (VMM launch)"),
    ("cubelet.create.sandbox-probe",  "  Health probe",     "  Poll until guest health endpoint returns 200"),
    ("cubelet.create.cubebox-service-inner", "  Service inner", "  Cubebox internal bookkeeping"),
    ("cubelet.create.cubebox-service", "  Cubebox service",  "  Full cubebox-service create (wraps above)"),
    ("cubelet.create.cubebox",    "  Cubebox workflow",      "  Full workflow incl. storage, network, cgroup, cubebox"),
]

DESTROY_PHASES = [
    ("client.kill_ms",            "client API call",        "Client DELETE /sandboxes/{id} round-trip"),
    ("destroy.sandbox-del-container", "  Delete container", "  Tear down the running MicroVM container"),
    ("destroy.del-task-sandbox",  "  Delete task",          "  Clean up task metadata"),
    ("destroy.network",           "  Release network",      "  Free TAP interface and network resources"),
    ("destroy.volume",            "  Release volume",       "  Clean up writable layer volume"),
    ("destroy.storage",           "  Release storage",      "  Remove storage backend entries"),
    ("destroy.cgroup",            "  Release cgroup",       "  Clean up cgroup allocation"),
    ("destroy.cleanup",           "  Final cleanup",        "  Remaining teardown"),
]

ALL_PHASES = CREATE_PHASES + DESTROY_PHASES


def count_lines(path):
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def read_lines_from(path, since):
    try:
        with open(path) as f:
            lines = f.readlines()
        return [l.strip() for l in lines[since:] if l.strip()]
    except FileNotFoundError:
        return []


def decode_ext_info_ms(raw):
    try:
        return int(base64.b64decode(raw).decode())
    except Exception:
        try:
            return int(raw)
        except Exception:
            return None


def parse_logs(request_id, sandbox_id, master_lines, cubelet_stat_lines, api_lines):
    result = {}

    # CubeMaster-req: ext_info in CreateSandbox_rsp
    for line in master_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("RequestId") != request_id:
            continue
        content = obj.get("LogContent", "")
        if "CreateSandbox_rsp:" in content:
            try:
                rsp_str = content.split("CreateSandbox_rsp:", 1)[1].strip()
                rsp = json.loads(rsp_str)
                for k, v in rsp.get("ext_info", {}).items():
                    val = decode_ext_info_ms(v)
                    if val is not None:
                        result[f"master.{k}"] = val
            except (json.JSONDecodeError, IndexError):
                pass

    # CubeMaster-req: destroy ext_info (different request_id)
    for line in master_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if sandbox_id not in obj.get("InstanceId", ""):
            continue
        content = obj.get("LogContent", "")
        if "Destroy_rsp:" in content:
            try:
                rsp_str = content.split("Destroy_rsp:", 1)[1].strip()
                rsp = json.loads(rsp_str)
                for k, v in rsp.get("ext_info", {}).items():
                    val = decode_ext_info_ms(v)
                    if val is not None:
                        result[f"destroy.{k}"] = val
            except (json.JSONDecodeError, IndexError):
                pass

    # Cubelet-stat: CostTime per Callee
    for line in cubelet_stat_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("RequestId") != request_id:
            continue
        callee = obj.get("Callee", "")
        cost = obj.get("CostTime", 0)
        action = obj.get("Action", "")
        if action == "Create" and cost > 0:
            result[f"cubelet.create.{callee}"] = round(cost, 3)
        elif action == "Destroy" and cost > 0:
            result[f"cubelet.destroy.{callee}"] = round(cost, 3)

    return result


def print_phase_table(title, phases, parsed):
    """Print one section (create or destroy) with aligned columns."""
    print(f"\n  {title}")
    print(f"  {'-' * 72}")
    print(f"  {'Phase':24s} {'Time':>8s}   {'Description'}")
    print(f"  {'-' * 72}")
    for key, name, desc in phases:
        val = parsed.get(key)
        if val is not None:
            print(f"  {name:24s} {val:>7.1f}ms   {desc}")
    print()


def print_aggregate(title, phases, all_results):
    """Print aggregate stats (min/avg/p50/max) for a section."""
    print(f"  {title}")
    print(f"  {'-' * 80}")
    print(f"  {'Phase':24s} {'min':>8s} {'avg':>8s} {'p50':>8s} {'max':>8s}")
    print(f"  {'-' * 80}")
    for key, name, _ in phases:
        values = [r[key] for r in all_results if key in r and isinstance(r[key], (int, float))]
        if values:
            s = sorted(values)
            n = len(s)
            print(f"  {name:24s} {min(s):>7.1f}ms {sum(s)/n:>7.1f}ms {s[n//2]:>7.1f}ms {max(s):>7.1f}ms")
    print()


def main():
    print(f"Template: {TEMPLATE_ID}")
    print(f"Rounds:   {ROUNDS}")
    print(f"API:      {API_URL}")

    all_results = []

    for i in range(ROUNDS):
        print(f"\n{'=' * 76}")
        print(f"  Round {i + 1}/{ROUNDS}")
        print(f"{'=' * 76}")

        # Snapshot log positions
        pos = {f: count_lines(f) for f in LOG_FILES}

        # --- Create ---
        t0 = time.monotonic()
        resp = requests.post(
            f"{API_URL}/sandboxes",
            json={"templateID": TEMPLATE_ID},
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=60,
        )
        t1 = time.monotonic()
        client_create_ms = (t1 - t0) * 1000

        if resp.status_code not in (200, 201):
            print(f"  ERROR: {resp.status_code} {resp.text}")
            continue

        data = resp.json()
        sandbox_id = data.get("sandboxID", "unknown")
        request_id = data.get("clientID", "")

        # --- Destroy ---
        t2 = time.monotonic()
        try:
            requests.delete(
                f"{API_URL}/sandboxes/{sandbox_id}",
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=30,
            )
        except Exception:
            pass
        t3 = time.monotonic()
        client_kill_ms = (t3 - t2) * 1000

        time.sleep(0.3)

        # Read new log lines
        master_lines = read_lines_from(LOG_MASTER_REQ, pos[LOG_MASTER_REQ])
        cubelet_stat_lines = read_lines_from(LOG_CUBELET_STAT, pos[LOG_CUBELET_STAT])
        cubelet_req_lines = read_lines_from(LOG_CUBELET_REQ, pos[LOG_CUBELET_REQ])
        api_lines = read_lines_from(LOG_API, pos[LOG_API])

        parsed = parse_logs(request_id, sandbox_id, master_lines, cubelet_stat_lines, api_lines)
        parsed["client.create_ms"] = round(client_create_ms, 1)
        parsed["client.kill_ms"] = round(client_kill_ms, 1)
        all_results.append(parsed)

        print(f"  sandbox_id = {sandbox_id}")
        print_phase_table("CREATE  (CubeAPI -> CubeMaster -> Cubelet -> MicroVM -> probe)", CREATE_PHASES, parsed)
        print_phase_table("DESTROY (CubeAPI -> CubeMaster -> Cubelet -> teardown)", DESTROY_PHASES, parsed)

    # --- Aggregate ---
    if all_results:
        print(f"\n{'#' * 76}")
        print(f"  AGGREGATE over {len(all_results)} successful runs")
        print(f"{'#' * 76}")
        print_aggregate("CREATE", CREATE_PHASES, all_results)
        print_aggregate("DESTROY", DESTROY_PHASES, all_results)


if __name__ == "__main__":
    main()
