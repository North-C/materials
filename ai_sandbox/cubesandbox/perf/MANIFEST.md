---
status: in-progress
scope: CubeSandbox profiling scripts, reports and raw/derived lineage
last_verified: 2026-08-29
source_revision: f036fd2 (file inventory and hash review only)
canonical: true
evidence_manifest: partial
---

# CubeSandbox Perf Manifest

This directory contains profiling guides, metric references, analysis scripts and performance reports. It does not currently contain a complete raw profile archive for every report.

## Canonical Entries

| Purpose | Entry | Status |
|---|---|---|
| Metric semantics and source mapping | [CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md](CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md) | reference candidate for CubeSandbox `v0.5.1` |
| Profiling collection guide | [CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md](CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md) | how-to candidate |
| Segmented latency report | [CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md](CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md) | historical result report |
| Template concurrent create guide | [TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md](TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md) | optimization how-to candidate |
| `runContainer` and probe call chain | [CUBESANDBOX_RUNCONTAINER_PROBE_CALL_CHAIN.md](CUBESANDBOX_RUNCONTAINER_PROBE_CALL_CHAIN.md) | call-chain explanation |

## Scripts

| Path | Role | SHA-256 | Decision |
|---|---|---|---|
| `scripts_v2/analyze_c50_profile.mjs` | current detailed analyzer candidate | `8d7b49fd42eb2d5edc6aa9bcf93e119c13fb9eb7043b360d138c8cf99a2fa402` | likely canonical; verify callers |
| `scripts_v2/run_c50_profile.sh` | current profiling runner candidate | `4bd09fdbc80d9ccc36e6595c8a17f5ca3e86d5a51d295d3ef63c8331f342a393` | likely canonical; verify callers |
| `scripts_v2/run_cubesandbox_openeuler_template_perf.sh` | current workload runner candidate | `64d0ec5aed2b404860f54dadff580309b4bd40c6326630be92e293b40d5788ec` | exact duplicate with root perf copy; verify callers before removing either |
| `scripts_v2/sample_c50_host.sh` | host sampler candidate | `586f88d1e3da177afbcfa1eebae6bf0ae00fb4f60daa4904ff644881f0ba55eb` | exact duplicate with root perf copy; verify callers before removing either |
| `analyze_c50_profile.mjs` | older or alternate analyzer | `a8f4a915e4ae972ef3611e0da20db2bfeb73e332345f34936e6219482b5f5227` | keep until caller/history review |
| `run_c50_profile.sh` | older or alternate runner | `2722012d7ad6c92d60623fed2c0141809052c4e58247cc5a8af5d14e388c1d85` | keep until caller/history review |
| `run_cubesandbox_openeuler_template_perf.sh` | duplicate candidate | `64d0ec5aed2b404860f54dadff580309b4bd40c6326630be92e293b40d5788ec` | exact duplicate with `scripts_v2/`; keep until caller/history review |
| `sample_c50_host.sh` | duplicate candidate | `586f88d1e3da177afbcfa1eebae6bf0ae00fb4f60daa4904ff644881f0ba55eb` | exact duplicate with `scripts_v2/`; keep until caller/history review |

## Reports

