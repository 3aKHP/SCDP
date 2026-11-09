# 合成验证

运行 `uv run pytest -q`。所有 HTTP 响应与剧情均在测试内生成，不访问官方来源。
`fixtures/golden.json` 是 Python 与 Go 共同读取的契约样例。
真实数据验证结果保存在忽略工作目录，不属于 CI。
