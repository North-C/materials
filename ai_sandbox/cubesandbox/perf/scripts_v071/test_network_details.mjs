import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { parseGoDurationNs, parseNetworkRecord, analyzeNetworkDetails, writeNetworkDetails, networkCsv } from './network_details.mjs';
const profile = () => ({ capture: { started_at: '2026-10-12T00:00:00Z', ended_at: '2026-10-12T00:00:01Z' },
  phases: Object.fromEntries([['formal', ['f1', 'f2']], ['warmup', ['w1']], ['unknown_phase', ['u1']]].map(([phase, ids]) =>
    [phase, { create_container_detail: { details: ids.map(instance_id => ({ instance_id })) } }])) });
const record = (content, id = 'f1', timestamp = '2026-10-12T00:00:00.123456789Z') => ({
  '@timestamp': timestamp, Module: 'Cubelet', InstanceId: id, LogContent: content, RetCode: 0 });
const create = (id = 'f1') => record(`network runtime create stages: sandbox_id=${id} total=19.51512ms success=true port_mappings=2 ensure_route=490ns acquire_tap=5.76µs reserve_ports=4.14µs write_tmp=123µs commit_creating=17.02µs apply_port_mappings=19.05725ms register_cubevs_tap=279.3µs push_egress=610ns commit_success=24.3µs commit_active=2.15µs`, id);
const build = records => analyzeNetworkDetails({ profile: profile(), records });
const stage = (result, name, phase = 'formal') => result.phases[phase].stages[name];

