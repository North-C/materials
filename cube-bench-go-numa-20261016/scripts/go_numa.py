#!/usr/bin/env python3
"""Root-only, local-host deployment recipe for the documented cgroup-v1 topology.
No embedded credentials, direct image-pull commands, sandbox deletions or API dependency.
"""
import argparse
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import runtime_snapshot

NATIVE = ['cubemaster', 'cube-templatecenter', 'cube-api', 'cubeops', 'cubelet']
CONTAINERS = {'coredns': 'cube-proxy-coredns', 'cube-egress': 'cube-egress',
              'cube-lifecycle-manager': 'cube-lifecycle-manager', 'cube-proxy': 'cube-proxy',
              'minio': 'cube-sandbox-minio', 'mysql': 'cube-sandbox-mysql',
              'redis': 'cube-sandbox-redis', 'webui': 'cube-webui'}
COMPONENTS = NATIVE + list(CONTAINERS)
GO = {'GOGC': '800', 'GOMAXPROCS': '32', 'GOMEMLIMIT': '8GiB'}
MARKER = '# Owned by materials-go-numa; restore with its private state directory.\n'
DROP = 'zzzz-materials-go-numa.conf'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def run(args, timeout=180):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=timeout).strip()


def unit(component):
    return 'cube-sandbox-' + component + '.service'


def mask(value):
    result = set()
    for token in value.split(','):
        if not token:
            continue
        a, _, b = token.partition('-')
        result.update(range(int(a), int(b or a) + 1))
    return result


def allowed(value):
    cpus = mask(value)
    return bool(cpus) and cpus <= set(range(96, 192))


def proposed(state):
    result = {}
    for component in COMPONENTS:
        data = MARKER + '[Service]\nCPUAffinity=\nCPUAffinity=96-191\nNUMAPolicy=bind\nNUMAMask=\nNUMAMask=1\n'
        if component == 'cubemaster':
            data += ''.join('Environment=' + k + '=' + v + '\n' for k, v in GO.items())
        if component in CONTAINERS:
            data += 'ExecStartPost=/usr/bin/python3 ' + str(state / 'container_cpuset.py') + ' ' + CONTAINERS[component] + '\n'
            data += '[Unit]\nRequiresMountsFor=' + str(state) + '\n'
        result[str(Path('/etc/systemd/system') / (unit(component) + '.d') / DROP)] = data
        # system.control has precedence over ordinary unit drop-ins. Preserve its
        # exact pre-existing bytes and restore only these two files on rollback.
        for key, value in [('AllowedCPUs', '96-191'), ('AllowedMemoryNodes', '1')]:
            result[str(Path('/etc/systemd/system.control') / (unit(component) + '.d') / ('50-' + key + '.conf'))] = MARKER + '[Service]\n' + key + '=' + value + '\n'
    return result


def describe_file(path):
    p = Path(path)
    if p.is_symlink():
        raise RuntimeError('Refusing symlink in managed/backup file: ' + path)
    if not p.exists():
        return {'exists': False}
    st = p.stat()
    return {'exists': True, 'sha256': digest(p.read_bytes()), 'mode': st.st_mode & 0o7777,
            'uid': st.st_uid, 'gid': st.st_gid}


def safe_parent(path):
    for parent in path.parents:
        if parent.is_symlink():
            raise RuntimeError('Refusing symlink parent: ' + str(parent))


def check_host():
    if os.geteuid() != 0:
        raise RuntimeError('Run locally on the target Linux host as root')
    if mask(Path('/sys/devices/system/node/node1/cpulist').read_text().strip()) != set(range(96, 192)):
        raise RuntimeError('Expected node1 CPUs 96-191; review mapping for this host')
    if not Path('/sys/fs/cgroup/cpuset/cpuset.cpus').exists():
        raise RuntimeError('This recipe requires the documented cgroup-v1 cpuset mount')


