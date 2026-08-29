---
status: in-progress
scope: CubeSandbox external evidence and source-code availability map
last_verified: 2026-08-29
source_revision: f036fd2 (link extraction and local path existence review only)
canonical: true
evidence_manifest: partial
---

# CubeSandbox Evidence Availability

This file maps legacy evidence/source links in CubeSandbox documents to the local verification archive. It does not copy evidence into this repository and does not make those paths publishable.

## Verification Root

Local root used for read-only checks:

```text
/home/lyq/Projects/Verification/cubesandbox
```

The directory contains `remote-results/`, `source_code/`, `artifacts/`, `fixes/`, `testcases_analysis/`, `docker/`, `analysis/` and related working material.

## Extraction Result

On 2026-08-29, CubeSandbox Markdown files were scanned for links and bare paths containing:

- `remote-results/`
- `source_code/`
- `/home/lyq/Projects/Verification/cubesandbox`

After normalizing relative paths to the verification root and stripping `:line` suffixes from source links:

| Class | Referenced paths | Existing locally | Missing locally |
|---|---:|---:|---:|
| All extracted paths | 327 | 327 | 0 |
| `remote-results/` | 253 | 253 | 0 |
| `source_code/` | 61 | 61 | 0 |
| `artifacts/` | 7 | 7 | 0 |

This means many links that are broken from the materials repository alone are still resolvable in the local verification archive. They should be converted to explicit evidence manifest entries instead of being treated as deleted evidence.

## Representative External Locations

| Location under verification root | Role | Files | Approx size | Decision |
|---|---|---:|---:|---|
| `remote-results/arm64-aprmask-validation-20260731` | AP1R validation evidence referenced by root-cause report | 7 | 437,700 B | external evidence; map to AP1R manifest |
| `remote-results/aprmask-multi-resource-65-20260805` | AP1R multi-resource validation source for the in-repo debug bundle | 22,827 | 105,610,260 B | external/raw evidence; do not bulk import |
| `remote-results/arm64-multi-template-concurrent-20260731` | concurrent Template validation evidence | 22 | 466,274 B | external evidence |
| `remote-results/template-create-perf-20260723` | Template create perf/profiling evidence | 220 | 22,746,761 B | external evidence for benchmark/perf manifests |
| `artifacts/cubesandbox-profile-v2-validation-20260805-1540` | profiling artifact bundle | 56 | 46,602,322 B | external artifact; manifest before import |
| `artifacts/cubesandbox-core-perf-2u2g-20260803` | core perf artifact bundle | 143 | 870,678 B | external artifact |
| `source_code/CubeSandbox` | source tree referenced by historical analysis | 20,160 | 7,077,265,865 B | external source checkout; do not import |
| `source_code/CubeSandbox-v0.6.0-iccfix-20260828` | source tree for later ICC/AP1R fix context | 8,546 | 2,395,107,539 B | external source checkout; do not import |

## Publishing and Repository Boundary

- These paths are local evidence locations, not portable Markdown links for a public Wiki.
- Large source trees and raw result directories should remain outside materials unless a later Workspace creates a small, reviewed manifest or curated subset.
- Public documentation should link to manifests, hashes, sanitized summaries and upstream commits rather than absolute local paths.
- Remote servers mentioned in reports are still secondary sources; because the local verification archive resolved all extracted paths, this phase did not contact remote servers.

## Next Actions

1. Update AP1R, benchmark and perf manifests to cite the corresponding verification-root locations.
2. For each external evidence directory, record owner, collection host, collection time, source revision, raw/derived split, hash strategy and sensitivity level.
3. Replace legacy absolute links only after a manifest exists and the target public/private policy is clear.
4. Keep local absolute paths out of future public Wiki pages unless they are explicitly marked as non-portable provenance.
