# Kata 沙箱与容器生命周期分析（Cloud Hypervisor）PPT 提纲

## 第 1 页：主题与结论

标题：

- `Kata 沙箱与容器生命周期分析：以 Cloud Hypervisor 为例`

核心结论：

- 在 Kata 中，`sandbox` 本质上是一台轻量 VM
- `container` 是运行在这台 VM 内的工作负载
- `cloud-hypervisor` 负责 VM 生命周期
- `kata-agent` 负责 guest 内容器生命周期

一句话总结：

- `创建/删除沙箱 = 管 VM`
- `创建/删除容器 = 管 guest 内进程与资源`

## 第 2 页：总体架构

标题：

- `生命周期的两层结构`

要点：

- 上层：`containerd / shim -> Kata runtime-rs`
- 中层：`Kata runtime-rs -> cloud-hypervisor`
- 下层：`VM 内 kata-agent -> guest containers`
- 运行时边界清晰：
  - 宿主机侧 runtime 管 VM
  - guest 内 agent 管容器

建议配图：

- 使用报告中的总体架构 Mermaid 图

## 第 3 页：创建沙箱

标题：

- `沙箱创建流程`

要点：

- runtime 创建 `VirtSandbox`
- 调用 `hypervisor.prepare_vm()`
- `resource_manager` 准备网络、sharefs、rootfs、vsock 等资源
- 调用 `hypervisor.start_vm()` 启动 `cloud-hypervisor`
- runtime 连接 `kata-agent`
- 向 guest 发送 `create_sandbox()`

强调：

- 这一步的目标是把一台可运行的 VM 建立起来
- 到这一步为止，容器还没有真正启动

## 第 4 页：创建容器

标题：

- `容器创建流程`

要点：

- runtime 创建 `Container` 对象
- 执行 `CreateContainer` hooks
- runtime 向 agent 发送 `create_container()`
- agent 在 guest 内准备：
  - OCI spec
  - devices
  - storages
  - bundle
  - namespace / cgroup / mount
- runtime 再调用 `start_container()`
- agent 在 guest 内执行容器 init 进程

强调：

- `create_container` 和 `start_container` 是两个阶段
- 真正的容器进程启动发生在 guest 内

## 第 5 页：删除容器

标题：

- `容器删除流程`

要点：

- runtime 等待容器进程退出或主动停止
- 向 agent 发送 `remove_container()`
- agent 在 guest 内销毁容器对象并回收 mount/cgroup 等资源
- runtime 清理宿主机侧 volume/rootfs 资源
- `ContainerManager` 删除内部状态并执行 `poststop` hooks

强调：

- 删除容器是“guest 内清理 + 宿主机侧清理”的组合

## 第 6 页：删除沙箱

标题：

- `沙箱删除流程`

要点：

- runtime 调用 `hypervisor.stop_vm()`
- `cloud-hypervisor` 停止 VM
- runtime 调用 `hypervisor.cleanup()`
- `resource_manager.cleanup()` 回收宿主机资源
- 停止 monitor 和 agent
- 向 shim 发送 shutdown

强调：

- 删除沙箱本质上是销毁整台 VM
- 其粒度高于删除容器

## 第 7 页：Cloud Hypervisor 在生命周期中的角色

标题：

- `Cloud Hypervisor 的职责边界`

要点：

- 负责：
  - `prepare_vm`
  - `start_vm`
  - `stop_vm`
  - `cleanup`
- 不负责：
  - guest 内容器 namespace/cgroup/mount 创建
  - guest 内容器进程启动与删除

结论：

- `CH 管 VM`
- `kata-agent 管容器`

## 第 8 页：汇报结论

标题：

- `总结`

要点：

- Kata 生命周期天然分为“沙箱层”和“容器层”
- `cloud-hypervisor` 只参与沙箱层
- `kata-agent` 才是容器层的执行者
- 因此，优化 Kata 启动时延时必须区分：
  - VM 启动开销
  - guest 内容器创建开销

一句话收束：

- `在 Kata 中，沙箱是 VM，容器在 VM 内；理解这两个生命周期的边界，是分析性能和优化路径的前提。`
