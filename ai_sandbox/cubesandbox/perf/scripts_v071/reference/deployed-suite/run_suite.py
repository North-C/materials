"""Run the benchmark files linked by the CubeSandbox performance article."""

import argparse
import base64
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from summarize_results import summarize

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / "examples/snapshot-rollback-clone"
GO = ROOT / "examples/cube-bench"
SECTIONS = ("3.2", "3.3", "4.1", "4.2", "4.3", "4.4", "4.5", "4.6")
NATIVE_HTTP_PROFILE = "native-http-v120-create"
FEATURE_V120_SHA256 = "cd7d4fdc4173f309a28149535ea31f782cef2f64c6371cb5ffcf3d8dbe9ef484"
SPEC_TEMPLATE_ENV = {
    "1vCPU/1GiB": ("1u1g", "CUBE_TEMPLATE_ID_1U1G"),
    "2vCPU/2GiB": ("2u2g", "CUBE_TEMPLATE_ID_2U2G"),
    "2vCPU/4GiB": ("2u4g", "CUBE_TEMPLATE_ID_2U4G"),
}
SPEC_RESOURCES = {
    "1vCPU/1GiB": (1, 1024),
    "2vCPU/2GiB": (2, 2048),
    "2vCPU/4GiB": (2, 4096),
}


def feature_create_cases(path):
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if digest != FEATURE_V120_SHA256:
        raise ValueError(f"unexpected feature SHA256: {digest}")
    section = content.decode("utf-8").split("Scenario Outline: 基于模板或镜像创建沙箱", 1)[1]
    section = section.split("Scenario Outline:", 1)[0]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.lstrip().startswith("|")]
    if rows[0] != ["规格", "并发数", "请求数", "预热轮次", "正式轮次"] or len(rows) != 34:
        raise ValueError("unexpected V1.20 create table")
    cases = []
    for spec, concurrency, total, warmups, measured in rows[1:]:
        if spec not in SPEC_TEMPLATE_ENV or (int(warmups), int(measured)) != (3, 3):
            raise ValueError("unsupported V1.20 create case")
        c, n = int(concurrency), int(total)
        if c < 1 or n < c:
            raise ValueError("invalid V1.20 create case")
        cases.append((spec, c, n, int(warmups), int(measured)))
    return cases


def native_case_spec(label):
    slug = label.split("-", 1)[0]
    for spec, (candidate, _) in SPEC_TEMPLATE_ENV.items():
        if slug == candidate:
            return spec
    raise ValueError(f"unknown native HTTP case label: {label}")


class APIError(RuntimeError):
    def __init__(self, method, path, status):
        super().__init__(f"{method} {path}: HTTP {status}")
        self.status = status


class API:
    def __init__(self, url, key):
        self.url = url.rstrip("/")
        self.key = key

    def request(self, method, path, params=None):
        url = self.url + path + ("?" + urlencode(params) if params else "")
        request = Request(url, method=method, headers={"Authorization": f"Bearer {self.key}"})
        try:
            with urlopen(request, timeout=30) as response:
                return (json.load(response), response.headers) if method == "GET" else (None, response.status)
        except HTTPError as exc:
            raise APIError(method, path, exc.code) from exc

    def sandboxes(self):
        items, _ = self.request("GET", "/v2/sandboxes", {"limit": 10000})
        if not isinstance(items, list) or len(items) >= 10000:
            raise RuntimeError("sandbox list invalid or truncated")
        return items

    def snapshots(self):
        ids, token, seen = set(), None, set()
        while True:
            params = {"limit": 100}
            if token:
                params["nextToken"] = token
            items, headers = self.request("GET", "/snapshots", params)
            if not isinstance(items, list) or len(items) > 100:
                raise RuntimeError("snapshot list invalid")
            ids.update(item["snapshotID"] for item in items)
            token = headers.get("x-next-token")
            if not token:
                return ids
            if token in seen:
                raise RuntimeError("snapshot pagination loop")
            seen.add(token)

    def drain_tagged(self, run_id, timeout=180, evidence_path=None):
        deadline, stable = time.monotonic() + timeout, 0
        evidence = {"run_id": run_id, "observed_ids": [], "deletes": [],
                    "final_owned": None, "status": "started"}
        seen = set()
        try:
            while time.monotonic() < deadline:
                items = self.sandboxes()
                owned = [item["sandboxID"] for item in items
                         if (item.get("metadata") or {}).get("perf_suite_run") == run_id]
                foreign = len(items) - len(owned)
                for sandbox_id in owned:
                    if sandbox_id not in seen:
                        evidence["observed_ids"].append(sandbox_id)
                        seen.add(sandbox_id)
                evidence["final_owned"] = len(owned)
                if owned:
                    def delete(sandbox_id):
                        try:
                            result = self.request("DELETE", f"/sandboxes/{sandbox_id}")
                            status = result[1] if isinstance(result, tuple) else None
                            return {"sandbox_id": sandbox_id, "http_status": status}
                        except APIError as exc:
                            if exc.status not in (404, 408, 429, 503):
                                raise
                            return {"sandbox_id": sandbox_id, "http_status": exc.status}

                    with ThreadPoolExecutor(max_workers=20) as pool:
                        evidence["deletes"].extend(pool.map(delete, owned))
                    stable = 0
                else:
                    stable += 1
                    if stable >= 2:
                        if foreign:
                            raise RuntimeError(f"{foreign} foreign sandbox(es) appeared; left untouched")
                        evidence["status"] = "drained"
                        return
                time.sleep(2)
            raise RuntimeError(f"tagged sandboxes did not drain for run {run_id}")
        finally:
            if evidence_path:
                save(evidence_path, evidence)


