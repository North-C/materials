#!/usr/bin/env python3
"""Adapt the pinned deployed suite to exactly one reference c100n100 case.

Run on the target node as a child of capture.py. The original suite retains its
preflight, capacity checks, exclusive-template ownership and cleanup. No suite
source, service or configuration is changed. Without --execute, only validation
and the suite's dry-run plan are performed.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys


SUITE_SHA256 = "399815f259a072db79415a29496283da089308b95e66ba63494aeeb58ecfdd09"
GATE_SHA256 = "164d9b81f587a27bc9fd93c9ba24006ac298df9ae097e0b9d389746495c738a1"
OFFICIAL_SHA256 = "d7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d"
CASE = ("3.2", "c100n100", ["cube-bench", "-c", "100", "-n", "100", "-w", "3", "-m", "create-only"])
CAPTURE_ENV = ("CUBE_CAPTURE_DIR", "CUBE_CAPTURE_TEMPLATE_ID",
               "CUBE_CAPTURE_BENCHMARK_BINARY", "CUBE_CAPTURE_OWNED_IDS")


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_new(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


def write_json(path, data):
    write_new(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def single_case_plan(original):
    def selected(profile, sections, density_points, feature_cases=None,
                 shm_size_mib=None, write_chunk_mib=None):
        if (profile != "reference" or list(sections) != ["3.2"] or density_points or
                feature_cases is not None or shm_size_mib is not None or write_chunk_mib is not None):
            raise ValueError("adapter_requires_reference_section_3_2_only")
        commands = original(profile, sections, density_points, feature_cases,
                            shm_size_mib, write_chunk_mib)
        matches = [item for item in commands if item[:2] == CASE[:2]]
        if len(matches) != 1 or matches[0] != CASE:
            raise ValueError("pinned_single_case_plan_mismatch")
        return matches
    return selected


def load_suite(path):
    spec = importlib.util.spec_from_file_location("_cube_capture_deployed_suite", path)
    if spec is None or spec.loader is None:
        raise ValueError("suite_import_unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def suite_process_context(suite_dir, environment, argv):
    old_path, old_argv = sys.path[:], sys.argv
    old_environment = os.environ.copy()
    old_bytecode = sys.dont_write_bytecode
    try:
        sys.path.insert(0, str(suite_dir))
        sys.argv = argv
        sys.dont_write_bytecode = True
        os.environ.clear()
        os.environ.update(environment)
        yield
    finally:
        sys.path[:] = old_path
        sys.argv = old_argv
        sys.dont_write_bytecode = old_bytecode
        os.environ.clear()
        os.environ.update(old_environment)


def export_evidence(folder, owned_path, template_id, status):
    """Use the ownership ledger, never raw-row position or a time window."""
    ledger_path = folder / "suite-results/c100n100.delete.json"
    owned = {"formal": [], "warmup": [], "unknown_phase": []}
    record = {"ledger": "suite-results/c100n100.delete.json", "status": "missing",
              "phase_basis": "official raw contains no sandbox IDs; phases are not inferred"}
    errors = []
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text())
            ids = ledger["observed_ids"]
            if (ledger.get("ownership_mode") != "exclusive-template" or
                    ledger.get("template_id") != template_id or not isinstance(ids, list) or
                    any(not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", sid) for sid in ids) or
                    len(ids) != len(set(ids)) or len(ids) > 103):
                raise ValueError("invalid_ownership_ledger")
            owned["unknown_phase"] = ids
            record.update(status="loaded", ledger_status=ledger.get("status"),
                          observed_count=len(ids), sha256=sha256(ledger_path))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            record.update(status="invalid", error_type=type(exc).__name__)
            errors.append("ownership_ledger_invalid")
    try:
        write_json(owned_path, owned)
    except OSError as exc:
        record.update(export_error_type=type(exc).__name__)
        errors.append("ownership_export_failed")
    status["ownership"] = record

    raw = folder / "suite-results/c100n100.json"
    status["raw_result"] = {"status": "missing"}
    if raw.is_file():
        try:
            # Preserve byte-for-byte, including failed/partial results; validity
            # and success remain the original suite's responsibility.
            destination = folder / "startup-latency/c100n100.raw.json"
            destination.parent.mkdir(mode=0o700, exist_ok=True)
            write_new(destination, raw.read_bytes())
            status["raw_result"] = {"status": "copied", "sha256": sha256(destination),
                                    "path": "startup-latency/c100n100.raw.json"}
        except OSError as exc:
            status["raw_result"] = {"status": "copy_failed", "error_type": type(exc).__name__}
            errors.append("raw_result_copy_failed")

    report_path = folder / "suite-results/report.json"
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text())
            commands = report.get("commands", [])
            status["suite_status"] = report.get("status")
            status["suite_preflight"] = report.get("preflight")
            status["case_status"] = commands[0].get("status") if len(commands) == 1 else None
            # A started/failed command alone cannot prove that the binary ran.
            status["benchmark_invocation_recorded"] = (
                len(commands) == 1 and commands[0].get("label") == "c100n100" and
                bool(commands[0].get("command")))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            errors.append("suite_report_unreadable")
            status["report_error_type"] = type(exc).__name__
    return errors


def run(args):
    environment = os.environ.copy()
    if any(not environment.get(key) for key in CAPTURE_ENV):
        raise ValueError("capture_environment_missing")
    folder = Path(environment["CUBE_CAPTURE_DIR"]).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError("capture_directory_missing")
    owned_path = Path(environment["CUBE_CAPTURE_OWNED_IDS"]).absolute()
    status_path = folder / "adapter-status.json"
    reserved = [status_path, folder / "suite-results", owned_path,
                folder / "startup-latency/c100n100.raw.json"]
    if (owned_path == folder / "owned-sandbox-ids.json" or len(set(reserved)) != len(reserved) or
            any(path.exists() or path.is_symlink() for path in reserved)):
        raise ValueError("adapter_output_already_exists_or_conflicts")
    if not owned_path.parent.is_dir():
        raise ValueError("owned_ids_parent_missing")
    status = {"schema_version": 1, "started_at": now(), "status": "validating",
              "execute_requested": args.execute, "suite_main_invoked": False,
              "benchmark_invocation_recorded": False,
              "case": {"section": CASE[0], "label": CASE[1], "command": CASE[2]},
              "adapter_sha256": sha256(Path(__file__)), "sources": {}, "errors": []}
    code = 2
    try:
        if args.native_binary_sha256 != OFFICIAL_SHA256:
            raise ValueError("expected_official_binary_sha256_required")
        suite_dir = args.suite_dir.resolve(strict=True)
        suite_path, gate = suite_dir / "run_suite.py", suite_dir / "host_quiet_gate.py"
        binary = Path(environment["CUBE_CAPTURE_BENCHMARK_BINARY"]).resolve(strict=True)
        for label, path, expected in (("suite", suite_path, SUITE_SHA256),
                                      ("host_gate", gate, GATE_SHA256),
                                      ("native_binary", binary, OFFICIAL_SHA256)):
            actual = sha256(path)
            status["sources"][label] = {"path": str(path), "sha256": actual, "expected_sha256": expected}
            if actual != expected:
                raise ValueError(label + "_sha256_mismatch")
        if not os.access(binary, os.X_OK) or not os.access(gate, os.X_OK):
            raise ValueError("binary_or_host_gate_not_executable")
        template_id = environment["CUBE_CAPTURE_TEMPLATE_ID"]
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", template_id):
            raise ValueError("invalid_template_id")
        environment.update({"CUBE_TEMPLATE_ID": template_id,
                            "E2B_API_URL": "http://127.0.0.1:3000",
                            "E2B_API_KEY": environment.get("E2B_API_KEY") or "capture-noauth-placeholder",
                            "CUBE_PROXY_NODE_IP": "192.168.25.90", "CUBE_PROXY_PORT_HTTP": "18080",
                            "CUBE_PERF_TAP_MIN_READY": "4000", "CUBE_PERF_QUIET_SAMPLES": "5",
                            "CUBE_PERF_GATE_INTERVAL": "5", "CUBE_PERF_GATE_TIMEOUT": "120",
                            "PYTHONDONTWRITEBYTECODE": "1"})
        argv = [str(suite_path), "--profile", "reference", "--sections", "3.2",
                "--native-binary", str(binary), "--native-binary-sha256", args.native_binary_sha256,
                "--ownership-mode", "exclusive-template", "--exclusive-template-id", template_id,
                "--host-gate", str(gate), "--memory-host", "local",
                "--memory-reserve-gib", "64", "--timeout", "600",
                "--output-dir", str(folder / "suite-results")]
        if getattr(args, "master_config", None) is not None:
            argv += ["--master-config", str(args.master_config.resolve())]
        if args.execute:
            argv.append("--execute")
        with suite_process_context(suite_dir, environment, argv):
            suite = load_suite(suite_path)
            original = suite.plan
            suite.plan = single_case_plan(original)
            try:
                # Assert the full selected plan before original main reaches any API.
                suite.plan("reference", ["3.2"], [])
                status["suite_main_invoked"] = True
                code = suite.main()
                if type(code) is not int or not 0 <= code <= 255:
                    raise ValueError("invalid_suite_exit_code")
                status["suite_exit_code"] = code
                status["status"] = ("suite_returned_success" if args.execute else "dry_run") if code == 0 else "suite_failed"
            finally:
                suite.plan = original
    except KeyboardInterrupt:
        code = 130
        status.update(status="interrupted", error_type="KeyboardInterrupt")
    except Exception as exc:
        code = 2
        status.update(status="adapter_failed", error_type=type(exc).__name__)
        # These explicit local validation errors contain no credentials.
        if isinstance(exc, ValueError) and re.fullmatch(r"[a-z0-9_]+", str(exc)):
            status["reason_code"] = str(exc)
    finally:
        if args.execute and status["suite_main_invoked"]:
            errors = export_evidence(folder, owned_path, environment["CUBE_CAPTURE_TEMPLATE_ID"], status)
            status["errors"].extend(errors)
            if errors and code == 0:
                code = 2
                status["status"] = "evidence_export_failed"
            if code == 0 and (status.get("suite_status") != "complete" or
                              status.get("case_status") != "complete" or
                              status.get("raw_result", {}).get("status") != "copied" or
                              status.get("ownership", {}).get("ledger_status") != "drained"):
                code = 2
                status["status"] = "suite_success_evidence_incomplete"
        status.update(ended_at=now(), exit_code=code)
        write_json(status_path, status)
    return code, status


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--suite-dir", required=True, type=Path, help="Existing deployed suite directory; never modified")
    result.add_argument("--native-binary-sha256", required=True, help="Explicit pinned original official benchmark SHA256")
    result.add_argument("--master-config", type=Path, default=None, help="Optional verified Master YAML path passed to the original suite")
    result.add_argument("--execute", action="store_true", help="Opt in to the single live c100n100 case and original suite cleanup")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        code, status = run(args)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "adapter_setup_failed", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps({"status": status["status"], "exit_code": code,
                      "suite_main_invoked": status["suite_main_invoked"],
                      "benchmark_invocation_recorded": status["benchmark_invocation_recorded"]}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
