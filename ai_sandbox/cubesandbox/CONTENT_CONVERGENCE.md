---
status: in-progress
scope: CubeSandbox canonical, supersede, evidence and duplicate mapping
last_verified: 2026-08-29
source_revision: f036fd2 (navigation and file-relationship review only)
canonical: true
evidence_manifest: partial
---

# CubeSandbox 内容收敛图

本文件是 CubeSandbox 的内容收敛索引。它只整理现有文档之间的关系，不移动、改名、删除或重写任何技术正文、脚本、日志和证据。

## 使用规则

- 先从 `README.md` 进入主题，再用本文件判断 canonical、historical、evidence、publication 和 duplicate candidate。
- `canonical` 表示当前推荐入口，不表示已对全部历史实验重新复测。
- `superseded` 表示结论关系被后续文档修正或吸收，原文仍保留为历史证据链。
- `publication` 可以面向读者重写表达，但不能替代 root-cause 报告、源码 revision 或 evidence manifest。
- `duplicate candidate` 只进入收敛提案；未确认调用方和打包边界前不删除。

## 主题级 Canonical Map

| Topic | Canonical entry | Supporting evidence | Historical or related inputs | Current decision |
|---|---|---|---|---|
| Project navigation | [README.md](README.md) | This file | existing top-level reports | `README.md` remains the project entry |
| External evidence availability | [EVIDENCE_AVAILABILITY.md](EVIDENCE_AVAILABILITY.md) | local verification archive | legacy `remote-results/`, `source_code/`, absolute verification links | All 327 extracted paths resolved locally on 2026-08-29; convert to manifests before publishing |
| Snapshot/lifecycle concept | [testcases_analysis/README.md](testcases_analysis/README.md) | diagrams and source evidence under `testcases_analysis/` | [snapshot-deep-dive.md](snapshot-deep-dive.md), [snapshot-runtime-deep-dive.md](snapshot-runtime-deep-dive.md), [CUBESANDBOX_TEMPLATE_AND_SNAPSHOT_CONTENT_ANALYSIS.md](CUBESANDBOX_TEMPLATE_AND_SNAPSHOT_CONTENT_ANALYSIS.md) | `testcases_analysis/` is the current implementation-oriented entry; the two deep dives stay as explanation candidates |
| ARM64 AP1R/NMI restore failure | [bug-fixes/CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md](bug-fixes/CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md) | [debug/arm64-vgic-ap1r-nmi-active-20260806/README.md](debug/arm64-vgic-ap1r-nmi-active-20260806/README.md), `bug-fixes/analysis/.../key-data/` | WFI/timer/multi-vCPU restore reports dated 2026-07-17 to 2026-07-24 | Treat root-cause report as conclusion candidate; prior reports become historical investigation chain |
| AP1R fix validation bundle | [debug/arm64-vgic-ap1r-nmi-active-20260806/README.md](debug/arm64-vgic-ap1r-nmi-active-20260806/README.md) | `SHA256SUMS`, `data/*.tsv`, `evidence/*.log`, `fixes/*.patch`, validation script | older remote-results references in 2026-07-31 report | Treat as evidence entry; missing external raw logs remain controlled/unavailable unless separately imported |
| Benchmark workflow | [benchmark/README.md](benchmark/README.md) | `benchmark/docs/`, `benchmark/scripts/`, `benchmark/checksums/` | `benchmark/reports/` historical reports and CSV | Subdomain canonical; image tar packages remain outside Git except checksum/manifest |
| Benchmark result interpretation | [testcases_analysis/README.md](testcases_analysis/README.md) plus [benchmark/reports/README.md](benchmark/reports/README.md) | CSV summaries in `benchmark/reports/cube-bench-sdk-formal-arm64-2c4g-20260716/` | formal install/test reports | Keep reports as historical evidence; use reports manifest before moving or pruning |
| Profiling metric semantics | [perf/CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md](perf/CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md) | `perf/scripts_v2/` scripts | older top-level performance reports | Current reference candidate for v0.5.1 metric definitions |
| Template concurrent performance | [perf/CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md](perf/CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md), [perf/TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md](perf/TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md), [perf/MANIFEST.md](perf/MANIFEST.md) | `perf/scripts_v2/`, host/profile outputs if manifest exists | 2026-07-27/28/29 top-level performance reports | Split result report from how-to guide; use perf manifest for lineage gaps |
| irqbypass publication | [articles/cubesandbox-arm64-irqbypass-engineering-story.md](articles/cubesandbox-arm64-irqbypass-engineering-story.md) | `articles/assets/cubesandbox-arm64-irqbypass/*.svg` and profiling/root-cause reports | perf and kernel optimization reports | Publication canonical for public narrative only |
| Guest image and kernel operations | [CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md](CUBESANDBOX_OPENEULER_GUEST_IMAGE_BUILD_GUIDE.md), [CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md](CUBESANDBOX_OPENEULER_VMLINUX_BM_BUILD.md) | image checksums and benchmark reports where available | guest image A/B and openEuler performance reports | Keep as operations group; each command needs version/environment review before execution |
| ARM64 adaptation summaries | [arm64-adaptation-issues-summary-zh.md](arm64-adaptation-issues-summary-zh.md), [arm64-adaptation-issues-summary.md](arm64-adaptation-issues-summary.md) | none in this Workspace | newer AP1R/perf/benchmark materials | Historical language pair until a current owner chooses a primary version |

