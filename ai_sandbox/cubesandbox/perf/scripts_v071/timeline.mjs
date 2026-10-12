#!/usr/bin/env node
// Partial, evidence-backed Shim timelines. No inferred Cubelet trace positions.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { loadProfile } from "./analyze.mjs";

const PHASES = ["formal", "warmup", "unknown_phase"];
const MARKERS = [
  ["request_start", "create req start", "host_wallclock"],
  ["load_spec", /^load spec finish at:(\d+)$/, "shim_monotonic"],
  ["vm_start", "start vm start", "host_wallclock"],
  ["agent_ready", "agent is ready", "host_wallclock"],
  ["sandbox_finish", /^start sandbox finish at:(\d+)$/, "shim_monotonic"],
  ["container_finish", /^start container finish at:(\d+)$/, "shim_monotonic"],
  ["request_finish", "create req finish", "host_wallclock"],
];

// Difference integer nanoseconds before converting to Number, avoiding epoch-ms
// floating-point cancellation. A timestamp's precision is not clock accuracy.
function timestampNs(value) {
  if (typeof value !== "string") return null;
  const match = value.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/);
  if (!match) return null;
  const seconds = Date.parse(match[1] + match[3]);
  return Number.isFinite(seconds) ? BigInt(seconds) * 1000000n + BigInt((match[2] ?? "").padEnd(9, "0")) : null;
}
function recordTime(record) {
  for (const key of ["Timestamp", "@timestamp", "timestamp"]) {
    const value = timestampNs(record[key]);
    if (value !== null) return value;
  }
  return null;
}
const milliseconds = (end, start) => end !== null && start !== null ? Number(end - start) / 1e6 : null;
const duration = (value) => (typeof value === "number" || (typeof value === "string" && value.trim() !== ""))
  && Number.isFinite(Number(value)) && Number(value) >= 0 ? Number(value) : null;

/** Input: {profile: loadProfile(dir), shim_requests: JSONL records, shim: stat records}.
 * Ownership and phase membership come exclusively from the analyzed profile.
 * Cumulative positions are relative to Instant::now(), just after the start log;
 * their alignment to host create-req-start is approximate and explicitly tagged.
 */
