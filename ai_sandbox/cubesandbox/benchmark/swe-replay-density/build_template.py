#!/usr/bin/env python3
# swerebench verified-135 -> AgentEnv / CubeSandbox templates (data-driven)
# Read manifest.csv, filter by language + wall time, derive image/template name, run stages:
#     docker pull -> docker tag(+arch check) -> docker push -> aenv pull
# CubeSandbox: pull -> bake envd -> local smoke -> push -> template job -> READY IDs.
# See CUBESANDBOX.md for image provenance, CubeMaster configuration and examples.
# Generate trajectory-template json, same format as inst463-trajectory-templates.json. No hardcoded image list.
#
# Usage:
#   python3 build_swb_templates.py --list                                # only filter and write json
#   python3 build_swb_templates.py --list --json-out inst463-trajectory-templates.json
#   python3 build_swb_templates.py --dry-run                             # print commands, no execution
#   python3 build_swb_templates.py                                       # run all four stages
#   python3 build_swb_templates.py --langs go,ts,java --max-wall 2100 --jobs 3
#   python3 build_swb_templates.py --phase pull,tag                      # only run selected phases
#   python3 build_swb_templates.py --jobs 1 --verbose                    # stream docker pull/push progress
#   python3 build_swb_templates.py --selftest                            # self test
#   python3 build_swb_templates.py --show-size                           # show image sizes (merged remote & local)
#   python3 build_swb_templates.py --force                               # force pull, tag, push to sync latest images
#   python3 build_swb_templates.py --cleanup                             # delete local registry images for filtered cases
#   python3 build_swb_templates.py --all                                 # FULL BUILD: process ALL cases, ignore langs/max-wall filters
import argparse, csv, json, os, re, subprocess, sys, platform
import shlex
import time
import uuid
from pathlib import Path
from urllib import request, error, parse
from concurrent.futures import ThreadPoolExecutor, as_completed
# Windows console default GBK, force utf8 output
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_DEFAULT = os.path.join(HERE, "swerebench-offline-replays-master",
                                "verified-135", "manifest.csv")
REG_DEFAULT = "127.0.0.1:5000/swerebench"
LANGS_DEFAULT = "go,ts,java"
MAX_WALL_DEFAULT = 2100.0
# Auto-detect architecture by default
ARCH_DEFAULT = None 
AENV_TIMEOUT = 1800
JSON_OUT_DEFAULT = os.path.join(HERE, "trajectory-templates.json")
# arch -> (docker --platform value, image inspect expected "Arch Os")
ARCH_MAP = {"arm64": ("linux/arm64", "arm64 linux"),
            "x86":   ("linux/amd64", "amd64 linux")}
PHASES = ["pull", "tag", "push", "aenv"]
CUBE_PHASES = ["pull", "build", "smoke", "push", "cube"]
ENVD_IMAGE_DEFAULT = "ghcr.io/tencentcloud/cubesandbox-base:2026.16"
CUBE_JSON_DEFAULT = os.path.join(HERE, "trajectory-templates-cubesandbox.json")
def detect_arch():
    """Auto-detect current machine architecture."""
    machine = platform.machine().lower()
    if machine in ('x86_64', 'amd64', 'x64', 'i386', 'i686'):
        return 'x86'
    elif machine in ('aarch64', 'arm64', 'arm'):
        return 'arm64'
    else:
        # Fallback to x86 if unknown, but warn user
        return 'x86'
def tpl_name(task, num):
    """template name: swb-<task>-<num>, replace non [A-Za-z0-9_-] to -, validator.js dot will cause 400"""
    return re.sub(r"[^A-Za-z0-9_-]", "-", f"swb-{task}-{num}")
def parse_row(row, arch):
    col = "image_arm64" if arch == "arm64" else "image_x86"
    remote = row[col].strip()
    path, tag = remote.rsplit(":", 1)
    slug = path.split("/")[-1]
    prefix = f"swerebench-{arch}-"
    task = slug[len(prefix):] if slug.startswith(prefix) else slug
    num = tag.split("-")[0]
    return {
        "instance_id": row["instance_id"],
        "replay_file": row["replay_file"],
        "language": row["language"],
        "wall": float(row["wall_sec_arm" if arch == "arm64" else "wall_sec_x86"]),
        "remote": remote, "task": task, "tag": tag, "num": num,
        "tpl": tpl_name(task, num),
        "workdir": row.get("workdir", "/testbed"),
    }
