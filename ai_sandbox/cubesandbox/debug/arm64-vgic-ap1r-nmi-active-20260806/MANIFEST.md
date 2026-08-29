---
status: in-progress
scope: AP1R/NMI restore failure evidence bundle
last_verified: 2026-08-29
source_revision: f036fd2 (bundle inventory and checksum review only)
canonical: true
evidence_manifest: partial
---

# AP1R/NMI Debug Bundle Manifest

This directory is the current evidence-entry candidate for the ARM64 AP1R/NMI Template restore failure. Use [../../bug-fixes/CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md](../../bug-fixes/CUBESANDBOX_ARM64_VGIC_AP1R_NMI_ACTIVE_ROOTCAUSE_AND_FIX_20260731.md) as the root-cause report.

## Bundle Summary

- Test machine recorded by the bundle README: `.65` ARM64 environment.
- Local verification source: `/home/lyq/Projects/Verification/cubesandbox/remote-results/aprmask-multi-resource-65-20260805`.
- Related 2026-07-31 validation source: `/home/lyq/Projects/Verification/cubesandbox/remote-results/arm64-aprmask-validation-20260731`.
- Validation matrix: 1U/2G to 5U/2G, 25 Templates, 7500 create requests.
- Reported result: 7500 success, 0 failure.
- Cleanup checks: 150 rounds reported as passing.
- Existing checksum file: [SHA256SUMS](SHA256SUMS).
- Checksum verification: `sha256sum -c SHA256SUMS` passed for all listed files on 2026-08-29.

## Files and Roles

| Path | Role | Checksum source |
|---|---|---|
| [README.md](README.md) | bundle overview | `SHA256SUMS` |
| [CUBESANDBOX_ARM64_TEMPLATE_RESTORE_FAILURE_PROBLEM_DESCRIPTION_20260806.md](CUBESANDBOX_ARM64_TEMPLATE_RESTORE_FAILURE_PROBLEM_DESCRIPTION_20260806.md) | problem statement and reasoning | `SHA256SUMS` |
| [REPORT.zh-CN.md](REPORT.zh-CN.md) | validation report | `SHA256SUMS` |
| [data/environment.tsv](data/environment.tsv) | environment metadata | `SHA256SUMS` |
| [data/templates.tsv](data/templates.tsv) | Template list | `SHA256SUMS` |
| [data/results.tsv](data/results.tsv) | per-request results | `SHA256SUMS` |
| [data/summary.tsv](data/summary.tsv) | per-Template summary | `SHA256SUMS` |
| [data/totals.tsv](data/totals.tsv) | global totals | `SHA256SUMS` |
| [data/cleanup-summary.tsv](data/cleanup-summary.tsv) | cleanup and TAP recovery checks | `SHA256SUMS` |
| [evidence/ap1r-pollution.log](evidence/ap1r-pollution.log) | pre-fix AP1R pollution evidence | `SHA256SUMS` |
| [evidence/identity-attempt-1-shim.log](evidence/identity-attempt-1-shim.log) | pre-fix CubeShim failure log | `SHA256SUMS` |
| [fixes/kernel-vgic-v3-apr-readback-mask.patch](fixes/kernel-vgic-v3-apr-readback-mask.patch) | kernel fix patch | `SHA256SUMS` |
| [fixes/vmm-icc-regs-u64-access.patch](fixes/vmm-icc-regs-u64-access.patch) | VMM fix patch | `SHA256SUMS` |
| [scripts/validate_aprmask_multi_resource_templates_65.sh](scripts/validate_aprmask_multi_resource_templates_65.sh) | validation script | `SHA256SUMS` |

## Canonical Relationship

| Item | Decision |
|---|---|
| Root-cause conclusion | `bug-fixes/...ROOTCAUSE_AND_FIX_20260731.md` remains the conclusion candidate |
| Evidence entry | This directory is the evidence canonical candidate |
| Patch copies | `debug/.../fixes/` is the evidence-bundle copy; `bug-fixes/analysis/.../scripts/` remains the analysis copy until provenance is fully mapped |
| External raw logs | Large raw logs or remote paths not present here are treated as controlled/unavailable evidence |

## External Evidence Availability

See [../../EVIDENCE_AVAILABILITY.md](../../EVIDENCE_AVAILABILITY.md) for the local archive map. The two AP1R validation directories above were observed locally on 2026-08-29; they remain external evidence locations and are not copied by this Workspace.

## Verification Needed Before `verified`

- Confirm component revisions in `data/environment.tsv` against the report.
- Confirm whether omitted large raw logs are reproducible, controlled elsewhere or intentionally discarded.
- Confirm that the root-cause report, problem statement and validation report use the same component identity vocabulary.

## Current Non-Actions

- No log or TSV file was rewritten.
- No patch was modified.
- No external raw log was imported.
- No remote validation was rerun.
