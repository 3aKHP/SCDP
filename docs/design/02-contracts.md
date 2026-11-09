# 数据契约建议

状态：契约语义设计。正式字段、schema 与合成示例以[契约 v1](../../schemas/README.md)为准。

## 共同约定

所有包有 schemaVersion、snapshotId、来源身份和构建工具身份。snapshotId 作为不可变的不透明身份；消费者通过发布序号与修订协议选择版本。上游版本号原样保留。

资源、剧情和业务实体使用稳定游戏身份。文本帧身份包含剧本 ID、原始帧序和必要的发生位置；保留原始游戏帧 ID。重复的零值帧 ID 可以存在，同一篇内的原文重复也应保留。

路径统一使用 POSIX 相对路径，拒绝绝对路径、越界路径及归一化冲突。来源 URL、传输状态和正文摘要分别记录。生产凭证独立于发布数据。

## Snapshot

| 字段 | 语义 |
|---|---|
| schemaVersion | 外部数据契约版本 |
| snapshotId | 不可变快照身份 |
| releaseSequence / publicationRevision | 消费排序与同一来源修订身份，正式规则见 ADR-0002 |
| observedAt / builtAt | UTC 时间，区分观察与构建 |
| source | 主清单版本、摘要、分片身份和资源目录指纹 |
| inputs | 翻译 SHA、元数据身份、解析与对齐规则版本 |
| capabilities | 实际完成的文本、元数据、媒体和派生能力 |
| scope | 当前构建选择范围、排除政策和覆盖统计 |
| assets / packages | 可下载资源或分片清单、长度、摘要与定位器 |
| baseline / predecessor | delta 的依赖血缘，完整快照明确标识 |
| validation | 校验器身份、结果、缺失与异常分类 |

初版能力示例可为 story.raw、story.structured、story.translation、catalog.partial、asset.inventory。media.spine、media.voice 等能力在相应资源组完成校验后声明。能力缺失的消费行为由协议明确规定。

## Asset 与 AssetVersion

| 字段 | 首期要求 |
|---|---|
| assetId | 稳定逻辑身份，与下载域名、内容摘要分离 |
| logicalPath | 官方逻辑路径，保留命名空间 |
| kind | story、image、spine.skeleton、spine.atlas、texture、audio.voice、audio.bgm、audio.se、video、font、effect、unknown 等可扩展类别 |
| sourceVersion | 官方资源版本计数原值 |
| representations | 原始响应、解码内容、转码或修补产物的引用 |
| mediaType / size / sha256 | 分别针对每个 representation；未下载时明确未知 |
| locator | 本地包成员、对象存储对象或受控下载定位器；含来源与解析器身份 |
| firstSeen / lastSeen / presence | 当前清单观察和历史保留状态 |
| availability | 资源获取与有效性状态 |
| dependencies | 关联资源 ID、关系类型及必要性 |
| provenance | 源清单、观察时间、实际来源、处理规则与工具版本 |

availability 建议包含 inventoried、pending、available、retryable_error、source_missing、quarantined；presence 建议区分 current、historical、unknown。状态互相独立。已在清单发现但首期未选择下载的媒体记录保持可发现状态。

## Story

每篇保留 scriptId、原始 assetId 与 representation 摘要。category、title、归属实体、sourceOrder、characters、speakers、sourceLanguage、metadataProvenance 与 unresolvedFields 描述语义目录。

正文与控制数据至少保留：

- 原始帧序、游戏帧 ID、说话人、原文与原始格式标签。
- 旁白、标题、选择项、label、nextLabel 与其他控制字段。
- 控制节点、边、入口、分支上下文，以及未解析控制类型。
- 每行的 voice 资源引用，以及场景使用的图片、BGM、SE、立绘、视频引用。
- 失败路线、互斥路径和特殊背景标签的证据与推断状态。

图结构的共同节点可复用，所有可读正文与其帧定位应可回溯。仅完成资源获取时标记 raw 状态；结构化能力通过相应校验后声明。

## Translation

译文按 scriptId、帧定位、原文摘要、说话人及发生上下文对应。记录文本、语言、翻译类型、上游文件与行号、Git SHA、对齐规则、确定性及候选。

人工译、AI 译、通用译文回退与缺译分别标注。原文修订触发原文摘要与上下文复核。歧义保留候选与标记；原文始终可读取。新增译文能独立更新派生包。

## Entity 与 Relation

建议实体包括 character、unit、card、costume、story、event、music、media。身份保留游戏 ID 与来源命名空间。关系支持 card_has_story、costume_belongs_to_card、character_appears_in_story、frame_uses_voice、scene_uses_background、spine_uses_atlas、atlas_uses_texture、derived_from。

关系包含 provenance、confidence 或等效的确定性状态。由编号推断的关联、第三方明确给出的关联和官方主数据关联能够区分。未知标题、未知解锁条件保持未解析值。

## 字节摘要与兼容

清单资源版本计数、HTTP ETag 和内容 SHA-256 分别保存，消费者使用发布契约中的长度与摘要核验包。ETag 的具体含义由来源适配器解释。

初版建议使用 JSON／JSONL 与标准归档分发；可提供独立目录 SQLite 作为加速产物。消费者能够从规范数据重建索引。外部格式与 idolum 的内部数据库 schema 分别版本化。

正式 schema 需列出 required、nullable、未知枚举处理、扩展字段、向后兼容规则与摘要规范。格式变更配套升级示例与两个消费者的契约测试。
