#!/usr/bin/env node
// Direct Go duration fields, never reconstructed by subtracting wallclock logs.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { loadProfile, stats } from './analyze.mjs';

const PHASES = ['formal', 'warmup', 'unknown_phase'];
export const NETWORK_FIELDS = {
  'create stages': ['total', 'ensure_route', 'acquire_tap', 'reserve_ports', 'write_tmp', 'commit_creating', 'apply_port_mappings', 'register_cubevs_tap', 'push_egress', 'commit_success', 'commit_active'],
  'ensure precheck': ['total', 'lock_wait', 'inmem_lookup', 'exists_check', 'legacy_check', 'create_state'],
  'register cubevs tap': ['total'],
  'tap fd handoff': ['total', 'lock_wait', 'snapshot', 'open_tap', 'dup_fd'],
};
const slug = name => name.replaceAll(' ', '_');
const UNITS = { ns: 1, us: 1000, 'µs': 1000, 'μs': 1000, ms: 1e6, s: 1e9, m: 60e9, h: 3600e9 };
export function parseGoDurationNs(value) {
  if (value === '0') return 0;
  if (typeof value !== 'string' || !value) return null;
  const pieces = [...value.matchAll(/(\d+(?:\.\d+)?|\.\d+)(ns|us|µs|μs|ms|s|m|h)/g)];
  if (!pieces.length || pieces.map(x => x[0]).join('') !== value) return null;
  const total = pieces.reduce((n, x) => n + Number(x[1]) * UNITS[x[2]], 0);
  // JavaScript numbers cannot preserve nanoseconds beyond this bound.
  return Number.isFinite(total) && total <= Number.MAX_SAFE_INTEGER ? total : null;
}
function clockNs(value) {
  if (typeof value !== 'string') return null;
  const m = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/);
  if (!m) return null;
  const ms = Date.parse(m[1] + m[3]);
  return Number.isFinite(ms) ? BigInt(ms) * 1000000n + BigInt((m[2] ?? '').padEnd(9, '0')) : null;
}
export function parseNetworkRecord(record) {
  const m = record.LogContent?.match(/^network runtime (create stages|ensure precheck|register cubevs tap|tap fd handoff): (.*)$/);
  if (!m) return null;
  const fields = {}, repeated = [];
  for (const token of m[2].split(/\s+/)) {
    const equal = token.indexOf('=');
    if (equal < 1) continue;
    const key = token.slice(0, equal);
    if (Object.hasOwn(fields, key)) repeated.push(key);
    fields[key] = token.slice(equal + 1);
  }
  // The similarly named informational registration/config log is not a timer.
  if (m[1] === 'register cubevs tap' && !Object.hasOwn(fields, 'total') && Object.hasOwn(fields, 'ifindex')) return null;
  return { kind: m[1], fields, repeated };
}

