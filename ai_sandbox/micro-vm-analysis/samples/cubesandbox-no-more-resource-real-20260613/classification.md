# Classification

- 目标签名：`no more resource`
- 首个失败点：CubeMaster scheduler / quota capacity
- 对应错误码：`130597`
- 归类层级：control plane / scheduler capacity
- 与 guest-visible 的关系：无直接关系；失败发生在调度过滤阶段
- 与网络数据面的关系：无直接关系；未伴随 `tap fd unavailable` 或 `CreateNetworkFailed`
- 仍缺什么：更细的长期 quota/overcommit 策略与调度窗口对照
