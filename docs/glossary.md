# SCDP 术语表

本表统一跨文档概念名称。操作步骤见[使用指南](guides/README.md)，CLI 和包布局见[接口参考](reference/README.md)；下表链接解释概念职责，正式字段见[契约 v1](../schemas/README.md)。

| 术语 | 定义 | 详细说明 |
|---|---|---|
| 资产（Asset） | 具有稳定逻辑身份的剧情或多媒体资源 | [数据契约](design/02-contracts.md) |
| 资产版本（AssetVersion） | 某次来源观察下资产的具体内容与证据 | [数据契约](design/02-contracts.md) |
| 表示形式（Representation） | 原始响应、解码内容或派生产物的一种字节表达 | [架构](design/01-architecture.md) |
| 资源目录（Inventory） | 来源声明的逻辑资源路径、版本和观察信息 | [来源研究](research/2026-11-10-assessment.md) |
| 快照（Snapshot） | 固定输入和处理规则形成的不可变数据状态 | [数据契约](design/02-contracts.md) |
| 发布修订（Publication Revision） | 同一来源身份下向前发布的修复代次 | [验证与发布](design/05-validation-release.md) |
| 剧本（Script） | 按游戏稳定剧本 ID 定位的原始帧序列 | [数据契约](design/02-contracts.md) |
| 剧情候选路径 | 按来源命名空间选出的待下载、解析文件路径 | [研究口径](research/2026-11-10-assessment.md) |
| 语义元数据 | 剧本标题、归属、角色、顺序、条件等解释信息 | [数据契约](design/02-contracts.md) |
| 来源证据（Provenance） | 输入身份、观察、处理规则和摘要的可追溯记录 | [数据契约](design/02-contracts.md) |
| 依赖闭包 | 获取一个资源或资源组所需的全部必需依赖 | [多媒体](design/03-multimedia.md) |
| 消费者投影 | 面向特定消费方式生成的数据布局和筛选结果 | [消费者](design/04-consumers.md) |
| 当前清单状态（Presence） | 资源是否出现在当前来源目录的观察状态 | [数据契约](design/02-contracts.md) |
| 可用状态（Availability） | 资源的获取、有效性和隔离处理结果 | [数据契约](design/02-contracts.md) |

原文、译文、媒体、消费者索引和应用私有运行数据分别具有自己的来源与生命周期。