export function analyzeNetworkDetails({ profile, records = [], inputIntegrity = {} }) {
  if (!profile?.phases) throw new Error('A loadProfile result is required');
  const owners = new Map(), conflicts = new Set();
  for (const phase of PHASES) for (const d of profile.phases[phase]?.create_container_detail?.details ?? []) {
    if (typeof d.instance_id !== 'string' || !d.instance_id) continue;
    if (owners.has(d.instance_id) && owners.get(d.instance_id) !== phase) conflicts.add(d.instance_id);
    owners.set(d.instance_id, phase);
  }
  for (const id of conflicts) owners.delete(id);
  const start = clockNs(profile.capture?.started_at), end = clockNs(profile.capture?.ended_at);
  const windowValid = start !== null && end !== null && start <= end;
  const integrity = { ...inputIntegrity, matched_records: 0, foreign_or_unattributed: 0,
    mismatched_instance_id: 0, outside_capture_window: 0, time_unverifiable: 0,
    repeated_field_records: 0, accepted_records: 0, duplicate_kind_instances: 0,
    conflicting_ownership_ids: [...conflicts], capture_window_verified: windowValid };
  const groups = new Map([...owners].map(([id, phase]) => [id, { instance_id: id, phase, operations: {} }]));
  for (const record of records) {
    const parsed = parseNetworkRecord(record);
    if (!parsed) continue;
    integrity.matched_records++;
    const { kind, fields, repeated } = parsed, id = fields.sandbox_id;
    if (record.InstanceId && record.InstanceId !== id) { integrity.mismatched_instance_id++; continue; }
    if (!owners.has(id)) { integrity.foreign_or_unattributed++; continue; }
    const timestamp = record['@timestamp'] ?? record.Timestamp ?? record.timestamp;
    const time = clockNs(timestamp);
    if (!windowValid || time === null) { integrity.time_unverifiable++; continue; }
    if (time < start || time > end) { integrity.outside_capture_window++; continue; }
    if (repeated.length) { integrity.repeated_field_records++; continue; }
    const outcome = fields.success === 'true' ? 'success' : fields.success === 'false' ? 'failure' : 'unknown';
    const durations = {};
    for (const field of NETWORK_FIELDS[kind]) {
      const raw = fields[field], ns = parseGoDurationNs(raw);
      // A zero accumulator may denote a skipped/failed stage; do not claim a zero-cost execution.
      const status = raw === undefined ? 'missing_field' : ns === null ? 'invalid_duration' : ns === 0 ? 'unknown_execution' : 'measured';
      durations[field] = { raw: raw ?? null, recorded_ns: ns, duration_ns: status === 'measured' ? ns : null, status };
    }
    const operation = { timestamp, request_id: record.RequestId ?? null, outcome,
      idempotent: fields.idempotent === 'true' ? true : fields.idempotent === 'false' ? false : null,
      attempts: /^\d+$/.test(fields.attempts ?? '') ? Number(fields.attempts) : null,
      port_mappings: /^\d+$/.test(fields.port_mappings ?? '') ? Number(fields.port_mappings) : null, durations };
    (groups.get(id).operations[slug(kind)] ??= []).push(operation);
    integrity.accepted_records++;
  }
  const phases = {};
  for (const phase of PHASES) {
    const instances = [...groups.values()].filter(x => x.phase === phase), stages = {};
    for (const [kind, fields] of Object.entries(NETWORK_FIELDS)) {
      const operationKey = slug(kind);
      for (const field of fields) {
        const samples = [], statusCounts = { measured: 0, missing_record: 0, missing_field: 0, invalid_duration: 0, unknown_execution: 0, ambiguous_duplicate: 0 };
        const outcomes = { success: 0, failure: 0, unknown: 0 };
        let recordedInstances = 0, recordCount = 0;
        for (const instance of instances) {
          const ops = instance.operations[operationKey] ?? [];
          recordCount += ops.length;
          if (ops.length) recordedInstances++;
          if (ops.length !== 1) { statusCounts[ops.length ? 'ambiguous_duplicate' : 'missing_record']++; continue; }
          const op = ops[0], d = op.durations[field];
          statusCounts[d.status]++; outcomes[op.outcome]++;
          if (d.duration_ns !== null) samples.push({ instance_id: instance.instance_id, outcome: op.outcome, duration_ns: d.duration_ns });
        }
        stages[`${operationKey}.${field}`] = { stats_ns: stats(samples.map(x => x.duration_ns)),
          successful_stats_ns: stats(samples.filter(x => x.outcome === 'success').map(x => x.duration_ns)),
          coverage: { owned_instances: instances.length, recorded_instances: recordedInstances, record_count: recordCount,
            measured_instances: samples.length, fraction: instances.length ? samples.length / instances.length : null },
          status_counts: statusCounts, outcomes, samples, additivity: 'do_not_sum',
          parent: field === 'total' ? null : `${operationKey}.total` };
      }
    }
    phases[phase] = { owned_instance_count: instances.length, expected_request_count: profile.phases[phase]?.expected_request_count ?? null, stages };
  }
  for (const instance of groups.values()) for (const ops of Object.values(instance.operations)) if (ops.length > 1) integrity.duplicate_kind_instances++;
  return { schema_version: 1, duration_unit: 'ns', phases, instances: [...groups.values()], integrity,
    phase_classification: profile.phase_classification ? { status: profile.phase_classification.status, method: profile.phase_classification.method } : null,
    interpretation: [
      'Stock v0.7.1 emits each timing record only on failure or when its own parent operation total >= 1 ms. Its child durations are a conditionally observed subset, not all requests.',
      'An instrumented build may remove this gate; actual coverage is reported. This parser does not infer the active gate from log presence.',
      'Missing records cannot be classified as fast: log loss, skips, failures and threshold suppression are distinct possibilities.',
      'Zero accumulators have unknown_execution status and are excluded from latency statistics. A failing stage can return before its timer assignment; zero does not prove it was unexecuted.',
      'Duplicate operation records for one instance are retained in per-instance output and excluded from stage statistics because retry/copy identity is unavailable.',
      'ensure precheck total includes create_state. create_state nests create stages; register_cubevs_tap includes registration logging and AddTAPDevice, while register cubevs tap total measures only AddTAPDevice.',
      'tap fd handoff snapshot/open_tap/dup_fd accumulate across attempts; open_tap includes branch overhead even when a cached FD avoids opening a TAP. lock_wait includes lookup/lock setup.',
      'Each duration uses Go monotonic time. Log emission timestamps do not define precise stage boundaries. Do not add nested stages or subtract unrelated aggregate percentiles.',
    ] };
}
export function networkCsv(result) {
  const rows = [['phase', 'stage', 'owned_instances', 'recorded_instances', 'measured_instances', 'coverage', 'mean_ns', 'p50_ns', 'p95_ns', 'min_ns', 'max_ns', 'missing_record', 'missing_field', 'invalid_duration', 'unknown_execution', 'ambiguous_duplicate']];
  for (const [phase, population] of Object.entries(result.phases)) for (const [stage, row] of Object.entries(population.stages)) rows.push([
    phase, stage, row.coverage.owned_instances, row.coverage.recorded_instances, row.coverage.measured_instances, row.coverage.fraction,
    ...['avg', 'p50', 'p95', 'min', 'max'].map(k => row.stats_ns?.[k] ?? null),
    ...['missing_record', 'missing_field', 'invalid_duration', 'unknown_execution', 'ambiguous_duplicate'].map(k => row.status_counts[k])]);
  return rows.map(row => row.map(x => x ?? '').join(',')).join('\n') + '\n';
}
export function writeNetworkDetails(directory, options = {}) {
  const root = path.resolve(directory), profile = loadProfile(root, options);
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'capture-manifest.json'), 'utf8'));
  const logInfo = manifest.logs?.cubelet_req ?? {};
  const file = path.resolve(root, logInfo.delta_path ?? 'evidence/cubelet_req-delta.log');
  if (!file.startsWith(root + path.sep)) throw new Error('Cubelet request log is outside capture directory');
  const bytes = fs.readFileSync(file), records = []; let malformed = 0;
  for (const line of bytes.toString('utf8').split('\n').filter(x => x.trim())) {
    try { const row = JSON.parse(line); if (!row || typeof row !== 'object' || Array.isArray(row)) throw new Error(); records.push(row); } catch { malformed++; }
  }
  const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
  if (logInfo.sha256 && sha256 !== logInfo.sha256) throw new Error('Cubelet request log SHA256 differs from manifest');
  const result = analyzeNetworkDetails({ profile, records, inputIntegrity: {
    path: path.relative(root, file), bytes: bytes.length, sha256, malformed_json_lines: malformed,
    final_newline_present: !bytes.length || bytes.at(-1) === 10, log_status: logInfo.status ?? 'unknown', log_gaps: logInfo.gaps ?? [],
  } });
  fs.writeFileSync(path.join(root, 'network-details.json'), JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
  fs.writeFileSync(path.join(root, 'network-details.csv'), networkCsv(result), { mode: 0o600 });
  return result;
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  if (!(args.length === 1 || (args.length === 3 && args[1] === '--phase-classification'))) {
    console.error('Usage: node network_details.mjs CAPTURE_DIRECTORY [--phase-classification FILE]'); process.exit(2);
  }
  const result = writeNetworkDetails(args[0], { phaseClassification: args[2] });
  console.log(JSON.stringify({ output: path.join(args[0], 'network-details.json'), integrity: result.integrity }));
}