class ExclusiveTemplateLedger:
    """Operational ownership under explicit exclusivity, NOT a seq-to-ID mapping."""

    def __init__(self, template_id, path):
        self.template_id, self.path, self.limit = template_id, path, 0
        self.ids = set()
        self.blocked = None
        self.evidence = {"ownership_mode": "exclusive-template", "template_id": template_id,
                         "basis": "empty baseline and operator-authorized dedicated template",
                         "observed_ids": [], "observations": [], "deletes": [], "status": "started"}

    def observe(self, items):
        # Validate the entire observation before adopting ANY new ID.
        ids = [item.get("sandboxID") for item in items]
        reason = self.blocked
        if any(not isinstance(sid, str) or not sid for sid in ids) or len(set(ids)) != len(ids):
            reason = "invalid or duplicate sandbox identity"
        elif any(item.get("templateID") != self.template_id for item in items):
            reason = "foreign template appeared; left untouched"
        elif len(set(ids) | self.ids) > self.limit:
            reason = "exclusive-template population exceeds authorized bound"
        elif any(item.get("state") != "running" for item in items):
            reason = "unknown/non-running sandbox state; not adopted"
        self.evidence["observations"].append({"ids": ids, "limit": self.limit, "error": reason})
        self.blocked = reason
        if not reason:
            self.ids.update(ids)
            self.evidence["observed_ids"] = sorted(self.ids)
        save(self.path, self.evidence)
        if reason:
            raise RuntimeError(reason)
        return items

    def drain(self, api, timeout=180):
        deadline, stable, first_error = time.monotonic() + timeout, 0, None
        try:
            while time.monotonic() < deadline:
                items = api.sandboxes()
                try:
                    self.observe(items)
                except RuntimeError as exc:
                    first_error = first_error or exc
                # Only positively attributed IDs with matching current identity/state.
                owned = [item["sandboxID"] for item in items
                         if item.get("sandboxID") in self.ids and
                         item.get("templateID") == self.template_id and item.get("state") == "running"]
                self.evidence["final_live_ids"] = [item.get("sandboxID") for item in items]
                def delete(sid):
                    try:
                        result = api.request("DELETE", f"/sandboxes/{sid}")
                        status = result[1] if isinstance(result, tuple) else None
                        return {"sandbox_id": sid, "http_status": status}, None
                    except Exception as exc:
                        retryable = isinstance(exc, APIError) and exc.status in (404, 408, 429, 503)
                        return {"sandbox_id": sid, "http_status": getattr(exc, "status", None),
                                "error": str(exc)}, None if retryable else exc

                for offset in range(0, len(owned), 20):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("exclusive-template cleanup deadline reached")
                    with ThreadPoolExecutor(max_workers=20) as pool:
                        receipts = list(pool.map(delete, owned[offset:offset + 20]))
                    self.evidence["deletes"].extend(receipt for receipt, _ in receipts)
                    save(self.path, self.evidence)
                    for _, error in receipts:
                        if error:
                            raise error
                if first_error:
                    # No further adoption after contaminated/ambiguous observation.
                    raise first_error
                if not items:
                    stable += 1
                    if stable >= 2:
                        self.evidence["status"] = "drained"
                        return
                else:
                    stable = 0
                time.sleep(2)
            raise RuntimeError("exclusive-template sandboxes did not drain")
        except BaseException as exc:
            self.evidence.update(status="failed", error=str(exc))
            raise
        finally:
            save(self.path, self.evidence)


def check_create_result(output_path, template_id, expected):
    data = json.loads(output_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    if (data["config"]["template"] != template_id or summary["successful"] != expected or
            summary["errors"] != 0 or len(data["raw"]) != expected or
            any(item.get("error") for item in data["raw"])):
        raise RuntimeError(f"native create result incomplete: {output_path.name}")
    return data


def check_reference_create(api, output_path, template_id, measured, live, ledger=None, run_id=None):
    check_create_result(output_path, template_id, measured)
    items = api.sandboxes()
    if ledger:
        ledger.observe(items)
    elif any((item.get("metadata") or {}).get("perf_suite_run") != run_id for item in items):
        raise RuntimeError("create metadata ownership mismatch")
    if len(items) != live or any(item.get("templateID") != template_id or
                               item.get("state") != "running" for item in items):
        raise RuntimeError(f"create live count/template/state mismatch: {len(items)}/{live}")
    return items


def memory_available_kib(host):
    if not host or host.startswith("-") or any(char.isspace() for char in host):
        raise ValueError(f"invalid memory host: {host!r}")
    if host == "local":
        with open("/proc/meminfo", encoding="ascii") as stream:
            content = stream.read()
    else:
        try:
            content = subprocess.check_output(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 host, "cat", "/proc/meminfo"], text=True, timeout=10)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"memory sampling failed on {host}: {type(exc).__name__}") from exc
    for line in content.splitlines():
        if line.startswith("MemAvailable:"):
            value = int(line.split()[1])
            if value > 0:
                return value
    raise RuntimeError(f"MemAvailable unavailable on {host}")


