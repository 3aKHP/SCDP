# 更新配置

`scdp cycle --config CONFIG` 读取 JSON。可复制[配置模板](../../deploy/cycle.example.json)，替换部署路径和已核验来源身份后使用。模板中的路径是部署示例，不是公共服务位置。

| 字段 | 默认或要求 |
|---|---|
| `work`、`destination` | 必填，持久工作目录和文件发布目录 |
| `budgetBytes` | 1073741824，累计下载预算 |
| `rate`、`workers` | 每秒 1 次、并发 2 |
| `rollingChecks`、`shardChecks` | 每轮分别检查 1 个正文、1 个分片 |
| `sourceBase` | 默认官方资源源地址；自定义源需兼容协议 |
| `translation` | 可选，译文来源配置，见下文 |
| `metadata` | 可选，本地固定元数据目录 |
| `consumerCommand` | 可选，命令 argv 数组，替换 `{bundle}`、`{archive}`、`{snapshotId}`；不通过 shell 执行 |
| `consumerTimeout` | 3600 秒 |
| `seedManifest` | 可选，从已有快照初始化基线；仅在无 cycle 状态时生效 |
| `codeCommit`、`workspaceDiffSha256` | 可选，运行报告的代码身份说明 |

本地译文使用 `path`、`identity`、`sha256` 固定归档身份。配置 `repository` 时更新循环可检测该 GitHub 来源的提交，并下载新归档；译文预算由 `translation.budgetBytes` 单独管理。`translation.budgetBytes` 默认 268435456 字节，`translation.responseLimit` 默认 67108864 字节。没有译文配置时仍可构建日文包。来源处理实现见 [sources.py](../../src/scdp/sources.py)。

消费者命令需由部署者提供；命令非零退出时不推进 cycle 活动状态，已经发布的文件仍可存在。消费者自身负责失败恢复，下一轮重试同一不可变候选。运行报告保存于工作目录 `runs/`。

单机 cycle 模板每十分钟调度一次。托管 producer 和独立消费者默认每两小时检查，实际生产启用状态见 [STATUS](../../STATUS.md)。
检查频率不是端到端时效承诺。安装步骤见[部署模板](../../deploy/README.md)，恢复与预算处理见[运维指南](../guides/operations.md)。

## 独立消费者

`python -m scdp.consumer --config CONFIG` 使用[消费模板](../../deploy/consumer.example.json)。
`repository` 指向公开数据 Release；`work` 保存活动身份、单轮回执和临时下载；`sources`、`index`、`candidates`、`recovery` 指定消费路径。
`consumerCommand` 沿用上述 argv 占位符，须负责完整验收和失败回退。`retentionCommand` 为固定受权维护命令；未配置时当前进程须能直接持有 `deploymentLock` 并管理候选。

`maxArchiveBytes` 默认 536870912、`maxUnpackedBytes` 默认 3221225472、`maxIndexBytes` 默认 2147483648、`reserveBytes` 默认 4294967296。
`consumerTimeout` 默认 7200 秒。容量公式及清理规则见[托管调度](../guides/hosted-pipeline.md#磁盘规划与保留)。
可选 `distribution` 指定已有受控分发目录；激活后更新分发指针，并校验、保留当前与前代归档。