def load_cases(manifest, langs, max_wall, arch, reg, process_all=False):
    cases = []
    with open(manifest, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not process_all and row["language"] not in langs:
                continue
            try:
                w = float(row["wall_sec_arm" if arch == "arm64" else "wall_sec_x86"])
            except (ValueError, KeyError):
                continue
            if not process_all and w >= max_wall:
                continue
            c = parse_row(row, arch)
            c["local_ref"] = f"{reg}/{c['task']}:{c['tag']}"
            cases.append(c)
    return sorted(cases, key=lambda c: c["instance_id"])
# ---- command runner ----
def run(cmd, dry, label, verbose=False):
    if dry:
        print(f"  $ {shlex.join(cmd)}", file=sys.stderr)
        return 0
    if verbose:
        r = subprocess.run(cmd)
    else:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode
def image_exists(ref):
    return subprocess.run(["docker", "image", "inspect", ref],
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0
def get_image_size(ref, dry=False):
    """Get image size in bytes. Returns None if image doesn't exist or error occurs."""
    if dry:
        return None
    try:
        r = subprocess.run(["docker", "image", "inspect", "--format", "{{.Size}}", ref],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError):
        pass
    return None
def format_size(size_bytes):
    """Format size in bytes to human readable format."""
    if size_bytes is None:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f}TB"
def arch_ok(remote, arch):
    expect = ARCH_MAP[arch][1]
    r = subprocess.run(["docker", "image", "inspect", "--format",
                        "{{.Architecture}} {{.Os}}", remote],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == expect
def aenv_existing_templates():
    """call aenv template list once to get existing template set"""
    try:
        r = subprocess.run(["aenv", "template", "list"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return set()
    if r.returncode != 0:
        return set()
    return set(re.findall(r"swb-\S+", r.stdout))
# ---- per-case phase functions; return 0=ok / 2=skip /1=fail ----
def do_pull(c, dry, arch, verbose=False, force=False):
    if not dry and not force and image_exists(c["remote"]):
        return 2
    plat = ARCH_MAP[arch][0]
    return 0 if run(["docker", "pull", "--platform", plat, c["remote"]],
                    dry, "pull", verbose) == 0 else 1
def do_tag(c, dry, arch, verbose=False, force=False):
    if not force and c["local_pre"]:
        return 2
    if not dry and not arch_ok(c["remote"], arch):
        print(f"  arch mismatch {c['instance_id']}", file=sys.stderr)
        return 1
    return 0 if run(["docker", "tag", c["remote"], c["local_ref"]],
                    dry, "tag", verbose) == 0 else 1
def do_push(c, dry, arch, verbose=False, force=False):
    if not force and c["local_pre"]:
        return 2
    return 0 if run(["docker", "push", c["local_ref"]],
                    dry, "push", verbose) == 0 else 1
def do_aenv(c, dry, arch, existing, verbose=False):
    if c["tpl"] in existing:
        return 2
    return 0 if run(["aenv", "pull", c["local_ref"], "--name", c["tpl"],
                     "--timeout", str(AENV_TIMEOUT)], dry, "aenv", verbose) == 0 else 1

# CubeSandbox: bake envd into OCI layers BEFORE uploading/building a template.
# Contract: https://docs.cubesandbox.com/zh/guide/tutorials/bring-your-own-image
CUBE_DOCKERFILE = """ARG SOURCE_IMAGE
ARG ENVD_IMAGE
FROM ${ENVD_IMAGE} AS cube_envd
FROM ${SOURCE_IMAGE}
USER root
SHELL ["/bin/sh", "-c"]
COPY --from=cube_envd /usr/bin/envd /usr/bin/envd
COPY --from=cube_envd /usr/local/bin/cube-entrypoint.sh /usr/local/bin/cube-entrypoint.sh
# These SWE replay images use Debian/Ubuntu. Fail explicitly for other bases.
RUN command -v apt-get >/dev/null \\
    && apt-get -o Acquire::Retries=0 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update \\
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends bash ca-certificates curl sudo tini passwd \\
    && rm -rf /var/lib/apt/lists/* \\
    && (id user >/dev/null 2>&1 || useradd --create-home --shell /bin/bash user) \\
    && mkdir -p /etc/sudoers.d /var/log \\
    && printf 'user ALL=(ALL) NOPASSWD:ALL\\n' > /etc/sudoers.d/user \\
    && chmod 0440 /etc/sudoers.d/user \\
    && chmod +x /usr/bin/envd /usr/local/bin/cube-entrypoint.sh \\
    && /usr/bin/envd -version
ARG REPLAY_WORKDIR
# bench-core has a shared cwd across templates. Prepare this alias BEFORE
# the first action so callers can use cwd=/testbed for every selected image.
# Never replace an existing directory or a link to another repository.
RUN test -n "$REPLAY_WORKDIR" && test -d "$REPLAY_WORKDIR" \\
    && if [ -e /testbed ] || [ -L /testbed ]; then \\
         test "$(readlink -f /testbed)" = "$(readlink -f "$REPLAY_WORKDIR")"; \\
       else ln -s "$REPLAY_WORKDIR" /testbed; fi
ENV ENVD_PORT=49983 ENVD_BIN=/usr/bin/envd ENVD_EXTRA_ARGS=-isnotfc ENVD_LOG_FILE=/var/log/envd.log
EXPOSE 49983
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/cube-entrypoint.sh"]
# Original interactive bash CMD would exit immediately without a TTY. Replay
# commands arrive through envd; preserve the source filesystem, ENV and WORKDIR.
CMD []
"""

def save_json(data, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

def cube_case_dir(c, args):
    # Instance IDs originate in CSV, so never use them directly as paths.
    return Path(args.build_dir) / args.arch / c["tpl"]

def do_cube_build(c, args):
    context = cube_case_dir(c, args)
    context.mkdir(parents=True, exist_ok=True)
    (context / "Dockerfile").write_text(CUBE_DOCKERFILE, encoding="utf-8")
    (context / ".dockerignore").write_text("*\n!Dockerfile\n", encoding="utf-8")
    if not args.dry_run and not arch_ok(c["remote"], args.arch):
        raise RuntimeError("source image architecture mismatch or image not pulled")
    cmd = ["docker", "build", "--platform", ARCH_MAP[args.arch][0], "--network", args.build_network,
           "--build-arg", "SOURCE_IMAGE=" + c["remote"],
           "--build-arg", "ENVD_IMAGE=" + args.envd_image,
           "--build-arg", "REPLAY_WORKDIR=" + c["workdir"],
           "-t", c["local_ref"]]
    if args.build_proxy:
        # Predefined Docker proxy arguments are not declared in the Dockerfile
        # or persisted as ENV. Pass names only; never log their values.
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"):
            if name in os.environ:
                cmd += ["--build-arg", name]
    cmd.append(str(context))
    # Always invoke Docker's content-aware layer cache; local tag existence
    # does not establish that an image contains the requested envd version.
    return 0 if run(cmd, args.dry_run, "build", args.verbose) == 0 else 1

def do_cube_smoke(c, args):
    """Test this invocation's container only; always remove it, even on failure."""
    cmd = ["docker", "create", "--network", "none", c["local_ref"]]
    if args.dry_run:
        return run(cmd, True, "smoke")
    if not arch_ok(c["local_ref"], args.arch):
        raise RuntimeError("adapted image architecture mismatch or missing")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    cid = result.stdout.strip()
    if not re.fullmatch(r"[a-f0-9]{64}", cid):
        raise RuntimeError("docker create did not return a container ID")
    try:
        # Create separately so even a failing entrypoint/start has a known ID
        # that can be removed in finally.
        subprocess.run(["docker", "start", cid], check=True, capture_output=True, text=True, timeout=30)
        deadline = time.monotonic() + args.smoke_timeout
        while time.monotonic() < deadline:
            health = subprocess.run(
                ["docker", "exec", cid, "curl", "--max-time", "2", "-sS",
                 "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:49983/health"],
                capture_output=True, text=True, timeout=10)
            if health.returncode == 0 and health.stdout == "204":
                # Replay commands run via envd; the source workdir must survive.
                subprocess.run(["docker", "exec", cid, "/bin/bash", "-lc",
                                'set -e; id user; test -d "$1"; '
                                'test "$(readlink -f /testbed)" = "$(readlink -f "$1")"; /usr/bin/envd -version',
                                "smoke", c["workdir"]], check=True, capture_output=True, text=True, timeout=10)
                print(f"  SMOKE {c['instance_id']}: health=204, bash/user/workdir OK", file=sys.stderr)
                return 0
            time.sleep(0.5)
        raise RuntimeError("envd health did not reach HTTP 204 before smoke timeout")
    finally:
        subprocess.run(["docker", "rm", "-f", cid], check=True,
                       stdout=subprocess.DEVNULL, timeout=30)

def cube_request(c, args):
    payload = {
        "source_image_ref": ("http://" if args.registry_http else "") + c["local_ref"],
        "instance_type": "cubebox", "network_type": "tap",
        "writable_layer_size": args.writable_layer_size,
        "exposed_ports": [49983],
        "container_overrides": {
            "resources": {"cpu": f"{args.cpu}m", "mem": f"{args.memory}Mi"},
            "probe": {"probe_handler": {"http_get": {"port": 49983, "path": "/health"}},
                      # Match cubemastercli: omitted failure_threshold means
                      # ONE failed attempt, not retries for the 30s budget.
                      "timeout_ms": 30000, "period_ms": 500,
                      "failure_threshold": 60, "success_threshold": 1},
        },
    }
    if args.cube_node:
        payload["distribution_scope"] = args.cube_node
    return payload

def cube_http(args, method, path, payload=None):
    headers = {"Content-Type": "application/json"}
    key = os.environ.get("CUBE_API_KEY", "")
    if key:
        headers["X-API-Key"] = key
    req = request.Request(args.cube_url.rstrip("/") + path, method=method,
                          data=json.dumps(payload).encode() if payload is not None else None,
                          headers=headers)
    try:
        with request.urlopen(req, timeout=args.http_timeout) as response:
            data = json.load(response)
    except error.HTTPError as exc:
        # Never dump response bodies or authentication headers to logs.
        raise RuntimeError(f"CubeMaster {method} {path}: HTTP {exc.code}") from None
    ret = (data.get("ret") or {}) if isinstance(data, dict) else {}
    if not isinstance(ret, dict) or ret.get("ret_code") != 200:
        ret = ret if isinstance(ret, dict) else {}
        message = str(ret.get("ret_msg", "missing success ret_code=200"))
        if key:
            message = message.replace(key, "<redacted>")
        raise RuntimeError(f"CubeMaster rejected request: {message}")
    return data

def do_cube_template(c, args):
    context = cube_case_dir(c, args)
    payload = cube_request(c, args)
    if not args.dry_run:
        # Submit immutable OCI content, so changing a local tag cannot cause
        # an old READY job to be mistaken for the newly baked image.
        inspected = subprocess.run(["docker", "image", "inspect", "--format",
                                    "{{json .RepoDigests}}", c["local_ref"]],
                                   capture_output=True, text=True, check=True)
        repository = c["local_ref"].rsplit(":", 1)[0]
        digests = [d for d in (json.loads(inspected.stdout) or [])
                   if d.startswith(repository + "@sha256:")]
        if len(digests) != 1:
            raise RuntimeError("expected one registry digest; run push phase first")
        # Docker's containerd image store can populate RepoDigests at local
        # build time. Only a registry lookup proves that the digest is published.
        manifest_cmd = ["docker", "manifest", "inspect"]
        if args.registry_http:
            manifest_cmd.append("--insecure")
        subprocess.run(manifest_cmd + [digests[0]], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, text=True, timeout=args.http_timeout)
        payload["source_image_ref"] = ("http://" if args.registry_http else "") + digests[0]
    save_json(payload, context / "request.json")
    if args.dry_run:
        print(f"  POST {args.cube_url}/cube/template/from-image <- {context / 'request.json'}", file=sys.stderr)
        return 0
    state_path = context / "job.json"
    identity = {"cube_url": args.cube_url.rstrip("/"), "request": payload}
    # Persist submitted IDs before waiting; reruns continue polling the same
    # job and never silently resubmit a timed-out/failed build.
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if any(state.get(k) != v for k, v in identity.items()):
            raise RuntimeError("existing job belongs to another target/request; use a new --build-dir")
        job = cube_http(args, "GET", "/cube/template/from-image?" +
                        parse.urlencode({"job_id": state["job_id"]}))["job"]
    else:
        job = cube_http(args, "POST", "/cube/template/from-image",
                        dict(payload, requestID=str(uuid.uuid4())))["job"]
    deadline = time.monotonic() + args.template_timeout
    while True:
        if not job.get("job_id"):
            raise RuntimeError("CubeMaster returned no job_id")
        state = dict(identity, **{k: job.get(k) for k in
                     ("job_id", "template_id", "status", "phase", "template_status")})
        save_json(state, state_path)
        if job.get("status") == "READY":
            template_id = job.get("template_id", "")
            if not template_id.startswith("tpl-"):
                raise RuntimeError("READY job returned no valid template ID")
            # A historical READY job is insufficient if its template was removed.
            info = cube_http(args, "GET", "/cube/template?" +
                             parse.urlencode({"template_id": template_id}))
            if info.get("status") != "READY":
                raise RuntimeError(f"template {template_id} is not READY")
            c["template_id"] = template_id
            return 0
        if job.get("status") in {"FAILED", "CANCELLED", "CANCELED"}:
            raise RuntimeError(f"template job {job['job_id']} {job['status']} at {job.get('phase')}; inspect job on CubeMaster")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"template wait timed out; job {job['job_id']} remains on server; rerun to poll")
        time.sleep(min(args.poll_interval, max(0, deadline - time.monotonic())))
        job = cube_http(args, "GET", "/cube/template/from-image?" +
                        parse.urlencode({"job_id": job["job_id"]}))["job"]

class Progress:
    """cross-phase overall progress. A case is 'done' when it exits the
    pipeline (fails in a phase) or completes the last phase."""
    def __init__(self, total, verbose=False):
        self.total = total
        self.done = 0
        self.verbose = verbose
        self._lock = __import__("threading").Lock()
    def _render(self):
        msg = f"[overall {self.done}/{self.total}]"
        if not self.verbose:
            sys.stderr.write("\r" + msg)
        else:
            sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    def print_line(self, msg):
        """Thread-safe printing that preserves the progress bar at the bottom."""
        with self._lock:
            if not self.verbose:
                sys.stderr.write("\r")
            sys.stderr.write(msg + "\n")
            if not self.verbose:
                self._render()
            sys.stderr.flush()
    def done_one(self):
        with self._lock:
            self.done += 1
            self._render()
    def finish(self):
        with self._lock:
            if not self.verbose:
                sys.stderr.write("\n")
            sys.stderr.flush()
def run_phase(name, cases, fn, jobs, dry, quiet_skip=False, last=False, progress=None):
    header = f"\n=== {name} ({len(cases)}) ==="
    if progress:
        progress.print_line(header)
    else:
        print(header, file=sys.stderr)
        sys.stderr.flush()
    
    ok, fail = [], []
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(fn, c): c for c in cases}
        for fut in as_completed(futs):
            c = futs[fut]
            try:
                rc = fut.result()
            except Exception as e:
                rc, e = 1, e
                msg = f"  ERR  {c['instance_id']}: {e}"
                if progress: progress.print_line(msg)
                else: print(msg, file=sys.stderr)
            
            if rc == 0:
                ok.append(c)
                msg = f"  OK   {c['tpl']}"
                if progress: progress.print_line(msg)
                else: print(msg, file=sys.stderr)
            elif rc == 2:
                ok.append(c)
                if not quiet_skip:
                    msg = f"  SKIP {c['tpl']}"
                    if progress: progress.print_line(msg)
                    else: print(msg, file=sys.stderr)
            else:
                fail.append(c)
                msg = f"  FAIL {c['instance_id']}"
                if progress: progress.print_line(msg)
                else: print(msg, file=sys.stderr)
            
            if progress is not None and (rc == 1 or last):
                progress.done_one()
    
    summary = f"  => {name}: {len(ok)} ok, {len(fail)} fail"
    if progress:
        progress.print_line(summary)
    else:
        print(summary, file=sys.stderr)
    
    return ok, fail
def write_json(cases, path):
    data = {c["replay_file"]: c["tpl"] for c in
            sorted(cases, key=lambda c: c["replay_file"])}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path
def selftest():
    assert tpl_name("bombsimon-wsl", "108") == "swb-bombsimon-wsl-108"
    assert tpl_name("validatorjs-validator.js", "1306") == \
        "swb-validatorjs-validator-js-1306"
    row = {"instance_id": "bombsimon__wsl-108",
           "image_arm64": "swr.cn-north-4.myhuaweicloud.com/kunpeng-ai/"
                          "swerebench-arm64-bombsimon-wsl:108-bbddf87",
           "image_x86": "x", "replay_file": "bombsimon__wsl-108.replay.json",
           "language": "go", "wall_sec_arm": "1315.6", "wall_sec_x86": "1324.1"}
    c = parse_row(row, "arm64")
    assert c["task"] == "bombsimon-wsl" and c["num"] == "108"
    assert c["tpl"] == "swb-bombsimon-wsl-108"
    print("selftest OK", file=sys.stderr)
def show_image_sizes(cases, arch, dry=False, jobs=1):
    """Show image sizes for filtered cases (merged remote & local for compact view)."""
    print(f"\n=== Image Sizes ({len(cases)} images) ===", file=sys.stderr)
    print(f"{'Instance':<35} {'Lang':<6} {'Remote Size':>12} {'Local Size':>12}", file=sys.stderr)
    print("-" * 70, file=sys.stderr)
    
    total_remote_size = 0
    total_local_size = 0
    remote_count = 0
    local_count = 0
    
    def get_size_info(c):
        remote_size = get_image_size(c["remote"], dry)
        local_size = get_image_size(c["local_ref"], dry) if not dry else None
        return c, remote_size, local_size
    
    if jobs == 1:
        results = [get_size_info(c) for c in cases]
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(lambda c: get_size_info(c), cases))
    
    for c, r_size, l_size in results:
        r_str = format_size(r_size)
        l_str = format_size(l_size)
        
        if r_size is not None:
            total_remote_size += r_size
            remote_count += 1
        if l_size is not None:
            total_local_size += l_size
            local_count += 1
            
        print(f"{c['instance_id']:<35} {c['language']:<6} {r_str:>12} {l_str:>12}", file=sys.stderr)
    
    print("-" * 70, file=sys.stderr)
    print(f"Summary: Remote {remote_count}/{len(cases)} ({format_size(total_remote_size)}) | "
          f"Local {local_count}/{len(cases)} ({format_size(total_local_size)})", file=sys.stderr)
def main():
    ap = argparse.ArgumentParser(description="build swerebench AgentEnv or CubeSandbox templates")
    ap.add_argument("--provider", choices=["aenv", "cubesandbox"], default="aenv")
    ap.add_argument("--manifest", default=MANIFEST_DEFAULT)
    ap.add_argument("--langs", default=LANGS_DEFAULT, help="comma separated, default go,ts,java")
    ap.add_argument("--max-wall", type=float, default=MAX_WALL_DEFAULT, help="max wall seconds")
    ap.add_argument("--arch", default=ARCH_DEFAULT, choices=["arm64", "x86"], 
                    help="Target architecture (default: auto-detect current machine)")
    ap.add_argument("--registry", default=REG_DEFAULT)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--phase", default=None,
                    help="aenv: pull,tag,push,aenv; cubesandbox: pull,build,smoke,push,cube")
    ap.add_argument("--json-out", default=None,
                    help="trajectory->template json output path "
                         "(default: trajectory-templates.json)")
    ap.add_argument("--list", action="store_true", help="list filtered cases, skip docker (only aenv writes a name mapping)")
    ap.add_argument("--show-size", action="store_true", help="show image sizes for filtered cases")
    ap.add_argument("--cleanup", action="store_true", help="delete local registry images for the filtered cases")
    ap.add_argument("--dry-run", action="store_true", help="print commands without running")
    ap.add_argument("--verbose", action="store_true",
                    help="stream subprocess output (docker pull/push progress); requires --jobs 1")
    ap.add_argument("--force", action="store_true",
                    help="force pull, tag, and push even if local images exist, ensuring latest sync")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--images-out", help="write selected upstream image references, one per line")
    ap.add_argument("--instance", action="append", help="limit to this instance_id (repeatable)")
    ap.add_argument("--build-dir", default=os.path.join(HERE, "build", "cubesandbox"))
    ap.add_argument("--envd-image", default=ENVD_IMAGE_DEFAULT, help="envd donor image, preferably pinned by digest")
    ap.add_argument("--build-network", choices=["default", "host", "none"], default="default")
    ap.add_argument("--build-proxy", action="store_true", help="forward HTTP(S)_PROXY/NO_PROXY to Docker build by name")
    ap.add_argument("--cube-url", default=os.environ.get("CUBE_MASTER_URL", ""),
                    help="CubeMaster base URL (not CubeAPI :3000); default $CUBE_MASTER_URL")
    ap.add_argument("--cube-node", action="append", help="Cube node ID/IP for template placement (repeatable)")
    ap.add_argument("--registry-http", action="store_true", help="use http:// image reference in CubeMaster request")
    ap.add_argument("--image-suffix", default="cube-envd-2026.16", help="adapted tag suffix, architecture appended")
    ap.add_argument("--cpu", type=int, default=2000, help="template CPU millicores")
    ap.add_argument("--memory", type=int, default=4096, help="template memory MiB")
    ap.add_argument("--writable-layer-size", default="10G")
    ap.add_argument("--template-timeout", type=float, default=1800, help="job wait budget in seconds; does not cancel server job")
    ap.add_argument("--http-timeout", type=float, default=30)
    ap.add_argument("--poll-interval", type=float, default=2)
    ap.add_argument("--smoke-timeout", type=float, default=30)
    
    # NEW: Add --all flag for full build
    ap.add_argument("--all", action="store_true", 
                    help="FULL BUILD: Process ALL cases in manifest (ignores --langs and --max-wall filters)")
    
    args = ap.parse_args()
    cube = args.provider == "cubesandbox"
    available_phases = CUBE_PHASES if cube else PHASES
    selected_phases = set(args.phase.split(",")) if args.phase is not None else set(available_phases)
    if not selected_phases or selected_phases - set(available_phases):
        ap.error(f"--phase must select from {','.join(available_phases)}")
    phases = [p for p in available_phases if p in selected_phases]
    args.json_out = args.json_out or (CUBE_JSON_DEFAULT if cube else JSON_OUT_DEFAULT)
    for name in ("jobs", "cpu", "memory", "template_timeout", "http_timeout", "poll_interval", "smoke_timeout"):
        if getattr(args, name) <= 0:
            ap.error(f"--{name.replace('_', '-')} must be positive")
    if cube and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", args.image_suffix):
        ap.error("--image-suffix must be a Docker tag component")
    if "://" in args.registry or any(ch.isspace() for ch in args.registry):
        ap.error("--registry must be host[:port]/namespace; use --registry-http for HTTP")
    active_cube = cube and "cube" in phases and not any((args.list, args.cleanup, args.show_size, args.selftest))
    if active_cube:
        url = parse.urlsplit(args.cube_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
            ap.error("--cube-url / CUBE_MASTER_URL must be an explicit http(s) CubeMaster URL without credentials")
        if args.registry == REG_DEFAULT:
            ap.error("Cube template creation requires explicit --registry reachable by CubeMaster")
    if args.verbose and args.jobs != 1:
        print("error: --verbose requires --jobs 1 (parallel progress bars would garble the console)",
              file=sys.stderr)
        return 2
    if args.selftest:
        selftest(); return 0
    # Auto-detect architecture if not explicitly provided
    if args.arch is None:
        args.arch = detect_arch()
        print(f"[Info] Auto-detected architecture: {args.arch}", file=sys.stderr)
    langs = set(args.langs.split(","))
    
    # Pass process_all to load_cases
    cases = load_cases(args.manifest, langs, args.max_wall, args.arch, args.registry, process_all=args.all)
    if args.instance:
        missing = set(args.instance) - {c["instance_id"] for c in cases}
        if missing:
            ap.error(f"instances absent from selected cases: {sorted(missing)}")
        cases = [c for c in cases if c["instance_id"] in args.instance]
    if not cases:
        ap.error("no cases matched")
    if cube:
        for c in cases:
            c["local_ref"] += f"-{args.image_suffix}-{args.arch}"
    
    from collections import Counter
    bd = Counter(c["language"] for c in cases)
    
    filter_desc = "ALL CASES (no filter)" if args.all else f"langs={sorted(langs)} arch={args.arch} wall<{args.max_wall}s"
    print(f"manifest={args.manifest}", file=sys.stderr)
    print(f"filter: {filter_desc} => {len(cases)} cases {dict(bd)}", file=sys.stderr)
    
    if args.all:
        print("[WARNING] Running in FULL BUILD mode. This may consume significant disk space and time.", file=sys.stderr)
    if args.images_out:
        Path(args.images_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.images_out).write_text("".join(c["remote"] + "\n" for c in cases), encoding="utf-8")
        print(f"Images => {args.images_out} ({len(cases)} entries)", file=sys.stderr)
    if not cube:
        jpath = write_json(cases, args.json_out)
        print(f"JSON => {jpath} ({len(cases)} entries)", file=sys.stderr)
    # Handle cleanup early
    if args.cleanup:
        print(f"\n=== Cleaning up {len(cases)} local images ===", file=sys.stderr)
        cleaned = 0
        for c in cases:
            if args.dry_run or image_exists(c["local_ref"]):
                print(f"  Removing {c['local_ref']}", file=sys.stderr)
                run(["docker", "rmi", "-f", c["local_ref"]], dry=args.dry_run, label="cleanup")
                cleaned += 1
            else:
                if not args.dry_run:
                    print(f"  Skipping (not found) {c['local_ref']}", file=sys.stderr)
        print(f"Cleanup done. Removed {cleaned} images.", file=sys.stderr)
        print("Hint: Run 'docker image prune -f' to reclaim disk space from dangling layers.", file=sys.stderr)
        return 0
    if args.show_size:
        show_image_sizes(cases, args.arch, args.dry_run, args.jobs)
        return 0
    if args.list:
        for c in cases:
            print(f"{c['language']:5} {c['wall']:7.1f}  {c['replay_file']:55} "
                  f"{c['tpl']}  {c['remote']}")
        return 0
    # Pre-checks that might output to stderr, done BEFORE progress bar initializes
    for c in cases:
        c["local_pre"] = image_exists(c["local_ref"]) if not args.dry_run and not cube else False
    existing = set() if args.dry_run else (
        aenv_existing_templates() if "aenv" in phases else set())
    
    if "aenv" in phases and not existing and not args.dry_run:
        print("warn: aenv not found or template list empty; new templates will still be attempted", file=sys.stderr)
    progress = Progress(len(cases), args.verbose)
    last_phase = phases[-1] if phases else None
    alive = cases
    failures = []
    for p in phases:
        is_last = (p == last_phase)
        if p == "pull":
            alive, fail = run_phase("pull", alive,
                                   lambda c: do_pull(c, args.dry_run, args.arch, args.verbose, args.force),
                                   args.jobs, args.dry_run, last=is_last, progress=progress)
        elif p == "tag":
            alive, fail = run_phase("tag", alive,
                                   lambda c: do_tag(c, args.dry_run, args.arch, args.verbose, args.force),
                                   args.jobs, args.dry_run, last=is_last, progress=progress)
        elif p == "push":
            alive, fail = run_phase("push", alive,
                                   lambda c: do_push(c, args.dry_run, args.arch, args.verbose, args.force or cube),
                                   args.jobs, args.dry_run, quiet_skip=True,
                                   last=is_last, progress=progress)
        elif p == "aenv":
            alive, fail = run_phase("aenv", alive,
                                   lambda c: do_aenv(c, args.dry_run, args.arch, existing, args.verbose),
                                   args.jobs, args.dry_run, last=is_last, progress=progress)
        elif p in {"build", "smoke", "cube"}:
            operation = {"build": do_cube_build, "smoke": do_cube_smoke, "cube": do_cube_template}[p]
            alive, fail = run_phase(p, alive, lambda c: operation(c, args),
                                   args.jobs, args.dry_run, last=is_last, progress=progress)
        failures.extend(fail)
        if not alive:
            progress.print_line("no surviving cases; stopping later phases")
            break
            
    progress.finish()
    if cube:
        if "cube" in phases and not args.dry_run:
            ready = {c["replay_file"]: c["template_id"] for c in cases if c.get("template_id")}
            save_json(dict(sorted(ready.items())), args.json_out)
            print(f"JSON => {args.json_out} ({len(ready)} READY templates; {len(failures)} failures)", file=sys.stderr)
        else:
            print("No template mapping written: CubeSandbox IDs require successful live template builds.", file=sys.stderr)
        return 1 if failures else 0
    
    if args.force:
        print(f"\n[Hint] To cleanly delete these {len(cases)} templates before retrying, run:", file=sys.stderr)
        print(f"  python3 -c \"import json; print('\n'.join(json.load(open('{args.json_out}')).values()))\" | xargs -I{{}} aenv template delete {{}}", file=sys.stderr)
        
    print(f"\ndone. list templates: aenv template list | grep swb-", file=sys.stderr)
    return 1 if failures else 0
if __name__ == "__main__":
    sys.exit(main())
