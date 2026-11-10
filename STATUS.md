# SCDP 当前状态

更新日期：2026-11-11。文本采集、归档、版本分发和 MCP-KB 接入已运行。

## 当前生产数据

官方清单版本 454，394,588 条资产目录，10,950 篇剧情。当前生产数据修订为 `releaseSequence=2`、`publicationRevision=1`。

阅读文档将普通对白合为段落，并保留控制边界。闪彩 collection 有 65,531 个切片；全库活动索引为 907,374,592 字节。全部 10,950 篇已通过生产分页全文读取和检索验证，其他 collection 的 17,811 个文件保持一致。结果与固定身份见[阅读分段验证报告](docs/research/2026-11-11-reading-segments.md)。

闪彩 collection 为 Public，已认证普通用户可访问；外部网关继续校验 Token，其他私有 collection 和受控下载服务保持原权限。代码和数据权利见 [NOTICE](NOTICE.md)，消费可见性与阅读格式见 [ADR-0004](docs/dev/adr/0004-reading-segments-and-public-collection.md)。

GitHub 托管生产已启用，每两小时检查一次；[首轮实际运行](https://github.com/3aKHP/SCDP/actions/runs/42918269262)已发布 [data-s2-r2](https://github.com/3aKHP/SCDP/releases/tag/data-s2-r2)。旧采集 timer 已停用，现有阅读服务继续运行，独立消费者正在进行生产切换验收。真实冻结检查点的 10,950 篇原件与解码、资产目录及累计账本离线恢复通过。82 项合成测试、workflow 检查与代码包构建通过。迁移步骤见[托管调度](docs/guides/hosted-pipeline.md)。

迁移验收还包括真实 Runner 发布、生产消费、完整前代恢复及清场前后磁盘测量，完成后记录实际结果。

## 已发布固定快照

GitHub v0.1.0 保留官方版本 453 的 10,936 篇剧情及原始附件摘要。其覆盖范围和首批验收结果见[首批发布报告](docs/research/2026-11-10-first-release.md)，不代表当前生产数据计数。

## 能力与后续工作

原文、已有译文、选项、条件跳转、重复标签、互斥与失败路线完整保留。缺译、歧义、部分标题冲突和未知关联显式记录，当前目录覆盖不等于恢复全部游戏历史。

逐篇译者署名提取与随包传递、历史译文许可覆盖范围继续评估。当前 v1 契约包含后续媒体表示与依赖，但尚不下载媒体内容。idolum 已有合成兼容验证，其生产激活及多媒体消费属于后续工作。

操作见[使用指南](docs/guides/README.md)，接口见[参考文档](docs/reference/README.md)。运行目标、凭证引用和恢复回执由忽略工作区维护。
