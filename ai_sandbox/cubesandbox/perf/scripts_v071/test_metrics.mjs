import test from "node:test";
import assert from "node:assert/strict";
import { analyzeMetrics } from "./metrics.mjs";

const histogram = (count, sum, buckets, labels = '') => `# TYPE chi_cubebox_image_forward_latency_milliseconds histogram\n` +
  buckets.map(([le, value]) => `chi_cubebox_image_forward_latency_milliseconds_bucket{${labels}le="${le}"} ${value}`).join('\n') +
  `\nchi_cubebox_image_forward_latency_milliseconds_sum{${labels.replace(/,$/, '')}} ${sum}\nchi_cubebox_image_forward_latency_milliseconds_count{${labels.replace(/,$/, '')}} ${count}\n`;
const before = histogram(10, 100, [[1, 1], [10, 5], [100, 10], ['+Inf', 10]]);
const after = histogram(14, 230, [[1, 1], [10, 7], [100, 14], ['+Inf', 14]]);

test('v0.7.1 real histogram names: differences retain milliseconds, quantiles have explicit bounds', () => {
  const result = analyzeMetrics(before, after);
  const h = result.histograms[0];
  assert.equal(h.name, 'chi_cubebox_image_forward_latency_milliseconds');
  assert.equal(h.unit, 'milliseconds');
  assert.equal(h.valid, true);
  assert.equal(h.count.delta, 4);
  assert.equal(h.sum.delta, 130);
  assert.equal(h.avg, 32.5);
  assert.deepEqual(h.buckets.map(b => b.delta), [0, 2, 4, 4]);
  assert.equal(h.quantiles[0].upper_bound, 10);
  assert.equal(h.quantiles[0].exact_sample_quantile, false);
  assert.equal(result.sandbox_attribution, 'none');
});

test('master counters stay per label; cubelet scheduler gauges can decrease without reset', () => {
  const snapshot = (ok, error, inflight) => `# TYPE cube_snapshot_commit_total counter\ncube_snapshot_commit_total{result="success"} ${ok}\ncube_snapshot_commit_total{result="error"} ${error}\n# TYPE cube_cubebox_scheduler_realtime_create_num gauge\ncube_cubebox_scheduler_realtime_create_num ${inflight}`;
  const result = analyzeMetrics(snapshot(5, 2, 100), snapshot(8, 4, 0));
  assert.deepEqual(result.counters.map(c => [c.labels.result, c.delta]), [['success', 3], ['error', 2]]);
  assert.equal(result.gauges[0].delta, -100);
  assert.equal(result.gauges[0].valid, true);
  assert.equal(result.histograms.length, 0);
});

test('histogram and counter resets are reported; no post-reset value masquerades as interval delta', () => {
  const result = analyzeMetrics(after + '\n# TYPE kata_agent_scrape_count counter\nkata_agent_scrape_count 100', before + '\n# TYPE kata_agent_scrape_count counter\nkata_agent_scrape_count 3');
  assert.equal(result.histograms[0].valid, false);
  assert.equal(result.histograms[0].avg, null);
  assert.deepEqual(result.histograms[0].quantiles, []);
  assert.ok(result.histograms[0].issues.includes('reset_or_decrease'));
  assert.equal(result.counters[0].delta, null);
});

test('missing series require explicit whole-series zero baseline; missing after never means zero', () => {
  const strict = analyzeMetrics('', after).histograms[0];
  assert.equal(strict.avg, null);
  assert.ok(strict.issues.includes('missing_before'));
  assert.equal(analyzeMetrics('', after, { assumeMissingBeforeZero: true }).histograms[0].avg, 230 / 14);
  assert.ok(analyzeMetrics(before, '').histograms[0].issues.includes('missing_after'));
  const partial = before.replace(/.*_sum.*\n/, '');
  assert.ok(analyzeMetrics(partial, after, { assumeMissingBeforeZero: true }).histograms[0].issues.includes('partial_missing_baseline'));
});

test('invalid finite values, duplicate series, malformed input and counter decreases are surfaced', () => {
  const result = analyzeMetrics('# TYPE x counter\nx 2', '# TYPE x counter\nx 3\nx NaN\nbroken ! text');
  assert.equal(result.counters[0].delta, null);
  assert.ok(result.counters[0].issues.includes('invalid_value'));
  assert.ok(result.counters[0].issues.includes('duplicate_series'));
  assert.equal(result.issues[0].code, 'parse_error');
  assert.equal(analyzeMetrics('# TYPE x counter\nx -1', '# TYPE x counter\nx 2').counters[0].valid, false);
  assert.equal(analyzeMetrics('# TYPE x counter\nx 1', '# TYPE x counter\nx Infinity').counters[0].valid, false);
});

