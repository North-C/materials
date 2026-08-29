# Large Object Manifest

- Status: `mat-01-phase-1`
- Last verified: 2026-08-29
- Scope: large objects and binary/evidence candidates observed in the read-only main checkout
- Main checkout: `/home/lyq/Projects/materials`, HEAD `f036fd2`
- Current action: metadata and storage decision plus LFS rules; no untracked object was copied, moved, deleted, staged or committed
- LFS upload: 6 existing virtualization PDF LFS objects uploaded to `origin` on 2026-08-29 using explicit object IDs only; no Git refs were pushed

This manifest records objects that need an explicit storage decision before they are committed. It is intentionally separate from the explanatory reports so that future Workspace runs can update hashes and storage state without rewriting technical conclusions.

## Storage Rules

1. Objects larger than 100 MiB must not enter normal Git history.
2. Approved archives and PDFs may use Git LFS through the root `.gitattributes` rules.
3. Git LFS is allowed for versioned evidence when the file must stay at a stable repository path and the LFS storage/bandwidth cost is acceptable.
4. One-off generated packages, rebuildable outputs, third-party downloads with stable upstream URLs, and sensitive raw evidence still need a manifest decision before being added.
5. Excalidraw sources are text project assets by default, not automatic LFS objects.
6. Logs, results, images, TSV/CSV/JSONL, and profile outputs remain evidence candidates until provenance and sensitivity are reviewed.

Current LFS rules added at repository root:

```gitattributes
*.tar filter=lfs diff=lfs merge=lfs -text
*.tar.gz filter=lfs diff=lfs merge=lfs -text
*.tgz filter=lfs diff=lfs merge=lfs -text
*.zip filter=lfs diff=lfs merge=lfs -text
*.pdf filter=lfs diff=lfs merge=lfs -text
```

Existing rule still present in `virtualization/.gitattributes`:

```gitattributes
*.pdf filter=lfs diff=lfs merge=lfs -text
```

## Verified Candidates

| Path | Size | SHA-256 | Git state in main checkout | Type | Decision |
|---|---:|---|---|---|---|
| `tbench-large-scale-text-editing-profile-perf-amd6.tar` | 598,772,736 B | `71569f3720ca0f3eb42f64295ab0f83433a7beea770d9a76e89aea58f453dc9b` | untracked | POSIX tar archive | Do not include for now. Filename contains a confirmed typo: future canonical name should use `amd64`, not `amd6`. Main checkout file is not renamed in this Workspace. |
| `virtualization/DDI_0487_M.b_a-profile_architecture_reference_manual.pdf` | 161,102,669 B | LFS object `0df13f5972e76226f19c1105934172e71008debd73ecff566da93ccea10cbcbf` | tracked via LFS | PDF reference | Existing virtualization PDFs are approved for LFS upload. Keep LFS state; no history rewrite. |
| `research/agent_cpu_sandbox_toolkit/terminal-bench-tasks/sqlite-with-gcov/vendor/sqlite-fossil-release.tar.gz` | 12,640,606 B | `7c02b6cc04dddc2f90e63d43ab8900cb694ba4665f4e4ac877ec724733125229` | untracked | gzip compressed data | Do not process in this Workspace. |
| `IO_stack_and_hypervisor.excalidraw` | 6,479,701 B | `465ea62f9228af72eaf41b0e1e138c77d5c97526caa9de7a1fc1f8b7867f3755` | untracked | UTF-8 text | Treat as diagram source candidate; keep in normal Git if approved and reviewed |
| `kvm/GIC.excalidraw` | 2,439,668 B | `1e5de8225053eaf5acf39b0ed1aec2438747b5b4aba433c984c62ea1c58d3492` | untracked | UTF-8 text | Treat as diagram source candidate; link to KVM/ARM GIC topic before adding |
| `kvm/kvm-arm64虚拟化.excalidraw` | 918,129 B | `1b69319f2c79702f6c17452b71a32d712404f5f5c9caea3823925689b527395c` | untracked | JSON data | Treat as diagram source candidate; link to KVM/ARM64 topic before adding |
| `现代Linux_IO技术栈.png` | 1,551,254 B | `790a84d5cc2a48ded1cabf3d39f747d1ccd1e9553ffc8bad7e8b7e13e0495ea2` | untracked | PNG, 1491 x 1055 RGB | Derived/publication asset candidate; find source/license/reference before adding |

## Existing Git LFS Objects

`git lfs ls-files --long` currently reports these PDF objects. They were uploaded to `origin` on 2026-08-29 using `git lfs push --object-id`:

| LFS object | Path |
|---|---|
| `0df13f5972e76226f19c1105934172e71008debd73ecff566da93ccea10cbcbf` | `virtualization/DDI_0487_M.b_a-profile_architecture_reference_manual.pdf` |
| `9f5a2c8eeafad9030c7af81b6223b28150db229594aaba6a7e1b0975d1129ef3` | `virtualization/learn_the_architecture_aarch64_virtualization_guide_102142_0100_06_en.pdf` |
| `83db31c3eb6c0d9b704675fb1ae9a71c5a8a24e9b920a61a954df4dd6e1a41ce` | `virtualization/virtio/virtio-v1.0.pdf` |
| `951e24ec44ac1f54fc0ade3d4d11d1df317976bf8183e5eab413cdaf44c475eb` | `virtualization/virtio/virtio-v1.1-cs01.pdf` |
| `42c7d2b9da95b4763e5416e18eab08d9a5d715dd98390cb5fb727205c15f5e45` | `virtualization/virtio/virtio-v1.2-cs01.pdf` |
| `17d95b4d1518054e7a49e4e2025e1433a4e8c92bb2181a889dcdaa74b9616675` | `virtualization/virtio/virtio-v1.3-csd01.pdf` |

## Confirmed Decisions

- The 598 MB Terminal-Bench perf tar is not included for now.
- The `amd6` suffix is a typo; future references should use `amd64`. The original file in the read-only main checkout was not renamed.
- The vendor tar is left untouched in this Workspace.
- Existing `virtualization/` PDFs are allowed to be uploaded as Git LFS objects.

## Candidate Next Actions

### `tbench-large-scale-text-editing-profile-perf-amd64.tar`

If this file is later added through LFS:

- record owner, source command, source revision, host/config, collection time and sensitivity;
- decide whether the tar is unique raw evidence or a rebuildable generated artifact;
- if accepted for Git LFS, copy it into this Workspace, verify SHA-256 after copy, then stage the tar plus `.gitattributes` and this manifest together;
- if not accepted for Git LFS, store it in controlled object storage/release asset and keep only manifest, hash and retrieval policy in Git.

### Vendor archive

`sqlite-fossil-release.tar.gz` is explicitly out of scope for this Workspace. If it is revisited later, start with upstream URL, version, license and expected hash before deciding whether to vendor it.

### Diagram and image assets

Before adding Excalidraw/PNG objects:

- assign each file to a topic page or project README;
- link diagram source to exported/publication images;
- confirm no sensitive topology, customer or internal environment details are exposed;
- keep Excalidraw in normal Git unless future size or binary embedding makes LFS necessary.

## Open Questions

- What is the owner and intended retention period for the Terminal-Bench perf tar?
- Should the root `.gitattributes` replace or coexist with `virtualization/.gitattributes` in a later cleanup Workspace?