export function buildTimelines({ profile, shim_requests = [], shim = [], warnings = [] }) {
  if (!profile?.phases) throw new Error("buildTimelines requires a loadProfile result in input.profile");
  const owners = new Map(), conflicts = new Set();
  for (const phase of PHASES) {
    for (const detail of profile.phases[phase]?.create_container_detail?.details ?? []) {
      const id = detail.instance_id;
      if (typeof id !== "string" || !id) continue;
      if (owners.has(id) && owners.get(id) !== phase) conflicts.add(id);
      else owners.set(id, phase);
    }
  }
  for (const id of conflicts) owners.delete(id);
  const start = timestampNs(profile.capture?.started_at), end = timestampNs(profile.capture?.ended_at);
  const windowValid = start !== null && end !== null && end >= start;
  const integrity = { foreign_records: 0, outside_capture_window: 0, time_unverifiable_records: 0,
    conflicting_ownership_ids: [...conflicts], capture_window_verified: windowValid };
  const requests = new Map(), stats = new Map();
  for (const [records, target] of [[shim_requests, requests], [shim, stats]]) {
    for (const record of records) {
      if (!owners.has(record.InstanceId)) { integrity.foreign_records++; continue; }
      const time = recordTime(record);
      if (time === null) integrity.time_unverifiable_records++;
      if (windowValid && time !== null && (time < start || time > end)) { integrity.outside_capture_window++; continue; }
      if (!target.has(record.InstanceId)) target.set(record.InstanceId, []);
      target.get(record.InstanceId).push(record);
    }
  }
  const instances = [...owners].map(([instance_id, phase]) => {
    const occurrences = Object.fromEntries(MARKERS.map(([name]) => [name, []]));
    for (const record of requests.get(instance_id) ?? []) {
      if (typeof record.LogContent !== "string") continue;
      const content = record.LogContent.trim();
      for (const [name, match, clock] of MARKERS) {
        const found = typeof match === "string" ? content === match : content.match(match);
        if (!found) continue;
        occurrences[name].push({ time: recordTime(record), value: clock === "shim_monotonic" ? duration(found[1]) : null });
      }
    }
    const root = occurrences.request_start;
    const origin = root.length === 1 ? root[0].time : null;
    const repeatedRequest = root.length > 1 || occurrences.request_finish.length > 1;
    const events = MARKERS.map(([id, , clock]) => {
      const items = occurrences[id];
      const one = items.length === 1 ? items[0] : null;
      const observed = one && origin !== null ? (clock === "shim_monotonic" ? one.value : milliseconds(one.time, origin)) : null;
      const status = !items.length ? "missing" : items.length > 1 || repeatedRequest ? "ambiguous"
        : observed === null ? "unanchored" : observed < 0 ? "invalid_order" : "observed";
      const wall = one ? milliseconds(one.time, origin) : null;
      return { id, clock_domain: clock, status, occurrence_count: items.length,
        relative_ms: status === "observed" ? observed : null,
        raw_cumulative_ms: clock === "shim_monotonic" ? one?.value ?? null : null,
        host_timestamp_ns: one?.time?.toString() ?? null,
        host_relative_ms: status === "observed" ? wall : null,
        alignment: clock === "shim_monotonic" ? "approximate_to_request_start; exact_relative_to_Instant_origin" : "same_host_wallclock",
        precision: clock === "shim_monotonic" ? "integer_ms_truncated; actual_elapsed_in_[value,value+1)" : "timestamp_resolution_is_not_clock_accuracy",
        wall_minus_cumulative_ms: status === "observed" && clock === "shim_monotonic" && wall !== null ? wall - observed : null };
    });
    const eventMap = new Map(events.map((event) => [event.id, event]));
    // A host clock step or malformed marker sequence must not produce a plausible
    // bar. Compare only within the same clock domain, never host vs cumulative.
    const ordering_anomalies = [];
    for (const order of [["request_start", "vm_start", "agent_ready", "request_finish"],
      ["load_spec", "sandbox_finish", "container_finish"]]) {
      const observed = order.map((id) => eventMap.get(id)).filter((event) => event.status === "observed");
      for (let index = 1; index < observed.length; index++) {
        const a = observed[index - 1], b = observed[index];
        if (b.relative_ms < a.relative_ms) {
          ordering_anomalies.push({ earlier: a.id, later: b.id, reason: "same_clock_markers_out_of_order" });
          a.status = b.status = "invalid_order";
        }
      }
    }
    for (const event of events) if (event.status !== "observed") event.relative_ms = null;
    const intervals = [];
    const add = (id, first, last, clock, startsAtZero = false) => {
      const a = eventMap.get(first), b = eventMap.get(last);
      const from = startsAtZero ? 0 : a?.relative_ms;
      const to = b?.relative_ms;
      const status = repeatedRequest || a?.status === "ambiguous" || b?.status === "ambiguous" ? "ambiguous"
        : (!startsAtZero && a?.status !== "observed") || b?.status !== "observed" ? "missing_boundary"
          : to < from ? "invalid_order" : "observed";
      intervals.push({ id, clock_domain: clock, status,
        start_ms: status === "observed" ? from : null, end_ms: status === "observed" ? to : null,
        duration_ms: status === "observed" ? to - from : null,
        alignment: clock === "shim_monotonic" ? "approximate_to_request_start" : "same_host_wallclock",
        uncertainty: clock === "shim_monotonic" ? "each_endpoint_truncated_below_1ms; origin_offset_unknown" : "wallclock_adjustment_and_logging_overhead_unbounded",
        additivity: "do_not_sum_overlapping_intervals" });
    };
    add("create_request", "request_start", "request_finish", "host_wallclock");
    add("vm_start_to_agent_ready", "vm_start", "agent_ready", "host_wallclock");
    add("load_spec_cumulative", null, "load_spec", "shim_monotonic", true);
    add("after_load_spec_to_sandbox_finish", "load_spec", "sandbox_finish", "shim_monotonic");
    add("sandbox_finish_to_container_finish", "sandbox_finish", "container_finish", "shim_monotonic");
    const unpositioned_durations = (stats.get(instance_id) ?? []).filter((record) => record.Action === "Create")
      .map((record) => ({ stage: record.CalleeAction ?? null, duration_ms: duration(record.CostTime),
        outcome: record.RetCode ?? null, start_ms: null, end_ms: null,
        reason: "StatDefer elapsed duration only; no verified phase endpoint is available",
        precision: "integer_ms_truncated", additivity: "do_not_sum_nested_stages" }));
    return { instance_id, phase, origin_host_timestamp_ns: origin?.toString() ?? null,
      status: repeatedRequest ? "ambiguous" : intervals.some((item) => item.status === "observed") ? "partial" : "unavailable",
      events, intervals, unpositioned_durations, ordering_anomalies,
      unobserved: ["API/CubeMaster/Cubelet absolute stage placement", "Individual VM and Agent stat timer endpoints",
        "Exact monotonic origin offset from request-start log", "Container-finish to request-finish same-clock interval"],
      clock_diagnostics: { wall_minus_cumulative_ms: events.filter((event) => event.wall_minus_cumulative_ms !== null)
        .map((event) => ({ event: event.id, value: event.wall_minus_cumulative_ms })),
      interpretation: "Differences include logging overhead, origin offset, integer truncation and possible wallclock changes; not a measured clock skew or RPC latency." } };
  });
  return { schema_version: 1, kind: "partial_per_instance_timeline", case: profile.case,
    units: "milliseconds", anchor: "create req start host log; cumulative lane uses subsequent Instant origin",
    integrity, evidence_integrity: profile.evidence_integrity ?? null,
    warnings: [...new Set([...(profile.warnings ?? []), ...warnings,
      ...(!windowValid ? ["Capture time window unavailable; record times cannot be checked."] : [])])],
    interpretation: ["This is a partial Shim timeline, not a fully observed end-to-end request timeline.",
      "Blue host-wallclock and orange monotonic lanes have different origins; orange positions are approximately aligned.",
      "Missing/ambiguous boundaries remain null. Repeated markers are never silently paired.",
      "Cubelet traces are emitted asynchronously in a batch; their timestamps are not stage endpoints.",
      "Shim stat durations without verified endpoints are listed without position. Guest forwarded timestamps are not used.",
      "Intervals overlap. Do not sum their durations or subtract aggregate percentiles."], instances };
}