test('non-monotonic snapshot and delta buckets are rejected even when every counter increased', () => {
  const base = histogram(10, 30, [[1, 5], [10, 10], ['+Inf', 10]]);
  const end = histogram(12, 40, [[1, 9], [10, 12], ['+Inf', 12]]);
  const h = analyzeMetrics(base, end).histograms[0];
  assert.ok(h.issues.includes('non_monotonic_delta_buckets'));
  assert.equal(h.avg, null);
  assert.ok(analyzeMetrics('', histogram(12, 40, [[1, 13], [10, 12], ['+Inf', 12]]), { assumeMissingBeforeZero: true }).histograms[0].issues.includes('non_monotonic_after_buckets'));
});

test('count/infinite bucket mismatch and incomplete histograms do not yield quantiles', () => {
  const h = analyzeMetrics(before, after.replace('le="+Inf"} 14', 'le="+Inf"} 15')).histograms[0];
  assert.ok(h.issues.includes('count_infinite_bucket_mismatch_after'));
  assert.deepEqual(h.quantiles, []);
  assert.ok(analyzeMetrics(before, after.replace(/.*le="\+Inf".*\n/, '')).histograms[0].issues.includes('missing_after'));
});

test('tail in +Inf bucket has no fabricated finite estimate; zero observations have no percentile', () => {
  const h = analyzeMetrics(histogram(0, 0, [[1, 0], ['+Inf', 0]]), histogram(2, 50, [[1, 0], ['+Inf', 2]])).histograms[0];
  assert.equal(h.quantiles[0].estimate, null);
  assert.equal(h.quantiles[0].upper_bound_unbounded, true);
  const zero = analyzeMetrics(before, before).histograms[0];
  assert.equal(zero.avg, null);
  assert.equal(zero.quantiles[0].method, 'no_observations');
});

test('label order/escaping handled; separate histogram label populations are never merged', () => {
  const b = '# TYPE x counter\nx{b="quote\\\"newline\\n",a="x"} 3';
  const a = '# TYPE x counter\nx{a="x",b="quote\\\"newline\\n"} 8';
  const counter = analyzeMetrics(b, a).counters[0];
  assert.equal(counter.delta, 5);
  assert.equal(counter.labels.b, 'quote"newline\n');
  const h = analyzeMetrics(histogram(1, 1, [[1, 1], ['+Inf', 1]], 'node="a",') + histogram(1, 1, [[1, 1], ['+Inf', 1]], 'node="b",'), histogram(2, 2, [[1, 2], ['+Inf', 2]], 'node="a",') + histogram(3, 3, [[1, 3], ['+Inf', 3]], 'node="b",')).histograms;
  assert.deepEqual(h.map(x => [x.labels.node, x.count.delta]), [['a', 1], ['b', 2]]);
});

test('known process restart invalidates monotonic deltas even if counter surpassed old value', () => {
  const b = '# TYPE process_start_time_seconds gauge\nprocess_start_time_seconds 100\n# TYPE x counter\nx 3';
  const a = '# TYPE process_start_time_seconds gauge\nprocess_start_time_seconds 200\n# TYPE x counter\nx 10';
  const result = analyzeMetrics(b, a);
  assert.ok(result.issues.some(x => x.code === 'process_restart_detected'));
  assert.equal(result.counters[0].delta, null);
});

test('metric type changes and invalid quantiles are reported', () => {
  const result = analyzeMetrics('# TYPE x counter\nx 1', '# TYPE x gauge\nx 2');
  assert.equal(result.gauges[0].valid, false);
  assert.ok(result.issues.some(x => x.code === 'type_changed'));
  assert.throws(() => analyzeMetrics('', '', { quantiles: [95] }), /fractions/);
});

test('throughput histogram is not interpreted as latency, and summary values are unsupported', () => {
  const b = before.replaceAll('chi_cubebox_image_forward_latency_milliseconds', 'cube_cubebox_image_host_pulling_throughput_mib_per_sec');
  const a = after.replaceAll('chi_cubebox_image_forward_latency_milliseconds', 'cube_cubebox_image_host_pulling_throughput_mib_per_sec');
  assert.equal(analyzeMetrics(b, a).histograms[0].unit, 'MiB/s');
  assert.equal(analyzeMetrics('# TYPE s summary\ns{quantile="0.5"} 1', '# TYPE s summary\ns{quantile="0.5"} 2').unsupported[0].type, 'summary');
});


test('bucket order is canonicalized, including +Inf; timestamps and exponent values are accepted', () => {
  const h = analyzeMetrics(histogram(0, 0, [['+Inf', 0], [10, 0], [1, 0]]), histogram(2, 8, [['+Inf', 2], [10, 2], [1, 0]])).histograms[0];
  assert.equal(h.valid, true);
  assert.deepEqual(h.buckets.map(b => b.le), ['1', '10', '+Inf']);
  const r = analyzeMetrics('# TYPE x counter\nx 1e2 1700000000', '# TYPE x counter\nx 1.5e2 1700000100');
  assert.equal(r.counters[0].delta, 50);
});
