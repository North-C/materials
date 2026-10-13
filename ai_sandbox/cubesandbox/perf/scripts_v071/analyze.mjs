#!/usr/bin/env node
// Adapted from North-C/materials c4b243ac perf/scripts_v2/analyze_c50_profile.mjs.
// Ownership and phase boundaries must come from the collector, never log presence.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { analyzeMetrics } from "./metrics.mjs";
import { loadAndClassify } from "./classify_phases.mjs";

const PHASES = ["formal", "warmup", "unknown_phase"];
const finite = (value) => (typeof value === "number" || (typeof value === "string" && value.trim() !== ""))
  && Number.isFinite(Number(value)) ? Number(value) : null;
const duration = (value) => {
  const number = finite(value);
  return number !== null && number >= 0 ? number : null;
};
export function stats(values) {
  const valid = values.map(duration).filter((value) => value !== null).sort((a, b) => a - b);
  if (!valid.length) return null;
  const quantile = (p) => valid[Math.max(0, Math.ceil(p * valid.length) - 1)];
  return { count: valid.length, avg: valid.reduce((a, b) => a + b, 0) / valid.length,
    min: valid[0], p50: quantile(0.5), p95: quantile(0.95), max: valid.at(-1) };
}
function timestamp(value) {
  if (typeof value !== "string") return null;
  const precise = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$/);
  const number = precise
    ? Date.parse(`${precise[1]}${precise[3]}`) + Number(`0.${precise[2] ?? "0"}`) * 1000
    : Date.parse(value);
  return Number.isFinite(number) ? number : null;
}
function recordTimestamp(record) {
  // Go CubeLog emits @timestamp; Shim request logs emit Timestamp.
  // Shim stat logs have no clock field and must remain time-unverifiable.
  for (const key of ["Timestamp", "@timestamp", "timestamp"]) {
    const parsed = timestamp(record[key]);
    if (parsed !== null) return parsed;
  }
  return null;
}
function difference(end, start) {
  return Number.isFinite(end) && Number.isFinite(start) && end >= start ? end - start : null;
}
function parseObject(value) {
  try { const object = JSON.parse(value); return object && typeof object === "object" ? object : null; }
  catch { return null; }
}

