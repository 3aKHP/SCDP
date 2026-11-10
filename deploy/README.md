# 生产调度与消费部署

GitHub 托管生产的 workflow 位于 [.github/workflows/data-pipeline.yml](../.github/workflows/data-pipeline.yml)，每两小时检查来源。
启用与检查点迁移见[托管调度指南](../docs/guides/hosted-pipeline.md)，实际生产切换状态见 [STATUS](../STATUS.md)。

- `scdp-consumer.service`、`scdp-consumer.timer`：每两小时拉取已发布标准包并调用消费适配器。
- `consumer.example.json`：消费路径、发布源、容量门槛及固定维护命令。
- `retention.py`：管理员拥有的固定回收入口，保留活动与立即前代。

## 单机更新与受控分发模板

单机模板可用于独立部署。将 `@RUN_USER@` 替换为实际运行身份后安装；该身份需读写工作与发布目录，
消费激活权限按部署者的维护命令配置。真实配置、服务目标和凭证引用保存在 Git 忽略目录。

- `scdp-cycle.service`、`scdp-cycle.timer`：每 10 分钟执行一次有锁、有预算的更新循环。
- `scdp-distribution.service`：仅监听回环地址，使用独立引用的管理员 Token 提供文本包及 Range 下载。
- `cycle.example.json`：配置结构；路径、来源身份与摘要须替换为已验证输入。

安装运行环境到 `/opt/scdp/venv`，工作与发布目录位于 `/data/scdp`，实际配置为 `/etc/scdp/cycle.json`。
先运行 `scdp cycle --config /etc/scdp/cycle.json` 并检查 `work/runs/`，完成发布与消费预验收后再启用 timer。
`consumerCommand` 是 argv 数组，可引用 `{bundle}`、`{archive}`、`{snapshotId}`；实现候选接入、协议检查及维护窗口激活。
消费者命令失败时更新状态不推进，下次执行重试同一不可变发布。消费者自身须在协议验收失败时恢复前代。

分发服务只接受 Token 文件第一条非空、非注释记录。其余 Token 无权读取私有包。
远程访问通过部署者现有 SSH 隧道或已鉴权的反向代理；该模板不会开放公网监听。
公开入口无需携带凭证参数；使用 Authorization 请求头。

运行与恢复的详细说明见[运维指南](../docs/guides/operations.md)。
