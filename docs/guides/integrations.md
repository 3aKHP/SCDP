# 下游集成

## 通用读取

使用标准包的 JSON／JSONL 与 Markdown，按 `scriptId` 关联剧情，按来源及原文摘要理解译文。首先核对包摘要、schema 主版本和能力范围，字段详见[包格式](../reference/package.md)与[正式契约](../../schemas/README.md)。

[Python 示例](../../examples/read_story.py)直接读取标准包；[Go 示例](../../examples/reader-go/main.go)读取合成契约对象，展示跨语言身份与依赖核对，不是标准包加载器。两者均不依赖消费者服务。

## MCP-KB

SCDP 已提供原生 collection 打包、隔离安装、索引检查及协议验证。collection ID 为 `games/shinycolors/story-bilingual`。需要部署者自行提供兼容 MCP-KB 源码、Python 环境和必要权限；本仓库不包含 MCP-KB 服务，也不提供公共查询端点。

从标准包构建隔离候选的命令见[采集指南](collect.md#mcp-kb-隔离接入)，已有导入包应按目标 MCP-KB 版本的原生安装说明操作。切换、回退和协议验收见[运维指南](operations.md)。不要把标准包直接当作原生导入包安装。

新构建的闪彩 collection 使用 Public 可见性，供已认证普通用户访问；不开放匿名服务，也不改变其他 collection 的权限。重建索引后 chunk ID 可能变化，持久引用使用文档路径和原件发生位置。

首批资料已通过一次完整生产接入验证，证据见[发布报告](../research/2026-11-10-first-release.md)；这不保证任意 MCP-KB 版本兼容。

## idolum

当前提供与 idolum Line／Episode 的合成兼容验证和消费策略准备，尚未完成生产导入。不要将 SCDP 包视作可直接导入其运行数据库的文件。角色映射、经历筛选、向量化和数据库升级由消费者负责。

后续集成将保留日文、译文来源和分支上下文；互斥路线不能被拼成同一次经历。媒体消费属于后续工作，当前包不含媒体文件。设计边界见[消费者适配](../design/04-consumers.md)。
