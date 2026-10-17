#!/usr/bin/env python3
"""Offline summary and validation; never changes capture evidence."""
import csv
import hashlib
import json
from pathlib import Path
from statistics import median

root = Path(__file__).resolve().parent
baseline = json.loads((root / 'reference/s13-baseline-summary.json').read_text())
rounds = []
stages = {}
checks = []
for state in ['pilot', 'formal']:
    for directory in sorted(p for p in (root / state).glob('round-*') if p.is_dir()):
        run = next((directory / 'runs').iterdir())
        raw = json.loads((run / 'capture/startup-latency/benchmark.raw.json').read_text())
        manifest = json.loads((run / 'capture/capture-manifest.json').read_text())
        clean = json.loads((directory / 'evidence/cleanup.json').read_text())
        result = json.loads((directory / 'evidence/run-exit.json').read_text())
        before = json.loads((directory / 'evidence/before.json').read_text())
        after = json.loads((directory / 'evidence/after.json').read_text())
        command_log = (run / 'capture/evidence/command.log').read_text()
        owned = json.loads((run / 'capture/owned-sandbox-ids.json').read_text())
        check = {
            'state': state, 'round': directory.name,
            'success_100': len(raw['raw']) == 100 and raw['summary']['successful'] == 100 and raw['summary']['errors'] == 0,
            'workload_matches': raw['config']['concurrency'] == 100 and raw['config']['total'] == 100 and raw['config']['warmup'] == 3,
            'correct_template': raw['config']['template'] == 'tpl-381852bfe518c30bb815e163',
            'no_tui_logged': 'mode=create-only, -no-tui' in command_log,
            'unknown_103': len(owned['unknown_phase']) == 103 and not owned['formal'] and not owned['warmup'],
            'cleanup_complete': clean['status'] == 'complete' and len(clean['outcomes']) == 103 and not clean['remaining_owned_ids'] and all(x['confirmed_absent'] for x in clean['outcomes']),
            'all_delete_204': all(any(a.get('status') == 204 for a in x['attempts']) for x in clean['outcomes']),
            'processes_stopped': result['capture_processes_stopped'],
            'round_complete': result['status'] == 'complete' and result['ownership_verified_by_cli_sets'],
            'services_stable': before['services'] == after['services'],
            'log_hashes_match': all(hashlib.sha256((run / 'capture' / x['delta_path']).read_bytes()).hexdigest() == x['sha256'] for x in manifest['logs'].values() if x['status'] == 'captured'),
        }
        checks.append(check)
        assert all(v for k, v in check.items() if k not in ['state', 'round']), check
        row = {'state': state, 'round': directory.name, 'run': str(run.relative_to(root)),
               'total_ms': raw['summary']['total_time_s'] * 1000,
               'avg_ms': raw['create']['avg'], 'p50_ms': raw['create']['p50'],
               'p95_ms': raw['create']['p95'], 'p99_ms': raw['create']['p99'],
               'max_ms': raw['create']['max'], 'successful': raw['summary']['successful'],
               'deleted': len(clean['outcomes']), 'capture_gaps': manifest['gaps']}
        rounds.append(row)
        if state == 'formal':
            for x in csv.DictReader((run / 'analysis/stage-latency.csv').open()):
                if x['phase'] != 'unknown_phase':
                    continue
                key = x['component'] + '/' + x['stage']
                stages.setdefault(key, []).append({'round': directory.name,
                    'avg_ms': float(x['avg_ms']) if x['avg_ms'] else None,
                    'p95_ms': float(x['p95_ms']) if x['p95_ms'] else None,
                    'observed': int(x['observed_instances'] or x['count'] or 0),
                    'owned': 103})

formal = [r for r in rounds if r['state'] == 'formal']
assert len(formal) == 5 and len(rounds) == 6
stage_summary = []
for key, values in stages.items():
    valid = [v['avg_ms'] for v in values if v['avg_ms'] is not None]
    old = baseline['stages'].get(key, [])
    stage_summary.append({'stage': key, 'median_of_round_means_ms': median(valid) if valid else None,
        'rounds_with_observation': len(valid), 'min_observed_per_round': min(v['observed'] for v in values),
        'max_observed_per_round': max(v['observed'] for v in values),
        'baseline_median_of_round_means_ms': median(v['avg_ms'] for v in old) if old else None,
        'phase': 'unknown_phase', 'includes_in_process_warmup': True})

summary = {'schema_version': 1, 'template': 'tpl-381852bfe518c30bb815e163',
    'benchmark_sha256': 'ae2f32cc4ca0e542543ce0200d26521416ca6a23c3377c63cd7ea5e9fbbfb511',
    'method': 'one excluded pilot plus five c100n100 w3 create-only no-tui runs',
    'rounds': rounds, 'formal_total_ms_median': median(r['total_ms'] for r in formal),
    'formal_total_ms_min': min(r['total_ms'] for r in formal),
    'formal_total_ms_max': max(r['total_ms'] for r in formal),
    'formal_successful_requests': sum(r['successful'] for r in formal),
    'deleted_including_pilot': sum(r['deleted'] for r in rounds),
    'baseline_total_ms_median': median(r['total_ms'] for r in baseline['rounds']),
    'stage_summary': stage_summary,
    'limitations': ['server stats include 3 warmup + 100 formal, unknown_phase103 per round',
        'no client seq to sandbox mapping; do not infer warmup IDs from ordering',
        'stage summary is median of round means, not pooled samples',
        'kernel, THP defrag, RCU and MADV_RANDOM runtime settings differ from historical s13',
        'template, warmup method and benchmark binary differ from previous 414.373ms run',
        'nested stages must not be summed; missing thresholded stages are not zero',
        'agent.log=warn suppresses guest INFO anchors; no new CPU/perf sampling in reference method']}
(root / 'result-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
(root / 'evidence/validation.json').write_text(json.dumps({'status': 'passed', 'rounds': checks}, indent=2) + '\n')
with (root / 'round-summary.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(rounds[0])); writer.writeheader(); writer.writerows(rounds)
with (root / 'stage-comparison.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(stage_summary[0])); writer.writeheader(); writer.writerows(stage_summary)
print(json.dumps({'formal_rounds': len(formal), 'median_total_ms': summary['formal_total_ms_median'],
    'successes': summary['formal_successful_requests'], 'deleted_including_pilot': summary['deleted_including_pilot']}))
