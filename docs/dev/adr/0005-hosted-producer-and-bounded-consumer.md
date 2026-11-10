---
status: Accepted
superseded_by: []
---
# 0005 — 托管生产调度与有界消费存储

- 决定日期与记录日期：2026-11-11。
- 实施状态：[STATUS](../../../STATUS.md)。

## 背景与决定

数据生产每两小时在 GitHub 托管 Runner 上执行，负责来源检查、采集、构建、校验及公开 Release 发布。
消费服务器拉取已完成发布的标准包，执行原生候选导入、完整协议验收、激活与失败回退。
MCP-KB 索引仍由消费环境结合其他 collection 构建。

数据 Release 使用 `data-s<releaseSequence>-r<publicationRevision>`。
包、`manifest.json`、`SHA256SUMS` 和 `NOTICE.md` 上传到 Draft 并读回校验后再公开。
已公开附件不覆盖；版本按序列和修订号比较，既有固定 Release 保留。

## 持久化与恢复

专用 `scdp-runner-state` Draft Release 保存私有采集检查点，其正文记录当前代、上一代和运行占用。
检查点包含原件对象、观察历史、获取记录、SQLite 账本、构建身份、译文及固定元数据。
允许列表导出并重写可迁移路径，排除部署配置、消费者回执、日志、构建目录和服务凭证。
Draft 访问限制见 GitHub 官方文档；该状态 Release 禁止公开。

生产 workflow 仅在默认分支和显式启用变量下运行，使用同一 concurrency group，运行中不取消。
开始真实获取前写入占用。新原件检查点先于其派生数据公开保存；最终检查点读回验证后推进状态。
普通失败也保存累计账本。Runner 丢失或检查点保存失败留下占用，下一轮拒绝使用旧账本继续获取。
恢复时按剩余授权预算保守计费，维护者核对后才能重新授权预算。

只保留当前与上一份已确认检查点，原件历史累计保存在每份完整检查点中。
Actions cache 不承担唯一账本。状态修改只允许单实例 workflow 或停用 workflow 后的维护操作；
Release API 不提供这里所需的跨操作者事务锁。

## 消费空间

消费目录保留当前代和立即前代完整 sources/index。其他具有明确 SCDP 所有权的候选在共享部署锁下回收。
回收前核对活动指针、当前与前代摘要、恢复日志状态。未知状态停止回收。
已完成候选内的准备副本及原生安装临时备份可以移除，原生包和核验回执保留。
下载与解包目录只用于当前消费，正常结束清理，中断残留在下轮处理前清理。

消费先检查下载空间，再按实际展开字节、collection 大小、全库 sources、索引上限和空闲保留量做容量门禁。
默认保留 4 GiB 空闲，标准包上限 512 MiB、展开上限 3 GiB、单索引上限 2 GiB。
这些是首期文本限额，多媒体接入前重新规划。公式见[托管调度运维](../../guides/hosted-pipeline.md)。

## 代价与验证

每轮传输完整检查点，增加 GitHub 存储与网络开销。消费失败不阻止已经完成的数据分发，服务器重试同一版本。
调度时间不保证端到端时效，记录实际排队与激活时间。
合成验证覆盖换机恢复、预算保留、异常占用、不可变发布、容量门禁、候选清理及清理后的回退。
真实迁移还须完成账本恢复、Runner 实际发布、生产协议验证、清场前后磁盘测量和定时观察。

## 依据

2026-11-11 核对：[Draft 可见性](https://docs.github.com/en/rest/releases/releases#list-releases)、
[Release 附件](https://docs.github.com/en/rest/releases/assets)、
[cache 与 artifact](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching)、
[schedule 事件](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。
