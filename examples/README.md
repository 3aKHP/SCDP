# 契约读取示例

[Go 读取器](reader-go/main.go) 与 Python `scdp.contracts.validate` 读取同一黄金样例。
在仓库根运行 `go run ./examples/reader-go/main.go tests/fixtures/golden.json`。
Go 使用标准库，无外部依赖。它核对身份、依赖与表示摘要并输出可比较的摘要。
完整 JSON Schema 校验由 Python 执行，Go 示例不声明为通用 schema 校验器。
