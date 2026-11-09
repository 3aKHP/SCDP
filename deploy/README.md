# 定时更新与私有分发

本目录提供 systemd 模板。将 `@RUN_USER@` 替换为实际运行身份后安装；该身份需读写工作与发布目录，
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

运行与恢复的详细说明见[运维指南](../docs/dev/operations.md)。
