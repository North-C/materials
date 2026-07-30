# CubeSandbox guest 镜像替换手册

本文适用于 one-click 部署的 CubeSandbox，默认安装根目录为：

```text
/usr/local/services/cubetoolbox
```

已验证的历史 ARM64 镜像保存在：

```text
/home/lyq/Projects/Verification/cubesandbox/artifacts/guest-images/arm64-openEuler-20260609-222734
```

替换镜像会影响后续冷启动和新生成的 Template。已有 Template 包含原镜像生成的快照，不会因为替换基础镜像而自动更新；确认生效时必须创建一个新 Template。

## 1. 本地制品校验

在保存镜像的本地机器执行：

```bash
cd /home/lyq/Projects/Verification/cubesandbox/artifacts/guest-images/arm64-openEuler-20260609-222734
sha256sum -c SHA256SUMS
zstd -t cube-guest-image-cpu.img.zst
sudo e2fsck -fn cube-guest-image-cpu.img
```

预期镜像身份：

```text
version:       20260609-222734
agent-version: v0.5.1
image sha256:  1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da
rootfs:        openEuler 24.03 LTS-SP3
architecture:  ARM64
```

## 2. 传输到目标机

以下命令在本地机器执行。修改 `TARGET` 为目标主机；`REMOTE_STAGE` 应使用新的空目录。

```bash
TARGET=root@192.168.25.90
LOCAL_BUNDLE=/home/lyq/Projects/Verification/cubesandbox/artifacts/guest-images/arm64-openEuler-20260609-222734
REMOTE_STAGE=/var/tmp/cubesandbox-guest-image-20260609-222734

ssh "$TARGET" "install -d -m 0755 '$REMOTE_STAGE'"
scp \
  "$LOCAL_BUNDLE/cube-guest-image-cpu.img.zst" \
  "$LOCAL_BUNDLE/version" \
  "$LOCAL_BUNDLE/agent-version" \
  "$TARGET:$REMOTE_STAGE/"
```

如果目标机没有 `zstd`，可直接传输 `cube-guest-image-cpu.img`，并跳过下一节的解压命令。

## 3. 目标机预检和展开镜像

登录目标机后以 root 执行：

```bash
set -euo pipefail

STAGE=/var/tmp/cubesandbox-guest-image-20260609-222734
INSTALL=/usr/local/services/cubetoolbox/cube-image
SERVICE=cube-sandbox-cubelet.service
API_URL=http://127.0.0.1:3000
API_KEY=e2b_000000
EXPECTED_IMAGE_SHA=1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da

test "$(id -u)" -eq 0
test -d "$INSTALL"
test -f "$STAGE/cube-guest-image-cpu.img.zst"
test -f "$STAGE/version"
test -f "$STAGE/agent-version"

zstd -t "$STAGE/cube-guest-image-cpu.img.zst"
zstd -d --sparse -f \
  "$STAGE/cube-guest-image-cpu.img.zst" \
  -o "$STAGE/cube-guest-image-cpu.img"

printf '%s  %s\n' \
  "$EXPECTED_IMAGE_SHA" \
  "$STAGE/cube-guest-image-cpu.img" | sha256sum -c -
e2fsck -fn "$STAGE/cube-guest-image-cpu.img"
test "$(tr -d '\n' <"$STAGE/version")" = "20260609-222734"
test "$(tr -d '\n' <"$STAGE/agent-version")" = "v0.5.1"
```

如实际部署使用的 API key 不是测试环境默认值，应先修改 `API_KEY`。

在停止 Cubelet 前，确认没有正在运行的 Sandbox，也没有 Template 构建任务：

```bash
systemctl is-active "$SERVICE"
curl -fsS "$API_URL/cubeapi/v1/health"

SANDBOXES="$(curl -fsS \
  -H "Authorization: Bearer $API_KEY" \
  "$API_URL/sandboxes")"
printf '%s\n' "$SANDBOXES" | jq .
test "$(printf '%s\n' "$SANDBOXES" | jq 'length')" -eq 0

SHIM_PIDS="$(pgrep -f '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' || true)"
TASK_DIRS="$(find /data/cubelet/root/io.containerd.runtime.v2.task \
  -mindepth 2 -maxdepth 2 -type d -print 2>/dev/null || true)"
test -z "$SHIM_PIDS"
test -z "$TASK_DIRS"
```

