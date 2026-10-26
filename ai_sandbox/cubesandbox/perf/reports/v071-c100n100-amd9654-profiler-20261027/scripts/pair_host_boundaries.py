#!/usr/bin/env python3
"""Pair host-clock log boundaries by requestID and sandboxID; no guest clocks."""
import argparse,datetime,json,math,re,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
def timestamp(s):
    m=re.fullmatch(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)',s)
    if not m:return None
    return int(datetime.datetime.fromisoformat(m[1]+m[3].replace('Z','+00:00')).timestamp())*10**9+int((m[2] or '').ljust(9,'0')[:9])
def log(path):
    for line in path.read_text().splitlines():
        try:d=json.loads(line)
        except ValueError:continue
        yield d

def stats(xs):
    xs=sorted(xs)
    return {'count':len(xs),'avg':statistics.mean(xs),'p50':xs[math.ceil(len(xs)*.5)-1],'p95':xs[math.ceil(len(xs)*.95)-1],'max':xs[-1]} if xs else None

names=['master_start','cubelet_start','shim_start','vm_start','agent_ready','shim_finish','master_reply']
segments=['master_to_cubelet','cubelet_to_shim','shim_before_vm','vm_to_agent','agent_to_shim_finish','shim_finish_to_master_reply']
results=[]
for rnd in [1,2,3,4,5]:
    run=next((a.raw/f'r{rnd}').glob('*/analysis/timeline.json')).parent.parent
    timeline=json.loads((run/'analysis/timeline.json').read_text());owned=set(json.loads((run/'capture/owned-sandbox-ids.json').read_text())['formal'])
    starts={};replies={};cubelet={}
    for d in log(run/'capture/evidence/master-delta.log'):
        text=d.get('LogContent','');ts=timestamp(d.get('@timestamp',''))
        if text.startswith('CreateSandbox:'):
            v=json.loads(text.split(':',1)[1]);starts.setdefault(v['requestID'],[]).append(ts)
        elif text.startswith('CreateSandbox_rsp:'):
            v=json.loads(text.split(':',1)[1]);sid=v.get('sandbox_id')
            if sid in owned:replies.setdefault(sid,[]).append((v.get('RequestID',v.get('requestID')),ts))
    for d in log(run/'capture/evidence/cubelet_req-delta.log'):
        if d.get('LogContent','').startswith('RunCubeSandboxRequest:'):
            v=json.loads(d['LogContent'].split(':',1)[1]);cubelet.setdefault(v['requestID'],[]).append(timestamp(d.get('@timestamp','')))
    rows=[];missing=[]
    for i in timeline['instances']:
        sid=i['instance_id']
        if sid not in owned:continue
        if len(replies.get(sid,[]))!=1:missing.append({'id':sid,'reason':'response missing/ambiguous'});continue
        rid,end=replies[sid][0]
        if len(starts.get(rid,[]))!=1 or len(cubelet.get(rid,[]))!=1:missing.append({'id':sid,'reason':'request boundary missing/ambiguous'});continue
        events={}
        for e in i.get('events',[]):
            if e.get('status')=='observed' and e.get('clock_domain')=='host_wallclock' and e.get('occurrence_count')==1 and e.get('host_timestamp_ns') is not None:events.setdefault(e['id'],[]).append(int(e['host_timestamp_ns']))
        if any(len(events.get(k,[]))!=1 for k in ['request_start','vm_start','agent_ready','request_finish']):missing.append({'id':sid,'reason':'Shim boundary missing/ambiguous'});continue
        points=[starts[rid][0],cubelet[rid][0],*[events[k][0] for k in ['request_start','vm_start','agent_ready','request_finish']],end]
        if any(x is None for x in points) or any(b<a for a,b in zip(points,points[1:])):missing.append({'id':sid,'reason':'boundary ordering anomaly'});continue
        spans={k:(b-a)/1e6 for k,a,b in zip(segments,points,points[1:])}
        spans['master_total']=(points[-1]-points[0])/1e6
        rows.append({'sandbox_id':sid,'request_id':rid,'boundaries_ns':dict(zip(names,points)),'ms':spans})
    ordered=sorted(rows,key=lambda r:r['boundaries_ns']['master_reply'])
    summary={'round':rnd,'paired':len(rows),'formal_owned':len(owned),'missing':missing,'spans':{k:stats([r['ms'][k] for r in rows]) for k in segments+['master_total']},'boundary_spreads_ms':{k:(max(r['boundaries_ns'][k] for r in rows)-min(r['boundaries_ns'][k] for r in rows))/1e6 for k in names},'master_observed_window_ms':(max(r['boundaries_ns']['master_reply'] for r in rows)-min(r['boundaries_ns']['master_start'] for r in rows))/1e6,'last_master_reply':ordered[-1] if ordered else None,'last10_master_reply':{k:stats([r['ms'][k] for r in ordered[-10:]]) for k in segments+['master_total']},'rows':rows}
    results.append(summary)
a.output.write_text(json.dumps({'method':'requestID links Master/Cubelet; returned sandboxID links formal Shim; all timestamps same host wallclock, not CPU durations; no guest clocks; log timing may include scheduling/buffering','segments':segments,'runs':results},indent=2))
for r in results:print(json.dumps({k:v for k,v in r.items() if k not in ('rows','last10_master_reply')},indent=2))
