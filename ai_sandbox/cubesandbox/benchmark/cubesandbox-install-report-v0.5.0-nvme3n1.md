# CubeSandbox v0.5.0 ARM64 安装报告

时间：2026-07-14 22:07 CST  
机器：root@192.168.25.90（master，aarch64/openEuler 24.03）  
部署目录：/home/lyq/cube-sandbox-one-click-v0.5.0-arm64  
安装方式：one-click 离线包

## 处理事项

1. 将 /dev/nvme3n1 格式化为 XFS：
   - UUID: f265026a-7907-49a2-8fe1-29edd2c0a14d
   - 挂载点：/data/cubelet
   - /etc/fstab：UUID=f265026a-7907-49a2-8fe1-29edd2c0a14d /data/cubelet xfs defaults,noatime 0 0

2. 替换先前 loopback XFS 方案：
   - 当前 /data/cubelet 来源为 /dev/nvme3n1。
   - 当前无 losetup 设备占用。
   - 原 loopback 文件 /home/lyq/cubesandbox-cubelet-xfs.img 已保留，未删除。
   - 清理了 cubeletmnt/mnt 中保存的旧 mount namespace，使 cubelet 内部 namespace 也使用 /dev/nvme3n1。

3. 运行时兼容修复：
   - Docker 18.09 不支持 host-gateway：WebUI 改为通过 http://192.168.25.90:3000 和 http://192.168.25.90:80 访问宿主服务。
   - cube-proxy 已存在本地镜像 cube-proxy:one-click：up-cube-proxy.sh 增加本地镜像存在时跳过 build，避免离线环境再次拉取 Docker Hub buildkit。
   - 清理重复的 Docker network support_default。

## 验证结果

1. one-click quickcheck：通过

```text
[quickcheck] OK
```

2. 关键服务状态：

```text
cube-sandbox-control.target active
cube-sandbox-network-agent.service active
cube-sandbox-cubelet.service active
cube-sandbox-cubemaster.service active
cube-sandbox-cube-api.service active
cube-sandbox-cube-proxy.service active
cube-sandbox-cube-egress.service active
cube-sandbox-cube-egress-net.service active/exited
cube-sandbox-coredns.service active
cube-sandbox-dns.service active/exited
cube-sandbox-mysql.service active
cube-sandbox-redis.service active
cube-sandbox-webui.service active
```

3. 存储验证：

```text
/data/cubelet /dev/nvme3n1 xfs rw,noatime
nvme3n1 xfs UUID=f265026a-7907-49a2-8fe1-29edd2c0a14d mounted at /data/cubelet
```

4. CLI 验证：

```text
cubecli version -> Server Version: v0.5.0, Revision: v1
cubemastercli node list -> 192.168.25.90 HEALTHY=true HOST_STATUS=RUNNING
```

5. Sandbox 启动验证：成功

```text
Template ID: tpl-c88f05ec7a2a41399383e7b9
Sandbox ID: f6615c68ef5b417bb6ee67db11d9be3b
Status: running
Host: 192.168.25.90
Sandbox IP: 10.100.0.17
Container: cubebox-name-0 running
```

## 生成的日志/记录

- /home/lyq/cubesandbox-smoke-v0.5.0-nvme3n1-final-*.log
- /home/lyq/cubesandbox-sandbox-run-output-v0.5.0-nvme3n1.log
- /home/lyq/cubesandbox-sandbox-detail-v0.5.0-nvme3n1.json
- /home/lyq/cubesandbox-sandbox-list-v0.5.0-nvme3n1.log
- /home/lyq/cubesandbox-template-info-v0.5.0-nvme3n1.json
- /home/lyq/cubesandbox-template-render-v0.5.0-nvme3n1.json

## 当前保留状态

- CubeSandbox 服务保持运行。
- 验证 Sandbox f6615c68ef5b417bb6ee67db11d9be3b 保持 running，用于后续检查。
- 原 loopback 镜像 /home/lyq/cubesandbox-cubelet-xfs.img 保留作为迁移前备份。
