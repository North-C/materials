#!/usr/bin/env python3
"""Measure CubeSandbox startup latency using the E2B SDK."""

import os
import time
import sys
from e2b_code_interpreter import Sandbox

TEMPLATE_ID = os.environ.get("CUBE_TEMPLATE_ID") or (sys.argv[1] if len(sys.argv) > 1 else input("Enter template ID: "))
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 5

latencies = []

for i in range(ROUNDS):
    start = time.monotonic()
    sandbox = Sandbox.create(template=TEMPLATE_ID)
    elapsed = time.monotonic() - start

    latencies.append(elapsed)
    print(f"[{i+1}/{ROUNDS}]  {elapsed:.3f}s  sandbox={sandbox.sandbox_id}")

    sandbox.close()

print(f"\n--- Results over {ROUNDS} runs ---")
print(f"Min:    {min(latencies):.3f}s")
print(f"Max:    {max(latencies):.3f}s")
print(f"Avg:    {sum(latencies)/len(latencies):.3f}s")
print(f"Median: {sorted(latencies)[len(latencies)//2]:.3f}s")
