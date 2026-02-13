# cgroup 框架介绍

[cgroup v1 和 v2](https://mfzzf.github.io/2025/03/13/Linux%E4%B8%AD%E7%9A%84Cgroup/)

```c
struct cgroup{
    atomic_t count;

    struct list_head sibling;
    struct list_head children;
    ...
};
```

## 基本概念

逻辑上，cgroup定义了一些专用术语，用来展示使用时的层次结构。

- 子系统(subsystem)\层级（Hierarch）、进程或进程组等

## 实现结构

整个cgroup以树的形式构建，具备很好的可扩展性，接入了众多内核的子系统。

- struct cgroup
- struct css_set
- struct list_head
- struct cg_cgroup_link
- struct cpuset

## 初始化和创建


## 向cgroup中加入进程


## cpu子系统与cgroup


## tasks 结构体





