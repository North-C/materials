import test from "node:test";
import assert from "node:assert/strict";
import { analyzeCapture, stats, stageCsv } from "./analyze.mjs";

const base = () => ({ manifest: { concurrency: 100, requests: 100, warmup: 3,
  started_at: "2026-10-12T00:00:00Z", ended_at: "2026-10-12T00:00:10Z", ownership_mode: "exclusive-template",
  logs: { cubelet_stat: { status: "captured", gaps: [] } } },
ownership: { formal: ["f1", "f2"], warmup: ["w1"], unknown_phase: ["u1"] },
raw: { raw: [{ seq: 1, create_ms: 15 }, { seq: 2, create_ms: 25 }] } });
const cubelet = (id, cost, stage = "cubebox-service", extra = {}) => ({ InstanceId: id,
  Timestamp: "2026-10-12T00:00:01Z", Action: "Create", Callee: stage, CostTime: cost, ...extra });
const shim = (id, cost, stage = "CreateContainer") => ({ ...cubelet(id, cost), CalleeAction: stage });
const event = (id, content, time = "2026-10-12T00:00:01Z") => ({ InstanceId: id, LogContent: content, Timestamp: time });

test("paired Cubelet residual uses unique same-instance successful durations, not percentile differences", () => {
  const input = base();
  input.cubelet = [cubelet("f1", 100, "cubebox-service", { RetCode: 200 }),
    cubelet("f1", 80, "cubebox", { RetCode: 200 }),
    cubelet("f2", 10, "cubebox-service", { RetCode: 200 }),
    cubelet("f2", 30, "cubebox", { RetCode: 200 })];
  const stage = analyzeCapture(input).phases.formal.cubelet_residuals.service_outside_cubebox;
  assert.equal(stage.stats.avg, 20);
  assert.equal(stage.coverage.observed_instances, 1);
  assert.deepEqual(stage.excluded_instances, ["f2"]);
  input.cubelet.push(input.cubelet[0]);
  assert.equal(analyzeCapture(input).phases.formal.cubelet_residuals.service_outside_cubebox.stats, null);
});

test("v0.7.1 real success code is 200, including nested Master responses", () => {
  const input = base();
  input.cubelet = [cubelet("f1", 12, "cubebox-service", { RetCode: 200 })];
  input.master = [event("f1", 'CreateSandbox_rsp:{"sandbox_id":"f1","ret":{"ret_code":200},"ext_info":{"cube-e2e":"20"}}')];
  const result = analyzeCapture(input);
  assert.equal(result.phases.formal.cubelet_stages["cubebox-service"].measured_outcomes.success, 1);
  assert.equal(result.phases.formal.cubemaster_stages["cube-e2e"].measured_outcomes.success, 1);
});

test("duplicate request markers cannot be silently paired with a single Shim stat", () => {
  const input = base();
  input.shim = [shim("f1", 30)];
  input.shim_requests = [event("f1", "create req start"), event("f1", "create req start"),
    event("f1", "create req finish", "2026-10-12T00:00:01.080Z")];
  const detail = analyzeCapture(input).phases.formal.create_container_detail.details.find(r => r.instance_id === "f1");
  assert.equal(detail.path, "ambiguous");
  assert.equal(detail.create_request_total_ms, null);
  assert.deepEqual(detail.repeated_markers, ["create_req_start_host_ms"]);
});

