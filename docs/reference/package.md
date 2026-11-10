# 数据包格式

## 标准包

归档根目录即包根目录。固定身份、成员长度和摘要在 `snapshot.json` 中；正文记录使用 UTF-8 JSONL，每行一个对象。正式字段由[契约](../../schemas/README.md)定义。

| 成员 | 内容 |
|---|---|
| `assets.jsonl`、`versions.jsonl` | 稳定资产身份与版本、表示形式 |
| `stories.jsonl`、`translations.jsonl` | 剧情结构与译文对齐记录 |
| `entities.jsonl`、`relations.jsonl` | 语义实体及关系 |
| `sources.json`、`inputs.json` | 来源记录与构建输入身份 |
| `schema.json`、`history-audit.json` | 随包 schema 与历史覆盖审计 |
| `coverage.json`、`metadata-report.json` | 覆盖范围、缺口与冲突 |
| `originals/` | 精确解码后的剧情 JSON；传输实体留在采集对象库 |
| `collection/README.md` | 可阅读剧情目录 |
| `collection/docs/` | Markdown 剧情与分支证据 |
| `collection/import-manifest.json` | `documents` 数组，包含 `scriptId`、相对 collection 的 `path`、长度和摘要 |
| `collection/references/`、`collection/collection.yaml` | 资源引用及消费配置 |

通过导入清单定位阅读文件，不根据标题猜路径。数据修订 2.1 起，普通对白以加粗帧标记连续展示，控制证据帧及其后续帧分段；选择、跳转和未知控制不会因取消逐帧标题而消失。阅读层统一 LF，精确原件保留原格式。未知控制、歧义和缺译保持可见，全文包含互斥路线。

## MCP-KB 导入包

由 MCP-KB 原生打包协议生成，用于该组件的安装流程。它不是完整标准包，不替代标准记录、解码原件和完整校验。安装要求见[集成指南](../guides/integrations.md)。

## 版本和验证

自动数据 Release 命名为 `data-s<releaseSequence>-r<publicationRevision>`，附件包括标准包、`SHA256SUMS`、`NOTICE.md` 和 `manifest.json`。
`manifest.json` 使用 `format: scdp-release/v1`，记录 `snapshotId`、`releaseSequence`、`publicationRevision`、`filename`、`bytes` 和 `sha256`。
`filename` 为 `scdp-phase-one.tar.gz`；长度与摘要指向压缩归档，序列和修订须与 tag 及包内 `snapshot.json` 一致。
消费者只接受完成公开的正式数据版本，校验失败保留现有活动版。旧 v0.1.0 不包含该描述符，作为固定快照单独使用。

当前发布为完整快照，`baseline` 为 null，不支持增量包。`snapshotId` 标识不可变构建，`releaseSequence` 与 `publicationRevision` 决定发布顺序。同身份内容不覆盖。

下载先核对 Release 摘要，完整标准包使用 `scdp validate` 校验。缺译与部分未知元数据允许存在，正文遗漏、摘要错误或必需依赖缺失不能视作可用发布。来源权利见 [NOTICE](../../NOTICE.md)。

新构建的 collection 可见性为 public，已认证普通 KB 用户可读；服务本身仍需鉴权。已有包不改写，具体决定见 [ADR-0004](../dev/adr/0004-reading-segments-and-public-collection.md)。
