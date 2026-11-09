# 消费者适配

状态：基于本地 idolum 与 MCP-KB 的代码调查形成的建议。

## 共享边界

SCDP 提供原始资产、结构化剧情、对齐译文、实体关系、资源依赖和版本清单。MCP-KB、idolum 和后续消费者各自选择资料范围、渲染方式、索引与运行缓存。

共享输出保留完整事实和处理证据。角色的可回忆范围、失败路线是否作为亲历、互斥经历如何进入 RAG，由 idolum 的消费策略定义；KB 可以提供全文阅读与分支说明。

## MCP-KB

MCP-KB 服务只读，source collection 为事实文档，SQLite 索引可重建。目标源码与部署位置由本地工作区映射管理。一期最终验收以完整闪彩文本 collection 在 MCP-KB 的实际安装、检索和全文读取为准，详见[验收矩阵](../handoff/07-acceptance.md)。

稳定 collection-id 为 games/shinycolors/story-bilingual，每次接入前核对目标环境。输出 docs/、references/、collection.yaml 与可追溯导入清单，原件引用或附件按索引政策排除。正文保留角色、旁白、选择、互斥路径与汇合位置。

资料包依次执行 staging、validate-collection、pack-collection、安装、索引重建和 smoke-index。首个消费者实现遵守目标仓库当前发布协议；默认可见性与实际发布状态按对应配置记录。

## idolum 剧情库

本轮调查的 idolum 源码基点为 95087bb95af5bfb761cce42966e92f1667e5f1d2，以下路径相对于该项目根目录。

关键入口：

| 文件 | 关注点 |
|---|---|
| backend/src/eidolon/corpus.py | Line、Episode、StoryCorpus、段落构建与向量复用 |
| backend/src/eidolon/story_import.py | 稳定剧本 ID、角色映射、失败路线、CSV 优先规则 |
| backend/src/eidolon/story_sync.py | 当前采集、来源合并和同步报告 |
| backend/src/eidolon/__main__.py | story import-csv、import-json、sync 的 CLI |
| contracts/README.md、schema.sql | 对外行为与内部数据库契约 |

Episode 包含 id、category、source、title、cast、lines、imported_from；Line 包含 speaker、ja、zh。imported_from 目前仅有 csv／json，translated 根据 csv 身份判断。原生 import-json 可读取原始帧中的日文正文，结构化双语数据需要专用适配器。

建议增加受版本约束的数据包导入边界，按稳定 scriptId 更新现有 Episode。双语来源和完整性应通过新的明确语义表达；如影响 translated、schema 或其他行为，按 idolum 自己的契约与决策流程记录变更。

SCDP 的角色 ID 保存游戏身份。idolum 根据自己的角色配置建立映射，保持人物别名和共同说话人的处理证据。没有可映射出场角色的剧情仍可归档，RAG 是否建立索引由消费者决定。

向量化由 idolum 完成，模型身份、维度、切块策略和向量缓存保留在消费侧。标题、正文、译文或策略变化时，按实际检索输入决定需要重新嵌入的段落。

## 分支、经历与更新

现有 idolum 会移除已识别失败路线并忽略选择项。新适配器可先保持经确认的产品行为，同时记录筛选政策与覆盖报告。互斥路径需具有上下文，避免将各分支的反应拼成单一已发生经历。

升级时校验包与资源依赖，构建或导入候选剧情状态，完成角色范围和代表性检索后激活。失败保留上一代可用状态。SCDP 源目录、派生 SQLite 与 idolum 的部署数据库分别管理；剧情更新通过导入边界执行。

## idolum 多媒体

| 文件 | 关注点 |
|---|---|
| backend/src/eidolon/stand_fetch.py | 原料清单、衣装获取与 atlas 兼容处理 |
| backend/src/eidolon/stand_outfits.py | source/spine_manifest.json、outfits/<idol_id>.json |
| backend/src/eidolon/stand_upload.py | 对象存储布局、真实 MIME、资源先于清单上传 |
| frontend 立绘消费与配置 | 渲染器版本、资源根路径、默认衣装与降级 |

建议媒体适配器从 SCDP 选择角色、卡片和衣装，解析依赖闭包，生成当前布局的兼容产物，再调用或替换原有上传边界。后续图片和语音可使用相同资产 resolver。用户运行素材和私人对象存储凭证由 idolum 部署管理。

## Python 与 Go

idolum ADR-0029 定义未来逐步迁移 Go。SCDP 通过数据包和稳定的 schema 供不同实现消费，避免将 Python 内部对象作为交换格式。消费者的模型服务、存储事务、HTTP 和通话协议各自保持契约。

初期可以提供语言无关的黄金样例和消费验收工具；Python 与 Go 对相同包应得到相同的剧情身份、来源、筛选范围、媒体依赖和摘要结果。