def snapshot(state):
    # Never overwrite or reuse another snapshot, including a partial snapshot.
    safe_parent(state)
    state.mkdir(mode=0o700, parents=False, exist_ok=False)
    meta = {'schema': 1, 'created_at': now(), 'status': 'snapshot_in_progress',
            'hostname': socket.gethostname(), 'files': {}, 'managed': {}, 'writes_started': []}
    write_json(state / 'state.json', meta)
    desired = proposed(state)
    for path in desired:
        safe_parent(Path(path))
        if Path(path).name == DROP and Path(path).exists():
            raise RuntimeError('A managed drop-in already exists; use its original state for restore: ' + path)
    paths = set(desired)
    units_text = {}
    for component in COMPONENTS:
        name = unit(component)
        props = dict(line.split('=', 1) for line in run(['systemctl', 'show', name, '-p', 'FragmentPath,DropInPaths,ActiveState']).splitlines())
        if props['ActiveState'] != 'active':
            raise RuntimeError('Snapshot requires initially active component: ' + name)
        paths.update(props['DropInPaths'].split())
        paths.add(props['FragmentPath'])
        units_text[name] = run(['systemctl', 'cat', name])
    if '' in paths:
        raise RuntimeError('Missing unit fragment')
    for path in sorted(paths):
        entry = describe_file(path)
        if entry['exists']:
            dest = state / 'backup' / path.lstrip('/')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        meta['files'][path] = entry
    for path, data in desired.items():
        meta['managed'][path] = {'sha256': digest(data.encode()), 'content': data}
    shutil.copy2(Path(__file__).with_name('container_cpuset.py'), state / 'container_cpuset.py')
    meta['helper_sha256'] = digest((state / 'container_cpuset.py').read_bytes())
    runtime = runtime_snapshot.snapshot()
    for name, data in runtime['containers'].items():
        if data['process_errors'] or not data['state']['Running']:
            raise RuntimeError('Container unavailable during snapshot: ' + name)
    write_json(state / 'runtime-before.json', runtime)
    write_json(state / 'units-before.private.json', units_text)
    meta['status'] = 'snapshot_complete'
    meta['snapshot_completed_at'] = now()
    write_json(state / 'state.json', meta)
    plan(state, meta)


def load(state):
    safe_parent(state)
    if state.is_symlink() or state.stat().st_uid != 0 or state.stat().st_mode & 0o077:
        raise RuntimeError('State directory must be root-owned and private (0700)')
    meta = json.loads((state / 'state.json').read_text())
    if meta['hostname'] != socket.gethostname():
        raise RuntimeError('Snapshot belongs to another host')
    return meta


def plan(state, meta):
    diffs = []
    for path, item in meta['managed'].items():
        before = meta['files'][path]
        original = (state / 'backup' / path.lstrip('/')).read_text() if before['exists'] else ''
        diffs.append(''.join(difflib.unified_diff(original.splitlines(True), item['content'].splitlines(True), fromfile=path + ':before', tofile=path + ':after')))
    (state / 'plan.private.diff').write_text(''.join(diffs))
    commands = [['systemctl', 'daemon-reload']]
    commands += [['docker', 'update', '--cpuset-cpus', '96-191', '--cpuset-mems', '1', n] for n in CONTAINERS.values()]
    commands += [['systemctl', 'stop', unit('cube-egress')]]
    commands += [['systemctl', 'restart', unit(c)] for c in NATIVE]
    commands += [['WAIT', 'Cubelet HTTP9998 metrics/bootstrap and TCP9999; max1200s'], ['systemctl', 'start', unit('cube-egress')]]
    commands += [['docker', 'update', '--cpuset-cpus', '96-191', '--cpuset-mems', '1', n] for n in CONTAINERS.values()]
    write_json(state / 'plan.json', {'files': list(meta['managed']), 'commands': commands,
               'note': 'No restart of Proxy/LCM or other container wrappers; verify image identity and actual workload.'})
    return commands


def readiness(state, label, timeout=1200):
    end = time.monotonic() + timeout
    samples = []
    while time.monotonic() < end:
        sample = {'time': now()}
        for key, url in [('metrics', 'http://127.0.0.1:9998/v1/metrics'), ('bootstrap', 'http://127.0.0.1:9998/v1/policies/dump')]:
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    sample[key] = response.status == 200
            except (OSError, ValueError):
                sample[key] = False
        try:
            with socket.create_connection(('127.0.0.1', 9999), timeout=2):
                sample['grpc'] = True
        except OSError:
            sample['grpc'] = False
        samples.append(sample)
        write_json(state / (label + '-readiness.json'), samples)
        if all(sample[k] for k in ['metrics', 'bootstrap', 'grpc']):
            return
        time.sleep(5)
    raise RuntimeError('Cubelet bootstrap not ready after 20 minutes')


