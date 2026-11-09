# 更新循环、消费切换与恢复

本页描述已实现的运维接口。实际门禁和正式部署进度见 [STATUS](../../STATUS.md)。

## 一次更新

`scdp cycle --config CONFIG` 使用工作目录互斥锁和累计账本。每轮条件读取主清单，复用经校验的分片与正文，
轮转检查指定数量的分片和正文。译文 Git 提交独立检测，新增归档使用单独的持久预算。
本地固定元数据以文件摘要检测变化。

完整输入身份包含来源观察、原件与解码摘要、目录历史、译文、元数据、代码与 schema。
输入相同时跳过获取、构建和发布，并记录 unchanged 心跳。滚动复核仍计入账本。
新候选在构建前复核全部分片，完成逐记录和逐处正文校验后打包、读回验证，再发布。
来源变化推进 releaseSequence；同一来源的内容修订或解析修复推进 publicationRevision。
每次运行的身份、起止时间、输入摘要、结果、错误与预算保存在 `work/runs/`。

配置模板和 systemd 单元见[部署入口](../../deploy/README.md)。配置中的路径为部署参数，不能直接作为公共发布元数据。

## 历史与幂等

目录历史保存 firstSeen、lastSeen、最后来源身份。清单移出标记 historical；已有可用正文继续进入历史阅读范围。
历史目录中没有正文原件的记录单列，不宣称已恢复。所有当前选择条目仍必须成功获取。

每次正文变更先保存旧获取记录，原始和解码对象保持不可变。同版本内容变化会改变构建身份。
中断后继续使用原工作目录；禁止通过新建账本绕过预算。预算耗尽先核对接收量、失败与重试，再调整同一作业的上限。

## MCP-KB 候选和切换

`kb-stage --base-sources PATH` 将既有资料复制到隔离候选，只替换目标 collection，重建完整索引，
核对其他文件的摘要与基线一致。已完成候选再次运行会复核并复用；被中断的同身份候选保留为诊断副本后重建。
未知或基线已变化的目标目录拒绝复用。

```bash
scdp kb-stage dist/candidate --kb-root "$SCDP_KB_ROOT" --python "$SCDP_KB_PYTHON" --output work/kb-candidate --base-sources "$SCDP_KB_SOURCES"
scdp kb-activate work/kb-candidate --sources "$SCDP_KB_SOURCES" --index "$SCDP_KB_INDEX" --recovery work/kb-recovery --service "$SCDP_KB_SERVICE" --deployment-lock "$SCDP_DEPLOY_LOCK"
```

切换前验证候选及活动基线。进入服务维护窗口后再次核对基线，保存旧 sources 与完整索引，
切换到已核验的候选对，再启动服务。启动或状态检查失败时恢复原对。
部署者须按目标系统要求记录维护操作，并在激活后执行实际 MCP 协议验收；协议失败时调用回退。
全程参与目标系统的共享部署锁，避免并行发布冲突。

```bash
scdp kb-rollback --recovery work/kb-recovery --service "$SCDP_KB_SERVICE" --deployment-lock "$SCDP_DEPLOY_LOCK"
```

回退校验活动指针与内容身份；已被其他发布改变的状态拒绝覆盖。回退恢复完整前代，随后重复实际协议烟测。
第一次上线的前代可以是尚未安装本 collection 的完整资料库，这也是停用首版的入口。
公开发布身份保持向前递增；消费者回退不会覆盖已发布包。

## 私有下载

分发服务从不可变发布目录提供 `latest.json`、`previous.json` 和 `<snapshotId>.tar.gz`。
请求须携带管理员 Authorization；无凭证和普通 Token 返回 401。服务支持单区间 Range，拒绝越界及任意路径。
消费端先核对公布的长度与 SHA-256，再验证归档、schema 和正文范围，之后才进入候选导入。

## 上线观察

正式启用 timer 后记录至少三次真实定时运行、无变化路径、一次受控更新、一次中断恢复、坏包拒绝与旧有效版本恢复。
定时周期仅表示检查频率；发现到消费激活的耗时以运行报告计量。

切换进程意外中断时，使用恢复目录内对应 `receipt.json` 的 activationId 执行：

```bash
scdp kb-recover --recovery work/kb-recovery --activation-id "$SCDP_ACTIVATION_ID" --service "$SCDP_KB_SERVICE" --deployment-lock "$SCDP_DEPLOY_LOCK"
```

恢复器结合日志与实际目录、索引和指针状态判断已经完成的步骤；识别不出的外部变更会拒绝覆盖。
