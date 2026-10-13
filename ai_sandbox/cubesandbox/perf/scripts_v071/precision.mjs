#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { loadProfile, stats } from './analyze.mjs';
const PHASES = ['formal', 'warmup', 'unknown_phase'];
const MARKERS = ['LoadSpec', 'AcquireSandboxLock', 'CheckSandboxState', 'InitSandbox', 'StartSandbox', 'CreateContainer', 'PublishTaskEvent'].map(x => `TaskCreate.${x}`);
// Preserve serialized integer clocks before JSON.parse can round them. This only
// rewrites numeric values of known clock/identity fields, never string contents.
export function parsePrecisionJson(text) {
  const keys = new Set(['origin_unix_ns', 'OperationId', 'StartMonoNs', 'EndMonoNs', 'DurationNs', 'DurationUs', 'DroppedRecordsBefore']);
  let result = '', previous = 0;
  const pattern = /"(?:[^"\\]|\\.)*"\s*:\s*(?:"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null)|"(?:[^"\\]|\\.)*"/g;
  for (const m of text.matchAll(pattern)) {
    const kv = m[0].match(/^"([^"\\]+)"\s*:\s*(-?\d+)$/);
    if (kv && keys.has(kv[1])) { result += text.slice(previous, m.index) + `"${kv[1]}":"${kv[2]}"`; previous = m.index + m[0].length; }
  }
  return JSON.parse(result + text.slice(previous));
}
function integer(value) {
  if (typeof value === 'string' && /^\d+$/.test(value)) return BigInt(value);
  return Number.isSafeInteger(value) && value >= 0 ? BigInt(value) : null;
}
function numberNs(value) { const n = integer(value); return n !== null && n <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(n) : null; }
function clockNs(value) {
  if (typeof value !== 'string') return null;
  const m = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/);
  const base = m ? Date.parse(m[1] + m[3]) : NaN;
  return Number.isFinite(base) ? BigInt(base) * 1000000n + BigInt((m[2] ?? '').padEnd(9, '0')) : null;
}
const nonnegative = x => typeof x === 'number' && Number.isFinite(x) && x >= 0;
const outcome = x => x === true ? 'success' : x === false ? 'failure' : 'unknown';
export function analyzePrecision({ profile, cubelet = [], shim = [], inputIntegrity = {} }) {
  if (!profile?.phases) throw new Error('A loadProfile result is required');
  const owners = new Map(), conflicts = new Set();
  for (const phase of PHASES) for (const d of profile.phases[phase]?.create_container_detail?.details ?? []) {
    if (owners.has(d.instance_id) && owners.get(d.instance_id) !== phase) conflicts.add(d.instance_id);
    owners.set(d.instance_id, phase);
  }
  for (const id of conflicts) owners.delete(id);
  const start = clockNs(profile.capture?.started_at), end = clockNs(profile.capture?.ended_at);
  const windowValid = start !== null && end !== null && end >= start;
  const integrity = { ...inputIntegrity, conflicting_ownership_ids: [...conflicts], capture_window_verified: windowValid,
    foreign: 0, id_conflicts: 0, outside_capture_window: 0, unverified_window: 0, invalid_records: 0,
    legacy_shim_records_without_trace: 0, shim_capture_delta_only: 0, duplicate_events: 0, duplicate_batches: 0,
    invalid_cumulative_operations: 0, unknown_cumulative_markers: 0, parent_relationship_anomalies: 0, dropped_records_by_clock: {} };
  const events = [], invalid = [], batchGroups = new Map();
  const reject = (reason, id, stage = null) => { integrity.invalid_records++; invalid.push({ reason, instance_id: id ?? null, stage }); };
  function eligible(id, record, allowDeltaOnly = false) {
    if (!owners.has(id)) { integrity.foreign++; return false; }
    if (record.InstanceId && record.InstanceId !== id) { integrity.id_conflicts++; return false; }
    if (!windowValid) { integrity.unverified_window++; return false; }
    const raw = record['@timestamp'] ?? record.Timestamp ?? record.timestamp, time = clockNs(raw);
    if (time === null) {
      if (allowDeltaOnly && raw === undefined) { integrity.shim_capture_delta_only++; return true; }
      integrity.unverified_window++; return false;
    }
    if (time < start || time > end) { integrity.outside_capture_window++; return false; }
    return true;
  }
  for (const record of cubelet) {
    if (typeof record.LogContent !== 'string' || !record.LogContent.startsWith('CUBE_PERF_TRACE ')) continue;
    let batch; try { batch = parsePrecisionJson(record.LogContent.slice('CUBE_PERF_TRACE '.length)); } catch { reject('malformed_cubelet_batch'); continue; }
    const id = batch.sandbox_id;
    if (!eligible(id, record)) continue;
    const origin = integer(batch.origin_unix_ns);
    if (batch.schema_version !== 1 || batch.component !== 'cubelet' || !Array.isArray(batch.spans) ||
        typeof batch.request_id !== 'string' || !batch.request_id || origin === null) { reject('invalid_cubelet_batch_schema', id); continue; }
    if (record.RequestId && record.RequestId !== batch.request_id) { integrity.id_conflicts++; continue; }
    if (origin < start || origin > end) { integrity.outside_capture_window++; continue; }
    const key = JSON.stringify([id, batch.request_id, origin.toString()]);
    (batchGroups.get(key) ?? (batchGroups.set(key, []), batchGroups.get(key))).push(batch);
  }
  for (const [batchKey, batches] of batchGroups) {
    if (batches.length !== 1) { integrity.duplicate_batches += batches.length; continue; }
    const batch = batches[0], id = batch.sandbox_id, spanCounts = new Map();
    for (const span of batch.spans) spanCounts.set(span.span_id, (spanCounts.get(span.span_id) ?? 0) + 1);
    const batchEvents = [];
    for (const span of batch.spans) {
      const sid = integer(span.span_id), parent = integer(span.parent_span_id);
      if (sid === null || parent === null || sid === 0n || spanCounts.get(span.span_id) !== 1) {
        if (spanCounts.get(span.span_id) > 1) integrity.duplicate_events++;
        reject('invalid_or_duplicate_span_id', id, span.stage); continue;
      }
      if (typeof span.stage !== 'string' || !span.stage || !nonnegative(span.start_offset_us) || !nonnegative(span.duration_us) ||
          span.duration_us * 1000 > Number.MAX_SAFE_INTEGER || span.start_offset_us * 1000 > Number.MAX_SAFE_INTEGER ||
          !['monotonic_interval', 'duration_backfill'].includes(span.timing_source) || typeof span.success !== 'boolean') {
        reject('invalid_cubelet_span', id, span.stage); continue;
      }
      const position = span.timing_source === 'monotonic_interval';
      batchEvents.push({ instance_id: id, phase: owners.get(id), component: 'cubelet', stage: span.stage,
        kind: span.kind ?? 'span', clock_id: `cubelet:${batchKey}`, operation_id: batch.request_id,
        span_id: sid.toString(), parent_span_id: parent.toString(), origin_unix_ns: batch.origin_unix_ns.toString(),
        start_ns: position ? span.start_offset_us * 1000 : null,
        end_ns: position ? (span.start_offset_us + span.duration_us) * 1000 : null,
        inferred_start_ns: position ? null : span.start_offset_us * 1000,
        duration_ns: span.duration_us * 1000, outcome: outcome(span.success), timing_source: span.timing_source,
        timeline_status: position ? 'monotonic_interval' : 'duration_only', time_window_verification: 'batch_timestamp_and_origin',
        additivity: 'do_not_sum', identity: `cubelet:${batchKey}:${sid}` });
    }
    const parentMap = new Map(batchEvents.map(x => [x.span_id, x]));
    for (const event of batchEvents) {
      const parent = parentMap.get(event.parent_span_id);
      if (event.parent_span_id !== '0' && (!parent || (event.start_ns !== null && parent.start_ns !== null &&
          (event.start_ns < parent.start_ns - 1 || event.end_ns > parent.end_ns + 1)))) {
        integrity.parent_relationship_anomalies++; event.parent_status = 'unverified';
      } else event.parent_status = 'verified';
    }
    events.push(...batchEvents);
  }
  for (const record of shim) {
    if (!record.PerfTrace) { integrity.legacy_shim_records_without_trace++; continue; }
    const id = record.InstanceId, trace = record.PerfTrace;
    if (!eligible(id, record, true)) continue;
    if (record.Action !== 'Create') continue;
    const s = integer(trace.StartMonoNs), e = integer(trace.EndMonoNs), d = integer(trace.DurationNs), op = integer(trace.OperationId);
    const du = integer(trace.DurationUs), dropped = integer(trace.DroppedRecordsBefore);
    if (trace.SchemaVersion !== 1 || typeof trace.ClockId !== 'string' || !/^\d+:\d+$/.test(trace.ClockId) ||
        op === null || !['span', 'cumulative'].includes(trace.Kind) || s === null || e === null || d === null ||
        du === null || dropped === null || e < s || e - s !== d || d / 1000n !== du ||
        numberNs(trace.DurationNs) === null || typeof record.CalleeAction !== 'string' || !record.CalleeAction) {
      reject('invalid_shim_trace', id, record.CalleeAction); continue;
    }
    const old = BigInt(integrity.dropped_records_by_clock[trace.ClockId] ?? 0);
    integrity.dropped_records_by_clock[trace.ClockId] = (dropped > old ? dropped : old).toString();
    events.push({ instance_id: id, phase: owners.get(id), component: 'shim', stage: record.CalleeAction,
      kind: trace.Kind, clock_id: trace.ClockId, operation_id: op.toString(), span_id: null, parent_span_id: null,
      // Absolute process monotonic positions stay decimal strings to avoid u128 rounding.
      start_ns: s.toString(), end_ns: e.toString(), duration_ns: Number(d),
      outcome: record.RetCode === 'Ok' ? 'success' : record.RetCode === 'Err' ? 'failure' : 'unknown',
      timing_source: trace.Kind === 'span' ? 'monotonic_interval' : 'cumulative_checkpoint',
      timeline_status: trace.Kind === 'span' ? 'monotonic_interval' : 'checkpoint',
      time_window_verification: record['@timestamp'] || record.Timestamp || record.timestamp ? 'record_timestamp' : 'capture_delta_only',
      additivity: 'do_not_sum', identity: JSON.stringify(['shim', trace.ClockId, op.toString(), trace.Kind, record.CalleeAction]) });
  }
  const identities = new Map();
  for (const event of events) (identities.get(event.identity) ?? (identities.set(event.identity, []), identities.get(event.identity))).push(event);
  const accepted = [];
  for (const group of identities.values()) {
    if (group.length > 1) { integrity.duplicate_events += group.length; for (const event of group) event.exclusion = 'duplicate_identity'; }
    else accepted.push(group[0]);
  }
  const operationGroups = new Map();
  // Include duplicate raw markers here so a duplicate cannot disappear and manufacture an adjacent interval.
  for (const event of events.filter(x => x.component === 'shim' && x.kind === 'cumulative')) {
    const key = JSON.stringify([event.instance_id, event.clock_id, event.operation_id]);
    (operationGroups.get(key) ?? (operationGroups.set(key, []), operationGroups.get(key))).push(event);
  }
  const derived = [];
  for (const group of operationGroups.values()) {
    const known = group.every(x => MARKERS.includes(x.stage));
    if (!known) integrity.unknown_cumulative_markers += group.filter(x => !MARKERS.includes(x.stage)).length;
    const ordered = [...group].sort((a, b) => MARKERS.indexOf(a.stage) - MARKERS.indexOf(b.stage));
    const valid = known && new Set(group.map(x => x.stage)).size === group.length &&
      new Set(group.map(x => x.start_ns)).size === 1 && ordered.every((x, i) => !x.exclusion && (!i || BigInt(x.end_ns) > BigInt(ordered[i - 1].end_ns)));
    if (!valid) { integrity.invalid_cumulative_operations++; continue; }
    for (let i = 1; i < ordered.length; i++) {
      const a = ordered[i - 1], b = ordered[i], d = BigInt(b.end_ns) - BigInt(a.end_ns);
      derived.push({ ...b, stage: `${a.stage}→${b.stage}`, kind: 'derived_interval', start_ns: a.end_ns,
        duration_ns: Number(d), timing_source: 'adjacent_same_operation_checkpoint_difference', timeline_status: 'monotonic_interval',
        skipped_marker_names: MARKERS.slice(MARKERS.indexOf(a.stage) + 1, MARKERS.indexOf(b.stage)),
        outcome: a.outcome === 'success' && b.outcome === 'success' ? 'success' : 'unknown',
        identity: `${a.identity}->${b.identity}` });
    }
  }
  accepted.push(...derived);
  const batchesByInstance = new Map();
  for (const batches of batchGroups.values()) {
    const id = batches[0].sandbox_id;
    const summary = batchesByInstance.get(id) ?? { distinct_batches: 0, batch_records: 0, duplicate_batch_identities: 0 };
    summary.distinct_batches++;
    summary.batch_records += batches.length;
    if (batches.length > 1) summary.duplicate_batch_identities++;
    batchesByInstance.set(id, summary);
  }
  const phases = {};
  for (const phase of PHASES) {
    const ids = [...owners].filter(([, p]) => p === phase).map(([id]) => id), stageGroups = new Map(), stages = {};
    for (const event of accepted.filter(x => x.phase === phase)) {
      // Workflow actions and their propagated metrics intentionally share stage
      // names. Keep those independent measurements separate in the aggregate.
      const key = event.component === 'cubelet'
        ? `cubelet.${event.kind}.${event.stage}.duration`
        : `${event.component}.${event.stage}.${event.kind === 'cumulative' ? 'cumulative' : event.kind === 'derived_interval' ? 'derived' : 'duration'}`;
      (stageGroups.get(key) ?? (stageGroups.set(key, []), stageGroups.get(key))).push(event);
    }
    for (const [key, rows] of stageGroups) {
      const counts = new Map(); for (const row of rows) counts.set(row.instance_id, (counts.get(row.instance_id) ?? 0) + 1);
      const unique = rows.filter(x => counts.get(x.instance_id) === 1);
      const outcomes = { success: 0, failure: 0, unknown: 0 }; for (const row of unique) outcomes[row.outcome]++;
      stages[key] = { stats_ns: stats(unique.map(x => x.duration_ns)), successful_stats_ns: stats(unique.filter(x => x.outcome === 'success').map(x => x.duration_ns)),
        coverage: { owned_instances: ids.length, recorded_instances: counts.size, record_count: rows.length,
          measured_instances: unique.length, repeated_instances: [...counts.values()].filter(x => x > 1).length,
          fraction: ids.length ? unique.length / ids.length : null }, outcomes,
        timing_sources: [...new Set(rows.map(x => x.timing_source))], additivity: 'do_not_sum',
        stats_population: 'One unambiguous invocation per instance and stage; repeated stage invocations excluded from aggregate but retained per-instance.',
        samples: unique.map(x => ({ instance_id: x.instance_id, duration_ns: x.duration_ns, outcome: x.outcome })) };
    }
    const batchInstances = ids.map(instance_id => ({ instance_id,
      ...(batchesByInstance.get(instance_id) ?? { distinct_batches: 0, batch_records: 0, duplicate_batch_identities: 0 }) }));
    const oneBatch = batchInstances.filter(x => x.distinct_batches === 1 && x.duplicate_batch_identities === 0);
    const rootInstances = new Set(accepted.filter(x => x.phase === phase && x.component === 'cubelet' &&
      x.kind === 'request' && x.stage === 'cubelet.request' && x.parent_span_id === '0').map(x => x.instance_id));
    const expected = profile.phases[phase]?.expected_request_count ??
      (phase === 'formal' ? profile.capture?.requests : phase === 'warmup' ? profile.capture?.warmup : null) ?? null;
    phases[phase] = { owned_instance_count: ids.length, stages, cubelet_batch_coverage: {
      expected_request_count: expected, owned_instances: ids.length,
      observed_instances: batchInstances.filter(x => x.distinct_batches > 0).length,
      missing_instances: batchInstances.filter(x => !x.distinct_batches).length,
      single_unambiguous_batch_instances: oneBatch.length,
      multiple_distinct_batch_instances: batchInstances.filter(x => x.distinct_batches > 1).length,
      duplicate_batch_instances: batchInstances.filter(x => x.duplicate_batch_identities > 0).length,
      request_span_instances: rootInstances.size,
      single_batch_with_request_span_instances: oneBatch.filter(x => rootInstances.has(x.instance_id)).length,
      coverage_of_owned: ids.length ? oneBatch.filter(x => rootInstances.has(x.instance_id)).length / ids.length : null,
      coverage_of_expected: expected ? oneBatch.filter(x => rootInstances.has(x.instance_id)).length / expected : null,
      instances: batchInstances,
      note: 'One unique request/origin batch and a valid request root span are required for complete instance coverage; this does not prove all child stages were emitted.',
    } };
  }
  return { schema_version: 1, duration_unit: 'ns', phases, integrity, rejected_records: invalid,
    instances: [...owners].map(([instance_id, phase]) => ({ instance_id, phase,
      intervals: accepted.filter(x => x.instance_id === instance_id),
      excluded_events: events.filter(x => x.instance_id === instance_id && x.exclusion) })),
    interpretation: [
      'Cubelet request-local offsets and Shim process-local offsets have different clock origins. Never subtract or merge them into a precise cross-process clock.',
      'Cubelet duration_backfill preserves duration but has no confirmed stage endpoints; inferred_start_ns is not a timeline position.',
      'Shim cumulative rows are elapsed checkpoints, not independent durations. Derived A→B intervals require a unique increasing marker sequence within the same clock and operation; skipped markers remain named explicitly.',
      'Shim stat rows without wall timestamps are attributable to the bounded capture delta only. ClockId is an identity, not an accurate wall-clock anchor.',
      'DroppedRecordsBefore is a process counter observed on surviving events; it cannot detect a lost final tail or all writer failures. Coverage is independently reported.',
      'Zero duration from explicit precise trace endpoints is measured; this differs from zero network accumulator fields with unknown execution.',
      'Nested, cumulative, backfilled and propagated measurements overlap. Do not sum them or subtract aggregate percentiles.',
    ] };
}
export function precisionCsv(result) {
  const rows = [['phase', 'stage', 'owned_instances', 'recorded_instances', 'measured_instances', 'coverage', 'mean_ns', 'p50_ns', 'p95_ns', 'min_ns', 'max_ns', 'repeated_instances']];
  for (const [phase, population] of Object.entries(result.phases)) for (const [stage, row] of Object.entries(population.stages)) rows.push([
    phase, stage, row.coverage.owned_instances, row.coverage.recorded_instances, row.coverage.measured_instances, row.coverage.fraction,
    ...['avg', 'p50', 'p95', 'min', 'max'].map(k => row.stats_ns?.[k] ?? null), row.coverage.repeated_instances]);
  return rows.map(row => row.map(x => x ?? '').join(',')).join('\n') + '\n';
}
export function writePrecision(directory, options = {}) {
  const root = path.resolve(directory), profile = loadProfile(root, options);
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'capture-manifest.json'), 'utf8')), inputs = {};
  function read(kind) {
    const info = manifest.logs?.[kind] ?? {}, relative = info.delta_path ?? `evidence/${kind}-delta.log`, file = path.resolve(root, relative);
    if (!file.startsWith(root + path.sep)) throw new Error(`Log path outside capture: ${kind}`);
    if (!fs.existsSync(file)) { inputs[kind] = { status: 'missing' }; return []; }
    const bytes = fs.readFileSync(file), sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
    if (info.sha256 && sha256 !== info.sha256) throw new Error(`Log SHA256 differs from manifest: ${kind}`);
    const records = []; let malformed = 0;
    for (const line of bytes.toString('utf8').split('\n').filter(x => x.trim())) {
      try { const r = parsePrecisionJson(line); if (!r || typeof r !== 'object' || Array.isArray(r)) throw new Error(); records.push(r); } catch { malformed++; }
    }
    inputs[kind] = { path: relative, bytes: bytes.length, sha256, malformed_json_lines: malformed, log_status: info.status ?? 'unknown', log_gaps: info.gaps ?? [] };
    return records;
  }
  const cubelet = read('cubelet_req'), shim = read('shim_stat');
  const result = analyzePrecision({ profile, cubelet, shim, inputIntegrity: { inputs } });
  fs.writeFileSync(path.join(root, 'precision.json'), JSON.stringify(result, null, 2) + '\n', { mode: 0o600 });
  fs.writeFileSync(path.join(root, 'precision.csv'), precisionCsv(result), { mode: 0o600 });
  return result;
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  if (!(args.length === 1 || (args.length === 3 && args[1] === '--phase-classification'))) {
    console.error('Usage: node precision.mjs CAPTURE_DIRECTORY [--phase-classification FILE]'); process.exit(2);
  }
  const result = writePrecision(args[0], { phaseClassification: args[2] });
  console.log(JSON.stringify({ output: path.join(args[0], 'precision.json'), integrity: result.integrity }));
}
