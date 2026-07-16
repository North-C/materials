# Benchmark Image Tags

本文档记录当前 benchmark 镜像的固定版本 tag。后续创建 CubeSandbox Template 时优先使用这些 tag，不再直接使用裸 `upstream-arm64` / `upstream-amd64` 作为可复现实验输入。

## 当前固定 tag

| 架构 | 推荐 tag | Image ID / config digest | Registry manifest digest | 位置 |
|---|---|---|---|---|
| arm64 | `cube-bench-suite:upstream-arm64-20260715-5e54db9` | `sha256:5e54db9373cf83f889afd23120127ce114cdd4f5923529323a67d6b76d58a1de` | `sha256:6b2a35715ad085bf5e96d19f8eb090377d9fff78c4ca2ed82a75324add8f7325` | 远端 `root@192.168.25.90` 和 registry `127.0.0.1:5000` |
| amd64 | `cube-bench-suite:upstream-amd64-20260715-5763a38` | `sha256:5763a38a2282ddd2e02dac289bf3ca75f92b5c1d22eb93a4a33308b14150974f` | `sha256:5763a38a2282ddd2e02dac289bf3ca75f92b5c1d22eb93a4a33308b14150974f` | 本地 Docker |

远端 arm64 registry 引用：

```text
127.0.0.1:5000/cube-bench-suite:upstream-arm64-20260715-5e54db9
```

本地 amd64 引用：

```text
cube-bench-suite:upstream-amd64-20260715-5763a38
```

## 命名规则

```text
upstream-<arch>-<build-date>-<image-id-prefix>
```

示例：

```text
upstream-arm64-20260715-5e54db9
upstream-amd64-20260715-5763a38
```

其中：

- `<arch>` 是 `arm64` 或 `amd64`。
- `<build-date>` 使用镜像构建日期，格式为 `YYYYMMDD`。
- `<image-id-prefix>` 使用 Docker image ID / config digest 的前 7 位。

## 使用约定

- `upstream-arm64` / `upstream-amd64` 只作为开发阶段可变 tag，不再作为正式测试报告中的唯一镜像标识。
- 创建 Template、导出报告、归档 benchmark 结果时，必须记录：
  - image tag
  - registry manifest digest
  - Docker image ID / config digest
  - tar 包 SHA256，若测试来自 tar 导入
- 已创建的 Template 仍会保留创建时解析出的不可变 digest；不会因为 tag 新增或重打而自动改变。

## 远端 arm64 操作记录

已在 `root@192.168.25.90` 执行：

```bash
docker tag sha256:5e54db9373cf83f889afd23120127ce114cdd4f5923529323a67d6b76d58a1de \
  cube-bench-suite:upstream-arm64-20260715-5e54db9

docker tag sha256:5e54db9373cf83f889afd23120127ce114cdd4f5923529323a67d6b76d58a1de \
  127.0.0.1:5000/cube-bench-suite:upstream-arm64-20260715-5e54db9

docker push 127.0.0.1:5000/cube-bench-suite:upstream-arm64-20260715-5e54db9
```

推送后 registry 返回：

```text
digest: sha256:6b2a35715ad085bf5e96d19f8eb090377d9fff78c4ca2ed82a75324add8f7325
```

## 本地 amd64 操作记录

已在本地执行：

```bash
docker tag sha256:5763a38a2282ddd2e02dac289bf3ca75f92b5c1d22eb93a4a33308b14150974f \
  cube-bench-suite:upstream-amd64-20260715-5763a38
```
