#!/usr/bin/env python3
"""Build the unified cube-perf-bench table for the rebuilt original template (tpl-4feed5ee).

Usage: python3 -I scripts/make_summary.py   (run from this report directory; result directories are under raw/)

Inputs (read-only): derived/{rest-2115,rerun4-2152,rerun-clone10-2158}.csv (from the 10-27
summarize.py; a rerun replaces the earlier row, which is kept with a suffix),
results-origtpl-{2021,snap10-2055,c50-2101}, the window audits, and the
10-27 nvme1 comparison.csv (BoostKit B-nvme1 / community A-nvme1, descriptive reference only).
Writes derived/unified.csv and derived/unified.md.
"""
import csv, json, re, statistics
from pathlib import Path

HERE = Path('.')
RAW = HERE / 'raw'
REF = Path('../v071-amd9654-community-vs-boostkit-20261027/derived/comparison.csv')
INVALID = {'dirty-d100', 'dirty-d200', 'dirty-d500', 'dirty-d800', 'dirty-d1024'}
METRICS = {  # family -> [(column, label)]
    'startup': [('total_ms', '整轮'), ('avg', 'avg'), ('p95', 'P95')],
    'snapshot': [('wall_avg', 'wall avg'), ('wall_p95', 'wall P95'), ('per_avg', 'per avg')],
    'rollback': [('wall_avg', 'wall avg'), ('wall_p95', 'wall P95'), ('per_avg', 'per avg')],
    'create': [('wall_avg', 'wall avg'), ('wall_p95', 'wall P95'), ('per_avg', 'per avg')],
    'clone': [('wall_avg', 'wall avg'), ('wall_p95', 'wall P95'), ('per_avg', 'per avg')],
    'pause': [('pause_avg', 'pause avg'), ('resume_avg', 'resume avg'), ('resume_p95', 'resume P95')],
    'dirty': [('snap_avg', 'snap avg'), ('create_avg', 'create avg'), ('dirty_MB_avg', '写入 MB')],
}


def family(case):
    if case.startswith(('pause', 'extended-pause')):
        return 'pause'
    if case.startswith(('startup', 'extended-startup')):
        return 'startup'
    return case.split('-')[0]


def foreign(audit):
    bad = set()
    p = RAW / audit
    if p.is_file():
        for line in p.read_text().splitlines():
            m = re.match(r'(\S+)\s+rc=\S+ .*foreign=(\{.*\})', line)
            if m and m.group(2) != '{}':
                bad.add(m.group(1))
    return bad


def load(path, src):
    p = HERE / path
    return {r['case']: dict(r, source=src) for r in csv.DictReader(p.open())} if p.is_file() else {}


rows = load('derived/rest-2115.csv', 'results-origtpl-rest-2115')
bad = foreign('results-origtpl-rest-2115/window-audit.txt')
for case in bad:
    rows[case]['foreign'] = 'yes'
for n, sub in enumerate(('results-origtpl-rerun4-2152', 'results-origtpl-rerun-clone10-2158')):
    bad_rerun = foreign(f'{sub}/window-audit.txt')
    for case, r in load(f'derived/{sub[len("results-origtpl-"):]}.csv', sub).items():
        old = rows.pop(case)
        label = f"{case} ({'首测' if n == 0 else f'重测{n}'}{'，外部创建' if old.get('foreign') else ''})"
        rows[label] = dict(old, case=label)
        rows[case] = dict(r, foreign='yes' if case in bad_rerun else '')


def five(sub, prefix, kind):
    vals = []
    for i in range(1, 6):
        d = RAW / f'{sub}/{prefix}-{i}'
        if kind == 'startup':
            s = json.loads((d / 'cube-bench.json').read_text())
            vals.append({'total_ms': s['summary']['total_time_s'] * 1000, 'avg': s['create']['avg'], 'p95': s['create']['p95']})
        else:
            cols = (d / 'stdout.log').read_text().split()[-7:]
            vals.append({'wall_avg': float(cols[2]), 'wall_p95': float(cols[4]), 'per_avg': float(cols[6])})
    return {k: round(statistics.median(v[k] for v in vals), 1) for k in vals[0]}, vals


for case, sub, prefix, kind in (('extended-startup-c100n100', 'results-origtpl-2021', 'c100', 'startup'),
                                ('startup-c50n500', 'results-origtpl-c50-2101', 'c50', 'startup'),
                                ('snapshot-c10', 'results-origtpl-snap10-2055', 'snap10', 'snapshot')):
    med, vals = five(sub, prefix, kind)
    first = METRICS[family(case)][0][0]
    rows[case] = dict(med, case=case, rc='0', source=sub, foreign='',
                      note='五次中位；' + first + ' 逐次 ' + ' / '.join(f'{v[first]:.1f}' for v in vals))

ref = {}
for r in csv.DictReader(REF.open()):
    if r['phase'] in ('B-nvme1', 'A-nvme1'):
        ref.setdefault(r['case'], {})[r['phase']] = r
ref.setdefault('extended-startup-c100n100', {})['B-nvme1'] = {'total_ms': '119.8'}

ORDER = ['startup-c1n20', 'startup-c10n200', 'startup-c20n300', 'startup-c50n500', 'extended-startup-c100n100',
         'extended-startup-c200n200', 'extended-startup-c300n300'] + [f'{k}-c{c}' for k in ('snapshot', 'rollback', 'pause')
         for c in (1, 5, 10)] + ['extended-pause-c100'] + [f'dirty-d{d}' for d in (0, 10, 50, 100, 200, 500, 800, 1024)] + \
        [f'create-c{c}' for c in (1, 10, 20, 50)] + ['clone-c1n1', 'clone-c10n100', 'clone-c20n100', 'clone-c50n100']
keys = sorted(rows, key=lambda c: (ORDER.index(c.split(' ')[0]) if c.split(' ')[0] in ORDER else 99, c))


def fmt(r, col):
    v = r.get(col, '') if r else ''
    return v if v not in ('', None) else '—'


out, md = [], ['| 项目 | 指标 | 本次（tpl-4feed5ee） | 10-27 BoostKit B-nvme1 | 10-27 社区 A-nvme1 | 状态 |',
               '| --- | --- | --- | --- | --- | --- |']
for case in keys:
    r = rows[case]
    base = case.split(' ')[0]
    m = METRICS[family(base)]
    status = '有效'
    if base in INVALID:
        status = '工作量无效（shm 64 MiB）'
    if r.get('foreign') == 'yes':
        status = '窗口有外部创建，不作样本'
    if r.get('rc') != '0':
        status = f"rc={r.get('rc')}"
    if r.get('note'):
        status += '；' + r['note']
    b, a = ref.get(base, {}).get('B-nvme1'), ref.get(base, {}).get('A-nvme1')
    md.append(f"| {case} | {' / '.join(l for _, l in m)} | {' / '.join(str(fmt(r, c)) for c, _ in m)} | "
              f"{' / '.join(str(fmt(b, c)) for c, _ in m) if b else '—'} | {' / '.join(str(fmt(a, c)) for c, _ in m) if a else '未测'} | {status} |")
    out.append({'case': case, 'status': status, 'source': r['source'], **{c: r.get(c, '') for c, _ in m}})
(HERE / 'derived/unified.md').write_text('\n'.join(md) + '\n')
cols = []
for r in out:
    cols += [k for k in r if k not in cols]
with (HERE / 'derived/unified.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, cols)
    w.writeheader()
    w.writerows(out)
print('\n'.join(md))
