# EPYC 9654 机器：c100 profiler 对照汇总

统计单位是整轮；各组预期5轮。正变化表示更慢，负变化表示更快。未自动排除任何快慢离群轮。

| 组 | 有效/已记录/预期 | 状态 | 整轮中位 ms | 最小–最大 ms | 样本标准差 ms |
| --- | --- | --- | ---: | --- | ---: |
| A_before | 5/5/5 | complete | 145.633 | 144.602–154.986 | 4.300 |
| U | 5/5/5 | complete | 174.288 | 148.609–189.490 | 15.494 |
| P | 5/5/5 | complete | 182.449 | 152.193–192.025 | 15.801 |
| C | 5/5/5 | complete | 183.727 | 165.087–190.351 | 9.650 |
| S | 5/5/5 | complete | 178.109 | 170.166–185.962 | 6.603 |
| F | 5/5/5 | complete | 170.883 | 167.775–188.753 | 9.621 |
| A_after | 5/5/5 | complete | 140.987 | 137.388–198.207 | 25.721 |

| 对照（候选−基线） | 状态 | 中位差 ms | 中位比例变化 % | 配对轮差中位 ms | 范围重叠 |
| --- | --- | ---: | ---: | ---: | --- |
| P − U | complete | 8.161 | 4.682 | -0.147 | True |
| C − P | complete | 1.279 | 0.701 | -8.297 | True |
| S − C | complete | -5.618 | -3.058 | -12.242 | True |
| F − S | complete | -7.226 | -4.057 | 0.434 | True |
| F − U | complete | -3.405 | -1.954 | -5.208 | True |
| A_after − A_before | complete | -4.646 | -3.190 | -5.390 | True |

对照条件与证据缺项：

- compiled_off: 变化因素=['server_patch']；未发现因子清单冲突。
- client_trace: 变化因素=['client_trace']；未发现因子清单冲突。
- server_trace: 变化因素=['server_trace']；未发现因子清单冲突。
- collector: 变化因素=['collector']；未发现因子清单冲突。
- whole_profiler: 变化因素=['client_trace', 'collector', 'server_patch', 'server_trace']；未发现因子清单冲突。
- deployment_drift: 变化因素=[]；deployed_binary_anchor_not_patch_attribution。
  配列口径：same ordinal across separated before/after phases; descriptive only, not interleaved Latin blocks。

## 逐轮与缺项

- 1: A_before-r1 (A_before, block 1): 145.169 ms；valid=True；输入验收通过。
- 2: A_before-r2 (A_before, block 2): 145.633 ms；valid=True；输入验收通过。
- 3: A_before-r3 (A_before, block 3): 146.708 ms；valid=True；输入验收通过。
- 4: A_before-r4 (A_before, block 4): 144.602 ms；valid=True；输入验收通过。
- 5: A_before-r5 (A_before, block 5): 154.986 ms；valid=True；输入验收通过。
- 6: U-b1-p1 (U, block 1): 182.596 ms；valid=True；输入验收通过。
- 7: P-b1-p2 (P, block 1): 182.449 ms；valid=True；输入验收通过。
- 8: C-b1-p3 (C, block 1): 165.087 ms；valid=True；输入验收通过。
- 9: S-b1-p4 (S, block 1): 185.962 ms；valid=True；输入验收通过。
- 10: F-b1-p5 (F, block 1): 169.261 ms；valid=True；输入验收通过。
  采集/验收说明：Post-measurement cleanup initially stopped because its primary-raw search also matched an analysis copy. The capture was not rerun; exact 103-ID cleanup and closing gates were recovered and verified. This completed timing round is retained.
