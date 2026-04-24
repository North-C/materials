#!/usr/bin/env python3
"""Measure CubeSandbox startup and code execution latency using the E2B SDK."""

import os
import time
import sys
from e2b_code_interpreter import Sandbox

TEMPLATE_ID = os.environ.get("CUBE_TEMPLATE_ID") or (sys.argv[1] if len(sys.argv) > 1 else input("Enter template ID: "))
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 5

startup_latencies = []
exec_latencies = []

for i in range(ROUNDS):
    # Measure sandbox startup
    start = time.monotonic()
    sandbox = Sandbox.create(template=TEMPLATE_ID)
    startup_elapsed = time.monotonic() - start

    # Measure code execution
    start = time.monotonic()
    result = sandbox.run_code("print('Hello from Cube Sandbox, safely isolated!')")
    exec_elapsed = time.monotonic() - start

    startup_latencies.append(startup_elapsed)
    exec_latencies.append(exec_elapsed)
    print(f"[{i+1}/{ROUNDS}]  startup={startup_elapsed:.3f}s  exec={exec_elapsed:.3f}s  sandbox={sandbox.sandbox_id}")
    print(f"           result: {result}")

    sandbox.kill()


def stats(name, latencies):
    print(f"  {name:10s}  min={min(latencies):.3f}s  max={max(latencies):.3f}s  "
          f"avg={sum(latencies)/len(latencies):.3f}s  median={sorted(latencies)[len(latencies)//2]:.3f}s")


print(f"\n--- Results over {ROUNDS} runs ---")
stats("startup", startup_latencies)
stats("exec", exec_latencies)