只在 Sandbox、shim、task 和 Template 构建任务均为空时继续。不要通过强杀活跃 shim 来腾空环境。

## 4. 备份并原子替换

继续在目标机执行。该流程先保存当前镜像，再把新文件复制到安装目录中的临时文件，最后通过同一文件系统内的 `mv` 完成原子切换。

```bash
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="/usr/local/services/cubetoolbox/cube-image.backup-$STAMP"

install -d -m 0755 "$BACKUP"
cp --reflink=auto --sparse=always \
  "$INSTALL/cube-guest-image-cpu.img" \
  "$BACKUP/cube-guest-image-cpu.img"
cp -a "$INSTALL/version" "$INSTALL/agent-version" "$BACKUP/"
sha256sum \
  "$BACKUP/cube-guest-image-cpu.img" \
  "$BACKUP/version" \
  "$BACKUP/agent-version" >"$BACKUP/SHA256SUMS.absolute"

printf 'backup=%s\n' "$BACKUP"

systemctl stop "$SERVICE"
test "$(systemctl is-active "$SERVICE" || true)" = "inactive"

cp --reflink=auto --sparse=always \
  "$STAGE/cube-guest-image-cpu.img" \
  "$INSTALL/.cube-guest-image-cpu.img.new"
cp "$STAGE/version" "$INSTALL/.version.new"
cp "$STAGE/agent-version" "$INSTALL/.agent-version.new"
chmod 0644 \
  "$INSTALL/.cube-guest-image-cpu.img.new" \
  "$INSTALL/.version.new" \
  "$INSTALL/.agent-version.new"

printf '%s  %s\n' \
  "$EXPECTED_IMAGE_SHA" \
  "$INSTALL/.cube-guest-image-cpu.img.new" | sha256sum -c -

mv -f \
  "$INSTALL/.cube-guest-image-cpu.img.new" \
  "$INSTALL/cube-guest-image-cpu.img"
mv -f "$INSTALL/.version.new" "$INSTALL/version"
mv -f "$INSTALL/.agent-version.new" "$INSTALL/agent-version"
sync -f "$INSTALL"
```

不要直接覆盖正在使用的镜像文件，也不要在 Cubelet 运行时分多次替换三个文件。

## 5. 重启 Cubelet

镜像由 compute 侧 Cubelet/Shim 使用。正常情况下只需要重新启动 `cube-sandbox-cubelet.service`，不需要重启 CubeAPI、CubeMaster、数据库或网络服务。

```bash
systemctl start "$SERVICE"

READY=0
for attempt in $(seq 1 90); do
  if systemctl is-active --quiet "$SERVICE" &&
     curl -fsS --max-time 3 "$API_URL/cubeapi/v1/health" >/dev/null; then
    READY=1
    break
  fi
  sleep 1
done
test "$READY" -eq 1

systemctl status "$SERVICE" --no-pager -l
curl -fsS "$API_URL/cubeapi/v1/health" | jq .
```

如果 90 秒内未恢复健康，不要创建 Sandbox。先查看：

```bash
systemctl status "$SERVICE" --no-pager -l
journalctl -u "$SERVICE" -n 300 --no-pager
```

## 6. 确认镜像已经生效

### 6.1 文件层确认

```bash
sha256sum \
  "$INSTALL/cube-guest-image-cpu.img" \
  "$INSTALL/version" \
  "$INSTALL/agent-version"
cat "$INSTALL/version"
cat "$INSTALL/agent-version"
```

预期分别为：

```text
1ba4bd9bfd374ddc62ac72f0f0c529a5bd6a702c5351a2ea7e62e4a124ec10da  cube-guest-image-cpu.img
eee1c2823c374cfc64d9f75393575bbf85e29aa8b18062eb9247af062e20968f  version
eb8d59c0680eb3f8813d4c7254f5cd6dbb0160cb24efa20e92bdda11d548c2e8  agent-version
```

### 6.2 服务和资源层确认

