# 贡献指南

问题和改进建议通过 [Issues](https://github.com/3aKHP/SCDP/issues)提出。请说明版本、复现步骤、预期与实际结果；日志应移除凭证、部署地址与私人路径。权利通知使用 [NOTICE](NOTICE.md) 中的专用入口。

## 开发与验证

需要 Python 3.12+、uv、Linux 文件锁；跨语言契约测试需要 Go。克隆仓库后在根目录运行：

```bash
uv sync --locked
uv run pytest -q
uv build
```

测试使用虚构剧情与模拟网络，不访问官方来源。新增行为选择有意义的测试；单纯文字修订检查链接、事实和示例即可。读取示例与说明见 [examples](examples/README.md)。

## 修改约定

当前接口以实现、schema 和[参考文档](docs/reference/README.md)为准。修改行为时同步更新文档；重要契约变更遵守 [ADR](docs/dev/adr/README.md)。写作规范见[文档规范](docs/dev/documenting.md)。使用 Agent 时遵守 [AGENTS](AGENTS.md)。

源码、schema 与合成夹具进入 Git。游戏正文、多媒体、运行数据库和真实凭证放入忽略目录，不随补丁提交。第三方代码复用记录来源、版本及许可证。新示例使用自行编写的虚构内容。

译文和元数据贡献需有来源身份，不能把来源不明内容当作官方数据。逐篇署名传递和许可覆盖核对见[后续工作](STATUS.md)，本轮尚未提供自动署名补齐工具。

提交说明描述问题、行为变化及实际验证结果；Commit 使用 Conventional Commits。提交前检查变更范围，避免将本地研究或部署信息带入公开文件。
