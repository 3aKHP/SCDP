# SCDP — Claude Code 接手入口

先完整阅读并遵循 [AGENTS.md](AGENTS.md)，按其中的开始工作顺序加载项目上下文。本文件提供任务导航，共同协作规则由 AGENTS.md 维护。

## 当前任务入口

项目处于研究交接阶段，已完成内容见 [STATUS.md](STATUS.md)。从 [接手指南](docs/handoff/01-agent-start.md) 和 [实现计划](docs/handoff/02-implementation-plan.md) 选择当前交付阶段。

开始实现时先完成 P0 的正式契约与工程入口，再推进可离线重放的采集、解码和校验。实现语言、构建工具、CLI 和测试命令在相应阶段确定，并以实际验证结果更新开发文档。

一期执行从 [交付范围](docs/handoff/04-phase-one-delivery.md)进入，最终按 [MCP-KB 接入规程](docs/handoff/10-mcp-kb-delivery.md)验收完整 collection。公开面不得包含私有仓库与部署拓扑，具体规则由 AGENTS.md 维护，目标映射仅在本地工作区查找。

## 按任务加载资料

| 任务 | 阅读入口 |
|---|---|
| 理解已验证的来源与指标 | [研究结论](docs/research/2026-11-10-assessment.md)、[证据索引](docs/research/evidence/README.md) |
| 固化资产和剧情格式 | [架构](docs/design/01-architecture.md)、[数据契约](docs/design/02-contracts.md) |
| 设计多媒体发现、依赖和交付 | [多媒体资产](docs/design/03-multimedia.md) |
| 对接 idolum 或 MCP-KB | [消费者适配](docs/design/04-consumers.md) |
| 实现恢复、校验和版本发布 | [验证与发布](docs/design/05-validation-release.md) |
| 修改文档或形成重要决定 | [文档规范](docs/dev/documenting.md)、[术语表](docs/glossary.md)、[ADR](docs/dev/adr/README.md) |

首期文本实现应同时满足通用资产契约。idolum 的后续多媒体消费需求由多媒体设计与消费者契约共同承接。

## 会话资料

本机存在 local_dev/README.md 时，按其说明定位研究原件、参考仓库和执行记录。共享交接以仓库内研究摘要、设计与任务说明为依据。

阶段交付后更新 STATUS.md 和对应任务状态，将实际执行的验证记录保存到本地工作区。Commit、Push 与生产操作遵循 AGENTS.md 和用户当时的授权。