def collect_verify(state):
    before = json.loads((state / 'runtime-before.json').read_text())
    checks = []
    evidence = runtime_snapshot.snapshot()
    def check(label, valid):
        checks.append({'check': label, 'ok': bool(valid)})
    for c in COMPONENTS:
        check(c + ' active', evidence['services'][c]['properties']['ActiveState'] == 'active')
    for c in NATIVE:
        p = evidence['services'][c]['process']
        check(c + ' process exists', p is not None)
        if p is None:
            continue
        check(c + ' complete stable threads', p['thread_sample_complete'] and not p['process_errors'])
        check(c + ' every thread CPU subset', all(allowed(t['cpus']) for t in p['thread_samples']))
        check(c + ' main-thread mapping policy bind:1', set(p['numa_policy_map_counts']) == {'bind:1'})
        check(c + ' actual cpuset and ancestors read', p['cpuset']['read_complete'])
        if c == 'cubemaster':
            check('CubeMaster Go environment (not effective GC target)', p['environment'] == GO)
    for name, d in evidence['containers'].items():
        check(name + ' snapshot complete', not d['process_errors'] and bool(d['processes']))
        check(name + ' image unchanged', d['image'] == before['containers'][name]['image'])
        check(name + ' Docker cpuset', d['cpus'] == '96-191' and d['mems'] == '1')
        for p in d['processes']:
            label = name + '/' + str(p['pid'])
            check(label + ' stable threads', p['thread_sample_complete'] and not p['process_errors'])
            check(label + ' every thread CPUs/mems', all(allowed(t['cpus']) and mask(t['mems']) == {1} for t in p['thread_samples']))
            check(label + ' cpuset readable', p['cpuset']['read_complete'])
            ancestors = p['cpuset']['ancestors']
            check(label + ' kernel leaf cpuset', bool(ancestors) and ancestors[0]['files'].get('cpuset.cpus') == '96-191' and ancestors[0]['files'].get('cpuset.mems') == '1')
    write_json(state / 'runtime-verified.json', evidence)
    result = {'time': now(), 'passed': all(c['ok'] for c in checks), 'checks': checks,
              'limits': 'Native main-thread numa_maps only; CPU all threads; no claim of existing page migration or GC target=800.'}
    write_json(state / 'verification.json', result)
    return result['passed']


def verify(state):
    # Process/thread churn may invalidate a point sample; never silently accept it.
    for _ in range(3):
        if collect_verify(state):
            return
        time.sleep(2)
    raise RuntimeError('Runtime verification failed; inspect private verification.json')


