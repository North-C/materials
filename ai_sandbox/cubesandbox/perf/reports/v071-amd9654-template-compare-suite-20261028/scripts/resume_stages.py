#!/usr/bin/env python3
"""Per-stage Cubelet cost of the initial create vs the resume create for each pause item.

Usage: resume_stages.py <windows.tsv>   (run on the test host)
Instance IDs: 32-hex IDs in the item's CubeAPI byte window. Cubelet-stat.log: per-instance Create
entries ordered by time; the 1st Create is the initial create, the 2nd is the resume (restore from the
pause snapshot). Prints sandbox-create / sandbox-probe / cubebox per round, and the probe histogram.
"""
import collections, json, re, statistics, sys

STAT = '/data/log/Cubelet/Cubelet-stat.log'
CALLEES = ('sandbox-create', 'sandbox-probe', 'cubebox')
items = []
for line in open(sys.argv[1]):
    f = line.rstrip('\n').split('\t')
    if f[0].startswith(('pause', 'extended-pause')):
        with open(f[3], 'rb') as fh:
            fh.seek(int(f[4])); blob = fh.read(int(f[5]) - int(f[4])).decode(errors='replace')
        ids = set(re.findall(r'"sandbox_id":"([0-9a-f]{32})"', blob))
        items.append((f[0], ids))
want = set().union(*(i for _, i in items))
per = collections.defaultdict(lambda: collections.defaultdict(dict))  # inst -> req -> callee -> (ts, cost)
with open(STAT, 'rb') as fh:
    for raw in fh:
        if b'"Action":"Create"' not in raw:
            continue
        m = re.search(rb'"InstanceId":"([0-9a-f]{32})"', raw)
        if not m or m.group(1).decode() not in want:
            continue
        d = json.loads(raw)
        if d.get('Callee') in CALLEES:
            per[d['InstanceId']][d['RequestId']][d['Callee']] = (d['@timestamp'], d['CostTime'])


def q(v):
    v = sorted(v)
    return f"n={len(v)} min={v[0]:.0f} p50={statistics.median(v):.0f} p90={v[int(len(v)*0.9)-1 if len(v)>1 else 0]:.0f} max={v[-1]:.0f}"


for name, ids in items:
    print(f'== {name}: {len(ids)} instances')
    for k, label in ((0, 'initial create'), (1, 'resume')):
        cols = {c: [] for c in CALLEES}
        for inst in ids:
            reqs = sorted(per[inst].values(), key=lambda r: min(t for t, _ in r.values()))
            if len(reqs) > k:
                for c in CALLEES:
                    if c in reqs[k]:
                        cols[c].append(reqs[k][c][1])
        for c in CALLEES:
            if cols[c]:
                print(f'  {label:14s} {c:15s} {q(cols[c])}')
        if k == 1 and cols['sandbox-probe']:
            hist = collections.Counter(int(v // 100) * 100 for v in cols['sandbox-probe'])
            print('  resume probe histogram (100 ms bins):', dict(sorted(hist.items())))