const RELATIONS = {
  "master.cube-e2e": ["api.create", "server_window", "direct_outer"],
  "master.sandbox-probe": ["cubelet.sandbox-probe", "propagated_copy", "propagated_metric"],
  "master.all-probe": ["master.cube-e2e", "aggregate_within", "derived_aggregate"],
  "master_trace.cube-e2e": ["api.create", "server_window", "direct_outer"],
  "master_trace.cubemaster-inner": ["master_trace.cube-e2e", "derived_from", "derived_residual"],
  "master_trace.cubemaster-inner-handle": ["master_trace.cube-e2e", "inside", "direct_inner"],
  "master_trace.cubemaster-post-redis": ["master_trace.cubemaster-inner-handle", "parallel_child", "direct_inner"],
  "master_trace.cubemaster-post-spec": ["master_trace.cubemaster-inner-handle", "parallel_child", "direct_inner"],
  "master_trace.bufferhandle": ["master_trace.cube-e2e", "inside", "direct_inner"],
  "cubelet.cubebox-service": ["master.cube-e2e", "remote_child", "direct_outer"],
  "cubelet.cubebox-service-inner": ["cubelet.cubebox-service", "derived_from", "derived_residual"],
  "cubelet.network": ["cubelet.cubebox-service", "precedes_cubebox", "thresholded_direct"],
  "cubelet.storage": ["cubelet.cubebox-service", "precedes_cubebox", "thresholded_direct"],
  "cubelet.cubebox": ["cubelet.cubebox-service", "inside", "direct_outer"],
  "cubelet.create-sandbox-metadata": ["cubelet.cubebox", "inside", "thresholded_direct"],
  "cubelet.sandbox-start": ["cubelet.cubebox", "inside", "direct_cumulative"],
  "cubelet.sandbox-create": ["cubelet.sandbox-start", "inside", "direct_inner"],
  "cubelet.sandbox-probe": ["cubelet.cubebox", "inside", "direct_inner"],
  "shim.CreatePodSandbox": ["cubelet.sandbox-create", "cross_component_inside", "direct_outer"],
  ...Object.fromEntries(["LaunchVmm", "RestoreVm", "ResetVm", "CreateSandbox", "CreateContainer"]
    .map((stage) => [`shim.${stage}`, ["shim.CreatePodSandbox", "inside", "direct_inner"]])),
};
function relationship(id) {
  const [parent_stage_id, containment, timing_kind] = RELATIONS[id] ?? [null, "unverified", "direct_unknown"];
  return { parent_stage_id, containment, timing_kind, additivity: "do_not_sum" };
}
function coverage(observed, expected, records, expectedRequests) {
  return { observed_instances: observed, owned_instances: expected,
    fraction_of_owned: expected ? observed / expected : null,
    expected_requests: expectedRequests,
    fraction_of_expected_requests: expectedRequests ? observed / expectedRequests : null,
    record_count: records, repeated_instance_records: Math.max(0, records - observed) };
}
function outcome(record) {
  // v0.7.1 CubeShim/shim/src/log/mod.rs StatRet serializes only Ok or Err.
  if (record.RetCode === "Ok") return "success";
  if (record.RetCode === "Err") return "failure";
  const code = finite(record.RetCode);
  // Cubelet/Master ErrorCode_Success is 200; ret helpers also accept OK=0.
  return code === null ? "unknown" : code === 0 || code === 200 ? "success" : "failure";
}
function outcomeCounts(records) {
  return Object.fromEntries(["success", "failure", "unknown"].map((name) =>
    [name, records.filter((record) => outcome(record) === name).length]));
}
function stageSummary(records, key, ids, prefix, expected) {
  const names = new Set(Object.keys(RELATIONS).filter((name) => name.startsWith(`${prefix}.`))
    .map((name) => name.slice(prefix.length + 1)));
  const groups = new Map();
  for (const record of records) {
    if (record.Action !== "Create" || !ids.has(record.InstanceId) || typeof record[key] !== "string") continue;
    const name = record[key];
    names.add(name);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(record);
  }
  return Object.fromEntries([...names].sort().map((name) => {
    const all = groups.get(name) ?? [];
    const valid = all.filter((record) => duration(record.CostTime) !== null);
    return [name, { stats: stats(valid.map((record) => record.CostTime)),
      coverage: coverage(new Set(valid.map((record) => record.InstanceId)).size, ids.size, valid.length, expected),
      outcomes: outcomeCounts(all), measured_outcomes: outcomeCounts(valid),
      stats_population: "All valid-duration records, including any reported failures; inspect outcome counts.",
      invalid_duration_records: all.length - valid.length, ...relationship(`${prefix}.${name}`),
      note: prefix === "cubelet" ? "Successful Cubelet traces below 5 ms can be suppressed; observed samples are conditional on logging." : null }];
  }));
}

function cubeletResiduals(records, ids, expected) {
  const definitions = {
    service_outside_cubebox: ["cubebox-service", ["cubebox"], "Non-contiguous service work outside cubebox, including earlier workflow steps; not pure scheduling."],
    sandbox_after_newtask: ["sandbox-start", ["sandbox-create"], "Same taskStart origin: NewTask return through Wait/Start and following status handling."],
    cubebox_outside_task_and_probe: ["cubebox", ["sandbox-start", "sandbox-probe"], "Non-contiguous cubebox work outside cumulative task start and probe; includes spec/metadata and other work."],
  };
  return Object.fromEntries(Object.entries(definitions).map(([name, [parent, children, note]]) => {
    const samples = [], excluded = [];
    for (const id of ids) {
      const selected = [parent, ...children].map(stage => records.filter(r =>
        r.InstanceId === id && r.Action === "Create" && r.Callee === stage));
      if (selected.some(rows => rows.length !== 1 || outcome(rows[0]) !== "success" || duration(rows[0].CostTime) === null)) {
        excluded.push(id); continue;
      }
      const costs = selected.map(rows => Number(rows[0].CostTime));
      const value = costs[0] - costs.slice(1).reduce((sum, n) => sum + n, 0);
      if (value < 0) { excluded.push(id); continue; }
      samples.push({ instance_id: id, duration_ms: value });
    }
    return [name, { stats: stats(samples.map(s => s.duration_ms)),
      coverage: coverage(samples.length, ids.size, samples.length, expected),
      samples, excluded_instances: excluded, parent_stage_id: `cubelet.${parent}`,
      containment: "derived_from_same_instance", timing_kind: "paired_duration_residual",
      additivity: "do_not_sum", note,
      measured_outcomes: { success: samples.length, failure: 0, unknown: 0 } }];
  }));
}

