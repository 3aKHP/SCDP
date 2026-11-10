# 下载与阅读剧情

只查阅剧情时选择标准包，无需采集上游或安装 MCP-KB。导入包面向已有兼容 MCP-KB 环境，见[集成指南](integrations.md)。

## 下载与校验

从 [Releases](https://github.com/3aKHP/SCDP/releases) 选择数据版本，将 `scdp-phase-one.tar.gz` 和 `SHA256SUMS` 下载到同一目录。自动版本使用 `data-s<序列>-r<修订>`，按序列、修订依次比较大小；[v0.1.0](https://github.com/3aKHP/SCDP/releases/tag/v0.1.0) 为固定首版。以下命令在 Linux、具备 GNU coreutils 和 tar 的环境中执行；检查输出应为标准包 `OK`。固定首版清单另含导入包，选择标准包对应的一行：

```bash
rg '  scdp-phase-one.tar.gz$' SHA256SUMS | sha256sum --check
mkdir scdp-data
tar -xzf scdp-phase-one.tar.gz -C scdp-data
```

先确认摘要成功再执行解压，目标目录应为空。未安装 `rg` 时可用 `grep` 完成同样的筛选。摘要不匹配时停止使用并重新下载；不要修改清单来适配文件。

## 阅读

打开 `scdp-data/collection/README.md`，通过目录找到剧情。Markdown 文件保留日文、已有译文和分支证据；可使用文本编辑器阅读。缺译或歧义不表示剧情缺失，也不会自动补为机器翻译。

克隆本仓库后，在仓库根目录使用 Python 3.12+：

```bash
python3 examples/read_story.py /path/to/scdp-data
python3 examples/read_story.py /path/to/scdp-data SCRIPT_ID
```

将路径替换为解压目录，第二条使用第一条输出的真实 ID。示例只读 `collection/import-manifest.json` 与其声明的阅读文件；它不执行下载、安装或完整校验。错误目录或不存在的 ID 返回非零退出码。

## 深入使用

标准包另含 JSONL 记录、解码原件与覆盖报告，详见[包格式](../reference/package.md)。需要完整语义校验时，先按[安装说明](collect.md#环境与安装)安装 SCDP，再运行：

```bash
uv run scdp validate /path/to/scdp-data
```

成功时输出 JSON 校验摘要，失败时非零退出。命令会在默认工作目录创建运行状态，示例读取器本身不写文件。

v0.1.0 中的 `private` 字段保留初始构建和消费策略；GitHub 附件目前公开下载，消费者访问权限独立配置。原作及译文的权利、使用限制和通知入口见 [NOTICE](../../NOTICE.md)。