## AP1R Supersede Chain

The 2026-07-31 root-cause report explicitly says it corrects and closes the remaining issue from `CUBESANDBOX_ARM64_2VCPU_WFI_TIMER_DELIVERY_ROOTCAUSE_20260724.md`. Based on that document relationship, use this chain:

| Role | Path | Status |
|---|---|---|
| Final root-cause candidate | [bug-fixes/CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md](bug-fixes/CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md) | conclusion candidate |
| Evidence bundle | [debug/arm64-vgic-ap1r-nmi-active-20260806/README.md](debug/arm64-vgic-ap1r-nmi-active-20260806/README.md) | evidence canonical candidate |
| Experiment design and raw chain | `bug-fixes/analysis/arm64-vgic-ap1r-nmi-active-20260731/` | supporting evidence |
| Prior corrected report | [CUBESANDBOX_ARM64_2VCPU_WFI_TIMER_DELIVERY_ROOTCAUSE_20260724.md](CUBESANDBOX_ARM64_2VCPU_WFI_TIMER_DELIVERY_ROOTCAUSE_20260724.md) | historical, corrected by 2026-07-31 report |
| Prior investigation reports | `CUBESANDBOX_ARM64_MULTIVCPU_*`, `CUBESANDBOX_ARM64_KVM_VTIMER_*`, `CUBESANDBOX_ARM64_RCU_STALL_*`, trace guides | historical investigation chain |
| Adjacent UB analysis | [CUBESANDBOX_CH_ISSUE6966_UB_COMPARISON_20260721.md](CUBESANDBOX_CH_ISSUE6966_UB_COMPARISON_20260721.md) | related, not the same root cause |

Do not delete or hide historical reports. They explain how earlier hypotheses were ruled out and why the final report changed the conclusion.

## Benchmark and Perf Evidence Boundary