def sample_memory(hosts):
    with ThreadPoolExecutor(max_workers=min(16, len(hosts))) as pool:
        return dict(zip(hosts, pool.map(memory_available_kib, hosts)))


def master_create_limit(config_path, from_k8s):
    import yaml

    if from_k8s:
        try:
            output = subprocess.check_output(
                ["kubectl", "get", "secret", "cube-master-config", "-n", "cube-system", "-o", "json"],
                text=True, stderr=subprocess.PIPE, timeout=10)
            encoded = json.loads(output)["data"]["conf.yaml"]
            content = base64.b64decode(encoded, validate=True)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                KeyError, ValueError) as exc:
            raise RuntimeError(f"cannot read Master config from Kubernetes: {type(exc).__name__}") from exc
    else:
        content = config_path.read_bytes()
    try:
        value = yaml.safe_load(content)["cubelet_conf"]["create_concurrent_limit"]
        if isinstance(value, bool) or int(value) < 1:
            raise ValueError("invalid limit")
        return int(value)
    except (TypeError, ValueError, KeyError, yaml.YAMLError) as exc:
        raise RuntimeError("Master config has no valid cubelet_conf.create_concurrent_limit") from exc


def check_capacity(commands, points, hosts, config_path=None, from_k8s=False,
                   idle_vm_mib=30, idle_memory_factor=1.5, memory_reserve_gib=8):
    node_reserve_kib = math.ceil(memory_reserve_gib * 1024 * 1024)
    creates = [(label, command) for section, label, command in commands if section == "3.2"]
    max_concurrency = max((int(command[command.index("-c") + 1]) for _, command in creates), default=0)
    # create-only warmups also leave live sandboxes until the tagged cleanup.
    peak = max([int(command[command.index("-n") + 1]) + int(command[command.index("-w") + 1])
                for _, command in creates] + points + [0])
    reserve_per_vm_kib = math.ceil(idle_vm_mib * idle_memory_factor * 1024)
    result = {"max_create_concurrency": max_concurrency, "max_live_sandboxes": peak,
              "idle_vm_mib": idle_vm_mib, "idle_memory_factor": idle_memory_factor,
              "reserve_per_vm_kib": reserve_per_vm_kib,
              "memory_reserve_gib": memory_reserve_gib, "node_reserve_kib": node_reserve_kib,
              "warnings": [], "blockers": [], "tier_checks": []}
    if peak:
        available = sample_memory(hosts)
        required = peak * reserve_per_vm_kib + len(hosts) * node_reserve_kib
        result.update(node_available_kib=available, required_kib=required)
        for label, command in creates:
            live = int(command[command.index("-n") + 1]) + int(command[command.index("-w") + 1])
            needed = live * reserve_per_vm_kib + len(hosts) * node_reserve_kib
            sufficient = (sum(available.values()) >= needed and
                          all(value >= node_reserve_kib for value in available.values()))
            result["tier_checks"].append({"label": label, "peak_live": live,
                                          "required_kib": needed, "memory_sufficient": sufficient})
            if not sufficient:
                result["blockers"].append(
                    f"{label} needs >= {needed // 1024 // 1024} GiB across listed Cubelets "
                    f"(including warmups); available {sum(available.values()) // 1024 // 1024} GiB")
        if points and (sum(available.values()) < points[-1] * reserve_per_vm_kib +
                       len(hosts) * node_reserve_kib or
                       any(value < node_reserve_kib for value in available.values())):
            result["blockers"].append(f"density point {points[-1]} exceeds listed Cubelet memory budget")
    if max_concurrency:
        if config_path or from_k8s:
            limit = master_create_limit(config_path, from_k8s)
            result["master_create_baseline"] = limit
            over_limit = [label for label, command in creates
                          if int(command[command.index("-c") + 1]) > limit]
            if over_limit:
                result["warnings"].append(
                    f"{', '.join(over_limit)} exceed Master create baseline {limit}; "
                    "requests may queue; this is not a hard cluster-wide limit")
        else:
            result["warnings"].append(
                "Master create baseline not checked; provide --master-config or --master-config-k8s")
        result["warnings"].append(
            "runtime effective create concurrency and node quota/TAP availability are not exposed by this check")
    return result


