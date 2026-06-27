# Fill Guide

1. 先在 `host.txt` 确认 `TapOpen` / `TapSetVnetHdrSize` 没失败。
2. 再写明是否出现 MMDS / limiter 伪失败证据。
3. 然后在 `guest.txt` 放入 guest 侧不可用证据。
4. 最后在 `classification.md` 写清：
   - 为什么不是 host backend 早失败
   - 为什么不是 MMDS / limiter 伪失败
   - 为什么最终归到 guest visibility / interrupt visibility
