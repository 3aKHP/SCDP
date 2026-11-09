# Shiny Colors Data Pipeline（SCDP）

《偶像大师 闪耀色彩》enza 页游的共享资产采集、历史归档与版本分发项目。

本仓库正在执行一期工程。已实现契约、采集与离线文本包基础，正在推进真实全量基线；正式资产发布、调度和 MCP-KB 完整消费验收尚未完成。实际进度见 [STATUS](STATUS.md)，可运行入口见[运行指南](docs/dev/running.md)。

## 产品范围

- 首期：官方日文剧情、关联元数据、已有中文译文的来源追踪与对齐。
- 一期验收消费者：MCP-KB；idolum 保留兼容设计与后续消费能力。
- 后续：idolum 将消费图片、Spine 立绘、语音等多媒体。通用资产身份、依赖、可用状态、交付和缓存接口须在首期设计中体现。
- 官方资源清单是资源发现与新鲜度主源；语义元数据和中文译文分别管理来源与版本。
- 原始资源、解码产物、结构化数据、消费者投影分别保存版本关系。

## 接手顺序

1. 阅读 [Agent 共同约定](AGENTS.md)；Claude Code 从 [专用入口](CLAUDE.md)加载相同规则与任务导航。
2. 从 [交接入口](docs/handoff/README.md) 开始，执行其中的阅读与实现顺序。
3. 对照 [研究报告](docs/research/2026-11-10-assessment.md) 和证据目录复核事实边界。
4. 按[一期交付范围](docs/handoff/04-phase-one-delivery.md)及其工程、数据、验收与上线任务推进，结合[设计文档](docs/design/README.md)固化契约。最终验证 MCP-KB 完整文本 collection 的实际消费。

## 当前研究快照

官方主清单 version 为 453，132 个分片，共 393759 条资源路径。json/ 下有 11000 条；排除 64 条 support_skills 后，得到 10936 条剧情候选路径。汉化库的 5612 个不同剧本编号均在清单内，另有 5324 条候选路径。

候选路径须经下载和解析确认内容。以上数字记录一次资源目录观察，完整历史剧情与完整语义目录仍需专项验收。

## 仓库目录

~~~text
src/scdp/       采集、契约、文本处理与打包
schemas/        正式机器契约入口
tests/          纯合成故障与契约测试
examples/       跨语言读取示例
docs/research/   调研结论、来源与可纳入版本管理的摘要证据
docs/design/     架构、数据契约、多媒体、消费者、验证发布的建议设计
docs/handoff/    Agent 入口、实现任务、未决事项
local_dev/      本地研究原件、原始剧情样本、临时工具和构建产物，Git 忽略
~~~

[文档地图](docs/README.md) · [当前状态](STATUS.md) · [文档规范](docs/dev/documenting.md) · [术语表](docs/glossary.md)