def plan(profile, sections, density_points, feature_cases=None, shm_size_mib=None, write_chunk_mib=None):
    if profile == NATIVE_HTTP_PROFILE:
        commands = []
        for spec, c, n, warmups, measured in feature_cases:
            slug = SPEC_TEMPLATE_ENV[spec][0]
            for phase, rounds in (("warm", warmups), ("formal", measured)):
                for round_number in range(1, rounds + 1):
                    label = f"{slug}-c{c}n{n}-{phase}{round_number}"
                    commands.append(("3.2", label, ["cube-bench", "-c", str(c), "-n", str(n),
                                                     "-w", "0", "-m", "create-only"]))
        return commands
    reference = profile == "reference"
    commands = []
    if "3.2" in sections:
        tiers = ([(1, 20), (10, 200), (20, 300), (50, 500),
                  (100, 100), (200, 200), (300, 300)] if reference
                 else [(1, 20), (10, 100), (20, 100)])
        for c, n in tiers:
            commands.append(("3.2", f"c{c}n{n}", ["cube-bench", "-c", str(c), "-n", str(n), "-w", "3", "-m", "create-only"]))
    if "3.3" in sections:
        commands.append(("3.3", "density", []))
    rounds = 5 if reference else 2
    for c in (1, 5, 10):
        if "4.1" in sections:
            commands.append(("4.1", f"c{c}", ["bench_snapshot_concurrency.py", "-c", str(c), "-n", str(rounds)]))
    for mb in ([0, 10, 50, 100, 200, 500, 800, 1024] if reference else [0, 10, 100]):
        if "4.2" in sections:
            command = ["bench_snapshot_dirty.py", "-d", str(mb), "-n", str(3 if reference else 2)]
            if shm_size_mib is not None:
                command += ["--shm-size-mib", str(shm_size_mib)]
            if write_chunk_mib is not None:
                command += ["--write-chunk-mib", str(write_chunk_mib)]
            commands.append(("4.2", f"dirty-{mb}MiB", command))
    for c in ([1, 10, 20, 50] if reference else [1, 10, 20]):
        if "4.3" in sections:
            commands.append(("4.3", f"c{c}", ["bench_create_concurrency.py", "-c", str(c), "-n", str(3 if reference else 2)]))
    for c in (1, 5, 10):
        if "4.4" in sections:
            commands.append(("4.4", f"c{c}", ["bench_rollback_concurrency.py", "-c", str(c), "-n", str(rounds)]))
    for n, c in ([(1, 1), (100, 10), (100, 20), (100, 50)] if reference else [(1, 1), (20, 10)]):
        if "4.5" in sections:
            commands.append(("4.5", f"n{n}c{c}", ["bench_clone_concurrency.py", "-n", str(n), "-c", str(c), "--rounds", str((5 if n == 1 else 2) if reference else 2)]))
    for c in (1, 5, 10):
        if "4.6" in sections:
            commands.append(("4.6", f"c{c}", ["bench_pause_resume_concurrency.py", "-c", str(c), "-n", str(rounds)]))
    return commands


def save(path, report):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_command(command, env, log_path, timeout):
    with log_path.open("x", encoding="utf-8") as stream:
        try:
            result = subprocess.run(command, cwd=SNAP if command[0] == sys.executable else GO,
                                    env=env, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"benchmark timed out; see {log_path}") from exc
    if result.returncode:
        raise RuntimeError(f"benchmark exited {result.returncode}; see {log_path}")


