#!/usr/bin/env python3
"""Record the SDK sandbox ID list; optionally report differences. Never delete."""
import argparse
import json
import os
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--compare", type=Path)
    a = p.parse_args()
    if a.output.exists():
        p.error("output exists; preserve the previous inventory and choose a new path")
    before = None
    if a.compare:
        values = json.loads(a.compare.read_text())
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            p.error("baseline must be a JSON array of sandbox IDs")
        before = set(values)
    from cubesandbox import Sandbox
    items = Sandbox.list()
    if not isinstance(items, list) or not all(isinstance(x, dict) and isinstance(x.get("sandboxID"), str) for x in items):
        p.error("unexpected SDK list shape; the validated SDK version is 0.7.0")
    ids = {x["sandboxID"] for x in items}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(a.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(sorted(ids), f, indent=2)
        f.write("\n")
    result = {"count": len(ids), "inventory": str(a.output)}
    if before is not None:
        result.update(new_ids_requiring_ownership_check=sorted(ids - before),
                      baseline_ids_no_longer_present=sorted(before - ids))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