def atomic_install(path, data, mode=0o644, uid=0, gid=0):
    p = Path(path)
    safe_parent(p)
    if p.is_symlink():
        raise RuntimeError('Refusing symlink destination: ' + path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_name(p.name + '.materials-tmp')
    # Exclusive creation avoids overwriting another writer's temporary file.
    with temp.open('xb') as stream:
        stream.write(data)
    os.chmod(temp, mode)
    os.chown(temp, uid, gid)
    temp.replace(p)


def restore(state, meta):
    errors = []
    meta['status'] = 'restore_in_progress'
    write_json(state / 'state.json', meta)
    # Continue independent recovery steps even when one fails. No API prerequisite.
    for path in meta['writes_started']:
        try:
            current = describe_file(path)
            original = meta['files'][path]
            if current == original:
                continue
            if current.get('sha256') != meta['managed'][path]['sha256']:
                raise RuntimeError('External edit detected; refusing overwrite: ' + path)
            if original['exists']:
                data = (state / 'backup' / path.lstrip('/')).read_bytes()
                if digest(data) != original['sha256']:
                    raise RuntimeError('Backup checksum mismatch: ' + path)
                atomic_install(path, data, original['mode'], original['uid'], original['gid'])
            else:
                Path(path).unlink()
        except Exception as exc:
            errors.append(str(exc))
    def attempt(fn):
        try:
            fn()
        except Exception as exc:
            errors.append(str(exc))
    attempt(lambda: run(['systemctl', 'daemon-reload']))
    attempt(lambda: run(['systemctl', 'stop', unit('cube-egress')]))
    for c in NATIVE:
        attempt(lambda c=c: run(['systemctl', 'restart', unit(c)]))
    ready = True
    try:
        readiness(state, 'restore')
    except Exception as exc:
        ready = False
        errors.append(str(exc))
    if ready:
        attempt(lambda: run(['systemctl', 'start', unit('cube-egress')]))
    before = json.loads((state / 'runtime-before.json').read_text())
    for name, d in before['containers'].items():
        attempt(lambda name=name, d=d: run(['docker', 'update', '--cpuset-cpus', d['cpus'], '--cpuset-mems', d['mems'], name]))
    for c in COMPONENTS:
        attempt(lambda c=c: run(['systemctl', 'is-active', unit(c)]))
    for name, d in before['containers'].items():
        def check_container(name=name, d=d):
            current = json.loads(run(['docker', 'inspect', name]))[0]
            if not current['State']['Running'] or current['Image'] != d['image'] or current['HostConfig']['CpusetCpus'] != d['cpus'] or current['HostConfig']['CpusetMems'] != d['mems']:
                raise RuntimeError('Restore container verification failed: ' + name)
        attempt(check_container)
    attempt(lambda: write_json(state / 'runtime-restored.json', runtime_snapshot.snapshot()))
    meta['status'] = 'restore_failed' if errors else 'restored_config_and_basic_health'
    meta['restore_finished_at'] = now()
    meta['restore_errors'] = errors
    write_json(state / 'state.json', meta)
    if errors:
        raise RuntimeError('Restore incomplete; inspect state.json; independent recovery attempted')


def apply(state, meta):
    if meta['status'] != 'snapshot_complete':
        raise RuntimeError('Apply requires an unused complete snapshot; current state=' + meta['status'])
    if digest((state / 'container_cpuset.py').read_bytes()) != meta['helper_sha256']:
        raise RuntimeError('Persistent helper changed since snapshot')
    for path, expected in meta['files'].items():
        if describe_file(path) != expected:
            raise RuntimeError('Configuration drift since snapshot: ' + path)
    before = json.loads((state / 'runtime-before.json').read_text())
    for name, data in before['containers'].items():
        current = json.loads(run(['docker', 'inspect', name]))[0]
        if current['Id'] != data['id'] or not current['State']['Running'] or current['HostConfig']['CpusetCpus'] != data['cpus'] or current['HostConfig']['CpusetMems'] != data['mems']:
            raise RuntimeError('Container drift since snapshot: ' + name)
    meta['status'] = 'apply_in_progress'
    write_json(state / 'state.json', meta)
    try:
        for path, item in meta['managed'].items():
            meta['writes_started'].append(path)
            write_json(state / 'state.json', meta)
            atomic_install(path, item['content'].encode())
        run(['systemctl', 'daemon-reload'])
        for name in CONTAINERS.values():
            run(['/usr/bin/python3', str(state / 'container_cpuset.py'), name], timeout=90)
        run(['systemctl', 'stop', unit('cube-egress')])
        for c in NATIVE:
            run(['systemctl', 'restart', unit(c)])
        readiness(state, 'apply')
        run(['systemctl', 'start', unit('cube-egress')])
        for name in CONTAINERS.values():
            run(['/usr/bin/python3', str(state / 'container_cpuset.py'), name], timeout=90)
        verify(state)
        meta['status'] = 'applied_and_runtime_verified'
        meta['applied_at'] = now()
        write_json(state / 'state.json', meta)
    except BaseException as exc:
        meta['apply_error'] = type(exc).__name__ + ': ' + str(exc)
        write_json(state / 'state.json', meta)
        try:
            restore(state, meta)
        except BaseException as recovery_error:
            raise RuntimeError('Apply failed AND recovery incomplete; inspect private state.json') from recovery_error
        raise RuntimeError('Apply failed; original configuration restored with basic health checks') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'plan', 'apply', 'verify', 'restore'])
    parser.add_argument('--state-dir', required=True, help='New absolute private directory on persistent local data disk; parent must exist')
    parser.add_argument('--maintenance-window', action='store_true', help='Operator confirms empty sandbox inventory and exclusive maintenance window')
    args = parser.parse_args()
    # Paths occur in systemd ExecStart/RequiresMountsFor: disallow quoting/specifier ambiguities.
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', args.state_dir) or '..' in Path(args.state_dir).parts:
        parser.error('--state-dir must be an absolute path without spaces, escapes, percent or ..')
    state = Path(args.state_dir)
    if state == Path('/'):
        parser.error('State must be a dedicated new subdirectory')
    os.umask(0o077)
    if args.action == 'restore':
        if os.geteuid() != 0:
            raise RuntimeError('Run locally as root')
    else:
        check_host()
    if args.action == 'snapshot':
        snapshot(state)
    else:
        meta = load(state)
        if args.action == 'plan':
            plan(state, meta)
        elif args.action == 'verify':
            verify(state)
        elif args.action == 'apply':
            if not args.maintenance_window:
                parser.error('apply requires --maintenance-window: operator has confirmed empty inventory/exclusive window')
            apply(state, meta)
        else:
            if meta['status'] not in ['apply_in_progress', 'applied_and_runtime_verified', 'restore_failed', 'restore_in_progress']:
                raise RuntimeError('Nothing eligible to restore from state=' + meta['status'])
            restore(state, meta)
    print(json.dumps({'action': args.action, 'state_dir': str(state), 'completed_at': now()}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), file=sys.stderr)
        sys.exit(1)
