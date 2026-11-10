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

模板每十分钟调度一次；这是检查频率，不是上游更新到消费完成的时效承诺。安装步骤见[部署模板](../../deploy/README.md)，恢复与预算处理见[运维指南](../guides/operations.md)。
