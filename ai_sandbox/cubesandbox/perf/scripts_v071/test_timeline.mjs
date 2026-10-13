import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { buildTimelines, timelineHtml, writeTimeline } from "./timeline.mjs";

const profile = () => ({ case: "c100n100", capture: { started_at: "2026-10-12T00:00:00Z", ended_at: "2026-10-12T00:01:00Z" },
  phases: Object.fromEntries([["formal", ["f1"]], ["warmup", ["w1"]], ["unknown_phase", []]]
    .map(([phase, ids]) => [phase, { create_container_detail: { details: ids.map((instance_id) => ({ instance_id })) } }])) });
const event = (content, milliseconds, id = "f1") => ({ InstanceId: id, LogContent: content,
  ...(milliseconds === null ? {} : { Timestamp: `2026-10-12T00:00:01.${String(milliseconds).padStart(3, "0")}Z` }) });
const normal = () => [event("create req start", 0), event("load spec finish at:2", 3),
  event("start vm start", 10), event("agent is ready", 45), event("start sandbox finish at:60", 61),
  event("start container finish at:90", 91), event("create req finish", 95)];
const build = (records, shim = []) => buildTimelines({ profile: profile(), shim_requests: records, shim });
const interval = (result, id) => result.instances[0].intervals.find((row) => row.id === id);

test("host and monotonic windows retain distinct clocks, origins and truncation", () => {
  const result = build(normal());
  assert.equal(interval(result, "create_request").duration_ms, 95);
  assert.equal(interval(result, "vm_start_to_agent_ready").duration_ms, 35);
  assert.equal(interval(result, "sandbox_finish_to_container_finish").duration_ms, 30);
  const monotonic = interval(result, "after_load_spec_to_sandbox_finish");
  assert.equal(monotonic.start_ms, 2);
  assert.equal(monotonic.end_ms, 60);
  assert.equal(monotonic.alignment, "approximate_to_request_start");
  assert.match(monotonic.uncertainty, /truncated/);
  assert.equal(result.instances[0].events.find((row) => row.id === "load_spec").wall_minus_cumulative_ms, 1);
  assert.equal(result.instances[1].status, "unavailable");
});

test("duplicate markers are ambiguous, including byte-identical duplicates", () => {
  let result = build([...normal(), event("start sandbox finish at:60", 61)]);
  assert.equal(interval(result, "sandbox_finish_to_container_finish").status, "ambiguous");
  assert.equal(interval(result, "sandbox_finish_to_container_finish").duration_ms, null);
  assert.equal(interval(result, "create_request").duration_ms, 95);
  result = build([...normal(), event("create req start", 0)]);
  assert.equal(result.instances[0].status, "ambiguous");
  assert.ok(result.instances[0].intervals.every((row) => row.duration_ms === null));
});

test("missing marker or request origin never silently becomes zero", () => {
  let result = build(normal().filter((row) => row.LogContent !== "agent is ready"));
  assert.equal(interval(result, "vm_start_to_agent_ready").duration_ms, null);
  result = build(normal().filter((row) => row.LogContent !== "create req start"));
  assert.ok(result.instances[0].intervals.every((row) => row.start_ms === null));
  assert.equal(result.instances[0].events.find((row) => row.id === "sandbox_finish").raw_cumulative_ms, 60);
  assert.equal(result.instances[0].events.find((row) => row.id === "sandbox_finish").relative_ms, null);
  result = build([event("create req start", 0), event("load spec finish at:0", 0)]);
  assert.equal(interval(result, "load_spec_cumulative").duration_ms, 0);
});