test("foreign IDs are excluded; formal, warmup and unknown populations stay separate", () => {
  const input = base();
  input.cubelet = [cubelet("f1", 10), cubelet("f2", 20), cubelet("w1", 500), cubelet("u1", 900), cubelet("foreign", 99999)];
  input.shim = [shim("f1", 7), shim("foreign", 1234)];
  input.master = ["f1", "foreign", "w1"].map((id) => event(id,
    `CreateSandbox_rsp:${JSON.stringify({ sandbox_id: id, ext_info: { "cube-e2e": id === "foreign" ? 999 : 30 } })}`));
  const result = analyzeCapture(input);
  assert.equal(result.phases.formal.cubelet_stages["cubebox-service"].stats.avg, 15);
  assert.equal(result.phases.warmup.cubelet_stages["cubebox-service"].stats.avg, 500);
  assert.equal(result.phases.unknown_phase.cubelet_stages["cubebox-service"].stats.avg, 900);
  assert.match(result.phases.unknown_phase.label, /may include warmup/);
  assert.equal(result.phases.formal.cubemaster_stages["cube-e2e"].stats.count, 1);
  assert.equal(result.attribution.cubelet.foreign_or_unattributed, 1);
  assert.equal(result.attribution.shim.foreign_or_unattributed, 1);
  assert.equal(result.attribution.master.foreign_or_unattributed, 1);
  assert.equal(result.benchmark.create.count, 2);
});

test("missing ownership never infers attribution from root logs", () => {
  const input = base(); delete input.ownership;
  input.cubelet = [cubelet("f1", 100)]; input.shim = [shim("f1", 20)];
  const result = analyzeCapture(input);
  assert.equal(result.phases.formal.owned_instance_count, 0);
  assert.equal(result.phases.formal.cubelet_stages["cubebox-service"].stats, null);
  assert.equal(result.phases.formal.create_container_detail.details.length, 0);
  assert.equal(result.attribution.cubelet.foreign_or_unattributed, 1);
});

test("missing/null/empty durations stay absent, measured zero is retained, coverage is explicit", () => {
  const input = base();
  input.cubelet = [cubelet("f1", null), cubelet("f2", ""), cubelet("f1", 0, "network")];
  input.master = [event("f1", 'CreateSandbox_rsp:{"sandbox_id":"f1","ext_info":{"sandbox-probe":null}}')];
  const result = analyzeCapture(input);
  assert.equal(result.phases.formal.cubelet_stages["cubebox-service"].stats, null);
  assert.equal(result.phases.formal.cubemaster_stages["sandbox-probe"].stats, null);
  assert.equal(result.phases.formal.cubelet_stages.network.stats.avg, 0);
  assert.equal(result.phases.formal.cubelet_stages.network.coverage.fraction_of_owned, 0.5);
  assert.equal(result.phases.formal.cubelet_stages.network.coverage.fraction_of_expected_requests, 0.01);
  assert.equal(result.phases.formal.create_container_detail.timings.shim_create_container.stats, null);
  assert.equal(stats([undefined, null, "", false, -1]), null);
});

test("nested stages are explicitly non-additive, corrected network topology and missing CSV cells", () => {
  const input = base(); input.cubelet = [cubelet("f1", 100), cubelet("f1", 80, "cubebox"), cubelet("f1", 60, "sandbox-start")];
  const result = analyzeCapture(input);
  const stages = result.phases.formal.cubelet_stages;
  assert.equal(stages.cubebox.parent_stage_id, "cubelet.cubebox-service");
  assert.equal(stages.network.parent_stage_id, "cubelet.cubebox-service");
  assert.equal(stages.network.containment, "precedes_cubebox");
  assert.equal(stages["sandbox-start"].additivity, "do_not_sum");
  assert.equal(result.phases.formal.shim_stages.CreateContainer.additivity, "do_not_sum");
  assert.ok(result.interpretation.some((text) => text.includes("Do not subtract aggregate")));
  const csv = stageCsv(result);
  assert.match(csv, /do_not_sum/);
  assert.doesNotMatch(csv, /500|503|当前主要热点/);
});

