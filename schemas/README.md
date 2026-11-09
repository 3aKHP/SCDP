# 契约 v1

[contract.schema.json](../src/scdp/contract.schema.json) 是 JSON Schema 2020-12 正式字段定义。Python `scdp.contracts.validate`
另检查身份唯一性、路径安全、资产版本对应和必需依赖可用性。

- 所有对象仅接受列出的字段；`extensions`、原始帧、来源与验证对象保留扩展空间。
- `kind` 和关系类型可扩展。未知类型保留原值，消费者按 unknown 展示；未知能力不得当作已支持。
- nullable 字段明确允许 null；必填字段不得省略。语义未知使用 null 或 `unresolvedFields`。
- 稳定资产 ID 为 `enza:<logicalPath>`；剧本 ID 为去掉 `json/` 和 `.json` 的路径。
- 帧发生位置为原始 JSON Pointer，包含数组序号，不使用游戏帧 id 作唯一键。
- 编码采用 UTF-8、无 BOM。身份摘要基于键排序、无多余空白、不转义 Unicode 的 JSON；禁止 NaN。
- 内容摘要针对对应 representation 的精确字节。HTTP 请求要求 identity 编码，raw 为响应实体。
- snapshotId 是构建输入和规则身份摘要；公开版本由 releaseSequence 和 publicationRevision 排序。
  发布序号单调递增，同一身份不得覆盖。首版完整包的 baseline 固定为 null。
- 同主版本只添加兼容能力；改变必需字段、身份或字段语义时升级主版本。消费者拒绝不支持的主版本。
- 缺译、未知标题与归属允许发布但须报告；正文遗漏、获取失败、错误摘要和必需依赖缺失阻止激活。

合成实例见 [黄金样例](../tests/fixtures/golden.json)。包布局及正式发布入口将在 E2–E4 完成后固化。