```bash
systemctl is-active "$SERVICE"
curl -fsS "$API_URL/cubeapi/v1/health" | jq .
curl -fsS \
  -H "Authorization: Bearer $API_KEY" \
  "$API_URL/sandboxes" | jq .

pgrep -af '^/usr/local/services/cubetoolbox/cube-shim/bin/containerd-shim-cube-rs ' || true
find /data/cubelet/root/io.containerd.runtime.v2.task \
  -mindepth 2 -maxdepth 2 -type d -print 2>/dev/null || true
```

切换后的空闲状态应为：Cubelet `active`、API `status=ok`，且 Sandbox、shim、task 均为 0。

### 6.3 新 Template 层确认

通过现有 CubeSandbox UI、SDK 或 Template API 创建一个新 Template。不要复用替换前生成的 Template ID。新 Template 到达 `READY` 后执行：

```bash
NEW_TEMPLATE_ID=tpl-xxxxxxxxxxxxxxxx

curl -fsS "$API_URL/templates/$NEW_TEMPLATE_ID" | jq '{
  templateID,
  status,
  replicas: [.replicas[] | {
    node_ip,
    status,
    phase,
    guest_image_version,
    agent_version,
    kernel_version,
    compat_status,
    compat_policy
  }]
}'
```

历史镜像的预期关键字段为：

```text
status:              READY
guest_image_version: 20260609-222734
compat_status:       OK
compat_policy:       STRICT
```

`guest_image_version` 来自实际生成新快照时使用的镜像版本，是确认生效的关键证据。已有 Template 仍显示旧版本是正常现象。

最后使用新 Template 完成至少一次 `create -> guest exec/health -> delete`，并再次确认 `sandboxes/shims/tasks=0/0/0`。测试期间检查日志中是否出现：

```bash
journalctl -u "$SERVICE" --since "10 minutes ago" --no-pager |
  rg -i 'reset guest time failed|reset reseed random failed|rcu.*stall|timer handling issue|Recv len invalid' || true
```

## 7. 回滚

如服务健康检查、新 Template 构建或 Sandbox 生命周期失败，使用第 4 节输出的明确 `BACKUP` 路径回滚。回滚前同样要求 Sandbox、shim、task 和 Template 构建任务为空。

```bash
BACKUP=/usr/local/services/cubetoolbox/cube-image.backup-YYYYmmdd-HHMMSS

test -f "$BACKUP/cube-guest-image-cpu.img"
test -f "$BACKUP/version"
test -f "$BACKUP/agent-version"

systemctl stop "$SERVICE"

cp --reflink=auto --sparse=always \
  "$BACKUP/cube-guest-image-cpu.img" \
  "$INSTALL/.cube-guest-image-cpu.img.rollback"
cp "$BACKUP/version" "$INSTALL/.version.rollback"
cp "$BACKUP/agent-version" "$INSTALL/.agent-version.rollback"

mv -f \
  "$INSTALL/.cube-guest-image-cpu.img.rollback" \
  "$INSTALL/cube-guest-image-cpu.img"
mv -f "$INSTALL/.version.rollback" "$INSTALL/version"
mv -f "$INSTALL/.agent-version.rollback" "$INSTALL/agent-version"
sync -f "$INSTALL"

systemctl start "$SERVICE"
systemctl is-active "$SERVICE"
curl -fsS "$API_URL/cubeapi/v1/health" | jq .
sha256sum \
  "$INSTALL/cube-guest-image-cpu.img" \
  "$INSTALL/version" \
  "$INSTALL/agent-version"
```

回滚基础镜像后，如需验证旧镜像路径，也应重新生成一个 Template；不要用替换期间生成的新快照判断回滚结果。

## 8. `.90` 已验证结果

2026-07-25 在 `192.168.25.90` 使用本文历史镜像重新生成 2-vCPU Template 后：

- 串行完整生命周期 `20/20` 成功。
- 恢复后的额外冒烟 `1/1` 成功。
- `reset guest time failed` 为 0。
- 最终 `sandboxes/shims/tasks=0/0/0`。

对照的社区镜像在同日相同 host 组件下为 `5/11` 成功，6 次失败均为 `reset guest time failed`。完整实验记录见 [CUBESANDBOX_GUEST_IMAGE_AB_20260725.md](CUBESANDBOX_GUEST_IMAGE_AB_20260725.md)。
