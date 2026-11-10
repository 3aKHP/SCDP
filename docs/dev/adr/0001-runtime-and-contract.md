---
status: Accepted
superseded_by: []
---
# 0001 — Python 运行时与文本交换契约

决定日期与记录日期：2026-11-10。

## 背景

首期需可靠归档全部剧情并向 MCP-KB 提供纯文本；idolum 当前使用 Python，未来使用 Go。
本机已验证 Python 3.12、Go 和 uv 可用。已有来源解码参考为 AGPL 代码。

## 决定

生产实现采用 Python 3.12 及以上版本，依赖使用 pyproject.toml 与 uv.lock 固定。
外部交换使用 UTF-8 JSON、JSONL、Markdown 和完整 tar.gz 包；首期不发布 delta。
[正式 schema](../../../schemas/README.md)定义记录，Python 和 Go 黄金读取器验证交换身份。

原件存入 SHA-256 对象库，SQLite 仅存获取状态、账本和事件，消费者数据库独立。
请求账本跨进程重启保留；写入对象和清单使用原子替换。进程锁覆盖同一工作目录。
主清单定位遵循客户端 `load(..., false, true)`：资源哈希前有 `asset-map-` 前缀；
分片及剧情使用普通哈希定位。清单观察与内容快照各有摘要。

初始构建身份包含观察身份、译文归档摘要、来源提交、工具代码摘要和发布序号。
构建时间不参与语义身份；已存在的身份拒绝不同内容覆盖。源版本仅用于来源记录，
不宣称上游参数可固定历史内容。源码采用 AGPL-3.0-or-later，复用记录见 [来源许可](../../../THIRD_PARTY.md)。
游戏数据、译文和部署配置独立管理，首期数据分发与 MCP-KB collection 默认为 private。

公开分发的后续决定见 [ADR-0003](0003-public-distribution-and-notice.md)，运行时与契约约束继续有效。

## 后果与验证

JSONL 可逐条处理全类型目录；完整包简化恢复并增加增量发布时的传输量。
源码改动产生新的构建身份；正式发布序列仍需部署端管理。
Unix flock 与 fsync 为当前执行平台要求，Go 读取器仅使用标准库。

验证入口为 `uv run pytest -q`，包括合成 discovery → fetch → decode → build → package → publish、
两种语言的身份与依赖比较、重复句对齐和归档安全检查。
工程门禁与真实上线分别记录在 [STATUS](../../../STATUS.md)。