| File | Role | SHA-256 |
|---|---|---|
| [CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md](CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md) | profiling guide | `b1e33c19f1284943511c86ef119a0467e6386bcc170a85a106a3323ece3d383a` |
| [CUBESANDBOX_CORE_PERF_2U2G_20260803.md](CUBESANDBOX_CORE_PERF_2U2G_20260803.md) | result report | `edeb468a425f5c7a4496f421b902a97b39c1c6ec9065caee5c9449316cc4abb6` |
| [CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md](CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md) | metric reference | `163096fdcb32e5f1b2b2e49e72e84255ec5a88f1351f584eddaa43816c6dbfd5` |
| [CUBESANDBOX_RUNCONTAINER_PROBE_CALL_CHAIN.md](CUBESANDBOX_RUNCONTAINER_PROBE_CALL_CHAIN.md) | call-chain explanation | `3f16b3c247ada9cc38077ed9ec5a2ed86f9d59ef864c349b82e55389b4711057` |
| [CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md](CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md) | result report | `5df53bae9ff549d6f0e33279b1ca4abe6440fbd4e9e6bdfc70439c1e7096bc5d` |
| [CUBESANDBOX_TEMPLATE_STARTUP_NUMA_BALANCING_ANALYSIS.md](CUBESANDBOX_TEMPLATE_STARTUP_NUMA_BALANCING_ANALYSIS.md) | root-cause/perf analysis | `f8e5878a2b6e373ec66750ad93cebd895fa4ff2f8b3793efc455c40c7c4ea20d` |
| [TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md](TEMPLATE_CONCURRENT_CREATE_OPTIMIZATION_GUIDE.md) | how-to guide | `6f3b4cc5c2e6d1f84266a6cd69095c6e3758d3b4be2f54ba2601b2fd0c3ef773` |

## Lineage Requirements

Before any performance number is promoted to verified:

- record host, kernel, CubeSandbox component revisions and image/template IDs;
- record exact workload command, concurrency, warmup count, success/failure denominator and cleanup evidence;
- link raw logs/profile output to the derived `analysis.json` or CSV;
- state whether the report uses current code or a historical branch;
- avoid subtracting aggregate P95 values from different sample sets.

## Reference Review

Literal reference search on 2026-08-29 shows mixed references:

- [CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md](CUBESANDBOX_PROFILE_METRIC_SOURCE_MAPPING.md) points to `scripts_v2/run_c50_profile.sh`, `scripts_v2/analyze_c50_profile.mjs`, `scripts_v2/run_cubesandbox_openeuler_template_perf.sh` and `scripts_v2/sample_c50_host.sh`.
- [scripts_v2/C50_PROFILE_GUIDE.md](scripts_v2/C50_PROFILE_GUIDE.md) documents the `scripts_v2` package model.
- [CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md](CUBESANDBOX_COMMUNITY_PROFILING_GUIDE.md) still points to the older root-level `perf/*.sh` and `perf/*.mjs` scripts.
- [CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md](CUBESANDBOX_SEGMENTED_LATENCY_PROFILING_20260803.md) references `scripts/run_c50_profile.sh` and `scripts/analyze_c50_profile.mjs`, which may describe a historical runtime layout rather than current repo paths.

Decision: `scripts_v2/` is the strongest canonical candidate for metric-source documentation, but old root-level scripts remain referenced by a how-to guide and historical reports. Do not delete or rename either path until the guides are updated or marked historical.

## External Evidence Availability

See [../EVIDENCE_AVAILABILITY.md](../EVIDENCE_AVAILABILITY.md) for the local archive map. Relevant observed locations include:

| Verification location | Role |
|---|---|
| `/home/lyq/Projects/Verification/cubesandbox/artifacts/cubesandbox-profile-v2-validation-20260805-1540` | profiling v2 validation artifact directory |
| `/home/lyq/Projects/Verification/cubesandbox/artifacts/cubesandbox-profile-v2-validation-20260805-1540.tar.gz` | profiling v2 validation archive candidate |
| `/home/lyq/Projects/Verification/cubesandbox/artifacts/cubesandbox-core-perf-2u2g-20260803` | core perf 2U2G artifact directory |
| `/home/lyq/Projects/Verification/cubesandbox/artifacts/cubesandbox-community-baseline-profile-20260804-223409` | community baseline profile artifact directory |
| `/home/lyq/Projects/Verification/cubesandbox/scripts/run_c50_profile.sh` | historical runtime script layout referenced by reports |
| `/home/lyq/Projects/Verification/cubesandbox/scripts/analyze_c50_profile.mjs` | historical runtime analyzer layout referenced by reports |

## Current Non-Actions

- No script copy was removed.
- No report was rewritten.
- No raw profile archive was imported.
- No new benchmark was run.
