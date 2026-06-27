# Checklist

## 1. 采样前

- [ ] 确认节点是 `arm64`
- [ ] 确认本次目标签名，例如 `tap fd unavailable`
- [ ] 确认触发类型：并发创建 / restore / 其他

## 2. 采样中

- [ ] 在 `commands.txt` 记录 `quickcheck.sh`
- [ ] 在 `commands.txt` 记录 `cube-diag/check-procs.sh`
- [ ] 在 `commands.txt` 记录 `collect-logs.sh` 参数
- [ ] 在 `host.txt` 保留 quickcheck 和 check-procs 摘要
- [ ] 在 `logs.txt` 记录产物目录与关键文件

## 3. 采样后

- [ ] 在 `classification.md` 写清目标签名
- [ ] 说明是否能和既有 `tap fd unavailable` 案例对应
- [ ] 说明还缺哪些日志或上下文