- 11: P-b2-p1 (P, block 2): 188.108 ms；valid=True；输入验收通过。
- 12: C-b2-p2 (C, block 2): 178.038 ms；valid=True；输入验收通过。
- 13: S-b2-p3 (S, block 2): 178.901 ms；valid=True；输入验收通过。
- 14: F-b2-p4 (F, block 2): 184.282 ms；valid=True；输入验收通过。
- 15: U-b2-p5 (U, block 2): 189.490 ms；valid=True；输入验收通过。
- 16: C-b3-p1 (C, block 3): 183.727 ms；valid=True；输入验收通过。
- 17: S-b3-p2 (S, block 3): 170.449 ms；valid=True；输入验收通过。
- 18: F-b3-p3 (F, block 3): 170.883 ms；valid=True；输入验收通过。
- 19: U-b3-p4 (U, block 3): 148.609 ms；valid=True；输入验收通过。
- 20: P-b3-p5 (P, block 3): 192.025 ms；valid=True；输入验收通过。
- 21: S-b4-p1 (S, block 4): 178.109 ms；valid=True；输入验收通过。
  采集/验收说明：Post-measurement observation validation initially read only *.log and missed 3 warmup Master records after log rotation. The unchanged original window contains 100 current-log records plus 3 in .log.1; validation was recovered by reading all suffixes and correlating the 103 unique client request IDs. Broader historical/off-cohort window records remain archived; all_window_server_records and off_cohort_records_excluded document their exclusion. This is an analysis/closing-gate repair, not a repeated or altered timing measurement. Subsequent window collection follows rotated files by inode.
- 22: F-b4-p2 (F, block 4): 167.775 ms；valid=True；输入验收通过。
- 23: U-b4-p3 (U, block 4): 174.288 ms；valid=True；输入验收通过。
- 24: P-b4-p4 (P, block 4): 152.193 ms；valid=True；输入验收通过。
- 25: C-b4-p5 (C, block 4): 190.351 ms；valid=True；输入验收通过。
- 26: F-b5-p1 (F, block 5): 188.753 ms；valid=True；输入验收通过。
- 27: U-b5-p2 (U, block 5): 172.188 ms；valid=True；输入验收通过。
- 28: P-b5-p3 (P, block 5): 174.227 ms；valid=True；输入验收通过。
  采集/验收说明：After the successful measured round, the closing load gate waited three 30-second intervals as load1 fell 7.15 → 5.57 → 4.26 → 3.49 (required ≤4). Inventory was empty and all 738 TAPs were Ready throughout. All attempts remain evidence; the timing round is retained, and the post-window load rise does not by itself locate interference inside the benchmark.
- 29: C-b5-p4 (C, block 5): 185.130 ms；valid=True；输入验收通过。
  采集/验收说明：Before this measured round, the opening load gate waited three 30-second intervals as load1 fell 6.49 → 4.83 → 4.28 → 3.66 (required ≤4). The benchmark ran only after the fourth successful gate, with the same w3 warmup. Waiting is outside summary.total_time_s; all attempts remain archived and the successful timing round is retained.
- 30: S-b5-p5 (S, block 5): 170.166 ms；valid=True；输入验收通过。
- 31: A_after-r1 (A_after, block 1): 198.207 ms；valid=True；输入验收通过。
- 32: A_after-r2 (A_after, block 2): 140.987 ms；valid=True；输入验收通过。
- 33: A_after-r3 (A_after, block 3): 137.388 ms；valid=True；输入验收通过。
- 34: A_after-r4 (A_after, block 4): 138.754 ms；valid=True；输入验收通过。
- 35: A_after-r5 (A_after, block 5): 149.596 ms；valid=True；输入验收通过。

## 解释边界

- Independent experimental units are rounds, not the 100 requests within each round.
- Whole-round wall_ms comes only from summary.total_time_s, excluding the benchmark warmup.
- Client create_ms ends at response headers; it excludes trace preparation before t0, body reading and decoding, which can still affect whole-round time.
- No unusually fast or slow successful round is automatically excluded; every exclusion is explicit or an input-validity failure.
- Percent changes are candidate / baseline - 1; a positive value means slower. Five rounds provide descriptive evidence, not proof of equivalence or zero overhead.
- A_before / A_after are deployment drift anchors; their old binary source tree is not assumed equal to the rebuilt U baseline.
- Factor metadata describes the planned experiment; actual binary identity, switches and environmental equivalence require external evidence.
- Stage intervals overlap and can have different coverage; their means or percentiles must not be added or subtracted to infer exclusive work.
- Client per-round P95 is recomputed from successful raw create_ms using nearest rank; frontdoor stage P95 preserves the profiler's interpolated definition.

公开附件：[逐轮数据](data/rounds.csv)、[配对差值](data/contrasts.csv)、[统计JSON](data/comparison.json)、[公开benchmark数值](data/benchmark-samples.json)、[复核说明](data/README.zh-CN.md)。
