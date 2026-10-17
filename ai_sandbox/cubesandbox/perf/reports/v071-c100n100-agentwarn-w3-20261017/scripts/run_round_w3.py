#!/usr/bin/env python3
"""Private, prebuilt-only c100n100 -w 3 (in-process warmup) capture with recoverable sandbox cleanup.

Derived from bench-comparison-20261016/cleanup-tools/run_round.py (sha256 f83ee705...).
Changes: invokes capture_w3.py; ownership is the 103-ID unknown_phase inventory set.
"""
import argparse
import concurrent.futures
import ctypes
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


SAFE_CODES = set('prewarmup_must_be_disabled missing_api_key inventory_invalid_response inventory_invalid_ids inventory_unavailable no_safe_cleanup_baseline unexpected_inventory_activity_or_evidence_conflict exclusive_template_required warmup_must_be_three another_round_holds_template_lock recovery_target_mismatch invalid_recovery_process_group capture_process_group_still_exists capture_process_evidence_missing binary_sha256_mismatch initial_inventory_not_empty template_not_ready template_resource_mismatch'.split())
SAFE_CODES.update({'capture_descendants_not_verified_stopped', 'linux_subreaper_required', 'preexisting_child_processes'})


def error_record(error):
    code = str(error)
    return {'error_type': type(error).__name__, 'code': code if code in SAFE_CODES else 'operation_failed'}


class API:
    def __init__(self, config):
        self.url = config['api_url'].rstrip('/')
        self.key = os.environ.get('E2B_API_KEY') or config.get('api_key', '')
        if not self.key:
            raise ValueError('missing_api_key')

    def call(self, path, method='GET'):
        request = urllib.request.Request(self.url + path, method=method,
                                         headers={'Authorization': 'Bearer ' + self.key})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = response.read()
                return response.status, json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            return error.code, None


