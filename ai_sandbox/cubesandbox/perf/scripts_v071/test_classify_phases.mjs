import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyPhases } from './classify_phases.mjs';

const COMMIT = '31d911e430fdf8a8879bd062b8e78066c1a8e89d';
const HASH = 'd7d7685433bea7909b124504f4851517bdae146c4bb13e279fbb816c20bd032d';
function fixture() {
  const ids = Array.from({ length: 103 }, (_, i) => `sb-${i}`);
  const iso = ms => new Date(Date.UTC(2026, 9, 12) + ms).toISOString();
  const identity = { boot_id: 'boot', commit: COMMIT, shim: { sha256: HASH }, sandbox_count: 0,
    template: { id: 'tpl-only', status: 'READY' }, services: ['cube-api', 'cubemaster', 'cubelet', 'templatecenter'].map((component, i) =>
      ({ component, pid: i + 1, start_ticks: '100', sha256: HASH, commit: COMMIT })) };
  return { manifest: { template_id: 'tpl-only', started_at: iso(0), ended_at: iso(10000),
    command: { executed: true, exit_code: 0, timed_out: false }, benchmark_binary: { sha256: HASH },
    logs: { master: { status: 'captured', gaps: [], starts_on_line_boundary: true, ends_on_line_boundary: true,
      before: { status: 'ok', inode: 1, device: 1, size: 10 }, after: { inode: 1, device: 1, size: 110 }, captured_bytes: 100, omitted_bytes: 0 } } },
    ownership: { formal: [], warmup: [], unknown_phase: ids },
    adapter: { suite_preflight: 'passed', status: 'suite_returned_success', exit_code: 0, suite_exit_code: 0, suite_status: 'complete',
      case_status: 'complete', execute_requested: true, suite_main_invoked: true, benchmark_invocation_recorded: true,
      errors: [], ownership: { ledger_status: 'drained' }, raw_result: { status: 'copied' },
      sources: { suite: { sha256: '399815f259a072db79415a29496283da089308b95e66ba63494aeeb58ecfdd09', expected_sha256: '399815f259a072db79415a29496283da089308b95e66ba63494aeeb58ecfdd09' }, native_binary: { sha256: HASH, expected_sha256: HASH } } },
    ledger: { ownership_mode: 'exclusive-template', status: 'drained', template_id: 'tpl-only', observed_ids: [...ids],
      final_live_ids: [], observations: [{ ids, error: null }, { ids: [], error: null }, { ids: [], error: null }] },
    raw: { config: { concurrency: 100, total: 100, warmup: 3, mode: 'create-only', template: 'tpl-only' },
      summary: { successful: 100, errors: 0 }, raw: Array.from({ length: 100 }, (_, seq) => ({ seq, create_ms: 100, error: '' })) },
    benchmarkLog: '    warmup [1/3] ok\n    warmup [2/3] ok\n    warmup [3/3] ok\n\n',
    identityBefore: identity, identityAfter: structuredClone(identity),
    masterRecords: ids.flatMap((sandbox_id, i) => {
      const requestID = `r-${i}`, start = i < 3 ? 100 + i * 200 : 1000 + (i - 3);
      return [ { '@timestamp': iso(start), RequestId: requestID, LogContent: `CreateSandbox:${JSON.stringify({ requestID })}` },
        { '@timestamp': iso(start + 100), RequestId: requestID,
          LogContent: `CreateSandbox_rsp:${JSON.stringify({ RequestID: requestID, sandbox_id, ret: { ret_code: 200 } })}` } ];
    }).concat([
      { '@timestamp': iso(10), RequestId: 'preflight', LogContent: 'CreateSandbox:{"requestID":"preflight"}' },
      { '@timestamp': iso(20), RequestId: 'preflight', LogContent: 'CreateSandbox_rsp:{"RequestID":"preflight","sandbox_id":"sb-preflight","ret":{"ret_code":200}}' },
      { '@timestamp': iso(30), RequestId: 'delete-preflight', LogContent: 'async DestroySandbox_rsp:{"requestID":"delete-preflight","sandbox_id":"sb-preflight","ret":{"ret_code":200}}' },
    ]) };
}

test('classifies proven server phases, preserves inputs, creates no raw mapping', () => {
  const input = fixture(), original = structuredClone(input), result = classifyPhases(input);
  assert.equal(result.status, 'classified');
  assert.deepEqual(result.ownership.warmup, ['sb-0', 'sb-1', 'sb-2']);
  assert.equal(result.ownership.formal.length, 100);
  assert.equal(result.raw_seq_to_sandbox_mapping, 'unavailable');
  assert.deepEqual(input, original);
});