test("CreateContainer uses same-clock per-instance differences, excludes foreign events", () => {
  const input = base(); input.shim = [shim("f1", 30)];
  input.shim_requests = [event("f1", "create req start", "2026-10-12T00:00:01.000Z"),
    event("f1", "create req finish", "2026-10-12T00:00:01.080Z"),
    event("f1", "start sandbox finish at:40"), event("f1", "start container finish at:70"),
    event("f1", '{"msg":"[cube-strace]recv create container","ts":"2026-10-11T23:00:00.000Z"}'),
    event("f1", '{"msg":"create container by restore","ts":"2026-10-11T23:00:00.002Z"}'),
    event("foreign", "start container finish at:9999")];
  const result = analyzeCapture(input);
  const detail = result.phases.formal.create_container_detail.details[0];
  assert.equal(detail.create_request_total_ms, 80);
  assert.equal(detail.sandbox_to_container_finish_ms, 30);
  assert.equal(detail.guest_receive_to_restore_branch_ms, 2);
  assert.equal(detail.restore_path_unresolved_ms, 28);
  assert.equal(result.attribution.shim_requests.foreign_or_unattributed, 1);
  assert.equal(result.phases.formal.create_container_detail.timings.create_request_total.coverage.observed_instances, 1);
});

test("rotation gaps and capture-window exclusions are visible", () => {
  const input = base(); input.manifest.logs.shim_stat = { status: "rotated", gaps: ["old inode unavailable"],
    before: { inode: 1, device: 4, size: 200 }, after: { inode: 2, device: 4, size: 20 } };
  input.cubelet = [cubelet("f1", 9, "cubebox-service", { Timestamp: "2026-10-11T00:00:01Z" }),
    cubelet("f2", 20, "cubebox-service", { Timestamp: undefined })];
  const result = analyzeCapture(input);
  assert.equal(result.attribution.cubelet.outside_capture_window, 1);
  assert.equal(result.attribution.cubelet.time_unverifiable, 1);
  assert.equal(result.phases.formal.cubelet_stages["cubebox-service"].stats.avg, 20);
  assert.ok(result.evidence_integrity.gaps[0].gaps.includes("file_identity_changed"));
  assert.ok(result.warnings.some((text) => text.includes("rotation")));
});

test("conflicting ownership excluded, repeated component records exposed and not falsely joined", () => {
  const input = base(); input.ownership.warmup.push("f2");
  input.shim = [shim("f1", 10), shim("f1", 20), shim("f2", 999)];
  input.shim_requests = [event("f1", "start sandbox finish at:10"), event("f1", "start container finish at:20")];
  const result = analyzeCapture(input);
  assert.equal(result.phases.formal.owned_instance_count, 1);
  assert.equal(result.phases.formal.shim_stages.CreateContainer.coverage.repeated_instance_records, 1);
  assert.equal(result.phases.formal.create_container_detail.details[0].shim_create_container_ms, null);
  assert.equal(result.phases.formal.create_container_detail.details[0].ambiguous_create_container_records, 2);
  assert.equal(result.phases.formal.create_container_detail.details[0].sandbox_to_container_finish_ms, null);
  assert.equal(result.phases.formal.create_container_detail.timings.sandbox_to_container_finish.stats, null);
  assert.ok(result.warnings.some((text) => text.includes("Conflicting phase")));
});

test("workload must agree with the manifest and official report config", () => {
  const input = base();
  input.raw.config = { concurrency: 100, total: 100, warmup: 3, mode: "create-only" };
  assert.equal(analyzeCapture(input).workload_verified, true);
  input.raw.config.concurrency = 50;
  const result = analyzeCapture(input);
  assert.equal(result.workload_verified, false);
  assert.equal(result.case, "unverified");
  assert.deepEqual(result.workload_mismatches[0], { field: "report.config.concurrency", actual: 50, expected: 100 });
  delete input.raw.config;
  assert.equal(analyzeCapture(input).workload_verified, false);
});

test("stage outcome counts distinguish failures, successes and unknown RetCode", () => {
  const input = base();
  input.cubelet = [cubelet("f1", 10, "cubebox-service", { RetCode: 0 }),
    cubelet("f2", 90, "cubebox-service", { RetCode: "7" }), cubelet("f1", 30)];
  const stage = analyzeCapture(input).phases.formal.cubelet_stages["cubebox-service"];
  assert.deepEqual(stage.outcomes, { success: 1, failure: 1, unknown: 1 });
  assert.deepEqual(stage.measured_outcomes, stage.outcomes);
  assert.match(stage.stats_population, /failures/);
});

