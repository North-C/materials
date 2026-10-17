#!/usr/bin/env python3
"""Run N sequential c100n100 -w3 rounds for one tuning state, with an identical quiet gate.

usage: run_series.py SESSION STATE ROUNDS
Stops at the first failed round (no re-runs to pick results). Each round output:
SESSION/STATE/round-NN; progress JSON lines in SESSION/STATE/progress.log.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

session, state, rounds = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
BIN_SHA = 'ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511'
GATE_SAMPLES, GATE_PAUSE, COOLDOWN, MAX_LOAD1 = 3, 5, 10, 4.0
sys.path.insert(0, str(session / 'scripts'))
import run_round_w3 as rr  # noqa: E402

# CAPTURE_CONFIG selects an alternative config (e.g. another template); default unchanged.
config_path = Path(os.environ.get('CAPTURE_CONFIG', str(session / 'capture100.local.json')))
config = json.loads(config_path.read_text())
api = rr.API(config)
base = session / state
base.mkdir(parents=True, exist_ok=True)
progress = (base / 'progress.log').open('a')


def emit(**value):
    value['time'] = rr.now()
    line = json.dumps(value, ensure_ascii=False)
    print(line, flush=True)
    progress.write(line + '\n')
    progress.flush()


def busy_processes():
    out = subprocess.run(['pgrep', '-a', '-f', 'cube-bench|containerd-shim-cube-rs'], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if 'pgrep' not in l]


def quiet_gate(deadline=600):
    start, passed, samples = time.monotonic(), 0, []
    while passed < GATE_SAMPLES:
        if time.monotonic() - start > deadline:
            emit(state=state, event='gate_timeout', samples=samples[-6:])
            sys.exit(4)
        rows = rr.inventory(api)
        load1 = float(Path('/proc/loadavg').read_text().split()[0])
        busy = busy_processes()
        ok = not rows and not busy and load1 < MAX_LOAD1
        samples.append({'inventory': len(rows), 'busy': len(busy), 'load1': load1, 'ok': ok})
        passed = passed + 1 if ok else 0
        if passed < GATE_SAMPLES:
            time.sleep(GATE_PAUSE)
    return samples[-GATE_SAMPLES:]


for i in range(1, rounds + 1):
    out = base / ('round-%02d' % i)
    gate = quiet_gate()
    emit(state=state, round=i, event='starting', gate=gate)
    cmd = [sys.executable, str(session / 'scripts/run_round_w3.py'), '--config', str(config_path),
           '--tool-dir', str(session / 'tool'), '--binary', str(session / 'bin/cube-bench'),
           '--expected-sha256', BIN_SHA, '--output', str(out)]
    with (base / ('round-%02d.log' % i)).open('w') as log:
        code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
    if code:
        emit(state=state, round=i, event='failed', code=code)
        sys.exit(code)
    raw = next((out / 'runs').glob('*/capture/startup-latency/benchmark.raw.json'))
    data = json.loads(raw.read_text())
    clean = json.loads((out / 'evidence/cleanup.json').read_text())
    s = data['summary']
    emit(state=state, round=i, event='complete', total_ms=round(s['total_time_s'] * 1000, 3),
         ok=s.get('successful'), errors=s.get('errors'), create=s.get('create'),
         cleanup=clean['status'], deleted=len(clean['outcomes']))
    time.sleep(COOLDOWN)
emit(state=state, event='series_complete', rounds=rounds)
