
[jenkins官方文档](https://www.jenkins.io/zh/doc/)

[Jenkins - Gitee 插件使用](https://gitee.com/help/articles/4193#article-header9)

dd07d0848d639e1fd483edbd21506f94
从易用性考虑，选择 docker 安装 Jenkins。

1. 拉取镜像
```bash
docker pull --platform linux/arm64 jenkins/jenkins:lts
```

如果无法直接拉取，可先配置镜像源。
```bash
vim /etc/docker/daemon.json
```
在daemon.json中添加如下内容：
```bash
{
    "registry-mirrors": [
        "http://docker.1ms.run"
    ]
}
```

重启docker：
```bash
systemctl daemon-reload && systemctl restart docker
```
查看 daemon.json 配置是否成功：
```bash
docker info
```

2. 启动jenkins

```bash
docker run --name jenkins -u root --rm -d -p 8080:8080 -p 50000:50000 -v /mnt/sdb/lyq/jenkins_home:/var/jenkins_home -v /var/run/docker.sock:/var/run/docker.sock jenkins/jenkins:lts
```
启动后,如果是远程连接，可以使用 vscode 的端口转发功能，将 8080 端口转发到本地。进入后需要输入管理员密码。

查看初始密码：
```bash
cat /var/jenkins_home/secrets/initialAdminPassword
```

初始安装完成插件后，直接重启即可，数据会被存储到 设置好的 volume 中，不会丢失。

3. 剩余工作时在 Jenkins 当中进行仓库任务配置。

[使用 Jenkins 构建 Go 项目流水线](https://cloud.tencent.com/developer/article/1804000)