const DETAIL_TIMERS = ["shim_create_container", "create_request_total", "vm_start_to_agent_ready",
  "load_spec_cumulative", "sandbox_finish_cumulative", "container_finish_cumulative",
  "sandbox_to_container_finish", "guest_receive_to_restore_branch",
  "normal_add_devices", "normal_add_storage", "normal_setup_bundle", "normal_init_container", "normal_start_container"];
function createContainerDetails(requests, shim, ids, phase, expected) {
  const byId = new Map([...ids].map((id) => [id, { instance_id: id, phase, path: "unknown" }]));
  const seen = new Map();
  const first = (object, key, value) => {
    const marker = `${object.instance_id}:${key}`;
    const count = (seen.get(marker) ?? 0) + 1;
    seen.set(marker, count);
    if (count > 1) object.repeated_markers = [...new Set([...(object.repeated_markers ?? []), key])];
    if (object[key] == null && value != null) object[key] = value;
  };
  for (const record of requests) {
    const detail = byId.get(record.InstanceId);
    if (!detail || typeof record.LogContent !== "string") continue;
    const content = record.LogContent.trim();
    const hostTime = recordTimestamp(record);
    const markers = { "create req start": "create_req_start_host_ms", "start vm start": "start_vm_host_ms",
      "agent is ready": "agent_ready_host_ms", "create req finish": "create_req_finish_host_ms" };
    if (markers[content]) first(detail, markers[content], hostTime);
    if (content === "exec a child process") detail.exec_child_entry_seen = true;
    if (content === "exec process start") detail.exec_helper_start_seen = true;
    for (const [pattern, field] of [
      [/^load spec finish at:(\d+(?:\.\d+)?)$/, "load_spec_cumulative_ms"],
      [/^start sandbox finish at:(\d+(?:\.\d+)?)$/, "sandbox_finish_cumulative_ms"],
      [/^start container finish at:(\d+(?:\.\d+)?)$/, "container_finish_cumulative_ms"],
    ]) { const match = content.match(pattern); if (match) first(detail, field, duration(match[1])); }
    const embedded = content.startsWith("{") ? parseObject(content) : null;
    if (embedded?.msg === "[cube-strace]recv create container") first(detail, "guest_create_receive_ms", timestamp(embedded.ts));
    if (embedded?.msg === "create container by restore") {
      detail.path = "snapshot-restore";
      first(detail, "guest_restore_branch_ms", timestamp(embedded.ts));
    }
    const normal = content.match(/created container!, add_devices: (\d+)ms, add storage:(\d+)ms, setup bundle:(\d+)ms, init container:(\d+)ms, start container:(\d+)ms/);
    if (normal) {
      detail.path = "normal-create";
      ["add_devices", "add_storage", "setup_bundle", "init_container", "start_container"]
        .forEach((name, index) => first(detail, `normal_${name}_ms`, Number(normal[index + 1])));
    }
  }
  const details = [...byId.values()].map((detail) => {
    const outer = shim.filter((record) => record.Action === "Create" && record.InstanceId === detail.instance_id
      && record.CalleeAction === "CreateContainer");
    // Multiple container calls cannot safely be joined to one request marker set.
    detail.shim_create_container_ms = outer.length === 1 ? duration(outer[0].CostTime) : null;
    detail.ambiguous_create_container_records = outer.length > 1 ? outer.length : 0;
    detail.create_container_outcome = outer.length === 1 ? outcome(outer[0]) : "unknown";
    detail.create_request_total_ms = difference(detail.create_req_finish_host_ms, detail.create_req_start_host_ms);
    detail.vm_start_to_agent_ready_ms = difference(detail.agent_ready_host_ms, detail.start_vm_host_ms);
    detail.sandbox_to_container_finish_ms = difference(detail.container_finish_cumulative_ms, detail.sandbox_finish_cumulative_ms);
    detail.guest_receive_to_restore_branch_ms = difference(detail.guest_restore_branch_ms, detail.guest_create_receive_ms);
    detail.restore_path_unresolved_ms = difference(detail.shim_create_container_ms, detail.guest_receive_to_restore_branch_ms);
    for (const name of DETAIL_TIMERS) detail[`${name}_ms`] ??= null;
    if (outer.length > 1 || detail.repeated_markers?.length) {
      detail.path = "ambiguous";
      detail.timing_pairing_ambiguous = true;
      for (const name of [...DETAIL_TIMERS, "restore_path_unresolved"]) detail[`${name}_ms`] = null;
    }
    return detail;
  });
  const timings = Object.fromEntries([...DETAIL_TIMERS, "restore_path_unresolved"].map((name) => {
    const valid = details.filter((detail) => duration(detail[`${name}_ms`]) !== null);
    return [name, { stats: stats(valid.map((detail) => detail[`${name}_ms`])),
      coverage: coverage(valid.length, ids.size, valid.length, expected), additivity: "do_not_sum",
      measured_outcomes: Object.fromEntries(["success", "failure", "unknown"].map((outcomeName) =>
        [outcomeName, valid.filter((detail) => detail.create_container_outcome === outcomeName).length])),
      timing_kind: name === "restore_path_unresolved" ? "diagnostic_residual" : "per_instance_measurement" }];
  }));
  return { details, timings, path_counts: Object.fromEntries(["unknown", "normal-create", "snapshot-restore", "ambiguous"]
    .map((name) => [name, details.filter((detail) => detail.path === name).length])),
  interpretation: {
    restore_path_unresolved: "Per-instance Shim duration minus guest branch-selection duration. Includes RPC/preparation and other work; not a direct start_exec_process timer.",
    guest_clock: "Only embedded guest timestamps are differenced. Forwarded host timestamps are asynchronous and are never subtracted from guest timestamps.",
    nested: "Cumulative timers and contained stages overlap; do not sum them or subtract aggregate percentiles.",
  } };
}

