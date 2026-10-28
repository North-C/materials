#!/usr/bin/env python3
"""Resume batches per template from today's CubeAPI log, with Cubelet-stat costs of the resume Create.

Usage: resume_by_tpl.py   (run on the test host; read-only)
A batch = resumed events of one template whose timestamps are within 1.5 s of the previous one.
For each resumed instance, the resume Create is its last Create in Cubelet-stat before the resumed event.
"""
import collections, json, re, statistics
from datetime import datetime

API = '/data/log/CubeAPI/cube-api-2026-10-28.log'
STAT = '/data/log/Cubelet/Cubelet-stat.log'


def ts(s):
    m = re.match(r'(.*T\d\d:\d\d:\d\d)(\.\d+)?(Z|[+-]\d\d:\d\d)$', s)
    frac = float('0' + (m.group(2) or ''))
    tz = '+00:00' if m.group(3) == 'Z' else m.group(3)
    return datetime.fromisoformat(m.group(1) + tz).timestamp() + frac


tpl, resumed = {}, []
for line in open(API, errors='replace'):
    if '"sandbox.created"' in line or '"sandbox.resumed"' in line:
        d = json.loads(line)
        if d['event'] == 'sandbox.created':
            tpl[d['sandbox_id']] = d.get('template_id', '?')
        else:
            resumed.append((ts(d['timestamp']), d['sandbox_id']))
want = {i for _, i in resumed}
creates = collections.defaultdict(list)  # inst -> [(ts, req, callee, cost)]
with open(STAT, 'rb') as fh:
    for raw in fh:
        if b'"Action":"Create"' not in raw:
            continue
        m = re.search(rb'"InstanceId":"([0-9a-f]{32})"', raw)
        if not m or m.group(1).decode() not in want:
            continue
        d = json.loads(raw)
        if d.get('Callee') in ('sandbox-create', 'sandbox-probe', 'cubebox'):
            creates[d['InstanceId']].append((ts(d['@timestamp']), d['RequestId'], d['Callee'], d['CostTime']))
batches = []
for t, i in sorted(resumed):
    k = tpl.get(i, '?')
    if batches and batches[-1]['tpl'] == k and t - batches[-1]['last'] < 1.5:
        b = batches[-1]
    else:
        b = {'tpl': k, 'first': t, 'last': t, 'ids': []}; batches.append(b)
    b['last'] = t; b['ids'].append((t, i))
for b in batches:
    cols = collections.defaultdict(list)
    for t, i in b['ids']:
        prior = [c for c in creates[i] if c[0] <= t + 0.05]
        if not prior:
            continue
        req = max(prior)[1]
        for c in prior:
            if c[1] == req:
                cols[c[2]].append(c[3])
    s = ' '.join(f"{k}:p50={statistics.median(v):.0f}/max={max(v):.0f}" for k, v in sorted(cols.items()))
    print(datetime.fromtimestamp(b['first']).strftime('%H:%M:%S'), b['tpl'][:12], f"n={len(b['ids'])}",
          f"span={1000*(b['last']-b['first']):.0f}ms", s)
