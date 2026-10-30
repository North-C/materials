#!/usr/bin/env python3
"""Validate this publication offline. No network, remote actions, or workloads."""
import argparse
import datetime
import hashlib
import json
import math
import pathlib
import re
import statistics

BASE = pathlib.Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((BASE / name).read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected):
    assert math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-7), (actual, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-validation', action='store_true')
    args = parser.parse_args()
    manifest = load('source-manifest.json')
    for entry in manifest['raw_copies']:
        assert sha(BASE / entry['published_path']) == entry['published_sha256'] == entry['source_sha256']
    summary = load('derived/host231-summary.json')
    assert summary['valid_samples'] == 20 and len(summary['rows']) == 20
    assert summary['initialization_runs'] == 2 and summary['excluded_attempts'] == 2
    groups = {}
    for row in summary['rows']:
        p = BASE / row['source']
        assert sha(p) == row['sha256']
        result = load(row['source'])
        assert result['fio version'] == 'fio-3.34'
        job = result['jobs'][0]
        assert job['error'] == 0
        io = job['write' if row['operation'].endswith('write') else 'read']
        for field, value in [('bw_bytes_s', io['bw_bytes']), ('iops', io['iops']),
                             ('runtime_ms', io['runtime']), ('lat_mean_us', io['lat_ns']['mean'] / 1000),
                             ('clat_p95_us', io['clat_ns']['percentile']['95.000000'] / 1000),
                             ('clat_p99_us', io['clat_ns']['percentile']['99.000000'] / 1000)]:
            close(row[field], value)
        assert 15000 <= io['runtime'] <= 15020
        assert row['actual_depth_percent'] > 99
        groups.setdefault(row['operation'], []).append(row)
    for operation, rows in groups.items():
        assert len(rows) == 5 and {r['round'] for r in rows} == set(range(1, 6))
        for metric, stats in summary['summary'][operation].items():
            if metric == 'n':
                continue
            values = [r[metric] for r in rows]
            close(stats['median'], statistics.median(values))
            close(stats['min'], min(values))
            close(stats['max'], max(values))
            close(stats['sample_cv_percent'], statistics.stdev(values) / statistics.mean(values) * 100)
    history = load('derived/host90-history.json')['measurements']
    assert len(history) == 6
    for row in history:
        p = BASE / row['source']
        assert sha(p) == row['source_sha256']
        if row['format'] == 'fio JSON':
            job = load(row['source'])['jobs'][0]
            assert job['error'] == 0
            io = job['write' if row['operation'].endswith('write') else 'read']
            values = io['bw_bytes'], io['iops'], io['lat_ns']['mean'] / 1000
        else:
            fields = p.read_text().strip().split(';')
            values = float(fields[6]) * 1024, float(fields[7]), float(fields[39])
        for key, value in zip(['bw_bytes_s', 'iops', 'mean_total_latency_us'], values):
            close(row[key], value)
    for comparison in summary['historical_comparisons']:
        old = next(r for r in history if r['source'] == comparison['historical_source'])
        metric = comparison['metric']
        new = summary['summary'][comparison['operation']][metric]['median']
        close(comparison['host90_historical_single'], old[metric])
        close(comparison['epyc9654_median'], new)
        close(comparison['epyc9654_change_percent'], (new / old[metric] - 1) * 100)
    assert summary['gate_summary']['count'] == 23 and summary['gate_summary']['all_passed']
    assert summary['cleanup']['complete'] and summary['cleanup']['directory_absent']
    for key in ['critical_warning', 'media_errors', 'num_err_log_entries', 'warning_temp_time', 'critical_comp_time']:
        assert summary['smart_before'][key] == summary['smart_after'][key] == 0
    post = load('raw/host231-fio/postcheck.json')
    assert post['fio_sha256'] == summary['fio_sha256']
    assert not post['blockers'] and not post['workspaces_remaining']
    for host, device in [('host231', '/dev/nvme1n1'), ('host90', '/dev/nvme2n1')]:
        j = load(f'raw/inventory/{host}-inventory.json')
        mount = j['mounts']['/data' if host == 'host231' else '/data/cubelet']['data']['filesystems'][0]
        assert mount['source'] == device
        service = load(f'raw/inventory/{host}-service-mounts.json')
        cubelet = next(s for s in service['processes'] if s['comm'] == 'cubelet')
        assert cubelet['mounts']['/data/cubelet/root']['filesystems'][0]['maj:min'] == mount['maj:min']
    checked_links = 0
    for p in BASE.rglob('*.md'):
        text = p.read_text()
        assert len(re.findall(r'^```', text, re.M)) % 2 == 0, p
        assert all(line.rstrip() == line for line in text.splitlines()), p
        assert not re.search(r'(?:鲲鹏|Kunpeng)\s*950', text), p
        for link in re.findall(r'\]\(([^)]+)\)', text):
            if link.startswith(('https:', 'http:', 'mailto:', '#')):
                continue
            target = (p.parent / link.split('#')[0]).resolve()
            assert target.is_relative_to(BASE) and (target.exists() or target.name in ['validation.json', 'SHA256SUMS']), (p, link)
            checked_links += 1
    result = {'status': 'passed', 'validated_at': datetime.datetime.now().astimezone().isoformat(),
              'raw_files_verified': len(manifest['raw_copies']), 'formal_fio_results_recomputed': 20,
              'historical_fio_results_recomputed': 6, 'excluded_preliminary_attempts': 2,
              'local_links_checked': checked_links, 'new_remote_actions': 0,
              'limitations': ['Historical single-run reference is not a simultaneous controlled comparison.',
                             'Exact HWE6A SKU-to-vendor-performance mapping remains unverified.']}
    if args.write_validation:
        (BASE / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