| Area | Current files | Evidence state | Next convergence action |
|---|---|---|---|
| Benchmark image builds | `benchmark/docker/`, `benchmark/checksums/`, `benchmark/docs/` | source and checksum available; image tar not stored | Add image artifact manifest if image tar must be retained elsewhere |
| Benchmark reports | `benchmark/reports/*.md`, `benchmark/reports/*/*.csv` | reports and derived CSV present; [benchmark/reports/README.md](benchmark/reports/README.md) added | Fill raw input and generator details |
| Profiling tools | `perf/scripts_v2/*`, `perf/run_c50_profile.sh`, `perf/analyze_c50_profile.mjs`; [perf/MANIFEST.md](perf/MANIFEST.md) added | references are mixed: metric-source docs point to `scripts_v2`, older how-to/history docs point to root-level scripts | `scripts_v2/` is strongest canonical candidate, but no pruning until guide status is settled |
| Profiling reports | `perf/CUBESANDBOX_*`, top-level `CUBESANDBOX_*PERF*` | multiple dated historical reports | Map each report to workload, revision, host and raw evidence manifest |
| Public article assets | `articles/assets/cubesandbox-arm64-irqbypass/*.svg` | publication derived assets | Keep tied to article; do not use as raw evidence |

## Duplicate and Near-Duplicate Candidates

| Candidate | Current observation | Decision |
|---|---|---|
| `perf/sample_c50_host.sh` and `perf/scripts_v2/sample_c50_host.sh` | exact SHA-256 duplicate: `586f88d1e3da177afbcfa1eebae6bf0ae00fb4f60daa4904ff644881f0ba55eb` | Keep both for now; check callers and README references before selecting canonical |
| `perf/run_cubesandbox_openeuler_template_perf.sh` and `perf/scripts_v2/run_cubesandbox_openeuler_template_perf.sh` | exact SHA-256 duplicate: `64d0ec5aed2b404860f54dadff580309b4bd40c6326630be92e293b40d5788ec` | Keep both for now; likely `scripts_v2/` should be canonical if profiling docs reference it |
| `bug-fixes/.../scripts/*.patch` and `debug/.../fixes/*.patch` | matching patch filenames and sizes for AP1R fixes | Treat `debug/.../fixes/` as evidence bundle copy; keep analysis copy until provenance manifest links them |
| `snapshot-deep-dive.md`, `snapshot-runtime-deep-dive.md`, `testcases_analysis/` | overlapping Snapshot vocabulary but different writing purpose | Keep separate: concepts, runtime explanation, and implementation/source-evidence index |
| ARM64 adaptation English/Chinese summaries | language pair from earlier state | Mark historical until owner defines primary version and sync policy |

## Required Manifests Before Any Move

| Manifest | Minimum fields | Candidate location |
|---|---|---|
| AP1R evidence manifest | source host, collection date, component revisions, patch hashes, raw/derived split, unavailable external paths | [debug/arm64-vgic-ap1r-nmi-active-20260806/MANIFEST.md](debug/arm64-vgic-ap1r-nmi-active-20260806/MANIFEST.md) added; still partial |
| Benchmark reports manifest | workload, template/image tags, runner command, raw input, summary generator, CSV hash, status | [benchmark/reports/README.md](benchmark/reports/README.md) added; still partial |
| Perf profiling manifest | host, workload, script version, raw profile/log paths, analysis command, report link | [perf/MANIFEST.md](perf/MANIFEST.md) added; still partial |
| Guest image/kernel manifest | image tag, kernel build revision, config, checksum, storage location, replacement status | `benchmark/checksums/README.md` or image-specific manifest |
| External evidence availability | non-portable path, availability, class, size, import policy | [EVIDENCE_AVAILABILITY.md](EVIDENCE_AVAILABILITY.md) added; still needs per-directory sensitivity/owner |

## Current Non-Actions

- No CubeSandbox file was moved, renamed or deleted.
- No old report was marked obsolete in place.
- No benchmark or perf script was removed.
- No remote experiment was rerun.
- No large artifact was added.
- No external `remote-results/` path was copied into the repository.

## Next Small Batch

1. Complete missing provenance fields in the three partial manifests.
2. Run checksum validation for AP1R bundle and benchmark/perf files.
3. Decide whether [CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md](perf/CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md) should be updated to `scripts_v2/` or marked historical.
4. After provenance is complete, update this file from `in-progress` to `reviewed`.