function normalizeOwnership(input, warnings) {
  const sets = Object.fromEntries(PHASES.map((phase) => [phase, new Set()]));
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    warnings.push("Ownership file missing or invalid: no component instance is attributable to this run.");
    return sets;
  }
  for (const phase of PHASES) {
    if (!Array.isArray(input[phase])) { warnings.push(`Ownership phase ${phase} missing/invalid; treated as empty.`); continue; }
    for (const id of input[phase]) {
      if (typeof id === "string" && id.trim() && id === id.trim()) sets[phase].add(id);
      else warnings.push(`Invalid ID in ownership phase ${phase} ignored.`);
    }
  }
  const all = new Set(PHASES.flatMap((phase) => [...sets[phase]]));
  for (const id of all) {
    if (PHASES.filter((phase) => sets[phase].has(id)).length > 1) {
      for (const phase of PHASES) sets[phase].delete(id);
      warnings.push(`Conflicting phase membership for ${id}: excluded from all phases.`);
    }
  }
  return sets;
}

export function analyzeCapture(input) {
  const manifest = input.manifest;
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) throw new Error("capture-manifest.json is required and must be an object");
  const warnings = [...(input.warnings ?? [])];
  const owners = normalizeOwnership(input.ownership, warnings);
  const owned = new Set(PHASES.flatMap((phase) => [...owners[phase]]));
  const requests = duration(manifest.requests);
  const warmup = duration(manifest.warmup);
  const start = timestamp(manifest.started_at), end = timestamp(manifest.ended_at);
  const validWindow = start !== null && end !== null && end >= start;
  if (!validWindow) warnings.push("Capture time window missing/invalid; temporal filtering is unavailable.");
  const attribution = {};
  const filtered = {};
  for (const source of ["cubelet", "shim", "shim_requests", "master", "master_stat"]) {
    const report = { input_records: 0, foreign_or_unattributed: 0, outside_capture_window: 0, time_unverifiable: 0, accepted: 0 };
    filtered[source] = [];
    for (const original of input[source] ?? []) {
      report.input_records++;
      let record = original;
      if (source === "master") {
        if (typeof original.LogContent !== "string" || !original.LogContent.startsWith("CreateSandbox_rsp:")) continue;
        const response = parseObject(original.LogContent.slice("CreateSandbox_rsp:".length));
        record = { ...original, RetCode: response?.ret?.ret_code ?? original.RetCode,
          InstanceId: response?.sandbox_id, ext_info: response?.ext_info ?? {} };
      }
      if (!owned.has(record.InstanceId)) { report.foreign_or_unattributed++; continue; }
      const time = recordTimestamp(record);
      if (validWindow && time !== null && (time < start || time > end)) { report.outside_capture_window++; continue; }
      if (!validWindow || time === null) report.time_unverifiable++;
      filtered[source].push(record); report.accepted++;
    }
    attribution[source] = report;
  }
  const phases = {};
  for (const phase of PHASES) {
    const ids = owners[phase];
    const expected = phase === "formal" ? requests : phase === "warmup" ? warmup : null;
    const masterRows = filtered.master.filter((row) => ids.has(row.InstanceId));
    const masterNames = new Set(["cube-e2e", "sandbox-probe", "all-probe"]);
    for (const row of masterRows) for (const name of Object.keys(row.ext_info)) if (name.includes("-probe")) masterNames.add(name);
    const masterStages = Object.fromEntries([...masterNames].map((name) => {
      const valid = masterRows.filter((row) => duration(row.ext_info[name]) !== null);
      return [name, { stats: stats(valid.map((row) => row.ext_info[name])),
        coverage: coverage(new Set(valid.map((row) => row.InstanceId)).size, ids.size, valid.length, expected),
        outcomes: outcomeCounts(masterRows), measured_outcomes: outcomeCounts(valid),
        stats_population: "All valid extension values; missing RetCode is unknown, not presumed success.",
        ...relationship(`master.${name}`) }];
    }));
    phases[phase] = {
      label: phase === "unknown_phase" ? "Owned instances with unverified phase; may include warmup" : phase,
      owned_instance_count: ids.size, expected_request_count: expected,
      ownership_coverage: expected ? ids.size / expected : null,
      cubelet_stages: stageSummary(filtered.cubelet, "Callee", ids, "cubelet", expected),
      shim_stages: stageSummary(filtered.shim, "CalleeAction", ids, "shim", expected),
      cubemaster_stages: masterStages,
      cubemaster_trace_stages: stageSummary(filtered.master_stat, "CalleeAction", ids, "master_trace", expected),
      cubelet_residuals: cubeletResiduals(filtered.cubelet, ids, expected),
      create_container_detail: createContainerDetails(filtered.shim_requests, filtered.shim, ids, phase, expected),
    };
  }
  if (!owners.formal.size) warnings.push("Formal sandbox IDs are unavailable: component stages cannot be claimed as the formal benchmark population.");
  if (requests !== null && owners.formal.size !== requests) warnings.push(`Formal ownership covers ${owners.formal.size}/${requests} requested instances; compare coverage with actual benchmark successes.`);
  if (owners.unknown_phase.size) warnings.push("unknown_phase is reported separately and may include warmup; it is not a formal-only distribution.");
  const rawObject = input.raw;
  const raw = Array.isArray(rawObject) ? rawObject : Array.isArray(rawObject?.raw) ? rawObject.raw : [];
  const successfulRaw = raw.filter((row) => row && !row.error && !row.err && !row.Err);
  const validRaw = successfulRaw.filter((row) => duration(row.create_ms) !== null);
  const summaryObject = input.summary?.summary ?? input.summary ?? rawObject?.summary ?? null;
  const config = rawObject?.config ?? input.summary?.config ?? null;
  const workloadChecks = [
    ["manifest.concurrency", manifest.concurrency, 100], ["manifest.requests", manifest.requests, 100],
    ["manifest.warmup", manifest.warmup, 3], ["report.config.concurrency", config?.concurrency, 100],
    ["report.config.total", config?.total ?? config?.requests ?? config?.iterations, 100],
    ["report.config.warmup", config?.warmup, 3], ["report.config.mode", config?.mode, "create-only"],
  ];
  if (manifest.mode !== undefined) workloadChecks.push(["manifest.mode", manifest.mode, "create-only"]);
  const workloadMismatches = workloadChecks.filter(([, actual, expected]) =>
    typeof expected === "number" ? finite(actual) !== expected : actual !== expected)
    .map(([field, actual, expected]) => ({ field, actual: actual ?? null, expected }));
  const workloadVerified = workloadMismatches.length === 0;
  if (!workloadVerified) warnings.push("Workload is not verified as c100n100/w3/create-only: configuration is absent or mismatched; inspect workload_mismatches.");
  const reportedSuccessful = duration(summaryObject?.successful);
  const observedSuccessful = raw.length ? successfulRaw.length : null;
  const successDenominator = reportedSuccessful ?? observedSuccessful;
  if (reportedSuccessful !== null && observedSuccessful !== null && reportedSuccessful !== observedSuccessful) {
    warnings.push(`Benchmark summary successful=${reportedSuccessful} differs from raw successful=${observedSuccessful}; inspect report completeness.`);
  }
  // Separate ownership coverage, planned load, observed attempts and successes.
  for (const phase of PHASES) {
    const population = phases[phase];
    population.benchmark_successful_instances = phase === "formal" ? successDenominator : null;
    population.benchmark_observed_attempts = phase === "formal" && raw.length ? raw.length : null;
    for (const section of [population.cubelet_stages, population.shim_stages, population.cubemaster_stages, population.cubemaster_trace_stages, population.cubelet_residuals,
      population.create_container_detail.timings]) {
      for (const stage of Object.values(section)) {
        stage.coverage.benchmark_successful_instances = population.benchmark_successful_instances;
        stage.coverage.fraction_of_benchmark_successes = population.benchmark_successful_instances
          ? stage.coverage.observed_instances / population.benchmark_successful_instances : null;
        stage.coverage.benchmark_observed_attempts = population.benchmark_observed_attempts;
        stage.coverage.fraction_of_observed_attempts = population.benchmark_observed_attempts
          ? stage.coverage.observed_instances / population.benchmark_observed_attempts : null;
      }
    }
  }
  const logIntegrity = manifest.logs && typeof manifest.logs === "object" ? manifest.logs : {};
  const logGaps = Object.entries(logIntegrity).flatMap(([name, value]) => {
    const gaps = Array.isArray(value?.gaps) ? [...value.gaps] : [];
    if (value?.status && !["ok", "captured", "complete", "unchanged", "appended"].includes(value.status)) gaps.push(`status:${value.status}`);
    if (value?.before && value?.after) {
      if (value.before.inode !== value.after.inode || value.before.device !== value.after.device) gaps.push("file_identity_changed");
      if (finite(value.after.size) !== null && finite(value.before.size) !== null && Number(value.after.size) < Number(value.before.size)) gaps.push("file_size_decreased");
    }
    return gaps.length ? [{ name, gaps: [...new Set(gaps)] }] : [];
  });
  if (logGaps.length) warnings.push("Log rotation/truncation/capture gaps were reported; stage coverage may be incomplete.");
  const captureGaps = Array.isArray(manifest.gaps) ? manifest.gaps : [];
  if (captureGaps.length) warnings.push("Collector reported additional capture gaps; inspect evidence_integrity.capture_gaps.");
  const commandExitCode = finite(manifest.command?.exit_code);
  if (commandExitCode !== null && commandExitCode !== 0) warnings.push(`Captured command failed with exit code ${commandExitCode}; captured does not mean benchmark success.`);
  if (!Object.keys(logIntegrity).length) warnings.push("Manifest has no log integrity metadata; absence of rotation gaps cannot be established.");
  if (!raw.length) warnings.push("Benchmark raw samples are missing; API latency is unavailable.");
  const result = {
    schema_version: 1, case: workloadVerified ? "c100n100" : "unverified", intended_case: "c100n100",
    workload_verified: workloadVerified, workload_mismatches: workloadMismatches,
    capture: { concurrency: manifest.concurrency ?? null,
      requests, warmup, ownership_mode: manifest.ownership_mode ?? null,
      started_at: manifest.started_at ?? null, ended_at: manifest.ended_at ?? null,
      status: manifest.status ?? null, ownership: manifest.ownership ?? null },
    benchmark_command: { exit_code: commandExitCode, timed_out: manifest.command?.timed_out ?? null },
    benchmark: { population: "Official cube-bench raw samples exclude warmup; cannot join seq to sandbox ID without an explicit mapping.",
      summary: summaryObject, create: stats(validRaw.map((row) => row.create_ms)), raw_sample_count: raw.length,
      valid_sample_count: validRaw.length, excluded_invalid_or_error_samples: raw.length - validRaw.length,
      expected_requests: requests, coverage: requests ? validRaw.length / requests : null,
      observed_attempts: raw.length || null, observed_successful: observedSuccessful,
      reported_successful: reportedSuccessful, successful_denominator: successDenominator,
      coverage_of_successful: successDenominator ? validRaw.length / successDenominator : null,
      coverage_of_observed_attempts: raw.length ? validRaw.length / raw.length : null,
      sample_to_instance_mapping: "unavailable" },
    phases, attribution, evidence_integrity: { logs: logIntegrity, gaps: logGaps, capture_gaps: captureGaps,
      inputs: input.inputs ?? {}, time_filter_applied: validWindow },
    interpretation: [
      "All stage and CreateContainer rows have additivity=do_not_sum. Nested/cumulative/propagated measurements overlap.",
      "Do not subtract aggregate means or percentiles across populations, processes or clocks to invent an unmeasured stage.",
      "A stage statistic describes observed log records; coverage counts distinct owned IDs. Repeated records are exposed, not silently deduplicated.",
      "Missing values remain null, including genuinely absent stages. Zero is included only when explicitly measured.",
      "A short profile does not by itself establish a bottleneck or performance regression.",
    ], warnings: [...new Set(warnings)],
  };
  return result;
}

