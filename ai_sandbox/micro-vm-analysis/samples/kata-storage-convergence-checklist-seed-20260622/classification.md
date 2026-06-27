# classification

project = kata-containers
line = storage-convergence
state = seed

possible_bucket =
- storage translation incomplete
- request propagation incomplete
- guest add_storages incomplete
- guest mount convergence incomplete

final_bucket =
undetermined_seed

confidence =
low

status_note =
当前仍是种子包，不是失败样本；还缺真实 storages 传递、guest add_storages 落地和 rootfs/volume 可用性证据

baseline_kind =
codepath_derived

current_evidence_strength =
stronger request propagation

next_missing_layer =
guest add_storages()/mount_from() runtime evidence + final usability

do_not_upgrade_if =
- only codepath-derived translation evidence is present
- only request-shaped JSON samples are present
- request propagation evidence exists but no guest storage landing evidence exists
- guest storage landing exists but no final rootfs/volume usability outcome exists

upgrade_to_real_when =
- one evidence set proves translation
- the same evidence set proves `CreateContainerRequest.storages`
- the same evidence set proves guest `add_storages()` / `mount_from()`
- the same evidence set proves final rootfs/volume usability outcome
