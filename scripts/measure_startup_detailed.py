#!/usr/bin/env python3
"""Detailed CubeSandbox latency breakdown using server-side logs.

Creates sandboxes, then parses CubeMaster and Cubelet logs to extract
per-phase timing as measured by the server itself.

This script must run INSIDE the CubeSandbox environment (VM or server).

Sub-phases extracted:
  From Cubelet-stat (CostTime in ms):
    sandbox-create         — Cubelet create workflow (VM restore + configure)
    sandbox-start          — Start the MicroVM
    sandbox-probe          — Wait for health probe to pass
    cubebox                — Full cubebox workflow
    cubebox-service        — Cubebox service total
    cubebox-service-inner  — Cubebox service inner logic

  From CubeMaster ext_info (ms):
    cube-e2e               — End-to-end from request received to response sent
    sandbox-probe          — Probe time reported by CubeMaster
    all-probe              — All probe time

  From destroy ext_info (ms):
    Per-step teardown timing (del-task-sandbox, cubebox, network, etc.)

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
CODE = "print('Hello from Cube Sandbox, safely isolated!')"

LOG_MASTER_REQ = "/data/log/CubeMaster/cubemaster-req.log"
LOG_CUBELET_STAT = "/data/log/Cubelet/Cubelet-stat.log"
LOG_CUBELET_REQ = "/data/log/Cubelet/Cubelet-req.log"
LOG_API = "/data/log/CubeAPI/cube-api.log"

LOG_FILES = [LOG_MASTER_REQ, LOG_CUBELET_STAT, LOG_CUBELET_REQ, LOG_API]


def count_lines(path):
    try:
        with open(path) as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        return 0


def read_lines_from(path, since):
    """Read lines starting from line number `since` (1-indexed, exclusive)."""
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


def parse_logs(request_id, sandbox_id, master_lines, cubelet_stat_lines, cubelet_req_lines, api_lines):
    result = {}

    # --- CubeMaster-req: ext_info in CreateSandbox_rsp ---
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

    # --- CubeMaster-req: destroy ext_info (different request_id) ---
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

    # --- Cubelet-stat: CostTime per Callee ---
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

    # --- CubeAPI: timestamp for sandbox.created ---
    for line in api_lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("event") == "sandbox.created" and obj.get("sandbox_id", "").startswith(sandbox_id[:8]):
            result["api.sandbox_created_ts"] = obj.get("timestamp", "")

    return result


def stats(name, values):
    s = sorted(values)
    n = len(s)
    print(
        f"  {name:40s}  min={min(s):>8.1f}ms  max={max(s):>8.1f}ms  "
        f"avg={sum(s) / n:>8.1f}ms  p50={s[n // 2]:>8.1f}ms"
    )


def main():
    print(f"Template: {TEMPLATE_ID}")
    print(f"Rounds:   {ROUNDS}")
    print(f"API:      {API_URL}")
    print()

    all_results = []

    for i in range(ROUNDS):
        print(f"[{i + 1}/{ROUNDS}]", end=" ")

        # Snapshot log positions
        pos = {f: count_lines(f) for f in LOG_FILES}

        # Create sandbox
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
            print(f"ERROR: {resp.status_code} {resp.text}")
            continue

        data = resp.json()
        sandbox_id = data.get("sandboxID", "unknown")
        request_id = data.get("clientID", "")
        print(f"sandbox={sandbox_id[:12]}  client_create={client_create_ms:.0f}ms", end="")

        # Kill sandbox
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
        print(f"  client_kill={client_kill_ms:.0f}ms")

        # Wait for logs to flush
        time.sleep(0.3)

        # Read new log lines
        master_lines = read_lines_from(LOG_MASTER_REQ, pos[LOG_MASTER_REQ])
        cubelet_stat_lines = read_lines_from(LOG_CUBELET_STAT, pos[LOG_CUBELET_STAT])
        cubelet_req_lines = read_lines_from(LOG_CUBELET_REQ, pos[LOG_CUBELET_REQ])
        api_lines = read_lines_from(LOG_API, pos[LOG_API])

        parsed = parse_logs(request_id, sandbox_id, master_lines, cubelet_stat_lines, cubelet_req_lines, api_lines)
        parsed["client.create_ms"] = round(client_create_ms, 1)
        parsed["client.kill_ms"] = round(client_kill_ms, 1)
        all_results.append(parsed)

        # Print server-side breakdown for this round
        for k in sorted(parsed.keys()):
            if k.startswith("cubelet.create.") or k.startswith("master."):
                print(f"    {k:52s} = {parsed[k]:>8.1f}ms")
        for k in sorted(parsed.keys()):
            if k.startswith("cubelet.destroy.") or k.startswith("destroy."):
                print(f"    {k:52s} = {parsed[k]:>8.1f}ms")

    # Aggregate
    print(f"\n{'=' * 85}")
    print(f"Aggregate over {len(all_results)} successful runs")
    print(f"{'=' * 85}")

    all_keys = set()
    for r in all_results:
        all_keys.update(r.keys())

    for k in sorted(all_keys):
        values = [r[k] for r in all_results if k in r and isinstance(r[k], (int, float))]
        if values:
            stats(k, values)


if __name__ == "__main__":
    main()
