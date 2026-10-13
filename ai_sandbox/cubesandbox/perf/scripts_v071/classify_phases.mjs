#!/usr/bin/env node
// Infer server-side phases only after proving the serial warmup boundary.
// This does not establish any cube-bench raw seq -> sandbox-ID mapping.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';

const COMMIT = '31d911e430fdf8a8879bd062b8e78066c1a8e89d';
const SUITE = '399815f259a072db79415a29496283da089308b95e66ba63494aeeb58ecfdd09';
const BINARY = 'd7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d';
const sameSet = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length &&
  new Set(a).size === a.length && new Set(b).size === b.length && a.every(x => b.includes(x));
const nonempty = x => typeof x === 'string' && x.trim().length > 0;
function clockNs(value) {
  if (typeof value !== 'string') return null;
  const m = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/);
  if (!m) return null;
  const base = Date.parse(m[1] + m[3]);
  return Number.isFinite(base) ? BigInt(base) * 1000000n + BigInt((m[2] ?? '').padEnd(9, '0')) : null;
}
function object(text) { try { return JSON.parse(text); } catch { return null; } }

export function classifyPhases(input) {
  const errors = [...(input.inputErrors ?? [])], checks = {};
  const check = (name, value) => { checks[name] = Boolean(value); if (!value) errors.push(name); };
  const { manifest: m = {}, ownership: o = {}, adapter: a = {}, ledger: l = {},
    raw: r = {}, identityBefore: before = {}, identityAfter: after = {} } = input;
  const ml = m.logs?.master ?? {};
  check('master_log_complete', ml.status === 'captured' && Array.isArray(ml.gaps) && !ml.gaps.length &&
    ml.starts_on_line_boundary === true && ml.ends_on_line_boundary === true &&
    ml.before?.inode === ml.after?.inode && ml.before?.device === ml.after?.device &&
    Number.isInteger(ml.before?.size) && Number.isInteger(ml.after?.size) &&
    ml.after.size >= ml.before.size && ml.captured_bytes === ml.after.size - ml.before.size &&
    ml.omitted_bytes === 0 && ml.before.status === 'ok');
  check('capture_command_succeeded', m.command?.executed === true && m.command?.exit_code === 0 && !m.command?.timed_out);
  check('ownership_originally_unknown_103', Array.isArray(o.formal) && !o.formal.length &&
    Array.isArray(o.warmup) && !o.warmup.length && Array.isArray(o.unknown_phase) &&
    o.unknown_phase.length === 103 && new Set(o.unknown_phase).size === 103 && o.unknown_phase.every(nonempty));
  check('adapter_success', a.status === 'suite_returned_success' && a.exit_code === 0 &&
    a.suite_exit_code === 0 && a.suite_status === 'complete' && a.case_status === 'complete' &&
    a.execute_requested === true && a.suite_main_invoked === true && a.benchmark_invocation_recorded === true &&
    Array.isArray(a.errors) && !a.errors.length && a.ownership?.ledger_status === 'drained' &&
    a.raw_result?.status === 'copied' && a.suite_preflight === 'passed');
  check('pinned_suite_preflight_contract', a.sources?.suite?.sha256 === SUITE && a.sources?.suite?.expected_sha256 === SUITE);
  check('official_binary_verified', a.sources?.native_binary?.sha256 === BINARY &&
    a.sources?.native_binary?.expected_sha256 === BINARY && m.benchmark_binary?.sha256 === BINARY);
  check('exclusive_ledger_drained', l.ownership_mode === 'exclusive-template' && l.status === 'drained' &&
    nonempty(l.template_id) && l.template_id === m.template_id &&
    sameSet(l.observed_ids, o.unknown_phase) && Array.isArray(l.final_live_ids) && !l.final_live_ids.length &&
    Array.isArray(l.observations) && l.observations.length > 0 && l.observations.every(x => !x.error) &&
    l.observations.slice(-2).length === 2 && l.observations.slice(-2).every(x => Array.isArray(x.ids) && !x.ids.length));
  check('official_workload_success', r.config?.concurrency === 100 && r.config?.total === 100 &&
    r.config?.warmup === 3 && r.config?.mode === 'create-only' && r.config?.template === m.template_id &&
    r.summary?.successful === 100 && r.summary?.errors === 0 && Array.isArray(r.raw) && r.raw.length === 100 &&
    r.raw.every(x => !x.error && !x.err && !x.Err && typeof x.create_ms === 'number' && Number.isFinite(x.create_ms) && x.create_ms >= 0));
  const warmupLines = (input.benchmarkLog ?? '').split(/\r?\n/).filter(x => /warmup \[/.test(x));
  check('three_successful_serial_warmup_messages', warmupLines.length === 3 &&
    warmupLines.every((x, i) => x.trim() === `warmup [${i + 1}/3] ok`));
  check('identity_empty_baselines', before.sandbox_count === 0 && after.sandbox_count === 0 &&
    before.template?.id === m.template_id && after.template?.id === m.template_id &&
    before.template?.status === 'READY' && after.template?.status === 'READY');
  check('stable_host_release', nonempty(before.boot_id) && before.boot_id === after.boot_id &&
    before.commit === COMMIT && after.commit === COMMIT &&
    nonempty(before.shim?.sha256) && before.shim.sha256 === after.shim?.sha256);
  const obs = before.observation;
  const validObservation = !obs && !after.observation || Boolean(obs && after.observation &&
    JSON.stringify(obs) === JSON.stringify(after.observation) && obs.schema_version === 1 &&
    obs.base_commit === COMMIT && ['off', 'on'].includes(obs.mode) && /^[a-f0-9]{64}$/.test(obs.patch_sha256 ?? '') &&
    sameSet(Object.keys(obs.components ?? {}), ['cubelet', 'containerd-shim-cube-rs']) &&
    Object.values(obs.components).every(x => /^[a-f0-9]{64}$/.test(x.sha256 ?? '') && x.commit === COMMIT + '+perftrace') &&
    before.shim?.sha256 === obs.components['containerd-shim-cube-rs'].sha256);
  check('stable_observation_build', validObservation);
  const components = ['cube-api', 'cubemaster', 'cubelet', 'templatecenter'];
  check('stable_service_processes', Array.isArray(before.services) && Array.isArray(after.services) &&
    sameSet(before.services.map(x => x.component), components) && sameSet(after.services.map(x => x.component), components) &&
    before.services.every(x => { const y = after.services.find(z => z.component === x.component);
      return Number.isInteger(x.pid) && x.pid > 0 && nonempty(String(x.start_ticks ?? '')) &&
        /^[a-f0-9]{64}$/.test(x.sha256 ?? '') && x.commit === (obs?.components?.[x.component]?.commit ?? COMMIT) && y.commit === x.commit &&
        (!obs?.components?.[x.component] || x.sha256 === obs.components[x.component].sha256) &&
        x.pid === y.pid && x.start_ticks === y.start_ticks && x.sha256 === y.sha256; }));
  const starts = new Map(), responses = new Map(); let badMarkers = 0;
  const records = input.masterRecords ?? [];
  for (const row of records) {
    const content = row.LogContent;
    if (typeof content !== 'string') continue;
    if (content.startsWith('CreateSandbox_rsp fail:')) { badMarkers++; continue; }
    const kind = content.startsWith('CreateSandbox:') ? 'start' : content.startsWith('CreateSandbox_rsp:') ? 'end' : null;
    if (!kind) continue;
    const payload = object(content.slice(content.indexOf(':') + 1));
    const requestId = kind === 'start' ? payload?.requestID : payload?.RequestID;
    const at = row['@timestamp'] ?? row.Timestamp ?? row.timestamp;
    const ns = clockNs(at);
    if (!nonempty(requestId) || ns === null || (nonempty(row.RequestId) && row.RequestId !== requestId)) { badMarkers++; continue; }
    const group = kind === 'start' ? starts : responses;
    if (group.has(requestId)) { badMarkers++; continue; }
    group.set(requestId, { request_id: requestId, at, ns, payload });
  }
  check('master_exactly_104_unique_pairs_including_preflight', badMarkers === 0 && starts.size === 104 && responses.size === 104 &&
    sameSet([...starts.keys()], [...responses.keys()]));
  const allPairs = [...starts.values()].filter(s => responses.has(s.request_id)).map(s => {
    const e = responses.get(s.request_id);
    return { request_id: s.request_id, sandbox_id: e.payload.sandbox_id,
      start: s.at, response: e.at, startNs: s.ns, endNs: e.ns, success: e.payload.ret?.ret_code === 200 };
  }).sort((a, b) => a.startNs < b.startNs ? -1 : a.startNs > b.startNs ? 1 : 0);
  const owned = new Set(o.unknown_phase ?? []);
  const pairs = allPairs.filter(p => owned.has(p.sandbox_id));
  const preflight = allPairs.filter(p => !owned.has(p.sandbox_id));
  const preflightDeletes = [];
  for (const row of records) {
    if (!row.LogContent?.startsWith('async DestroySandbox_rsp:')) continue;
    const payload = object(row.LogContent.slice('async DestroySandbox_rsp:'.length));
    if (!preflight.some(p => p.sandbox_id === payload?.sandbox_id)) continue;
    const at = row['@timestamp'] ?? row.Timestamp ?? row.timestamp;
    preflightDeletes.push({ sandbox_id: payload.sandbox_id, request_id: payload.requestID, at, ns: clockNs(at), success: payload.ret?.ret_code === 200 });
  }
  check('single_preflight_completed_and_delete_ack_before_owned', preflight.length === 1 && pairs.length === 103 &&
    preflight[0].success && preflight[0].endNs >= preflight[0].startNs && preflight[0].endNs < pairs[0].startNs &&
    preflightDeletes.length === 1 && preflightDeletes[0].success && preflightDeletes[0].ns !== null &&
    preflightDeletes[0].ns >= preflight[0].endNs && preflightDeletes[0].ns < pairs[0].startNs);
  const capStart = clockNs(m.started_at), capEnd = clockNs(m.ended_at);
  check('master_pairs_successful_owned_in_window', capStart !== null && capEnd !== null && capEnd >= capStart &&
    sameSet(pairs.map(p => p.sandbox_id), o.unknown_phase) && allPairs.every(p =>
      p.success && p.endNs >= p.startNs && p.startNs >= capStart && p.endNs <= capEnd));
  check('warmup_boundary_strictly_ordered', pairs.length === 103 &&
    pairs.slice(0, 3).every((p, i) => p.endNs < pairs[i + 1].startNs));
  const success = errors.length === 0;
  return { schema_version: 1, status: success ? 'classified' : 'unverified',
    method: 'exclusive-template; exact Master request/response pairs; proven serial warmup boundary',
    raw_seq_to_sandbox_mapping: 'unavailable', checks, errors: [...new Set(errors)],
    ownership: success ? { warmup: pairs.slice(0, 3).map(p => p.sandbox_id), formal: pairs.slice(3).map(p => p.sandbox_id), unknown_phase: [] } : null,
    evidence: { files: input.fileEvidence ?? {}, binary_sha256: a.sources?.native_binary?.sha256 ?? null,
      build_kind: before.build_kind ?? "official-v0.7.1", observation: obs ?? null,
      template_id: m.template_id ?? null, master_start_count: starts.size, master_response_count: responses.size,
      malformed_or_duplicate_markers: badMarkers, warmup_messages: warmupLines,
      services_before: before.services ?? null, services_after: after.services ?? null,
      excluded_preflight: preflight.map(({ startNs, endNs, ...p }) => p),
      preflight_delete_ack: preflightDeletes.map(({ ns, ...p }) => p),
      preflight_drain_basis: 'Pinned suite requires empty API inventory after guest_preflight and again before benchmark; suite preflight/case success verified. Delete ack alone is not proof of drain.',
      pairs: pairs.map(({ startNs, endNs, ...p }) => p) },
    limitations: ['Server phase classification only; cube-bench raw rows are not mapped to sandbox IDs.',
      'Depends on exclusive use of the dedicated template, the pinned official runner, and complete captured Master logs.',
      'No source ownership file is modified. Failed checks leave all phases unclassified.'] };
}

export function loadAndClassify(directory) {
  const root = path.resolve(directory), fileEvidence = {}, inputErrors = [];
  function read(name, json = true) {
    const full = path.resolve(root, name);
    if (!full.startsWith(root + path.sep)) { inputErrors.push(`outside_capture:${name}`); return null; }
    try { const bytes = fs.readFileSync(full); fileEvidence[name] = { bytes: bytes.length,
      sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
      return json ? JSON.parse(bytes.toString('utf8')) : bytes.toString('utf8');
    } catch { inputErrors.push(`unreadable_or_invalid:${name}`); return null; }
  }
  const manifest = read('capture-manifest.json') ?? {};
  const log = read(manifest.logs?.master?.delta_path ?? 'evidence/master-delta.log', false) ?? '';
  const masterRecords = [];
  for (const line of log.split('\n').filter(x => x.trim())) {
    const row = object(line);
    if (!row || typeof row !== 'object' || Array.isArray(row)) inputErrors.push('master_log_invalid_json_line');
    else masterRecords.push(row);
  }
  return classifyPhases({ manifest, ownership: read('owned-sandbox-ids.json') ?? {},
    adapter: read('adapter-status.json') ?? {}, ledger: read('suite-results/c100n100.delete.json') ?? {},
    raw: read('startup-latency/c100n100.raw.json') ?? {}, benchmarkLog: read('suite-results/3.2-c100n100.log', false) ?? '',
    identityBefore: read('service-identity-before.json') ?? {}, identityAfter: read('service-identity-after.json') ?? {},
    masterRecords, fileEvidence, inputErrors });
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  if (process.argv.length !== 3) { console.error('Usage: node classify_phases.mjs CAPTURE_DIRECTORY'); process.exit(2); }
  const result = loadAndClassify(process.argv[2]);
  const output = path.join(process.argv[2], 'phase-classification.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  console.log(JSON.stringify({ status: result.status, output, errors: result.errors }));
  process.exitCode = result.status === 'classified' ? 0 : 1;
}
