#!/usr/bin/env python3
"""Run the one authorized c100n100 case with before/after service identity evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from verify_target import verify


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite-dir", type=Path, required=True)
    parser.add_argument("--benchmark-binary", type=Path, required=True)
    parser.add_argument("--template-id", required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output already exists; inspect the existing attempt")
    before = verify(args.template_id)
    scripts = Path(__file__).resolve().parent
    command = [sys.executable, str(scripts / "capture.py"), "--output", str(args.output),
               "--owned-ids", str(args.output / "ownership-input.json"),
               "--benchmark-binary", str(args.benchmark_binary), "--template-id", args.template_id,
               "--sample-host", "--", sys.executable, str(scripts / "run_single_case.py"),
               "--suite-dir", str(args.suite_dir), "--native-binary-sha256",
               "d7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d", "--execute"]
    code = subprocess.call(command)
    if not args.output.is_dir():
        return code or 2
    save(args.output / "service-identity-before.json", before)
    try:
        after = verify(args.template_id)
        save(args.output / "service-identity-after.json", after)
    except Exception as error:
        save(args.output / "service-identity-after-error.json", {"error_type": type(error).__name__})
        return code or 2
    stable = before["boot_id"] == after["boot_id"] and before["services"] == after["services"]
    save(args.output / "verified-run.json", {"capture_exit_code": code, "stable_service_identity": stable,
                                            "final_sandbox_count": after["sandbox_count"]})
    return code or (0 if stable else 2)


if __name__ == "__main__":
    raise SystemExit(main())
