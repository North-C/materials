#!/usr/bin/env python3
"""Read-only snapshot of the tunable state on .90 (no secrets). usage: state_snapshot.py OUT.json"""
import glob
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

UNITS = ['cubemaster', 'cubelet', 'cube-api', 'cube-templatecenter', 'cubeops', 'cube-egress', 'cube-proxy',
         'cube-lifecycle-manager', 'coredns', 'minio', 'mysql', 'redis', 'webui']
BINARIES = ['/usr/local/services/cubetoolbox/Cubelet/bin/cubelet', '/usr/local/services/cubetoolbox/CubeAPI/bin/cube-api',
            '/usr/local/services/cubetoolbox/CubeMaster/bin/cubemaster',
            '/usr/local/services/cubetoolbox/CubeTemplateCenter/bin/templatecenter',
            '/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs',
            '/data/cubelet/root/component_versions/cube-shim/v0.7.1/bin/containerd-shim-cube-rs',
            '/usr/local/services/cubetoolbox/cube-shim/bin/cube-runtime',
            '/data/cubelet/root/component_versions/cube-shim/v0.7.1/bin/cube-runtime']
CONFIGS = ['/usr/local/services/cubetoolbox/CubeMaster/conf.yaml', '/usr/local/services/cubetoolbox/Cubelet/config/config.toml']
GO_KEYS = ('GOGC=', 'GOMAXPROCS=', 'GOMEMLIMIT=', 'GODEBUG=')


def sh(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=30).stdout.strip()


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def proc(pid):
    out = {'pid': pid, 'exe_sha256': sha(f'/proc/{pid}/exe')}
    threads = glob.glob(f'/proc/{pid}/task/*/status')
    affs = set()
    for t in threads:
        for line in (read(t) or '').splitlines():
            if line.startswith('Cpus_allowed_list'):
                affs.add(line.split()[1])
    out['threads'] = len(threads)
    out['thread_affinities'] = sorted(affs)
    first = (read(f'/proc/{pid}/numa_maps') or '').splitlines()[:1]
    out['numa_policy_first_map'] = first[0].split()[1] if first else None
    env = (Path(f'/proc/{pid}/environ').read_bytes() if Path(f'/proc/{pid}/environ').exists() else b'').split(b'\0')
    out['go_env'] = sorted(e.decode() for e in env if e.decode(errors='replace').startswith(GO_KEYS))
    return out


snap = {'time': datetime.now(timezone.utc).isoformat(), 'boot_id': read('/proc/sys/kernel/random/boot_id'),
        'loadavg': read('/proc/loadavg'),
        'kernel': {k: read(v) for k, v in {
            'thp_enabled': '/sys/kernel/mm/transparent_hugepage/enabled',
            'thp_defrag': '/sys/kernel/mm/transparent_hugepage/defrag',
            'numa_balancing': '/proc/sys/kernel/numa_balancing',
            'governor_cpu0': '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'}.items()},
        'tuned': sh('tuned-adm', 'active'),
        'binaries': {p: sha(p) for p in BINARIES}, 'configs': {p: sha(p) for p in CONFIGS},
        'tap_count': len([d for d in Path('/sys/class/net').iterdir() if d.name.startswith('z')]) if Path('/sys/class/net').exists() else None,
        'net_dev_count': len(list(Path('/sys/class/net').iterdir())),
        'units': {}, 'containers': {}}
for u in UNITS:
    unit = f'cube-sandbox-{u}.service'
    props = sh('systemctl', 'show', unit, '-p', 'MainPID,ActiveState,SubState,NRestarts,CPUAffinity,NUMAPolicy,NUMAMask,DropInPaths')
    rec = dict(line.split('=', 1) for line in props.splitlines() if '=' in line)
    if rec.get('MainPID', '0') != '0':
        rec['process'] = proc(rec['MainPID'])
    snap['units'][u] = rec
for cid in sh('docker', 'ps', '-q').split():
    info = sh('docker', 'inspect', '-f', '{{.Name}} {{.HostConfig.CpusetCpus}} {{.HostConfig.CpusetMems}} {{.State.Pid}}', cid).split()
    if len(info) == 4:
        snap['containers'][info[0].lstrip('/')] = {'cpuset_cpus': info[1], 'cpuset_mems': info[2], 'pid': info[3]}
Path(sys.argv[1]).write_text(json.dumps(snap, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'go_env': snap['units']['cubemaster'].get('process', {}).get('go_env'),
                  'cubelet_aff': snap['units']['cubelet'].get('process', {}).get('thread_affinities'),
                  'cubelet_policy': snap['units']['cubelet'].get('process', {}).get('numa_policy_first_map'),
                  'kernel': snap['kernel'], 'net_dev_count': snap['net_dev_count']}, ensure_ascii=False))