test('Go duration units including both micro signs, ASCII us and compound values', () => {
  for (const [value, expected] of [['1ns', 1], ['2µs', 2000], ['3μs', 3000], ['4us', 4000], ['.5ms', 500000], ['1.1s', 1100000000], ['1m2.3s', 62300000000], ['1h', 3600000000000], ['0s', 0], ['0', 0]]) assert.equal(parseGoDurationNs(value), expected);
  for (const value of ['-1ns', '+1ns', 'NaNms', '', undefined, '2', '1nstrash', '1e3ns', '10000000000h']) assert.equal(parseGoDurationNs(value), null);
});
test('real Cubelet schema retains nanoseconds, formal coverage and outcome', () => {
  const r = build([create(), create('w1'), create('u1')]);
  const tap = stage(r, 'create_stages.acquire_tap');
  assert.equal(tap.stats_ns.avg, 5760); assert.equal(tap.coverage.fraction, 0.5);
  assert.equal(tap.outcomes.success, 1); assert.equal(stage(r, 'create_stages.acquire_tap', 'warmup').stats_ns.count, 1);
  assert.equal(r.instances.length, 4); assert.equal(r.instances[0].operations.create_stages[0].port_mappings, 2);
});
test('all four schemas parsed while register informational log excluded', () => {
  const r = build([create(), record('network runtime ensure precheck: sandbox_id=f1 total=20ms success=true idempotent=false lock_wait=2us inmem_lookup=3us exists_check=4us legacy_check=5us create_state=19ms'),
    record('network runtime register cubevs tap: sandbox_id=f1 total=2ms success=true'),
    record('network runtime tap fd handoff: sandbox_id=f1 total=2ms success=true attempts=2 lock_wait=10us snapshot=20us open_tap=30us dup_fd=40us')]);
  assert.equal(stage(r, 'ensure_precheck.exists_check').stats_ns.avg, 4000);
  assert.equal(stage(r, 'register_cubevs_tap.total').stats_ns.avg, 2000000);
  assert.equal(stage(r, 'tap_fd_handoff.snapshot').stats_ns.avg, 20000);
  assert.equal(r.instances[0].operations.tap_fd_handoff[0].attempts, 2);
  assert.equal(parseNetworkRecord(record('network runtime register cubevs tap: sandbox_id=f1 ifindex=1 sandbox_ip=10.0.0.1')), null);
});
test('foreign, conflicting IDs, missing clock and outside nanosecond bounds rejected', () => {
  const r = build([create('foreign'), { ...create(), InstanceId: 'w1' }, { ...create(), '@timestamp': undefined },
    { ...create(), '@timestamp': '2026-10-12T00:00:01.000000001Z' }, { ...create(), '@timestamp': '2026-10-12T00:00:01Z' }]);
  assert.equal(r.integrity.foreign_or_unattributed, 1); assert.equal(r.integrity.mismatched_instance_id, 1);
  assert.equal(r.integrity.time_unverifiable, 1); assert.equal(r.integrity.outside_capture_window, 1);
  assert.equal(r.integrity.accepted_records, 1);
});
test('unverifiable capture window fails closed', () => {
  const p = profile(); delete p.capture.started_at;
  const r = analyzeNetworkDetails({ profile: p, records: [create()] });
  assert.equal(r.integrity.accepted_records, 0); assert.equal(r.integrity.capture_window_verified, false);
});
test('duplicate parent records retained but excluded from single-instance statistics', () => {
  const r = build([create(), create()]);
  assert.equal(stage(r, 'create_stages.acquire_tap').stats_ns, null);
  assert.equal(stage(r, 'create_stages.acquire_tap').status_counts.ambiguous_duplicate, 1);
  assert.equal(stage(r, 'create_stages.acquire_tap').coverage.record_count, 2);
  assert.equal(r.integrity.duplicate_kind_instances, 1); assert.equal(r.instances[0].operations.create_stages.length, 2);
});
test('zero accumulator, absent field, invalid duration and failure remain distinct', () => {
  const r = build([record('network runtime tap fd handoff: sandbox_id=f1 total=2ms success=false attempts=1 lock_wait=1us snapshot=0s open_tap=bad')]);
  assert.equal(stage(r, 'tap_fd_handoff.snapshot').status_counts.unknown_execution, 1);
  assert.equal(stage(r, 'tap_fd_handoff.snapshot').stats_ns, null);
  assert.equal(stage(r, 'tap_fd_handoff.open_tap').status_counts.invalid_duration, 1);
  assert.equal(stage(r, 'tap_fd_handoff.dup_fd').status_counts.missing_field, 1);
  assert.equal(stage(r, 'tap_fd_handoff.total').outcomes.failure, 1);
  assert.equal(stage(r, 'tap_fd_handoff.total').successful_stats_ns, null);
  assert.equal(stage(r, 'tap_fd_handoff.total').stats_ns.avg, 2000000);
});
test('explicit success needed; outer RetCode does not imply operation success', () => {
  const r = build([record('network runtime register cubevs tap: sandbox_id=f1 total=2ms')]);
  assert.equal(stage(r, 'register_cubevs_tap.total').outcomes.unknown, 1);
});
test('repeated key is malformed and cannot override measurement', () => {
  const r = build([record('network runtime register cubevs tap: sandbox_id=f1 total=2ms total=3ms success=true')]);
  assert.equal(r.integrity.repeated_field_records, 1); assert.equal(r.integrity.accepted_records, 0);
});
test('parent threshold selection and nonadditivity documented; missing never zero-filled', () => {
  const r = build([create()]);
  assert.match(r.interpretation.join(' '), />= 1 ms/); assert.match(r.interpretation.join(' '), /conditionally observed/);
  assert.equal(stage(r, 'create_stages.acquire_tap').additivity, 'do_not_sum');
  assert.equal(stage(r, 'create_stages.acquire_tap').status_counts.missing_record, 1);
  assert.match(networkCsv(r), /mean_ns,p50_ns,p95_ns/);
});
test('loadProfile entrypoint validates classification, manifest hash and input bounds', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'network-detail-'));
  try {
    const manifest = { started_at: '2026-10-12T00:00:00Z', ended_at: '2026-10-12T00:00:01Z', requests: 1,
      logs: { cubelet_req: { delta_path: 'req.log', status: 'captured', gaps: [] } } };
    const save = () => fs.writeFileSync(path.join(root, 'capture-manifest.json'), JSON.stringify(manifest));
    save(); fs.writeFileSync(path.join(root, 'owned-sandbox-ids.json'), JSON.stringify({ formal: ['f1'], warmup: [], unknown_phase: [] }));
    fs.writeFileSync(path.join(root, 'req.log'), JSON.stringify(create()) + '\nnot-json\n');
    const r = writeNetworkDetails(root);
    assert.equal(r.integrity.malformed_json_lines, 1); assert.equal(stage(r, 'create_stages.acquire_tap').coverage.fraction, 1);
    assert.ok(fs.existsSync(path.join(root, 'network-details.csv')));
    fs.writeFileSync(path.join(root, 'classification.json'), JSON.stringify({ status: 'unverified' }));
    assert.throws(() => writeNetworkDetails(root, { phaseClassification: path.join(root, 'classification.json') }), /classified status/);
    manifest.logs.cubelet_req.sha256 = 'wrong'; save(); assert.throws(() => writeNetworkDetails(root), /SHA256/);
    manifest.logs.cubelet_req.delta_path = '../outside'; save(); assert.throws(() => writeNetworkDetails(root), /outside capture/);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
