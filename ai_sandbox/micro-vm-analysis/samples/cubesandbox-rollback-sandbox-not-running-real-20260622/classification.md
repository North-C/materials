# Classification

- 目标签名：`sandbox is not running`
- 首个失败点：rollback case 内创建 snapshot 时，控制面判定 sandbox 不是 running
- 归类层级：control plane / sandbox lifecycle window
- 与网络数据面的关系：无直接关系；未伴随 `tap fd unavailable` 或 `CreateNetworkFailed`
- 仍缺什么：更底层的 CubeMaster/Cubelet/Shim 同步时序日志