def run_host_gate(path, expected_sha256, label, env, folder, report, timeout):
    if path is None:
        return
    log_path = folder / f"host-gate-{label}.log"
    record = {"label": label, "command": [str(path)], "tool_sha256": expected_sha256,
              "log": log_path.name, "status": "started"}
    report.setdefault("host_gates", []).append(record)
    save(folder / "report.json", report)
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            raise RuntimeError("host gate SHA256 changed")
        with log_path.open("x", encoding="utf-8") as stream:
            result = subprocess.run([str(path)], cwd=ROOT, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError(f"host gate exited {result.returncode}; see {log_path}")
        record["status"] = "passed"
    except BaseException as exc:
        record.update(status="failed", error=str(exc))
        raise RuntimeError(f"host gate {label} failed: {exc}") from exc
    finally:
        save(folder / "report.json", report)


def check_dirty_measurement(log_path):
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines or len(lines[-1].split()) < 2 or float(lines[-1].split()[1]) < 0:
        raise RuntimeError(f"actual dirty bytes not measured; see {log_path}")


def check_native_http_round(api, run_id, output_path, template_id, spec, expected):
    data = json.loads(output_path.read_text(encoding="utf-8"))
    summary = data["summary"]
    if (data["config"]["template"] != template_id or
        summary["successful"] != expected or summary["errors"] or
        len(data["raw"]) != expected or any(item.get("error") for item in data["raw"])):
        raise RuntimeError(f"native HTTP result incomplete: {output_path.name}")
    items = api.sandboxes()
    owned = [item for item in items
             if (item.get("metadata") or {}).get("perf_suite_run") == run_id]
    if len(items) != expected or len(owned) != expected:
        raise RuntimeError(f"native HTTP live count/ownership mismatch: {len(owned)}/{expected}")
    cpu, memory = SPEC_RESOURCES[spec]
    if any(item.get("templateID") != template_id or item.get("cpuCount") != cpu or
           item.get("memoryMB") != memory or item.get("state") != "running"
           for item in owned):
        raise RuntimeError(f"native HTTP template/spec/state mismatch: {output_path.name}")
    return items


def verify_native_binary(path, expected_sha256):
    if not expected_sha256 or len(expected_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in expected_sha256):
        raise ValueError("native HTTP profile requires a lowercase 64-character binary SHA256")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected_sha256:
        raise RuntimeError(f"native cube-bench binary SHA256 changed: {actual}")
    return actual


def guest_preflight(template_id, env):
    from cubesandbox import Config, Sandbox

    config = Config(api_url=env["E2B_API_URL"], api_key=env["E2B_API_KEY"],
                    proxy_node_ip=env["CUBE_PROXY_NODE_IP"],
                    proxy_port=int(env.get("CUBE_PROXY_PORT_HTTP", "80")))
    with Sandbox.create(template=template_id, config=config) as sandbox:
        hello = sandbox.run_code("print('cube-bench-ready')")
        if hello.error or "cube-bench-ready" not in str(hello.logs.stdout):
            raise RuntimeError("guest preflight failed")


def wait_guest_health(items, env, timeout=60):
    address = env["CUBE_PROXY_NODE_IP"]
    port = int(env.get("CUBE_PROXY_PORT_HTTP", "80"))
    domain = env.get("CUBE_SANDBOX_DOMAIN", "cube.app")
    pending = {item["sandboxID"] for item in items}
    deadline = time.monotonic() + timeout

    def ready(sandbox_id):
        request = Request(f"http://{address}:{port}/health",
                          headers={"Host": f"49999-{sandbox_id}.{domain}"})
        try:
            with urlopen(request, timeout=5) as response:
                return response.status == 200
        except (HTTPError, URLError, TimeoutError):
            return False

    while pending and time.monotonic() < deadline:
        ids = list(pending)
        with ThreadPoolExecutor(max_workers=min(20, len(ids))) as pool:
            pending = {sid for sid, healthy in zip(ids, pool.map(ready, ids)) if not healthy}
        if pending:
            time.sleep(2)
    if pending:
        raise RuntimeError(f"{len(pending)} sandbox(es) did not pass guest health within {timeout}s")


def density(api, run_id, points, env, folder, report, timeout, settle_seconds, hosts,
            reserve_per_vm_kib, binary=None, binary_sha256=None, ledger=None, record=None,
            memory_reserve_gib=8):
    node_reserve_kib = math.ceil(memory_reserve_gib * 1024 * 1024)
    baseline, count = sample_memory(hosts), 0
    for point in points:
        while count < point:
            batch = min(20, point - count)
            if any(available - batch * reserve_per_vm_kib < node_reserve_kib
                   for available in sample_memory(hosts).values()):
                raise RuntimeError(f"insufficient memory headroom at {count}/{point}")
            label = f"density-{count + batch}"
            binary = binary or GO / "bin/cube-bench"
            if binary_sha256:
                verify_native_binary(binary, binary_sha256)
            if ledger:
                ledger.limit = count + batch
                ledger.observe(api.sandboxes())
            cmd = [str(binary), "-c", str(batch), "-n", str(batch),
                   "-w", "0", "-m", "create-only", "--no-tui", "-o", str(folder / f"{label}.json")]
            batch_record = {"command": cmd, "status": "started",
                            "tool_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}
            if record is not None:
                record.setdefault("batches", []).append(batch_record)
                save(folder / "report.json", report)
            try:
                run_command(cmd, env, folder / f"{label}.log", timeout)
                owned = check_reference_create(api, folder / f"{label}.json", env["CUBE_TEMPLATE_ID"],
                                               batch, count + batch, ledger, run_id)
                batch_record["status"] = "complete"
            except BaseException as exc:
                batch_record.update(status="failed", error=str(exc))
                raise
            finally:
                if record is not None:
                    save(folder / "report.json", report)
            count += batch
            if any(available < node_reserve_kib
                   for available in sample_memory(hosts).values()):
                raise RuntimeError("memory headroom breached")
        wait_guest_health(owned, env)
        time.sleep(settle_seconds)
        settled_items = api.sandboxes()
        if ledger:
            ledger.observe(settled_items)
        if len(settled_items) != count or {item["sandboxID"] for item in settled_items} != {
                item["sandboxID"] for item in owned}:
            raise RuntimeError("sandbox count changed during density settling")
        available = sample_memory(hosts)
        if any(value < node_reserve_kib for value in available.values()):
            raise RuntimeError("memory headroom breached during density settling")
        report["density"].append({"count": point, "node_available_kib": available,
                                  "available_kib": sum(available.values()),
                                  "per_vm_kib": (sum(baseline.values()) - sum(available.values())) / point,
                                  "settle_seconds": settle_seconds})
        save(folder / "report.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("quick", "reference", NATIVE_HTTP_PROFILE), default="quick")
    parser.add_argument("--feature-file", type=Path,
                        help="exact V1.20 feature file; required for native-http-v120-create")
    parser.add_argument("--native-binary-sha256",
                        help="required for native HTTP execution; pins prebuilt cube-bench across A/B")
    parser.add_argument("--native-binary", type=Path,
                        help="prebuilt unmodified official cube-bench for 3.2/3.3; never rebuilt")
    parser.add_argument("--ownership-mode", choices=("metadata", "exclusive-template"), default="metadata")
    parser.add_argument("--exclusive-template-id",
                        help="explicit assertion this new Template belongs exclusively to this run")
    parser.add_argument("--host-gate", type=Path,
                        help="executable read-only host readiness gate; before guest preflight and each command")
    parser.add_argument("--base-image-digest",
                        help="verified sandbox-code manifest digest used by all Templates")
    parser.add_argument("--gic-profile", choices=("v3", "v4"),
                        help="verified KVM GIC profile for native HTTP A/B")
    parser.add_argument("--sections", default="3.2,4.1,4.2,4.3,4.4,4.5,4.6")
    parser.add_argument("--density-points", default="")
    parser.add_argument("--density-max-instances", type=int, default=1000,
                        help="explicit authorized density ceiling (default: 1000); does not provision capacity")
    parser.add_argument("--memory-reserve-gib", type=float, default=8,
                        help="minimum MemAvailable per Cubelet, including density checks (default: 8 GiB)")
    parser.add_argument("--memory-host", action="append", default=[], metavar="HOST",
                        help="Cubelet host for 3.x capacity checks; repeat for every node, use 'local' for this host")
    parser.add_argument("--idle-vm-mib", type=int, default=30,
                        help="estimated host memory used by one idle 3.x sandbox (default: 30 MiB)")
    parser.add_argument("--idle-memory-factor", type=float, default=1.5,
                        help="safety factor for the idle-memory estimate (default: 1.5)")
    config_source = parser.add_mutually_exclusive_group()
    config_source.add_argument("--master-config", type=Path, help="read Master baseline from this YAML file")
    config_source.add_argument("--master-config-k8s", action="store_true",
                               help="read Master baseline from cube-system/cube-master-config in current kubectl context")
    parser.add_argument("--vmm-log", type=Path, default=Path("/data/log/CubeVmm/vmm.log"))
    parser.add_argument("--shm-size-mib", type=int, default=None,
                        help="4.2 only: explicit grow-only guest /dev/shm tmpfs size; default no remount")
    parser.add_argument("--write-chunk-mib", type=int, default=None,
                        help="4.2 only: explicit dirty-write buffer size; default single allocation/write")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cooldown", type=float, default=5)
    parser.add_argument("--density-settle", type=float, default=15)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--execute", action="store_true", help="opt in to live benchmark operations")
    args = parser.parse_args()
    # Child benchmarks run from their own source directories, not the caller's cwd.
    args.vmm_log = args.vmm_log.resolve()
    if args.output_dir is not None:
        args.output_dir = args.output_dir.resolve()
    if args.native_binary is not None:
        args.native_binary = args.native_binary.resolve()
    if args.host_gate is not None:
        args.host_gate = args.host_gate.resolve()
    sections = [item.strip() for item in args.sections.split(",")]
    try:
        if not sections or len(sections) != len(set(sections)) or set(sections) - set(SECTIONS):
            raise ValueError("invalid or duplicate section ID")
        native_http = args.profile == NATIVE_HTTP_PROFILE
        if args.ownership_mode == "exclusive-template" and (
                not args.native_binary or not args.exclusive_template_id or native_http):
            raise ValueError("exclusive-template requires --native-binary, --exclusive-template-id and quick/reference profile")
        if args.exclusive_template_id and args.ownership_mode != "exclusive-template":
            raise ValueError("--exclusive-template-id requires --ownership-mode exclusive-template")
        if args.native_binary and not native_http and args.ownership_mode != "exclusive-template":
            raise ValueError("unmodified official binary requires explicit exclusive-template ownership")
        binary = args.native_binary or GO / "bin/cube-bench"
        pinned_binary = bool(args.native_binary) or native_http
        if args.native_binary:
            verify_native_binary(binary, args.native_binary_sha256)
        if args.host_gate and (not args.host_gate.is_file() or not os.access(args.host_gate, os.X_OK)):
            raise ValueError("--host-gate must be an existing executable file")
        if native_http and (sections != ["3.2"] or not args.feature_file):
            raise ValueError("native-http-v120-create requires --sections 3.2 and --feature-file")
        feature_cases = feature_create_cases(args.feature_file) if native_http else None
        points = [int(item) for item in args.density_points.split(",")] if args.density_points else []
        if args.density_max_instances < 1:
            raise ValueError("--density-max-instances must be a positive integer")
        if not math.isfinite(args.memory_reserve_gib) or args.memory_reserve_gib <= 0:
            raise ValueError("--memory-reserve-gib must be positive and finite")
        if points and (points != sorted(set(points)) or points[0] < 1 or
                       points[-1] > args.density_max_instances):
            raise ValueError("density points must increase and stay within --density-max-instances")
        if "3.3" in sections and (not args.memory_host or not points or
                                points != sorted(set(points)) or points[0] < 1 or
                                points[-1] > args.density_max_instances):
            raise ValueError("3.3 requires --memory-host for every Cubelet and increasing "
                             f"--density-points <= --density-max-instances ({args.density_max_instances})")
        if len(args.memory_host) != len(set(args.memory_host)):
            raise ValueError("duplicate --memory-host")
        if (args.cooldown < 0 or args.density_settle < 0 or args.timeout < 1 or
                args.idle_vm_mib < 1 or not math.isfinite(args.idle_memory_factor) or
                args.idle_memory_factor < 1):
            raise ValueError("invalid cooldown, timeout, or idle-memory estimate")
        for name in ("shm_size_mib", "write_chunk_mib"):
            value = getattr(args, name)
            if value is not None and (value <= 0 or "4.2" not in sections):
                raise ValueError(f"--{name.replace('_', '-')} must be positive and requires section 4.2")
        max_dirty_mib = 1024 if args.profile == "reference" else 100
        if args.shm_size_mib is not None and args.shm_size_mib < max_dirty_mib:
            raise ValueError(f"--shm-size-mib must cover this profile's largest write ({max_dirty_mib} MiB)")
        commands = plan(args.profile, sections, points, feature_cases, args.shm_size_mib, args.write_chunk_mib)
        if not args.execute:
            for section, label, command in commands:
                print(section, label, " ".join(command) if command else "incremental create-only")
            return 0

        env = os.environ.copy()
        required = (["E2B_API_URL", "E2B_API_KEY", "CUBE_PROXY_NODE_IP"] +
                    [item[1] for item in SPEC_TEMPLATE_ENV.values()] if native_http else
                    ["E2B_API_URL", "E2B_API_KEY", "CUBE_TEMPLATE_ID", "CUBE_PROXY_NODE_IP"])
        if any(not env.get(name) for name in required):
            raise RuntimeError(f"required environment variables: {', '.join(required)}")
        if args.ownership_mode == "exclusive-template" and args.exclusive_template_id != env["CUBE_TEMPLATE_ID"]:
            raise ValueError("--exclusive-template-id must exactly match CUBE_TEMPLATE_ID")
        if native_http:
            if (not args.base_image_digest or not args.base_image_digest.startswith("sha256:") or
                len(args.base_image_digest) != 71 or
                any(char not in "0123456789abcdef" for char in args.base_image_digest[7:]) or
                    not args.gic_profile):
                raise ValueError("native HTTP execution requires --base-image-digest and --gic-profile")
            verify_native_binary(binary, args.native_binary_sha256)
        if "4.2" in sections and not args.vmm_log.is_file():
            raise RuntimeError(f"4.2 requires local VMM log: {args.vmm_log}")
        if ("3.2" in sections or "3.3" in sections) and not args.memory_host:
            raise RuntimeError("3.x execution requires --memory-host for every Cubelet node")
        api = API(env["E2B_API_URL"], env["E2B_API_KEY"])
        if api.sandboxes():
            raise RuntimeError("deployment is not empty; no benchmark was started")
        baseline_snapshots = api.snapshots()
        capacity = check_capacity(commands, points, args.memory_host, args.master_config,
                                  args.master_config_k8s, args.idle_vm_mib,
                                  args.idle_memory_factor, args.memory_reserve_gib)
        if capacity["max_live_sandboxes"]:
            print(f"CAPACITY idle-memory budget: {args.idle_vm_mib} MiB x "
                  f"{args.idle_memory_factor:g} = "
                  f"{capacity['reserve_per_vm_kib'] / 1024:g} MiB/sandbox", file=sys.stderr)
        for tier in capacity["tier_checks"]:
            print(f"CAPACITY {tier['label']}: peak_live={tier['peak_live']}, "
                  f"memory={'OK' if tier['memory_sufficient'] else 'INSUFFICIENT'}", file=sys.stderr)
        for warning in capacity["warnings"]:
            print(f"WARNING: {warning}", file=sys.stderr)
        if capacity["blockers"]:
            raise RuntimeError("; ".join(capacity["blockers"]))
        run_id = uuid.uuid4().hex
        folder = args.output_dir or ROOT / "results" / run_id
        folder.mkdir(parents=True, exist_ok=False)
        report = {"run_id": run_id, "source_revision": "cf571c65e41ca9f43012a1c3914575aef3cd6c21",
                  "profile": args.profile, "sections": sections, "capacity": capacity,
                  "commands": [{"section": section, "label": label, "status": "unexecuted",
                                "planned_command": command}
                               for section, label, command in commands],
                  "density": [], "preflight": "pending", "status": "started"}
        report.update(ownership_mode=args.ownership_mode,
                      density_max_instances=args.density_max_instances,
                      density_points=points,
                      memory_reserve_gib=args.memory_reserve_gib,
                      exclusive_template_id=args.exclusive_template_id,
                      cube_bench_category=("operator-supplied prebuilt official binary; provenance must be externally verified"
                                           if args.native_binary else "suite-local metadata-instrumented cube-bench"),
                      native_binary_path=str(binary), native_binary_sha256=args.native_binary_sha256,
                      runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        if "4.2" in sections:
            report["dirty_workload_preparation"] = {
                "tool_category": "上游测试准备修正版", "shm_size_mib": args.shm_size_mib,
                "write_chunk_mib": args.write_chunk_mib,
                "scope": "owned guest only; untimed preparation; snapshot/restore timers, warmup and statistics unchanged",
                "script_sha256": hashlib.sha256((SNAP / "bench_snapshot_dirty.py").read_bytes()).hexdigest(),
            }
        gate_sha256 = hashlib.sha256(args.host_gate.read_bytes()).hexdigest() if args.host_gate else None
        report["host_gate"] = {"path": str(args.host_gate), "sha256": gate_sha256} if args.host_gate else None
        if native_http:
            report.update(feature_sha256=FEATURE_V120_SHA256,
                          metric_scope="native cube-bench HTTP response; not V1.20 platform readiness",
                          base_image_digest=args.base_image_digest, gic_profile=args.gic_profile,
                          templates={spec: env[var] for spec, (_, var) in SPEC_TEMPLATE_ENV.items()},
                          api_url=env["E2B_API_URL"], proxy_node_ip=env["CUBE_PROXY_NODE_IP"],
                          proxy_port_http=env.get("CUBE_PROXY_PORT_HTTP", "80"),
                          native_binary_sha256=args.native_binary_sha256,
                          runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        save(folder / "report.json", report)
        env.update(CUBE_PERF_RUN_ID=run_id, CUBE_API_URL=env["E2B_API_URL"],
                   CUBE_API_KEY=env["E2B_API_KEY"], VMM_LOG=str(args.vmm_log))
        try:
            run_host_gate(args.host_gate, gate_sha256, "preflight", env, folder, report, args.timeout)
            if native_http:
                for _, template_var in SPEC_TEMPLATE_ENV.values():
                    guest_preflight(env[template_var], env)
            else:
                guest_preflight(env["CUBE_TEMPLATE_ID"], env)
            report["preflight"] = "passed"
            if api.sandboxes():
                raise RuntimeError("guest preflight did not drain")
            if any(section.startswith("3.") for section in sections) and not pinned_binary:
                subprocess.run(["make", "-C", str(GO)], check=True,
                               stdout=subprocess.DEVNULL, timeout=args.timeout)
            for index, (section, label, command) in enumerate(commands):
                record = report["commands"][index]
                ledger = (ExclusiveTemplateLedger(args.exclusive_template_id, folder / f"{label}.delete.json")
                          if args.ownership_mode == "exclusive-template" and section.startswith("3.") else None)
                if section == "3.2" and ledger:
                    ledger.limit = int(command[command.index("-n") + 1]) + int(command[command.index("-w") + 1])
                record["planned_command"] = command
                try:
                    if pinned_binary and section.startswith("3."):
                        verify_native_binary(binary, args.native_binary_sha256)
                    if api.sandboxes() or api.snapshots() != baseline_snapshots:
                        raise RuntimeError("resource baseline drift before next command")
                    run_host_gate(args.host_gate, gate_sha256, f"{section}-{label}",
                                  env, folder, report, args.timeout)
                    if api.sandboxes() or api.snapshots() != baseline_snapshots:
                        raise RuntimeError("resource baseline drift during host gate")
                    record["status"] = "started"
                    save(folder / "report.json", report)
                    primary_error = None
                    try:
                        if section == "3.3":
                            density(api, run_id, points, env, folder, report, args.timeout,
                                    args.density_settle, args.memory_host,
                                    capacity["reserve_per_vm_kib"], binary,
                                    args.native_binary_sha256 if pinned_binary else None, ledger, record,
                                    args.memory_reserve_gib)
                        else:
                            if section == "3.2":
                                command = [str(binary), *command[1:], "--no-tui", "-o", str(folder / f"{label}.json")]
                                if native_http:
                                    spec = native_case_spec(label)
                                    command_env = {**env, "CUBE_TEMPLATE_ID": env[SPEC_TEMPLATE_ENV[spec][1]]}
                                    record["spec"] = spec
                                    record["phase"] = "warm" if "-warm" in label else "formal"
                                else:
                                    command_env = env
                            else:
                                command = [sys.executable, str(SNAP / command[0]), *command[1:]]
                                command_env = env
                            tool_path = binary if section == "3.2" else Path(command[1])
                            record.update(command=command,
                                          tool_sha256=hashlib.sha256(tool_path.read_bytes()).hexdigest())
                            save(folder / "report.json", report)
                            run_command(command, command_env, folder / f"{section}-{label}.log", args.timeout)
                            if native_http:
                                expected = int(command[command.index("-n") + 1])
                                items = check_native_http_round(api, run_id, folder / f"{label}.json",
                                                                command_env["CUBE_TEMPLATE_ID"], spec, expected)
                                wait_guest_health(items, command_env)
                            elif section == "3.2":
                                expected = int(command[command.index("-n") + 1])
                                warmups = int(command[command.index("-w") + 1])
                                check_reference_create(api, folder / f"{label}.json", env["CUBE_TEMPLATE_ID"],
                                                       expected, expected + warmups, ledger, run_id)
                            if section == "4.2":
                                check_dirty_measurement(folder / f"{section}-{label}.log")
                    except BaseException as exc:
                        primary_error = exc
                        record["error"] = str(exc)
                        raise
                    finally:
                        try:
                            if ledger:
                                ledger.drain(api)
                            elif section.startswith("3."):
                                api.drain_tagged(run_id, evidence_path=folder / f"{label}.delete.json")
                            if api.sandboxes() or api.snapshots() != baseline_snapshots:
                                raise RuntimeError(f"{section} {label} left resources; stopped without global cleanup")
                        except BaseException as cleanup_exc:
                            record["cleanup_error"] = str(cleanup_exc)
                            if primary_error is None:
                                raise
                except BaseException as exc:
                    if record["status"] == "started":
                        record["status"] = "failed"
                    else:
                        record["blocked"] = True
                    record.setdefault("error", str(exc))
                    save(folder / "report.json", report)
                    raise
                record["status"] = "complete"
                save(folder / "report.json", report)
                time.sleep(args.cooldown)
            report["status"] = "complete"
        except BaseException as exc:
            report["status"] = "failed"
            if report["preflight"] == "pending":
                report["preflight"] = "failed"
            report["error"] = str(exc)
            raise
        finally:
            save(folder / "report.json", report)
            try:
                (folder / "report.md").write_text(summarize(report, folder), encoding="utf-8")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                if report["status"] != "failed":
                    raise RuntimeError(f"could not write Markdown report: {exc}") from exc
                print(f"WARNING: could not write Markdown report: {exc}", file=sys.stderr)
        print(f"report: {folder / 'report.json'}")
        print(f"summary: {folder / 'report.md'}")
        return 0
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
