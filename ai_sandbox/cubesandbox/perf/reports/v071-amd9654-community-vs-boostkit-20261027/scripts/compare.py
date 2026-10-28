#!/usr/bin/env python3
"""Community (A) vs BoostKit (B) table from a summarize.py CSV.

Usage: python3 -I compare.py <summary.csv> <A-label> <B-label> > table.md

Delta = (B - A) / A. Cases whose workload is known invalid are listed but get no
delta. Single-invocation cases are descriptive only; c100 uses five rounds.
"""
import csv, sys
from collections import defaultdict

INVALID = {'dirty-d100', 'dirty-d200', 'dirty-d500', 'dirty-d800', 'dirty-d1024'}
METRICS = [  # (case prefix, column, label)
    ('startup', 'avg', 'avg'), ('startup', 'p95', 'P95'),
    ('extended-startup', 'avg', 'avg'), ('extended-startup', 'p95', 'P95'),
    ('snapshot', 'wall_avg', 'wall avg'), ('rollback', 'wall_avg', 'wall avg'),
    ('pause', 'pause_avg', 'pause avg'), ('pause', 'resume_avg', 'resume avg'),
    ('extended-pause', 'pause_avg', 'pause avg'), ('extended-pause', 'resume_avg', 'resume avg'),
    ('dirty', 'snap_avg', 'snap avg'), ('dirty', 'create_avg', 'create avg'), ('dirty', 'dirty_MB_avg', 'dirty MB'),
    ('create', 'wall_avg', 'wall avg'), ('clone', 'wall_avg', 'wall avg'),
]
ORDER = ['startup-c1n20', 'startup-c10n200', 'startup-c20n300', 'startup-c50n500',
         'extended-startup-c200n200', 'extended-startup-c300n300',
         'snapshot-c1', 'snapshot-c5', 'snapshot-c10', 'rollback-c1', 'rollback-c5', 'rollback-c10',
         'pause-c1', 'pause-c5', 'pause-c10', 'extended-pause-c100',
         'dirty-d0', 'dirty-d10', 'dirty-d50', 'dirty-d100', 'dirty-d200', 'dirty-d500', 'dirty-d800', 'dirty-d1024',
         'create-c1', 'create-c10', 'create-c20', 'create-c50',
         'clone-c1n1', 'clone-c10n100', 'clone-c20n100', 'clone-c50n100']

path, a_label, b_label = sys.argv[1:4]
data = defaultdict(dict)
for r in csv.DictReader(open(path)):
    data[r['case']][r['phase']] = r


def val(row, col):
    try:
        return float(row.get(col, ''))
    except ValueError:
        return None


print(f'| 项目 | 指标 | {a_label} | {b_label} | B 相对 A |')
print('| --- | --- | --- | --- | --- |')
for case in ORDER:
    rows = data.get(case, {})
    a, b = rows.get(a_label), rows.get(b_label)
    for prefix, col, label in METRICS:
        if not case.startswith(prefix + '-') or (prefix == 'startup' and case.startswith('extended')):
            continue
        if prefix in ('pause', 'startup') and case.startswith('extended-'):
            continue
        av = val(a, col) if a and a['rc'] == '0' else None
        bv = val(b, col) if b and b['rc'] == '0' else None
        fa = '未完成' if av is None else f'{av:.1f}'
        fb = '未完成' if bv is None else f'{bv:.1f}'
        if col == 'dirty_MB_avg':
            fb = 'N/A（-1）' if bv == -1 else fb
            delta = '—'
        elif case in INVALID:
            delta = '工作量无效'
        elif av and bv is not None:
            delta = f'{(bv - av) / av * 100:+.1f}%'
        else:
            delta = '—'
        print(f'| {case} | {label} | {fa} | {fb} | {delta} |')

for k, label in (('total_ms', '整轮 total_ms'), ('avg', '客户端 avg'), ('p95', 'P95'), ('p99', 'P99')):
    a = data.get(f'c100n100 x5 {k}', {}).get(a_label)
    b = data.get(f'c100n100 x5 {k}', {}).get(b_label)
    def fmt(r):
        return '未完成' if not r else f"中位 {float(r['median']):.1f}（{float(r['min']):.1f}–{float(r['max']):.1f}）"
    delta = f"{(float(b['median']) - float(a['median'])) / float(a['median']) * 100:+.1f}%" if a and b else '—'
    print(f'| c100n100 ×5 | {label} | {fmt(a)} | {fmt(b)} | {delta} |')
