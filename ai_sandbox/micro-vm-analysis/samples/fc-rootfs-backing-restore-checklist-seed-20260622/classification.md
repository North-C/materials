# classification

project = firecracker
line = rootfs-backing-restore
state = seed

possible_bucket =
- root expression mismatch
- backing file inconsistency
- restore succeeded but guest device invisible
- guest rootfs not usable

final_bucket =
undetermined_seed

confidence =
low

status_note =
当前仍是种子包，不是失败样本；还缺真实 restore 成功、backing file 一致性和 guest rootfs 可见性证据

baseline_kind =
codepath_derived

current_evidence_strength =
codepath-derived baseline

next_missing_layer =
real restore + backing consistency + guest-visible/rootfs result

do_not_upgrade_if =
- only codepath-derived root/backing evidence is present
- restore success exists but no backing consistency evidence exists
- backing consistency evidence exists but no guest device visibility evidence exists
- guest device visibility exists but no rootfs usability result exists

upgrade_to_real_when =
- one evidence set proves restore success
- the same evidence set proves root expression
- the same evidence set proves backing consistency
- the same evidence set proves guest device visibility and rootfs usability outcome
