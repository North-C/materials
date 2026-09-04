# OpenCloudOS Kernel PR 657 的 6.6.119 tag 合入核验

## 结论

[OpenCloudOS-Kernel PR 657](https://gitee.com/OpenCloudOS/OpenCloudOS-Kernel/pulls/657) 的合并提交是 `dc6528044d879fdbb863f62813ddddd96487284f`，标题为 `!657 Support NMI in the virtual machine`。该 PR 向目标分支引入 15 个 KVM/arm64 vNMI 提交。

- `6.6.119-47` **没有合入 PR 657**，15 个提交的可达性结果为 `0/15`。
- 从 Git 提交拓扑看，PR 合并提交之前最近的祖先 tag 是 `6.6.119-47.2`，但它也不包含该 PR。
- `6.6.119-48`、`6.6.119-49` 以及最新核对的 `6.6.119-49.31` 均不包含该 PR。
- **首个包含 PR 657 全部 15 个提交的 tag 是 `6.6.119-50`。** 若需要选择已具备该功能的 OpenCloudOS 6.6 内核，应使用 `6.6.119-50` 或其后续包含版本。

这里的“最近 tag”有两种含义，不能混用：

| 含义 | 结果 | 是否包含 PR 657 |
| --- | --- | --- |
| PR 合并前最近的祖先 tag | `6.6.119-47.2` | 否 |
| 最早包含 PR 的发布 tag | `6.6.119-50` | 是 |

## 核验对象

核验时间为 2026-09-04，仓库远端为：

```text
https://gitee.com/OpenCloudOS/OpenCloudOS-Kernel.git
```

关键对象如下：

| 对象 | Commit | 说明 |
| --- | --- | --- |
| PR 657 合并提交 | `dc6528044d879fdbb863f62813ddddd96487284f` | 2026-03-10 合并，第二父提交是该 PR 最后一个补丁 |
| `6.6.119-47` | `a482632abce9aa10d0d5ad000d3a0a248197bd6e` | 不包含 PR |
| `6.6.119-47.2` | `e582681e0b889dd0696517b9fad262318a8d0a6e` | PR 之前最近的祖先 tag，不包含 PR |
| `6.6.119-49.31` | `4768893861330ea2475a51a7bca510fe96b526fa` | 核验时 `49` 系列最新 tag，不包含 PR |
| `6.6.119-50` | `8d690da18df3ece564cf188ea9101e252b8052e1` | 首个包含 PR 的 tag |

PR 合并提交信息：

```text
commit:  dc6528044d879fdbb863f62813ddddd96487284f
parents: 48b1f2e11d4853863ac7538d4bdd29ab939ec30b
         d3e4a45c7a2878168bf798b328e958a74529d768
date:    2026-03-10T06:33:43+00:00
title:   !657 Support NMI in the virtual machine Merge pull request !657 from xiexiaodong/vNMI_6.6
```

## 验证方法

### 1. 验证 PR 合并提交是否为 tag 的祖先

判断某个 tag 是否包含 PR，不能只比较发布日期或版本号，应检查提交可达性：

```bash
pr=dc6528044d879fdbb863f62813ddddd96487284f

git merge-base --is-ancestor "$pr" '6.6.119-47^{}'
echo $?  # 1：不包含

git merge-base --is-ancestor "$pr" '6.6.119-50^{}'
echo $?  # 0：包含
```

`git merge-base --is-ancestor A B` 返回 `0` 表示 A 是 B 的祖先，即 B 包含 A；返回 `1` 表示不包含。`^{}` 用于把 tag 解析到它最终指向的 commit。

本次核验结果：

```text
6.6.119-47     contains=NO
6.6.119-47.2   contains=NO
6.6.119-48.3   contains=NO
6.6.119-49.31  contains=NO
6.6.119-50     contains=YES
```

### 2. 验证 PR 引入的全部提交

PR 657 是 merge commit。下面的范围表示该 PR 相对目标分支第一父提交引入的提交集合：

```bash
pr=dc6528044d879fdbb863f62813ddddd96487284f
git rev-list --count "${pr}^1..${pr}^2"
# 15
```

逐一执行祖先检查后得到：

```text
6.6.119-47    =  0/15
6.6.119-49.31 =  0/15
6.6.119-50    = 15/15
```

这同时排除了“tag 没有 merge commit，但通过其他路径包含相同 15 个提交”的情况。

### 3. 定位 PR 前最近的祖先 tag

```bash
git describe --tags --long --match '6.6.119-*' \
  dc6528044d879fdbb863f62813ddddd96487284f
```

输出：

```text
6.6.119-47.2-127-gdc6528044d87
```

这表示 PR 合并提交位于 `6.6.119-47.2` 之后，按 `git describe` 的计数相隔 127 个提交。它只能说明 `47.2` 是此前最近的可达 tag，不能说明 `47.2` 已经包含 PR。

### 4. 定位首个包含 PR 的 tag

```bash
git tag --contains dc6528044d879fdbb863f62813ddddd96487284f \
  --list '6.6.119-*' --sort=version:refname | sed -n '1p'
```

输出：

```text
6.6.119-50
```

## 为什么 `47.5` 等较晚创建的 tag 仍可能不包含 PR

tag 的创建时间晚于 PR 合并时间，并不代表该 tag 一定包含 PR。Git 仓库可以同时维护不同分支：一个 tag 可能在另一条 release 历史上继续演进，而 PR 先合入 devel 历史，之后才通过新的合并点进入 release 历史。

因此，本问题必须以 commit ancestry 和 PR 内全部提交的可达性为准，不能根据日期、tag 字符串大小或 `git log --all` 中是否能搜索到提交来判断。

## 最终版本边界

```text
6.6.119-47   不包含 PR 657
6.6.119-47.2 PR 之前最近的祖先 tag，但不包含 PR 657
6.6.119-49.31 仍不包含 PR 657
6.6.119-50   首个包含 PR 657 全部 15 个提交的 tag
```
