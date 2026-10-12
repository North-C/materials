#!/usr/bin/env python3
"""Bounded, node-local evidence capture around an explicitly supplied command.

This program never deletes sandboxes, rotates logs, changes services/configuration,
or installs probes. Command arguments/environment are not saved. Child console
output is retained only in a private, capped file and may itself be sensitive.
The command itself remains the operator's responsibility. An independently
verified service identity and approved ownership-aware runner are prerequisites;
checking a client binary does not verify either of those prerequisites.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request


OFFICIAL_SHA256 = "d7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d"
EXPECTED_COMMIT = "31d911e430fdf8a8879bd062b8e78066c1a8e89d"
MIB = 1024 * 1024
ANCHOR_BYTES = 4096
METRICS_URL = "http://127.0.0.1:9998/v1/metrics"
DEFAULT_LOGS = {
    "cubelet_req": "/data/log/Cubelet/Cubelet-req.log",
    "cubelet_stat": "/data/log/Cubelet/Cubelet-stat.log",
    "shim_req": "/data/log/CubeShim/cube-shim-req.log",
    "shim_stat": "/data/log/CubeShim/cube-shim-stat.log",
    "vmm": "/data/log/CubeVmm/vmm.log",
    "master": "/data/log/CubeMaster/cubemaster-req.log",
    "master_stat": "/data/log/CubeMaster/cubemaster-stat.log",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(MIB), b""):
            h.update(block)
    return h.hexdigest()


def private_open(path, mode="wb"):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(fd, mode)


def write_json(path, value):
    with private_open(path, "w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def stat_fields(info):
    return {"device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
            "mtime_ns": info.st_mtime_ns}


def snapshot(path):
    """Read at most the last 4 KiB of pre-existing log data, solely as an anchor."""
    result = {"observed_at": now()}
    if path is None:
        return {**result, "status": "missing"}
    try:
        with Path(path).open("rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return {**result, "status": "not_regular"}
            offset = max(0, info.st_size - ANCHOR_BYTES)
            stream.seek(offset)
            anchor = stream.read(info.st_size - offset)
            result.update(stat_fields(info))
            result.update(status="ok", anchor_offset=offset,
                          anchor_sha256=hashlib.sha256(anchor).hexdigest(),
                          starts_on_line_boundary=not anchor or anchor.endswith(b"\n"))
    except OSError as exc:
        result.update(status="unavailable", error_type=type(exc).__name__, errno=exc.errno)
    return result


def capture_delta(path, before, destination, cap_bytes):
    """Never copy replacement files or fall back to copying entire old histories."""
    result = {"source_path": str(path) if path else None, "before": before,
              "after": None, "delta_path": None, "captured_bytes": 0, "gaps": []}
    if before.get("status") != "ok":
        result.update(after=snapshot(path), status="unavailable")
        result["gaps"].append("no_readable_start_offset")
        return result
    try:
        with Path(path).open("rb") as stream:
            end = os.fstat(stream.fileno())
            result["after"] = {**stat_fields(end), "observed_at": now()}
            if not stat.S_ISREG(end.st_mode):
                result.update(status="not_regular")
                result["gaps"].append("source_not_regular")
                return result
            if (end.st_dev, end.st_ino) != (before["device"], before["inode"]):
                result.update(status="rotated")
                result["gaps"].append("inode_or_device_changed")
                return result
            if end.st_size < before["size"]:
                result.update(status="truncated")
                result["gaps"].append("source_shrank")
                return result
            stream.seek(before["anchor_offset"])
            anchor = stream.read(before["size"] - before["anchor_offset"])
            if hashlib.sha256(anchor).hexdigest() != before["anchor_sha256"]:
                result.update(status="rewritten")
                result["gaps"].append("preexisting_tail_changed_possible_copytruncate")
                return result
            available = end.st_size - before["size"]
            remaining = min(available, cap_bytes)
            result.update(available_bytes=available, omitted_bytes=max(0, available - cap_bytes),
                          read_start=before["size"], read_end=before["size"],
                          starts_on_line_boundary=before["starts_on_line_boundary"])
            stream.seek(before["size"])
            last = b""
            digest = hashlib.sha256()
            with private_open(destination) as output:
                while remaining:
                    block = stream.read(min(remaining, MIB))
                    if not block:
                        result["gaps"].append("source_short_read")
                        break
                    output.write(block)
                    digest.update(block)
                    result["captured_bytes"] += len(block)
                    remaining -= len(block)
                    last = block[-1:]
            result.update(delta_path=str(destination), sha256=digest.hexdigest(),
                          read_end=before["size"] + result["captured_bytes"],
                          ends_on_line_boundary=not last or last == b"\n")
            if available > cap_bytes:
                result["gaps"].append("byte_cap_exceeded")
            if not before["starts_on_line_boundary"]:
                result["gaps"].append("partial_first_line")
            if last and last != b"\n":
                result["gaps"].append("partial_last_line")
            final = os.fstat(stream.fileno())
            current = Path(path).stat()
            if (current.st_dev, current.st_ino) != (end.st_dev, end.st_ino):
                result["gaps"].append("rotation_during_read")
            if final.st_size < end.st_size:
                result["gaps"].append("truncation_during_read")
            # Detect same-inode truncate/rewrite even when it regrew during the read.
            stream.seek(before["anchor_offset"])
            if hashlib.sha256(stream.read(before["size"] - before["anchor_offset"])).hexdigest() != before["anchor_sha256"]:
                result["gaps"].append("anchor_changed_during_read")
            result["status"] = "partial" if result["gaps"] else "captured"
    except OSError as exc:
        result.update(status="unavailable", error_type=type(exc).__name__, errno=exc.errno)
        result["gaps"].append("source_or_destination_io_error")
    return result


def latest_api_log(directory):
    try:
        files = [p for p in Path(directory).glob("cube-api-*.log") if p.is_file()]
        return max(files, key=lambda p: (p.stat().st_mtime_ns, p.name)) if files else None
    except OSError:
        return None


def capture_metrics(destination, cap_bytes=2 * MIB, timeout=3.0):
    result = {"url": METRICS_URL, "observed_at": now(), "captured_bytes": 0, "gaps": []}
    deadline = time.monotonic() + timeout
    try:
        # Ignore proxy environment variables: this is explicitly a loopback request.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(METRICS_URL, timeout=timeout) as response:
            result["http_status"] = response.status
            with private_open(destination) as output:
                while result["captured_bytes"] < cap_bytes:
                    if time.monotonic() >= deadline:
                        result["gaps"].append("metrics_deadline_exceeded")
                        break
                    block = response.read(min(65536, cap_bytes - result["captured_bytes"]))
                    if not block:
                        break
                    output.write(block)
                    result["captured_bytes"] += len(block)
                if result["captured_bytes"] == cap_bytes and response.read(1):
                    result["gaps"].append("metrics_byte_cap_exceeded")
        result.update(path=str(destination), status="partial" if result["gaps"] else "captured")
    except (OSError, urllib.error.URLError, ValueError) as exc:
        result.update(status="unavailable", error_type=type(exc).__name__)
        result["gaps"].append("metrics_request_failed")
        if destination.exists():
            result["path"] = str(destination)
    return result


def ownership_fingerprint(path):
    if path is None:
        return None
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 8 * MIB:
            return {"status": "invalid"}
        return {"status": "ok", **stat_fields(info), "sha256": sha256(path)}
    except FileNotFoundError:
        return None
    except OSError:
        return {"status": "unavailable"}


def load_owned_ids(path, before):
    import re
    empty = {"formal": [], "warmup": [], "unknown_phase": []}
    record = {"source_path": str(path) if path else None, "gaps": [], "status": "missing"}
    after = ownership_fingerprint(path)
    if after is None:
        record["gaps"].append("ownership_missing")
        return empty, record
    if after.get("status") != "ok":
        record.update(status="invalid")
        record["gaps"].append("ownership_source_unreadable_or_too_large")
        return empty, record
    if before is not None and after == before:
        record.update(status="stale")
        record["gaps"].append("ownership_file_not_updated_by_command")
        return empty, record
    try:
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or set(value) != set(empty):
            raise ValueError("schema")
        all_ids = set()
        for phase in empty:
            if not isinstance(value[phase], list):
                raise ValueError("phase")
            for sid in value[phase]:
                if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", sid):
                    raise ValueError("id")
                if sid in all_ids:
                    raise ValueError("duplicate")
                all_ids.add(sid)
        record.update(status="loaded", sha256=after["sha256"], counts={k: len(v) for k, v in value.items()})
        if value["unknown_phase"]:
            record["gaps"].append("ownership_phase_unknown")
        if len(value["formal"]) != 100 or len(value["warmup"]) != 3:
            record["gaps"].append("owned_counts_differ_from_declared_workload")
        return value, record
    except (OSError, ValueError, UnicodeError):
        record.update(status="invalid")
        record["gaps"].append("ownership_schema_invalid_or_duplicate_ids")
        return empty, record


def sample_host(stop, destination, interval, record):
    """No process argv/environ or per-thread stack collection; at most 10k samples."""
    sources = ("loadavg", "meminfo", "stat", "pressure/cpu", "pressure/io", "pressure/memory")
    record.update(samples=0, gaps=[])
    try:
        with private_open(destination, "w") as output:
            while not stop.is_set() and record["samples"] < 10000:
                sample = {"at": now(), "proc": {}}
                for name in sources:
                    try:
                        with (Path("/proc") / name).open() as stream:
                            sample["proc"][name] = stream.read(32768)
                    except OSError:
                        sample["proc"][name] = None
                output.write(json.dumps(sample) + "\n")
                output.flush()
                record["samples"] += 1
                stop.wait(interval)
        if record["samples"] == 10000:
            record["gaps"].append("host_sample_limit_reached")
        record["status"] = "captured"
    except OSError as exc:
        record.update(status="unavailable", error_type=type(exc).__name__)
        record["gaps"].append("host_sampler_io_error")


def run_command(command, output, template_id, binary, owned_path):
    # Never serialize argv/env; a child may itself print sensitive output, hence
    # this file is private and bounded and is never repeated on the console.
    environment = os.environ.copy()
    environment["CUBE_CAPTURE_DIR"] = str(output)
    environment["CUBE_CAPTURE_TEMPLATE_ID"] = template_id
    environment["CUBE_CAPTURE_BENCHMARK_BINARY"] = str(binary)
    if owned_path:
        environment["CUBE_CAPTURE_OWNED_IDS"] = str(owned_path)
    result = {"started_at": now(), "exit_code": None,
              "console": {"path": "evidence/command.log", "cap_bytes": 4 * MIB,
                          "captured_bytes": 0, "omitted_bytes": 0, "gaps": []}}
    process, drain = None, None

    def drain_console(pipe, stream):
        record = result["console"]
        try:
            with pipe, stream:
                while True:
                    block = pipe.read(65536)
                    if not block:
                        break
                    keep = min(len(block), record["cap_bytes"] - record["captured_bytes"])
                    if keep:
                        stream.write(block[:keep])
                    record["captured_bytes"] += keep
                    record["omitted_bytes"] += len(block) - keep
            if record["omitted_bytes"]:
                record["gaps"].append("command_output_cap_exceeded")
        except OSError as exc:
            record["error_type"] = type(exc).__name__
            record["gaps"].append("command_output_io_error")

    try:
        console = private_open(output / "evidence/command.log")
        try:
            process = subprocess.Popen(command, env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            console.close()
            raise
        drain = threading.Thread(target=drain_console, args=(process.stdout, console), daemon=True)
        drain.start()
        result["exit_code"] = process.wait()
    except KeyboardInterrupt:
        result["interrupted"] = True
        if process:
            for sig, wait in ((signal.SIGINT, 5), (signal.SIGTERM, 3), (signal.SIGKILL, 3)):
                if process.poll() is not None:
                    break
                os.killpg(process.pid, sig)
                try:
                    process.wait(timeout=wait)
                except subprocess.TimeoutExpired:
                    continue
            result["exit_code"] = process.returncode
        if result["exit_code"] is None:
            result["exit_code"] = 130
    except OSError as exc:
        result.update(exit_code=127, launch_error_type=type(exc).__name__, errno=exc.errno)
    finally:
        if drain:
            drain.join(timeout=5)
            if drain.is_alive():
                result["console"]["gaps"].append("command_console_eof_not_reached")
    result["ended_at"] = now()
    return result


def run_capture(args):
    if platform.system() != "Linux":
        raise ValueError("requires_linux_target_node")
    binary = args.benchmark_binary.resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError("benchmark_binary_not_executable")
    binary_hash = sha256(binary)
    if binary_hash != OFFICIAL_SHA256:
        raise ValueError("benchmark_binary_sha256_mismatch")
    output = args.output.absolute()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    evidence = output / "evidence"
    evidence.mkdir(mode=0o700)
    owned_path = args.owned_ids.absolute() if args.owned_ids else None
    if owned_path == output / "owned-sandbox-ids.json":
        raise ValueError("owned_source_must_differ_from_normalized_destination")
    owned_before = ownership_fingerprint(owned_path)
    logs = {k: Path(v) for k, v in DEFAULT_LOGS.items()}
    for name, path in args.log:
        logs[name] = Path(path).absolute()
    auto_api = "api" not in logs
    if auto_api:
        logs["api"] = latest_api_log(args.api_log_dir)
    manifest = {
        "schema_version": 1, "status": "preflight" if args.preflight_only else "capturing",
        "concurrency": 100, "requests": 100, "warmup": 3,
        "workload_verification": "declared_contract_not_actual_command_or_results_verification",
        "ownership_mode": "explicit-owned-ids", "template_id": args.template_id,
        "started_at": now(), "ended_at": None, "logs": {}, "metrics": {}, "gaps": [],
        "expected_service_version": "v0.7.1", "expected_service_commit": EXPECTED_COMMIT,
        "service_identity_verified": False,
        "benchmark_binary": {"path": str(binary), "expected_sha256": OFFICIAL_SHA256,
                             "sha256": binary_hash, "verified": True, "actual_invocation_verified": False},
        "command": {"executed": False}, "host_sampling": {"status": "disabled"},
        "limits": {"per_log_bytes": args.log_max_mib * MIB,
                   "metrics_bytes": args.metrics_max_mib * MIB, "metrics_timeout_seconds": args.metrics_timeout},
        "limitations": ["Capture success is not benchmark success or a verified service version.",
                        "The external command must implement safe explicit-ID ownership and cleanup.",
                        "No argv or environment values are persisted; private command.log contains capped child output and may be sensitive.",
                        "Only fixed-path log increments are read; rotation/truncation/caps are evidence gaps.",
                        "Cubelet v0.7.1 suppresses successful trace stages shorter than 5 ms.",
                        "Nested stages must not be added; missing stages are not zero."]}
    before = {name: snapshot(path) for name, path in logs.items()}
    write_json(output / "capture-start.json", {"started_at": manifest["started_at"],
               "logs": {name: {"source_path": str(logs[name]) if logs[name] else None, "before": value}
                        for name, value in before.items()}})
    stop, sampler = threading.Event(), None
    if not args.preflight_only:
        manifest["metrics"]["before"] = capture_metrics(evidence / "metrics-before.prom", args.metrics_max_mib * MIB, args.metrics_timeout)
        if args.sample_host:
            manifest["host_sampling"] = {"path": "evidence/host-samples.jsonl", "interval_seconds": args.sample_interval}
            sampler = threading.Thread(target=sample_host, args=(stop, evidence / "host-samples.jsonl", args.sample_interval, manifest["host_sampling"]), daemon=True)
            sampler.start()
        try:
            manifest["command"] = {"executed": True, **run_command(args.command, output, args.template_id, binary, owned_path)}
        finally:
            stop.set()
            if sampler:
                sampler.join(timeout=5)
                if sampler.is_alive():
                    manifest["gaps"].append("host_sampler_did_not_stop")
            # Includes a bounded tail-flush window before the final log offsets.
            if args.tail_seconds:
                time.sleep(args.tail_seconds)
            manifest["metrics"]["after"] = capture_metrics(evidence / "metrics-after.prom", args.metrics_max_mib * MIB, args.metrics_timeout)
    for name, path in logs.items():
        if args.preflight_only:
            item = {"source_path": str(path) if path else None, "before": before[name],
                    "after": None, "status": "preflight_only", "delta_path": None, "captured_bytes": 0,
                    "gaps": [] if before[name].get("status") == "ok" else ["no_readable_start_offset"]}
        else:
            item = capture_delta(path, before[name], evidence / (name + "-delta.log"), args.log_max_mib * MIB)
            if item.get("delta_path"):
                item["delta_path"] = str(Path(item["delta_path"]).relative_to(output))
        manifest["logs"][name] = item
    if auto_api and latest_api_log(args.api_log_dir) != logs["api"]:
        manifest["logs"]["api"]["gaps"].append("new_latest_api_log_not_captured")
    if args.preflight_only:
        ids = {"formal": [], "warmup": [], "unknown_phase": []}
        ownership = {"status": "preflight_not_loaded", "gaps": []}
    else:
        ids, ownership = load_owned_ids(owned_path, owned_before)
    write_json(output / "owned-sandbox-ids.json", ids)
    manifest["ownership"] = ownership
    for metric in manifest["metrics"].values():
        if metric.get("path"):
            metric["path"] = str(Path(metric["path"]).relative_to(output))
    manifest["ended_at"] = now()
    manifest["status"] = "preflight_only" if args.preflight_only else "captured"
    manifest["gaps"].extend(ownership["gaps"])
    manifest["gaps"].extend(manifest["command"].get("console", {}).get("gaps", []))
    for name, item in manifest["logs"].items():
        manifest["gaps"].extend(name + ":" + gap for gap in item["gaps"])
    for name, item in manifest["metrics"].items():
        manifest["gaps"].extend("metrics_" + name + ":" + gap for gap in item["gaps"])
    write_json(output / "capture-manifest.json", manifest)
    code = manifest["command"].get("exit_code", 0)
    return (128 - code if code < 0 else code), manifest


def parse_log(value):
    name, sep, path = value.partition("=")
    if not sep or name not in set(DEFAULT_LOGS) | {"api"} or not path:
        raise argparse.ArgumentTypeError("expected known_log_name=/absolute/path")
    return name, path


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", required=True, type=Path, help="New private directory; its parent must exist")
    result.add_argument("--owned-ids", type=Path, help="Command-produced JSON with formal/warmup/unknown_phase arrays")
    result.add_argument("--benchmark-binary", required=True, type=Path)
    result.add_argument("--template-id", required=True)
    result.add_argument("--preflight-only", action="store_true", help="Check binary/log offsets only, without HTTP requests or command execution")
    result.add_argument("--log", type=parse_log, action="append", default=[], metavar="NAME=PATH")
    result.add_argument("--api-log-dir", type=Path, default=Path("/data/log/CubeAPI"))
    result.add_argument("--log-max-mib", type=int, default=64)
    result.add_argument("--metrics-max-mib", type=int, default=2)
    result.add_argument("--metrics-timeout", type=float, default=3)
    result.add_argument("--tail-seconds", type=float, default=1, help="Bounded post-command flush window (0–10 seconds)")
    result.add_argument("--sample-host", action="store_true")
    result.add_argument("--sample-interval", type=float, default=1, help="Optional /proc sampling interval, at least one second")
    result.add_argument("command", nargs=argparse.REMAINDER)
    return result


def main():
    cli = parser()
    args = cli.parse_args()
    if args.command[:1] == ["--"]:
        args.command = args.command[1:]
    if not args.preflight_only and not args.command:
        cli.error("Supply an explicit command after --, or use --preflight-only")
    if not 1 <= args.log_max_mib <= 1024 or not 1 <= args.metrics_max_mib <= 16:
        cli.error("Log cap must be 1–1024 MiB; metrics cap 1–16 MiB")
    if not 0 < args.metrics_timeout <= 10 or not 0 <= args.tail_seconds <= 10 or args.sample_interval < 1:
        cli.error("Require metrics timeout (0,10], tail [0,10], sample interval >=1 seconds")
    try:
        code, manifest = run_capture(args)
    except (OSError, ValueError) as exc:
        # Do not echo argv, environment values, or exception strings containing them.
        allowed = {"requires_linux_target_node", "benchmark_binary_not_executable",
                   "benchmark_binary_sha256_mismatch", "owned_source_must_differ_from_normalized_destination"}
        reason = str(exc) if isinstance(exc, ValueError) and str(exc) in allowed else "setup_io_error"
        if isinstance(exc, FileExistsError):
            reason = "output_already_exists"
        print(json.dumps({"status": "capture_setup_failed", "error_type": type(exc).__name__, "reason_code": reason}))
        return 2
    print(json.dumps({"status": manifest["status"], "command_exit_code": manifest["command"].get("exit_code"),
                      "gaps": len(manifest["gaps"]), "manifest": str(args.output.absolute() / "capture-manifest.json")}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
