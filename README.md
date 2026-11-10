# Shiny Colors Data Pipeline（SCDP）

SCDP 采集并归档《偶像大师 闪耀色彩》enza 页游的剧情，将日文原文、已有中文译文及来源信息整理为可阅读的 Markdown 和可供程序处理的 JSON／JSONL 数据包。

它适合查阅剧情、建立检索资料库，以及为其他应用提供有版本和来源记录的数据。阅读资料无需部署 MCP 服务。

## 获取数据

从 [Releases](https://github.com/3aKHP/SCDP/releases) 下载数据及 `SHA256SUMS`，按[下载与阅读指南](docs/guides/use-data.md)核对摘要。

| 附件 | 适用用途 |
|---|---|
| `scdp-phase-one.tar.gz`（标准包） | 阅读剧情、处理结构化记录、开发集成；包含解码原件、译文来源和覆盖报告 |
| `scdp-mcp-kb-collection.tar.gz`（固定首版导入包） | v0.1.0 提供，已有兼容 MCP-KB 环境时通过原生工具安装 |

首次使用建议选择标准包。自动更新使用 `data-s<序列>-r<修订>` Release，提供标准包及 `manifest.json`。固定首版 v0.1.0 收录 10,936 篇剧情，见[首批报告](docs/research/2026-11-10-first-release.md)；当前范围见所选 Release 和 [STATUS](STATUS.md)。

## 快速开始

标准包解压后，从 `collection/README.md` 浏览目录，或直接打开 `collection/docs/` 下的 Markdown。程序读取示例在克隆本仓库后运行，只需要 Python 3.12+：

```bash
python3 examples/read_story.py /path/to/extracted-bundle
python3 examples/read_story.py /path/to/extracted-bundle SCRIPT_ID
```

第一条列出剧本 ID，第二条输出指定剧情。将路径和 `SCRIPT_ID` 替换为实际值。完整下载、解压及校验步骤见[使用数据](docs/guides/use-data.md)。

## 当前能力与限制

- 保留原文、选项、条件跳转和失败路线；阅读文档包含多条分支，不表示它们都在同一次经历中发生。
- 对齐已有社区中文译文并记录来源；缺译和歧义保留标记，日文仍可读取。当前不自动生成翻译。
- 支持断点恢复、历史归档、完整性校验、版本打包和定时更新。
- 资源目录包含多媒体类型；当前仅下载剧情文本，不提供图片、Spine、音频或视频文件。
- 标题、角色与卡片关联存在未知或推断值；当前清单覆盖不等于恢复全部游戏历史。

## 文档

- [使用已发布数据](docs/guides/use-data.md)
- [自行采集与构建](docs/guides/collect.md)
- [下游集成](docs/guides/integrations.md)
- [更新、恢复与运维](docs/guides/operations.md)
- [CLI、配置与包格式](docs/reference/README.md)
- [贡献指南](CONTRIBUTING.md) · [当前状态与后续工作](STATUS.md) · [文档地图](docs/README.md)

源码位于 `src/scdp/`，合成测试位于 `tests/`，使用示例位于 `examples/`，部署模板位于 `deploy/`。

## 来源与许可

本项目为非官方、非商业的同人资料整理与研究交流项目。代码采用 [AGPL-3.0-or-later](LICENSE)，第三方代码来源见 [THIRD_PARTY](THIRD_PARTY.md)。游戏原文和社区译文保留各自权利，不由代码许可证覆盖。

中文来源为 [ShinyGroup/SCTranslationData](https://github.com/ShinyGroup/SCTranslationData)。逐篇译者署名随包传递仍待完善。使用说明及权利通知、下架入口见 [NOTICE](NOTICE.md)。
