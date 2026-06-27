# Fill Guide

1. 先填 `SUMMARY.md` 的 backend、host dev name、queue 参数。
2. 再把原始错误文本放进 `host.txt`。
3. 若进入 guest，再填 `guest.txt`。
4. 最后在 `classification.md` 写清：
   - 为什么是 backend-specific failure
   - 为什么不是 machine / vIOMMU 更早失败
   - 为什么不是 guest discovery 更后失败
