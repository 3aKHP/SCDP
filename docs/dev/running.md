# 安装、归档与离线构建

当前为一期实现中的 CLI。正式上线、自动调度与 MCP-KB 验收进度见 [STATUS](../../STATUS.md)。

## 环境与安装

需要 Python 3.12+、uv、Linux 文件锁。合成契约测试另需 Go。
在仓库根目录运行：

```bash
uv sync --locked
uv run scdp --help
uv run pytest -q
```

## 获取与恢复

真实采集只选择 `json/` 下的 JSON，排除 `json/support_skills/`。目录仍保存全部资产类型。
默认总接收预算 1 GiB、单响应及解码上限 16 MiB、并发 2、启动速率每秒 1 次、每请求最多 4 次尝试。
累计账本保存在工作目录；重启不会重置预算。失败结果至少保留 5 分钟后可再尝试。
服务端 Retry-After 超过 60 秒时保存等待时点并退出该次获取。

```bash
uv run scdp --work work/scdp discover
uv run scdp --work work/scdp fetch --limit 5
uv run scdp --work work/scdp resume
uv run scdp --work work/scdp status
```

`--limit` 用于小规模验证，不能作为全量完成证明。`resume` 默认处理完整选择集，校验并复用成功对象。
退出码 2 表示获取集合未全部成功。其他异常非零退出并保留账本及检查点。
`discover --audit` 条件复核全部分片，可在采集后对比观察身份。

HTTP 响应实体采用 identity 编码。预算计入失败与重试正文；每个并发请求先预留接收额度，
正常结束释放未使用部分，崩溃时保守计入预留量。传输库及代理缓存、协议开销不属于应用层计数。
维护页、截断、未知编码、错误响应类型与超限对象不进入 available 状态。

## 离线文本包

全部选择条目获取成功后运行：

```bash
uv run scdp --work work/scdp decode
uv run scdp --work work/scdp build --output dist/candidate
uv run scdp --work work/scdp validate dist/candidate
uv run scdp --work work/scdp package dist/candidate --output dist/candidate.tar.gz
```

已有译文归档使用 `build --translations PATH --translation-identity COMMIT` 固定独立来源。
译文更新重新构建候选，不需要重取原文。`--sequence` 与 `--revision` 显式传入发布排序。
候选目录存在时仅允许相同输入身份并复核摘要，其他身份应使用新目录。

包包含 snapshot.json、JSONL 记录、解码原件、覆盖报告及 collection/。
collection 内含 docs/、references/、collection.yaml 与 import-manifest.json；只有阅读文档纳入正文索引。
帧发生位置和精确原文摘要在标准记录保留。媒体只记录目录，包不包含媒体文件或部署数据库。

## 文件分发后端

```bash
uv run scdp publish-plan dist/candidate.tar.gz --destination data/releases
uv run scdp publish dist/candidate.tar.gz --destination data/releases
```

发布器校验包、写入不可变对象、读回摘要，再更新 latest.json；上一清单保留为 previous.json。
这是文件存储后端。远程可下载服务、调度、正式消费者安装和实际 MCP 验收由后续上线任务完成。
源包发布不代表消费者激活。现阶段不得将本地发布测试报告为 G10 通过。
