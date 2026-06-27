# Classification

- 目标签名：`No space left on device`
- 具体路径：`/dev/shm/dirty`
- 首个失败点：benchmark precondition / tmpfs capacity
- 归类层级：storage / snapshot benchmark precondition
- 与 guest-visible 的关系：无直接关系；问题发生在写脏页准备阶段
- 与中断/I/O 数据面的关系：无直接关系；未伴随 `tap fd unavailable`、`FsEvent`、`VmSetFs`
- 已验证短期修复：将 `dev_shm_size_in_bytes` 提升到 `2147483648` 后，100MiB-1024MiB dirty-page 用例全部通过
