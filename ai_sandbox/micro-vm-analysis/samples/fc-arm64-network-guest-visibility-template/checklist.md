# Checklist

## 1. 采样前

- [ ] 确认节点是 `arm64`
- [ ] 固定 `host_dev_name`
- [ ] 确认本次不是 restore 场景
- [ ] 确认本次不是 MMDS 专项场景

## 2. 采样中

- [ ] 在 `commands.txt` 记录启动命令和检查命令
- [ ] 在 `host.txt` 保留 `TapOpen` / `TapSetVnetHdrSize` 结果
- [ ] 在 `host.txt` 标出是否存在 `undo_pop()` 或 MMDS 证据
- [ ] 在 `guest.txt` 保留 guest 侧“不可用”的最小证据

## 3. 采样后

- [ ] 在 `classification.md` 说明为什么不是 host backend 早失败
- [ ] 在 `classification.md` 说明为什么不是 MMDS / limiter 伪失败
- [ ] 在 `classification.md` 最终归到 `guest visibility / interrupt visibility`
