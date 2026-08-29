---
status: in-progress
scope: CubeSandbox benchmark reports, derived CSV and provenance gaps
last_verified: 2026-08-29
source_revision: f036fd2 (file inventory and hash review only)
canonical: true
evidence_manifest: partial
---

# CubeSandbox Benchmark Reports Manifest

This directory stores historical benchmark reports and derived CSV summaries. It is not the benchmark runner source; use [../README.md](../README.md) for build and execution workflow.

## Contents

| File | Role | SHA-256 |
|---|---|---|
| [CUBESANDBOX_TEMPLATE_CREATE_PERF_REPORT_20260720.md](CUBESANDBOX_TEMPLATE_CREATE_PERF_REPORT_20260720.md) | historical report | `fea894d020447631179ca496f9873fa73ade9718cb27a1588999db4ed91d5b5f` |
| [CUBESANDBOX_TEMPLATE_CREATE_PERF_RETEST_REPORT_20260720.md](CUBESANDBOX_TEMPLATE_CREATE_PERF_RETEST_REPORT_20260720.md) | historical retest report | `b7ce597304206c6aafbce92a39f8ede67b3fcd19e41b4e45d99cc37f44eec0de` |
| [cube-bench-formal-report-arm64-8c16g.md](cube-bench-formal-report-arm64-8c16g.md) | formal benchmark report | `e8c2846412cbf5ed328c749716a4564569a9d75d7da0f37827b969cd244babc4` |
| [cubesandbox-benchmark-install-report-arm64-8c16g-20260714-223455.md](cubesandbox-benchmark-install-report-arm64-8c16g-20260714-223455.md) | install and benchmark report | `05ec138d0e03de34602903b13337092a7633b22a2359c2ded460e1632b0f1be8` |
| [cubesandbox-install-report-v0.5.0-nvme3n1.md](cubesandbox-install-report-v0.5.0-nvme3n1.md) | install report | `aa08fc569df881da13c7b26e328a637a6d7fff191ee587539a9829666ee20838` |

## Derived CSV Set

The CSV files under [cube-bench-sdk-formal-arm64-2c4g-20260716/](cube-bench-sdk-formal-arm64-2c4g-20260716/) are derived evidence. Keep them linked to their generator and raw runner output before treating any table as verified canonical.

| File | Role | SHA-256 |
|---|---|---|
| `benchmark-summary.csv` | derived benchmark summary | `209f2e3331e54036334de8dad668dbb8edc55b61e6048ffecf8168a9df44fc16` |
| `summary.csv` | derived aggregate summary | `d09da548e45b5a7146b3e0427b33b99a67d46f9fb96ec5f7c53ccd72773767c9` |
| `summary-memory.csv` | derived memory summary | `c0f0b1088fd2708ba8c71e05de31df9c5a9f3eb0ef6797fa1941b7612f8cb76c` |
| `summary-prime.csv` | derived prime summary | `142ce90fb64cebe7633d28c7c9aac8833c3a5ee1fcebc51912d43a570b1bf113` |
| `summary-runtimes.csv` | derived runtime summary | `bc40293a55160f2ef8060815b3b1e173ca08bac7a2026a605f9df86d3eee4a96` |

## Current Decision

- Keep all reports and CSV in place.
- Do not choose the latest dated report as canonical without matching workload, template/image, runner version and raw input.
- Do not move CSV into docs pages; summarize them from a manifest or report.
- Image tar files remain outside this directory; only checksum metadata belongs here unless a later LFS decision approves otherwise.

## External Evidence Availability

See [../../EVIDENCE_AVAILABILITY.md](../../EVIDENCE_AVAILABILITY.md) for the local archive map. Relevant observed locations include:

| Verification location | Role |
|---|---|
| `/home/lyq/Projects/Verification/cubesandbox/remote-results/template-create-perf-20260723` | Template create performance/profiling evidence |
| `/home/lyq/Projects/Verification/cubesandbox/remote-results/cubesandbox-benchmark-install-report-arm64-8c16g-20260714-223455.md` | Historical install/benchmark report source |
| `/home/lyq/Projects/Verification/cubesandbox/remote-results/benchmark-results-20260714-223058-envd.tar.gz.sha256` | Historical exported benchmark result checksum |
| `/home/lyq/Projects/Verification/cubesandbox/testcases_analysis` | Source copy for current testcases analysis package |

## Provenance Gaps

- Raw runner output paths are not fully mapped to each CSV.
- Generator command and version are not recorded next to the CSV set.
- Template IDs, image tags, host identity and source revisions need a single manifest entry per benchmark run.
- Failure denominators and cleanup/readiness evidence must be recorded before using these reports for performance claims.
