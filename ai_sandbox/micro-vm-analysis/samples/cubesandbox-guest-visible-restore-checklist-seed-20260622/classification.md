# classification

project = cubesandbox
line = guest-visible-restore
state = seed

possible_bucket =
- control plane reached VMM but worker not awakened
- backend rebound incomplete
- guest agent visibility incomplete
- ready convergence incomplete

final_bucket =
undetermined_seed

confidence =
low

status_note =
当前仍是种子包，不是失败样本；还缺真实控制面成功证据、worker/后端重绑证据和 guest-visible state 收敛证据

baseline_kind =
codepath_derived

current_evidence_strength =
codepath-derived baseline + upgrade guards

next_missing_layer =
same-attempt host/runtime/guest evidence proving control-plane success + worker progression + guest-visible failure

do_not_upgrade_if =
- only control-plane failure is present
- only success-baseline evidence is present
- control-plane succeeded but no worker/backend evidence exists
- worker/backend evidence exists but no guest-visible convergence evidence exists

upgrade_to_real_when =
- one evidence set proves control-plane success
- the same evidence set proves worker/backend progression
- the same evidence set proves guest-visible convergence failure

contrast_assets =
- success baseline:
  `analysis/samples/cubesandbox-guest-visible-restore-baseline-real-20260622`
- control-plane failure:
  `analysis/samples/cubesandbox-rollback-sandbox-not-running-real-20260622`
