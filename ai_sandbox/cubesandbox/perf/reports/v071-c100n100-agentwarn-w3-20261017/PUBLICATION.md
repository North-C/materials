# 发布范围、脱敏与校验

本次根据用户明确要求，将最新 agentwarn/w3 c100n100 报告与完整数据包发布到 materials 主分支，与先前性能报告相邻。

## 范围

完整保留初次交付包中的 **398 个原文件**：1 轮 pilot、5 轮正式测试的原始 benchmark JSON、组件日志增量、metrics、CLI 归属证据、清理回执、HTML/CSV/JSON/时间轴、环境快照、参考指南、执行脚本及通用工具源码归档。另加入报告入口、本发布说明、脱敏映射和公开文件校验清单。

没有包含含 API 密钥的 `capture100.agentwarn.json`，也没有重复打包传输中间包 `partial-data.tar.gz`、`captured-data.tar.gz`。

## 凭据检查与处理

- 在目标机用实际 API 密钥匹配原始包及嵌套 `tool.tar`，匹配数为 0；密钥本身未回传或写入报告。
- 独立检查包含嵌套工具包。发现 1 个真实 rootfs artifact 下载令牌，分布在 6 份 `cubelet_req-delta.log` 中，共 1,236 处：注解字段 618 处、下载 URL query 618 处。
- 这 1,236 处均替换为固定的 36 字符 `REDACTED_ARTIFACT_TOKEN_____________`。替换前后文件长度相同；保留所有 JSON/日志行、sandbox ID、时间戳、耗时和其他数值。
- 没有删除任何原交付文件。除上述 6 个文件外，其余 392 个原文件逐字节保持一致。未发现其他真实 Bearer、Cookie、私钥或常见访问令牌；工具样例中的 `YOUR_API_KEY` 是占位符。
- 具体文件路径、替换数、原始/公开 SHA256 和长度见 [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json)，不记录真实令牌值。

## 原始证据与公开副本的哈希边界

私有原始包 SHA256：

```text
b1228b26055a51a0875c85e17ec4104a47e8c72e7af4b30f0af4e0abf88bb46b
```

原 `capture-manifest.json`、派生报告内的采集元数据和验收记录保留原样，表示**采集时的原始证据**。其中 6 份日志的历史 SHA256 与公开脱敏副本不同，这是明确记录的发布变换，不应将这两套哈希混用。

- [SOURCE_SHA256SUMS](SOURCE_SHA256SUMS)：原交付文件的历史哈希，仅用于原证据追溯。
- [SHA256SUMS](SHA256SUMS)：本次公开副本的文件哈希，使用它验证下载后的文件。
- [PUBLICATION-MANIFEST.json](PUBLICATION-MANIFEST.json)：6 份日志从原始到公开版本的哈希映射。
- [PUBLICATION-VALIDATION.json](PUBLICATION-VALIDATION.json)：原文件保留、数值、JSON、链接和公开文件校验结果。

若重分析工具强制匹配原采集日志 SHA，应按上述映射识别脱敏文件；不要将发布替换误解为采集时截断或偷偷改写原采集哈希。已生成的时延结果不受令牌值替换影响。

## 下载和验证

下载 [result.tar.gz](result.tar.gz) 与 [result.tar.gz.sha256](result.tar.gz.sha256)，然后：

```sh
sha256sum -c result.tar.gz.sha256
mkdir published-result
tar -xzf result.tar.gz -C published-result
cd published-result
sha256sum -c SHA256SUMS
```

macOS 可将 `sha256sum -c` 替换为 `shasum -a 256 -c`。HTML 下载后可离线打开。用户最初收到的本地和 .90 私有原包未被覆盖；本次公开包有独立 SHA256。
