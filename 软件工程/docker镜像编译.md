## 通用操作

创建multi-arch driver，并添加上代理：

```bash
docker buildx create --name multi-platform --use --platform linux/amd64,linux/arm64 --driver docker-container --driver-opt env.HTTP_PROXY=socks5://host.docker.internal:1080 --driver-opt env.HTTPS_PROXY=socks5://host.docker.internal:1080
```

使用指定的driver:

```bash
docker buildx use XXXX
```


每次编译结束，如果出错，需要stop 并且rm buildx的容器：

```bash
docker stop XXX
docker rm XXX
```
最保险的方案是，删除所有的cache:

```shell
docker system prune --all
```

编译成功后，如果一定要同时构建多架构，又想留在本地（不推送远程）
`--load` 不支持多平台，但可以把结果以 oci 或 docker 归档的形式导出到本地目录，再用 docker load 导入：

```shell
# 1. 构建并导出为 tar 包
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --output type=oci,dest=./myimage.tar \
  .

# 2. 把 tar 包导入到本地
docker load -i ./myimage.tar
``` 
这种方式会生成一个多架构索引镜像，docker images 会显示一条记录，但 docker inspect 能看到它包含多个平台 manifest。


## hotelReservation 编译

在 hotelReservation/Kubernetes/scripts 目录下提供了编译的脚本 build-docker-images.sh 脚本。

```shell

```


## socialNetwork 编译

在 DeathStarBench/socialNetwork/docker 目录下提供了服务组件的编译文件：

以m crouter 的编译为例：

```shell
docker buildx build -t kunpeng/mcrouter:latest -f Dockerfile . --platform linux/arm64,linux/amd64 --output type=oci,dest=/home/test/lyq/DeathStarBench/mcrouter.tar
```