def inventory(api, attempts=3, pause=time.sleep):
    for attempt in range(attempts):
        try:
            status, rows = api.call('/sandboxes')
            if status != 200 or not isinstance(rows, list):
                raise ValueError('inventory_invalid_response')
            ids = [row.get('sandboxID') for row in rows if isinstance(row, dict)]
            if len(ids) != len(rows) or any(not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', sid) for sid in ids) or len(set(ids)) != len(ids):
                raise ValueError('inventory_invalid_ids')
            return rows
        except Exception:
            if attempt + 1 == attempts:
                raise RuntimeError('inventory_unavailable') from None
            pause(1)


def read_cli_evidence(output, template):
    """Malformed/missing reports do not prevent cleanup under established exclusivity."""
    result = {'warmup_ids': [], 'unknown_phase_ids': [], 'formal_ids': [], 'warnings': [], 'conflict': False}
    runs = list((Path(output) / 'runs').glob('*'))
    if len(runs) != 1:
        result['warnings'].append('run_directory_count_' + str(len(runs)))
        return result
    for filename, phase in [('capture/evidence/cubemastercli/before.json', 'warmup'),
                            ('capture/owned-sandbox-ids.json', 'unknown_phase')]:
        try:
            value = json.loads((runs[0] / filename).read_text())
            if phase == 'warmup':
                if value.get('status') != 'ok' or value.get('errors'):
                    raise ValueError('invalid_cli_inventory')
                ids = [row['sandbox_id'] for row in value['rows'] if row.get('template_id') == template]
            else:
                ids = value['unknown_phase'] + value['formal'] + value['warmup']
            if not isinstance(ids, list) or any(not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', sid) for sid in ids) or len(ids) != len(set(ids)):
                raise ValueError('invalid_evidence_ids')
            result[phase + '_ids'] = sorted(ids)
        except Exception:
            result['warnings'].append(phase + '_evidence_missing_or_invalid')
    # -w 3 runs inside cube-bench: the pre-run CLI inventory must hold no template instance.
    warm, owned = set(result['warmup_ids']), set(result['unknown_phase_ids'])
    result['conflict'] = bool(warm) or len(owned) > 103
    return result


def cleanup(api, context, output, attempts=3, pause=time.sleep):
    receipt = {'started_at': now(), 'status': 'incomplete', 'outcomes': [], 'errors': [],
               'ownership_basis': 'empty_initial_inventory_and_operator_declared_template_exclusivity',
               'remaining_owned_ids': None}
    try:
        if context.get('baseline') != [] or context.get('exclusive_template') is not True:
            raise ValueError('no_safe_cleanup_baseline')
        if context.get('capture_started') and context.get('capture_processes_stopped') is not True:
            raise ValueError('capture_descendants_not_verified_stopped')
        template = context['template_id']
        rows = inventory(api, pause=pause)
        save(Path(output) / 'evidence/pre-cleanup-inventory.json', rows)
        if context.get('capture_started') is not True:
            receipt['status'] = 'complete' if not rows else 'refused_ambiguous_ownership'
            receipt['capture_not_started'] = True
            receipt['remaining_owned_ids'] = []
            receipt['unexpected_remaining_ids'] = [row['sandboxID'] for row in rows]
            return receipt
        candidates = {row['sandboxID'] for row in rows if row.get('templateID') == template}
        evidence = read_cli_evidence(output, template)
        receipt['cli_evidence'] = evidence
        receipt['candidate_ids'] = sorted(candidates)
        # API inventories are authoritative for existence; known CLI IDs may already
        # have expired, but an ID now belonging to another template is a conflict.
        known = set(evidence['warmup_ids'] + evidence['unknown_phase_ids'])
        foreign = {row['sandboxID'] for row in rows if row.get('templateID') != template}
        if foreign or len(candidates | known) > 103 or evidence['conflict'] or known & foreign:
            receipt['status'] = 'refused_ambiguous_ownership'
            raise ValueError('unexpected_inventory_activity_or_evidence_conflict')
        targets = candidates | known

        def delete(sid):
            outcome = {'id': sid, 'attempts': [], 'confirmed_absent': False}
            for attempt in range(attempts):
                try:
                    status, _ = api.call('/sandboxes/' + sid, 'DELETE')
                    outcome['attempts'].append({'status': status})
                    if status == 204:
                        outcome['confirmed_absent'] = True
                        break
                    # A 404 alone is not proof: cross-check the full inventory.
                    if sid not in {r['sandboxID'] for r in inventory(api, pause=pause)}:
                        outcome['confirmed_absent'] = True
                        break
                except Exception as error:
                    outcome['attempts'].append({'error_type': type(error).__name__})
                if attempt + 1 < attempts:
                    pause(1)
            return outcome

        # Persist each completed deletion, even if a later request fails.
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for outcome in pool.map(delete, sorted(targets)):
                receipt['outcomes'].append(outcome)
                save(Path(output) / 'evidence/cleanup.json', receipt)
        final_rows = []
        consecutive_empty = 0
        for attempt in range(attempts + 1):
            final_rows = inventory(api, pause=pause)
            remaining = {row['sandboxID'] for row in final_rows}
            receipt['remaining_owned_ids'] = sorted(targets & remaining)
            # Any new instance appearing during cleanup is an unsafe non-quiescent
            # environment. Do not chase it with another deletion wave.
            receipt['unexpected_remaining_ids'] = sorted(remaining - targets)
            consecutive_empty = consecutive_empty + 1 if not remaining else 0
            if consecutive_empty >= 2:
                break
            if attempt + 1 < attempts + 1:
                pause(1)
        save(Path(output) / 'evidence/post-cleanup-inventory.json', final_rows)
        for outcome in receipt['outcomes']:
            if outcome['id'] not in {r['sandboxID'] for r in final_rows}:
                outcome['confirmed_absent'] = True
        if consecutive_empty >= 2 and all(row['confirmed_absent'] for row in receipt['outcomes']):
            receipt['status'] = 'complete'
    except BaseException as error:
        receipt['errors'].append(error_record(error))
    finally:
        receipt['ended_at'] = now()
        save(Path(output) / 'evidence/cleanup.json', receipt)
    return receipt


def host_snapshot():
    result = {'time': now(), 'settings': {}, 'services': {}}
    for name in ['/proc/loadavg', '/proc/meminfo', '/proc/mounts',
                 '/sys/kernel/mm/transparent_hugepage/enabled',
                 '/sys/kernel/mm/transparent_hugepage/defrag', '/proc/sys/kernel/numa_balancing']:
        try:
            value = Path(name).read_text().strip()
            if name.endswith('meminfo'):
                value = '\n'.join(line for line in value.splitlines() if 'Huge' in line)
            if name.endswith('mounts'):
                value = '\n'.join(line for line in value.splitlines() if 'hugetlbfs' in line)
            result['settings'][name] = value
        except OSError:
            result['settings'][name] = None
    for unit in ['cube-sandbox-cubelet.service', 'cube-sandbox-cubemaster.service', 'cube-sandbox-cube-api.service']:
        try:
            pid = subprocess.check_output(['systemctl', 'show', unit, '--property=MainPID', '--value'],
                                          text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
            result['services'][unit] = {'pid': pid, 'sha256': digest('/proc/' + pid + '/exe')}
        except Exception as error:
            result['services'][unit] = {'error_type': type(error).__name__}
    return result


def proc_identity(pid):
    try:
        fields = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': fields[19], 'state': fields[0]}
    except FileNotFoundError:
        return None


def descendants(root_pid):
    processes = {}
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            value = proc_identity(int(path.name))
            if value:
                processes[value['pid']] = value
    owned, frontier = {}, {root_pid}
    while frontier:
        children = {pid: value for pid, value in processes.items() if value['ppid'] in frontier and pid not in owned}
        owned.update(children)
        frontier = set(children)
    return owned


def set_subreaper(enabled):
    if sys.platform != 'linux':
        raise ValueError('linux_subreaper_required')
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if libc.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0 or libc.prctl(36, int(enabled), 0, 0, 0) != 0:
        raise ValueError('linux_subreaper_required')
    return bool(previous.value)


def stop_descendants(root_pid, timeout=10):
    """Subreaper adoption retains ownership across setsid/double-fork/parent exit."""
    tracked, errors = {}, []
    deadline = time.monotonic() + timeout
    try:
        # Stop discovered parents/children; repeated snapshots catch any child
        # forked between enumeration and SIGSTOP. No argv/env matching is used.
        stable = 0
        while time.monotonic() < deadline and stable < 2:
            current = descendants(root_pid)
            new = set(current) - set(tracked)
            stable = 0 if new else stable + 1
            tracked.update(current)
            for pid, expected in current.items():
                identity = proc_identity(pid)
                if identity and identity['start_ticks'] == expected['start_ticks'] and identity['state'] not in ('Z', 'X'):
                    try:
                        os.kill(pid, signal.SIGSTOP)
                    except ProcessLookupError:
                        pass
            time.sleep(0.02)
        for pid, expected in tracked.items():
            identity = proc_identity(pid)
            if identity and identity['start_ticks'] == expected['start_ticks']:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        while time.monotonic() < deadline:
            # Reap adopted children too; the leader may already have been reaped
            # by Popen.wait(). All children were absent before launch.
            while True:
                try:
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                    if pid == 0:
                        break
                except ChildProcessError:
                    break
            current = descendants(root_pid)
            if not current:
                return {'stopped': True, 'tracked': list(tracked.values()), 'remaining': [], 'errors': errors}
            # Reparenting may reveal another generation after its parent dies.
            for pid, expected in current.items():
                tracked[pid] = expected
                identity = proc_identity(pid)
                if identity and identity['start_ticks'] == expected['start_ticks']:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            time.sleep(0.05)
    except Exception as error:
        errors.append(error_record(error))
    return {'stopped': False, 'tracked': list(tracked.values()), 'errors': errors}


def run_capture(command, output, secret, timeout, on_started=None):
    """Stop all descendants, including separate sessions, before cleanup."""
    previous_subreaper = set_subreaper(True)
    if descendants(os.getpid()):
        set_subreaper(previous_subreaper)
        raise ValueError('preexisting_child_processes')
    process = None
    stopped = True
    started = now()
    old_handlers = {}
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    for sig in (signal.SIGINT, signal.SIGTERM):
        old_handlers[sig] = signal.signal(sig, interrupted)
    # Private temporary stdout is never published; only redacted text is retained.
    try:
        with tempfile.TemporaryFile() as stream:
            try:
                process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                process_record = {'pid': process.pid, 'process_group': process.pid,
                                  'started_at': now(), 'stopped': False}
                try:
                    process_record['linux_start_ticks'] = Path('/proc/' + str(process.pid) + '/stat').read_text().rsplit(')', 1)[1].split()[19]
                    process_record['boot_id'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
                except OSError:
                    process_record['start_identity_unavailable'] = True
                save(Path(output) / 'evidence/capture-process.json', process_record)
                if on_started:
                    on_started()
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                code = 124
            except KeyboardInterrupt:
                code = 130
            except Exception:
                code = 126
            finally:
                # Ignore repeat interrupts while terminating/reaping and cleaning.
                for sig in old_handlers:
                    signal.signal(sig, signal.SIG_IGN)
                if process is not None:
                    termination = stop_descendants(os.getpid())
                    stopped = termination['stopped']
                    if stopped:
                        process.wait(timeout=0)
                    process_record.update(stopped=stopped, termination=termination, ended_at=now())
                    save(Path(output) / 'evidence/capture-process.json', process_record)
                    if not stopped:
                        code = code or 125
                stream.seek(0)
                text = stream.read().decode('utf-8', errors='replace')
                if secret:
                    text = text.replace(secret, '[REDACTED]')
                log = Path(output) / 'capture-console.log'
                log.write_text(text)
                log.chmod(0o600)
        return {'exit_code': code, 'started_at': started, 'ended_at': now(), 'capture_processes_stopped': stopped}
    finally:
        # main deliberately installs cleanup-time handlers before its finally.
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        set_subreaper(previous_subreaper)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['config', 'tool-dir', 'binary', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--cleanup-only', action='store_true')
    parser.add_argument('--timeout', type=float, default=900)
    args = parser.parse_args(argv)
    os.umask(0o077)
    output = args.output.resolve()
    config = json.loads(args.config.read_text())
    api = API(config)
    template = config['template_id']
    if config.get('cubemastercli', {}).get('exclusive_template') is not True:
        raise ValueError('exclusive_template_required')
    if config.get('warmup') != 0:
        raise ValueError('prewarmup_must_be_disabled')
    lock_name = hashlib.sha256((api.url + '\n' + template).encode()).hexdigest()
    lock = open('/tmp/cube-bench-round-' + lock_name + '.lock', 'a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ValueError('another_round_holds_template_lock') from None
    try:
        return execute_locked(args, output, config, api, template)
    finally:
        lock.close()


def execute_locked(args, output, config, api, template):
    if args.cleanup_only:
        context = json.loads((output / 'evidence/context.json').read_text())
        if context.get('api_url') != api.url or context.get('template_id') != template:
            raise ValueError('recovery_target_mismatch')
        process_file = output / 'evidence/capture-process.json'
        if context.get('capture_started') and not process_file.exists():
            raise ValueError('capture_process_evidence_missing')
        if process_file.exists():
            group = json.loads(process_file.read_text())['process_group']
            if type(group) is not int or group <= 1:
                raise ValueError('invalid_recovery_process_group')
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                pass
            else:
                raise ValueError('capture_process_group_still_exists')
        # Cleanup-only requires the original capture to have stopped; the lock
        # blocks recovery while a cooperating wrapper still owns the round.
        receipt = cleanup(api, context, output)
        return 0 if receipt['status'] == 'complete' else 3
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    context = {'template_id': template, 'api_url': api.url, 'exclusive_template': True,
               'baseline': None, 'started_at': now(), 'wrapper_pid': os.getpid(), 'capture_started': False,
               'capture_processes_stopped': False}
    result = {'status': 'failed', 'errors': [], 'exit_code': None}
    receipt = None
    try:
        if digest(args.binary) != args.expected_sha256.lower():
            raise ValueError('binary_sha256_mismatch')
        context['binary_sha256'] = args.expected_sha256.lower()
        baseline = inventory(api)
        if baseline:
            raise ValueError('initial_inventory_not_empty')
        context['baseline'] = baseline
        save(output / 'evidence/context.json', context)
        status, tpl = api.call('/templates/' + template)
        if status != 200 or not isinstance(tpl, dict) or tpl.get('status') != 'READY':
            raise ValueError('template_not_ready')
        containers = tpl['createRequest']['containers']
        if len(containers) != 1 or containers[0].get('resources') != {'cpu': '2000m', 'mem': '2048Mi'} or containers[0].get('image', {}).get('writable_layer_size') != '1G':
            raise ValueError('template_resource_mismatch')
        save(output / 'evidence/template.json', {'template_id': template, 'status': tpl['status'],
             'containers': [{'resources': c.get('resources'), 'probe': c.get('probe'),
                             'image': {key: c.get('image', {}).get(key) for key in ['image', 'storage_media', 'writable_layer_size']}} for c in containers]})
        save(output / 'evidence/before.json', host_snapshot())
        command = [sys.executable, str(args.tool_dir.resolve() / 'capture_w3.py'), '--config', str(args.config.resolve()),
                   '--benchmark-binary', str(args.binary.resolve()), '--output-root', str(output / 'runs')]
        save(output / 'evidence/invocation.json', {'command': command, 'started_at': now(),
             'formal': {'concurrency': 100, 'total': 100, 'warmup': 3, 'warmup_mode': 'in_process_shared_client',
                        'mode': 'create-only', 'no_tui': True},
             'prewarmup': None})
        def on_started():
            context['capture_started'] = True
            save(output / 'evidence/context.json', context)
        result.update(run_capture(command, output, api.key, args.timeout, on_started=on_started))
        context['capture_processes_stopped'] = result.get('capture_processes_stopped') is True
    except BaseException as error:
        result['errors'].append(error_record(error))
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, signal.SIG_IGN)
        save(output / 'evidence/context.json', context)
        receipt = cleanup(api, context, output)
        evidence = receipt.get('cli_evidence', {})
        verified = (len(evidence.get('unknown_phase_ids', [])) == 103 and not evidence.get('warmup_ids')
                    and not evidence.get('conflict', True)
                    and set(evidence.get('unknown_phase_ids', [])) == set(receipt.get('candidate_ids', [])))
        result['ownership_verified_by_cli_sets'] = verified
        if result['exit_code'] == 0 and verified and receipt['status'] == 'complete':
            result['status'] = 'complete'
        result['cleanup_status'] = receipt['status']
        result['ended_at'] = now()
        save(output / 'evidence/run-exit.json', result)
        save(output / 'evidence/after.json', host_snapshot())
    print(json.dumps({'output': str(output), 'status': result['status'], 'cleanup': receipt['status']}))
    return 0 if result['status'] == 'complete' else 3


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('Round setup failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(2)