export function loadProfile(profileDir, options = {}) {
  const inputs = {}, warnings = [];
  function readJson(relative, required = false) {
    const file = path.join(profileDir, relative);
    if (!fs.existsSync(file)) {
      inputs[relative] = { status: "missing" };
      if (required) throw new Error(`Required input missing: ${relative}`);
      return null;
    }
    try { const value = JSON.parse(fs.readFileSync(file, "utf8")); inputs[relative] = { status: "read" }; return value; }
    catch (error) {
      inputs[relative] = { status: "invalid_json" };
      if (required) throw new Error(`Invalid required JSON: ${relative}`);
      warnings.push(`Invalid JSON in ${relative}: excluded.`); return null;
    }
  }
  const manifest = readJson("capture-manifest.json", true);
  function lines(name, fallback) {
    const relative = manifest.logs?.[name]?.delta_path ?? fallback;
    const absolute = path.resolve(profileDir, relative);
    const root = path.resolve(profileDir) + path.sep;
    if (!absolute.startsWith(root)) { warnings.push(`Rejected log path outside profile directory for ${name}.`); return []; }
    if (!fs.existsSync(absolute)) { inputs[relative] = { status: "missing", parsed_records: 0 }; return []; }
    const text = fs.readFileSync(absolute, "utf8");
    const records = []; let invalid = 0;
    for (const line of text.split("\n").filter((line) => line.trim())) {
      const record = parseObject(line);
      if (record && !Array.isArray(record)) records.push(record); else invalid++;
    }
    inputs[relative] = { status: "read", parsed_records: records.length, invalid_lines: invalid,
      final_newline_present: !text || text.endsWith("\n") };
    if (invalid) warnings.push(`${relative}: ${invalid} malformed/non-JSON lines excluded.`);
    return records;
  }
  let ownership = readJson("owned-sandbox-ids.json");
  let phaseClassification = null;
  if (options.phaseClassification) {
    phaseClassification = JSON.parse(fs.readFileSync(options.phaseClassification, "utf8"));
    if (phaseClassification.status !== "classified") throw new Error("Phase classification must have classified status");
    const original = PHASES.flatMap((p) => ownership?.[p] ?? []).sort();
    const proposed = PHASES.flatMap((p) => phaseClassification.ownership?.[p] ?? []).sort();
    if (JSON.stringify(original) !== JSON.stringify(proposed)) throw new Error("Classification changes owned instance set");
    const verified = loadAndClassify(profileDir);
    if (verified.status !== "classified" || JSON.stringify(verified.ownership) !== JSON.stringify(phaseClassification.ownership)
      || JSON.stringify(verified.evidence.files) !== JSON.stringify(phaseClassification.evidence?.files)) {
      throw new Error("Classification is stale or does not match current source evidence");
    }
    ownership = phaseClassification.ownership;
  }
  let raw = readJson("startup-latency/c100n100.raw.json");
  if (raw === null && inputs["startup-latency/c100n100.raw.json"]?.status === "missing") {
    raw = readJson("startup-latency/c100n100.json");
  }
  const summary = readJson("startup-latency/c100n100.summary.json");
  const cubelet = lines("cubelet_stat", "evidence/cubelet_stat-delta.log");
  const shim = lines("shim_stat", "evidence/shim_stat-delta.log");
  const shimRequests = lines("shim_req", "evidence/shim_req-delta.log");
  const master = lines("master", "evidence/master-delta.log");
  const masterStat = lines("master_stat", "evidence/master_stat-delta.log");
  const result = analyzeCapture({ manifest, ownership, raw, summary, cubelet, shim, shim_requests: shimRequests, master, master_stat: masterStat, inputs, warnings });
  result.phase_classification = phaseClassification;
  function metricText(which) {
    const item = manifest.metrics?.[which];
    if (!item || item.status !== "captured" || item.gaps?.length) return null;
    const file = path.resolve(profileDir, item.path ?? `evidence/metrics-${which}.prom`);
    if (!file.startsWith(path.resolve(profileDir) + path.sep) || !fs.existsSync(file)) return null;
    return fs.readFileSync(file, "utf8");
  }
  const before = metricText("before"), after = metricText("after");
  result.metrics = before !== null && after !== null ? analyzeMetrics(before, after) : {
    status: "unavailable", reason: "Both complete, readable metrics snapshots are required" };
  return result;
}

