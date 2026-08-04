#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const profileDir = process.argv[2];
if (!profileDir) {
  console.error("usage: analyze_c50_profile.mjs PROFILE_DIR");
  process.exit(2);
}

const evidenceDir = path.join(profileDir, "evidence");
const startupDir = path.join(profileDir, "startup-latency");
const caseName = fs
  .readdirSync(startupDir)
  .find((name) => name.endsWith(".summary.json"))
  ?.replace(".summary.json", "");

if (!caseName) {
  throw new Error(`no case summary found under ${startupDir}`);
}

function quantile(values, percentile) {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.ceil((percentile / 100) * sorted.length) - 1;
  return sorted[Math.max(0, index)];
}

function stats(values) {
  if (values.length === 0) return null;
  const sum = values.reduce((total, value) => total + value, 0);
  return {
    count: values.length,
    avg: sum / values.length,
    p50: quantile(values, 50),
    p95: quantile(values, 95),
    max: Math.max(...values),
  };
}

function readJsonLines(file) {
  return fs
    .readFileSync(file, "utf8")
    .split("\n")
    .filter(Boolean)
    .flatMap((line) => {
      try {
        return [JSON.parse(line)];
      } catch {
        return [];
      }
    });
}

function groupStageStats(records, stageKey) {
  const groups = new Map();
  for (const record of records) {
    const stage = record[stageKey];
    const cost = Number(record.CostTime);
    if (!stage || !Number.isFinite(cost)) continue;
    if (!groups.has(stage)) groups.set(stage, []);
    groups.get(stage).push(cost);
  }
  return Object.fromEntries(
    [...groups.entries()]
      .map(([stage, values]) => [stage, stats(values)])
      .sort((left, right) => (right[1].avg ?? 0) - (left[1].avg ?? 0)),
  );
}

const benchmark = JSON.parse(
  fs.readFileSync(path.join(startupDir, `${caseName}.json`), "utf8"),
);
const benchmarkBlocks = [];
const raw = [...benchmark.raw].sort((left, right) => left.seq - right.seq);
for (let index = 0; index < raw.length; index += 50) {
  const block = raw.slice(index, index + 50);
  const blockStats = stats(block.map((entry) => entry.create_ms));
  benchmarkBlocks.push({
    sequence: `${block[0].seq}-${block.at(-1).seq}`,
    ...blockStats,
  });
}

const cubeletRecords = readJsonLines(path.join(evidenceDir, "cubelet_stat-delta.log"));
const createRoots = cubeletRecords.filter(
  (record) => record.Action === "Create" && record.Callee === "cubebox-service",
);
const instanceIds = new Set(createRoots.map((record) => record.InstanceId));
const cubeletCreate = cubeletRecords.filter(
  (record) => record.Action === "Create" && instanceIds.has(record.InstanceId),
);

const shimRecords = readJsonLines(path.join(evidenceDir, "shim_stat-delta.log"));
const shimCreate = shimRecords.filter(
  (record) => record.Action === "Create" && instanceIds.has(record.InstanceId),
);

const masterRecords = readJsonLines(path.join(evidenceDir, "master-delta.log"));
const masterExtensions = [];
for (const record of masterRecords) {
  if (typeof record.LogContent !== "string") continue;
  if (!record.LogContent.startsWith("CreateSandbox_rsp:")) continue;
  try {
    const response = JSON.parse(record.LogContent.slice("CreateSandbox_rsp:".length));
    if (instanceIds.has(response.sandbox_id)) masterExtensions.push(response.ext_info ?? {});
  } catch {
    // Ignore incomplete or unrelated request log records.
  }
}

const masterStages = {};
for (const stage of ["cube-e2e", "sandbox-probe", "all-probe"]) {
  masterStages[stage] = stats(
    masterExtensions
      .map((extension) => Number(extension[stage]))
      .filter(Number.isFinite),
  );
}

const hostSamplesFile = path.join(evidenceDir, "host-samples.csv");
const hostLines = fs.existsSync(hostSamplesFile)
  ? fs.readFileSync(hostSamplesFile, "utf8").trim().split("\n")
  : [];
const hostHeaders = hostLines.length > 0 ? hostLines[0].split(",") : [];
const hostRows = hostLines.slice(1).map((line) =>
  Object.fromEntries(
    line.split(",").map((value, index) => [hostHeaders[index], Number(value)]),
  ),
);

const cpuFields = ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"];
const hostIntervals = [];
for (let index = 1; index < hostRows.length; index += 1) {
  const previous = hostRows[index - 1];
  const current = hostRows[index];
  const delta = Object.fromEntries(
    cpuFields.map((field) => [field, current[field] - previous[field]]),
  );
  const total = cpuFields.reduce((sum, field) => sum + delta[field], 0);
  const busy = total - delta.idle - delta.iowait - delta.steal;
  const elapsed = current.uptime_s - previous.uptime_s;
  hostIntervals.push({
    end_s: current.uptime_s - hostRows[0].uptime_s,
    elapsed_s: elapsed,
    busy_pct: (busy / total) * 100,
    system_pct: (delta.system / total) * 100,
    iowait_pct: (delta.iowait / total) * 100,
    idle_pct: (delta.idle / total) * 100,
    ctxt_per_s: (current.ctxt - previous.ctxt) / elapsed,
    processes_per_s: (current.processes - previous.processes) / elapsed,
    intr_per_s: (current.intr - previous.intr) / elapsed,
    softirq_per_s: (current.softirq_total - previous.softirq_total) / elapsed,
    runnable: current.runnable,
    procs_running: current.procs_running,
    procs_blocked: current.procs_blocked,
    threads: current.threads,
    shim_count: current.shim_count,
  });
}

const bpfFile = path.join(evidenceDir, "bpftrace-profile.txt");
const bpfText = fs.existsSync(bpfFile) ? fs.readFileSync(bpfFile, "utf8") : "";
const migrationSamples = [...bpfText.matchAll(/@(vm_kernel\[[\s\S]*?migration_entry_wait[\s\S]*?\]): (\d+)/g)]
  .map((match) => Number(match[2]))
  .reduce((sum, value) => sum + value, 0);

const result = {
  case: caseName,
  benchmark: { ...benchmark.summary, create: benchmark.create },
  benchmark_blocks: benchmarkBlocks,
  correlated_instances: instanceIds.size,
  cubelet_stages: groupStageStats(cubeletCreate, "Callee"),
  shim_stages: groupStageStats(shimCreate, "CalleeAction"),
  cubemaster_stages: masterStages,
  host_summary:
    hostRows.length > 0
      ? {
          sample_count: hostRows.length,
          max_runnable: Math.max(...hostRows.map((row) => row.runnable)),
          max_procs_running: Math.max(...hostRows.map((row) => row.procs_running)),
          max_procs_blocked: Math.max(...hostRows.map((row) => row.procs_blocked)),
          max_threads: Math.max(...hostRows.map((row) => row.threads)),
          max_shims: Math.max(...hostRows.map((row) => row.shim_count)),
          max_iowait_pct: Math.max(...hostIntervals.map((row) => row.iowait_pct)),
          max_system_pct: Math.max(...hostIntervals.map((row) => row.system_pct)),
          max_ctxt_per_s: Math.max(...hostIntervals.map((row) => row.ctxt_per_s)),
          max_processes_per_s: Math.max(...hostIntervals.map((row) => row.processes_per_s)),
        }
      : null,
  host_intervals: hostIntervals,
  bpftrace: { migration_entry_wait_samples: migrationSamples },
};

process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
