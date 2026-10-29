#!/usr/bin/env python3
"""Export allowlisted anonymous measurements; verify the public package offline.

Python standard library only. No network, remote actions, or source mutations.
Usage: export_public_data.py --root PRIVATE_ARTIFACT --output NEW_PUBLIC_DIR
       verify_public_data.py --verify PUBLIC_DIR
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys

METRICS = ('wall_ms', 'create_mean_ms', 'create_p95_ms', 'create_max_ms')
GROUPS = ('A_before', 'U', 'P', 'C', 'S', 'F', 'A_after')
ROUND = re.compile(r'^F-b([1-5])-p[1-5]$')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def numeric(x):
    return type(x) in (float, int) and math.isfinite(x)


def stats(values):
    xs = sorted(values)
    return {'n': len(xs), 'mean': statistics.mean(xs) if xs else None,
            'median': statistics.median(xs) if xs else None,
            'min': xs[0] if xs else None, 'max': xs[-1] if xs else None,
            'p95': xs[math.ceil(.95 * len(xs)) - 1] if xs else None,
            'sample_sd': statistics.stdev(xs) if len(xs) > 1 else None}


def round_stats(values):
    xs = [x for x in values if numeric(x)]
    return {'rounds': len(xs), 'median': statistics.median(xs) if xs else None,
            'min': min(xs) if xs else None, 'max': max(xs) if xs else None}


def equal(a, b, label):
    if numeric(a) and numeric(b):
        if not math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError('numeric mismatch at ' + label)
    elif isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            raise ValueError('field mismatch at ' + label)
        for k in a:
            equal(a[k], b[k], label + '.' + k)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            raise ValueError('length mismatch at ' + label)
        for i, (x, y) in enumerate(zip(a, b)):
            equal(x, y, label + '.' + str(i))
    elif a != b or type(a) is not type(b):
        raise ValueError('value mismatch at ' + label)


def csv_write(path, fields, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(row.get(k), ensure_ascii=False) if isinstance(row.get(k), (dict, list)) else row.get(k) for k in fields})


def anonymous(run, phase, seq):
    if not ROUND.fullmatch(run) or phase not in ('formal', 'warmup') or type(seq) is not int:
        raise ValueError('unrecognized anonymous request coordinates')
    return run + '-' + phase + '-' + f'{seq:03d}'


def verify(directory):
    comp = read(directory / 'comparison.json')
    samples = read(directory / 'benchmark-samples.json')['rounds']
    runs = comp['runs']
    assert len(runs) == len(samples) == 35
    assert len({r['id'] for r in runs}) == 35
    by_run = {r['id']: r for r in runs}
    for raw in samples:
        rid = raw['round']
        assert len(raw['formal']) == 100
        assert sorted(r['seq'] for r in raw['formal']) == list(range(1, 101))
        assert all(r['successful'] for r in raw['formal'])
        assert raw['summary']['successful'] == 100 and raw['summary']['errors'] == 0
        s = stats([r['create_ms'] for r in raw['formal']])
        got = {'wall_ms': raw['summary']['total_time_s'] * 1000,
               'create_mean_ms': s['mean'], 'create_p95_ms': s['p95'], 'create_max_ms': s['max']}
        equal(got, by_run[rid]['metrics'], rid + '.metrics')
        assert by_run[rid]['valid'] and by_run[rid]['counts']['successful_rows'] == 100
    for group in GROUPS:
        rr = [r for r in runs if r['group'] == group]
        assert len(rr) == 5 and sorted(r['block'] for r in rr) == [1, 2, 3, 4, 5]
        assert comp['groups'][group]['status'] == 'complete'
        for metric in METRICS:
            equal(stats([r['metrics'][metric] for r in rr]), comp['groups'][group]['metrics'][metric], group + '.' + metric)
    assert len(comp['contrasts']) == 6
    for contrast in comp['contrasts']:
        for metric, c in contrast['metrics'].items():
            baseline = comp['groups'][contrast['baseline']]['metrics'][metric]
            candidate = comp['groups'][contrast['candidate']]['metrics'][metric]
            equal(baseline, c['baseline'], contrast['id'] + '.baseline')
            equal(candidate, c['candidate'], contrast['id'] + '.candidate')
            delta = candidate['median'] - baseline['median']
            equal(delta, c['median_delta_ms'], contrast['id'] + '.median_delta')
            equal(100 * delta / baseline['median'], c['median_percent'], contrast['id'] + '.median_percent')
            deltas, percents = [], []
            for pair in c['paired_rounds']:
                b = by_run[pair['baseline_id']]['metrics'][metric]
                a = by_run[pair['candidate_id']]['metrics'][metric]
                equal(a-b, pair['delta_ms'], contrast['id'] + '.pair')
                equal(100 * (a-b) / b, pair['percent'], contrast['id'] + '.percent')
                deltas.append(a-b)
                percents.append(100 * (a-b)/b)
            assert len(deltas) == 5
            equal(stats(deltas), c['paired_delta_ms'], contrast['id'] + '.paired_stats')
            equal(stats(percents), c['paired_percent'], contrast['id'] + '.paired_percent_stats')
    req = read(directory / 'requests.json')['requests']
    stage = read(directory / 'stage-summary.json')
    definitions = read(directory / 'stage-definitions.json')['stages']
    assert len(req) == 515 and len(definitions) == len(stage['stages']) == 79
    assert len({r['request_id'] for r in req}) == 515
    assert Counter(r['phase'] for r in req) == {'formal': 500, 'warmup': 15}
    round_ids = sorted({r['round'] for r in req})
    assert len(round_ids) == 5
    for r in req:
        assert r['request_id'] == anonymous(r['round'], r['phase'], r['anonymous_index'])
        assert set(r['stages']) == set(definitions)
    for rid in round_ids:
        assert Counter(r['phase'] for r in req if r['round'] == rid) == {'formal': 100, 'warmup': 3}
        for phase, count in (('formal', 100), ('warmup', 3)):
            assert sorted(r['anonymous_index'] for r in req if r['round'] == rid and r['phase'] == phase) == list(range(1, count + 1))
    validated_stage_rows = 0
    for key, summary in stage['stages'].items():
        pooled, missing = [], Counter()
        for row in summary['rounds']:
            rr = [r for r in req if r['round'] == row['round'] and r['phase'] == 'formal' and r['eligible_success']]
            assert len(rr) == 100
            cells = [r['stages'][key] for r in rr]
            statuses = Counter(c['status'] for c in cells)
            vals = [c['ms'] for c in cells if c['status'] == 'measured' and numeric(c['ms'])]
            s = stats(vals)
            equal(dict(statuses), row['statuses'], key + '.statuses')
            equal(s['n'], row['n'], key + '.n')
            assert row['denominator'] == 100
            for output, field in (('mean_ms', 'mean'), ('median_ms', 'median'), ('p95_ms', 'p95'), ('max_ms', 'max')):
                equal(s[field], row[output], key + '.' + output)
            if row.get('max_request_id'):
                match = [r for r in rr if r['request_id'] == row['max_request_id']]
                assert len(match) == 1
                equal(match[0]['stages'][key]['ms'], row['max_ms'], key + '.max_request')
            pooled.extend(vals)
            missing.update({k:v for k,v in statuses.items() if k != 'measured'})
            validated_stage_rows += 1
        equal(len(pooled), summary['observed_requests'], key + '.coverage')
        assert summary['possible_requests'] == 500
        assert summary['full_coverage_rounds'] == sum(r['n'] == r['denominator'] for r in summary['rounds'])
        equal(dict(missing), summary['missing_or_nonmeasurement_statuses'], key + '.missing')
        equal(round_stats([r['mean_ms'] for r in summary['rounds']]), summary['round_mean_ms'], key + '.round_means')
        equal(round_stats([r['p95_ms'] for r in summary['rounds']]), summary['round_p95_ms'], key + '.round_p95')
        p = stats(pooled)
        for output, field in (('n','n'), ('mean_ms','mean'), ('median_ms','median'), ('p95_ms','p95'), ('max_ms','max')):
            equal(p[field], summary['request_pool_descriptive_only'][output], key + '.pool.' + output)
    for rid, net in read(directory / 'network-details.json')['rounds'].items():
        ids = {r['request_id']:r for r in req if r['round'] == rid}
        for phase, info in net['phases'].items():
            if phase in ('formal', 'warmup'):
                assert info['owned_instance_count'] == (100 if phase == 'formal' else 3)
            for name, s in info['stages'].items():
                for sample in s['samples']:
                    assert sample['request_id'] in ids and ids[sample['request_id']]['phase'] == phase
                    assert numeric(sample['duration_ns'])
    if (directory / 'SOURCE-MANIFEST.json').exists():
        provenance = read(directory / 'SOURCE-MANIFEST.json')
        for record in provenance['public_files']:
            assert sha(directory / record['path']) == record['sha256'], 'public file checksum mismatch: ' + record['path']
    return {'status':'passed', 'rounds':35, 'successful_formal_requests':3500, 'complete_groups':7,
            'contrasts':6, 'validated_contrast_metric_sets':24, 'profiled_requests':515,
            'profiled_formal':500, 'profiled_warmup':15, 'stages':79,
            'validated_stage_rounds':validated_stage_rows,
            'comparison_method':'All four metrics, seven group distributions and six block/ordinal contrasts recomputed from public samples.',
            'stage_method':'395 mean/median/nearest-rank P95/max/coverage/status rows and 79 aggregate summaries recomputed from the 500 eligible formal requests; warmup excluded.',
            'numeric_tolerance':{'relative':1e-12, 'absolute_ms':1e-12},
            'scope':'Offline public-data consistency only; raw logs, ownership, clock domain and deployment provenance are not independently reverified.'}


def export(root, output):
    if output.exists():
        raise ValueError('output must be a new directory')
    comp_path = root / 'analysis/comparison/comparison.json'
    comp = read(comp_path)
    assert len(comp['runs']) == 35 and all(r['valid'] for r in comp['runs'])
    assert all(g['status'] == 'complete' and g['valid_rounds'] == 5 for g in comp['groups'].values())
    output.mkdir(parents=True)
    sources = []
    sensitive = set()
    def source(path, logical, targets):
        sources.append({'source_id':logical, 'source_sha256':sha(path), 'source_bytes':path.stat().st_size, 'public_outputs':targets})
    def note_sensitive(obj):
        if isinstance(obj, dict):
            for k,v in obj.items():
                if k in ('sandbox_id','request_id','host_request_id','instance_id','boot_id','bootid','template') and isinstance(v,str) and len(v) >= 8:
                    sensitive.add(v)
                note_sensitive(v)
        elif isinstance(obj,list):
            for v in obj: note_sensitive(v)
    safe_comp = {'schema_version':1, 'units':'ms', 'groups':{}, 'runs':[], 'contrasts':comp['contrasts'],
                 'statistical_unit':'one c100 round', 'expected_rounds_per_group':5,
                 'pairing':'U/P/C/S/F use Latin blocks; A anchors use descriptive ordinal pairing across separated periods, not same-block treatment attribution.'}
    samples = []
    for r in comp['runs']:
        path = root / r['raw']
        raw = read(path)
        note_sensitive(raw)
        summary = {k:raw['summary'][k] for k in ('successful','errors','success_rate','throughput_qps','total_time_s')}
        formal = [{'seq':x['seq'], 'create_ms':x['create_ms'], 'successful':not bool(x.get('error'))} for x in raw['raw']]
        samples.append({'round':r['id'], 'summary':summary, 'formal':sorted(formal,key=lambda x:x['seq'])})
        safe_comp['runs'].append({k:r[k] for k in ('id','group','block','order','valid','metrics')})
        safe_comp['runs'][-1]['counts'] = r['evidence']
        source(path, 'benchmark.' + r['id'], ['benchmark-samples.json','comparison.json','rounds.csv','contrasts.csv'])
    for g,v in comp['groups'].items():
        safe_comp['groups'][g] = {'factors':v['metadata']['factors'], **{k:v[k] for k in ('observed_rounds','valid_rounds','expected_rounds','status','metrics')}}
    write(output / 'comparison.json',safe_comp)
    write(output / 'benchmark-samples.json',{'schema_version':1,'units':'ms except total_time_s (seconds), success_rate (fraction), throughput_qps (requests/s)', 'rounds':samples})
    round_rows = [{**{k:r[k] for k in ('id','group','block','order','valid')}, **r['metrics'], **r['counts']} for r in safe_comp['runs']]
    csv_write(output/'rounds.csv', list(round_rows[0]), round_rows)
    contrast_rows=[]
    for c in safe_comp['contrasts']:
        for metric,v in c['metrics'].items():
            contrast_rows.append({'contrast':c['id'],'baseline':c['baseline'],'candidate':c['candidate'],'metric':metric,
                'baseline_median':v['baseline']['median'],'candidate_median':v['candidate']['median'],
                'median_delta_ms':v['median_delta_ms'],'median_percent':v['median_percent'],
                'paired_delta_mean_ms':v['paired_delta_ms']['mean'],'paired_delta_median_ms':v['paired_delta_ms']['median'],
                'paired_delta_min_ms':v['paired_delta_ms']['min'],'paired_delta_max_ms':v['paired_delta_ms']['max'],
                'paired_rounds':v['paired_rounds'],'warnings':c['warnings']})
    csv_write(output/'contrasts.csv',list(contrast_rows[0]),contrast_rows)
    source(comp_path,'comparison.verified',['comparison.json','rounds.csv','contrasts.csv'])
    requests, sidmap, definitions = [], {}, None
    profile_paths = sorted(p for p in (root/'analysis').glob('bottleneck-F-b?-p?/bottleneck.json'))
    assert len(profile_paths)==5
    for path in profile_paths:
        rid = path.parent.name.removeprefix('bottleneck-')
        data=read(path)
        note_sensitive(data)
        if definitions is None: definitions=data['stage_definitions']
        else: equal(definitions,data['stage_definitions'],'stage definitions across rounds')
        for r in data['requests']:
            index = r['seq'] if r['phase'] == 'formal' else int(r['client_source']['json_pointer'].rsplit('/', 1)[1]) + 1
            aid=anonymous(rid,r['phase'],index)
            assert (rid,r['sandbox_id']) not in sidmap
            sidmap[rid,r['sandbox_id']]=aid
            requests.append({'round':rid,'request_id':aid,'phase':r['phase'],'seq':r['seq'],'anonymous_index':index,
                'eligible_success':r['eligible_success'],'client_status':r['client_status'],
                'stages':{k:{'ms':v['ms'],'status':v['status']} for k,v in r['stages'].items()}})
        source(path,'bottleneck.'+rid,['requests.json','stage-definitions.json','stage-summary.json','stage-rounds.csv','network-details.json'])
    requests.sort(key=lambda r:(r['round'],r['phase'],r['seq']))
    write(output/'requests.json',{'schema_version':1,'units':'ms','request_id_method':'round + phase + formal client sequence or one-based warmup array position, with no original identifier retained','requests':requests})
    write(output/'stage-definitions.json',{'schema_version':1,'stages':definitions})
    stage_path=root/'analysis/stages-five-rounds/stage-summary.json'
    stages=read(stage_path)
    safe_stage={k:stages[k] for k in ('schema_version','units','status','expected_rounds','included_rounds','statistical_unit','summary_method','limitations')}
    safe_stage['stages']={}
    stage_rows=[]
    for key,v in stages['stages'].items():
        clean={k:x for k,x in v.items() if k!='rounds'}
        clean['rounds']=[]
        for row in v['rounds']:
            rr={k:x for k,x in row.items() if k not in ('source','max_request')}
            rr['max_request_id']=sidmap[(row['round'],row['max_request']['sandbox_id'])] if row.get('max_request') else None
            clean['rounds'].append(rr)
            stage_rows.append(rr)
        safe_stage['stages'][key]=clean
    write(output/'stage-summary.json',safe_stage)
    csv_write(output/'stage-rounds.csv',list(stage_rows[0]),stage_rows)
    source(stage_path,'stage-summary.verified',['stage-summary.json','stage-rounds.csv'])
    network={}
    for rid in sorted({r['round'] for r in requests}):
        paths=list((root/'raw'/rid).glob('runs/*/analysis/network-details.json'))
        assert len(paths)==1
        path=paths[0]
        net=read(path)
        note_sensitive(net)
        clean={'duration_unit':net['duration_unit'],'phases':{}}
        for phase,p in net['phases'].items():
            pclean={k:p[k] for k in ('owned_instance_count','expected_request_count')}
            pclean['stages']={}
            for key,s in p['stages'].items():
                sc={k:s[k] for k in ('stats_ns','successful_stats_ns','coverage','status_counts','outcomes','additivity','parent')}
                sc['samples']=[{'request_id':sidmap[(rid,x['instance_id'])], 'outcome':x['outcome'], 'duration_ns':x['duration_ns']} for x in s['samples']]
                pclean['stages'][key]=sc
            clean['phases'][phase]=pclean
        network[rid]=clean
        source(path,'network-details.'+rid,['network-details.json'])
    write(output/'network-details.json',{'schema_version':1,'units':'ns (not ms)','rounds':network,
        'limitations':['23 original network fields remain separate from the 79-stage summary.','Missing observations are not zero. Aggregate network percentiles retain the original parser definition; samples are provided, no new causal claim is made.']})
    (output/'verify_public_data.py').write_text(Path(__file__).read_text())
    source(Path(__file__),'export-and-verify-tool',['verify_public_data.py'])
    (output/'README.zh-CN.md').write_text('''# EPYC 9654 机器：100 并发 profiler 公开派生数据

日期：2026-10-29。状态：35 轮计时、7 组各五轮、六类对照；五轮完整观测包含 500 formal + 15 warmup。这里是原始证据的匿名派生投影，不是原始日志包。

## 文件与复核

- `benchmark-samples.json`：35 轮 summary 与 3500 个正式 create_ms。`total_time_s` 单位秒，其他请求耗时毫秒；warmup 不计入整轮计时。
- `comparison.json`、`rounds.csv`、`contrasts.csv`：四项指标的逐轮、组内和配对描述统计；七组因素矩阵。U/P/C/S/F 按 block 配对，A_before/A_after 按序号仅描述前后漂移。保留所有快慢轮，没有排除异常值。
- `requests.json`：515 个匿名请求各 79 项值与状态，正式/预热严格分开。编号由轮次、phase 与正式客户端 seq 或 warmup 数组序号生成（原 warmup seq 为 0，另保留 anonymous_index），跨表可关联，不含原 SID/RequestId。
- `stage-definitions.json`、`stage-summary.json`、`stage-rounds.csv`：79 项定义、五轮汇总、395 行统计。P95 用 nearest-rank；轮间统计以五轮为单位，500 请求合并分布仅供描述。包含/并行/残差阶段不能相加，缺失不补零，marker 不作耗时样本。
- `network-details.json`：五轮原 profiler 网络 23 字段的匿名样本、统计及覆盖。单位为 ns，与上述 ms 区分；保留原网络 parser 分位数口径。
- `verify_public_data.py`：仅 Python 标准库、无网络或远端操作。运行 `python3 -I verify_public_data.py --verify .`，从公开值复核 35 轮、7 组、6 类对照的四项指标，以及 500 formal 的全部 395 行与 79 项汇总。以 1e-12 相对/绝对容差验证浮点重算，导出原值不作四舍五入。
- `verification.json`：导出时的离线验证结果；`SOURCE-MANIFEST.json`：每个未公开源文件的逻辑编号、原件 SHA256、对应公开文件 SHA256；`SHA256SUMS`：公开包逐文件校验值（不自校验该清单）。

## 未公开与证据边界

未公开原始日志、配置、身份快照、journal、地址、用户名路径、SID/RequestId、boot/time namespace、绝对时间轴、源码 bundle、二进制或凭据。原始配置与逐次部署/清理门禁不在本子包中；35 valid 和因素身份是既有本地证据的验收结果，公开数值重算不能重新证明环境同一性、资源归属或时钟兼容。原件哈希只固定原件字节，不能让读者从哈希恢复日志。

每轮本地已确认的入口、Master、Cubelet、Shim 关联在导出中保留为同一匿名请求的阶段值；公开值可重算统计，无法从未公开日志独立复做解析或校验原记录时间戳。warmup 的 15 个请求保留逐阶段值，但不混入 500 formal 的汇总。旧 A 组没有逐请求 SID/warmup 导出，计时 100 成功仍保留。

没有新增性能测试或优化。额外 Go runtime trace 因部署前门禁停止，真实样本为 0；不能据阶段差值证明 SQL 池或日志锁耗时。U→F 的中位数和均值方向不一致，五轮证据不足以声称固定开销、零开销或性能收益。
''')
    result=verify(output)
    payloads={p.name:p.read_text() for p in output.iterdir() if p.is_file()}
    forbidden_patterns=(r'\b(?:\d{1,3}\.){3}\d{1,3}\b',r'/(?:Users|home|root)/',r'\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b')
    for name,payload in payloads.items():
        if name.endswith('.py'): continue  # source contains literal scanner patterns, not deployment values
        for value in sensitive:
            if value in payload: raise ValueError('original identifier detected in public file: '+name)
        if any(re.search(pattern,payload) for pattern in forbidden_patterns):
            raise ValueError('forbidden address/path/UUID pattern in public file: '+name)
    result['privacy_projection']={'method':'allowlisted fields only; exact original identifier scan and address/absolute user path/UUID pattern scan','status':'passed','original_identifiers_retained':0}
    write(output/'verification.json',result)
    public=[{'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(output.iterdir()) if p.is_file()]
    indexed={p['path']:p for p in public}
    for record in sources:
        record['public_outputs']=[indexed[name] for name in record['public_outputs']]
    write(output/'SOURCE-MANIFEST.json',{'schema_version':1,'kind':'private-original to public-derived provenance','source_paths':'Logical IDs only; original private paths not published.', 'source_files':sources,'public_files':public})
    (output/'SHA256SUMS').write_text(''.join(sha(p)+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.is_file() and p.name!='SHA256SUMS'))
    verify(output)
    return {'status':'passed','files':len(list(output.iterdir())),'bytes':sum(p.stat().st_size for p in output.iterdir()),'verification':result}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--verify',type=Path)
    args=p.parse_args()
    if args.verify:
        result=verify(args.verify.resolve(strict=True))
    elif args.root and args.output:
        result=export(args.root.resolve(strict=True),args.output.resolve())
    else:
        p.error('choose --verify DIR or --root PRIVATE --output NEW_DIR')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
