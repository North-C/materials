# 内容目录使用方式

`docs/index.md` 与 `docs/topics/` 是仓库内的 Markdown 内容目录，不是第二份内容仓库，也不承担网页生成职责。

## 三层模型

```text
根 README / 内容目录 / 主题索引
        |
        | 导航、状态、canonical 映射
        v
所属项目中的 Markdown / 脚本 / 图源
        |
        | evidence manifest
        v
原始证据或受控的仓库外对象
```

### 目录层

目录页只写 scope、分类、状态和关系，不复制项目正文。读者从根 README 或主题索引进入项目原文；同一结论只维护一个 canonical source。

### 内容层

技术正文、脚本和图源继续放在所属领域或项目目录。项目 README 负责说明 canonical docs、状态、source revision、evidence 和阅读顺序。

### 证据层

小型文本证据可以在项目内版本化；大型或敏感 evidence 放受控对象存储。内容目录只链接脱敏 manifest、hash、来源、revision、复现状态和相关结论。

## 目录页约定

主题页至少包含：

- scope 与不包含的范围；
- 当前入口与 canonical 候选；
- durable knowledge、project-local docs、evidence、generated/ephemeral 分类；
- `draft / in-progress / verified / historical` 状态；
- provenance 缺口；
- 下一批 Workspace 和禁止动作；
- 相关主题与治理决策。

## 当前优先级

1. 为 CubeSandbox 建立项目级 README 和主题导航。
2. 收敛 research 的研究结论、toolkit、task、版本和证据入口。
3. 完善根目录散落文件的 scope、公开级别与迁移映射。
4. 完善大文件/生成物登记，但不迁移、删除或提交大对象。

## 网页展示边界

网页 Wiki 构建已推迟。当前不保留静态站生成器、依赖锁、构建脚本、CI 或发布配置。未来恢复时，以这些内容目录和项目 README 为输入另立 Workspace，不改变当前 Markdown 的 canonical 关系。
