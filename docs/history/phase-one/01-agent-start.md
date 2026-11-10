> 历史归档：2026-11-10 一期建设材料。保留当时要求与观察，不作为当前操作指南。当前用法见[使用指南](../../guides/README.md)。

# 接手指南

## 交接上下文

用户希望自建闪耀色彩资产流水线，复用 AKDP 的自主采集和可靠分发经验。MCP-KB 与自维护的 idolum 共享数据来源。idolum 将来确定消费非文本多媒体，这项需求已经进入首期接口设计范围。

当前实现、验收证据和下一步交付见 [STATUS.md](../../../STATUS.md)。

## 阅读顺序

1. 根目录 README.md、AGENTS.md、STATUS.md、.gitignore。
2. [来源评估](../../research/2026-11-10-assessment.md) 与 [证据摘要清单](../../research/evidence/provenance.json)。
3. [架构](../../design/01-architecture.md)、[契约](../../design/02-contracts.md)、[多媒体](../../design/03-multimedia.md)。
4. [消费者](../../design/04-consumers.md)、[验证发布](../../design/05-validation-release.md)。
5. [实现计划](02-implementation-plan.md) 与 [未决事项](03-open-questions.md)。
6. [一期交付范围](04-phase-one-delivery.md)至[执行 Agent 指南](09-agent-execution.md)，按系列索引加载工程、数据、验收与上线任务。

v1 字段和格式已在[正式契约](../../../schemas/README.md)固化。阅读本地相关仓库前遵守其 AGENTS.md、README、领域文档和凭证规则。

## 研究复核

[研究报告](../../research/2026-11-10-assessment.md)给出来源、观察口径和样本结论，[证据索引](../../research/evidence/README.md)列出可分发的结构统计与摘要。拥有本地研究副本时，可按工作区说明核对完整索引、原件和参考脚本。新环境从公开来源获取输入并固定观察身份。

研究脚本用于固定快照调查。正式实现应校验缓存的来源版本与摘要，并覆盖重试、并发、发布验证和各资产类别的处理规则。代码复用记录来源与许可，逻辑定位 hash 与内容摘要分别处理。

## 当前事实边界

- 研究报告保留初始目录与抽样口径；当前全量获取、可读性、正文唯一性和消费结果见 [STATUS](../../../STATUS.md)。
- 官方标题、完整卡片／活动关联、解锁条件仍需语义来源适配。
- say Halo 的共享引导有样本，全部角色路线与正式目录未完成验收。
- 最新人工作品译文取决于上游更新。原文、元数据和译文各自追踪来源。
- 后续媒体需单独验证定位、依赖、编码、容量和消费布局。

## 参考项目

| 项目 | 仓库身份 | 本轮核对提交 |
|---|---|---|
| idolum | 3aKHP/idolum | 95087bb95af5bfb761cce42966e92f1667e5f1d2 |
| AKDP | 3aKHP/arknights-data-pipeline | bcd442cd5e4214858e72bca3b6dcad0f255bd1fb |
| MCP-KB | 独立消费者组件 | 本机源码基点由忽略目录中的交接记录维护 |
| eidolon-sc 上游 | Sallyn0225/eidolon-sc | 8cdb82b84670466041aed02640bb747f81ddca96 |

idolum 独立维护，以其源码与 contracts/ 为消费兼容依据。跨仓库操作前核对目标工作区、用户授权和仓库约定。本机目录映射由本地工作区维护。

## 工程验证顺序

完成 P0 契约和一个离线可重复的 discovery → fetch → decode 小闭环。合成样例覆盖文本、分支、失败路线、Spine 依赖与不同表示形式。真实源复核先限于主清单、必要分片和少量样本。

之后再推进一次可恢复的全量文本基线采集，并出具覆盖报告。业务门禁和原始归档的职责在这一阶段通过真实数据校验。