test("API errors are excluded and successful/attempted/planned coverage stay distinct", () => {
  const input = base();
  input.raw = { raw: [{ seq: 1, create_ms: 10 }, { seq: 2, create_ms: 999, err: "HTTP 500" },
    { seq: 3, create_ms: 999, error: "timeout" }, { seq: 4, create_ms: null }], summary: { successful: 2, errors: 2 } };
  input.cubelet = [cubelet("f1", 8)];
  const result = analyzeCapture(input);
  assert.equal(result.benchmark.create.avg, 10);
  assert.equal(result.benchmark.observed_attempts, 4);
  assert.equal(result.benchmark.observed_successful, 2);
  assert.equal(result.benchmark.coverage_of_successful, 0.5);
  assert.equal(result.benchmark.coverage_of_observed_attempts, 0.25);
  assert.equal(result.benchmark.coverage, 0.01);
  const stage = result.phases.formal.cubelet_stages["cubebox-service"];
  assert.equal(stage.coverage.fraction_of_benchmark_successes, 0.5);
  assert.equal(stage.coverage.fraction_of_observed_attempts, 0.25);
  assert.equal(stage.coverage.fraction_of_expected_requests, 0.01);
});

test("actual Go CubeLog @timestamp schema supports timezone and capture-window filtering", () => {
  const input = base();
  input.cubelet = [
    { Action: "Create", Callee: "cubebox-service", InstanceId: "f1", CostTime: 12.5, RetCode: 0,
      "@timestamp": "2026-10-12T08:00:01.50486491+08:00" },
    { Action: "Create", Callee: "cubebox-service", InstanceId: "f2", CostTime: 999, RetCode: 0,
      "@timestamp": "2026-10-12T07:59:59.50486491+08:00" },
  ];
  input.master = [{ "@timestamp": "2026-10-12T08:00:01.07970315+08:00", RetCode: 0,
    LogContent: 'CreateSandbox_rsp:{"sandbox_id":"f1","ext_info":{"cube-e2e":"15","sandbox-probe":"2","all-probe":"2"}}' }];
  const result = analyzeCapture(input);
  assert.equal(result.phases.formal.cubelet_stages["cubebox-service"].stats.avg, 12.5);
  assert.equal(result.attribution.cubelet.outside_capture_window, 1);
  assert.equal(result.attribution.cubelet.time_unverifiable, 0);
  assert.equal(result.attribution.master.time_unverifiable, 0);
  assert.equal(result.phases.formal.cubemaster_stages["cube-e2e"].stats.avg, 15);
});

test("actual Rust Shim stat schema classifies Ok/Err without inventing timestamps", () => {
  const input = base();
  input.shim = [
    { Module: "cube-shim", InstanceId: "f1", ContainerId: "c1", Caller: "cube-shim", Action: "Create",
      Callee: "Agent", CalleeAction: "CreateContainer", RetCode: "Ok", CostTime: 29, FunctionType: "" },
    { Module: "cube-shim", InstanceId: "f2", ContainerId: "c2", Caller: "cube-shim", Action: "Create",
      Callee: "Agent", CalleeAction: "CreateContainer", RetCode: "Err", CostTime: 74, FunctionType: "" },
  ];
  const result = analyzeCapture(input);
  const stage = result.phases.formal.shim_stages.CreateContainer;
  assert.deepEqual(stage.outcomes, { success: 1, failure: 1, unknown: 0 });
  assert.deepEqual(stage.measured_outcomes, stage.outcomes);
  assert.equal(result.attribution.shim.time_unverifiable, 2);
  assert.deepEqual(result.phases.formal.create_container_detail.timings.shim_create_container.measured_outcomes,
    { success: 1, failure: 1, unknown: 0 });
});
