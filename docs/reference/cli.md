# CLI 参考

在仓库根安装后用 `uv run scdp`，或在已安装环境使用 `scdp`。`scdp --help` 与 `scdp COMMAND --help` 列出完整参数。

全局参数位于子命令之前：`--work` 默认 `work/scdp`；`--budget` 默认 1073741824 字节；`--rate` 默认每秒 1 次。下载预算跨重启累计。

| 命令 | 输入及用途 |
|---|---|
| `discover` | 官方目录发现；`--base` 指定来源，`--audit` 复核全部分片 |
| `fetch`、`resume` | 使用当前观察获取文本；`--workers` 默认 2，`--limit` 限制数量，`--sample` 选择代表样本 |
| `status` | 输出工作目录累计状态 |
| `decode` | 从已获取原件离线解码 |
| `build` | `--output` 必填；可传 `--translations`、`--translation-identity`、`--metadata`；`--sequence` 默认 1，`--revision` 默认 0 |
| `validate` | 校验指定包目录 |
| `package` | 指定包目录及必填 `--output`，生成归档 |
| `publish-plan`、`publish` | 指定归档及必填 `--destination`，审阅或执行文件系统发布；不会自动上传 GitHub |
| `cycle` | `--config` 必填，读取独立 JSON 配置并执行一次更新 |
| `kb-stage` | 标准包及 `--kb-root`、`--python`、`--output`；可用 `--base-sources` 保留既有资料 |
| `kb-activate` | 候选目录及 `--sources`、`--index`、`--recovery`、`--service`；可指定 `--deployment-lock` |
| `kb-rollback` | `--recovery`、`--service`；可指定 `--deployment-lock` |
| `kb-recover` | `--recovery`、`--service`；可指定 `--activation-id`、`--deployment-lock` |

成功通常输出 JSON。获取结果 `complete: false` 时退出码为 2，其他异常非零退出。`fetch --limit 5` 是局部试跑，不能视为完整构建输入；`resume` 不带限制时处理全部选择集。

`cycle` 的预算与工作目录来自配置文件，不继承全局同名选项。激活、回退和恢复会操作消费者目录及服务，使用前按[运维指南](../guides/operations.md)准备隔离候选和恢复信息。
