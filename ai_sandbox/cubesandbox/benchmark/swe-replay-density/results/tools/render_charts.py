#!/usr/bin/env python3
"""Render corrected publication charts from the published numeric tables."""
import argparse
import csv
from datetime import datetime
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def rows(path):
    with path.open(encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def elapsed(data, key, fmt):
    values = [datetime.strptime(r[key], fmt) for r in data]
    return [(v-values[0]).total_seconds() for v in values]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('results', type=Path)
    args = ap.parse_args()
    root = args.results
    dest = root/'batch2/charts'
    colors = plt.cm.viridis([0.15, 0.4, 0.65, 0.9])
    rounds = [384, 768, 1152, 1536]
    plt.rcParams.update({'font.size': 10, 'svg.hashsalt': 'density-publication'})

    def save(fig, stem):
        fig.tight_layout()
        fig.savefig(dest/(stem+'.png'), dpi=150)
        fig.savefig(dest/(stem+'.svg'), metadata={'Date': None})
        plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for n, color in zip(rounds, colors):
        data = rows(root/f'batch2/data/density-mon{n}.progress.csv')
        x = elapsed(data, 'local_time_utc_plus_8', '%Y-%m-%d %H:%M:%S')
        for ax, key in zip(axes, ['steps', 'avg_sec', 'p99_sec']):
            ax.plot(x, [float(r[key]) for r in data], label=f'{n} VMs ({n*2/384:g}:1)', color=color)
    for ax, title in zip(axes, ['Cumulative steps', 'Logged avg step latency (s)', 'Logged p99 step latency (s)']):
        ax.set(title=title, xlabel='Seconds since first progress sample')
        ax.grid(alpha=.25)
        ax.legend(fontsize=8)
    fig.suptitle('Batch 2: exec_only, 2 vCPU / 4096 MiB per VM; CPU ratio denominator = 384 logical CPUs')
    save(fig, '10_ladder_progress_latency_corrected')

    fig, axes = plt.subplots(1, 4, figsize=(19, 4.8))
    for n, color in zip(rounds, colors):
        data = rows(root/f'batch2/data/host_metrics_mon{n}.csv')
        x = elapsed(data, 'ts', '%Y-%m-%dT%H:%M:%SZ')
        for ax, key, scale in zip(axes, ['cpu_util_pct', 'mem_used_mb', 'load1', 'vm_shim_count'], [1, 1024, 1, 1]):
            values = [float(r[key])/scale for r in data]
            assert min(values) >= 0
            ax.plot(x, values, label=f'{n} workload VMs', color=color)
    for ax, title, unit in zip(axes,
            ['Host CPU utilization', 'Host MemTotal - MemFree', 'Host load1', 'Matched shim process count'],
            ['%', 'GiB (includes page cache)', 'Load average', 'Processes']):
        ax.set(title=title, xlabel='Seconds since first host sample', ylabel=unit)
        ax.grid(alpha=.25)
        ax.legend(fontsize=8)
    fig.suptitle('Batch 2 host sampler (5s): host totals include other activity; counts do not establish resource ownership')
    save(fig, '11_ladder_host_corrected')

    data = [r for r in json.loads((root/'summary.json').read_text()) if r['category'] == 'density_with_monitor']
    assert [r['configured_sandboxes'] for r in data] == rounds
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    labels = [f'{n}\n({n*2/384:g}:1 CPU)' for n in rounds]
    for ax, key, title in zip(axes, ['wall_sec', 'steps_per_sec', 'timeout_runs'],
                             ['Native run_summary wall (s)', 'Aggregate steps/s', 'Runs with >=1 timed-out step']):
        bars = ax.bar(labels, [r[key] for r in data], color=colors)
        ax.bar_label(bars, fmt='%.2f' if key == 'steps_per_sec' else '%g', padding=3, fontsize=9)
        ax.margins(y=.15)
        ax.set_title(title)
        ax.grid(alpha=.25, axis='y')
    fig.suptitle('Batch 2: all trajectories completed; timeout runs = 9 / 15 / 51 / 194')
    save(fig, '13_ladder_summary_verified')
    print('Rendered 3 corrected/verified figures in PNG and SVG')


if __name__ == '__main__':
    main()
