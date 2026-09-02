# Kunpeng-TAP Pcore Biding 二进制与镜像构建指南

## 1. 适用范围

本文说明如何为 Kunpeng-TAP Pcore Biding 插件构建 Linux ARM64 二进制和容器镜像。

源码核查基线：

- 源码仓库：`https://gitcode.com/yuncongyue/cloud-native.git`
- 分支：`kunpeng-tap-confidential-plugin`
- 提交：`f8c9d89f15e7024584baaf60a5f7c780836bad4f`
- 核查日期：2026-09-02

> 注意：仓库中的实际项目名是 `kunpeng-tap-pcore-biding`，不是
> `kunpeng-tap-pcore-binding`。目录名、二进制名、Dockerfile、镜像名和
> Kubernetes 资源名均使用 `biding`，构建时必须保持这一拼写。

## 2. 构建关系

该插件没有独立的 Makefile 构建目标，构建流程分为两步：

1. 使用 Go 将 `./cmd/kunpeng-tap-pcore-biding` 交叉编译为 ARM64 静态二进制。
2. 使用 `Dockerfile.kunpeng-tap-pcore-biding` 将该二进制复制进
   `scratch` 镜像。

仓库中的 `make -f Makefile.kunpeng-tap build` 构建的是常规
`kunpeng-tap-manager` 和 `kunpeng-tap`，不会生成 Pcore Biding 插件。

## 3. 环境要求

- Git。
- Go 1.25 或更高版本；源码基线的 `go.mod` 声明 `go 1.25.0`。
- 可访问 Go Module 依赖源。
- Docker，且支持构建 `linux/arm64` 镜像。
- 构建主机可以是 AMD64 或 ARM64；二进制架构由 `GOARCH=arm64` 明确指定。

检查环境：

```bash
git --version
go version
docker version
```

## 4. 准备源码

为了保证构建可复现，建议在独立目录中检出已核查提交：

```bash
git clone --branch kunpeng-tap-confidential-plugin --single-branch \
  https://gitcode.com/yuncongyue/cloud-native.git \
  cloud-native-pcore-build

cd cloud-native-pcore-build
git switch --detach f8c9d89f15e7024584baaf60a5f7c780836bad4f
git status --short --branch
```

如果需要构建分支最新代码，可以省略固定提交的 `git switch --detach`，但应记录实际
`git rev-parse HEAD` 输出，避免产物来源不明确。

## 5. 构建 ARM64 二进制

可以先运行插件范围内的单元测试：

```bash
go test ./pkg/kunpeng-tap-pcore-biding/...
```

在仓库根目录执行：

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 \
  go build \
  -o kunpeng-tap-pcore-biding \
  ./cmd/kunpeng-tap-pcore-biding
```

参数含义：

- `CGO_ENABLED=0`：关闭 CGO，生成不依赖系统动态库的 Go 二进制，以适配
  `scratch` 运行镜像。
- `GOOS=linux`：目标操作系统为 Linux。
- `GOARCH=arm64`：目标架构为 ARM64。
- `-o kunpeng-tap-pcore-biding`：将产物放在仓库根目录。Dockerfile 会从构建上下文
  根目录复制这个文件。

验证二进制：

```bash
test -x kunpeng-tap-pcore-biding
file kunpeng-tap-pcore-biding
go version -m kunpeng-tap-pcore-biding
sha256sum kunpeng-tap-pcore-biding
```

`file` 输出应表明该文件是 Linux ARM64/AArch64 ELF 可执行文件。应保存
`git rev-parse HEAD`、`go version` 和 SHA-256，以便追踪产物来源。

## 6. 构建 ARM64 镜像

保持二进制位于仓库根目录，然后执行：

```bash
docker build \
  --platform=linux/arm64 \
  -f Dockerfile.kunpeng-tap-pcore-biding \
  -t kunpeng-tap-pcore-biding:latest \
  .
```

专用 Dockerfile 的行为如下：

- 基础镜像是 `scratch`。
- 将本地 `kunpeng-tap-pcore-biding` 复制到
  `/usr/local/bin/kunpeng-tap-pcore-biding`。
- 将该文件设置为镜像 `ENTRYPOINT`。

`--platform=linux/arm64` 只声明镜像平台，不负责把错误架构的本地二进制转换为
ARM64。因此，镜像构建前仍须通过 `GOARCH=arm64` 编译，并用 `file` 检查二进制。

验证镜像：

```bash
docker image inspect kunpeng-tap-pcore-biding:latest \
  --format 'os={{.Os}} arch={{.Architecture}} entrypoint={{json .Config.Entrypoint}}'
