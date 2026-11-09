# 2026-11-10 来源与可行性评估

观察范围为 enza 页游《偶像大师 闪耀色彩》。首期交付剧情文本和关联元数据；idolum 后续将消费非文本多媒体，通用资产接口应在首期建立。

## 结论

自建 SCDP 具备关键技术条件。官方客户端使用 asset-map.json 与分片清单发现资源；本轮匿名读取了完整清单，并抽样验证官方剧情下载、解码与选项控制信息。

建议官方资源清单负责发现和新鲜度，SCDP 负责可追溯采集与版本分发，第三方元数据和中文译文独立管理。MCP-KB 与 idolum 通过各自适配器消费同一份事实数据。

## 官方清单实测

| 项目 | 本次观察 |
|---|---|
| 主清单 version | 453 |
| 分片 | 132，读取全部成功 |
| 资源路径 | 393759 |
| 主清单声明总字节 | 38617604383，约 38.6 GB |
| 分片传输字节 | 1554239 |
| 分片解码后字节 | 24981599 |
| json/ 路径 | 11000 |
| support_skills | 64 |
| 首期剧情候选路径 | 10936 |
| 主清单缓存 | max-age=60；ETag 条件请求实测 304 |
| 前后快照 | 本轮读取前后的主清单解码内容一致 |

完整目录包含 sounds 278406、images 78929、spine 17282、movies 3398 条路径，其余为 AE、粒子、字体及 json/ 资源。各顶层目录与扩展名统计见 [索引汇总](evidence/official-inventory-summary.json)。Spine 等目录也包含 JSON，首期候选口径限定 json/ 命名空间。

主清单的 totalSize 为上游声明值。文件版本是整数计数，尚未发现可据此验证文件内容的上游摘要。采集程序需要自行计算原始与解码内容摘要。

## 剧情来源完整度与新鲜度

SCTranslationData 固定提交为 dce164640732863cfd15b9aa318b799669321687。全量 CSV 解析得到 5623 个文件、5612 个不同剧本编号、10 组重复编号、1 个缺少来源编号的文件。按已收录正文的非空译文列统计，239391 / 249950 行约为 95.78%；选择项、info、表头与译者记录排除，通用译文回退尚未计入。该比例描述库存译文情况。

该仓 2026-11-08 的最新提交修改旧活动的一份 CSV，增删各 4 行；最近新增剧情文件为 2026-06-16。编号最高的常规活动为 086《よっつのものがたり》，活动开始于 2025-05-30。按 2026 年活动表抽查的 11 场新剧情活动均无同名目录匹配。

ShinyColorsDB 的近期卡片元数据列到 2026-10-31，2026-10-30 的两张新卡所列 5 篇剧情均可读取；其 28 本相册的 Last-Modified 均为 2024-03-24。相册中 3655 个不同的可映射数字剧本编号，在汉化 CSV 中匹配到 2077 个，未匹配 1578 个。此项属于旧目录编号比对，包含失败路线和特别交流。

官方当前剧情候选路径中匹配到全部 5612 个汉化剧本编号，另有 5324 条候选路径。候选路径仍可能包含短交流、系统片段、内容重复或不可用文件。[比对结果](evidence/official-vs-csv.json)

## 下载与结构样本

- produce_events/201502201：2026-10-30 新卡剧情样本，官方 JSON 与 ShinyColorsDB 镜像解析结果一致。
- game_event_communications/400109901：活动剧情样本，168 帧、86 帧含正文。
- produce_events/100100308：旧失败路线样本，14 帧、5 帧含正文。
- produce_events/180300102：67 帧，包含 3 个 select 字段、6 个 nextLabel 字段和 4 个 label 字段。
- produce_events/109900601：共享培育引导样本；完整 say Halo 剧情覆盖仍待独立核对。

以上实测验证少量具体文件的可获取性。全部候选文件的下载成功率、正文总量、图结构正确性和多媒体可用性尚待验证。[样本结果](evidence/official-samples-summary.json) · [分支样本](evidence/official-choice-sample.json)

## AKDP 参考

参考项目为 3aKHP/arknights-data-pipeline，核对提交 bcd442cd5e4214858e72bca3b6dcad0f255bd1fb。调查阅读了 README.md、SOURCE_STRATEGY.md、data-pipeline.yml，并抽查变更检测及打包代码。

可继承的工程模式包括：官方新鲜度信号、历史基线与新增资源合并、内容指纹、固定工具身份、发布前校验、draft-first、不可变发布与向前修订、消费者保留上一代有效版本。现有 AKDP 定时周期为 2 小时。

SCDP 的源版本、翻译版本、语义元数据版本需要分别表示；正式消费身份由 SCDP 发布协议定义。

## idolum 参考

参考项目为 3aKHP/idolum，核对提交 95087bb95af5bfb761cce42966e92f1667e5f1d2。调查核对了 Episode/Line、剧情导入、向量缓存、衣装源清单、对象存储上传和 contracts/。

idolum 以剧本路径作为剧情身份；现有导入过滤失败路线、丢弃选择项，CSV 优先于同篇原始 JSON。其角色经历规则由消费者适配层执行。其数据模型和路径布局为兼容目标，生产数据库含用户资料，消费集成应通过剧情导入边界完成。

idolum ADR-0029 明确未来逐步迁移 Go。contracts/README.md 在本次本地快照中记录 2026-11-01 的 70 张表和接口快照。SCDP 的外部交换格式应支持 Python 与 Go。

## 参考方法与来源

- [eidolon-sc 官方资源适配](https://github.com/Sallyn0225/eidolon-sc/blob/8cdb82b84670466041aed02640bb747f81ddca96/backend/src/eidolon/official_cdn.py)：路径解析、公开资源解码和截断检查参考，代码适用该仓 AGPL。
- [eidolon-sc 剧情缓存](https://github.com/Sallyn0225/eidolon-sc/blob/8cdb82b84670466041aed02640bb747f81ddca96/backend/src/eidolon/script_cache.py)：条件请求、断点与原子写入参考。
- [shinycolors-assets-downloader](https://github.com/hakatashi/shinycolors-assets-downloader/blob/1810c260eb26915abbe938027875d1faa539fb1f/index.ts)：主清单与分片枚举参考，仓库 LICENSE 为 Apache-2.0。
- [SC_text_table](https://github.com/nico-3p/SC_text_table)：资源清单消费的另一实现，尚未评估生产适用性。
- [SCTranslationData](https://github.com/ShinyGroup/SCTranslationData/tree/dce164640732863cfd15b9aa318b799669321687/data/story)：中文译文和历史剧情元数据来源。
- [ShinyColorsDB](https://shinycolors.moe/)：卡片、角色及镜像参考。
- [2026 活动表](https://shinycolors.wiki/wiki/Event_List/2026)、[よっつのものがたり](https://wikiwiki.jp/shinycolors/よっつのものがたり)：活动名称与日期对照。
- [GitHub schedule 说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)：定时运行可能延迟。

源码许可与游戏数据分发条件分别记录。正式公开数据分发策略在实现阶段明确；当前本地研究原文位于忽略目录。

## 仍需证明

全量候选文件可用性；完整语义目录与解锁条件来源；新版培育归属；无版本号变化的内容修订检测；全部分支控制格式；实际文本下载量；媒体实体关联与物理路径解析；从未进入当前清单的历史资料恢复范围。

首次获取 10936 个文件，按每秒 1 次请求计算，仅间隔约 3.04 小时，传输、重试和解析时间另计。每 10 分钟检查清单为建议目标，实际时效以官方可用时间、缓存和构建耗时观测。