test("wallclock reversals and out-of-order monotonic markers suppress affected bars", () => {
  let records = normal().map((row) => row.LogContent === "agent is ready" ? event("agent is ready", 5) : row);
  let result = build(records);
  assert.equal(interval(result, "vm_start_to_agent_ready").duration_ms, null);
  assert.equal(result.instances[0].ordering_anomalies.length, 1);
  records = normal().map((row) => row.LogContent === "start container finish at:90" ? event("start container finish at:50", 91) : row);
  result = build(records);
  assert.equal(interval(result, "sandbox_finish_to_container_finish").duration_ms, null);
  assert.equal(result.instances[0].ordering_anomalies[0].earlier, "sandbox_finish");
});

test("stat timers stay unpositioned and forwarded guest logs do not supply host endpoints", () => {
  const result = build([event('{"msg":"agent is ready","ts":"2026-10-11T00:00:00Z"}', 0)],
    [{ InstanceId: "f1", Action: "Create", CalleeAction: "RestoreVm", CostTime: 17, RetCode: "Ok" }]);
  const stat = result.instances[0].unpositioned_durations[0];
  assert.equal(stat.duration_ms, 17);
  assert.equal(stat.start_ms, null);
  assert.equal(stat.end_ms, null);
  assert.ok(result.instances[0].events.every((row) => row.status === "missing"));
  assert.equal(result.integrity.time_unverifiable_records, 1);
});

test("ownership, phase separation, capture window and nanosecond timestamps", () => {
  const records = [...normal(), event("create req start", 0, "foreign"),
    { ...event("create req start", 0, "w1"), Timestamp: "2026-10-11T00:00:01Z" }];
  const result = build(records);
  assert.equal(result.integrity.foreign_records, 1);
  assert.equal(result.integrity.outside_capture_window, 1);
  assert.equal(result.instances[1].phase, "warmup");
  const precise = build([
    { InstanceId: "f1", LogContent: "create req start", Timestamp: "2026-10-12T00:00:01.000000001Z" },
    { InstanceId: "f1", LogContent: "create req finish", Timestamp: "2026-10-12T00:00:01.000000009Z" },
  ]);
  assert.equal(interval(precise, "create_request").duration_ms, 0.000008);
  const conflict = profile();
  conflict.phases.warmup.create_container_detail.details.push({ instance_id: "f1" });
  assert.equal(buildTimelines({ profile: conflict, shim_requests: normal() }).instances.length, 1);
});

test("HTML escapes evidence, remains self-contained, and exposes uncertainty", () => {
  const result = build(normal());
  result.instances[0].instance_id = '<img src=x onerror="alert(1)">';
  result.warnings.push("<script>bad()</script>");
  const html = timelineHtml(result);
  assert.ok(!html.includes('<img src=x'));
  assert.ok(!html.includes("<script>bad()"));
  assert.match(html, /&lt;img/);
  assert.match(html, /<svg/);
  assert.match(html, /仅近似对齐/);
  assert.doesNotMatch(html, /<script src=|<link|https?:\/\//);
});

test("capture-directory writer produces reproducible JSON and standalone viewer", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "cube-timeline-test-"));
  try {
    fs.mkdirSync(path.join(dir, "evidence"));
    fs.writeFileSync(path.join(dir, "capture-manifest.json"), JSON.stringify({ concurrency: 100, requests: 100, warmup: 3,
      started_at: "2026-10-12T00:00:00Z", ended_at: "2026-10-12T00:01:00Z", logs: {} }));
    fs.writeFileSync(path.join(dir, "owned-sandbox-ids.json"), JSON.stringify({ formal: ["f1"], warmup: [], unknown_phase: [] }));
    fs.writeFileSync(path.join(dir, "evidence/shim_req-delta.log"), normal().map(JSON.stringify).join("\n") + "\ninvalid\n");
    const result = writeTimeline(dir);
    assert.equal(result.instances.length, 1);
    assert.ok(result.warnings.some((text) => text.includes("malformed")));
    assert.equal(JSON.parse(fs.readFileSync(path.join(dir, "timeline.json"))).instances[0].status, "partial");
    assert.match(fs.readFileSync(path.join(dir, "timeline.html"), "utf8"), /f1/);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
