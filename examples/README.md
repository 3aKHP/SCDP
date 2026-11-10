# 数据读取示例

## 标准包阅读（Python）

`read_story.py` 只使用 Python 3.12+ 标准库。在仓库根运行：

```bash
python3 examples/read_story.py /path/to/bundle
python3 examples/read_story.py /path/to/bundle SCRIPT_ID
```

第一条列出 ID，第二条原样输出阅读文档，包括已有译文、缺译和分支证据。路径应指向已解压的标准包，不是 MCP-KB 导入包。输入错误非零退出。示例不下载、不写入、不代替完整校验。下载说明见[使用指南](../docs/guides/use-data.md)。

## 合成契约（Go）

[Go 读取器](reader-go/main.go) 与 Python `scdp.contracts.validate` 使用同一黄金样例。在仓库根运行：

```bash
go run ./examples/reader-go/main.go tests/fixtures/golden.json
```

它使用 Go 标准库，核对合成对象的身份、依赖和表示摘要。输入是单个 JSON 契约样例，不是标准包目录；完整 schema 校验由 Python 执行。
