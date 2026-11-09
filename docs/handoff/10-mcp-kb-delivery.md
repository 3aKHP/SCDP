# MCP-KB 完整文本 collection 接入规程

状态：待执行。2026-11-10 只读核对了目标组件 README、kbctl.py 参数定义和服务工具入口；未修改消费者、未执行安装或线上调用。源码基点与本机位置在忽略目录维护。执行时重新核对实际版本与目标约定。

## 交付契约

SCDP 生成稳定 collection，建议 ID 为 `games/shinycolors/story-bilingual`，E0 固化后保持稳定。collection.yaml、docs/、references/ 与导入清单采用 MCP-KB 当前契约。原始附件不进入正文检索分母，正文和分支不能按长度、缺译或未知角色筛掉。

建议按稳定 scriptId 生成文档身份，可按类别组织路径。若分支使单篇过长，可分文档并生成显式目录与跳转，必须保持帧到文档映射可逆。不要套用其他游戏的裁剪阈值或 idolum 的经历政策。

源 collection 是事实文档，SQLite 索引可重建。SCDP 不向运行数据库直接写业务数据，不通过只读 MCP 服务进行导入；安装与索引使用运维 CLI。

## 接入前核对

1. 从本地映射找到目标组件，先读目标仓库规则及组件说明，记录实际代码与工作区身份。
2. 检查 collection schema、支持文本类型、单文件限制、排除规则、索引切块、全文读取分页和可见性规则。若完整性受到默认限制影响，先调整文档布局或形成消费者补丁并验证。
3. 在新的隔离 sources 目录生成候选，校验 UTF-8、路径安全、文档总数、帧映射及摘要。生成器重复执行不得覆盖未经核对的现有 collection。
4. 明确 collection 的目标可见性。组件的 public/private 访问角色不等同于原始资源可以公开分发，分发政策与实际调用身份分别验证。

## 已核对的命令顺序

以下为参数化操作模板，不表示已执行。运行环境需要 Python 及组件自身依赖。由执行 Agent 将 `SCDP_KB_ROOT`、`SCDP_STAGE_SOURCES`、`SCDP_COLLECTION_ID`、`SCDP_PACKAGE`、`SCDP_TEST_SOURCES`、`SCDP_TEST_INDEX` 和 `SCDP_SMOKE_QUERY` 设置为隔离测试值。所有目录与输出路径在本地计划记录，公开文档不填入真实部署值。

先查看当前命令帮助，确认与此模板一致，再执行：

```bash
python3 "$SCDP_KB_ROOT/kbctl.py" validate-collection --sources-root "$SCDP_STAGE_SOURCES" --collection-id "$SCDP_COLLECTION_ID" --json
python3 "$SCDP_KB_ROOT/kbctl.py" pack-collection --sources-root "$SCDP_STAGE_SOURCES" --collection-id "$SCDP_COLLECTION_ID" --output "$SCDP_PACKAGE" --json
python3 "$SCDP_KB_ROOT/kbctl.py" install-package --package "$SCDP_PACKAGE" --sources-root "$SCDP_TEST_SOURCES" --json
python3 "$SCDP_KB_ROOT/kbctl.py" rebuild-index --sources-root "$SCDP_TEST_SOURCES" --index "$SCDP_TEST_INDEX" --json
python3 "$SCDP_KB_ROOT/kbctl.py" smoke-index --index "$SCDP_TEST_INDEX" --collection "$SCDP_COLLECTION_ID" --query "$SCDP_SMOKE_QUERY" --require-hit --json
```

使用多个代表性 query 重复烟测。单条 smoke 命中不能代替全量对账，也不能替代实际 MCP 协议调用。

已核对的 `install-package --replace` 会先备份已有 collection。它只作为候选更新路径，执行前仍需核对目标和恢复入口；索引重建及切换的一致性由实际部署方案保证。不要假定源码替换会自动重建索引或自动刷新运行服务。

## 全量覆盖与实际读取

维护 scriptId、源帧位置、文档路径和文档摘要之间的清单。将生成清单与安装后的文件逐条对拍，再对照索引的 document/chunk 记录核查所有正文文档进入索引，分块合计覆盖可索引内容。目录、引用附件等排除项单列。

在 staging 对全部正文文档运行读取完整性检查。正式环境验证全部安装文件摘要及索引覆盖，并通过 MCP 读取接口分批遍历文档；有分页时持续读取到文件末尾，按返回范围还原正文或核对行范围，检测输出上限导致的遗漏。本机读取结果仅保存摘要和失败明细，避免重复传输无变化全文；完整接口验收仍需记录实际读取覆盖。

调用 `kb_list_collections`、`kb_tree`、`kb_outline`、`kb_search`、`kb_read_chunk`、`kb_cat` 和 `kb_grep` 验证发现、浏览、检索与读取。每次读取使用索引返回的真实路径及参数，禁止猜测路径后把失败归因于源数据缺失。

公开验收只给覆盖率、身份摘要和检查结果。实际服务入口、认证配置、请求回执和拓扑保留在本地工作区，生成 collection 的 imported_from 等字段也不得泄露私有路径。

## 更新与回退

用隔离环境依次验证初装、同包重装、单篇原文修订、仅译文修订、新增、源移出及回退。源移出按历史归档和 collection 范围政策处理，避免旧内容无意残留或被静默删除。

正式更新先上传并验证包，再安装候选、构建与核验索引，最后按目标环境支持的方式切换。若组件没有候选源与索引的原子切换能力，执行 Agent 必须实现或安排有明确一致性边界的维护流程，不能让源文档和索引版本长期错配。

失败恢复之前的 collection 与对应索引，复核其他 collection 未被改变，再重试新候选。只有 [G10](07-acceptance.md)通过，才声明一期完整文本消费上线。
