#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const profileDir = process.argv[2];
if (!profileDir) {
  console.error(
    "usage: analyze_c50_profile.mjs PROFILE_DIR [--details-out FILE] [--csv-out FILE]",
  );
  process.exit(2);
}

let detailsOut = null;
let csvOut = path.join(profileDir, "stage-latency.csv");
for (let index = 3; index < process.argv.length; index += 1) {
  if (process.argv[index] === "--details-out" && process.argv[index + 1]) {
    detailsOut = process.argv[++index];
  } else if (process.argv[index] === "--csv-out" && process.argv[index + 1]) {
    csvOut = process.argv[++index];
  } else {
    throw new Error(`unknown or incomplete argument: ${process.argv[index]}`);
  }
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
    min: Math.min(...values),
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

function parseTimestamp(value) {
  if (typeof value !== "string") return null;
  const precise = value.match(
    /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$/,
  );
  if (precise) {
    const seconds = Date.parse(`${precise[1]}${precise[3]}`);
    const fractionalMs = Number(`0.${precise[2] ?? "0"}`) * 1000;
    return Number.isFinite(seconds) && Number.isFinite(fractionalMs)
      ? seconds + fractionalMs
      : null;
  }
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function parseEmbeddedLog(content) {
  if (typeof content !== "string" || !content.startsWith("{")) return null;
  try {
    return JSON.parse(content.trim());
  } catch {
    return null;
  }
}

function setFirst(target, key, value) {
  if (target[key] == null && value != null) target[key] = value;
}

function difference(end, start) {
  return Number.isFinite(end) && Number.isFinite(start) ? end - start : null;
}

function numericStats(records, key) {
  return stats(records.map((record) => record[key]).filter(Number.isFinite));
}

function csvValue(value) {
  if (value == null) return "";
  const text = typeof value === "number" && !Number.isInteger(value)
    ? value.toFixed(6).replace(/0+$/, "").replace(/\.$/, "")
    : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function buildStageRelationshipCsv(result) {
  const definitions = [
    {
      order: 10, depth: 0, component: "API", id: "api.create", name: "Create API latency",
      parent: "", containment: "root", group: "request", index: 1, previous: "",
      related: "", kind: "direct_outer", additivity: "outer_total",
      source: "benchmark.create",
      note: "客户端观测边界；仅含500个正式请求，不含3个warmup。",
    },
    {
      order: 20, depth: 1, component: "CubeMaster", id: "master.cube-e2e", name: "cube-e2e",
      parent: "api.create", containment: "observed_within", group: "request", index: 2,
      previous: "api.create", related: "", kind: "direct_outer", additivity: "do_not_sum",
      source: "cubemaster_stages.cube-e2e",
      note: "服务端主计时；503条包含warmup，与API边界和样本数不同。",
    },
    {
      order: 30, depth: 2, component: "Cubelet", id: "cubelet.cubebox-service", name: "cubebox-service",
      parent: "master.cube-e2e", containment: "remote_child", group: "master-create", index: 1,
      previous: "", related: "", kind: "direct_outer", additivity: "do_not_sum",
      source: "cubelet_stages.cubebox-service",
      note: "CubeMaster调用Cubelet的服务窗口；跨进程计时，不与父阶段逐样本相减。",
    },
    {
      order: 35, depth: 3, component: "Cubelet", id: "cubelet.cubebox-service-inner", name: "cubebox-service-inner",
      parent: "cubelet.cubebox-service", containment: "derived_from", group: "", index: "",
      previous: "", related: "cubelet.sandbox-probe", kind: "derived_residual", additivity: "do_not_sum",
      source: "cubelet_stages.cubebox-service-inner",
      note: "源码按service - probe - volume派生；不是独立连续时间段。",
    },
    {
      order: 40, depth: 3, component: "Cubelet", id: "cubelet.cubebox", name: "cubebox",
      parent: "cubelet.cubebox-service", containment: "inside", group: "cubelet-service", index: 1,
      previous: "", related: "", kind: "direct_outer", additivity: "do_not_sum",
      source: "cubelet_stages.cubebox",
      note: "Cubelet创建工作流外层；包含sandbox-start和随后执行的sandbox-probe。",
    },
    {
      order: 45, depth: 4, component: "Cubelet", id: "cubelet.network", name: "network",
      parent: "cubelet.cubebox", containment: "partial_observation", group: "", index: "",
      previous: "", related: "", kind: "thresholded_direct", additivity: "do_not_sum",
      source: "cubelet_stages.network",
      note: "只记录超过日志阈值的样本，count不足时不能代表全部请求；顺序不在当前日志中确定。",
    },
    {
      order: 46, depth: 4, component: "Cubelet", id: "cubelet.storage", name: "storage",
      parent: "cubelet.cubebox", containment: "partial_observation", group: "", index: "",
      previous: "", related: "", kind: "thresholded_direct", additivity: "do_not_sum",
      source: "cubelet_stages.storage",
      note: "只记录超过日志阈值的样本，count不足时不能代表全部请求；顺序不在当前日志中确定。",
    },
    {
      order: 49, depth: 4, component: "Cubelet", id: "cubelet.create-sandbox-metadata", name: "create-sandbox-metadata",
      parent: "cubelet.cubebox", containment: "partial_observation", group: "cubelet-container", index: 1,
      previous: "", related: "", kind: "thresholded_direct", additivity: "do_not_sum",
      source: "cubelet_stages.create-sandbox-metadata",
      note: "c.NewContainer元数据创建；在sandbox-start之前执行，仅超过日志阈值的样本可见。",
    },
    {
      order: 50, depth: 4, component: "Cubelet", id: "cubelet.sandbox-start", name: "sandbox-start",
      parent: "cubelet.cubebox", containment: "inside", group: "cubelet-container", index: 2,
      previous: "cubelet.create-sandbox-metadata", related: "", kind: "direct_cumulative", additivity: "do_not_sum",
      source: "cubelet_stages.sandbox-start",
      note: "从NewTask前开始，到task.Start完成；包含sandbox-create。",
    },
    {
      order: 60, depth: 5, component: "Cubelet", id: "cubelet.sandbox-create", name: "sandbox-create",
      parent: "cubelet.sandbox-start", containment: "inside", group: "cubelet-task-start", index: 1,
      previous: "", related: "", kind: "direct_inner", additivity: "do_not_sum",
      source: "cubelet_stages.sandbox-create",
      note: "c.NewTask调用耗时；不能与包含它的sandbox-start相加。",
    },
    {
      order: 70, depth: 6, component: "CubeShim", id: "shim.CreatePodSandbox", name: "CreatePodSandbox",
      parent: "cubelet.sandbox-create", containment: "cross_component_inside", group: "cubelet-new-task", index: 1,
      previous: "", related: "", kind: "direct_outer", additivity: "partial_children",
      source: "shim_stages.CreatePodSandbox",
      note: "Shim创建主窗口；下列Shim子阶段按顺序执行，但未覆盖连接和其他残差。",
    },
    {
      order: 71, depth: 7, component: "CubeShim", id: "shim.LaunchVmm", name: "LaunchVmm",
      parent: "shim.CreatePodSandbox", containment: "inside", group: "shim-create-pod", index: 1,
      previous: "", related: "", kind: "direct_inner", additivity: "partial_sequential_child",
      source: "shim_stages.LaunchVmm", note: "启动VMM进程。",
    },
    {
      order: 72, depth: 7, component: "CubeShim", id: "shim.RestoreVm", name: "RestoreVm",
      parent: "shim.CreatePodSandbox", containment: "inside", group: "shim-create-pod", index: 2,
      previous: "shim.LaunchVmm", related: "", kind: "direct_inner", additivity: "partial_sequential_child",
      source: "shim_stages.RestoreVm", note: "从Template快照恢复VM。",
    },
    {
      order: 73, depth: 7, component: "CubeShim", id: "shim.ResetVm", name: "ResetVm",
      parent: "shim.CreatePodSandbox", containment: "inside", group: "shim-create-pod", index: 3,
      previous: "shim.RestoreVm", related: "", kind: "direct_inner", additivity: "partial_sequential_child",
      source: "shim_stages.ResetVm", note: "agent ready后重置Guest状态；中间连接agent的时间未单独计时。",
    },
    {
      order: 74, depth: 7, component: "CubeShim", id: "shim.CreateSandbox", name: "CreateSandbox",
      parent: "shim.CreatePodSandbox", containment: "inside", group: "shim-create-pod", index: 4,
      previous: "shim.ResetVm", related: "", kind: "direct_inner", additivity: "partial_sequential_child",
      source: "shim_stages.CreateSandbox", note: "Guest Agent CreateSandbox RPC。",
    },
    {
      order: 75, depth: 7, component: "CubeShim", id: "shim.CreateContainer", name: "CreateContainer",
      parent: "shim.CreatePodSandbox", containment: "inside", group: "shim-create-pod", index: 5,
      previous: "shim.CreateSandbox", related: "", kind: "direct_inner", additivity: "partial_sequential_child",
      source: "shim_stages.CreateContainer", note: "Guest Agent CreateContainer RPC所在窗口；当前主要热点。",
    },
    {
      order: 76, depth: 7, component: "CubeShim", id: "shim.create-request-total", name: "create request total",
      parent: "shim.CreatePodSandbox", containment: "equivalent_window", group: "", index: "",
      previous: "", related: "shim.CreatePodSandbox", kind: "direct_boundary", additivity: "do_not_sum",
      source: "create_container_detail.direct_timings_ms.create_request_total",
      note: "create req起止边界，与CreatePodSandbox近似同窗；不可相加。",
    },
    {
      order: 76.1, depth: 8, component: "CubeShim", id: "shim.sandbox-finish-cumulative", name: "sandbox finish cumulative",
      parent: "shim.create-request-total", containment: "cumulative_from_origin", group: "shim-cumulative-boundaries", index: 1,
      previous: "", related: "shim.CreatePodSandbox", kind: "cumulative_marker", additivity: "do_not_sum",
      source: "create_container_detail.direct_timings_ms.sandbox_finish_cumulative",
      note: "从create req起点累计到sandbox完成；表示位置，不是可相加的独立阶段。",
    },
    {
      order: 76.2, depth: 8, component: "CubeShim", id: "shim.container-finish-cumulative", name: "container finish cumulative",
      parent: "shim.create-request-total", containment: "cumulative_from_origin", group: "shim-cumulative-boundaries", index: 2,
      previous: "shim.sandbox-finish-cumulative", related: "shim.CreateContainer", kind: "cumulative_marker", additivity: "do_not_sum",
      source: "create_container_detail.direct_timings_ms.container_finish_cumulative",
      note: "从create req起点累计到container完成；与sandbox累计值做差才得到container窗口。",
    },
    {
      order: 77, depth: 7, component: "CubeShim", id: "shim.vm-start-to-agent-ready", name: "VM start to agent ready",
      parent: "shim.CreatePodSandbox", containment: "overlapping_window", group: "", index: "",
      previous: "", related: "shim.LaunchVmm|shim.RestoreVm|shim.ResetVm", kind: "direct_boundary", additivity: "do_not_sum",
      source: "create_container_detail.direct_timings_ms.vm_start_to_agent_ready",
      note: "跨越VMM启动、restore和agent连接边界，与多个Shim子阶段重叠。",
    },
    {
      order: 78, depth: 8, component: "CubeShim", id: "shim.sandbox-to-container-finish", name: "sandbox finish to container finish",
      parent: "shim.CreateContainer", containment: "equivalent_window", group: "", index: "",
      previous: "", related: "shim.CreateContainer", kind: "direct_boundary", additivity: "do_not_sum",
      source: "create_container_detail.direct_timings_ms.sandbox_to_container_finish",
      note: "同一累计时钟相减得到的container窗口，与CreateContainer近似同窗。",
    },
    {
      order: 79, depth: 8, component: "GuestAgent", id: "guest.receive-to-restore-branch", name: "receive to restore branch",
      parent: "shim.CreateContainer", containment: "cross_component_inside", group: "create-container-derived", index: 1,
      previous: "", related: "", kind: "direct_inner", additivity: "derived_decomposition",
      source: "create_container_detail.direct_timings_ms.guest_receive_to_restore_branch",
      note: "Guest内嵌高精度时间戳；只表示RPC分发和restore分支选择。",
    },
    {
      order: 80, depth: 8, component: "Derived", id: "derived.restore-path-unresolved", name: "restore path unresolved",
      parent: "shim.CreateContainer", containment: "derived_from", group: "create-container-derived", index: 2,
      previous: "guest.receive-to-restore-branch", related: "shim.CreateContainer", kind: "diagnostic_residual", additivity: "derived_decomposition",
      source: "create_container_detail.diagnostic_residual_ms.restore_path_unresolved",
      note: "CreateContainer减Guest分支选择；包含请求准备、RPC和start_exec_process，不是单函数直接计时。",
    },
    {
      order: 90, depth: 4, component: "Cubelet", id: "cubelet.sandbox-probe", name: "sandbox-probe",
      parent: "cubelet.cubebox", containment: "inside", group: "cubelet-container", index: 3,
      previous: "cubelet.sandbox-start", related: "master.sandbox-probe", kind: "direct_inner", additivity: "sequential_child",
      source: "cubelet_stages.sandbox-probe", note: "在runContainer/task.Start完成后执行readiness Probe。",
    },
    {
      order: 91, depth: 5, component: "CubeMaster", id: "master.sandbox-probe", name: "sandbox-probe",
      parent: "cubelet.sandbox-probe", containment: "propagated_copy", group: "", index: "",
      previous: "", related: "cubelet.sandbox-probe", kind: "propagated_metric", additivity: "do_not_sum",
      source: "cubemaster_stages.sandbox-probe", note: "Cubelet Probe耗时经响应传播到CubeMaster；不是第二次Probe。",
    },
    {
      order: 92, depth: 2, component: "CubeMaster", id: "master.all-probe", name: "all-probe",
      parent: "master.cube-e2e", containment: "aggregate_of", group: "", index: "",
      previous: "", related: "master.sandbox-probe", kind: "derived_aggregate", additivity: "do_not_sum",
      source: "cubemaster_stages.all-probe", note: "所有容器Probe之和；本Template只有一个Probe，因此等于sandbox-probe。",
    },
  ];

  const get = (object, dottedPath) => dottedPath
    .split(".")
    .reduce((value, key) => value?.[key], object);
  const knownSources = new Set(definitions.map((definition) => definition.source));
  const fallback = [];
  for (const [section, component, prefix] of [
    ["cubelet_stages", "Cubelet", "cubelet"],
    ["shim_stages", "CubeShim", "shim"],
    ["cubemaster_stages", "CubeMaster", "master"],
  ]) {
    for (const name of Object.keys(result[section] ?? {})) {
      const source = `${section}.${name}`;
      if (knownSources.has(source)) continue;
      fallback.push({
        order: 900 + fallback.length, depth: "", component, id: `${prefix}.${name}`,
        name, parent: "", containment: "unknown", group: "", index: "", previous: "",
        related: "", kind: "direct_unknown", additivity: "do_not_sum", source,
        note: "分析器尚未定义该阶段的顺序和包含关系，请结合源码补充拓扑。",
      });
    }
  }

  const allDefinitions = [...definitions, ...fallback];
  const includedDefinitions = allDefinitions.filter((definition) => get(result, definition.source));
  const definitionsById = new Map(allDefinitions.map((definition) => [definition.id, definition]));
  const effectiveSequence = new Map();
  for (const group of new Set(includedDefinitions.map((definition) => definition.group).filter(Boolean))) {
    const members = includedDefinitions
      .filter((definition) => definition.group === group)
      .sort((left, right) => Number(left.index) - Number(right.index));
    members.forEach((definition, index) => {
      effectiveSequence.set(definition.id, {
        index: index + 1,
        previous: index > 0 ? members[index - 1].id : "",
      });
    });
  }
  const hierarchyPath = (definition, visited = new Set()) => {
    if (!definition.parent || visited.has(definition.id)) return definition.id;
    const parent = definitionsById.get(definition.parent);
    if (!parent) return `${definition.parent} > ${definition.id}`;
    const nextVisited = new Set(visited).add(definition.id);
    return `${hierarchyPath(parent, nextVisited)} > ${definition.id}`;
  };
  const headers = [
    "flow_order", "depth", "component", "stage_id", "stage_name", "parent_stage_id",
    "hierarchy_path", "containment_relation", "sequence_group", "sequence_index", "previous_stage_id",
    "related_stage_ids", "timing_kind", "additivity", "source_field", "count", "avg_ms",
    "min_ms", "p50_ms", "p95_ms", "max_ms", "notes",
  ];
  const rows = includedDefinitions.flatMap((definition) => {
    const stageStats = get(result, definition.source);
    const sequence = effectiveSequence.get(definition.id);
    return [[
      definition.order, definition.depth, definition.component, definition.id, definition.name,
      definition.parent, hierarchyPath(definition), definition.containment, definition.group,
      sequence?.index ?? definition.index, sequence?.previous ?? definition.previous,
      definition.related, definition.kind, definition.additivity,
      definition.source, stageStats.count, stageStats.avg, stageStats.min, stageStats.p50,
      stageStats.p95, stageStats.max, definition.note,
    ]];
  });
  return `${[headers, ...rows].map((row) => row.map(csvValue).join(",")).join("\n")}\n`;
}

function buildCreateContainerDetail(
  shimRequestRecords,
  shimCreateRecords,
  ids,
  eventSource,
) {
  const byInstance = new Map([...ids].map((id) => [id, { instance_id: id }]));
  const outerCreateContainer = new Map(
    shimCreateRecords
      .filter((record) => record.CalleeAction === "CreateContainer")
      .map((record) => [record.InstanceId, Number(record.CostTime)]),
  );

  for (const record of shimRequestRecords) {
    if (!byInstance.has(record.InstanceId) || typeof record.LogContent !== "string") continue;
    const detail = byInstance.get(record.InstanceId);
    const content = record.LogContent.trim();
    const hostTimestamp = parseTimestamp(record.Timestamp);

    if (content === "create req start") setFirst(detail, "create_req_start_host_ms", hostTimestamp);
    else if (content === "start vm start") setFirst(detail, "start_vm_host_ms", hostTimestamp);
    else if (content === "agent is ready") setFirst(detail, "agent_ready_host_ms", hostTimestamp);
    else if (content === "exec a child process") detail.exec_child_entry_seen = true;
    else if (content === "exec process start") detail.exec_helper_start_seen = true;
    else if (content === "create req finish") setFirst(detail, "create_req_finish_host_ms", hostTimestamp);

    const loadSpec = content.match(/^load spec finish at:(\d+(?:\.\d+)?)$/);
    if (loadSpec) detail.load_spec_cumulative_ms = Number(loadSpec[1]);
    const sandboxFinish = content.match(/^start sandbox finish at:(\d+(?:\.\d+)?)$/);
    if (sandboxFinish) detail.sandbox_finish_cumulative_ms = Number(sandboxFinish[1]);
    const containerFinish = content.match(/^start container finish at:(\d+(?:\.\d+)?)$/);
    if (containerFinish) detail.container_finish_cumulative_ms = Number(containerFinish[1]);

    const embedded = parseEmbeddedLog(content);
    if (embedded?.msg === "[cube-strace]recv create container") {
      setFirst(detail, "guest_create_receive_ms", parseTimestamp(embedded.ts));
    } else if (embedded?.msg === "create container by restore") {
      detail.path = "snapshot-restore";
      setFirst(detail, "guest_restore_branch_ms", parseTimestamp(embedded.ts));
    }

    const normal = content.match(
      /created container!, add_devices: (\d+)ms, add storage:(\d+)ms, setup bundle:(\d+)ms, init container:(\d+)ms, start container:(\d+)ms/,
    );
    if (normal) {
      detail.path = "normal-create";
      detail.normal_add_devices_ms = Number(normal[1]);
      detail.normal_add_storage_ms = Number(normal[2]);
      detail.normal_setup_bundle_ms = Number(normal[3]);
      detail.normal_init_container_ms = Number(normal[4]);
      detail.normal_start_container_ms = Number(normal[5]);
    }
  }

  const details = [...byInstance.values()].map((detail) => {
    detail.path ??= "unknown";
    detail.shim_create_container_ms = outerCreateContainer.get(detail.instance_id) ?? null;
    detail.create_request_total_ms = difference(
      detail.create_req_finish_host_ms,
      detail.create_req_start_host_ms,
    );
    detail.vm_start_to_agent_ready_ms = difference(
      detail.agent_ready_host_ms,
      detail.start_vm_host_ms,
    );
    detail.sandbox_to_container_finish_ms = difference(
      detail.container_finish_cumulative_ms,
      detail.sandbox_finish_cumulative_ms,
    );
    detail.guest_receive_to_restore_branch_ms = difference(
      detail.guest_restore_branch_ms,
      detail.guest_create_receive_ms,
    );
    detail.restore_path_unresolved_ms = difference(
      detail.shim_create_container_ms,
      detail.guest_receive_to_restore_branch_ms,
    );
    return detail;
  });

  const markerKeys = [
    "shim_create_container_ms",
    "create_request_total_ms",
    "vm_start_to_agent_ready_ms",
    "sandbox_finish_cumulative_ms",
    "container_finish_cumulative_ms",
    "sandbox_to_container_finish_ms",
    "guest_create_receive_ms",
    "guest_restore_branch_ms",
    "guest_receive_to_restore_branch_ms",
    "exec_child_entry_seen",
    "exec_helper_start_seen",
  ];
  const coverage = Object.fromEntries(
    markerKeys.map((key) => [key, details.filter((detail) => detail[key] != null).length]),
  );
  const pathCounts = {};
  for (const detail of details) pathCounts[detail.path] = (pathCounts[detail.path] ?? 0) + 1;

  return {
    summary: {
      schema_version: 2,
      event_source: eventSource,
      raw_event_count: shimRequestRecords.length,
      instance_count: details.length,
      path_counts: pathCounts,
      marker_coverage: coverage,
      direct_timings_ms: {
        shim_create_container: numericStats(details, "shim_create_container_ms"),
        create_request_total: numericStats(details, "create_request_total_ms"),
        vm_start_to_agent_ready: numericStats(details, "vm_start_to_agent_ready_ms"),
        sandbox_finish_cumulative: numericStats(details, "sandbox_finish_cumulative_ms"),
        container_finish_cumulative: numericStats(details, "container_finish_cumulative_ms"),
        sandbox_to_container_finish: numericStats(details, "sandbox_to_container_finish_ms"),
        guest_receive_to_restore_branch: numericStats(
          details,
          "guest_receive_to_restore_branch_ms",
        ),
      },
      normal_path_agent_timings_ms: {
        add_devices: numericStats(details, "normal_add_devices_ms"),
        add_storage: numericStats(details, "normal_add_storage_ms"),
        setup_bundle: numericStats(details, "normal_setup_bundle_ms"),
        init_container: numericStats(details, "normal_init_container_ms"),
        start_container: numericStats(details, "normal_start_container_ms"),
      },
      diagnostic_residual_ms: {
        restore_path_unresolved: numericStats(details, "restore_path_unresolved_ms"),
      },
      interpretation: {
        sandbox_to_container_finish:
          "Same-process cumulative timer difference; directly comparable with Shim CreateContainer.",
        guest_receive_to_restore_branch:
          "Same guest clock; measures dispatch and branch selection before start_exec_process.",
        restore_path_unresolved:
          "Shim CreateContainer minus guest branch-selection time. It includes request preparation/RPC and start_exec_process, so it is not a direct start_exec_process timer.",
        forwarded_log_timestamps:
          "Wrapper timestamps for guest stdout/stderr are intentionally not subtracted because forwarding is asynchronous and may reorder delivery.",
      },
    },
    details,
  };
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
const focusedCreateContainerFile = path.join(evidenceDir, "create-container-events.jsonl");
const shimRequestFile = fs.existsSync(focusedCreateContainerFile)
  ? focusedCreateContainerFile
  : path.join(evidenceDir, "shim_req-delta.log");
const shimRequestRecords = fs.existsSync(shimRequestFile) ? readJsonLines(shimRequestFile) : [];
const createContainerDetail = buildCreateContainerDetail(
  shimRequestRecords,
  shimCreate,
  instanceIds,
  path.relative(profileDir, shimRequestFile),
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
  create_container_detail: createContainerDetail.summary,
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
  generated_files: {
    stage_latency_csv: path.relative(profileDir, csvOut),
    create_container_details_jsonl: detailsOut
      ? path.relative(profileDir, detailsOut)
      : null,
  },
};

if (detailsOut) {
  fs.mkdirSync(path.dirname(detailsOut), { recursive: true });
  fs.writeFileSync(
    detailsOut,
    `${createContainerDetail.details.map((detail) => JSON.stringify(detail)).join("\n")}\n`,
  );
}

fs.mkdirSync(path.dirname(csvOut), { recursive: true });
fs.writeFileSync(csvOut, buildStageRelationshipCsv(result));

process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
