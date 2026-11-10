# GitHub 生产调度与消费服务器

本页说明托管管线的配置、迁移及恢复。实际生产切换状态见 [STATUS](../../STATUS.md)，架构决定见 [ADR-0005](../dev/adr/0005-hosted-producer-and-bounded-consumer.md)。

## 调度与职责

[data-pipeline.yml](../../.github/workflows/data-pipeline.yml) 在 UTC 偶数小时第 17 分钟触发，也支持手动触发。
只有 `main` 分支、仓库变量 `SCDP_PRODUCER_ENABLED=true` 时执行生产。
生产 job 在 GitHub 托管 `ubuntu-latest` 上运行，使用 `contents: write` 的 `github.token`。
无需服务器 SSH 密钥或 MCP 凭证，初次启用前必须初始化检查点。

[消费 timer](../../deploy/scdp-consumer.timer) 每两小时第 47 分钟检查完成发布的版本。
若 Runner 尚未完成，本轮维持当前版，下轮再检查。GitHub schedule 可能延迟，错峰时间不是完成保证。

## 冻结与导出

停用旧 producer timer，等当前 cycle 退出，记录活动快照、发布序列、累计字节与请求数，MCP-KB 保持运行。
在安装新代码的独立工具环境执行：

```bash
python -m scdp.runner export --config /path/to/cycle.json --output /path/to/checkpoint.tar.gz
```

导出持有工作目录锁，通过 SQLite backup 保存一致数据库，核对对象摘要后生成允许列表归档。
检查点属于私有运维资料，不上传公共 artifact 或公开 Release。
离线恢复核对历史原件、当前选择集、输入身份、累计字节和请求数与冻结基线相同。

## 初始化与启用

先提交并推送已验证代码，记录完整 commit SHA，保持 producer 变量未启用。
用具有目标仓库 contents 写入权限的 `GH_TOKEN` 执行一次初始化，Token 只通过环境注入：

```bash
python -m scdp.runner initialize --repository OWNER/REPO --commit COMMIT_SHA --checkpoint /path/to/checkpoint.tar.gz
```

专用 Draft `scdp-runner-state` 只保存检查点。初始化解包校验输入，上传后完整读回核对 SHA-256。
核对 Draft 状态及访问限制后启用变量并手动执行 workflow。首轮代码身份改变可能产生向前内容修订。
没有检查点、检查点损坏或存在未结束占用时，workflow 失败并保留原公开版本。
自动数据更新提供标准包、描述符、摘要清单及权利说明。既有固定版本的原生导入包保持可用。

## 安装消费端

使用[消费配置模板](../../deploy/consumer.example.json)，实际路径、运行身份与权限由部署者设置。
`consumerCommand` 沿用已验证的适配器，须完成候选和生产协议验证并在失败时回退。
`retentionCommand` 调用固定参数、管理员拥有的[回收入口](../../deploy/retention.py)，配置文件同样由管理员拥有。
仅授予该固定命令的权限。入口持有恢复目录锁和共享部署锁。

首次安装在 `work/active-release.json` 写入当前生产包已核验的 `snapshotId`、`releaseSequence`、`publicationRevision`。
三者必须与活动恢复记录及实际内容一致，不能以固定首版代替当前生产基线。

```bash
python -m scdp.consumer --config /path/to/consumer.json
```

首次手动拉取完成全文读取、检索、其他 collection 对账和回退验证后，再启用消费 timer。
无变化时不下载标准包或重建索引，失败不推进 `active-release.json`。
回退后先停用消费 timer，将消费状态与恢复的活动身份重新对账，避免自动重新激活被回退版本。

## 磁盘规划与保留

常驻数据为当前代与立即前代 sources/index、各自原生包、少量回执和日志。
消费工作目录不长期保存完整标准包或展开树。未知目录不自动删除，迁移遗留目录由维护者核对后清场。

令 `U` 为归档展开字节、`C` 为 collection 字节、`S` 为当前全库 sources 字节、`I` 为索引上限、`R` 为空闲保留量。
下载前要求可用空间至少为 `包大小 + R`；下载完成后，解包前要求至少为：

```text
U + S + 3 × C + 2 × I + R
```

当前代与前代已占用空间不重复计入可用空间。公式预留原生安装副本、替换备份、索引和临时数据库。
可选 `distribution` 继续维护原有受控分发，激活后更新其指针并仅保留当前与前代标准包；容量门禁额外预留 `U + 包大小` 供分发读回验证使用。
观测写入 `capacity.json`，默认 `R=4 GiB`、`I=2 GiB`。其他限额见模板。
systemd `LimitFSIZE` 与 `maxIndexBytes` 同步，约束单文件；容量门禁不等于文件系统硬配额。
共享磁盘其他任务仍可消耗预留空间，出现空间不足时保留活动版本并排查其他写入者。

自动回收只处理具有 `scdp-stage.json` 的直接候选，以及保留候选内已完成的准备副本与安装临时备份。
当前/前代内容与摘要必须完整，未结束恢复日志阻止回收。原件历史位于 Runner 检查点中。
更早代次退役后记录 `previousRetained=false`。回退到立即前代后仍可继续拉取更新，再次尝试回退至已退役数据会在改动服务前被拒绝。

## Runner 异常恢复

先停用 producer 变量，确认没有运行中的 workflow。检查 Draft 正文 `lease`，不要手工删除占用后直接重跑。
普通失败后已保存完整检查点可正常重试，Runner 丢失时必须保守处理未知下载量：

```bash
python -m scdp.runner recover --repository OWNER/REPO --directory /path/to/new-recovery-dir --expected-lease LEASE_ID
```

恢复器优先使用占用记录中已读回校验的发布前检查点，否则使用上一确认检查点。
它把尚未用尽的官方及译文授权预算全部记为已消耗，保存新检查点后释放占用；请求次数仅为已知下界。
维护者核对失败范围并显式调整原账本预算，再验证来源与已公开版本，不通过重新初始化绕过累计预算。
检查点维护必须在 producer 停用期间进行，并保留前代。

## 清场与验收

Runner 发布、生产消费及恢复验证完成后，在服务器之外保存并校验冻结检查点与必要回执。
清点旧采集工作区、历史解包树、重复上传包、过期候选和部署临时工具，核对活动及立即前代引用后回收。
仍被活动/前代引用的候选必须保留；受控分发服务如继续运行，保留其当前及前代归档。

记录清场前后磁盘可用量、物理占用、活动与前代大小、容量公式结果，实测无变化拉取及更新或隔离构建峰值。
坏包、容量不足和消费失败不得改变活动版本，正常结束不遗留完整展开树。
迁移结束后旧采集 timer 停用，生产来源获取只由 GitHub 托管 Runner 执行。
