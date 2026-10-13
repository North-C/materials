#!/usr/bin/env node
// Prometheus text snapshot differencing. No request attribution is inferred.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const identity = (name, labels) => JSON.stringify([name, Object.entries(labels).sort(([a], [b]) => a.localeCompare(b))]);
const finite = (v) => Number.isFinite(v) ? v : null;
const bound = (le) => le === "+Inf" ? Infinity : Number(le);
function labelsOf(text = "") {
  const labels = Object.create(null);
  let rest = text.trim();
  while (rest) {
    const m = rest.match(/^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*"((?:[^"\\]|\\[\\"n])*)"\s*(,|$)/);
    if (!m || Object.hasOwn(labels, m[1])) throw new Error("invalid or duplicate label");
    labels[m[1]] = m[2].replace(/\\([\\"n])/g, (_, c) => c === "n" ? "\n" : c);
    rest = rest.slice(m[0].length).trim();
  }
  return labels;
}
function parse(text, snapshot) {
  const samples = new Map(), types = new Map(), issues = [];
  for (const [index, raw] of String(text ?? "").split(/\r?\n/).entries()) {
    const line = raw.trim();
    if (!line) continue;
    const type = line.match(/^# TYPE (\S+) (\S+)$/);
    if (type) {
      if (types.has(type[1]) && types.get(type[1]) !== type[2]) issues.push({ code: "conflicting_type", snapshot, line: index + 1 });
      types.set(type[1], type[2]); continue;
    }
    if (line.startsWith("#")) continue;
    const m = line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{((?:[^"}]|"(?:[^"\\]|\\.)*")*)\})?\s+(\S+)(?:\s+[-+]?\d+(?:\.\d+)?)?\s*(?:#.*)?$/);
    try {
      if (!m) throw new Error("malformed sample");
      const labels = labelsOf(m[2]);
      const key = identity(m[1], labels);
      const value = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/.test(m[3]) ? Number(m[3]) : NaN;
      const sample = { name: m[1], labels, value, issues: [] };
      if (!Number.isFinite(value)) sample.issues.push("invalid_value");
      if (samples.has(key)) sample.issues.push("duplicate_series");
      samples.set(key, sample);
    } catch (error) {
      issues.push({ code: "parse_error", snapshot, line: index + 1, message: error.message });
    }
  }
  return { samples, types, issues };
}
function classify(sample, types) {
  const direct = types.get(sample.name);
  if (direct) return { family: sample.name, type: direct, part: "value" };
  const m = sample.name.match(/^(.*)_(bucket|count|sum)$/);
  if (m && types.get(m[1]) === "histogram") return { family: m[1], type: "histogram", part: m[2] };
  if (sample.name.endsWith("_total") && types.get(sample.name.slice(0, -6)) === "counter") {
    return { family: sample.name, type: "counter", part: "value" };
  }
  return { family: sample.name, type: "untyped", part: "value" };
}
function unitOf(name) {
  if (name.includes("mib_per_sec")) return "MiB/s";
  if (name.includes("milliseconds")) return "milliseconds";
  if (name.includes("seconds")) return "seconds";
  if (name.includes("bytes")) return "bytes";
  return "native_metric_unit";
}
function quantileEstimate(buckets, count, q) {
  if (!count) return { q, estimate: null, lower_bound: null, upper_bound: null, method: "no_observations" };
  const rank = q * count;
  let lower = 0, previous = 0;
  for (const b of buckets) {
    const upper = bound(b.le);
    if (b.delta >= rank) {
      // The +Inf bucket has no finite upper bound, so do not invent a point estimate.
      const estimate = Number.isFinite(upper) ? lower + (upper - lower) * (rank - previous) / (b.delta - previous) : null;
      return { q, estimate: finite(estimate), lower_bound: lower, upper_bound: finite(upper),
        upper_bound_unbounded: !Number.isFinite(upper), method: "linear_interpolation_within_cumulative_bucket", exact_sample_quantile: false };
    }
    lower = upper; previous = b.delta;
  }
  return { q, estimate: null, method: "incomplete_buckets", exact_sample_quantile: false };
}

/**
 * Analyze ONE endpoint's matching snapshots (do not concatenate endpoints).
 * options.quantiles: fractions in (0,1], default [.5,.95,.99].
 * options.assumeMissingBeforeZero: explicit opt-in for entirely new series;
 * default false because absence does not establish a zero baseline.
 * Values/avg retain native metric units; histogram quantiles are estimates.
 */
export function analyzeMetrics(beforeText, afterText, options = {}) {
  const quantiles = options.quantiles ?? [0.5, 0.95, 0.99];
  if (!Array.isArray(quantiles) || quantiles.some(q => !Number.isFinite(q) || q <= 0 || q > 1)) throw new Error("quantiles must be fractions in (0,1]");
  const before = parse(beforeText, "before"), after = parse(afterText, "after");
  const types = new Map([...before.types, ...after.types]);
  const issues = [...before.issues, ...after.issues];
  if (!before.samples.size) issues.push({ code: "no_samples", snapshot: "before" });
  if (!after.samples.size) issues.push({ code: "no_samples", snapshot: "after" });
  for (const [name, type] of before.types) if (after.types.has(name) && after.types.get(name) !== type) issues.push({ code: "type_changed", name });
  const restarted = [...before.samples].some(([key, sample]) => sample.name === "process_start_time_seconds" && after.samples.has(key) && after.samples.get(key).value !== sample.value);
  if (restarted) issues.push({ code: "process_restart_detected" });
  const counters = [], gauges = [], histograms = [], unsupported = [];
  const groups = new Map();
  for (const key of new Set([...before.samples.keys(), ...after.samples.keys()])) {
    const b = before.samples.get(key), a = after.samples.get(key), sample = a ?? b;
    const definition = classify(sample, types);
    const rowIssues = [...new Set([...(b?.issues ?? []), ...(a?.issues ?? [])])];
    if (!b) rowIssues.push("missing_before");
    if (!a) rowIssues.push("missing_after");
    if (issues.some(i => i.code === "type_changed" && i.name === definition.family)) rowIssues.push("type_changed");
    const row = { name: sample.name, labels: sample.labels, before: finite(b?.value), after: finite(a?.value), delta: null, valid: false, issues: rowIssues };
    const monotonic = definition.type === "counter" || definition.type === "histogram";
    if (monotonic && ((b && b.value < 0) || (a && a.value < 0))) rowIssues.push("negative_value");
    if (monotonic && b && a && a.value < b.value) rowIssues.push("reset_or_decrease");
    if (monotonic && restarted) rowIssues.push("process_restart_detected");
    const assumed = !b && a && options.assumeMissingBeforeZero === true;
    if (assumed) row.assumed_zero_baseline = true;
    row.valid = rowIssues.every(code => code === "missing_before" && assumed);
    if (row.valid) row.delta = a.value - (b?.value ?? 0);
    if (definition.type === "histogram") {
      const labels = { ...sample.labels }; delete labels.le;
      const groupKey = identity(definition.family, labels);
      if (!groups.has(groupKey)) groups.set(groupKey, { name: definition.family, labels, count: null, sum: null, buckets: [], issues: [] });
      const group = groups.get(groupKey);
      if (definition.part === "bucket") group.buckets.push({ le: sample.labels.le, ...row });
      else if (definition.part === "count" || definition.part === "sum") group[definition.part] = row;
      else group.issues.push("unsupported_histogram_sample");
    } else if (definition.type === "counter") counters.push(row);
    else if (definition.type === "gauge") gauges.push(row);
    else unsupported.push({ ...row, delta: null, valid: false, type: definition.type });
  }
  for (const group of groups.values()) {
    group.unit = unitOf(group.name);
    group.scope = "endpoint_interval_all_matching_labels";
    group.buckets.sort((a, b) => bound(a.le) - bound(b.le));
    for (const row of [group.count, group.sum, ...group.buckets]) {
      if (!row) group.issues.push("missing_count_or_sum");
      else group.issues.push(...row.issues.filter(code => !(code === "missing_before" && row.assumed_zero_baseline)));
    }
    if (!group.buckets.length || group.buckets.at(-1).le !== "+Inf") group.issues.push("missing_infinite_bucket");
    if (group.buckets.some(b => b.le === undefined || (b.le !== "+Inf" && (!Number.isFinite(Number(b.le)) || Number(b.le) < 0)))) group.issues.push("invalid_or_negative_bucket_bound");
    if (new Set(group.buckets.map(b => bound(b.le))).size !== group.buckets.length) group.issues.push("duplicate_bucket_bound");
    // Partial series creation is not a trustworthy zero baseline, even with opt-in.
    const allRows = [group.count, group.sum, ...group.buckets].filter(Boolean);
    if (allRows.some(r => r.assumed_zero_baseline) && allRows.some(r => !r.assumed_zero_baseline)) group.issues.push("partial_missing_baseline");
    for (const field of ["before", "after", "delta"]) {
      const counts = [group.count?.[field], ...group.buckets.map(b => b[field])];
      if (counts.some(v => v !== null && v !== undefined && !Number.isSafeInteger(v))) group.issues.push(`invalid_${field}_count`);
      const buckets = group.buckets.map(b => b[field]);
      if (buckets.some((v, i) => i > 0 && v !== null && buckets[i - 1] !== null && v < buckets[i - 1])) group.issues.push(`non_monotonic_${field}_buckets`);
      if (group.count?.[field] != null && buckets.at(-1) != null && group.count[field] !== buckets.at(-1)) group.issues.push(`count_infinite_bucket_mismatch_${field}`);
    }
    if (group.count?.delta === 0 && group.sum?.delta !== 0) group.issues.push("sum_changed_without_observations");
    group.issues = [...new Set(group.issues)];
    group.valid = group.issues.length === 0;
    group.avg = group.valid && group.count.delta > 0 ? group.sum.delta / group.count.delta : null;
    group.quantiles = group.valid ? quantiles.map(q => quantileEstimate(group.buckets, group.count.delta, q)) : [];
    histograms.push(group);
  }
  return { schema_version: 1, scope: "endpoint_interval_all_matching_labels", sandbox_attribution: "none",
    assumptions: { missing_before_is_zero: options.assumeMissingBeforeZero === true },
    interpretation: ["Values retain native metric units. Gauge changes are endpoint changes, not event counts or latency.",
      "Histogram average is delta(sum)/delta(count); bucket quantiles are interpolated estimates with bounds, not exact sample percentiles.",
      "Includes every observation between scrapes (warmup, formal and unrelated work); no sandbox or benchmark phase attribution is inferred.",
      "Two snapshots cannot detect every restart/reset, prove exclusive workload, or recover missing increments. Invalid series are not reset-corrected.",
      "v0.7.1 CreateContainer restore sub-stages and Cubelet workflow durations are logs, not exported latency histograms."],
    snapshots: { before_samples: before.samples.size, after_samples: after.samples.size }, issues, counters, histograms, gauges, unsupported };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (args.length !== 2) { console.error("usage: node metrics.mjs BEFORE.prom AFTER.prom > metrics-analysis.json"); process.exitCode = 2; }
  else process.stdout.write(JSON.stringify(analyzeMetrics(fs.readFileSync(args[0], "utf8"), fs.readFileSync(args[1], "utf8")), null, 2) + "\n");
}