for (const [name, change] of [
  ['preflight still present', x => x.masterRecords.at(-1)['@timestamp'] = '2026-10-12T00:00:09Z'],
  ['preflight missing', x => x.masterRecords.splice(-3)],
  ['preflight delete unacknowledged', x => x.masterRecords.pop()],
  ['unverified suite', x => x.adapter.sources.suite.sha256 = 'other'],
  ['wrong Master success code', x => x.masterRecords[1].LogContent = x.masterRecords[1].LogContent.replace('200', '0')],
  ['wrong response RequestID casing', x => x.masterRecords[1].LogContent = x.masterRecords[1].LogContent.replace('RequestID', 'requestID')],
  ['log gap', x => x.manifest.logs.master.gaps.push('rotation')],
  ['log identity change', x => x.manifest.logs.master.after.inode++],
  ['truncated log', x => x.manifest.logs.master.captured_bytes--],
  ['partial final line', x => x.manifest.logs.master.ends_on_line_boundary = false],
  ['missing file', x => x.inputErrors = ['missing']],
  ['foreign ledger ID', x => x.ledger.observed_ids[3] = 'foreign'],
  ['wrong template', x => x.raw.config.template = 'foreign'],
  ['bad warmup', x => x.benchmarkLog = x.benchmarkLog.replace('[2/3] ok', '[2/3] failed: error')],
  ['extra warmup', x => x.benchmarkLog += 'warmup [1/3] ok\n'],
  ['restarted Master', x => x.identityAfter.services[1].start_ticks = '101'],
  ['new boot', x => x.identityAfter.boot_id = 'other'],
  ['unverified binary', x => x.adapter.sources.native_binary.sha256 = 'other'],
  ['baseline nonempty', x => x.identityBefore.sandbox_count = 1],
  ['cleanup failed', x => x.ledger.status = 'failed'],
  ['benchmark failure', x => x.raw.raw[0].error = 'failure'],
  ['duplicate request', x => x.masterRecords.push(x.masterRecords[0])],
  ['missing response', x => x.masterRecords.splice(1, 1)],
  ['request-ID mismatch', x => x.masterRecords[0].RequestId = 'wrong'],
  ['warmup overlaps', x => x.masterRecords[2]['@timestamp'] = x.masterRecords[0]['@timestamp']],
  ['boundary ambiguous same timestamp', x => x.masterRecords[6]['@timestamp'] = x.masterRecords[5]['@timestamp']],
  ['response before request', x => x.masterRecords[1]['@timestamp'] = '2026-10-12T00:00:00Z'],
]) test(`fails closed: ${name}`, () => {
  const input = fixture(); change(input);
  const result = classifyPhases(input);
  assert.equal(result.status, 'unverified'); assert.equal(result.ownership, null); assert.ok(result.errors.length);
});

test('request timestamps determine phases despite out-of-order log delivery', () => {
  const input = fixture(); input.masterRecords.reverse();
  assert.deepEqual(classifyPhases(input).ownership.warmup, ['sb-0', 'sb-1', 'sb-2']);
});

test('nanosecond precision preserves strict serial boundary', () => {
  const input = fixture();
  input.masterRecords[1]['@timestamp'] = '2026-10-12T00:00:00.200000001Z';
  input.masterRecords[2]['@timestamp'] = '2026-10-12T00:00:00.200000002Z';
  assert.equal(classifyPhases(input).status, 'classified');
});

test('empty evidence returns rejection rather than accepting missing fields', () => {
  assert.equal(classifyPhases({}).status, 'unverified');
});

function observedFixture() {
  const input = fixture();
  const observation = { schema_version: 1, base_commit: COMMIT, patch_sha256: HASH, mode: 'on',
    components: Object.fromEntries(['cubelet', 'containerd-shim-cube-rs'].map(name => [name, { sha256: HASH, commit: COMMIT + '+perftrace' }])) };
  for (const identity of [input.identityBefore, input.identityAfter]) {
    identity.build_kind = 'v0.7.1+perftrace';
    identity.observation = structuredClone(observation);
    identity.services.find(x => x.component === 'cubelet').commit = COMMIT + '+perftrace';
  }
  return input;
}
test('explicit observation build retains provenance and classifies phases', () => {
  const result = classifyPhases(observedFixture());
  assert.equal(result.status, 'classified');
  assert.equal(result.evidence.build_kind, 'v0.7.1+perftrace');
  assert.equal(result.evidence.observation.mode, 'on');
});
for (const [name, change] of [
  ['mode changed', x => x.identityAfter.observation.mode = 'off'],
  ['patch not pinned', x => x.identityBefore.observation.patch_sha256 = 'unknown'],
  ['shim not pinned', x => x.identityBefore.observation.components['containerd-shim-cube-rs'].sha256 = '0'.repeat(64)],
  ['service differs', x => x.identityBefore.services.find(s => s.component === 'cubelet').sha256 = '0'.repeat(64)],
  ['unexpected patched component', x => x.identityBefore.observation.components.cubemaster = {sha256: HASH, commit: COMMIT + '+perftrace'}],
]) test(`rejects observation evidence: ${name}`, () => {
  const input = observedFixture(); change(input);
  assert.equal(classifyPhases(input).status, 'unverified');
});
