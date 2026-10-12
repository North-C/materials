#!/usr/bin/env python3
"""Publish archived results; never contacts Docker, a sandbox, or a remote host."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import yaml

OMIT = {'action', 'stdout', 'stderr'}
HEX_ID = re.compile(r'\b[0-9a-f]{32}\b')
IP = re.compile(r'\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b')
HOME = re.compile(r'/(?:home/[^/\s"<>]+|root)(?=/|\b)')
PROGRESS = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Replay:\s+(\d+)/(\d+)\s+traj=(\d+)/(\d+)\s+avg=([\d.]+)s\s+p99=([\d.]+)s')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def text_clean(value):
    value = IP.sub('NODE_ADDRESS', value)
    value = HOME.sub('USER_HOME', value)
    value = re.sub(r'\btpl-[a-z0-9]+\b', 'TEMPLATE_ID', value)
    # Monitor VM names are 32 hex digits. Keep a stable public join key.
    value = HEX_ID.sub(lambda m: 'vm-' + hashlib.sha256(m[0].encode()).hexdigest()[:16], value)
    return value


def clean(value):
    if isinstance(value, dict):
        return {k: ('REDACTED' if re.search(r'(?i)(api.?key|password|authorization|secret|token)', k) and v
                    else clean(v)) for k, v in value.items() if k not in OMIT}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return text_clean(value) if isinstance(value, str) else value


def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def gzip_text(path):
    return io.TextIOWrapper(gzip.GzipFile(filename='', mode='wb', fileobj=path.open('wb'), mtime=0), encoding='utf-8')


def csv_write(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True, help='density-bench evidence root')
    ap.add_argument('--output', type=Path, required=True, help='new publication directory')
    args = ap.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    if out.exists():
        ap.error('output already exists; preserve it and use a new directory')
    out.mkdir(parents=True)
    records, summaries = [], []

    def record(src, dst, transform):
        records.append({'source': str(src.relative_to(source)), 'source_sha256': sha(src),
                        'published': str(dst.relative_to(out)), 'published_sha256': sha(dst),
                        'bytes': dst.stat().st_size, 'transform': transform})

    b1 = Path('validation/20261009-cube90/batch1-nomonitor-20261009')
    b2 = Path('validation/20261009-cube90/batch2-monladder-20261010')
    specs = [
        ('cube95-cwd-before', Path('validation/20261009-cube95/remote-after-network/results/replay-smoke'), 'functional_before_fix'),
        ('cube95-testbed', Path('validation/20261009-cube95/remote-after-network/results/replay-testbed'), 'functional_verified'),
        ('batch1-preflight', b1/'results/replay-preflight-1', 'preflight'),
        ('batch1-384', b1/'results/replay-exec-384-r1', 'density_no_monitor'),
        ('batch1-768', b1/'results/replay-exec-768-r2', 'density_no_monitor'),
        ('batch1-1152-attempt', b1/'results/replay-exec-1152-r3', 'admission_limited'),
        ('batch2-preflight', b2/'results/mon-preflight', 'preflight'),
    ] + [(f'batch2-{n}', b2/f'results/mon-mon{n}', 'density_with_monitor') for n in (384, 768, 1152, 1536)]
    specs.append(('quarantine-interrupted', b2/'quarantine/aborted-manual-20s-run', 'invalid_interrupted'))
    for name, rel, category in specs:
        found = list((source/rel).rglob('*_run_summary.json'))
        assert len(found) == 1, (name, len(found))
        native = found[0].parent
        dest = out/'runs'/name
        dest.mkdir(parents=True)
        summary = json.loads(found[0].read_text())
        traj = [json.loads(p.read_text()) for p in sorted((native/'trajectories').glob('*/replay_result.json'))]
        runs = [r for d in traj for r in d.get('runs', [])]
        steps = [s for r in runs for s in r.get('steps', [])]
        row = {'run': name, 'category': category, 'configured_sandboxes': summary['total_count'],
               'cpu_budget_logical': 384 if 'cube95' not in name else '', 'vcpus_per_vm': 2,
               'configured_cpu_ratio': summary['total_count'] * 2 / 384 if 'cube95' not in name else '',
               'native_overcommit_ratio': summary['overcommit_ratio'], 'wall_sec': summary['wall_sec'],
               **summary['throughput'], 'exported_runs': len(runs),
               'timeout_runs': sum(any(s.get('timed_out') for s in r.get('steps', [])) for r in runs),
               'timeout_steps': sum(bool(s.get('timed_out')) for s in steps),
               'non_timeout_slice_failed_steps': sum(bool(s.get('slice_failed')) and not s.get('timed_out') for s in steps),
               'nonzero_exit_steps': sum(s.get('return_code') not in (0, None) for s in steps),
               'create_error_runs': sum(bool(r.get('create_error_type')) for r in runs),
               'kill_error_runs': sum(bool(r.get('kill_error_type')) for r in runs),
               'exported_steps': len(steps),
               'monitor_present': (native/'vm_monitor/cubesandbox_monitor.csv').is_file()}
        if category != 'invalid_interrupted':
            assert row['exported_steps'] == row['total_steps'], name
        summaries.append(row)
        for src in sorted(native.rglob('*')):
            if not src.is_file() or src.suffix not in {'.json', '.jsonl', '.csv', '.svg', '.png', '.xlsx', '.txt'}:
                continue
            relative = src.relative_to(native)
            compress = src.suffix == '.jsonl' or src.name == 'replay_result.json' or src.suffix == '.csv' and src.stat().st_size > 1024*1024
            dst = dest / (str(relative) + ('.gz' if compress else ''))
            dst.parent.mkdir(parents=True, exist_ok=True)
            transform = 'sanitized'
            if src.suffix == '.json':
                data = clean(json.loads(src.read_text()))
                if src == found[0]:
                    data['publication_category'] = category
                    data['paths'] = {k: ('vm_monitor' if k == 'vm_monitor_dir' else
                                         'trajectories/index.json' if k == 'trajectory_index' else
                                         Path(v).name + ('.gz' if k == 'lifecycle_series' else '')) if v else v
                                     for k, v in data['paths'].items()}
                elif src.name == 'index.json':
                    for entry in data.get('trajectories', []):
                        if entry.get('file'):
                            entry['file'] += '.gz'
                if compress:
                    with gzip_text(dst) as f:
                        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                        f.write('\n')
                else:
                    json_write(dst, data)
            elif src.suffix == '.jsonl':
                with src.open() as inp, gzip_text(dst) as f:
                    for line in inp:
                        f.write(json.dumps(clean(json.loads(line)), ensure_ascii=False, separators=(',', ':')) + '\n')
            elif src.suffix == '.xlsx':
                with zipfile.ZipFile(src) as inp, zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as z:
                    for item in inp.infolist():
                        data = inp.read(item.filename)
                        if item.filename.endswith(('.xml', '.rels')):
                            data = text_clean(data.decode('utf-8')).encode('utf-8')
                        z.writestr(item, data)
            elif src.suffix == '.png':
                shutil.copyfile(src, dst)
                transform = 'unchanged_native_chart'
            elif compress:
                with src.open(encoding='utf-8-sig') as inp, gzip_text(dst) as f:
                    for line in inp:
                        f.write(text_clean(line))
            else:
                dst.write_text(text_clean(src.read_text(encoding='utf-8-sig')))
            if compress:
                transform += '+deterministic_gzip'
            record(src, dst, transform)
        json_write(dest/'classification.json', {'category': category, 'source_run': str(native.relative_to(source)),
                   'driver_commit': '262a0534cc76d138a38b42bc890c9bdd9b40922d' if name.startswith('cube95') else '93f978f7ec27d9bc519dca2efdc809ada09acbaa',
                   'stats': row, 'cleanup_revalidated_during_publication': False})
        print('exported', name, 'steps', len(steps), flush=True)

    for batch, rel in [('batch1', b1), ('batch2', b2)]:
        dest = out/batch
        (dest/'charts').mkdir(parents=True)
        (dest/'data').mkdir()
        for src in sorted((source/rel/'charts').glob('*.png')):
            if src.name in {'10_ladder_progress_latency.png', '11_ladder_host.png'}:
                continue  # Publish corrected replacements with a documented erratum.
            dst = dest/'charts'/src.name
            shutil.copyfile(src, dst)
            record(src, dst, 'unchanged_historical_chart')
        for src in sorted((source/rel/'charts/host-svg-from-sampler').rglob('*.svg')):
            dst = dest/'charts/host-svg-from-sampler'/src.relative_to(source/rel/'charts/host-svg-from-sampler')
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text_clean(src.read_text()))
            record(src, dst, 'sanitized_historical_derived_chart')
        for src in sorted((source/rel/'logs').glob('*.log')):
            rows = []
            for line in src.read_text(errors='replace').splitlines():
                m = PROGRESS.match(line)
                if m:
                    rows.append(dict(zip(['local_time_utc_plus_8', 'steps', 'expected_steps', 'trajectories', 'expected_trajectories', 'avg_sec', 'p99_sec'], m.groups())))
            if rows:
                dst = dest/'data'/(src.stem+'.progress.csv')
                csv_write(dst, rows)
                record(src, dst, 'progress_metrics_only_no_log_bodies')
        for src in sorted((source/rel/'logs').glob('host_metrics_*.csv')):
            dst = dest/'data'/src.name
            shutil.copyfile(src, dst)
            record(src, dst, 'unchanged_numeric_host_samples')
        for src in sorted((source/rel/'configs').glob('*.yaml')):
            dst = dest/'data'/(src.stem+'.config.json')
            json_write(dst, clean(yaml.safe_load(src.read_text())))
            record(src, dst, 'sanitized_config_yaml_to_json_comments_omitted')

    admission = source/b2/'logs/admission-probe.log'
    text = admission.read_text()
    assert 'Sandboxes ready: 900' in text
    report = text[text.rfind('[Phase 0 Complete]'):]
    dst = out/'batch2/data/admission-900.txt'
    dst.write_text(text_clean(report))
    record(admission, dst, 'create_only_final_statistics_excerpt')
    csv_write(out/'summary.csv', summaries)
    json_write(out/'summary.json', summaries)
    json_write(out/'evidence-manifest.json', {'schema': 1, 'sources_relative_to': 'density-bench',
               'raw_logs_published': False, 'removed_json_fields': sorted(OMIT),
               'vm_names': 'stable vm- plus first 16 SHA256 hex digits of original 32-hex name',
               'artifacts': records})
    print('DONE', len(records), 'source-derived artifacts', flush=True)


if __name__ == '__main__':
    main()
