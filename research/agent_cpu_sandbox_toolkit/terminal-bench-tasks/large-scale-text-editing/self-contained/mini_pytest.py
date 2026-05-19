#!/usr/bin/env python3
import importlib.util
import inspect
import json
import sys
import traceback
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        print("usage: mini_pytest.py /path/to/test_outputs.py", file=sys.stderr)
        return 2

    test_path = Path(sys.argv[1]).resolve()
    spec = importlib.util.spec_from_file_location("tbench_test_outputs", test_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    results = []
    for name, fn in sorted(vars(module).items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        if inspect.signature(fn).parameters:
            results.append({"name": name, "status": "skip", "reason": "requires pytest fixtures"})
            continue
        try:
            fn()
        except Exception as exc:
            results.append({
                "name": name,
                "status": "fail",
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            })
        else:
            results.append({"name": name, "status": "pass"})

    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")
    report = {
        "test_file": str(test_path),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "status": "pass" if failed == 0 and passed > 0 else "fail",
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
