# classification

project = cloud-hypervisor
line = backend-notifier-restore
state = seed

possible_bucket =
- transport restore incomplete
- backend reconnect incomplete
- route/controller restore incomplete
- guest-visible state not yet proven

final_bucket =
undetermined_seed

confidence =
low

status_note =
当前仍是种子包，不是失败样本；还缺真实 restore 成功、backend/notifier 证据和 guest 可见性证据

baseline_kind =
doc_test_derived

current_evidence_strength =
doc/test-derived baseline

next_missing_layer =
runtime transport/notifier/controller evidence + guest-visible result

do_not_upgrade_if =
- only documented/test-derived baseline evidence is present
- restore success exists but no transport/notifier evidence exists
- transport/notifier evidence exists but no controller restore evidence exists
- transport/controller evidence exists but no guest-visible result exists

upgrade_to_real_when =
- one evidence set proves restore success
- the same evidence set proves transport/notifier reconstruction
- the same evidence set proves controller restore status
- the same evidence set proves guest-visible failure or success outcome

contrast_assets =
- success baseline:
  `analysis/samples/ch-backend-notifier-restore-baseline-real-20260622`
