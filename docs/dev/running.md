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
正常结束释放未使用部分，崩溃时保守计入预留量。越过限额的最后一个传输缓冲块仍计入累计值并停止处理。未交付给应用的传输库与代理缓存及协议开销单独预留。
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

## 元数据与完整校验

`build --metadata PATH` 可读取固定来源目录的 `album<number>.json` 与 `card-*.json`。
输入为含 `url` 和 `data` 的公开来源响应包装；每个输入记录 SHA-256。
适配器仅投影游戏角色、卡片、衣装、剧情标题与关系字段，不复制应用用户状态。
编号到剧情命名空间的匹配和说话人名称匹配标为 inferred，冲突与未匹配记录进入 metadata-report.json。

译文优先使用同篇 CSV 的原文与发生上下文；重复句无法确定位置时保留候选并标为 ambiguous。
`data/comm-story.csv` 提供独立的通用剧情词条回退，文档明确标注 fallback。
原文修订后按新原文摘要和上下文重新对齐。标题候选与完整历史缺口独立报告。

`validate` 同时核对文件摘要和全量记录 schema，重算目录指纹及选择集，核对原件帧、
每处正文的文档位置、控制证据、跳转目标、译文上下文、媒体目录引用和实体关系。
所有未识别帧字段保留原值，其字符串进入文档证据并标注 unresolved。
包内原件为解码后的精确 JSON；传输实体继续保留在采集对象库。

## MCP-KB 隔离接入

先配置目标组件根目录与其 Python 环境，通过原生 CLI 创建隔离 candidate、安装源和索引：

```bash
uv run scdp kb-stage dist/candidate --kb-root "$SCDP_KB_ROOT" --python "$SCDP_KB_PYTHON" --output work/kb-stage
```

该命令执行校验、原生 collection 打包、安装、同包重装和索引重建，并逐文档对拍安装摘要、
索引记录与非空正文行覆盖。新目标目录自动创建；同身份的已完成候选会复核复用，中断候选会保留诊断副本后重建，未知目标目录会拒绝覆盖。原生回执含本机路径，留在隔离工作目录。

通过 MCP HTTP 的读取验收使用安装了 MCP Python SDK 的环境：

```bash
"$SCDP_KB_PYTHON" -m scdp.kb_probe --url "$SCDP_KB_URL" --token-file "$SCDP_KB_TOKEN_FILE" --bundle dist/candidate --report work/kb-protocol-report.json
```

此 Python 环境还需安装 SCDP。凭证只在调用时注入，不写入报告。
校验器对全部正文文档分页读取并与源文件逐行比较，再检查各类别的原文、已有中文、检索、
chunk 读回、outline 和 grep。报告记录覆盖与摘要，不复制正文及服务地址。
这条命令是实际协议验证；隔离合成数据的通过不能替代全量真实资料和正式目标验收。

阅读文档统一使用 LF 换行；原始换行字节和格式标记保留在精确解码原件与发生位置记录中。
完整性校验仅对阅读层换行做这一规范化，其他正文字符及分支证据逐处核对。
