# 2026-11-10 证据摘要

本目录保存固定日期的指标、来源身份、原始帧结构统计和主清单元数据，供版本管理与本地核对。剧情正文、媒体、完整资源目录和上游快照归档位于 Git 忽略的 local_dev/sandbox/research-20261110/。

[provenance.json](provenance.json) 记录初始交接证据的 SHA-256、大小、原件路径、来源提交和研究边界。后续离线分析的输入身份与方法记录在其摘要内。可先核对这些摘要，再使用本地原件复算。

| 文件 | 内容 |
|---|---|
| sc-audit.json | 汉化 CSV 全量解析指标及重复编号摘要 |
| album-baseline-comparison.json | 28 本旧相册与汉化剧本编号比对 |
| official-asset-map.json | 官方主清单观察，含分片名称与版本 |
| official-inventory-summary.json | 132 个分片的目录和类型计数 |
| official-vs-csv.json | 官方候选路径与汉化编号的交集 |
| official-samples-summary.json | 少量官方剧情的大小、摘要与帧字段 |
| official-branch-samples.json | 培育、失败路线和共享引导样本 |
| official-choice-sample.json | 选项与跳转结构样本 |
| official-manifest-stability.json | 清单读取前后的一致性观察 |
| feasibility-assessment.json | 原始可行性评估记录 |
| summary.json | 来源新鲜度与相册目录的原始摘要 |
| offline-resource-map-summary.json | 后续离线目录分组与文本容量观察，自带输入摘要和方法说明 |

原始评估记录保留当时的字段名。项目当前范围和交接入口以根 README.md、STATUS.md 及 docs/handoff/ 为准。未进行全量正文或媒体下载。
