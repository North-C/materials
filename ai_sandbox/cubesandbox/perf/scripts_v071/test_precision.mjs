import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parsePrecisionJson, analyzePrecision, writePrecision, precisionCsv } from './precision.mjs';
const ORIGIN = '1791763200000000000';
const profile = () => ({ capture: { started_at: '2026-10-12T00:00:00Z', ended_at: '2026-10-12T00:00:01Z' }, phases:
  Object.fromEntries([['formal', ['f1', 'f2']], ['warmup', ['w1']], ['unknown_phase', []]].map(([phase, ids]) =>
    [phase, { create_container_detail: { details: ids.map(instance_id => ({ instance_id })) } }])) });
const span = (extra = {}) => ({ span_id: 1, parent_span_id: 0, stage: 'cubelet.request', kind: 'request', start_offset_us: 0, duration_us: 10.123,
  timing_source: 'monotonic_interval', success: true, ...extra });
const batch = (spans = [span()], id = 'f1', extra = {}) => ({ '@timestamp': '2026-10-12T00:00:00.1Z', InstanceId: id,
  LogContent: 'CUBE_PERF_TRACE ' + JSON.stringify({ schema_version: 1, component: 'cubelet', request_id: 'req', sandbox_id: id,
    origin_unix_ns: ORIGIN, spans, ...extra }) });
const shim = (stage = 'RestoreVm', extra = {}, trace = {}) => ({ InstanceId: 'f1', Action: 'Create', RetCode: 'Ok', CalleeAction: stage, CostTime: 0,
  PerfTrace: { SchemaVersion: 1, ClockId: '123:1791763200000000000', OperationId: 2, Kind: 'span', StartMonoNs: 100,
    EndMonoNs: 1099, DurationNs: 999, DurationUs: 0, DroppedRecordsBefore: 0, ...trace }, ...extra });
const marker = (stage, d, trace = {}) => shim(`TaskCreate.${stage}`, {}, { Kind: 'cumulative', StartMonoNs: 100,
  EndMonoNs: 100 + d, DurationNs: d, DurationUs: Math.floor(d / 1000), ...trace });
const build = (cubelet = [], records = [], p = profile()) => analyzePrecision({ profile: p, cubelet, shim: records });
const stage = (r, name) => r.phases.formal.stages[name];

