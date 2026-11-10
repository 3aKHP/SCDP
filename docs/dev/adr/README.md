# 架构决策记录

本目录供贡献者记录影响资产身份、数据与版本契约、持久化、模块依赖、媒体交付、消费者兼容或发布策略的重要选择。当前设计入口见 [设计文档簇](../../design/README.md)。

## 创建与索引

形成具体决定时使用 [模板](template.md)。文件按创建顺序采用 NNNN-short-title.md，四位编号递增并保持稳定。新增记录同步登记本页，候选方案记录有依据的内容。

每篇写明背景、决定、理由、代价、来源与验证入口。原始决定日期和记录日期分别表示，无法核实的日期明确标记。

- [0001 — Python 运行时与文本交换契约](0001-runtime-and-contract.md)（Accepted）
- [0002 — 历史正文、内容修订与消费切换](0002-history-and-activation.md)（Accepted）

- [0003 — 公开分发与权利通知处理](0003-public-distribution-and-notice.md)（Accepted）

- [0004 — 阅读段落与公开 collection](0004-reading-segments-and-public-collection.md)（Accepted）

- [0005 — 托管生产调度与有界消费存储](0005-hosted-producer-and-bounded-consumer.md)（Accepted）

## 状态

| status | 含义 |
|---|---|
| Proposed | 具体方案待决定 |
| Accepted | 决定已接受，实现进度另行跟踪 |
| Rejected | 决定未采用，保留依据 |
| Superseded | 已由后续记录替代 |

编号记录使用 YAML front matter。status 必填，superseded_by 为同目录文件名列表，默认空列表。Superseded 状态列出有效后继记录。

已接受决定发生实质变化时新增 ADR，更新旧记录状态、替代关系与本页索引。文字和引用修正保留当时事实。交付进度与审阅过程放在任务或本地记录。