const escapeHtml = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
const display = (value) => value === null ? "缺失" : `${Number(value.toFixed(3))} ms`;

export function timelineHtml(result) {
  const cards = result.instances.map((instance) => {
    const available = instance.intervals.filter((item) => item.status === "observed");
    const max = Math.max(1, ...available.map((item) => item.end_ms),
      ...instance.events.map((event) => event.relative_ms ?? 0));
    const x = (value) => 285 + value / max * 740;
    const rows = instance.intervals.map((item, index) => {
      const y = 45 + index * 38;
      return `<text x="12" y="${y + 15}" class="label">${escapeHtml(item.id)}</text>` + (item.status !== "observed"
        ? `<text x="285" y="${y + 15}" class="missing">${escapeHtml(item.status)}</text>`
        : `<rect x="${x(item.start_ms)}" y="${y}" width="${Math.max(1, x(item.end_ms) - x(item.start_ms))}" height="21" rx="2" fill="${item.clock_domain === "host_wallclock" ? "#3275b5" : "#b56826"}"><title>${escapeHtml(`${item.id}: ${display(item.start_ms)} → ${display(item.end_ms)}; ${item.alignment}; ${item.uncertainty}`)}</title></rect><text x="1040" y="${y + 15}" class="label">${display(item.duration_ms)}</text>`);
    }).join("");
    const height = 65 + instance.intervals.length * 38;
    const ticks = [0, .25, .5, .75, 1].map((part) => `<text x="${x(max * part)}" y="25" text-anchor="middle" class="label">${display(max * part)}</text>`).join("");
    return `<article data-phase="${escapeHtml(instance.phase)}" data-id="${escapeHtml(instance.instance_id)}"><h2>${escapeHtml(instance.instance_id)} <small>${escapeHtml(instance.phase)} · ${escapeHtml(instance.status)}</small></h2><div class="chart"><svg viewBox="0 0 1160 ${height}" role="img" aria-label="${escapeHtml(instance.instance_id)} 部分时间轴">${ticks}${rows}</svg></div><details><summary>边界证据、缺失和未定位时长</summary><table><thead><tr><th>边界</th><th>状态</th><th>相对位置</th><th>次数</th><th>wall − cumulative</th></tr></thead><tbody>${instance.events.map((event) => `<tr><td>${escapeHtml(event.id)}</td><td>${escapeHtml(event.status)}</td><td>${display(event.relative_ms)}</td><td>${event.occurrence_count}</td><td>${display(event.wall_minus_cumulative_ms)}</td></tr>`).join("")}</tbody></table><p>wall − cumulative 同时包含记录开销、起点偏移、整数截断和可能的墙钟调整，不代表实测时钟偏差。</p><table><thead><tr><th>仅时长，无位置</th><th>时长</th><th>RetCode</th></tr></thead><tbody>${instance.unpositioned_durations.map((item) => `<tr><td>${escapeHtml(item.stage)}</td><td>${display(item.duration_ms)}</td><td>${escapeHtml(item.outcome)}</td></tr>`).join("")}</tbody></table><p>未观测：${instance.unobserved.map(escapeHtml).join("；")}。</p></details></article>`;
  }).join("");
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CubeSandbox 每实例部分时间轴</title><style>body{margin:32px auto;max-width:1280px;padding:0 24px;color:#243342;background:#fafafa;font:15px/1.6 system-ui,sans-serif}h1{font-size:28px}h2{font-size:17px}small{font-weight:400;color:#677583}article{background:white;border:1px solid #dce1e5;margin:20px 0;padding:16px}svg{min-width:850px;width:100%}.chart{overflow:auto}.label{font:12px system-ui;fill:#34495e}.missing{font:12px system-ui;fill:#976121}table{border-collapse:collapse;width:100%;font-size:13px}td,th{text-align:left;border-bottom:1px solid #e7eaed;padding:5px}input,select{font:inherit;padding:6px}details{margin-top:10px}summary{cursor:pointer}li{margin:3px 0}.blue{color:#3275b5}.orange{color:#b56826}</style><h1>CubeSandbox 每实例部分时间轴</h1><p>${escapeHtml(result.case)} · ${result.instances.length} 个归属明确的实例。横轴为相对 create req start 的毫秒位置。<span class="blue">蓝色：同一 host 墙钟</span>；<span class="orange">橙色：Shim 单调时钟累计计时</span>，其起点位于 start 日志之后，和横轴仅近似对齐。整数毫秒向下截断，不应据此解释亚毫秒差异。</p><p>此图只显示有证据的 Shim 窗口。Cubelet 批量 Trace 时间不是阶段结束；无起止点的 stat 只列时长。各行存在包含/重叠关系，不能直接相加。</p><label>阶段 <select id="phase"><option value="all">全部</option>${PHASES.map((phase) => `<option>${phase}</option>`).join("")}</select></label> <label>实例 <input id="filter" placeholder="按 ID 筛选"></label><p id="count"></p>${cards || "<p>没有可归属的实例，未从日志推断所有权。</p>"}<details><summary>采集与归属提示</summary><ul>${result.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul><pre>${escapeHtml(JSON.stringify(result.integrity, null, 2))}</pre></details><script>const phase=document.getElementById('phase'), filter=document.getElementById('filter');function update(){let n=0;document.querySelectorAll('article').forEach(card=>{card.hidden=(phase.value!=='all'&&card.dataset.phase!==phase.value)||!card.dataset.id.includes(filter.value);if(!card.hidden)n++;});document.getElementById('count').textContent='显示 '+n+' 个实例';}phase.addEventListener('change',update);filter.addEventListener('input',update);update();</script></html>\n`;
}

function readRecords(profileDir, manifest, name, warnings) {
  const relative = manifest.logs?.[name]?.delta_path ?? `evidence/${name}-delta.log`;
  const file = path.resolve(profileDir, relative);
  const root = fs.realpathSync(profileDir) + path.sep;
  if (!fs.existsSync(file)) { warnings.push(`Missing ${name} log.`); return []; }
  if (!fs.realpathSync(file).startsWith(root)) { warnings.push(`Rejected ${name} path outside profile directory.`); return []; }
  let invalid = 0;
  const rows = fs.readFileSync(file, "utf8").split("\n").filter((line) => line.trim()).flatMap((line) => {
    try { const record = JSON.parse(line); if (record && typeof record === "object" && !Array.isArray(record)) return [record]; }
    catch { /* Count malformed lines explicitly. */ }
    invalid++; return [];
  });
  if (invalid) warnings.push(`${name}: ${invalid} malformed/non-object log lines excluded.`);
  return rows;
}

export function writeTimeline(profileDir, options = {}) {
  const manifest = JSON.parse(fs.readFileSync(path.join(profileDir, "capture-manifest.json"), "utf8"));
  const warnings = [];
  const result = buildTimelines({ profile: loadProfile(profileDir, options), warnings,
    shim_requests: readRecords(profileDir, manifest, "shim_req", warnings),
    shim: readRecords(profileDir, manifest, "shim_stat", warnings) });
  fs.writeFileSync(path.join(profileDir, "timeline.json"), JSON.stringify(result, null, 2) + "\n");
  fs.writeFileSync(path.join(profileDir, "timeline.html"), timelineHtml(result));
  return result;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const usage = "Usage: node timeline.mjs PROFILE_DIR [--phase-classification FILE]\nWrites timeline.json and self-contained timeline.html.";
  if (process.argv.includes("--help")) console.log(usage);
  else {
    try {
      const args = process.argv.slice(2), options = {};
      if (!args.length) throw new Error(usage);
      for (let index = 1; index < args.length; index++) {
        if (args[index] === "--phase-classification" && args[index + 1]) options.phaseClassification = args[++index];
        else throw new Error(`Unknown/incomplete argument: ${args[index]}`);
      }
      const result = writeTimeline(args[0], options);
      console.log(`Wrote timeline.json and timeline.html (${result.instances.length} instances).`);
    } catch (error) { console.error(`timeline: ${error.message}`); process.exitCode = 2; }
  }
}