test('lossless integer parser preserves ns and leaves escaped LogContent untouched', () => {
  const r = parsePrecisionJson('{"PerfTrace":{"StartMonoNs":9007199254740993,"DurationUs":0},"origin_unix_ns":1791763200000000001,"LogContent":"escaped \\"origin_unix_ns\\":123"}'.replaceAll('\\\\"', '\\"'));
  assert.equal(r.PerfTrace.StartMonoNs, '9007199254740993'); assert.equal(r.origin_unix_ns, '1791763200000000001');
  assert.equal(r.LogContent, 'escaped "origin_unix_ns":123');
});
test('Cubelet precise intervals preserve short duration, attribution, parent relation and coverage', () => {
  const r = build([batch([span(), span({ span_id: 2, parent_span_id: 1, stage: 'tiny', start_offset_us: 1, duration_us: .123 })]), batch([span()], 'w1')]);
  assert.equal(stage(r, 'cubelet.request.tiny.duration').stats_ns.avg, 123);
  assert.equal(stage(r, 'cubelet.request.tiny.duration').coverage.fraction, .5);
  assert.equal(r.instances[0].intervals.find(x => x.stage === 'tiny').parent_status, 'verified');
  assert.equal(r.phases.warmup.stages['cubelet.request.cubelet.request.duration'].coverage.fraction, 1);
});
test('duration backfill never becomes a confirmed timeline interval', () => {
  const r = build([batch([span(), span({ span_id: 2, parent_span_id: 1, stage: 'metric', timing_source: 'duration_backfill', duration_us: .5 })])]);
  const e = r.instances[0].intervals.find(x => x.stage === 'metric');
  assert.equal(e.duration_ns, 500); assert.equal(e.start_ns, null); assert.equal(e.end_ns, null); assert.equal(e.timeline_status, 'duration_only');
});
test('same-name workflow action and metric remain separate aggregate populations', () => {
  const r = build([batch([span(),
    span({ span_id: 2, parent_span_id: 1, stage: 'cgroup', kind: 'workflow_action', duration_us: 2 }),
    span({ span_id: 3, parent_span_id: 1, stage: 'cgroup', kind: 'metric', timing_source: 'duration_backfill', duration_us: 3 })])]);
  assert.equal(stage(r, 'cubelet.workflow_action.cgroup.duration').stats_ns.avg, 2000);
  assert.equal(stage(r, 'cubelet.metric.cgroup.duration').stats_ns.avg, 3000);
  assert.equal(stage(r, 'cubelet.workflow_action.cgroup.duration').coverage.repeated_instances, 0);
  assert.equal(stage(r, 'cubelet.metric.cgroup.duration').coverage.repeated_instances, 0);
  assert.equal(r.instances[0].intervals.length, 3);
});
test('multiple request or origin batches cannot masquerade as complete single-request coverage', () => {
  const p = profile(); p.phases.formal.expected_request_count = 100;
  const r = build([batch(), batch([span()], 'f1', { request_id: 'another-request' }),
    batch([span()], 'f2'), batch([span()], 'f2', { origin_unix_ns: '1791763200000000001' })], [], p);
  const coverage = r.phases.formal.cubelet_batch_coverage;
  assert.equal(coverage.expected_request_count, 100); assert.equal(coverage.observed_instances, 2);
  assert.equal(coverage.multiple_distinct_batch_instances, 2); assert.equal(coverage.single_batch_with_request_span_instances, 0);
  assert.equal(coverage.coverage_of_expected, 0); assert.equal(coverage.coverage_of_owned, 0);
  assert.deepEqual(coverage.instances.map(x => x.distinct_batches), [2, 2]);
});
test('exact duplicate batch and missing request root separately invalidate complete batch coverage', () => {
  const r = build([batch(), batch(), batch([span({ span_id: 2, parent_span_id: 1, kind: 'metric', stage: 'metric' })], 'f2')]);
  const coverage = r.phases.formal.cubelet_batch_coverage;
  assert.equal(coverage.duplicate_batch_instances, 1); assert.equal(coverage.single_unambiguous_batch_instances, 1);
  assert.equal(coverage.single_batch_with_request_span_instances, 0);
});
test('missing parent or out-of-parent interval is surfaced without inventing a parent', () => {
  const r = build([batch([span(), span({ span_id: 2, parent_span_id: 1, stage: 'overflow', duration_us: 20 }),
    span({ span_id: 3, parent_span_id: 99, stage: 'orphan' })])]);
  assert.equal(r.integrity.parent_relationship_anomalies, 2);
});
test('duplicate batches and duplicate span identities do not inflate distributions', () => {
  let r = build([batch(), batch()]); assert.equal(r.integrity.duplicate_batches, 2); assert.equal(Object.keys(r.phases.formal.stages).length, 0);
  r = build([batch([span(), span()])]); assert.equal(r.integrity.duplicate_events, 2); assert.equal(Object.keys(r.phases.formal.stages).length, 0);
  r = build([], [shim(), shim()]); assert.equal(r.integrity.duplicate_events, 2); assert.equal(r.instances[0].excluded_events.length, 2);
});
test('Shim ns endpoints are exact at >2^53 absolute offsets, while integer ms is irrelevant', () => {
  const r = build([], [shim('RestoreVm', {}, { StartMonoNs: '9007199254740993', EndMonoNs: '9007199254741992' })]);
  assert.equal(stage(r, 'shim.RestoreVm.duration').stats_ns.avg, 999);
  assert.equal(r.instances[0].intervals[0].start_ns, '9007199254740993'); assert.equal(r.integrity.shim_capture_delta_only, 1);
});
test('inconsistent duration, truncated us, unsafe integers and negative durations rejected', () => {
  const r = build([], [shim('a', {}, { DurationNs: 998 }), shim('b', {}, { DurationUs: 1 }),
    shim('c', {}, { StartMonoNs: Number.MAX_SAFE_INTEGER + 2 }), shim('d', {}, { DurationNs: -1 })]);
  assert.equal(r.integrity.invalid_records, 4); assert.equal(r.instances[0].intervals.length, 0);
});
test('cumulative subtraction uses same clock, same operation and named interval endpoints', () => {
  const r = build([], [marker('LoadSpec', 1000), marker('AcquireSandboxLock', 1123), marker('CheckSandboxState', 1125),
    marker('LoadSpec', 3000, { OperationId: 3 }), marker('AcquireSandboxLock', 9000, { ClockId: '999:123' })]);
  const e = r.instances[0].intervals.filter(x => x.kind === 'derived_interval');
  assert.equal(e.length, 2); assert.equal(e[0].duration_ns, 123); assert.equal(e[1].duration_ns, 2);
  assert.equal(e[0].stage, 'TaskCreate.LoadSpec→TaskCreate.AcquireSandboxLock');
});
test('duplicates, reversing order, changed origin and unknown markers prevent operation derivation', () => {
  for (const rows of [[marker('LoadSpec', 1000), marker('LoadSpec', 1000), marker('AcquireSandboxLock', 1100)],
    [marker('LoadSpec', 1100), marker('AcquireSandboxLock', 1000)],
    [marker('LoadSpec', 1000), marker('AcquireSandboxLock', 1100, { StartMonoNs: 200, EndMonoNs: 1300 })],
    [marker('LoadSpec', 1000), marker('NewUnknownMarker', 1100)]]) {
    const r = build([], rows); assert.equal(r.integrity.invalid_cumulative_operations, 1);
    assert.equal(r.instances[0].intervals.filter(x => x.kind === 'derived_interval').length, 0);
  }
});
test('missing checkpoints remain explicit gaps rather than a fabricated isolated stage', () => {
  const r = build([], [marker('CheckSandboxState', 1000), marker('StartSandbox', 2000)]);
  const e = r.instances[0].intervals.find(x => x.kind === 'derived_interval');
  assert.deepEqual(e.skipped_marker_names, ['TaskCreate.InitSandbox']); assert.equal(e.duration_ns, 1000);
});
test('ownership/window filter excludes foreign, conflicting, stale or malformed clocks', () => {
  const r = build([batch([], 'foreign'), { ...batch(), InstanceId: 'f2' },
    { ...batch(), '@timestamp': '2026-10-12T00:00:01.000000001Z' }, { ...batch(), '@timestamp': undefined },
    batch([span()], 'f1', { origin_unix_ns: '1' })], [shim('x', { Timestamp: '2026-10-11T00:00:00Z' })]);
  assert.equal(r.integrity.foreign, 1); assert.equal(r.integrity.id_conflicts, 1); assert.equal(r.integrity.outside_capture_window, 3);
  assert.equal(r.integrity.unverified_window, 1); assert.equal(r.instances[0].intervals.length, 0);
});
test('drop counter tracks per-clock maximum; repeated invocations exposed and unaggregated', () => {
  const r = build([], [shim('RestoreVm', {}, { DroppedRecordsBefore: 1 }), shim('RestoreVm', {}, { OperationId: 3, DroppedRecordsBefore: 4 })]);
  assert.equal(r.integrity.dropped_records_by_clock['123:1791763200000000000'], '4');
  assert.equal(stage(r, 'shim.RestoreVm.duration').stats_ns, null); assert.equal(stage(r, 'shim.RestoreVm.duration').coverage.repeated_instances, 1);
  assert.equal(r.instances[0].intervals.length, 2);
});
test('measured zero is valid; failure and unknown are separate from success', () => {
  const r = build([], [shim('zero', { RetCode: 'Err' }, { EndMonoNs: 100, DurationNs: 0 }), shim('unknown', { RetCode: undefined })]);
  assert.equal(stage(r, 'shim.zero.duration').stats_ns.avg, 0); assert.equal(stage(r, 'shim.zero.duration').successful_stats_ns, null);
  assert.equal(stage(r, 'shim.unknown.duration').outcomes.unknown, 1);
  assert.match(precisionCsv(r), /mean_ns,p50_ns,p95_ns/);
});
test('file entrypoint uses loadProfile, validates hashes and rejects stale classifications', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'precision-'));
  try {
    const manifest = { started_at: '2026-10-12T00:00:00Z', ended_at: '2026-10-12T00:00:01Z', requests: 1,
      logs: { cubelet_req: { delta_path: 'req.log' }, shim_stat: { delta_path: 'shim.log' } } };
    const save = () => fs.writeFileSync(path.join(root, 'capture-manifest.json'), JSON.stringify(manifest));
    save(); fs.writeFileSync(path.join(root, 'owned-sandbox-ids.json'), JSON.stringify({ formal: ['f1'], warmup: [], unknown_phase: [] }));
    fs.writeFileSync(path.join(root, 'req.log'), JSON.stringify(batch()) + '\n');
    fs.writeFileSync(path.join(root, 'shim.log'), JSON.stringify(shim()) + '\nbad-json\n');
    const r = writePrecision(root); assert.equal(stage(r, 'shim.RestoreVm.duration').coverage.fraction, 1);
    assert.equal(r.integrity.inputs.shim_stat.malformed_json_lines, 1); assert.ok(fs.existsSync(path.join(root, 'precision.csv')));
    manifest.logs.shim_stat.sha256 = 'wrong'; save(); assert.throws(() => writePrecision(root), /SHA256/);
    fs.writeFileSync(path.join(root, 'classification.json'), '{"status":"unverified"}');
    assert.throws(() => writePrecision(root, { phaseClassification: path.join(root, 'classification.json') }), /classified status/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