export function stageCsv(result) {
  const headers = ["phase", "component", "stage", "parent_stage_id", "containment", "timing_kind", "additivity",
    "count", "avg_ms", "min_ms", "p50_ms", "p95_ms", "max_ms", "observed_instances", "owned_instances", "expected_requests", "fraction_of_owned", "fraction_of_expected_requests", "repeated_instance_records",
    "benchmark_successful_instances", "fraction_of_benchmark_successes", "benchmark_observed_attempts", "fraction_of_observed_attempts",
    "measured_success_records", "measured_failure_records", "measured_unknown_outcome_records"];
  const rows = [];
  const add = (phase, component, name, stage) => rows.push([phase, component, name, stage.parent_stage_id,
    stage.containment, stage.timing_kind, stage.additivity, stage.stats?.count, stage.stats?.avg, stage.stats?.min,
    stage.stats?.p50, stage.stats?.p95, stage.stats?.max, stage.coverage?.observed_instances,
    stage.coverage?.owned_instances, stage.coverage?.expected_requests, stage.coverage?.fraction_of_owned,
    stage.coverage?.fraction_of_expected_requests, stage.coverage?.repeated_instance_records,
    stage.coverage?.benchmark_successful_instances, stage.coverage?.fraction_of_benchmark_successes,
    stage.coverage?.benchmark_observed_attempts, stage.coverage?.fraction_of_observed_attempts,
    stage.measured_outcomes?.success, stage.measured_outcomes?.failure, stage.measured_outcomes?.unknown]);
  add("formal", "API", "create", { stats: result.benchmark.create, additivity: "do_not_sum", timing_kind: "client_observed",
    coverage: { expected_requests: result.benchmark.expected_requests, fraction_of_expected_requests: result.benchmark.coverage,
      benchmark_successful_instances: result.benchmark.successful_denominator, fraction_of_benchmark_successes: result.benchmark.coverage_of_successful,
      benchmark_observed_attempts: result.benchmark.observed_attempts, fraction_of_observed_attempts: result.benchmark.coverage_of_observed_attempts } });
  for (const phase of PHASES) for (const [component, key] of [["Cubelet", "cubelet_stages"], ["CubeShim", "shim_stages"], ["CubeMaster", "cubemaster_stages"], ["CubeMaster trace", "cubemaster_trace_stages"], ["Cubelet paired residual", "cubelet_residuals"]]) {
    for (const [name, stage] of Object.entries(result.phases[phase][key])) add(phase, component, name, stage);
  }
  for (const phase of PHASES) for (const [name, stage] of Object.entries(result.phases[phase].create_container_detail.timings)) add(phase, "CreateContainer detail", name, stage);
  const cell = (value) => value == null ? "" : /[",\r\n]/.test(String(value)) ? `"${String(value).replaceAll('"', '""')}"` : String(value);
  return [headers, ...rows].map((row) => row.map(cell).join(",")).join("\n") + "\n";
}

function main(args) {
  const usage = "Usage: node analyze.mjs PROFILE_DIR [--csv-out FILE] [--details-out FILE] [--phase-classification FILE]\nJSON summary goes to stdout; default CSV is PROFILE_DIR/stage-latency.csv.\n";
  if (args.includes("--help") || args.includes("-h")) { process.stdout.write(usage); return; }
  if (!args.length) throw new Error(usage.trim());
  const profileDir = args[0]; let csvOut = path.join(profileDir, "stage-latency.csv"), detailsOut = null, phaseClassification = null;
  for (let i = 1; i < args.length; i++) {
    if (args[i] === "--csv-out" && args[i + 1]) csvOut = args[++i];
    else if (args[i] === "--details-out" && args[i + 1]) detailsOut = args[++i];
    else if (args[i] === "--phase-classification" && args[i + 1]) phaseClassification = args[++i];
    else throw new Error(`Unknown/incomplete argument: ${args[i]}`);
  }
  const result = loadProfile(profileDir, { phaseClassification });
  fs.mkdirSync(path.dirname(csvOut), { recursive: true }); fs.writeFileSync(csvOut, stageCsv(result));
  if (detailsOut) {
    const rows = PHASES.flatMap((phase) => result.phases[phase].create_container_detail.details);
    fs.mkdirSync(path.dirname(detailsOut), { recursive: true });
    fs.writeFileSync(detailsOut, rows.map((row) => JSON.stringify(row)).join("\n") + (rows.length ? "\n" : ""));
  }
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try { main(process.argv.slice(2)); }
  catch (error) { console.error(`analyze: ${error.message}`); process.exitCode = 2; }
}
