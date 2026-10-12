#!/usr/bin/env python3
"""Read-only, credential-free v0.7.1 target identity and template evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

COMMIT = "31d911e430fdf8a8879bd062b8e78066c1a8e89d"
ROOT = Path("/usr/local/services/cubetoolbox")


def get(path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:3000" + path, timeout=30) as response:
        return json.load(response)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify(template_id):
    release = json.loads((ROOT / "release-manifest.json").read_text())
    assert release["git_commit"] == COMMIT, "release commit mismatch"
    services = []
    expected = {"cube-api", "cubemaster", "cubelet", "templatecenter"}
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / "comm").read_text().strip()
            if comm not in expected:
                continue
            exe = os.readlink(proc / "exe")
            actual = digest(proc / "exe")
            component = release["components"][comm]
            fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            services.append({"component": comm, "pid": int(proc.name), "start_ticks": fields[19],
                             "exe": exe, "sha256": actual,
                             "version": component["version"], "commit": component["commit"]})
            assert actual == component["digest_sha256"].removeprefix("sha256:"), comm
            assert component["commit"] == COMMIT, comm
        except (FileNotFoundError, ProcessLookupError):
            continue
    assert len(services) == len(expected) and {s["component"] for s in services} == expected, "service process mismatch"
    shim = ROOT / "cube-shim/bin/containerd-shim-cube-rs"
    shim_digest = digest(shim)
    assert shim_digest == release["components"][shim.name]["digest_sha256"].removeprefix("sha256:"), "shim mismatch"
    items = get("/v2/sandboxes?limit=10000")
    assert isinstance(items, list) and not items, "sandbox baseline not empty"
    template = get("/templates/" + template_id)
    request = template["createRequest"]
    containers = request["containers"]
    assert template["status"] == "READY", "template not ready"
    assert len(containers) == 1, "expected one container"
    assert containers[0]["resources"] == {"cpu": "2000m", "mem": "2048Mi"}, "template resources mismatch"
    assert containers[0]["image"]["writable_layer_size"] == "1G", "writable layer mismatch"
    assert any(r["node_id"] == "192.168.25.90" and r["status"] == "READY" for r in template["replicas"]), "local replica not ready"
    master_config = ROOT / "CubeMaster/conf.yaml"
    limit = re.findall(r"^\s*create_concurrent_limit:\s*(\d+)", master_config.read_text(), re.M)
    assert limit == ["100"], "master concurrency mismatch"
    return {"verified_at": datetime.now(timezone.utc).isoformat(), "read_only": True,
            "release_version": release["release_version"], "commit": COMMIT,
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "kernel": os.uname().release, "services": services,
            "shim": {"path": str(shim), "sha256": shim_digest},
            "sandbox_count": len(items), "master_create_concurrent_limit": 100,
            "template": {"id": template_id, "status": template["status"],
                         "resources": containers[0]["resources"], "writable_layer_size": "1G",
                         "replicas": template["replicas"], "probe": containers[0].get("probe"),
                         "args": containers[0].get("args")},
            "loadavg": Path("/proc/loadavg").read_text().strip()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    assert re.fullmatch(r"[A-Za-z0-9_-]+", args.template_id), "invalid template id"
    result = verify(args.template_id)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"verified": True, "output": str(args.output), "sandbox_count": 0}))
