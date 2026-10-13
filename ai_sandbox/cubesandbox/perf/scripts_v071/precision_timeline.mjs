#!/usr/bin/env node
// Standalone viewer: each monotonic clock gets an independently scaled plot.
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

function render() {
  'use strict';
  const data = JSON.parse(document.getElementById('trace-data').textContent);
  const phaseSelect = document.getElementById('phase'), sandboxSelect = document.getElementById('sandbox');
  const summary = document.getElementById('summary'), plots = document.getElementById('plots');
  const extra = document.getElementById('extra'), coverage = document.getElementById('coverage');
  const el = (tag, text, parent, cls) => {
    const node = document.createElement(tag); if (text !== undefined && text !== null) node.textContent = String(text);
    if (cls) node.className = cls; if (parent) parent.appendChild(node); return node;
  };
  const fmt = ns => {
    if (ns === null || ns === undefined || !Number.isFinite(Number(ns))) return '—';
    const n = Number(ns); return n >= 1e6 ? (n / 1e6).toFixed(3) + ' ms' : n >= 1e3 ? (n / 1e3).toFixed(3) + ' µs' : n.toFixed(1) + ' ns';
  };
  function table(parent, headings, rows) {
    const wrapper = el('div', null, parent, 'table-wrap'), t = el('table', null, wrapper), head = el('tr', null, el('thead', null, t));
    headings.forEach(x => el('th', x, head)); const body = el('tbody', null, t);
    rows.forEach(values => { const tr = el('tr', null, body); values.forEach(x => el('td', x, tr)); });
  }
  function details(parent, title, content) {
    const d = el('details', null, parent); el('summary', title, d); el('pre', JSON.stringify(content, null, 2), d);
  }
  function phaseChanged() {
    sandboxSelect.replaceChildren();
    for (const instance of (data.instances ?? []).filter(x => x.phase === phaseSelect.value)) {
      const o = el('option', instance.instance_id, sandboxSelect); o.value = instance.instance_id;
    }
    update();
  }
  function update() {
    plots.replaceChildren(); extra.replaceChildren(); summary.replaceChildren(); coverage.replaceChildren();
    const population = data.phases?.[phaseSelect.value] ?? {}, batchCoverage = population.cubelet_batch_coverage;
    const selected = (data.instances ?? []).find(x => x.instance_id === sandboxSelect.value && x.phase === phaseSelect.value);
    if (batchCoverage) el('p', 'Cubelet 批次完整覆盖：' + batchCoverage.single_batch_with_request_span_instances + '/' +
      batchCoverage.owned_instances + ' owned；预期 ' + (batchCoverage.expected_request_count ?? '未知') +
      '；多批次实例 ' + batchCoverage.multiple_distinct_batch_instances + '；重复批次实例 ' + batchCoverage.duplicate_batch_instances, summary);
    const rows = Object.entries(population.stages ?? {}).map(([stage, s]) => [stage,
      (s.coverage?.measured_instances ?? 0) + '/' + (s.coverage?.owned_instances ?? 0),
      fmt(s.stats_ns?.avg), fmt(s.stats_ns?.p50), fmt(s.stats_ns?.p95), s.coverage?.repeated_instances ?? 0]);
    table(coverage, ['阶段（包含计时种类）', '统计覆盖', '均值', 'P50', 'P95', '重复实例'], rows);
    if (!selected) { el('p', '此 phase 没有归属明确的实例。', plots); return; }
    const all = selected.intervals ?? [], groups = new Map();
    for (const event of all.filter(x => x.timeline_status === 'monotonic_interval' && x.start_ns !== null && x.end_ns !== null)) {
      const key = event.component + ':' + event.clock_id;
      if (!groups.has(key)) groups.set(key, []); groups.get(key).push(event);
    }
    el('p', '实例 ' + selected.instance_id + '：' + all.length + ' 条可用记录，' + groups.size + ' 个独立时钟视图。', summary);
    for (const events of groups.values()) {
      const component = events[0].component, clock = events[0].clock_id;
      const section = el('section', null, plots, 'clock');
      el('h2', component === 'cubelet' ? 'Cubelet · 请求内单调时钟' : 'Shim · 进程内单调时钟', section);
      const clockText = el('p', 'Clock: ' + clock, section, 'clock-id'); clockText.title = clock;
      const isShim = component === 'shim';
      // BigInt subtraction precedes Number conversion: u128 absolute positions
      // can be large even when the plotted request-local range is small.
      const origin = isShim ? events.reduce((min, x) => BigInt(x.start_ns) < min ? BigInt(x.start_ns) : min, BigInt(events[0].start_ns)) : 0;
      const offset = value => isShim ? Number(BigInt(value) - origin) : Number(value);
      const positioned = events.map(event => ({ event, start: offset(event.start_ns), end: offset(event.end_ns) }))
        .filter(x => Number.isFinite(x.start) && Number.isFinite(x.end) && x.start >= 0 && x.end >= x.start && x.end <= Number.MAX_SAFE_INTEGER);
      const maximum = Math.max(1, ...positioned.map(x => x.end));
      el('p', isShim ? '独立零点 = 本实例此 clock 最早可见 span 开始。不能与 Cubelet 或其他 clock 横向对齐。' :
        '零点 = Cubelet 请求 origin；此图只对齐同一请求内的真实 monotonic_interval。', section, 'muted');
      const axis = el('div', null, section, 'axis'); el('span', '相对开始 / 时长', axis);
      el('span', '0 → ' + fmt(maximum) + '（此图独立比例尺）', axis);
      const parentMap = new Map(events.filter(x => x.span_id).map(x => [x.span_id, x]));
      function depth(event) {
        let n = 0, parent = event.parent_span_id; const seen = new Set();
        while (parent && parent !== '0' && parentMap.has(parent) && !seen.has(parent) && n < 8) {
          seen.add(parent); parent = parentMap.get(parent).parent_span_id; n++;
        }
        return n;
      }
      positioned.sort((a, b) => a.start - b.start || b.end - a.end);
      for (const { event, start, end } of positioned) {
        const row = el('div', null, section, 'plot-row');
        const label = el('div', null, row, 'row-label'); label.style.paddingLeft = (depth(event) * 12) + 'px';
        el('strong', event.stage, label);
        el('small', event.kind + ' · span ' + (event.span_id ?? '—') + ' / parent ' + (event.parent_span_id ?? '—') +
          ' · op ' + event.operation_id + ' · ' + event.outcome, label);
        el('small', fmt(start) + ' / ' + fmt(event.duration_ns), label);
        const track = el('div', null, row, 'track');
        const bar = el('div', null, track, 'bar ' + component + (event.kind === 'derived_interval' ? ' derived' : ''));
        bar.style.left = (start / maximum * 100) + '%'; bar.style.width = Math.max(0.12, (end - start) / maximum * 100) + '%';
        bar.title = event.stage + '\nStart: ' + fmt(start) + '\nDuration: ' + fmt(event.duration_ns) +
          '\nSource: ' + event.timing_source + '\nParent: ' + (event.parent_status ?? 'not emitted') +
          '\nWindow: ' + event.time_window_verification;
      }
      if (positioned.length < events.length) el('p', '部分位置超过安全显示范围，保留在原始数据中。', section, 'warning');
    }
    if (!groups.size) el('p', '没有可确认起止位置的 span。', plots);
    el('h2', '仅持续时间：duration_backfill', extra);
    table(extra, ['阶段', 'kind', 'span / parent', '时长', '状态'], all.filter(x => x.timeline_status === 'duration_only')
      .map(x => [x.stage, x.kind, x.span_id + ' / ' + x.parent_span_id, fmt(x.duration_ns), x.outcome]));
    el('p', '以上记录只有可靠 duration；推定开始时间不会绘入时间轴。', extra, 'muted');
    el('h2', '累计 checkpoints', extra);
    table(extra, ['阶段', 'Clock / Operation', '累计 elapsed', '状态'], all.filter(x => x.kind === 'cumulative')
      .map(x => [x.stage, x.clock_id + ' / ' + x.operation_id, fmt(x.duration_ns), x.outcome]));
    el('p', '累计值不能相加。图中的 A→B 来自同一 clock / operation 的相邻可见 checkpoints，涵盖两点之间全部工作。', extra, 'muted');
    const anomalies = all.filter(x => x.parent_status === 'unverified' || x.skipped_marker_names?.length);
    details(extra, '本实例异常、跳过 marker 与排除记录', { anomalies, excluded_events: selected.excluded_events ?? [],
      rejected_records: (data.rejected_records ?? []).filter(x => x.instance_id === selected.instance_id) });
    details(extra, '本实例全部原始解析记录', selected);
  }
  for (const phase of ['formal', 'warmup', 'unknown_phase']) {
    const option = el('option', phase, phaseSelect); option.value = phase;
  }
  const notes = document.getElementById('notes');
  for (const note of data.interpretation ?? []) el('li', note, notes);
  details(document.getElementById('integrity'), '全局采集完整性、丢弃计数与异常', data.integrity ?? {});
  phaseSelect.addEventListener('change', phaseChanged); sandboxSelect.addEventListener('change', update); phaseChanged();
}
export function precisionTimelineHtml(data) {
  if (data?.schema_version !== 1 || !Array.isArray(data.instances) || !data.phases) throw new Error('Expected precision.json schema_version=1');
  const json = JSON.stringify(data).replaceAll('<', '\\u003c').replaceAll('>', '\\u003e').replaceAll('&', '\\u0026')
    .replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029');
  return `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CubeSandbox · 精细阶段时间轴</title><style>
*{box-sizing:border-box}body{margin:0;background:#f8f9fa;color:#202630;font:14px/1.55 system-ui,-apple-system,sans-serif}main{max-width:1440px;margin:auto;padding:28px}h1{font-size:25px;margin:0 0 10px}h2{font-size:18px;margin:24px 0 8px}p{margin:8px 0}.warning{padding:12px 16px;background:#fff1d9;border-left:3px solid #9a650f}.muted,small{color:#5a6470}label{display:inline-flex;align-items:center;gap:8px;margin:14px 20px 14px 0}select{max-width:80vw;padding:7px;background:white;border:1px solid #bec6ce;border-radius:4px}.clock{margin:20px 0 28px;padding:0 0 18px;border-top:2px solid #aeb8c2}.clock-id{font:12px/1.5 ui-monospace,monospace;overflow-wrap:anywhere;color:#5a6470}.axis,.plot-row{display:grid;grid-template-columns:minmax(210px,32%) 1fr;gap:18px}.axis{padding:8px 0;color:#5a6470}.axis span:last-child{text-align:right}.plot-row{min-height:60px;padding:7px 0;border-top:1px solid #e2e7eb}.row-label{min-width:0;overflow-wrap:anywhere}.row-label strong{font-size:12px;font-weight:600}.row-label small{display:block;font:11px/1.5 ui-monospace,monospace}.track{position:relative;margin:8px 0;background:repeating-linear-gradient(to right,#e1e7ec 0,#e1e7ec 1px,transparent 1px,transparent 25%);overflow:hidden}.bar{position:absolute;top:8px;height:15px;min-width:2px;border-radius:2px}.cubelet{background:#397758}.shim{background:#396a94}.derived{background:#84a9c5;border:1px solid #396a94}.table-wrap{overflow:auto}table{border-collapse:collapse;min-width:640px;width:100%;font-size:12px}th,td{text-align:left;padding:8px;border-bottom:1px solid #dce2e7;vertical-align:top}th{background:#edf1f4}td:first-child{overflow-wrap:anywhere}details{margin:16px 0}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1f4;padding:14px;font:11px/1.5 ui-monospace,monospace}li{margin:6px 0}@media(max-width:700px){main{padding:16px}.axis,.plot-row{grid-template-columns:44% 1fr;gap:8px}.row-label strong{font-size:11px}}
</style></head><body><main>
<h1>CubeSandbox · 精细阶段时间轴</h1>
<p class="warning">各 clock 独立零点、独立比例尺。Cubelet 与 Shim 不能横向对齐或相减；嵌套阶段不能相加。duration_backfill 只列于表格。</p>
<div><label>Phase <select id="phase" aria-label="Phase"></select></label><label>Sandbox <select id="sandbox" aria-label="Sandbox"></select></label></div>
<div id="summary"></div><div id="plots"></div><div id="extra"></div>
<h2>所选 phase 的阶段分布</h2><div id="coverage"></div>
<h2>数据解释与限制</h2><ul id="notes"></ul><div id="integrity"></div>
</main><script type="application/json" id="trace-data">${json}</script><script>(${render.toString()})();</script></body></html>\n`;
}
export function writePrecisionTimeline(input) {
  const file = path.resolve(input), data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const output = path.join(path.dirname(file), 'precision-timeline.html');
  fs.writeFileSync(output, precisionTimelineHtml(data), { mode: 0o600 }); return output;
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  if (process.argv.length !== 3) { console.error('Usage: node precision_timeline.mjs CAPTURE/precision.json'); process.exit(2); }
  console.log(JSON.stringify({ output: writePrecisionTimeline(process.argv[2]) }));
}