```

预期关键结果：

```text
os=linux arch=arm64 entrypoint=["/usr/local/bin/kunpeng-tap-pcore-biding"]
```

由于镜像基于 `scratch`，镜像内没有 Shell、`ls` 或 `ldd` 等调试工具，不应使用
`docker run ... sh` 验证镜像。

## 7. 保存或分发镜像

将镜像保存为离线文件：

```bash
docker save \
  -o kunpeng-tap-pcore-biding-arm64.tar \
  kunpeng-tap-pcore-biding:latest

sha256sum kunpeng-tap-pcore-biding-arm64.tar
```

在使用 containerd 的 Kubernetes 节点上导入：

```bash
ctr -n k8s.io images import kunpeng-tap-pcore-biding-arm64.tar
ctr -n k8s.io images list | grep kunpeng-tap-pcore-biding
```

也可以推送到镜像仓库：

```bash
pcore_image_ref=registry.example.com/kunpeng-tap-pcore-biding:v0.1.0
docker tag kunpeng-tap-pcore-biding:latest \
  "$pcore_image_ref"
docker push "$pcore_image_ref"
```

使用自定义仓库地址时，必须同步修改
`config/kunpeng-tap-pcore-biding/daemonset.yaml` 中的 `image:`。仓库默认清单使用：

```yaml
image: kunpeng-tap-pcore-biding:latest
imagePullPolicy: IfNotPresent
```

## 8. 一次性构建命令

在已准备好的源码根目录中，可以依次执行：

```bash
set -Eeuo pipefail

go test ./pkg/kunpeng-tap-pcore-biding/...

CGO_ENABLED=0 GOOS=linux GOARCH=arm64 \
  go build -o kunpeng-tap-pcore-biding \
  ./cmd/kunpeng-tap-pcore-biding

file kunpeng-tap-pcore-biding
sha256sum kunpeng-tap-pcore-biding

docker build \
  --platform=linux/arm64 \
  -f Dockerfile.kunpeng-tap-pcore-biding \
  -t kunpeng-tap-pcore-biding:latest \
  .

docker image inspect kunpeng-tap-pcore-biding:latest \
  --format 'os={{.Os}} arch={{.Architecture}} entrypoint={{json .Config.Entrypoint}}'
```

如果需要保留二进制产物，不要删除仓库根目录下的
`kunpeng-tap-pcore-biding`；如果只需要镜像，可在镜像构建完成后删除这个临时文件。

## 9. 常见问题

### 找不到源码目录或 Dockerfile

先确认当前分支：

```bash
git branch --show-current
git rev-parse HEAD
```

Pcore Biding 源码和专用 Dockerfile 位于 `kunpeng-tap-confidential-plugin` 分支，常规
`master` 分支可能不包含这些文件。

### `make -f Makefile.kunpeng-tap build` 没有生成插件

这是预期行为。该 Makefile 只构建常规 Kunpeng-TAP manager/proxy。Pcore Biding
必须使用本文给出的 `go build ./cmd/kunpeng-tap-pcore-biding` 命令。

### Kubernetes 节点无法使用本地镜像

DaemonSet 的 `imagePullPolicy` 是 `IfNotPresent`。需要确保每个目标节点的
containerd `k8s.io` namespace 中已经导入同名镜像，或者将镜像推送到节点可访问的
仓库并更新 DaemonSet 的 `image:`。

### AMD64 主机无法直接运行构建出的二进制

该二进制的目标架构是 ARM64。AMD64 主机可以完成交叉编译和镜像组装，但直接运行
ARM64 二进制需要 ARM64 主机或正确配置的 QEMU/binfmt 模拟环境。

## 10. 本文命令验证记录

2026-09-02 在 Linux AMD64 构建机上，针对本文固定的源码提交执行了插件单元测试、
ARM64 交叉编译和 Docker 镜像构建：

- Go：`go1.26.2 linux/amd64`。
- Docker Client/Server：`29.5.2`。
- `go test ./pkg/kunpeng-tap-pcore-biding/...`：通过。
- 二进制类型：`ELF 64-bit LSB executable, ARM aarch64, statically linked`。
- 二进制 SHA-256：
  `6580b1110be66a7cc8309b180f7fdc00d8569ea85ffd018fea1aa055ed6bf025`。
- 镜像检查结果：
  `os=linux arch=arm64 entrypoint=["/usr/local/bin/kunpeng-tap-pcore-biding"]`。

上述记录证明本文的二进制和镜像构建命令在该源码与工具链组合下可执行。它不等同于
ARM64 节点运行验证、NRI 注册验证或 Kubernetes 端到端验证；部署前仍需在目标环境
完成这些检查。
