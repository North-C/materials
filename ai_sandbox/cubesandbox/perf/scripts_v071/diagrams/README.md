# 启动阶段流程图源文件

`template-startup-stages.mmd` 是图的唯一结构源文件；口径及图例见 [STAGES.md](../STAGES.md#启动流程与计时覆盖关系)。SVG 可在 GitHub 文档中直接显示，放大后查看细节。

本次使用 Mermaid CLI 12.0.0 和本目录配置渲染。安装 Node.js 与该版本 CLI 后，在本目录执行：

```sh
mmdc -i template-startup-stages.mmd -o template-startup-stages.svg \
  -c mermaid-config.json -b white --no-font-embed
```

如使用已有浏览器，可追加 `-p /path/to/puppeteer.json` 指定其 `executablePath`。字体优先使用 PingFang SC，其他系统使用 sans-serif 回退；渲染后检查中文、换行、箭头和嵌套框。SVG 不嵌入字体，不需要网络加载字体。
