#!/usr/bin/python3
"""Read-only process, full-thread affinity, NUMA and actual v1 cpuset evidence."""
import json, subprocess, collections, datetime, os
from pathlib import Path

units = ['cubemaster','cubelet','cube-api','cube-templatecenter','cubeops','coredns','cube-egress','cube-lifecycle-manager','cube-proxy','minio','mysql','redis','webui']
names = ['cube-egress','cube-proxy','cube-lifecycle-manager','cube-webui','cube-sandbox-redis','cube-sandbox-mysql','cube-sandbox-minio','cube-proxy-coredns']

def cmd(c):
    return subprocess.check_output(c, text=True, timeout=30).strip()

def cpuset_evidence(cgroup_text):
    result = {'controller': 'cpuset', 'path': None, 'mountpoint': None, 'ancestors': [], 'errors': []}
    paths = [line.split(':', 2)[2] for line in cgroup_text.splitlines()
             if len(line.split(':', 2)) == 3 and 'cpuset' in line.split(':', 2)[1].split(',')]
    if not paths:
        result['errors'].append('no cgroup v1 cpuset entry')
        return result
    result['path'] = paths[0]
    try:
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            before, after = line.split(' - ', 1)
            lhs, rhs = before.split(), after.split()
            if rhs[0] != 'cgroup' or 'cpuset' not in rhs[2].split(','):
                continue
            mountroot, mountpoint = Path(lhs[3]), Path(lhs[4])
            result['mountpoint'] = str(mountpoint)
            result['mount_root'] = str(mountroot)
            current = mountpoint / Path(paths[0]).relative_to(mountroot)
            while True:
                item = {'directory': str(current), 'files': {}, 'errors': []}
                for name in ['cpuset.cpus','cpuset.mems','cpuset.effective_cpus','cpuset.effective_mems',
                             'cpuset.cpus.effective','cpuset.mems.effective','cpuset.memory_migrate']:
                    path = current / name
                    if not path.exists():
                        if name in ['cpuset.cpus', 'cpuset.mems']:
                            item['errors'].append('missing ' + name)
                        continue
                    try:
                        item['files'][name] = path.read_text().strip()
                    except OSError as exc:
                        item['errors'].append(str(exc))
                result['ancestors'].append(item)
                if current == mountpoint:
                    break
                current = current.parent
            break
        if result['mountpoint'] is None:
            result['errors'].append('cpuset mount not found')
    except (OSError, ValueError, IndexError) as exc:
        result['errors'].append(str(exc))
    result['read_complete'] = bool(result['ancestors']) and not result['errors'] and not any(x['errors'] for x in result['ancestors'])
    return result

def proc(pid):
    p = Path('/proc') / str(pid)
    groups, errors, samples = collections.Counter(), [], []
    process_errors = []
    tids = sorted((p / 'task').glob('*'), key=lambda t: int(t.name))
    for t in tids:
        try:
            status = dict(x.split(':',1) for x in (t/'status').read_text().splitlines() if ':' in x)
            cpus, mems = status['Cpus_allowed_list'].strip(), status['Mems_allowed_list'].strip()
            groups[(cpus, mems)] += 1
            samples.append({'tid': int(t.name), 'name': status.get('Name','').strip(), 'cpus': cpus, 'mems': mems})
        except (OSError, KeyError) as exc:
            errors.append(str(t) + ': ' + str(exc))
    pol, pages = collections.Counter(), collections.Counter()
    try:
        for line in (p/'numa_maps').read_text().splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            pol[parts[1]] += 1
            for value in parts:
                if value.startswith('N') and '=' in value:
                    key, number = value.split('=', 1)
                    if key[1:].isdigit() and number.isdigit():
                        pages[key] += int(number)
    except OSError as exc:
        process_errors.append('numa_maps: ' + str(exc))
    env = {}
    try:
        env = {k:v for k,v in (s.split('=',1) for s in (p/'environ').read_text().split('\0') if '=' in s)
               if k in ['GOGC','GOMAXPROCS','GOMEMLIMIT']}
    except OSError as exc:
        process_errors.append('environ: ' + str(exc))
    try:
        cgroup = (p/'cgroup').read_text()
    except OSError as exc:
        cgroup = None
        process_errors.append('cgroup: ' + str(exc))
    try:
        exe = os.readlink(p/'exe')
    except OSError as exc:
        exe = None
        process_errors.append('exe: ' + str(exc))
    tids_after = {int(t.name) for t in (p/'task').glob('*')}
    tids_before = {int(t.name) for t in tids}
    return {'pid': pid, 'threads': [{'cpus': k[0], 'mems': k[1], 'count': v} for k,v in groups.items()],
            'thread_errors': errors, 'thread_samples': samples, 'thread_count': len(samples),
            'nonzero_threads': bool(samples), 'thread_set_changed': tids_after != tids_before,
            'threads_added': sorted(tids_after - tids_before), 'threads_exited': sorted(tids_before - tids_after),
            'thread_sample_complete': bool(samples) and not errors and tids_after == tids_before,
            'numa_policy_map_counts': dict(pol), 'numa_pages': dict(pages), 'numa_sample_tid': pid,
            'numa_scope': 'main-thread maps; page counts aggregate mappings, not unique resident pages',
            'environment': env, 'cgroup': cgroup, 'cpuset': cpuset_evidence(cgroup or ''),
            'exe': exe, 'process_errors': process_errors}

def snapshot():
    result = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'services': {}, 'containers': {}}
    for u in units:
        name = 'cube-sandbox-' + u + '.service'
        props = dict(x.split('=',1) for x in cmd(['systemctl','show',name,'-p','MainPID,ActiveState,SubState,CPUAffinity,AllowedCPUs,AllowedMemoryNodes,NUMAPolicy,NUMAMask,NRestarts']).splitlines())
        pid = int(props['MainPID'])
        result['services'][u] = {'properties': props, 'process': proc(pid) if pid else None}
    for n in names:
        item = {'id': None, 'image': None, 'state': None, 'cpus': None, 'mems': None,
                'processes': [], 'process_errors': []}
        result['containers'][n] = item
        try:
            d = json.loads(cmd(['docker','inspect',n]))[0]
            item.update({'id': d['Id'], 'image': d['Image'], 'state': d['State'],
                         'cpus': d['HostConfig']['CpusetCpus'], 'mems': d['HostConfig']['CpusetMems']})
        except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError) as exc:
            item['process_errors'].append('docker inspect: ' + str(exc))
            continue
        if not d['State'].get('Running'):
            item['process_errors'].append('container not running: ' + d['State'].get('Status', 'unknown'))
            continue
        try:
            pids = [int(x.split()[0]) for x in cmd(['docker','top',n,'-eo','pid']).splitlines()[1:]]
            item['processes'] = [proc(pid) for pid in pids]
            if not pids:
                item['process_errors'].append('docker top returned no processes')
            after = json.loads(cmd(['docker','inspect',n]))[0]
            after_pids = [int(x.split()[0]) for x in cmd(['docker','top',n,'-eo','pid']).splitlines()[1:]]
            if after['Id'] != d['Id'] or set(after_pids) != set(pids):
                item['process_errors'].append('container identity/process set changed during sample')
        except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError) as exc:
            item['process_errors'].append('docker top/process sample: ' + str(exc))
    return result

if __name__ == '__main__':
    print(json.dumps(snapshot(), indent=2))
